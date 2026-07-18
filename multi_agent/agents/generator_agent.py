"""
Generator Agent — translates natural language into SQL.

Holds its own LLM chain. Uses RAG to identify the relevant tables from the
vector index, then fetches *live* schema for only those tables (so column
definitions are always fresh). Falls back to the full schema dump if the
vector index is unavailable.

Strategy B — dynamic per-database retrieval with no hardcoded examples.
"""

from __future__ import annotations

import os
from typing import Optional

from langchain_core.documents import Document

from ..base_agent import BaseAgent
from ..state import AgentState, clean_sql
from db_utils import get_db_schema_context


def _build_retriever(db_uri: str):
    try:
        from multi_agent.retrieval import RetrievalPipeline
        from multi_agent.retrieval.embedder import get_embedder
        from multi_agent.retrieval.vector_store import VectorStore
        from multi_agent.retrieval.indexer import collection_name_for

        embedder = get_embedder(provider=os.getenv("EMBEDDER_PROVIDER", "huggingface"),
                                model=os.getenv("EMBEDDER_MODEL"))
        cname = collection_name_for(db_uri)
        store = VectorStore(embedder, collection_name=cname)
        if not store.load():
            return None
        return RetrievalPipeline(store, default_k=5)
    except Exception:
        return None


def _get_schema_for_tables(db_uri: str, tables: list[str]) -> str:
    """Fetch live schema for a specific set of tables."""
    try:
        from sqlalchemy import inspect, create_engine
        engine = create_engine(db_uri)
        inspector = inspect(engine)
        parts = []
        for table in tables:
            try:
                cols = inspector.get_columns(table)
                pk_cols = {c["name"] for c in inspector.get_pk_constraint(table).get("constrained_columns", [])}
                fks = inspector.get_foreign_keys(table)
                fk_map = {}
                for fk in fks:
                    for sc, tc in zip(fk["constrained_columns"], fk["referred_columns"]):
                        fk_map[sc] = f"{fk['referred_table']}.{tc}"
                col_lines = []
                for c in cols:
                    note = str(c["type"])
                    if c["name"] in pk_cols:
                        note += " PK"
                    if c["name"] in fk_map:
                        note += f" FK→{fk_map[c['name']]}"
                    if not c.get("nullable", True):
                        note += " NOT NULL"
                    col_lines.append(f"  {c['name']} ({note})")
                parts.append(f"CREATE TABLE {table} (\n" + "\n".join(col_lines) + "\n);")
            except Exception:
                pass
        return "\n\n".join(parts)
    except Exception:
        return ""


class GeneratorAgent(BaseAgent):
    name = "GeneratorAgent"
    display = "SQL Generator"

    def __init__(self, provider: Optional[str] = None):
        super().__init__(provider)
        self.system_prompt = (
            "You are a professional SQL database developer and data analyst.\n"
            "Translate the user's request into a valid, executable SQLite SELECT query.\n\n"
            "Database Schema Context:\n=========================================\n"
            "{schema_context}\n=========================================\n\n"
            "{retrieved_context}"
            "Constraints:\n"
            "1. SQLite dialect only. 2. SELECT queries only — never INSERT/UPDATE/DELETE/DROP/ALTER.\n"
            "3. Output ONLY the raw SQL on the first line. No markdown, no explanation.\n"
            "4. Join tables using the FOREIGN KEYs shown in the schema.\n"
            "5. If past successful queries are provided above, use them as a guide for style and structure.\n"
            "After the SQL, add a line with '--explain:' followed by a 1-sentence plain-English explanation of what the SQL does."
        )

    def run(self, state: AgentState) -> None:
        state.log(self.name, "Generating raw SQL")

        # 1. Try RAG to find relevant tables + build targeted context
        retriever = _build_retriever(state.db_uri)
        retrieved_context = ""

        if retriever is not None and retriever.is_indexed:
            try:
                # RAG identifies which tables are relevant to the query
                relevant_tables = retriever.retrieve_relevant_tables(state.user_query, k=5)
                state.log(
                    self.name,
                    f"RAG identified relevant tables",
                    tables=relevant_tables,
                )

                if relevant_tables:
                    # Fetch live schema for only the relevant tables (always fresh)
                    schema_context = _get_schema_for_tables(state.db_uri, relevant_tables)
                    # Also include any additional context from the index (FKs, sample data, past queries)
                    rag_extra = retriever.retrieve_context_for_query(state.user_query, k=5)
                    if rag_extra:
                        retrieved_context = (
                            "Additional context from past queries and relationships:\n"
                            "----------------------------------------\n"
                            f"{rag_extra}\n"
                            "----------------------------------------\n\n"
                        )
                else:
                    schema_context = get_db_schema_context(state.db_uri)

                if not schema_context or schema_context.strip() in (
                    "", "No tables found in the database.",
                ):
                    schema_context = get_db_schema_context(state.db_uri)

            except Exception as e:
                state.log(self.name, "RAG retrieval failed, falling back to full schema", error=str(e))
                schema_context = get_db_schema_context(state.db_uri)
                retrieved_context = ""
        else:
            # 2. No index available — fall back to full schema dump
            schema_context = get_db_schema_context(state.db_uri)

        # Inject conversation history if available (for follow-up queries)
        history_block = ""
        if state.conversation_history:
            pairs = []
            for msg in state.conversation_history[-4:]:
                role = "User" if msg.get("role") == "user" else "Assistant"
                pairs.append(f"{role}: {msg.get('content', '')}")
            history_block = "\n".join(pairs) + "\n\n"

        prompt = self.system_prompt + history_block
        chain = self._chain(prompt, "Generate the SQL query for: '{user_query}'")
        raw = chain.invoke({
            "schema_context": schema_context,
            "retrieved_context": retrieved_context,
            "user_query": state.user_query,
        }).content

        # Parse SQL and explanation from the merged output.
        # The prompt asks for SQL on the first line(s), then '--explain:' followed by explanation.
        sql = clean_sql(raw)
        state.sql_query = sql

        # Extract explanation after '--explain:' marker
        expl_marker = "--explain:"
        if expl_marker in raw:
            state.explanation = raw.split(expl_marker, 1)[1].split("\n")[0].strip()
        state.log(self.name, "Completed", output=sql)
