"""不需網路、不需 API key 的基本測試：pip install pytest 後執行 pytest"""
from app.core.analyzer import parse_analysis
from app.core.categories import find_category
from app.core.fetcher import canonicalize, detect_platform, extract_urls


def test_extract_urls_from_share_text():
    text = "這家好好吃！https://www.instagram.com/p/ABC123/?igsh=xyz 推推"
    assert extract_urls(text) == ["https://www.instagram.com/p/ABC123/?igsh=xyz"]


def test_detect_platform():
    assert detect_platform("https://www.threads.com/@a/post/1") == "threads"
    assert detect_platform("https://m.facebook.com/story.php?id=1") == "facebook"
    assert detect_platform("https://twitter.com/a/status/1") == "x"
    assert detect_platform("https://maps.app.goo.gl/abc") == "googlemaps"
    assert detect_platform("https://example.com") == "web"


def test_canonicalize_removes_tracking():
    a = canonicalize("https://www.instagram.com/p/ABC123/?igsh=xyz&utm_source=line")
    b = canonicalize("https://instagram.com/p/ABC123")
    assert a == b
    assert canonicalize("https://twitter.com/a/status/1?s=20&t=abc") == canonicalize("https://x.com/a/status/1")


def test_parse_analysis_handles_fences_and_bad_category():
    raw = '```json\n{"category":"unknown","title":"拉麵","summary":"好吃","tags":["#拉麵"],"content_sufficient":"false"}\n```'
    a = parse_analysis(raw)
    assert a.category == "other" and a.title == "拉麵" and a.tags == ["拉麵"] and a.content_sufficient is False


def test_find_category():
    assert find_category("餐廳").key == "food"
    assert find_category(" AI ").key == "ai_coding"
    assert find_category("火星") is None
