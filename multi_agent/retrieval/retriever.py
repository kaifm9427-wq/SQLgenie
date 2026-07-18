"""
Retrieval pipeline: embed query → search store → return relevant schema context.

The GeneratorAgent uses this to pull only the relevant tables, columns, and
relationships instead of dumping the entire schema into every prompt.

Key capabilities:
  - retrieve_context:       formatted string for prompt injection (backward compat)
  - retrieve_relevant_tables:  just the table names most relevant to the query
  - retrieve_context_for_query: structured schema-only context for relevant tables
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from langchain_core.documents import Document

from .vector_store import VectorStore


class RetrievalPipeline:
    """RAG retrieval layer — scoped to a single vector store collection."""

    def __init__(self, vector_store: VectorStore, default_k: int = 5):
        self._store = vector_store
        self._default_k = default_k

    # ── public API ────────────────────────────────────────────────────

    def retrieve_context(
        self,
        query: str,
        k: Optional[int] = None,
        filter: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Return a single formatted string of top-k relevant documents.
        Backward-compatible — used when the caller wants everything.
        """
        docs = self._store.similarity_search(query, k=k or self._default_k, filter=filter)
        return _format_docs(docs)

    def retrieve_relevant_tables(
        self,
        query: str,
        k: int = 5,
    ) -> List[str]:
        """
        Return only the table names most semantically relevant to the query.
        Used by the GeneratorAgent to decide which tables to fetch fresh
        schema for.
        """
        table_schema_docs = self._store.similarity_search(
            query, k=k, filter={"type": "table_schema"}
        )
        seen: set = set()
        tables: list = []
        for d in table_schema_docs:
            t = d.metadata.get("table", "")
            if t and t not in seen:
                seen.add(t)
                tables.append(t)
        return tables

    def retrieve_context_for_query(
        self,
        query: str,
        k: int = 5,
    ) -> str:
        """
        Build a structured context string for the GeneratorAgent prompt.

        Returns:
          - Table schema docs for the most relevant tables
          - FK relationships linking those tables
          - Sample data for those tables
          - Any past_query docs that match

        Each section is labelled so the LLM can parse it easily.
        """
        tables = self.retrieve_relevant_tables(query, k=k)
        if not tables:
            return ""

        parts: list[str] = []

        # 1. Table schemas (type=table_schema) for relevant tables
        for t in tables:
            docs = self._store.similarity_search(
                query, k=1, filter={"$and": [{"type": "table_schema"}, {"table": t}]}
            )
            for d in docs:
                parts.append(f"[TABLE: {t}]\n{d.page_content}")

        # 2. FK relationships for relevant tables
        for t in tables:
            fk_docs = self._store.similarity_search(
                query, k=2, filter={"$and": [{"type": "foreign_key"}, {"source_table": t}]}
            )
            for d in fk_docs:
                parts.append(f"[RELATIONSHIP]\n{d.page_content}")

        # 3. Sample data for relevant tables
        for t in tables:
            sample_docs = self._store.similarity_search(
                query, k=1, filter={"$and": [{"type": "sample_data"}, {"table": t}]}
            )
            for d in sample_docs:
                parts.append(f"[SAMPLE DATA: {t}]\n{d.page_content}")

        # 4. Past successful queries (self-learning)
        past_docs = self._store.similarity_search(
            query, k=2, filter={"type": "past_query"}
        )
        if past_docs:
            past_lines = ["[PAST QUERIES]"]
            for d in past_docs:
                past_lines.append(d.page_content)
            parts.append("\n".join(past_lines))

        return "\n\n".join(parts)

    def retrieve_docs(
        self,
        query: str,
        k: Optional[int] = None,
        filter: Optional[Dict[str, Any]] = None,
    ) -> List[Document]:
        return self._store.similarity_search(query, k=k or self._default_k, filter=filter)

    def store_doc(self, document: Document) -> None:
        """Append a single document to the index (e.g. self-learning)."""
        self._store.add([document])

    @property
    def is_indexed(self) -> bool:
        return bool(self._store.load())


def _format_docs(docs: List[Document]) -> str:
    parts = []
    for i, d in enumerate(docs, 1):
        tag = d.metadata.get("type", "context")
        parts.append(f"[{i}] ({tag}) {d.page_content}")
    return "\n\n".join(parts)
