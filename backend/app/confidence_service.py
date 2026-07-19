import enum
from dataclasses import dataclass

# "Answers only when confidence is high, uses verified sources, and
# escalates uncertain cases" — the three bands below are the whole policy.
HIGH_THRESHOLD = 90.0
LOW_THRESHOLD = 70.0


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
    unnormalized vectors but practically ~[0, 1.3] for OpenAI text
    embeddings. Convert to a 0-100 confidence score."""
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
