# Emma's cool shop

A small online shop split into two Flask services, each with its own SQL Server
database, and a static UI that calls both from the browser.

Live URL: <https://ejliuexstudents2026ui.z28.web.core.windows.net/>

```
 browser ── static UI (ui/, Azure Storage static website)
   │  JSON over HTTPS (CORS)
   ├──► catalog  (services/catalog)  products, options, stock, pictures, admin ──► catalog database
   └──► orders   (services/orders)   cart pricing, checkout, orders            ──► orders database
              │
              └── HTTP + X-Internal-Token ──► catalog /internal/variants/{id}, /decrement, /restore
```

Orders only reaches the catalog through those three internal endpoints (the
ADR-2 seam, now HTTP). Each service owns its tables, runs its own versioned SQL
migrations at startup, and answers `GET /health`. The services, their
settings and their Azure resources are described in `system.yaml`; their APIs
in `services/<name>/openapi.yaml`. Design decisions are in `ADR.md` (6–10 for
this assignment).

## Run locally with Docker Compose

Requires Docker Desktop. From the repository root:

```sh
docker compose up --build
```

| What | URL |
|---|---|
| Shop (static UI) | <http://localhost:8180> |
| Catalog API | <http://localhost:8101/health> |
| Orders API | <http://localhost:8102/health> |
| SQL Server (for tools) | `localhost:14330` |

Compose starts one SQL Server container, a one-off `db-init` job that creates
`catalog_db` and `orders_db` with one login each (`db/init.sql`), both
services, and nginx serving `ui/`. Each service applies its pending migrations
before gunicorn starts. The local admin password is `admin`; local passwords
are defaults in `docker-compose.yml` and can be overridden with environment
variables (`MSSQL_SA_PASSWORD`, `CATALOG_DB_PASSWORD`, `ORDERS_DB_PASSWORD`,
`ADMIN_PASSWORD`, `INTERNAL_TOKEN`). Data is kept in the `mssql-data` volume;
`docker compose down -v` deletes it.

The shop starts with no products: sign in at **Admin** and add some. Fake
payment: any card works except one ending in `0000`, which is declined.

## Run a single service

Each service starts with only the database, without the other service:

```sh
docker compose up --build catalog      # catalog + SQL Server
docker compose up --build orders       # orders + SQL Server, no catalog
```

Orders without the catalog shows the designed partial failure: `/health` and
`GET /orders/{id}` work, while cart and checkout answer
`503 {"error": "The catalog is unavailable right now..."}`.

To run a service outside Docker (Linux; pymssql's macOS wheel does not work on
every Mac), start the database with `docker compose up -d mssql db-init`, then:

```sh
cd services/catalog
python -m pip install -r requirements.txt
export DATABASE_URL='mssql+pymssql://catalog_user:LocalDev_Catalog_1@localhost:14330/catalog_db'
export ADMIN_PASSWORD=admin INTERNAL_TOKEN=local-internal-token CORS_ORIGINS=http://localhost:8180
python -m catalog.migrate && flask --app 'catalog:create_app()' run --port 8101
```

Every environment variable each service reads, with its default, is listed in
`system.yaml`.

## Tests and coverage

The tests run in a Python container against the compose SQL Server, in a
separate `<service>_test` database that is recreated on each run:

```sh
docker compose run --rm catalog-tests
docker compose run --rm orders-tests
```

Latest result: catalog 76 tests, 96% coverage; orders 46 tests, 97% coverage.
The orders suite includes the cross-seam integration tests
(`services/orders/tests/test_cross_seam.py`): the real orders app and its HTTP
client against a stub catalog server that follows the catalog's OpenAPI
document, including the catalog being stopped or too slow. CI fails below 70%
coverage per service (ADR-9).

## How deployment works

`.github/workflows/ci.yml` runs on every push and pull request:

1. **Validate**: `system.yaml` against `system.schema.json`, both
   `openapi.yaml` files against the OpenAPI specification, and
   `scripts/check_system.py` (the endpoints orders calls exist in the
   catalog's document).
2. **Test** (per service): ruff, then pytest with coverage against a
   throwaway SQL Server container.
3. **Image** (per service): Docker build; on `main` the image is pushed to
   `ghcr.io/emmlje18/small-shop-<service>:<commit SHA>`.
4. **Deploy** (only on a push to `main`, only if 1–3 passed on that commit):
   signs in to Azure as the managed identity through OpenID Connect (no stored
   Azure password), creates or updates both Container Apps with the new image
   (min 0, max 1 replica; database URL, admin password and internal token as
   Container Apps secrets), writes `ui/config.js` with the two service URLs,
   uploads `ui/` to the `$web` container, and polls `/health` on both
   services until they report the new commit SHA (up to 6 minutes, to allow for
   a cold start and a paused database resuming).

Changes reach `main` only through pull requests. Evidence of the
data-preserving migration on Azure is in `docs/evidence/migration-004.md`.

## Assignment 1 monolith

The original single-process app (`app.py`, `app/`, `templates/`, `static/`,
root `Dockerfile`, `tests/`) is kept unchanged for reference. It runs with
`python app.py` on port 8000 with SQLite; it is not deployed.

## Azure: initial setup (done once, by hand)

After this one-time setup, nothing is created or changed in the portal: the
GitHub Actions pipeline creates and updates the two Container Apps and uploads
the UI. Every resource is in one resource group in `francecentral`, one of the
five regions this Azure for Students subscription allows.

| Resource | Name |
|---|---|
| Resource group | `rg-ejliu-exstudents2026` |
| Managed identity for GitHub Actions | `ejliu-exstudents2026-github` |
| SQL logical server | `ejliu-exstudents2026-sql` |
| Catalog database (serverless, free offer) | `ejliu-exstudents2026-catalog-db` |
| Orders database (serverless, free offer) | `ejliu-exstudents2026-orders-db` |
| Container Apps environment (Consumption) | `ejliu-exstudents2026-env` |
| UI storage account (static website) | `ejliuexstudents2026ui` |

To reproduce, sign in with `az login` and run, in order:

```sh
PREFIX=ejliu-exstudents2026; RG=rg-$PREFIX; LOC=francecentral
REPO=emmlje18/small-shop; SRV=$PREFIX-sql; SA=ejliuexstudents2026ui

# 0. Register the resource providers (once per subscription).
for p in Microsoft.App Microsoft.Sql Microsoft.Storage Microsoft.ManagedIdentity Microsoft.OperationalInsights; do
  az provider register --namespace $p --wait
done

# 1. Resource group.
az group create -n $RG -l $LOC

# 2. Managed identity that the pipeline signs in as through OpenID Connect.
#    Trusted only for runs on main of this repository; Contributor on this group only.
az identity create -g $RG -n $PREFIX-github -l $LOC
az identity federated-credential create -g $RG --identity-name $PREFIX-github -n github-main \
  --issuer https://token.actions.githubusercontent.com \
  --subject 'repo:emmlje18@246001628/small-shop@1407407026:ref:refs/heads/main' \
  --audiences api://AzureADTokenExchange
#    GitHub's OIDC subject includes the owner and repo IDs (owner@id/repo@id);
#    the deploy log prints the exact subject if it ever changes.
az role assignment create --role Contributor \
  --assignee-object-id "$(az identity show -g $RG -n $PREFIX-github --query principalId -o tsv)" \
  --assignee-principal-type ServicePrincipal --scope "$(az group show -n $RG --query id -o tsv)"

# 3. Passwords: generated into files outside the repository, never printed.
mkdir -p ~/.small-shop-secrets && chmod 700 ~/.small-shop-secrets
for f in sql-admin-password catalog-db-password orders-db-password admin-password internal-token; do
  printf '%sAa1_' "$(openssl rand -base64 32 | tr -dc 'A-Za-z0-9' | head -c 24)" > ~/.small-shop-secrets/$f
done

# 4. SQL server, "allow Azure services" firewall rule, and one serverless database
#    per service on the free offer (General Purpose, Gen5, 0.5-1 vCore, LRS backups;
#    the free offer fixes auto-pause at 60 minutes and the size at 32 GB).
az sql server create -g $RG -n $SRV -l $LOC --admin-user sqladmin \
  --admin-password "$(cat ~/.small-shop-secrets/sql-admin-password)" --minimal-tls-version 1.2
az sql server firewall-rule create -g $RG -s $SRV -n AllowAzureServices \
  --start-ip-address 0.0.0.0 --end-ip-address 0.0.0.0
for svc in catalog orders; do
  az sql db create -g $RG -s $SRV -n $PREFIX-$svc-db --edition GeneralPurpose \
    --compute-model Serverless --family Gen5 --min-capacity 0.5 --capacity 1 \
    --backup-storage-redundancy Local --use-free-limit --free-limit-exhaustion-behavior AutoPause
done

# 5. One login per service, with a user in its own database only. Open the
#    firewall to this machine just for these commands, then close it again.
#    The scripts are in db/azure/ and read passwords from sqlcmd variables.
az sql server firewall-rule create -g $RG -s $SRV -n TempSetupMyIP \
  --start-ip-address "$(curl -s https://api.ipify.org)" --end-ip-address "$(curl -s https://api.ipify.org)"
export CATALOG_DB_PASSWORD="$(cat ~/.small-shop-secrets/catalog-db-password)"
export ORDERS_DB_PASSWORD="$(cat ~/.small-shop-secrets/orders-db-password)"
export SQLCMDPASSWORD="$(cat ~/.small-shop-secrets/sql-admin-password)"
sq() { docker run --rm -e SQLCMDPASSWORD -e CATALOG_DB_PASSWORD -e ORDERS_DB_PASSWORD -e DB_USER \
  -v "$PWD/db/azure:/s:ro" --platform linux/amd64 --entrypoint /opt/mssql-tools18/bin/sqlcmd \
  mcr.microsoft.com/mssql/server:2022-latest -S tcp:$SRV.database.windows.net,1433 -U sqladmin -b -l 60 "$@"; }
sq -d master -i /s/create-logins.sql
DB_USER=catalog_user sq -d $PREFIX-catalog-db -i /s/create-db-user.sql
DB_USER=orders_user  sq -d $PREFIX-orders-db  -i /s/create-db-user.sql
az sql server firewall-rule delete -g $RG -s $SRV -n TempSetupMyIP

# 6. Storage account for the UI, with static website hosting ($web container).
az storage account create -g $RG -n $SA -l $LOC --sku Standard_LRS --kind StorageV2 \
  --min-tls-version TLS1_2 --allow-blob-public-access false
az storage blob service-properties update --account-name $SA --static-website \
  --index-document index.html --404-document index.html

# 7. Container Apps environment, Consumption only. --logs-destination none avoids
#    creating a Log Analytics workspace; logs are read with `az containerapp logs show`.
az containerapp env create -g $RG -n $PREFIX-env -l $LOC --logs-destination none

# 8. Secrets the pipeline reads. Values go straight from Azure or the files to GitHub.
az identity show -g $RG -n $PREFIX-github --query clientId -o tsv | gh secret set AZURE_CLIENT_ID
az account show --query tenantId -o tsv | gh secret set AZURE_TENANT_ID
az account show --query id -o tsv | gh secret set AZURE_SUBSCRIPTION_ID
gh secret set CATALOG_DB_PASSWORD < ~/.small-shop-secrets/catalog-db-password
gh secret set ORDERS_DB_PASSWORD < ~/.small-shop-secrets/orders-db-password
gh secret set ADMIN_PASSWORD < ~/.small-shop-secrets/admin-password
gh secret set INTERNAL_TOKEN < ~/.small-shop-secrets/internal-token

# 9. Read-only access for grading.
az role assignment create --assignee <professor-email> --role Reader \
  --scope "$(az group show -n $RG --query id -o tsv)"
```
