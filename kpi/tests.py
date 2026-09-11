from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from decimal import Decimal

from organizations.models import Organization
from academics.models import Student
from crm.models import Lead, Pipeline, Section
from finance.models import Cashbox, Payment
from kpi.models import KPITemplate, KPIGoal, KPISubGoal, KPILog

User = get_user_model()

class KPISystemTests(APITestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="KPI Test Org")
        self.admin = User.objects.create_user(
            username="+998901112299",
            password="securepassword",
            role="admin",
            organization=self.org
        )
        self.employee = User.objects.create_user(
            username="+998901113300",
            password="securepassword",
            role="employee",
            organization=self.org
        )
        
        self.client.force_authenticate(user=self.admin)
        
        # Create pipeline and section for lead tests
        self.pipeline = Pipeline.objects.create(organization=self.org, name="Sotuv voronkasi")
        self.section = Section.objects.create(organization=self.org, pipeline=self.pipeline, name="Yangi")

        # Create cashbox for payments
        self.cashbox = Cashbox.objects.create(organization=self.org, name="Kassa")

        # Create a standard template for role 'employee'
        self.template = KPITemplate.objects.create(
            organization=self.org,
            name="Moderator KPI Andozasi",
            role="employee",
            sub_goals_config=[
                {
                    "name": "Lidlarni talabaga aylantirish",
                    "metric_type": "automatic",
                    "system_event": "lead_to_student",
                    "target_value": 10.00,
                    "weight": 40.00
                },
                {
                    "name": "To'lovlar yig'ish",
                    "metric_type": "automatic",
                    "system_event": "new_payment",
                    "target_value": 1000000.00,
                    "weight": 60.00
                }
            ]
        )

    def test_create_kpi_template(self):
        url = reverse('kpi-template-list')
        data = {
            "name": "O'qituvchi KPI Andozasi",
            "role": "teacher",
            "sub_goals_config": [
                {
                    "name": "Davomat topshirish",
                    "metric_type": "automatic",
                    "system_event": "attendance_taken",
                    "target_value": 20.00,
                    "weight": 100.00
                }
            ]
        }
        response = self.client.post(f"{url}?org_id={self.org.id}", data=data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(KPITemplate.objects.filter(role="teacher").count(), 1)

    def test_assign_template_to_employees(self):
        url = reverse('kpi-goal-assign-template')
        data = {
            "template_id": self.template.id,
            "employee_ids": [self.employee.id],
            "start_date": "2026-08-01",
            "end_date": "2026-08-31",
            "name": "August 2026 KPI"
        }
        response = self.client.post(f"{url}?org_id={self.org.id}", data=data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        
        # Verify goal and sub-goals creation
        goal = KPIGoal.objects.filter(employee=self.employee).first()
        self.assertIsNotNone(goal)
        self.assertEqual(goal.name, "August 2026 KPI")
        self.assertEqual(goal.sub_goals.count(), 2)

    def test_automatic_lead_won_kpi_sync(self):
        # First assign template to employee
        goal = KPIGoal.objects.create(
            organization=self.org,
            employee=self.employee,
            name="August KPI",
            start_date=timezone.datetime(2026, 8, 1).date(),
            end_date=timezone.datetime(2026, 8, 31).date()
        )
        sub_won = KPISubGoal.objects.create(
            organization=self.org,
            parent_goal=goal,
            name="Lid Won",
            metric_type="automatic",
            system_event="lead_to_student",
            target_value=Decimal('10.00'),
            weight=Decimal('40.00')
        )
        
        # Create a lead assigned to employee
        lead = Lead.objects.create(
            organization=self.org,
            name="Akmal",
            phone="+998909000001",
            moderator=self.employee,
            status="open",
            contacted_at=timezone.datetime(2026, 8, 15)
        )

        # Update lead status to won
        lead.status = "won"
        lead.save()

        # Check sub-goal progress
        sub_won.refresh_from_db()
        self.assertEqual(sub_won.current_value, Decimal('1.00'))

        # Check parent goal calculation: (1 / 10) * 40 = 4%
        goal.refresh_from_db()
        self.assertEqual(goal.total_progress, Decimal('4.00'))

        # Check logs created
        self.assertTrue(KPILog.objects.filter(sub_goal=sub_won).exists())

    def test_automatic_payment_kpi_sync(self):
        # Assign template to employee
        goal = KPIGoal.objects.create(
            organization=self.org,
            employee=self.employee,
            name="August KPI",
            start_date=timezone.datetime(2026, 8, 1).date(),
            end_date=timezone.datetime(2026, 8, 31).date()
        )
        sub_payment = KPISubGoal.objects.create(
            organization=self.org,
            parent_goal=goal,
            name="To'lovlar",
            metric_type="automatic",
            system_event="new_payment",
            target_value=Decimal('1000000.00'),
            weight=Decimal('60.00')
        )

        student = Student.objects.create(
            organization=self.org,
            first_name="John",
            phone="+998901234500"
        )

        # Create a payment collected by the employee
        Payment.objects.create(
            organization=self.org,
            student=student,
            amount=Decimal('250000.00'),
            date=timezone.datetime(2026, 8, 10).date(),
            cashbox=self.cashbox,
            payment_method="Naqd",
            employee=self.employee
        )

        sub_payment.refresh_from_db()
        self.assertEqual(sub_payment.current_value, Decimal('250000.00'))

        # Check parent goal progress: (250,000 / 1,000,000) * 60 = 15%
        goal.refresh_from_db()
        self.assertEqual(goal.total_progress, Decimal('15.00'))
