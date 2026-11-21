from __future__ import annotations

import uuid
import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("payments", "0002_broka_payment_safety"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="AuthorizedPaymentMethod",
            fields=[
                ("id", models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
                ("provider_customer_id", models.CharField(max_length=128)),
                ("provider_payment_method_id", models.CharField(max_length=128, unique=True)),
                ("consent_reference", models.CharField(max_length=128)),
                ("verified_at", models.DateTimeField(null=True, blank=True)),
                ("is_active", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("owner", models.ForeignKey(to=settings.AUTH_USER_MODEL, on_delete=django.db.models.deletion.PROTECT, related_name="authorized_payment_methods")),
            ],
            options={"indexes": [models.Index(fields=["owner", "is_active"], name="payments_ap_owner_active_idx")]},
        ),
    ]
