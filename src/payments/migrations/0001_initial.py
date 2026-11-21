# Generated manually for the scaffold.
from __future__ import annotations

import uuid
from decimal import Decimal

import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="PaymentIntent",
            fields=[
                ("id", models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
                ("reference", models.CharField(max_length=128, unique=True, db_index=True)),
                ("provider", models.CharField(max_length=32, default="flutterwave")),
                ("amount", models.DecimalField(max_digits=14, decimal_places=2)),
                ("currency", models.CharField(max_length=3)),
                ("status", models.CharField(max_length=32, default="created")),
                ("customer", models.JSONField(default=dict, blank=True)),
                ("metadata", models.JSONField(default=dict, blank=True)),
                ("redirect_url", models.URLField(blank=True, default="")),
                ("provider_customer_id", models.CharField(max_length=128, blank=True, default="")),
                ("provider_payment_method_id", models.CharField(max_length=128, blank=True, default="")),
                ("provider_charge_id", models.CharField(max_length=128, blank=True, default="", db_index=True)),
                ("next_action", models.JSONField(default=dict, blank=True)),
                ("last_provider_response", models.JSONField(default=dict, blank=True)),
                ("failure_code", models.CharField(max_length=128, blank=True, default="")),
                ("failure_message", models.TextField(blank=True, default="")),
                ("created_at", models.DateTimeField(default=django.utils.timezone.now, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "indexes": [
                    models.Index(fields=["status", "created_at"], name="payments_pa_status_4c47f9_idx"),
                    models.Index(fields=["provider", "provider_charge_id"], name="payments_pa_provider_9e031a_idx"),
                ],
            },
        ),
        migrations.CreateModel(
            name="PaymentAttempt",
            fields=[
                ("id", models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
                ("status", models.CharField(max_length=32, default="started", db_index=True)),
                ("request_payload", models.JSONField(default=dict, blank=True)),
                ("response_payload", models.JSONField(default=dict, blank=True)),
                ("error_message", models.TextField(blank=True, default="")),
                ("created_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("completed_at", models.DateTimeField(null=True, blank=True)),
                ("intent", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="attempts", to="payments.paymentintent")),
            ],
        ),
        migrations.CreateModel(
            name="PaymentEvent",
            fields=[
                ("id", models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
                ("provider", models.CharField(max_length=32, default="flutterwave")),
                ("provider_event_id", models.CharField(max_length=128, unique=True, db_index=True)),
                ("event_type", models.CharField(max_length=128, db_index=True)),
                ("payload", models.JSONField(default=dict)),
                ("processed_at", models.DateTimeField(null=True, blank=True)),
                ("created_at", models.DateTimeField(default=django.utils.timezone.now, db_index=True)),
            ],
        ),
        migrations.CreateModel(
            name="OutboxEvent",
            fields=[
                ("id", models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
                ("topic", models.CharField(max_length=128, db_index=True)),
                ("key", models.CharField(max_length=128, db_index=True)),
                ("payload", models.JSONField(default=dict)),
                ("attempts", models.PositiveIntegerField(default=0)),
                ("published_at", models.DateTimeField(null=True, blank=True)),
                ("created_at", models.DateTimeField(default=django.utils.timezone.now, db_index=True)),
            ],
        ),
    ]
