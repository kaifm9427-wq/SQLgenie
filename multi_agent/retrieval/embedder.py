"""
Pluggable embedder factory for SQL Genie's RAG pipeline.

Supports:
  - HuggingFaceEmbeddings (local, zero-setup) — default fallback
  - OllamaEmbeddings       (local, requires Ollama running with an embedding model)

Follows the same provider-agnostic pattern as llm_config.get_llm().

Embedder instances are cached globally (by provider+model key) so the ~80 MB
HuggingFace model is loaded from disk only once per process lifetime — this
cuts query latency by several seconds after the first call.
"""

from __future__ import annotations

import os
from typing import Optional

from langchain_core.embeddings import Embeddings

# Global cache: key = "provider:model" → Embeddings instance.
_EMBEDDER_CACHE: dict = {}


def get_embedder(provider: Optional[str] = None, model: Optional[str] = None) -> Embeddings:
    """
    Return a cached Embeddings instance for the given provider.

    The underlying model (e.g. all-MiniLM-L6-v2) is loaded once and reused
    across all call sites — retriever, self-learning, index status checks.

    Args:
        provider: "ollama" | "huggingface" | None (defaults to huggingface).
        model:   Optional model override.

    Raises:
        ImportError if the required package is not installed.
    """
    provider = (provider or os.getenv("EMBEDDER_PROVIDER", "huggingface")).lower()
    model = model or os.getenv("EMBEDDER_MODEL", "all-MiniLM-L6-v2")
    cache_key = f"{provider}:{model}"

    cached = _EMBEDDER_CACHE.get(cache_key)
    if cached is not None:
        return cached

    if provider == "ollama":
        embedder = _ollama_embedder(model)
    elif provider == "huggingface":
        embedder = _hf_embedder(model)
    else:
        raise ValueError(f"Unknown embedder provider: {provider}. Use 'ollama' or 'huggingface'.")

    _EMBEDDER_CACHE[cache_key] = embedder
    return embedder


def _hf_embedder(model: str) -> Embeddings:
    try:
        from langchain_huggingface import HuggingFaceEmbeddings
    except ImportError:
        from langchain_community.embeddings import HuggingFaceEmbeddings

    return HuggingFaceEmbeddings(
        model_name=model,
        model_kwargs={"device": "cpu"},
    )


def _ollama_embedder(model: str) -> Embeddings:
    try:
        from langchain_ollama import OllamaEmbeddings
    except ImportError:
        raise ImportError(
            "langchain-ollama is required for Ollama embeddings. "
            "Install it with: pip install langchain-ollama"
        )

    return OllamaEmbeddings(model=model)
