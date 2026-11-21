from __future__ import annotations

import graphene
from graphene.types.generic import GenericScalar
from django.db import transaction
from graphene_django import DjangoObjectType

from ..adapters.broker import get_command_bus
from ..models import PaymentIntent
from ..schemas import CardChargeCommand
from ..settings import get_payment_settings
from ..tasks import process_card_charge


class PaymentIntentType(DjangoObjectType):
    class Meta:
        model = PaymentIntent
        fields = (
            "id",
            "reference",
            "provider",
            "amount",
            "currency",
            "status",
            "metadata",
            "redirect_url",
            "provider_charge_id",
            "next_action",
            "failure_code",
            "failure_message",
            "created_at",
            "updated_at",
        )


class CustomerInput(graphene.InputObjectType):
    email = graphene.String(required=True)
    name = GenericScalar()
    phone = GenericScalar()
    address = GenericScalar()


class EncryptedCardInput(graphene.InputObjectType):
    nonce = graphene.String(required=True)
    encrypted_card_number = graphene.String(required=True)
    encrypted_expiry_month = graphene.String(required=True)
    encrypted_expiry_year = graphene.String(required=True)
    encrypted_cvv = graphene.String(required=True)


class RequestCardCharge(graphene.Mutation):
    class Arguments:
        reference = graphene.String(required=True)
        amount = graphene.Decimal(required=True)
        currency = graphene.String(required=True)
        customer = CustomerInput(required=True)
        encrypted_card = EncryptedCardInput(required=True)
        redirect_url = graphene.String()
        metadata = GenericScalar()
        scenario_key = graphene.String()

    payment_intent = graphene.Field(PaymentIntentType)

    @classmethod
    def mutate(cls, root, info, **kwargs):
        customer = dict(kwargs["customer"])
        encrypted_card = dict(kwargs["encrypted_card"])
        metadata = kwargs.get("metadata") or {}
        with transaction.atomic():
            intent, created = PaymentIntent.objects.get_or_create(
                reference=kwargs["reference"],
                defaults={
                    "amount": kwargs["amount"],
                    "currency": kwargs["currency"].upper(),
                    "customer": customer,
                    "metadata": metadata,
                    "redirect_url": kwargs.get("redirect_url") or "",
                },
            )
            if created:
                intent.mark_queued()

        command = CardChargeCommand(
            intent_id=intent.id,
            reference=intent.reference,
            amount=intent.amount,
            currency=intent.currency,
            customer=customer,
            encrypted_card=encrypted_card,
            redirect_url=kwargs.get("redirect_url"),
            metadata=metadata,
            scenario_key=kwargs.get("scenario_key"),
        )
        payload = command.model_dump(mode="json")
        settings = get_payment_settings()
        if settings.broker_backend == "celery":
            process_card_charge.delay(payload)
        else:
            get_command_bus().publish(key=intent.reference, payload=payload)
        return RequestCardCharge(payment_intent=intent)


class Query(graphene.ObjectType):
    payment_intent = graphene.Field(PaymentIntentType, id=graphene.UUID(required=True))
    payment_intents = graphene.List(PaymentIntentType, status=graphene.String())

    def resolve_payment_intent(root, info, id):
        return PaymentIntent.objects.get(id=id)

    def resolve_payment_intents(root, info, status=None):
        queryset = PaymentIntent.objects.all().order_by("-created_at")
        if status:
            queryset = queryset.filter(status=status)
        return queryset[:100]


class Mutation(graphene.ObjectType):
    request_card_charge = RequestCardCharge.Field()


schema = graphene.Schema(query=Query, mutation=Mutation)
