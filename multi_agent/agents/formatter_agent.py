"""
Formatter Agent — turns SQL results into a natural-language answer.

LLM-based. Takes the execution result (columns + rows) and the user's
question and writes a concise paragraph. This preserves the earlier
pipeline's quality of explanation while keeping latency manageable
via LLM caching and keep-alive.
"""

from __future__ import annotations

from typing import Optional

from ..base_agent import BaseAgent
from ..state import AgentState, _summarize_results


class FormatterAgent(BaseAgent):
    name = "FormatterAgent"
    display = "Result Formatter"

    def __init__(self, provider: Optional[str] = None):
        super().__init__(provider)
        self.system_prompt = (
            "You are a data analyst who explains SQL query results in plain English.\n"
            "Given the user's question, the SQL that was run, and the result data, "
            "write 1-3 sentences answering the question conversationally.\n"
            "Do not mention column names or SQL syntax. Do not use markdown formatting.\n"
            "Just answer as if you are a friendly assistant."
        )

    def run(self, state: AgentState) -> None:
        state.log(self.name, "Formatting answer")

        if state.status == "not_answerable":
            state.answer = state.block_reason or "This question cannot be answered with the available data."
            state.log(self.name, "Completed")
            return

        res = state.execution_result or {}
        if not res.get("success"):
            state.answer = res.get("error", "Query execution failed.")
            state.log(self.name, "Completed")
            return

        result_summary = _summarize_results(res)

        chain = self._chain(
            self.system_prompt,
            "Question: {user_query}\nSQL: {sql_query}\nResults:\n{result_summary}",
        )
        raw = chain.invoke({
            "user_query": state.user_query,
            "sql_query": state.sql_query,
            "result_summary": result_summary,
        }).content
        state.answer = raw.strip()
        state.log(self.name, "Completed")
