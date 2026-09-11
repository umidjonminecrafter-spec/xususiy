from django.test import TestCase
from django.contrib.auth import get_user_model
from django.core.cache import cache
from rest_framework.test import APIClient
from rest_framework import status
from unittest.mock import patch

from organizations.models import (
    Organization, Branch, Tariff, Subscription,
    ExamSetting, ReceiptSetting, BackupSetting,
    TelegramNotificationSetting, LessonNotificationTemplate
)
from academics.models import Student, Group, Room

User = get_user_model()


class OrganizationAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.org = Organization.objects.create(name="Test Edu", phone="+998901112233")
        self.branch = Branch.objects.create(name="Main Branch", organization=self.org)
        self.user = User.objects.create_user(
            username="+998901112233",
            password="testpassword123",
            first_name="Admin",
            last_name="User",
            organization=self.org,
            branch=self.branch,
            role="owner"
        )
        self.client.force_authenticate(user=self.user)

    def test_organization_list_and_settings(self):
        # List orgs
        res = self.client.get('/api/v1/organizations/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        # Settings GET
        res = self.client.get('/api/v1/organizations/settings/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['name'], "Test Edu")

        # Settings PATCH
        res = self.client.patch('/api/v1/organizations/settings/', {'name': 'Updated Edu'})
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['name'], 'Updated Edu')

    def test_exam_settings(self):
        res = self.client.get('/api/v1/organizations/exam-settings/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        res = self.client.put('/api/v1/organizations/exam-settings/', {'include_active_students': False})
        self.assertEqual(res.status_code, status.HTTP_200_OK)

    def test_receipt_settings(self):
        res = self.client.get('/api/v1/organizations/receipt-settings/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        res = self.client.put('/api/v1/organizations/receipt-settings/', {'header_text': 'Smart Receipt'})
        self.assertEqual(res.status_code, status.HTTP_200_OK)

    def test_backup_settings(self):
        res = self.client.get('/api/v1/organizations/backup-settings/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        res = self.client.put('/api/v1/organizations/backup-settings/', {'is_auto_backup': True})
        self.assertEqual(res.status_code, status.HTTP_200_OK)

    def test_telegram_settings_and_templates(self):
        res = self.client.get('/api/v1/organizations/telegram-settings/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        # Lesson templates
        res = self.client.post('/api/v1/organizations/lesson-templates/', {
            'name': 'Eslatma',
            'template_type': 'before',
            'delay_minutes': 10,
            'message_text': 'Ertaga dars bor'
        })
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        template_id = res.data['id']

        res = self.client.get('/api/v1/organizations/lesson-templates/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res.data), 1)

        res = self.client.put(f'/api/v1/organizations/lesson-templates/{template_id}/', {
            'name': 'Yangilangan Eslatma',
            'template_type': 'during',
            'delay_minutes': 5,
            'message_text': 'Dars soat 10 da'
        })
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        res = self.client.delete(f'/api/v1/organizations/lesson-templates/{template_id}/')
        self.assertEqual(res.status_code, status.HTTP_204_NO_CONTENT)

    def test_branches(self):
        res = self.client.get('/api/v1/organizations/branches/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        # Set location action
        res = self.client.post(f'/api/v1/organizations/branches/{self.branch.id}/set-location/', {
            'latitude': 41.311081,
            'longitude': 69.240562
        })
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        # Standalone update location view
        res = self.client.post(f'/api/v1/organizations/branches/{self.branch.id}/set-location/', {
            'latitude': 41.320000,
            'longitude': 69.250000
        })
        self.assertEqual(res.status_code, status.HTTP_200_OK)

    def test_tariffs_and_subscriptions(self):
        tariff = Tariff.objects.create(name="Standard", price=100000)
        res = self.client.get('/api/v1/organizations/tariffs/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        res = self.client.get('/api/v1/organizations/subscriptions/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)

    def test_login_view(self):
        anon_client = APIClient()
        res = anon_client.post('/api/v1/organizations/login/', {
            'username': '+998901112233',
            'password': 'testpassword123'
        })
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn('access', res.data)

    @patch('organizations.views.send_sms', return_value=(True, 'OK'))
    def test_sms_verification_flow(self, mock_send_sms):
        anon_client = APIClient()
        phone = "+998901234567"
        
        # Send SMS code
        res = anon_client.post('/api/v1/organizations/sms/send/', {'phone_number': phone})
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        cached_code = cache.get(f"sms_code_{phone}")
        self.assertIsNotNone(cached_code)

        # Verify SMS code
        res = anon_client.post('/api/v1/organizations/sms/verify/', {
            'phone_number': phone,
            'code': str(cached_code)
        })
        self.assertEqual(res.status_code, status.HTTP_200_OK)

    def test_global_search(self):
        Student.objects.create(
            organization=self.org,
            branch=self.branch,
            first_name="Ali",
            last_name="Valiyev",
            phone="+998909998877"
        )
        res = self.client.get('/api/v1/organizations/global-search/?q=Ali')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res.data), 1)
        self.assertEqual(res.data[0]['type'], 'student')
