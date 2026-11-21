from __future__ import annotations

import json
from django.db import transaction
from django.utils import timezone
from flutterwave_sdk import Webhook
from flutterwave_sdk.webhook import WebhookSignatureError
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.response import Response
from rest_framework.views import APIView

from .serializers import CreateCardChargeSerializer, PaymentIntentSerializer
from ..adapters.broker import get_command_bus
from ..models import PaymentEvent, PaymentStatus
from ..models import PaymentIntent
from ..schemas import CardChargeCommand
from ..settings import get_payment_settings
from ..tasks import process_card_charge


class PaymentIntentViewSet(mixins.RetrieveModelMixin, mixins.ListModelMixin, viewsets.GenericViewSet):
    queryset = PaymentIntent.objects.all().order_by("-created_at")
    serializer_class = PaymentIntentSerializer
    lookup_field = "id"

    @action(detail=False, methods=["post"], url_path="card-charge")
    def card_charge(self, request: Request) -> Response:
        serializer = CreateCardChargeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        with transaction.atomic():
            intent, created = PaymentIntent.objects.get_or_create(
                reference=data["reference"],
                defaults={
                    "amount": data["amount"],
                    "currency": data["currency"],
                    "customer": data["customer"],
                    "metadata": data.get("metadata", {}),
                    "redirect_url": data.get("redirect_url", ""),
                },
            )
            if created:
                intent.mark_queued()

        command = CardChargeCommand(
            intent_id=intent.id,
            reference=intent.reference,
            amount=intent.amount,
            currency=intent.currency,
            customer=data["customer"],
            encrypted_card=data["encrypted_card"],
            redirect_url=data.get("redirect_url") or None,
            metadata=data.get("metadata", {}),
            scenario_key=data.get("scenario_key") or None,
        )
        payload = command.model_dump(mode="json")

        settings = get_payment_settings()
        if settings.broker_backend == "celery":
            process_card_charge.delay(payload)
        else:
            get_command_bus().publish(key=intent.reference, payload=payload)

        return Response(PaymentIntentSerializer(intent).data, status=status.HTTP_202_ACCEPTED)

    @action(detail=True, methods=["post"], url_path="verify")
    def verify(self, request, id=None):
        intent = self.get_object()

        verified = PaymentProcessor().verify_intent(
            intent_id=str(intent.id),
            provider_charge_id=request.data.get("provider_charge_id") or None,
        )

        return Response(PaymentIntentSerializer(verified).data)


class FlutterwaveWebhookView(APIView):
    permission_classes = [AllowAny]
    authentication_classes: list[type] = []

    def post(self, request: Request) -> Response:
        settings = get_payment_settings()
        try:
            event = Webhook.construct_event(
                payload=request.body,
                headers={key: value for key, value in request.headers.items()},
                secret_hash=settings.flutterwave_webhook_secret,
            )
        except WebhookSignatureError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        payload = event.to_dict()
        event_id = str(payload.get("webhook_id") or payload.get("id") or payload.get("event_id"))
        event_type = str(payload.get("event") or payload.get("type") or payload.get("event_type"))
        payment_event, created = PaymentEvent.objects.get_or_create(
            provider_event_id=event_id,
            defaults={"event_type": event_type, "payload": payload},
        )
        if created:
            self._apply_event(payload)
            payment_event.processed_at = timezone.now()
            payment_event.save(update_fields=["processed_at"])
        return Response({"received": True})

    def _apply_event(self, payload: dict[str, object]) -> None:
        data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
        reference = str(data.get("reference", "")) if isinstance(data, dict) else ""
        provider_charge_id = str(data.get("id", "")) if isinstance(data, dict) else ""
        provider_status = str(data.get("status", "")).lower() if isinstance(data, dict) else ""
        if not reference and not provider_charge_id:
            return
        queryset = PaymentIntent.objects.all()
        if reference:
            queryset = queryset.filter(reference=reference)
        else:
            queryset = queryset.filter(provider_charge_id=provider_charge_id)
        intent = queryset.first()
        if not intent:
            return
        intent.last_provider_response = payload
        if provider_status in {"successful", "success", "succeeded", "completed"}:
            intent.status = PaymentStatus.SUCCEEDED
        elif provider_status in {"failed", "cancelled", "canceled"}:
            intent.status = PaymentStatus.FAILED
        intent.save(update_fields=["status", "last_provider_response", "updated_at"])
