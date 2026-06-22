"""
database.py
MySQL-based data layer for the Client Profile Management System.

Supports:
- Real MySQL via pymysql
- Full DEMO MODE (in-memory) for frontend testing (set USE_SAMPLE_DATA=true)

New data model includes:
- clients (name, industry, totals, api_* flags)
- communication_logs
- sales_records (with optional product)
- deliveries (for world map by country)
- system_logs (queryable on homepage)
- products + client_products + json_templates + client_json_sends

Key analytics: get_key_metrics() computes avg response time (inter-comm gaps) and
conversion time = days from first comm log ("first request") to first JSON API template send.

All functions return plain dicts/lists for easy use in Streamlit + Pydantic.
Graceful fallbacks for missing tables (demo/cloud friendly).
"""

from __future__ import annotations
import re
import json
import os
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from dotenv import load_dotenv

load_dotenv()

# ----------------------------------------------------------
# DB backend switch (production prep)
#   - "mysql"  → pymysql (current)
#   - "mongodb" → pymongo (stub - implement later)
# Set DB_BACKEND=mongodb in .env to switch later.
# Currently we only wire MySQL path.
# ----------------------------------------------------------
DB_BACKEND = os.getenv("DB_BACKEND", "mysql").lower()

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
        {"client_id": 1, "log_date": "2025-04-10", "event": "Requested full JSON API template"},
        {"client_id": 2, "log_date": "2025-03-10", "event": "Demo of product catalog sync"},
        {"client_id": 2, "log_date": "2025-04-22", "event": "Follow-up requirements"},
        {"client_id": 3, "log_date": "2025-05-05", "event": "Requested JSON + API specs for pilot"},
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
        if "customer_cluster" not in c:
            c["customer_cluster"] = None
        # backfill api flags if missing for demo
        for fl in ("api_pdf", "json_file", "product_specs"):
            if fl not in c:
                c[fl] = False

    # Seed demo products, junctions, some json sends for UI testing (Products/JSON tabs, profile assigns, slicers etc)
    global _DEMO_PRODUCTS, _DEMO_CLIENT_PRODUCTS, _DEMO_JSON_TEMPLATES, _DEMO_CLIENT_JSON_SENDS
    if not _DEMO_PRODUCTS:
       _DEMO_PRODUCTS = [
            {"id": 1, "name": "Round Corner Booster Pack Cards (2.5\" x 3.5\")", "category": "Custom Card Decks", "subtype": "Playing Cards", "specs": json.dumps(["20X20X20", "30X30X30"])},
            {"id": 2, "name": "Trading Card Game (2.48\" x 3.46\")", "category": "Custom Cards Decks", "subtype": "Trading Cards", "specs": json.dumps(["v1", "v2", "v2.1"])},
            {"id": 3, "name": "Square Corner Booster Pack Cards (2.5\" x 3.5\")", "category": "Custom Cards Decks", "subtype": "Sports & Collectible Cards", "specs": json.dumps(["basic", "advanced", "enterprise"])},
            {"id": 4, "name": "Tarot Cards (2.75\" x 4.75\")", "category": "Custom Card Decks", "subtype": "Tarot Cards", "specs": json.dumps(["white", "clear", "thermal"])},
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
            {"id": 2, "client_id": 3, "json_template_id": 1, "sent_date": "2025-06-20", "product": "Custom API Kit", "product_specs": ["basic"]},
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
            {"id": 1, "name": "Acme Corp", "email": "contact@acme.com", "industry": "Technology", "web_store_url": "https://acme.example.com/store", "notes": "Key account - prefers JSON", "api_pdf": True, "json_file": True, "product_specs": True, "total_orders": 0, "total_addresses_delivered": 0, "total_order_amount": 0.0, "customer_cluster": "Strategic", "status": "Onboarded"},
            {"id": 2, "name": "Global Retail Ltd", "email": "info@globalretail.com", "industry": "Retail", "web_store_url": "https://globalretail.example.com/shop", "notes": "High volume packaging", "api_pdf": False, "json_file": True, "product_specs": True, "total_orders": 0, "total_addresses_delivered": 0, "total_order_amount": 0.0, "customer_cluster": "Volume Packaging", "status": "Active"},
            {"id": 3, "name": "HealthFirst Inc", "email": "hello@healthfirst.com", "industry": "Healthcare", "web_store_url": None, "notes": "Compliance focused", "api_pdf": True, "json_file": False, "product_specs": True, "total_orders": 0, "total_addresses_delivered": 0, "total_order_amount": 0.0, "customer_cluster": "Compliance", "status": "Requested"},
            {"id": 4, "name": "Nordic Manufacturing", "email": "sales@nordic-mfg.no", "industry": "Manufacturing", "web_store_url": "https://nordic-mfg.example.com", "notes": "", "api_pdf": True, "json_file": True, "product_specs": False, "total_orders": 0, "total_addresses_delivered": 0, "total_order_amount": 0.0, "customer_cluster": "Integration Focused", "status": "Active"},
            {"id": 5, "name": "Pacific Logistics", "email": "ops@pacific-logistics.au", "industry": "Logistics", "web_store_url": None, "notes": "New - testing packs", "api_pdf": False, "json_file": True, "product_specs": True, "total_orders": 0, "total_addresses_delivered": 0, "total_order_amount": 0.0, "customer_cluster": "New Logistics", "status": "Onboarded"},
        ]

        _DEMO_PRODUCTS = [
            {"id": 1, "name": "Round Corner Booster Pack Cards (2.5\" x 3.5\")", "category": "Custom Card Decks", "subtype": "Playing Cards", "specs": json.dumps(["20X20X20", "30X30X30"])},
            {"id": 2, "name": "Trading Card Game (2.48\" x 3.46\")", "category": "Custom Cards Decks", "subtype": "Trading Cards", "specs": json.dumps(["v1", "v2", "v2.1"])},
            {"id": 3, "name": "Square Corner Booster Pack Cards (2.5\" x 3.5\")", "category": "Custom Cards Decks", "subtype": "Sports & Collectible Cards", "specs": json.dumps(["basic", "advanced", "enterprise"])},
            {"id": 4, "name": "Tarot Cards (2.75\" x 4.75\")", "category": "Custom Card Decks", "subtype": "Tarot Cards", "specs": json.dumps(["white", "clear", "thermal"])},
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
            {"id": 3, "client_id": 5, "json_template_id": 1, "sent_date": "2025-06-15", "product": "Booster Pack", "product_specs": ["20X20X20"]},
        ]

        _DEMO_COMMS = [
            {"client_id":1,"log_date":"2025-02-10","event":"Kickoff - API contract"},
            {"client_id":1,"log_date":"2025-03-05","event":"Requirements workshop for integration"},
            {"client_id":1,"log_date":"2025-04-12","event":"Contract review and API discussion"},
            {"client_id":1,"log_date":"2025-05-20","event":"Requested JSON template for Booster integration"},
            {"client_id":5,"log_date":"2025-05-10","event":"Onboarding - requested JSON"},
            {"client_id":3,"log_date":"2025-04-15","event":"Pilot kickoff, requested API specs + JSON"},
            {"client_id":2,"log_date":"2025-01-20","event":"Initial inquiry and catalog demo"},
            {"client_id":2,"log_date":"2025-02-28","event":"Follow-up pricing call"},
        ]
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
    for idx, (nm, em, ind, url, ap, jf, ps, nt, cl, st) in enumerate([
        ("Acme Corp","contact@acme.com","Technology","https://acme.example.com/store",True,True,True,"Key account","Strategic","Onboarded"),
        ("Global Retail Ltd","info@globalretail.com","Retail","https://globalretail.example.com/shop",False,True,True,"High volume","Volume Packaging","Active"),
        ("HealthFirst Inc","hello@healthfirst.com","Healthcare",None,True,False,True,"Compliance","Compliance","Requested"),
        ("Nordic Manufacturing","sales@nordic-mfg.no","Manufacturing","https://nordic-mfg.example.com",True,True,False,"","Integration Focused","Active"),
        ("Pacific Logistics","ops@pacific-logistics.au","Logistics",None,False,True,True,"New onboarding","New Logistics","Onboarded"),
    ],1):
        cids[idx] = insert_client({"name":nm,"email":em,"industry":ind,"web_store_url":url,"api_pdf":ap,"json_file":jf,"product_specs":ps,"notes":nt,"total_orders":0,"total_addresses_delivered":0,"total_order_amount":0.0,"customer_cluster":cl,"status":st})

    # products (using the 4 types from UI)
    pids = {}
    for idx, (nm, cat, sp, sub) in enumerate([
        ("Standard 20x","Custom Card Decks",["20X20X20","30X30X30"], "Booster Pack"),
        ("Basic v1","Board Game Components",["v1","v2","v2.1"], "Sensor Module"),
        ("Entry Kit","Merch & Apparel",["basic","advanced","enterprise"], "Custom API Kit"),
        ("White Label","Jigsaw Puzzles",["white","clear","thermal"], "Label Stock 100mm"),
    ],1):
        pids[idx] = create_product(nm, cat, sp, subtype=sub)

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

    # comms + totals (richer for metrics demo)
    try:
        add_communication_log(cids[1], "2025-02-10", "Kickoff call - API integration contract")
        add_communication_log(cids[1], "2025-03-05", "Requirements workshop for integration")
        add_communication_log(cids[1], "2025-04-12", "Contract review and API discussion")
        add_communication_log(cids[1], "2025-05-20", "Requested JSON template for Booster integration")
        add_communication_log(cids[5], "2025-05-10", "New customer onboarding - requested JSON template")
        add_communication_log(cids[3], "2025-04-15", "Pilot kickoff, requested API specs + JSON")
        add_communication_log(cids[2], "2025-01-20", "Initial inquiry and catalog demo")
        add_communication_log(cids[2], "2025-02-28", "Follow-up pricing call")
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
            {"client_id": 1, "log_date": "2025-04-10", "event": "Requested full JSON API template"},
            {"client_id": 2, "log_date": "2025-03-10", "event": "Demo of product catalog sync"},
            {"client_id": 2, "log_date": "2025-04-22", "event": "Follow-up requirements"},
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
        if "customer_cluster" not in c:
            c["customer_cluster"] = None
        for fl in ("api_pdf", "json_file", "product_specs"):
            if fl not in c:
                c[fl] = False

    global _DEMO_PRODUCTS, _DEMO_CLIENT_PRODUCTS, _DEMO_JSON_TEMPLATES, _DEMO_CLIENT_JSON_SENDS
    _DEMO_PRODUCTS = [
        {"id": 1, "name": "Round Corner Booster Pack Cards (2.5\" x 3.5\")", "category": "Custom Card Decks", "subtype": "Playing Cards", "specs": json.dumps(["20X20X20", "30X30X30"])},
        {"id": 2, "name": "Trading Card Game (2.48\" x 3.46\")", "category": "Custom Cards Decks", "subtype": "Trading Cards", "specs": json.dumps(["v1", "v2", "v2.1"])},
        {"id": 3, "name": "Square Corner Booster Pack Cards (2.5\" x 3.5\")", "category": "Custom Cards Decks", "subtype": "Sports & Collectible Cards", "specs": json.dumps(["basic", "advanced", "enterprise"])},
        {"id": 4, "name": "Tarot Cards (2.75\" x 4.75\")", "category": "Custom Card Decks", "subtype": "Tarot Cards", "specs": json.dumps(["white", "clear", "thermal"])},
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
    if DB_BACKEND == "mongodb":
        raise RuntimeError("MongoDB backend selected (DB_BACKEND=mongodb). Implement pymongo path in database.py or switch to mysql.")
    if _DEMO_MODE:
        raise RuntimeError("DEMO MODE active — MySQL is disabled.")
    try:
        import pymysql
        from pymysql.cursors import DictCursor
    except ImportError:
        raise RuntimeError("pymysql not installed. Run: pip install pymysql cryptography")
    return pymysql.connect(
        host=os.getenv("MYSQL_HOST", "localhost"),
        port=int(os.getenv("MYSQL_PORT", 3306)),
        user=os.getenv("MYSQL_USER", "remoteuser"),
        password=os.getenv("MYSQL_PASSWORD", ""),
        database=os.getenv("MYSQL_DATABASE", "cj"),
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
            "customer_cluster": data.get("customer_cluster"),
            "status": data.get("status", "Onboarded"),
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
                                total_orders, total_addresses_delivered, total_order_amount, notes, customer_cluster, status)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
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
            data.get("customer_cluster"),
            data.get("status", "Onboarded"),
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
        allowed = ("name", "email", "industry", "web_store_url", "api_pdf", "json_file", "product_specs", "notes", "customer_cluster", "status")
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
        allowed = ("name", "email", "industry", "web_store_url", "api_pdf", "json_file", "product_specs", "notes", "customer_cluster", "status")
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


def delete_client(client_id: int):
    """Delete a client (and cascade related if FKs set, otherwise manual)."""
    if _DEMO_MODE:
        global _DEMO_CLIENTS, _DEMO_COMMS, _DEMO_SALES, _DEMO_DELIVERIES, _DEMO_CLIENT_PRODUCTS, _DEMO_CLIENT_JSON_SENDS
        _DEMO_CLIENTS = [c for c in _DEMO_CLIENTS if c.get("id") != client_id]
        _DEMO_COMMS = [x for x in _DEMO_COMMS if x.get("client_id") != client_id]
        _DEMO_SALES = [x for x in _DEMO_SALES if x.get("client_id") != client_id]
        _DEMO_DELIVERIES = [x for x in _DEMO_DELIVERIES if x.get("client_id") != client_id]
        _DEMO_CLIENT_PRODUCTS = [x for x in _DEMO_CLIENT_PRODUCTS if x.get("client_id") != client_id]
        _DEMO_CLIENT_JSON_SENDS = [x for x in _DEMO_CLIENT_JSON_SENDS if x.get("client_id") != client_id]
        return
    # Real
    # Clean dependent rows first (in case no FK cascade)
    for tbl in ("client_json_sends", "sales_records", "deliveries", "communication_logs", "client_products"):
        try:
            _execute(f"DELETE FROM {tbl} WHERE client_id = %s", (client_id,))
        except:
            pass
    _execute("DELETE FROM clients WHERE id = %s", (client_id,))


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

    # Base tables (init all required tables for Flask app)
    _execute("""
        CREATE TABLE IF NOT EXISTS clients (
            id INT AUTO_INCREMENT PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            email VARCHAR(255) NULL,
            industry VARCHAR(255) NULL,
            web_store_url VARCHAR(500) NULL,
            notes TEXT NULL,
            customer_cluster VARCHAR(255) NULL,
            status VARCHAR(50) DEFAULT 'Onboarded',
            total_orders INT DEFAULT 0,
            total_addresses_delivered INT DEFAULT 0,
            total_order_amount DECIMAL(12,2) DEFAULT 0,
            api_pdf BOOLEAN NOT NULL DEFAULT FALSE,
            json_file BOOLEAN NOT NULL DEFAULT FALSE,
            product_specs BOOLEAN NOT NULL DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
        )
    """)

    _execute("""
        CREATE TABLE IF NOT EXISTS communication_logs (
            id INT AUTO_INCREMENT PRIMARY KEY,
            client_id INT NOT NULL,
            log_date DATE NOT NULL,
            event TEXT NOT NULL,
            FOREIGN KEY (client_id) REFERENCES clients(id) ON DELETE CASCADE
        )
    """)

    _execute("""
        CREATE TABLE IF NOT EXISTS sales_records (
            id INT AUTO_INCREMENT PRIMARY KEY,
            client_id INT NOT NULL,
            sale_date DATE NOT NULL,
            description TEXT NULL,
            quantity INT DEFAULT 0,
            amount DECIMAL(12,2) DEFAULT 0,
            product VARCHAR(255) NULL,
            FOREIGN KEY (client_id) REFERENCES clients(id) ON DELETE CASCADE
        )
    """)

    _execute("""
        CREATE TABLE IF NOT EXISTS deliveries (
            id INT AUTO_INCREMENT PRIMARY KEY,
            client_id INT NOT NULL,
            country VARCHAR(255) NOT NULL,
            address_count INT DEFAULT 1,
            delivered_date DATE NULL,
            FOREIGN KEY (client_id) REFERENCES clients(id) ON DELETE CASCADE
        )
    """)

    _execute("""
        CREATE TABLE IF NOT EXISTS system_logs (
            id INT AUTO_INCREMENT PRIMARY KEY,
            log_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            message TEXT NOT NULL,
            tags JSON NULL,
            client_name VARCHAR(255) NULL,
            industry VARCHAR(255) NULL
        )
    """)

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

    # customer_cluster (for Clustering tab)
    if not _column_exists("clients", "customer_cluster"):
        try:
            _execute("ALTER TABLE clients ADD COLUMN customer_cluster VARCHAR(255) NULL")
        except Exception:
            pass

    # status for client management
    if not _column_exists("clients", "status"):
        try:
            _execute("ALTER TABLE clients ADD COLUMN status VARCHAR(50) DEFAULT 'Onboarded'")
        except Exception:
            pass

    # timestamps if missing
    if not _column_exists("clients", "created_at"):
        try:
            _execute("ALTER TABLE clients ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
        except Exception:
            pass
    if not _column_exists("clients", "updated_at"):
        try:
            _execute("ALTER TABLE clients ADD COLUMN updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP")
        except Exception:
            pass

    # Sales product for pick + homepage product slicer
    if not _column_exists("sales_records", "product"):
        try:
            _execute("ALTER TABLE sales_records ADD COLUMN product VARCHAR(255) NULL")
        except Exception:
            pass

    # 2. Products master (with type/subtype for new UI)
    _execute("""
        CREATE TABLE IF NOT EXISTS products (
            id INT AUTO_INCREMENT PRIMARY KEY,
            name VARCHAR(255) NOT NULL UNIQUE,
            category VARCHAR(255) NULL,
            subtype VARCHAR(255) NULL,
            specs JSON NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
        )
    """)

    # Ensure subtype column
    if not _column_exists("products", "subtype"):
        try:
            _execute("ALTER TABLE products ADD COLUMN subtype VARCHAR(255) NULL")
        except Exception:
            pass

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


def create_product(name: str, category: str = None, specs: list[str] = None, subtype: str = None) -> int:
    specs_json = json.dumps(specs) if specs else None
    if _DEMO_MODE:
        new_id = max([p.get("id", 0) for p in _DEMO_PRODUCTS], default=0) + 1
        _DEMO_PRODUCTS.append({
            "id": new_id,
            "name": name,
            "category": category,
            "subtype": subtype,
            "specs": specs_json
        })
        try:
            message = f"New product added: {name} (category: {category or '—'})"
            add_system_log(message, ["product"])
        except Exception:
            pass
        return new_id
    # Try insert with subtype if column exists
    try:
        if subtype:
            pid = _execute(
                "INSERT INTO products (name, category, subtype, specs) VALUES (%s, %s, %s, %s)",
                (name, category, subtype, specs_json)
            )
        else:
            pid = _execute(
                "INSERT INTO products (name, category, specs) VALUES (%s, %s, %s)",
                (name, category, specs_json)
            )
    except Exception:
        pid = _execute(
            "INSERT INTO products (name, category, specs) VALUES (%s, %s, %s)",
            (name, category, specs_json)
        )
    try:
        message = f"New product added: {name} (category: {category or '—'})"
        add_system_log(message, ["product"])
    except Exception:
        pass
    return pid


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


def save_client_json_send(client_id: int, uploaded_file=None, product: str = None, product_specs: list[str] = None, override_filename=None, generated_json: dict = None) -> int:
    """
    Saves the (uploaded or GENERATED) JSON file to disk, creates a json_templates entry,
    and records the send in client_json_sends.
    When generated_json is provided (from json-processor mechanism), we write the processed dict.
    product_specs now receives the rich form choice summary list for display.
    Returns the json_template_id.
    """
    def _clean_part(s: str) -> str:
        s = str(s or "")
        s = s.encode('ascii', 'ignore').decode('ascii')
        s = s.strip().replace(" ", "_")
        s = re.sub(r'[^\w\-.]', '_', s)
        s = re.sub(r'_+', '_', s)
        s = s.strip('_')
        if not s:
            s = "part"
        return s

    base = _clean_part(product or "Template")
    if not base:
        base = "Template"
    spec_part = ""
    if product_specs:
        cleaned = [_clean_part(s) for s in product_specs if s and str(s).strip()]
        if cleaned:
            spec_part = "_" + "_".join(cleaned)[:80]
    derived_name = f"{base}{spec_part}.json"
    if not derived_name.lower().endswith(".json"):
        derived_name += ".json"
    if derived_name == ".json":
        derived_name = "template.json"
    try:
        from werkzeug.utils import secure_filename
        derived_name = secure_filename(derived_name) or "template.json"
    except Exception:
        pass
    if not derived_name.lower().endswith(".json"):
        derived_name += ".json"

    if _DEMO_MODE:
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
        try:
            client = fetch_client(client_id) or {}
            client_name = client.get("name") or f"Client #{client_id}"
            specs_str = ", ".join([str(x) for x in (product_specs or [])]) if product_specs else "—"
            message = f"JSON template generated for {client_name}: {product or '—'} ({specs_str})"
            add_system_log(message, ["json", "upload", "processor"], client_name=client_name, industry=client.get("industry"))
        except Exception:
            pass
        return new_tid

    try:
        os.makedirs(UPLOAD_DIR, exist_ok=True)
        save_path = os.path.join(UPLOAD_DIR, derived_name)

        if generated_json:
            with open(save_path, "w", encoding="utf-8") as f:
                json.dump(generated_json, f, indent=2, ensure_ascii=False)
        elif uploaded_file:
            with open(save_path, "wb") as f:
                uploaded_file.stream.seek(0)
                f.write(uploaded_file.stream.read())
        else:
            # nothing to write, still create record? create minimal placeholder
            with open(save_path, "w", encoding="utf-8") as f:
                json.dump({"note": "no content provided"}, f)

        specs_json = json.dumps(product_specs) if product_specs else None

        template_id = _execute(
            "INSERT INTO json_templates (name, file_path) VALUES (%s, %s)",
            (derived_name, save_path)
        )

        _execute(
            "INSERT INTO client_json_sends (client_id, json_template_id, sent_date, product, product_specs) "
            "VALUES (%s, %s, CURDATE(), %s, %s)",
            (client_id, template_id, product, specs_json)
        )

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

        try:
            client = fetch_client(client_id) or {}
            client_name = client.get("name") or f"Client #{client_id}"
            specs_str = ", ".join([str(x) for x in (product_specs or [])]) if product_specs else "—"
            message = f"JSON template generated for {client_name}: {product or '—'} ({specs_str})"
            add_system_log(message, ["json", "processor", "generated"], client_name=client_name, industry=client.get("industry"))
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
                "client_name": cl.get("name"),
                "is_demo": True   # flag for cloud/demo downloads
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


# ============================================================
# ANALYTICS: Key Metrics (Average Response Time + Conversion Time to first JSON API Template)
# ============================================================

def _parse_date(d: Any) -> Any:
    """Return a date object from 'YYYY-MM-DD' string or date/datetime; None on failure."""
    if d is None:
        return None
    if hasattr(d, "date"):
        try:
            return d.date()
        except Exception:
            pass
    s = str(d).strip()
    if not s:
        return None
    # take just the date part if timestamp
    s = s[:10]
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except Exception:
        return None


def get_key_metrics() -> dict:
    """
    Core analytics for the system.

    Response Time: average days between consecutive Communication Logs (clients with 2+ logs).
    Conversion Time: days from a client's FIRST communication log date ("first request") to their FIRST client_json_sends.sent_date (JSON API template delivery).
    Both work in DEMO and real MySQL. Returns safe defaults if tables are missing.
    """
    if _DEMO_MODE:
        from collections import defaultdict
        from datetime import date as _date

        # comms per client
        comms_by_c: dict[int, list] = defaultdict(list)
        for c in _DEMO_COMMS:
            cid = c.get("client_id")
            dt = _parse_date(c.get("log_date"))
            if cid and dt:
                comms_by_c[cid].append(dt)

        # json sends per client (first = min sent_date)
        json_by_c: dict[int, list] = defaultdict(list)
        for s in _DEMO_CLIENT_JSON_SENDS:
            cid = s.get("client_id")
            dt = _parse_date(s.get("sent_date"))
            if cid and dt:
                json_by_c[cid].append(dt)

        clients = _DEMO_CLIENTS
        per_client = []
        conversion_deltas = []
        response_deltas = []  # pooled inter-comm deltas

        for c in clients:
            cid = c.get("id")
            name = c.get("name") or f"Client #{cid}"
            ind = c.get("industry")
            c_comms = sorted(set(comms_by_c.get(cid, [])))
            c_jsons = sorted(json_by_c.get(cid, []))

            first_comm = c_comms[0] if c_comms else None
            first_json = c_jsons[0] if c_jsons else None
            conv_days = (first_json - first_comm).days if (first_comm and first_json and first_json >= first_comm) else None
            if conv_days is not None:
                conversion_deltas.append(conv_days)

            num_comms = len(c_comms)
            avg_inter = None
            if num_comms >= 2:
                deltas = [(c_comms[i+1] - c_comms[i]).days for i in range(num_comms-1) if (c_comms[i+1] - c_comms[i]).days >= 0]
                if deltas:
                    avg_inter = round(sum(deltas) / len(deltas), 1)
                    response_deltas.extend(deltas)

            per_client.append({
                "Client ID": cid,
                "Client Name": name,
                "Industry": ind or "—",
                "Cluster Label": c.get("customer_cluster") or "—",
                "First Comm Date": str(first_comm) if first_comm else "—",
                "First JSON Sent": str(first_json) if first_json else "—",
                "Conversion Days (to 1st JSON)": conv_days if conv_days is not None else "—",
                "# Comms": num_comms,
                "Avg Days Between Comms": avg_inter if avg_inter is not None else "—",
                "Has JSON Template": "Yes" if first_json else "No",
            })

        avg_conv = round(sum(conversion_deltas) / len(conversion_deltas), 1) if conversion_deltas else None
        avg_resp = round(sum(response_deltas) / len(response_deltas), 1) if response_deltas else None

        # Build grouped averages for clustering by Industry or Cluster Label (customer label)
        from collections import defaultdict
        def _agg_group(rows, gkey):
            gs = defaultdict(list)
            for r in rows:
                gval = r.get(gkey) or "—"
                gs[gval].append(r)
            res = {}
            for g, rs in gs.items():
                convs = [x.get("Conversion Days (to 1st JSON)") for x in rs if isinstance(x.get("Conversion Days (to 1st JSON)"), (int, float))]
                resps = [x.get("Avg Days Between Comms") for x in rs if isinstance(x.get("Avg Days Between Comms"), (int, float))]
                res[g] = {
                    "client_count": len(rs),
                    "avg_conversion_days": round(sum(convs) / len(convs), 1) if convs else None,
                    "avg_response_days": round(sum(resps) / len(resps), 1) if resps else None,
                    "with_conversion": len(convs),
                }
            return res

        return {
            "summary": {
                "avg_conversion_time_days": avg_conv,
                "num_clients_with_json_template": len(conversion_deltas),
                "avg_response_time_days": avg_resp,
                "num_clients_with_multiple_comms": sum(1 for c in per_client if isinstance(c.get("# Comms"), int) and c["# Comms"] >= 2),
                "total_clients": len(clients),
            },
            "per_client": per_client,
            "grouped": {
                "by_industry": _agg_group(per_client, "Industry"),
                "by_customer_cluster": _agg_group(per_client, "Cluster Label"),
            },
        }

    # Real MySQL
    try:
        from collections import defaultdict

        clients = fetch_clients() or []
        if not clients:
            return {"summary": {"avg_conversion_time_days": None, "num_clients_with_json_template": 0, "avg_response_time_days": None, "num_clients_with_multiple_comms": 0, "total_clients": 0}, "per_client": [], "grouped": {"by_industry": {}, "by_customer_cluster": {}}}

        # Fetch all comms
        try:
            comm_rows = _query("SELECT client_id, log_date FROM communication_logs") or []
        except Exception as e:
            if "1146" in str(e) or "doesn't exist" in str(e).lower():
                comm_rows = []
            else:
                comm_rows = []

        # Fetch all json sends
        try:
            json_rows = _query("SELECT client_id, sent_date FROM client_json_sends") or []
        except Exception as e:
            if "1146" in str(e) or "doesn't exist" in str(e).lower():
                json_rows = []
            else:
                json_rows = []

        comms_by_c: dict[int, list] = defaultdict(list)
        for r in comm_rows:
            cid = r.get("client_id")
            dt = _parse_date(r.get("log_date"))
            if cid and dt:
                comms_by_c[cid].append(dt)

        json_by_c: dict[int, list] = defaultdict(list)
        for r in json_rows:
            cid = r.get("client_id")
            dt = _parse_date(r.get("sent_date"))
            if cid and dt:
                json_by_c[cid].append(dt)

        per_client = []
        conversion_deltas = []
        response_deltas = []

        for c in clients:
            cid = c.get("id")
            name = c.get("name") or f"Client #{cid}"
            ind = c.get("industry")
            c_comms = sorted(set(comms_by_c.get(cid, [])))
            c_jsons = sorted(json_by_c.get(cid, []))

            first_comm = c_comms[0] if c_comms else None
            first_json = c_jsons[0] if c_jsons else None
            conv_days = (first_json - first_comm).days if (first_comm and first_json and first_json >= first_comm) else None
            if conv_days is not None:
                conversion_deltas.append(conv_days)

            num_comms = len(c_comms)
            avg_inter = None
            if num_comms >= 2:
                deltas = [(c_comms[i+1] - c_comms[i]).days for i in range(num_comms-1) if (c_comms[i+1] - c_comms[i]).days >= 0]
                if deltas:
                    avg_inter = round(sum(deltas) / len(deltas), 1)
                    response_deltas.extend(deltas)

            per_client.append({
                "Client ID": cid,
                "Client Name": name,
                "Industry": ind or "—",
                "Cluster Label": c.get("customer_cluster") or "—",
                "First Comm Date": str(first_comm) if first_comm else "—",
                "First JSON Sent": str(first_json) if first_json else "—",
                "Conversion Days (to 1st JSON)": conv_days if conv_days is not None else "—",
                "# Comms": num_comms,
                "Avg Days Between Comms": avg_inter if avg_inter is not None else "—",
                "Has JSON Template": "Yes" if first_json else "No",
            })

        avg_conv = round(sum(conversion_deltas) / len(conversion_deltas), 1) if conversion_deltas else None
        avg_resp = round(sum(response_deltas) / len(response_deltas), 1) if response_deltas else None

        # Build grouped averages for clustering by Industry or Cluster Label (customer label)
        from collections import defaultdict
        def _agg_group(rows, gkey):
            gs = defaultdict(list)
            for r in rows:
                gval = r.get(gkey) or "—"
                gs[gval].append(r)
            res = {}
            for g, rs in gs.items():
                convs = [x.get("Conversion Days (to 1st JSON)") for x in rs if isinstance(x.get("Conversion Days (to 1st JSON)"), (int, float))]
                resps = [x.get("Avg Days Between Comms") for x in rs if isinstance(x.get("Avg Days Between Comms"), (int, float))]
                res[g] = {
                    "client_count": len(rs),
                    "avg_conversion_days": round(sum(convs) / len(convs), 1) if convs else None,
                    "avg_response_days": round(sum(resps) / len(resps), 1) if resps else None,
                    "with_conversion": len(convs),
                }
            return res

        return {
            "summary": {
                "avg_conversion_time_days": avg_conv,
                "num_clients_with_json_template": len(conversion_deltas),
                "avg_response_time_days": avg_resp,
                "num_clients_with_multiple_comms": sum(1 for c in per_client if isinstance(c.get("# Comms"), int) and c["# Comms"] >= 2),
                "total_clients": len(clients),
            },
            "per_client": per_client,
            "grouped": {
                "by_industry": _agg_group(per_client, "Industry"),
                "by_customer_cluster": _agg_group(per_client, "Cluster Label"),
            },
        }
    except Exception as e:
        if "1146" in str(e) or "doesn't exist" in str(e).lower():
            return {"summary": {"avg_conversion_time_days": None, "num_clients_with_json_template": 0, "avg_response_time_days": None, "num_clients_with_multiple_comms": 0, "total_clients": len(fetch_clients() or [])}, "per_client": [], "grouped": {"by_industry": {}, "by_customer_cluster": {}}}
        # surface other errors to caller (UI will show)
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