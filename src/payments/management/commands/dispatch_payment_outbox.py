"""Dispatch the Django transactional outbox through Broka's own leasing/retry engine."""
from __future__ import annotations

import asyncio
from django.core.management.base import BaseCommand

from broka.integrations.django import get_broker
from broka.integrations.django.outbox import build_outbox_dispatcher


class Command(BaseCommand):
    help = "Publish persistent payment commands/events using Broka's Django outbox."

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true")

    def handle(self, *args, **options):
        async def run():
            async with get_broker() as broker:
                dispatcher = build_outbox_dispatcher(broker)
                if options["once"]:
                    return await dispatcher.dispatch_once()
                await dispatcher.run(asyncio.Event())
        try:
            count = asyncio.run(run())
            if options["once"]:
                self.stdout.write(f"Leased {count} outbox message(s)")
        except KeyboardInterrupt:
            self.stdout.write("Outbox dispatcher stopped.")
