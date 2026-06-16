# customer-journey

Client Profile Management System (Streamlit + MySQL / Demo mode)

## Key Features
- Dedicated client profile pages (via ?client_id=)
- Communication logs, sales (with product selection), deliveries
- World map dispatch visualization (per-client + global)
- **Product slicer** on homepage for filtered sales details + exportable table
- Products catalog (table view with flat client entries, downloadable related JSONs)
- JSON Templates (single-product search returning spec-grouped results with downloadable files and client lists)
- In-profile: free-text notes, add/assign products for client, JSON template uploads (auto-renamed to e.g. Booster_Pack_20X20X20.json)
- Advanced client search (API kit checkboxes + products multi-select) + results export
- System logs query + CSV export
- Auto schema initialization (new columns/tables for products, client_products, json sends, sales.product, client notes, etc.)
- Full in-memory demo mode + "Clear & Seed Fresh Test Data" button for rich sample data
- English UI, no emojis

## Run
`ash
pip install -r requirements.txt
streamlit run main.py
`

Set USE_SAMPLE_DATA=true in .env (or copy from .env.example) for demo without MySQL.
For real MySQL (recommended for persistence): configure MYSQL_* and the app will auto-create required tables/columns on first load.

See sql/ for init and update scripts if manual setup needed.
