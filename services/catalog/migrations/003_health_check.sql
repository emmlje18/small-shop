-- 003: a one-row table that GET /health writes to and reads back, to prove the
-- service can both write and read its own database.

CREATE TABLE dbo.health_check (
    id INT NOT NULL CONSTRAINT pk_health_check PRIMARY KEY
        CONSTRAINT ck_health_check_single_row CHECK (id = 1),
    checked_at DATETIME2 NOT NULL
);
