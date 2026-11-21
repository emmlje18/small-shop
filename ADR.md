# Architecture Decision Records

## [1]. Use Flask and SQLite in one local process
Date: 2026-10-06
Status: Decided
Context: The assignment requires a small monolithic application that starts with one command, uses SQLite, and can later run in one container. The project also needs to be simple enough to explain during a closed-book comprehension check.
Decision: Use Python with Flask for the web app and the standard-library `sqlite3` module for persistence. Keep the app in one process and organize catalog and orders as separate folders inside the same application.
Alternatives considered: A larger framework such as Django would include features this small shop does not need; a separate database server would violate the single-container storage requirement.
Consequences: Flask keeps request handling small and `sqlite3` avoids an ORM or external database dependency. The app remains easy to start locally, while the catalog and orders code can be separated later if the next assignment calls for it.

## [2]. Keep the catalog and orders as separate backend domains
Date: 2026-10-06
Status: Decided
Context: The shop has two backend responsibilities that may later become separate services: maintaining products and stock, and recording purchases. Checkout needs catalog information and stock changes, but it should not depend on catalog SQL or catalog tables directly.
Decision: Keep catalog SQL in `app/catalog/repository.py` and expose product operations through `CatalogService`. Give orders only the `get_variant_snapshot`, `decrement_stock`, and `restore_stock` operations it needs through an injected catalog service.
Alternatives considered: Put all shop SQL in one repository, which would make checkout depend directly on catalog table details; duplicate catalog SQL in orders, which could allow the two domains to disagree about stock and product data.
Consequences: Catalog can change its table queries without requiring orders to change as long as the three operations keep their behavior. A checkout may need to coordinate separate catalog and order transactions, so order logic must explicitly restore reserved stock if checkout fails.

## [3]. Save product details as order-item snapshots
Date: 2026-10-10
Status: Decided
Context: A product's name, price, and options can change after a customer buys it. The orders domain must also remain independent from catalog tables so it can be separated later.
Decision: Store money as integer cents. Save `product_name`, `option_label`, and `unit_price_cents` in each `order_items` row at checkout, and keep `variant_id` as a plain integer without a foreign key to catalog tables.
Alternatives considered: Link each order item only to the current product variant with a foreign key. That would make old order details depend on later catalog changes and would couple the two domains more tightly.
Consequences: Old orders retain the original product details and price even if the catalog changes. The data is intentionally duplicated, and stock restoration must use the saved variant id. An option removed from sale keeps its variant row and is set to zero stock, so saved orders can still refer to that id.

## [4]. Test domain rules with pytest and temporary SQLite files
Date: 2026-10-10
Status: Decided
Context: The assignment requires at least 70% coverage of core business logic. Cart and checkout rules include stock changes that are difficult to confirm reliably through manual browser testing alone.
Decision: Use `pytest` and `pytest-cov` for service, repository, and fake-payment tests. Use a separate temporary SQLite database for each database test and an in-memory fake catalog for order-service tests.
Alternatives considered: Test only through Flask pages or manually in the browser. Those approaches would make it harder to test failure paths such as overselling and payment failure, and would focus coverage on routes instead of business rules.
Consequences: Tests run quickly and can safely check stock restoration and order status changes. The tests do not cover template rendering or browser behavior, so those remain part of manual container verification.

## [5]. Do not integrate a real payment provider
Date: 2026-10-11
Status: Decided
Context: The shop needs a checkout outcome so it can demonstrate paid and cancelled orders, but the assignment is a self-contained local application. A real payment provider would require external accounts, secret keys, network access, and additional security responsibilities.
Decision: Use `FakePaymentProvider` inside the same process. Its `charge()` method declines card numbers ending in `0000` and returns a generated fake reference for other card numbers.
Alternatives considered: Integrate Stripe or another real payment provider. That would add an external runtime dependency and would require handling real credentials and payment data, which is outside the assignment scope.
Consequences: Checkout can exercise success and failure paths without processing real money or storing card numbers. A later real integration could replace `FakePaymentProvider` while keeping `OrderService` dependent on the same `charge()` operation.

## [6]. Split into catalog and orders services along the ADR-2 seam
Date: 2026-11-20
Status: Decided
Context: Assignment 2 needs one service per domain, each with its own database, talking over HTTP, with a static UI on a different website.
Decision: Catalog owns products and variants; orders owns orders and order items. ADR-2's three operations become catalog endpoints (`/internal/variants/{id}`, `/decrement`, `/restore`) that orders calls with a secret `X-Internal-Token`. Checkout stays in orders and calls catalog on the server. Images move into the catalog database, admin sends its password in a header, and the cart moves to the browser, because container disks are wiped and cross-site cookies are blocked.
Alternatives considered: Checkout in the UI calling both services, but a closed tab could skip giving stock back. Image URLs instead of uploads, but that drops the upload feature.
Consequences: ADR-2 held, and no table had to move. Checkout now spans two databases, so orders must give stock back itself when payment fails. The internal endpoints are public and rely on the token.

## [7]. One database per service, versioned SQL migrations, forward-only recovery
Date: 2026-11-21
Status: Decided
Context: The monolith kept all four tables in one SQLite file and created them on first boot. Now each service needs its own SQL Server database, and the schema must change in place once real data exists.
Decision: Catalog's database holds `products` and `product_variants`; orders' database holds `orders` and `order_items`. Each service has numbered SQL files (`migrations/001_init.sql`, `002_...`) and a small runner that records applied files in `schema_migrations`, runs only new ones in order, and commits each file with its record in one transaction. The Dockerfile runs it once before gunicorn starts. The Assignment 1 SQLite data is not copied; the new databases start empty.
Alternatives considered: A migration tool such as Alembic, which adds a dependency and hides the SQL I need to explain. Creating tables on every boot, which cannot change a table that already has data.
Consequences: The foreign key from `order_items.variant_id` to the catalog is gone, so the database no longer checks it; orders only stores ids it got from catalog at checkout, and saves the product name and price as a snapshot so old orders stay readable. A failed migration rolls back and stops the container, so the old revision keeps serving. Applied files are never edited: a bad migration is fixed by a new migration, or in the worst case by Azure SQL's point-in-time restore.
