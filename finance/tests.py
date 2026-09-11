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

    def test_cash_transaction_kirim_with_student(self):
        """
        Verify that student is allowed for Kassa kirim (INCOME).
        """
        url = reverse('transaction-create')
        data = {
            "cashbox": self.cashbox.id,
            "transaction_type": "kirim",
            "payment_method": "naqd",
            "amount": "150000.00",
            "date": "2026-07-01",
            "category_name": "Kurs to'lovi",
            "student": self.student.id,
            "description": "Student payment"
        }

        response = self.client.post(url, data=data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # Verify kassa balance
        self.cashbox.refresh_from_db()
        self.assertEqual(self.cashbox.balance, Decimal("150000.00"))

    def test_cash_transaction_chiqim_employee_required(self):
        """
        Verify that employee is required for chiqim (EXPENSE) if description/category contains employee keywords.
        """
        import datetime
        from finance.models import CashTransaction
        CashTransaction.objects.create(
            organization=self.org,
            cashbox=self.cashbox,
            transaction_type='kirim',
            payment_method='naqd',
            amount=Decimal("100000.00"),
            date=datetime.date(2026, 7, 1),
            category_name="Kassaga kirim"
        )

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

        # Verify kassa balance (100000 - 50000 = 50000)
        self.cashbox.refresh_from_db()
        self.assertEqual(self.cashbox.balance, Decimal("50000.00"))

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
        from finance.models import Payment, Bonus

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
        from academics.models import get_lessons_in_month
        now_d = timezone.now().date()
        lessons_count = get_lessons_in_month(group1, now_d.year, now_d.month)
        expected_cost = round(Decimal('270000.00') / Decimal(lessons_count), 2)
        
        attendance = Attendance.objects.create(
            organization=self.org,
            group=group1,
            student=student,
            date=now_d,
            status="present"
        )
        
        charge_attendance(student, group1, now_d, attendance.id, self.org)
        
        # Verify transaction created with expected discounted amount
        tx = Transaction.objects.filter(student=student, description__contains="Davomat").first()
        self.assertIsNotNone(tx)
        self.assertEqual(float(tx.amount), float(expected_cost))

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
        from finance.models import Transaction, Fine
        
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
        from finance.models import Payment, Expense
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
        Payment.objects.create(
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
        from finance.models import Bonus
        from datetime import date
        
        # Authenticate
        self.client.force_authenticate(user=self.manager)
        
        # Create some bonuses
        Bonus.objects.create(
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


class TeacherSalaryHelperUnitTests(APITestCase):
    """
    Unit tests for isolated teacher salary service functions.
    """
    def setUp(self):
        self.org = Organization.objects.create(name="Helper Test Org")
        self.teacher = User.objects.create_user(
            username="salary_teacher_helper",
            password="securepassword",
            role="teacher",
            organization=self.org
        )

    def test_calculate_fixed_salary_without_holidays(self):
        from finance.services.salary import calculate_fixed_salary
        amount, details = calculate_fixed_salary(Decimal('1000000.00'), holiday_days_count=0, last_day=30)
        self.assertEqual(amount, Decimal('1000000.00'))
        self.assertEqual(details, {})

    def test_calculate_fixed_salary_with_holidays(self):
        from finance.services.salary import calculate_fixed_salary
        amount, details = calculate_fixed_salary(Decimal('1000000.00'), holiday_days_count=3, last_day=30)
        # Expected: 1,000,000 * (1 - 3/30) = 900,000.00
        self.assertEqual(amount, Decimal('900000.00'))
        self.assertEqual(details['holiday_days_deducted'], 3)
        self.assertEqual(details['original_rate'], '1000000.00')

    def test_calculate_per_student_salary(self):
        from finance.services.salary import calculate_per_student_salary
        amount, details = calculate_per_student_salary(Decimal('50000.00'), student_count=10, holiday_days_count=0, last_day=30)
        self.assertEqual(amount, Decimal('500000.00'))
        self.assertEqual(details['student_count'], 10)

        # With holidays
        amount_h, details_h = calculate_per_student_salary(Decimal('50000.00'), student_count=10, holiday_days_count=3, last_day=30)
        self.assertEqual(amount_h, Decimal('450000.00'))
        self.assertEqual(details_h['holiday_days_deducted'], 3)

    def test_resolve_teacher_salary_rule(self):
        from finance.services.salary import resolve_teacher_salary_rule
        from finance.models import TeacherSalaryRule

        # 1. Fallback when no rule exists
        rule_type, rate = resolve_teacher_salary_rule(self.org.id, self.teacher, '2026-05', 2026, 5)
        self.assertEqual(rule_type, 'fixed')
        self.assertEqual(rate, Decimal('800.00'))

        # 2. Specific rule defined
        TeacherSalaryRule.objects.create(
            organization=self.org,
            teacher=self.teacher,
            rule_type='percentage',
            rate=Decimal('40.00'),
            period='2026-05',
            is_active=True
        )
        rule_type, rate = resolve_teacher_salary_rule(self.org.id, self.teacher, '2026-05', 2026, 5)
        self.assertEqual(rule_type, 'percentage')
        self.assertEqual(rate, Decimal('40.00'))







