# Emma's cool shop

A small Flask online shop, built as one process with SQLite storage.

## Run directly on your computer

From the project root, install the dependencies and start the app:

```sh
python -m pip install -r requirements.txt
python app.py
```

The app listens on `0.0.0.0` using port `8000` by default. It creates the
SQLite database and upload directory automatically. The database is at
`DATA_DIR/shop.db`; by default, `DATA_DIR` is `./data`.

Check that the app is running at <http://127.0.0.1:8000/health>.

The admin catalog pages are at <http://127.0.0.1:8000/admin/login>. The local
default password is `admin`; set `ADMIN_PASSWORD` before using the admin pages
outside local development. Product images may be JPG, JPEG, PNG, GIF, or WebP,
up to 5 MiB per request.

## Configure the app

| Variable | Default | Purpose |
|---|---|---|
| `PORT` | `8000` | Port the web app listens on. |
| `DATA_DIR` | `./data` | Directory for `shop.db` and uploaded images. |
| `ADMIN_PASSWORD` | `admin` | Local development password for the future admin pages. |
| `SECRET_KEY` | `local-development-key` | Flask session signing key. |

Set these in the environment when starting the app. No `.env` file is required.

## Run in the provided container

The root `Dockerfile` is copied from the course template. Its source-copy TODO
includes `app/` so the image contains the Flask package as well as `app.py`.
Build and run it from the project root:

```sh
docker build -t small-shop .
docker run --rm -p 8000:8000 -v small-shop-data:/data small-shop
```

In the container, `DATA_DIR` defaults to `/data`, so SQLite is stored at
`/data/shop.db` and uploaded files at `/data/uploads`. To check a different
port, set `PORT` and publish that same port, for example:

```sh
docker run --rm -e PORT=9000 -p 9000:9000 -v small-shop-data:/data small-shop
```

Run the copied course contract checker from the project root:

```sh
./container/run.sh .
```

The checker requires Docker Desktop to be running.

## Test coverage

Run the core business-logic tests and coverage report from the project root:

```sh
python3 -m pytest --cov=app.catalog.service --cov=app.catalog.repository --cov=app.orders.service --cov=app.orders.repository --cov=app.orders.payment --cov-report=term-missing
```

Latest result: **26 tests passed, 87% coverage** across the selected catalog and
orders business-logic modules. Flask routes and templates are excluded because
the assignment asks for unit tests of core logic rather than framework glue.

## Container verification evidence

The provided checker was run on 2026-10-12 and passed every check:

```text
=== SDD Assignment 1 contract check ===
Repository: /Users/emmaliu/small-shop

==> Repository shape
  PASS  one Dockerfile, one manifest (requirements.txt)

==> Build from a clean context, no build args
  PASS  image built
  PASS  image size 270 MB

==> Start on PORT=8000 and reach it from the host
  PASS  HTTP 200 from http://localhost:8000/

==> SQLite file under DATA_DIR
  PASS  found in /data: shop.db uploads

==> Data persists, and a second boot does not re-seed
  PASS  volume at /data persists
  PASS  row counts unchanged across restart: order_items=0 orders=0 product_variants=0 products=0

==> PORT override is honoured (not hardcoded)
  PASS  HTTP 200 from http://localhost:9123/

=== ALL CHECKS PASSED ===
```

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

Live URL: <https://ejliuexstudents2026ui.z28.web.core.windows.net/>

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
  --subject repo:$REPO:ref:refs/heads/main --audiences api://AzureADTokenExchange
az role assignment create --role Contributor \
  --assignee-object-id "$(az identity show -g $RG -n $PREFIX-github --query principalId -o tsv)" \
  --assignee-principal-type ServicePrincipal --scope "$(az group show -n $RG --query id -o tsv)"

# 3. Passwords: generated into files outside the repository, never printed.
mkdir -p ~/.small-shop-secrets && chmod 700 ~/.small-shop-secrets
for f in sql-admin-password catalog-db-password orders-db-password; do
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

# 9. Read-only access for grading.
az role assignment create --assignee <professor-email> --role Reader \
  --scope "$(az group show -n $RG --query id -o tsv)"
```
