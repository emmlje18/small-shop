"""Payment provider interface and local fake payment provider."""

from uuid import uuid4


class PaymentProvider:
    """Describe the one payment operation used by the order service."""

    def charge(self, amount_cents, card_number):
        """Return a payment reference on success, or None on failure."""
        raise NotImplementedError


class FakePaymentProvider(PaymentProvider):
    """Provide predictable local payment results without a real payment service."""

    def charge(self, amount_cents, card_number):
        """Fail cards ending in 0000 and accept every other entered card."""
        if not isinstance(amount_cents, int) or amount_cents <= 0:
            return None

        clean_card_number = str(card_number).replace(" ", "").replace("-", "")
        if not clean_card_number or clean_card_number.endswith("0000"):
            return None

        return f"fake-{uuid4().hex}"
