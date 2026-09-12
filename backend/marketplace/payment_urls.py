from django.urls import path
from . import payout_views

urlpatterns = [
    path("operator/payout-recipients/verify/", payout_views.verify_recipient, name="payout-recipient-verify"),
    path("operator/withdrawals/<int:pk>/", payout_views.withdrawal_operation, name="withdrawal-operator"),
]
