# 架構說明與 App 化規劃

## 1. 設計原則：入口和核心分開

```
   LINE 機器人        LIFF 網頁（下一步）      iPhone／Android App（之後）
        │                   │                          │
  channels/line_webhook     └──────── REST API /api/v1 ┘
        │                                │
        └──────────────┬─────────────────┘
                       ▼
               core/service.py   收藏、合併截圖、查詢、修改
               ├─ fetcher.py     平台辨識、抓內容
               └─ analyzer.py    Claude 分類＋摘要
                       ▼
                 資料庫（SQLite → Postgres）
```

- `core/` 完全不 import LINE 的東西。LINE bot 和 REST API 呼叫的是**同一組** service 函式，所以 App 上線時，分類、摘要、去重、截圖合併的行為和 LINE 一模一樣。
- 新增入口（App、Telegram、瀏覽器擴充功能）＝ 新增一個轉接層，核心不動。
- 分類用英文代號（`food`、`ai_coding`）存進資料庫，中文名稱只在顯示時對照，之後做多語系或改名都不用動資料。

## 2. 使用者身分：一個帳號走到底

| 入口 | 怎麼識別 |
|---|---|
| LINE bot | webhook 帶的 `userId` |
| LIFF 網頁 | `liff.getIDToken()` → `POST /api/v1/auth/line` 換 access token |
| App | LINE Login SDK 取得 ID token → 同一個 `POST /api/v1/auth/line` |

三種入口最後都對到 `users.line_user_id`，所以在 LINE 存的東西，App 一登入就看得到。

**關鍵設定：LINE Login channel 必須和 Messaging API channel 在同一個 Provider 底下**，否則同一個人會拿到不同的 userId，資料就對不起來。

過渡期也可以在 LINE 輸入「綁定」拿到金鑰，直接當 Bearer token 測 API。

## 3. API 一覽（完整互動文件在 `/docs`，機器可讀格式在 `/openapi.json`）

| 方法 | 路徑 | 用途 |
|---|---|---|
| POST | `/api/v1/auth/line` | LINE ID token 換 access token |
| GET | `/api/v1/categories` | 分類清單＋各分類數量 |
| GET | `/api/v1/items?category=&q=&limit=&before_id=` | 列表、篩選、搜尋、分頁 |
| POST | `/api/v1/items` | 收藏連結（App 分享選單呼叫這個） |
| POST | `/api/v1/items/image` | 上傳截圖（multipart） |
| GET | `/api/v1/items/{id}` | 單筆詳情 |
| PATCH | `/api/v1/items/{id}` | 改分類、標題、標籤、備註 |
| POST | `/api/v1/items/{id}/reanalyze` | 重新抓取並分析 |
| DELETE | `/api/v1/items/{id}` | 刪除 |

分頁用 cursor（`before_id`），比頁碼穩定，App 做無限捲動直接用。

## 4. 資料模型

`items` 的重點欄位：

- `category`、`title`、`summary`、`key_points`、`tags`：AI 產生，使用者可改
- `details`（JSON）：依分類不同的結構化資料。餐廳有 `name`、`address`、`price`，旅遊有 `location`、`spots`，AI 工具有 `tools`、`repo_url`。App 可以依分類顯示不同卡片，例如餐廳卡加「在地圖開啟」按鈕。
- `status`：`ok`／`partial`（平台擋住內容）／`failed`（AI 出錯，可重新分析）
- `canonical_url`：去掉追蹤參數的網址，用來防止重複收藏

## 5. 做 App 時的建議路線

**框架：Expo（React Native）**
- 一套程式碼同時出 iOS 和 Android。
- 用 **EAS Build** 在雲端編譯 iOS 版，**Windows 也能開發**，不需要 Mac。要安裝到 iPhone 或上架仍需要 Apple Developer 帳號（年費）。

**系統分享選單**：用 `expo-share-intent` 套件，讓 App 出現在 IG、Threads 的分享清單；收到連結後呼叫 `POST /api/v1/items`。這個功能需要 development build，不能在 Expo Go 裡測。

**API 型別自動產生**：
```bash
npx openapi-typescript https://你的網址/openapi.json -o src/api/schema.ts
```
後端改欄位後重新產生一次，前端型別就同步了。

**LINE 登入**：用 LINE 官方 SDK 或 OAuth 流程取得 ID token，打 `/api/v1/auth/line`。

## 6. 上 App 前要補的東西（目前刻意保持簡單）

| 項目 | 現在 | App 化時 |
|---|---|---|
| 資料表版本 | 啟動時 `create_all` | 改用 Alembic migrations，避免改欄位時資料遺失 |
| 背景工作 | FastAPI BackgroundTasks | 量大時換佇列（Redis＋RQ、Cloud Tasks），API 改成「先回 202，App 輪詢或收推播」 |
| 截圖檔案 | 分析完就丟 | 存到 Supabase Storage／S3，App 可以看原圖 |
| Token | 永久有效的隨機金鑰 | 加上到期、刷新與撤銷（或改 JWT） |
| 搜尋 | SQL `LIKE` | Postgres 全文檢索或向量搜尋（「找上次那家有提到排隊的拉麵」） |
| 推播 | 無 | Expo Notifications：分析完成通知 |

## 7. 下一步建議順序

1. 部署 LINE bot，實際用一兩週，調整分類清單和 prompt。
2. 做 LIFF 收藏夾網頁：分類卡片、搜尋、改分類（呼叫同一組 API）。
3. 換 Postgres＋Alembic。
4. Expo App：先做分享選單＋列表兩個畫面。
