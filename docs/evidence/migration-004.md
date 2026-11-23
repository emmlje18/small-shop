# Evidence: data-preserving migration 004 on Azure

Migration `services/catalog/migrations/004_image_version.sql` adds
`products.image_version` to a table that already held live products, without
deleting anything (default 0; 1 for products that already had a picture).

- PR: https://github.com/emmlje18/small-shop/pull/7
- CD run that deployed it: https://github.com/emmlje18/small-shop/actions/runs/45057711158
- Queries run as `catalog_user` against `ejliu-exstudents2026-catalog-db`
  through a temporary firewall rule, removed afterwards.

## Before (18:55:57 UTC, deploy job starting)

```
SELECT version, applied_at FROM schema_migrations ORDER BY version;
   001_init.sql 2026-11-22 11:19:35.495000
   002_product_images.sql 2026-11-22 11:19:35.507533
   003_health_check.sql 2026-11-22 11:19:35.537689
SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME='products';
   id, name, description, price_cents, image_path, is_active, created_at, image_data, image_content_type
SELECT id, name, price_cents, is_active, CASE WHEN image_data IS NULL THEN 0 ELSE 1 END AS has_image FROM products ORDER BY id;
   id | name | price_cents | is_active | has_image
   1 | Chibi Stickers Genshin Impact (7cm Waterproof) | 200 | True | 1
   2 | Stamp Stickers Honkai Starrail (4cm Waterproof) | 100 | True | 1
product_variants rows: 14
```

## During: catalog startup log on Azure Container Apps

```
2026-11-22 18:56:10,107 INFO catalog.migrate Applying migration 004_image_version.sql
2026-11-22 18:56:10,125 INFO catalog.migrate Applied migration 004_image_version.sql
```

## After (18:57:35 UTC)

```
SELECT version, applied_at FROM schema_migrations ORDER BY version;
   001_init.sql 2026-11-22 11:19:35.495000
   002_product_images.sql 2026-11-22 11:19:35.507533
   003_health_check.sql 2026-11-22 11:19:35.537689
   004_image_version.sql 2026-11-22 18:56:10.155648
SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME='products';
   id, name, description, price_cents, image_path, is_active, created_at, image_data, image_content_type, image_version
SELECT id, name, price_cents, is_active, CASE WHEN image_data IS NULL THEN 0 ELSE 1 END AS has_image, image_version FROM products ORDER BY id;
   id | name | price_cents | is_active | has_image | image_version
   1 | Chibi Stickers Genshin Impact (7cm Waterproof) | 200 | True | 1 | 1
   2 | Stamp Stickers Honkai Starrail (4cm Waterproof) | 100 | True | 1 | 1
product_variants rows: 14
```

Both products, their pictures and all 14 options are unchanged; the new
column is filled in, and 004 is recorded once in `schema_migrations`.
