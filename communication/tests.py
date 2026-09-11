from rest_framework import status
from rest_framework.test import APITestCase
from django.contrib.auth import get_user_model
from django.test import RequestFactory
from organizations.models import Organization, Branch
from academics.models import Course, Group, Student, StudentGroup
from communication.models import NotificationSchedule, Notification
from communication.services import dispatch_notification_schedule
from organizations.admin import send_notification_to_organizations

User = get_user_model()

class NotificationScheduleAPITests(APITestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="Test Org")
        self.branch = Branch.objects.create(name="Test Branch", organization=self.org)
        self.user = User.objects.create_user(
            username="+998901112236",
            password="securepassword",
            email="owner@talim.com",
            phone="+998901112236",
            role="owner",
            organization=self.org
        )
        # Create some users
        self.employee = User.objects.create_user(
            username="+998901112237",
            password="securepassword",
            email="emp@talim.com",
            phone="+998901112237",
            role="employee",
            organization=self.org
        )
        self.teacher = User.objects.create_user(
            username="+998901112238",
            password="securepassword",
            email="teacher@talim.com",
            phone="+998901112238",
            role="teacher",
            organization=self.org
        )
        self.student_user = User.objects.create_user(
            username="+998901112239",
            password="securepassword",
            email="student@talim.com",
            phone="+998901112239",
            role="student",
            organization=self.org
        )
        # Create Course
        self.course = Course.objects.create(
            name="Math Course",
            price=200000.00,
            organization=self.org,
            branch=self.branch
        )
        # Create Student and Group link
        self.student = Student.objects.create(
            first_name="Jane",
            last_name="Doe",
            phone="+998901112239",
            organization=self.org,
            branch=self.branch
        )
        self.group = Group.objects.create(
            name="Math 101",
            course=self.course,
            organization=self.org,
            branch=self.branch
        )
        StudentGroup.objects.create(
            student=self.student,
            group=self.group,
            organization=self.org,
            branch=self.branch
        )

        self.client.force_authenticate(user=self.user)
        # Mock active branch in headers
        self.client.credentials(HTTP_X_BRANCH_ID=str(self.branch.id))

    def test_send_immediate_without_send_at(self):
        """
        Ensure sending an immediate notification (via send-now endpoint)
        does not fail validation when send_at is missing from the payload.
        """
        url = "/api/v1/communication/notification-schedules/send-now/"
        data = {
            "title": "Urgent Alert",
            "message": "This is an immediate notification.",
            "target_roles": ["employee"]
        }
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn('schedule', response.data)
        self.assertEqual(response.data['schedule']['delivery_mode'], 'immediate')
        self.assertIsNotNone(response.data['schedule']['send_at'])

    def test_dispatch_to_multiple_recipients(self):
        """
        Test that dispatch_notification_schedule successfully resolves and
        creates notifications for target roles, target users, and target groups.
        """
        schedule = NotificationSchedule.objects.create(
            title="Bulk Announcement",
            message="Hello everyone!",
            delivery_mode="immediate",
            target_roles=["teacher", "employee"],
            target_user_ids=[self.user.id],
            target_group_ids=[self.group.id],
            organization=self.org,
            branch=self.branch,
            created_by=self.user
        )

        sent_count = dispatch_notification_schedule(schedule)
        self.assertEqual(sent_count, 4)
        self.assertEqual(Notification.objects.filter(title="Bulk Announcement").count(), 4)
        self.assertTrue(Notification.objects.filter(user=self.teacher, title="Bulk Announcement").exists())
        self.assertTrue(Notification.objects.filter(user=self.employee, title="Bulk Announcement").exists())
        self.assertTrue(Notification.objects.filter(user=self.user, title="Bulk Announcement").exists())
        self.assertTrue(Notification.objects.filter(user=self.student_user, title="Bulk Announcement").exists())

    def test_admin_send_notification_to_organizations_targets_only_ceos(self):
        """
        Test that send_notification_to_organizations Django Admin action
        creates notifications targeting only CEO (owner role) users in the organization.
        """
        # We simulate the POST apply request
        factory = RequestFactory()
        request = factory.post('/admin/organizations/organization/', {
            'apply': 'Apply',
            'title': 'System Maintenance',
            'message': 'Database will undergo upgrade.',
            'notification_type': 'info',
            '_selected_action': [str(self.org.id)]
        })
        request.user = self.user
        
        # Mock message storage that doesn't require middleware
        from django.contrib.messages.storage.base import BaseStorage
        class MockMessageStorage(BaseStorage):
            def _get(self):
                return [], True
            def _store(self, messages, response):
                return []
        
        request._messages = MockMessageStorage(request)

        # Queryset of organizations
        queryset = Organization.objects.filter(id=self.org.id)

        # Mock ModelAdmin
        class MockModelAdmin:
            def message_user(self, *args, **kwargs):
                pass

        # Call the admin action
        response = send_notification_to_organizations(MockModelAdmin(), request, queryset)
        
        # Verify redirect response
        self.assertEqual(response.status_code, 302)

        # Verify created notifications
        notifications = Notification.objects.filter(title='System Maintenance')
        # Should be exactly 1, targeting the owner user (self.user)
        self.assertEqual(notifications.count(), 1)
        
        notif = notifications.first()
        self.assertEqual(notif.user, self.user) # owner role
        self.assertEqual(notif.organization, self.org)

        self.assertFalse(Notification.objects.filter(user=self.employee, title='System Maintenance').exists())
        self.assertFalse(Notification.objects.filter(user=self.teacher, title='System Maintenance').exists())
        self.assertFalse(Notification.objects.filter(user=self.student_user, title='System Maintenance').exists())

    def test_sms_telegram_and_scheduling(self):
        """
        Verify that creating SMSMessages triggers send_telegram_message (forwarding to Telegram)
        and that process_sms_schedules management command executes pending SmsSchedules.
        """
        from communication.models import SMSMessages, SmsSchedules
        from django.core.management import call_command
        
        # Set student telegram_chat_id
        self.student.telegram_chat_id = "987654321"
        self.student.save()

        # Mock send_telegram_message
        from unittest.mock import patch
        with patch('academics.telegram_bot.send_telegram_message') as mock_send:
            # 1. Test automatic SMS forwarding to Telegram
            SMSMessages.objects.create(
                organization=self.org,
                recipient=self.student.phone,
                message="Salom, bu test xabari!"
            )
            self.assertTrue(mock_send.called)
            self.assertEqual(mock_send.call_count, 1)
            # Verify recipient check
            self.assertEqual(mock_send.call_args[0][1], "987654321")
            self.assertIn("Salom, bu test xabari!", mock_send.call_args[0][2])

            mock_send.reset_mock()

            # 2. Test scheduled SMS processing
            import datetime
            from django.utils import timezone
            
            # Create a scheduled SMS for the past (due to send)
            schedule = SmsSchedules.objects.create(
                organization=self.org,
                recipient=self.student.phone,
                message="Rejalashtirilgan xabar",
                scheduled_time=timezone.now() - datetime.timedelta(minutes=5)
            )

            # Run management command
            call_command('process_sms_schedules')

            # Verify that it created a sent SMSMessage
            self.assertTrue(SMSMessages.objects.filter(message="Rejalashtirilgan xabar", status='sent').exists())
            # Verify that the schedule is marked as sent
            schedule.refresh_from_db()
            self.assertTrue(schedule.is_sent)

            # Verify that it automatically forwarded to Telegram
            self.assertTrue(mock_send.called)
            self.assertEqual(mock_send.call_count, 1)
            self.assertEqual(mock_send.call_args[0][1], "987654321")
            self.assertIn("Rejalashtirilgan xabar", mock_send.call_args[0][2])


class StudentSMSHistoryAPITests(APITestCase):
    def setUp(self):
        self.org1 = Organization.objects.create(name="Org 1")
        self.org2 = Organization.objects.create(name="Org 2")
        
        self.admin1 = User.objects.create_user(
            username="+998901112250",
            password="securepassword",
            phone="+998901112250",
            role="admin",
            organization=self.org1
        )
        self.admin2 = User.objects.create_user(
            username="+998901112251",
            password="securepassword",
            phone="+998901112251",
            role="admin",
            organization=self.org2
        )
        self.student1 = Student.objects.create(
            first_name="John",
            last_name="Doe",
            phone="+998901110001",
            father_phone="+998901110002",
            mother_phone="+998901110003",
            organization=self.org1
        )
        
        self.client.force_authenticate(user=self.admin1)

    def test_student_sms_history_api_success(self):
        """
        Verify that fetching history via StudentSMSHistoryAPIView GET method
        returns all SMS sent to student's or parents' phones.
        """
        from communication.models import SMSMessages
        SMSMessages.objects.create(
            organization=self.org1,
            recipient=self.student1.phone,
            message="SMS 1",
            status="sent"
        )
        SMSMessages.objects.create(
            organization=self.org1,
            recipient=self.student1.father_phone,
            message="SMS 2",
            status="sent"
        )
        SMSMessages.objects.create(
            organization=self.org1,
            recipient=self.student1.mother_phone,
            message="SMS 3",
            status="sent"
        )
        # Message for another recipient (should not be in history)
        SMSMessages.objects.create(
            organization=self.org1,
            recipient="+998901119999",
            message="SMS other",
            status="sent"
        )
        # Message for student phone but different organization
        SMSMessages.objects.create(
            organization=self.org2,
            recipient=self.student1.phone,
            message="SMS org 2",
            status="sent"
        )

        url = f"/api/v1/communication/student-sms-history/{self.student1.id}/"
        response = self.client.get(f"{url}?org_id={self.org1.id}")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['student']['id'], self.student1.id)
        self.assertEqual(response.data['total_count'], 3)

        messages = [item['message'] for item in response.data['sms_history']]
        self.assertIn("SMS 1", messages)
        self.assertIn("SMS 2", messages)
        self.assertIn("SMS 3", messages)
        self.assertNotIn("SMS other", messages)
        self.assertNotIn("SMS org 2", messages)

    def test_student_sms_history_api_not_found(self):
        """
        Verify that trying to retrieve SMS history of a student from another
        organization returns 404 Not Found.
        """
        self.client.force_authenticate(user=self.admin2) # Admin of Org 2
        url = f"/api/v1/communication/student-sms-history/{self.student1.id}/"
        
        response = self.client.get(f"{url}?org_id={self.org2.id}")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_sms_telegram_bot_routing(self):
        """
        Verify that SMSMessages forwarding routes to the correct bot token
        based on the recipient type (student, father/mother, staff, or admin).
        """
        from organizations.models import TelegramNotificationSetting
        from communication.models import SMSMessages
        from unittest.mock import patch
        
        # Set Telegram settings
        TelegramNotificationSetting.objects.create(
            organization=self.org1,
            bot_token="TOKEN_GEN",
            student_bot_token="TOKEN_STUDENT",
            parent_bot_token="TOKEN_PARENT",
            staff_bot_token="TOKEN_STAFF"
        )
        
        # Set chat IDs
        self.student1.telegram_chat_id = "STUDENT_CHAT"
        self.student1.father_telegram_chat_id = "FATHER_CHAT"
        self.student1.mother_telegram_chat_id = "MOTHER_CHAT"
        self.student1.save()
        
        # Create a teacher user
        teacher = User.objects.create_user(
            username="+998901119900",
            password="password",
            phone="+998901119900",
            role="teacher",
            telegram_chat_id="TEACHER_CHAT",
            organization=self.org1
        )

        # Mock send_telegram_message function
        with patch('academics.telegram_bot.send_telegram_message') as mock_send:
            # 1. Send to Student -> should use student_bot_token
            SMSMessages.objects.create(
                organization=self.org1,
                recipient=self.student1.phone,
                message="To Student"
            )
            self.assertTrue(mock_send.called)
            self.assertEqual(mock_send.call_args[0][0], "TOKEN_STUDENT")
            self.assertEqual(mock_send.call_args[0][1], "STUDENT_CHAT")
            
            mock_send.reset_mock()

            # 2. Send to Father -> should use parent_bot_token
            SMSMessages.objects.create(
                organization=self.org1,
                recipient=self.student1.father_phone,
                message="To Father"
            )
            self.assertTrue(mock_send.called)
            self.assertEqual(mock_send.call_args[0][0], "TOKEN_PARENT")
            self.assertEqual(mock_send.call_args[0][1], "FATHER_CHAT")

            mock_send.reset_mock()

            # 3. Send to Mother -> should use parent_bot_token
            SMSMessages.objects.create(
                organization=self.org1,
                recipient=self.student1.mother_phone,
                message="To Mother"
            )
            self.assertTrue(mock_send.called)
            self.assertEqual(mock_send.call_args[0][0], "TOKEN_PARENT")
            self.assertEqual(mock_send.call_args[0][1], "MOTHER_CHAT")

            mock_send.reset_mock()

            # 4. Send to Teacher -> should use staff_bot_token
            SMSMessages.objects.create(
                organization=self.org1,
                recipient=teacher.phone,
                message="To Teacher"
            )
            self.assertTrue(mock_send.called)
            self.assertEqual(mock_send.call_args[0][0], "TOKEN_STAFF")
            self.assertEqual(mock_send.call_args[0][1], "TEACHER_CHAT")

            mock_send.reset_mock()

            # 5. Send to Admin -> should use bot_token (TOKEN_GEN)
            self.admin1.telegram_chat_id = "ADMIN_CHAT"
            self.admin1.save()
            
            SMSMessages.objects.create(
                organization=self.org1,
                recipient=self.admin1.phone,
                message="To Admin"
            )
            self.assertTrue(mock_send.called)
            self.assertEqual(mock_send.call_args[0][0], "TOKEN_GEN")
            self.assertEqual(mock_send.call_args[0][1], "ADMIN_CHAT")


