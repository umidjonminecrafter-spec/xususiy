import datetime
from decimal import Decimal
from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase
from rest_framework import status

from organizations.models import Organization, Branch, Subscription, Tariff
from academics.models import Student, Group, GroupLesson, Attendance, Course
from crm.models import Lead, Pipeline, Section
from finance.models import Payment, Expense, ExpenseCategory, Cashbox

User = get_user_model()


class BranchIsolationTests(APITestCase):
    """
    Test suite to ensure strict branch isolation across all modules.
    Data from one branch must never mix with data from another branch.
    """

    def setUp(self):
        # 1. Organization & Subscription
        self.org = Organization.objects.create(name="Multi-Branch Academy")
        today = datetime.date.today()
        tariff = Tariff.objects.create(name="Unlimited", price=Decimal("1000.00"), student_limit=0)
        Subscription.objects.create(
            organization=self.org,
            tariff=tariff,
            start_date=today,
            end_date=today + datetime.timedelta(days=365),
            is_active=True
        )

        # 2. Branches
        self.branch_a = Branch.objects.create(organization=self.org, name="Chilonzor Filiali")
        self.branch_b = Branch.objects.create(organization=self.org, name="Yunusobod Filiali")

        self.course = Course.objects.create(
            organization=self.org,
            name="General Course",
            price=Decimal("300000.00")
        )

        # 3. Users
        self.owner = User.objects.create_user(
            username="owner_user",
            password="password123",
            role="owner",
            organization=self.org
        )

        self.staff_a = User.objects.create_user(
            username="staff_chilonzor",
            password="password123",
            role="staff",
            organization=self.org,
            branch=self.branch_a
        )
        self.staff_a.branches.add(self.branch_a)

        self.staff_b = User.objects.create_user(
            username="staff_yunusobod",
            password="password123",
            role="staff",
            organization=self.org,
            branch=self.branch_b
        )
        self.staff_b.branches.add(self.branch_b)

        # 4. Operational Data for Branch A
        self.student_a = Student.objects.create(
            organization=self.org,
            branch=self.branch_a,
            first_name="Ali",
            last_name="Valiyev",
            phone="+998901111111",
            balance=Decimal("0.00")
        )
        self.debtor_a = Student.objects.create(
            organization=self.org,
            branch=self.branch_a,
            first_name="Qodir",
            last_name="Qarzdorov",
            phone="+998901119999",
            balance=Decimal("-50000.00")  # Debtor in Branch A
        )
        self.group_a = Group.objects.create(
            organization=self.org,
            branch=self.branch_a,
            course=self.course,
            name="Python-Branch-A",
            start_date=today,
            end_date=today + datetime.timedelta(days=30),
            status="active"
        )
        self.lead_a = Lead.objects.create(
            organization=self.org,
            branch=self.branch_a,
            name="Lead Branch A",
            phone="+998901112233",
            status="open"
        )
        self.cashbox_a = Cashbox.objects.create(
            organization=self.org,
            branch=self.branch_a,
            name="Kassa A",
            balance=Decimal("1000000.00")
        )
        self.payment_a = Payment.objects.create(
            organization=self.org,
            branch=self.branch_a,
            student=self.student_a,
            cashbox=self.cashbox_a,
            amount=Decimal("200000.00"),
            payment_method="Cash",
            date=today
        )

        # 5. Operational Data for Branch B
        self.student_b = Student.objects.create(
            organization=self.org,
            branch=self.branch_b,
            first_name="Hasan",
            last_name="Husanov",
            phone="+998902222222",
            balance=Decimal("0.00")
        )
        self.debtor_b = Student.objects.create(
            organization=self.org,
            branch=self.branch_b,
            first_name="Sobir",
            last_name="Qarzdorov",
            phone="+998902228888",
            balance=Decimal("-100000.00")  # Debtor in Branch B
        )
        self.group_b = Group.objects.create(
            organization=self.org,
            branch=self.branch_b,
            course=self.course,
            name="English-Branch-B",
            start_date=today,
            end_date=today + datetime.timedelta(days=30),
            status="active"
        )
        self.lead_b = Lead.objects.create(
            organization=self.org,
            branch=self.branch_b,
            name="Lead Branch B",
            phone="+998904445566",
            status="open"
        )
        self.cashbox_b = Cashbox.objects.create(
            organization=self.org,
            branch=self.branch_b,
            name="Kassa B",
            balance=Decimal("500000.00")
        )
        self.payment_b = Payment.objects.create(
            organization=self.org,
            branch=self.branch_b,
            student=self.student_b,
            cashbox=self.cashbox_b,
            amount=Decimal("300000.00"),
            payment_method="Cash",
            date=today
        )

    def _extract_results(self, response_data):
        if isinstance(response_data, dict):
            return response_data.get('results', response_data)
        return response_data

    def test_students_branch_isolation(self):
        """Students query param must strictly return only that branch's students."""
        self.client.force_authenticate(user=self.owner)

        # Branch A query
        response = self.client.get(f'/api/v1/students/?branch={self.branch_a.id}')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = self._extract_results(response.data)
        student_ids = [s['id'] for s in results]
        self.assertIn(self.student_a.id, student_ids)
        self.assertIn(self.debtor_a.id, student_ids)
        self.assertNotIn(self.student_b.id, student_ids)
        self.assertNotIn(self.debtor_b.id, student_ids)

        # Branch B query
        response = self.client.get(f'/api/v1/students/?branch={self.branch_b.id}')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = self._extract_results(response.data)
        student_ids = [s['id'] for s in results]
        self.assertIn(self.student_b.id, student_ids)
        self.assertIn(self.debtor_b.id, student_ids)
        self.assertNotIn(self.student_a.id, student_ids)
        self.assertNotIn(self.debtor_a.id, student_ids)

    def test_leads_branch_isolation(self):
        """Leads query must strictly return only that branch's leads."""
        self.client.force_authenticate(user=self.owner)

        # Branch A
        response = self.client.get(f'/api/v1/crm/leads/?branch={self.branch_a.id}')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = self._extract_results(response.data)
        lead_ids = [item['id'] for item in results]
        self.assertIn(self.lead_a.id, lead_ids)
        self.assertNotIn(self.lead_b.id, lead_ids)

        # Branch B
        response = self.client.get(f'/api/v1/crm/leads/?branch={self.branch_b.id}')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = self._extract_results(response.data)
        lead_ids = [item['id'] for item in results]
        self.assertIn(self.lead_b.id, lead_ids)
        self.assertNotIn(self.lead_a.id, lead_ids)

    def test_groups_branch_isolation(self):
        """Groups query must strictly return only that branch's groups."""
        self.client.force_authenticate(user=self.owner)

        # Branch A
        response = self.client.get(f'/api/v1/academics/groups/?branch={self.branch_a.id}')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = self._extract_results(response.data)
        group_ids = [item['id'] for item in results]
        self.assertIn(self.group_a.id, group_ids)
        self.assertNotIn(self.group_b.id, group_ids)

        # Branch B
        response = self.client.get(f'/api/v1/academics/groups/?branch={self.branch_b.id}')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = self._extract_results(response.data)
        group_ids = [item['id'] for item in results]
        self.assertIn(self.group_b.id, group_ids)
        self.assertNotIn(self.group_a.id, group_ids)

    def test_student_debts_branch_isolation(self):
        """Student debts view must strictly filter debtors by branch."""
        self.client.force_authenticate(user=self.owner)

        # Branch A debts
        response = self.client.get(f'/api/v1/finance/student-debts/?branch={self.branch_a.id}')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = self._extract_results(response.data)
        student_ids = [s['id'] for s in results]
        self.assertIn(self.debtor_a.id, student_ids)
        self.assertNotIn(self.debtor_b.id, student_ids)

        # Branch B debts
        response = self.client.get(f'/api/v1/finance/student-debts/?branch={self.branch_b.id}')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = self._extract_results(response.data)
        student_ids = [s['id'] for s in results]
        self.assertIn(self.debtor_b.id, student_ids)
        self.assertNotIn(self.debtor_a.id, student_ids)

    def test_student_debts_summary_branch_isolation(self):
        """Student debts summary must calculate debts strictly for selected branch."""
        self.client.force_authenticate(user=self.owner)

        # Branch A summary: 1 debtor, 50,000 UZS debt
        response = self.client.get(f'/api/v1/finance/student-debts/summary/?branch={self.branch_a.id}')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(Decimal(str(response.data['total_student_debts'])), Decimal("50000.00"))
        self.assertEqual(response.data['debtors_count'], 1)

        # Branch B summary: 1 debtor, 100,000 UZS debt
        response = self.client.get(f'/api/v1/finance/student-debts/summary/?branch={self.branch_b.id}')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(Decimal(str(response.data['total_student_debts'])), Decimal("100000.00"))
        self.assertEqual(response.data['debtors_count'], 1)

    def test_global_search_branch_isolation(self):
        """Global search must not leak students/groups from other branches when branch is passed."""
        self.client.force_authenticate(user=self.owner)

        # Search for 'Valiyev' (student_a) in Branch B -> should be empty
        response = self.client.get(f'/api/v1/organizations/global-search/?q=Valiyev&branch={self.branch_b.id}')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 0)

        # Search for 'Valiyev' in Branch A -> found
        response = self.client.get(f'/api/v1/organizations/global-search/?q=Valiyev&branch={self.branch_a.id}')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['name'], "Ali Valiyev")

    def test_branch_status_analytics_per_branch(self):
        """BranchStatusAPIView returns separate rows for each branch with accurate stats."""
        self.client.force_authenticate(user=self.owner)

        response = self.client.get('/api/v1/analytics/branch-status/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 2)

        branch_names = [row['filial'] for row in response.data]
        self.assertIn("Chilonzor Filiali", branch_names)
        self.assertIn("Yunusobod Filiali", branch_names)

        # Filter specifically for branch A
        response_a = self.client.get(f'/api/v1/analytics/branch-status/?branch_id={self.branch_a.id}')
        self.assertEqual(response_a.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response_a.data), 1)
        self.assertEqual(response_a.data[0]['filial'], "Chilonzor Filiali")
        self.assertEqual(response_a.data[0]['qarzdorlar'], 1)

    def test_create_student_with_explicit_branch(self):
        """Creating a student via POST with branch in payload stores correct branch."""
        self.client.force_authenticate(user=self.owner)

        payload = {
            "first_name": "Nodir",
            "last_name": "Sobirov",
            "phone": "+998909998877",
            "password": "password123",
            "branch": self.branch_b.id
        }
        response = self.client.post('/api/v1/students/', payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        new_student = Student.objects.get(id=response.data['id'])
        self.assertEqual(new_student.branch_id, self.branch_b.id)

    def test_non_admin_cannot_access_other_branch(self):
        """Staff restricted to Branch A cannot view Branch B data by spoofing query param."""
        self.client.force_authenticate(user=self.staff_a)

        # Staff A querying branch B should return empty queryset (not branch B's students)
        response = self.client.get(f'/api/v1/students/?branch={self.branch_b.id}')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = self._extract_results(response.data)
        student_ids = [s['id'] for s in results]
        self.assertNotIn(self.student_b.id, student_ids)
