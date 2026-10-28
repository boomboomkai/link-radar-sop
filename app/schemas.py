"""API 的資料格式。這就是之後 App 和 LIFF 網頁要對接的「合約」。"""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, computed_field

from app.core.categories import CATEGORY_MAP


class ItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source_type: str
    url: str | None
    platform: str
    category: str
    title: str | None
    summary: str | None
    key_points: list[str] = []
    tags: list[str] = []
    details: dict = {}
    author: str | None
    image_url: str | None
    user_note: str | None
    status: str
    created_at: datetime
    updated_at: datetime

    @computed_field
    @property
    def category_label(self) -> str:
        c = CATEGORY_MAP.get(self.category)
        return c.label if c else self.category


class ItemList(BaseModel):
    items: list[ItemOut]
    next_cursor: int | None = Field(None, description="下一頁請帶 before_id=next_cursor")


class ItemCreate(BaseModel):
    url: str = Field(..., min_length=8, max_length=2000)
    note: str | None = Field(None, max_length=2000)


class ItemCreated(BaseModel):
    item: ItemOut
    created: bool


class ItemUpdate(BaseModel):
    category: str | None = None
    title: str | None = Field(None, max_length=300)
    tags: list[str] | None = None
    user_note: str | None = None


class CategoryOut(BaseModel):
    key: str
    label: str
    emoji: str
    count: int


class LineLoginIn(BaseModel):
    id_token: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: int
    display_name: str | None = None
