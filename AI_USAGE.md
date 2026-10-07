# AI Usage Log

This log records meaningful AI assistance used while building the project.

## 2026-10-06 — Commit 1: Flask startup and SQLite schema

- **Commit:** `4103ede` — Create Flask startup skeleton and SQLite schema
- **Tool:** ChatGPT (Codex)
- **Prompt:** Review and implement my Stage 1 plan: create the app folder
  structure, configuration, SQLite schema creation at startup, an app entry
  point that binds to `0.0.0.0` and reads `PORT`, a root `requirements.txt`,
  `.gitignore`, a minimal README, and a `/health` route. Do not add shop features
  yet.
- **Disposition:** Modified
- **What changed and why:** The requested startup and schema were implemented.
  The app also creates `DATA_DIR/uploads` automatically and warns when the
  default admin password is active.
- **How it works (in own words):** `app.py` calls `create_app()` to build the
  Flask application, then starts it on host server `0.0.0.0` and port `8000` by default. `create_app()` reads settings from the environment, creates the data and upload folders,
  initializes the SQLite tables, and registers `/health` so I can
  check that the web app responds.

## 2026-10-06 — Commit 2: Catalog storage and service operations

- **Commit:** `e8ef8d5` — Add catalog storage and service operations
- **Tool:** ChatGPT (Codex)
- **Prompt:** Implement Stage 2 of the Flask shop: catalog storage and service
  logic for products and variants, nonnegative price and stock validation, and
  the three catalog operations orders will need. Keep SQL in the catalog
  repository, preserve the domain seam, and record the catalog design decision.
- **Disposition:** Modified
- **What changed and why:** The catalog service was adapted to the existing
  SQLite schema and connection helper. Product and variant operations are
  grouped in `CatalogService`, which can be injected into the future order
  service. Database connections now close after each operation.
- **How it works (in own words):** `CatalogService` checks product names, prices, option labels, and stock before
  saving them. It calls `repository.py`, where SQL creates and lists products and
  variants. For checkout, `get_variant_snapshot()` returns the product name,
  option, price, and stock; `decrement_stock()` runs one conditional update so it
  cannot reduce stock below zero; and `restore_stock()` adds reserved units back.
  Each repository operation commits its own database work and closes its SQLite
  connection.

## 2026-10-07 — Commit 3: Container setup for the revised requirements

- **Commit:** `864c39f` — Add provided container template and run instructions
- **Tool:** ChatGPT (Codex)
- **Prompt:** Compare my project with the updated assignment repository.
  Identify any required changes, and make the necessary updates to my
  individual project.
- **Disposition:** Modified
- **What changed and why:** The revised brief requires using the provided
  Dockerfile template. I copied that template to the project root and copied the
  provided checker and its instructions into `container/`. I changed only the
  source-copy TODO so the image includes the `app/` package, pinned Flask, and
  documented direct and container run commands and environment defaults.
- **How it works (in own words):** The Dockerfile tells Docker
  to start with a small Python image, install the exact Flask version from
  `requirements.txt`, and copy `app.py` and the `app/` folder into the image.
  When the container starts, `CMD` runs `python app.py`. The app listens on the
  configured port and puts its SQLite file under `/data`, where Docker can keep
  it in a volume so it does not get erased. The copied `container/run.sh` builds
  the image and checks that it starts, responds, honors the port setting, and
  keeps its database under `/data`.

## 2026-10-07 — Commit 4: Admin catalog pages

- **Commit:** `0066d9d` — Add admin catalog management pages
- **Tool:** ChatGPT (Codex)
- **Prompt:** Build stage 3: admin login, product listing and
  creation with a first variant, image extension and size validation, and plain
  templates. Explain each added function so I can understand the code.
- **Disposition:** Modified
- **What changed and why:** Added an admin blueprint and templates, connected
  them to the app, added image upload validation, and extended product creation
  to store an optional image path. The provided Dockerfile now copies the
  templates and stylesheet needed by those pages.
- **How it works (in own words):** The login route compares the
  entered password with `ADMIN_PASSWORD` and stores a signed-in flag in the
  Flask session. `admin_required` checks that flag before showing admin pages.
  The product form converts a price such as `12.50` into integer cents, validates
  stock as a whole nonnegative number, checks an optional image's extension,
  and lets `CatalogService` save the product and its first variant. The catalog
  page asks the service for products and their variants, then Jinja displays
  them using the templates.

## 2026-10-08 — Commit 6: Multiple product options

- **Commit:** `6600c95` — Allow multiple product options in admin form
- **Tool:** ChatGPT (Codex)
- **Prompt:** Extend the admin product form so one product can have as many
  variations as needed, such as different colours of one product. Do not add
  the example product as shop data.
- **Disposition:** Modified
- **What changed and why:** The product form can now add and remove option rows.
  The route validates every label and stock value before saving the product and
  all of its variants.
- **How it works, draft to adapt in my own words:** The repeated form inputs use
  the same names, so `request.form.getlist()` collects every option label and
  every stock value. `parse_variants()` matches each label with its stock and
  validates them before the catalog service saves anything. A small JavaScript
  file copies a hidden option-row template when I click “Add option”; it also
  prevents me from removing the last required option row.
