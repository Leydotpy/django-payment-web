"""Payment API. Untrusted webhooks enter a durable inbox; verified status is domain-owned."""
from __future__ import annotations

import hashlib
from decimal import Decimal

from django.db import transaction
from flutterwave_sdk import Webhook
from flutterwave_sdk.webhook import WebhookSignatureError
from rest_framework import mixins, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from ..domain import PaymentProcessor
from ..events import queue_message
from ..models import PaymentEvent, PaymentIntent
from ..settings import get_payment_settings
from ..usecases import PaymentConflict, create_payment_charge
from .serializers import CreateChargeSerializer, PaymentIntentSerializer


class PaymentIntentViewSet(mixins.RetrieveModelMixin, mixins.ListModelMixin, viewsets.GenericViewSet):
    serializer_class = PaymentIntentSerializer
    lookup_field = "id"
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        queryset = PaymentIntent.objects.all().order_by("-created_at")
        return queryset if self.request.user.is_staff else queryset.filter(owner=self.request.user)

    @action(detail=False, methods=["post"], url_path="charge")
    def charge(self, request: Request) -> Response:
        serializer = CreateChargeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            intent = create_payment_charge(
                owner=request.user, reference=data["reference"], amount=Decimal(data["amount"]),
                currency=data["currency"], customer_id=data["customer_id"],
                payment_method_id=data["payment_method_id"],
                metadata=data.get("metadata"), redirect_url=data.get("redirect_url", ""),
            )
        except PaymentConflict as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        return Response(PaymentIntentSerializer(intent).data, status=status.HTTP_202_ACCEPTED)

    @action(detail=False, methods=["post"], url_path="card-charge")
    def card_charge(self, request: Request) -> Response:
        return Response(
            {"detail": "Direct card payloads are disabled. Tokenize or host the card with the payment provider, then POST to /charge/."},
            status=status.HTTP_410_GONE,
        )

    @action(detail=True, methods=["post"], url_path="verify")
    def verify(self, request: Request, id=None) -> Response:
        intent = self.get_object()
        try:
            verified = PaymentProcessor().verify_intent(intent_id=str(intent.id))
        except Exception:
            return Response({"detail": "Payment verification is temporarily unavailable."}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        return Response(PaymentIntentSerializer(verified).data)


class FlutterwaveWebhookView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes: list[type] = []

    def post(self, request: Request) -> Response:
        secret = get_payment_settings().flutterwave_webhook_secret
        if not secret:
            return Response({"detail": "Webhook verification is not configured."}, status=503)
        try:
            signed = Webhook.construct_event(
                payload=request.body, headers=dict(request.headers),
                secret_hash=secret, allow_legacy_verif_hash=False,
            )
        except WebhookSignatureError:
            return Response({"detail": "Invalid webhook signature."}, status=400)

        payload = signed.to_dict()
        data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
        reference = str(data.get("reference") or data.get("tx_ref") or "")
        charge_id = str(data.get("id") or "")
        event_type = str(payload.get("type") or payload.get("event") or "unknown")
        event_id = hashlib.sha256(request.body).hexdigest()

        with transaction.atomic():
            _, created = PaymentEvent.objects.get_or_create(
                provider_event_id=event_id,
                defaults={"event_type": event_type, "payload": {
                    "reference": reference, "charge_id": charge_id, "status": str(data.get("status") or ""),
                }},
            )
            if created:
                queue_message(
                    "payments.webhook.received", {"provider_event_id": event_id},
                    reference=reference or charge_id or event_id,
                )
        return Response({"received": True}, status=200)
