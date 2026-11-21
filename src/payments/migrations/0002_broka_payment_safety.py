from __future__ import annotations

import uuid
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("payments", "0001_initial"), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]

    operations = [
        migrations.AddField(model_name="paymentintent", name="owner", field=models.ForeignKey(to=settings.AUTH_USER_MODEL, on_delete=django.db.models.deletion.PROTECT, null=True, blank=True, related_name="payment_intents")),
        migrations.AddField(model_name="paymentintent", name="provider_status", field=models.CharField(max_length=64, blank=True, default="")),
        migrations.AddField(model_name="paymentintent", name="verification_payload", field=models.JSONField(blank=True, default=dict)),
        migrations.AddField(model_name="paymentintent", name="verified_at", field=models.DateTimeField(null=True, blank=True)),
        migrations.AlterField(model_name="paymentintent", name="status", field=models.CharField(max_length=32, choices=[("created", "Created"), ("queued", "Queued"), ("processing", "Processing"), ("requires_action", "Requires customer action"), ("succeeded", "Succeeded"), ("failed", "Failed"), ("cancelled", "Cancelled"), ("verification_failed", "Verification failed")], default="created")),
        migrations.CreateModel(name="PaymentOutboxRecord", fields=[
            ("id", models.UUIDField(primary_key=True, editable=False, serialize=False)),
            ("payload", models.BinaryField()),
            ("destination", models.CharField(max_length=512, db_index=True)),
            ("status", models.CharField(max_length=32, db_index=True, default="pending", choices=[("pending", "Pending"), ("leased", "Leased"), ("published", "Published"), ("failed", "Failed"), ("dead_lettered", "Dead lettered")])),
            ("created_at", models.DateTimeField(db_index=True)),
            ("available_at", models.DateTimeField(db_index=True)),
            ("attempts", models.PositiveIntegerField(default=0)),
            ("last_error", models.TextField(null=True, blank=True)),
            ("lease_id", models.UUIDField(null=True, blank=True, db_index=True)),
            ("leased_until", models.DateTimeField(null=True, blank=True, db_index=True)),
            ("published_at", models.DateTimeField(null=True, blank=True)),
            ("metadata", models.JSONField(blank=True, default=dict)),
        ], options={"db_table": "payments_broka_outbox", "ordering": ("available_at", "created_at", "id")}),
    ]
