# Small Shop

A small Flask online shop, built as one process with SQLite storage.

## Run locally

From the project root, install the dependencies and start the app:

```sh
python -m pip install -r requirements.txt
python app.py
```

The app listens on `0.0.0.0` using port `8000` by default. Set `PORT` to change
the port, or `DATA_DIR` to choose where SQLite stores `shop.db` and uploads.
The default data directory is `./data`.

Check that the app is running at <http://127.0.0.1:8000/health>.
