"""
utils.py
純業務邏輯工具函式（不依賴 Streamlit）

包含：
- 客戶群聚自動建議（規則式，無 ML）
- request_history 攤平（供儀表板趨勢圖）
- API 使用統計
- CSV 欄位對應解析 + 驗證
- 匯出用 DataFrame 準備
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pandas as pd

from models import ClientProfile


# ==========================
# 群聚建議（規則式）
# ==========================

def suggest_cluster(client: dict[str, Any] | ClientProfile) -> str:
    """
    根據 api_kit、products、country、from_where 給出建議群聚標籤。
    規則可在此擴充，永遠回傳字串。
    """
    if isinstance(client, ClientProfile):
        c = client.model_dump()
    else:
        c = client or {}

    api_kit = c.get("api_kit") or {}
    if isinstance(api_kit, dict):
        json_flag = bool(api_kit.get("json"))
        pdf_flag = bool(api_kit.get("api_pdf"))
        specs_flag = bool(api_kit.get("product_specs"))
    else:
        json_flag = getattr(api_kit, "json", False)
        pdf_flag = getattr(api_kit, "api_pdf", False)
        specs_flag = getattr(api_kit, "product_specs", False)

    products: list[str] = c.get("products") or []
    product_count = len(products)

    country = (c.get("country") or "").lower()
    from_where = (c.get("from_where") or "").lower()
    text = f"{country} {from_where}"

    # 判斷地區
    region = "General"
    for reg, keywords in {
        "APAC": ["taiwan", "singapore", "hong kong", "japan", "korea", "apac", "asia", "中國", "台灣", "新加坡", "香港"],
        "EU": ["germany", "france", "netherlands", "uk", "europe", "eu", "德國", "歐洲"],
        "NA": ["united states", "usa", "canada", "mexico", "north america", "美國", "加拿大"],
    }.items():
        if any(kw in text for kw in keywords):
            region = reg
            break

    # 主要規則
    if json_flag and product_count >= 3:
        return f"JSON_Heavy_{region}"
    if json_flag and product_count >= 1:
        return f"JSON_Mixed_{region}"
    if pdf_flag and not json_flag and not specs_flag:
        return "PDF_Only" if region == "General" else f"PDF_Only_{region}"
    if pdf_flag and specs_flag:
        return f"PDF_Specs_{region}"
    if json_flag and pdf_flag:
        return f"Mixed_Cluster_{region}"

    # 預設
    if product_count >= 2:
        return f"Mixed_Cluster_{region}"
    return "General"


# ==========================
# History & Stats
# ==========================

def flatten_request_history(clients: list[dict[str, Any]]) -> pd.DataFrame:
    """
    把所有客戶的 request_history 攤平成 DataFrame，方便畫趨勢圖。
    欄位：timestamp, client_email, client_name, api_type, product_count, template_used, notes
    """
    rows: list[dict] = []
    for c in clients or []:
        email = c.get("email", "")
        name = c.get("name", "")
        for h in c.get("request_history") or []:
            if isinstance(h, dict):
                ts = h.get("timestamp") or ""
                try:
                    if ts.endswith("Z"):
                        ts = ts[:-1] + "+00:00"
                    dt = datetime.fromisoformat(ts)
                except Exception:
                    dt = None
                rows.append({
                    "timestamp": dt,
                    "client_email": email,
                    "client_name": name,
                    "api_type": h.get("api_type", ""),
                    "product_count": len(h.get("products") or []),
                    "template_used": h.get("template_used", ""),
                    "notes": h.get("notes", ""),
                })
    if not rows:
        return pd.DataFrame(columns=["timestamp", "client_email", "client_name", "api_type", "product_count", "template_used", "notes"])
    df = pd.DataFrame(rows)
    df = df.sort_values("timestamp", na_position="last")
    return df


def get_api_usage_stats(clients: list[dict[str, Any]]) -> dict[str, int]:
    """
    統計目前客戶使用的 API 類型（依 api_kit 旗標 + 歷史記錄）
    回傳 {"json": 12, "api_pdf": 7, "product_specs": 4}
    """
    stats = {"json": 0, "api_pdf": 0, "product_specs": 0}

    for c in clients or []:
        api_kit = c.get("api_kit") or {}
        if isinstance(api_kit, dict):
            if api_kit.get("json"):
                stats["json"] += 1
            if api_kit.get("api_pdf"):
                stats["api_pdf"] += 1
            if api_kit.get("product_specs"):
                stats["product_specs"] += 1
        else:
            # Pydantic 物件
            if getattr(api_kit, "json", False):
                stats["json"] += 1
            if getattr(api_kit, "api_pdf", False):
                stats["api_pdf"] += 1
            if getattr(api_kit, "product_specs", False):
                stats["product_specs"] += 1

    # 也可從歷史補充（簡單計數）
    for c in clients or []:
        for h in c.get("request_history") or []:
            at = (h.get("api_type") if isinstance(h, dict) else getattr(h, "api_type", None)) or ""
            if at in stats:
                # 這裡只做目前狀態統計，不重複加歷史（避免誇大）
                pass
    return stats


def prepare_dashboard_metrics(clients: list[dict[str, Any]]) -> dict[str, Any]:
    """給儀表板用的各類統計摘要"""
    total = len(clients)
    clusters = {}
    countries = {}
    for c in clients:
        cl = c.get("customer_cluster") or "未分類"
        clusters[cl] = clusters.get(cl, 0) + 1
        co = c.get("country") or "未知"
        countries[co] = countries.get(co, 0) + 1

    api_stats = get_api_usage_stats(clients)
    history_df = flatten_request_history(clients)

    trend = pd.DataFrame()
    if not history_df.empty and "timestamp" in history_df.columns:
        trend = (
            history_df.dropna(subset=["timestamp"])
            .groupby(history_df["timestamp"].dt.date)
            .size()
            .reset_index(name="count")
            .rename(columns={"timestamp": "date"})
        )

    return {
        "total_clients": total,
        "cluster_distribution": clusters,
        "country_distribution": countries,
        "api_usage": api_stats,
        "request_trend": trend,
        "recent_requests": history_df.tail(8).to_dict("records") if not history_df.empty else [],
    }


# ==========================
# CSV 處理
# ==========================

TARGET_FIELDS = ["name", "email", "country", "from_where", "customer_cluster"]


def parse_csv_with_mapping(uploaded_file, mapping: dict[str, str]) -> list[dict[str, Any]]:
    """
    讀取上傳的 CSV，依 mapping（目標欄位 -> CSV 欄位名）重新命名並回傳 list of dict。
    忽略 mapping 值為 "" 或 "— 忽略 —" 的欄位。
    """
    try:
        df = pd.read_csv(uploaded_file)
    except Exception as e:
        raise ValueError(f"CSV 讀取失敗：{e}")

    # 移除完全空白的 row
    df = df.dropna(how="all")

    result: list[dict] = []
    for _, row in df.iterrows():
        record: dict[str, Any] = {}
        for target, source_col in mapping.items():
            if not source_col or source_col.startswith("—"):
                continue
            if source_col in df.columns:
                val = row.get(source_col)
                if pd.isna(val):
                    val = None
                record[target] = val

        # 額外處理 products（若 mapping 有 "products"）
        if "products" in mapping:
            src = mapping["products"]
            if src and not src.startswith("—") and src in df.columns:
                raw = row.get(src)
                if isinstance(raw, str):
                    record["products"] = [p.strip() for p in raw.split(",") if p.strip()]
                elif isinstance(raw, list):
                    record["products"] = raw

        # api_kit 簡單處理（若 CSV 有提供 json / api_pdf 等欄位）
        api_kit = {}
        for flag in ["json", "api_pdf", "product_specs"]:
            if flag in mapping:
                src = mapping[flag]
                if src and not src.startswith("—") and src in df.columns:
                    v = row.get(src)
                    api_kit[flag] = str(v).strip().lower() in ("true", "1", "yes", "y", "是")
        if api_kit:
            record["api_kit"] = api_kit

        if record.get("email"):   # 至少要有 email 才能 upsert
            result.append(record)
    return result


def validate_and_normalize_rows(rows: list[dict[str, Any]]) -> tuple[list[ClientProfile], list[str]]:
    """
    用 Pydantic 驗證每一筆，成功回傳模型列表，失敗收集錯誤訊息。
    """
    valid: list[ClientProfile] = []
    errors: list[str] = []

    for idx, row in enumerate(rows):
        try:
            # 補強必填
            if not row.get("name"):
                row["name"] = row.get("email", "未命名客戶")
            prof = ClientProfile.model_validate(row)
            valid.append(prof)
        except Exception as e:
            errors.append(f"第 {idx+1} 筆 ({row.get('email', '?')}): {str(e)}")
    return valid, errors


def prepare_export_dataframe(clients: list[dict[str, Any]]) -> pd.DataFrame:
    """
    準備適合匯出的 DataFrame（展平 api_kit 與 history 統計）
    """
    rows = []
    for c in clients or []:
        api = c.get("api_kit") or {}
        if isinstance(api, dict):
            json_f = api.get("json", False)
            pdf_f = api.get("api_pdf", False)
            spec_f = api.get("product_specs", False)
        else:
            json_f = getattr(api, "json", False)
            pdf_f = getattr(api, "api_pdf", False)
            spec_f = getattr(api, "product_specs", False)

        hist = c.get("request_history") or []
        hist_count = len(hist)
        last_req = ""
        if hist:
            last = hist[-1]
            last_req = last.get("timestamp", "") if isinstance(last, dict) else getattr(last, "timestamp", "")

        row = {
            "id": c.get("id"),
            "name": c.get("name"),
            "email": c.get("email"),
            "country": c.get("country"),
            "from_where": c.get("from_where"),
            "customer_cluster": c.get("customer_cluster") or "",
            "products": ", ".join(c.get("products") or []),
            "api_json": json_f,
            "api_pdf": pdf_f,
            "api_product_specs": spec_f,
            "request_history_count": hist_count,
            "last_request_in_history": last_req,
            "last_edited": c.get("last_edited"),
        }
        rows.append(row)

    return pd.DataFrame(rows)


# ============================================================
# 內建樣本資料（用於無 Supabase 的前端測試 / DEMO MODE）
# ============================================================

def get_demo_seed_data() -> list[dict[str, Any]]:
    """Rich sample data matching the new MySQL schema (clients + logs + sales + deliveries)."""
    from datetime import datetime, timezone as _tz
    now = datetime.now(_tz.utc).isoformat()

    return [
        {
            "id": 1,
            "name": "Acme Corp",
            "industry": "Technology",
            "total_orders": 12,
            "total_addresses_delivered": 45,
            "total_order_amount": 125000.50,
        },
        {
            "id": 2,
            "name": "Global Retail Ltd",
            "industry": "Retail",
            "total_orders": 8,
            "total_addresses_delivered": 120,
            "total_order_amount": 87500.00,
        },
        {
            "id": 3,
            "name": "HealthFirst Inc",
            "industry": "Healthcare",
            "total_orders": 5,
            "total_addresses_delivered": 22,
            "total_order_amount": 45000.00,
        },
    ]
