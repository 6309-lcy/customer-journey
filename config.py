"""
config.py
環境變數載入 + 應用常數定義

使用方式：
    from config import SUPABASE_URL, SUPABASE_KEY, DASHBOARD_PASSWORD
    from config import COMMON_PRODUCTS, API_FLAG_KEYS, DEFAULT_CLUSTERS
"""

import os
from dotenv import load_dotenv

# 載入 .env（若存在）
load_dotenv()

# ==========================
# Supabase 連線設定
# ==========================
SUPABASE_URL: str | None = os.getenv("SUPABASE_URL")
SUPABASE_KEY: str | None = os.getenv("SUPABASE_ANON_KEY") or os.getenv("SUPABASE_SERVICE_ROLE_KEY")

# 向後相容別名
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY")

DASHBOARD_PASSWORD: str = os.getenv("DASHBOARD_PASSWORD", "demo123")

# ============================================================
# 前端測試模式（無需 Supabase）
# ============================================================
# 設為 true 時，database 層會切換到記憶體樣本資料（in-memory）。
# 適合純粹測試 UI、表單、篩選、CSV、知識圖譜、群聚等前端行為。
# 設定方式：
#   1. .env 加入 USE_SAMPLE_DATA=true
#   2. 或直接執行時環境變數 USE_SAMPLE_DATA=1 streamlit run main.py
USE_SAMPLE_DATA: bool = os.getenv("USE_SAMPLE_DATA", "false").lower() in ("1", "true", "yes", "on")

# ==========================
# 應用常數（給 UI 與建議演算法使用）
# ==========================

# 常見產品清單（新增客戶表單與 CSV 建議使用）
COMMON_PRODUCTS: list[str] = [
    "Alpha API",
    "Beta Specs",
    "Gamma Connector",
    "Delta PDF Pack",
    "Epsilon Hardware",
    "Zeta Analytics",
    "Theta Edge",
    "Omega Quotation",
    "Custom Integration",
]

# API Kit 旗標（對應 api_kit JSONB 欄位）
API_FLAG_KEYS: list[str] = ["json", "api_pdf", "product_specs"]

# 預設可選的群聚標籤（供下拉或提示）
DEFAULT_CLUSTERS: list[str] = [
    "JSON_Heavy_APAC",
    "JSON_Heavy_EU",
    "JSON_Heavy_NA",
    "PDF_Only",
    "PDF_Only_EU",
    "PDF_Only_APAC",
    "Mixed_Cluster",
    "General",
    "Enterprise",
]

# 群聚建議用的關鍵字（擴充這裡即可加強規則）
CLUSTER_KEYWORDS = {
    "APAC": ["taiwan", "singapore", "hong kong", "japan", "korea", "apac", "asia", "中國", "台灣", "新加坡"],
    "EU": ["germany", "france", "netherlands", "uk", "europe", "eu", "德國", "歐洲"],
    "NA": ["united states", "usa", "canada", "mexico", "north america", "美國", "加拿大"],
}

# Streamlit page settings
PAGE_TITLE = "Client Profile Management System | Knowledge Graph Dashboard"
PAGE_ICON = ""
LAYOUT = "wide"

# ============================================================
# Request History Templates
# ============================================================
# These are the common template names users can pick when logging
# a new request in a client's history.
#
# You can freely add or change these. 
# The app will also automatically collect any templates that have 
# already been used in existing request_history records and offer them.
KNOWN_TEMPLATES: list[str] = [
    "full_kit_v1",
    "full_kit_v2",
    "json_only",
    "json_specs",
    "pdf_only",
    "pdf_specs",
    "minimal_quote",
    "custom_integration",
]


def validate_env() -> tuple[bool, list[str]]:
    """
    檢查必要的環境變數是否存在。
    回傳 (是否通過, 錯誤訊息清單)
    """
    errors: list[str] = []
    if not SUPABASE_URL:
        errors.append("缺少 SUPABASE_URL")
    if not (SUPABASE_KEY or SUPABASE_ANON_KEY):
        errors.append("缺少 SUPABASE_ANON_KEY 或 SUPABASE_SERVICE_ROLE_KEY")
    return len(errors) == 0, errors


def get_supabase_key() -> str:
    """取得實際要用的 key（優先 service_role）"""
    return SUPABASE_KEY or SUPABASE_ANON_KEY or ""
