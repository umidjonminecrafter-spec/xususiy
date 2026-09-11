from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from django.contrib.auth import get_user_model
import datetime
from organizations.models import Organization
from academics.models import Student, Group, Attendance, Course

User = get_user_model()

class AnalyticsTests(APITestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="Analytics Org")
        self.admin = User.objects.create_user(
            username="analyticsadmin",
            password="securepassword",
            role="admin",
            organization=self.org
        )
        self.client.force_authenticate(user=self.admin)

        # Create basic course, group, student, and attendance
        self.course = Course.objects.create(organization=self.org, name="English", price=120000.00)
        self.group = Group.objects.create(organization=self.org, name="Eng-101", course=self.course)
        self.student = Student.objects.create(
            organization=self.org,
            first_name="David",
            last_name="Beckham",
            phone="+998901234560"
        )
        
        self.attendance_date = datetime.date(2026, 6, 18)
        self.attendance = Attendance.objects.create(
            organization=self.org,
            group=self.group,
            student=self.student,
            date=self.attendance_date,
            status="present"
        )

    def test_global_attendance_date_normalization(self):
        """
        Verify that DD/MM/YYYY date formats are normalized to YYYY-MM-DD
        and return the correct attendance records.
        """
        url = reverse('global-attendance')
        
        # Test DD/MM/YYYY format
        response = self.client.get(f"{url}?date=18/06/2026&org_id={self.org.id}")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['student_name'], "David Beckham")

        # Test DD-MM-YYYY format
        response2 = self.client.get(f"{url}?date=18-06-2026&org_id={self.org.id}")
        self.assertEqual(response2.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response2.data), 1)

    def test_global_attendance_uzbek_status_filtering(self):
        """
        Verify that Uzbek status terms like 'keldi' are correctly mapped
        to 'present' inside the backend filtering.
        """
        url = reverse('global-attendance')
        
        # Filter with 'keldi' (uzbek present)
        response = self.client.get(f"{url}?date=2026-06-18&attendance_status=keldi&org_id={self.org.id}")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)

        # Filter with 'sababli' (uzbek excused) -> should return 0 since student present
        response2 = self.client.get(f"{url}?date=2026-06-18&attendance_status=sababli&org_id={self.org.id}")
        self.assertEqual(response2.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response2.data), 0)

    def test_date_from_parameter_support(self):
        """
        Verify that global-attendance, attendance-stats, and unmarked-groups
        views all correctly support date_from parameter instead of date.
        """
        # 1. global-attendance
        url_global = reverse('global-attendance')
        response = self.client.get(f"{url_global}?date_from=18/06/2026&org_id={self.org.id}")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)

        # 2. attendance-stats (AttendanceAnalyticsAPIView)
        url_stats = reverse('attendance-stats')
        response_stats = self.client.get(f"{url_stats}?date_from=18/06/2026&org_id={self.org.id}")
        self.assertEqual(response_stats.status_code, status.HTTP_200_OK)
        self.assertEqual(response_stats.data['summary']['kelganlar'], 1)
        self.assertEqual(response_stats.data['summary']['birinchi dars'], 0)

        # 3. unmarked-groups
        url_unmarked = reverse('unmarked-groups')
        response_unmarked = self.client.get(f"{url_unmarked}?date_from=18/06/2026&org_id={self.org.id}")
        self.assertEqual(response_unmarked.status_code, status.HTTP_200_OK)

    def test_date_range_support(self):
        """
        Verify that analytics views support date ranges (date_from and date_to).
        """
        # Create another attendance on a different date in the range
        Attendance.objects.create(
            organization=self.org,
            group=self.group,
            student=self.student,
            date=datetime.date(2026, 6, 20),
            status="absent"
        )

        url_stats = reverse('attendance-stats')
        response = self.client.get(f"{url_stats}?date_from=18/06/2026&date_to=22/06/2026&org_id={self.org.id}")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Should sum kelganlar=1 (from June 18) and sababsiz=1 (from June 20)
        self.assertEqual(response.data['summary']['kelganlar'], 1)
        self.assertEqual(response.data['summary']['sababsiz'], 1)
