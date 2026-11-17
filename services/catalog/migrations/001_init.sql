-- 001: catalog tables, ported from the Assignment 1 SQLite schema.
-- INTEGER PRIMARY KEY -> INT IDENTITY, TEXT -> NVARCHAR, CURRENT_TIMESTAMP -> SYSUTCDATETIME().
-- Constraints are named so later migrations can refer to them.

CREATE TABLE dbo.products (
    id INT IDENTITY(1, 1) NOT NULL CONSTRAINT pk_products PRIMARY KEY,
    name NVARCHAR(200) NOT NULL,
    description NVARCHAR(MAX) NOT NULL CONSTRAINT df_products_description DEFAULT N'',
    price_cents INT NOT NULL CONSTRAINT ck_products_price_cents CHECK (price_cents >= 0),
    image_path NVARCHAR(255) NULL,
    is_active BIT NOT NULL CONSTRAINT df_products_is_active DEFAULT 1,
    created_at DATETIME2 NOT NULL CONSTRAINT df_products_created_at DEFAULT SYSUTCDATETIME()
);

CREATE TABLE dbo.product_variants (
    id INT IDENTITY(1, 1) NOT NULL CONSTRAINT pk_product_variants PRIMARY KEY,
    product_id INT NOT NULL
        CONSTRAINT fk_product_variants_product REFERENCES dbo.products (id),
    option_label NVARCHAR(100) NOT NULL,
    stock INT NOT NULL CONSTRAINT ck_product_variants_stock CHECK (stock >= 0)
);

CREATE INDEX ix_product_variants_product_id ON dbo.product_variants (product_id);
