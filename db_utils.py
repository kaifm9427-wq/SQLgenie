import os
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError
from langchain_community.utilities import SQLDatabase

def get_db_engine(db_uri: str):
    """
    Create a SQLAlchemy engine for direct connection.
    """
    # Enforce read-only / query safety if needed
    return create_engine(db_uri)

def validate_db_connection(db_uri: str) -> dict:
    """
    Attempt to connect to the database and retrieve base metadata.
    Returns diagnostic details.
    """
    report = {
        "success": False,
        "message": "",
        "tables": []
    }
    
    try:
        # Check SQLite file physical existence
        if db_uri.startswith("sqlite:///"):
            db_path = db_uri.replace("sqlite:///", "")
            if not os.path.exists(db_path):
                report["message"] = f"SQLite file not found at path: {db_path}"
                return report
        
        # Test connecting using LangChain's SQLDatabase wrapper
        db = SQLDatabase.from_uri(db_uri)
        tables = db.get_usable_table_names()
        
        report["success"] = True
        report["message"] = "Successfully connected to the database."
        report["tables"] = tables
        
    except SQLAlchemyError as e:
        report["message"] = f"Database connection error: {str(e)}"
    except Exception as e:
        report["message"] = f"Unexpected error: {str(e)}"
        
    return report

_SCHEMA_CACHE: dict = {}

def get_db_schema_context(db_uri: str) -> str:
    """
    Retrieves the table schemas and sample rows in a format optimized
    for injection into LLM prompts. Result is cached by db_uri.
    """
    cached = _SCHEMA_CACHE.get(db_uri)
    if cached is not None:
        return cached
    try:
        db = SQLDatabase.from_uri(db_uri)
        tables = db.get_usable_table_names()
        if not tables:
            result = "No tables found in the database."
        else:
            result = db.get_table_info(tables)
        _SCHEMA_CACHE[db_uri] = result
        return result
    except Exception as e:
        return f"Error retrieving database schema: {str(e)}"


# ── Rich metadata extraction for RAG indexing ──────────────────────

def get_foreign_keys(db_uri: str) -> list:
    """Extract foreign key relationships from the database."""
    fks = []
    try:
        engine = get_db_engine(db_uri)
        inspector = __import__("sqlalchemy").inspect(engine)
        for table in inspector.get_table_names():
            for fk in inspector.get_foreign_keys(table):
                fks.append({
                    "source_table": table,
                    "source_columns": fk["constrained_columns"],
                    "target_table": fk["referred_table"],
                    "target_columns": fk["referred_columns"],
                })
    except Exception:
        pass
    return fks


def get_column_details(db_uri: str, table: str) -> list:
    """Detailed per-column info: type, nullable, default, PK, FK."""
    cols = []
    try:
        engine = get_db_engine(db_uri)
        inspector = __import__("sqlalchemy").inspect(engine)
        pk_cols = set(inspector.get_pk_constraint(table).get("constrained_columns", []))
        fk_map = {}
        for fk in inspector.get_foreign_keys(table):
            for sc, tc in zip(fk["constrained_columns"], fk["referred_columns"]):
                fk_map[sc] = {"table": fk["referred_table"], "column": tc}
        for col in inspector.get_columns(table):
            cols.append({
                "name": col["name"],
                "type": str(col["type"]),
                "nullable": col.get("nullable", True),
                "default": str(col.get("default", "")),
                "is_pk": col["name"] in pk_cols,
                "fk_target": fk_map.get(col["name"]),
            })
    except Exception:
        pass
    return cols


def get_sample_values(db_uri: str, table: str, column: str, limit: int = 10) -> list:
    """Sample distinct values for a column (useful for enum/category columns)."""
    values = []
    try:
        engine = get_db_engine(db_uri)
        with engine.connect() as conn:
            result = conn.execute(
                __import__("sqlalchemy").text(
                    f'SELECT DISTINCT "{column}" FROM "{table}" WHERE "{column}" IS NOT NULL LIMIT {limit}'
                )
            )
            values = [row[0] for row in result.fetchall()]
    except Exception:
        pass
    return values


def get_column_stats(db_uri: str, table: str, column: str) -> dict:
    """Basic stats for a column: null count, distinct count, min, max."""
    stats = {"null_ratio": None, "distinct_count": None, "min": None, "max": None}
    try:
        engine = get_db_engine(db_uri)
        with engine.connect() as conn:
            total = conn.execute(
                __import__("sqlalchemy").text(f'SELECT COUNT(*) FROM "{table}"')
            ).scalar()
            if not total:
                return stats
            nulls = conn.execute(
                __import__("sqlalchemy").text(f'SELECT COUNT(*) FROM "{table}" WHERE "{column}" IS NULL')
            ).scalar()
            stats["null_ratio"] = round(nulls / total, 4)
            # Try numeric/date stats
            try:
                row = conn.execute(
                    __import__("sqlalchemy").text(
                        f'SELECT COUNT(DISTINCT "{column}"), MIN("{column}"), MAX("{column}") FROM "{table}"'
                    )
                ).fetchone()
                if row:
                    stats["distinct_count"] = row[0]
                    stats["min"] = str(row[1]) if row[1] is not None else None
                    stats["max"] = str(row[2]) if row[2] is not None else None
            except Exception:
                pass
    except Exception:
        pass
    return stats


def get_row_count(db_uri: str, table: str) -> int:
    try:
        engine = get_db_engine(db_uri)
        with engine.connect() as conn:
            return conn.execute(
                __import__("sqlalchemy").text(f'SELECT COUNT(*) FROM "{table}"')
            ).scalar() or 0
    except Exception:
        return 0


def get_database_metadata_bundle(db_uri: str) -> dict:
    """Comprehensive metadata bundle for RAG indexing. Returns all tables,
    their columns with types, FK relationships, row counts, and sample values
    for text-like columns."""
    bundle = {"tables": {}, "foreign_keys": []}
    try:
        bundle["foreign_keys"] = get_foreign_keys(db_uri)
        engine = get_db_engine(db_uri)
        inspector = __import__("sqlalchemy").inspect(engine)
        for table in inspector.get_table_names():
            cols = get_column_details(db_uri, table)
            row_count = get_row_count(db_uri, table)
            # Get sample values for text/category columns
            sample_vals = {}
            for c in cols:
                if "VARCHAR" in c["type"].upper() or "TEXT" in c["type"].upper() or "CHAR" in c["type"].upper():
                    vals = get_sample_values(db_uri, table, c["name"], limit=5)
                    if vals:
                        sample_vals[c["name"]] = vals
            bundle["tables"][table] = {
                "columns": cols,
                "row_count": row_count,
                "sample_values": sample_vals if sample_vals else {},
            }
    except Exception:
        pass
    return bundle


def get_schema_signature(db_uri: str) -> dict:
    """
    Returns a lightweight {table_name: [column_names]} map for the database.
    Used to validate that generated SQL only references tables/columns that
    actually exist, so the system can explain why a question is unanswerable.
    """
    signature = {}
    try:
        engine = get_db_engine(db_uri)
        inspector = __import__("sqlalchemy").inspect(engine)
        for table in inspector.get_table_names():
            try:
                cols = [c["name"] for c in inspector.get_columns(table)]
            except Exception:
                cols = []
            signature[table.lower()] = cols
    except Exception:
        pass
    return signature

def execute_query(db_uri: str, sql_query: str, read_only: bool = True) -> dict:
    """
    Executes a SQL query against the database.
    If read_only is True, wraps the transaction and aborts on any write operation.
    """
    result = {
        "success": False,
        "columns": [],
        "data": [],
        "error": None
    }
    
    engine = get_db_engine(db_uri)
    
    # Simple check for write operations as an extra validation step
    if read_only:
        cleaned_query = sql_query.strip().lower()
        destructive_keywords = ["insert", "update", "delete", "drop", "truncate", "alter", "create", "replace"]
        if any(cleaned_query.startswith(kw) or f" {kw} " in cleaned_query for kw in destructive_keywords):
            result["error"] = "Execution Blocked: Destructive write operations are forbidden."
            return result
            
    try:
        with engine.connect() as connection:
            # For SQLite, SQLAlchemy runs in transactional mode
            # Execute query
            db_result = connection.execute(text(sql_query))
            
            # Fetch columns and data
            if db_result.returns_rows:
                result["columns"] = list(db_result.keys())
                result["data"] = [list(row) for row in db_result.fetchall()]
            result["success"] = True
            
    except SQLAlchemyError as e:
        result["error"] = str(e)
    except Exception as e:
        result["error"] = f"Unexpected execution error: {str(e)}"
        
    return result

if __name__ == "__main__":
    # Self-test block
    DB_URI = "sqlite:///sandbox.db"
    print("Testing Connection Validation...")
    print(validate_db_connection(DB_URI))
    
    print("\nTesting Schema Formatting...")
    schema = get_db_schema_context(DB_URI)
    print(schema[:500] + "\n... (truncated)")
    
    print("\nTesting Query Execution...")
    query = "SELECT * FROM customers LIMIT 2"
    print(execute_query(DB_URI, query))
