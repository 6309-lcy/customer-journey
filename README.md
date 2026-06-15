# 客戶檔案管理系統 + 知識圖譜儀表板
# Client Profile + Knowledge Graph Dashboard

使用 **Streamlit + Supabase + NetworkX + PyVis + Plotly** 建立的完整客戶檔案 CRUD 與互動知識圖譜儀表板。

完全符合指定資料模型與功能需求：
- `client_profiles` 表（UUID、email unique、api_kit JSONB、products JSONB、request_history JSONB[]、customer_cluster 等）
- CRUD、CSV 匯入（支援欄位 mapping）、CSV 匯出
- 即時搜尋與多條件篩選
- 知識圖譜（客戶 ↔ 產品 ↔ API 類型）
- 手動 + 規則式自動客戶群聚建議
- 儀表板統計與視覺化（總數、API 使用趨勢、群聚分布）
- 繁體中文介面 + 詳細錯誤處理 + Session 登入保護
- 純本地手動操作（不接任何郵件系統）

---

## 專案結構

```
customer_journey/
├── sql/
│   └── init_schema.sql          # Supabase 資料表建立 SQL（含種子資料 + RLS）
├── main.py                      # Streamlit 主程式（直接執行）
├── database.py                  # Supabase 連線與所有 CRUD
├── models.py                    # Pydantic 資料模型
├── utils.py                     # 群聚建議、CSV 處理、統計工具
├── graph_utils.py               # NetworkX 建圖 + PyVis 互動圖譜產生
├── config.py                    # 常數與環境載入
├── requirements.txt
├── .env.example
├── .gitignore
└── README.md
```

---

## 快速開始（5 分鐘）

### 1. 準備 Supabase（免費專案即可）

1. 前往 https://supabase.com 建立新專案
2. 進入專案 → **SQL Editor**
3. 複製 `sql/init_schema.sql` 全部內容，貼上並執行
4. 執行成功後到 **Table Editor** 確認 `client_profiles` 表存在，並看到 4 筆種子資料
5. 取得連線資訊：
   - Project Settings → API
   - 複製 `Project URL` 與 `anon public` key

### 2. 本地環境設定

```powershell
# 1. 建立虛擬環境（推薦）
python -m venv .venv
.\.venv\Scripts\Activate.ps1     # PowerShell
# 或 .\.venv\Scripts\activate.bat

# 2. 安裝相依套件
pip install -r requirements.txt

# 3. 複製環境變數檔
copy .env.example .env
```

### 3. 編輯 `.env`

```env
SUPABASE_URL=https://your-project-ref.supabase.co
SUPABASE_ANON_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
DASHBOARD_PASSWORD=你設定的管理密碼
```

> **安全性提醒**：此專案使用 ANON KEY + 開放 RLS policy（僅適合本地展示或內部工具）。正式環境請改用 `SERVICE_ROLE_KEY` 並收緊 RLS。

### 4. 啟動應用

```powershell
streamlit run main.py
```

- 瀏覽器會自動開啟 `http://localhost:8501`
- 輸入你在 `.env` 設定的 `DASHBOARD_PASSWORD` 登入
- 預設後備密碼為 `demo123`（請務必修改）

---

## 🧪 純前端測試模式（無需 Supabase）

如果你只想測試前端 UI（表單、篩選、CSV mapping、知識圖譜互動、群聚建議等），可以完全不連 Supabase：

1. 在 `.env` 加入：
   ```env
   USE_SAMPLE_DATA=true
   ```

2. 執行 `streamlit run main.py`

啟動後會出現醒目的 **🧪 DEMO / OFFLINE MODE** 橫幅，所有功能依然完整可用，但資料只活在記憶體中（重新整理 = 重置）。

側邊欄也有「重置為樣本資料」按鈕，方便快速回到乾淨測試狀態。

---

## 主要功能使用說明

### 儀表板 (Dashboard)
- 總客戶數、熱門 API 類型統計
- 請求趨勢折線圖（來自 request_history）
- 群聚分布圓餅圖 + 國家長條圖
- 最近請求快速檢視

### 客戶管理 (CRUD)
- 左側多條件即時篩選（姓名/Email、國家、群聚、API 類型）
- 表單新增客戶（含 api_kit 勾選 + 產品清單 + 來源說明）
- 選取客戶後可「編輯」或「刪除」
- 編輯模式下可**直接附加新的請求歷史紀錄**（timestamp 自動帶現在時間）

### CSV 匯入 / 匯出
- **匯出**：一鍵下載目前篩選結果為 CSV（UTF-8 with BOM，Excel 開啟中文正常）
- **匯入**：上傳 CSV 後出現**欄位對應表**（下拉選單）
  - 每個目標欄位（name、email、country…）可選擇來源 CSV 欄位或「— 忽略 —」
  - 重複 email 會自動 upsert
  - 匯入後顯示成功/失敗筆數 + 錯誤訊息

### 知識圖譜 (Knowledge Graph)
- 使用 NetworkX 建立圖（客戶、產品、API 類型三類節點）
- PyVis 產生互動式 HTML 圖譜嵌入 Streamlit
- 支援：
  - 依群聚/國家篩選後重新產生圖
  - 「節點詳情查詢」下拉選單（可點選任何 client/product/api 節點）
  - 「以此節點為中心重新繪圖」按鈕（只顯示直接相連的子圖）
- 滑鼠可縮放、拖曳、懸停查看基本資訊

### 客戶群聚 (Cluster)
- 每位客戶顯示目前群聚標籤
- 「自動建議群聚」按鈕：依簡單規則即時計算（JSON 重度使用者、多產品、APAC、PDF Only 等）
- 可手動輸入任意標籤並儲存

---

## 常見問題與排錯

| 問題 | 可能原因與解決方式 |
|------|------------------|
| 登入失敗 | 檢查 `.env` DASHBOARD_PASSWORD，或使用預設 demo123 |
| 無法載入資料 / permission denied | Supabase RLS 未開啟或 policy 錯誤。請重新執行 `init_schema.sql` 中的 RLS 建立語句 |
| PyVis 圖譜沒顯示或版面跑掉 | 第一次可能需等幾秒；確保使用最新 pyvis；嘗試重新整理頁面 |
| CSV 中文亂碼 | 匯出已用 `utf-8-sig`，匯入時請用 Excel「從文字/CSV」並選 UTF-8 |
| 新增客戶後資料沒更新 | 點擊頁面上的「🔄 重新載入全部資料」按鈕 |
| Email 重複錯誤 | 系統已處理 upsert，正常情況下會顯示「已更新」而非錯誤 |
| 圖譜節點太少 | 種子資料只有 4 筆，可在 CRUD 頁面多新增幾筆或按「載入範例資料」 |

---

## 開發 / 客製化提示

- 所有商業邏輯都在 `utils.py` 與 `graph_utils.py`（純函式，容易測試）
- Pydantic 模型在 `models.py`，新增欄位非常容易
- 想改圖譜顏色/物理參數 → 編輯 `graph_utils.py` 的 `generate_pyvis_html`
- 想加強自動群聚 → 擴充 `utils.py` 的 `suggest_cluster` 函式
- 想改用 multipage Streamlit → 可將各 tab 拆成 `pages/01_儀表板.py` 等

---

## 技術堆疊版本（2026-06 建議）

詳見 `requirements.txt`。

- Streamlit 1.36+
- Supabase Python client 2.5+
- PyVis（使用 `cdn_resources='in_line'` 確保可嵌入 Streamlit）
- Plotly（儀表板視覺化最佳選擇）

---

## License & 貢獻

此專案為展示用，可自由修改與內部使用。歡迎提出改進建議（尤其是圖譜點擊互動體驗與大量資料時的效能優化）。

---

**現在就可以執行 `streamlit run main.py` 開始使用！**

有任何問題請先確認：
1. `.env` 內容正確
2. Supabase SQL 已成功執行
3. 虛擬環境已安裝所有套件
