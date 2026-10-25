import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(dotenv_path=BASE_DIR / ".env")

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+psycopg2://coach:coach@localhost:5433/coach_v2")
# 模型选型（PRD §6.2，10-26 小王拍板：DeepSeek 为主，DashScope 兜底）
MODEL_PROVIDER = os.getenv("MODEL_PROVIDER", "deepseek")
MODEL_PRIMARY = os.getenv("MODEL_PRIMARY", "deepseek-chat")
FALLBACK_PROVIDER = os.getenv("FALLBACK_PROVIDER", "dashscope")
MODEL_FALLBACK = os.getenv("MODEL_FALLBACK", "qwen-plus-latest")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-v4")
EMBEDDING_DIM = int(os.getenv("EMBEDDING_DIM", "1024"))
GUARD_MAX_RETRIES = int(os.getenv("GUARD_MAX_RETRIES", "1"))
SYSTEM_PROMPT_VERSION = os.getenv("SYSTEM_PROMPT_VERSION", "v0.2")  # 提示词版本，校准通过后切换（PRD §5.5）

KNOWLEDGE_DIR = BASE_DIR / "knowledge"
SOURCES_DIR = KNOWLEDGE_DIR / "sources"
PROMPTS_DIR = BASE_DIR / "app" / "prompts"

# OpenAI 兼容端点注册表：换模型 = 这里的 key + .env，不动代码
ENDPOINTS = {
    "dashscope": {"base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1", "key_env": "DASHSCOPE_API_KEY"},
    "deepseek": {"base_url": "https://api.deepseek.com/v1", "key_env": "DEEPSEEK_API_KEY"},
}


def provider_endpoint(name: str) -> tuple[str, str]:
    """返回 (base_url, api_key)。"""
    ep = ENDPOINTS[name]
    return ep["base_url"], os.getenv(ep["key_env"], "")


def api_key() -> str:
    """embedding（DashScope）用。"""
    return os.getenv("DASHSCOPE_API_KEY", "")
