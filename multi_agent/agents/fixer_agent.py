"""
Fixer Agent — repairs invalid SQL.

Invoked by the Supervisor only when the Critic rejects the SQL. Takes the
Critic's feedback and the current (broken) SQL and produces a corrected query.
"""

from __future__ import annotations

from typing import Optional

from ..base_agent import BaseAgent
from ..state import AgentState, clean_sql
from db_utils import get_db_schema_context


class FixerAgent(BaseAgent):
    name = "FixerAgent"
    display = "Fixer Agent"

    def __init__(self, provider: Optional[str] = None):
        super().__init__(provider)
        self.system_prompt = (
            "You are an expert SQL debugger and developer.\n"
            "Fix the generated SQL based on the QA Critic's feedback.\n\n"
            "Database Schema Context:\n---------------------------\n{schema_context}\n"
            "---------------------------\n\nFeedback from QA Critic:\n'{critique}'\n\n"
            "Output ONLY the raw SQL query. No markdown, no explanation."
        )

    def run(self, state: AgentState) -> None:
        state.log(self.name, "Fixing SQL")
        schema_context = get_db_schema_context(state.db_uri)
        chain = self._chain(
            self.system_prompt,
            "Original User Request: '{user_query}'\nIncorrect SQL Query: '{sql_query}'",
        )
        raw = chain.invoke({
            "schema_context": schema_context,
            "user_query": state.user_query,
            "sql_query": state.sql_query,
            "critique": state.critique or "",
        }).content
        fixed = clean_sql(raw)
        state.sql_query = fixed
        state.log(self.name, "Completed", output=fixed)
