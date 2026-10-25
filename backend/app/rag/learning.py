"""Learning from reviewer feedback: the reinforcement loop for answers.

A supervisor rates an assistant reply in a call transcript (thumbs up/down,
optionally typing the right answer). That rating is a reward signal applied
at three levels:

1. Retrieval. Every chunk the reply was grounded in gets +1 (helpful) or -1
   (wrong) on KnowledgeChunk.feedback_score, which re-ranks future searches
   (see rag.service.search). Chunks behind bad answers sink and chunks
   behind good ones rise.
2. Answers. A wrong reply is fixed at once. The reviewer's own correction
   is used if they typed one. Otherwise the question is re-answered strictly
   from the source documents, with the wrong answer shown to the LLM as what
   not to say. The fix is stored as a LearnedAnswer, and a confirmed good
   grounded reply is stored too.
3. Speed. agent.run_turn checks LearnedAnswers before the LLM, so a learned
   question is answered correctly in milliseconds instead of seconds, for
   every later caller who asks it.

If the documents can't answer the question, nothing is invented. The
question is vetoed (it always takes the full LLM path, never a fast canned
answer), and a "missing knowledge" Training Center insight is raised so
someone uploads the document that would answer it.

Thumbs on instant-model answers (app/fastpath) can also be exported via
fastpath_feedback_export(). train_instant_answer_model.py --feedback folds
them into the next retrain.
"""

from __future__ import annotations

import json
import logging
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app import confidence_service
from app.config import settings
from app.fastpath.textnorm import normalize
from app.llm.client import json_completion
from app.models.call import Call
from app.models.conversation_message import ConversationMessage, MessageRole
from app.models.learned_answer import AnswerFeedback, LearnedAnswer
from app.models.training_insight import InsightCategory, InsightStatus, TrainingInsight
from app.rag import service as rag_service
from app.rag.embeddings import embed_query

logger = logging.getLogger("learning")

REGENERATE_K = 4

REGENERATE_PROMPT = """A reviewer marked an AI phone agent's answer to a caller as WRONG. \
Write the correct answer using ONLY the numbered sources provided.

Rules:
- Use only facts stated in the sources. Never use general knowledge or guess.
- If the sources do not clearly answer the question, set "found" to false.
- The answer is spoken on a phone call: at most 3 short sentences, plain words, no lists or markdown.
- Do not repeat the mistake in the wrong answer.

Respond with ONLY a JSON object:
{"found": true | false, "answer": "the corrected answer", "sources": [numbers of the sources you used]}"""


# --------------------------------------------------------------------------- lookup


@dataclass
class LearnedHit:
    id: uuid.UUID
    answer: str | None  # None = vetoed: skip every fast path for this question
    citations: list[dict] | None
    similarity: float


# Per-agent snapshot of active learned answers keyed by normalized question,
# so the exact-match check that runs on EVERY turn costs a dict lookup, not
# a DB round-trip. Writes in this process invalidate immediately; the TTL
# bounds staleness from writes made by other processes.
_CACHE_TTL_S = 30.0
_cache: dict[uuid.UUID, tuple[float, dict[str, LearnedHit], bool]] = {}
_cache_lock = threading.Lock()


def invalidate(agent_id: uuid.UUID) -> None:
    with _cache_lock:
        _cache.pop(agent_id, None)


def _snapshot(db: Session, agent_id: uuid.UUID) -> tuple[dict[str, LearnedHit], bool]:
    now = time.monotonic()
    with _cache_lock:
        cached = _cache.get(agent_id)
    if cached is not None and now - cached[0] < _CACHE_TTL_S:
        return cached[1], cached[2]

    rows = db.execute(
        select(
            LearnedAnswer.id,
            LearnedAnswer.question_norm,
            LearnedAnswer.answer,
            LearnedAnswer.citations,
            LearnedAnswer.question_embedding.is_not(None),
        ).where(LearnedAnswer.agent_id == agent_id, LearnedAnswer.active.is_(True))
    ).all()
    by_norm = {norm: LearnedHit(id_, answer, citations, 1.0) for id_, norm, answer, citations, _ in rows}
    has_embeddings = any(has_emb and answer for _, _, answer, _, has_emb in rows)
    with _cache_lock:
        _cache[agent_id] = (now, by_norm, has_embeddings)
    return by_norm, has_embeddings


def lookup_exact(db: Session, agent_id: uuid.UUID, utterance: str) -> LearnedHit | None:
    """Same question after normalization (case, punctuation, numbers). No
    network call -- safe to run before even the instant-answer model."""
    norm = normalize(utterance)
    if not norm:
        return None
    by_norm, _ = _snapshot(db, agent_id)
    return by_norm.get(norm)


def lookup_similar(db: Session, agent_id: uuid.UUID, utterance: str) -> LearnedHit | None:
    """Near-identical rewording of a learned question (embedding similarity
    >= settings.learned_answer_min_similarity). Costs one embedding call,
    so it's skipped entirely for agents with nothing learned yet."""
    _, has_embeddings = _snapshot(db, agent_id)
    if not has_embeddings or not normalize(utterance):
        return None
    try:
        vector = embed_query(utterance)
    except Exception:
        logger.warning("Embedding unavailable; skipping learned-answer similarity lookup", exc_info=True)
        return None

    distance = LearnedAnswer.question_embedding.cosine_distance(vector)
    row = db.execute(
        select(LearnedAnswer.id, LearnedAnswer.answer, LearnedAnswer.citations, distance.label("distance"))
        .where(
            LearnedAnswer.agent_id == agent_id,
            LearnedAnswer.active.is_(True),
            LearnedAnswer.answer.is_not(None),
            LearnedAnswer.question_embedding.is_not(None),
        )
        .order_by(distance)
        .limit(1)
    ).first()
    if row is None:
        return None
    similarity = 1 - float(row.distance)
    if similarity < settings.learned_answer_min_similarity:
        return None
    return LearnedHit(row.id, row.answer, row.citations, similarity)


def record_use(db: Session, hit: LearnedHit) -> None:
    db.execute(update(LearnedAnswer).where(LearnedAnswer.id == hit.id).values(uses=LearnedAnswer.uses + 1))


# --------------------------------------------------------------------------- feedback


@dataclass
class FeedbackOutcome:
    feedback_id: uuid.UUID
    # confirmed | reinforced | corrected | regenerated | not_in_documents | recorded
    outcome: str
    message: str
    learned: LearnedAnswer | None = None


def _has_chunk_citations(citations: list[dict] | None) -> bool:
    return any(isinstance(c, dict) and c.get("chunk_id") for c in citations or [])


def _question_for(db: Session, message: ConversationMessage) -> str | None:
    """The caller utterance this reply answered: the latest customer message
    before it in the same call."""
    return db.execute(
        select(ConversationMessage.content)
        .where(
            ConversationMessage.call_id == message.call_id,
            ConversationMessage.role == MessageRole.CUSTOMER,
            ConversationMessage.timestamp <= message.timestamp,
        )
        .order_by(ConversationMessage.timestamp.desc())
        .limit(1)
    ).scalar_one_or_none()


def _learned_row_for_reply(db: Session, agent_id: uuid.UUID, reply: str) -> LearnedAnswer | None:
    return db.execute(
        select(LearnedAnswer).where(LearnedAnswer.agent_id == agent_id, LearnedAnswer.answer == reply).limit(1)
    ).scalar_one_or_none()


def _embed_or_none(question: str) -> list[float] | None:
    try:
        return embed_query(question)
    except Exception:
        logger.warning("Embedding unavailable; learned answer will only match exact rewordings", exc_info=True)
        return None


def _upsert_learned(
    db: Session,
    tenant_id: uuid.UUID,
    agent_id: uuid.UUID,
    question: str,
    answer: str | None,
    citations: list[dict] | None,
    origin: str,
) -> LearnedAnswer:
    norm = normalize(question)
    row = db.execute(
        select(LearnedAnswer).where(LearnedAnswer.agent_id == agent_id, LearnedAnswer.question_norm == norm)
    ).scalar_one_or_none()
    now = datetime.now(timezone.utc)
    if row is None:
        row = LearnedAnswer(
            tenant_id=tenant_id,
            agent_id=agent_id,
            question=question,
            question_norm=norm,
            question_embedding=_embed_or_none(question),
            positive=0,
            negative=0,
            uses=0,
            created_at=now,
        )
        db.add(row)
    # A new answer starts its track record from scratch.
    row.answer = answer
    row.citations = citations
    row.origin = origin
    row.positive = 0
    row.negative = 0
    row.active = True
    row.updated_at = now
    db.flush()
    invalidate(agent_id)
    return row


def regenerate_from_source(
    db: Session, agent_id: uuid.UUID, question: str, wrong_answer: str
) -> tuple[str, list[dict]] | None:
    """Re-answer `question` strictly from the agent's documents. None if the
    documents don't contain a confident answer -- never a guess."""
    results = rag_service.search(db, agent_id, question, k=REGENERATE_K)
    if confidence_service.evaluate(results).band == confidence_service.ConfidenceBand.LOW:
        return None

    sources = []
    for i, r in enumerate(results, start=1):
        cite = r["filename"] + (f" p.{r['page']}" if r["page"] else "")
        sources.append(f"[{i}] ({cite}) {r['text']}")
    messages = [
        {"role": "system", "content": REGENERATE_PROMPT},
        {
            "role": "user",
            "content": f"Question: {question}\nWrong answer: {wrong_answer}\n\nSources:\n" + "\n\n".join(sources),
        },
    ]
    # Small local models occasionally pad JSON-mode output with whitespace
    # until max_tokens cuts it off mid-string (seen live with qwen3:1.7b).
    # Retry once; a second failure raises -- a malfunction must never be
    # mistaken for "the documents don't say", which would veto the question.
    try:
        data = json_completion(messages, max_tokens=500)
    except json.JSONDecodeError:
        data = json_completion(messages, max_tokens=500)
    answer = str(data.get("answer") or "").strip()
    used = sorted({n for n in map(_as_int, data.get("sources") or []) if n is not None and 1 <= n <= len(results)})
    if not data.get("found") or not answer or not used:
        return None
    if normalize(answer) == normalize(wrong_answer):
        return None  # the model just repeated the mistake
    return answer, rag_service.build_citations([results[n - 1] for n in used])


def _as_int(value) -> int | None:
    try:
        return int(str(value).strip().strip("[]"))
    except ValueError:
        return None


def _flag_missing_knowledge(db: Session, tenant_id: uuid.UUID, question: str) -> None:
    title = f"Documents don't answer: {question}"[:255]
    existing = db.execute(
        select(TrainingInsight).where(TrainingInsight.title == title, TrainingInsight.status == InsightStatus.NEW)
    ).scalar_one_or_none()
    if existing is not None:
        existing.supporting_call_count += 1
        return
    db.add(
        TrainingInsight(
            tenant_id=tenant_id,
            category=InsightCategory.MISSING_KNOWLEDGE,
            title=title,
            description=(
                "A reviewer marked the AI's answer to this question as wrong, and the uploaded documents "
                "don't contain a confident answer to re-learn from. Upload a document that covers it."
            ),
            supporting_call_count=1,
            status=InsightStatus.NEW,
        )
    )


def apply_feedback(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID | None,
    message: ConversationMessage,
    helpful: bool,
    correction: str | None = None,
    question: str | None = None,
) -> FeedbackOutcome:
    if message.role != MessageRole.ASSISTANT:
        raise ValueError("Only assistant replies can be rated")
    agent_id = db.execute(select(Call.agent_id).where(Call.id == message.call_id)).scalar_one_or_none()
    if agent_id is None:
        raise ValueError("This call has no agent to learn into")
    question = (question or "").strip() or _question_for(db, message)
    if not question:
        raise ValueError("No caller question precedes this reply")
    correction = (correction or "").strip() or None
    source = message.message_type or "text"

    feedback = AnswerFeedback(
        tenant_id=tenant_id,
        agent_id=agent_id,
        message_id=message.id,
        user_id=user_id,
        question=question,
        answer=message.content,
        source=source,
        helpful=helpful,
        correction=correction,
        created_at=datetime.now(timezone.utc),
    )
    # Added only in done(), once learned_answer_id is known: the table is
    # append-only (INSERT, no UPDATE grant), so it must be written once.

    # 1. Retrieval reward on the exact chunks this reply was grounded in.
    rag_service.reward_chunks(db, message.citations, +1.0 if helpful else -1.0)

    used_row = _learned_row_for_reply(db, agent_id, message.content) if source == "learned" else None

    def done(outcome: str, text: str, learned: LearnedAnswer | None = None) -> FeedbackOutcome:
        feedback.learned_answer_id = learned.id if learned is not None else None
        db.add(feedback)
        db.flush()
        return FeedbackOutcome(feedback.id, outcome, text, learned)

    # 2. Answer-level learning.
    if helpful:
        if used_row is not None:
            used_row.positive += 1
            return done("reinforced", "Thanks — this learned answer's score went up.", used_row)
        if source == "text" and _has_chunk_citations(message.citations):
            learned = _upsert_learned(db, tenant_id, agent_id, question, message.content, message.citations, "confirmed")
            return done("confirmed", "Saved — this question will now be answered instantly with this reply.", learned)
        return done("recorded", "Thanks — feedback recorded.")

    if used_row is not None:
        used_row.negative += 1
        if used_row.negative > used_row.positive:
            used_row.active = False
            invalidate(agent_id)

    if correction:
        learned = _upsert_learned(db, tenant_id, agent_id, question, correction, None, "correction")
        return done("corrected", "Learned — your correction will be used from the next call on.", learned)

    regenerated = regenerate_from_source(db, agent_id, question, message.content)
    if regenerated is not None:
        answer, citations = regenerated
        learned = _upsert_learned(db, tenant_id, agent_id, question, answer, citations, "regenerated")
        return done("regenerated", "Re-answered from your documents — this answer will be used from now on.", learned)

    veto = _upsert_learned(db, tenant_id, agent_id, question, None, None, "unanswered")
    _flag_missing_knowledge(db, tenant_id, question)
    return done(
        "not_in_documents",
        "Your documents don't answer this, so it won't get a fast answer again — flagged as missing "
        "knowledge in the Training Center. You can also type the correct answer.",
        veto,
    )


# --------------------------------------------------------------------------- fast-path export


def fastpath_feedback_export(db: Session, intent_answers: dict[str, str]) -> dict:
    """Ratings of instant-model answers, shaped for
    `train_instant_answer_model.py --feedback`. A wrong instant answer
    becomes an out-of-scope example (the safe fix: send it to the LLM). A
    confirmed one becomes an extra example of its intent. `intent_answers`
    maps intent id -> canned answer text, to recover which intent fired."""
    by_answer = {answer: intent for intent, answer in intent_answers.items()}
    rows = db.execute(
        select(AnswerFeedback.question, AnswerFeedback.answer, AnswerFeedback.helpful)
        .where(AnswerFeedback.source == "instant")
        .order_by(AnswerFeedback.created_at)
    ).all()
    examples: dict[str, list[str]] = {}
    oos: list[str] = []
    for question, answer, helpful in rows:
        if not helpful:
            oos.append(question)
        elif answer in by_answer:
            examples.setdefault(by_answer[answer], []).append(question)
    return {"examples": examples, "out_of_scope_examples": oos}
