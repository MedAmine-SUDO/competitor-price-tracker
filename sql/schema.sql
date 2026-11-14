-- Competitor price tracker schema. Safe to run more than once.

CREATE TABLE IF NOT EXISTS runs (
    id              BIGSERIAL PRIMARY KEY,
    started_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at     TIMESTAMPTZ,
    status          TEXT NOT NULL DEFAULT 'running',   -- running | ok | degraded | failed
    products_seen   INTEGER NOT NULL DEFAULT 0,
    pages_fetched   INTEGER NOT NULL DEFAULT 0,
    errors          INTEGER NOT NULL DEFAULT 0,
    report          JSONB NOT NULL DEFAULT '{}'::jsonb
);

-- Groups of listings that are the same product on different sites.
CREATE TABLE IF NOT EXISTS product_groups (
    id              BIGSERIAL PRIMARY KEY,
    canonical_name  TEXT NOT NULL,
    match_key       TEXT UNIQUE,          -- stable key, e.g. normalized reference
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- One row per listing on one site.
CREATE TABLE IF NOT EXISTS products (
    id              BIGSERIAL PRIMARY KEY,
    site            TEXT NOT NULL,
    site_product_id TEXT NOT NULL,
    url             TEXT NOT NULL,
    name            TEXT NOT NULL,
    brand           TEXT,
    reference       TEXT,
    category        TEXT,
    group_id        BIGINT REFERENCES product_groups(id) ON DELETE SET NULL,
    match_method    TEXT,                 -- reference | fuzzy | NULL
    first_seen      TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen       TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (site, site_product_id)
);
CREATE INDEX IF NOT EXISTS products_group_idx ON products(group_id);

-- Full price history: one row per product per run.
CREATE TABLE IF NOT EXISTS price_snapshots (
    id              BIGSERIAL PRIMARY KEY,
    product_id      BIGINT NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    run_id          BIGINT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    scraped_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    price           NUMERIC(12,3) NOT NULL,   -- regular price (TND)
    promo_price     NUMERIC(12,3),            -- NULL when not on promo
    in_stock        BOOLEAN,
    stock_label     TEXT,
    UNIQUE (product_id, run_id)
);
CREATE INDEX IF NOT EXISTS snapshots_product_time_idx ON price_snapshots(product_id, scraped_at DESC);

-- Price-drop alerts, so the same drop is never sent twice.
CREATE TABLE IF NOT EXISTS alerts (
    id              BIGSERIAL PRIMARY KEY,
    product_id      BIGINT NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    run_id          BIGINT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    old_price       NUMERIC(12,3) NOT NULL,
    new_price       NUMERIC(12,3) NOT NULL,
    drop_pct        NUMERIC(6,2) NOT NULL,
    sent            BOOLEAN NOT NULL DEFAULT false,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (product_id, run_id)
);

-- Latest snapshot per product, with the price a customer actually pays.
CREATE OR REPLACE VIEW latest_prices AS
SELECT DISTINCT ON (s.product_id)
       p.id AS product_id, p.site, p.name, p.brand, p.reference, p.category, p.url,
       p.group_id, s.price, s.promo_price,
       COALESCE(s.promo_price, s.price) AS effective_price,
       s.in_stock, s.stock_label, s.scraped_at, s.run_id
FROM price_snapshots s
JOIN products p ON p.id = s.product_id
ORDER BY s.product_id, s.scraped_at DESC;
