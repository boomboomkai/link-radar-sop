import os

from dotenv import load_dotenv

load_dotenv()


def _bool(name: str, default: bool) -> bool:
    v = os.getenv(name)
    return default if v is None else v.strip().lower() in ("1", "true", "yes", "on")


class Settings:
    LINE_CHANNEL_SECRET: str = os.getenv("LINE_CHANNEL_SECRET", "")
    LINE_CHANNEL_ACCESS_TOKEN: str = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")
    LINE_PUSH_FALLBACK: bool = _bool("LINE_PUSH_FALLBACK", True)
    LINE_LOGIN_CHANNEL_ID: str = os.getenv("LINE_LOGIN_CHANNEL_ID", "")
    LIFF_URL: str = os.getenv("LIFF_URL", "")
    # 管理者的 LINE userId（U 開頭），多個用逗號分隔。有設定時，新使用者需經管理者核准才能使用
    ADMIN_LINE_USER_IDS: list[str] = [u.strip() for u in os.getenv("ADMIN_LINE_USER_IDS", "").split(",")
                                      if u.strip()]

    ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
    CLAUDE_MODEL: str = os.getenv("CLAUDE_MODEL", "claude-haiku-5-5")

    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./link_radar.db")
    CORS_ORIGINS: list[str] = [o.strip() for o in os.getenv("CORS_ORIGINS", "*").split(",") if o.strip()]
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")


settings = Settings()
