"""The feedback learning loop (app.rag.learning), end to end against a real
(throwaway) tenant in the configured database. Embeddings and the LLM are
replaced with deterministic stand-ins so these run without Ollama and
assert exact outcomes."""

import hashlib
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import numpy as np
import pytest
from sqlalchemy import select

import app.conversation.agent as agent_module
import app.rag.learning as learning
import app.rag.service as rag_service
from app.config import settings
from app.conversation.orchestrator import ConversationSession
from app.db.session import tenant_session
from app.models.agent import Agent
from app.models.call import Call
from app.models.conversation_message import ConversationMessage, MessageRole
from app.models.knowledge import KnowledgeChunk, KnowledgeDocument
from app.models.learned_answer import AnswerFeedback, LearnedAnswer
from app.models.training_insight import TrainingInsight
from app.tools.context import CallContext

DIM = 768


def fake_embed(text: str) -> list[float]:
    """Bag-of-words hashed into 768 dims: shared words -> similar vectors."""
    v = np.zeros(DIM)
    for word in text.lower().replace("?", " ").replace(".", " ").split():
        v[int(hashlib.md5(word.encode()).hexdigest(), 16) % DIM] += 1.0
    return list(v / (np.linalg.norm(v) or 1.0))


@pytest.fixture(autouse=True)
def offline_ai(monkeypatch):
    monkeypatch.setattr(rag_service, "embed_query", fake_embed)
    monkeypatch.setattr(learning, "embed_query", fake_embed)

    def no_llm(*args, **kwargs):
        raise AssertionError("the LLM must not be called on this path")

    monkeypatch.setattr(agent_module, "chat_completion", no_llm)
    monkeypatch.setattr(learning, "json_completion", no_llm)


def _seed(tenant_id, question, reply, chunk_texts=(), cite_chunks=True):
    """Agent + document chunks + a call where `reply` answered `question`."""
    with tenant_session(tenant_id) as db:
        agent = Agent(tenant_id=tenant_id, name="Learner", persona="")
        db.add(agent)
        db.flush()
        doc = KnowledgeDocument(tenant_id=tenant_id, agent_id=agent.id, filename="policy.pdf")
        db.add(doc)
        db.flush()
        chunks = [
            KnowledgeChunk(tenant_id=tenant_id, agent_id=agent.id, document_id=doc.id, page=i + 1,
                           text=text, embedding=fake_embed(text))
            for i, text in enumerate(chunk_texts)
        ]
        db.add_all(chunks)
        call = Call(tenant_id=tenant_id, agent_id=agent.id, twilio_call_sid=f"CA{uuid.uuid4().hex}",
                    from_number="+10000000000", to_number="+10000000001")
        db.add(call)
        db.flush()
        t0 = datetime.now(timezone.utc)
        db.add(ConversationMessage(tenant_id=tenant_id, call_id=call.id, role=MessageRole.CUSTOMER,
                                   content=question, timestamp=t0))
        citations = [{"filename": "policy.pdf", "page": c.page, "confidence": 60.0, "chunk_id": str(c.id)}
                     for c in chunks] if cite_chunks else None
        message = ConversationMessage(tenant_id=tenant_id, call_id=call.id, role=MessageRole.ASSISTANT,
                                      content=reply, citations=citations, timestamp=t0 + timedelta(seconds=1))
        db.add(message)
        db.flush()
        return agent.id, message.id, [c.id for c in chunks]


def _feedback(tenant_id, message_id, **kwargs):
    with tenant_session(tenant_id) as db:
        message = db.execute(select(ConversationMessage).where(ConversationMessage.id == message_id)).scalar_one()
        out = learning.apply_feedback(db, tenant_id=tenant_id, user_id=None, message=message, **kwargs)
        return out.outcome, (out.learned.answer if out.learned else None)


def _chunk_scores(tenant_id, chunk_ids):
    with tenant_session(tenant_id) as db:
        rows = dict(db.execute(select(KnowledgeChunk.id, KnowledgeChunk.feedback_score)
                               .where(KnowledgeChunk.id.in_(chunk_ids))).all())
        return [rows[c] for c in chunk_ids]


def _turn(tenant_id, agent_id, utterance):
    with tenant_session(tenant_id) as db:
        session = ConversationSession("Learner", "")
        session.add_user_message(utterance)
        ctx = CallContext(db=db, tenant_id=tenant_id, agent_id=agent_id, call_id=None)
        return agent_module.run_turn(session, ctx)


def test_correction_is_learned_and_then_answered_without_the_llm(pbm_test_tenant_id):
    tid = pbm_test_tenant_id
    agent_id, msg_id, chunks = _seed(tid, "What are the pharmacy hours?", "We are open 24 hours.",
                                     ["Pharmacy hours are 9am to 5pm on weekdays."])

    outcome, answer = _feedback(tid, msg_id, helpful=False, correction="We're open 9am to 5pm on weekdays.")
    assert outcome == "corrected" and answer == "We're open 9am to 5pm on weekdays."
    assert _chunk_scores(tid, chunks) == [-1.0]  # the chunk behind the wrong answer was penalized

    # Same question, different punctuation/case: exact-match hit, no LLM.
    assert _turn(tid, agent_id, "what are the pharmacy hours") == "We're open 9am to 5pm on weekdays."
    with tenant_session(tid) as db:
        row = db.execute(select(LearnedAnswer).where(LearnedAnswer.agent_id == agent_id)).scalar_one()
        assert row.origin == "correction" and row.uses == 1
        assert db.execute(select(AnswerFeedback).where(AnswerFeedback.agent_id == agent_id)).scalar_one().helpful is False


def test_thumbs_down_reanswers_from_the_source_documents(pbm_test_tenant_id, monkeypatch):
    tid = pbm_test_tenant_id
    question = "how long does mail order delivery take"
    agent_id, msg_id, chunks = _seed(tid, question, "Mail order takes one day.",
                                     [f"{question}? Mail order delivery takes 5 business days."])
    seen = {}

    def fake_json_completion(messages, max_tokens=500):
        seen["prompt"] = messages[1]["content"]
        # sources as strings: small local models don't always emit JSON numbers
        return {"found": True, "answer": "Mail order delivery takes 5 business days.", "sources": ["1"]}

    monkeypatch.setattr(learning, "json_completion", fake_json_completion)
    outcome, answer = _feedback(tid, msg_id, helpful=False)
    assert outcome == "regenerated" and answer == "Mail order delivery takes 5 business days."
    assert "Wrong answer: Mail order takes one day." in seen["prompt"]
    assert "5 business days" in seen["prompt"]  # the source text was provided

    monkeypatch.setattr(settings, "learned_answer_min_similarity", 0.9)
    assert _turn(tid, agent_id, "how long does the mail order delivery take") == answer  # near-duplicate


def test_unanswerable_question_is_vetoed_and_flagged(pbm_test_tenant_id, monkeypatch):
    """The instant model answers this FAQ question on its own -- after a
    thumbs-down with nothing better in the documents, it must go to the LLM."""
    tid = pbm_test_tenant_id
    question = "what's the prior authorization process"
    agent_id, msg_id, _ = _seed(tid, question, "Prior auth is never needed.", [question + " is described here."],
                                cite_chunks=False)
    monkeypatch.setattr(learning, "json_completion", lambda *a, **k: {"found": False, "answer": "", "sources": []})

    outcome, answer = _feedback(tid, msg_id, helpful=False)
    assert outcome == "not_in_documents" and answer is None
    with tenant_session(tid) as db:
        assert db.execute(select(TrainingInsight).where(TrainingInsight.title.contains(question))).scalar_one()

    llm = SimpleNamespace(tool_calls=None, content="Let me look into that for you.")
    monkeypatch.setattr(agent_module, "chat_completion", lambda *a, **k: llm)
    assert _turn(tid, agent_id, question) == "Let me look into that for you."


def test_thumbs_up_caches_a_grounded_reply_and_rewards_its_chunks(pbm_test_tenant_id):
    tid = pbm_test_tenant_id
    agent_id, msg_id, chunks = _seed(tid, "do you deliver to rural areas", "Yes, we deliver everywhere in the state.",
                                     ["We deliver to every address in the state, rural areas included."])
    outcome, answer = _feedback(tid, msg_id, helpful=True)
    assert outcome == "confirmed" and answer == "Yes, we deliver everywhere in the state."
    assert _chunk_scores(tid, chunks) == [1.0]
    assert _turn(tid, agent_id, "Do you deliver to rural areas?") == "Yes, we deliver everywhere in the state."


def test_negative_feedback_reranks_near_tied_chunks_but_not_confidence(pbm_test_tenant_id, monkeypatch):
    tid = pbm_test_tenant_id
    agent_id, _, (a, b) = _seed(tid, "q", "r", ["chunk a", "chunk b"])
    q = np.eye(DIM)[0]

    def unit(cos):  # a unit vector at the given cosine similarity to q
        return list(cos * np.eye(DIM)[0] + np.sqrt(1 - cos**2) * np.eye(DIM)[1])

    with tenant_session(tid) as db:
        db.get(KnowledgeChunk, a).embedding = unit(0.80)
        db.get(KnowledgeChunk, b).embedding = unit(0.79)
    monkeypatch.setattr(rag_service, "embed_query", lambda text: list(q))

    with tenant_session(tid) as db:
        assert [r["chunk_id"] for r in rag_service.search(db, agent_id, "q", k=2)] == [a, b]
        rag_service.reward_chunks(db, [{"chunk_id": str(a)}], -3.0)
    with tenant_session(tid) as db:
        results = rag_service.search(db, agent_id, "q", k=2)
    assert [r["chunk_id"] for r in results] == [b, a]
    assert results[1]["distance"] == pytest.approx(0.20, abs=1e-6)  # raw distance (confidence input) untouched
