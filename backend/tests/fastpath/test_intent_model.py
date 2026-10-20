"""Unit tests for the instant-answer fast path. Pure ML logic -- no database
needed, unlike most of this project's test suite."""

import json

import numpy as np
import pytest

from app.fastpath.intent_model import OOS, IntentModel, choose_threshold, load_intents, load_test_queries

DATA_DIR = __import__("pathlib").Path(__file__).resolve().parent.parent.parent / "app" / "fastpath" / "data"


@pytest.fixture(scope="module")
def trained():
    data = load_intents(DATA_DIR / "faq_intents.json")
    model, report = IntentModel.train(data, verbose=False)
    return model, report


def test_training_meets_precision_target(trained):
    model, report = trained
    assert report["meets_target"]
    assert report["cv_instant_precision"] >= 0.95


def test_held_out_quality(trained):
    model, _ = trained
    m = model.evaluate(load_test_queries(DATA_DIR / "test_queries.json"))
    assert m["precision"] >= 0.90  # instant answers are almost always right
    assert m["false_accept_rate"] <= 0.10  # must almost never intercept a claims/benefits/verification question


@pytest.mark.parametrize("text,intent", [
    ("hello there", "greeting"),
    ("thanks so much", "thanks"),
    ("what's the prior authorization process", "prior_authorization_process"),
    ("how does the mail order pharmacy program work", "mail_order_pharmacy"),
])
def test_obvious_faq_questions_are_answered_instantly(trained, text, intent):
    p = trained[0].predict(text)
    assert p.accepted and p.intent == intent


@pytest.mark.parametrize("text", [
    "what's my claim status",
    "is Metformin covered",
    "find a pharmacy near zip 110001",
    "my member ID is MEM10234 date of birth May 14th 1990 zip code 110001",
    "what are my benefits",
    "",
    "   ",
    "tell me a joke",
])
def test_personalized_or_off_topic_questions_fall_through_to_llm(trained, text):
    """These must NEVER get an instant canned answer -- they need a real
    per-member/per-claim lookup (or are plain off-topic), so they have to
    reach the normal tool-calling path."""
    assert not trained[0].predict(text).accepted


def test_save_load_roundtrip(trained, tmp_path):
    model, _ = trained
    path = tmp_path / "model.joblib"
    model.save(path)
    loaded = IntentModel.load(path)
    texts = ["hello there", "what's the prior authorization process", "what's my claim status"]
    assert np.allclose(model.predict_proba(texts), loaded.predict_proba(texts))
    assert loaded.threshold == model.threshold


def test_bad_intent_files_are_rejected(tmp_path):
    def write(intents, oos=None):
        p = tmp_path / "intents.json"
        p.write_text(json.dumps({"company": "X", "intents": intents,
                                 "out_of_scope_examples": oos or ["a", "b", "c", "d", "e", "f"]}))
        return p

    with pytest.raises(ValueError, match="duplicate"):
        load_intents(write([{"id": "a", "answer": "x"}, {"id": "a", "answer": "y"}]))
    with pytest.raises(ValueError, match="answer"):
        load_intents(write([{"id": "a", "examples": ["hi"]}]))
    data = load_intents(write([{"id": "a", "answer": "x", "examples": ["hi", "hello"]},
                               {"id": "b", "answer": "y", "examples": ["bye", "ciao", "tata"]}]))
    with pytest.raises(ValueError, match="at least 3"):
        IntentModel.train(data, verbose=False)


def test_choose_threshold_prefers_coverage_at_target_precision():
    classes = ["a", "b", OOS]
    proba = np.array([[0.9, 0.05, 0.05]] * 6 + [[0.05, 0.9, 0.05]] * 2 + [[0.5, 0.3, 0.2], [0.45, 0.35, 0.2]])
    y = np.array([0] * 6 + [1] * 2 + [2, 1])
    stats = choose_threshold(proba, y, classes, target=0.95)
    assert stats.meets_target and stats.precision == 1.0
    assert 0.5 < stats.threshold <= 0.9
