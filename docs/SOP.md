# 連結雷達 製作流程與 SOP

這份文件記錄「連結雷達」從構想到上線的完整過程，以及之後維護、更新、排除問題的標準作業流程（SOP）。照著做，就能從零重建一套一模一樣的服務。

> 文件中的 `<你的服務網址>`、`<你的官方帳號>` 等都是佔位字，請換成自己的設定。**任何金鑰都不要寫進程式碼或這份文件。**

---

## 目錄

1. [專案簡介](#1-專案簡介)
2. [製作歷程](#2-製作歷程)
3. [系統架構](#3-系統架構)
4. [部署 SOP（從零開始）](#4-部署-sop從零開始)
5. [圖文選單設定 SOP](#5-圖文選單設定-sop)
6. [審核制設定 SOP](#6-審核制設定-sop)
7. [日常維運 SOP](#7-日常維運-sop)
8. [疑難排解](#8-疑難排解)
9. [費用與限制](#9-費用與限制)
10. [未來規劃](#10-未來規劃)

---

## 1. 專案簡介

**問題**：在 Facebook、Instagram、Threads、X 看到想留的貼文（餐廳、旅遊、AI 工具…），存在各平台裡很難再找到。

**解法**：一個 LINE 機器人。在任何 App 按「分享 → LINE → 機器人」，它會：

1. 辨識平台、展開短網址
2. 抓取貼文內容（抓不到時可補傳截圖）
3. 用 Claude AI 自動分類、下標題、寫摘要、加標籤
4. 存進資料庫，之後可依分類瀏覽、搜尋、刪除

**使用技術**

| 用途 | 服務 | 費用 |
|---|---|---|
| 使用者介面 | LINE 官方帳號＋Messaging API | 免費（回覆不計額度） |
| 後端程式 | Python＋FastAPI | — |
| AI 分類摘要 | Claude API（Haiku） | 每則約 0.001 美元 |
| 主機 | Render | 免費方案 |
| 資料庫 | Neon（Postgres） | 免費方案 |
| 程式碼存放 | GitHub（私人儲存庫） | 免費 |

---

## 2. 製作歷程

### 2.1 決定產品形式

比較三種做法：

| | LINE 機器人 | 網頁 App | 原生 iPhone App |
|---|---|---|---|
| 分享連結 | 最方便（系統分享選單就有 LINE） | 要複製貼上（iPhone 網頁無法出現在分享選單） | 最方便 |
| 瀏覽整理 | 聊天介面較難翻找 | 最好 | 最好 |
| 開發難度 | 低 | 中 | 高（需要 Mac＋Xcode） |

**結論**：先做 LINE 機器人負責「收」，之後再做網頁負責「看」。兩邊共用同一個後端和資料庫。

### 2.2 為 App 預留架構

雖然先做 LINE，程式一開始就把「核心邏輯」和「LINE 介面」分開，並提供 REST API。之後做網頁或 App 時，只要寫畫面，不用重寫分類、摘要、去重等邏輯。詳見 [ARCHITECTURE.md](ARCHITECTURE.md)。

### 2.3 功能迭代紀錄

| 版本 | 內容 |
|---|---|
| v0.1 | 收連結、抓內容、AI 分類摘要、去重、截圖補齊、最近／分類／看分類／搜尋／改分類指令、REST API |
| v0.2 | 「最近、看分類、搜尋」改為條列式清單（一張卡片多筆，不用左右滑） |
| v0.3 | 圖文選單（聊天室下方六格按鈕） |
| v0.4 | 刪除功能：卡片與清單上的刪除鈕、「刪除」指令，皆需二次確認 |
| v0.5 | 「分類」改為大按鈕清單，整行可點 |
| v0.6 | 審核制：新使用者需管理者核准才能使用 |

---

## 3. 系統架構

```
 IG / Threads / FB / X ──分享──▶ LINE 官方帳號
                                     │ Webhook
                                     ▼
                        Render 上的 FastAPI 伺服器
                        ├─ channels/line_webhook.py  LINE 轉接層
                        ├─ api/v1.py                 REST API（網頁／App 用）
                        └─ core/                     核心邏輯（不依賴 LINE）
                            ├─ fetcher.py   平台辨識、抓內容
                            ├─ analyzer.py  呼叫 Claude
                            └─ service.py   收藏、查詢、刪除、審核
                                     │
                     ┌───────────────┴───────────────┐
                     ▼                               ▼
              Neon 資料庫（Postgres）           Claude API
```

**各平台抓取能力**

| 平台 | 方式 | 效果 |
|---|---|---|
| X | 公開代理 API（fxtwitter，備援 vxtwitter） | 通常能拿到全文 |
| 一般網頁、新聞、部落格 | 直接抓 HTML | 好 |
| Threads、IG、FB | 只讀連結預覽資訊 | 常只有部分，靠截圖補齊 |
| Google 地圖短網址 | 展開後取地點名稱 | 有店名 |

---

## 4. 部署 SOP（從零開始）

整個流程約 1 小時。**請準備一個記事本，存放過程中拿到的四組金鑰，不要傳給任何人。**

需要準備：一台電腦（步驟 4、5 需要）、LINE 帳號、信用卡（Claude API 儲值用）。

### 步驟 1：LINE 官方帳號與 Messaging API

1. 用 **LINE Official Account** App 或 manager.line.biz 建立一個官方帳號。
2. 啟用 Messaging API（**手機 App 沒有這個選項**，要用網頁版）：
   - 電腦或手機 Safari 開 **manager.line.biz**（手機請切換「要求桌面版網站」）
   - 進入帳號 → 右上角「設定」→ 左側「Messaging API」→「啟用 Messaging API」
   - 建立 **Provider**（服務提供者），名稱自訂。**之後做網頁登入要用同一個 Provider。**
3. 在同一頁複製 **Channel secret** → 記事本。
4. 左側「回應設定」：**自動回應訊息：關閉**、**Webhook：開啟**、**聊天：關閉**。
5. 取得 **Channel access token**：
   - 開 **developers.line.biz/console/**，用 LINE 帳號登入
   - 選 Provider → 點官方帳號的 channel → 上方「Messaging API」分頁
   - 最下方 **Channel access token (long-lived)** → **Issue** → 複製 → 記事本

> ⚠️ 一個官方帳號只能設一個 Webhook。如果帳號已經接了別的機器人，請另外建新帳號。

### 步驟 2：Claude API 金鑰

1. 開 **platform.claude.com** 登入。
2. **Settings → Billing**：儲值（5 美元約可處理 2,500～5,000 則），建議設定每月花費上限。
3. **Settings → API keys** → 建立金鑰。若跳出「身分聯合」說明，選「**使用 API 金鑰繼續**」。
4. 金鑰（`sk-ant-` 開頭）**只顯示一次**，立刻複製 → 記事本。

> API 與 Claude App 訂閱是分開計費的。

### 步驟 3：Neon 資料庫

1. 開 **neon.tech**，用 GitHub 帳號註冊。
2. 建立專案：Region 選 **AWS Asia Pacific (Singapore)**。
3. 點 **Connect**，複製 `postgresql://` 開頭的連線字串 → 記事本。
   - 密碼若顯示星號，先按 Show password
   - **檢查網址中不能有 `&amp;`**（見疑難排解 8.4）

### 步驟 4：程式碼放上 GitHub

1. github.com → **New repository** → 名稱 `link-radar`、選 **Private**、不勾任何初始化選項。
2. 在空白儲存庫頁點「**uploading an existing file**」。
3. 把專案資料夾**裡面的內容**（app、docs、tests、requirements.txt、Dockerfile…）全部拖進去 → **Commit changes**。
4. 確認儲存庫最上層直接看得到 `app`、`requirements.txt`（不是多包一層資料夾）。

### 步驟 5：Render 部署

1. render.com → 用 GitHub 登入 → **New → Web Service** → 授權並選 `link-radar`。
2. 設定：
   - **Language**：Docker（自動偵測，不用填指令）
   - **Region**：**Singapore**（與資料庫同區；若預設是別區，點「Deploy in a new region」）
   - **Instance Type**：Free
3. **Environment Variables**：點「Add from .env」貼上以下內容（換成實際值，等號前後不要空格）：
   ```
   LINE_CHANNEL_SECRET=
   LINE_CHANNEL_ACCESS_TOKEN=
   ANTHROPIC_API_KEY=
   DATABASE_URL=
   ```
   不要按「Generate」。
4. **Deploy web service**，等紀錄出現「Your service is live 🎉」。
5. 測試：瀏覽器開 `<你的服務網址>/health`，應顯示 `{"status":"ok"}`。
   （直接開首頁顯示 `Not Found` 是正常的。）

### 步驟 6：串接 LINE 並測試

1. developers.line.biz → 你的 channel → **Messaging API** 分頁 → **Webhook settings**：
   - Webhook URL：`<你的服務網址>/line/webhook` → **Update**
   - 按 **Verify** → 出現 **Success**（逾時就等 30 秒再按，伺服器可能在休眠）
   - **Use webhook**：開啟
2. 用手機 LINE 掃同頁的 QR code 加好友。
3. 輸入「分類」，應回覆「還沒有收藏…」；再分享一個連結測試。

---

## 5. 圖文選單設定 SOP

聊天室下方的六格按鈕。圖片在 [docs/richmenu.png](richmenu.png)（2500×1686），產生程式在 `docs/richmenu_generator.py`。

![圖文選單](richmenu.png)

1. 把 `richmenu.png` 存到手機。
2. LINE Official Account App → 切到你的帳號 → **圖文選單** → **建立**。
3. 版型選**大型、上下兩排各三格**，上傳圖片。
4. 每格動作類型選「**文字**」：

   | 格子 | 按鈕 | 文字 |
   |---|---|---|
   | A | 最近收藏 | `最近` |
   | B | 分類總覽 | `分類` |
   | C | 搜尋收藏 | `搜尋` |
   | D | 美食口袋 | `看 餐廳` |
   | E | AI 工具 | `看 AI` |
   | F | 使用說明 | `說明` |

5. 顯示設定：標題自訂、使用期間結束時間拉到最遠、選單列文字「📚 收藏選單」、預設顯示。
6. 儲存後重新打開聊天室。

---

## 6. 審核制設定 SOP

設定後，新加入的使用者要經管理者核准才能使用。未核准者只會收到等待提示，不會消耗 AI 額度。

**啟用**

1. developers.line.biz → 你的 channel → **Basic settings** → 最下方 **Your user ID**（U 開頭）。
2. Render → 你的服務 → **Environment** → 新增 `ADMIN_LINE_USER_IDS` = 你的 User ID（多位管理者用逗號分隔）→ **Save, rebuild, and deploy**。

不設定這個變數＝不啟用審核，任何人加好友都能直接使用。

**日常操作**（管理者在 LINE 輸入）

| 指令 | 作用 |
|---|---|
| `待審核` | 列出等待核准的人 |
| `成員` | 列出所有使用者與狀態 |
| `核准 #編號` | 核准，對方會收到通知 |
| `拒絕 #編號` | 拒絕（之後可再核准） |

有新申請時，管理者會收到通知，附核准／拒絕按鈕。每個新申請約用掉 2 則 push 訊息（每月免費 200 則）。

> 審核制啟用前就存在的使用者，自動視為已核准。

---

## 7. 日常維運 SOP

### 7.1 更新程式

1. 取得新版檔案。
2. GitHub 儲存庫 → 進入檔案所在資料夾（例如 `app/channels`）→ **Add file → Upload files** → 拖入檔案（同名自動覆蓋）→ **Commit changes**。
   - 多個資料夾都有變動時：在儲存庫**首頁**上傳整個專案的內容即可。
3. Render 會自動重新部署，約 2～3 分鐘，狀態回到 **Live** 即完成。
   - 沒有自動部署：Render 右上角 **Manual Deploy → Deploy latest commit**。

### 7.2 修改設定（環境變數）

Render → 服務 → **Environment** → 編輯 → **Save, rebuild, and deploy**。

| 變數 | 必填 | 說明 |
|---|---|---|
| `LINE_CHANNEL_SECRET` | ✅ | LINE Channel secret |
| `LINE_CHANNEL_ACCESS_TOKEN` | ✅ | LINE Channel access token |
| `ANTHROPIC_API_KEY` | ✅ | Claude API 金鑰 |
| `DATABASE_URL` | ✅ | Neon 連線字串 |
| `ADMIN_LINE_USER_IDS` | | 管理者 User ID，啟用審核制 |
| `CLAUDE_MODEL` | | 預設 `claude-haiku-5-5` |
| `LINE_PUSH_FALLBACK` | | 回覆逾時時改用 push，預設 `true` |
| `LIFF_URL`、`LINE_LOGIN_CHANNEL_ID` | | 之後做網頁收藏夾時使用 |

### 7.3 查看紀錄

Render → 服務 → **Logs**。在 Search logs 輸入關鍵字（如 `Error`、`401`、`psycopg`）快速定位問題。

### 7.4 定期檢查

| 頻率 | 項目 | 位置 |
|---|---|---|
| 每月 | Claude API 餘額與用量 | platform.claude.com → Usage／Billing |
| 每月 | LINE 訊息額度 | LINE Official Account 主頁「免費訊息則數」 |
| 每季 | 資料庫容量（上限 0.5 GB） | Neon 專案頁 Storage |

### 7.5 更換金鑰（金鑰外洩或失效時）

1. 到對應平台重新發行（LINE：Reissue；Claude：建立新金鑰並刪除舊的；Neon：Reset password）。
2. Render 更新對應環境變數 → Save, rebuild, and deploy。

---

## 8. 疑難排解

實際部署時遇過的問題與解法：

### 8.1 LINE Business ID「電話號碼認證：發生錯誤」
- 改用「**使用 LINE 帳號登入**」，通常不需電話認證。
- 或改用電腦瀏覽器無痕視窗、關閉 VPN／iCloud 私密轉送。
- 嘗試太多次會被暫時鎖住，隔天再試。

### 8.2 找不到 Messaging API 設定
手機 App 沒有，必須用 **manager.line.biz 網頁版**（手機請切桌面版網站）。

### 8.3 機器人一直回「感謝您的訊息！很抱歉，本帳號無法個別回覆…」
回應設定中「自動回應訊息」沒關。注意：自動回應的編輯畫面裡的「啟用」按鈕是打開它，不是關閉。

### 8.4 部署失敗：`invalid connection option "amp;channel_binding"`
複製 Neon 網址時 `&` 被轉成 `&amp;`。到 Render 編輯 `DATABASE_URL`，刪掉結尾的 `&amp;channel_binding=require`，或把所有 `&amp;` 改成 `&`。

### 8.5 部署失敗：`DATABASE_URL` 其他格式問題
值必須直接以 `postgresql://` 開頭，前面不能有 `psql`，前後不能有引號，密碼不能是星號。

### 8.6 機器人完全沒回應，紀錄出現 `401 Unauthorized` / `Authentication failed`
**Channel access token 錯誤**（拿到別的帳號的、複製不完整、或之後又按了 Reissue 導致舊的失效）。重新 Reissue 並完整複製，更新 Render 環境變數。
（能收到 401 代表 Webhook 與 Channel secret 是對的。）

### 8.7 機器人完全沒回應，紀錄也沒有 `POST /line/webhook`
LINE 沒把訊息送過來：檢查 Webhook URL 是否正確、**Use webhook** 是否開啟、Verify 是否 Success。

### 8.8 第一則訊息要等很久
Render 免費方案閒置約 15 分鐘會休眠，喚醒需 30～60 秒。之後恢復正常。要消除可升級 Render 付費方案。

### 8.9 IG／Threads／FB 只抓到部分內容
平台限制，屬正常現象。10 分鐘內補傳貼文截圖，會自動合併到那一筆。

### 8.10 收藏顯示「AI 分析失敗」
多半是 Claude API 餘額不足或金鑰錯誤。儲值或更新金鑰後，可透過 API `POST /api/v1/items/{id}/reanalyze` 重新分析。

---

## 9. 費用與限制

| 項目 | 免費額度／費用 | 實際影響 |
|---|---|---|
| Claude API | 每則約 0.001 美元 | 5 美元約 2,500～5,000 則，**最先需要注意** |
| Neon 儲存 | 0.5 GB／專案 | 約可存 2～5 萬筆收藏 |
| Neon 運算 | 每月 100 CU-hours，閒置自動暫停 | 個人使用用不完 |
| Render | 每月 750 小時，閒置休眠 | 個人使用足夠；同帳號多個免費服務共用時數 |
| LINE 訊息 | 回覆免費；push 每月 200 則 | 只有休眠補送與審核通知會用到 push |

**多人使用**：每個 LINE 使用者有獨立的收藏庫，互相看不到。但 AI 費用由架設者負擔，且管理者技術上可以看到資料庫內容，分享前請告知使用者。

---

## 10. 未來規劃

- [ ] **網頁收藏夾（LIFF）**：在 LINE 內開啟網頁，分類卡片瀏覽、搜尋、編輯（API 已完成，只差畫面）
- [ ] 搜尋按鈕改為「按下後直接輸入關鍵字」
- [ ] 資料庫改用 Alembic 管理版本
- [ ] 截圖存檔（Supabase Storage／S3）
- [ ] 原生 App：Expo（React Native）＋EAS Build，Windows 也能開發 iOS 版；用 `expo-share-intent` 出現在系統分享選單
