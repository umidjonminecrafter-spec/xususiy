from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from decimal import Decimal
from organizations.models import Organization
from academics.models import Course, Student, Group, StudentGroup, Holiday
from finance.models import TeacherSalaryRule, TeacherSalaryCalculation

User = get_user_model()

class HolidayImpactTests(APITestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="Holiday Test Org")
        self.teacher = User.objects.create_user(
            username="testteacher",
            password="securepassword",
            role="teacher",
            organization=self.org
        )
        self.admin_user = User.objects.create_user(
            username="testadmin",
            password="securepassword",
            role="admin",
            organization=self.org
        )
        self.client.force_authenticate(user=self.teacher)

        self.course = Course.objects.create(
            organization=self.org,
            name="Math",
            price=200000.00,
            duration_weeks=12
        )
        self.group = Group.objects.create(
            organization=self.org,
            name="Math-1",
            course=self.course,
            teacher=self.teacher
        )
        self.student = Student.objects.create(
            organization=self.org,
            first_name="John",
            last_name="Doe",
            phone="+998901112233",
            balance=0.00
        )
        self.student_group = StudentGroup.objects.create(
            organization=self.org,
            student=self.student,
            group=self.group
        )

        # Create a rule for fixed salary
        self.fixed_rule = TeacherSalaryRule.objects.create(
            organization=self.org,
            teacher=self.teacher,
            rule_type='fixed',
            rate=Decimal('1000000.00'),
            period='2026-05',
            is_active=True
        )

    def test_fixed_salary_holiday_deduction(self):
        # Create a staff impact holiday in May 2026 (3 days)
        Holiday.objects.create(
            organization=self.org,
            name="May Day Holiday",
            start_date=timezone.datetime(2026, 5, 1).date(),
            end_date=timezone.datetime(2026, 5, 3).date(),
            staff_impact=True,
            student_impact=False
        )

        url = reverse('teacher-salary-calculate')
        data = {
            "period": "2026-05",
            "org_id": self.org.id
        }
        
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.post(f"{url}?org_id={self.org.id}", data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        
        # May has 31 days. 3 days holiday.
        # Expected payout: 1,000,000 * (1 - 3/31) = 1,000,000 * 28/31 = 903225.81
        calc = TeacherSalaryCalculation.objects.get(teacher=self.teacher, period='2026-05')
        expected_amount = Decimal('1000000.00') * (Decimal(28) / Decimal(31))
        self.assertAlmostEqual(float(calc.calculated_amount), float(expected_amount), places=2)

    def test_student_price_holiday_discount(self):
        # Create a student impact holiday in the current month (e.g. 5 days)
        now = timezone.now().date()
        import calendar
        _, last_day = calendar.monthrange(now.year, now.month)
        
        # Clear existing holidays to be sure
        Holiday.objects.all().delete()
        
        # Create holiday starting at the start of the month for 5 days
        h_start = now.replace(day=1)
        h_end = now.replace(day=5)
        
        Holiday.objects.create(
            organization=self.org,
            name="Student Holiday",
            start_date=h_start,
            end_date=h_end,
            staff_impact=False,
            student_impact=True
        )

        url = reverse('student-group-detail', kwargs={'pk': self.student_group.id})
        response = self.client.get(f"{url}?org_id={self.org.id}")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Expected price: 200,000 * (1 - 5 / last_day)
        expected_price = Decimal('200000.00') * (Decimal(last_day - 5) / Decimal(last_day))
        self.assertAlmostEqual(float(response.data['price']), float(expected_price), places=2)


class CashTransactionAPITests(APITestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="Cash Test Org")
        self.admin = User.objects.create_user(
            username="cashadmin",
            password="securepassword",
            role="admin",
            organization=self.org
        )
        self.employee = User.objects.create_user(
            username="cashemployee",
            password="securepassword",
            role="teacher",
            organization=self.org
        )
        self.student = Student.objects.create(
            organization=self.org,
            first_name="Jane",
            last_name="Doe",
            phone="+998909876543",
            balance=0.00
        )

        from finance.models import Cashbox
        self.cashbox = Cashbox.objects.create(
            organization=self.org,
            name="Naqd pul",
            balance=Decimal("0.00")
        )

        self.client.force_authenticate(user=self.admin)

    def test_cash_transaction_kirim_disallows_student(self):
        """
        Verify that student is disallowed for Kassa kirim (INCOME).
        """
        url = reverse('transaction-create')
        data = {
            "cashbox": self.cashbox.id,
            "transaction_type": "kirim",
            "payment_method": "naqd",
            "amount": "150000.00",
            "date": "2026-07-01",
            "category_name": "Boshqa kirim",
            "description": "General income"
        }

        # General kirim without student -> should pass
        response = self.client.post(url, data=data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # Attempt with student -> should fail
        data_with_student = data.copy()
        data_with_student["student"] = self.student.id
        response = self.client.post(url, data_with_student, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("student", response.data)

        # Verify kassa balance
        self.cashbox.refresh_from_db()
        self.assertEqual(self.cashbox.balance, Decimal("150000.00"))

    def test_cash_transaction_chiqim_employee_required(self):
        """
        Verify that employee is required for chiqim (EXPENSE) if description/category contains employee keywords.
        """
        url = reverse('transaction-create')
        data = {
            "cashbox": self.cashbox.id,
            "transaction_type": "chiqim",
            "payment_method": "naqd",
            "amount": "50000.00",
            "date": "2026-07-01",
            "category_name": "ish haqi oylik",
            "description": "Xodim oyligi"
        }

        # Attempt without employee -> should fail
        response = self.client.post(url, data=data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("employee", response.data)

        # Attempt with employee -> should pass
        data["employee"] = self.employee.id
        response = self.client.post(url, data=data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # Verify kassa balance (starts at 0 before this test, so after subtracting 50000 it is -50000)
        self.cashbox.refresh_from_db()
        self.assertEqual(self.cashbox.balance, Decimal("-50000.00"))

    def test_transaction_report_api(self):
        """
        Verify that transaction report API returns CashTransaction serializer outputs correctly.
        """
        from finance.models import CashTransaction
        import datetime
        CashTransaction.objects.create(
            organization=self.org,
            cashbox=self.cashbox,
            transaction_type="kirim",
            payment_method="naqd",
            amount=Decimal("200000.00"),
            date=datetime.date(2026, 7, 1),
            student=self.student,
            category_name="o'quvchi to'lov",
            comment="Izoh matni"
        )

        url = reverse('transaction-report')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["student_name"], self.student.full_name)
        self.assertEqual(response.data[0]["description"], "Izoh matni")

    def test_cashbox_transfer_success(self):
        """
        Verify that transferring money from one cashbox to another updates balances and creates CashTransactions.
        """
        from finance.models import Cashbox, CashTransaction
        import datetime

        # Give initial balance to self.cashbox
        CashTransaction.objects.create(
            organization=self.org,
            cashbox=self.cashbox,
            transaction_type="kirim",
            payment_method="naqd",
            amount=Decimal("1000000.00"),
            date=datetime.date(2026, 7, 1),
            student=self.student,
            category_name="o'quvchi to'lov",
            comment="Initial balance"
        )

        # Create second cashbox
        target_cashbox = Cashbox.objects.create(
            organization=self.org,
            name="Plastik karta",
            balance=Decimal("0.00")
        )
        CashTransaction.objects.create(
            organization=self.org,
            cashbox=target_cashbox,
            transaction_type="kirim",
            payment_method="naqd",
            amount=Decimal("200000.00"),
            date=datetime.date(2026, 7, 1),
            student=self.student,
            category_name="o'quvchi to'lov",
            comment="Initial target balance"
        )

        url = reverse('transaction-transfer')
        data = {
            "from_cashbox": self.cashbox.id,
            "to_cashbox": target_cashbox.id,
            "amount": "300000.00",
            "izoh": "Plastikka o'tkazma"
        }

        response = self.client.post(url, data=data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn("kassalararo muvaffaqiyatli o'tkazildi", response.data["detail"])

        # Verify balances
        self.cashbox.refresh_from_db()
        target_cashbox.refresh_from_db()

        # self.cashbox: 1000000 - 300000 = 700000
        # target_cashbox: 200000 + 300000 = 500000
        self.assertEqual(self.cashbox.balance, Decimal("700000.00"))
        self.assertEqual(target_cashbox.balance, Decimal("500000.00"))

        # Verify CashTransactions created
        txs = CashTransaction.objects.filter(category_name="Kassalararo o'tkazma").order_by('id')
        self.assertEqual(txs.count(), 2)

        self.assertEqual(txs[0].cashbox, self.cashbox)
        self.assertEqual(txs[0].transaction_type, "chiqim")
        self.assertEqual(txs[0].amount, Decimal("300000.00"))
        self.assertEqual(txs[0].employee, self.admin)

        self.assertEqual(txs[1].cashbox, target_cashbox)
        self.assertEqual(txs[1].transaction_type, "kirim")
        self.assertEqual(txs[1].amount, Decimal("300000.00"))
        self.assertEqual(txs[1].employee, self.admin)

        # Verify general Transactions created
        from finance.models import Transaction
        gen_txs = Transaction.objects.filter(description__icontains="Kassalararo o'tkazma").order_by('id')
        self.assertEqual(gen_txs.count(), 2)

        self.assertEqual(gen_txs[0].cashbox, self.cashbox)
        self.assertEqual(gen_txs[0].type, "EXPENSE")
        self.assertEqual(gen_txs[0].amount, Decimal("300000.00"))
        self.assertEqual(gen_txs[0].employee, self.admin)

        self.assertEqual(gen_txs[1].cashbox, target_cashbox)
        self.assertEqual(gen_txs[1].type, "INCOME")
        self.assertEqual(gen_txs[1].amount, Decimal("300000.00"))
        self.assertEqual(gen_txs[1].employee, self.admin)


class AnalyticsEndpointsTests(APITestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="Analytics Org")
        self.admin = User.objects.create_user(
            username="+998901112255",
            password="securepassword",
            role="admin",
            organization=self.org
        )
        self.client.force_authenticate(user=self.admin)

    def test_branch_monitoring_report(self):
        url = reverse('branch-monitoring')
        response = self.client.get(f"{url}?date=2026-06-23")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_teacher_efficiency_report(self):
        url = reverse('teacher-efficiency-report')
        response = self.client.get(f"{url}?from_date=2026-06-01&to_date=2026-06-19")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_admin_efficiency_report(self):
        url = reverse('admin-efficiency-report')
        response = self.client.get(f"{url}?from_date=2026-06-01&to_date=2026-06-19")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_student_left_reasons_report(self):
        url = reverse('student-left-reasons-report')
        response = self.client.get(f"{url}?tab=all&from_date=2026-06-01&to_date=2026-06-20&time_resolution=kun")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_unsubmitted_attendance_report(self):
        url = reverse('unsubmitted-attendance')
        response = self.client.get(f"{url}?from_date=2026-06-01&to_date=2026-06-23")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_revenue_plan_report(self):
        url = reverse('report-revenue-plan')
        response = self.client.get(f"{url}?branch=1&date=2026-06-19&status=active")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_unpaid_payments_report(self):
        url = reverse('report-unpaid-payments')
        # Create student with negative balance
        student = Student.objects.create(
            organization=self.org,
            first_name="Bob",
            last_name="Smith",
            phone="+998901234599",
            balance=-120000.00
        )
        course = Course.objects.create(organization=self.org, name="Science", price=150000.00)
        group = Group.objects.create(organization=self.org, name="Science-1", course=course)
        StudentGroup.objects.create(organization=self.org, student=student, group=group)

        response = self.client.get(f"{url}?org_id={self.org.id}")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        table_data = response.data['table_data']
        self.assertTrue(any(row['name'] == "Bob Smith" and row['groups'] == "Science-1" for row in table_data))

    def test_cancelled_payments_report(self):
        url = reverse('report-cancelled-payments')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_discounts_bonuses_report(self):
        url = reverse('report-discounts-bonuses')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_cash_flow_report(self):
        url = reverse('report-cash-flow')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_employee_balance_report(self):
        url = reverse('report-employee-balance')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)


class FinanceSettingIntegrationTests(APITestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="Integration Test Org")
        self.manager = User.objects.create_user(
            username="+998901112277",
            password="securepassword",
            role="admin",
            is_staff=True,
            organization=self.org
        )
        self.client.force_authenticate(user=self.manager)
        
        from finance.models import Cashbox, FinanceSetting
        self.cashbox = Cashbox.objects.create(
            organization=self.org,
            name="Asosiy kassa",
            balance=0.00
        )
        
        self.setting = FinanceSetting.objects.create(
            organization=self.org,
            is_bonus_enabled=True,
            bonus_types=[
                {"id": 1, "name": "Buyurtma qo'shgani uchun bonus miqdori", "amount": "50000.00"},
                {"id": 2, "name": "Birinchi to'lovi uchun bonus miqdori", "amount": "30000.00"}
            ],
            is_penalty_enabled=True,
            penalty_types=[
                {"id": 1, "name": "To'lov qilmasdan ketgani uchun jarima", "amount": "15000.00"}
            ],
            is_percent_bonus_enabled=True,
            student_payment_percent="5.00",
            is_auto_discount_enabled=True,
            two_groups_discount_percent="10.00",
            three_groups_discount_percent="15.00",
            four_groups_discount_percent="20.00"
        )

    def test_lead_bonus_triggers(self):
        from crm.models import Lead
        from finance.models import Bonus, FinanceAction, Transaction

        # Create a lead
        Lead.objects.create(
            organization=self.org,
            name="Jane Doe",
            phone="+998905555555",
            created_by=self.manager
        )

        # Verify bonus creation
        bonus = Bonus.objects.filter(employee=self.manager).first()
        self.assertIsNotNone(bonus)
        self.assertEqual(bonus.amount, Decimal('50000.00'))

        # Verify FinanceAction
        action = FinanceAction.objects.filter(employee=self.manager, action_type='BONUS').first()
        self.assertIsNotNone(action)
        self.assertEqual(action.amount, Decimal('50000.00'))

        # Verify Transaction
        tx = Transaction.objects.filter(employee=self.manager, category='BONUS').first()
        self.assertIsNotNone(tx)
        self.assertEqual(tx.amount, Decimal('50000.00'))
        self.assertEqual(tx.type, 'EXPENSE')

    def test_first_payment_bonus_triggers(self):
        from academics.models import Student
        from finance.models import Payment, Bonus, FinanceAction, Transaction

        student = Student.objects.create(
            organization=self.org,
            first_name="Alice",
            phone="+998904444444",
            moderator=self.manager.id
        )

        # Create first payment
        Payment.objects.create(
            organization=self.org,
            student=student,
            amount=Decimal('100000.00'),
            date=timezone.now().date(),
            cashbox=self.cashbox,
            payment_method="Cash",
            employee=self.manager
        )

        # Moderator should get first payment bonus
        bonus = Bonus.objects.filter(employee=self.manager, reason__contains="Birinchi to'lov").first()
        self.assertIsNotNone(bonus)
        self.assertEqual(bonus.amount, Decimal('30000.00'))

    def test_finance_staff_payment_percent_bonus(self):
        from academics.models import Student
        from finance.models import Payment, Bonus

        student = Student.objects.create(
            organization=self.org,
            first_name="Bob",
            phone="+998903333333"
        )

        # Create payment
        Payment.objects.create(
            organization=self.org,
            student=student,
            amount=Decimal('200000.00'),
            date=timezone.now().date(),
            cashbox=self.cashbox,
            payment_method="Card",
            employee=self.manager
        )

        # Payment processor should get 5% bonus
        bonus = Bonus.objects.filter(employee=self.manager, reason__contains="Kirim to'lovi foiz bonusi").first()
        self.assertIsNotNone(bonus)
        # 5% of 200000 is 10000
        self.assertEqual(bonus.amount, Decimal('10000.00'))

    def test_student_leaving_unpaid_fine(self):
        from academics.models import Student, Group, Course, StudentGroupLeave
        from finance.models import Fine, FinanceAction

        course = Course.objects.create(
            organization=self.org,
            name="Physics",
            price=200000.00,
            duration_weeks=4
        )
        group = Group.objects.create(
            organization=self.org,
            name="Physics-1",
            course=course
        )
        student = Student.objects.create(
            organization=self.org,
            first_name="Charlie",
            phone="+998902222222",
            balance=Decimal('-1000.00'),  # negative balance
            moderator=self.manager.id
        )

        # Create leave record
        StudentGroupLeave.objects.create(
            organization=self.org,
            student=student,
            group=group,
            leave_date=timezone.now().date()
        )

        # Moderator should get penalty fine
        fine = Fine.objects.filter(employee=self.manager).first()
        self.assertIsNotNone(fine)
        self.assertEqual(fine.amount, Decimal('15000.00'))

        action = FinanceAction.objects.filter(employee=self.manager, action_type='PENALTY').first()
        self.assertIsNotNone(action)
        self.assertEqual(action.amount, Decimal('15000.00'))

    def test_auto_discount_applied_on_attendance(self):
        from academics.models import Student, Group, Course, StudentGroup, Attendance, charge_attendance
        from finance.models import Transaction

        course1 = Course.objects.create(organization=self.org, name="Bio", price=300000.00)
        course2 = Course.objects.create(organization=self.org, name="Chem", price=300000.00)
        
        group1 = Group.objects.create(organization=self.org, name="Bio-1", course=course1)
        group2 = Group.objects.create(organization=self.org, name="Chem-1", course=course2)

        student = Student.objects.create(
            organization=self.org,
            first_name="Diana",
            phone="+998901111111"
        )

        # Enroll in 2 groups
        StudentGroup.objects.create(organization=self.org, student=student, group=group1)
        StudentGroup.objects.create(organization=self.org, student=student, group=group2)

        # Charge attendance for group1 (monthly price: 300,000 UZS)
        # Lessons count in month
        from academics.models import get_lessons_in_month
        test_date = timezone.now().date()
        lessons_in_month = get_lessons_in_month(group1, test_date.year, test_date.month)
        expected_amount = round(Decimal('270000.00') / Decimal(lessons_in_month), 2)
        
        attendance = Attendance.objects.create(
            organization=self.org,
            group=group1,
            student=student,
            date=test_date,
            status="present"
        )
        
        charge_attendance(student, group1, test_date, attendance.id, self.org)
        
        # Verify transaction created with expected discounted amount
        tx = Transaction.objects.filter(student=student, description__contains="Davomat").first()
        self.assertIsNotNone(tx)
        self.assertEqual(float(tx.amount), float(expected_amount))

    def test_teacher_salary_percentage_fallback(self):
        from finance.models import StaffSalaryPercent, TeacherSalaryCalculation
        
        # Create StaffSalaryPercent
        percent_setting = StaffSalaryPercent.objects.create(
            organization=self.org,
            name="Senior Teacher",
            percent=Decimal('45.00')
        )
        
        # Create a teacher and link to percent_setting
        teacher = User.objects.create_user(
            username="+998901112288",
            password="securepassword",
            role="teacher",
            salary_percentage=percent_setting,
            organization=self.org
        )
        
        # We need to compute their salary. They have no specific TeacherSalaryRule.
        from academics.models import Course, Group, Student, StudentGroup, Attendance, charge_attendance
        course = Course.objects.create(organization=self.org, name="Math", price=200000.00)
        group = Group.objects.create(organization=self.org, name="Math-1", course=course, teacher=teacher)
        student = Student.objects.create(organization=self.org, first_name="Eve", phone="+998901234567")
        StudentGroup.objects.create(organization=self.org, student=student, group=group)
        
        from datetime import date
        att = Attendance.objects.create(
            organization=self.org,
            group=group,
            student=student,
            date=date(2026, 7, 15),
            status="present"
        )
        charge_attendance(student, group, date(2026, 7, 15), att.id, self.org)
        
        # Calculate salary
        url = reverse('teacher-salary-calculate')
        data = {
            "period": "2026-07",
            "org_id": self.org.id
        }
        
        response = self.client.post(f"{url}?org_id={self.org.id}", data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        
        # Verify calculated salary is calculated strictly from attendance charges
        calc = TeacherSalaryCalculation.objects.get(teacher=teacher, period='2026-07')
        self.assertTrue(calc.calculated_amount > Decimal('0.00'))

    def test_finance_setting_sync_to_actions(self):
        from finance.models import FinanceAction
        
        # Verify they are synced as FinanceAction
        bonuses = FinanceAction.objects.filter(
            organization=self.org,
            action_type='BONUS',
            student__isnull=True,
            employee__isnull=True
        )
        self.assertEqual(bonuses.count(), 2)
        for b in bonuses:
            self.assertEqual(b.target_type, 'EMPLOYEE')  # default empty role is EMPLOYEE
        
        penalties = FinanceAction.objects.filter(
            organization=self.org,
            action_type='PENALTY',
            student__isnull=True,
            employee__isnull=True
        )
        self.assertEqual(penalties.count(), 1)
        self.assertEqual(penalties.first().target_type, 'EMPLOYEE')
        
        # Modify settings to remove one bonus, add a student bonus, and add a student penalty
        self.setting.bonus_types = [
            {"id": 1, "name": "Buyurtma qo'shgani uchun bonus miqdori", "amount": "60000.00"},
            {"id": 3, "name": "Talaba faollik bonusi", "amount": "10000.00", "role": "student"}
        ]
        self.setting.penalty_types = [
            {"id": 1, "name": "To'lov qilmasdan ketgani uchun jarima", "amount": "15000.00"},
            {"id": 2, "name": "Yangi jarima", "amount": "25000.00", "role": "student"}
        ]
        self.setting.save()
        
        # Verify sync updated the amount, deleted the removed bonus, and added the new penalty
        bonuses = FinanceAction.objects.filter(
            organization=self.org,
            action_type='BONUS',
            student__isnull=True,
            employee__isnull=True
        )
        self.assertEqual(bonuses.count(), 2)
        
        emp_bonus = bonuses.filter(reason="Buyurtma qo'shgani uchun bonus miqdori").first()
        self.assertIsNotNone(emp_bonus)
        self.assertEqual(emp_bonus.amount, Decimal('60000.00'))
        self.assertEqual(emp_bonus.target_type, 'EMPLOYEE')

        std_bonus = bonuses.filter(reason="Talaba faollik bonusi").first()
        self.assertIsNotNone(std_bonus)
        self.assertEqual(std_bonus.amount, Decimal('10000.00'))
        self.assertEqual(std_bonus.target_type, 'STUDENT')
        
        penalties = FinanceAction.objects.filter(
            organization=self.org,
            action_type='PENALTY',
            student__isnull=True,
            employee__isnull=True
        )
        self.assertEqual(penalties.count(), 2)
        
        emp_penalty = penalties.filter(reason="To'lov qilmasdan ketgani uchun jarima").first()
        self.assertIsNotNone(emp_penalty)
        self.assertEqual(emp_penalty.target_type, 'EMPLOYEE')

        std_penalty = penalties.filter(reason="Yangi jarima").first()
        self.assertIsNotNone(std_penalty)
        self.assertEqual(std_penalty.target_type, 'STUDENT')
        self.assertEqual(std_penalty.amount, Decimal('25000.00'))

    def test_finance_setting_specific_person_sync(self):
        from academics.models import Student, BalanceHistory
        from finance.models import FinanceAction, Transaction, Bonus, Fine
        
        # Create a test student and teacher
        student = Student.objects.create(
            organization=self.org,
            first_name="Ali",
            last_name="Valiyev",
            phone="+998901234567",
            balance=Decimal('100000.00')
        )
        
        teacher = User.objects.create_user(
            username="+998901112288",
            password="securepassword",
            role="teacher",
            organization=self.org
        )
        
        # Test 1: Add specific student bonus and teacher penalty via settings
        self.setting.bonus_types = [
            {
                "id": 1,
                "name": "Super Student Bonus",
                "amount": "25000.00",
                "role": "student",
                "student": student.id,
                "cashbox": self.cashbox.id,
                "description": "Faol qatnashgani uchun"
            }
        ]
        self.setting.penalty_types = [
            {
                "id": 1,
                "name": "Kechikish jarimasi",
                "amount": "15000.00",
                "role": "teacher",
                "employee": teacher.id,
                "description": "Darsga kech qoldi"
            }
        ]
        self.setting.save()
        
        # Verify student balance updated (+25,000 UZS)
        student.refresh_from_db()
        self.assertEqual(student.balance, Decimal('125000.00'))
        
        # Verify student BalanceHistory created
        self.assertTrue(BalanceHistory.objects.filter(student=student, amount=Decimal('25000.00')).exists())
        
        # Verify Transaction was created for the student bonus
        tx = Transaction.objects.filter(student_id=student.id, category='BONUS').first()
        self.assertIsNotNone(tx)
        self.assertEqual(tx.amount, Decimal('25000.00'))
        self.assertEqual(tx.cashbox, self.cashbox)
        self.assertEqual(tx.description, "Talaba uchun bonus: Super Student Bonus (Faol qatnashgani uchun)")
        
        # Verify Fine was created for the teacher penalty
        fine = Fine.objects.filter(employee_id=teacher.id).first()
        self.assertIsNotNone(fine)
        self.assertEqual(fine.amount, Decimal('15000.00'))
        self.assertEqual(fine.reason, "Kechikish jarimasi: Darsga kech qoldi")

        # Test 2: Modify the specific student bonus amount to 40,000 UZS
        self.setting.bonus_types[0]['amount'] = "40000.00"
        self.setting.save()
        
        # Verify student balance updated by the diff (+15,000 UZS)
        student.refresh_from_db()
        self.assertEqual(student.balance, Decimal('140000.00'))
        
        # Verify transaction updated
        tx.refresh_from_db()
        self.assertEqual(tx.amount, Decimal('40000.00'))
        
        # Test 3: Delete the student bonus from settings
        self.setting.bonus_types = []
        self.setting.save()
        
        # Verify student balance reverted (-40,000 UZS)
        student.refresh_from_db()
        self.assertEqual(student.balance, Decimal('100000.00'))
        
        # Verify Transaction was deleted
        self.assertFalse(Transaction.objects.filter(id=tx.id).exists())

    def test_debtor_payment_percent_bonus(self):
        from academics.models import Student
        from finance.models import Payment, Bonus

        # Set debtor percent to 8% in settings
        self.setting.debtor_balance_percent = Decimal('8.00')
        self.setting.save()

        # Create a debtor student (balance < 0)
        student = Student.objects.create(
            organization=self.org,
            first_name="Frank",
            phone="+998901234569",
            balance=Decimal('-500.00')
        )

        Payment.objects.create(
            organization=self.org,
            student=student,
            amount=Decimal('1000.00'),
            date=timezone.now().date(),
            cashbox=self.cashbox,
            payment_method="Cash",
            employee=self.manager
        )

        # 8% of 1000 is 80 UZS
        bonus = Bonus.objects.filter(employee=self.manager, reason__contains="qarzdorlik to'lovi").first()
        self.assertIsNotNone(bonus)
        self.assertEqual(bonus.amount, Decimal('80.00'))

    def test_employee_salary_calculation_with_all_settings(self):
        from finance.models import StaffSalaryPercent, Salary, Payment
        from academics.models import Student
        from datetime import date
        
        # Link manager to a salary percentage (e.g. 10%)
        percent_setting = StaffSalaryPercent.objects.create(
            organization=self.org,
            name="Manager level",
            percent=Decimal('10.00')
        )
        self.manager.salary_percentage = percent_setting
        self.manager.save()

        # Enable count bonus and KPI settings
        self.setting.is_count_bonus_enabled = True
        self.setting.has_money_students_amount = Decimal('12000.00')  # active student count bonus
        self.setting.debtor_students_amount = Decimal('8000.00')  # zero debtors bonus
        self.setting.kpi_settings = {
            "target_revenue": "100000.00",
            "kpi_bonus": "15000.00"
        }
        self.setting.save()

        # Process a payment by the manager (total payments = 200,000 UZS)
        student = Student.objects.create(organization=self.org, first_name="Grace", phone="+998908888888", balance=Decimal('0.00'))
        Payment.objects.create(
            organization=self.org,
            student=student,
            amount=Decimal('200000.00'),
            date=date(2026, 7, 15),
            cashbox=self.cashbox,
            employee=self.manager
        )

        # Calculate salary
        url = reverse('salary-calculate')
        data = {
            "period": "2026-07"
        }
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # Let's verify calculated salary:
        # Base salary (10% of 200,000) = 20,000 UZS
        # Active students (Grace balance >= 0, so count > 0) bonus = 12,000 UZS
        # Debtors (0 debtors) bonus = 8,000 UZS
        # KPI target revenue (payments 200,000 >= 100,000 target) bonus = 15,000 UZS
        # Expected base salary + bonuses = 20000 + 12000 + 8000 + 15000 = 55,000 UZS + bonuses
        
        salary_rec = Salary.objects.filter(employee=self.manager, date=date(2026, 7, 15)).first()
        self.assertIsNotNone(salary_rec)
        self.assertTrue(salary_rec.amount >= Decimal('55000.00'))

    def test_telegram_daily_report_generation(self):
        from academics.models import Student, BalanceHistory
        from academics.tasks import generate_daily_report_message
        from finance.models import Payment, Expense, Salary
        from datetime import date
        
        # Create some students
        s1 = Student.objects.create(
            organization=self.org,
            first_name="Vali",
            last_name="Aliyev",
            phone="+998901234568",
            balance=Decimal('-50000.00')
        )
        
        s2 = Student.objects.create(
            organization=self.org,
            first_name="Sami",
            last_name="Karimov",
            phone="+998901234569",
            balance=Decimal('20000.00')
        )
        
        report_date = date(2026, 7, 6)
        
        # Payments yesterday
        p1 = Payment.objects.create(
            organization=self.org,
            student=s2,
            amount=Decimal('150000.00'),
            date=report_date,
            cashbox=self.cashbox,
            employee=self.manager,
            payment_method="Naqd"
        )
        
        # Expense yesterday
        from finance.models import ExpenseCategory
        exp_category = ExpenseCategory.objects.create(
            organization=self.org,
            name="Office expenses"
        )
        Expense.objects.create(
            organization=self.org,
            category=exp_category,
            amount=Decimal('30000.00'),
            date=report_date,
            cashbox=self.cashbox,
            description="Office stationery"
        )
        
        # Debts issued yesterday
        BalanceHistory.objects.create(
            organization=self.org,
            student=s1,
            amount=Decimal('-50000.00'),
            transaction_type="Lesson charge"
        )
        BalanceHistory.objects.filter(student=s1).update(date=report_date)
        
        # Generate daily report message in UZ (default)
        report_msg_uz = generate_daily_report_message(self.org, report_date, lang='uz')
        self.assertIn("Kunlik hisobot", report_msg_uz)
        self.assertIn("150 000 UZS", report_msg_uz)
        self.assertIn("120 000 UZS", report_msg_uz)
        self.assertIn("Sotuvlar", report_msg_uz)
        self.assertIn("Mijozlar", report_msg_uz)
        self.assertIn("Qarzdorlik", report_msg_uz)
        self.assertIn("Yangi qarzdorlik: 50 000", report_msg_uz)

        # Generate in RU
        report_msg_ru = generate_daily_report_message(self.org, report_date, lang='ru')
        self.assertIn("Ежедневный отчет за 2026-07-06", report_msg_ru)
        self.assertIn("Выручка", report_msg_ru)
        self.assertIn("Чистая прибыль", report_msg_ru)
        self.assertIn("Клиенты", report_msg_ru)
        self.assertIn("Долги", report_msg_ru)
        self.assertIn("Выдано долгов: 50 000", report_msg_ru)

    def test_bonus_and_fine_filters(self):
        from finance.models import Bonus, Fine
        from datetime import date
        
        # Authenticate
        self.client.force_authenticate(user=self.manager)
        
        # Create some bonuses
        b1 = Bonus.objects.create(
            organization=self.org,
            employee=self.manager,
            amount=Decimal('10000.00'),
            date=date(2026, 7, 1),
            reason="Good job"
        )
        b2 = Bonus.objects.create(
            organization=self.org,
            employee=self.manager,
            amount=Decimal('15000.00'),
            date=date(2026, 7, 5),
            reason="Excellent effort"
        )
        
        # Test filtering by employee
        response = self.client.get('/api/v1/finance/bonuses/', {'employee': self.manager.id})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data['results']), 2)
        
        # Test filtering by date range (gte / lte)
        response = self.client.get('/api/v1/finance/bonuses/', {
            'date__gte': '2026-07-02',
            'date__lte': '2026-07-06'
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data['results']), 1)
        self.assertEqual(response.data['results'][0]['id'], b2.id)
        
        # Test searching
        response = self.client.get('/api/v1/finance/bonuses/', {'search': 'excellent'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data['results']), 1)
        self.assertEqual(response.data['results'][0]['id'], b2.id)

    def test_payment_serializer_student_mapping(self):
        """
        Verify that PaymentSerializer resolves student_id or student nested dict correctly.
        """
        from finance.serializers import PaymentSerializer
        from finance.models import Cashbox
        from academics.models import Student
        student = Student.objects.create(organization=self.org, first_name="Ali", last_name="Valiyev", phone="+998909876543")
        cashbox = Cashbox.objects.create(organization=self.org, name="Kassa")
        
        # 1. Test student_id
        data1 = {
            "student_id": student.id,
            "amount": "100000.00",
            "date": "2026-07-13",
            "cashbox": cashbox.id,
            "payment_method": "naqd",
            "comment": "Test payment 1"
        }
        serializer1 = PaymentSerializer(data=data1)
        self.assertTrue(serializer1.is_valid(), serializer1.errors)
        payment1 = serializer1.save(organization=self.org)
        self.assertEqual(payment1.student_id, student.id)
        self.assertEqual(serializer1.data['student_name'], f"{student.first_name} {student.last_name}")

        # 2. Test student nested dict
        data2 = {
            "student": {"id": student.id},
            "amount": "50000.00",
            "date": "2026-07-13",
            "cashbox": cashbox.id,
            "payment_method": "click",
            "comment": "Test payment 2"
        }
        serializer2 = PaymentSerializer(data=data2)
        self.assertTrue(serializer2.is_valid(), serializer2.errors)
        payment2 = serializer2.save(organization=self.org)
        self.assertEqual(payment2.student_id, student.id)


from unittest.mock import patch


class PaymentReportBotNotificationTests(APITestCase):
    def setUp(self):
        from organizations.models import Organization
        from accounts.models import User
        from finance.models import Cashbox
        from academics.models import Student

        self.org = Organization.objects.create(name="Smart Academy")
        self.owner = User.objects.create_user(
            username="owner_user",
            role="owner",
            organization=self.org,
            telegram_chat_id="999888777"
        )
        self.cashbox = Cashbox.objects.create(
            name="Asosiy Kassa",
            organization=self.org
        )
        self.student = Student.objects.create(
            organization=self.org,
            first_name="Temur",
            last_name="Bekmurodov",
            phone="+998901112233"
        )

    @patch('academics.telegram_bot.send_telegram_message')
    def test_payment_sent_to_report_bot_on_save(self, mock_send):
        mock_send.return_value = True
        from finance.models import Payment
        from datetime import date
        from decimal import Decimal

        payment = Payment(
            organization=self.org,
            student=self.student,
            amount=Decimal("500000.00"),
            date=date.today(),
            cashbox=self.cashbox,
            payment_method="Naqd",
            employee=self.owner,
            comment="1-oylik to'lov"
        )
        payment.save()

        self.assertIsNotNone(payment.id)
        mock_send.assert_called()

        call_args = mock_send.call_args[0]
        chat_id = call_args[1]
        text = call_args[2]

        self.assertEqual(chat_id, "999888777")
        self.assertIn("YANGI TO'LOV QABUL QILINDI", text)
        self.assertIn("Temur Bekmurodov", text)
        self.assertIn("500 000 UZS", text)
        self.assertIn("Asosiy Kassa", text)
        self.assertIn("1-oylik to'lov", text)


class TeacherHourlyWorkLogTests(APITestCase):
    def setUp(self):
        from organizations.models import Organization, Branch
        from accounts.models import User
        from finance.models import TeacherWorkLog, Cashbox

        self.org = Organization.objects.create(
            name="Test Edu Org",
            role_permissions={
                "manager": {
                    "pages": {
                        "Ish haqi": {
                            "view": True,
                            "create": True,
                            "edit": True,
                            "delete": True
                        }
                    }
                }
            }
        )
        self.branch1 = Branch.objects.create(organization=self.org, name="Chilonzor")
        self.branch2 = Branch.objects.create(organization=self.org, name="Yunusobod")

        self.owner = User.objects.create_user(
            username="owner_user",
            phone="+998901112233",
            role="owner",
            organization=self.org
        )

        self.manager1 = User.objects.create_user(
            username="manager1_user",
            phone="+998902223344",
            role="manager",
            organization=self.org,
            branch=self.branch1
        )
        self.manager1.branches.add(self.branch1)

        # Teacher 1: Soatbay (Hourly 50,000 UZS)
        self.teacher1 = User.objects.create_user(
            username="teacher1_user",
            phone="+998903334455",
            role="teacher",
            organization=self.org,
            branch=self.branch1,
            salary_type="hourly",
            hourly_rate=Decimal("50000.00")
        )
        self.teacher1.branches.add(self.branch1)

        # Teacher 2: Soatbay (Hourly 60,000 UZS)
        self.teacher2 = User.objects.create_user(
            username="teacher2_user",
            phone="+998904445566",
            role="teacher",
            organization=self.org,
            branch=self.branch1,
            salary_type="hourly",
            hourly_rate=Decimal("60000.00")
        )
        self.teacher2.branches.add(self.branch1)

        self.cashbox1 = Cashbox.objects.create(
            organization=self.org,
            branch=self.branch1,
            name="Chilonzor Kassa",
            balance=Decimal("10000000.00")
        )

    def test_hourly_teacher_validation(self):
        from accounts.models import User
        from django.core.exceptions import ValidationError

        # Invalid: hourly with 0 rate
        user_invalid = User(
            username="test_bad_hourly",
            phone="+998905556677",
            role="teacher",
            organization=self.org,
            salary_type="hourly",
            hourly_rate=Decimal("0.00")
        )
        with self.assertRaises(ValidationError):
            user_invalid.clean()

    def test_daily_work_log_creation(self):
        from finance.models import TeacherWorkLog
        from datetime import date

        self.client.force_authenticate(user=self.manager1)
        url = "/api/v1/finance/teacher-work-logs/"
        data = {
            "date": "2026-09-08",
            "teacher": self.teacher1.id,
            "hours": "6.00",
            "hourly_rate": "50000.00",
            "note": "Kunda 6 soat dars o'tdi"
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Decimal(str(response.data['total_amount'])), Decimal("300000.00"))
        self.assertEqual(response.data['branch'], self.branch1.id)

    def test_quick_substitution_scenario(self):
        """
        O'qituvchi 1 (50,000 stavka) 6 soatdan 4 soatini o'tdi,
        Qolgan 2 soatini O'qituvchi 2 (60,000 stavka) zamen o'tdi.
        """
        from finance.models import TeacherWorkLog

        self.client.force_authenticate(user=self.manager1)
        url = "/api/v1/finance/teacher-work-logs/quick-substitution/"
        payload = {
            "date": "2026-09-08",
            "original_teacher_id": self.teacher1.id,
            "original_hours": "4.00",
            "original_hourly_rate": "50000.00",
            "substitute_teacher_id": self.teacher2.id,
            "substitute_hours": "2.00",
            "substitute_hourly_rate": "60000.00",
            "reason": "O'qituvchi 1 ning zarur ishi chiqib ketgani sababli",
            "note": "6 soatlik dars taqsimoti"
        }
        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # 1-o'qituvchi logini tekshiramiz: 4 soat * 50,000 = 200,000
        orig_data = response.data['original_teacher_log']
        self.assertEqual(Decimal(str(orig_data['hours'])), Decimal("4.00"))
        self.assertEqual(Decimal(str(orig_data['total_amount'])), Decimal("200000.00"))
        self.assertFalse(orig_data['is_substitution'])

        # 2-o'qituvchi (zamen) logini tekshiramiz: 2 soat * 60,000 = 120,000
        sub_data = response.data['substitute_teacher_log']
        self.assertEqual(Decimal(str(sub_data['hours'])), Decimal("2.00"))
        self.assertEqual(Decimal(str(sub_data['total_amount'])), Decimal("120000.00"))
        self.assertTrue(sub_data['is_substitution'])
        self.assertEqual(sub_data['original_teacher'], self.teacher1.id)

    def test_monthly_salary_calculate_with_work_logs(self):
        """
        Oylik hisoblashda work loglar asosida to'liq hisob-kitobni tekshiramiz:
        Teacher 1: 6 soat (300,000) + 4 soat (200,000) = 500,000 UZS.
        Teacher 2: 2 soat zamen (120,000) = 120,000 UZS.
        """
        from finance.models import TeacherWorkLog, TeacherSalaryCalculation

        # Teacher 1 ga 1-kun 6 soat dars
        TeacherWorkLog.objects.create(
            organization=self.org,
            branch=self.branch1,
            date="2026-09-01",
            teacher=self.teacher1,
            hours=Decimal("6.00"),
            hourly_rate=Decimal("50000.00"),
            is_substitution=False
        )

        # Teacher 1 ga 2-kun 4 soat dars
        TeacherWorkLog.objects.create(
            organization=self.org,
            branch=self.branch1,
            date="2026-09-02",
            teacher=self.teacher1,
            hours=Decimal("4.00"),
            hourly_rate=Decimal("50000.00"),
            is_substitution=False
        )

        # Teacher 2 ga 2-kun 2 soat zamen dars
        TeacherWorkLog.objects.create(
            organization=self.org,
            branch=self.branch1,
            date="2026-09-02",
            teacher=self.teacher2,
            hours=Decimal("2.00"),
            hourly_rate=Decimal("60000.00"),
            is_substitution=True,
            original_teacher=self.teacher1
        )

        # Oylikni hisoblaymiz (Chilonzor filiali uchun)
        self.client.force_authenticate(user=self.manager1)
        url = f"/api/v1/finance/teacher-salary/calculate/?branch={self.branch1.id}"
        payload = {"period": "2026-09"}
        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # Teacher 1 calculation tekshiramiz
        calc1 = TeacherSalaryCalculation.objects.filter(
            organization=self.org,
            teacher=self.teacher1,
            period="2026-09",
            branch=self.branch1
        ).first()
        self.assertIsNotNone(calc1)
        self.assertEqual(calc1.calculated_amount, Decimal("500000.00"))
        self.assertEqual(calc1.details.get('hours_taught'), "10.00")
        self.assertEqual(calc1.details.get('regular_hours'), "10.00")
        self.assertEqual(calc1.details.get('substitution_hours'), "0.00")

        # Teacher 2 calculation tekshiramiz (Zamen uchun olgan oyligi)
        calc2 = TeacherSalaryCalculation.objects.filter(
            organization=self.org,
            teacher=self.teacher2,
            period="2026-09",
            branch=self.branch1
        ).first()
        self.assertIsNotNone(calc2)
        self.assertEqual(calc2.calculated_amount, Decimal("120000.00"))
        self.assertEqual(calc2.details.get('hours_taught'), "2.00")
        self.assertEqual(calc2.details.get('substitution_hours'), "2.00")

    def test_work_log_branch_isolation(self):
        from accounts.models import User
        from finance.models import TeacherWorkLog

        manager2 = User.objects.create_user(
            username="manager2_user",
            phone="+998909998877",
            role="manager",
            organization=self.org,
            branch=self.branch2
        )
        manager2.branches.add(self.branch2)

        # 1. Filial 1 uchun log yaratildi
        log1 = TeacherWorkLog.objects.create(
            organization=self.org,
            branch=self.branch1,
            date="2026-09-08",
            teacher=self.teacher1,
            hours=Decimal("4.00"),
            hourly_rate=Decimal("50000.00")
        )

        # 2. Manager 2 (Filial 2 rahbari) ro'yxatni ochganda Filial 1 logini ko'rmasligi kerak
        self.client.force_authenticate(user=manager2)
        response = self.client.get("/api/v1/finance/teacher-work-logs/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data.get('results', response.data)
        self.assertEqual(len(results), 0)

        # 3. Manager 2 Filial 1 ni so'rasa ham, unga faqat o'z filiali (0 ta yozuv) qaytadi, Filial 1 ko'rinmaydi
        res_other = self.client.get(f"/api/v1/finance/teacher-work-logs/?branch={self.branch1.id}")
        self.assertEqual(res_other.status_code, status.HTTP_200_OK)
        results_other = res_other.data.get('results', res_other.data)
        self.assertEqual(len(results_other), 0)

        # 4. Manager 2 yangi log yaratganda, u majburan o'z filialiga (Filial 2) saqlanadi
        create_res = self.client.post("/api/v1/finance/teacher-work-logs/", {
            "date": "2026-09-08",
            "teacher": self.teacher1.id,
            "branch": self.branch1.id,  # Filial 1 ni berishga ursa ham
            "hours": "2.00",
            "hourly_rate": "50000.00"
        })
        self.assertEqual(create_res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(create_res.data['branch'], self.branch2.id)  # Manager 2 filiali bo'lib tushadi

    def test_multi_branch_salary_calculation_isolation(self):
        """
        O'qituvchi bir nechta filialda dars o'tganda (masalan Filial 1 va Filial 2),
        har bir filial bo'yicha oylik hisoblanganda yozuvlar bir-birini ezib (overwrite) yubormasligi kerak.
        """
        from finance.models import TeacherWorkLog, TeacherSalaryCalculation

        self.teacher1.branches.add(self.branch2)

        # Filial 1 uchun 10 soat dars (500,000 UZS)
        TeacherWorkLog.objects.create(
            organization=self.org,
            branch=self.branch1,
            date="2026-09-05",
            teacher=self.teacher1,
            hours=Decimal("10.00"),
            hourly_rate=Decimal("50000.00")
        )

        # Filial 2 uchun 6 soat dars (300,000 UZS)
        TeacherWorkLog.objects.create(
            organization=self.org,
            branch=self.branch2,
            date="2026-09-06",
            teacher=self.teacher1,
            hours=Decimal("6.00"),
            hourly_rate=Decimal("50000.00")
        )

        # 1. Filial 1 bo'yicha oylik hisoblash (Manager 1)
        self.client.force_authenticate(user=self.manager1)
        res1 = self.client.post(
            f"/api/v1/finance/teacher-salary/calculate/?branch={self.branch1.id}",
            {"period": "2026-09"},
            format='json'
        )
        self.assertEqual(res1.status_code, status.HTTP_201_CREATED)

        # 2. Filial 2 bo'yicha oylik hisoblash (Manager 2 yoki Owner)
        from accounts.models import User
        manager2 = User.objects.filter(username="manager2_user").first()
        if not manager2:
            manager2 = User.objects.create_user(
                username="manager2_salary_calc",
                phone="+998909871122",
                role="manager",
                organization=self.org,
                branch=self.branch2
            )
            manager2.branches.add(self.branch2)
        self.client.force_authenticate(user=manager2)
        res2 = self.client.post(
            f"/api/v1/finance/teacher-salary/calculate/?branch={self.branch2.id}",
            {"period": "2026-09"},
            format='json'
        )
        self.assertEqual(res2.status_code, status.HTTP_201_CREATED)

        # 3. Har ikkala hisob-kitob alohida saqlanganini tekshiramiz
        calc_b1 = TeacherSalaryCalculation.objects.filter(
            organization=self.org,
            teacher=self.teacher1,
            period="2026-09",
            branch=self.branch1
        ).first()
        calc_b2 = TeacherSalaryCalculation.objects.filter(
            organization=self.org,
            teacher=self.teacher1,
            period="2026-09",
            branch=self.branch2
        ).first()

        self.assertIsNotNone(calc_b1, "Filial 1 hisob-kitobi mavjud bo'lishi kerak")
        self.assertIsNotNone(calc_b2, "Filial 2 hisob-kitobi mavjud bo'lishi kerak")
        self.assertEqual(calc_b1.calculated_amount, Decimal("500000.00"))
        self.assertEqual(calc_b2.calculated_amount, Decimal("300000.00"))

    def test_multi_branch_teacher_balance_and_payout(self):
        """
        O'qituvchining har bir filialdagi alohida balansi va yagona umumiy balansi
        hisob-kitobi hamda filial kassasidan to'lov qilingandagi o'zgarishini tekshirish.
        """
        from finance.models import TeacherWorkLog, TeacherSalaryCalculation, Cashbox
        from academics.models import TeacherSalaryPayment

        self.teacher1.branches.add(self.branch2)

        # Filial 1 hisoblangan: 500,000 UZS
        TeacherSalaryCalculation.objects.create(
            organization=self.org,
            branch=self.branch1,
            teacher=self.teacher1,
            period="2026-09",
            calculated_amount=Decimal("500000.00")
        )

        # Filial 2 hisoblangan: 300,000 UZS
        TeacherSalaryCalculation.objects.create(
            organization=self.org,
            branch=self.branch2,
            teacher=self.teacher1,
            period="2026-09",
            calculated_amount=Decimal("300000.00")
        )

        # Filial 1 kassasidan 200,000 UZS to'lov qilamiz
        TeacherSalaryPayment.objects.create(
            organization=self.org,
            branch=self.branch1,
            teacher=self.teacher1,
            period="2026-09",
            amount=Decimal("200000.00")
        )

        self.client.force_authenticate(user=self.manager1)

        # 1. Filial 1 rahbari ko'zi bilan teacher-balance endpointini tekshiramiz
        url_bal = f"/api/v1/finance/teacher-work-logs/teacher-balance/?teacher={self.teacher1.id}&branch={self.branch1.id}"
        res_bal = self.client.get(url_bal)
        self.assertEqual(res_bal.status_code, status.HTTP_200_OK)

        data = res_bal.data
        # Joriy filial (Chilonzor) balansi: 500,000 - 200,000 = 300,000 UZS
        self.assertEqual(Decimal(str(data['current_branch_balance'])), Decimal("300000.00"))
        # Barcha filiallar bo'yicha umumiy balans: 300,000 (Filial 1) + 300,000 (Filial 2) = 600,000 UZS
        self.assertEqual(Decimal(str(data['overall_balance'])), Decimal("600000.00"))
        self.assertEqual(data['current_branch_id'], self.branch1.id)

        # Filiallar ro'yxatini tekshiramiz
        branches_res = data['branches']
        b1_data = next((b for b in branches_res if b['branch_id'] == self.branch1.id), None)
        b2_data = next((b for b in branches_res if b['branch_id'] == self.branch2.id), None)
        self.assertIsNotNone(b1_data)
        self.assertIsNotNone(b2_data)
        self.assertEqual(Decimal(str(b1_data['balance'])), Decimal("300000.00"))
        self.assertEqual(Decimal(str(b1_data['paid_amount'])), Decimal("200000.00"))
        self.assertEqual(Decimal(str(b2_data['balance'])), Decimal("300000.00"))
        self.assertEqual(Decimal(str(b2_data['paid_amount'])), Decimal("0.00"))

        # 2. Kundalik dars kiritish oynasidagi o'qituvchilar ro'yxati (teachers endpoint)
        url_teachers = f"/api/v1/finance/teacher-work-logs/teachers/?branch={self.branch1.id}"
        res_t = self.client.get(url_teachers)
        self.assertEqual(res_t.status_code, status.HTTP_200_OK)
        t_entry = next((item for item in res_t.data if item['id'] == self.teacher1.id), None)
        self.assertIsNotNone(t_entry)
        self.assertEqual(Decimal(str(t_entry['current_branch_balance'])), Decimal("300000.00"))
        self.assertEqual(Decimal(str(t_entry['overall_balance'])), Decimal("600000.00"))
        self.assertIn("Chilonzor", t_entry['branches_summary'])


class BranchFinanceNetProfitTests(APITestCase):
    def setUp(self):
        from organizations.models import Organization, Branch
        from accounts.models import User
        from finance.models import Cashbox, ExpenseCategory
        from academics.models import Student

        self.org = Organization.objects.create(
            name="Net Profit Test Org",
            role_permissions={
                "manager": {
                    "pages": {
                        "Xarajatlar": {"view": True, "create": True, "edit": True, "delete": True},
                        "Kassa": {"view": True, "create": True, "edit": True, "delete": True},
                        "Hisobotlar": {"view": True, "create": True, "edit": True, "delete": True},
                    }
                }
            }
        )
        self.branch1 = Branch.objects.create(organization=self.org, name="Chilonzor")
        self.branch2 = Branch.objects.create(organization=self.org, name="Yunusobod")

        self.owner = User.objects.create_user(
            username="np_owner",
            phone="+998901110001",
            role="owner",
            organization=self.org
        )

        self.manager1 = User.objects.create_user(
            username="np_manager1",
            phone="+998901110002",
            role="manager",
            organization=self.org,
            branch=self.branch1
        )
        self.manager1.branches.add(self.branch1)

        self.manager2 = User.objects.create_user(
            username="np_manager2",
            phone="+998901110003",
            role="manager",
            organization=self.org,
            branch=self.branch2
        )
        self.manager2.branches.add(self.branch2)

        self.cashbox1 = Cashbox.objects.create(
            organization=self.org,
            branch=self.branch1,
            name="Chilonzor Kassa",
            balance=Decimal("2000000.00")
        )

        self.cashbox2 = Cashbox.objects.create(
            organization=self.org,
            branch=self.branch2,
            name="Yunusobod Kassa",
            balance=Decimal("5000000.00")
        )

        self.category = ExpenseCategory.objects.create(
            organization=self.org,
            name="Ijara"
        )

        self.student1 = Student.objects.create(
            organization=self.org,
            branch=self.branch1,
            first_name="Ali",
            phone="+998901234567"
        )
        self.student2 = Student.objects.create(
            organization=self.org,
            branch=self.branch2,
            first_name="Vali",
            phone="+998907654321"
        )

    def test_expense_insufficient_balance_blocked(self):
        """Kassa balansidan ortiqcha xarajat qilish 400 xatosi bilan to'xtatilishi kerak."""
        self.client.force_authenticate(user=self.manager1)
        data = {
            "category": self.category.id,
            "amount": "3000000.00",  # Kassa balansida bor-yo'g'i 2,000,000 UZS bor
            "cashbox": self.cashbox1.id,
            "date": "2026-09-08",
            "payment_method": "naqd",
            "description": "Katta xarajat"
        }
        response = self.client.post("/api/v1/finance/expenses/", data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        error_text = str(response.data).lower()
        self.assertTrue("yetarli emas" in error_text or "mablag" in error_text)

    def test_expense_branch_manager_isolation(self):
        """1-filial rahbari 2-filial kassasidan xarajat qila olmasligi kerak."""
        self.client.force_authenticate(user=self.manager1)
        data = {
            "category": self.category.id,
            "amount": "500000.00",
            "cashbox": self.cashbox2.id,  # 2-filial kassasi
            "date": "2026-09-08",
            "payment_method": "naqd",
            "description": "Begona filial kassasidan xarajat"
        }
        response = self.client.post("/api/v1/finance/expenses/", data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        error_text = str(response.data).lower()
        self.assertTrue("boshqa filial" in error_text or "kassa" in error_text or "huquq" in error_text)

    def test_expense_branch_attribution_and_cashbox_balance_deduction(self):
        """Xarajat to'g'ri filialga biriktirilishi, to'lov turi va kassa balansi aniq kamayishi kerak."""
        self.client.force_authenticate(user=self.manager1)
        data = {
            "category": self.category.id,
            "amount": "500000.00",
            "cashbox": self.cashbox1.id,
            "date": "2026-09-08",
            "payment_method": "plastik",
            "description": "Ofis mebellari"
        }
        response = self.client.post("/api/v1/finance/expenses/", data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['branch_id'], self.branch1.id)
        self.assertEqual(response.data['payment_method'], 'plastik')

        from finance.models import Expense, Transaction
        exp = Expense.objects.get(id=response.data['id'])
        self.assertEqual(exp.branch_id, self.branch1.id)
        self.assertEqual(exp.payment_method, 'plastik')

        tx = Transaction.objects.filter(source_expense=exp).first()
        self.assertIsNotNone(tx)
        self.assertEqual(tx.branch_id, self.branch1.id)
        self.assertEqual(tx.payment_method, 'plastik')

    def test_three_payment_methods_normalization(self):
        """3 xil to'lov turi (naqd, plastik, bank) to'g'ri normallashishi kerak."""
        from finance.models import normalize_payment_method
        self.assertEqual(normalize_payment_method("Cash"), "naqd")
        self.assertEqual(normalize_payment_method("card"), "plastik")
        self.assertEqual(normalize_payment_method("terminal"), "plastik")
        self.assertEqual(normalize_payment_method("click"), "plastik")
        self.assertEqual(normalize_payment_method("transfer"), "bank")
        self.assertEqual(normalize_payment_method("hisob"), "bank")
        self.assertEqual(normalize_payment_method("bank"), "bank")

    def test_pnl_per_branch_and_overall(self):
        """
        Filiallar bo'yicha sof foyda alohida hisoblanishi,
        har bir to'lov turi bo'yicha kirim/chiqim/sof foyda aniq ko'rinishi
        va Owner uchun umumiy + barcha filiallar alohida chiqishi kerak.
        """
        from finance.models import Payment, Expense
        today = timezone.now().date()

        # Filial 1:
        # Kirim: 7,000,000 (naqd) + 3,000,000 (plastik) = 10,000,000 UZS
        # Chiqim: 3,000,000 (naqd) + 1,000,000 (plastik) = 4,000,000 UZS
        # Sof Foyda (Net Profit): 6,000,000 UZS
        Payment.objects.create(
            organization=self.org,
            branch=self.branch1,
            student=self.student1,
            cashbox=self.cashbox1,
            amount=Decimal("7000000.00"),
            date=today,
            payment_method="naqd"
        )
        Payment.objects.create(
            organization=self.org,
            branch=self.branch1,
            student=self.student1,
            cashbox=self.cashbox1,
            amount=Decimal("3000000.00"),
            date=today,
            payment_method="plastik"
        )
        Expense.objects.create(
            organization=self.org,
            branch=self.branch1,
            category=self.category,
            cashbox=self.cashbox1,
            amount=Decimal("3000000.00"),
            date=today,
            payment_method="naqd",
            description="Chilonzor naqd xarajat"
        )
        Expense.objects.create(
            organization=self.org,
            branch=self.branch1,
            category=self.category,
            cashbox=self.cashbox1,
            amount=Decimal("1000000.00"),
            date=today,
            payment_method="plastik",
            description="Chilonzor plastik xarajat"
        )

        # Filial 2:
        # Kirim: 4,000,000 (naqd) + 2,000,000 (bank) = 6,000,000 UZS
        # Chiqim: 1,000,000 (naqd) + 1,000,000 (bank) = 2,000,000 UZS
        # Sof Foyda (Net Profit): 4,000,000 UZS
        Payment.objects.create(
            organization=self.org,
            branch=self.branch2,
            student=self.student2,
            cashbox=self.cashbox2,
            amount=Decimal("4000000.00"),
            date=today,
            payment_method="naqd"
        )
        Payment.objects.create(
            organization=self.org,
            branch=self.branch2,
            student=self.student2,
            cashbox=self.cashbox2,
            amount=Decimal("2000000.00"),
            date=today,
            payment_method="bank"
        )
        Expense.objects.create(
            organization=self.org,
            branch=self.branch2,
            category=self.category,
            cashbox=self.cashbox2,
            amount=Decimal("1000000.00"),
            date=today,
            payment_method="naqd",
            description="Yunusobod naqd xarajat"
        )
        Expense.objects.create(
            organization=self.org,
            branch=self.branch2,
            category=self.category,
            cashbox=self.cashbox2,
            amount=Decimal("1000000.00"),
            date=today,
            payment_method="bank",
            description="Yunusobod bank xarajat"
        )

        # 1. Filial 1 rahbari (Manager 1) PnL hisobotini olganda:
        self.client.force_authenticate(user=self.manager1)
        res_m1 = self.client.get("/api/v1/finance/reports/pnl/")
        self.assertEqual(res_m1.status_code, status.HTTP_200_OK)
        d1 = res_m1.data
        self.assertEqual(d1['branch_id'], self.branch1.id)
        self.assertEqual(Decimal(str(d1['total_income'])), Decimal("10000000.00"))
        self.assertEqual(Decimal(str(d1['total_expense'])), Decimal("4000000.00"))
        self.assertEqual(Decimal(str(d1['net_profit'])), Decimal("6000000.00"))
        self.assertEqual(Decimal(str(d1['sof_foyda'])), Decimal("6000000.00"))

        # To'lov turlari bo'yicha:
        self.assertEqual(Decimal(str(d1['by_payment_method']['naqd']['net_profit'])), Decimal("4000000.00"))
        self.assertEqual(Decimal(str(d1['by_payment_method']['plastik']['net_profit'])), Decimal("2000000.00"))
        self.assertEqual(Decimal(str(d1['by_payment_method']['bank']['net_profit'])), Decimal("0.00"))
        self.assertNotIn('branches', d1)

        # 2. Tashkilot rahbari (Owner) umumiy PnL hisobotini olganda:
        self.client.force_authenticate(user=self.owner)
        res_owner = self.client.get("/api/v1/finance/reports/pnl/")
        self.assertEqual(res_owner.status_code, status.HTTP_200_OK)
        d_all = res_owner.data

        # Umumiy ko'rsatkichlar:
        # Kirim: 10m + 6m = 16m UZS
        # Chiqim: 4m + 2m = 6m UZS
        # Sof Foyda: 16m - 6m = 10m UZS
        self.assertEqual(Decimal(str(d_all['total_income'])), Decimal("16000000.00"))
        self.assertEqual(Decimal(str(d_all['total_expense'])), Decimal("6000000.00"))
        self.assertEqual(Decimal(str(d_all['net_profit'])), Decimal("10000000.00"))
        self.assertEqual(Decimal(str(d_all['sof_foyda'])), Decimal("10000000.00"))

        # Umumiy to'lov turlari:
        self.assertEqual(Decimal(str(d_all['by_payment_method']['naqd']['net_profit'])), Decimal("7000000.00"))
        self.assertEqual(Decimal(str(d_all['by_payment_method']['plastik']['net_profit'])), Decimal("2000000.00"))
        self.assertEqual(Decimal(str(d_all['by_payment_method']['bank']['net_profit'])), Decimal("1000000.00"))

        # Filiallar ro'yxati chiqishi:
        self.assertIn('branches', d_all)
        self.assertEqual(len(d_all['branches']), 2)
        b1_rep = next(b for b in d_all['branches'] if b['branch_id'] == self.branch1.id)
        b2_rep = next(b for b in d_all['branches'] if b['branch_id'] == self.branch2.id)
        self.assertEqual(Decimal(str(b1_rep['net_profit'])), Decimal("6000000.00"))
        self.assertEqual(Decimal(str(b2_rep['net_profit'])), Decimal("4000000.00"))

        # 3. Owner aniq 2-filial bo'yicha so'raganda:
        res_b2 = self.client.get(f"/api/v1/finance/reports/pnl/?branch={self.branch2.id}")
        self.assertEqual(res_b2.status_code, status.HTTP_200_OK)
        d_b2 = res_b2.data
        self.assertEqual(d_b2['branch_id'], self.branch2.id)
        self.assertEqual(Decimal(str(d_b2['total_income'])), Decimal("6000000.00"))
        self.assertEqual(Decimal(str(d_b2['total_expense'])), Decimal("2000000.00"))
        self.assertEqual(Decimal(str(d_b2['net_profit'])), Decimal("4000000.00"))
        self.assertEqual(Decimal(str(d_b2['sof_foyda'])), Decimal("4000000.00"))












