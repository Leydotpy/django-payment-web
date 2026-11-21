from __future__ import annotations

from rest_framework.routers import DefaultRouter

from django.urls import path
from .views import FlutterwaveWebhookView, PaymentIntentViewSet

router = DefaultRouter()
router.register("payment-intents", PaymentIntentViewSet, basename="payment-intent")

urlpatterns = [path("webhooks/flutterwave/", FlutterwaveWebhookView.as_view(), name="flutterwave-webhook"), *router.urls]
