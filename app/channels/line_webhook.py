"""LINE 轉接層：把 LINE 事件翻譯成 core/service 的呼叫，再把結果翻譯成 LINE 訊息。"""
import logging
import re

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from linebot.v3 import WebhookParser
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import (
    AsyncApiClient, AsyncMessagingApi, AsyncMessagingApiBlob, Configuration, PushMessageRequest,
    ReplyMessageRequest, ShowLoadingAnimationRequest,
)
from linebot.v3.webhooks import FollowEvent, ImageMessageContent, MessageEvent, TextMessageContent

from app.channels import line_flex as ui
from app.config import settings
from app.core import service
from app.core.categories import CATEGORIES, find_category
from app.core.fetcher import extract_urls
from app.db import SessionLocal

log = logging.getLogger(__name__)
router = APIRouter()
parser = WebhookParser(settings.LINE_CHANNEL_SECRET)
line_config = Configuration(access_token=settings.LINE_CHANNEL_ACCESS_TOKEN)

MAX_URLS_PER_MESSAGE = 3

HELP = (
    "👋 把 FB、IG、Threads、X 或任何網頁連結分享給我，我會自動分類並摘要。\n\n"
    "📸 平台擋住內容時，補傳一張貼文截圖，我會合併到上一筆；直接傳截圖也可以。\n\n"
    "指令：\n"
    "・最近：最近 5 筆收藏\n"
    "・分類：各分類數量\n"
    "・看 餐廳：看某個分類\n"
    "・搜尋 拉麵：搜尋收藏\n"
    "・改 旅遊：把上一筆改成別的分類\n"
    "・刪除：刪除上一筆（卡片和清單上也有刪除鈕）\n"
    "・綁定：取得網頁／App 登入用的金鑰"
)
ADMIN_HELP = (
    "🛠 管理者指令：\n"
    "・待審核：列出等待核准的人\n"
    "・成員：列出所有使用者\n"
    "・核准 #編號／拒絕 #編號"
)
PENDING_MSG = "👋 已收到你的使用申請！\n管理者核准後就能開始使用，到時會通知你 🙏"
BLOCKED_MSG = "抱歉，你目前沒有使用權限。"
STATUS_LABEL = {"pending": "⏳ 待審核", "approved": "✅ 已核准", "blocked": "⛔ 已拒絕"}
DEFAULT_QR = [("最近收藏", "最近"), ("分類", "分類"), ("說明", "說明")]


@router.post("/line/webhook")
async def line_webhook(request: Request, background: BackgroundTasks):
    signature = request.headers.get("X-Line-Signature", "")
    body = (await request.body()).decode("utf-8")
    try:
        events = parser.parse(body, signature)
    except InvalidSignatureError:
        raise HTTPException(status_code=400, detail="Invalid signature")
    # 先回 200 給 LINE，抓網頁與 AI 分析放到背景做
    for event in events:
        background.add_task(handle_event, event)
    return "OK"


# ── 送訊息 ──────────────────────────────────────────────

async def send(event, messages: list) -> None:
    async with AsyncApiClient(line_config) as client:
        api = AsyncMessagingApi(client)
        try:
            await api.reply_message(ReplyMessageRequest(reply_token=event.reply_token, messages=messages))
        except Exception:
            log.warning("reply 失敗（token 可能過期）", exc_info=True)
            user_id = getattr(event.source, "user_id", None)
            if settings.LINE_PUSH_FALLBACK and user_id:
                await api.push_message(PushMessageRequest(to=user_id, messages=messages))


async def push(to: str, messages: list) -> None:
    async with AsyncApiClient(line_config) as client:
        await AsyncMessagingApi(client).push_message(PushMessageRequest(to=to, messages=messages))


async def fetch_display_name(user_id: str) -> str | None:
    try:
        async with AsyncApiClient(line_config) as client:
            return (await AsyncMessagingApi(client).get_profile(user_id)).display_name
    except Exception:
        log.debug("取得名稱失敗", exc_info=True)
        return None


async def notify_admins(user) -> None:
    """有新使用者申請時通知管理者（push，會用到每月訊息額度）。"""
    name = user.display_name or "（未知名稱）"
    for admin in settings.ADMIN_LINE_USER_IDS:
        try:
            await push(admin, [ui.text(
                f"🔔 新的使用申請\n\n名稱：{name}\n編號：#{user.id}",
                ui.quick_reply([(f"核准 #{user.id}", f"核准 #{user.id}"), (f"拒絕 #{user.id}", f"拒絕 #{user.id}")]))])
        except Exception:
            log.warning("通知管理者失敗", exc_info=True)


async def gate(event, user_id: str) -> bool:
    """回傳 True 表示可以繼續處理。待審核／被拒絕的人只會收到提示，不會用到 AI。"""
    with SessionLocal() as db:
        user, created = service.ensure_line_user(db, user_id)
        if created and not user.display_name:
            name = await fetch_display_name(user_id)
            if name:
                user = service.get_or_create_line_user(db, user_id, name)
        if created and user.status == "pending":
            await notify_admins(user)
        status = user.status
    if status == "approved":
        return True
    await send(event, [ui.text(PENDING_MSG if status == "pending" else BLOCKED_MSG)])
    return False


async def show_loading(user_id: str) -> None:
    try:
        async with AsyncApiClient(line_config) as client:
            await AsyncMessagingApi(client).show_loading_animation(
                ShowLoadingAnimationRequest(chat_id=user_id, loading_seconds=30))
    except Exception:
        log.debug("loading 動畫失敗", exc_info=True)


async def download_content(message_id: str) -> bytes:
    async with AsyncApiClient(line_config) as client:
        return bytes(await AsyncMessagingApiBlob(client).get_message_content(message_id))


def _media_type(data: bytes) -> str:
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data[:3] == b"GIF":
        return "image/gif"
    return "image/jpeg"


# ── 事件處理 ────────────────────────────────────────────

async def handle_event(event) -> None:
    try:
        if not isinstance(event, (FollowEvent, MessageEvent)):
            return
        user_id = getattr(event.source, "user_id", None)
        if not user_id or not await gate(event, user_id):
            return
        if isinstance(event, FollowEvent):
            await send(event, [ui.text(HELP, ui.quick_reply(DEFAULT_QR))])
            return
        if isinstance(event.message, TextMessageContent):
            await handle_text(event, user_id, event.message.text.strip())
        elif isinstance(event.message, ImageMessageContent):
            await handle_image(event, user_id)
    except Exception:
        log.exception("處理 LINE 事件失敗")
        try:
            await send(event, [ui.text("糟糕，處理時出了點問題，請稍後再試一次 🙏")])
        except Exception:
            pass


async def handle_text(event, user_id: str, text: str) -> None:
    urls = extract_urls(text)
    if urls:
        await handle_urls(event, user_id, text, urls)
        return

    if service.is_admin(user_id) and await handle_admin(event, text):
        return

    with SessionLocal() as db:
        user = service.get_or_create_line_user(db, user_id)

        if text in ("說明", "help", "?", "？"):
            msgs = [ui.text(HELP, ui.quick_reply(DEFAULT_QR, settings.LIFF_URL))]

        elif text in ("最近", "最新"):
            items, _ = service.list_items(db, user, limit=5)
            msgs = ([ui.items_message([(i, "") for i in items], "最近收藏")] if items
                    else [ui.text("還沒有收藏，分享一個連結給我試試看！")])

        elif text in ("分類", "清單"):
            counts = service.category_counts(db, user)
            if not counts:
                msgs = [ui.text("還沒有收藏，分享一個連結給我試試看！")]
            else:
                rows = [(c, counts[c.key]) for c in CATEGORIES if counts.get(c.key)]
                msgs = [ui.categories_message(rows, sum(counts.values()))]

        elif text.startswith("看"):
            cat = find_category(text[1:])
            if not cat:
                msgs = [ui.text("找不到這個分類，可以輸入「分類」看看有哪些。")]
            else:
                items, _ = service.list_items(db, user, category=cat.key, limit=10)
                msgs = ([ui.items_message([(i, "") for i in items], f"{cat.label}收藏")] if items
                        else [ui.text(f"{cat.label}還沒有收藏。")])

        elif text.startswith(("搜尋", "找")):
            q = text.removeprefix("搜尋").removeprefix("找").strip()
            if not q:
                msgs = [ui.text("要搜尋什麼呢？例如「搜尋 拉麵」")]
            else:
                items, _ = service.list_items(db, user, q=q, limit=5)
                msgs = ([ui.items_message([(i, "") for i in items], f"搜尋：{q}")] if items
                        else [ui.text(f"找不到和「{q}」有關的收藏。")])

        elif text.startswith("改"):
            cat = find_category(text[1:])
            item = service.latest_item(db, user)
            if not item:
                msgs = [ui.text("還沒有收藏可以修改。")]
            elif not cat:
                names = "、".join(c.label for c in CATEGORIES)
                msgs = [ui.text(f"要改成哪個分類？可以用：{names}")]
            else:
                service.update_item(db, item, category=cat.key)
                msgs = [ui.text(f"已把「{item.title}」改到 {cat.emoji} {cat.label}")]

        elif text.startswith("確定刪除"):
            item = _target_item(db, user, text)
            if not item:
                msgs = [ui.text("找不到這筆收藏，可能已經刪除了。")]
            else:
                title = item.title or "這筆收藏"
                service.delete_item(db, item)
                msgs = [ui.text(f"🗑 已刪除「{title}」", ui.quick_reply(DEFAULT_QR))]

        elif text.startswith("刪除"):
            item = _target_item(db, user, text)
            if not item:
                msgs = [ui.text("找不到這筆收藏，可能已經刪除了。")]
            else:
                msgs = [ui.text(f"確定要刪除「{item.title or '這筆收藏'}」嗎？",
                                ui.quick_reply([("確定刪除", f"確定刪除 #{item.id}"), ("取消", "取消")]))]

        elif text == "取消":
            msgs = [ui.text("好的，沒有刪除。")]

        elif text == "綁定":
            msgs = [ui.text(
                "這是你的個人金鑰，網頁或 App 登入時使用。請不要傳給別人。\n\n" + user.api_token)]

        else:
            msgs = [ui.text("把連結或截圖分享給我就會自動收藏喔！輸入「說明」看所有指令。",
                            ui.quick_reply(DEFAULT_QR))]

    await send(event, msgs)


async def handle_admin(event, text: str) -> bool:
    """管理者指令。回傳 True 表示已處理。"""
    m = re.match(r"^(核准|拒絕)\s*#?(\d+)$", text)
    if text in ("待審核", "成員"):
        with SessionLocal() as db:
            users = service.list_users(db, "pending" if text == "待審核" else None)
        if not users:
            await send(event, [ui.text("目前沒有待審核的人 👍" if text == "待審核" else "還沒有使用者。")])
            return True
        lines = [f"#{u.id} {u.display_name or '（未知名稱）'}　{STATUS_LABEL.get(u.status, u.status)}"
                 for u in users[:50]]
        qr = []
        for u in users:
            if u.status == "pending":
                qr += [(f"核准 #{u.id}", f"核准 #{u.id}"), (f"拒絕 #{u.id}", f"拒絕 #{u.id}")]
        await send(event, [ui.text(("⏳ 待審核\n\n" if text == "待審核" else "👥 成員\n\n") + "\n".join(lines),
                                   ui.quick_reply(qr[:12]) if qr else None)])
        return True
    if m:
        action, uid = m.group(1), int(m.group(2))
        with SessionLocal() as db:
            target = service.get_user(db, uid)
            if not target:
                await send(event, [ui.text(f"找不到 #{uid}")])
                return True
            if service.is_admin(target.line_user_id):
                await send(event, [ui.text("管理者帳號不能被拒絕。")])
                return True
            service.set_user_status(db, target, "approved" if action == "核准" else "blocked")
            name, line_id = target.display_name or f"#{uid}", target.line_user_id
        await send(event, [ui.text(f"{'✅ 已核准' if action == '核准' else '⛔ 已拒絕'}：{name}")])
        if action == "核准" and line_id:
            try:
                await push(line_id, [ui.text("🎉 你已通過審核，可以開始使用了！\n\n" + HELP,
                                             ui.quick_reply(DEFAULT_QR))])
            except Exception:
                log.warning("通知使用者失敗", exc_info=True)
        return True
    if text in ("管理", "管理說明"):
        await send(event, [ui.text(ADMIN_HELP)])
        return True
    return False


def _target_item(db, user, text: str):
    """「刪除 #12」指定某一筆；只打「刪除」就是最新一筆。只會找到自己的收藏。"""
    m = re.search(r"#(\d+)", text)
    return service.get_item(db, user, int(m.group(1))) if m else service.latest_item(db, user)


async def handle_urls(event, user_id: str, text: str, urls: list[str]) -> None:
    await show_loading(user_id)
    note = text
    for u in urls:
        note = note.replace(u, "")
    note = note.strip() or None

    results = []
    with SessionLocal() as db:
        user = service.get_or_create_line_user(db, user_id)
        for u in urls[:MAX_URLS_PER_MESSAGE]:
            item, created = await service.ingest_url(db, user, u, note)
            results.append((item, "new" if created else "dup"))

    msgs = [ui.items_message(results, f"已收藏：{results[0][0].title or '新連結'}")]
    if any(i.status in ("partial", "failed") for i, s in results if s == "new"):
        msgs.append(ui.text("這個平台沒讓我讀到完整內容。10 分鐘內補傳一張貼文截圖，我會自動補齊這一筆 📸"))
    if len(urls) > MAX_URLS_PER_MESSAGE:
        msgs.append(ui.text(f"一次最多處理 {MAX_URLS_PER_MESSAGE} 個連結，其餘請分開傳。"))
    await send(event, msgs[:5])


async def handle_image(event, user_id: str) -> None:
    await show_loading(user_id)
    data = await download_content(event.message.id)
    with SessionLocal() as db:
        user = service.get_or_create_line_user(db, user_id)
        try:
            item, merged = await service.ingest_image(db, user, data, _media_type(data))
        except ValueError as e:
            await send(event, [ui.text(f"這張圖沒辦法處理：{e}")])
            return
    await send(event, [ui.items_message([(item, "merged" if merged else "new")],
                                        f"已收藏：{item.title or '截圖'}")])
