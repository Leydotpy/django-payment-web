import base64
import hashlib
import hmac
import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient

from payments.domain import PaymentProcessor
from payments.models import AuthorizedPaymentMethod, PaymentIntent, PaymentOutboxRecord, PaymentStatus
from payments.settings import get_payment_settings


@pytest.fixture
def owner(db):
    return get_user_model().objects.create_user(username="merchant1", password="p-test")


@pytest.fixture
def method(owner):
    return AuthorizedPaymentMethod.objects.create(
        owner=owner, provider_customer_id="cus_1", provider_payment_method_id="pm_1",
        consent_reference="provider-consent-1", verified_at=timezone.now(), is_active=True,
    )


def payment_data(reference="PAYMENT001"):
    return {
        "reference": reference, "amount": "120.50", "currency": "NGN",
        "customer_id": "cus_1", "payment_method_id": "pm_1",
    }


@pytest.mark.django_db
def test_charge_creates_only_one_durable_broka_command(owner, method):
    client = APIClient()
    client.force_authenticate(user=owner)
    first = client.post("/api/payment-intents/charge/", payment_data(), format="json")
    repeated = client.post("/api/payment-intents/charge/", payment_data(), format="json")
    assert first.status_code == 202, first.data
    assert repeated.status_code == 202, repeated.data
    assert first.data["id"] == repeated.data["id"]
    assert PaymentOutboxRecord.objects.count() == 1
    assert PaymentIntent.objects.get(reference="PAYMENT001").owner == owner


@pytest.mark.django_db
def test_unapproved_provider_method_cannot_be_charged(owner):
    client = APIClient()
    client.force_authenticate(user=owner)
    response = client.post("/api/payment-intents/charge/", payment_data("PAYMENT002"), format="json")
    assert response.status_code == 409
    assert PaymentIntent.objects.count() == 0


@pytest.mark.django_db
def test_tenant_cannot_read_another_merchant_payment(owner, method):
    client = APIClient()
    client.force_authenticate(user=owner)
    response = client.post("/api/payment-intents/charge/", payment_data("PAYMENT003"), format="json")
    assert response.status_code == 202
    other = get_user_model().objects.create_user(username="merchant2", password="p-test")
    client.force_authenticate(user=other)
    assert client.get(f'/api/payment-intents/{response.data["id"]}/').status_code == 404
    assert client.get("/api/payment-intents/").data == []


@pytest.mark.django_db
def test_verified_success_is_emitted_once(owner):
    intent = PaymentIntent.objects.create(
        reference="PAYMENT004", owner=owner, amount="100.00", currency="NGN",
        provider_charge_id="ch_1", status=PaymentStatus.PROCESSING,
    )
    verification = SimpleNamespace(
        status="succeeded", is_trusted_success=True, is_successful=True, is_failed=False,
        mismatch_reasons=[], response=SimpleNamespace(raw={"data": {"id": "ch_1"}}),
    )
    api = SimpleNamespace(transactions=SimpleNamespace(verify=lambda *a, **kw: verification))
    with patch("payments.domain.get_flutterwave_client", return_value=api):
        PaymentProcessor().verify_intent(intent_id=str(intent.id))
        PaymentProcessor().verify_intent(intent_id=str(intent.id))
    intent.refresh_from_db()
    assert intent.status == PaymentStatus.SUCCEEDED
    assert intent.verified_at is not None
    assert PaymentOutboxRecord.objects.count() == 1


@pytest.mark.django_db
def test_signed_webhook_does_not_directly_mark_success(owner, monkeypatch):
    monkeypatch.setenv("PAYMENTS_FLUTTERWAVE_CLIENT_ID", "test")
    monkeypatch.setenv("PAYMENTS_FLUTTERWAVE_CLIENT_SECRET", "test")
    monkeypatch.setenv("PAYMENTS_FLUTTERWAVE_WEBHOOK_SECRET", "webhook-test")
    get_payment_settings.cache_clear()
    intent = PaymentIntent.objects.create(
        owner=owner, reference="PAYMENT005", amount="10.00", currency="NGN",
    )
    payload = json.dumps({
        "webhook_id": "ev_1", "type": "charge.completed",
        "data": {"id": "ch_1", "reference": intent.reference, "status": "succeeded"},
    }).encode()
    signature = base64.b64encode(hmac.new(b"webhook-test", payload, hashlib.sha256).digest()).decode()
    client = APIClient()
    result = client.post(
        "/api/webhooks/flutterwave/", data=payload,
        content_type="application/json", HTTP_FLUTTERWAVE_SIGNATURE=signature,
    )
    assert result.status_code == 200, result.data
    intent.refresh_from_db()
    assert intent.status == PaymentStatus.CREATED
    assert PaymentOutboxRecord.objects.count() == 1
    get_payment_settings.cache_clear()
