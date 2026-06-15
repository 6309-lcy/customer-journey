"""
main.py
Client Profile Management System + Knowledge Graph Dashboard

How to run:
    streamlit run main.py

Features:
- Fully English interface (titles, buttons, labels)
- Simple password login (from .env DASHBOARD_PASSWORD)
- 5 main tabs: Dashboard / Client Management (CRUD) / CSV Import/Export / Knowledge Graph / Client Clustering
- Full CRUD + real-time search and filtering
- CSV import with user-driven column mapping
- PyVis interactive knowledge graph + node details + focus subgraph
- Rule-based cluster suggestions + manual labeling
- Plotly charts on the dashboard
- Detailed error handling
- "Load Sample Data" button for quick start

Notes (Streamlit rerun model):
- Important state lives in st.session_state
- After data mutations, call st.rerun() for immediate UI update
- For the graph (HTML component), use buttons to trigger regeneration
"""

from __future__ import annotations

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
import graph_utils
import utils
from models import ClientProfile

# ============================================================
# 啟用 Demo / Sample Data 模式（無需 Supabase，可純前端測試）
# ============================================================
if config.USE_SAMPLE_DATA:
    # 明確開啟 demo 模式
    database.enable_demo_mode()
elif not config.SUPABASE_URL or not (config.SUPABASE_KEY or config.SUPABASE_ANON_KEY):
    # 沒有任何 Supabase 設定時，自動進入 demo 模式（最方便的前端測試情境）
    database.enable_demo_mode()
    # 給一個比較不打擾的提示（只在第一次）
    if "demo_auto_activated" not in st.session_state:
        st.session_state["demo_auto_activated"] = True

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
        "edit_client_id": None,       # Currently selected client for editing related records
        "graph_focus_node": None,     # 知識圖譜聚焦節點
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
# 主畫面
# ============================================================
def main() -> None:
    # --- 登入檢查 ---
    if not st.session_state.logged_in:
        render_login_gate()

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
        last = st.session_state.last_refresh.strftime('%H:%M:%S') if st.session_state.last_refresh else "Not loaded"
        st.caption(f"Logged in | Last updated: {last}")

        if st.button("Logout", type="secondary"):
            st.session_state.logged_in = False
            st.rerun()

        st.markdown("---")
        st.markdown("**Tech Stack**")
        st.caption("Streamlit + Supabase + NetworkX + PyVis + Plotly + Pydantic")

    # --- Top title ---
    st.title("Client Profile Management System")
    st.markdown("**Client Profile + Knowledge Graph Dashboard** - Manual data management tool")

    # Demo mode banner (clear notice for frontend testing)
    if database.is_demo_mode():
        st.warning(
            "**DEMO / OFFLINE MODE** - Using in-memory sample data.\n"
            "All create, edit, delete, CSV import, cluster changes etc. only exist for the current session.\n"
            "Refreshing the page or restarting Streamlit will reset to the initial seed data. Ideal for pure frontend UI testing."
        )
        col1, col2 = st.columns([1, 3])
        with col1:
            if st.button("Reset to Initial Sample Data", use_container_width=True):
                database.reset_demo_data()
                st.session_state.clients_cache = []
                refresh_data()
                st.rerun()

    clients = get_current_clients()

    # ============================================================
    # Tabs
    # ============================================================
    tab_dash, tab_crud, tab_csv, tab_graph, tab_cluster = st.tabs([
        "Dashboard",
        "Client Management (CRUD)",
        "CSV Import / Export",
        "Knowledge Graph",
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
            # === Global Dispatch Map (addresses the "per-client maps not global" gap) ===
            try:
                global_map = database.get_country_dispatch_data()
                if global_map:
                    st.markdown("**Global Addresses Delivered by Country (all clients)**")
                    gmap_df = pd.DataFrame(global_map)
                    gfig = px.choropleth(
                        gmap_df,
                        locations="country",
                        locationmode="country names",
                        color="total_addresses",
                        hover_name="country",
                        color_continuous_scale=px.colors.sequential.Plasma,
                        title="Worldwide Dispatch Heatmap (Demo + Live Data)"
                    )
                    gfig.update_layout(height=360, margin={"r":0,"t":20,"l":0,"b":0})
                    st.plotly_chart(gfig, use_container_width=True)
            except Exception:
                pass

            # === System Logs Query Tool (replaces old country graphs on homepage) ===
            # Note: Per-client maps remain available in Client Management; global view added here.
            st.markdown("### System Logs Query & Export")
            st.caption("Query all system events (onboarding, sales, API requests, etc.). Export the current view to CSV.")

            qcol1, qcol2, qcol3 = st.columns(3)
            with qcol1:
                start_d = st.date_input("Start Date", value=None, key="log_start")
            with qcol2:
                end_d = st.date_input("End Date", value=None, key="log_end")
            with qcol3:
                log_industry = st.selectbox("Industry", ["All"] + sorted({c.get("industry") for c in clients if c.get("industry")}), key="log_ind")

            log_tag = st.text_input("Filter by Tag (exact match)", value="", key="log_tag", placeholder="sales, onboarding, api")
            log_search = st.text_input("Search in message", value="", key="log_search")

            if st.button("Run Query", type="primary"):
                start_str = start_d.isoformat() if start_d else None
                end_str = end_d.isoformat() if end_d else None
                ind_filter = None if log_ind == "All" else log_ind

                logs = database.query_system_logs(
                    start_date=start_str,
                    end_date=end_str,
                    industry=ind_filter,
                    tag=log_tag or None,
                    search_text=log_search or None
                )
                st.session_state["current_log_results"] = logs

            current_logs = st.session_state.get("current_log_results", [])

            if current_logs:
                log_df = pd.DataFrame(current_logs)
                # Make tags display nicely
                if "tags" in log_df.columns:
                    log_df["tags"] = log_df["tags"].apply(lambda x: ", ".join(x) if isinstance(x, list) else x)
                st.dataframe(log_df, use_container_width=True, hide_index=True)

                # Export current view
                csv = log_df.to_csv(index=False).encode("utf-8-sig")
                st.download_button(
                    "Export Current Results to CSV",
                    data=csv,
                    file_name=f"system_logs_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                    mime="text/csv"
                )
            else:
                st.caption("No logs match the filters, or run a query first.")

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

        # Simple filter for current schema (name / industry)
        with st.expander("Search and Filter Options", expanded=True):
            name_search = st.text_input("Search by name or industry", key="filter_text", placeholder="e.g. Tech or Acme")

        display_clients = clients
        if name_search:
            ns = name_search.lower().strip()
            display_clients = [
                c for c in clients 
                if ns in str(c.get("name", "")).lower() or ns in str(c.get("industry", "")).lower()
            ]

        # Clean display table using the new data model
        if display_clients:
            display_df = pd.DataFrame([
                {
                    "ID": c.get("id"),
                    "Name": c.get("name"),
                    "Industry": c.get("industry"),
                    "Total Orders": c.get("total_orders", 0),
                    "Addresses Delivered": c.get("total_addresses_delivered", 0),
                    "Total Order Amount ($)": float(c.get("total_order_amount", 0)),
                }
                for c in display_clients
            ])
            st.dataframe(display_df, use_container_width=True, hide_index=True)
        else:
            st.warning("No clients match the current search.")

        st.divider()

        # Action section: select client for edit
        st.markdown("### Select a Client to Manage")
        # Only clients with a valid numeric id (prevents "None" parse errors from old data)
        valid_clients = [c for c in clients if c.get("id") is not None]
        if valid_clients:
            selected_client = st.selectbox(
                "Select client",
                valid_clients,
                format_func=lambda c: f"{c.get('id')} - {c.get('name')} ({c.get('industry', '')})",
                key="crud_select"
            )

            if selected_client:
                client_id = selected_client.get("id")
                with st.expander("Client Snapshot", expanded=False):
                    st.json(selected_client)

                col1, col2 = st.columns(2)
                with col1:
                    if st.button("Edit / Add Records for this client", use_container_width=True):
                        st.session_state.edit_client_id = client_id
                        st.rerun()
                with col2:
                    if st.button("Clear selection", use_container_width=True):
                        st.session_state.edit_client_id = None
                        st.rerun()
        else:
            st.info("No valid clients with IDs available. Click 'Reset to Sample Data (Demo Mode)' in the sidebar.")

        st.divider()

        # Add / Edit form (new model)
        is_edit = bool(st.session_state.get("edit_client_id"))
        editing_client = None
        if is_edit:
            editing_client = database.fetch_client(st.session_state.edit_client_id) or {}
            st.markdown(f"### Edit Client: {editing_client.get('name')}")

        with st.form("client_form", clear_on_submit=False):
            name = st.text_input("Client Name *", value=editing_client.get("name", "") if editing_client else "")
            industry = st.text_input("Industry", value=editing_client.get("industry", "") if editing_client else "", placeholder="Technology, Retail, Healthcare...")

            submitted = st.form_submit_button("Save Client", type="primary", use_container_width=True)

            if submitted:
                try:
                    data = {"name": name.strip(), "industry": industry.strip() or None}
                    if is_edit:
                        cid = st.session_state.get("edit_client_id")
                        if cid:
                            database.update_client(cid, data)
                        st.success("Basic client info updated. Use the sections below to add logs, sales, and deliveries.")
                    else:
                        new_id = database.insert_client(data)
                        st.success(f"New client created (ID: {new_id}). Add related records below.")
                        st.session_state.edit_client_id = new_id
                        refresh_data()
                        st.rerun()
                except Exception as e:
                    st.error(f"Save failed: {e}")

        # Related data sections (only when a client is selected for editing)
        selected_client_id = st.session_state.get("edit_client_id")
        if selected_client_id:
            st.divider()
            st.markdown(f"### Related Records for Client ID {selected_client_id}")

            # Communication Log
            with st.expander("Add Communication Log"):
                clog_date = st.date_input("Date")
                clog_event = st.text_area("Event / Note (e.g. contract for api integration)")
                if st.button("Add Communication Log"):
                    database.add_communication_log(selected_client_id, str(clog_date), clog_event)
                    st.success("Communication log added.")
                    refresh_data()
                    st.rerun()

            comms = database.get_communication_logs(selected_client_id)
            if comms:
                st.markdown("**Existing Communication Logs**")
                st.dataframe(pd.DataFrame(comms)[["log_date", "event"]], use_container_width=True, hide_index=True)

            # Sales Record
            with st.expander("Add Sales Record"):
                s_date = st.date_input("Sale Date")
                s_desc = st.text_input("Description (e.g. Sold out 30 decks)")
                s_qty = st.number_input("Quantity", min_value=0, value=1)
                s_amt = st.number_input("Amount ($)", min_value=0.0, value=0.0, step=100.0)
                if st.button("Add Sales Record"):
                    database.add_sales_record(selected_client_id, str(s_date), s_desc, int(s_qty), float(s_amt))
                    st.success("Sales record added.")
                    refresh_data()
                    st.rerun()

            sales = database.get_sales_records(selected_client_id)
            if sales:
                st.markdown("**Sales History**")
                st.dataframe(pd.DataFrame(sales)[["sale_date", "description", "quantity", "amount"]], use_container_width=True, hide_index=True)

            # Deliveries (for map)
            with st.expander("Add Delivery / Dispatch Country"):
                del_country = st.text_input("Country (e.g. United States, Taiwan, Germany)")
                del_count = st.number_input("Number of addresses delivered", min_value=1, value=1)
                del_date = st.date_input("Delivered Date (optional)")
                if st.button("Add Delivery"):
                    database.add_delivery(selected_client_id, del_country, int(del_count), str(del_date) if del_date else None)
                    st.success("Delivery added. World map will update.")
                    refresh_data()
                    st.rerun()

            dels = database.get_deliveries(selected_client_id)
            if dels:
                st.markdown("**Deliveries for this client**")
                st.dataframe(pd.DataFrame(dels)[["country", "address_count", "delivered_date"]], use_container_width=True, hide_index=True)

            # Per-client world map (unique to this customer profile)
            client_map_data = database.get_client_dispatch_data(selected_client_id)
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
                    title=f"Addresses Delivered by Country - Client #{selected_client_id}"
                )
                fig.update_layout(height=420, margin={"r":0,"t":30,"l":0,"b":0})
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.caption("No deliveries yet for this client. Add some above to see their unique world map.")

            if st.button("Done Editing This Client"):
                st.session_state.edit_client_id = None
                refresh_data()
                st.rerun()

    # ============================================================
    # 3. CSV Import / Export
    # ============================================================
    with tab_csv:
        st.subheader("CSV Import / Export")

        # Export
        st.markdown("### Export Current Client Data")
        if st.button("Generate Downloadable CSV", key="btn_export"):
            if clients:
                # Simple export of current clients (new schema)
                export_df = pd.DataFrame([
                    {
                        "ID": c.get("id"),
                        "Name": c.get("name"),
                        "Industry": c.get("industry"),
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
                    mapping["email"] = st.selectbox("Email (legacy/optional)", csv_cols, index=0, key="map_email")
                    mapping["industry"] = st.selectbox("Industry (new schema)", csv_cols, index=0, key="map_industry")
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
    # 4. Knowledge Graph
    # ============================================================
    with tab_graph:
        st.subheader("Client Knowledge Graph (NetworkX + PyVis)")

        st.caption("Node legend: Blue = Clients, Green = Products, Red = API Types. Edges represent 'interested in' or 'has requested this API'.")

        # Build graph from current filtered clients
        graph_clients = filtered if "filtered" in locals() and filtered else clients

        if st.button("Generate / Update Knowledge Graph", type="primary"):
            G = graph_utils.build_knowledge_graph(graph_clients)
            st.session_state["current_graph"] = G

        G = st.session_state.get("current_graph")
        if G is None:
            G = graph_utils.build_knowledge_graph(graph_clients)
            st.session_state["current_graph"] = G

        # Node selection for details
        focus_choice = None
        if G and G.number_of_nodes() > 0:
            node_choices = graph_utils.list_all_nodes_for_ui(G)
            focus_choice = st.selectbox(
                "Select a node to view details (simulates click behavior)",
                ["(No focus)"] + node_choices,
                key="graph_node_select"
            )

            focus_node = None
            if focus_choice and focus_choice != "(No focus)":
                focus_node = graph_utils.get_focus_node_id_from_ui_choice(focus_choice)
                if st.button("Rebuild subgraph centered on this node"):
                    st.session_state.graph_focus_node = focus_node
                    st.rerun()

        # Render the PyVis HTML
        current_focus = st.session_state.get("graph_focus_node")
        html = graph_utils.generate_pyvis_html(G, focus_node=current_focus, height="620px")
        components.html(html, height=650, scrolling=False)

        st.markdown("---")
        st.markdown("**Node Details**")

        if focus_choice and focus_choice != "(No focus)":
            node_id = graph_utils.get_focus_node_id_from_ui_choice(focus_choice)
            details = graph_utils.get_node_details(node_id, graph_clients)
            st.json(details)
        else:
            st.caption("Select a node above to see detailed information about the client, product, or API type here.")

    # ============================================================
    # 5. Client Clustering
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
                        st.markdown(f"**{name}**  \n`{email or 'id:'+str(cid)}`")
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
    st.caption("Data source: Supabase (or in-memory demo data) | All changes are written immediately | This tool is for manual internal data management")


if __name__ == "__main__":
    main()
