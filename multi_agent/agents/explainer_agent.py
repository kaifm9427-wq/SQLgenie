from __future__ import annotations

from typing import Optional

from ..base_agent import BaseAgent
from ..state import AgentState


class ExplainerAgent(BaseAgent):
    name = "ExplainerAgent"
    display = "SQL Explainer"

    def __init__(self, provider: Optional[str] = None):
        super().__init__(provider)
        self.system_prompt = (
            "You are a senior data analyst who explains SQL queries in plain English.\n"
            "Given a user's question and the generated SQL, write a concise 1-2 sentence "
            "explanation of what the SQL does and how it answers the question.\n"
            "Focus on: what data is being selected, from which tables, any filters/joins/aggregations.\n"
            "Do not repeat the SQL verbatim. Do not include markdown formatting."
        )

    def run(self, state: AgentState) -> None:
        if not state.sql_query:
            state.explanation = ""
            return

        state.log(self.name, "Explaining SQL")
        chain = self._chain(
            self.system_prompt,
            "Question: {user_query}\nSQL: {sql_query}",
        )
        raw = chain.invoke({
            "user_query": state.user_query,
            "sql_query": state.sql_query,
        }).content
        state.explanation = raw.strip()
        state.log(self.name, "Completed")
