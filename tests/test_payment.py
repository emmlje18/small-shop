"""Tests for the predictable local fake payment provider."""

from app.orders.payment import FakePaymentProvider


def test_fake_payment_succeeds_for_normal_card_number():
    """Any entered card number that does not end in 0000 is accepted."""
    payment = FakePaymentProvider()

    payment_ref = payment.charge(500, "4242 4242 4242 4242")

    assert payment_ref.startswith("fake-")


def test_fake_payment_fails_for_card_ending_in_0000():
    """The special declined card number produces no payment reference."""
    payment = FakePaymentProvider()

    assert payment.charge(500, "4242 4242 4242 0000") is None
