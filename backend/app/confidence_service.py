import enum
from dataclasses import dataclass

# "Answers only when confidence is high, uses verified sources, and
# escalates uncertain cases" — the three bands below are the whole policy.
#
# Recalibrated 2026-08-22 against nomic-embed-text (see score_from_distance's
# note below): a real 9-pair sample against one uploaded document (6 known-
# relevant queries, 3 known-irrelevant) scored relevant matches at 56.8-63.7%
# and irrelevant queries at 47.6-49.8% -- a real gap, just sitting entirely
# under the old 70/90 cutoffs inherited from Azure OpenAI's embeddings, which
# caused every query (relevant or not) to be treated as LOW/unanswerable.
# LOW_THRESHOLD=53 sits in that observed gap. HIGH_THRESHOLD=75 is set above
# every score observed so far -- deliberately conservative, since 9 pairs
# from 1 document is nowhere near enough to say what a *genuinely* HIGH-
# confidence match looks like for this model. This is NOT the calibration
# study docs/validation/evidence_requirements.md calls for (that needs a
# larger, varied, labeled sample) -- it's a real-data correction of cutoffs
# that were provably wrong, not a validated final answer. Revisit as more
# real query/document pairs accumulate.
HIGH_THRESHOLD = 75.0
LOW_THRESHOLD = 53.0


class ConfidenceBand(str, enum.Enum):
    HIGH = "high"  # >=90: answer directly
    MEDIUM = "medium"  # 70-89: answer, but cite the source and hedge
    LOW = "low"  # <70: don't answer from this — escalate


def band_for(score: float) -> ConfidenceBand:
    if score >= HIGH_THRESHOLD:
        return ConfidenceBand.HIGH
    if score >= LOW_THRESHOLD:
        return ConfidenceBand.MEDIUM
    return ConfidenceBand.LOW


def score_from_distance(distance: float) -> float:
    """pgvector cosine_distance is 1 - cosine_similarity, in [0, 2] for
    unnormalized vectors. Convert to a 0-100 confidence score.

    See the recalibration note on HIGH_THRESHOLD/LOW_THRESHOLD above --
    those cutoffs are fit to nomic-embed-text's actual (lower, narrower)
    similarity range from a small real sample, not assumed."""
    similarity = 1 - distance
    return round(max(0.0, min(1.0, similarity)) * 100, 1)


@dataclass
class ConfidenceResult:
    score: float
    band: ConfidenceBand
    citation: str | None


def evaluate(search_results: list[dict]) -> ConfidenceResult:
    """Score confidence off the single best-matching chunk — a caller's
    question is answered by its best source, not diluted by weaker ones
    also returned in the top-k."""
    if not search_results:
        return ConfidenceResult(score=0.0, band=ConfidenceBand.LOW, citation=None)

    top = search_results[0]
    score = score_from_distance(top["distance"])
    citation = top["filename"] + (f" (page {top['page']})" if top.get("page") else "")
    return ConfidenceResult(score=score, band=band_for(score), citation=citation)


_DIRECTIVES = {
    ConfidenceBand.HIGH: "Confidence is HIGH ({score}%). Answer directly and confidently from this information.",
    ConfidenceBand.MEDIUM: (
        "Confidence is MEDIUM ({score}%). Answer from this information, but tell the caller "
        "you're referencing {citation} and it's worth confirming."
    ),
    ConfidenceBand.LOW: (
        "Confidence is LOW ({score}%) — no reliable match was found. Do NOT answer from the "
        "knowledge base. Apologize, say you don't have a confident answer, and call escalate_to_human."
    ),
}


def build_directive(result: ConfidenceResult) -> str:
    return _DIRECTIVES[result.band].format(score=result.score, citation=result.citation or "the source document")
