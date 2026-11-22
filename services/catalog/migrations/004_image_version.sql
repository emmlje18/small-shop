-- 004: give each product picture a version number.
-- The shop shows a picture at /products/<id>/image?v=<image_version>. The
-- number goes up every time the picture is replaced, so browsers download the
-- new picture instead of showing a cached copy of the old one, while an
-- unchanged picture can stay cached.
--
-- This changes a table that already holds products. Nothing is deleted:
-- existing rows get 1 if they already have a picture and 0 if not.

ALTER TABLE dbo.products ADD
    image_version INT NOT NULL CONSTRAINT df_products_image_version DEFAULT 0;
GO

UPDATE dbo.products SET image_version = 1 WHERE image_data IS NOT NULL;
