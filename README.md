# Small Shop

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

The checker requires Docker to be running. Add its passing output here before
submission.
