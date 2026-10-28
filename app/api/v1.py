"""REST API v1：給 LIFF 網頁與未來的 iOS／Android App 使用。完整文件在 /docs。"""
import httpx
from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from app.config import settings
from app.core import service
from app.core.analyzer import MAX_IMAGE_BYTES
from app.core.categories import CATEGORIES, CATEGORY_MAP
from app.db import get_db
from app.models import Item, User
from app.schemas import (
    CategoryOut, ItemCreate, ItemCreated, ItemList, ItemOut, ItemUpdate, LineLoginIn, TokenOut,
)

router = APIRouter(prefix="/api/v1")

ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}


def current_user(authorization: str | None = Header(None), db: Session = Depends(get_db)) -> User:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "缺少 Bearer token")
    user = service.get_user_by_token(db, authorization.split(" ", 1)[1].strip())
    if not user:
        raise HTTPException(401, "token 無效")
    if user.status != "approved":
        raise HTTPException(403, "帳號尚未通過審核")
    return user


def _own_item(item_id: int, user: User, db: Session) -> Item:
    item = service.get_item(db, user, item_id)
    if not item:
        raise HTTPException(404, "找不到這筆收藏")
    return item


# ── 登入 ────────────────────────────────────────────────

@router.post("/auth/line", response_model=TokenOut, tags=["auth"])
async def login_with_line(body: LineLoginIn, db: Session = Depends(get_db)):
    """LIFF 或 App 用 LINE Login 取得 ID token，換成本服務的 access token。"""
    if not settings.LINE_LOGIN_CHANNEL_ID:
        raise HTTPException(503, "尚未設定 LINE_LOGIN_CHANNEL_ID")
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.post(
            "https://api.line.me/oauth2/v2.1/verify",
            data={"id_token": body.id_token, "client_id": settings.LINE_LOGIN_CHANNEL_ID},
        )
    if r.status_code != 200:
        raise HTTPException(401, "LINE ID token 驗證失敗")
    info = r.json()
    user = service.get_or_create_line_user(db, info["sub"], info.get("name"))
    return TokenOut(access_token=user.api_token, user_id=user.id, display_name=user.display_name)


# ── 分類 ────────────────────────────────────────────────

@router.get("/categories", response_model=list[CategoryOut], tags=["items"])
def categories(user: User = Depends(current_user), db: Session = Depends(get_db)):
    counts = service.category_counts(db, user)
    return [CategoryOut(key=c.key, label=c.label, emoji=c.emoji, count=counts.get(c.key, 0))
            for c in CATEGORIES]


# ── 收藏 ────────────────────────────────────────────────

@router.get("/items", response_model=ItemList, tags=["items"])
def list_items(
    category: str | None = None,
    q: str | None = Query(None, description="搜尋標題、摘要、內文、標籤、備註"),
    limit: int = Query(20, ge=1, le=100),
    before_id: int | None = None,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    items, cursor = service.list_items(db, user, category, q, limit, before_id)
    return ItemList(items=items, next_cursor=cursor)


@router.post("/items", response_model=ItemCreated, tags=["items"])
async def create_item(body: ItemCreate, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """App 的分享選單會呼叫這個。"""
    if not body.url.startswith(("http://", "https://")):
        raise HTTPException(422, "請提供 http(s) 連結")
    item, created = await service.ingest_url(db, user, body.url, body.note)
    return ItemCreated(item=item, created=created)


@router.post("/items/image", response_model=ItemCreated, tags=["items"])
async def create_item_from_image(
    file: UploadFile = File(...),
    note: str | None = Form(None),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    if file.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(415, "只支援 JPEG、PNG、WebP、GIF")
    data = await file.read()
    if len(data) > MAX_IMAGE_BYTES:
        raise HTTPException(413, "圖片超過 5MB")
    item, merged = await service.ingest_image(db, user, data, file.content_type, note)
    return ItemCreated(item=item, created=not merged)


@router.get("/items/{item_id}", response_model=ItemOut, tags=["items"])
def get_item(item_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return _own_item(item_id, user, db)


@router.patch("/items/{item_id}", response_model=ItemOut, tags=["items"])
def update_item(item_id: int, body: ItemUpdate, user: User = Depends(current_user),
                db: Session = Depends(get_db)):
    item = _own_item(item_id, user, db)
    if body.category and body.category not in CATEGORY_MAP:
        raise HTTPException(422, "未知的分類")
    return service.update_item(db, item, **body.model_dump(exclude_none=True))


@router.post("/items/{item_id}/reanalyze", response_model=ItemOut, tags=["items"])
async def reanalyze(item_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    item = _own_item(item_id, user, db)
    try:
        return await service.reanalyze_item(db, item)
    except ValueError as e:
        raise HTTPException(422, str(e))


@router.delete("/items/{item_id}", status_code=204, tags=["items"])
def delete_item(item_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    service.delete_item(db, _own_item(item_id, user, db))
