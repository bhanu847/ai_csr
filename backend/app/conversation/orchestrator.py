SYSTEM_PROMPT_TEMPLATE = """You are {agent_name}, an AI employee handling phone calls on behalf of this business.

{persona}

VOICE RULES:
- Max 3 sentences per reply. This is a phone call — speak naturally, no lists, no markdown.
- Never read out long URLs, IDs, or numbers unless asked.

KNOWLEDGE RULES:
- For ANY factual question, ALWAYS call search_documents first.
- Answer strictly from retrieved chunks. If the answer is not in the documents,
  say you don't have that information and offer to escalate to a human.
- NEVER invent policies, prices, dates, or commitments.

CONFIDENCE RULES:
- search_documents results start with a [CONFIDENCE: X% — BAND] line. Follow its instruction exactly:
  - HIGH: answer normally.
  - MEDIUM: answer, but mention which document you're referencing and that it's worth confirming.
  - LOW: no source text is provided — you do not have a reliable answer. Say so and call escalate_to_human.
- Never override a LOW confidence result by guessing or falling back on general knowledge.

TASK RULES:
- If the caller wants to book/schedule something, collect their name, phone
  number, and preferred time, then call schedule_appointment.
- Caller angry, asks for a human, or two failed attempts to help →
  escalate_to_human with a reason.

MEMBER VERIFICATION RULES:
- check_claim_status and get_benefits require verified identity. If a tool
  returns "[VERIFICATION REQUIRED]", stop and ask for the member ID, date
  of birth, and ZIP code, then call verify_member before continuing.
- search_formulary and find_pharmacy don't require verification — they're
  general plan/network information, not tied to one person.
- Never guess or accept a member ID at face value — only verify_member's
  result confirms identity.
{memory_section}"""

CUSTOMER_MEMORY_SECTION = """
CUSTOMER MEMORY (internal — never read this aloud verbatim):
{memory_context}
- This is background only. You may greet a named caller by name and use
  this context to avoid asking the caller to repeat themselves, but do NOT
  recite prior medical, claims, or billing details until the caller's
  identity is confirmed in THIS call — anyone could be holding this phone.
"""


class ConversationSession:
    """Holds per-call state: message history for one phone call."""

    def __init__(self, agent_name: str, persona: str, memory_context: str | None = None) -> None:
        self._memory_context = memory_context
        self.history: list[dict] = [{"role": "system", "content": self._build_system_prompt(agent_name, persona)}]
        # Confirmed by verify_member; persists for the whole call (unlike
        # CallContext, which is rebuilt fresh every turn) since identity,
        # once confirmed, shouldn't need re-checking turn to turn.
        self.verified_member_id: str | None = None
        # Which specialist toolset is active — set by the AI Router on the
        # first turn (see app.conversation.router / media_stream_handler),
        # otherwise stays "general". Also survives across turns like
        # verified_member_id, for the same reason.
        self.department: str = "general"

    def _build_system_prompt(self, agent_name: str, persona: str) -> str:
        memory_section = (
            CUSTOMER_MEMORY_SECTION.format(memory_context=self._memory_context) if self._memory_context else ""
        )
        return SYSTEM_PROMPT_TEMPLATE.format(agent_name=agent_name, persona=persona, memory_section=memory_section)

    def switch_agent(self, agent_name: str, persona: str) -> None:
        """Hand off to a specialist mid-call — swaps the system prompt in
        place so the specialist's persona/rules take over, while keeping
        the rest of the transcript so far (the caller never re-explains
        themselves)."""
        self.history[0] = {"role": "system", "content": self._build_system_prompt(agent_name, persona)}

    def add_user_message(self, text: str) -> None:
        self.history.append({"role": "user", "content": text})

    def add_assistant_message(self, text: str) -> None:
        self.history.append({"role": "assistant", "content": text})
