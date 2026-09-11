from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase
from rest_framework import status

from organizations.models import Organization
from crm.models import Pipeline, Section, Source, LostReason, Lead, LeadForm

User = get_user_model()


class CRMAPITests(APITestCase):
    def setUp(self):
        self.org = Organization.objects.create(
            name="CRM Test Org",
            phone="+998901234567"
        )
        self.user = User.objects.create_user(
            username="crm_admin",
            password="testpassword123",
            organization=self.org,
            role="admin",
        )
        self.pipeline = Pipeline.objects.create(
            organization=self.org,
            name="Asosiy Voronka",
            order=1
        )
        self.section = Section.objects.create(
            organization=self.org,
            pipeline=self.pipeline,
            name="Yangi lidlar"
        )
        self.source = Source.objects.create(
            organization=self.org,
            name="Instagram Reklama"
        )
        self.lost_reason = LostReason.objects.create(
            organization=self.org,
            reason="Narxi qimmatlik qildi"
        )
        self.client.force_authenticate(user=self.user)

    def test_pipeline_crud(self):
        res = self.client.get('/api/v1/crm/pipelines/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertTrue(len(res.data) >= 1)

    def test_source_and_section_list(self):
        res_source = self.client.get('/api/v1/crm/sources/')
        self.assertEqual(res_source.status_code, status.HTTP_200_OK)
        
        res_sec = self.client.get('/api/v1/crm/sections/')
        self.assertEqual(res_sec.status_code, status.HTTP_200_OK)

    def test_lead_create_and_detail(self):
        create_res = self.client.post('/api/v1/crm/leads/', {
            "name": "Ali Valiyev",
            "phone": "+998901112233",
            "pipeline": self.pipeline.id,
            "section": self.section.id,
            "source": self.source.id,
            "status": "open"
        })
        self.assertEqual(create_res.status_code, status.HTTP_201_CREATED)
        lead_id = create_res.data['id']

        detail_res = self.client.get(f'/api/v1/crm/leads/{lead_id}/')
        self.assertEqual(detail_res.status_code, status.HTTP_200_OK)
        self.assertEqual(detail_res.data['name'], "Ali Valiyev")

    def test_lead_bulk_create(self):
        bulk_data = {
            "leads": [
                {
                    "name": "Lid 1",
                    "phone": "+998901110001",
                    "pipeline": self.pipeline.id,
                    "section": self.section.id,
                    "source": self.source.id,
                },
                {
                    "name": "Lid 2",
                    "phone": "+998901110002",
                    "pipeline": self.pipeline.id,
                    "section": self.section.id,
                    "source": self.source.id,
                }
            ]
        }
        res = self.client.post('/api/v1/crm/leads/bulk-create/', bulk_data, format='json')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['success_count'], 2)

    def test_public_form_submit(self):
        form = LeadForm.objects.create(
            organization=self.org,
            name="Landing Form",
            pipeline=self.pipeline,
            section=self.section,
            source=self.source
        )
        self.client.logout()

        # Public view form detail
        get_res = self.client.get(f'/api/v1/crm/public/forms/{form.id}/')
        self.assertEqual(get_res.status_code, status.HTTP_200_OK)

        # Public submit
        submit_res = self.client.post('/api/v1/crm/public/forms/submit/', {
            "form_id": form.id,
            "name": "Tashrifchi",
            "phone": "+998909998877"
        })
        self.assertEqual(submit_res.status_code, status.HTTP_201_CREATED)
        self.assertTrue(Lead.objects.filter(phone="+998909998877").exists())
