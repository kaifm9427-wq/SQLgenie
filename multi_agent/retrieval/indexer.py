"""
Indexer — dynamically indexes any connected database's schema metadata into
Chroma for semantic retrieval.

No static examples. Every index is built live from the database metadata:
  - table_schema:    full CREATE TABLE–style description per table
  - column_detail:   per-column type, nullable, PK, FK, statistics, sample values
  - foreign_key:     every FK relationship as a standalone document
  - sample_data:     a few sample rows per table as usage hints

This is Strategy B — works for arbitrary user databases, not just a known schema.
"""

from __future__ import annotations

import os
from typing import List, Optional

from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings

from db_utils import get_database_metadata_bundle, get_db_engine
from .vector_store import VectorStore

import hashlib

COLLECTION_PREFIX = "sql_genie"


def _normalize_uri(db_uri: str) -> str:
    """Normalize a database URI so the same DB always hashes the same way.
    Resolves relative SQLite paths to absolute so that the sandbox DB
    has the same collection name whether accessed via 'sqlite:///sandbox.db'
    or the API-resolved absolute path."""
    uri = db_uri.strip()
    if uri.startswith("sqlite:///"):
        path = uri[len("sqlite:///"):]
        if not os.path.isabs(path):
            abs_path = os.path.abspath(path)
            return f"sqlite:///{abs_path}"
    return uri


def collection_name_for(db_uri: str) -> str:
    """Deterministic collection name based on a *normalized* database URI."""
    normalized = _normalize_uri(db_uri)
    h = hashlib.md5(normalized.encode()).hexdigest()[:12]
    return f"{COLLECTION_PREFIX}_{h}"


def index_database(
    db_uri: str,
    embeddings: Embeddings,
    persist_directory: str = "chroma_db",
    collection_name: Optional[str] = None,
    force_rebuild: bool = False,
) -> VectorStore:
    """
    Build (or rebuild) a vector index for the given database.

    Scans the live schema — tables, columns, types, foreign keys, sample
    data — and indexes everything as searchable documents so the
    GeneratorAgent can retrieve only the relevant subset at query time.

    Returns the populated VectorStore.
    """
    if collection_name is None:
        collection_name = collection_name_for(db_uri)

    store = VectorStore(embeddings, persist_directory, collection_name)

    if not force_rebuild and store.load():
        return store

    bundle = get_database_metadata_bundle(db_uri)
    docs: List[Document] = []

    for table_name, info in bundle.get("tables", {}).items():
        cols = info.get("columns", [])
        row_count = info.get("row_count", 0)
        sample_vals = info.get("sample_values", {})

        # ── 1. Table schema document ──────────────────────────────────
        col_lines = []
        for c in cols:
            parts = [f"  {c['name']} {c['type']}"]
            if c["is_pk"]:
                parts.append("PK")
            if c["fk_target"]:
                parts.append(f"FK → {c['fk_target']['table']}.{c['fk_target']['column']}")
            if not c["nullable"]:
                parts.append("NOT NULL")
            col_lines.append(" ".join(parts))

        schema_text = (
            f"Table: {table_name}\n"
            f"Row count: ~{row_count}\n"
            f"Columns:\n" + "\n".join(col_lines)
        )
        docs.append(Document(
            page_content=schema_text,
            metadata={"type": "table_schema", "table": table_name.lower()},
        ))

        # ── 2. Per-column detail documents ────────────────────────────
        for c in cols:
            detail_lines = [
                f"Table: {table_name}",
                f"Column: {c['name']}",
                f"Type: {c['type']}",
                f"Nullable: {c['nullable']}",
                f"Primary key: {c['is_pk']}",
            ]
            if c["default"]:
                detail_lines.append(f"Default: {c['default']}")
            if c["fk_target"]:
                detail_lines.append(f"Foreign key → {c['fk_target']['table']}.{c['fk_target']['column']}")
            if c["name"] in sample_vals:
                vals = sample_vals[c["name"]]
                detail_lines.append(f"Sample values: {', '.join(str(v) for v in vals[:5])}")

            docs.append(Document(
                page_content="\n".join(detail_lines),
                metadata={
                    "type": "column_detail",
                    "table": table_name.lower(),
                    "column": c["name"].lower(),
                },
            ))

        # ── 3. Sample data document ────────────────────────────────────
        if sample_vals:
            sample_lines = [f"Table: {table_name}"]
            for col_name, vals in sample_vals.items():
                sample_lines.append(f"  {col_name}: {', '.join(str(v) for v in vals[:3])}")
            docs.append(Document(
                page_content="\n".join(sample_lines),
                metadata={"type": "sample_data", "table": table_name.lower()},
            ))

    # ── 4. Foreign key relationship documents ──────────────────────────
    for fk in bundle.get("foreign_keys", []):
        src = fk["source_table"]
        tgt = fk["target_table"]
        scols = ", ".join(fk["source_columns"])
        tcols = ", ".join(fk["target_columns"])
        content = (
            f"Foreign key: {src}.{scols} → {tgt}.{tcols}\n"
            f"JOIN {src} ON {src}.{fk['source_columns'][0]} = {tgt}.{fk['target_columns'][0]}"
        )
        docs.append(Document(
            page_content=content,
            metadata={
                "type": "foreign_key",
                "source_table": src.lower(),
                "target_table": tgt.lower(),
            },
        ))

    store.index(docs)
    return store
