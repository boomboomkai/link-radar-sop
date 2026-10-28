import secrets
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_token() -> str:
    return secrets.token_urlsafe(32)


class User(Base):
    """一個使用者。目前以 LINE userId 識別；App 用 LINE Login 登入後對應到同一筆。"""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    line_user_id: Mapped[str | None] = mapped_column(String(64), unique=True, index=True)
    display_name: Mapped[str | None] = mapped_column(String(100))
    api_token: Mapped[str] = mapped_column(String(64), unique=True, index=True, default=new_token)
    status: Mapped[str] = mapped_column(String(16), default="approved")  # pending / approved / blocked
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Item(Base):
    """一筆收藏：一個連結或一張截圖，加上 AI 分析結果。"""

    __tablename__ = "items"
    __table_args__ = (
        UniqueConstraint("user_id", "canonical_url", name="uq_item_user_url"),
        Index("ix_items_user_category", "user_id", "category"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)

    source_type: Mapped[str] = mapped_column(String(16), default="url")  # url / image / url+image
    url: Mapped[str | None] = mapped_column(Text)
    canonical_url: Mapped[str | None] = mapped_column(String(1000))  # 去掉追蹤參數，用來判斷重複
    platform: Mapped[str] = mapped_column(String(32), default="web")

    category: Mapped[str] = mapped_column(String(32), default="other")
    title: Mapped[str | None] = mapped_column(String(300))
    summary: Mapped[str | None] = mapped_column(Text)
    key_points: Mapped[list] = mapped_column(JSON, default=list)
    tags: Mapped[list] = mapped_column(JSON, default=list)
    details: Mapped[dict] = mapped_column(JSON, default=dict)  # 依分類而異：店名、地址、工具名…

    author: Mapped[str | None] = mapped_column(String(200))
    image_url: Mapped[str | None] = mapped_column(Text)
    raw_text: Mapped[str | None] = mapped_column(Text)
    user_note: Mapped[str | None] = mapped_column(Text)

    status: Mapped[str] = mapped_column(String(16), default="ok")  # ok / partial / failed
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
