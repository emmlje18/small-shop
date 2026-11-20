-- 002: keep product images in the database.
-- On Azure Container Apps the container's disk is wiped whenever the app
-- scales to zero, so uploaded files cannot live there (ADR-6). The image bytes
-- and their content type are stored on the product row instead. Both columns
-- are nullable, so existing products simply have no image.

ALTER TABLE dbo.products ADD
    image_data VARBINARY(MAX) NULL,
    image_content_type NVARCHAR(100) NULL;
