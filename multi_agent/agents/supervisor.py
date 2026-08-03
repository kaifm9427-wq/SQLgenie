"""
Supervisor — the central coordinator of the SQL Genie multi-agent system.

Pipeline (5 specialised agents):
  Guardrail (LLM) → Generator → Explainer → Execute
  → [Critic + Fixer if SQL fails] → Formatter (LLM)

Schema context is cached per run so each agent doesn't re-read the database.
"""

from __future__ import annotations

from typing import Optional

from langchain_core.documents import Document

import os
from ..base_agent import BaseAgent
from ..state import AgentState, _last_log, _extract_table_refs
from ..agents.guardrail_agent import GuardrailAgent
from ..agents.generator_agent import GeneratorAgent
from ..agents.explainer_agent import ExplainerAgent
from ..agents.critic_agent import CriticAgent
from ..agents.fixer_agent import FixerAgent
from ..agents.formatter_agent import FormatterAgent
from db_utils import get_db_schema_context, execute_query


def _learn_from_success(state: AgentState) -> None:
    try:
        from multi_agent.retrieval.embedder import get_embedder
        from multi_agent.retrieval.vector_store import VectorStore
        from multi_agent.retrieval.indexer import collection_name_for

        embedder = get_embedder(provider=os.getenv("EMBEDDER_PROVIDER", "huggingface"),
                                model=os.getenv("EMBEDDER_MODEL"))
        if embedder is None:
            return
        cname = collection_name_for(state.db_uri)
        store = VectorStore(embedder, collection_name=cname)
        if not store.load():
            return

        tables_used = _extract_table_refs(state.sql_query or "")
        result_summary = ""
        if state.execution_result:
            data = state.execution_result.get("data") or []
            cols = state.execution_result.get("columns") or []
            result_summary = f"Returned {len(data)} rows: {', '.join(cols[:5])}"

        content = (
            f"Question: {state.user_query}\n"
            f"SQL: {state.sql_query}\n"
            f"Result: {result_summary}"
        )
        doc = Document(
            page_content=content,
            metadata={
                "type": "past_query",
                "tables": tables_used,
                "question": state.user_query,
            },
        )
        store.add([doc])
    except Exception:
        pass


class Supervisor:
    """
    Central coordinator. Runs the full 5-agent pipeline:
      Guardrail (LLM) → Generator → Explainer → Execute
      → Critic/Fixer (only if SQL failed) → Formatter (LLM)
    """

    def __init__(self, provider: Optional[str] = None, max_iterations: int = 3):
        self.provider = provider
        self.max_iterations = max_iterations
        self.guardrail = GuardrailAgent(provider)
        self.generator = GeneratorAgent(provider)
        self.explainer = ExplainerAgent(provider)
        self.critic = CriticAgent(provider)
        self.fixer = FixerAgent(provider)
        self.formatter = FormatterAgent(provider)
        # Per-run cache for expensive operations
        self._schema_cache: str = ""

    def _cached_schema(self, db_uri: str) -> str:
        if not self._schema_cache:
            self._schema_cache = get_db_schema_context(db_uri)
        return self._schema_cache

    def run(self, user_query: str, db_uri: str, conversation_history: Optional[list] = None) -> AgentState:
        state = AgentState(user_query, db_uri, self.provider)
        self._schema_cache = ""
        if conversation_history:
            state.conversation_history = conversation_history

        # Stage 1 — Guardrail (LLM + static)
        self.guardrail.run(state)
        if state.status == "blocked":
            return state

        # Stage 2 — Generator
        self.generator.run(state)
        if not state.sql_query:
            state.status = "max_iterations_reached"

        # Stage 3 — Explainer
        self.explainer.run(state)
        if not state.sql_query:
            state.status = "max_iterations_reached"

        # Stage 4 — Execute (before critic so we can validate by running it)
        if state.status != "not_answerable" and state.sql_query:
            state.execution_result = execute_query(db_uri, state.sql_query, read_only=True)
            if state.execution_result and not state.execution_result.get("success"):
                iteration = 1
                while iteration <= self.max_iterations:
                    self.critic.run(state)
                    if state.status == "not_answerable":
                        break
                    last = _last_log(state, self.critic.name)
                    is_valid = bool(last.get("is_valid", False)) if last else False
                    if is_valid:
                        break
                    self.fixer.run(state)
                    state.execution_result = execute_query(db_uri, state.sql_query or "", read_only=True)
                    if state.execution_result and state.execution_result.get("success"):
                        break
                    iteration += 1
        else:
            state.execution_result = {
                "success": False,
                "columns": [],
                "data": [],
                "error": state.block_reason or "No SQL generated",
            }

        # Self-learning
        if state.status == "success" and state.execution_result and state.execution_result.get("success"):
            _learn_from_success(state)

        # Stage 5 — Formatter (LLM)
        self.formatter.run(state)
        return state
