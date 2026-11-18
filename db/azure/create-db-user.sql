-- Azure initial setup, run once inside ONE service database (sqlcmd -d) as the
-- server admin, with $(DB_USER) set to that service's login. Idempotent.
-- The user gets db_owner in this database only, because its migrations create
-- and alter tables. It has no user in the other database, so it cannot open it.

IF USER_ID(N'$(DB_USER)') IS NULL CREATE USER [$(DB_USER)] FOR LOGIN [$(DB_USER)];
ALTER ROLE db_owner ADD MEMBER [$(DB_USER)];
GO
