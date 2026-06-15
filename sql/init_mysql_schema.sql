-- ============================================================
-- MySQL Schema for Client Profile Management System
-- Run this in your MySQL client (e.g. MySQL Workbench, CLI, or phpMyAdmin)
-- ============================================================

CREATE DATABASE IF NOT EXISTS client_profile_db 
  CHARACTER SET utf8mb4 
  COLLATE utf8mb4_unicode_ci;

USE client_profile_db;

-- Main clients table
CREATE TABLE IF NOT EXISTS clients (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    industry VARCHAR(255),
    total_orders INT DEFAULT 0,
    total_addresses_delivered INT DEFAULT 0,
    total_order_amount DECIMAL(12,2) DEFAULT 0.00,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

-- Communication logs (date + event description)
CREATE TABLE IF NOT EXISTS communication_logs (
    id INT AUTO_INCREMENT PRIMARY KEY,
    client_id INT NOT NULL,
    log_date DATE NOT NULL,
    event TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (client_id) REFERENCES clients(id) ON DELETE CASCADE
);

-- Sales records
CREATE TABLE IF NOT EXISTS sales_records (
    id INT AUTO_INCREMENT PRIMARY KEY,
    client_id INT NOT NULL,
    sale_date DATE NOT NULL,
    description TEXT,
    quantity INT DEFAULT 0,
    amount DECIMAL(10,2) DEFAULT 0.00,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (client_id) REFERENCES clients(id) ON DELETE CASCADE
);

-- Deliveries / Dispatching countries (for world map)
CREATE TABLE IF NOT EXISTS deliveries (
    id INT AUTO_INCREMENT PRIMARY KEY,
    client_id INT NOT NULL,
    country VARCHAR(100) NOT NULL,
    address_count INT DEFAULT 1,
    delivered_date DATE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (client_id) REFERENCES clients(id) ON DELETE CASCADE
);

-- System logs (queryable on homepage)
CREATE TABLE IF NOT EXISTS system_logs (
    id INT AUTO_INCREMENT PRIMARY KEY,
    log_timestamp DATETIME NOT NULL,
    message TEXT NOT NULL,
    tags JSON,                    -- e.g. ["contract", "integration", "sales"]
    client_name VARCHAR(255),
    industry VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Helpful indexes
CREATE INDEX idx_clients_name ON clients(name);
CREATE INDEX idx_clients_industry ON clients(industry);
CREATE INDEX idx_system_logs_timestamp ON system_logs(log_timestamp);
CREATE INDEX idx_system_logs_industry ON system_logs(industry);

-- Optional: Insert some sample data for testing
INSERT INTO clients (name, industry, total_orders, total_addresses_delivered, total_order_amount) VALUES
('Acme Corp', 'Technology', 12, 45, 125000.50),
('Global Retail Ltd', 'Retail', 8, 120, 87500.00),
('HealthFirst Inc', 'Healthcare', 5, 22, 45000.00);

INSERT INTO communication_logs (client_id, log_date, event) VALUES
(1, '2025-01-15', 'Initial contact and contract discussion for API integration'),
(1, '2025-02-20', 'Follow-up meeting - signed API integration contract'),
(2, '2025-03-10', 'Demo of product catalog sync');

INSERT INTO sales_records (client_id, sale_date, description, quantity, amount) VALUES
(1, '2025-04-05', 'Sold out 30 decks', 30, 15000.00),
(2, '2025-05-12', 'Sold out 50 decks', 50, 25000.00);

INSERT INTO deliveries (client_id, country, address_count, delivered_date) VALUES
(1, 'United States', 25, '2025-04-10'),
(1, 'Canada', 12, '2025-04-15'),
(2, 'United Kingdom', 40, '2025-05-20'),
(2, 'Germany', 35, '2025-05-25'),
(3, 'Australia', 15, '2025-06-01');

INSERT INTO system_logs (log_timestamp, message, tags, client_name, industry) VALUES
('2025-06-25 10:30:00', 'customer Acme Corp required json file', '["api", "integration"]', 'Acme Corp', 'Technology'),
('2025-07-30 14:15:00', 'customer Global Retail Ltd joined us', '["onboarding"]', 'Global Retail Ltd', 'Retail'),
('2025-08-31 09:00:00', 'Customer HealthFirst Inc sold 25 unit', '["sales"]', 'HealthFirst Inc', 'Healthcare');