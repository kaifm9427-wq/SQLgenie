"""
Critic Agent — validates the generated SQL.

Runs a dry-run execution first (no LLM needed); if that passes, an LLM audit
checks semantic correctness against the schema. Emits a JSON verdict that the
Supervisor reads to decide whether to loop back to the Fixer.
"""

from __future__ import annotations

from typing import Optional

from ..base_agent import BaseAgent
from ..state import AgentState, _extract_json, _truthy, SchemaValidator
from db_utils import get_db_schema_context, execute_query, get_schema_signature


class CriticAgent(BaseAgent):
    name = "CriticAgent"
    display = "SQL Critic"

    def __init__(self, provider: Optional[str] = None):
        super().__init__(provider)
        self.system_prompt = (
            "You are a Senior SQL QA Analyst and database auditor.\n"
            "Compare the user's request and the generated SQL to verify semantic correctness.\n"
            "Verify against the schema:\n---------------------------\n{schema_context}\n"
            "---------------------------\n\nCheck: correct tables/columns? correct joins? correct filters/sorting?\n\n"
            'CRITICAL: respond with ONLY JSON: {{"is_valid": true|false, "critique": "..."}}'
            "Use is_valid=true when the SQL correctly answers the request."
        )

    def run(self, state: AgentState) -> None:
        # 1) Schema feasibility — does the SQL reference tables that don't exist?
        #    If so the question is not answerable; report it instead of looping.
        sig = get_schema_signature(state.db_uri)
        check = SchemaValidator(sig).validate(state.sql_query or "")
        if not check["valid"]:
            state.status = "not_answerable"
            state.block_reason = check["reason"]
            state.critique = check["reason"]
            state.log(
                self.name,
                "Not answerable",
                is_valid=False,
                critique=check["reason"],
                missing_tables=check["missing_tables"],
            )
            return

        # 2) Compiler / dry-run check (no LLM needed).
        exec_res = execute_query(state.db_uri, state.sql_query or "", read_only=True)
        if not exec_res["success"]:
            state.critique = f"Database Execution Error: {exec_res['error']}"
            state.log(self.name, "Failed", is_valid=False, critique=state.critique)
            return

        schema_context = get_db_schema_context(state.db_uri)
        chain = self._chain(
            self.system_prompt,
            "User Request: '{user_query}'\nGenerated SQL Query: '{sql_query}'",
        )
        raw = chain.invoke({
            "schema_context": schema_context,
            "user_query": state.user_query,
            "sql_query": state.sql_query,
        }).content
        parsed = _extract_json(raw)
        is_valid = _truthy(parsed.get("is_valid"))
        critique = str(parsed.get("critique", "") or "").strip() or "Query looks correct."
        state.critique = critique
        state.log(
            self.name,
            "Passed" if is_valid else "Failed",
            is_valid=is_valid,
            critique=critique,
        )
