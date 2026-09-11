"""
Full End-to-End verification and data population script for Finance (Moliya) module.
Tests every flow, checks cashbox balance consistency, reports, and API responses.
"""
import os
import django
from decimal import Decimal

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.utils import timezone
from rest_framework.test import APIClient
from accounts.models import User
from organizations.models import Organization, Branch
from academics.models import Student, Course, Group, StudentGroup, Attendance
from finance.models import (
    Cashbox, CashTransaction, ExpenseCategory, ExpenseSubcategory,
    Expense, Payment, FinanceAction, StaffSalaryPercent,
    TeacherSalaryPayment, Bonus
)

print("=" * 70)
print("STARTING COMPLETE FINANCE END-TO-END VERIFICATION")
print("=" * 70)

# 1. Organization and Admin setup
org = Organization.objects.first()
if not org:
    org = Organization.objects.create(name="Smart Academy", phone="+998774578407")

branch = Branch.objects.filter(organization=org).first()
if not branch:
    branch = Branch.objects.create(organization=org, name="Chilonzor filiali")

admin_user = User.objects.filter(organization=org, phone="+998774578407").first()
if not admin_user:
    admin_user = User.objects.filter(organization=org).first()

print(f"✓ Organization: '{org.name}' (ID: {org.id})")
print(f"✓ Branch: '{branch.name}' (ID: {branch.id})")
print(f"✓ User: '{admin_user.username}' (Role: {admin_user.role})")

# Setup API Client
client = APIClient()
client.force_authenticate(user=admin_user)

# 2. Cashbox Setup & Verification
main_box, _ = Cashbox.objects.get_or_create(
    organization=org,
    name="Asosiy kassa",
    defaults={'branch': branch}
)
sub_box, _ = Cashbox.objects.get_or_create(
    organization=org,
    name="Filial Kassa (Kichik)",
    defaults={'branch': branch}
)

initial_main_bal = Decimal(str(main_box.balance))
initial_sub_bal = Decimal(str(sub_box.balance))
print(f"\n[1] Initial Cashboxes:")
print(f"    - '{main_box.name}': {initial_main_bal} UZS")
print(f"    - '{sub_box.name}': {sub_box.balance} UZS")

# 3. Direct Cash Inflow (CashTransaction kirim)
kirim_amount = Decimal('500000.00')
ct_kirim = CashTransaction.objects.create(
    organization=org,
    cashbox=main_box,
    amount=kirim_amount,
    transaction_type='kirim',
    payment_method='naqd',
    date=timezone.now().date(),
    employee=admin_user,
    category_name="Investitsiya / Kirim",
    comment="Kassa to'ldirish (Test Kirim)"
)
main_box.refresh_from_db()
print(f"\n[2] Direct Cash Inflow:")
print(f"    Added: +{kirim_amount} UZS")
print(f"    New balance: {main_box.balance} UZS")
assert main_box.balance == initial_main_bal + kirim_amount, "Cashbox balance mismatch after Kirim!"
print("    ✓ Cashbox balance increased correctly.")

# 4. Expense Creation
exp_cat, _ = ExpenseCategory.objects.get_or_create(organization=org, name="Ofis xarajatlari")
exp_sub, _ = ExpenseSubcategory.objects.get_or_create(organization=org, category=exp_cat, name="Kantselyariya")

expense_amount = Decimal('75000.00')
exp = Expense.objects.create(
    organization=org,
    branch=branch,
    category=exp_cat,
    subcategory=exp_sub,
    cashbox=main_box,
    amount=expense_amount,
    date=timezone.now().date(),
    description="Qog'oz va ruchkalar sotib olindi"
)
main_box.refresh_from_db()
print(f"\n[3] Expense Creation:")
print(f"    Deducted: -{expense_amount} UZS")
print(f"    New balance: {main_box.balance} UZS")
assert main_box.balance == initial_main_bal + kirim_amount - expense_amount, "Cashbox balance mismatch after Expense!"
print("    ✓ Cashbox balance decreased correctly.")

# 5. Cash Transfer Between Cashboxes
transfer_amount = Decimal('100000.00')
main_pre_transfer = Decimal(str(main_box.balance))
sub_pre_transfer = Decimal(str(sub_box.balance))

transfer_response = client.post('/api/v1/finance/transactions/transfer/', {
    'from_cashbox': main_box.id,
    'to_cashbox': sub_box.id,
    'amount': float(transfer_amount),
    'comment': "Filial kassasiga o'tkazma"
}, format='json')

assert transfer_response.status_code == 201, f"Transfer failed: {transfer_response.data}"
main_box.refresh_from_db()
sub_box.refresh_from_db()

print(f"\n[4] Cashbox Transfer:")
print(f"    Transferred: {transfer_amount} UZS from '{main_box.name}' to '{sub_box.name}'")
print(f"    From box balance: {main_box.balance} UZS (Expected: {main_pre_transfer - transfer_amount})")
print(f"    To box balance: {sub_box.balance} UZS (Expected: {sub_pre_transfer + transfer_amount})")
assert main_box.balance == main_pre_transfer - transfer_amount, "Source cashbox balance mismatch after transfer!"
assert sub_box.balance == sub_pre_transfer + transfer_amount, "Target cashbox balance mismatch after transfer!"
print("    ✓ Both cashbox balances transferred atomically.")

# 6. Student Payment & Isolation Check
student, _ = Student.objects.get_or_create(
    organization=org,
    phone="+998901234567",
    defaults={'first_name': "Dilshod", 'last_name': "Karimov", 'branch': branch, 'balance': Decimal('0.00')}
)
student_pre_bal = student.balance
main_pre_pay_bal = main_box.balance

pay_amount = Decimal('400000.00')
payment = Payment.objects.create(
    organization=org,
    branch=branch,
    student=student,
    amount=pay_amount,
    date=timezone.now().date(),
    payment_method='plastik',
    cashbox=main_box,
    comment="Oylik kurs to'lovi"
)
student.refresh_from_db()
main_box.refresh_from_db()

print(f"\n[5] Student Payment:")
print(f"    Payment amount: {pay_amount} UZS")
print(f"    Student balance: {student.balance} UZS (Expected: {student_pre_bal + pay_amount})")
print(f"    Cashbox balance: {main_box.balance} UZS (Expected: {main_pre_pay_bal} - UNCHANGED)")
assert student.balance == student_pre_bal + pay_amount, "Student balance was not credited!"
assert main_box.balance == main_pre_pay_bal, "CRITICAL ERROR: Student payment modified Cashbox balance!"
print("    ✓ Student balance credited and Cashbox balance remained strictly untouched!")

# Verify thermal receipt endpoint
receipt_resp = client.get(f'/api/v1/finance/payments/{payment.id}/receipt/')
assert receipt_resp.status_code == 200, f"Receipt endpoint failed with {receipt_resp.status_code}"
assert "Kvitansiya" in receipt_resp.content.decode('utf-8'), "Receipt HTML content invalid!"
print("    ✓ Thermal receipt generated successfully.")

# 7. Attendance Charging & Cashbox Isolation
course, _ = Course.objects.get_or_create(
    organization=org,
    name="Ingliz tili (IELTS)",
    defaults={'price': Decimal('300000.00')}
)
teacher, _ = User.objects.get_or_create(
    organization=org,
    username="+998909876543",
    defaults={'first_name': "Bobur", 'last_name': "Aliyev", 'role': 'teacher', 'phone': "+998909876543"}
)
group, _ = Group.objects.get_or_create(
    organization=org,
    name="IELTS-Morning-01",
    defaults={'course': course, 'teacher': teacher, 'branch': branch}
)
StudentGroup.objects.get_or_create(organization=org, student=student, group=group)

student_pre_att_bal = student.balance
main_pre_att_bal = main_box.balance

att = Attendance.objects.create(
    organization=org,
    group=group,
    student=student,
    date=timezone.now().date(),
    status="present"
)

student.refresh_from_db()
main_box.refresh_from_db()

print(f"\n[6] Attendance Billing:")
print(f"    Student balance before: {student_pre_att_bal} UZS, after: {student.balance} UZS")
print(f"    Cashbox balance before: {main_pre_att_bal} UZS, after: {main_box.balance} UZS")
assert student.balance < student_pre_att_bal, "Student balance did not decrease on attendance!"
assert main_box.balance == main_pre_att_bal, "CRITICAL ERROR: Attendance charge modified Cashbox balance!"
print("    ✓ Attendance billed from student balance; Cashbox balance strictly untouched.")

# 8. Teacher Salary Payout
salary_percent, _ = StaffSalaryPercent.objects.get_or_create(
    organization=org,
    name="Standard Teacher Percent",
    defaults={'percent': Decimal('50.00')}
)
teacher.salary_percentage = salary_percent
teacher.save()

payout_amount = Decimal('150000.00')
main_pre_payout = main_box.balance

tsp = TeacherSalaryPayment.objects.create(
    organization=org,
    teacher=teacher,
    amount=payout_amount,
    period=timezone.now().strftime('%Y-%m')
)
main_box.refresh_from_db()
print(f"\n[7] Teacher Salary Payout:")
print(f"    Payout: -{payout_amount} UZS")
print(f"    Cashbox balance: {main_box.balance} UZS (Expected: {main_pre_payout - payout_amount})")
assert main_box.balance == main_pre_payout - payout_amount, "Cashbox balance mismatch after teacher salary payout!"
print("    ✓ Teacher salary paid and deducted from Cashbox balance via Transaction mirror.")

# 9. FinanceAction: Employee Bonus
emp_bonus_amount = Decimal('50000.00')
main_pre_bonus = main_box.balance

fa_bonus = FinanceAction.objects.create(
    organization=org,
    action_type='BONUS',
    target_type='EMPLOYEE',
    employee=teacher,
    amount=emp_bonus_amount,
    reason="Yaxshi dars o'tgani uchun bonus"
)
main_box.refresh_from_db()
print(f"\n[8] FinanceAction (Employee Bonus):")
print(f"    Bonus: -{emp_bonus_amount} UZS")
print(f"    Cashbox balance: {main_box.balance} UZS (Expected: {main_pre_bonus - emp_bonus_amount})")
assert main_box.balance == main_pre_bonus - emp_bonus_amount, "Cashbox balance mismatch after employee bonus!"
bonus_rec = Bonus.objects.filter(organization=org, employee=teacher, amount=emp_bonus_amount).first()
assert bonus_rec is not None, "Bonus record was not created for employee!"
print("    ✓ Employee bonus created and deducted from Cashbox balance.")

# 10. FinanceAction: Student Penalty
stu_penalty_amount = Decimal('15000.00')
stu_pre_penalty = student.balance
main_pre_penalty = main_box.balance

fa_penalty = FinanceAction.objects.create(
    organization=org,
    action_type='PENALTY',
    target_type='STUDENT',
    student=student,
    amount=stu_penalty_amount,
    reason="Kitobni kechiktirgani uchun jarima"
)
student.refresh_from_db()
main_box.refresh_from_db()
print(f"\n[9] FinanceAction (Student Penalty):")
print(f"    Penalty: -{stu_penalty_amount} UZS")
print(f"    Student balance: {student.balance} UZS (Expected: {stu_pre_penalty - stu_penalty_amount})")
print(f"    Cashbox balance: {main_box.balance} UZS (Expected: {main_pre_penalty} - UNCHANGED)")
assert student.balance == stu_pre_penalty - stu_penalty_amount, "Student balance did not decrease on penalty!"
assert main_box.balance == main_pre_penalty, "Student penalty should not affect Cashbox balance!"
print("    ✓ Student penalty deducted from student balance; Cashbox untouched.")

# 11. Reports & Search Verification
print(f"\n[10] Financial Reports Verification:")

# TransactionViewSet with search query
tx_search_resp = client.get('/api/v1/finance/transactions/?search=Dilshod')
assert tx_search_resp.status_code == 200, f"Transaction search crashed with {tx_search_resp.status_code}: {tx_search_resp.data}"
print("    ✓ TransactionViewSet search by student name works without 500 error.")

# PnL Report
pnl_resp = client.get('/api/v1/finance/reports/pnl/')
assert pnl_resp.status_code == 200, f"PnL report failed with {pnl_resp.status_code}"
pnl_data = pnl_resp.data
print(f"    ✓ PnL Report: Total Income = {pnl_data.get('total_income')}, Total Expense = {pnl_data.get('total_expense')}, Net Profit = {pnl_data.get('net_profit')}")

# Finance Summary Report
fin_report_resp = client.get('/api/v1/finance/report/')
assert fin_report_resp.status_code == 200, f"Finance report failed with {fin_report_resp.status_code}"
print(f"    ✓ Finance Report: Income = {fin_report_resp.data.get('total_income')}, Expense = {fin_report_resp.data.get('total_expense')}, Profit = {fin_report_resp.data.get('net_profit')}")

# Cash Flow Report
cash_flow_resp = client.get('/api/v1/finance/reports/cash-flow/')
assert cash_flow_resp.status_code == 200, f"Cash flow report failed with {cash_flow_resp.status_code}"
print("    ✓ Cash Flow Report loaded successfully.")

# Employee Balance Report
emp_bal_resp = client.get('/api/v1/finance/reports/employee-balance/')
assert emp_bal_resp.status_code == 200, f"Employee balance report failed with {emp_bal_resp.status_code}"
assert len(emp_bal_resp.data.get('table_data', [])) > 0, "Employee balance report table is empty!"
print(f"    ✓ Employee Balance Report loaded with {len(emp_bal_resp.data['table_data'])} employee rows.")

# Revenue Plan Report
rev_plan_resp = client.get('/api/v1/finance/reports/revenue-plan/')
assert rev_plan_resp.status_code == 200, f"Revenue plan report failed with {rev_plan_resp.status_code}"
print("    ✓ Revenue Plan Report loaded successfully.")

# Student Debts Summary
stu_debts_resp = client.get('/api/v1/finance/student-debts/summary/')
assert stu_debts_resp.status_code == 200, f"Student debts summary failed with {stu_debts_resp.status_code}"
print(f"    ✓ Student Debts Summary: Total Debt = {stu_debts_resp.data.get('total_student_debts')}")

# Transaction Report (Table)
tx_report_resp = client.get('/api/v1/finance/transactions/report/')
assert tx_report_resp.status_code == 200, f"Transaction report failed with {tx_report_resp.status_code}"
print(f"    ✓ Transaction Table Report returned {len(tx_report_resp.data)} entries.")

print("\n" + "=" * 70)
print("ALL END-TO-END FINANCE CHECKS COMPLETED SUCCESSFULLY WITH 100% ACCURACY!")
print("=" * 70)
