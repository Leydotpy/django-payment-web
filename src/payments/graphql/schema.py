"""GraphQL payments access is explicitly scoped to the authenticated owner."""
from __future__ import annotations

import graphene
from graphene.types.generic import GenericScalar
from graphene_django import DjangoObjectType
from graphql import GraphQLError

from ..models import PaymentIntent
from ..usecases import PaymentConflict, create_payment_charge


def require_user(info):
    user = info.context.user
    if not user.is_authenticated:
        raise GraphQLError("Authentication is required.")
    return user


class PaymentIntentType(DjangoObjectType):
    class Meta:
        model = PaymentIntent
        fields = (
            "id", "reference", "provider", "amount", "currency", "status",
            "metadata", "redirect_url", "provider_charge_id", "provider_status",
            "verified_at", "next_action", "failure_code", "failure_message",
            "created_at", "updated_at",
        )


class RequestCharge(graphene.Mutation):
    class Arguments:
        reference = graphene.String(required=True)
        amount = graphene.Decimal(required=True)
        currency = graphene.String(required=True)
        customer_id = graphene.String(required=True)
        payment_method_id = graphene.String(required=True)
        metadata = GenericScalar()
        redirect_url = graphene.String()

    payment_intent = graphene.Field(PaymentIntentType)

    @classmethod
    def mutate(cls, root, info, **kwargs):
        user = require_user(info)
        try:
            intent = create_payment_charge(
                owner=user, reference=kwargs["reference"], amount=kwargs["amount"],
                currency=kwargs["currency"], customer_id=kwargs["customer_id"],
                payment_method_id=kwargs["payment_method_id"],
                metadata=kwargs.get("metadata"), redirect_url=kwargs.get("redirect_url") or "",
            )
        except PaymentConflict as exc:
            raise GraphQLError(str(exc)) from exc
        return RequestCharge(payment_intent=intent)


class Query(graphene.ObjectType):
    payment_intent = graphene.Field(PaymentIntentType, id=graphene.UUID(required=True))
    payment_intents = graphene.List(PaymentIntentType, status=graphene.String())

    def resolve_payment_intent(root, info, id):
        user = require_user(info)
        qs = PaymentIntent.objects.all() if user.is_staff else PaymentIntent.objects.filter(owner=user)
        return qs.filter(id=id).first()

    def resolve_payment_intents(root, info, status=None):
        user = require_user(info)
        qs = PaymentIntent.objects.all() if user.is_staff else PaymentIntent.objects.filter(owner=user)
        if status:
            qs = qs.filter(status=status)
        return qs.order_by("-created_at")[:100]


class Mutation(graphene.ObjectType):
    request_charge = RequestCharge.Field()


schema = graphene.Schema(query=Query, mutation=Mutation)
