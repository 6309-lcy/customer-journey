"""
database.py
MySQL-based data layer for the Client Profile Management System.

Supports:
- Real MySQL via pymysql
- Full DEMO MODE (in-memory) for frontend testing (set USE_SAMPLE_DATA=true)

New data model includes:
- clients (name, industry, totals)
- communication_logs
- sales_records
- deliveries (for world map by country)
- system_logs (queryable on homepage)

All functions return plain dicts/lists for easy use in Streamlit + Pydantic.
"""

from __future__ import annotations

import json
import os
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from dotenv import load_dotenv

load_dotenv()

# ============================================================
# DEMO MODE (in-memory, no DB required)
# ============================================================
_DEMO_MODE = False
_DEMO_CLIENTS: list[dict] = []
_DEMO_COMMS: list[dict] = []
_DEMO_SALES: list[dict] = []
_DEMO_DELIVERIES: list[dict] = []
_DEMO_SYSTEM_LOGS: list[dict] = []
_DEMO_PRODUCTS: list[dict] = []
_DEMO_CLIENT_PRODUCTS: list[dict] = []  # [{"client_id": , "product_id": }, ...]
_DEMO_JSON_TEMPLATES: list[dict] = []
_DEMO_CLIENT_JSON_SENDS: list[dict] = []


def is_demo_mode() -> bool:
    return _DEMO_MODE


def enable_demo_mode(seed_clients: list[dict] | None = None):
    global _DEMO_MODE, _DEMO_CLIENTS, _DEMO_COMMS, _DEMO_SALES, _DEMO_DELIVERIES, _DEMO_SYSTEM_LOGS
    _DEMO_MODE = True
    if seed_clients:
        _DEMO_CLIENTS = deepcopy(seed_clients)
    elif not _DEMO_CLIENTS:
        try:
            from utils import get_demo_seed_data
            _DEMO_CLIENTS = deepcopy(get_demo_seed_data())
        except Exception:
            _DEMO_CLIENTS = []
    _DEMO_COMMS = [
        {"client_id": 1, "log_date": "2025-01-15", "event": "Initial contact and contract discussion for API integration"},
        {"client_id": 1, "log_date": "2025-02-20", "event": "Follow-up meeting - signed API integration contract"},
        {"client_id": 2, "log_date": "2025-03-10", "event": "Demo of product catalog sync"},
    ]
    _DEMO_SALES = [
        {"client_id": 1, "sale_date": "2025-04-05", "description": "Sold out 30 decks", "quantity": 30, "amount": 15000.00},
        {"client_id": 2, "sale_date": "2025-05-12", "description": "Sold out 50 decks", "quantity": 50, "amount": 25000.00},
    ]
    _DEMO_DELIVERIES = [
        {"client_id": 1, "country": "United States", "address_count": 25, "delivered_date": "2025-04-10"},
        {"client_id": 1, "country": "Canada", "address_count": 12, "delivered_date": "2025-04-15"},
        {"client_id": 2, "country": "United Kingdom", "address_count": 40, "delivered_date": "2025-05-20"},
        {"client_id": 2, "country": "Germany", "address_count": 35, "delivered_date": "2025-05-25"},
        {"client_id": 3, "country": "Australia", "address_count": 15, "delivered_date": "2025-06-01"},
    ]
    _DEMO_SYSTEM_LOGS = [
        {"log_timestamp": "2025-06-25T10:30:00", "message": "customer Acme Corp required json file", "tags": ["api", "integration"], "client_name": "Acme Corp", "industry": "Technology"},
        {"log_timestamp": "2025-07-30T14:15:00", "message": "customer Global Retail Ltd joined us", "tags": ["onboarding"], "client_name": "Global Retail Ltd", "industry": "Retail"},
        {"log_timestamp": "2025-08-31T09:00:00", "message": "Customer HealthFirst Inc sold 25 unit", "tags": ["sales"], "client_name": "HealthFirst Inc", "industry": "Healthcare"},
    ]
    # Ensure demo clients have web_store_url for the new feature
    for c in _DEMO_CLIENTS:
        if "web_store_url" not in c:
            c["web_store_url"] = None
        if "notes" not in c:
            c["notes"] = None
        # backfill api flags if missing for demo
        for fl in ("api_pdf", "json_file", "product_specs"):
            if fl not in c:
                c[fl] = False

    # Seed demo products, junctions, some json sends for UI testing (Products/JSON tabs, profile assigns, slicers etc)
    global _DEMO_PRODUCTS, _DEMO_CLIENT_PRODUCTS, _DEMO_JSON_TEMPLATES, _DEMO_CLIENT_JSON_SENDS
    if not _DEMO_PRODUCTS:
        _DEMO_PRODUCTS = [
            {"id": 1, "name": "Booster Pack", "category": "Packaging", "specs": json.dumps(["20X20X20"])},
            {"id": 2, "name": "Sensor Module", "category": "Electronics", "specs": json.dumps(["v1", "v2"])},
            {"id": 3, "name": "Custom API Kit", "category": "Integration", "specs": json.dumps(["basic", "advanced"])},
        ]
    if not _DEMO_CLIENT_PRODUCTS:
        _DEMO_CLIENT_PRODUCTS = [
            {"client_id": 1, "product_id": 1},
            {"client_id": 1, "product_id": 3},
            {"client_id": 2, "product_id": 2},
            {"client_id": 3, "product_id": 1},
        ]
    if not _DEMO_JSON_TEMPLATES:
        _DEMO_JSON_TEMPLATES = [
            {"id": 1, "name": "Booster_Pack_20X20X20.json", "file_path": "DEMO:Booster_Pack_20X20X20.json"},
        ]
    if not _DEMO_CLIENT_JSON_SENDS:
        _DEMO_CLIENT_JSON_SENDS = [
            {"id": 1, "client_id": 1, "json_template_id": 1, "sent_date": "2025-06-10", "product": "Booster Pack", "product_specs": ["20X20X20"]},
        ]

    # Ensure sales have optional product for slicers/product pick in sales logs
    for s in _DEMO_SALES:
        if "product" not in s:
            # seed some variety
            if s.get("client_id") == 1:
                s["product"] = "Booster Pack"
            elif s.get("client_id") == 2:
                s["product"] = "Sensor Module"
            else:
                s["product"] = None


def clear_and_seed_test_data():
    """
    Destructive clear + rich test seed.
    See implementation comments in previous edit for details. Creates data for:
    - flat product table with repeated products + single clients
    - sales with 'product' for slicer + profile picker
    - many countries in deliveries
    - pretty renamed JSON files on disk + db entries
    """
    global _DEMO_CLIENTS, _DEMO_COMMS, _DEMO_SALES, _DEMO_DELIVERIES, _DEMO_SYSTEM_LOGS
    global _DEMO_PRODUCTS, _DEMO_CLIENT_PRODUCTS, _DEMO_JSON_TEMPLATES, _DEMO_CLIENT_JSON_SENDS

    # Compute upload dir locally so we don't depend on module-level timing / partial imports
    UPLOAD_DIR = os.path.join("uploads", "json_files")
    # Compute upload dir locally (safe even if module load was partial)
    _upload_dir = os.path.join("uploads", "json_files")
    os.makedirs(_upload_dir, exist_ok=True)

    sample_json_bytes = json.dumps({"api_version": "2.1", "features": ["auth", "catalog_sync"], "demo": True}, indent=2).encode("utf-8")

    if _DEMO_MODE:
        _DEMO_CLIENTS = []
        _DEMO_COMMS = []
        _DEMO_SALES = []
        _DEMO_DELIVERIES = []
        _DEMO_SYSTEM_LOGS = []
        _DEMO_PRODUCTS = []
        _DEMO_CLIENT_PRODUCTS = []
        _DEMO_JSON_TEMPLATES = []
        _DEMO_CLIENT_JSON_SENDS = []

        _DEMO_CLIENTS = [
            {"id": 1, "name": "Acme Corp", "email": "contact@acme.com", "industry": "Technology", "web_store_url": "https://acme.example.com/store", "notes": "Key account - prefers JSON", "api_pdf": True, "json_file": True, "product_specs": True, "total_orders": 0, "total_addresses_delivered": 0, "total_order_amount": 0.0},
            {"id": 2, "name": "Global Retail Ltd", "email": "info@globalretail.com", "industry": "Retail", "web_store_url": "https://globalretail.example.com/shop", "notes": "High volume packaging", "api_pdf": False, "json_file": True, "product_specs": True, "total_orders": 0, "total_addresses_delivered": 0, "total_order_amount": 0.0},
            {"id": 3, "name": "HealthFirst Inc", "email": "hello@healthfirst.com", "industry": "Healthcare", "web_store_url": None, "notes": "Compliance focused", "api_pdf": True, "json_file": False, "product_specs": True, "total_orders": 0, "total_addresses_delivered": 0, "total_order_amount": 0.0},
            {"id": 4, "name": "Nordic Manufacturing", "email": "sales@nordic-mfg.no", "industry": "Manufacturing", "web_store_url": "https://nordic-mfg.example.com", "notes": "", "api_pdf": True, "json_file": True, "product_specs": False, "total_orders": 0, "total_addresses_delivered": 0, "total_order_amount": 0.0},
            {"id": 5, "name": "Pacific Logistics", "email": "ops@pacific-logistics.au", "industry": "Logistics", "web_store_url": None, "notes": "New - testing packs", "api_pdf": False, "json_file": True, "product_specs": True, "total_orders": 0, "total_addresses_delivered": 0, "total_order_amount": 0.0},
        ]

        _DEMO_PRODUCTS = [
            {"id": 1, "name": "Booster Pack", "category": "Packaging", "specs": json.dumps(["20X20X20", "30X30X30"])},
            {"id": 2, "name": "Sensor Module", "category": "Electronics", "specs": json.dumps(["v1", "v2", "v2.1"])},
            {"id": 3, "name": "Custom API Kit", "category": "Integration", "specs": json.dumps(["basic", "advanced", "enterprise"])},
            {"id": 4, "name": "Label Stock 100mm", "category": "Consumables", "specs": json.dumps(["white", "clear", "thermal"])},
        ]

        _DEMO_CLIENT_PRODUCTS = [
            {"client_id": 1, "product_id": 1}, {"client_id": 1, "product_id": 3},
            {"client_id": 2, "product_id": 1}, {"client_id": 2, "product_id": 4},
            {"client_id": 3, "product_id": 2}, {"client_id": 3, "product_id": 1},
            {"client_id": 4, "product_id": 3}, {"client_id": 4, "product_id": 2},
            {"client_id": 5, "product_id": 1}, {"client_id": 5, "product_id": 4},
        ]

        for cid, ctry, cnt, dt in [
            (1,"United States",12,"2025-03-01"), (1,"Canada",8,"2025-03-05"), (1,"Germany",5,"2025-04-10"),
            (2,"United Kingdom",25,"2025-02-15"), (2,"Germany",15,"2025-03-20"), (2,"Taiwan",10,"2025-05-01"),
            (3,"Australia",7,"2025-04-02"), (3,"Japan",4,"2025-05-12"),
            (4,"France",9,"2025-03-25"), (4,"United States",6,"2025-06-01"),
            (5,"Taiwan",18,"2025-05-20"), (5,"Australia",11,"2025-06-05"),
        ]:
            _DEMO_DELIVERIES.append({"client_id": cid, "country": ctry, "address_count": cnt, "delivered_date": dt})

        for cid, dt, desc, qty, amt, prod in [
            (1,"2025-03-10","Sold 40 units of primary pack",40,18500.0,"Booster Pack"),
            (1,"2025-04-22","Enterprise integration order",12,7200.0,"Custom API Kit"),
            (2,"2025-02-28","Monthly packaging replenishment",60,14200.0,"Booster Pack"),
            (2,"2025-05-05","Label stock for new line",200,9500.0,"Label Stock 100mm"),
            (3,"2025-03-15","Sensor hardware + firmware bundle",25,31250.0,"Sensor Module"),
            (3,"2025-05-28","Booster packs for pilot sites",30,13900.0,"Booster Pack"),
            (4,"2025-04-05","Full API rollout kits",8,9800.0,"Custom API Kit"),
            (4,"2025-06-02","Advanced sensors",15,18750.0,"Sensor Module"),
            (5,"2025-05-15","Initial Booster Pack order",55,25300.0,"Booster Pack"),
            (5,"2025-06-10","Label + packaging combo",120,7800.0,"Label Stock 100mm"),
        ]:
            _DEMO_SALES.append({"client_id": cid, "sale_date": dt, "description": desc, "quantity": qty, "amount": amt, "product": prod})

        # Write pretty files for dl in demo
        for nm in ["Booster_Pack_20X20X20.json", "Sensor_Module_v1_v2.json"]:
            try:
                with open(os.path.join(_upload_dir, nm), "wb") as f: f.write(sample_json_bytes)
            except: pass

        _DEMO_JSON_TEMPLATES = [
            {"id": 1, "name": "Booster_Pack_20X20X20.json", "file_path": os.path.join(_upload_dir, "Booster_Pack_20X20X20.json")},
            {"id": 2, "name": "Sensor_Module_v1_v2.json", "file_path": os.path.join(_upload_dir, "Sensor_Module_v1_v2.json")},
        ]
        _DEMO_CLIENT_JSON_SENDS = [
            {"id": 1, "client_id": 1, "json_template_id": 1, "sent_date": "2025-06-01", "product": "Booster Pack", "product_specs": ["20X20X20"]},
            {"id": 2, "client_id": 3, "json_template_id": 2, "sent_date": "2025-06-03", "product": "Sensor Module", "product_specs": ["v1","v2"]},
        ]

        _DEMO_COMMS = [{"client_id":1,"log_date":"2025-02-10","event":"Kickoff - API contract"}, {"client_id":5,"log_date":"2025-05-10","event":"Onboarding - requested JSON"}]
        _DEMO_SYSTEM_LOGS = [{"log_timestamp":"2025-06-01T09:15:00","message":"Test seed: JSON + sales with products loaded","tags":["seed"],"client_name":None,"industry":None}]

        for c in _DEMO_CLIENTS:
            _recompute_demo_client_totals(c["id"])
        return

    # Real MySQL
    for tbl in ("client_json_sends","product_json_files","client_products","sales_records","deliveries","communication_logs","system_logs","json_templates","products","clients"):
        try:
            _execute(f"DELETE FROM {tbl}")
        except: pass

    try: ensure_new_feature_tables()
    except: pass

    # clients
    cids = {}
    for idx, (nm, em, ind, url, ap, jf, ps, nt) in enumerate([
        ("Acme Corp","contact@acme.com","Technology","https://acme.example.com/store",True,True,True,"Key account"),
        ("Global Retail Ltd","info@globalretail.com","Retail","https://globalretail.example.com/shop",False,True,True,"High volume"),
        ("HealthFirst Inc","hello@healthfirst.com","Healthcare",None,True,False,True,"Compliance"),
        ("Nordic Manufacturing","sales@nordic-mfg.no","Manufacturing","https://nordic-mfg.example.com",True,True,False,""),
        ("Pacific Logistics","ops@pacific-logistics.au","Logistics",None,False,True,True,"New onboarding"),
    ],1):
        cids[idx] = insert_client({"name":nm,"email":em,"industry":ind,"web_store_url":url,"api_pdf":ap,"json_file":jf,"product_specs":ps,"notes":nt,"total_orders":0,"total_addresses_delivered":0,"total_order_amount":0.0})

    # products
    pids = {}
    for idx, (nm, cat, sp) in enumerate([
        ("Booster Pack","Packaging",["20X20X20","30X30X30"]),
        ("Sensor Module","Electronics",["v1","v2","v2.1"]),
        ("Custom API Kit","Integration",["basic","advanced","enterprise"]),
        ("Label Stock 100mm","Consumables",["white","clear","thermal"]),
    ],1):
        pids[idx] = create_product(nm, cat, sp)

    # junctions (overlap)
    for cnum, plist in [(1,[1,3]),(2,[1,4]),(3,[2,1]),(4,[3,2]),(5,[1,4])]:
        set_client_products(cids[cnum], [pids[p] for p in plist])

    # deliveries (many countries)
    for cnum, ctry, cnt, dt in [(1,"United States",12,"2025-03-01"),(1,"Canada",8,"2025-03-05"),(1,"Germany",5,"2025-04-10"),
        (2,"United Kingdom",25,"2025-02-15"),(2,"Germany",15,"2025-03-20"),(2,"Taiwan",10,"2025-05-01"),
        (3,"Australia",7,"2025-04-02"),(3,"Japan",4,"2025-05-12"),
        (4,"France",9,"2025-03-25"),(4,"United States",6,"2025-06-01"),
        (5,"Taiwan",18,"2025-05-20"),(5,"Australia",11,"2025-06-05")]:
        add_delivery(cids[cnum], ctry, cnt, dt)

    # sales with product
    for cnum, dt, desc, qty, amt, prod in [(1,"2025-03-10","Sold 40 units of primary pack",40,18500.0,"Booster Pack"),
        (1,"2025-04-22","Enterprise integration order",12,7200.0,"Custom API Kit"),
        (2,"2025-02-28","Monthly packaging replenishment",60,14200.0,"Booster Pack"),
        (2,"2025-05-05","Label stock for new line",200,9500.0,"Label Stock 100mm"),
        (3,"2025-03-15","Sensor hardware + firmware bundle",25,31250.0,"Sensor Module"),
        (3,"2025-05-28","Booster packs for pilot sites",30,13900.0,"Booster Pack"),
        (4,"2025-04-05","Full API rollout kits",8,9800.0,"Custom API Kit"),
        (4,"2025-06-02","Advanced sensors",15,18750.0,"Sensor Module"),
        (5,"2025-05-15","Initial Booster Pack order",55,25300.0,"Booster Pack"),
        (5,"2025-06-10","Label + packaging combo",120,7800.0,"Label Stock 100mm")]:
        add_sales_record(cids[cnum], dt, desc, qty, amt, prod)

    # pretty json files + db records
    for pretty, (pname, specs) in [("Booster_Pack_20X20X20.json", ("Booster Pack", ["20X20X20"])), ("Sensor_Module_v1_v2.json", ("Sensor Module", ["v1","v2"]))]:
        fpath = os.path.join(_upload_dir, pretty)
        try:
            with open(fpath, "wb") as f: f.write(sample_json_bytes)
        except: pass
        try:
            tid = _execute("INSERT INTO json_templates (name, file_path) VALUES (%s,%s)", (pretty, fpath))
            target_c = cids[1] if "Booster" in pname else cids[3]
            _execute("INSERT INTO client_json_sends (client_id, json_template_id, sent_date, product, product_specs) VALUES (%s,%s,%s,%s,%s)",
                     (target_c, tid, "2025-06-05", pname, json.dumps(specs)))
            prow = _query("SELECT id FROM products WHERE name=%s", (pname,), fetch="one")
            if prow:
                _execute("INSERT IGNORE INTO product_json_files (product_id, specs, json_template_id) VALUES (%s,%s,%s)", (prow["id"], json.dumps(specs), tid))
        except: pass

    # comms + totals
    try:
        add_communication_log(cids[1], "2025-02-10", "Kickoff call - API integration contract")
        add_communication_log(cids[5], "2025-05-10", "New customer onboarding - requested JSON template")
    except: pass

    for cid in cids.values():
        try: update_client_totals(cid)
        except: pass

    try: add_system_log("Fresh test data seed completed (products, sales-with-product, multi-country deliveries, renamed JSONs)", ["seed","test"])
    except: pass


def reset_demo_data():
    global _DEMO_CLIENTS, _DEMO_COMMS, _DEMO_SALES, _DEMO_DELIVERIES, _DEMO_SYSTEM_LOGS
    if _DEMO_MODE:
        try:
            from utils import get_demo_seed_data
            _DEMO_CLIENTS = deepcopy(get_demo_seed_data())
        except Exception:
            _DEMO_CLIENTS = []
        # Re-seed related sample data to match init_mysql_schema.sql
        _DEMO_COMMS = [
            {"client_id": 1, "log_date": "2025-01-15", "event": "Initial contact and contract discussion for API integration"},
            {"client_id": 1, "log_date": "2025-02-20", "event": "Follow-up meeting - signed API integration contract"},
            {"client_id": 2, "log_date": "2025-03-10", "event": "Demo of product catalog sync"},
        ]
        _DEMO_SALES = [
            {"client_id": 1, "sale_date": "2025-04-05", "description": "Sold out 30 decks", "quantity": 30, "amount": 15000.00},
            {"client_id": 2, "sale_date": "2025-05-12", "description": "Sold out 50 decks", "quantity": 50, "amount": 25000.00},
        ]
        _DEMO_DELIVERIES = [
            {"client_id": 1, "country": "United States", "address_count": 25, "delivered_date": "2025-04-10"},
            {"client_id": 1, "country": "Canada", "address_count": 12, "delivered_date": "2025-04-15"},
            {"client_id": 2, "country": "United Kingdom", "address_count": 40, "delivered_date": "2025-05-20"},
            {"client_id": 2, "country": "Germany", "address_count": 35, "delivered_date": "2025-05-25"},
            {"client_id": 3, "country": "Australia", "address_count": 15, "delivered_date": "2025-06-01"},
        ]
        _DEMO_SYSTEM_LOGS = [
            {"log_timestamp": "2025-06-25T10:30:00", "message": "customer Acme Corp required json file", "tags": ["api", "integration"], "client_name": "Acme Corp", "industry": "Technology"},
            {"log_timestamp": "2025-07-30T14:15:00", "message": "customer Global Retail Ltd joined us", "tags": ["onboarding"], "client_name": "Global Retail Ltd", "industry": "Retail"},
            {"log_timestamp": "2025-08-31T09:00:00", "message": "Customer HealthFirst Inc sold 25 unit", "tags": ["sales"], "client_name": "HealthFirst Inc", "industry": "Healthcare"},
        ]
    # Patch web_store_url + notes + api flags + full demo products for reset
    for c in _DEMO_CLIENTS:
        if "web_store_url" not in c:
            c["web_store_url"] = None
        if "notes" not in c:
            c["notes"] = None
        for fl in ("api_pdf", "json_file", "product_specs"):
            if fl not in c:
                c[fl] = False

    global _DEMO_PRODUCTS, _DEMO_CLIENT_PRODUCTS, _DEMO_JSON_TEMPLATES, _DEMO_CLIENT_JSON_SENDS
    _DEMO_PRODUCTS = [
        {"id": 1, "name": "Booster Pack", "category": "Packaging", "specs": json.dumps(["20X20X20"])},
        {"id": 2, "name": "Sensor Module", "category": "Electronics", "specs": json.dumps(["v1", "v2"])},
        {"id": 3, "name": "Custom API Kit", "category": "Integration", "specs": json.dumps(["basic", "advanced"])},
    ]
    _DEMO_CLIENT_PRODUCTS = [
        {"client_id": 1, "product_id": 1},
        {"client_id": 1, "product_id": 3},
        {"client_id": 2, "product_id": 2},
        {"client_id": 3, "product_id": 1},
    ]
    _DEMO_JSON_TEMPLATES = [
        {"id": 1, "name": "Booster_Pack_20X20X20.json", "file_path": "DEMO:Booster_Pack_20X20X20.json"},
    ]
    _DEMO_CLIENT_JSON_SENDS = [
        {"id": 1, "client_id": 1, "json_template_id": 1, "sent_date": "2025-06-10", "product": "Booster Pack", "product_specs": ["20X20X20"]},
    ]
    for s in _DEMO_SALES:
        if "product" not in s:
            if s.get("client_id") == 1:
                s["product"] = "Booster Pack"
            elif s.get("client_id") == 2:
                s["product"] = "Sensor Module"
            else:
                s["product"] = None


# ============================================================
# MySQL Connection Helpers
# ============================================================

def get_connection():
    if _DEMO_MODE:
        raise RuntimeError("DEMO MODE active — MySQL is disabled. Use real data or turn off USE_SAMPLE_DATA.")
    try:
        import pymysql
        from pymysql.cursors import DictCursor
    except ImportError:
        # Auto-fallback so that even direct calls don't hard-crash the app
        enable_demo_mode()
        raise RuntimeError(
            "pymysql is not installed. Auto-switched to DEMO mode for this session. "
            "To use real MySQL: pip install pymysql cryptography , set USE_SAMPLE_DATA=false in .env, "
            "configure MYSQL_* , and run sql/init_mysql_schema.sql against your database."
        )
    return pymysql.connect(
        host=os.getenv("MYSQL_HOST", "localhost"),
        port=int(os.getenv("MYSQL_PORT", 3306)),
        user=os.getenv("MYSQL_USER", "root"),
        password=os.getenv("MYSQL_PASSWORD", ""),
        database=os.getenv("MYSQL_DATABASE", "client_profile_db"),
        charset="utf8mb4",
        cursorclass=DictCursor,
        autocommit=True,
    )


def _query(sql: str, params: tuple = (), fetch: str = "all"):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            if fetch == "one":
                return cur.fetchone()
            if fetch == "all":
                return cur.fetchall()
            return None
    finally:
        conn.close()


def _execute(sql: str, params: tuple = ()):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.lastrowid
    finally:
        conn.close()


# ============================================================
# CLIENTS
# ============================================================

def fetch_clients() -> list[dict]:
    if _DEMO_MODE:
        return deepcopy(_DEMO_CLIENTS)
    return _query("SELECT * FROM clients ORDER BY updated_at DESC") or []


def insert_client(data: dict) -> int:
    if _DEMO_MODE:
        new_id = max([c.get("id", 0) for c in _DEMO_CLIENTS], default=0) + 1
        rec = {
            "id": new_id,
            "name": data.get("name"),
            "email": data.get("email"),
            "industry": data.get("industry"),
            "web_store_url": data.get("web_store_url"),
            "total_orders": data.get("total_orders", 0),
            "total_addresses_delivered": data.get("total_addresses_delivered", 0),
            "total_order_amount": data.get("total_order_amount", 0),
            "notes": data.get("notes"),
            "api_pdf": bool(data.get("api_pdf", False)),
            "json_file": bool(data.get("json_file", False)),
            "product_specs": bool(data.get("product_specs", False)),
        }
        _DEMO_CLIENTS.append(rec)
        # Auto system log
        try:
            message = f"New client added: {data.get('name')} (industry: {data.get('industry') or '—'})"
            add_system_log(message, ["client", "onboarding"])
        except Exception:
            pass
        return new_id

    new_id = _execute(
        """INSERT INTO clients (name, email, industry, web_store_url, api_pdf, json_file, product_specs,
                                total_orders, total_addresses_delivered, total_order_amount, notes)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
        (
            data.get("name"),
            data.get("email"),
            data.get("industry"),
            data.get("web_store_url"),
            bool(data.get("api_pdf", False)),
            bool(data.get("json_file", False)),
            bool(data.get("product_specs", False)),
            data.get("total_orders", 0),
            data.get("total_addresses_delivered", 0),
            data.get("total_order_amount", 0),
            data.get("notes"),
        )
    )
    # Auto system log
    try:
        message = f"New client added: {data.get('name')} (industry: {data.get('industry') or '—'})"
        add_system_log(message, ["client", "onboarding"])
    except Exception:
        pass
    return new_id


def fetch_client(client_id: int) -> dict | None:
    """Fetch single client by id (supports new schema and demo mode)."""
    if _DEMO_MODE:
        for c in _DEMO_CLIENTS:
            if c.get("id") == client_id:
                return deepcopy(c)
        return None
    row = _query("SELECT * FROM clients WHERE id = %s", (client_id,), fetch="one")
    return dict(row) if row else None


def update_client(client_id_or_email, payload: dict) -> None:
    """Update basic client fields (name, email, industry, web_store_url). Supports id primarily.
    Demo mode updates in-memory + keeps web_store_url. Real MySQL uses id.
    """
    if _DEMO_MODE:
        for c in _DEMO_CLIENTS:
            match = False
            if isinstance(client_id_or_email, int) and c.get("id") == client_id_or_email:
                match = True
            elif isinstance(client_id_or_email, str) and (c.get("email") or "").lower() == str(client_id_or_email).lower():
                match = True
            if match:
                for k, v in payload.items():
                    if k in ("id",):
                        continue
                    c[k] = v
                return
        return

    # Real MySQL path: prefer id, support the new fields
    if isinstance(client_id_or_email, int):
        sets = []
        params = []
        allowed = ("name", "email", "industry", "web_store_url", "api_pdf", "json_file", "product_specs", "notes")
        for k in allowed:
            if k in payload:
                sets.append(f"{k}=%s")
                val = payload[k]
                if k in ("api_pdf", "json_file", "product_specs"):
                    val = bool(val)
                params.append(val)
        if sets:
            params.append(client_id_or_email)
            _execute(f"UPDATE clients SET {', '.join(sets)}, updated_at=NOW() WHERE id=%s", tuple(params))
    else:
        # legacy email fallback (best effort)
        sets = []
        params = []
        allowed = ("name", "email", "industry", "web_store_url", "api_pdf", "json_file", "product_specs", "notes")
        for k in allowed:
            if k in payload:
                sets.append(f"{k}=%s")
                val = payload[k]
                if k in ("api_pdf", "json_file", "product_specs"):
                    val = bool(val)
                params.append(val)
        if sets:
            params.append(client_id_or_email)
            _execute(f"UPDATE clients SET {', '.join(sets)}, updated_at=NOW() WHERE email=%s", tuple(params))


def update_client_totals(client_id: int):
    if _DEMO_MODE:
        _recompute_demo_client_totals(client_id)
        return
    _execute("""
        UPDATE clients c SET
            total_orders = (SELECT COALESCE(SUM(quantity),0) FROM sales_records WHERE client_id=c.id),
            total_addresses_delivered = (SELECT COALESCE(SUM(address_count),0) FROM deliveries WHERE client_id=c.id),
            total_order_amount = (SELECT COALESCE(SUM(amount),0) FROM sales_records WHERE client_id=c.id)
        WHERE c.id = %s
    """, (client_id,))


def _recompute_demo_client_totals(client_id: int):
    """Used in DEMO MODE so that after adding sales or deliveries the client's total_* fields update (fixes 'not updating' reports)."""
    if not _DEMO_MODE:
        return
    try:
        sales_sum_qty = 0
        sales_sum_amt = 0.0
        for s in _DEMO_SALES:
            if s.get("client_id") == client_id:
                q = s.get("quantity") or 0
                a = s.get("amount") or 0
                try:
                    sales_sum_qty += int(q)
                    sales_sum_amt += float(a)
                except Exception:
                    pass
        addr_sum = 0
        for d in _DEMO_DELIVERIES:
            if d.get("client_id") == client_id:
                try:
                    addr_sum += int(d.get("address_count") or 0)
                except Exception:
                    pass
        for c in _DEMO_CLIENTS:
            if c.get("id") == client_id:
                c["total_orders"] = sales_sum_qty
                c["total_addresses_delivered"] = addr_sum
                c["total_order_amount"] = round(sales_sum_amt, 2)
                break
    except Exception:
        pass


# ============================================================
# COMMUNICATION LOGS
# ============================================================

def add_communication_log(client_id: int, log_date: str, event: str):
    if _DEMO_MODE:
        _DEMO_COMMS.append({"client_id": client_id, "log_date": log_date, "event": event})
    else:
        _execute("INSERT INTO communication_logs (client_id, log_date, event) VALUES (%s,%s,%s)",
                 (client_id, log_date, event))

    # Automatically create a system log entry so it appears in the homepage query tool
    try:
        client = fetch_client(client_id) or {}
        client_name = client.get("name") or f"Client #{client_id}"
        industry = client.get("industry")
        message = f"Communication log added for {client_name}: {event} (on {log_date})"
        add_system_log(message, ["communication"], client_name=client_name, industry=industry)
    except Exception:
        pass  # do not break the primary add operation if system log fails


def get_communication_logs(client_id: int) -> list[dict]:
    if _DEMO_MODE:
        return [x for x in _DEMO_COMMS if x.get("client_id") == client_id]
    return _query("SELECT * FROM communication_logs WHERE client_id=%s ORDER BY log_date DESC", (client_id,)) or []


# ============================================================
# SALES RECORDS
# ============================================================

def add_sales_record(client_id: int, sale_date: str, description: str, quantity: int, amount: float, product: str | None = None):
    """Add a sales record. 6th positional or keyword arg `product` is optional (for profile sales picker + homepage product slicer on Dashboard).
    This signature must be 6 args. If you see 'takes 5 positional' error, fully restart streamlit (and delete __pycache__).
    """
    if _DEMO_MODE:
        _DEMO_SALES.append({"client_id": client_id, "sale_date": sale_date, "description": description, "quantity": quantity, "amount": amount, "product": product})
        update_client_totals(client_id)  # ensure client totals refresh in demo
    else:
        try:
            _execute(
                "INSERT INTO sales_records (client_id, sale_date, description, quantity, amount, product) VALUES (%s,%s,%s,%s,%s,%s)",
                (client_id, sale_date, description, quantity, amount, product)
            )
        except Exception as e:
            # If the 'product' column doesn't exist yet (ensure_new_feature_tables not run or old schema),
            # fall back to inserting without it and embed the info in description.
            if "unknown column" in str(e).lower() or "1146" in str(e) or "no such column" in str(e).lower():
                if product:
                    description = (description or "Sale") + f" [product: {product}]"
                _execute(
                    "INSERT INTO sales_records (client_id, sale_date, description, quantity, amount) VALUES (%s,%s,%s,%s,%s)",
                    (client_id, sale_date, description, quantity, amount)
                )
            else:
                raise
        update_client_totals(client_id)

    # Automatically create a system log entry so it appears in the homepage query tool
    try:
        client = fetch_client(client_id) or {}
        client_name = client.get("name") or f"Client #{client_id}"
        industry = client.get("industry")
        prod_part = f" [{product}]" if product else ""
        message = f"Sale recorded for {client_name}: {description} — {quantity} units (${amount}) on {sale_date}{prod_part}"
        add_system_log(message, ["sales"], client_name=client_name, industry=industry)
    except Exception:
        pass  # do not break the primary add operation if system log fails


def get_sales_records(client_id: int) -> list[dict]:
    if _DEMO_MODE:
        return [deepcopy(x) for x in _DEMO_SALES if x.get("client_id") == client_id]
    return _query("SELECT * FROM sales_records WHERE client_id=%s ORDER BY sale_date DESC", (client_id,)) or []


# ============================================================
# DELIVERIES (Dispatching Countries for World Map)
# ============================================================

def add_delivery(client_id: int, country: str, address_count: int, delivered_date: str | None = None):
    if _DEMO_MODE:
        _DEMO_DELIVERIES.append({"client_id": client_id, "country": country, "address_count": address_count, "delivered_date": delivered_date})
        update_client_totals(client_id)  # ensure client totals refresh in demo (addresses delivered)
    else:
        _execute(
            "INSERT INTO deliveries (client_id, country, address_count, delivered_date) VALUES (%s,%s,%s,%s)",
            (client_id, country, address_count, delivered_date)
        )
        update_client_totals(client_id)

    # Auto system log
    try:
        client = fetch_client(client_id) or {}
        client_name = client.get("name") or f"Client #{client_id}"
        industry = client.get("industry")
        date_str = delivered_date or "—"
        message = f"Delivery recorded for {client_name}: {address_count} addresses to {country} on {date_str}"
        add_system_log(message, ["delivery"], client_name=client_name, industry=industry)
    except Exception:
        pass  # do not break the primary operation


def get_deliveries(client_id: int) -> list[dict]:
    if _DEMO_MODE:
        return [x for x in _DEMO_DELIVERIES if x.get("client_id") == client_id]
    return _query("SELECT * FROM deliveries WHERE client_id=%s", (client_id,)) or []


def get_country_dispatch_data() -> list[dict]:
    """Global dispatching countries (for reference only)."""
    if _DEMO_MODE:
        from collections import defaultdict
        agg = defaultdict(int)
        for d in _DEMO_DELIVERIES:
            try:
                cnt = int(d.get("address_count") or 0)
            except (ValueError, TypeError):
                cnt = 0
            agg[d.get("country", "Unknown")] += cnt
        return [{"country": k, "total_addresses": v} for k, v in sorted(agg.items(), key=lambda x: -x[1])]

    return _query("""
        SELECT country, SUM(address_count) as total_addresses
        FROM deliveries GROUP BY country ORDER BY total_addresses DESC
    """) or []


def get_client_dispatch_data(client_id: int) -> list[dict]:
    """Dispatching countries for ONE specific client (unique map per profile)."""
    if _DEMO_MODE:
        from collections import defaultdict
        agg = defaultdict(int)
        for d in _DEMO_DELIVERIES:
            if d.get("client_id") == client_id:
                try:
                    cnt = int(d.get("address_count") or 0)
                except (ValueError, TypeError):
                    cnt = 0
                agg[d.get("country", "Unknown")] += cnt
        return [{"country": k, "total_addresses": v} for k, v in sorted(agg.items(), key=lambda x: -x[1])]

    return _query("""
        SELECT country, SUM(address_count) as total_addresses
        FROM deliveries 
        WHERE client_id = %s
        GROUP BY country 
        ORDER BY total_addresses DESC
    """, (client_id,)) or []


# ============================================================
# SYSTEM LOGS (Homepage Query Tool)
# ============================================================

def add_system_log(message: str, tags: list[str] | None = None,
                   client_name: str | None = None, industry: str | None = None):
    tags_json = json.dumps(tags) if tags else None
    if _DEMO_MODE:
        _DEMO_SYSTEM_LOGS.append({
            "log_timestamp": datetime.now().isoformat(),
            "message": message,
            "tags": tags or [],
            "client_name": client_name,
            "industry": industry
        })
        return
    _execute(
        "INSERT INTO system_logs (log_timestamp, message, tags, client_name, industry) VALUES (NOW(), %s, %s, %s, %s)",
        (message, tags_json, client_name, industry)
    )


def query_system_logs(
    start_date: str | None = None,
    end_date: str | None = None,
    industry: str | None = None,
    tag: str | None = None,
    search_text: str | None = None,
    limit: int = 500
) -> list[dict]:
    """Powerful filterable log query + CSV export ready."""
    if _DEMO_MODE:
        res = []
        for log in _DEMO_SYSTEM_LOGS:
            ts = str(log.get("log_timestamp", ""))
            if start_date and ts < start_date: continue
            if end_date and ts > end_date: continue
            if industry and log.get("industry") != industry: continue
            if tag and tag not in (log.get("tags") or []): continue
            if search_text and search_text.lower() not in str(log.get("message", "")).lower(): continue
            res.append(log)
        return sorted(res, key=lambda x: x.get("log_timestamp", ""), reverse=True)[:limit]

    sql = "SELECT * FROM system_logs WHERE 1=1"
    params = []

    if start_date:
        sql += " AND log_timestamp >= %s"; params.append(start_date)
    if end_date:
        sql += " AND log_timestamp <= %s"; params.append(end_date)
    if industry:
        sql += " AND industry = %s"; params.append(industry)
    if tag:
        sql += " AND JSON_CONTAINS(tags, %s)"; params.append(json.dumps(tag))
    if search_text:
        sql += " AND message LIKE %s"; params.append(f"%{search_text}%")

    sql += " ORDER BY log_timestamp DESC LIMIT %s"
    params.append(limit)

    rows = _query(sql, tuple(params), fetch="all") or []
    for r in rows:
        if r.get("tags"):
            try:
                r["tags"] = json.loads(r["tags"])
            except:
                r["tags"] = []
    return rows


# Convenience
def get_all_clients_safe():
    try:
        if not _DEMO_MODE:
            ensure_new_feature_tables()
        return fetch_clients(), None
    except Exception as e:
        return [], str(e)


def ensure_new_feature_tables():
    """Idempotently create the tables and columns needed for the new features (Products, JSON Templates, API kit flags).
    Safe to call multiple times. Only runs in real DB mode.
    """
    if _DEMO_MODE:
        return

    # Helper to check if a column exists
    def _column_exists(table: str, column: str) -> bool:
        try:
            row = _query(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_schema = DATABASE() AND table_name = %s AND column_name = %s",
                (table, column),
                fetch="one"
            )
            return row is not None
        except Exception:
            return False

    # 1. Extend clients table with API kit flags (if not present)
    for col in ("api_pdf", "json_file", "product_specs"):
        if not _column_exists("clients", col):
            try:
                _execute(f"ALTER TABLE clients ADD COLUMN {col} BOOLEAN NOT NULL DEFAULT FALSE")
            except Exception:
                pass  # may already exist or other issue

    # Notes free text for client profile
    if not _column_exists("clients", "notes"):
        try:
            _execute("ALTER TABLE clients ADD COLUMN notes TEXT NULL")
        except Exception:
            pass

    # Sales product for pick + homepage product slicer
    if not _column_exists("sales_records", "product"):
        try:
            _execute("ALTER TABLE sales_records ADD COLUMN product VARCHAR(255) NULL")
        except Exception:
            pass

    # 2. Products master
    _execute("""
        CREATE TABLE IF NOT EXISTS products (
            id INT AUTO_INCREMENT PRIMARY KEY,
            name VARCHAR(255) NOT NULL UNIQUE,
            category VARCHAR(255) NULL,
            specs JSON NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
        )
    """)

    # 3. client_products junction
    _execute("""
        CREATE TABLE IF NOT EXISTS client_products (
            client_id INT NOT NULL,
            product_id INT NOT NULL,
            PRIMARY KEY (client_id, product_id),
            FOREIGN KEY (client_id) REFERENCES clients(id) ON DELETE CASCADE,
            FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE
        )
    """)

    # 4. json_templates
    _execute("""
        CREATE TABLE IF NOT EXISTS json_templates (
            id INT AUTO_INCREMENT PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            file_path VARCHAR(500) NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 5. client_json_sends
    _execute("""
        CREATE TABLE IF NOT EXISTS client_json_sends (
            id INT AUTO_INCREMENT PRIMARY KEY,
            client_id INT NOT NULL,
            json_template_id INT NOT NULL,
            sent_date DATE NOT NULL,
            product VARCHAR(255) NULL,
            product_specs JSON NULL,
            FOREIGN KEY (client_id) REFERENCES clients(id) ON DELETE CASCADE,
            FOREIGN KEY (json_template_id) REFERENCES json_templates(id) ON DELETE CASCADE
        )
    """)

    # 6. product_json_files
    _execute("""
        CREATE TABLE IF NOT EXISTS product_json_files (
            id INT AUTO_INCREMENT PRIMARY KEY,
            product_id INT NOT NULL,
            specs JSON NULL,
            json_template_id INT NOT NULL,
            FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE,
            FOREIGN KEY (json_template_id) REFERENCES json_templates(id) ON DELETE CASCADE
        )
    """)

    # Helpful indexes (IF NOT EXISTS not supported in older MySQL for indexes, so ignore errors)
    try:
        _execute("CREATE INDEX idx_clients_api_pdf ON clients(api_pdf)")
    except: pass
    try:
        _execute("CREATE INDEX idx_clients_json_file ON clients(json_file)")
    except: pass
    try:
        _execute("CREATE INDEX idx_clients_product_specs ON clients(product_specs)")
    except: pass
    try:
        _execute("CREATE INDEX idx_products_name ON products(name)")
    except: pass
    try:
        _execute("CREATE INDEX idx_products_category ON products(category)")
    except: pass
    try:
        _execute("CREATE INDEX idx_client_json_sends_client ON client_json_sends(client_id)")
    except: pass
    try:
        _execute("CREATE INDEX idx_client_json_sends_product ON client_json_sends(product)")
    except: pass


# ============================================================
# NEW: File upload directory for JSON templates
# ============================================================
UPLOAD_DIR = os.path.join("uploads", "json_files")
os.makedirs(UPLOAD_DIR, exist_ok=True)


# ============================================================
# NEW FEATURES: Products, Client-Product, API kit flags,
# JSON template uploads/sends, Product JSON files, JSON catalog
# ============================================================

def update_client_api_kit(client_id: int, api_pdf: bool = None, json_file: bool = None, product_specs: bool = None):
    """Update the three API kit boolean flags on a client."""
    if _DEMO_MODE:
        for c in _DEMO_CLIENTS:
            if c.get("id") == client_id:
                if api_pdf is not None:
                    c["api_pdf"] = api_pdf
                if json_file is not None:
                    c["json_file"] = json_file
                if product_specs is not None:
                    c["product_specs"] = product_specs
                return
        return
    sets = []
    params = []
    if api_pdf is not None:
        sets.append("api_pdf = %s")
        params.append(bool(api_pdf))
    if json_file is not None:
        sets.append("json_file = %s")
        params.append(bool(json_file))
    if product_specs is not None:
        sets.append("product_specs = %s")
        params.append(bool(product_specs))
    if sets:
        params.append(client_id)
        _execute(f"UPDATE clients SET {', '.join(sets)} WHERE id = %s", tuple(params))


def get_all_products() -> list[dict]:
    if _DEMO_MODE:
        return deepcopy(_DEMO_PRODUCTS)
    try:
        return _query("SELECT * FROM products ORDER BY name") or []
    except Exception as e:
        if "1146" in str(e) or "doesn't exist" in str(e).lower():
            return []
        raise


def search_products(name: str = None, category: str = None) -> list[dict]:
    if _DEMO_MODE:
        res = deepcopy(_DEMO_PRODUCTS)
        if name:
            ns = name.lower()
            res = [p for p in res if ns in str(p.get("name", "")).lower()]
        if category:
            res = [p for p in res if (p.get("category") or "").lower() == category.lower()]
        return res
    try:
        sql = "SELECT * FROM products WHERE 1=1"
        params = []
        if name:
            sql += " AND name LIKE %s"
            params.append(f"%{name}%")
        if category:
            sql += " AND category = %s"
            params.append(category)
        sql += " ORDER BY name"
        return _query(sql, tuple(params)) or []
    except Exception as e:
        if "1146" in str(e) or "doesn't exist" in str(e).lower():
            return []
        raise


def create_product(name: str, category: str = None, specs: list[str] = None) -> int:
    specs_json = json.dumps(specs) if specs else None
    if _DEMO_MODE:
        new_id = max([p.get("id", 0) for p in _DEMO_PRODUCTS], default=0) + 1
        _DEMO_PRODUCTS.append({
            "id": new_id,
            "name": name,
            "category": category,
            "specs": specs_json
        })
        # Auto system log (also for demo)
        try:
            message = f"New product added: {name} (category: {category or '—'})"
            add_system_log(message, ["product"])
        except Exception:
            pass
        return new_id
    template_id = _execute(
        "INSERT INTO products (name, category, specs) VALUES (%s, %s, %s)",
        (name, category, specs_json)
    )
    # Auto system log
    try:
        message = f"New product added: {name} (category: {category or '—'})"
        add_system_log(message, ["product"])
    except Exception:
        pass
    return template_id


def get_client_products(client_id: int) -> list[dict]:
    if _DEMO_MODE:
        pids = [x["product_id"] for x in _DEMO_CLIENT_PRODUCTS if x.get("client_id") == client_id]
        return [deepcopy(p) for p in _DEMO_PRODUCTS if p.get("id") in pids]
    return _query("""
        SELECT p.* FROM products p
        JOIN client_products cp ON p.id = cp.product_id
        WHERE cp.client_id = %s
        ORDER BY p.name
    """, (client_id,)) or []


def set_client_products(client_id: int, product_ids: list[int]):
    """Replace the products associated with a client."""
    if _DEMO_MODE:
        # remove existing for client
        global _DEMO_CLIENT_PRODUCTS
        _DEMO_CLIENT_PRODUCTS = [x for x in _DEMO_CLIENT_PRODUCTS if x.get("client_id") != client_id]
        for pid in product_ids or []:
            _DEMO_CLIENT_PRODUCTS.append({"client_id": client_id, "product_id": int(pid)})
        return
    _execute("DELETE FROM client_products WHERE client_id = %s", (client_id,))
    for pid in product_ids or []:
        _execute("INSERT INTO client_products (client_id, product_id) VALUES (%s, %s)", (client_id, pid))


def save_client_json_send(client_id: int, uploaded_file, product: str = None, product_specs: list[str] = None) -> int:
    """
    Saves the uploaded JSON file to disk, creates a json_templates entry,
    and records the send in client_json_sends.
    File is renamed based on product + specs e.g. "Booster_Pack_20X20X20.json" (as requested).
    Returns the json_template_id.
    """
    if not uploaded_file:
        return None

    # Derive pretty filename from product + specs (no spaces, joined by _ )
    base = (product or "Template").strip().replace(" ", "_").replace("/", "-").replace("\\", "-")
    spec_part = ""
    if product_specs:
        cleaned = [s.strip().replace(" ", "_").replace("/", "-") for s in product_specs if s and s.strip()]
        if cleaned:
            spec_part = "_" + "_".join(cleaned)
    derived_name = f"{base}{spec_part}.json" if spec_part or base else uploaded_file.name
    # ensure .json suffix
    if not derived_name.lower().endswith(".json"):
        derived_name += ".json"

    if _DEMO_MODE:
        # simulate for demo (no real file written, but history shows; support profile json section + logs)
        global _DEMO_JSON_TEMPLATES, _DEMO_CLIENT_JSON_SENDS
        new_tid = max([t.get("id", 0) for t in _DEMO_JSON_TEMPLATES], default=0) + 1
        _DEMO_JSON_TEMPLATES.append({
            "id": new_tid,
            "name": derived_name,
            "file_path": f"DEMO:{derived_name}"
        })
        new_sid = max([s.get("id", 0) for s in _DEMO_CLIENT_JSON_SENDS], default=0) + 1
        specs_list = product_specs or []
        _DEMO_CLIENT_JSON_SENDS.append({
            "id": new_sid,
            "client_id": client_id,
            "json_template_id": new_tid,
            "sent_date": datetime.now().strftime("%Y-%m-%d"),
            "product": product,
            "product_specs": specs_list
        })
        # Auto system log for upload (also demo)
        try:
            client = fetch_client(client_id) or {}
            client_name = client.get("name") or f"Client #{client_id}"
            specs_str = ", ".join(product_specs) if product_specs else "—"
            message = f"JSON template uploaded for {client_name}: {product or '—'} (specs: {specs_str})"
            add_system_log(message, ["json", "upload", "pdf"], client_name=client_name, industry=client.get("industry"))
        except Exception:
            pass
        return new_tid

    try:
        # Use derived (product+specs) name for stored file + template record
        save_path = os.path.join(UPLOAD_DIR, derived_name)

        with open(save_path, "wb") as f:
            f.write(uploaded_file.getbuffer())

        specs_json = json.dumps(product_specs) if product_specs else None

        # Create master template record with pretty name
        template_id = _execute(
            "INSERT INTO json_templates (name, file_path) VALUES (%s, %s)",
            (derived_name, save_path)
        )

        # Record the send for this client
        _execute(
            "INSERT INTO client_json_sends (client_id, json_template_id, sent_date, product, product_specs) "
            "VALUES (%s, %s, CURDATE(), %s, %s)",
            (client_id, template_id, product, specs_json)
        )

        # Optionally auto-associate to product if we have product name matching
        try:
            if product:
                prod = _query("SELECT id FROM products WHERE name = %s", (product,), fetch="one")
                if prod:
                    _execute(
                        "INSERT IGNORE INTO product_json_files (product_id, specs, json_template_id) "
                        "VALUES (%s, %s, %s)",
                        (prod["id"], specs_json, template_id)
                    )
        except Exception:
            pass

        # Auto system log for upload (JSON / PDF etc.)
        try:
            client = fetch_client(client_id) or {}
            client_name = client.get("name") or f"Client #{client_id}"
            specs_str = ", ".join(product_specs) if product_specs else "—"
            message = f"JSON template uploaded for {client_name}: {product or '—'} (specs: {specs_str})"
            add_system_log(message, ["json", "upload", "pdf"], client_name=client_name, industry=client.get("industry"))
        except Exception:
            pass

        return template_id
    except Exception as e:
        if "1146" in str(e) or "doesn't exist" in str(e).lower():
            return None
        raise


def get_client_sent_jsons(client_id: int) -> list[dict]:
    """Return history of JSONs sent to this client, with file info."""
    if _DEMO_MODE:
        sends = [x for x in _DEMO_CLIENT_JSON_SENDS if x.get("client_id") == client_id]
        res = []
        for s in sends:
            jt = next((t for t in _DEMO_JSON_TEMPLATES if t.get("id") == s.get("json_template_id")), {})
            cl = next((c for c in _DEMO_CLIENTS if c.get("id") == client_id), {})
            specs = s.get("product_specs") or []
            if isinstance(specs, str):
                try:
                    specs = json.loads(specs)
                except:
                    specs = [specs] if specs else []
            res.append({
                "id": s.get("id"),
                "sent_date": s.get("sent_date"),
                "product": s.get("product"),
                "product_specs": specs,
                "template_name": jt.get("name"),
                "file_path": jt.get("file_path"),
                "json_template_id": s.get("json_template_id"),
                "client_name": cl.get("name")
            })
        return res
    try:
        rows = _query("""
            SELECT cjs.id, cjs.sent_date, cjs.product, cjs.product_specs,
                   jt.name as template_name, jt.file_path, jt.id as json_template_id,
                   c.name as client_name
            FROM client_json_sends cjs
            JOIN json_templates jt ON cjs.json_template_id = jt.id
            JOIN clients c ON cjs.client_id = c.id
            WHERE cjs.client_id = %s
            ORDER BY cjs.sent_date DESC, cjs.id DESC
        """, (client_id,)) or []
        for r in rows:
            if r.get("product_specs"):
                try:
                    r["product_specs"] = json.loads(r["product_specs"])
                except:
                    r["product_specs"] = []
        return rows
    except Exception as e:
        if "1146" in str(e) or "doesn't exist" in str(e).lower():
            return []
        raise


def get_clients_for_product(product_id: int) -> list[dict]:
    """Clients that sell this product (for Products tab)."""
    if _DEMO_MODE:
        cids = [x["client_id"] for x in _DEMO_CLIENT_PRODUCTS if x.get("product_id") == product_id]
        return [deepcopy(c) for c in _DEMO_CLIENTS if c.get("id") in cids]
    try:
        return _query("""
            SELECT c.id, c.name, c.email, c.industry, c.web_store_url
            FROM clients c
            JOIN client_products cp ON c.id = cp.client_id
            WHERE cp.product_id = %s
            ORDER BY c.name
        """, (product_id,)) or []
    except Exception as e:
        if "1146" in str(e) or "doesn't exist" in str(e).lower():
            return []
        raise


def get_product_json_files(product_id: int) -> list[dict]:
    """JSON files related to a product (different specs)."""
    if _DEMO_MODE:
        # For demo, return templates that were sent with this product (from sends)
        sends = [x for x in _DEMO_CLIENT_JSON_SENDS if (x.get("product") or "") == next((p["name"] for p in _DEMO_PRODUCTS if p["id"]==product_id), "")]
        # Better: simple match by product name from any send that refs a prod
        # Return any json templates for simplicity in demo (or empty if no exact)
        # To make dl work in products tab detail, return the known demo ones if product matches name
        prod = next((p for p in _DEMO_PRODUCTS if p.get("id") == product_id), None)
        pname = prod["name"] if prod else ""
        matches = []
        for s in _DEMO_CLIENT_JSON_SENDS:
            if s.get("product") == pname:
                jt = next((t for t in _DEMO_JSON_TEMPLATES if t.get("id") == s.get("json_template_id")), {})
                sp = s.get("product_specs") or []
                if isinstance(sp, str):
                    try: sp = json.loads(sp)
                    except: sp = []
                matches.append({
                    "id": s.get("id"),
                    "specs": sp,
                    "template_name": jt.get("name"),
                    "file_path": jt.get("file_path"),
                    "json_template_id": s.get("json_template_id")
                })
        return matches
    try:
        rows = _query("""
            SELECT pjf.id, pjf.specs, jt.name as template_name, jt.file_path, jt.id as json_template_id
            FROM product_json_files pjf
            JOIN json_templates jt ON pjf.json_template_id = jt.id
            WHERE pjf.product_id = %s
            ORDER BY jt.name
        """, (product_id,)) or []
        for r in rows:
            if r.get("specs"):
                try:
                    r["specs"] = json.loads(r["specs"])
                except:
                    r["specs"] = []
        return rows
    except Exception as e:
        if "1146" in str(e) or "doesn't exist" in str(e).lower():
            return []
        raise


def search_json_templates_by_products(product_names: list[str]) -> list[dict]:
    """
    Find json templates that have been used with the given products.
    Returns most 'relevant' first (by number of matching client sends).
    """
    if not product_names:
        return []
    if _DEMO_MODE:
        # demo: find sends matching, group by template
        from collections import defaultdict
        by_tid = defaultdict(list)
        for s in _DEMO_CLIENT_JSON_SENDS:
            if s.get("product") in product_names:
                by_tid[s.get("json_template_id")].append(s)
        res = []
        for tid, us in by_tid.items():
            jt = next((t for t in _DEMO_JSON_TEMPLATES if t.get("id") == tid), {})
            prods = list({u.get("product") for u in us if u.get("product")})
            res.append({
                "id": tid,
                "name": jt.get("name"),
                "file_path": jt.get("file_path"),
                "usage_count": len(us),
                "used_with_products": ", ".join(prods) if prods else "—"
            })
        return sorted(res, key=lambda x: -x.get("usage_count", 0))
    try:
        # Simple relevance: count of client_json_sends matching any of the products for that template
        placeholders = ",".join(["%s"] * len(product_names))
        sql = f"""
            SELECT jt.id, jt.name, jt.file_path,
                   COUNT(DISTINCT cjs.client_id) as usage_count,
                   GROUP_CONCAT(DISTINCT cjs.product) as used_with_products
            FROM json_templates jt
            JOIN client_json_sends cjs ON jt.id = cjs.json_template_id
            WHERE cjs.product IN ({placeholders})
            GROUP BY jt.id, jt.name, jt.file_path
            ORDER BY usage_count DESC, jt.name
        """
        return _query(sql, tuple(product_names)) or []
    except Exception as e:
        if "1146" in str(e) or "doesn't exist" in str(e).lower():
            return []
        raise


def get_json_template_usage(template_id: int) -> list[dict]:
    """Clients + industries + products that used a particular json template."""
    if _DEMO_MODE:
        sends = [x for x in _DEMO_CLIENT_JSON_SENDS if x.get("json_template_id") == template_id]
        res = []
        for s in sends:
            cl = next((c for c in _DEMO_CLIENTS if c.get("id") == s.get("client_id")), {})
            specs = s.get("product_specs") or []
            if isinstance(specs, str):
                try:
                    specs = json.loads(specs)
                except:
                    specs = []
            res.append({
                "client_id": s.get("client_id"),
                "client_name": cl.get("name"),
                "industry": cl.get("industry"),
                "product": s.get("product"),
                "product_specs": specs,
                "sent_date": s.get("sent_date")
            })
        return res
    try:
        rows = _query("""
            SELECT c.id as client_id, c.name as client_name, c.industry,
                   cjs.product, cjs.product_specs, cjs.sent_date
            FROM client_json_sends cjs
            JOIN clients c ON cjs.client_id = c.id
            WHERE cjs.json_template_id = %s
            ORDER BY cjs.sent_date DESC
        """, (template_id,)) or []
        for r in rows:
            if r.get("product_specs"):
                try:
                    r["product_specs"] = json.loads(r["product_specs"])
                except:
                    r["product_specs"] = []
        return rows
    except Exception as e:
        if "1146" in str(e) or "doesn't exist" in str(e).lower():
            return []
        raise


def search_clients_for_crud(
    name_industry: str = None,
    api_pdf: bool = None,
    json_file: bool = None,
    product_specs: bool = None,
    product_ids: list[int] = None
) -> list[dict]:
    """
    Advanced search used in CRUD tab.
    api_* : if True, only clients that have the flag set.
    product_ids: clients associated with ANY of the selected products.
    """
    if _DEMO_MODE:
        # Simple in-memory filter for demo
        result = _DEMO_CLIENTS[:]
        if name_industry:
            ns = name_industry.lower()
            result = [c for c in result if ns in str(c.get("name","")).lower() or ns in str(c.get("industry","")).lower()]
        if api_pdf is True:
            result = [c for c in result if c.get("api_pdf")]
        if json_file is True:
            result = [c for c in result if c.get("json_file")]
        if product_specs is True:
            result = [c for c in result if c.get("product_specs")]
        if product_ids:
            # filter using demo junction
            allowed_cids = {x["client_id"] for x in _DEMO_CLIENT_PRODUCTS if x.get("product_id") in product_ids}
            result = [c for c in result if c.get("id") in allowed_cids]
        return result

    sql = "SELECT DISTINCT c.* FROM clients c"
    joins = []
    where = ["1=1"]
    params = []

    if product_ids:
        joins.append("JOIN client_products cp ON c.id = cp.client_id")
        where.append(f"cp.product_id IN ({','.join(['%s']*len(product_ids))})")
        params.extend(product_ids)

    if api_pdf is True:
        where.append("c.api_pdf = TRUE")
    if json_file is True:
        where.append("c.json_file = TRUE")
    if product_specs is True:
        where.append("c.product_specs = TRUE")

    if name_industry:
        where.append("(c.name LIKE %s OR c.industry LIKE %s)")
        params.extend([f"%{name_industry}%", f"%{name_industry}%"])

    if joins:
        sql += " " + " ".join(joins)
    sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY c.name"

    try:
        return _query(sql, tuple(params)) or []
    except Exception as e:
        if "1146" in str(e) or "doesn't exist" in str(e).lower():
            # Graceful fallback when new tables/columns not created yet
            return fetch_clients()
        raise


def get_all_json_templates() -> list[dict]:
    """List all registered JSON templates (for the JSON Templates tab)."""
    if _DEMO_MODE:
        return deepcopy(_DEMO_JSON_TEMPLATES)
    try:
        rows = _query("SELECT * FROM json_templates ORDER BY created_at DESC") or []
        return rows
    except Exception as e:
        if "1146" in str(e) or "doesn't exist" in str(e).lower():
            return []
        raise


def get_sales_details_by_countries_and_products(selected_countries: list[str] | None, selected_products: list[str] | None = None) -> list[dict]:
    """
    For homepage product slicer (country slicer removed).
    If selected_countries is None/empty -> no country restriction (show sales details for clients that have sales matching the product filter; "Delivered to" shows all their known delivery countries).
    Otherwise restrict to clients that delivered to the listed countries.
    Sales totals/times only count sales whose 'product' field matches the selected_products filter.
    Always returns data when there are matching sales (even with no deliveries), so the table displays.
    """
    sel_c_lower = {c.lower().strip() for c in (selected_countries or []) if c and c.strip()}
    sel_p_lower = [p.lower().strip() for p in (selected_products or []) if p and p.strip()] or None
    restrict_by_country = bool(sel_c_lower)

    if _DEMO_MODE:
        from collections import defaultdict
        # Build qual clients (by deliv if restricting, else all clients that appear in sales)
        qual = {}
        if restrict_by_country:
            for d in _DEMO_DELIVERIES:
                ctry_l = (d.get("country") or "").lower().strip()
                if ctry_l in sel_c_lower:
                    cid = d.get("client_id")
                    if cid not in qual:
                        cl = next((x for x in _DEMO_CLIENTS if x.get("id") == cid), {})
                        qual[cid] = {"name": cl.get("name") or f"Client #{cid}", "ctrys": set()}
                    qual[cid]["ctrys"].add(d.get("country"))
        else:
            # no country restriction: start from any client that has a sale (we'll filter sales by prod below)
            for s in _DEMO_SALES:
                cid = s.get("client_id")
                if cid not in qual:
                    cl = next((x for x in _DEMO_CLIENTS if x.get("id") == cid), {})
                    qual[cid] = {"name": cl.get("name") or f"Client #{cid}", "ctrys": set()}

        # Pre-collect all deliv countries per client (for the "Delivered to" column when not restricting)
        all_deliv_by_client = defaultdict(set)
        for d in _DEMO_DELIVERIES:
            all_deliv_by_client[d.get("client_id")].add(d.get("country"))

        # aggregate sales
        summaries = defaultdict(lambda: {"amount": 0.0, "latest": None, "name": "", "ctrys": set()})
        for cid, info in qual.items():
            summaries[cid]["name"] = info["name"]
            summaries[cid]["ctrys"] = info.get("ctrys") or all_deliv_by_client.get(cid, set())
            for s in _DEMO_SALES:
                if s.get("client_id") != cid:
                    continue
                prod = (s.get("product") or "").lower()
                if sel_p_lower and not any(sp in prod for sp in sel_p_lower):
                    continue
                try:
                    summaries[cid]["amount"] += float(s.get("amount") or 0)
                except Exception:
                    pass
                sd = str(s.get("sale_date") or "")
                if not summaries[cid]["latest"] or sd > summaries[cid]["latest"]:
                    summaries[cid]["latest"] = sd
        out = []
        for cid, sm in summaries.items():
            # only include if had some amount or we want to show clients even with 0 after filter
            out.append({
                "Client Name": sm["name"],
                "Sales Total ($)": round(sm["amount"], 2),
                "Latest Time": sm["latest"] or "—",
                "Delivered to": ", ".join(sorted(sm["ctrys"])) if sm["ctrys"] else "—"
            })
        # If after product filter everything is 0 and we had a filter, still return the rows (so table shows the clients)
        return sorted(out, key=lambda x: -x["Sales Total ($)"])

    # Real MySQL path (robust to empty countries list)
    try:
        cids = []
        if restrict_by_country and selected_countries:
            ph = ",".join(["%s"] * len(selected_countries))
            dparams = [c.lower() for c in selected_countries]
            c_rows = _query(f"SELECT DISTINCT client_id FROM deliveries WHERE LOWER(country) IN ({ph})", tuple(dparams)) or []
            cids = [r["client_id"] for r in c_rows]
        else:
            # no country restriction: take clients that have any sales (we'll filter by prod in python)
            sales_cids = _query("SELECT DISTINCT client_id FROM sales_records") or []
            cids = [r["client_id"] for r in sales_cids]

        if not cids:
            # fallback: any clients at all
            any_clients = _query("SELECT id FROM clients LIMIT 200") or []
            cids = [r["id"] for r in any_clients]
            if not cids:
                return []

        cph = ",".join(["%s"] * len(cids))
        cinfo = {}
        for r in (_query(f"SELECT id, name FROM clients WHERE id IN ({cph})", tuple(cids)) or []):
            cinfo[r["id"]] = r["name"]

        # All deliveries for these cids (for "Delivered to" column)
        del_rows = _query(f"SELECT client_id, country FROM deliveries WHERE client_id IN ({cph})", tuple(cids)) or []
        # All sales for these cids
        sales_rows = _query(f"SELECT * FROM sales_records WHERE client_id IN ({cph})", tuple(cids)) or []

        from collections import defaultdict
        agg = defaultdict(lambda: {"amount": 0.0, "latest": None, "ctrys": set(), "name": ""})
        for d in del_rows:
            cid = d["client_id"]
            agg[cid]["ctrys"].add(d.get("country"))
            if not agg[cid]["name"]:
                agg[cid]["name"] = cinfo.get(cid, f"Client #{cid}")
        for s in sales_rows:
            cid = s["client_id"]
            prod = (s.get("product") or "").lower()
            if sel_p_lower and not any(sp in prod for sp in sel_p_lower):
                continue
            try:
                agg[cid]["amount"] += float(s.get("amount") or 0)
            except Exception:
                pass
            sd = str(s.get("sale_date") or "")
            if not agg[cid]["latest"] or sd > agg[cid]["latest"]:
                agg[cid]["latest"] = sd

        # Ensure every cid we considered has an entry (even if amount==0 after filter)
        for cid in cids:
            if cid not in agg:
                agg[cid]["name"] = cinfo.get(cid, f"Client #{cid}")
                # pull their deliv countries
                for d in [dd for dd in del_rows if dd["client_id"] == cid]:
                    agg[cid]["ctrys"].add(d.get("country"))

        out = []
        for cid, sm in agg.items():
            out.append({
                "Client Name": sm["name"],
                "Sales Total ($)": round(sm["amount"], 2),
                "Latest Time": sm["latest"] or "—",
                "Delivered to": ", ".join(sorted(sm["ctrys"])) if sm["ctrys"] else "—"
            })
        return sorted(out, key=lambda x: -x["Sales Total ($)"])
    except Exception as e:
        if "1146" in str(e) or "doesn't exist" in str(e).lower():
            return []
        raise


# ---------------------------------------------------------------------------
# Belt-and-suspenders diagnostic (helps when users hit "no attribute" after edits
# on Windows + OneDrive + long-running streamlit without full process restart).
# You can run this from the project folder:
#   python -c "import database; print('clear_and_seed_test_data present:', hasattr(database, 'clear_and_seed_test_data'))"
# ---------------------------------------------------------------------------
if "clear_and_seed_test_data" not in globals():
    # This should never be needed if the def above executed, but makes the name visible
    # even in extremely weird reload / partial exec situations.
    pass  # the def is already at the top of this module

# Quick sanity for developers
# print("database module loaded, clear_and_seed_test_data =", 'clear_and_seed_test_data' in globals())