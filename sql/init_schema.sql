-- =====================================================================
-- client_profiles 資料表：客戶檔案 + 知識圖譜儀表板 專用
-- 請在 Supabase 專案的 SQL Editor 中一次執行此整段 SQL
-- =====================================================================

-- 啟用 pgcrypto（提供 gen_random_uuid()，若已啟用可忽略）
create extension if not exists "pgcrypto";

-- 建立主表（完全符合需求規格）
create table if not exists client_profiles (
    id uuid primary key default gen_random_uuid(),
    name text not null,
    email text not null unique,
    country text,
    from_where text,                              -- 記錄來源與希望的服務類型
    api_kit jsonb not null default '{}'::jsonb,   -- { "json": bool, "api_pdf": bool, "product_specs": bool, "last_requested": "..." }
    products jsonb not null default '[]'::jsonb,  -- ["Product A", "Product B", ...]
    customer_cluster text,                        -- 例如 "JSON_Heavy_APAC", "PDF_Only", "Mixed_Cluster"
    request_history jsonb not null default '[]'::jsonb,
    -- 範例單一記錄：
    -- {"timestamp": "2026-06-12T10:30:00Z", "template_used": "full_kit_v2", "products": ["Alpha", "Beta"], "api_type": "json", "notes": "客戶要求客製化欄位"}
    last_edited timestamptz not null default now()
);

-- 實用索引（加速查詢與篩選）
create index if not exists idx_client_profiles_email on client_profiles (email);
create index if not exists idx_client_profiles_country on client_profiles (country);
create index if not exists idx_client_profiles_cluster on client_profiles (customer_cluster);

-- JSONB GIN 索引（未來可做高效 contains / @> 查詢）
create index if not exists idx_client_profiles_products_gin on client_profiles using gin (products);
create index if not exists idx_client_profiles_api_kit_gin on client_profiles using gin (api_kit);
create index if not exists idx_client_profiles_history_gin on client_profiles using gin (request_history);

-- 自動更新 last_edited 的觸發器（強烈建議保留）
create or replace function update_last_edited_column()
returns trigger as $$
begin
    new.last_edited = now();
    return new;
end;
$$ language plpgsql;

drop trigger if exists trg_update_last_edited on client_profiles;
create trigger trg_update_last_edited
    before update on client_profiles
    for each row
    execute function update_last_edited_column();

-- =====================================================================
-- Row Level Security（RLS）設定
-- 使用 ANON KEY 時必須開啟以下 permissive policy（僅供本地/展示用途）
-- 正式上線請改用 SERVICE_ROLE_KEY + 嚴格的 RLS policy
-- =====================================================================
alter table client_profiles enable row level security;

-- 開發/展示用：允許所有操作（使用 anon key 即可從 Streamlit 直接存取）
drop policy if exists "Allow all operations for demo (anon key)" on client_profiles;
create policy "Allow all operations for demo (anon key)"
on client_profiles
for all
using (true)
with check (true);

comment on table client_profiles is 'Client Profile 主表。支援 JSONB 彈性欄位 + Knowledge Graph 節點/邊資料來源。';

-- =====================================================================
-- 種子資料（可重複執行，email 衝突時略過）
-- 包含不同 api_kit 組合、產品、cluster、request_history 範例
-- =====================================================================
insert into client_profiles
    (name, email, country, from_where, api_kit, products, customer_cluster, request_history, last_edited)
values
    (
        '測試公司 Alpha',
        'contact@alpha-tw.com',
        'Taiwan',
        '官網表單 - 需要完整 JSON API 與 PDF 規格書',
        '{
            "json": true,
            "api_pdf": true,
            "product_specs": false,
            "last_requested": "2026-06-10T08:15:00Z"
        }'::jsonb,
        '["Alpha API", "Beta Specs", "Gamma Connector"]'::jsonb,
        'JSON_Heavy_APAC',
        '[
            {
                "timestamp": "2026-06-10T08:15:00Z",
                "template_used": "full_kit_v1",
                "products": ["Alpha API", "Beta Specs"],
                "api_type": "json",
                "notes": "首次大量請求，客戶希望 3 天內回覆"
            }
        ]'::jsonb,
        now()
    ),
    (
        'EuroTech GmbH',
        'info@eurotech.de',
        'Germany',
        'LinkedIn 轉介 - 僅需 PDF 格式產品文件',
        '{
            "json": false,
            "api_pdf": true,
            "product_specs": true,
            "last_requested": "2026-06-08T14:30:00Z"
        }'::jsonb,
        '["Delta PDF Pack", "Epsilon Hardware"]'::jsonb,
        'PDF_Only_EU',
        '[
            {
                "timestamp": "2026-06-08T14:30:00Z",
                "template_used": "pdf_only",
                "products": ["Delta PDF Pack"],
                "api_type": "api_pdf",
                "notes": "德文版本優先"
            },
            {
                "timestamp": "2026-06-09T09:00:00Z",
                "template_used": "pdf_only",
                "products": ["Epsilon Hardware"],
                "api_type": "api_pdf",
                "notes": ""
            }
        ]'::jsonb,
        now()
    ),
    (
        'SG Data Solutions',
        'hello@sgdata.sg',
        'Singapore',
        'Email 詢問 - 強烈需要 JSON + 產品規格',
        '{
            "json": true,
            "api_pdf": false,
            "product_specs": true,
            "last_requested": "2026-06-11T03:45:00Z"
        }'::jsonb,
        '["Alpha API", "Zeta Analytics", "Theta Edge"]'::jsonb,
        'JSON_Heavy_APAC',
        '[
            {
                "timestamp": "2026-06-11T03:45:00Z",
                "template_used": "json_specs",
                "products": ["Alpha API", "Zeta Analytics"],
                "api_type": "json",
                "notes": "新加坡時區優先處理"
            }
        ]'::jsonb,
        now()
    ),
    (
        '北美製造 N.A. Corp',
        'procurement@na-mfg.com',
        'United States',
        '貿易展會 - 目前只想要 PDF 報價單',
        '{
            "json": false,
            "api_pdf": true,
            "product_specs": false,
            "last_requested": "2026-05-28T19:20:00Z"
        }'::jsonb,
        '["Omega Quotation"]'::jsonb,
        'PDF_Only',
        '[]'::jsonb,
        now()
    )
on conflict (email) do nothing;

-- 執行後可立即在 Supabase Table Editor 查看資料
-- 建議接著在 Authentication > Policies 確認 policy 存在（或手動調整）
