"""Contract tests for Broka outbox transport, Dispio routing and idempotent provider commands."""
from __future__ import annotations

import asyncio
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.db import transaction

from broka import Broker
from broka.integrations.django.outbox import DjangoModelOutboxStore, build_outbox_dispatcher
from dispio import Dispatcher
from dispio.integrations import BrokaDispatchBridge

from payments.domain import PaymentProcessor
from payments.events import queue_message
from payments.models import PaymentIntent, PaymentOutboxRecord, PaymentStatus
from payments.schemas import PaymentChargeCommand


@pytest.mark.django_db(transaction=True)
def test_broka_outbox_dispatches_to_subscriber():
    with transaction.atomic():
        queue_message(
            "payments.charge.requested", {"reference": "EVENT001", "intent_id": "e-1"},
            reference="EVENT001",
        )
    received = []

    async def run():
        event = asyncio.Event()

        async def handle(delivery):
            received.append(delivery.message)
            event.set()

        async with Broker.from_config({"engine": "memory"}) as broker:
            await broker.subscribe("payments.charge.requested", handle)
            dispatcher = build_outbox_dispatcher(
                broker, store=DjangoModelOutboxStore(PaymentOutboxRecord)
            )
            count = await dispatcher.dispatch_once()
            await asyncio.wait_for(event.wait(), timeout=5)
            return count

    assert asyncio.run(run()) == 1
    assert received[0]["reference"] == "EVENT001"
    assert PaymentOutboxRecord.objects.get(destination="payments.charge.requested").status == "published"


@pytest.mark.asyncio
async def test_dispio_bridge_routes_broka_style_delivery():
    called = []
    bridge = BrokaDispatchBridge(Dispatcher(name="payment-tests"))

    @bridge.on("payments.charge.requested")
    async def handle(delivery):
        called.append(delivery.message["intent_id"])

    delivery = SimpleNamespace(route="payments.charge.requested", message={"intent_id": "abc"})
    await bridge.dispatch_delivery(delivery)
    assert called == ["abc"]


@pytest.mark.django_db
def test_charge_command_is_idempotent_and_success_is_verified():
    user = get_user_model().objects.create_user(username="billing")
    intent = PaymentIntent.objects.create(
        owner=user, reference="COMMAND001", amount=Decimal("12.50"), currency="NGN",
        provider_customer_id="customer1", provider_payment_method_id="method1",
    )
    calls = []
    response = SimpleNamespace(
        data={"id": "charge123", "status": "succeeded"},
        raw={"data": {"id": "charge123", "status": "succeeded"}},
    )
    result = SimpleNamespace(
        status="succeeded", is_trusted_success=True, is_successful=True, is_failed=False,
        mismatch_reasons=[], response=response,
    )

    def charge(**kwargs):
        calls.append(kwargs)
        return response

    provider = SimpleNamespace(
        charges=SimpleNamespace(create=charge),
        transactions=SimpleNamespace(verify=lambda *args, **kwargs: result),
    )
    command = PaymentChargeCommand(
        intent_id=intent.id, reference=intent.reference, amount=intent.amount,
        currency=intent.currency, customer_id="customer1", payment_method_id="method1",
    )
    with patch("payments.domain.get_flutterwave_client", return_value=provider):
        PaymentProcessor().process_charge(command)
        PaymentProcessor().process_charge(command)

    intent.refresh_from_db()
    assert intent.status == PaymentStatus.SUCCEEDED
    assert len(calls) == 1
    assert calls[0]["amount"] == Decimal("12.50")
    assert PaymentOutboxRecord.objects.filter(destination="payment.completed").count() == 1


@pytest.mark.django_db
def test_provider_success_with_amount_mismatch_is_not_trusted():
    user = get_user_model().objects.create_user(username="mismatch")
    intent = PaymentIntent.objects.create(
        owner=user, reference="COMMAND002", amount=Decimal("99.00"), currency="NGN",
        provider_charge_id="chargeM", status=PaymentStatus.PROCESSING,
    )
    result = SimpleNamespace(
        status="succeeded", is_trusted_success=False, is_successful=True,
        mismatch_reasons=["amount_mismatch"], is_failed=False,
        response=SimpleNamespace(raw={"data": {"id": "chargeM"}}),
    )
    provider = SimpleNamespace(transactions=SimpleNamespace(verify=lambda *a, **kw: result))
    with patch("payments.domain.get_flutterwave_client", return_value=provider):
        PaymentProcessor().verify_intent(intent_id=str(intent.id))
    intent.refresh_from_db()
    assert intent.status == PaymentStatus.VERIFICATION_FAILED
    assert not PaymentOutboxRecord.objects.filter(destination="payment.completed").exists()
