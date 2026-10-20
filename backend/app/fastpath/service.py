"""Lazily loads the trained instant-answer model for app/conversation/agent.py.

If no model has been trained yet (models/instant_answer.joblib doesn't exist), every turn just
falls through to the normal LLM/tool-calling path -- this is a pure speed optimization, never a
hard dependency.
"""

from __future__ import annotations

import logging
from pathlib import Path

from app.fastpath.intent_model import IntentModel

logger = logging.getLogger("fastpath")

MODEL_PATH = Path(__file__).resolve().parent.parent.parent / "models" / "instant_answer.joblib"

_model: IntentModel | None = None
_load_attempted = False


def get_instant_answer_model() -> IntentModel | None:
    global _model, _load_attempted
    if not _load_attempted:
        _load_attempted = True
        if MODEL_PATH.is_file():
            _model = IntentModel.load(MODEL_PATH)
            logger.info("Loaded instant-answer model from %s (%d intents)", MODEL_PATH, len(_model.intents))
        else:
            logger.warning(
                "No instant-answer model at %s -- run train_instant_answer_model.py. "
                "Every turn will fall through to the LLM until then.",
                MODEL_PATH,
            )
    return _model
