-- =============================================================================
-- BI DWH — Initial Schema (MVP)
-- Stack: PostgreSQL 16
-- =============================================================================

-- ------------------------------------------------------------------------------
-- Extensions
-- ------------------------------------------------------------------------------
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- ------------------------------------------------------------------------------
-- Dimensions
-- ------------------------------------------------------------------------------

CREATE TABLE dim_date (
    date_id              DATE PRIMARY KEY,
    year                 SMALLINT NOT NULL,
    quarter              SMALLINT NOT NULL,
    month                SMALLINT NOT NULL,
    month_name           VARCHAR(20) NOT NULL,
    week_of_year         SMALLINT NOT NULL,
    day_of_week          SMALLINT NOT NULL,
    day_of_month         SMALLINT NOT NULL,
    day_name             VARCHAR(20) NOT NULL,
    is_weekend           BOOLEAN NOT NULL DEFAULT FALSE,
    is_holiday_rf        BOOLEAN NOT NULL DEFAULT FALSE,
    fiscal_year          SMALLINT,
    fiscal_quarter       SMALLINT
);

CREATE TABLE dim_currency (
    currency_id          SERIAL PRIMARY KEY,
    currency_code        CHAR(3) UNIQUE NOT NULL,
    currency_name        VARCHAR(50) NOT NULL,
    is_active            BOOLEAN NOT NULL DEFAULT TRUE,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE dim_counterparty (
    counterparty_id      SERIAL PRIMARY KEY,
    source_system        VARCHAR(50) NOT NULL, -- 'amoCRM', '1C', 'manual'
    source_id            VARCHAR(255),         -- ID в исходной системе
    counterparty_name    VARCHAR(255) NOT NULL,
    counterparty_type    VARCHAR(50) NOT NULL CHECK (counterparty_type IN ('customer','supplier','partner','employee','other')),
    inn                  VARCHAR(12),
    kpp                  VARCHAR(9),
    email                VARCHAR(255),
    phone                VARCHAR(50),
    parent_counterparty_id INT REFERENCES dim_counterparty(counterparty_id),
    is_dupe_of           INT REFERENCES dim_counterparty(counterparty_id),
    is_active            BOOLEAN NOT NULL DEFAULT TRUE,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_dim_counterparty_source ON dim_counterparty(source_system, source_id);
CREATE INDEX idx_dim_counterparty_name ON dim_counterparty USING gin(counterparty_name gin_trgm_ops);

CREATE TABLE dim_product (
    product_id           SERIAL PRIMARY KEY,
    source_system        VARCHAR(50) NOT NULL,
    source_id            VARCHAR(255),
    sku                  VARCHAR(100),
    product_name         VARCHAR(255) NOT NULL,
    product_category     VARCHAR(100),
    unit                 VARCHAR(20) DEFAULT 'шт',
    is_active            BOOLEAN NOT NULL DEFAULT TRUE,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_dim_product_source ON dim_product(source_system, source_id);

CREATE TABLE dim_department (
    department_id        SERIAL PRIMARY KEY,
    department_name      VARCHAR(100) NOT NULL,
    department_code      VARCHAR(20) UNIQUE,
    parent_department_id INT REFERENCES dim_department(department_id),
    manager_name         VARCHAR(255),
    is_active            BOOLEAN NOT NULL DEFAULT TRUE,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE dim_employee (
    employee_id          SERIAL PRIMARY KEY,
    source_system        VARCHAR(50) NOT NULL,
    source_id            VARCHAR(255),
    full_name            VARCHAR(255) NOT NULL,
    department_id        INT REFERENCES dim_department(department_id),
    position_title       VARCHAR(100),
    email                VARCHAR(255),
    is_active            BOOLEAN NOT NULL DEFAULT TRUE,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Планы счетов для P&L (упрощенная Российская/МСФО гибридная структура)
CREATE TABLE dim_account (
    account_id           SERIAL PRIMARY KEY,
    account_code         VARCHAR(20) UNIQUE NOT NULL,
    account_name         VARCHAR(255) NOT NULL,
    account_type         VARCHAR(50) NOT NULL CHECK (account_type IN ('revenue','cogs','opex','capex','tax','other_income','other_expense')),
    parent_account_id    INT REFERENCES dim_account(account_id),
    pnl_section          VARCHAR(50) NOT NULL CHECK (pnl_section IN ('revenue','gross_profit','operating_profit','net_profit')),
    is_active            BOOLEAN NOT NULL DEFAULT TRUE,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ------------------------------------------------------------------------------
-- Exchange Rates
-- ------------------------------------------------------------------------------
CREATE TABLE fact_exchange_rates (
    rate_id              BIGSERIAL PRIMARY KEY,
    date_id              DATE NOT NULL REFERENCES dim_date(date_id),
    currency_from        CHAR(3) NOT NULL,
    currency_to          CHAR(3) NOT NULL DEFAULT 'RUB',
    rate_value           NUMERIC(18,8) NOT NULL,
    source               VARCHAR(50) NOT NULL DEFAULT 'CBRF', -- 'CBRF','internal','manual'
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (date_id, currency_from, currency_to, source)
);
CREATE INDEX idx_fact_exchange_rates_lookup ON fact_exchange_rates(date_id, currency_from, currency_to);

-- ------------------------------------------------------------------------------
-- Facts
-- ------------------------------------------------------------------------------

-- Финансовые транзакции (1С + ручной ввод)
CREATE TABLE fact_transactions (
    transaction_id       BIGSERIAL PRIMARY KEY,
    transaction_date     DATE NOT NULL,
    posting_date         DATE NOT NULL,
    date_id              DATE NOT NULL REFERENCES dim_date(date_id),
    document_number      VARCHAR(100),
    document_type        VARCHAR(50) NOT NULL DEFAULT 'unknown',
    account_id           INT NOT NULL REFERENCES dim_account(account_id),
    counterparty_id      INT REFERENCES dim_counterparty(counterparty_id),
    department_id        INT REFERENCES dim_department(department_id),
    product_id           INT REFERENCES dim_product(product_id),
    employee_id          INT REFERENCES dim_employee(employee_id),
    currency_id          INT NOT NULL REFERENCES dim_currency(currency_id),
    amount_original      NUMERIC(18,4) NOT NULL,
    amount_rub           NUMERIC(18,4) NOT NULL,
    vat_amount           NUMERIC(18,4) DEFAULT 0,
    vat_rate             NUMERIC(5,2) DEFAULT 0,
    quantity             NUMERIC(18,4),
    unit_price           NUMERIC(18,4),
    description          TEXT,
    source_system        VARCHAR(50) NOT NULL,
    source_id            VARCHAR(255),
    is_manual_entry      BOOLEAN NOT NULL DEFAULT FALSE,
    is_deleted           BOOLEAN NOT NULL DEFAULT FALSE,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_fact_transactions_date ON fact_transactions(date_id);
CREATE INDEX idx_fact_transactions_account ON fact_transactions(account_id);
CREATE INDEX idx_fact_transactions_counterparty ON fact_transactions(counterparty_id);
CREATE INDEX idx_fact_transactions_source ON fact_transactions(source_system, source_id);

-- Продажи / сделки (amoCRM + 1С)
CREATE TABLE fact_sales (
    sale_id              BIGSERIAL PRIMARY KEY,
    source_system        VARCHAR(50) NOT NULL,
    source_id            VARCHAR(255) NOT NULL,
    deal_date            DATE NOT NULL,
    date_id              DATE NOT NULL REFERENCES dim_date(date_id),
    close_date           DATE,
    counterparty_id      INT REFERENCES dim_counterparty(counterparty_id),
    product_id           INT REFERENCES dim_product(product_id),
    employee_id          INT REFERENCES dim_employee(employee_id),
    department_id        INT REFERENCES dim_department(department_id),
    stage_name           VARCHAR(100),
    pipeline_name        VARCHAR(100),
    deal_status          VARCHAR(50) NOT NULL DEFAULT 'open', -- 'open','won','lost'
    amount_original      NUMERIC(18,4) NOT NULL DEFAULT 0,
    amount_rub           NUMERIC(18,4) NOT NULL DEFAULT 0,
    currency_id          INT REFERENCES dim_currency(currency_id),
    margin_amount_rub    NUMERIC(18,4),
    cost_amount_rub      NUMERIC(18,4),
    probability_pct      NUMERIC(5,2) DEFAULT 0,
    lead_time_days       INT,
    description          TEXT,
    is_deleted           BOOLEAN NOT NULL DEFAULT FALSE,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_fact_sales_date ON fact_sales(date_id);
CREATE INDEX idx_fact_sales_status ON fact_sales(deal_status);
CREATE INDEX idx_fact_sales_source ON fact_sales(source_system, source_id);

-- Лиды (amoCRM)
CREATE TABLE fact_crm_leads (
    lead_id              BIGSERIAL PRIMARY KEY,
    source_system        VARCHAR(50) NOT NULL DEFAULT 'amoCRM',
    source_id            VARCHAR(255) NOT NULL,
    created_date         DATE NOT NULL,
    date_id              DATE NOT NULL REFERENCES dim_date(date_id),
    converted_date       DATE,
    counterparty_id      INT REFERENCES dim_counterparty(counterparty_id),
    employee_id          INT REFERENCES dim_employee(employee_id),
    pipeline_name        VARCHAR(100),
    source_channel       VARCHAR(100), -- ' organic','paid','referral'
    lead_status          VARCHAR(50) NOT NULL DEFAULT 'new', -- 'new','qualified','converted','lost'
    utm_source           VARCHAR(100),
    utm_medium           VARCHAR(100),
    utm_campaign         VARCHAR(100),
    is_deleted           BOOLEAN NOT NULL DEFAULT FALSE,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_fact_crm_leads_date ON fact_crm_leads(date_id);
CREATE INDEX idx_fact_crm_leads_status ON fact_crm_leads(lead_status);

-- Расходы (Google Sheets + ручной ввод + 1C)
CREATE TABLE fact_expenses (
    expense_id           BIGSERIAL PRIMARY KEY,
    expense_date         DATE NOT NULL,
    date_id              DATE NOT NULL REFERENCES dim_date(date_id),
    account_id           INT NOT NULL REFERENCES dim_account(account_id),
    counterparty_id      INT REFERENCES dim_counterparty(counterparty_id),
    department_id        INT REFERENCES dim_department(department_id),
    employee_id          INT REFERENCES dim_employee(employee_id),
    expense_category     VARCHAR(100) NOT NULL,
    expense_item         VARCHAR(255) NOT NULL,
    currency_id          INT NOT NULL REFERENCES dim_currency(currency_id),
    amount_original      NUMERIC(18,4) NOT NULL,
    amount_rub           NUMERIC(18,4) NOT NULL,
    vat_amount           NUMERIC(18,4) DEFAULT 0,
    description          TEXT,
    receipt_info         VARCHAR(255), -- номер чека/акта
    source_system        VARCHAR(50) NOT NULL,
    is_manual_entry      BOOLEAN NOT NULL DEFAULT FALSE,
    is_deleted           BOOLEAN NOT NULL DEFAULT FALSE,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_fact_expenses_date ON fact_expenses(date_id);
CREATE INDEX idx_fact_expenses_account ON fact_expenses(account_id);

-- ------------------------------------------------------------------------------
-- Staging (сырые данные из источников)
-- ------------------------------------------------------------------------------
CREATE SCHEMA IF NOT EXISTS staging;

CREATE TABLE staging.stg_amocrm_leads (
    raw_id               BIGSERIAL PRIMARY KEY,
    amo_id               BIGINT NOT NULL,
    name                 TEXT,
    status_id            BIGINT,
    pipeline_id          BIGINT,
    responsible_user_id  BIGINT,
    created_at_ts        TIMESTAMPTZ,
    updated_at_ts        TIMESTAMPTZ,
    price                NUMERIC(18,4),
    currency             VARCHAR(10),
    custom_fields        JSONB,
    tags                 JSONB,
    raw_json             JSONB NOT NULL,
    loaded_at            TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE staging.stg_amocrm_deals (
    raw_id               BIGSERIAL PRIMARY KEY,
    amo_id               BIGINT NOT NULL,
    name                 TEXT,
    status_id            BIGINT,
    pipeline_id          BIGINT,
    responsible_user_id  BIGINT,
    created_at_ts        TIMESTAMPTZ,
    closed_at_ts         TIMESTAMPTZ,
    price                NUMERIC(18,4),
    currency             VARCHAR(10),
    custom_fields        JSONB,
    raw_json             JSONB NOT NULL,
    loaded_at            TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE staging.stg_1c_transactions (
    raw_id               BIGSERIAL PRIMARY KEY,
    doc_number           VARCHAR(100),
    doc_date             DATE,
    doc_type             VARCHAR(100),
    organization         VARCHAR(255),
    counterparty_name    VARCHAR(255),
    counterparty_inn     VARCHAR(12),
    account_debit        VARCHAR(20),
    account_credit       VARCHAR(20),
    amount               NUMERIC(18,4),
    currency_code        VARCHAR(10),
    description          TEXT,
    raw_json             JSONB,
    loaded_at            TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE staging.stg_gsheets_expenses (
    raw_id               BIGSERIAL PRIMARY KEY,
    sheet_name           VARCHAR(100) NOT NULL,
    row_num              INT NOT NULL,
    date_raw             VARCHAR(50),
    amount_raw           VARCHAR(50),
    currency_raw         VARCHAR(10),
    category_raw         VARCHAR(100),
    item_raw             VARCHAR(255),
    department_raw       VARCHAR(100),
    description_raw      TEXT,
    parsed_ok            BOOLEAN DEFAULT FALSE,
    parse_error          TEXT,
    raw_row_json         JSONB NOT NULL,
    loaded_at            TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ------------------------------------------------------------------------------
-- Audit & Service
-- ------------------------------------------------------------------------------
CREATE TABLE audit_log (
    audit_id             BIGSERIAL PRIMARY KEY,
    table_name           VARCHAR(100) NOT NULL,
    record_id            BIGINT NOT NULL,
    action               VARCHAR(20) NOT NULL CHECK (action IN ('INSERT','UPDATE','DELETE')),
    changed_by           VARCHAR(255) NOT NULL,
    changed_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    old_values           JSONB,
    new_values           JSONB,
    reason               TEXT
);
CREATE INDEX idx_audit_table_record ON audit_log(table_name, record_id);
CREATE INDEX idx_audit_changed_at ON audit_log(changed_at);

CREATE TABLE etl_runs (
    run_id               BIGSERIAL PRIMARY KEY,
    etl_name             VARCHAR(100) NOT NULL,
    started_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at          TIMESTAMPTZ,
    status               VARCHAR(20) NOT NULL DEFAULT 'running' CHECK (status IN ('running','success','partial','failed')),
    records_processed    BIGINT DEFAULT 0,
    records_inserted     BIGINT DEFAULT 0,
    records_updated      BIGINT DEFAULT 0,
    records_failed       BIGINT DEFAULT 0,
    error_message        TEXT,
    log_output           TEXT
);

CREATE TABLE data_input_templates (
    template_id          SERIAL PRIMARY KEY,
    template_code        VARCHAR(50) UNIQUE NOT NULL,
    template_name        VARCHAR(255) NOT NULL,
    target_table         VARCHAR(100) NOT NULL,
    json_schema          JSONB NOT NULL,
    allowed_roles        VARCHAR(50)[] NOT NULL DEFAULT ARRAY['admin'],
    is_active            BOOLEAN NOT NULL DEFAULT TRUE,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE data_input_entries (
    entry_id             BIGSERIAL PRIMARY KEY,
    template_id          INT NOT NULL REFERENCES data_input_templates(template_id),
    submitted_by         VARCHAR(255) NOT NULL,
    submitted_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    entry_data           JSONB NOT NULL,
    validation_errors    JSONB,
    status               VARCHAR(20) NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','submitted','validated','rejected','applied')),
    applied_at           TIMESTAMPTZ,
    applied_by           VARCHAR(255),
    rejection_reason     TEXT
);

-- ------------------------------------------------------------------------------
-- Users / RBAC (простая модель для data input UI)
-- ------------------------------------------------------------------------------
CREATE TABLE bi_users (
    user_id              SERIAL PRIMARY KEY,
    username             VARCHAR(100) UNIQUE NOT NULL,
    email                VARCHAR(255) UNIQUE NOT NULL,
    hashed_password      VARCHAR(255),
    full_name            VARCHAR(255),
    role                 VARCHAR(50) NOT NULL DEFAULT 'viewer' CHECK (role IN ('admin','ceo','cfo','sales_head','manager','viewer')),
    department_id        INT REFERENCES dim_department(department_id),
    employee_id          INT REFERENCES dim_employee(employee_id),
    is_active            BOOLEAN NOT NULL DEFAULT TRUE,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ------------------------------------------------------------------------------
-- Seed data
-- ------------------------------------------------------------------------------
INSERT INTO dim_currency (currency_code, currency_name) VALUES
('RUB','Российский рубль'),
('USD','Доллар США'),
('CNY','Китайский юань'),
('EUR','Евро')
ON CONFLICT (currency_code) DO NOTHING;

INSERT INTO dim_department (department_name, department_code) VALUES
('Продажи','SALES'),
('Закупки','PROCUREMENT'),
('Маркетинг','MARKETING'),
('Бухгалтерия','ACC'),
('IT','IT'),
('Администрация','ADMIN')
ON CONFLICT (department_code) DO NOTHING;

INSERT INTO dim_account (account_code, account_name, account_type, pnl_section) VALUES
('REV-001','Выручка от продаж','revenue','revenue'),
('COGS-001','Себестоимость проданных товаров','cogs','gross_profit'),
('OPEX-001','Расходы на персонал (ФОТ)','opex','operating_profit'),
('OPEX-002','Аренда и коммунальные платежи','opex','operating_profit'),
('OPEX-003','Маркетинг и реклама','opex','operating_profit'),
('OPEX-004','Закупки/запасы','opex','operating_profit'),
('OPEX-005','Канцелярия, хознужды, кофе','opex','operating_profit'),
('OPEX-006','Логистика и доставка','opex','operating_profit'),
('OPEX-007','Телефония и связь','opex','operating_profit'),
('OPEX-008','Амортизация','opex','operating_profit'),
('OPEX-009','Прочие операционные расходы','opex','operating_profit'),
('TAX-001','Налог на прибыль','tax','net_profit'),
('OI-001','Прочие доходы','other_income','net_profit'),
('OE-001','Прочие расходы','other_expense','net_profit')
ON CONFLICT (account_code) DO NOTHING;

-- ------------------------------------------------------------------------------
-- Populate date dimension (current year + 2 past + 2 future)
-- ------------------------------------------------------------------------------
DO $$
DECLARE
    d DATE;
BEGIN
    FOR d IN SELECT generate_series(
        DATE_TRUNC('year', CURRENT_DATE) - INTERVAL '2 years',
        DATE_TRUNC('year', CURRENT_DATE) + INTERVAL '2 years' - INTERVAL '1 day',
        INTERVAL '1 day'
    )
    LOOP
        INSERT INTO dim_date (
            date_id, year, quarter, month, month_name, week_of_year,
            day_of_week, day_of_month, day_name, is_weekend, is_holiday_rf,
            fiscal_year, fiscal_quarter
        ) VALUES (
            d,
            EXTRACT(YEAR FROM d)::SMALLINT,
            EXTRACT(QUARTER FROM d)::SMALLINT,
            EXTRACT(MONTH FROM d)::SMALLINT,
            TO_CHAR(d, 'TMMonth'),
            EXTRACT(WEEK FROM d)::SMALLINT,
            EXTRACT(DOW FROM d)::SMALLINT,
            EXTRACT(DAY FROM d)::SMALLINT,
            TO_CHAR(d, 'TMDay'),
            EXTRACT(DOW FROM d) IN (0,6),
            FALSE,
            EXTRACT(YEAR FROM d)::SMALLINT,
            EXTRACT(QUARTER FROM d)::SMALLINT
        )
        ON CONFLICT (date_id) DO NOTHING;
    END LOOP;
END $$;
