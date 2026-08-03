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


def _total_memory_mb() -> int:
    """Total system RAM in MB. Returns 0 when it cannot be determined."""
    try:
        if hasattr(os, "sysconf"):
            page = os.sysconf("SC_PAGE_SIZE")
            pages = os.sysconf("SC_PHYS_PAGES")
            return (page * pages) // (1024 * 1024)
    except Exception:
        pass
    return 0


def get_embedder(provider: Optional[str] = None, model: Optional[str] = None) -> Optional[Embeddings]:
    """
    Return a cached Embeddings instance for the given provider.

    The underlying model (e.g. all-MiniLM-L6-v2) is loaded once and reused
    across all call sites — retriever, self-learning, index status checks.

    Args:
        provider: "ollama" | "huggingface" | "none" | None (defaults to huggingface).
        model:   Optional model override.

    Returns:
        An Embeddings instance, or None when RAG embeddings are disabled
        (provider "none", or a low-memory host with the default provider).

    Raises:
        ImportError if the required package is not installed.
    """
    provider = (provider or os.getenv("EMBEDDER_PROVIDER", "huggingface")).lower()
    model = model or os.getenv("EMBEDDER_MODEL", "all-MiniLM-L6-v2")
    cache_key = f"{provider}:{model}"

    cached = _EMBEDDER_CACHE.get(cache_key)
    if cached is not None:
        return cached

    # Explicit opt-out of the local RAG embedder.
    if provider in ("none", "disabled"):
        return None

    # Free-tier hosts (Render/Koyeb ~512MB) get OOM-killed when importing
    # torch via sentence-transformers. Auto-disable the local embedder on
    # low-memory machines unless the user explicitly opts in.
    total_mb = _total_memory_mb()
    if provider == "huggingface" and os.getenv("EMBEDDER_PROVIDER") is None and (total_mb == 0 or total_mb < 2048):
        print("⚠️ Low-memory host detected: local embeddings disabled (RAG skipped). "
              "Set EMBEDDER_PROVIDER=huggingface to force.")
        return None

    if provider == "ollama":
        embedder = _ollama_embedder(model)
    elif provider == "huggingface":
        embedder = _hf_embedder(model)
    else:
        raise ValueError(f"Unknown embedder provider: {provider}. Use 'ollama', 'huggingface', or 'none'.")

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
