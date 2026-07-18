"""
Shared state and helpers for the SQL Genie multi-agent system.

AgentState is the single mutable context the Supervisor passes between agents.
Helper functions (JSON extraction, SQL cleaning, result summarisation) are kept
here so every agent module can import them without circular dependencies.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Optional


class AgentState:
    """Mutable shared context the Supervisor passes between agents."""

    def __init__(self, user_query: str, db_uri: str, provider: Optional[str] = None):
        self.user_query = user_query
        self.db_uri = db_uri
        self.provider = provider
        self.sql_query: Optional[str] = None
        self.critique: Optional[str] = None
        self.execution_result: Optional[Dict[str, Any]] = None
        self.answer: Optional[str] = None
        self.explanation: Optional[str] = None
        self.conversation_history: list = []
        self.status: str = "success"
        self.block_reason: Optional[str] = None
        # Structured telemetry for the UI pipeline
        self.logs: list[Dict[str, Any]] = []

    def log(self, agent: str, status: str, **extra: Any) -> None:
        entry = {"agent": agent, "status": status, **extra}
        self.logs.append(entry)


def clean_sql(text: str) -> str:
    cleaned = re.sub(r"```sql\s*", "", text or "")
    cleaned = re.sub(r"```\s*", "", cleaned).strip()
    # Strip inline explanation marker and anything after it
    if "--explain:" in cleaned:
        cleaned = cleaned.split("--explain:")[0].strip()
    if cleaned.endswith(";"):
        cleaned = cleaned[:-1]
    return cleaned.strip()


def _extract_json(text: str) -> Dict[str, Any]:
    import json as _json

    if not text:
        return {}
    cleaned = re.sub(r"```(?:json)?", "", text, flags=re.IGNORECASE).strip()
    try:
        obj = _json.loads(cleaned)
        if isinstance(obj, dict):
            return obj
    except Exception:
        pass
    start = cleaned.find("{")
    while start != -1:
        depth = 0
        in_str = False
        esc = False
        for i in range(start, len(cleaned)):
            c = cleaned[i]
            if esc:
                esc = False
                continue
            if c == "\\":
                esc = True
                continue
            if c == '"':
                in_str = not in_str
                continue
            if in_str:
                continue
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    try:
                        obj = _json.loads(cleaned[start:i + 1])
                        if isinstance(obj, dict):
                            return obj
                    except Exception:
                        pass
                    break
        start = cleaned.find("{", start + 1)
    return {}


def _truthy(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    if isinstance(v, str):
        return v.strip().lower() in ("true", "1", "yes")
    if isinstance(v, (int, float)):
        return bool(v)
    return bool(v)


def _summarize_results(res: Dict[str, Any]) -> str:
    cols = res.get("columns") or []
    data = res.get("data") or res.get("rows") or []
    if not cols:
        return str(res.get("message", ""))
    preview = data[:20]
    lines = ["Columns: " + ", ".join(map(str, cols))]
    for row in preview:
        lines.append(", ".join(str(c) for c in row))
    if len(data) > 20:
        lines.append(f"... ({len(data)} rows total)")
    return "\n".join(lines)


def _last_log(state: AgentState, agent: str) -> Dict[str, Any]:
    for entry in reversed(state.logs):
        if entry["agent"] == agent:
            return entry
    return {}


import re as _re

# Tables / columns are referenced in SQL as: FROM <tbl>, JOIN <tbl>, <tbl>.<col>
_TABLE_REFS = _re.compile(r"\b(?:from|join)\s+([\"`\[]?[\w]+[\"%\]\.]?)", _re.IGNORECASE)


def _extract_table_refs(sql: str) -> list:
    refs = []
    for m in _TABLE_REFS.findall(sql or ""):
        name = m.strip().strip("\"`'[]")
        if name:
            refs.append(name.lower())
    return refs


class SchemaValidator:
    """
    Validates that a generated SQL query only references tables (and, where
    possible, columns) that exist in the connected database. When the query
    depends on entities absent from the schema, the question is *not answerable*
    — this is reported explicitly so the system can explain why, instead of
    looping on a doomed fix.
    """

    def __init__(self, schema_signature: Dict[str, list]):
        # signature: {table_name_lower: [column_names_lower]}
        self.signature = {str(k).lower(): [str(c).lower() for c in v]
                          for k, v in (schema_signature or {}).items()}

    def validate(self, sql: str) -> Dict[str, Any]:
        referenced = _extract_table_refs(sql)
        missing_tables = [t for t in referenced if t not in self.signature]
        if missing_tables:
            # De-dupe while preserving order
            seen = set()
            uniq = []
            for t in missing_tables:
                if t not in seen:
                    seen.add(t)
                    uniq.append(t)
            available = ", ".join(sorted(self.signature.keys())) or "(none)"
            return {
                "valid": False,
                "missing_tables": uniq,
                "missing_columns": [],
                "available_tables": sorted(self.signature.keys()),
                "reason": (
                    f"The query references table(s) not present in this database: "
                    f"{', '.join(uniq)}. Available tables: {available}."
                ),
            }
        return {
            "valid": True,
            "missing_tables": [],
            "missing_columns": [],
            "available_tables": sorted(self.signature.keys()),
            "reason": "",
        }
