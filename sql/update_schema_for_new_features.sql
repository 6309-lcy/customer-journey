-- ============================================================
-- Schema updates for new features requested:
-- - API kit flags on clients (for CRUD search)
-- - Products management + client associations
-- - JSON template uploads/sends per client
-- - Product JSON files association
-- - Central JSON templates catalog (optional normalization)
-- Run this against your 'cj' database.
-- ============================================================

USE cj;

-- 1. Extend clients with API kit checkboxes (used in CRUD advanced search)
ALTER TABLE clients
  ADD COLUMN api_pdf BOOLEAN NOT NULL DEFAULT FALSE,
  ADD COLUMN json_file BOOLEAN NOT NULL DEFAULT FALSE,
  ADD COLUMN product_specs BOOLEAN NOT NULL DEFAULT FALSE;

-- 2. Products master table
CREATE TABLE IF NOT EXISTS products (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(255) NOT NULL UNIQUE,
    category VARCHAR(255) NULL,
    specs JSON NULL,                    -- e.g. ["specA", "specB", "color:red"]
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

-- 3. Client <-> Product (clients that sell / are associated with products)
CREATE TABLE IF NOT EXISTS client_products (
    client_id INT NOT NULL,
    product_id INT NOT NULL,
    PRIMARY KEY (client_id, product_id),
    FOREIGN KEY (client_id) REFERENCES clients(id) ON DELETE CASCADE,
    FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE
);

-- 4. Master JSON templates (for central "JSON template" tab and relevance)
CREATE TABLE IF NOT EXISTS json_templates (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(255) NOT NULL,         -- user-friendly name or original filename
    file_path VARCHAR(500) NOT NULL,    -- relative path to stored file
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 5. Client sent JSON history (the "json template upload" in client profile)
-- Links to a json_template, plus context (product, specs) at time of sending
CREATE TABLE IF NOT EXISTS client_json_sends (
    id INT AUTO_INCREMENT PRIMARY KEY,
    client_id INT NOT NULL,
    json_template_id INT NOT NULL,
    sent_date DATE NOT NULL,
    product VARCHAR(255) NULL,
    product_specs JSON NULL,            -- e.g. ["spec1", "version:2"]
    FOREIGN KEY (client_id) REFERENCES clients(id) ON DELETE CASCADE,
    FOREIGN KEY (json_template_id) REFERENCES json_templates(id) ON DELETE CASCADE
);

-- 6. Product <-> JSON files (for "related json file with different specs" in Products tab)
-- Allows a product to have multiple JSON variants for different spec combinations
CREATE TABLE IF NOT EXISTS product_json_files (
    id INT AUTO_INCREMENT PRIMARY KEY,
    product_id INT NOT NULL,
    specs JSON NULL,                    -- the spec combination this JSON is for
    json_template_id INT NOT NULL,      -- link to the actual file/template
    FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE,
    FOREIGN KEY (json_template_id) REFERENCES json_templates(id) ON DELETE CASCADE
);

-- Helpful indexes
CREATE INDEX idx_clients_api_pdf ON clients(api_pdf);
CREATE INDEX idx_clients_json_file ON clients(json_file);
CREATE INDEX idx_clients_product_specs ON clients(product_specs);
CREATE INDEX idx_products_name ON products(name);
CREATE INDEX idx_products_category ON products(category);
CREATE INDEX idx_client_json_sends_client ON client_json_sends(client_id);
CREATE INDEX idx_client_json_sends_product ON client_json_sends(product);

-- Optional seed example (remove or adapt if not wanted)
-- INSERT INTO products (name, category, specs) VALUES
-- ('Alpha API', 'Core', '["basic", "advanced"]'),
-- ('Zeta Analytics', 'Analytics', '["realtime", "batch"]');
