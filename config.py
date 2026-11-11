import os


def _load_dotenv() -> None:
    """Load key=value pairs from .env in the project root if not already set."""
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if not os.path.exists(env_path):
        return
    with open(env_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = val


_load_dotenv()

# ── LLM (Gemini API) ───────────────────────────────────────────────────────────
# Set GEMINI_API_KEY in .env (recommended) or your environment, or paste it here.
# Get a free key at: https://aistudio.google.com/apikey
GEMINI_API_KEY = ""               # leave empty to read from .env / environment
GEMINI_MODEL   = "gemini-3.5-flash-lite"  # fast & reliable; or "gemini-3.8-flash" / "gemini-4-argon"
THINKING_LEVEL = "low"            # "low" (faster) | "medium" (default) | "high"
REQUEST_TIMEOUT = 60.0            # HTTP timeout in seconds per API call

# ── Database ────────────────────────────────────────────────────────────────────
DB_TYPE     = "sqlite"            # "sqlite" | "postgres"
SQLITE_PATH = "db/ecommerce.db"

# PostgreSQL — only used when DB_TYPE = "postgres"
PG_DSN = "postgresql://user:password@localhost:5432/mydb"

# ── Agent ───────────────────────────────────────────────────────────────────────
MAX_RETRIES = 3                   # max self-correction retries on SQL error
