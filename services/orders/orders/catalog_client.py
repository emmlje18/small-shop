"""HTTP client for the catalog service: the orders side of the ADR-2 seam.

It offers the same three methods OrderService used in Assignment 1
(get_variant_snapshot, decrement_stock, restore_stock), but each one is now an
HTTP call to the catalog's /internal endpoints. Every call has a timeout, so a
slow or stopped catalog can never hang a request in this service.
"""

import logging

import requests

log = logging.getLogger(__name__)


class CatalogUnavailable(Exception):
    """The catalog could not be reached, timed out, or answered with an error."""


class CatalogClient:
    def __init__(self, base_url, internal_token, timeout_s=5.0, session=None):
        self.base_url = base_url.rstrip("/")
        self.internal_token = internal_token
        self.timeout_s = timeout_s
        self.session = session or requests.Session()

    def _request(self, method, path, **kwargs):
        """Send one request; turn network errors and 5xx answers into CatalogUnavailable."""
        try:
            response = self.session.request(
                method,
                f"{self.base_url}{path}",
                headers={"X-Internal-Token": self.internal_token},
                timeout=self.timeout_s,
                **kwargs,
            )
        except requests.RequestException as error:
            log.warning("Catalog call %s %s failed: %s", method, path, error)
            raise CatalogUnavailable("The catalog could not be reached.") from error
        if response.status_code >= 500 or response.status_code == 401:
            # 401 means the shared token is wrong: a configuration problem, not
            # the customer's fault, so it is reported the same way as an outage.
            log.warning("Catalog call %s %s answered %s", method, path, response.status_code)
            raise CatalogUnavailable(f"The catalog answered {response.status_code}.")
        return response

    def get_variant_snapshot(self, variant_id):
        """Current name, option, price and stock of an option, or None if not for sale."""
        response = self._request("GET", f"/internal/variants/{variant_id}")
        if response.status_code == 404:
            return None
        return response.json()

    def decrement_stock(self, variant_id, quantity):
        """Reserve stock: True if reserved, False if not enough is left (409)."""
        response = self._request(
            "POST", f"/internal/variants/{variant_id}/decrement", json={"quantity": quantity}
        )
        return response.status_code == 200

    def restore_stock(self, variant_id, quantity):
        """Give reserved stock back; raises CatalogUnavailable if the catalog refuses."""
        response = self._request(
            "POST", f"/internal/variants/{variant_id}/restore", json={"quantity": quantity}
        )
        if response.status_code != 200:
            raise CatalogUnavailable(f"The catalog answered {response.status_code}.")
