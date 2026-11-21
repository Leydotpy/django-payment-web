from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from payments.adapters.publisher import MessagePublisher
from payments.models import OutboxEvent


class Command(BaseCommand):
    help = "Publish pending payment outbox events. Run from cron/Celery beat in production."

    def handle(self, *args, **options):
        publisher = MessagePublisher()
        published = 0
        for event in OutboxEvent.objects.filter(published_at__isnull=True).order_by("created_at")[:100]:
            with transaction.atomic():
                locked = OutboxEvent.objects.select_for_update(skip_locked=True).get(id=event.id)
                if locked.published_at:
                    continue
                publisher.publish(topic=locked.topic, key=locked.key, payload=locked.payload)
                locked.published_at = timezone.now()
                locked.attempts += 1
                locked.save(update_fields=["published_at", "attempts"])
                published += 1
        self.stdout.write(self.style.SUCCESS(f"Published {published} outbox event(s)."))
