import logging

from app.llm.client import json_completion

logger = logging.getLogger("router")

ROUTER_PROMPT = """Classify the customer's message into exactly one department \
from this list: {departments}. Pick "general" if nothing else clearly fits, \
it's small talk, or the intent is ambiguous. Respond with ONLY a JSON object: \
{{"department": "..."}}"""


def classify_department(transcript: str, available_departments: list[str]) -> str:
    """Best-effort intent classification for the one-time routing decision
    made on a call's first utterance. Falls back to "general" (stay on the
    router/default agent) on any failure — routing is an optimization, not
    something that should ever block or break a call."""
    if "general" not in available_departments:
        available_departments = [*available_departments, "general"]

    try:
        data = json_completion(
            [
                {"role": "system", "content": ROUTER_PROMPT.format(departments=", ".join(available_departments))},
                {"role": "user", "content": transcript},
            ],
            max_tokens=50,
        )
    except Exception:
        logger.exception("Department classification failed")
        return "general"

    department = str(data.get("department", "general")).strip().lower()
    return department if department in available_departments else "general"
