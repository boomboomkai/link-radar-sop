import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import models  # noqa: F401  註冊資料表
from app.api.v1 import router as api_router
from app.channels.line_webhook import router as line_router
from app.config import settings
from app.db import Base, engine, migrate

logging.basicConfig(level=settings.LOG_LEVEL)


@asynccontextmanager
async def lifespan(_: FastAPI):
    # 第一版直接建表；資料表穩定後改用 Alembic 管理版本（見 docs/ARCHITECTURE.md）
    Base.metadata.create_all(bind=engine)
    migrate()
    yield


app = FastAPI(title="連結雷達 Link Radar API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(line_router)   # LINE webhook：/line/webhook
app.include_router(api_router)    # REST API：/api/v1/...


@app.get("/health")
def health():
    return {"status": "ok"}
