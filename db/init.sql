-- Local development only: create one database and one login per service.
-- Run by the one-off `db-init` compose service as `sa`. Safe to run on every
-- `docker compose up`: each statement first checks whether its object exists.
-- On Azure the databases and logins are created once during the initial setup.
--
-- sqlcmd fills $(CATALOG_DB_PASSWORD) and $(ORDERS_DB_PASSWORD) from the
-- environment variables of the db-init container.

IF DB_ID(N'catalog_db') IS NULL CREATE DATABASE catalog_db;
GO
IF DB_ID(N'orders_db') IS NULL CREATE DATABASE orders_db;
GO

IF SUSER_ID(N'catalog_user') IS NULL
    CREATE LOGIN catalog_user
        WITH PASSWORD = N'$(CATALOG_DB_PASSWORD)', DEFAULT_DATABASE = catalog_db;
GO
IF SUSER_ID(N'orders_user') IS NULL
    CREATE LOGIN orders_user
        WITH PASSWORD = N'$(ORDERS_DB_PASSWORD)', DEFAULT_DATABASE = orders_db;
GO

-- Each login becomes a user in its own database only. It gets db_owner there
-- because its migrations create and alter tables. It has no user in the other
-- database, so it cannot open it.
USE catalog_db;
IF USER_ID(N'catalog_user') IS NULL CREATE USER catalog_user FOR LOGIN catalog_user;
ALTER ROLE db_owner ADD MEMBER catalog_user;
GO

USE orders_db;
IF USER_ID(N'orders_user') IS NULL CREATE USER orders_user FOR LOGIN orders_user;
ALTER ROLE db_owner ADD MEMBER orders_user;
GO
