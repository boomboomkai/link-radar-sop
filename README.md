# 連結雷達 Link Radar

把 FB、IG、Threads、X 或任何網頁連結分享給 LINE 機器人，它會自動：
辨識平台 → 抓取內容 → 用 Claude 分類（餐廳、旅遊、AI／程式…）→ 摘要 → 存進資料庫。
抓不到內容時補傳一張截圖，會自動合併到上一筆。

後端同時提供 REST API（`/api/v1`），之後的 LIFF 網頁和 iPhone／Android App 直接沿用，不用重寫。

📘 **完整製作流程、部署與維運 SOP、疑難排解：[docs/SOP.md](docs/SOP.md)**
🏗 架構與 App 化規劃：[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)

---

## 一、準備帳號

1. **LINE 官方帳號＋Messaging API**
   - 到 LINE Official Account Manager 建立一個官方帳號，在「設定 → Messaging API」啟用，選一個 Provider（之後 LINE Login 要用同一個）。
   - 到 LINE Developers Console 打開這個 channel：
     - Basic settings → 複製 **Channel secret**
     - Messaging API → 發行 **Channel access token（long-lived）**
   - 建議和記帳 bot 分開成兩個官方帳號，互不干擾。
2. **Claude API key**：到 console.anthropic.com 建立。

## 二、在 Windows 本機跑起來

```powershell
cd link-radar
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env      # 用記事本填入上面三個值
uvicorn app.main:app --reload --port 8000
```

開瀏覽器到 http://localhost:8000/docs 可以看到 API 文件。

LINE 需要一個公開的 https 網址才能送訊息進來，本機測試可以用 ngrok：

```powershell
ngrok http 8000
```

把 ngrok 給的網址加上 `/line/webhook`，貼到 LINE Developers → Messaging API → **Webhook URL**，然後：
- 打開 **Use webhook**
- 在 LINE Official Account Manager 關掉 **自動回應訊息**（不然它會搶著回）

加機器人好友，傳一個連結試試看。

## 三、部署上線（以 Render 為例）

1. 程式碼推到 GitHub。
2. Render → New → Web Service，選這個 repo：
   - Build command：`pip install -r requirements.txt`
   - Start command：`uvicorn app.main:app --host 0.0.0.0 --port $PORT`
3. Environment 填入 `.env` 的值，**`DATABASE_URL` 改用 Postgres**（Neon 或 Supabase 免費方案）。Render 免費方案重啟後硬碟會清空，SQLite 資料會不見。
4. Webhook URL 改成 `https://你的服務.onrender.com/line/webhook`。

注意：Render 免費方案閒置會休眠，第一則訊息可能要等 30 秒以上，這時程式會改用 push 補發結果（消耗每月免費訊息額度）。常用的話建議付費方案，或改用 Railway、Fly.io、Google Cloud Run（附 Dockerfile）。

## 四、LINE 指令

| 指令 | 作用 |
|---|---|
| 傳連結（可夾帶文字） | 自動收藏，夾帶的文字存成備註 |
| 傳截圖 | 10 分鐘內接在抓不完整的連結後面會自動合併，否則存成新收藏 |
| 最近 | 最近 5 筆（條列式） |
| 分類 | 各分類數量，點分類即可查看 |
| 看 餐廳 | 某分類最新 10 筆 |
| 搜尋 拉麵 | 搜尋標題、摘要、內文、標籤 |
| 改 旅遊 | 把上一筆改分類 |
| 刪除 | 刪除上一筆（卡片、清單上也有刪除鈕，皆需確認） |
| 綁定 | 取得網頁／App 用的金鑰 |

管理者另有「待審核」、「成員」、「核准 #編號」、「拒絕 #編號」，見 [SOP 第 6 節](docs/SOP.md#6-審核制設定-sop)。

## 五、各平台能抓到什麼

| 平台 | 方式 | 效果 |
|---|---|---|
| X | 公開代理 API（fxtwitter，備援 vxtwitter） | 通常能拿到全文 |
| 一般網頁、部落格、新聞 | 直接抓 HTML | 好 |
| Threads、IG、FB | 只讀連結預覽資訊 | 常只有部分文字，靠截圖補齊 |
| Google 地圖短網址 | 展開後取地點名稱 | 有店名 |

## 六、測試

```powershell
pip install pytest
pytest
```

## 專案結構

```
app/
  main.py               FastAPI 進入點
  config.py / db.py     設定、資料庫連線
  models.py             資料表：User、Item
  schemas.py            API 資料格式（App 對接的合約）
  core/                 ← 核心邏輯，不依賴 LINE
    categories.py       分類清單
    fetcher.py          平台辨識、短網址展開、內容抓取
    analyzer.py         Claude 分類＋摘要
    service.py          收藏、查詢、修改流程
  channels/             ← 各種入口的轉接層
    line_webhook.py     LINE 事件處理
    line_flex.py        LINE 卡片外觀
  api/v1.py             REST API（LIFF、App 用）
docs/SOP.md             製作流程與 SOP
docs/ARCHITECTURE.md    架構與 App 化規劃
docs/richmenu.png       LINE 圖文選單圖片
```
