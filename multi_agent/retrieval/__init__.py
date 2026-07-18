"""RAG & vector-search infrastructure for SQL Genie."""

from .embedder import get_embedder
from .vector_store import VectorStore
from .retriever import RetrievalPipeline

__all__ = [
    "EmbedderFactory",
    "VectorStore",
    "RetrievalPipeline",
]
