"""呼叫 Claude：一次完成分類、標題、摘要、標籤與結構化欄位。"""
import base64
import json
import re
from dataclasses import dataclass, field

import anthropic

from app.config import settings
from app.core.categories import CATEGORIES, CATEGORY_MAP, DEFAULT_CATEGORY
from app.core.fetcher import FetchResult

MAX_IMAGE_BYTES = 5 * 1024 * 1024

_PROMPT = """你是「連結收藏整理助理」。使用者把社群貼文或網頁分享進來，你要判斷分類並用繁體中文整理。

可用分類（category 只能填冒號左邊的代號）：
<<CATEGORIES>>

只輸出一個 JSON 物件，不要任何其他文字、註解或 Markdown。欄位：
- category：分類代號
- title：15 字內的標題，直接點出重點（例如「店名＋招牌菜」「工具名＋用途」）
- summary：2～3 句繁體中文摘要
- key_points：重點陣列，最多 5 點，沒有就給 []
- tags：2～5 個標籤，不含 #
- details：依分類補充的物件，只放內容裡確實有的欄位
    food：name、area、address、price、dishes（陣列）、hours
    travel：location、spots（陣列）、best_season、budget
    ai_coding：tools（陣列）、language、repo_url
    shopping：product、price、deadline、store
    其他分類可放 links、people 等
- content_sufficient：內容太少、只看到登入頁或只有標題時填 false

規則：
- 只根據提供的內容整理，不要編造店名、地址、價格或日期。
- 內容不足時，依網址和片段推測分類，summary 說明只取得部分內容。
- 原文是外文也用繁體中文摘要，專有名詞可保留原文。"""

SYSTEM_PROMPT = _PROMPT.replace(
    "<<CATEGORIES>>", "\n".join(f"{c.key}：{c.label}" for c in CATEGORIES)
)


@dataclass
class Analysis:
    category: str = DEFAULT_CATEGORY
    title: str = "未命名收藏"
    summary: str = ""
    key_points: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    details: dict = field(default_factory=dict)
    content_sufficient: bool = True
    extracted_text: str = ""


_client: anthropic.AsyncAnthropic | None = None


def _get_client() -> anthropic.AsyncAnthropic:
    global _client
    if _client is None:
        _client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
    return _client


async def analyze_fetch(fr: FetchResult, note: str | None = None) -> Analysis:
    prompt = "請整理以下分享內容。\n\n" + fr.to_prompt()
    if note:
        prompt += f"\n\n使用者分享時附上的文字：{note}"
    return await _call([{"type": "text", "text": prompt}])


async def analyze_image(
    data: bytes,
    media_type: str,
    note: str | None = None,
    prior_url: str | None = None,
    prior_text: str | None = None,
) -> Analysis:
    if len(data) > MAX_IMAGE_BYTES:
        raise ValueError("圖片超過 5MB")
    text = (
        "這是使用者分享的社群貼文或網頁截圖，請讀出畫面內容後整理。"
        "另外在 JSON 多加 extracted_text 欄位：截圖中主要文字的原文（最多 800 字）。"
    )
    if prior_url:
        text += f"\n\n這張截圖對應的原始連結：{prior_url}"
    if prior_text:
        text += f"\n先前從連結抓到的片段：\n{prior_text[:2000]}"
    if note:
        text += f"\n\n使用者附上的文字：{note}"
    blocks = [
        {"type": "image", "source": {"type": "base64", "media_type": media_type,
                                     "data": base64.standard_b64encode(data).decode()}},
        {"type": "text", "text": text},
    ]
    return await _call(blocks, max_tokens=2048)


async def _call(blocks: list[dict], max_tokens: int = 1024) -> Analysis:
    msg = await _get_client().messages.create(
        model=settings.CLAUDE_MODEL,
        max_tokens=max_tokens,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": blocks}],
    )
    raw = "".join(getattr(b, "text", "") for b in msg.content)
    return parse_analysis(raw)


def _extract_json(raw: str) -> dict | None:
    s = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip())
    start, end = s.find("{"), s.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        v = json.loads(s[start:end + 1])
    except json.JSONDecodeError:
        return None
    return v if isinstance(v, dict) else None


def _strs(v, limit: int) -> list[str]:
    if not isinstance(v, list):
        return []
    return [str(x).strip().lstrip("#") for x in v if str(x).strip()][:limit]


def parse_analysis(raw: str) -> Analysis:
    data = _extract_json(raw)
    if data is None:
        return Analysis(summary=raw.strip()[:300], content_sufficient=False)

    cat = str(data.get("category", "")).strip()
    if cat not in CATEGORY_MAP:
        cat = DEFAULT_CATEGORY
    sufficient = data.get("content_sufficient", True)
    if isinstance(sufficient, str):
        sufficient = sufficient.strip().lower() not in ("false", "0", "no")

    return Analysis(
        category=cat,
        title=str(data.get("title") or "未命名收藏").strip()[:100],
        summary=str(data.get("summary") or "").strip(),
        key_points=_strs(data.get("key_points"), 5),
        tags=_strs(data.get("tags"), 6),
        details=data["details"] if isinstance(data.get("details"), dict) else {},
        content_sufficient=bool(sufficient),
        extracted_text=str(data.get("extracted_text") or "")[:3000],
    )
