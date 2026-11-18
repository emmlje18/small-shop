-- Azure initial setup, run once against the master database of <prefix>-sql
-- as the server admin. Creates one login per service. Idempotent.
-- sqlcmd fills $(CATALOG_DB_PASSWORD) and $(ORDERS_DB_PASSWORD) from the environment.

IF NOT EXISTS (SELECT 1 FROM sys.sql_logins WHERE name = N'catalog_user')
    CREATE LOGIN catalog_user WITH PASSWORD = N'$(CATALOG_DB_PASSWORD)';
GO
IF NOT EXISTS (SELECT 1 FROM sys.sql_logins WHERE name = N'orders_user')
    CREATE LOGIN orders_user WITH PASSWORD = N'$(ORDERS_DB_PASSWORD)';
GO
