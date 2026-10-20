"""The instant-answer model: a fast pre-check before the LLM/tool-calling loop.

What it is: TF-IDF features (character n-grams + word n-grams) feeding a logistic-regression
classifier. It is tiny, trains in seconds, and predicts in about a millisecond with no LLM call.
Character n-grams make it robust to Hinglish spelling variations ("kahan" / "kaha"), typos and
speech-to-text mistakes.

How it stays safe: during training it runs cross-validation and picks a confidence threshold
so that, on questions it has never seen, its instant answers are right at least
`target_precision` of the time (default 95%). Anything below the threshold is NOT answered
instantly - it falls through to the normal LLM/tool-calling path. Critically, every question
that needs a real per-member/per-claim lookup (claims, benefits, formulary, pharmacy lookup,
identity verification) belongs in `out_of_scope_examples`, not as an answerable intent - this
model only ever answers static, non-personalized facts and generic conversational turns.
"""

from __future__ import annotations

import json
import time
import warnings
from dataclasses import asdict, dataclass, field
from pathlib import Path

import joblib
import numpy as np
import sklearn
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedKFold
from sklearn.pipeline import FeatureUnion, Pipeline

from .textnorm import normalize

OOS = "_out_of_scope"  # label for "do not answer instantly, send to the LLM"


@dataclass
class Intent:
    id: str
    answer: str = ""
    end_call: bool = False
    examples: list[str] = field(default_factory=list)


@dataclass
class Prediction:
    intent: str
    confidence: float
    accepted: bool  # True = confident enough to answer instantly
    runner_up: str
    runner_up_confidence: float


@dataclass
class IntentData:
    company: str
    intents: dict[str, Intent]
    oos_examples: list[str]


def load_intents(path: str | Path) -> IntentData:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    intents: dict[str, Intent] = {}
    for item in raw.get("intents", []):
        intent = Intent(
            id=item["id"],
            answer=item.get("answer", ""),
            end_call=bool(item.get("end_call", False)),
            examples=[e for e in item.get("examples", []) if str(e).strip()],
        )
        if intent.id == OOS:
            raise ValueError(f"'{OOS}' is reserved; put those sentences in out_of_scope_examples")
        if intent.id in intents:
            raise ValueError(f"duplicate intent id: {intent.id}")
        if not intent.answer:
            raise ValueError(f"intent '{intent.id}' needs an 'answer'")
        intents[intent.id] = intent
    return IntentData(raw.get("company", ""), intents, list(raw.get("out_of_scope_examples", [])))


def load_test_queries(path: str | Path) -> list[tuple[str, str]]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    return [(q, label) for q, label in raw.get("queries", [])]


def build_pipeline(C: float) -> Pipeline:
    features = FeatureUnion([
        ("char", TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 5), sublinear_tf=True)),
        ("word", TfidfVectorizer(analyzer="word", ngram_range=(1, 2), sublinear_tf=True,
                                 token_pattern=r"(?u)\b\w+\b")),
    ])
    clf = LogisticRegression(C=C, max_iter=5000, class_weight="balanced")
    return Pipeline([("features", features), ("clf", clf)])


@dataclass
class ThresholdStats:
    threshold: float
    precision: float  # of instant answers, how many were right
    coverage: float  # of real FAQ questions, how many got an instant answer
    false_accept_rate: float  # of out-of-scope questions, how many wrongly got an instant answer
    meets_target: bool


def evaluate_at(proba: np.ndarray, y: np.ndarray, classes: list[str], threshold: float) -> dict:
    oos_idx = classes.index(OOS)
    pred = proba.argmax(axis=1)
    conf = proba.max(axis=1)
    answered = (pred != oos_idx) & (conf >= threshold)
    correct = answered & (pred == y)
    in_scope = y != oos_idx
    n_answered = int(answered.sum())
    return {
        "precision": float(correct.sum() / n_answered) if n_answered else 1.0,
        "coverage": float((answered & in_scope).sum() / max(1, in_scope.sum())),
        "correct_coverage": float((correct & in_scope).sum() / max(1, in_scope.sum())),
        "false_accept_rate": float((answered & ~in_scope).sum() / max(1, (~in_scope).sum())),
        "answered": n_answered,
        "wrong": int(n_answered - correct.sum()),
    }


def choose_threshold(proba: np.ndarray, y: np.ndarray, classes: list[str], target: float) -> ThresholdStats:
    """Lowest threshold whose precision (and that of every higher threshold) is >= target."""
    grid = np.round(np.arange(0.95, 0.049, -0.01), 2)
    chosen = None
    best_precision, best_t = -1.0, float(grid[0])
    for t in grid:  # from strict to loose
        p = evaluate_at(proba, y, classes, float(t))["precision"]
        if p > best_precision:
            best_precision, best_t = p, float(t)
        if p >= target:
            chosen = float(t)
        else:
            break  # precision dropped below target: stop loosening
    meets = chosen is not None
    t = chosen if meets else best_t
    m = evaluate_at(proba, y, classes, t)
    return ThresholdStats(t, m["precision"], m["coverage"], m["false_accept_rate"], meets)


class IntentModel:
    def __init__(self, pipeline: Pipeline, threshold: float, data: IntentData, meta: dict):
        self.pipeline = pipeline
        self.threshold = threshold
        self.company = data.company
        self.intents = data.intents
        self.oos_examples = data.oos_examples
        self.meta = meta
        self.classes: list[str] = list(pipeline.classes_)

    # ------------------------------------------------------------------ predict
    def predict_proba(self, texts: list[str]) -> np.ndarray:
        return self.pipeline.predict_proba([normalize(t) for t in texts])

    def predict(self, text: str) -> Prediction:
        if not normalize(text):
            return Prediction(OOS, 0.0, False, OOS, 0.0)
        proba = self.predict_proba([text])[0]
        order = np.argsort(proba)[::-1]
        best, second = self.classes[order[0]], self.classes[order[1]]
        conf = float(proba[order[0]])
        accepted = best != OOS and conf >= self.threshold
        return Prediction(best, conf, accepted, second, float(proba[order[1]]))

    # ------------------------------------------------------------------ train
    @classmethod
    def train(cls, data: IntentData, target_precision: float = 0.95,
              c_grid: tuple[float, ...] = (3.0, 10.0, 30.0, 100.0), n_splits: int = 5,
              seed: int = 13, verbose: bool = True) -> tuple["IntentModel", dict]:
        texts, labels = [], []
        for intent in data.intents.values():
            for ex in intent.examples:
                texts.append(normalize(ex))
                labels.append(intent.id)
        for ex in data.oos_examples:
            texts.append(normalize(ex))
            labels.append(OOS)

        counts = {lab: labels.count(lab) for lab in set(labels)}
        if OOS not in counts or counts[OOS] < 5:
            raise ValueError("add at least 5 out_of_scope_examples (things that must go to the LLM)")
        too_few = [lab for lab, n in counts.items() if n < 3]
        if too_few:
            raise ValueError(f"these intents need at least 3 examples (8-20 recommended): {too_few}")
        thin = [lab for lab, n in counts.items() if n < 8 and lab != OOS]
        if thin and verbose:
            print(f"  note: few examples for {thin}; aim for 8-20 each for better coverage")

        X = np.array(texts, dtype=object)
        classes = sorted(counts)
        y = np.array([classes.index(lab) for lab in labels])
        k = max(2, min(n_splits, min(counts.values())))
        skf = StratifiedKFold(n_splits=k, shuffle=True, random_state=seed)

        results = []
        for C in c_grid:
            oof = np.zeros((len(X), len(classes)))
            for tr, te in skf.split(X, y):
                pipe = build_pipeline(C).fit(X[tr], y[tr])
                proba = pipe.predict_proba(X[te])
                oof[np.ix_(te, pipe.classes_)] = proba
            stats = choose_threshold(oof, y, classes, target_precision)
            acc = float((oof.argmax(axis=1) == y).mean())
            results.append((C, stats, acc, oof))
            if verbose:
                print(f"  C={C:<6g} cv-accuracy={acc:.1%}  threshold={stats.threshold:.2f}  "
                      f"instant-precision={stats.precision:.1%}  coverage={stats.coverage:.1%}  "
                      f"oos-false-accept={stats.false_accept_rate:.1%}")

        # Best = meets precision target with the highest coverage (ties -> higher accuracy).
        results.sort(key=lambda r: (r[1].meets_target, r[1].coverage if r[1].meets_target else r[1].precision, r[2]),
                     reverse=True)
        C, stats, acc, oof = results[0]
        if not stats.meets_target:
            warnings.warn(f"could not reach {target_precision:.0%} precision in cross-validation "
                          f"(best {stats.precision:.1%}); add more examples and out-of-scope examples")

        pipeline = build_pipeline(C).fit(X, np.array(labels, dtype=object))
        report = {
            "C": C,
            "threshold": stats.threshold,
            "cv_accuracy": acc,
            "cv_instant_precision": stats.precision,
            "cv_coverage": stats.coverage,
            "cv_oos_false_accept": stats.false_accept_rate,
            "meets_target": stats.meets_target,
            "target_precision": target_precision,
            "n_examples": len(X),
            "n_intents": len(classes) - 1,
            "confusions": _top_confusions(oof, y, classes),
        }
        meta = {
            "trained_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "sklearn_version": sklearn.__version__,
            "report": report,
        }
        return cls(pipeline, stats.threshold, data, meta), report

    # ------------------------------------------------------------------ evaluate
    def evaluate(self, queries: list[tuple[str, str]]) -> dict:
        unknown = sorted({lab for _, lab in queries if lab not in self.classes})
        if unknown:
            raise ValueError(f"test file uses unknown intents: {unknown}")
        proba = self.predict_proba([q for q, _ in queries])
        y = np.array([self.classes.index(lab) for _, lab in queries])
        m = evaluate_at(proba, y, self.classes, self.threshold)
        mistakes = []
        for (q, lab), p in zip(queries, proba):
            best = self.classes[int(p.argmax())]
            conf = float(p.max())
            answered = best != OOS and conf >= self.threshold
            if answered and best != lab:
                mistakes.append({"text": q, "expected": lab, "got": best, "confidence": round(conf, 3), "kind": "WRONG instant answer"})
            elif not answered and lab != OOS:
                mistakes.append({"text": q, "expected": lab, "got": best, "confidence": round(conf, 3), "kind": "sent to LLM (ok, just slower)"})
        m["n"] = len(queries)
        m["mistakes"] = mistakes
        return m

    # ------------------------------------------------------------------ save / load
    def save(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump({
            "pipeline": self.pipeline,
            "threshold": self.threshold,
            "company": self.company,
            "intents": {k: asdict(v) for k, v in self.intents.items()},
            "oos_examples": self.oos_examples,
            "meta": self.meta,
        }, path)

    @classmethod
    def load(cls, path: str | Path) -> "IntentModel":
        # joblib uses pickle: only load model files you created yourself.
        blob = joblib.load(path)
        data = IntentData(blob["company"], {k: Intent(**v) for k, v in blob["intents"].items()}, blob["oos_examples"])
        return cls(blob["pipeline"], blob["threshold"], data, blob["meta"])


def _top_confusions(oof: np.ndarray, y: np.ndarray, classes: list[str], top: int = 8) -> list[dict]:
    pred = oof.argmax(axis=1)
    pairs: dict[tuple[str, str], int] = {}
    for yi, pi in zip(y, pred):
        if yi != pi:
            key = (classes[yi], classes[pi])
            pairs[key] = pairs.get(key, 0) + 1
    ranked = sorted(pairs.items(), key=lambda kv: kv[1], reverse=True)[:top]
    return [{"true": a, "predicted": b, "count": n} for (a, b), n in ranked]
