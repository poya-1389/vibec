import os
from dataclasses import dataclass

@dataclass(frozen=True)
class Settings:
    bot_token: str = os.getenv("VIBE_BOT_TOKEN", "")
    api_base: str = os.getenv("VIBE_API_BASE", "https://api.vibegram.chat")
    owner_username: str = os.getenv("OWNER_USERNAME", "VibeChat")
    owner_id: int = int(os.getenv("OWNER_ID", "0"))
    database_url: str = os.getenv("DATABASE_PATH", "/data/vibechat.db")
    default_language: str = os.getenv("DEFAULT_LANGUAGE", "fa")
    free_daily_limit: int = int(os.getenv("FREE_DAILY_LIMIT", "0"))
    ai_timeout: float = float(os.getenv("AI_TIMEOUT", "45"))
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")
    groq_api_key: str = os.getenv("GROQ_API_KEY", "")
    gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    groq_model: str = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
    gemini_base_url: str = os.getenv(
        "GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai/"
    )
    groq_base_url: str = os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1/")
    enable_stars: bool = os.getenv("ENABLE_STARS", "false").lower() == "true"
    pro_price_stars: int = int(os.getenv("PRO_PRICE_STARS", "250"))
    pro_duration_days: int = int(os.getenv("PRO_DURATION_DAYS", "30"))

settings = Settings()
