from dataclasses import dataclass


@dataclass(frozen=True)
class Category:
    key: str    # 存進資料庫、給 App 用的穩定代號（之後做多語系也不用改資料）
    label: str
    emoji: str


CATEGORIES: list[Category] = [
    Category("food", "餐廳美食", "🍜"),
    Category("travel", "旅遊景點", "✈️"),
    Category("ai_coding", "AI／程式開發", "🤖"),
    Category("tech", "科技3C", "📱"),
    Category("shopping", "購物優惠", "🛒"),
    Category("finance", "理財投資", "💰"),
    Category("health", "健康運動", "💪"),
    Category("learning", "學習知識", "📚"),
    Category("entertainment", "娛樂影視", "🎬"),
    Category("news", "新聞時事", "📰"),
    Category("lifestyle", "生活居家", "🏠"),
    Category("other", "其他", "📌"),
]
CATEGORY_MAP = {c.key: c for c in CATEGORIES}
DEFAULT_CATEGORY = "other"


def find_category(text: str) -> Category | None:
    """讓使用者打「餐廳」「AI」「travel」都能對到分類。"""
    s = text.strip().lower()
    if not s:
        return None
    for c in CATEGORIES:
        if s in (c.key, c.label.lower()):
            return c
    for c in CATEGORIES:
        if s in c.label.lower() or s in c.key:
            return c
    return None
