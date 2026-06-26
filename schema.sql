CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS products (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name text NOT NULL,
    category text NOT NULL,
    price numeric(10, 2) NOT NULL CHECK (price >= 0),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    current_version_id bigint
);

CREATE TABLE IF NOT EXISTS product_versions (
    version_id bigserial PRIMARY KEY,
    product_id uuid NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    name text NOT NULL,
    category text NOT NULL,
    price numeric(10, 2) NOT NULL CHECK (price >= 0),
    created_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL,
    visible_until bigint
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_products_current_version
    ON products (current_version_id)
    WHERE current_version_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_product_versions_product_visible
    ON product_versions (product_id, version_id DESC);

CREATE INDEX IF NOT EXISTS idx_product_versions_browse
    ON product_versions (version_id DESC)
    WHERE visible_until IS NULL;

CREATE INDEX IF NOT EXISTS idx_product_versions_category_browse
    ON product_versions (category, version_id DESC);
