"""辨識平台、展開短網址、抓取內容。這一層完全不知道 LINE 或 App 的存在。"""
import re
from dataclasses import dataclass
from urllib.parse import parse_qsl, unquote_plus, urlencode, urlparse, urlunparse

import httpx
from bs4 import BeautifulSoup

MAX_TEXT = 8000

PLATFORMS: dict[str, tuple[str, ...]] = {
    "facebook": ("facebook.com", "fb.com", "fb.watch", "fb.me"),
    "instagram": ("instagram.com", "instagr.am"),
    "threads": ("threads.net", "threads.com"),
    "x": ("x.com", "twitter.com", "t.co"),
    "youtube": ("youtube.com", "youtu.be"),
    "tiktok": ("tiktok.com",),
    "googlemaps": ("maps.app.goo.gl", "maps.google.com"),
    "dcard": ("dcard.tw",),
    "ptt": ("ptt.cc",),
}
PLATFORM_LABELS = {
    "facebook": "Facebook", "instagram": "Instagram", "threads": "Threads", "x": "X",
    "youtube": "YouTube", "tiktok": "TikTok", "googlemaps": "Google 地圖", "dcard": "Dcard",
    "ptt": "PTT", "web": "網頁", "screenshot": "截圖",
}
META_PLATFORMS = {"facebook", "instagram", "threads"}
SHORTLINK_HOSTS = {
    "t.co", "fb.me", "fb.watch", "bit.ly", "reurl.cc", "lihi.cc", "lihi1.cc", "pse.is",
    "goo.gl", "maps.app.goo.gl", "tinyurl.com", "youtu.be", "vt.tiktok.com",
}
DROP_PARAMS = {"fbclid", "igsh", "igshid", "mibextid", "si", "ref", "ref_src", "ref_url", "rdid", "share_url", "gclid"}
X_DROP_PARAMS = {"s", "t"}
GENERIC_DESC = ("log in", "登入", "sign up", "create an account", "see instagram photos and videos")

URL_RE = re.compile(r"https?://[^\s<>\"'（）【】「」]+", re.IGNORECASE)
X_STATUS_RE = re.compile(r"/([^/]+)/status(?:es)?/(\d+)")

BROWSER_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1"
)
# Meta 系平台對「連結預覽爬蟲」比較願意回 og:description（貼文文字）
PREVIEW_UA = "facebookexternalhit/1.1 (+http://www.facebook.com/externalhit_uatext.php)"


@dataclass
class FetchResult:
    url: str
    final_url: str
    platform: str
    title: str | None = None
    description: str | None = None
    text: str | None = None
    author: str | None = None
    image_url: str | None = None
    ok: bool = False
    note: str | None = None

    def combined_text(self) -> str:
        return "\n".join(p for p in (self.title, self.description, self.text) if p)

    def to_prompt(self) -> str:
        parts = [f"網址：{self.final_url}", f"平台：{PLATFORM_LABELS.get(self.platform, self.platform)}"]
        if self.author:
            parts.append(f"作者：{self.author}")
        if self.title:
            parts.append(f"標題：{self.title}")
        if self.description:
            parts.append(f"描述：{self.description}")
        if self.text:
            parts.append(f"內文：\n{self.text}")
        if not self.ok:
            parts.append(f"（注意：只取得部分內容，{self.note or '可能被登入牆擋住'}）")
        return "\n".join(parts)


# ── 工具函式 ────────────────────────────────────────────

def extract_urls(text: str) -> list[str]:
    urls: list[str] = []
    for m in URL_RE.findall(text or ""):
        u = m.rstrip(".,;:!?。，、！？…")
        if u not in urls:
            urls.append(u)
    return urls


def _host(url: str) -> str:
    return (urlparse(url).hostname or "").lower()


def detect_platform(url: str) -> str:
    h = _host(url)
    if h.startswith(("www.google.", "google.")) and urlparse(url).path.startswith("/maps"):
        return "googlemaps"
    for name, domains in PLATFORMS.items():
        if any(h == d or h.endswith("." + d) for d in domains):
            return name
    return "web"


def canonicalize(url: str) -> str:
    """去掉追蹤參數、統一主機名稱，用來判斷「同一個連結是否收藏過」。"""
    p = urlparse(url.strip())
    platform = detect_platform(url)
    host = _host(url)
    for prefix in ("www.", "m.", "mobile."):
        if host.startswith(prefix):
            host = host[len(prefix):]
            break
    if host == "twitter.com":
        host = "x.com"
    if host == "threads.com":
        host = "threads.net"
    query = [
        (k, v) for k, v in parse_qsl(p.query, keep_blank_values=True)
        if not (k.lower().startswith("utm_") or k.lower() in DROP_PARAMS
                or (platform == "x" and k.lower() in X_DROP_PARAMS))
    ]
    path = p.path.rstrip("/") or "/"
    return urlunparse(((p.scheme or "https").lower(), host, path, "", urlencode(query), ""))


def _maps_place_name(url: str) -> str | None:
    m = re.search(r"/maps/place/([^/@]+)", urlparse(url).path)
    return unquote_plus(m.group(1)) if m else None


def _has_content(r: FetchResult) -> bool:
    path = urlparse(r.final_url).path.lower()
    if "login" in path or "/accounts/" in path:
        return False
    desc = (r.description or "").strip()
    text = (r.text or "").strip()
    desc_ok = len(desc) >= 20 and not any(g in desc.lower() for g in GENERIC_DESC)
    if r.platform in META_PLATFORMS:
        return desc_ok
    if r.platform == "googlemaps":
        return bool(r.title)
    return desc_ok or len(text) >= 80


# ── 各平台抓取 ──────────────────────────────────────────

async def _fill_from_x(client: httpx.AsyncClient, r: FetchResult) -> bool:
    """X 用公開代理服務取得貼文文字（不需登入）。第三方服務可能變動，所以有兩個備援。"""
    m = X_STATUS_RE.search(urlparse(r.final_url).path)
    if not m:
        return False
    user, tid = m.groups()

    try:
        resp = await client.get(f"https://api.fxtwitter.com/{user}/status/{tid}")
        if resp.status_code == 200:
            t = resp.json().get("tweet") or {}
            text = t.get("text") or ""
            quote = t.get("quote") or {}
            if quote.get("text"):
                qa = (quote.get("author") or {}).get("screen_name", "")
                text += f"\n\n［引用 @{qa}］{quote['text']}"
            if text:
                a = t.get("author") or {}
                r.author = f"{a.get('name', '')} (@{a.get('screen_name', user)})"
                r.text = text[:MAX_TEXT]
                photos = (t.get("media") or {}).get("photos") or []
                r.image_url = photos[0].get("url") if photos else None
                r.ok = True
                return True
    except (httpx.HTTPError, ValueError):
        pass

    try:
        resp = await client.get(f"https://api.vxtwitter.com/{user}/status/{tid}")
        if resp.status_code == 200:
            j = resp.json()
            if j.get("text"):
                r.author = f"{j.get('user_name', '')} (@{j.get('user_screen_name', user)})"
                r.text = j["text"][:MAX_TEXT]
                media = j.get("mediaURLs") or []
                r.image_url = media[0] if media else None
                r.ok = True
                return True
    except (httpx.HTTPError, ValueError):
        pass
    return False


def _fill_from_html(html: str, r: FetchResult) -> None:
    soup = BeautifulSoup(html, "html.parser")

    def meta(*keys: str) -> str | None:
        for k in keys:
            tag = soup.find("meta", attrs={"property": k}) or soup.find("meta", attrs={"name": k})
            if tag and tag.get("content"):
                return tag["content"].strip()
        return None

    r.title = meta("og:title", "twitter:title") or (soup.title.get_text(strip=True) if soup.title else None)
    r.description = meta("og:description", "twitter:description", "description")
    r.image_url = meta("og:image", "twitter:image")
    r.author = r.author or meta("author", "article:author")

    if r.platform in META_PLATFORMS:
        return  # Meta 系頁面內文多半是登入提示，只用 meta 資訊

    for tag in soup(["script", "style", "noscript", "header", "footer", "nav", "aside", "form", "svg"]):
        tag.decompose()
    main = soup.find("article") or soup.find("main") or soup.body
    if main:
        text = re.sub(r"\n{2,}", "\n", main.get_text("\n", strip=True))
        r.text = text[:MAX_TEXT] or None


async def fetch(url: str) -> FetchResult:
    r = FetchResult(url=url, final_url=url, platform=detect_platform(url))
    headers = {"User-Agent": BROWSER_UA, "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8"}
    async with httpx.AsyncClient(follow_redirects=True, timeout=15.0, headers=headers) as client:
        try:
            if _host(url) in SHORTLINK_HOSTS:
                resp = await client.get(url)
                r.final_url = str(resp.url)
                r.platform = detect_platform(r.final_url)

            if r.platform == "x" and await _fill_from_x(client, r):
                return r

            ua = PREVIEW_UA if r.platform in META_PLATFORMS else BROWSER_UA
            resp = await client.get(r.final_url, headers={"User-Agent": ua})
            r.final_url = str(resp.url)
            ctype = resp.headers.get("content-type", "")
            if "html" in ctype:
                _fill_from_html(resp.text, r)
            else:
                r.note = f"不是網頁內容（{ctype or '未知格式'}）"
        except httpx.HTTPError as e:
            r.note = f"抓取失敗（{type(e).__name__}）"

    if r.platform == "googlemaps":
        r.title = _maps_place_name(r.final_url) or r.title
    r.ok = _has_content(r)
    return r
