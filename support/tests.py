from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from django.contrib.auth import get_user_model
from unittest.mock import patch
from organizations.models import Organization
from support.models import FAQCategory, FAQItem, ChatSession, SupportTicket
from support.services.faq import FAQService
from support.services.ticket import TicketService
from support.services.chat import AIChatService

User = get_user_model()


class SupportModuleTests(APITestCase):
    def setUp(self):
        # Create Organizations
        self.org1 = Organization.objects.create(name="Organization One")
        self.org2 = Organization.objects.create(name="Organization Two")

        # Create Users
        self.admin = User.objects.create_user(
            username="admin1",
            password="securepassword",
            role="admin",
            organization=self.org1
        )
        self.user = User.objects.create_user(
            username="user1",
            password="securepassword",
            role="student",
            organization=self.org1
        )
        self.other_user = User.objects.create_user(
            username="otheruser",
            password="securepassword",
            role="student",
            organization=self.org2
        )

        # Create FAQs in Org 1
        self.category1 = FAQCategory.objects.create(
            name="General Info",
            organization=self.org1
        )
        self.faq1 = FAQItem.objects.create(
            category=self.category1,
            question="Qanday ro'yxatdan o'taman?",
            answer="Saytning bosh sahifasidagi ro'yxatdan o'tish tugmasini bosing.",
            keywords=["ro'yxatdan", "kirish", "akkount"],
            organization=self.org1
        )
        self.faq2 = FAQItem.objects.create(
            category=self.category1,
            question="To'lov usullari qanaqa?",
            answer="Biz click, payme va naqd pul to'lovlarini qabul qilamiz.",
            keywords=["to'lov", "click", "payme", "pul"],
            organization=self.org1
        )

        # Create FAQ in Org 2 (to test tenant isolation)
        self.category2 = FAQCategory.objects.create(
            name="Org 2 Info",
            organization=self.org2
        )
        self.faq_org2 = FAQItem.objects.create(
            category=self.category2,
            question="Org 2 FAQ",
            answer="This is Org 2 answer",
            keywords=["org2"],
            organization=self.org2
        )

    def test_faq_service_search_exact_match(self):
        """
        Verify exact question matching in FAQService.
        """
        item, score = FAQService.search_matching_faq("Qanday ro'yxatdan o'taman?", self.org1.id)
        self.assertEqual(item, self.faq1)
        self.assertEqual(score, 1.0)

    def test_faq_service_search_keyword_match(self):
        """
        Verify keyword overlap matching in FAQService.
        """
        item, score = FAQService.search_matching_faq("to'lov qilish bo'yicha yordam bering", self.org1.id)
        self.assertEqual(item, self.faq2)
        self.assertTrue(score >= 0.7)

    def test_faq_service_search_tenant_isolation(self):
        """
        Verify search results do not bleed across organizations.
        """
        # Org 2 question searched inside Org 1
        item, score = FAQService.search_matching_faq("Org 2 FAQ", self.org1.id)
        self.assertIsNone(item)
        self.assertEqual(score, 0.0)

    def test_ticket_service_manual_and_auto_creation(self):
        """
        Verify ticket manual and automatic creations.
        """
        session = ChatSession.objects.create(
            user=self.user,
            organization=self.org1
        )
        
        # Test auto-creation
        ticket = TicketService.auto_create_ticket(session, "Tizim butunlay ishlamayapti, operatorga ulang")
        self.assertEqual(ticket.session, session)
        self.assertEqual(ticket.priority, "high")  # escalates due to 'ishlamayapti' / 'operator'
        self.assertEqual(ticket.status, "open")
        self.assertEqual(ticket.organization, self.org1)

        # Test manual user creation
        manual_ticket = TicketService.create_user_ticket(
            user=self.user,
            organization_id=self.org1.id,
            title="Manual Ticket",
            description="Need help"
        )
        self.assertEqual(manual_ticket.user, self.user)
        self.assertEqual(manual_ticket.status, "open")

    def test_ai_chat_service_faq_hits(self):
        """
        Verify that AIChatService returns FAQ answer directly for matching questions.
        """
        res = AIChatService.handle_chat_message(
            session_id_str=None,
            message="To'lov usullari qanaqa?",
            user=self.user
        )
        self.assertEqual(res['source'], "faq")
        self.assertEqual(res['answer'], self.faq2.answer)
        self.assertEqual(res['ticket_created'], False)

    @patch('support.utils.llm_client.LLMClient.ask_ai')
    def test_ai_chat_service_llm_fallback_and_auto_ticketing(self, mock_ask_ai):
        """
        Verify LLM fallback and auto-ticketing triggers on low confidence scores.
        """
        # Simulate LLM returning a low confidence answer
        mock_ask_ai.return_statement = ("Kechirasiz, tushunmadim.", 0.1)
        mock_ask_ai.return_value = ("Kechirasiz, tushunmadim.", 0.1)

        res = AIChatService.handle_chat_message(
            session_id_str=None,
            message="Noma'lum g'alati savol",
            user=self.user
        )
        
        self.assertEqual(res['source'], "llm")
        self.assertTrue(res['ticket_created'])
        self.assertIsNotNone(res['ticket_id'])
        self.assertIn("chiptasi ochildi", res['answer'])

    def test_chat_api_endpoint(self):
        """
        Verify the ChatAPIView endpoint works for authenticated users.
        """
        self.client.force_authenticate(user=self.user)
        url = reverse('chat-api')
        
        # Test start session with FAQ exact match
        data = {"message": "Qanday ro'yxatdan o'taman?"}
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['source'], "faq")
        self.assertIsNotNone(response.data['session_id'])

    def test_support_ticket_viewset_isolation(self):
        """
        Verify that regular users only see their own tickets, while admins see all organization tickets.
        """
        # Create tickets
        ticket1 = SupportTicket.objects.create(
            user=self.user,
            title="Ticket 1",
            description="Alice issue",
            organization=self.org1
        )
        SupportTicket.objects.create(
            user=self.admin,
            title="Ticket 2",
            description="Admin issue",
            organization=self.org1
        )
        
        # Authenticate as Alice (regular student)
        self.client.force_authenticate(user=self.user)
        url = reverse('support-ticket-list')
        response = self.client.get(f"{url}?org_id={self.org1.id}")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Should only see Alice's ticket (results inside paginated envelope)
        self.assertEqual(len(response.data['results']), 1)
        self.assertEqual(response.data['results'][0]['id'], ticket1.id)

        # Authenticate as Admin of Org 1
        self.client.force_authenticate(user=self.admin)
        response_admin = self.client.get(f"{url}?org_id={self.org1.id}")
        self.assertEqual(response_admin.status_code, status.HTTP_200_OK)
        # Admins see all tickets in Org 1
        self.assertEqual(len(response_admin.data['results']), 2)
