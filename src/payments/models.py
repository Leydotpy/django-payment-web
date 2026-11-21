from __future__ import annotations

import uuid
from decimal import Decimal

from django.conf import settings
from django.db import models
from broka.integrations.django.models import AbstractOutboxRecord
from django.utils import timezone


class PaymentStatus(models.TextChoices):
    CREATED = "created", "Created"
    QUEUED = "queued", "Queued"
    PROCESSING = "processing", "Processing"
    REQUIRES_ACTION = "requires_action", "Requires customer action"
    SUCCEEDED = "succeeded", "Succeeded"
    FAILED = "failed", "Failed"
    CANCELLED = "cancelled", "Cancelled"
    VERIFICATION_FAILED = "verification_failed", "Verification failed"


class Provider(models.TextChoices):
    FLUTTERWAVE = "flutterwave", "Flutterwave"


class PaymentIntent(models.Model):
    """Local, auditable representation of a payment request.

    Raw card data is deliberately not persisted here. Store only references, masked provider
    details, metadata and provider status.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    reference = models.CharField(max_length=128, unique=True, db_index=True)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="payment_intents")
    provider = models.CharField(max_length=32, choices=Provider.choices, default=Provider.FLUTTERWAVE)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    currency = models.CharField(max_length=3)
    status = models.CharField(max_length=32, choices=PaymentStatus.choices, default=PaymentStatus.CREATED)
    customer = models.JSONField(default=dict, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    redirect_url = models.URLField(blank=True, default="")
    provider_customer_id = models.CharField(max_length=128, blank=True, default="")
    provider_payment_method_id = models.CharField(max_length=128, blank=True, default="")
    provider_charge_id = models.CharField(max_length=128, blank=True, default="", db_index=True)
    next_action = models.JSONField(default=dict, blank=True)
    last_provider_response = models.JSONField(default=dict, blank=True)
    provider_status = models.CharField(max_length=64, blank=True, default="")
    verification_payload = models.JSONField(default=dict, blank=True)
    verified_at = models.DateTimeField(null=True, blank=True)
    failure_code = models.CharField(max_length=128, blank=True, default="")
    failure_message = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["status", "created_at"]),
            models.Index(fields=["provider", "provider_charge_id"]),
        ]

    def mark_queued(self) -> None:
        self.status = PaymentStatus.QUEUED
        self.save(update_fields=["status", "updated_at"])

    def mark_processing(self) -> None:
        self.status = PaymentStatus.PROCESSING
        self.save(update_fields=["status", "updated_at"])

    def mark_failed(self, *, message: str, code: str = "") -> None:
        self.status = PaymentStatus.FAILED
        self.failure_message = message
        self.failure_code = code
        self.save(update_fields=["status", "failure_message", "failure_code", "updated_at"])


class PaymentAttempt(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    intent = models.ForeignKey(PaymentIntent, on_delete=models.CASCADE, related_name="attempts")
    status = models.CharField(max_length=32, default="started", db_index=True)
    request_payload = models.JSONField(default=dict, blank=True)
    response_payload = models.JSONField(default=dict, blank=True)
    error_message = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(default=timezone.now)
    completed_at = models.DateTimeField(null=True, blank=True)


class PaymentEvent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    provider = models.CharField(max_length=32, choices=Provider.choices, default=Provider.FLUTTERWAVE)
    provider_event_id = models.CharField(max_length=128, unique=True, db_index=True)
    event_type = models.CharField(max_length=128, db_index=True)
    payload = models.JSONField(default=dict)
    processed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)


class OutboxEvent(models.Model):
    """Transactional outbox for events this service must publish."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    topic = models.CharField(max_length=128, db_index=True)
    key = models.CharField(max_length=128, db_index=True)
    payload = models.JSONField(default=dict)
    attempts = models.PositiveIntegerField(default=0)
    published_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    @property
    def is_published(self) -> bool:
        return self.published_at is not None


class PaymentOutboxRecord(AbstractOutboxRecord):
    """Application-owned persistent Broka outbox. Stored in the same DB transaction as payments."""

    class Meta:
        db_table = "payments_broka_outbox"
        ordering = ("available_at", "created_at", "id")


class AuthorizedPaymentMethod(models.Model):
    """Provider-authenticated customer consent, provisioned by a trusted integration/admin."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="authorized_payment_methods")
    provider_customer_id = models.CharField(max_length=128)
    provider_payment_method_id = models.CharField(max_length=128, unique=True)
    consent_reference = models.CharField(max_length=128)
    verified_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        indexes = [models.Index(fields=["owner", "is_active"])]
