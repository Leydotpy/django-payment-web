# Django payment service with Broka and Dispio

This branch replaces bespoke RabbitMQ/Kafka event publishers with **Broka's durable Django outbox**
and **Dispio's application handler dispatch**. The checkout surface intentionally no longer
accepts encrypted card numbers or CVVs: the old `POST /api/payment-intents/card-charge/`
returns HTTP 410.

## Components

- `flutterwave_sdk` (Python import: `flutterwave_sdk`): provider operations
- `broka` (GitHub repo `Leydotpy/pyev`): durable event transport and outbox
- `dispio` (GitHub repo `Leydotpy/pyev-dispatch`): application message dispatch
- Django: payment states, authorised payment methods, tenant access control and verification

**No payment is marked successful until its provider charge, reference, amount and currency
are independently verified.**

## Setup

Install Django, Django REST Framework, Graphene-Django, Celery, psycopg, pydantic-settings,
then install the three sibling packages. The Flutterwave SDK must be installed from the
`fix/sdk-security-and-packaging` branch (until its PR is merged) because the old root
module layout is not an installable Python package.

Set `POSTGRES_*`, `DJANGO_SECRET_KEY`, `PAYMENTS_FLUTTERWAVE_CLIENT_ID`,
`PAYMENTS_FLUTTERWAVE_CLIENT_SECRET`, `PAYMENTS_FLUTTERWAVE_WEBHOOK_SECRET`,
`PAYMENTS_FLUTTERWAVE_ENVIRONMENT=sandbox`, and `PAYMENTS_RABBITMQ_URL`.
The Broka engine defaults to RabbitMQ; do not use memory/local engines to connect
separate processes.

```sh
python src/manage.py migrate
python src/manage.py pyev_outbox list    # inspect queued messages
python src/manage.py dispatch_payment_outbox
python src/manage.py consume_payment_events
# Schedule periodic reconciliation independently:
python src/manage.py reconcile_payments
```

Each worker runs in its own operating-system process. Run both the outbox dispatcher and
consumer continuously under a process supervisor. Run reconciliation periodically. Keep
separate broker/queue namespaces for sandbox and production.

## Tokenised charge initiation

1. Authenticate to the API with a Django session or DRF TokenAuthentication.
2. Obtain a customer and payment-method ID through a **provider-approved hosted/tokenised
   consent flow**, not by posting raw card details to this service.
3. An authorised integration or staff user must create an `AuthorizedPaymentMethod` binding
   the provider customer/method IDs to the API user, with recorded consent reference and
   `verified_at`; activate it only after checking the provider's record. No public grant
   endpoint is exposed.
4. POST `/api/payment-intents/charge/`:

```json
{
  "reference": "INVOICE20260001",
  "amount": "45000.00",
  "currency": "NGN",
  "customer_id": "provider-customer-id",
  "payment_method_id": "provider-payment-method-id"
}
```

The API writes a `PaymentIntent` and a Broka outbox command atomically, then returns HTTP
202. The broker delivers the command and Dispio routes it to `PaymentProcessor`. The
provider receives a stable per-charge idempotency key. A successful provider response
is still independently verified, and only then is `payment.completed` emitted. Signed
webhooks are recorded as minimal inbox data and processed through the same verification
engine. Payment status may remain `processing` when the remote operation outcome is
uncertain; reconciliation searches provider charges by reference before making another
attempt.

## Release and migration warnings

- The removed manual Kafka/RabbitMQ consumers use a different wire format. Drain old
  queues before deploying the new consumers; do not run both command consumers.
- Existing `OutboxEvent` records are legacy data. Export/replay outstanding records and
  reconcile outstanding payments before removing that table in a later migration.
- Existing ownerless payment intents are accessible only to staff. Assign a verified
  owner before exposing them to merchants.
- Provisioning payment-method consent is currently an internal/manual integration step,
  not a fully implemented hosted-card onboarding experience.
- The outbox is **at least once**, not exactly once; provider idempotency and state
  locking are still essential.
- Payment attempts and provider responses require a retention/redaction policy.
- Sandbox integration, security/PCI review, provider contract testing, and operational
  drills remain mandatory before production use.

Broka's optional Django application is enabled to expose its built-in system checks and
`pyev_outbox`, `pyev_health`, and dead-letter inspection commands. Until the associated
Broka namespace fix is released, install its `fix/django-app-module-namespace` branch.
