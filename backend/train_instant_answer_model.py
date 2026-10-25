"""Train the instant-answer fast-path model.

    python train_instant_answer_model.py
    python train_instant_answer_model.py --target 0.97   # stricter: fewer instant answers, fewer mistakes
    python train_instant_answer_model.py --feedback feedback.json   # learn from reviewer ratings

Prints how often it answers instantly and how often those answers are right, in cross-validation
and (if present) against app/fastpath/data/test_queries.json, a held-out set never used in training.

--feedback takes the JSON from GET /api/feedback/fastpath-export: instant answers reviewers marked
wrong become out-of-scope examples (sent to the LLM from now on), confirmed ones become extra
examples. Those are real caller sentences -- read the file before training on it.

A running server picks up the new model file within a few seconds; no restart needed.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

from app.fastpath.intent_model import OOS, IntentModel, load_intents, load_test_queries, merge_feedback

ROOT = Path(__file__).resolve().parent
DEFAULT_INTENTS = ROOT / "app" / "fastpath" / "data" / "faq_intents.json"
DEFAULT_TEST = ROOT / "app" / "fastpath" / "data" / "test_queries.json"
DEFAULT_OUT = ROOT / "models" / "instant_answer.joblib"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--intents", default=str(DEFAULT_INTENTS))
    ap.add_argument("--test", default=str(DEFAULT_TEST), help="held-out test questions (optional)")
    ap.add_argument("--feedback", help="reviewer ratings from GET /api/feedback/fastpath-export (optional)")
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--target", type=float, default=0.95,
                    help="required precision of instant answers in cross-validation (default 0.95)")
    args = ap.parse_args()

    data = load_intents(args.intents)
    if args.feedback:
        data, fb = merge_feedback(data, json.loads(Path(args.feedback).read_text(encoding="utf-8")))
        print(f"Feedback: +{fb['added_examples']} confirmed examples, +{fb['added_oos']} wrong answers "
              f"now out-of-scope, {fb['removed_examples']} examples dropped as marked wrong")
        if fb["unknown_intents"]:
            print(f"  ignored feedback for intents no longer in {args.intents}: {fb['unknown_intents']}")
    n_ex = sum(len(i.examples) for i in data.intents.values())
    print(f"Training on {len(data.intents)} intents, {n_ex} examples, {len(data.oos_examples)} out-of-scope examples")
    t0 = time.perf_counter()
    model, report = IntentModel.train(data, target_precision=args.target)
    print(f"Trained in {time.perf_counter() - t0:.1f}s. Picked C={report['C']:g}, "
          f"confidence threshold={report['threshold']:.2f}")

    if report["confusions"]:
        print("\nMost confused pairs in cross-validation (add more distinct examples to separate them):")
        for c in report["confusions"]:
            print(f"  {c['true']:<28} -> {c['predicted']:<28} x{c['count']}")

    if args.test and Path(args.test).is_file():
        queries = load_test_queries(args.test)
        m = model.evaluate(queries)
        n_in = sum(1 for _, lab in queries if lab != OOS)
        n_oos = len(queries) - n_in
        print(f"\nHeld-out test ({len(queries)} questions never seen in training: {n_in} FAQ, {n_oos} out-of-scope)")
        print(f"  instant answers:              {m['answered']}  ({m['wrong']} wrong)")
        print(f"  precision of instant answers: {m['precision']:.1%}")
        print(f"  FAQ questions answered instantly: {m['coverage']:.1%}")
        print(f"  out-of-scope wrongly answered:    {m['false_accept_rate']:.1%}")
        wrong = [x for x in m["mistakes"] if x["kind"].startswith("WRONG")]
        slow = [x for x in m["mistakes"] if not x["kind"].startswith("WRONG")]
        if wrong:
            print("\n  Wrong instant answers (fix by adding examples / out-of-scope examples):")
            for x in wrong:
                print(f"    '{x['text']}'  expected {x['expected']}, got {x['got']} ({x['confidence']:.2f})")
        if slow:
            print("\n  FAQ questions sent to the LLM instead (correct but slower):")
            for x in slow:
                print(f"    '{x['text']}'  expected {x['expected']} (best guess {x['got']} {x['confidence']:.2f})")
    else:
        print("\nNo held-out test file found -- only cross-validation numbers above are real evidence here.")

    # Write-then-rename so a running server never loads a half-written file.
    out = Path(args.out)
    tmp = out.with_name(out.name + ".tmp")
    model.save(tmp)
    os.replace(tmp, out)
    print(f"\nSaved model to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
