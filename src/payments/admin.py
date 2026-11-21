from __future__ import annotations

from django.contrib import admin

from .models import OutboxEvent, PaymentAttempt, PaymentEvent, PaymentIntent


@admin.register(PaymentIntent)
class PaymentIntentAdmin(admin.ModelAdmin):
    list_display = ("reference", "amount", "currency", "status", "provider_charge_id", "created_at")
    list_filter = ("status", "provider", "currency")
    search_fields = ("reference", "provider_charge_id", "provider_customer_id")
    readonly_fields = ("id", "created_at", "updated_at")


@admin.register(PaymentAttempt)
class PaymentAttemptAdmin(admin.ModelAdmin):
    list_display = ("intent", "status", "created_at", "completed_at")
    search_fields = ("intent__reference",)


@admin.register(PaymentEvent)
class PaymentEventAdmin(admin.ModelAdmin):
    list_display = ("provider_event_id", "event_type", "processed_at", "created_at")
    search_fields = ("provider_event_id", "event_type")


@admin.register(OutboxEvent)
class OutboxEventAdmin(admin.ModelAdmin):
    list_display = ("topic", "key", "attempts", "published_at", "created_at")
    list_filter = ("topic", "published_at")
