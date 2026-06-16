"""
main.py
Client Profile Management System

How to run:
    streamlit run main.py

Features:
- Fully English interface (titles, buttons, labels)
- Simple password login (from .env DASHBOARD_PASSWORD)
- 4 main tabs: Dashboard / Client Management (CRUD) / CSV Import/Export / Client Clustering
- Dedicated client profile page (open via ?client_id= in URL or button) -- independent full view for comm logs / sales / deliveries / web_store_url / map
- Full CRUD + real-time search and filtering (web_store_url supported)
- CSV import/export with web_store_url
- Per-client world maps + global dispatch on dashboard
- System logs query + export on Dashboard
- Detailed error handling + pymysql lazy for demo
- Easy "Add New Client" (name + email + industry + web store url)
- Real MySQL or pure demo mode (USE_SAMPLE_DATA)

Notes (Streamlit rerun model):
- Important state lives in st.session_state
- Profile navigation uses st.query_params for URL change ("new page")
- After data mutations, call st.rerun() for immediate UI update
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from io import StringIO
from typing import Any

import pandas as pd
import plotly.express as px
import streamlit as st
import streamlit.components.v1 as components

# 本地模組
import config
import database

import utils
from models import ClientProfile

# ============================================================
# 啟用 Demo / Sample Data 模式（無需 Supabase/MySQL，可純前端測試）
# For real MySQL: set USE_SAMPLE_DATA=false in .env + configure MYSQL_* + run init_mysql_schema.sql
# ============================================================
if config.USE_SAMPLE_DATA:
    # 明確開啟 demo 模式
    database.enable_demo_mode()
else:
    # Not forcing demo. If MYSQL_* are configured we will try real MySQL on first data load.
    pass

# ------------------------------------------------------------------
# Graceful fallback: if the user set USE_SAMPLE_DATA=false (to use a real/new MySQL)
# but pymysql is not installed in the current .venv, auto-switch to demo mode.
# This prevents the hard "Failed to load data: pymysql is not installed" error
# and gives a clear actionable message instead. Common after copying .env.example.
# ------------------------------------------------------------------
if not database.is_demo_mode():
    try:
        import pymysql  # noqa: F401
    except ImportError:
        database.enable_demo_mode()
        st.session_state["pymysql_fallback_notice"] = True

# ============================================================
# Streamlit 基本設定
# ============================================================
st.set_page_config(
    page_title=config.PAGE_TITLE,
    page_icon=config.PAGE_ICON,
    layout=config.LAYOUT,
    initial_sidebar_state="expanded",
)

# ============================================================
# Session State 初始化
# ============================================================
def init_session_state() -> None:
    defaults = {
        "logged_in": False,
        "clients_cache": [],
        "last_refresh": None,
        "edit_client_id": None,       # kept for possible future quick edit; profile now uses query param
        "graph_focus_node": None,
        "show_demo_loaded": False,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


init_session_state()

# ============================================================
# 登入閘道（Sidebar）
# ============================================================
def render_login_gate() -> None:
    with st.sidebar:
        st.markdown("### Admin Login")
        pw = st.text_input("Enter admin password", type="password", key="login_pw")
        if st.button("Login", type="primary", use_container_width=True):
            expected = config.DASHBOARD_PASSWORD or "demo123"
            if pw == expected:
                st.session_state.logged_in = True
                st.success("Login successful! Welcome to the Client Profile System")
                st.rerun()
            else:
                st.error("Incorrect password. Please try again.")
        st.markdown("---")
        st.caption("This is a simple demo protection layer. For production, consider Supabase Auth or a stricter backend.")
        st.stop()


# ============================================================
# 資料載入 / 重新整理（已相容 Demo 模式）
# ============================================================
def load_clients(force: bool = False) -> list[dict[str, Any]]:
    """載入客戶資料（Supabase 或 Demo 記憶體）"""
    if force or not st.session_state.clients_cache:
        data, err = database.get_all_clients_safe()
        st.session_state.clients_cache = data
        st.session_state.last_refresh = datetime.now(timezone.utc)

        if err:
            # Demo 模式下幾乎不會有 err
            if database.is_demo_mode():
                st.warning(f"Demo mode load issue: {err}")
            else:
                st.error(f"Failed to load data: {err}")
                st.info("Please verify your .env settings, that the Supabase project has run init_schema.sql, and check the RLS policies.")

        # Demo 模式首次如果完全沒資料，自動種子
        if database.is_demo_mode() and not st.session_state.clients_cache:
            try:
                from utils import get_demo_seed_data
                st.session_state.clients_cache = utils.get_demo_seed_data()  # type: ignore
                database.enable_demo_mode(st.session_state.clients_cache)
            except Exception:
                pass

    return st.session_state.clients_cache


def refresh_data() -> None:
    """Helper for refresh buttons"""
    load_clients(force=True)
    st.toast("Data reloaded")


# ============================================================
# 範例資料載入（第一次使用最方便）
# ============================================================
DEMO_CLIENTS = [
    {
        "name": "示範科技股份有限公司",
        "email": "demo@tech-tw.com",
        "country": "Taiwan",
        "from_where": "官網 + 2026 台北自動化展",
        "api_kit": {"json": True, "api_pdf": True, "product_specs": True, "last_requested": "2026-06-12T02:00:00Z"},
        "products": ["Alpha API", "Zeta Analytics", "Custom Integration"],
        "customer_cluster": "JSON_Heavy_APAC",
        "request_history": [
            {
                "timestamp": "2026-06-12T02:00:00Z",
                "template_used": "full_kit_v2",
                "products": ["Alpha API", "Zeta Analytics"],
                "api_type": "json",
                "notes": "需要 6 月底前交付測試環境"
            }
        ],
    },
    {
        "name": "歐洲精密製造",
        "email": "sales@eu-precision.eu",
        "country": "Germany",
        "from_where": "LinkedIn 轉介 - 只要 PDF 報價單",
        "api_kit": {"json": False, "api_pdf": True, "product_specs": False},
        "products": ["Delta PDF Pack"],
        "customer_cluster": "PDF_Only_EU",
        "request_history": [],
    },
]


def load_demo_data() -> None:
    """Load or reset sample data.
    In DEMO MODE this resets to the rich built-in seed data (great for frontend testing).
    """
    try:
        if database.is_demo_mode():
            database.reset_demo_data()
            st.session_state.clients_cache = []
            refresh_data()
            st.session_state.show_demo_loaded = True
            st.success("Demo mode reset to initial sample data (6 rich examples).")
            return

        # Real Supabase path
        result = database.upsert_clients(DEMO_CLIENTS)
        refresh_data()
        st.session_state.show_demo_loaded = True
        st.success(f"Loaded/updated {result['success']} sample records.")
        if result["errors"]:
            st.warning("Some records had issues: " + "; ".join(result["errors"]))
    except Exception as e:
        st.error(f"Failed to load sample data: {e}")


# ============================================================
# 通用小工具
# ============================================================
def get_current_clients() -> list[dict[str, Any]]:
    return st.session_state.clients_cache or load_clients()


def apply_filters(
    clients: list[dict[str, Any]],
    name_email: str,
    countries: list[str],
    clusters: list[str],
    has_json: bool,
    has_pdf: bool,
    has_specs: bool,
) -> list[dict[str, Any]]:
    """客戶端多條件篩選"""
    result = []
    name_email = (name_email or "").strip().lower()

    for c in clients:
        # 文字搜尋 (support legacy email + new industry)
        if name_email:
            hay = f"{c.get('name','')} {c.get('email','')} {c.get('industry','')}".lower()
            if name_email not in hay:
                continue

        # 國家
        if countries and c.get("country") not in countries:
            continue

        # 群聚 (legacy cluster)
        cl = c.get("customer_cluster") or "Unclassified"
        if clusters and cl not in clusters:
            continue

        # API 旗標
        api = c.get("api_kit") or {}
        if isinstance(api, dict):
            j, p, s = api.get("json"), api.get("api_pdf"), api.get("product_specs")
        else:
            j, p, s = getattr(api, "json", False), getattr(api, "api_pdf", False), getattr(api, "product_specs", False)

        if has_json and not j:
            continue
        if has_pdf and not p:
            continue
        if has_specs and not s:
            continue

        result.append(c)
    return result


def format_last_edited(c: dict) -> str:
    le = c.get("last_edited")
    if not le:
        return "—"
    if isinstance(le, str):
        try:
            if le.endswith("Z"):
                le = le[:-1] + "+00:00"
            dt = datetime.fromisoformat(le)
            return dt.astimezone().strftime("%Y-%m-%d %H:%M")
        except Exception:
            return str(le)[:16]
    if isinstance(le, datetime):
        return le.astimezone().strftime("%Y-%m-%d %H:%M")
    return str(le)


# ============================================================
# Dedicated Client Profile Page (independent view, URL-driven via ?client_id=)
# Replaces the old "edit at bottom of CRUD tab". Selecting a client opens this full page.
# ============================================================
def render_client_profile_page(client_id: int, new_features_ready: bool = None) -> None:
    """Full standalone client profile page (looks like homepage). Use browser back or button to return.
    All updates (comm logs, sales, deliveries, basic info incl. web_store_url) happen here.
    """
    # Self-contained readiness check so the page works even if called from legacy paths
    # or before the caller computed the flag.
    if new_features_ready is None:
        try:
            _ = database.get_all_products()
            _ = database.get_all_json_templates()
            new_features_ready = True
        except Exception as e:
            if "1146" in str(e) or "doesn't exist" in str(e).lower():
                new_features_ready = False
            else:
                new_features_ready = True  # unknown error, let it surface later if any

    prof = database.fetch_client(client_id) or {}
    if not prof or not prof.get("id"):
        st.error(f"Client with ID {client_id} not found.")
        if st.button("← Back to Client Management"):
            if "client_id" in st.query_params:
                del st.query_params["client_id"]
            st.rerun()
        return

    name = prof.get("name") or "Unnamed Client"

    # Top nav / header (page_config already set at top of app)
    colb1, colb2 = st.columns([1, 4])
    with colb1:
        if st.button("← Back to Dashboard", use_container_width=True):
            if "client_id" in st.query_params:
                del st.query_params["client_id"]
            st.rerun()
    with colb2:
        st.title(f"Client Profile: {name}")
        st.caption(f"ID: {prof.get('id')}  •  Last view: {datetime.now().strftime('%Y-%m-%d %H:%M')}")

    # Summary header with totals + web store link
    email_str = prof.get("email") or "—"
    industry_str = prof.get("industry") or "—"
    ws_url = prof.get("web_store_url")
    st.markdown(
        f"**Email:** {email_str} &nbsp;&nbsp;|&nbsp;&nbsp; **Industry:** {industry_str}"
    )
    if ws_url:
        st.markdown(f"**Web Store:** [Open client web store page]({ws_url})")
    else:
        st.caption("Web Store URL not set for this client.")

    # API Kit as basic info of the client (as requested)
    api_pdf = bool(prof.get("api_pdf"))
    json_file = bool(prof.get("json_file"))
    prod_specs = bool(prof.get("product_specs"))
    st.markdown(
        f"**API Kit:** PDF={'✓' if api_pdf else '—'} | JSON={'✓' if json_file else '—'} | Product Specs={'✓' if prod_specs else '—'}"
    )

    # NEW: full-width free text area (notes) right after API Kit basic info (as requested)
    current_notes = prof.get("notes") or ""
    with st.form("profile_notes_form", clear_on_submit=False):
        notes_text = st.text_area(
            "Notes (free text, full width)",
            value=current_notes,
            height=120,
            key=f"notes_{client_id}"
        )
        if st.form_submit_button("Save Notes", type="secondary"):
            try:
                database.update_client(client_id, {"notes": notes_text.strip() or None})
                st.success("Notes saved.")
                st.rerun()
            except Exception as e:
                st.error(f"Save notes failed: {e}")

    # Totals
    t1, t2, t3 = st.columns(3)
    t1.metric("Total Orders", prof.get("total_orders", 0))
    t2.metric("Addresses Delivered", prof.get("total_addresses_delivered", 0))
    t3.metric("Total Order Amount ($)", f"{float(prof.get('total_order_amount', 0)) :,.2f}")

    st.divider()

    # --- Basic Info Edit (incl. new web_store_url) ---
    with st.expander("Edit Basic Client Info", expanded=False):
        with st.form("profile_basic_form", clear_on_submit=False):
            b_name = st.text_input("Client Name *", value=prof.get("name", ""))
            b_email = st.text_input("Email (optional)", value=prof.get("email") or "")
            b_ind = st.text_input("Industry (optional)", value=prof.get("industry") or "")
            b_url = st.text_input("Web Store URL (optional, full https://...)", value=prof.get("web_store_url") or "")
            if st.form_submit_button("Save Basic Info", type="primary"):
                try:
                    payload = {
                        "name": b_name.strip(),
                        "email": b_email.strip() or None,
                        "industry": b_ind.strip() or None,
                        "web_store_url": b_url.strip() or None,
                    }
                    database.update_client(client_id, payload)
                    st.success("Basic info updated.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Update failed: {e}")

    st.divider()

    # NEW: Manage products for this client (select existing + add new products here, per request)
    if new_features_ready:
        st.subheader("Products for this Client")
        current_prods = database.get_client_products(client_id) or []
        if current_prods:
            st.write("Currently sells: " + ", ".join([p.get("name") for p in current_prods]))
        else:
            st.caption("No products assigned yet.")
        # Assign existing
        all_p = database.get_all_products() or []
        if all_p:
            curr_names = [pp["name"] for pp in current_prods]
            avail = [p["name"] for p in all_p]
            sel_names = st.multiselect("Assign / update products sold (from catalog)", options=avail, default=curr_names, key=f"prof_prod_{client_id}")
            if st.button("Save Product Assignments", key=f"save_prof_prod_{client_id}"):
                sel_ids = [p["id"] for p in all_p if p["name"] in sel_names]
                try:
                    database.set_client_products(client_id, sel_ids)
                    st.success("Products updated for client.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Failed: {e}")
        # Add brand new product for this client
        with st.expander("Create & assign a new product for this client", expanded=False):
            with st.form(f"prof_new_prod_{client_id}", clear_on_submit=True):
                npn = st.text_input("New Product Name *")
                npc = st.text_input("Category (optional)")
                nps = st.text_input("Specs (comma sep, optional)")
                if st.form_submit_button("Create Product & Assign to Client"):
                    if npn.strip():
                        try:
                            specs_l = [s.strip() for s in nps.split(",") if s.strip()] if nps else None
                            new_pid = database.create_product(npn.strip(), npc.strip() or None, specs_l)
                            # assign it (merge with current)
                            existing_ids = [p["id"] for p in current_prods]
                            database.set_client_products(client_id, list(set(existing_ids + [new_pid])))
                            st.success(f"Created and assigned: {npn.strip()}")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Failed to create/assign: {e}")
                    else:
                        st.warning("Name required.")
    else:
        st.caption("Product assignment requires new features schema.")

    st.divider()

    # === Communication Logs ===
    st.subheader("Communication Logs")
    with st.form("add_comm_form", clear_on_submit=True):
        c_date = st.date_input("Date", value=datetime.now().date(), key="prof_c_date")
        c_event = st.text_area("Event / Note (e.g. contract for api integration, follow-up call)", key="prof_c_event")
        if st.form_submit_button("Add Communication Log"):
            if c_event.strip():
                database.add_communication_log(client_id, str(c_date), c_event.strip())
                st.success("Communication log added.")
                st.rerun()
            else:
                st.warning("Event note cannot be empty.")

    comms = database.get_communication_logs(client_id) or []
    if comms:
        st.dataframe(
            pd.DataFrame(comms)[["log_date", "event"]],
            use_container_width=True, hide_index=True
        )
    else:
        st.caption("No communication logs yet.")

    st.divider()

    # === Sales Records ===
    st.subheader("Sales Records")
    with st.form("add_sales_form", clear_on_submit=True):
        s_date = st.date_input("Sale Date", value=datetime.now().date(), key="prof_s_date")
        s_desc = st.text_input("Description (e.g. Sold out 30 decks on contract)", key="prof_s_desc")
        s_qty = st.number_input("Quantity", min_value=0, value=1, step=1, key="prof_s_qty")
        s_amt = st.number_input("Amount ($)", min_value=0.0, value=0.0, step=100.0, key="prof_s_amt")
        # NEW: pick product(s) sold for this sales log (used by mainpage country/product slicers)
        prod_names_for_sale = []
        try:
            prod_names_for_sale = [p["name"] for p in (database.get_all_products() or [])]
        except Exception:
            pass
        sold_prods = st.multiselect("Product(s) sold (pick from catalog; links to homepage slicers)", options=prod_names_for_sale, key=f"sale_prods_{client_id}")
        if st.form_submit_button("Add Sales Record"):
            prod_str = ", ".join(sold_prods) if sold_prods else None
            final_desc = s_desc.strip() or (f"Sold {s_qty} x {prod_str}" if prod_str else "Sale")
            # Robust call: use 6 args (product support). If the loaded database module is stale
            # (common after edits without full restart / __pycache__), fall back gracefully and embed product in description.
            try:
                database.add_sales_record(client_id, str(s_date), final_desc, int(s_qty), float(s_amt), prod_str)
            except TypeError as te:
                if "positional argument" in str(te) or "takes 5" in str(te) or "unexpected keyword" in str(te).lower():
                    # Old version of add_sales_record loaded (no product param yet).
                    # Preserve the product info in the description so data isn't lost.
                    if prod_str:
                        final_desc = (final_desc or "Sale") + f" [product: {prod_str}]"
                    database.add_sales_record(client_id, str(s_date), final_desc, int(s_qty), float(s_amt))
                    st.warning("Note: The sales 'product' feature will be fully active after you fully restart Streamlit (see below). Product info saved in description for now.")
                else:
                    raise
            st.success("Sales record added. Totals will refresh.")
            st.rerun()

    sales = database.get_sales_records(client_id) or []
    if sales:
        sales_cols = ["sale_date", "description", "quantity", "amount"]
        if any("product" in s for s in sales):
            sales_cols = ["sale_date", "description", "quantity", "amount", "product"]
        try:
            st.dataframe(pd.DataFrame(sales)[sales_cols], use_container_width=True, hide_index=True)
        except Exception:
            st.dataframe(pd.DataFrame(sales), use_container_width=True, hide_index=True)
    else:
        st.caption("No sales records yet.")

    st.divider()

    # === Deliveries / Dispatch ===
    st.subheader("Deliveries / Dispatching Countries (drives the per-client map)")
    with st.form("add_del_form", clear_on_submit=True):
        d_country = st.text_input("Country (e.g. United States, Taiwan, Germany, United Kingdom)", key="prof_d_country")
        d_count = st.number_input("Number of addresses delivered", min_value=1, value=1, step=1, key="prof_d_count")
        d_date = st.date_input("Delivered Date (optional)", value=None, key="prof_d_date")
        if st.form_submit_button("Add Delivery"):
            if d_country.strip():
                dd = str(d_date) if d_date else None
                database.add_delivery(client_id, d_country.strip(), int(d_count), dd)
                st.success("Delivery added. The client map will update.")
                st.rerun()
            else:
                st.warning("Country is required.")

    dels = database.get_deliveries(client_id) or []
    if dels:
        st.dataframe(
            pd.DataFrame(dels)[["country", "address_count", "delivered_date"]],
            use_container_width=True, hide_index=True
        )
    else:
        st.caption("No deliveries recorded for this client yet.")

    # Per-client unique world map (as requested previously)
    client_map_data = database.get_client_dispatch_data(client_id)
    if client_map_data:
        st.markdown("**Dispatching Countries Map (this client only)**")
        map_df = pd.DataFrame(client_map_data)
        fig = px.choropleth(
            map_df,
            locations="country",
            locationmode="country names",
            color="total_addresses",
            hover_name="country",
            color_continuous_scale=px.colors.sequential.Plasma,
            title=f"Addresses Delivered by Country - {name}"
        )
        fig.update_layout(height=420, margin={"r":0,"t":30,"l":0,"b":0})
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.caption("Add deliveries above to see this client's unique dispatching map.")

    st.divider()

    # ============================================================
    # NEW: JSON Template Upload + History for this client
    # ============================================================
    if not new_features_ready:
        st.warning("JSON upload section requires schema update (run sql/update_schema_for_new_features.sql on 'cj').")
    else:
        st.subheader("JSON Templates Sent to this Client")

        # Load products for selection
        prod_list = database.get_all_products()
        prod_names = [p["name"] for p in prod_list] if prod_list else []

        with st.form("json_upload_form", clear_on_submit=True):
            uploaded = st.file_uploader("Upload JSON Template file (required)", type=["json", "txt"], key=f"json_up_{client_id}")
            sel_product = st.selectbox("Product", options=[""] + prod_names, key=f"json_prod_{client_id}")
            specs_input = st.text_input("Product Specs (comma separated, e.g. basic, advanced, color:red)", key=f"json_specs_{client_id}")
            upload_btn = st.form_submit_button("Upload & Send JSON Template", type="primary")

            if upload_btn:
                if not uploaded:
                    st.error("Please upload a JSON file.")
                else:
                    specs_list = [s.strip() for s in specs_input.split(",") if s.strip()] if specs_input else None
                    try:
                        template_id = database.save_client_json_send(
                            client_id,
                            uploaded,
                            product=sel_product or None,
                            product_specs=specs_list
                        )
                        st.success("JSON template uploaded and recorded. It will now appear in the JSON Templates tab and homepage queries (via system logs if you want).")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Upload failed: {e}")

        # Show history of sent JSONs for this client - tabular table with headers (Date, client name, file name downloadable link). No "view in json tab".
        sent_jsons = database.get_client_sent_jsons(client_id)
        if sent_jsons:
            st.markdown("**JSON Templates History**")
            # Headers
            hdr = st.columns([1.2, 2.2, 3.5])
            for i, h in enumerate(["Date", "Client Name", "File (downloadable link)"]):
                with hdr[i]:
                    st.caption(f"**{h}**")
            for s in sent_jsons:
                row = st.columns([1.2, 2.2, 3.5])
                with row[0]:
                    st.write(s.get("sent_date") or "—")
                with row[1]:
                    st.write(s.get("client_name") or name)
                with row[2]:
                    fname = s.get("template_name") or "template.json"
                    if s.get("file_path") and os.path.exists(s.get("file_path", "")):
                        try:
                            with open(s["file_path"], "rb") as f:
                                file_bytes = f.read()
                            st.download_button(
                                label=f"Download {fname}",
                                data=file_bytes,
                                file_name=fname,
                                key=f"dl_{s.get('id')}_{client_id}"
                            )
                        except Exception:
                            st.caption(f"{fname} (file missing)")
                    else:
                        st.caption(f"{fname} (file missing)")
        else:
            st.caption("No JSON templates sent to this client yet. Use the form above to upload one.")

    st.divider()
    st.caption("All changes are saved immediately. Use the Back button or change the URL query param to return.")


# ============================================================
# 主畫面
# ============================================================
def main() -> None:
    # --- 登入檢查 ---
    if not st.session_state.logged_in:
        render_login_gate()

    # ============================================================
    # NEW FEATURES SCHEMA CHECK - compute this as early as possible
    # so that the dedicated client profile page (which can be routed to directly via ?client_id)
    # can receive the flag without NameError.
    # ============================================================
    clients = get_current_clients()

    new_features_ready = True
    try:
        _ = database.get_all_products()
        _ = database.get_all_json_templates()
    except Exception as e:
        if "1146" in str(e) or "doesn't exist" in str(e).lower():
            new_features_ready = False
        else:
            raise

    if not new_features_ready:
        st.error(
            "**New features (Products tab, JSON Templates tab, advanced CRUD filters) require a one-time schema update.**\n\n"
            "Please run the SQL file in your MySQL client connected to the `cj` database:\n\n"
            "    sql/update_schema_for_new_features.sql\n\n"
            "Then click 'Refresh All Data' in the sidebar or reload the page.\n\n"
            "Until then, the basic CRUD, client profiles, logs, etc. should still work."
        )

    # ============================================================
    # Dedicated profile page routing via URL query param (e.g. ?client_id=2)
    # This makes "select client" open an independent full page.
    # ============================================================
    client_id_from_url = None
    try:
        qp = st.query_params
        raw_cid = qp.get("client_id")
        if raw_cid:
            val = raw_cid[0] if isinstance(raw_cid, list) else raw_cid
            client_id_from_url = int(val)
    except Exception:
        client_id_from_url = None

    if client_id_from_url is not None:
        render_client_profile_page(client_id_from_url, new_features_ready=new_features_ready)
        return

    # --- Sidebar ---
    with st.sidebar:
        st.markdown("### Control Panel")
        if st.button("Refresh All Data", use_container_width=True):
            refresh_data()

        btn_label = (
            "Reset to Sample Data (Demo Mode)"
            if database.is_demo_mode()
            else "Load Sample Data (Recommended for first use)"
        )
        if st.button(btn_label, use_container_width=True):
            load_demo_data()

        st.markdown("---")
        # NEW: Clear everything and load rich fresh test data (exercises products with specs, client-product links for flat table, sales with product for slicer/profile, deliveries to many countries for map, JSON uploads with renamed "Product_Specs.json" files, system logs, etc.)
        st.markdown("**Fresh Test Data (destructive)**")
        confirm_clear = st.checkbox("I understand this will DELETE all current records (clients, sales, deliveries, products, JSON templates, logs...) in demo or the connected MySQL 'cj' DB and replace with new test data.", key="confirm_clear_seed")
        if confirm_clear and st.button("🗑️ Clear DB + Load Fresh Test Data", use_container_width=True, type="primary"):
            try:
                with st.spinner("Clearing and seeding test data..."):
                    # Defensive lookup + clear instructions (common cause of "no attribute" on Windows/OneDrive + long-running streamlit)
                    seed_fn = getattr(database, "clear_and_seed_test_data", None)
                    if seed_fn is None:
                        st.error(
                            "clear_and_seed_test_data not found in the imported database module.\n\n"
                            "**This almost always means you are running an old Streamlit process that imported the module before the edit.**\n\n"
                            "1. Stop the current streamlit completely (Ctrl+C or close the terminal window).\n"
                            "2. Start a completely fresh process:  streamlit run main.py\n"
                            "3. Log in again and try the button.\n\n"
                            "You can also verify manually in a new terminal (from the project folder):\n"
                            "   python -c \"import database; print(hasattr(database, 'clear_and_seed_test_data'))\""
                        )
                        # Last-resort attempt: force Python to re-read the .py (can be noisy but sometimes helps)
                        try:
                            import importlib
                            importlib.reload(database)
                            seed_fn = getattr(database, "clear_and_seed_test_data", None)
                            if seed_fn:
                                st.warning("Module reload succeeded as a workaround. Proceeding with seed...")
                                seed_fn()
                        except Exception as reload_err:
                            st.info(f"Reload attempt also failed (expected in many cases): {reload_err}")
                    else:
                        seed_fn()
                st.session_state.clients_cache = []
                refresh_data()
                st.success("Done. Database cleared and rich test data loaded (multiple overlapping products/clients, sales tagged with products, deliveries in 7+ countries, sample JSON templates with pretty renamed files ready for download, etc.). Test the product slicer on Dashboard, sales product picker on any profile, Products tab flat rows, JSON tab, and profile JSON history.")
                st.rerun()
            except Exception as e:
                st.error(f"Clear/seed failed: {e}")

        st.markdown("---")
        last = st.session_state.last_refresh.strftime('%H:%M:%S') if st.session_state.last_refresh else "Not loaded"
        st.caption(f"Logged in | Last updated: {last}")

        if st.button("Logout", type="secondary"):
            st.session_state.logged_in = False
            st.rerun()

        st.markdown("---")
        st.markdown("**Tech Stack**")
        st.caption("Streamlit + MySQL (pymysql) + Plotly + Pandas")

    # --- Top title ---
    st.title("Client Profile Management System")
    st.markdown("**Client Profile Management System** - Manual data management tool")

    # Demo mode banner (clear notice for frontend testing)
    if database.is_demo_mode():
        if st.session_state.get("pymysql_fallback_notice"):
            st.info(
                "pymysql is not installed in your Python environment → automatically switched to **DEMO mode** (in-memory data, no database needed).\n\n"
                "**To connect to a real / new MySQL database instead:**\n"
                "1. Activate your venv and run:  `pip install pymysql cryptography`\n"
                "2. Edit `.env` : set `USE_SAMPLE_DATA=false` and fill in your MYSQL_HOST / USER / PASSWORD / DATABASE (recommend a fresh DB name)\n"
                "3. In your MySQL client, execute the full contents of `sql/init_mysql_schema.sql` (creates tables including the web_store_url column + sample data)\n"
                "4. Restart the Streamlit app (`streamlit run main.py`)\n\n"
                "The current session is using safe demo data so you can continue testing the UI, dedicated client profile page, adding logs/sales/deliveries, maps, etc. immediately."
            )
        else:
            st.warning(
                "**DEMO / OFFLINE MODE** - Using in-memory sample data.\n"
                "All create, edit, delete, CSV import, cluster changes etc. only exist for the current session.\n"
                "Refreshing the page or restarting Streamlit will reset to the initial seed data. Ideal for pure frontend UI testing.\n"
                "To use your NEW MySQL database instead: set USE_SAMPLE_DATA=false in .env, configure MYSQL_*, run sql/init_mysql_schema.sql on the target DB, then restart the app."
            )

        col1, col2 = st.columns([1, 3])
        with col1:
            if st.button("Reset to Initial Sample Data", use_container_width=True):
                database.reset_demo_data()
                st.session_state.clients_cache = []
                refresh_data()
                st.rerun()

    # Clients already loaded above for the early new_features_ready check.

    # ============================================================
    # Tabs
    # ============================================================
    tab_dash, tab_crud, tab_products, tab_json, tab_csv, tab_cluster = st.tabs([
        "Dashboard",
        "Client Management (CRUD)",
        "Products",
        "JSON Templates",
        "CSV Import / Export",
        "Client Clustering",
    ])

    # ============================================================
    # 1. Dashboard
    # ============================================================
    with tab_dash:
        st.subheader("Dashboard Overview")

        if not clients:
            st.info("No client data yet. Please add clients in Client Management or click the sidebar button to load sample data.")
        else:
            # === Global Dispatch Map + Product Slicer for Sales Details ===
            # (Country slicer removed per request; map is always the full global view. Product slicer filters the sales details below and integrates with "pick products" in client profile sales logs.)
            try:
                global_map = database.get_country_dispatch_data()
                if global_map:
                    st.markdown("**Global Addresses Delivered by Country (all clients)**")
                    gmap_df = pd.DataFrame(global_map)
                    all_countries = [str(r.get("country")) for r in global_map if r.get("country")]

                    # Only product slicer now (countries removed)
                    all_prod_names = []
                    try:
                        all_prod_names = [p["name"] for p in database.get_all_products()]
                    except Exception:
                        pass

                    selected_prods_for_slicer = st.multiselect(
                        "Product slicer for sales details (filters which sold products are included in the totals below; works with the product picker on client profile sales logs)",
                        options=all_prod_names,
                        default=[],
                        key="map_product_slicer"
                    )

                    # Always full map (no country filtering/slicer)
                    gfig = px.choropleth(
                        gmap_df,
                        locations="country",
                        locationmode="country names",
                        color="total_addresses",
                        hover_name="country",
                        color_continuous_scale=px.colors.sequential.Plasma,
                        title="Worldwide Dispatch Heatmap (all countries)"
                    )
                    gfig.update_layout(height=360, margin={"r":0,"t":20,"l":0,"b":0})
                    st.plotly_chart(gfig, use_container_width=True)

                    # Sales details — use all countries so it always has data to display; product filter applies to the sales sums/times.
                    # This replaces the previous country-restricted details.
                    st.markdown("**Sales Details (by product selection)**")
                    st.caption("Clients with any recorded deliveries. Sales totals + latest time only include sales logs where the picked product(s) match the slicer above. Use the product picker when adding sales records on a client profile page to make them appear here.")
                    details = database.get_sales_details_by_countries_and_products(
                        all_countries,   # pass all so details display even without country slicer
                        selected_prods_for_slicer or None
                    )
                    if details:
                        details_df = pd.DataFrame(details)
                        st.dataframe(details_df, use_container_width=True, hide_index=True)
                        # Export this view
                        csv_details = details_df.to_csv(index=False).encode("utf-8-sig")
                        st.download_button(
                            "Export Current Sliced Sales Details to CSV",
                            data=csv_details,
                            file_name=f"sales_details_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                            mime="text/csv",
                            key="export_sliced_details"
                        )
                    else:
                        st.caption("No sales details yet. Add deliveries (for countries) + sales records with products chosen (in client profiles), then use the product slicer above.")
            except Exception:
                pass

            # === System Logs Query Tool (replaces old country graphs on homepage) ===
            # Note: Per-client maps remain available in Client Management; global view added here.
            st.markdown("### System Logs Query & Export")
            st.caption("Filters apply live. Use the fields below to query system events (onboarding, sales, API requests, etc.). Export the current filtered view to CSV.")

            qcol1, qcol2, qcol3 = st.columns(3)
            with qcol1:
                start_d = st.date_input("Start Date", value=None, key="log_start")
            with qcol2:
                end_d = st.date_input("End Date", value=None, key="log_end")
            with qcol3:
                log_ind = st.selectbox("Industry", ["All"] + sorted({c.get("industry") for c in clients if c.get("industry")}), key="log_ind")

            log_tag = st.text_input("Filter by Tag (exact match)", value="", key="log_tag", placeholder="sales, onboarding, api")
            log_search = st.text_input("Search in message", value="", key="log_search")

            # Live query - recomputed on every widget change (cheap for this table size)
            start_str = start_d.isoformat() if start_d else None
            end_str = end_d.isoformat() if end_d else None
            ind_filter = None if log_ind == "All" else log_ind

            current_logs = database.query_system_logs(
                start_date=start_str,
                end_date=end_str,
                industry=ind_filter,
                tag=log_tag or None,
                search_text=log_search or None
            )

            if current_logs:
                log_df = pd.DataFrame(current_logs)
                # Make tags display nicely
                if "tags" in log_df.columns:
                    log_df["tags"] = log_df["tags"].apply(lambda x: ", ".join(x) if isinstance(x, list) else x)
                st.dataframe(log_df, use_container_width=True, hide_index=True)

                # Export current (live filtered) view
                csv = log_df.to_csv(index=False).encode("utf-8-sig")
                st.download_button(
                    "Export Current Results to CSV",
                    data=csv,
                    file_name=f"system_logs_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                    mime="text/csv"
                )
            else:
                st.caption("No logs match the current filters.")

            # Quick add system log
            with st.expander("Add New System Log (for testing the query tool)"):
                new_msg = st.text_input("Log Message", value="customer X required json file at ...")
                new_tags = st.text_input("Tags (comma separated)", value="api,integration")
                new_ind = st.text_input("Industry (optional)", value="")
                if st.button("Add System Log"):
                    tags_list = [t.strip() for t in new_tags.split(",") if t.strip()]
                    database.add_system_log(new_msg, tags_list, client_name=None, industry=new_ind or None)
                    st.success("System log added.")
                    st.rerun()

            st.divider()

            # Basic client metrics (kept lightweight)
            st.markdown("### Client Snapshot")
            c1, c2, c3 = st.columns(3)
            c1.metric("Total Clients", len(clients))
            total_orders = sum(c.get("total_orders", 0) for c in clients)
            c2.metric("Total Orders (all clients)", total_orders)
            total_amount = sum(float(c.get("total_order_amount", 0)) for c in clients)
            c3.metric("Total Order Value ($)", f"{total_amount:,.2f}")

    # ============================================================
    # 2. Client Management (CRUD)
    # ============================================================
    with tab_crud:
        st.subheader("Client List and Management")

        # Load products once for add form + filter (supports selecting existing products when adding client)
        all_products_for_crud = []
        prod_id_to_name_crud = {}
        try:
            all_products_for_crud = database.get_all_products() or []
            prod_id_to_name_crud = {p["id"]: p["name"] for p in all_products_for_crud}
        except Exception:
            pass

        # ========== Simple dedicated section to add clients (now with web store URL + product selection) ==========
        with st.expander("➕ Add New Client (quick)", expanded=True):
            with st.form("quick_add_client", clear_on_submit=True):
                new_name = st.text_input("Client Name *", placeholder="e.g. Example Corp")
                new_email = st.text_input("Email (optional)", placeholder="e.g. contact@example.com")
                new_industry = st.text_input("Industry (optional)", placeholder="e.g. Technology, Retail, Healthcare")
                new_web_url = st.text_input("Web Store URL (optional)", placeholder="https://client.example.com/store")

                st.markdown("**API Kit flags (for filtering):**")
                ca1, ca2, ca3 = st.columns(3)
                with ca1:
                    new_api_pdf = st.checkbox("API PDF", key="new_api_pdf")
                with ca2:
                    new_json = st.checkbox("JSON file", key="new_json")
                with ca3:
                    new_prod_specs = st.checkbox("Product Specs", key="new_prod_specs")

                # NEW: select existing products from Products page for this new client
                new_client_prod_names = []
                if all_products_for_crud:
                    new_client_prod_names = st.multiselect(
                        "Products this client sells (select from existing in Products tab)",
                        options=[p["name"] for p in all_products_for_crud],
                        key="add_new_client_products"
                    )

                add_submitted = st.form_submit_button("Add Client", type="primary")

                if add_submitted:
                    if not new_name.strip():
                        st.error("Client Name is required.")
                    else:
                        try:
                            data = {
                                "name": new_name.strip(),
                                "email": new_email.strip() or None,
                                "industry": new_industry.strip() or None,
                                "web_store_url": new_web_url.strip() or None,
                                "api_pdf": new_api_pdf,
                                "json_file": new_json,
                                "product_specs": new_prod_specs,
                                "total_orders": 0,
                                "total_addresses_delivered": 0,
                                "total_order_amount": 0.0,
                            }
                            new_id = database.insert_client(data)
                            # Assign selected existing products (if any)
                            if new_client_prod_names:
                                sel_ids = [pid for pid, nm in prod_id_to_name_crud.items() if nm in new_client_prod_names]
                                if sel_ids:
                                    database.set_client_products(new_id, sel_ids)
                            st.success(f"Client added! ID: {new_id} — {new_name.strip()}")
                            # Open the new client immediately in the dedicated profile page
                            st.query_params["client_id"] = str(new_id)
                            refresh_data()
                            st.rerun()
                        except Exception as e:
                            st.error(f"Add failed: {e}")

        st.divider()

        # Enhanced filter: name/industry + API kit checkboxes + Product multi-select
        with st.expander("Search and Filter Options", expanded=True):
            name_search = st.text_input("Search by name or industry", key="filter_text", placeholder="e.g. Tech or Acme")

            st.markdown("**API Kit Requirements (clients that have these set):**")
            col_api1, col_api2, col_api3 = st.columns(3)
            with col_api1:
                filter_api_pdf = st.checkbox("API PDF", key="filter_api_pdf")
            with col_api2:
                filter_json = st.checkbox("JSON file", key="filter_json")
            with col_api3:
                filter_product_specs = st.checkbox("Product Specs", key="filter_product_specs")

            # Product filter (multi)
            selected_product_ids = []
            if new_features_ready:
                try:
                    all_products = database.get_all_products()
                    product_options = {p["id"]: p["name"] for p in all_products} if all_products else {}
                    if product_options:
                        selected_product_names = st.multiselect(
                            "Products the client sells (multi-select)",
                            options=list(product_options.values()),
                            key="filter_products"
                        )
                        selected_product_ids = [pid for pid, pname in product_options.items() if pname in selected_product_names]
                except Exception:
                    pass  # will be caught by the top-level warning anyway
            else:
                st.caption("Product filter disabled until schema is updated.")

        # Apply advanced filters (API kit + products + text)
        display_clients = database.search_clients_for_crud(
            name_industry=name_search or None,
            api_pdf=filter_api_pdf if filter_api_pdf else None,
            json_file=filter_json if filter_json else None,
            product_specs=filter_product_specs if filter_product_specs else None,
            product_ids=selected_product_ids if selected_product_ids else None
        )
        if not name_search and not filter_api_pdf and not filter_json and not filter_product_specs and not selected_product_ids:
            display_clients = clients  # show all if no filters active

        # Clean display table using the new data model (includes web_store_url)
        if display_clients:
            display_df = pd.DataFrame([
                {
                    "ID": c.get("id"),
                    "Name": c.get("name"),
                    "Email": c.get("email"),
                    "Industry": c.get("industry"),
                    "API PDF": bool(c.get("api_pdf")),
                    "JSON File": bool(c.get("json_file")),
                    "Product Specs": bool(c.get("product_specs")),
                    "Web Store URL": (c.get("web_store_url") or "—")[:60],
                    "Total Orders": c.get("total_orders", 0),
                    "Addresses Delivered": c.get("total_addresses_delivered", 0),
                    "Total Order Amount ($)": float(c.get("total_order_amount", 0)),
                }
                for c in display_clients
            ])
            st.dataframe(display_df, use_container_width=True, hide_index=True)

            # Export for the search section (filtered results)
            try:
                export_search_df = pd.DataFrame([
                    {
                        "ID": c.get("id"),
                        "Name": c.get("name"),
                        "Email": c.get("email"),
                        "Industry": c.get("industry"),
                        "Web Store URL": c.get("web_store_url"),
                        "Total Orders": c.get("total_orders", 0),
                        "Addresses Delivered": c.get("total_addresses_delivered", 0),
                        "Total Order Amount ($)": float(c.get("total_order_amount", 0)),
                    }
                    for c in display_clients
                ])
                csv_search = export_search_df.to_csv(index=False).encode("utf-8-sig")
                st.download_button(
                    "Export Current Search Results to CSV",
                    data=csv_search,
                    file_name=f"client_search_results_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                    mime="text/csv",
                    key="export_crud_search"
                )
            except Exception:
                pass
        else:
            st.warning("No clients match the current search.")

        st.divider()

        # Action section: select client -> opens independent dedicated profile page (via URL)
        st.markdown("### Select a Client to Manage")
        st.caption("Click 'Open Full Profile Page' to view / edit communication logs, sales, deliveries and the per-client map on a dedicated screen (changes the URL).")
        # Only clients with a valid numeric id
        valid_clients = [c for c in clients if c.get("id") is not None]
        if valid_clients:
            selected_client = st.selectbox(
                "Select client",
                valid_clients,
                format_func=lambda c: f"{c.get('id')} - {c.get('name')} ({c.get('email') or c.get('industry', '')})",
                key="crud_select"
            )

            if selected_client:
                client_id = selected_client.get("id")
                with st.expander("Quick Snapshot", expanded=False):
                    snapshot = {k: v for k, v in selected_client.items() if k in ("id", "name", "email", "industry", "web_store_url", "total_orders", "total_addresses_delivered", "total_order_amount")}
                    snapshot["api_kit"] = {
                        "pdf": bool(selected_client.get("api_pdf")),
                        "json": bool(selected_client.get("json_file")),
                        "product_specs": bool(selected_client.get("product_specs"))
                    }
                    st.json(snapshot)

                col1, col2 = st.columns(2)
                with col1:
                    if st.button("Open Full Profile Page (logs, sales, map, edit)", type="primary", use_container_width=True):
                        st.query_params["client_id"] = str(client_id)
                        st.rerun()
                with col2:
                    if st.button("Clear selection", use_container_width=True):
                        # no edit_id needed anymore for profile
                        st.session_state.edit_client_id = None
                        if "client_id" in st.query_params:
                            del st.query_params["client_id"]
                        st.rerun()
        else:
            st.info("No valid clients with IDs available. Click 'Reset to Sample Data (Demo Mode)' in the sidebar or add a new client above.")

        st.divider()

        # Quick basic edit form (now includes API kit flags + products assignment)
        st.markdown("#### Quick Basic Edit (name / email / industry / url + API kit + Products)")
        st.caption("For full management (logs, sales, deliveries, JSON uploads) use the 'Open Full Profile Page' button above.")
        is_edit = bool(st.session_state.get("edit_client_id"))
        editing_client = None
        current_client_products = []
        if is_edit:
            editing_client = database.fetch_client(st.session_state.edit_client_id) or {}
            current_client_products = database.get_client_products(st.session_state.edit_client_id)
            st.markdown(f"Editing: **{editing_client.get('name')}** (ID {editing_client.get('id')})")

        with st.form("client_form", clear_on_submit=False):
            name = st.text_input("Client Name *", value=editing_client.get("name", "") if editing_client else "")
            email = st.text_input("Email (optional)", value=editing_client.get("email", "") if editing_client else "", placeholder="contact@example.com")
            industry = st.text_input("Industry", value=editing_client.get("industry", "") if editing_client else "", placeholder="Technology, Retail, Healthcare...")
            web_url = st.text_input("Web Store URL (optional)", value=editing_client.get("web_store_url", "") if editing_client else "", placeholder="https://...")

            st.markdown("**API Kit flags:**")
            ea1, ea2, ea3 = st.columns(3)
            with ea1:
                e_api_pdf = st.checkbox("API PDF", value=bool(editing_client.get("api_pdf")) if editing_client else False)
            with ea2:
                e_json = st.checkbox("JSON file", value=bool(editing_client.get("json_file")) if editing_client else False)
            with ea3:
                e_prod_specs = st.checkbox("Product Specs", value=bool(editing_client.get("product_specs")) if editing_client else False)

            # Products multi-select for this client
            all_prod_for_edit = database.get_all_products()
            prod_id_to_name = {p["id"]: p["name"] for p in all_prod_for_edit} if all_prod_for_edit else {}
            current_prod_names = [prod_id_to_name.get(p["id"]) for p in current_client_products if p["id"] in prod_id_to_name]
            selected_prod_names = st.multiselect(
                "Products this client sells",
                options=list(prod_id_to_name.values()),
                default=[n for n in current_prod_names if n],
                key="edit_client_products"
            )
            selected_prod_ids_for_save = [pid for pid, pname in prod_id_to_name.items() if pname in selected_prod_names]

            submitted = st.form_submit_button("Save Client", type="primary", use_container_width=True)

            if submitted:
                try:
                    data = {
                        "name": name.strip(),
                        "email": email.strip() or None,
                        "industry": industry.strip() or None,
                        "web_store_url": web_url.strip() or None,
                        "api_pdf": e_api_pdf,
                        "json_file": e_json,
                        "product_specs": e_prod_specs,
                    }
                    if is_edit:
                        cid = st.session_state.get("edit_client_id")
                        if cid:
                            database.update_client(cid, data)
                            database.set_client_products(cid, selected_prod_ids_for_save)
                        st.success("Basic client info + products updated.")
                    else:
                        new_id = database.insert_client(data)
                        if selected_prod_ids_for_save:
                            database.set_client_products(new_id, selected_prod_ids_for_save)
                        st.success(f"New client created (ID: {new_id}).")
                        st.session_state.edit_client_id = new_id
                        refresh_data()
                        st.rerun()
                except Exception as e:
                    st.error(f"Save failed: {e}")

    # ============================================================
    # NEW: 3. Products Tab
    # ============================================================
    with tab_products:
        if not new_features_ready:
            st.warning("Products tab requires the schema update (see error banner above). Run sql/update_schema_for_new_features.sql against your 'cj' DB, then refresh.")
        else:
            st.subheader("Products Catalog")

            # Query
            pqcol1, pqcol2 = st.columns(2)
            with pqcol1:
                p_name = st.text_input("Search by product name", key="prod_name")
            with pqcol2:
                p_cat = st.text_input("Category (empty = any)", key="prod_cat")

            filtered_products = database.search_products(name=p_name or None, category=p_cat or None)
            if not p_name and not p_cat:
                filtered_products = database.get_all_products()

            if not filtered_products:
                st.info("No products found. Add new products below.")
            else:
                # Table columns view - FLAT per product+client (separate entries), JSON File = downloadable name/link, Client = single clickable name
                # 2 clients for same product => 2 rows
                flat_rows = []
                for prod in filtered_products:
                    specs = prod.get("specs") or []
                    if isinstance(specs, str):
                        try:
                            specs = json.loads(specs)
                        except:
                            specs = [specs]
                    pjson = database.get_product_json_files(prod["id"])
                    pclients = database.get_clients_for_product(prod["id"])
                    jf_name = pjson[0].get("template_name") if pjson else "—"
                    jf_path = pjson[0].get("file_path") if pjson else None
                    jf_id = pjson[0].get("id") if pjson else None
                    if pclients:
                        for cli in pclients:
                            flat_rows.append({
                                "Name": prod.get("name"),
                                "Category": prod.get("category") or "—",
                                "Specs": ", ".join(specs) if specs else "—",
                                "JSON File": jf_name,
                                "_jf_path": jf_path,
                                "_jf_id": jf_id,
                                "Client": cli.get("name"),
                                "_client_id": cli.get("id"),
                            })
                    else:
                        # still show product even with no clients yet (one row)
                        flat_rows.append({
                            "Name": prod.get("name"),
                            "Category": prod.get("category") or "—",
                            "Specs": ", ".join(specs) if specs else "—",
                            "JSON File": jf_name,
                            "_jf_path": jf_path,
                            "_jf_id": jf_id,
                            "Client": "—",
                            "_client_id": None,
                        })

                if flat_rows:
                    # Use st.dataframe for clean table headers (as requested for Product tab).
                    # Flat rows = one entry per product+client (multiple clients => multiple rows for same product).
                    # "JSON File" and "Client" are shown as text here; real downloads + profile links are in the selector below.
                    display_df = pd.DataFrame([
                        {k: v for k, v in r.items() if not k.startswith("_")}
                        for r in flat_rows
                    ])
                    st.dataframe(
                        display_df,
                        use_container_width=True,
                        hide_index=True,
                        column_config={
                            "Name": "Name",
                            "Category": "Category",
                            "Specs": "Specs (multi)",
                            "JSON File": st.column_config.TextColumn("JSON File (download in details below)"),
                            "Client": "Client",
                        }
                    )
                else:
                    st.caption("No data.")

                # Selector gives the actual downloadable links (for the JSONs of that product) and client profile buttons.
                selected = st.selectbox(
                    "Select product to see downloadable JSON file(s) + client profile links (click client name to open full profile)",
                    options=["—"] + [p["name"] for p in filtered_products],
                    key="prod_detail_select"
                )
                if selected != "—":
                    prod = next((p for p in filtered_products if p.get("name") == selected), None)
                    if prod:
                        st.markdown(f"### {selected} Details")
                        specs = prod.get("specs") or []
                        if isinstance(specs, str):
                            try:
                                specs = json.loads(specs)
                            except:
                                specs = [specs]
                        st.write("Specs:", specs or "—")

                        pjson = database.get_product_json_files(prod["id"])
                        if pjson:
                            st.markdown("**Related JSON files (downloadable):**")
                            for pj in pjson:
                                pj_specs = pj.get("specs") or []
                                if isinstance(pj_specs, str):
                                    try:
                                        pj_specs = json.loads(pj_specs)
                                    except:
                                        pass
                                label = f"{pj.get('template_name')} (specs: {pj_specs})"
                                if pj.get("file_path") and os.path.exists(pj.get("file_path", "")):
                                    try:
                                        with open(pj["file_path"], "rb") as f:
                                            data = f.read()
                                        st.download_button(label, data=data, file_name=pj.get("template_name"), key=f"prodjson_{pj.get('id')}")
                                    except:
                                        st.caption(label + " (file missing)")
                                else:
                                    st.caption(label + " (file missing)")
                        else:
                            st.caption("No JSON files linked to this product yet.")

                        pclients = database.get_clients_for_product(prod["id"])
                        if pclients:
                            st.markdown("**Clients selling this product (click to open profile):**")
                            for pc in pclients:
                                if st.button(f"→ {pc.get('name')} (ID {pc.get('id')})", key=f"prodclient_{prod['id']}_{pc['id']}"):
                                    st.query_params["client_id"] = str(pc["id"])
                                    st.rerun()
                        else:
                            st.caption("No clients associated yet.")

            st.divider()

            # Simple add product form
            st.markdown("### Add New Product")
            with st.form("add_product_form", clear_on_submit=True):
                np_name = st.text_input("Product Name *")
                np_cat = st.text_input("Category (optional)")
                np_specs = st.text_input("Specs (comma separated)")
                if st.form_submit_button("Create Product"):
                    if not np_name.strip():
                        st.error("Name is required.")
                    else:
                        specs_l = [s.strip() for s in np_specs.split(",") if s.strip()] if np_specs else None
                        try:
                            pid = database.create_product(np_name.strip(), np_cat.strip() or None, specs_l)
                            st.success(f"Product created (ID {pid}).")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Failed: {e}")

    # ============================================================
    # NEW: 4. JSON Templates Tab
    # ============================================================
    with tab_json:
        if not new_features_ready:
            st.warning("JSON Templates tab requires the schema update (see error banner above). Run sql/update_schema_for_new_features.sql against your 'cj' DB, then refresh.")
        else:
            st.subheader("JSON Templates Catalog")

            st.caption("Search by products to find the most relevant templates (based on usage across clients).")

            # Product search - SINGLE select (as requested)
            all_jprod = database.get_all_products() or []
            jprod_names = [p["name"] for p in all_jprod]
            sel_jprod = st.selectbox("Search by Product (single)", options=[""] + jprod_names, key="json_search_prod_single")

            if sel_jprod:
                # Build grouped result by Product + Spec (one row per spec variant). Clients per spec only.
                try:
                    from collections import defaultdict
                    groups = defaultdict(lambda: {"json_name": None, "json_path": None, "clients": set()})
                    all_tpls = database.get_all_json_templates() or []
                    for t in all_tpls:
                        us = database.get_json_template_usage(t.get("id")) or []
                        for u in us:
                            if (u.get("product") or "") == sel_jprod:
                                sp = u.get("product_specs") or []
                                if isinstance(sp, str):
                                    try:
                                        sp = json.loads(sp)
                                    except:
                                        sp = [sp] if sp else []
                                key = tuple(sp) if sp else ("(no spec)",)
                                groups[key]["json_name"] = t.get("name")
                                groups[key]["json_path"] = t.get("file_path")
                                if u.get("client_name"):
                                    groups[key]["clients"].add(u.get("client_name"))
                    if groups:
                        hdr = st.columns([2.0, 2.5, 3.0, 3.5])
                        for i, h in enumerate(["Product", "Specs", "Json file (downloadable link)", "Clients"]):
                            with hdr[i]:
                                st.caption(f"**{h}**")
                        for sp_key, info in groups.items():
                            row = st.columns([2.0, 2.5, 3.0, 3.5])
                            specs_str = ", ".join(sp_key) if sp_key and sp_key != ("(no spec)",) else "—"
                            with row[0]:
                                st.write(sel_jprod)
                            with row[1]:
                                st.write(specs_str)
                            with row[2]:
                                jn = info.get("json_name") or "file.json"
                                jp = info.get("json_path")
                                if jp and os.path.exists(str(jp)):
                                    try:
                                        with open(jp, "rb") as f:
                                            jb = f.read()
                                        st.download_button(jn, data=jb, file_name=jn, key=f"jtab_dl_{sel_jprod}_{hash(sp_key)}")
                                    except Exception:
                                        st.caption(f"{jn} (file err)")
                                else:
                                    st.caption(jn)
                            with row[3]:
                                clist = ", ".join(sorted(info["clients"])) if info["clients"] else "—"
                                st.write(clist)
                    else:
                        st.info("No sends recorded for this product/spec combination yet.")
                except Exception as e:
                    st.error(f"Search error: {e}")
            else:
                st.caption("Select a product above to see matching entries (Product+Spec rows).")

            # (end of search-only tab; removed 'all json templates' and individual per-entry sections per request)

    # ============================================================
    # 5. CSV Import / Export
    # ============================================================
    with tab_csv:
        st.subheader("CSV Import / Export")

        # Export
        st.markdown("### Export Current Client Data")
        if st.button("Generate Downloadable CSV", key="btn_export"):
            if clients:
                # Simple export of current clients (new schema + web_store_url)
                export_df = pd.DataFrame([
                    {
                        "ID": c.get("id"),
                        "Name": c.get("name"),
                        "Email": c.get("email"),
                        "Industry": c.get("industry"),
                        "Web Store URL": c.get("web_store_url"),
                        "Total Orders": c.get("total_orders", 0),
                        "Addresses Delivered": c.get("total_addresses_delivered", 0),
                        "Total Order Amount": float(c.get("total_order_amount", 0)),
                    }
                    for c in clients
                ])
                csv = export_df.to_csv(index=False).encode("utf-8-sig")
                st.download_button(
                    label="Download Client Data CSV",
                    data=csv,
                    file_name=f"client_profiles_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                    mime="text/csv",
                )
            else:
                st.warning("No client data available to export.")

        st.divider()

        # Import
        st.markdown("### Upload CSV for Bulk Import / Update")
        uploaded = st.file_uploader("Select client CSV file (UTF-8)", type=["csv"], key="csv_uploader")

        if uploaded:
            try:
                raw_df = pd.read_csv(uploaded)
                st.markdown("**Preview of raw file (first 5 rows)**")
                st.dataframe(raw_df.head(), use_container_width=True)

                st.markdown("**Please map columns** (Target field -> Source CSV column)")
                csv_cols = ["-- Ignore --"] + list(raw_df.columns)

                mapping: dict[str, str] = {}

                colmap1, colmap2, colmap3 = st.columns(3)
                with colmap1:
                    mapping["name"] = st.selectbox("Client Name (name)", csv_cols, index=0, key="map_name")
                    mapping["email"] = st.selectbox("Email (legacy/optional - not used in new schema)", csv_cols, index=0, key="map_email")
                    mapping["industry"] = st.selectbox("Industry (new schema)", csv_cols, index=0, key="map_industry")
                    mapping["web_store_url"] = st.selectbox("Web Store URL (new)", csv_cols, index=0, key="map_web_url")
                    mapping["country"] = st.selectbox("Country (country)", csv_cols, index=0, key="map_country")
                with colmap2:
                    mapping["from_where"] = st.selectbox("Source / Service Type", csv_cols, index=0, key="map_from")
                    mapping["customer_cluster"] = st.selectbox("Cluster Label (legacy)", csv_cols, index=0, key="map_cluster")
                    mapping["products"] = st.selectbox("Product List (legacy)", csv_cols, index=0, key="map_products")
                with colmap3:
                    mapping["json"] = st.selectbox("Needs JSON (true/false)", csv_cols, index=0, key="map_json")
                    mapping["api_pdf"] = st.selectbox("Needs PDF", csv_cols, index=0, key="map_pdf")
                    mapping["product_specs"] = st.selectbox("Needs Product Specs", csv_cols, index=0, key="map_specs")

                if st.button("Execute Import / Update (upsert by name or email; supports industry)", type="primary"):
                    try:
                        raw_rows = utils.parse_csv_with_mapping(uploaded, mapping)
                        valid_profiles, errors = utils.validate_and_normalize_rows(raw_rows)

                        if errors:
                            st.warning("The following rows failed validation and were skipped:\n" + "\n".join(errors))

                        if valid_profiles:
                            db_rows = [p.to_db_dict() for p in valid_profiles]
                            result = database.upsert_clients(db_rows)
                            st.success(f"Import completed: {result['success']} successful out of {result['total']}")
                            if result["errors"]:
                                st.error("Errors:\n" + "\n".join(result["errors"]))
                            refresh_data()
                    except Exception as e:
                        st.error(f"Error during import process: {e}")

            except Exception as e:
                st.error(f"Failed to read CSV: {e}")

    # ============================================================
    # 4. Client Clustering
    # ============================================================
    with tab_cluster:
        st.subheader("Client Cluster Labeling (Manual + Auto Suggestion)")

        st.caption("Auto suggestions are generated using simple rules (JSON-heavy users, number of products, region keywords, etc.). You can accept the suggestion or enter any custom label manually.")

        if not clients:
            st.info("No client data available.")
        else:
            for c in clients:
                cid = c.get("id")
                email = c.get("email")
                name = c.get("name")
                key_base = str(cid) if cid is not None else (email or name or "unk")
                current = c.get("customer_cluster") or "Unclassified"
                suggested = utils.suggest_cluster(c)

                with st.container(border=True):
                    col_a, col_b, col_c = st.columns([2.5, 2, 2.5])
                    with col_a:
                        st.markdown(f"**{name}**  \nID: `{cid}`")
                        st.caption(f"Current cluster: **{current}**")
                    with col_b:
                        st.markdown(f"Suggested: `{suggested}`")
                        if st.button("Accept Suggestion", key=f"suggest_{key_base}"):
                            try:
                                database.update_client(cid if cid is not None else email, {"customer_cluster": suggested})
                                st.success("Cluster updated.")
                                refresh_data()
                                st.rerun()
                            except Exception as e:
                                st.error(str(e))
                    with col_c:
                        new_label = st.text_input("Enter custom cluster label", value=current, key=f"manual_{key_base}")
                        if st.button("Save Manual Label", key=f"save_manual_{key_base}"):
                            try:
                                database.update_client(cid if cid is not None else email, {"customer_cluster": new_label.strip() or None})
                                st.success("Saved.")
                                refresh_data()
                                st.rerun()
                            except Exception as e:
                                st.error(str(e))

    # ============================================================
    # Footer status
    # ============================================================
    st.markdown("---")
    st.caption("Data source: MySQL (pymysql) or in-memory demo (USE_SAMPLE_DATA) | Dedicated profile page uses ?client_id=URL | All changes written immediately | This tool is for manual internal data management")


if __name__ == "__main__":
    main()
