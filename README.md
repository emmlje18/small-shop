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
up to 2 MiB per request.

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

Latest result: **13 tests passed, 79% coverage** across the selected catalog and
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
  PASS  image size 232 MB

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
