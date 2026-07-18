"""
Thin wrapper around a persistent Chroma vector store.

Handles initialisation, indexing, and similarity search so the rest of
the retrieval pipeline doesn't need to care about the underlying store.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings

# Default directory relative to the project root
DEFAULT_PERSIST_DIR = "chroma_db"
DEFAULT_COLLECTION = "sql_genie"


class VectorStore:
    """Persistent Chroma-based vector store for SQL Genie's RAG pipeline."""

    def __init__(
        self,
        embeddings: Embeddings,
        persist_directory: str = DEFAULT_PERSIST_DIR,
        collection_name: str = DEFAULT_COLLECTION,
    ):
        self._embeddings = embeddings
        self._persist_dir = persist_directory
        self._collection = collection_name
        self._store: Optional[Chroma] = None

    # ── lifecycle ──────────────────────────────────────────────────────

    def index(self, documents: List[Document]) -> None:
        """Create (or overwrite) the index from a list of documents."""
        if self._store is not None:
            self._store.delete_collection()
        self._store = Chroma.from_documents(
            documents=documents,
            embedding=self._embeddings,
            persist_directory=self._persist_dir,
            collection_name=self._collection,
        )

    def add(self, documents: List[Document]) -> None:
        """Append documents to an existing index."""
        if self._store is None:
            self.load()
        self._store.add_documents(documents)

    def load(self) -> bool:
        """Load an existing index from disk. Returns True if the collection exists and has docs."""
        import os
        if not os.path.isdir(self._persist_dir):
            return False
        try:
            self._store = Chroma(
                persist_directory=self._persist_dir,
                embedding_function=self._embeddings,
                collection_name=self._collection,
            )
            # Verify the collection actually has documents (Chrom.get_or_create creates empty)
            return self._store._collection.count() > 0
        except Exception:
            self._store = None
            return False

    def clear(self) -> None:
        """Delete the collection entirely."""
        if self._store is not None:
            try:
                self._store.delete_collection()
            except Exception:
                pass
        self._store = None

    # ── query ──────────────────────────────────────────────────────────

    def similarity_search(
        self,
        query: str,
        k: int = 5,
        filter: Optional[Dict[str, Any]] = None,
    ) -> List[Document]:
        if self._store is None:
            self.load()
        return self._store.similarity_search(query, k=k, filter=filter)

    # ── internal ───────────────────────────────────────────────────────

    @property
    def store(self) -> Chroma:
        if self._store is None:
            self.load()
        return self._store
