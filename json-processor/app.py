from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse, Response
from pathlib import Path
import json
import csv
from datetime import datetime, timezone
from typing import Any
import socket
import io
import os
import re

app = FastAPI(title="JSON Processor")

# Support configurable data directory for deployment (Docker volume, etc.)
# Set DATA_DIR=/app/data when running in container
BASE_DIR = Path(__file__).parent
DATA_DIR = Path(os.getenv("DATA_DIR", BASE_DIR / "data")).resolve()
UPLOADS_DIR = DATA_DIR / "uploads"
PROCESSED_DIR = DATA_DIR / "processed"
LOG_CSV = DATA_DIR / "processing_log.csv"

print(f"[startup] Using data directory: {DATA_DIR}")

# Ensure directories exist
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

# Serve the frontend
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

# === New CSV format as requested ===
CSV_COLUMNS = ["Template", "Client Name", "Product", "Qty", "Client Email", "Processed At", "Date Join"]


def ensure_csv_header():
    """Create/ensure CSV with the exact requested columns.
    Very tolerant of OneDrive/Windows file locks.
    Also cleans up old 'Template' column values to contain only clean filenames (no ugly paths).
    """
    try:
        if not LOG_CSV.exists():
            with open(LOG_CSV, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(CSV_COLUMNS)
            return

        # Read current header (best effort)
        try:
            with open(LOG_CSV, "r", newline="", encoding="utf-8") as f:
                reader = csv.reader(f)
                existing = next(reader, [])
        except Exception:
            existing = []

        if existing and existing != CSV_COLUMNS:
            # Robust migration: reorder columns + add missing ones (e.g. Processed At, Date Join position)
            # This handles moving Template to first, Email before Processed At, Date Join after Processed At
            try:
                old_header = existing
                all_data = []
                with open(LOG_CSV, "r", newline="", encoding="utf-8") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        new_row = []
                        for col in CSV_COLUMNS:
                            # Try exact, then case-insensitive
                            val = row.get(col, None)
                            if val is None:
                                for k, v in row.items():
                                    if k.lower() == col.lower():
                                        val = v
                                        break
                            new_row.append(val if val is not None else "")
                        all_data.append(new_row)

                with open(LOG_CSV, "w", newline="", encoding="utf-8") as f:
                    writer = csv.writer(f)
                    writer.writerow(CSV_COLUMNS)
                    writer.writerows(all_data)
                print("[CSV] Columns reordered and migrated to current format.")
            except Exception as e:
                print(f"[CSV] Could not migrate/reorder columns (locked?): {e}")

        # One-time cleanup: ensure "Template" column contains only the basename (no data/processed/ paths)
        # Makes CSV nice in Excel. Template is always the first column now.
        try:
            rows = []
            changed = False
            template_idx = CSV_COLUMNS.index("Template") if "Template" in CSV_COLUMNS else 0
            with open(LOG_CSV, "r", newline="", encoding="utf-8") as f:
                reader = csv.reader(f)
                for i, row in enumerate(reader):
                    if i == 0:
                        rows.append(row)
                        continue
                    if len(row) > template_idx:
                        val = row[template_idx]
                        if val and ('/' in val or '\\' in val):
                            row[template_idx] = Path(val).name
                            changed = True
                    rows.append(row)

            if changed:
                with open(LOG_CSV, "w", newline="", encoding="utf-8") as f:
                    writer = csv.writer(f)
                    writer.writerows(rows)
                print("[CSV] Cleaned Template column to use only clean filenames.")
        except Exception as e:
            print(f"[CSV] Could not clean Template column: {e}")

    except PermissionError as e:
        print(f"[CSV] Permission warning (common on OneDrive): {e}")
    except Exception as e:
        print(f"[CSV] Header check warning: {e}")


def force_reset_csv():
    """Force the CSV to the exact 6 columns the user wants, truncating whatever was there before.
    This is safe to call while the server is running.
    """
    LOG_CSV.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(CSV_COLUMNS)
    return {"success": True, "message": "CSV log reset to the 6 requested columns."}


def get_local_lan_ip() -> str:
    """Best effort to get a LAN IP so you can tell colleagues an address to use."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.2)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "localhost"


ensure_csv_header()


def get_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def extract_csv_row(original_data: Any, template_path: str) -> list:
    """
    Extract the exact columns requested by the user from the uploaded JSON (the config).
    Handles the short config shape (and {data: config} wrapper).
    Looks for several common key variations (case-insensitive).
    """
    fields = extract_config_fields(original_data)

    client_name = fields["client_name"]
    product     = fields["product"]
    qty         = fields["qty"]
    date_join   = fields.get("date_join", "")
    client_email = fields.get("client_email", "")

    # "Template" column holds the output file (relative path to the generated JSON)
    template = template_path

    return [client_name, product, qty, date_join, template, client_email]


def extract_config_fields(data: Any) -> dict:
    """Extract key fields from the uploaded config for naming and logging."""
    if isinstance(data, dict) and isinstance(data.get("data"), dict):
        config = data["data"]
    else:
        config = data if isinstance(data, dict) else {}

    def find_value(possible_keys: list[str], default: str = "") -> str:
        for key in possible_keys:
            if key in config and config[key] not in (None, ""):
                val = config[key]
                return str(val).strip() if not isinstance(val, (dict, list)) else default
        lower_map = {k.lower(): k for k in config}
        for wanted in possible_keys:
            if wanted.lower() in lower_map:
                actual = lower_map[wanted.lower()]
                val = config[actual]
                if val not in (None, ""):
                    return str(val).strip() if not isinstance(val, (dict, list)) else default
        return default

    return {
        "client_name": find_value(["Client Name", "clientname", "client_name", "ClientName", "name", "Client"]),
        "product": find_value(["Product", "product"]),
        "qty": find_value(["Qty", "qty", "quantity", "Quantity"]),
        "date_join": find_value(["Date Join", "date join", "dateJoin", "date_join", "DateJoin", "join date", "Join Date"]),
        "client_email": find_value(["Client Email", "client email", "clientemail", "email", "Email", "client_email", "ClientEmail"]),
    }


def sort_keys_recursive(obj: Any) -> Any:
    """Recursively sort dictionary keys for consistent, diff-friendly output."""
    if isinstance(obj, dict):
        return {k: sort_keys_recursive(obj[k]) for k in sorted(obj.keys())}
    elif isinstance(obj, list):
        return [sort_keys_recursive(item) for item in obj]
    else:
        return obj


def compute_basic_stats(data: Any) -> dict:
    """Lightweight stats about the incoming JSON."""
    if isinstance(data, dict):
        stats = {
            "type": "object",
            "key_count": len(data),
        }
        if "items" in data and isinstance(data["items"], list):
            stats["item_count"] = len(data["items"])
            # Try to sum qty if present
            total_qty = 0
            for it in data["items"]:
                if isinstance(it, dict):
                    q = it.get("qty", 0)
                    if isinstance(q, (int, float)):
                        total_qty += q
                    elif isinstance(q, str):
                        try:
                            total_qty += float(q)
                        except ValueError:
                            pass
            stats["total_qty"] = total_qty
        return stats
    elif isinstance(data, list):
        return {"type": "array", "length": len(data)}
    return {"type": type(data).__name__}


def process_json(data: Any, original_filename: str) -> dict:
    """
    ============================================================
    n8n "Generate Full Template" Function Node logic (exact port)
    ============================================================

    Input (the uploaded JSON):
      - Either the raw config object (like n8n/new request.json):
          { "qty": 30, "material paths": "...", "properties": {...}, ... }
      - Or wrapped as { "data": <config> }  (to match $input.first().json.data)

    Output (exactly matches the return of the pasted n8n Function Node):
      {
        "json": {
          "template": <full order object>,
          "thirdOrderId": "replace_with_yout_order_number",
          "quantity": <int>
        }
      }

    IMPORTANT: This replicates the "Run Once for All Items" behavior.
    """
    # Support both shapes: direct config or { "data": config }
    if isinstance(data, dict) and isinstance(data.get("data"), dict):
        config = data["data"]
    else:
        config = data if isinstance(data, dict) else {}

    # === Exact translation of the provided n8n Function Node ===
    try:
        quantity = int(str(config.get("qty", 1)))
    except Exception:
        quantity = 1

    material_path = str(config.get("material paths", "")).strip()
    image_link = "replace_with_your_design"

    properties: dict = {}
    raw_props = config.get("properties")
    if raw_props is not None and isinstance(raw_props, dict) and not isinstance(raw_props, list):
        properties = dict(raw_props)

    page_content_designs = [
        {"pageContentIndex": i, "effect": "CMYK", "image": image_link}
        for i in range(quantity)
    ]

    third_order_id = "replace_with_your_order_number"

    base_item = {
        "thirdOrderItemId": third_order_id,
        "qty": quantity,
        "unitPrice": "10.00",
        "storeProductId": "your_store_product_id",
        "properties": properties,
        "customizeProject": {
            "customizeType": "IMAGE",
            "comparisonThumbnail": image_link,
            "designs": [
                {
                    "side": "Card_Front",
                    "materialPath": material_path,
                    "pageContentDesigns": list(page_content_designs)
                },
                {
                    "side": "Card_Back",
                    "materialPath": material_path,
                    "pageContentDesigns": list(page_content_designs)
                }
            ],
            "content": [
                {"side": "Booster_Pack", "image": image_link}
            ]
        }
    }

    final_json = {
        "thirdOrderId": third_order_id,
        "thirdOrderNumber": third_order_id,
        "items": [base_item],
        "shippingMethod": "Standard",
        "paymentMethod": "PayPal",
        "currency": "USD",
        "status": "processing",
        "deliveryAddress": {
            "country": "US",
            "state": "NJ",
            "city": "Atlantic City",
            "address_1": "1301 Bacharach Boulevard Atlantic City NJ 08401 United States",
            "address_2": "",
            "postcode": "08401",
            "first_name": "REPLACE_WITH_FIRST_NAME",
            "last_name": "REPLACE_WITH_LAST_NAME",
            "phone": "0777-123456",
            "mobile": "18475031246",
            "email": "REPLACE_WITH_EMAIL@example.com",
            "company": "REPLACE_WITH_COMPANY"
        },
        "billingAddress": {},
        "orderTotals": [
            {"name": "TAX", "value": "0.00"},
            {"name": "SHIPPING", "value": "1.00"},
            {"name": "SUBTOTAL", "value": f"{10 * quantity:.2f}"},
            {"name": "ORDER_TOTAL", "value": f"{11 * quantity:.2f}"}
        ]
    }

    final_json["billingAddress"] = dict(final_json["deliveryAddress"])

    # This is exactly what the n8n function node returns
    processed = {
        "json": {
            "template": final_json,
            "thirdOrderId": third_order_id,
            "quantity": quantity
        }
    }

    original_stats = compute_basic_stats(data)
    processed_stats = compute_basic_stats(processed)

    return {
        "processed_json": processed,
        "original_stats": original_stats,
        "processed_stats": processed_stats,
        "meta": {
            "_processed_at": get_now_iso(),
            "_source_file": original_filename,
            "_processor_version": "0.2.0-n8n-template-generator",
            "quantity": quantity,
            "thirdOrderId": third_order_id,
        }
    }


def append_log(row: list):
    """Append one row to the CSV log."""
    with open(LOG_CSV, "a", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow(row)


def save_json(data: Any, directory: Path, base_name: str, *, add_timestamp: bool = True) -> Path:
    """Save JSON. 
    By default adds timestamp prefix to avoid collisions.
    For processed output files we pass add_timestamp=False and a nice name.
    """
    directory.mkdir(parents=True, exist_ok=True)

    # Basic sanitization
    safe = "".join(c if c.isalnum() or c in "._-" else "_" for c in base_name)[:80]
    if not safe.lower().endswith(".json"):
        safe += ".json"

    if add_timestamp:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{ts}_{safe}"
    else:
        filename = safe

    # Ensure unique filename
    original = filename
    counter = 1
    while (directory / filename).exists():
        if '.' in original:
            name, ext = original.rsplit('.', 1)
            filename = f"{name}_{counter}.{ext}"
        else:
            filename = f"{original}_{counter}"
        counter += 1

    path = directory / filename
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    return path


@app.get("/", response_class=HTMLResponse)
async def serve_frontend():
    html_path = BASE_DIR / "static" / "index.html"
    return HTMLResponse(content=html_path.read_text(encoding="utf-8"))


@app.post("/api/process")
async def process_file(json_file: UploadFile = File(...)):
    filename = json_file.filename or "unknown.json"
    if not filename.lower().endswith(".json"):
        raise HTTPException(status_code=400, detail="Only .json files are accepted")

    try:
        raw = await json_file.read()
        size_bytes = len(raw)

        # Parse JSON
        try:
            original_data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=400, detail=f"Invalid JSON: {exc.msg}")

        # Run placeholder improvement
        result = process_json(original_data, filename)
        processed_data = result["processed_json"]

        # === Compute nice output filename: {{today.date_clientname_product_qty}}.json ===
        fields = extract_config_fields(original_data)
        date_str = datetime.now().strftime("%Y%m%d")

        def sanitize_filename_part(s: str) -> str:
            s = re.sub(r'[^a-zA-Z0-9]', '_', str(s or "").strip())
            s = re.sub(r'_+', '_', s).strip('_').lower()
            return s or "unknown"

        client_s = sanitize_filename_part(fields["client_name"])
        product_s = sanitize_filename_part(fields["product"])
        qty_s = sanitize_filename_part(fields["qty"])

        nice_name = f"{date_str}_{client_s}_{product_s}_{qty_s}.json"

        # Persist both versions (great for local debugging / audit)
        orig_saved = save_json(original_data, UPLOADS_DIR, filename)
        proc_saved = save_json(processed_data, PROCESSED_DIR, nice_name, add_timestamp=False)

        # Build the new CSV row using the requested columns
        # Use only the clean filename in "Template" column (no ugly full path)
        clean_template = proc_saved.name
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        fields = extract_config_fields(original_data)  # reuse for clean assembly
        csv_row = [
            clean_template,                    # Template (first)
            fields["client_name"],
            fields["product"],
            fields["qty"],
            fields["client_email"],
            timestamp,                         # Processed At
            fields["date_join"]                # Date Join (after Processed At)
        ]
        append_log(csv_row)

        # Compute values needed for the response (and previously used for logging)
        proc_size = len(json.dumps(processed_data, ensure_ascii=False).encode("utf-8"))
        qty = result.get("meta", {}).get("quantity", "")

        # Response for the UI
        return {
            "success": True,
            "original_filename": filename,
            "original_size": size_bytes,
            "processed_size": proc_size,
            "quantity": qty,
            "thirdOrderId": result.get("meta", {}).get("thirdOrderId"),
            "download_name": nice_name,
            "processed_json": processed_data,
            "saved": {
                "original": str(orig_saved.relative_to(BASE_DIR)),
                "processed": str(proc_saved.relative_to(BASE_DIR)),
            },
            "stats": {
                "original": result["original_stats"],
                "processed": result["processed_stats"],
            },
        }

    except HTTPException:
        raise
    except Exception as exc:
        # Best effort error logging (still 6 columns)
        try:
            err_row = ["", "", "", "", "", f"ERROR: {str(exc)[:120]}"]
            # Try to fill Client Name / Product if we have the filename
            append_log(err_row)
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=f"Processing error: {str(exc)}")


@app.get("/api/logs")
async def get_recent_logs(limit: int = 40):
    """Return the most recent log rows for the history table."""
    ensure_csv_header()
    if not LOG_CSV.exists():
        return {"logs": []}

    rows = []
    with open(LOG_CSV, "r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(dict(row))

    rows.reverse()  # newest first
    return {"logs": rows[:limit]}


@app.post("/api/reset-log")
async def reset_log_endpoint():
    """Reset the CSV log to the exact 6 columns the user requested.
    Useful when the old header is still present due to file locks.
    """
    try:
        result = force_reset_csv()
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to reset CSV: {str(e)}")


@app.get("/health")
async def health_check():
    """Simple health endpoint for Docker / load balancers / monitoring."""
    return {
        "status": "ok",
        "data_dir": str(DATA_DIR),
        "csv_exists": LOG_CSV.exists()
    }


@app.get("/api/download/processed/{filename}")
async def download_processed(filename: str, download_name: str = None):
    """Force download of a generated output JSON (the main thing internal users need).
    If download_name is provided, the downloaded file will use that name (following the naming rule).
    """
    safe_name = Path(filename).name
    file_path = PROCESSED_DIR / safe_name
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="Processed file not found")

    # Use the provided download_name (if any) so the saved file follows the rule, even for old internal filenames
    final_name = download_name or safe_name
    # Basic safety: ensure it ends with .json
    if not final_name.lower().endswith('.json'):
        final_name += '.json'

    return FileResponse(
        path=file_path,
        filename=final_name,
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{final_name}"'}
    )


@app.get("/api/download-log")
async def download_log():
    """Internal-only: download the raw processing log CSV (for Excel/analysis)."""
    ensure_csv_header()
    if not LOG_CSV.exists():
        raise HTTPException(404, "No log yet")
    return FileResponse(
        LOG_CSV,
        filename="processing_log.csv",
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="processing_log.csv"'}
    )


# Note: The old /api/export-csv-with-links was removed per requirements.
# Internal users access the log via the web UI history table or the /api/download-log endpoint.


# Allow running directly: python app.py
if __name__ == "__main__":
    import uvicorn
    lan_ip = get_local_lan_ip()
    print(f"\n[Sharing tip] For other people to download the JSONs, run with:")
    print(f"  python -m uvicorn app:app --host 0.0.0.0 --port 8000 --reload")
    print(f"  Then give them:  http://{lan_ip}:8000\n")
    print("[Deployment] For real deployment use Docker (see docker-compose.yml + README)")
    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=True)
