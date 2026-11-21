from __future__ import annotations

from rest_framework import serializers

from ..models import PaymentIntent


class EncryptedCardSerializer(serializers.Serializer):
    nonce = serializers.CharField(min_length=12, max_length=12)
    encrypted_card_number = serializers.CharField()
    encrypted_expiry_month = serializers.CharField()
    encrypted_expiry_year = serializers.CharField()
    encrypted_cvv = serializers.CharField()


class CustomerSerializer(serializers.Serializer):
    email = serializers.EmailField()
    name = serializers.DictField(required=False)
    phone = serializers.DictField(required=False)
    address = serializers.DictField(required=False)


class CreateCardChargeSerializer(serializers.Serializer):
    reference = serializers.CharField(max_length=128)
    amount = serializers.DecimalField(max_digits=14, decimal_places=2)
    currency = serializers.CharField(min_length=3, max_length=3)
    customer = CustomerSerializer()
    encrypted_card = EncryptedCardSerializer(write_only=True)
    redirect_url = serializers.URLField(required=False, allow_blank=True)
    metadata = serializers.DictField(required=False)
    scenario_key = serializers.CharField(required=False, allow_blank=True)

    def validate_currency(self, value: str) -> str:
        return value.upper()


class PaymentIntentSerializer(serializers.ModelSerializer):
    class Meta:
        model = PaymentIntent
        fields = [
            "id",
            "reference",
            "provider",
            "amount",
            "currency",
            "status",
            "customer",
            "metadata",
            "redirect_url",
            "provider_charge_id",
            "next_action",
            "failure_code",
            "failure_message",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields
