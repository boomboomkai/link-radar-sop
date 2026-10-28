"""LINE 訊息外觀（Flex 卡片、快速回覆）。只負責「長什麼樣子」。"""
import json

from linebot.v3.messaging import (
    FlexContainer, FlexMessage, MessageAction, QuickReply, QuickReplyItem, TextMessage, URIAction,
)

from app.core.categories import CATEGORY_MAP
from app.models import Item

STATUS_LABEL = {"new": "✅ 已收藏", "dup": "📎 之前收藏過", "merged": "🔗 已用截圖補齊",
                "partial": "⚠️ 只取得部分內容", "failed": "⚠️ AI 分析失敗"}


def _t(s: str | None, fallback: str = "－", limit: int = 2000) -> str:
    s = (s or "").strip()
    return (s[:limit] + "…") if len(s) > limit else (s or fallback)


def _valid_url(url: str | None) -> bool:
    return bool(url) and url.startswith(("http://", "https://")) and len(url) <= 1000


def item_bubble(item: Item, state: str = "new") -> dict:
    cat = CATEGORY_MAP.get(item.category) or CATEGORY_MAP["other"]
    if item.status in ("partial", "failed") and state == "new":
        state = item.status
    header = [{"type": "text", "text": f"{cat.emoji} {cat.label}", "size": "xs", "color": "#888888", "flex": 1}]
    if STATUS_LABEL.get(state):  # Flex 不允許空字串，列表模式就不顯示狀態
        header.append({"type": "text", "text": STATUS_LABEL[state], "size": "xs", "color": "#888888",
                       "align": "end", "flex": 1})
    contents = [
        {"type": "box", "layout": "horizontal", "contents": header},
        {"type": "text", "text": _t(item.title, "未命名收藏", 80), "weight": "bold", "size": "md",
         "wrap": True, "margin": "sm"},
        {"type": "text", "text": _t(item.summary, "（沒有摘要）", 300), "size": "sm", "wrap": True,
         "margin": "md", "color": "#333333"},
    ]
    if item.tags:
        contents.append({"type": "text", "text": " ".join(f"#{t}" for t in item.tags[:5]), "size": "xs",
                         "color": "#1E88E5", "wrap": True, "margin": "md"})
    bubble: dict = {"type": "bubble", "size": "kilo",
                    "body": {"type": "box", "layout": "vertical", "contents": contents}}
    buttons = []
    if _valid_url(item.url):
        buttons.append({"type": "button", "style": "link", "height": "sm", "flex": 2,
                        "action": {"type": "uri", "label": "開啟原文", "uri": item.url}})
    buttons.append({"type": "button", "style": "link", "height": "sm", "flex": 1, "color": "#999999",
                    "action": {"type": "message", "label": "刪除", "text": f"刪除 #{item.id}"}})
    bubble["footer"] = {"type": "box", "layout": "horizontal", "contents": buttons}
    return bubble


def list_bubble(items: list[Item], header: str) -> dict:
    """條列式：多筆收藏排在同一張卡片，一行一筆，點一下開啟原文。"""
    rows: list[dict] = []
    for idx, item in enumerate(items):
        if idx:
            rows.append({"type": "separator", "margin": "md"})
        cat = CATEGORY_MAP.get(item.category) or CATEGORY_MAP["other"]
        info: dict = {"type": "box", "layout": "vertical", "spacing": "xs", "flex": 1, "contents": [
            {"type": "text", "text": _t(item.title, "未命名收藏", 40), "weight": "bold", "size": "sm",
             "wrap": True, "maxLines": 2},
            {"type": "text", "text": f"{cat.emoji} " + _t(item.summary, "（沒有摘要）", 60), "size": "xs",
             "color": "#888888", "wrap": True, "maxLines": 2},
        ]}
        if _valid_url(item.url):
            info["action"] = {"type": "uri", "label": "開啟原文", "uri": item.url}
        delete = {"type": "text", "text": "🗑", "size": "lg", "flex": 0, "gravity": "center",
                  "margin": "md", "action": {"type": "message", "label": "刪除", "text": f"刪除 #{item.id}"}}
        rows.append({"type": "box", "layout": "horizontal", "margin": "md", "contents": [info, delete]})
    return {
        "type": "bubble", "size": "mega",
        "header": {"type": "box", "layout": "vertical", "paddingBottom": "none", "contents": [
            {"type": "text", "text": f"{_t(header, '收藏', 30)}（{len(items)} 筆）", "weight": "bold",
             "size": "md", "wrap": True},
            {"type": "text", "text": "點標題開啟原文，點 🗑 刪除", "size": "xxs", "color": "#999999", "margin": "xs"},
        ]},
        "body": {"type": "box", "layout": "vertical", "contents": rows},
    }


def categories_message(counts: list[tuple], total: int) -> FlexMessage:
    """分類總覽：一行一個分類，整行都能點，點了就看該分類。counts = [(Category, 數量), ...]"""
    rows: list[dict] = []
    for idx, (cat, n) in enumerate(counts):
        if idx:
            rows.append({"type": "separator", "margin": "md"})
        rows.append({
            "type": "box", "layout": "horizontal", "margin": "md", "paddingTop": "md", "paddingBottom": "md",
            "action": {"type": "message", "label": cat.label[:20], "text": f"看 {cat.label}"},
            "contents": [
                {"type": "text", "text": cat.emoji, "size": "xl", "flex": 0, "gravity": "center"},
                {"type": "text", "text": cat.label, "size": "md", "weight": "bold", "flex": 1,
                 "gravity": "center", "margin": "lg"},
                {"type": "text", "text": f"{n} 筆", "size": "sm", "color": "#888888", "flex": 0,
                 "gravity": "center"},
                {"type": "text", "text": "›", "size": "xl", "color": "#BBBBBB", "flex": 0,
                 "gravity": "center", "margin": "md"},
            ],
        })
    bubble = {
        "type": "bubble", "size": "mega",
        "header": {"type": "box", "layout": "vertical", "paddingBottom": "none", "contents": [
            {"type": "text", "text": f"📂 你的收藏（共 {total} 筆）", "weight": "bold", "size": "md"},
            {"type": "text", "text": "點分類查看收藏", "size": "xxs", "color": "#999999", "margin": "xs"},
        ]},
        "body": {"type": "box", "layout": "vertical", "contents": rows},
    }
    return FlexMessage(alt_text=f"你的收藏（共 {total} 筆）",
                       contents=FlexContainer.from_json(json.dumps(bubble)))


def items_message(items: list[tuple[Item, str]], alt: str) -> FlexMessage:
    items = items[:12]
    if len(items) > 1 and all(not state for _, state in items):
        # 最近／看分類／搜尋：條列式
        container = list_bubble([i for i, _ in items], alt)
    else:
        # 剛收藏：完整大卡片
        bubbles = [item_bubble(i, s) for i, s in items]
        container = bubbles[0] if len(bubbles) == 1 else {"type": "carousel", "contents": bubbles}
    return FlexMessage(alt_text=alt[:400], contents=FlexContainer.from_json(json.dumps(container)))


def quick_reply(labels: list[tuple[str, str]], liff_url: str = "") -> QuickReply:
    items = [QuickReplyItem(action=MessageAction(label=lab[:20], text=txt)) for lab, txt in labels]
    if liff_url:
        items.insert(0, QuickReplyItem(action=URIAction(label="打開收藏夾", uri=liff_url)))
    return QuickReply(items=items[:13])


def text(msg: str, qr: QuickReply | None = None) -> TextMessage:
    return TextMessage(text=msg[:5000], quick_reply=qr)
