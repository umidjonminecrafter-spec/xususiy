import datetime
from decimal import Decimal
from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase
from rest_framework import status

from organizations.models import Organization, Tariff, Subscription
from billing.models import BillingHistory, BalanceTopUp, SubscriptionRequest

User = get_user_model()


class BillingAPITests(APITestCase):
    def setUp(self):
        self.org = Organization.objects.create(
            name="Billing Test Org",
            phone="+998901234567"
        )
        self.user = User.objects.create_user(
            username="billing_admin",
            password="testpassword123",
            organization=self.org,
            role="director",
        )
        self.tariff = Tariff.objects.create(
            name="Standard Plan",
            price=Decimal("500000.00"),
            months=1,
            student_limit=100,
            discount_enabled=True,
            discount_percent=Decimal("10.00"),
        )
        self.subscription = Subscription.objects.create(
            organization=self.org,
            tariff=self.tariff,
            start_date=datetime.date.today(),
            end_date=datetime.date.today() + datetime.timedelta(days=30),
            is_active=True,
            balance=Decimal("1000000.00"),
        )
        self.client.force_authenticate(user=self.user)

    def test_billing_plans_public(self):
        self.client.logout()
        res = self.client.get('/api/v1/billing/plans/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertTrue(len(res.data) >= 1)

    def test_billing_current_view(self):
        res = self.client.get('/api/v1/billing/current/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(Decimal(str(res.data['balance'])), Decimal("1000000.00"))
        self.assertTrue(res.data['is_active'])
        self.assertEqual(res.data['tariff']['id'], self.tariff.id)

    def test_balance_topup(self):
        res = self.client.post('/api/v1/billing/topup/', {
            "amount": "250000.00",
            "comment": "Payme to'lovi"
        })
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(Decimal(str(res.data['balance'])), Decimal("1250000.00"))
        self.assertTrue(BalanceTopUp.objects.filter(organization=self.org, amount=Decimal("250000.00")).exists())

    def test_subscribe_preview_and_confirm(self):
        # Preview
        preview_res = self.client.post('/api/v1/billing/subscribe/', {
            "tariff_id": self.tariff.id
        })
        self.assertEqual(preview_res.status_code, status.HTTP_200_OK)
        self.assertTrue(preview_res.data['enough_balance'])

        # Confirm
        confirm_res = self.client.post('/api/v1/billing/subscribe/confirm/', {
            "tariff_id": self.tariff.id
        })
        self.assertEqual(confirm_res.status_code, status.HTTP_200_OK)
        self.assertEqual(Decimal(str(confirm_res.data['deducted'])), self.tariff.final_price)
        self.assertTrue(SubscriptionRequest.objects.filter(organization=self.org, status='approved').exists())

    def test_billing_history(self):
        BillingHistory.objects.create(
            organization=self.org,
            amount=Decimal("450000.00"),
            plan_name="Standard Plan",
            months=1
        )
        res = self.client.get('/api/v1/billing/history/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res.data), 1)

    def test_billing_pay_request_and_list(self):
        res = self.client.post('/api/v1/billing/pay/', {
            "tariff_id": self.tariff.id,
            "months": 1,
            "amount": "450000.00"
        })
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res.data['status'], 'success')

        list_res = self.client.get('/api/v1/billing/requests/')
        self.assertEqual(list_res.status_code, status.HTTP_200_OK)
        self.assertTrue(len(list_res.data) >= 1)
