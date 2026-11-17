-- 001: orders tables, ported from the Assignment 1 SQLite schema.
-- INTEGER PRIMARY KEY -> INT IDENTITY, TEXT -> NVARCHAR, CURRENT_TIMESTAMP -> SYSUTCDATETIME().
-- Constraints are named so later migrations can refer to them.

CREATE TABLE dbo.orders (
    id INT IDENTITY(1, 1) NOT NULL CONSTRAINT pk_orders PRIMARY KEY,
    customer_name NVARCHAR(200) NOT NULL,
    customer_email NVARCHAR(320) NOT NULL,
    status NVARCHAR(20) NOT NULL CONSTRAINT ck_orders_status
        CHECK (status IN (N'pending', N'paid', N'shipped', N'cancelled')),
    total_cents INT NOT NULL CONSTRAINT ck_orders_total_cents CHECK (total_cents >= 0),
    payment_ref NVARCHAR(100) NULL,
    created_at DATETIME2 NOT NULL CONSTRAINT df_orders_created_at DEFAULT SYSUTCDATETIME()
);

-- variant_id is a plain integer with no foreign key: variants live in the
-- catalog service's database (ADR-3). The product details are copied here.
CREATE TABLE dbo.order_items (
    id INT IDENTITY(1, 1) NOT NULL CONSTRAINT pk_order_items PRIMARY KEY,
    order_id INT NOT NULL CONSTRAINT fk_order_items_order REFERENCES dbo.orders (id),
    variant_id INT NOT NULL,
    product_name NVARCHAR(200) NOT NULL,
    option_label NVARCHAR(100) NOT NULL,
    unit_price_cents INT NOT NULL CONSTRAINT ck_order_items_unit_price_cents
        CHECK (unit_price_cents >= 0),
    quantity INT NOT NULL CONSTRAINT ck_order_items_quantity CHECK (quantity > 0)
);

CREATE INDEX ix_order_items_order_id ON dbo.order_items (order_id);
