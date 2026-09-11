from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase
from rest_framework import status
from organizations.models import Organization
from audit.models import AuditLog

User = get_user_model()


class AuditLogTests(APITestCase):
    def setUp(self):
        self.organization = Organization.objects.create(name="Audit Test Org")
        self.user = User.objects.create_user(
            username="+998901234567",
            phone="+998901234567",
            password="testpassword",
            organization=self.organization,
            role="owner"
        )
        self.client.force_authenticate(user=self.user)
        self.audit_log = AuditLog.objects.create(
            organization=self.organization,
            user=self.user,
            action="STUDENT_CREATED",
            entity_type="Student",
            entity_id=1
        )

    def test_list_audit_logs(self):
        response = self.client.get('/api/v1/audit/audit-logs/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data.get('results', response.data)
        self.assertTrue(len(results) >= 1)

    def test_retrieve_audit_log(self):
        response = self.client.get(f'/api/v1/audit/audit-logs/{self.audit_log.id}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['action'], "STUDENT_CREATED")
