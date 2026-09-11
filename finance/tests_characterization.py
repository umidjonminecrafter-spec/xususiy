import datetime
from decimal import Decimal
from django.urls import reverse
from django.utils import timezone
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from organizations.models import Organization, Subscription, Tariff
from academics.models import Student, TeacherSalaryPayment
from finance.models import (
    Cashbox, Payment, Expense, ExpenseCategory, Salary, Transaction, FinanceAction,
    Bonus, Fine, CashTransaction
)

User = get_user_model()


class FinancialCharacterizationProtectionTests(APITestCase):
    """
    Qat'iy himoya qatlami (Characterization & Regression Tests):
    Moliya hisob-kitoblari va asosiy endpoint'larning xatti-harakatini to'liq 'muzlatib' tekshiradi.
    """

    def setUp(self):
        self.org = Organization.objects.create(name="Golden Master Org")
        self.tariff = Tariff.objects.create(name="Standard", price=Decimal("100.00"), student_limit=0)
        self.sub = Subscription.objects.create(
            organization=self.org,
            tariff=self.tariff,
            start_date=timezone.now().date(),
            end_date=timezone.now().date() + datetime.timedelta(days=365),
            is_active=True
        )

        self.admin = User.objects.create_user(
            username="golden_admin",
            password="securepassword",
            role="admin",
            organization=self.org
        )

        self.teacher = User.objects.create_user(
            username="golden_teacher",
            password="securepassword",
            role="teacher",
            organization=self.org
        )

        self.cashbox = Cashbox.objects.create(
            organization=self.org,
            name="Asosiy Kassa",
            balance=Decimal("0.00")
        )

        self.secondary_cashbox = Cashbox.objects.create(
            organization=self.org,
            name="Bank Hisob",
            balance=Decimal("0.00")
        )

        self.expense_category = ExpenseCategory.objects.create(
            organization=self.org,
            name="Operatsion xarajatlar"
        )

        self.client.force_authenticate(user=self.admin)

    def test_finance_summary_report_endpoint(self):
        """
        /api/v1/finance/report/ endpointi bo'yicha kirim, chiqim va sof foyda hisobi.
        """
        student = Student.objects.create(organization=self.org, first_name="Ali", phone="+998901110011")
        Payment.objects.create(
            organization=self.org,
            student=student,
            amount=Decimal("500000.00"),
            date=timezone.now().date(),
            cashbox=self.cashbox,
            payment_method="naqd"
        )
        Expense.objects.create(
            organization=self.org,
            category=self.expense_category,
            amount=Decimal("200000.00"),
            date=timezone.now().date(),
            description="Ijara to'lovi"
        )

        url = reverse('finance-report')
        response = self.client.get(f"{url}?org_id={self.org.id}")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(Decimal(str(response.data['total_income'])), Decimal("500000.00"))
        self.assertEqual(Decimal(str(response.data['total_expense'])), Decimal("200000.00"))
        self.assertEqual(Decimal(str(response.data['net_profit'])), Decimal("300000.00"))

    def test_financial_reports_view_cards_and_charts(self):
        """
        /api/v1/finance/financial-reports/ endpointi bo'yicha Transaction va grafik agregatsiyasi.
        """
        Transaction.objects.create(
            organization=self.org,
            cashbox=self.cashbox,
            amount=Decimal("300000.00"),
            type="INCOME",
            category="EDUCATION",
            description="Ingliz tili kursi"
        )
        Transaction.objects.create(
            organization=self.org,
            cashbox=self.cashbox,
            amount=Decimal("100000.00"),
            type="EXPENSE",
            category="OTHER",
            description="Kantselyariya"
        )

        url = reverse('financial-reports')
        response = self.client.get(f"{url}?org_id={self.org.id}")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        cards = response.data['cards']
        self.assertEqual(cards['total_income'], 300000.0)
        self.assertEqual(cards['total_expense'], 100000.0)
        self.assertEqual(cards['balance'], 200000.0)
        self.assertEqual(cards['net_profit'], 200000.0)

        # Linear chart validation
        linear = response.data['linear_chart']
        self.assertTrue(len(linear['labels']) >= 1)
        self.assertIn(300000.0, linear['kirim_line'])
        self.assertIn(100000.0, linear['chiqim_line'])

        # Pie chart validation
        pie_kirim = response.data['pie_chart']['kirim']
        self.assertIn("Ingliz tili kursi", pie_kirim['labels'])

    def test_cash_flow_report_endpoint(self):
        """
        /api/v1/finance/reports/cash-flow/ pul oqimi va kategoriya taqsimoti hisobi.
        """
        Transaction.objects.create(
            organization=self.org,
            cashbox=self.cashbox,
            amount=Decimal("400000.00"),
            type="INCOME",
            description="Oylik to'lovlar"
        )
        Transaction.objects.create(
            organization=self.org,
            cashbox=self.cashbox,
            amount=Decimal("150000.00"),
            type="EXPENSE",
            description="Internet to'lovi"
        )

        url = reverse('report-cash-flow')
        response = self.client.get(f"{url}?org_id={self.org.id}")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['jami_kirim'], 400000.0)
        self.assertEqual(response.data['jami_chiqim'], 150000.0)
        self.assertEqual(response.data['sof_pul_oqimi'], 250000.0)
        self.assertEqual(response.data['net_profit'], 250000.0)

    def test_pnl_report_endpoint(self):
        """
        /api/v1/finance/reports/pnl/ (Profit and Loss) hisoboti endpointi.
        """
        student = Student.objects.create(organization=self.org, first_name="Jasur", phone="+998901110022")
        Payment.objects.create(
            organization=self.org,
            student=student,
            amount=Decimal("800000.00"),
            date=timezone.now().date(),
            cashbox=self.cashbox
        )
        Expense.objects.create(
            organization=self.org,
            category=self.expense_category,
            amount=Decimal("200000.00"),
            date=timezone.now().date(),
            description="Reklama xarajati"
        )
        TeacherSalaryPayment.objects.create(
            organization=self.org,
            teacher=self.teacher,
            amount=Decimal("300000.00"),
            period=timezone.now().strftime("%Y-%m"),
            paid_at=timezone.now()
        )

        url = reverse('pnl-report')
        response = self.client.get(f"{url}?org_id={self.org.id}")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['total_income'], 800000.0)
        self.assertEqual(response.data['expenses'], 200000.0)
        self.assertEqual(response.data['teacher_salaries'], 300000.0)
        self.assertEqual(response.data['total_expense'], 500000.0)
        self.assertEqual(response.data['net_profit'], 300000.0)
        self.assertEqual(response.data['sof_foyda'], 300000.0)

    def test_financial_analytics_endpoint(self):
        """
        /api/v1/finance/analytics/ kirim, chiqim, bonus, jarima turlari.
        """
        Transaction.objects.create(
            organization=self.org,
            cashbox=self.cashbox,
            amount=Decimal("120000.00"),
            type="INCOME",
            description="Test Kirim"
        )
        url = reverse('financial-analytics')

        # 1. Type: kirim
        res_kirim = self.client.get(f"{url}?type=kirim&org_id={self.org.id}")
        self.assertEqual(res_kirim.status_code, status.HTTP_200_OK)
        self.assertEqual(float(res_kirim.data['total_amount']), 120000.0)

        # 2. Type: bonus via FinanceAction
        FinanceAction.objects.create(
            organization=self.org,
            action_type="BONUS",
            amount=Decimal("50000.00"),
            reason="Yaxshi natija",
            employee=self.teacher,
            target_type="EMPLOYEE"
        )
        res_bonus = self.client.get(f"{url}?type=bonus&org_id={self.org.id}")
        self.assertEqual(res_bonus.status_code, status.HTTP_200_OK)
        self.assertEqual(float(res_bonus.data['total_amount']), 50000.0)

    def test_cashbox_transfer_endpoint(self):
        """
        /api/v1/finance/transactions/transfer/ kassalararo pul ko'chirish va balans sinxronizatsiyasi.
        """
        CashTransaction.objects.create(
            organization=self.org,
            cashbox=self.cashbox,
            transaction_type="kirim",
            payment_method="naqd",
            amount=Decimal("1000000.00"),
            date=timezone.now().date(),
            category_name="Boshlang'ich qoldiq"
        )
        CashTransaction.objects.create(
            organization=self.org,
            cashbox=self.secondary_cashbox,
            transaction_type="kirim",
            payment_method="naqd",
            amount=Decimal("500000.00"),
            date=timezone.now().date(),
            category_name="Boshlang'ich qoldiq"
        )

        from finance.views.base import sync_cashbox_balance
        sync_cashbox_balance(self.cashbox)
        sync_cashbox_balance(self.secondary_cashbox)

        url = reverse('transaction-transfer')
        data = {
            "from_cashbox": self.cashbox.id,
            "to_cashbox": self.secondary_cashbox.id,
            "amount": "200000.00",
            "izoh": "Bank hisobiga o'tkazma"
        }
        response = self.client.post(url, data=data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        self.cashbox.refresh_from_db()
        self.secondary_cashbox.refresh_from_db()
        self.assertEqual(self.cashbox.balance, Decimal("800000.00"))
        self.assertEqual(self.secondary_cashbox.balance, Decimal("700000.00"))

    def test_discounts_and_bonuses_report_endpoint(self):
        """
        /api/v1/finance/reports/discounts-bonuses/ chegirma va bonuslar hisoboti.
        """
        student = Student.objects.create(organization=self.org, first_name="Dilshod", phone="+998901110033")
        Transaction.objects.create(
            organization=self.org,
            cashbox=self.cashbox,
            student=student,
            amount=Decimal("50000.00"),
            category="VOUCHER",
            description="Chegirma 50000"
        )
        Transaction.objects.create(
            organization=self.org,
            cashbox=self.cashbox,
            student=student,
            amount=Decimal("20000.00"),
            category="BONUS",
            description="Bonus 20000"
        )

        url = reverse('report-discounts-bonuses')
        response = self.client.get(f"{url}?org_id={self.org.id}")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['total_discounts'], 50000.0)
        self.assertEqual(response.data['total_bonuses'], 20000.0)
        self.assertEqual(response.data['total_count'], 2)

    def test_employee_finance_balance_report_endpoint(self):
        """
        /api/v1/finance/reports/employee-balance/ xodimlar balansi va oyliklari hisoboti.
        """
        Salary.objects.create(
            organization=self.org,
            employee=self.teacher,
            amount=Decimal("1500000.00"),
            status="paid",
            date=timezone.now().date()
        )
        Bonus.objects.create(
            organization=self.org,
            employee=self.teacher,
            amount=Decimal("100000.00"),
            date=timezone.now().date(),
            reason="Yutuq"
        )
        Fine.objects.create(
            organization=self.org,
            employee=self.teacher,
            amount=Decimal("50000.00"),
            date=timezone.now().date(),
            reason="Kechikish"
        )

        url = reverse('report-employee-balance')
        response = self.client.get(f"{url}?org_id={self.org.id}")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        totals = response.data['totals']
        self.assertEqual(totals['salary'], 1500000.0)
        self.assertEqual(totals['bonus'], 100000.0)
        self.assertEqual(totals['penalty'], 50000.0)
