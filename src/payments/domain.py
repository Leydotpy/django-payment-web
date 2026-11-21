"""Payment domain: provider calls are never trusted without independent verification."""
from __future__ import annotations

import hashlib
from decimal import Decimal
from typing import Any

from django.db import transaction
from django.utils import timezone
from flutterwave_sdk import RequestOptions

from .events import queue_message
from .models import PaymentAttempt, PaymentEvent, PaymentIntent, PaymentStatus
from .schemas import PaymentChargeCommand, PaymentCompletedEvent, PaymentFailedEvent
from .sdk import get_flutterwave_client


def operation_key(intent_id: object, operation: str) -> str:
    """Stable alphanumeric key specific to one provider operation."""
    return hashlib.sha256(f"flutterwave:{operation}:{intent_id}".encode()).hexdigest()


class PaymentProcessor:
    def process_charge(self, command: PaymentChargeCommand) -> PaymentIntent:
        """Submit tokenised payment references; no card or CVV data crosses the broker."""
        with transaction.atomic():
            intent = PaymentIntent.objects.select_for_update().get(pk=command.intent_id)
            if (
                intent.reference != command.reference
                or intent.amount != command.amount
                or intent.currency != command.currency
                or intent.provider_customer_id != command.customer_id
                or intent.provider_payment_method_id != command.payment_method_id
            ):
                raise ValueError("Charge command does not match the persisted payment intent.")
            if intent.status not in {PaymentStatus.CREATED, PaymentStatus.QUEUED}:
                # Duplicate deliveries do not create a second provider charge.
                return intent
            intent.mark_processing()
            attempt = PaymentAttempt.objects.create(
                intent=intent,
                request_payload={"reference": command.reference, "customer_id": command.customer_id,
                                 "payment_method_id": command.payment_method_id},
            )

        try:
            response = get_flutterwave_client().charges.create(
                amount=command.amount,
                currency=command.currency,
                reference=command.reference,
                customer_id=command.customer_id,
                payment_method_id=command.payment_method_id,
                options=RequestOptions(
                    idempotency_key=operation_key(intent.id, "charge"),
                    trace_id=f"intent-{intent.id}",
                ),
            )
            charge = response.data
            charge_id = str(charge.get("id") or "")
            provider_status = str(charge.get("status") or "").lower()
            action = charge.get("next_action")
            next_action = action.to_dict() if hasattr(action, "to_dict") else (action or {})
        except Exception:
            # The remote outcome is UNKNOWN on connection loss/timeout/5xx.
            # Never declare failure or issue another charge until reconciliation.
            with transaction.atomic():
                locked = PaymentIntent.objects.select_for_update().get(pk=intent.id)
                locked.failure_code = "provider_outcome_unknown"
                locked.failure_message = "Provider response unavailable; reconciliation required."
                locked.save(update_fields=["failure_code", "failure_message", "updated_at"])
                attempt.status = "indeterminate"
                attempt.completed_at = timezone.now()
                attempt.save(update_fields=["status", "completed_at"])
            return PaymentIntent.objects.get(pk=intent.id)

        with transaction.atomic():
            locked = PaymentIntent.objects.select_for_update().get(pk=intent.id)
            locked.provider_charge_id = charge_id
            locked.provider_status = provider_status
            locked.next_action = next_action
            locked.last_provider_response = response.raw
            locked.status = PaymentStatus.REQUIRES_ACTION if next_action else PaymentStatus.PROCESSING
            locked.failure_code = ""
            locked.failure_message = ""
            locked.save()
            attempt.status = "completed"
            attempt.response_payload = response.raw
            attempt.completed_at = timezone.now()
            attempt.save(update_fields=["status", "response_payload", "completed_at"])
            if charge_id:
                queue_message("payments.verification.requested", {"intent_id": str(intent.id)}, reference=locked.reference)

        if charge_id and provider_status in {"successful", "success", "succeeded", "completed", "failed"}:
            return self.verify_intent(intent_id=str(intent.id))
        return PaymentIntent.objects.get(pk=intent.id)

    def verify_intent(self, *, intent_id: str) -> PaymentIntent:
        with transaction.atomic():
            intent = PaymentIntent.objects.select_for_update().get(pk=intent_id)
            if intent.status in {PaymentStatus.SUCCEEDED, PaymentStatus.CANCELLED}:
                return intent
            charge_id = intent.provider_charge_id
            if not charge_id:
                intent.failure_code = "missing_provider_charge_id"
                intent.failure_message = "Cannot verify until a provider charge ID is recovered."
                intent.save(update_fields=["failure_code", "failure_message", "updated_at"])
                return intent
            expected_reference = intent.reference
            expected_amount = Decimal(intent.amount)
            expected_currency = intent.currency

        result = get_flutterwave_client().transactions.verify(
            charge_id,
            expected_reference=expected_reference,
            expected_amount=expected_amount,
            expected_currency=expected_currency,
            options=RequestOptions(trace_id=f"verify-{intent_id}"),
        )
        with transaction.atomic():
            locked = PaymentIntent.objects.select_for_update().get(pk=intent_id)
            if locked.status in {PaymentStatus.SUCCEEDED, PaymentStatus.CANCELLED}:
                return locked
            if locked.provider_charge_id != charge_id:
                # A concurrent reconciliation found a different provider operation.
                raise ValueError("Provider charge changed during verification.")
            locked.provider_status = result.status
            locked.verification_payload = result.response.raw
            locked.last_provider_response = result.response.raw

            if result.is_trusted_success:
                locked.status = PaymentStatus.SUCCEEDED
                locked.verified_at = timezone.now()
                locked.failure_code = ""
                locked.failure_message = ""
                locked.save()
                event = PaymentCompletedEvent(
                    intent_id=locked.id, reference=locked.reference,
                    provider_charge_id=charge_id, provider_status=result.status,
                    amount=locked.amount, currency=locked.currency, metadata=locked.metadata,
                )
                queue_message(event.event_type, event.model_dump(mode="json"), reference=locked.reference)
            elif result.is_successful and result.mismatch_reasons:
                locked.status = PaymentStatus.VERIFICATION_FAILED
                locked.failure_code = "verification_mismatch"
                locked.failure_message = ",".join(result.mismatch_reasons)
                locked.save()
            elif result.is_failed:
                locked.status = PaymentStatus.FAILED
                locked.failure_code = result.status
                locked.failure_message = "Provider independently confirmed an unsuccessful charge."
                locked.save()
                event = PaymentFailedEvent(
                    intent_id=locked.id, reference=locked.reference,
                    provider_charge_id=charge_id, message=locked.failure_message,
                    code=locked.failure_code, metadata=locked.metadata,
                )
                queue_message(event.event_type, event.model_dump(mode="json"), reference=locked.reference)
            else:
                if locked.status != PaymentStatus.REQUIRES_ACTION:
                    locked.status = PaymentStatus.PROCESSING
                locked.save()
            return locked

    def reconcile_intent(self, *, intent_id: str) -> PaymentIntent:
        """Recover a provider charge ID after a timed-out create, then verify the result."""
        intent = PaymentIntent.objects.get(pk=intent_id)
        if intent.status in {PaymentStatus.SUCCEEDED, PaymentStatus.CANCELLED}:
            return intent
        if not intent.provider_charge_id:
            response = get_flutterwave_client().charges.list(reference=intent.reference)
            matches = [
                item for item in response.data
                if str(item.get("reference") or item.get("tx_ref") or "") == intent.reference
                and item.get("id")
            ]
            if len(matches) > 1:
                raise RuntimeError("Multiple provider charges share the payment reference; review required.")
            if len(matches) == 1:
                with transaction.atomic():
                    locked = PaymentIntent.objects.select_for_update().get(pk=intent.id)
                    if not locked.provider_charge_id:
                        locked.provider_charge_id = str(matches[0].get("id"))
                        locked.save(update_fields=["provider_charge_id", "updated_at"])
            else:
                return intent
        return self.verify_intent(intent_id=str(intent.id))

    def process_webhook(self, *, provider_event_id: str) -> None:
        """Consume a signed webhook inbox record and independently verify its payment."""
        with transaction.atomic():
            event = PaymentEvent.objects.select_for_update().get(provider_event_id=provider_event_id)
            if event.processed_at:
                return
            data = event.payload
            reference = str(data.get("reference") or "")
            charge_id = str(data.get("charge_id") or "")

        intent = (
            PaymentIntent.objects.filter(reference=reference).first() if reference else
            PaymentIntent.objects.filter(provider_charge_id=charge_id).first()
        )
        if intent is not None:
            with transaction.atomic():
                locked = PaymentIntent.objects.select_for_update().get(pk=intent.pk)
                if not locked.provider_charge_id and charge_id and locked.reference == reference:
                    locked.provider_charge_id = charge_id
                    locked.save(update_fields=["provider_charge_id", "updated_at"])
            self.verify_intent(intent_id=str(intent.id))

        with transaction.atomic():
            event = PaymentEvent.objects.select_for_update().get(provider_event_id=provider_event_id)
            if not event.processed_at:
                event.processed_at = timezone.now()
                event.save(update_fields=["processed_at"])


def serialize_intent(intent: PaymentIntent) -> dict[str, Any]:
    return {
        "id": str(intent.id), "reference": intent.reference,
        "amount": str(intent.amount), "currency": intent.currency,
        "status": intent.status, "provider": intent.provider,
        "provider_charge_id": intent.provider_charge_id,
        "provider_status": intent.provider_status,
        "verified_at": intent.verified_at.isoformat() if intent.verified_at else None,
        "next_action": intent.next_action, "metadata": intent.metadata,
        "created_at": intent.created_at.isoformat(), "updated_at": intent.updated_at.isoformat(),
    }
