import os

from dotenv import load_dotenv

load_dotenv()

# Postgres is the deployment target; tests point this at SQLite so they need no server.
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg://opspilot:opspilot@localhost:5432/opspilot",
)

APP_ENV = os.getenv("APP_ENV", "local")

EMBEDDING_PROVIDER = os.getenv("EMBEDDING_PROVIDER", "openai")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
EMBEDDING_DIMENSIONS = int(os.getenv("EMBEDDING_DIMENSIONS", "1536"))

# Cosine distance cutoff for runbook chunks. Raise it for models with wider score spreads.
RUNBOOK_MAX_DISTANCE = float(os.getenv("RUNBOOK_MAX_DISTANCE", "0.75"))

# LangGraph checkpoints use a psycopg DSN, not a SQLAlchemy URL.
CHECKPOINT_DSN = os.getenv("CHECKPOINT_DATABASE_URL", DATABASE_URL).replace(
    "postgresql+psycopg://", "postgresql://", 1
)
