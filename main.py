import os
import base64
import time
import uuid
import concurrent.futures
from fastapi import FastAPI, HTTPException, Header, BackgroundTasks, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional, List
from collections import defaultdict

from db_utils import get_db_schema_context, execute_query, validate_db_connection
from multi_agent.orchestrator import Supervisor
from mail_utils import send_event_email
from seed_demo_db import seed_demo_db
import auth_db


# ── RAG index helpers ────────────────────────────────────────────────

def index_database_for_uri(db_uri: str) -> dict:
    """Build (or rebuild) the vector index for the given database URI."""
    try:
        from multi_agent.retrieval.embedder import get_embedder
        from multi_agent.retrieval.indexer import index_database
        embedder = get_embedder(provider=os.getenv("EMBEDDER_PROVIDER", "huggingface"),
                                model=os.getenv("EMBEDDER_MODEL"))
        if embedder is None:
            return {"success": False, "error": "RAG embeddings are disabled on this host."}
        store = index_database(db_uri, embedder, force_rebuild=True)
        return {"success": True, "indexed": bool(store.load())}
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_index_status(db_uri: str) -> dict:
    """Check whether a vector index exists for the given database."""
    try:
        from multi_agent.retrieval.embedder import get_embedder
        from multi_agent.retrieval.vector_store import VectorStore
        from multi_agent.retrieval.indexer import collection_name_for
        embedder = get_embedder(provider=os.getenv("EMBEDDER_PROVIDER", "huggingface"),
                                model=os.getenv("EMBEDDER_MODEL"))
        if embedder is None:
            return {"indexed": False, "document_count": 0}
        cname = collection_name_for(db_uri)
        store = VectorStore(embedder, collection_name=cname)
        has_index = store.load()
        # Count indexed documents
        count = 0
        if has_index:
            try:
                count = store.store._collection.count()
            except Exception:
                pass
        return {"indexed": has_index, "document_count": count}
    except Exception:
        return {"indexed": False, "document_count": 0}

app = FastAPI(title="SQL Genie: AI-Powered Natural Language to SQL Dashboard")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Rate Limiter (in-memory token bucket) ──
RATE_LIMIT = int(os.getenv("RATE_LIMIT_PER_MINUTE", "10"))
_rate_buckets: dict = defaultdict(lambda: {"tokens": RATE_LIMIT, "reset": time.time() + 60})

def check_rate_limit(request: Request):
    """Simple per-IP rate limiter. Raises 429 if exceeded."""
    ip = request.client.host if request.client else "unknown"
    now = time.time()
    bucket = _rate_buckets[ip]
    if now > bucket["reset"]:
        bucket["tokens"] = RATE_LIMIT
        bucket["reset"] = now + 60
    if bucket["tokens"] <= 0:
        raise HTTPException(status_code=429, detail=f"Rate limit exceeded. Max {RATE_LIMIT} requests per minute.")
    bucket["tokens"] -= 1

# Default database URI (Use local SQLite database sandbox)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_URI = "sqlite:///sandbox.db"

# Ensure the demo database exists so a fresh deployment works immediately
seed_demo_db()


def resolve_sqlite_path(db_path: str) -> str:
    """
    Resolve a SQLite database path. If the path is relative, anchor it to the
    project root so the sandbox DB is found regardless of the server's CWD.
    """
    if not db_path:
        return db_path
    if os.path.isabs(db_path):
        return db_path
    anchored = os.path.join(BASE_DIR, db_path)
    if os.path.exists(anchored):
        return anchored
    return db_path

# ── Conversation store (in-memory) ──
_conversations: dict = defaultdict(list)

def _get_conversation(cid: str) -> list:
    return _conversations.get(cid, [])

def _add_to_conversation(cid: str, role: str, content: str):
    _conversations[cid].append({"role": role, "content": content, "ts": time.time()})
    # Keep max 20 messages
    if len(_conversations[cid]) > 20:
        _conversations[cid] = _conversations[cid][-20:]


class QueryRequest(BaseModel):
    query: str
    provider: Optional[str] = "ollama"
    conversation_id: Optional[str] = None

class ConnectionRequest(BaseModel):
    db_type: str  # "sqlite", "postgresql", "mysql"
    host: Optional[str] = None
    port: Optional[int] = None
    username: Optional[str] = None
    password: Optional[str] = None
    database: str
    ssl_mode: Optional[str] = "disable"

class AuthRequest(BaseModel):
    username: str
    password: str
    name: Optional[str] = None
    email: Optional[str] = None

def assemble_uri(req: ConnectionRequest) -> str:
    """
    Constructs a SQLAlchemy connection URI from discrete credential fields.
    Password is URL-encoded to handle special characters (@, :, /, etc).
    """
    import urllib.parse
    db_type = req.db_type.lower()
    pw_enc = urllib.parse.quote(req.password or "", safe="")
    if db_type == "sqlite":
        db_path = req.database
        if db_path.startswith("sqlite:///"):
            return db_path
        db_path = resolve_sqlite_path(db_path)
        return f"sqlite:///{db_path}"
    elif db_type == "postgresql":
        port = req.port or 5432
        uri = f"postgresql://{req.username}:{pw_enc}@{req.host}:{port}/{req.database}"
        if req.ssl_mode and req.ssl_mode != "disable":
            uri += f"?sslmode={req.ssl_mode}"
        return uri
    elif db_type == "mysql":
        port = req.port or 3306
        uri = f"mysql+pymysql://{req.username}:{pw_enc}@{req.host}:{port}/{req.database}"
        if req.ssl_mode and req.ssl_mode != "disable":
            uri += f"?ssl_mode={req.ssl_mode}"
        return uri
    else:
        raise ValueError(f"Unsupported database type: {db_type}")

def get_user_id_from_token(authorization: Optional[str]) -> int:
    """Extract user ID from JWT token or API key in the Authorization header."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Authentication credentials missing or invalid.")
    token = authorization.split(" ")[1]

    # 1. Try JWT token
    payload = auth_db.verify_token(token)
    if payload:
        return payload["user_id"]

    # 2. Try API key (starts with sg_)
    if token.startswith("sg_"):
        user = auth_db.verify_api_key(token)
        if user:
            return user["user_id"]

    raise HTTPException(status_code=401, detail="Authentication session invalid or expired.")

def resolve_db_uri(x_database_uri: Optional[str], authorization: Optional[str]) -> str:
    """
    Determines connection URI based on dynamic headers, user profile, or sandbox fallback.
    """
    # 1. Direct header override takes precedence
    if x_database_uri:
        return x_database_uri
        
    # 2. Check if logged-in user profile connection is saved persistently in users.db
    if authorization and authorization.startswith("Bearer "):
        try:
            user_id = get_user_id_from_token(authorization)
            profile = auth_db.get_connection_profile(user_id)
            if profile:
                req = ConnectionRequest(**profile)
                return assemble_uri(req)
        except Exception:
            pass
            
    # 3. Default local SQLite sandbox fallback
    return f"sqlite:///{resolve_sqlite_path(DB_URI.replace('sqlite:///', ''))}"

# Serve index.html directly on the root endpoint
@app.get("/")
def get_index():
    # If static index.html exists, return it
    if os.path.exists("static/index.html"):
        return FileResponse("static/index.html")
    return HTMLResponse("<h1>SQL Genie Backend is Running.</h1><p>Please create index.html in the static folder.</p>")

@app.get("/health")
def health():
    """Lightweight health check for platform probes and keep-alive pings."""
    return {"status": "ok"}

# --- Authentication API Routes ---

@app.post("/api/auth/signup")
def user_signup(request: AuthRequest, background_tasks: BackgroundTasks):
    """
    Registers a new user account with extended credentials (Name, Email, password rules) and triggers a notification.
    """
    username = request.username.strip()
    name = (request.name or "").strip()
    email = (request.email or "").strip()
    password = request.password
    
    # Check username
    if len(username) < 3:
        raise HTTPException(status_code=400, detail="Username must be at least 3 characters long.")
    # Check email presence
    if not email or "@" not in email:
        raise HTTPException(status_code=400, detail="A valid email address is required.")
    # Check name presence
    if not name:
        raise HTTPException(status_code=400, detail="Full Name is required.")
        
    # Enforce alphanumeric password logic: length >= 8, containing both letters and numbers
    has_letter = any(c.isalpha() for c in password)
    has_digit = any(c.isdigit() for c in password)
    if len(password) < 8 or not has_letter or not has_digit:
        raise HTTPException(
            status_code=400,
            detail="Password must be at least 8 characters long and contain both letters and numbers."
        )
        
    user_id = auth_db.create_user(username, password, name, email)
    if not user_id:
        raise HTTPException(status_code=400, detail="Username or Email already registered.")
        
    # Dispatch background email warning alert
    background_tasks.add_task(send_event_email, email, name, "signup")
        
    # Issue JWT token
    token = auth_db.create_token(user_id, username)
    return {
        "success": True,
        "token": token,
        "username": username
    }

@app.post("/api/auth/login")
def user_login(request: AuthRequest, background_tasks: BackgroundTasks):
    """
    Logs in a user, returning their JWT session token, and triggers a notification alert.
    """
    user = auth_db.verify_user(request.username.strip(), request.password)
    if not user:
        raise HTTPException(status_code=400, detail="Incorrect username or password.")
        
    # Dispatch background login email alert
    if user.get("email"):
        background_tasks.add_task(send_event_email, user["email"], user["name"], "login")
        
    token = auth_db.create_token(user["id"], user["username"])
    return {
        "success": True,
        "token": token,
        "username": user["username"]
    }

@app.get("/api/auth/connection")
def get_user_connection(authorization: Optional[str] = Header(None)):
    """
    Returns the persistently saved connection details (excluding password).
    """
    user_id = get_user_id_from_token(authorization)
    profile = auth_db.get_connection_profile(user_id)
    if not profile:
        return {"success": False, "profile": None}
    
    # Hide password in response
    profile_safe = profile.copy()
    profile_safe["password"] = "*****" if profile_safe["password"] else ""
    return {
        "success": True,
        "profile": profile_safe
    }

@app.post("/api/auth/connection")
def save_user_connection(request: ConnectionRequest, background_tasks: BackgroundTasks,
                         authorization: Optional[str] = Header(None)):
    """
    Validates and persistently saves custom connection credentials for a user.
    Also triggers RAG indexing of the database schema in the background.
    """
    user_id = get_user_id_from_token(authorization)
    
    # Validate the connection before saving it
    try:
        uri = assemble_uri(request)
        connection_report = validate_db_connection(uri)
        if not connection_report["success"]:
            raise HTTPException(status_code=400, detail=connection_report["message"])
            
        # Save connection configuration persistently
        auth_db.save_connection(
            user_id=user_id,
            db_type=request.db_type,
            host=request.host,
            port=request.port,
            username=request.username,
            password=request.password,
            database=request.database,
            ssl_mode=request.ssl_mode
        )

        # Index the database in the background
        background_tasks.add_task(index_database_for_uri, uri)
        
        return {
            "success": True,
            "message": "Connection verified, saved, and schema indexed for RAG.",
            "tables": connection_report["tables"]
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# --- API Key Management Routes ---

class ApiKeyCreateRequest(BaseModel):
    name: Optional[str] = "default"

class ApiKeyResponse(BaseModel):
    id: int
    prefix: str
    name: str
    created_at: int
    last_used_at: Optional[int] = None
    revoked: bool

@app.post("/api/auth/keys", response_model=dict)
def create_api_key(request: ApiKeyCreateRequest, authorization: Optional[str] = Header(None)):
    """Generate a new API key for programmatic access."""
    user_id = get_user_id_from_token(authorization)
    raw_key = auth_db.create_api_key(user_id, name=request.name)
    if not raw_key:
        raise HTTPException(status_code=500, detail="Failed to create API key.")
    return {"success": True, "key": raw_key, "name": request.name}

@app.get("/api/auth/keys", response_model=dict)
def list_api_keys(authorization: Optional[str] = Header(None)):
    """List all non-revoked API keys for the authenticated user."""
    user_id = get_user_id_from_token(authorization)
    keys = auth_db.list_api_keys(user_id)
    return {"success": True, "keys": keys}

@app.delete("/api/auth/keys/{key_id}", response_model=dict)
def revoke_api_key(key_id: int, authorization: Optional[str] = Header(None)):
    """Revoke an API key by its ID."""
    user_id = get_user_id_from_token(authorization)
    ok = auth_db.revoke_api_key(key_id, user_id)
    if not ok:
        raise HTTPException(status_code=404, detail="API key not found or already revoked.")
    return {"success": True, "message": "API key revoked."}


# --- Core Execution Routes ---

@app.post("/api/connect")
def connect_database(request: ConnectionRequest, background_tasks: BackgroundTasks):
    """
    Tests and verifies custom user database connection settings temporarily.
    Also triggers RAG indexing of the database schema in the background.
    """
    try:
        uri = assemble_uri(request)
        connection_report = validate_db_connection(uri)
        if not connection_report["success"]:
            raise HTTPException(status_code=400, detail=connection_report["message"])

        # Index the database in the background
        background_tasks.add_task(index_database_for_uri, uri)

        return {
            "success": True,
            "message": "Connection verified and schema indexed for RAG.",
            "db_uri": uri,
            "tables": connection_report["tables"]
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/reindex")
def reindex_database(background_tasks: BackgroundTasks,
                     x_database_uri: Optional[str] = Header(None),
                     authorization: Optional[str] = Header(None)):
    """Force-rebuild the RAG vector index for the connected database."""
    db_uri = resolve_db_uri(x_database_uri, authorization)
    background_tasks.add_task(index_database_for_uri, db_uri)
    return {"success": True, "message": "Reindexing started in the background."}


@app.get("/api/index/status")
def index_status(x_database_uri: Optional[str] = Header(None),
                 authorization: Optional[str] = Header(None)):
    """Check whether the connected database has been indexed for RAG."""
    db_uri = resolve_db_uri(x_database_uri, authorization)
    return get_index_status(db_uri)

@app.get("/api/schema")
def get_schema(x_database_uri: Optional[str] = Header(None), authorization: Optional[str] = Header(None)):
    """
    Returns the database schema context. Reads database URI dynamically from headers/token.
    """
    db_uri = resolve_db_uri(x_database_uri, authorization)
    connection_report = validate_db_connection(db_uri)
    if not connection_report["success"]:
        raise HTTPException(status_code=400, detail=connection_report["message"])
        
    schema_context = get_db_schema_context(db_uri)
    return {
        "success": True,
        "tables": connection_report["tables"],
        "schema_context": schema_context
    }

EXEC_TIMEOUT = int(os.getenv("QUERY_TIMEOUT_SECONDS", "120"))

@app.post("/api/query")
def run_query(request: QueryRequest, req: Request,
              x_database_uri: Optional[str] = Header(None),
              authorization: Optional[str] = Header(None)):
    check_rate_limit(req)
    """
    Core NL2SQL endpoint. Runs input validation guardrails, self-correcting agent loop,
    executes query dynamically, and formats the output into conversational text.
    """
    db_uri = resolve_db_uri(x_database_uri, authorization)

    # Multi-turn conversation support
    cid = request.conversation_id or uuid.uuid4().hex[:12]
    conv = _get_conversation(cid)

    # 1. Run the multi-agent supervisor pipeline on the requested database
    supervisor = Supervisor(provider=request.provider, max_iterations=3)

    # Run with server-side timeout to prevent hanging LLM calls
    with concurrent.futures.ThreadPoolExecutor() as pool:
        fut = pool.submit(supervisor.run, user_query=request.query, db_uri=db_uri, conversation_history=conv)
        try:
            state = fut.result(timeout=EXEC_TIMEOUT)
        except concurrent.futures.TimeoutError:
            return {
                "success": False,
                "error_type": "timeout",
                "message": f"The query took longer than {EXEC_TIMEOUT}s and was cancelled. Try simplifying your question or using a faster LLM provider.",
                "logs": []
            }

    # Store conversation turn
    _add_to_conversation(cid, "user", request.query)

    # If blocked by the Guardrail agent
    if state.status == "blocked":
        _add_to_conversation(cid, "assistant", f"[Blocked] {state.block_reason}")
        return {
            "success": False,
            "error_type": "security_violation",
            "message": state.block_reason or "Blocked by security guardrail.",
            "logs": state.logs,
            "conversation_id": cid,
        }

    # If the question cannot be answered with the available schema
    if state.status == "not_answerable":
        _add_to_conversation(cid, "assistant", state.answer or state.block_reason or "")
        return {
            "success": False,
            "error_type": "not_answerable",
            "message": state.block_reason or "This question cannot be answered with the available data.",
            "logs": state.logs,
            "sql_query": state.sql_query,
            "answer": state.answer,
            "conversation_id": cid,
        }

    sql_query = state.sql_query
    explanation = state.explanation

    # 2. Execution result is already produced by the Formatter stage's upstream step
    execution_result = state.execution_result or execute_query(db_uri, sql_query or "", read_only=True)

    if not execution_result["success"]:
        _add_to_conversation(cid, "assistant", f"[Error] {execution_result['error']}")
        return {
            "success": False,
            "error_type": "execution_failed",
            "message": execution_result["error"],
            "logs": state.logs,
            "sql_query": sql_query,
            "conversation_id": cid,
        }

    _add_to_conversation(cid, "assistant", state.answer or "")

    return {
        "success": True,
        "logs": state.logs,
        "sql_query": sql_query,
        "explanation": explanation,
        "execution_result": execution_result,
        "answer": state.answer,
        "conversation_id": cid,
    }

# Mount static folder if it exists
if not os.path.exists("static"):
    os.makedirs("static")
app.mount("/static", StaticFiles(directory="static"), name="static")

if __name__ == "__main__":
    import uvicorn
    # Start uvicorn server locally on port 8000
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)
