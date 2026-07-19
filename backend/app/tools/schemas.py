TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "search_documents",
            "description": "Search this agent's knowledge base for information relevant to the caller's question. Always call this before answering any factual question.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The caller's question, rephrased as a search query.",
                    }
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "schedule_appointment",
            "description": "Book an appointment for the caller once you have their name, phone number, and preferred time.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "phone": {"type": "string"},
                    "preferred_time": {"type": "string"},
                    "reason": {"type": "string"},
                },
                "required": ["name", "phone", "preferred_time"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "escalate_to_human",
            "description": "Escalate the call to a human. Use when the caller is frustrated, explicitly asks for a human, or after two failed attempts to answer.",
            "parameters": {
                "type": "object",
                "properties": {"reason": {"type": "string"}},
                "required": ["reason"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "verify_member",
            "description": "Confirm the caller's identity as a plan member before discussing claims or benefits. Requires member ID, date of birth, and ZIP code.",
            "parameters": {
                "type": "object",
                "properties": {
                    "member_id": {"type": "string"},
                    "date_of_birth": {"type": "string", "description": "YYYY-MM-DD"},
                    "zip_code": {"type": "string"},
                },
                "required": ["member_id", "date_of_birth", "zip_code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_claim_status",
            "description": "Look up a verified member's claims. Requires verify_member to have succeeded earlier in this call.",
            "parameters": {
                "type": "object",
                "properties": {
                    "claim_number": {
                        "type": "string",
                        "description": "Specific claim number if the caller gave one, otherwise omit to get the most recent claim.",
                    }
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_benefits",
            "description": "Look up a verified member's plan, copays, and deductible status. Requires verify_member to have succeeded earlier in this call.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_formulary",
            "description": "Check whether a drug is covered, its tier, copay, and whether prior authorization is required. Does not require member verification.",
            "parameters": {
                "type": "object",
                "properties": {"drug_name": {"type": "string"}},
                "required": ["drug_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_pharmacy",
            "description": "Find in-network pharmacies near a ZIP code. Does not require member verification.",
            "parameters": {
                "type": "object",
                "properties": {"zip_code": {"type": "string"}},
                "required": ["zip_code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_ticket",
            "description": "Open a follow-up ticket for a request that can't be resolved on this call.",
            "parameters": {
                "type": "object",
                "properties": {
                    "subject": {"type": "string"},
                    "description": {"type": "string"},
                },
                "required": ["subject", "description"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "schedule_callback",
            "description": "Schedule a callback for the caller at a preferred time.",
            "parameters": {
                "type": "object",
                "properties": {
                    "phone": {"type": "string"},
                    "preferred_time": {"type": "string"},
                    "reason": {"type": "string"},
                },
                "required": ["phone", "preferred_time"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "send_email",
            "description": "Queue a confirmation or informational email to the caller.",
            "parameters": {
                "type": "object",
                "properties": {
                    "to": {"type": "string"},
                    "subject": {"type": "string"},
                    "body": {"type": "string"},
                },
                "required": ["to", "subject", "body"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_customer",
            "description": "Update the caller's profile — name and/or preferred language — with information they give you.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "language": {"type": "string"},
                },
                "required": [],
            },
        },
    },
]
