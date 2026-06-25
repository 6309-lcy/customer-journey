

from __future__ import annotations
import re
import os
import json
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash, send_from_directory, jsonify, session
from werkzeug.utils import secure_filename

import database

# ----------------------------------------------------------
# Flask setup
# ----------------------------------------------------------
app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET", "dev-secret-change-in-prod")
app.config["UPLOAD_FOLDER"] = database.UPLOAD_DIR
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
app.config['SESSION_COOKIE_SAMESITE'] = 'None'
app.config['SESSION_COOKIE_SECURE'] = True  # required when SameSite=None

# Demo login (popup-style login page + creds printed for external ngrok demo)
DEMO_USER = "admin"
DEMO_PASS = "cj2026demo"

@app.after_request
def add_headers(response):
    response.headers['X-Frame-Options'] = 'ALLOWALL'
    response.headers['Content-Security-Policy'] = "frame-ancestors *"
    return response

@app.before_request
def require_login():
    open_endpoints = {"login", "static", "download_json"}
    if request.endpoint not in open_endpoints and not session.get("logged_in"):
        return redirect(url_for("login", next=request.url))

# Simple allowed extensions for JSON
ALLOWED_EXT = {"json", "txt"}

def sanitize_filename(name: str) -> str:
    name = name.encode('ascii', 'ignore').decode('ascii')
    name = re.sub(r'[^\w\-.]', '_', name)
    name = re.sub(r'_+', '_', name)
    return secure_filename(name)
def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXT

# ----------------------------------------------------------
# json-processor mechanism (ported/adapted from json-processor/app.py)
# We use ONLY the core generation logic here. Input = short config like new request.json
# Output = the exact processed wrapper containing full "template"
# ----------------------------------------------------------
def process_json_config(config: dict) -> dict:
    
    try:
        quantity = int(str(config.get("qty", 1)))
    except Exception:
        quantity = 1
    if quantity < 1:
        quantity = 1

    material_path = str(config.get("material paths", "") or config.get("material_paths", "")).strip() or "0,0,0"
    image_link = "replace_with_your_design"

    properties: dict = {}
    raw_props = config.get("properties")
    if isinstance(raw_props, dict):
        properties = dict(raw_props)
    effect = config.get("printing_effects")
    if raw_props['front design mode'] == "same":
        page_content_designs_front = [
            {"pageContentIndex": 0, "effect": effect, "image": image_link}
            # for i in range(quantity)
        ]
    else:
        page_content_designs_front = [
            {"pageContentIndex": i, "effect": effect, "image": image_link}
            for i in range(quantity)
        ]
    if raw_props['back design mode'] == "same":
        page_content_designs_back = [
            {"pageContentIndex": 0, "effect": effect, "image": image_link}
            # for i in range(quantity)
        ]
    else:
        page_content_designs_back = [
            {"pageContentIndex": i, "effect": effect, "image": image_link}
            for i in range(quantity)
        ]

    third_order_id = "replace_with_your_order_number"
    packaging = {}
    if config.get("packaging") == "Custom Tin Box":
        packaging = [
            {
                "Side": "Top", "image" : image_link
            },
            {
                "Side": "Bottom", "image" : image_link
            }
        ]
    elif config.get("packaging") == "Custom Tuck Box":
        ## should be non null
        if config.get("tuck_extra") == "Outside":
            packaging = [
                {
                    "side" : "Dynamic_tuck_box_outside",
                    "materialPath" : material_path,
                    "pageContentDesigns": [
                        {
                            "pageContentIndex" :0,
                            "effect": effect,
                            "image" :image_link
                        }
                    ]
                }
            ]
        else : 
             packaging = [
                {
                    "side" : "Dynamic_tuck_box_outside",
                    "materialPath" : material_path,
                    "pageContentDesigns": [
                        {
                            "pageContentIndex" :0,
                            "effect": effect,
                            "image" :image_link
                        }
                    ],
                    "side" : "Dynamic_tuck_box_inside",
                    "materialPath" : material_path,
                    "pageContentDesigns": [
                        {
                            "pageContentIndex" :0,
                            "effect": effect,
                            "image" :image_link
                        }
                    ]
                }
            ]
    elif config.get("packaging") == "Custom Tin Box":
        packaging = [
            {"side":"Top", "image": image_link},
            {"side" : "Bottom", "image" : image_link}
        ]
    else: #booster pack
        packaging = [
            {"side":"Booster_Pack", "image": image_link}
        ]
        
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
                    "pageContentDesigns": list(page_content_designs_front)
                },
                {
                    "side": "Card_Back",
                    "materialPath": material_path,
                    "pageContentDesigns": list(page_content_designs_back)
                }
            ],
            "content": packaging
            
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

    # Return ONLY the template (not wrapped {"json": { "template": ... }})
    # This is the final JSON file content saved for the client/product.
    return final_json

# ----------------------------------------------------------
# DB switch helper (for future Mongo). Currently MySQL only.
# ----------------------------------------------------------
def using_mysql() -> bool:
    return os.getenv("DB_BACKEND", "mysql").lower() != "mongodb"

# Note: database.py will connect MySQL. Mongo stub can be added later by user.

# ----------------------------------------------------------
# Helpers
# ----------------------------------------------------------
STATUS_COLORS = {
    "Onboarded": "bg-emerald-100 text-emerald-700",
    "Active": "bg-blue-100 text-blue-700",
    "Requested": "bg-amber-100 text-amber-700",
    "Need help": "bg-red-100 text-red-700",
}

PRODUCT_TYPES = [
    "Custom Card Decks",
    "Board Game Components",
    "Jigsaw Puzzles",
    "Merch & Apparel",
]

def get_clients_for_display():
    try:
        if not database.is_demo_mode():
            database.ensure_new_feature_tables()
    except Exception:
        pass
    clients = database.fetch_clients() or []
    for c in clients:
        c.setdefault("status", "Onboarded")
        c.setdefault("customer_cluster", None)
        for key in ("created_at", "updated_at"):
            val = c.get(key)
            if hasattr(val, "strftime"):
                c[key] = val.strftime("%Y-%m-%d" if key == "created_at" else "%Y-%m-%d %H:%M")
            elif val:
                c[key] = str(val)[:16]
            else:
                c[key] = None
    return clients

def get_products_for_display():
    try:
        if not database.is_demo_mode():
            database.ensure_new_feature_tables()
    except Exception:
        pass
    prods = database.get_all_products() or []
    for p in prods:
        p.setdefault("type", p.get("category") or "Custom Card Decks")
        p.setdefault("sub_type", p.get("subtype") or "")
        p.setdefault("name", p.get("name") or p.get("sub_type") or "")
        sp = p.get("specs") or []
        if isinstance(sp, str):
            try: sp = json.loads(sp)
            except: sp = [sp] if sp else []
        p["specs"] = sp
    return prods

def get_client_products_simple(client_id: int):
    """Return list of product names for a client."""
    try:
        prods = database.get_client_products(client_id) or []
        return [p.get("name") for p in prods if p.get("name")]
    except:
        return []

# ----------------------------------------------------------
# Routes - Navbar driven
# ----------------------------------------------------------

@app.route("/")
@app.route("/clients")
def clients_page():
    try:
        if not database.is_demo_mode():
            database.ensure_new_feature_tables()
    except Exception:
        pass
    clients = get_clients_for_display()

    # Search / filter
    q = (request.args.get("q") or "").strip().lower()
    industry = (request.args.get("industry") or "").strip()
    cluster = (request.args.get("cluster") or "").strip()

    filtered = []
    for c in clients:
        name_ind = f"{c.get('name','')} {c.get('email','')} {c.get('industry','')} {c.get('customer_cluster','')}".lower()
        if q and q not in name_ind:
            continue
        if industry and (c.get("industry") or "") != industry:
            continue
        if cluster and (c.get("customer_cluster") or "") != cluster:
            continue
        filtered.append(c)

    # Stats
    total = len(clients)

    # Unique for filters
    industries = sorted({c.get("industry") for c in clients if c.get("industry")})
    clusters = sorted({c.get("customer_cluster") for c in clients if c.get("customer_cluster")})

    return render_template(
        "clients.html",
        clients=filtered,
        total=total,
        industries=industries,
        clusters=clusters,
        current_q=q,
        current_industry=industry,
        current_cluster=cluster,
        status_colors=STATUS_COLORS,
    )

@app.route("/clients/add", methods=["POST"])
def add_client():
    name = (request.form.get("name") or "").strip()
    email = (request.form.get("email") or "").strip()
    industry = (request.form.get("industry") or "").strip()
    web_url = (request.form.get("web_store_url") or "").strip()
    status = (request.form.get("status") or "Onboarded").strip()

    if not name or not email:
        flash("Name and Email are required.", "error")
        return redirect(url_for("clients_page"))

    try:
        data = {
            "name": name,
            "email": email or None,
            "industry": industry or None,
            "web_store_url": web_url or None,
            "status": status,
            "customer_cluster": None,
            "notes": None,
        }
        new_id = database.insert_client(data)
        flash(f"Client added: {name}", "success")
        return redirect(url_for("client_profile", client_id=new_id))
    except Exception as e:
        flash(f"Failed to add client: {e}", "error")
        return redirect(url_for("clients_page"))

@app.route("/clients/<int:client_id>/delete", methods=["POST"])
def delete_client_route(client_id: int):
    try:
        database.delete_client(client_id)
        flash("Client deleted.", "success")
    except Exception as e:
        flash(f"Delete failed: {e}", "error")
    return redirect(url_for("clients_page"))

# ----------------------------------------------------------
# Client Profile (drill-down)
# ----------------------------------------------------------
@app.route("/client/<int:client_id>")
def client_profile(client_id: int):
    client = database.fetch_client(client_id)
    if not client:
        flash("Client not found.", "error")
        return redirect(url_for("clients_page"))

    # Ensure fields + normalize dates for templates
    client.setdefault("status", "Onboarded")
    client.setdefault("customer_cluster", "")
    client.setdefault("notes", "")
    for key in ("created_at", "updated_at"):
        val = client.get(key)
        if val and hasattr(val, "strftime"):
            pass  # keep object, template will handle
        elif val:
            client[key] = str(val)

    # Related data
    comms = database.get_communication_logs(client_id) or []
    sales = database.get_sales_records(client_id) or []
    sent_jsons = database.get_client_sent_jsons(client_id) or []
    products = database.get_client_products(client_id) or []
    client_product_ids = [p["id"] for p in products]
    for p in products:
        p.setdefault("type", p.get("category") or "")
        p.setdefault("sub_type", p.get("subtype") or "")
        sp = p.get("specs") or []
        if isinstance(sp, str):
            try: sp = json.loads(sp)
            except: sp = [sp] if sp else []
        p["specs"] = sp
    for item in comms + sales + sent_jsons:
        for k in ("log_date", "sale_date", "sent_date"):
            v = item.get(k)
            if hasattr(v, "strftime"):
                item[k] = v.strftime("%Y-%m-%d")
            elif v:
                item[k] = str(v)[:10]

    # Dispatch countries (list only, no maps)
    deliveries = database.get_deliveries(client_id) or []
    countries = sorted({d.get("country") for d in deliveries if d.get("country")})

    # All products for assignment + json upload selector
    all_products = database.get_all_products() or []
    products_for_ui = []
    for p in all_products:
        specs = p.get("specs") or []
        if isinstance(specs, str):
            try:
                specs = json.loads(specs)
            except:
                specs = [specs] if specs else []
        products_for_ui.append({
            "id": p.get("id"),
            "name": p.get("name") or "",
            "type": p.get("type") or p.get("category") or "",
            "sub_type": p.get("sub_type") or p.get("subtype") or "",
            "specs": specs
        })

    # Simple system / comm summary for "Requests & Communication History"
    system_logs = []
    try:
        if not database.is_demo_mode():
            database.ensure_new_feature_tables()
        system_logs = database.query_system_logs(limit=20) or []
    except:
        pass

    return render_template(
        "client_profile.html",
        client=client,
        comms=comms,
        sales=sales,
        sent_jsons=sent_jsons,
        products=products,
        countries=countries,
        all_products=all_products,
        products_for_ui=products_for_ui,
        client_product_ids=client_product_ids,
        system_logs=system_logs,
        status_colors=STATUS_COLORS,
        product_types=PRODUCT_TYPES,
    )

@app.route("/client/<int:client_id>/update", methods=["POST"])
def update_client_basic(client_id: int):
    payload = {
        "name": request.form.get("name", "").strip(),
        "email": request.form.get("email") or None,
        "industry": request.form.get("industry") or None,
        "web_store_url": request.form.get("web_store_url") or None,
        "status": request.form.get("status") or "Onboarded",
        "customer_cluster": request.form.get("customer_cluster") or None,
        "notes": request.form.get("notes") or None,
    }
    # API kit optional
    for k in ("api_pdf", "json_file", "product_specs"):
        if k in request.form:
            payload[k] = request.form.get(k) == "on"

    try:
        database.update_client(client_id, payload)
        flash("Client updated.", "success")
    except Exception as e:
        flash(f"Update failed: {e}", "error")
    return redirect(url_for("client_profile", client_id=client_id))

@app.route("/client/<int:client_id>/add_comm", methods=["POST"])
def add_comm(client_id: int):
    date = request.form.get("log_date") or datetime.now().strftime("%Y-%m-%d")
    event = (request.form.get("event") or "").strip()
    if event:
        try:
            database.add_communication_log(client_id, date, event)
            flash("Communication log added.", "success")
        except Exception as e:
            flash(f"Failed: {e}", "error")
    return redirect(url_for("client_profile", client_id=client_id))

@app.route("/api/check_existing_json", methods=["POST"])
def api_check_existing_json():
    """Sub function for client gen: compare specs (incl qty) before generate."""
    spec = {
        "quantity": request.form.get("size_deck") or request.form.get("quantity"),
        "card_stock": request.form.get("card_stock"),
        "packaging": request.form.get("packaging"),
        "custom": request.form.get("type_sel") or request.form.get("custom") or "Custom",
        "front_design": request.form.get("image_text_front") or request.form.get("front_design"),
        "back_design": request.form.get("image_text_back") or request.form.get("back_design"),
    }
    prod = request.form.get("product")
    match = database.find_matching_json_template(spec, prod)
    if match:
        fname = match.get("template_name") or match.get("name") or "template.json"
        match["download_url"] = url_for("download_json", filename=fname)
        return jsonify({"match": True, "template": match})
    return jsonify({"match": False})


@app.route("/client/<int:client_id>/add_json", methods=["POST"])
def add_json_for_client(client_id: int):
    # New flow: detailed form fields from JSON tab (no uploaded file required)
    # Falls back to legacy file upload if present.
    product = (request.form.get("product") or "").strip() or None

    # Collect rich form values for summary + processor
    card_stock = request.form.get("card_stock") or ""
    size_deck = request.form.get("size_deck") or "1"
    printing = request.form.get("printing") or ""
    finish = request.form.get("finish") or ""
    packaging = request.form.get("packaging") or ""
    seal = request.form.get("seal") or ""
    eff =request.form.get("effect") or "CMYK"
    card_sel = request.form.get("card_selection_mode") or ""
    type_sel = request.form.get("type_sel") or "Custom"
    store_pt = request.form.get("store_product_type") or ""
    img_front = request.form.get("image_text_front") or ""
    img_back = request.form.get("image_text_back") or ""

    # New: 3 separate material path inputs (unique per Card Stock / Printing / Finish)
    mp_card = (request.form.get("material_card_stock") or "1111,1111,1111").strip()
    mp_print = (request.form.get("material_printing") or "1111,1111,1111").strip()
    mp_finish = (request.form.get("material_finish") or "1111,1111,1111").strip()
    # Use mechanism with a combined paths value (or primary). Here we combine for distinctness.
    material_paths = f"{mp_card},{mp_print},{mp_finish}".strip(",").replace(",,", ",")

    # Build human summary list for display (replaces old product_specs everywhere)
    # Note: product name and store type are omitted from display per request
    summary = []
    if card_stock:
        summary.append(f"Card Stock: {card_stock}")
    try:
        qty_i = int(size_deck)
        if qty_i < 1: qty_i = 1
    except:
        qty_i = 1
    summary.append(f"Quantity: {qty_i}")
    if printing:
        summary.append(f"Printing: {printing}")
    if finish:
        summary.append(f"Finish: {finish}")
    if packaging:
        summary.append(f"Packaging: {packaging}")
    if seal:
        summary.append(f"Seal: {seal}")
    if card_sel:
        summary.append(f"Card Selection: {card_sel}")
    summary.append(f"Custom: {type_sel}")
    if img_front:
        summary.append(f"Front Design: {img_front}")
    if img_back:
        summary.append(f"Back Design: {img_back}")
    if eff:
        summary.append(f"Effect: {eff}")

    # Filter for actual stored product_specs (no product name, no store type)
    specs_for_record = [s for s in summary if "Store" not in s]

    # Map design modes
    def _mode(v: str) -> str:
        v = (v or "").lower()
        if "different" in v:
            return "different"
        return "same"
    front_mode = _mode(img_front)
    back_mode = _mode(img_back)

    uploaded = request.files.get("json_file")
    legacy_specs = None
    if uploaded and allowed_file(uploaded.filename):
        uploaded.filename = sanitize_filename(uploaded.filename)
        specs_raw = request.form.get("product_specs") or ""
        legacy_specs = [s.strip() for s in specs_raw.split(",") if s.strip()] if specs_raw else None
        try:
            database.save_client_json_send(client_id, uploaded, product=product, product_specs=legacy_specs or specs_for_record)
            flash("JSON template uploaded and recorded.", "success")
        except Exception as e:
            flash(f"Upload failed: {e}", "error")
        return redirect(url_for("client_profile", client_id=client_id))

    # NEW GENERATE FLOW (preferred)
    if not product:
        flash("Please select a Sub Type Product.", "error")
        return redirect(url_for("client_profile", client_id=client_id))

    # REUSE support (from comparison "yes, download existing + update history")
    # IMPORTANT: matching is now scoped to the *product* (same Sub Type Product), not per-client.
    # So Client B requesting identical specs for the same product as Client A will reuse Client A's file.
    # A new client_json_sends row is added so the JSON template history includes both clients.
    reuse_tid = request.form.get("reuse_template_id")
    if reuse_tid:
        try:
            tid = int(reuse_tid)
            sp_json = json.dumps(specs_for_record) if specs_for_record else None
            if database.is_demo_mode():
                new_sid = max([s.get("id",0) for s in getattr(database, '_DEMO_CLIENT_JSON_SENDS', [])], default=0) + 1
                getattr(database, '_DEMO_CLIENT_JSON_SENDS', []).append({
                    "id": new_sid, "client_id": client_id, "json_template_id": tid,
                    "sent_date": datetime.now().strftime("%Y-%m-%d"), "product": product, "product_specs": specs_for_record or []
                })
            else:
                database._execute(
                    "INSERT INTO client_json_sends (client_id, json_template_id, sent_date, product, product_specs) VALUES (%s, %s, CURDATE(), %s, %s)",
                    (client_id, tid, product, sp_json)
                )
            try:
                database.add_communication_log(client_id, datetime.now().strftime("%Y-%m-%d"), f"Reused existing JSON for {product}")
            except: pass
            fname = "template.json"
            try:
                for t in (database.get_all_json_templates() or []):
                    if t.get("id") == tid: fname = t.get("name") or fname
            except: pass
            return jsonify({"success": True, "reused": True, "download_url": url_for("download_json", filename=fname)})
        except Exception as ex:
            return jsonify({"success": False, "error": str(ex)}), 400

    # Build short config exactly like json-processor's "new request.json"
    tuck_extra = request.form.get("tuck_extra") or ""
    if packaging in ["Custom Tuck Box", "Custom Tin Box"]:

        raw_prop = {
            "back design mode": back_mode,
            "front design mode": front_mode,
            "Customized Model" : "Easy"
        }
    else :
        raw_prop = {
            "back design mode": back_mode,
            "front design mode": front_mode
            
        }


    client_obj = database.fetch_client(client_id) or {}
    eff = request.form.get("printing_effect") or request.form.get("finish") or ""
    tuck_extra = request.form.get("tuck_extra") or ""
    short_config = {
        "clientname": client_obj.get("name") or f"client_{client_id}",
        "product": product,
        "qty": qty_i,
        "material paths": material_paths,
        "properties": raw_prop,
        "printing_effects" : eff,
        "packaging": packaging,
        "tuck-extra" : tuck_extra
    }

    # Generate using the ported mechanism (returns the template directly)
    try:
        template_json = process_json_config(short_config)
    except Exception as ex:
        flash(f"Failed to generate from processor: {ex}", "error")
        return redirect(url_for("client_profile", client_id=client_id))

    # compute derived for response/download (override used in save)
    def _c(s):
        s = str(s or "").encode('ascii', 'ignore').decode('ascii')
        s = re.sub(r'[^\w\-.]', '_', s)
        s = re.sub(r'_+', '_', s).strip('_') or "part"
        return s
    base = _c(product or "Template")
    derived_name = f"{base}{datetime.now().strftime('%Y%m%d')}.json"
    if not derived_name.lower().endswith(".json"):
        derived_name += ".json"

    try:
        # Save the final *template* (no "json" wrapper)
        tid = database.save_client_json_send(
            client_id,
            uploaded_file=None,
            product=product,
            product_specs=specs_for_record,
            generated_json=template_json,
            override_filename=derived_name
        )
        # auto comm log on generate
        try:
            event = f"Generated JSON template for {product} (qty:{qty_i}, card_stock:{card_stock}, packaging:{packaging})"
            database.add_communication_log(client_id, datetime.now().strftime("%Y-%m-%d"), event)
        except: pass
        # JS fetch path: no redirect, return download info
        if request.form.get("card_stock") or request.form.get("material_card_stock"):
            return jsonify({"success": True, "download_url": url_for("download_json", filename=derived_name)})
        flash("JSON template generated via processor and sent.", "success")
    except Exception as e:
        if request.form.get("card_stock") or request.form.get("material_card_stock"):
            return jsonify({"success": False, "error": str(e)}), 400
        flash(f"Save failed: {e}", "error")

    return redirect(url_for("client_profile", client_id=client_id))
@app.route("/client/<int:client_id>/add_delivery", methods=["POST"])
def add_delivery(client_id: int):
    country = (request.form.get("country") or "").strip()
    count = int(request.form.get("address_count") or 1)
    ddate = request.form.get("delivered_date") or None
    if country:
        try:
            database.add_delivery(client_id, country, count, ddate)
            flash("Delivery / dispatch country added.", "success")
        except Exception as e:
            flash(f"Failed: {e}", "error")
    return redirect(url_for("client_profile", client_id=client_id))

@app.route("/client/<int:client_id>/add_product", methods=["POST"])
def add_product_to_client(client_id):
    try:
        pid = int(request.form.get("product_id"))
        current = [p["id"] for p in (database.get_client_products(client_id) or [])]
        if pid not in current:
            current.append(pid)
            database.set_client_products(client_id, current)
            flash("Product added to client's store.", "success")
        else:
            flash("Product already assigned.", "info")
    except Exception as e:
        flash(f"Failed to add product: {e}", "error")
    return redirect(url_for("client_profile", client_id=client_id))

# ----------------------------------------------------------
# Products
# ----------------------------------------------------------
@app.route("/products")
def products_page():
    products = get_products_for_display()

    q = (request.args.get("q") or "").lower().strip()
    ptype = (request.args.get("type") or "").strip()

    filtered = []
    for p in products:
        if q and q not in (p.get("name", "") + " " + (p.get("type", "") or "")).lower():
            continue
        if ptype and p.get("type") != ptype:
            continue
        # attach clients count preview
        try:
            clients = database.get_clients_for_product(p["id"]) or []
            p["client_names"] = [c.get("name") for c in clients]
        except:
            p["client_names"] = []
        filtered.append(p)

    total = len(products)
    types = PRODUCT_TYPES

    return render_template(
        "products.html",
        products=filtered,
        total=total,
        types=types,
        current_q=q,
        current_type=ptype,
    )

@app.route("/products/add", methods=["POST"])
def add_product():
    name = (request.form.get("name") or "").strip()
    ptype = request.form.get("type") or "Custom Card Decks"
    sub_type = (request.form.get("sub_type") or "").strip()
    specs_str = (request.form.get("specs") or "").strip()

    if not name:
        flash("Product name (sub type product) is required.", "error")
        return redirect(url_for("products_page"))

    try:
        specs_l = [s.strip() for s in specs_str.split(",") if s.strip()] if specs_str else None
        pid = database.create_product(name, category=ptype, specs=specs_l, subtype=sub_type)
        flash("Product added.", "success")
    except Exception as e:
        flash(f"Add product failed: {e}", "error")
    return redirect(url_for("products_page"))

@app.route("/product/<int:product_id>/upload_json", methods=["POST"])
def upload_json_for_product(product_id: int):
    """Upload JSON under a product with column metadata (same dropdown style as client profile)."""
    uploaded = request.files.get("json_file")
    qty = request.form.get("quantity") or request.form.get("size_deck") or "1"
    card = request.form.get("card_stock") or ""
    packg = request.form.get("packaging") or ""
    cust = request.form.get("custom") or request.form.get("type_sel") or "Custom"
    front = request.form.get("front_design") or request.form.get("image_text_front") or ""
    back = request.form.get("back_design") or request.form.get("image_text_back") or ""

    if not uploaded or not allowed_file(uploaded.filename):
        flash("Select a valid .json file.", "error")
        return redirect(url_for("product_profile", product_id=product_id))

    uploaded.filename = sanitize_filename(uploaded.filename)

    specs_dict = {
        "quantity": qty,
        "card_stock": card,
        "packaging": packg,
        "custom": cust,
        "front_design": front,
        "back_design": back
    }

    try:
        # derive + save file + template + link to product (no client send needed)
        def _c(s):
            s = str(s or "").encode('ascii','ignore').decode('ascii')
            s = re.sub(r'[^\w\-.]', '_', s)
            return re.sub(r'_+', '_', s).strip('_') or "part"
        base = _c( "Product" + str(product_id) )
        derived = f"{base}{datetime.now().strftime('%Y%m%d')}.json"
        if not derived.lower().endswith(".json"): derived += ".json"
        os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
        save_path = os.path.join(app.config["UPLOAD_FOLDER"], derived)
        with open(save_path, "wb") as f:
            uploaded.stream.seek(0)
            f.write(uploaded.stream.read())

        tid = 10000 + product_id
        try:
            if not database.is_demo_mode():
                tid = database.execute_raw("INSERT INTO json_templates (name, file_path) VALUES (%s, %s)", (derived, save_path))
                database.execute_raw(
                    "INSERT INTO product_json_files (product_id, specs, json_template_id) VALUES (%s, %s, %s)",
                    (product_id, json.dumps(specs_dict), tid)
                )
            else:
                # demo: append fake entry so table can pick it in some flows
                database._DEMO_JSON_TEMPLATES.append({"id": tid, "name": derived, "file_path": "DEMO:" + derived})
        except Exception:
            pass
        flash("JSON uploaded and linked to product.", "success")
    except Exception as e:
        flash(f"Upload failed: {e}", "error")

    return redirect(url_for("product_profile", product_id=product_id))


@app.route("/product/<int:product_id>")
def product_profile(product_id: int):
    try:
        if not database.is_demo_mode():
            database.ensure_new_feature_tables()
    except Exception:
        pass
    prod = None
    for p in (database.get_all_products() or []):
        if p.get("id") == product_id:
            prod = p
            break
    if not prod:
        flash("Product not found.", "error")
        return redirect(url_for("products_page"))

    prod.setdefault("type", prod.get("category") or "Custom Card Decks")
    prod.setdefault("sub_type", prod.get("subtype") or "")
    prod.setdefault("name", prod.get("name") or "")

    # Clients that sell it
    try:
        clients = database.get_clients_for_product(product_id) or []
    except:
        clients = []

    # Related JSONs for this product (from product_json_files or sends)
    json_files = []
    try:
        json_files = database.get_product_json_files(product_id) or []
        for jf in json_files:
            # ensure flat keys exist for the 6-col table
            sp = jf.get('specs') or {}
            if isinstance(sp, (str, bytes)):
                try: sp = json.loads(sp)
                except: sp = {}
            if isinstance(sp, list):
                d = {}
                for it in sp:
                    if isinstance(it,str) and ':' in it: 
                        k,v = [x.strip() for x in it.split(':',1)]; d[k.lower().replace(' ','_')] = v
                sp = d
            if isinstance(sp, dict):
                if "front" in sp and "front_design" not in sp:
                    sp["front_design"] = sp["front"]
                if "back" in sp and "back_design" not in sp:
                    sp["back_design"] = sp["back"]
            jf.setdefault('quantity', sp.get('quantity') or sp.get('size_of_deck') or '—')
            jf.setdefault('card_stock', sp.get('card_stock') or sp.get('Card Stock') or '—')
            jf.setdefault('packaging', sp.get('packaging') or sp.get('Packaging') or '—')
            jf.setdefault('custom', sp.get('custom') or sp.get('type_sel') or 'Custom')
            jf.setdefault('front_design', sp.get('front_design') or sp.get('Front') or sp.get('front') or '—')
            jf.setdefault('back_design', sp.get('back_design') or sp.get('Back') or sp.get('back') or '—')
            # map short internal mode to friendly display value
            fd = str(jf.get('front_design', '')).lower()
            if fd == 'same':
                jf['front_design'] = 'Same for all front'
            elif fd == 'different':
                jf['front_design'] = 'Different for all front'
            bd = str(jf.get('back_design', '')).lower()
            if bd == 'same':
                jf['back_design'] = 'Same for all back'
            elif bd == 'different':
                jf['back_design'] = 'Different for all backs'
    except:
        pass

    # For each json, we can fetch history later in the popup route

    return render_template(
        "product_profile.html",
        product=prod,
        clients=clients,
        json_files=json_files,
    )
@app.route("/products/delete/<int:product_id>", methods=["DELETE", "POST"])
def delete_product(product_id: int):
    try:
        # Check for dependencies
        clients = database.get_clients_for_product(product_id) or []
        if clients:
            return jsonify({
                "success": False,
                "error": f"Cannot delete product. It is currently used by {len(clients)} client(s)."
            }), 400

        # Perform deletion
        success = database.delete_product(product_id)

        if success:
            return jsonify({
                "success": True,
                "message": "Product deleted successfully."
            })
        else:
            return jsonify({
                "success": False,
                "error": "Product not found or could not be deleted."
            }), 404

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

# JSON history popup data (AJAX friendly)
@app.route("/json/<int:json_template_id>/history")
def json_history(json_template_id: int):
    # Find usages
    usages = []
    try:
        usages = database.get_json_template_usage(json_template_id) or []
    except:
        pass

    # Basic info
    template = None
    try:
        for t in (database.get_all_json_templates() or []):
            if t.get("id") == json_template_id:
                template = t
                break
    except:
        pass

    return render_template(
        "_json_history_modal.html",
        template=template,
        usages=usages,
    )

@app.route("/uploads/json_files/<path:filename>")
def download_json(filename):
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename, as_attachment=True)

# ----------------------------------------------------------
# Clusters
# ----------------------------------------------------------
@app.route("/clusters")
def clusters_page():
    try:
        if not database.is_demo_mode():
            database.ensure_new_feature_tables()
    except Exception:
        pass
    clients = get_clients_for_display()

    # Group by cluster
    from collections import defaultdict
    groups = defaultdict(list)
    for c in clients:
        cl = c.get("customer_cluster") or "Unclustered"
        groups[cl].append(c)

    cluster_list = []
    for name, members in groups.items():
        preview = [m.get("name") for m in members[:5]]
        overflow = max(0, len(members) - 5)
        cluster_list.append({
            "name": name,
            "count": len(members),
            "members": members,
            "preview": preview,
            "overflow": overflow,
        })

    # Sort by count desc
    cluster_list.sort(key=lambda x: -x["count"])

    total_clusters = len([c for c in cluster_list if c["name"] != "Unclustered"])

    return render_template(
        "clusters.html",
        clusters=cluster_list,
        total_clusters=total_clusters,
        total_clients=len(clients),
        all_clients=clients,
    )

@app.route("/clusters/add", methods=["POST"])
def add_cluster():
    # Since we use label on client, creating a cluster is just informational.
    # We create it by assigning at least one client later.
    new_name = (request.form.get("name") or "").strip()
    if new_name:
        flash(f'Cluster label "{new_name}" ready. Assign clients via Edit on the card or client profile.', "success")
    return redirect(url_for("clusters_page"))

@app.route("/clusters/<cluster_name>/assign", methods=["POST"])
def assign_to_cluster(cluster_name: str):
    # client_ids from form (multi)
    selected = request.form.getlist("client_ids")
    count = 0
    for cid_str in selected:
        try:
            cid = int(cid_str)
            database.update_client(cid, {"customer_cluster": cluster_name if cluster_name != "Unclustered" else None})
            count += 1
        except:
            pass
    flash(f"Updated {count} client(s) to cluster '{cluster_name}'.", "success")
    return redirect(url_for("clusters_page"))

@app.route("/clusters/<cluster_name>/delete", methods=["POST"])
def delete_cluster(cluster_name: str):
    # Unassign all clients with this cluster
    clients = get_clients_for_display()
    count = 0
    for c in clients:
        if (c.get("customer_cluster") or "") == cluster_name:
            try:
                database.update_client(c["id"], {"customer_cluster": None})
                count += 1
            except:
                pass
    flash(f"Unassigned {count} clients from '{cluster_name}'. (Cluster label removed)", "success")
    return redirect(url_for("clusters_page"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        u = (request.form.get("username") or "").strip()
        p = (request.form.get("password") or "").strip()
        if u == DEMO_USER and p == DEMO_PASS:
            session["logged_in"] = True
            session["user"] = u
            flash("Logged in with full privileges (demo admin). MySQL operations available via the configured DB user.")
            nxt = request.args.get("next") or url_for("clients_page")
            return redirect(nxt)
        flash("Invalid credentials. Use the printed demo account.")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("Logged out.")
    return redirect(url_for("login"))

# ----------------------------------------------------------
# Simple seed for MySQL (call manually if needed)
# ----------------------------------------------------------
@app.route("/admin/seed", methods=["POST"])
def admin_seed():
    try:
        if hasattr(database, "clear_and_seed_test_data"):
            database.clear_and_seed_test_data()
            flash("Database seeded with rich test data.", "success")
        else:
            flash("Seed function not available.", "error")
    except Exception as e:
        flash(f"Seed failed: {e}", "error")
    return redirect(url_for("clients_page"))

# ----------------------------------------------------------
# Run
# ----------------------------------------------------------
if __name__ == "__main__":
    # Auto ensure basic tables/columns on start (MySQL)
    try:
        if not database.is_demo_mode():
            database.ensure_new_feature_tables()
    except Exception as ex:
        print("Schema ensure warning:", ex)

    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)