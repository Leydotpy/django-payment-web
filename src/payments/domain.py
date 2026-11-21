from __future__ import annotations

from decimal import Decimal
from decimal import Decimal
from django.db import transaction
from django.db import transaction
from django.utils import timezone
from django.utils import timezone
from flutterwave_sdk import RequestOptions
from flutterwave_sdk import RequestOptions
from flutterwave_sdk.errors import FlutterwaveError
from typing import Any

from .models import PaymentAttempt
from .models import PaymentIntent, PaymentStatus, OutboxEvent
from .schemas import CardChargeCommand
from .schemas import PaymentCompletedEvent, PaymentFailedEvent
from .sdk import get_flutterwave_client


class PaymentProcessor:
    """Runs provider-side payment commands.

    This class is intentionally framework-light. Celery, RabbitMQ, Kafka, REST and GraphQL
    adapters call into it instead of duplicating provider logic.
    """

    def process_card_charge(self, command: CardChargeCommand) -> PaymentIntent:
        with transaction.atomic():
            intent = PaymentIntent.objects.select_for_update().get(id=command.intent_id)
            if intent.status in {PaymentStatus.SUCCEEDED, PaymentStatus.CANCELLED}:
                return intent
            intent.mark_processing()
            attempt = PaymentAttempt.objects.create(
                intent=intent,
                request_payload=command.model_dump(mode="json", exclude={"encrypted_card"}),
            )

        client = get_flutterwave_client()
        options = RequestOptions(
            trace_id=f"intent-{intent.id}",
            idempotency_key=f"payment-intent-{intent.id}",
            scenario_key=command.scenario_key,
        )

        try:
            customer_response = client.customers.create(
                **command.customer.model_dump(exclude_none=True),
                options=options,
            )
            customer = customer_response.data
            payment_method_response = client.payment_methods.create(
                type="card",
                customer_id=str(customer.id),
                card=command.encrypted_card.model_dump(),
                options=options,
            )
            payment_method = payment_method_response.data
            charge_response = client.charges.create(
                amount=float(command.amount),
                currency=command.currency,
                reference=command.reference,
                customer_id=str(customer.id),
                payment_method_id=str(payment_method.id),
                redirect_url=command.redirect_url,
                meta=command.metadata,
                options=options,
            )
            charge = charge_response.data
        except FlutterwaveError as exc:
            return self._fail_intent(intent, attempt, message=str(exc), code=exc.__class__.__name__)
        except Exception as exc:  # pragma: no cover - protects worker process boundaries
            return self._fail_intent(intent, attempt, message=str(exc), code=exc.__class__.__name__)

        provider_status = str(charge.get("status", "")).lower()
        next_action = charge.get("next_action")
        next_action_payload = next_action.to_dict() if hasattr(next_action, "to_dict") else (next_action or {})

        with transaction.atomic():
            locked = PaymentIntent.objects.select_for_update().get(id=intent.id)
            locked.provider_customer_id = str(customer.id)
            locked.provider_payment_method_id = str(payment_method.id)
            locked.provider_charge_id = str(charge.id)
            locked.next_action = next_action_payload
            locked.last_provider_response = charge_response.raw
            locked.status = (
                PaymentStatus.SUCCEEDED
                if provider_status in {"successful", "success", "succeeded", "completed"}
                else PaymentStatus.REQUIRES_ACTION if next_action_payload else PaymentStatus.PROCESSING
            )
            locked.save()

            attempt.status = "completed"
            attempt.response_payload = charge_response.raw
            attempt.completed_at = timezone.now()
            attempt.save(update_fields=["status", "response_payload", "completed_at"])

            event = (
                PaymentCompletedEvent(
                    intent_id=locked.id,
                    reference=locked.reference,
                    provider_charge_id=locked.provider_charge_id,
                    provider_status=provider_status,
                    amount=Decimal(locked.amount),
                    currency=locked.currency,
                    metadata=locked.metadata,
                )
                if locked.status == PaymentStatus.SUCCEEDED
                else None
            )
            if event is not None:
                OutboxEvent.objects.create(
                    topic="payments.events",
                    key=locked.reference,
                    payload=event.model_dump(mode="json"),
                )
            return locked

    def _fail_intent(
            self,
            intent: PaymentIntent,
            attempt: PaymentAttempt,
            *,
            message: str,
            code: str,
    ) -> PaymentIntent:
        with transaction.atomic():
            locked = PaymentIntent.objects.select_for_update().get(id=intent.id)
            locked.mark_failed(message=message, code=code)
            attempt.status = "failed"
            attempt.error_message = message
            attempt.completed_at = timezone.now()
            attempt.save(update_fields=["status", "error_message", "completed_at"])
            OutboxEvent.objects.create(
                topic="payments.events",
                key=locked.reference,
                payload=PaymentFailedEvent(
                    intent_id=locked.id,
                    reference=locked.reference,
                    message=message,
                    code=code,
                    metadata=locked.metadata,
                ).model_dump(mode="json"),
            )
            return locked

    def verify_intent(
            self,
            *,
            intent_id: str,
            provider_charge_id: str | None = None,
    ) -> PaymentIntent:
        with transaction.atomic():
            intent = PaymentIntent.objects.select_for_update().get(id=intent_id)

            charge_id = provider_charge_id or intent.provider_charge_id
            if not charge_id:
                intent.status = PaymentStatus.FAILED
                intent.failure_code = "missing_provider_charge_id"
                intent.failure_message = "Cannot verify payment without a provider charge id."
                intent.save()
                return intent

        client = get_flutterwave_client()

        result = client.transactions.verify(
            charge_id,
            expected_reference=intent.reference,
            expected_amount=Decimal(intent.amount),
            expected_currency=intent.currency,
            options=RequestOptions(trace_id=f"verify-{intent.id}"),
        )

        with transaction.atomic():
            locked = PaymentIntent.objects.select_for_update().get(id=intent.id)

            locked.provider_status = result.status
            locked.verification_payload = result.response.raw
            locked.last_provider_response = result.response.raw

            if result.is_trusted_success:
                locked.status = PaymentStatus.SUCCEEDED
                locked.verified_at = timezone.now()
                locked.failure_code = ""
                locked.failure_message = ""
                locked.save()

                OutboxEvent.objects.create(
                    topic="payments.events",
                    key=locked.reference,
                    payload=PaymentCompletedEvent(
                        intent_id=locked.id,
                        reference=locked.reference,
                        provider_charge_id=locked.provider_charge_id,
                        provider_status=result.status,
                        amount=locked.amount,
                        currency=locked.currency,
                        verified=True,
                        metadata=locked.metadata,
                    ).model_dump(mode="json"),
                )

                return locked

            if result.is_successful and result.mismatch_reasons:
                locked.status = PaymentStatus.VERIFICATION_FAILED
                locked.failure_code = "verification_mismatch"
                locked.failure_message = ",".join(result.mismatch_reasons)
                locked.save()
                return locked

            if result.is_failed:
                locked.status = PaymentStatus.FAILED
                locked.failure_code = result.status
                locked.failure_message = "Provider returned a failed payment status."
                locked.save()

                OutboxEvent.objects.create(
                    topic="payments.events",
                    key=locked.reference,
                    payload=PaymentFailedEvent(
                        intent_id=locked.id,
                        reference=locked.reference,
                        provider_charge_id=locked.provider_charge_id,
                        message=locked.failure_message,
                        code=locked.failure_code,
                        metadata=locked.metadata,
                    ).model_dump(mode="json"),
                )

                return locked

            locked.status = PaymentStatus.PROCESSING
            locked.save()
            return locked


def serialize_intent(intent: PaymentIntent) -> dict[str, Any]:
    return {
        "id": str(intent.id),
        "reference": intent.reference,
        "amount": str(intent.amount),
        "currency": intent.currency,
        "status": intent.status,
        "provider": intent.provider,
        "provider_charge_id": intent.provider_charge_id,
        "next_action": intent.next_action,
        "metadata": intent.metadata,
        "created_at": intent.created_at.isoformat(),
        "updated_at": intent.updated_at.isoformat(),
    }
