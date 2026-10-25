"""Lazily loads the trained instant-answer model for app/conversation/agent.py.

If no model has been trained yet (models/instant_answer.joblib doesn't exist), every turn just
falls through to the normal LLM/tool-calling path -- this is a pure speed optimization, never a
hard dependency.

Retraining takes effect without a restart: the file's modification time is re-checked at most
every RELOAD_CHECK_S seconds, and a changed file is loaded in place.
"""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path

from app.fastpath.intent_model import IntentModel

logger = logging.getLogger("fastpath")

MODEL_PATH = Path(__file__).resolve().parent.parent.parent / "models" / "instant_answer.joblib"
RELOAD_CHECK_S = 10.0

_model: IntentModel | None = None
_loaded_mtime: float | None = None
_last_check = float("-inf")
_warned_missing = False
_lock = threading.Lock()


def get_instant_answer_model() -> IntentModel | None:
    global _model, _loaded_mtime, _last_check, _warned_missing
    now = time.monotonic()
    if now - _last_check < RELOAD_CHECK_S:
        return _model
    with _lock:
        if now - _last_check < RELOAD_CHECK_S:
            return _model
        _last_check = now
        try:
            mtime = MODEL_PATH.stat().st_mtime
        except FileNotFoundError:
            if not _warned_missing:
                _warned_missing = True
                logger.warning(
                    "No instant-answer model at %s -- run train_instant_answer_model.py. "
                    "Every turn will fall through to the LLM until then.",
                    MODEL_PATH,
                )
            return _model
        if mtime != _loaded_mtime:
            try:
                _model = IntentModel.load(MODEL_PATH)
                _loaded_mtime = mtime
                logger.info("Loaded instant-answer model from %s (%d intents)", MODEL_PATH, len(_model.intents))
            except Exception:
                # e.g. caught mid-write by the trainer: keep serving the old model, retry next check.
                logger.exception("Could not load instant-answer model from %s", MODEL_PATH)
    return _model
