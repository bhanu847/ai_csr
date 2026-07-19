from app.tools.schemas import TOOL_SCHEMAS

_ALL_TOOL_NAMES = {schema["function"]["name"] for schema in TOOL_SCHEMAS}

# Baseline every department keeps regardless of specialty — knowledge
# lookup and the two safety-net actions (escalate, follow-up ticket).
_BASELINE = {"search_documents", "escalate_to_human", "create_ticket"}

DEPARTMENT_TOOLS: dict[str, set[str]] = {
    "general": _ALL_TOOL_NAMES,
    "claims": _BASELINE | {"verify_member", "check_claim_status", "schedule_callback", "update_customer"},
    "pharmacy": _BASELINE | {"verify_member", "search_formulary", "find_pharmacy", "schedule_callback"},
    "benefits": _BASELINE | {"verify_member", "get_benefits", "schedule_callback", "send_email"},
    "provider": _BASELINE | {"find_pharmacy", "schedule_appointment", "schedule_callback"},
    "escalation": {"escalate_to_human", "create_ticket", "schedule_callback"},
}


def tools_for_department(department: str) -> list[dict]:
    allowed = DEPARTMENT_TOOLS.get(department.lower(), _ALL_TOOL_NAMES)
    return [schema for schema in TOOL_SCHEMAS if schema["function"]["name"] in allowed]
