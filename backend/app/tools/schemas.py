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
]
