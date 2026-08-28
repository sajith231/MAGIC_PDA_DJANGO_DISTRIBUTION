from django.urls import path
from . import views

urlpatterns = [
    path("e-gate-billing", views.e_gate_billing, name="e_gate_billing"),
]