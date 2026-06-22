"""
Flask-based Client Management System
Simple production-oriented app (no Streamlit).

Features per spec:
- 3 main sections via top navbar: Clients, Clusters, Products
- Clean enterprise SaaS Tailwind UI (play CDN)
- MySQL only for now (switchable stub prepared in database.py)
- Client CRUD + status (Onboarded/Active/Requested/Need help)
- Client profile with sidebar + tabs (Products / Requests & Communication / Json Files)
- Clusters as label-based cards with member previews + management
- Products catalog + drill-down with spec cards + JSON history popup

Run:
  pip install flask pymysql python-dotenv
  python app.py
"""

from __future__ import annotations
import re
import os
import json
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash, send_from_directory, jsonify
from werkzeug.utils import secure_filename

import database

# ----------------------------------------------------------
# Flask setup
# ----------------------------------------------------------
app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET", "dev-secret-change-in-prod")
app.config["UPLOAD_FOLDER"] = database.UPLOAD_DIR
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

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

@app.route("/client/<int:client_id>/add_json", methods=["POST"])
def add_json_for_client(client_id: int):
    uploaded = request.files.get("json_file")
    product = request.form.get("product") or None
    specs_raw = request.form.get("product_specs") or ""
    specs = [s.strip() for s in specs_raw.split(",") if s.strip()] if specs_raw else None

    if not uploaded or not allowed_file(uploaded.filename):
        flash("Please upload a valid .json file.", "error")
        return redirect(url_for("client_profile", client_id=client_id))

    # Sanitize uploaded name (though save derives its own from product+specs)
    uploaded.filename = sanitize_filename(uploaded.filename)

    try:
        database.save_client_json_send(client_id, uploaded, product=product, product_specs=specs)
        flash("JSON template uploaded and recorded.", "success")
    except Exception as e:
        flash(f"Upload failed: {e}", "error")

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
    except:
        pass

    # For each json, we can fetch history later in the popup route

    return render_template(
        "product_profile.html",
        product=prod,
        clients=clients,
        json_files=json_files,
    )

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