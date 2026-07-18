"""
Base agent scaffold shared by every specialist in the SQL Genie system.

Each concrete agent inherits from BaseAgent, gets its own LLM instance and its
own prompt chain, and overrides `run(state)`. This guarantees genuine context
isolation between agents rather than one shared prompt.
"""

from __future__ import annotations

from typing import Optional

from langchain_core.prompts import ChatPromptTemplate

from llm_config import get_llm
from .state import AgentState


class BaseAgent:
    """Common scaffold: holds a name, grabs its own LLM, builds its own chain."""

    name = "base"
    display = "Agent"

    def __init__(self, provider: Optional[str] = None):
        self.provider = provider

    def _llm(self):
        return get_llm(self.provider)

    def _chain(self, system_prompt: str, human_template: str):
        prompt = ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            ("human", human_template),
        ])
        return prompt | self._llm()

    def run(self, state: AgentState) -> None:  # pragma: no cover - overridden
        raise NotImplementedError
