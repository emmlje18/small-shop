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
