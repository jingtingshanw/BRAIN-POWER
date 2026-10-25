import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(dotenv_path=BASE_DIR / ".env")

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+psycopg2://coach:coach@localhost:5433/coach_v2")
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "dashscope")
MODEL_PRIMARY = os.getenv("MODEL_PRIMARY", "qwen-plus-latest")
MODEL_FALLBACK = os.getenv("MODEL_FALLBACK", "qwen-flash")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-v4")
EMBEDDING_DIM = int(os.getenv("EMBEDDING_DIM", "1024"))
GUARD_MAX_RETRIES = int(os.getenv("GUARD_MAX_RETRIES", "1"))
SYSTEM_PROMPT_VERSION = os.getenv("SYSTEM_PROMPT_VERSION", "v0.1")  # 提示词版本，校准通过后切换（PRD §5.5）

KNOWLEDGE_DIR = BASE_DIR / "knowledge"
SOURCES_DIR = KNOWLEDGE_DIR / "sources"
PROMPTS_DIR = BASE_DIR / "app" / "prompts"


def api_key() -> str:
    key = os.getenv("DASHSCOPE_API_KEY", "")
    return key
