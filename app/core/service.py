"""核心流程：收藏、查詢、修改。LINE bot、LIFF 網頁、未來的 App 都呼叫這裡。"""
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import String, cast, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.core import analyzer
from app.core.analyzer import Analysis
from app.core.categories import CATEGORY_MAP
from app.core.fetcher import FetchResult, canonicalize, fetch
from app.models import Item, User

log = logging.getLogger(__name__)

# 連結抓不完整時，這段時間內補傳的截圖會合併進那一筆
PARTIAL_MERGE_WINDOW = timedelta(minutes=10)


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _apply(item: Item, a: Analysis) -> None:
    item.category = a.category
    item.title = a.title
    item.summary = a.summary
    item.key_points = a.key_points
    item.tags = a.tags
    item.details = a.details


# ── 使用者 ──────────────────────────────────────────────

def is_admin(line_user_id: str | None) -> bool:
    return bool(line_user_id) and line_user_id in settings.ADMIN_LINE_USER_IDS


def ensure_line_user(db: Session, line_user_id: str, display_name: str | None = None) -> tuple[User, bool]:
    """回傳 (使用者, 是否新建立)。有設管理者時，新使用者預設為待審核。"""
    user = db.scalar(select(User).where(User.line_user_id == line_user_id))
    created = False
    if not user:
        need_review = bool(settings.ADMIN_LINE_USER_IDS) and not is_admin(line_user_id)
        user = User(line_user_id=line_user_id, display_name=display_name,
                    status="pending" if need_review else "approved")
        db.add(user)
        created = True
    if display_name and user.display_name != display_name:
        user.display_name = display_name
    if is_admin(line_user_id) and user.status != "approved":
        user.status = "approved"  # 管理者永遠可用
    db.commit()
    db.refresh(user)
    return user, created


def get_or_create_line_user(db: Session, line_user_id: str, display_name: str | None = None) -> User:
    return ensure_line_user(db, line_user_id, display_name)[0]


def get_user(db: Session, user_id: int) -> User | None:
    return db.get(User, user_id)


def list_users(db: Session, status: str | None = None) -> list[User]:
    stmt = select(User).order_by(User.id)
    if status:
        stmt = stmt.where(User.status == status)
    return list(db.scalars(stmt))


def set_user_status(db: Session, user: User, status: str) -> User:
    if status not in ("pending", "approved", "blocked"):
        raise ValueError("未知的狀態")
    user.status = status
    db.commit()
    db.refresh(user)
    return user


def get_user_by_token(db: Session, token: str) -> User | None:
    return db.scalar(select(User).where(User.api_token == token))


# ── 收藏 ────────────────────────────────────────────────

def _find_by_url(db: Session, user: User, canonical: str) -> Item | None:
    return db.scalar(select(Item).where(Item.user_id == user.id, Item.canonical_url == canonical))


async def _analyze_into(item: Item, fr: FetchResult, note: str | None) -> None:
    try:
        a = await analyzer.analyze_fetch(fr, note)
        _apply(item, a)
        item.status = "ok" if (fr.ok and a.content_sufficient) else "partial"
    except Exception:
        log.exception("AI 分析失敗：%s", fr.final_url)
        item.category = item.category or "other"
        item.title = (fr.title or fr.final_url)[:300]
        item.summary = "AI 分析失敗，已先存下連結，之後可以重新分析。"
        item.status = "failed"


async def ingest_url(db: Session, user: User, url: str, note: str | None = None) -> tuple[Item, bool]:
    """回傳 (收藏, 是否為新收藏)。同一個連結不會重複存。"""
    canonical = canonicalize(url)
    if existing := _find_by_url(db, user, canonical):
        return existing, False

    fr = await fetch(url)
    final_canonical = canonicalize(fr.final_url)
    if final_canonical != canonical and (existing := _find_by_url(db, user, final_canonical)):
        return existing, False

    item = Item(
        user_id=user.id, source_type="url", url=fr.final_url, canonical_url=final_canonical,
        platform=fr.platform, author=fr.author, image_url=fr.image_url,
        raw_text=fr.combined_text()[:20000] or None, user_note=note,
    )
    await _analyze_into(item, fr, note)
    db.add(item)
    try:
        db.commit()
    except IntegrityError:  # 同時送兩次同一個連結
        db.rollback()
        return _find_by_url(db, user, final_canonical), False
    db.refresh(item)
    return item, True


async def ingest_image(
    db: Session, user: User, data: bytes, media_type: str, note: str | None = None
) -> tuple[Item, bool]:
    """回傳 (收藏, 是否合併到先前抓不完整的連結)。"""
    prior = db.scalar(
        select(Item)
        .where(Item.user_id == user.id, Item.status.in_(("partial", "failed")), Item.source_type == "url")
        .order_by(Item.id.desc())
        .limit(1)
    )
    if prior and datetime.now(timezone.utc) - _aware(prior.created_at) > PARTIAL_MERGE_WINDOW:
        prior = None

    a = await analyzer.analyze_image(
        data, media_type, note,
        prior_url=prior.url if prior else None,
        prior_text=prior.raw_text if prior else None,
    )

    if prior:
        _apply(prior, a)
        prior.source_type = "url+image"
        prior.status = "ok"
        if note:
            prior.user_note = "\n".join(p for p in (prior.user_note, note) if p)
        prior.raw_text = ((prior.raw_text or "") + "\n\n［截圖辨識］\n" + a.extracted_text)[:20000]
        db.commit()
        db.refresh(prior)
        return prior, True

    item = Item(
        user_id=user.id, source_type="image", platform="screenshot", user_note=note,
        raw_text=a.extracted_text or None, status="ok" if a.content_sufficient else "partial",
    )
    _apply(item, a)
    db.add(item)
    db.commit()
    db.refresh(item)
    return item, False


async def reanalyze_item(db: Session, item: Item) -> Item:
    if not item.url:
        raise ValueError("截圖收藏沒有連結可以重新抓取")
    fr = await fetch(item.url)
    item.raw_text = fr.combined_text()[:20000] or item.raw_text
    item.image_url = fr.image_url or item.image_url
    await _analyze_into(item, fr, item.user_note)
    db.commit()
    db.refresh(item)
    return item


# ── 查詢與修改 ──────────────────────────────────────────

def list_items(
    db: Session, user: User, category: str | None = None, q: str | None = None,
    limit: int = 20, before_id: int | None = None,
) -> tuple[list[Item], int | None]:
    """以 id 倒序分頁。回傳 (項目, 下一頁 cursor)。"""
    stmt = select(Item).where(Item.user_id == user.id)
    if category:
        stmt = stmt.where(Item.category == category)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(
            Item.title.ilike(like), Item.summary.ilike(like), Item.raw_text.ilike(like),
            Item.user_note.ilike(like), cast(Item.tags, String).ilike(like),
        ))
    if before_id:
        stmt = stmt.where(Item.id < before_id)
    rows = list(db.scalars(stmt.order_by(Item.id.desc()).limit(limit + 1)))
    next_cursor = rows[limit - 1].id if len(rows) > limit else None
    return rows[:limit], next_cursor


def category_counts(db: Session, user: User) -> dict[str, int]:
    rows = db.execute(
        select(Item.category, func.count()).where(Item.user_id == user.id).group_by(Item.category)
    ).all()
    return {cat: n for cat, n in rows}


def get_item(db: Session, user: User, item_id: int) -> Item | None:
    return db.scalar(select(Item).where(Item.id == item_id, Item.user_id == user.id))


def latest_item(db: Session, user: User) -> Item | None:
    return db.scalar(select(Item).where(Item.user_id == user.id).order_by(Item.id.desc()).limit(1))


def update_item(db: Session, item: Item, **changes) -> Item:
    if "category" in changes and changes["category"] not in CATEGORY_MAP:
        raise ValueError("未知的分類")
    for k, v in changes.items():
        if v is not None and k in ("category", "title", "tags", "user_note"):
            setattr(item, k, v)
    db.commit()
    db.refresh(item)
    return item


def delete_item(db: Session, item: Item) -> None:
    db.delete(item)
    db.commit()
