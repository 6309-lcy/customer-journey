# JSON Processor — n8n Template Generator (Local Test Tool)

Raw local tool that takes a short config JSON (like `n8n/new request.json`) and outputs the full order **template** exactly as produced by the n8n Function Node you pasted:

```js
// === Function Node: Generate Full Template ===
// (Run Once for All Items)
```

It replicates the logic 1:1 in Python.

**Not for production.** For local testing + CSV logging of generations.

## Input format (the file you upload)

The uploaded `.json` should be the config object, for example (see `n8n/new request.json`):

```json
{
  "clientname": "anson",
  "product": "booster pack",
  "qty": 30,
  "material paths": "500000,5000000,500000",
  "properties": {
    "back design mode": "same",
    "front design mode": "same"
  }
}
```

The processor also accepts a wrapper `{ "data": <config> }` (matching `$input.first().json.data`).

## Output format

Exactly:

```json
{
  "json": {
    "template": { /* full order with items[0].customizeProject.designs, orderTotals, REPLACE placeholders, etc. */ },
    "thirdOrderId": "replace_order_number",
    "quantity": 30
  }
}
```

This is ready to be used as the template in your n8n flow (you can save it as `template_replace_order_number.json` etc.).

## Run (Windows PowerShell)

1. Open PowerShell and go to this folder:

```powershell
cd "C:\Users\lcy20\OneDrive\桌面\QP\json-processor"
```

2. Install dependencies (one time):

```powershell
pip install -r requirements.txt
```

3. Start the server (local only):

```powershell
python -m uvicorn app:app --reload
```

   **To let other people on your network access and download the generated JSONs**, start like this instead:

```powershell
python -m uvicorn app:app --host 0.0.0.0 --port 8000 --reload
```

   Then give them your computer's LAN IP (example: `http://192.168.1.105:8000`).

4. Open in your browser:

```
http://localhost:8000
```

   Other users on the same WiFi/LAN can open the same address using your LAN IP.

## How it works

- Drag & drop or select a `.json` file
- Click **Process JSON**
- Backend:
  - Validates + parses the JSON
  - Runs a placeholder "improvement" step (see `app.py:process_json`)
  - Saves original copy → `data/uploads/`
  - Saves processed copy → `data/processed/`
  - Appends one row using your exact CSV columns (Client Name, Product, Qty, Date Join, Template, Client Email) to `data/processing_log.csv`
- Frontend shows the improved JSON + download / copy buttons
- Processing history table loads recent CSV rows

## Current transformation (exact match to your n8n Function Node)

- Reads `qty`, `"material paths"`, and optional `properties` from the uploaded config
- Creates N `pageContentDesigns` (where N = qty)
- Produces the full `template` with Card_Front + Card_Back + Booster_Pack content
- Fixed addresses + calculated orderTotals
- Returns precisely:
  ```json
  { "json": { "template": <full order>, "thirdOrderId": "...", "quantity": N } }
  ```

## Update the logic later

If the n8n node changes in the future:

1. Edit only `process_json()` in `app.py`
2. (Optional) extend the CSV columns in the endpoint + `ensure_csv_header`
3. The rest of the app (saving, frontend, logging) stays the same
4. Restart server (or let `--reload` handle it)

## Sharing the CSV + Output JSONs with other people

The generated JSON files live only on **your** computer (`data/processed/`).

### Easy way to share

1. Start the server so other machines can reach it (see run instructions above, use `--host 0.0.0.0`).

2. On the web page, click the big blue button:
   > **Download shareable CSV (with links)**

3. This generates a new CSV file where the **"Download Link"** column contains real URLs like:
   ```
   http://192.168.1.105:8000/api/download/processed/20260612_..._improved_xxx.json
   ```

4. Send this CSV to your colleagues (via email, Teams, Google Drive, etc.).

5. When they open the CSV (Excel, Google Sheets, etc.), they can click (or copy) the links and download the exact generated JSON templates you produced.

The links only work while **your** computer is running the server and is reachable on the network.

### From the web UI
- The history table on the page shows the output filenames as direct download links.
- If you (or someone else) opens the page using the LAN IP, the links will work for them too.

### Internal use focus
- The web UI history table is the main way for internal users to see past generations and directly download the output JSON templates.
- There is a "Download Log CSV" button for people who need the raw log in Excel.
- We intentionally removed the public "shareable CSV with links" export — no need to send CSV files around.

## Useful files

- `data/processing_log.csv` — the structured log (open in Excel)
- `data/uploads/` — every original config you uploaded
- `data/processed/` — every generated template JSON (the "Template" column points here)

## Stop the server

In the terminal: `Ctrl + C`

## Notes

- Runs only on localhost (127.0.0.1:8000)
- All data stays on your machine
- No auth, no rate limits — local test only
- You can edit `app.py` freely while `--reload` is active

---

## Deployment

This started as a raw local tool. If you want to run it properly (team access, always-on, etc.):

### Recommended: Docker + Volume (easiest & cleanest)

1. In the `json-processor/` folder:

```bash
docker compose up -d --build
```

2. The data (uploads, generated templates, CSV) lives in a named Docker volume called `json_processor_data`.

3. Access at `http://your-server-ip:8000`

### Important deployment considerations

**Security (critical)**
- Currently there is **no authentication**. Anyone who can reach the port can upload configs and download all generated templates.
- For real use, you should at least:
  - Put it behind a reverse proxy with basic auth (Caddy, Nginx + htpasswd, or Traefik)
  - Or run it only on an internal network / Tailscale / WireGuard
  - Or add simple auth to the app (let me know if you want this added)

**Persistent storage**
- The `data/` folder must survive container restarts. The provided `docker-compose.yml` uses a volume for this.

**Making download links work publicly**
- When you put this behind a domain + HTTPS (Caddy, Nginx, Traefik), the "Download shareable CSV" feature will automatically generate correct public links (it respects `X-Forwarded-Proto` and the `host` header).

**Environment variables**
- `DATA_DIR` — override the data directory (useful in containers)

### Quick & dirty temporary sharing (no real server)

If you just want to share with a few people for a day:

```bash
# On your local machine
python -m uvicorn app:app --host 0.0.0.0 --port 8000

# Then use ngrok or Cloudflare Tunnel
ngrok http 8000
# or
cloudflared tunnel --url http://localhost:8000
```

Give people the temporary URL. The shareable CSV links will work while the tunnel is alive.

### Want help going further?

Tell me your target environment and I can prepare it:

- Add **basic authentication** (username/password)
- Switch to **proper database** (SQLite or Postgres) instead of CSV for the log
- Store generated JSONs in **S3 / MinIO** instead of local disk
- Add **HTTPS + domain** config (Caddyfile example)
- Merge this into your existing n8n `docker-compose.yml`
- Make a production `docker-compose` with reverse proxy + automatic HTTPS

Just say the word (e.g. "add basic auth + docker with traefik" or "I have a VPS, give me the full setup").

This is still relatively small, so it can go from local prototype to "team tool" quite quickly.
