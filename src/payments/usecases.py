"""Shared authenticated charge initiation for REST and GraphQL."""
from __future__ import annotations

from decimal import Decimal
from django.db import transaction

from .events import queue_message
from .models import AuthorizedPaymentMethod, PaymentIntent, PaymentStatus
from .schemas import PaymentChargeCommand


class PaymentConflict(ValueError):
    pass


def create_payment_charge(
    *, owner, reference: str, amount: Decimal, currency: str,
    customer_id: str, payment_method_id: str, metadata: dict | None = None,
    redirect_url: str = "",
) -> PaymentIntent:
    amount = Decimal(str(amount))
    currency = currency.upper()
    if amount <= 0 or not currency.isalpha() or len(currency) != 3:
        raise PaymentConflict("Invalid payment amount or currency.")
    if not reference.strip() or not customer_id or not payment_method_id:
        raise PaymentConflict("Reference, customer and payment method are required.")
    if not (6 <= len(reference) <= 42) or not all(ch.isascii() and (ch.isalnum() or ch == "-") for ch in reference):
        raise PaymentConflict("Reference must be 6–42 ASCII letters, digits or hyphens.")
    if not AuthorizedPaymentMethod.objects.filter(
        owner=owner, provider_customer_id=customer_id,
        provider_payment_method_id=payment_method_id,
        verified_at__isnull=False, is_active=True,
    ).exists():
        raise PaymentConflict("This payment method is not authorised for the requesting account.")
    with transaction.atomic():
        intent, created = PaymentIntent.objects.select_for_update().get_or_create(
            reference=reference,
            defaults={
                "owner": owner, "amount": amount, "currency": currency,
                "provider_customer_id": customer_id,
                "provider_payment_method_id": payment_method_id,
                "metadata": metadata or {}, "redirect_url": redirect_url,
                "status": PaymentStatus.QUEUED,
            },
        )
        if not created:
            if (
                intent.owner_id != owner.pk or intent.amount != amount
                or intent.currency != currency or intent.provider_customer_id != customer_id
                or intent.provider_payment_method_id != payment_method_id
            ):
                # Do not reveal another tenant's payment intent.
                raise PaymentConflict("Payment reference is unavailable or conflicts with the original request.")
            return intent

        command = PaymentChargeCommand(
            intent_id=intent.id, reference=reference, amount=amount, currency=currency,
            customer_id=customer_id, payment_method_id=payment_method_id,
        )
        queue_message("payments.charge.requested", command.model_dump(mode="json"), reference=reference)
        return intent
