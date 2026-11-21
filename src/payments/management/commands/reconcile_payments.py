"""Recheck unresolved provider outcomes; safe to schedule periodically."""
from __future__ import annotations

from django.core.management.base import BaseCommand
from payments.domain import PaymentProcessor
from payments.models import PaymentIntent, PaymentStatus


class Command(BaseCommand):
    help = "Reconcile indeterminate and pending payments against Flutterwave."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=100)

    def handle(self, *args, **options):
        ids = list(PaymentIntent.objects.filter(status=PaymentStatus.PROCESSING)
                   .order_by("updated_at").values_list("id", flat=True)[:options["limit"]])
        success = 0
        for intent_id in ids:
            try:
                PaymentProcessor().reconcile_intent(intent_id=str(intent_id))
                success += 1
            except Exception as exc:
                self.stderr.write(f"Payment {intent_id}: {type(exc).__name__}")
        self.stdout.write(f"Examined {success}/{len(ids)} processing payment(s)")
