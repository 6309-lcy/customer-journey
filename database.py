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

import pymysql
from dotenv import load_dotenv
from pymysql.cursors import DictCursor

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
    _DEMO_COMMS = []
    _DEMO_SALES = []
    _DEMO_DELIVERIES = [
        {"client_id": 1, "country": "United States", "address_count": 25},
        {"client_id": 1, "country": "Canada", "address_count": 12},
        {"client_id": 2, "country": "United Kingdom", "address_count": 40},
        {"client_id": 2, "country": "Germany", "address_count": 35},
        {"client_id": 3, "country": "Australia", "address_count": 15},
    ]
    _DEMO_SYSTEM_LOGS = [
        {"log_timestamp": "2025-06-25T10:30:00", "message": "customer Acme Corp required json file", "tags": ["api", "integration"], "client_name": "Acme Corp", "industry": "Technology"},
        {"log_timestamp": "2025-07-30T14:15:00", "message": "customer Global Retail Ltd joined us", "tags": ["onboarding"], "client_name": "Global Retail Ltd", "industry": "Retail"},
        {"log_timestamp": "2025-08-31T09:00:00", "message": "Customer HealthFirst Inc sold 25 unit", "tags": ["sales"], "client_name": "HealthFirst Inc", "industry": "Healthcare"},
    ]


def reset_demo_data():
    global _DEMO_CLIENTS, _DEMO_COMMS, _DEMO_SALES, _DEMO_DELIVERIES, _DEMO_SYSTEM_LOGS
    if _DEMO_MODE:
        try:
            from utils import get_demo_seed_data
            _DEMO_CLIENTS = deepcopy(get_demo_seed_data())
        except Exception:
            _DEMO_CLIENTS = []
        _DEMO_COMMS = []
        _DEMO_SALES = []
        _DEMO_DELIVERIES = []
        _DEMO_SYSTEM_LOGS = []


# ============================================================
# MySQL Connection Helpers
# ============================================================

def get_connection():
    if _DEMO_MODE:
        raise RuntimeError("DEMO MODE active — MySQL is disabled. Use real data or turn off USE_SAMPLE_DATA.")
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
        rec = {"id": new_id, **data}
        _DEMO_CLIENTS.append(rec)
        return new_id

    return _execute(
        """INSERT INTO clients (name, industry, total_orders, total_addresses_delivered, total_order_amount)
           VALUES (%s, %s, %s, %s, %s)""",
        (
            data.get("name"),
            data.get("industry"),
            data.get("total_orders", 0),
            data.get("total_addresses_delivered", 0),
            data.get("total_order_amount", 0),
        )
    )


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
    """Update basic client fields. Supports id (new) or email (legacy fallback). Demo mode in-memory update."""
    if _DEMO_MODE:
        for i, c in enumerate(_DEMO_CLIENTS):
            match = False
            if isinstance(client_id_or_email, int) and c.get("id") == client_id_or_email:
                match = True
            elif isinstance(client_id_or_email, str) and (c.get("email") or "").lower() == str(client_id_or_email).lower():
                match = True
            if match:
                for k, v in payload.items():
                    if k in ("id",): continue
                    c[k] = v
                return
        return
    # Real DB: try id first, fallback email (legacy)
    # For minimal, assume caller passes id when available; implement simple UPDATE
    if isinstance(client_id_or_email, int):
        sets = []
        params = []
        for k in ("name", "industry"):
            if k in payload:
                sets.append(f"{k}=%s")
                params.append(payload[k])
        if sets:
            params.append(client_id_or_email)
            _execute(f"UPDATE clients SET {', '.join(sets)} WHERE id=%s", tuple(params))
    else:
        # legacy email path (no-op or simple if schema has email)
        pass


def update_client_totals(client_id: int):
    if _DEMO_MODE:
        return
    _execute("""
        UPDATE clients c SET
            total_orders = (SELECT COALESCE(SUM(quantity),0) FROM sales_records WHERE client_id=c.id),
            total_addresses_delivered = (SELECT COALESCE(SUM(address_count),0) FROM deliveries WHERE client_id=c.id),
            total_order_amount = (SELECT COALESCE(SUM(amount),0) FROM sales_records WHERE client_id=c.id)
        WHERE c.id = %s
    """, (client_id,))


# ============================================================
# COMMUNICATION LOGS
# ============================================================

def add_communication_log(client_id: int, log_date: str, event: str):
    if _DEMO_MODE:
        _DEMO_COMMS.append({"client_id": client_id, "log_date": log_date, "event": event})
        return
    _execute("INSERT INTO communication_logs (client_id, log_date, event) VALUES (%s,%s,%s)",
             (client_id, log_date, event))


def get_communication_logs(client_id: int) -> list[dict]:
    if _DEMO_MODE:
        return [x for x in _DEMO_COMMS if x.get("client_id") == client_id]
    return _query("SELECT * FROM communication_logs WHERE client_id=%s ORDER BY log_date DESC", (client_id,)) or []


# ============================================================
# SALES RECORDS
# ============================================================

def add_sales_record(client_id: int, sale_date: str, description: str, quantity: int, amount: float):
    if _DEMO_MODE:
        _DEMO_SALES.append({"client_id": client_id, "sale_date": sale_date, "description": description, "quantity": quantity, "amount": amount})
        return
    _execute(
        "INSERT INTO sales_records (client_id, sale_date, description, quantity, amount) VALUES (%s,%s,%s,%s,%s)",
        (client_id, sale_date, description, quantity, amount)
    )
    update_client_totals(client_id)


def get_sales_records(client_id: int) -> list[dict]:
    if _DEMO_MODE:
        return [x for x in _DEMO_SALES if x.get("client_id") == client_id]
    return _query("SELECT * FROM sales_records WHERE client_id=%s ORDER BY sale_date DESC", (client_id,)) or []


# ============================================================
# DELIVERIES (Dispatching Countries for World Map)
# ============================================================

def add_delivery(client_id: int, country: str, address_count: int, delivered_date: str | None = None):
    if _DEMO_MODE:
        _DEMO_DELIVERIES.append({"client_id": client_id, "country": country, "address_count": address_count, "delivered_date": delivered_date})
        return
    _execute(
        "INSERT INTO deliveries (client_id, country, address_count, delivered_date) VALUES (%s,%s,%s,%s)",
        (client_id, country, address_count, delivered_date)
    )
    update_client_totals(client_id)


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
        return fetch_clients(), None
    except Exception as e:
        return [], str(e)