import json

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings


def _normalize_url(url: str) -> str:
    # Render / Neon / Supabase 給的網址常是 postgres:// 開頭，轉成 psycopg3 驅動
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    return url


DB_URL = _normalize_url(settings.DATABASE_URL)

engine = create_engine(
    DB_URL,
    connect_args={"check_same_thread": False} if DB_URL.startswith("sqlite") else {},
    pool_pre_ping=True,
    # 讓 JSON 欄位直接存中文，搜尋標籤時才找得到
    json_serializer=lambda obj: json.dumps(obj, ensure_ascii=False),
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def migrate() -> None:
    """補上舊資料表缺少的欄位（create_all 不會幫既有的表加欄位）。"""
    from sqlalchemy import inspect, text

    insp = inspect(engine)
    if "users" in insp.get_table_names():
        cols = {c["name"] for c in insp.get_columns("users")}
        if "status" not in cols:
            with engine.begin() as conn:
                # 既有使用者視為已核准
                conn.execute(text("ALTER TABLE users ADD COLUMN status VARCHAR(16) NOT NULL DEFAULT 'approved'"))


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
