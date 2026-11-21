from __future__ import annotations

from rest_framework import serializers
from ..models import PaymentIntent


class CreateChargeSerializer(serializers.Serializer):
    reference = serializers.CharField(max_length=128)
    amount = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=0.01)
    currency = serializers.RegexField(r"^[A-Za-z]{3}$")
    customer_id = serializers.CharField(max_length=128)
    payment_method_id = serializers.CharField(max_length=128)
    metadata = serializers.DictField(required=False)
    redirect_url = serializers.URLField(required=False, allow_blank=True)

    def validate_currency(self, value: str) -> str:
        return value.upper()


class PaymentIntentSerializer(serializers.ModelSerializer):
    class Meta:
        model = PaymentIntent
        fields = [
            "id", "reference", "provider", "amount", "currency", "status",
            "customer", "metadata", "redirect_url", "provider_charge_id",
            "provider_status", "verified_at", "next_action", "failure_code",
            "failure_message", "created_at", "updated_at",
        ]
        read_only_fields = fields
