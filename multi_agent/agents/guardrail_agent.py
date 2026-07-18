"""
Guardrail Agent — the first line of defence.

A two-layer guard:
1. Static keyword check (fast) blocks obvious destructive intent.
2. LLM semantic check classifies ambiguous queries against the business domain.

Both must pass for the query to proceed.
"""

from __future__ import annotations

import re
from typing import Optional

from ..base_agent import BaseAgent
from ..state import AgentState, _extract_json, _truthy

_DESTRUCTIVE = [r"\bdrop\b", r"\bdelete\b", r"\btruncate\b", r"\balter\b", r"\binsert\b", r"\bupdate\b"]


class GuardrailAgent(BaseAgent):
    name = "GuardrailAgent"
    display = "Security Guardrail"

    def __init__(self, provider: Optional[str] = None):
        super().__init__(provider)
        self.system_prompt = (
            "You are a security guardrail for a natural-language-to-SQL system.\n"
            "Determine whether the user's request is safe (read-only SELECT) or unsafe "
            "(destructive, write-intent, or malicious).\n\n"
            'Respond with ONLY JSON: {{"is_safe": true|false, "reason": "..."}}'
        )

    def run(self, state: AgentState) -> None:
        state.log(self.name, "Evaluating")

        # Layer 1 — static keyword check (fast reject)
        q = state.user_query.lower().strip()
        for pat in _DESTRUCTIVE:
            if re.search(pat, q):
                state.status = "blocked"
                state.block_reason = f"Request blocked: keyword '{pat.strip('\\\\b')}' detected."
                state.log(self.name, "Blocked", error=state.block_reason)
                return

        # Layer 2 — LLM semantic check
        chain = self._chain(
            self.system_prompt,
            "User Request: '{user_query}'",
        )
        raw = chain.invoke({"user_query": state.user_query}).content
        parsed = _extract_json(raw)
        is_safe = _truthy(parsed.get("is_safe"))
        if not is_safe:
            reason = str(parsed.get("reason", "Blocked by security guardrail.") or "Blocked by security guardrail.")
            state.status = "blocked"
            state.block_reason = reason
            state.log(self.name, "Blocked", error=reason)
            return

        state.log(self.name, "Passed")
