from django.utils import timezone
import logging
from datetime import datetime, time
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db.models import Sum, Q

from finance.models import (
    Payment, Expense, Salary, Transaction, FinanceAction,
    Bonus, Fine, CashTransaction, TeacherSalaryCalculation
)
from finance.serializers import TeacherSalaryCalculationSerializer
from finance.filters import FinancialReportFilter
from academics.models import Student, TeacherSalaryPayment

logger = logging.getLogger(__name__)


def get_finance_summary(organization_id, branch_id=None):
    """
    Kompaniya yoki filial bo'yicha umumiy kirim, chiqim va sof foydani hisoblaydi.
    """
    if branch_id:
        payment_filter = Q(organization_id=organization_id, branch_id=branch_id)
        expense_filter = Q(organization_id=organization_id, branch_id=branch_id)
        payments_sum = Payment.objects.filter(payment_filter).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
        expenses_sum = Expense.objects.filter(expense_filter).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    else:
        payments_sum = Payment.objects.filter(organization_id=organization_id).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
        expenses_sum = Expense.objects.filter(organization_id=organization_id).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

    return {
        "total_income": payments_sum,
        "total_expense": expenses_sum,
        "net_profit": payments_sum - expenses_sum
    }


def get_advanced_payment_report(org_id=None, branch_id=None, start_date=None, end_date=None, cashbox_id=None, teacher_id=None, search_query=None):
    """
    To'lovlar uchun o'qituvchi, sana va kassa bo'yicha filtrlangan Payment queryset qaytaradi.
    """
    queryset = Payment.objects.all().select_related('student', 'cashbox', 'employee')
    if org_id and str(org_id).isdigit():
        queryset = queryset.filter(organization_id=int(org_id))
    elif org_id:
        queryset = queryset.filter(organization_id=org_id)

    if branch_id:
        if str(branch_id).isdigit():
            queryset = queryset.filter(branch_id=int(branch_id))
        else:
            queryset = queryset.filter(branch_id=branch_id)

    if start_date and end_date:
        queryset = queryset.filter(date__range=[start_date, end_date])
    elif start_date:
        queryset = queryset.filter(date__gte=start_date)
    elif end_date:
        queryset = queryset.filter(date__lte=end_date)

    if cashbox_id and str(cashbox_id).isdigit():
        queryset = queryset.filter(cashbox_id=int(cashbox_id))

    if teacher_id and str(teacher_id).isdigit():
        queryset = queryset.filter(student__student_groups__group__teacher_id=int(teacher_id)).distinct()

    if search_query:
        queryset = queryset.filter(
            Q(student__first_name__icontains=search_query) |
            Q(student__last_name__icontains=search_query) |
            Q(comment__icontains=search_query)
        )

    return queryset.order_by('-date', '-id')


def get_transaction_report(organization, branch_id=None, cashbox_id=None, payment_method=None, start_date=None, end_date=None, teacher_id=None):
    """
    Kassa operatsiyalari (CashTransaction) hisoboti querysetini qaytaradi.
    """
    queryset = CashTransaction.objects.filter(
        organization=organization
    ).select_related('student', 'cashbox', 'employee').order_by('-date', '-id')

    if branch_id:
        queryset = queryset.filter(cashbox__branch_id=branch_id)

    if cashbox_id:
        queryset = queryset.filter(cashbox_id=cashbox_id)

    if payment_method:
        queryset = queryset.filter(payment_method=payment_method.lower())

    if start_date and end_date:
        queryset = queryset.filter(date__range=[start_date, end_date])

    if teacher_id:
        queryset = queryset.filter(student__student_groups__group__teacher_id=teacher_id).distinct()

    return queryset


def get_financial_analytics(organization_id, branch_id=None, report_type='kirim', get_params=None):
    """
    Kirim, chiqim, bonus va jarimalar bo'yicha analitika ma'lumotlarini hisoblaydi.
    """
    get_params = get_params or {}
    report_type = (report_type or 'kirim').lower()

    tx_filters = Q(cashbox__organization_id=organization_id)
    if branch_id:
        tx_filters &= Q(cashbox__branch_id=branch_id)
    tx_queryset = Transaction.objects.filter(tx_filters)

    filtered_tx = FinancialReportFilter(get_params, queryset=tx_queryset).qs

    labels_data = {}
    total_sum = 0
    table_rows = []

    if report_type == 'kirim':
        queryset = filtered_tx.filter(type='INCOME')
        total_sum = queryset.aggregate(total=Sum('amount'))['total'] or 0
        for tx in queryset:
            desc = tx.description or "Boshqa kirimlar"
            labels_data[desc] = labels_data.get(desc, 0) + float(tx.amount)
            table_rows.append({"nomi": desc, "summa": float(tx.amount), "sana": tx.created_at})

    elif report_type == 'chiqim':
        queryset = filtered_tx.filter(type='EXPENSE')
        total_sum = queryset.aggregate(total=Sum('amount'))['total'] or 0
        for tx in queryset:
            desc = tx.description or "Boshqa chiqimlar"
            labels_data[desc] = labels_data.get(desc, 0) + float(tx.amount)
            table_rows.append({"nomi": desc, "summa": float(tx.amount), "sana": tx.created_at})

    elif report_type == 'bonus':
        actions = FinanceAction.objects.filter(action_type='BONUS')
        if hasattr(FinanceAction, 'organization_id'):
            actions = actions.filter(organization_id=organization_id)
        if branch_id:
            actions = actions.filter(branch_id=branch_id)

        if get_params.get('start_date'):
            actions = actions.filter(created_at__gte=get_params.get('start_date'))
        if get_params.get('end_date'):
            actions = actions.filter(created_at__lte=get_params.get('end_date'))

        total_sum = actions.aggregate(total=Sum('amount'))['total'] or 0
        for act in actions:
            name = f"{act.get_target_type_display()}: {act.employee or act.student}"
            labels_data[name] = labels_data.get(name, 0) + float(act.amount)
            table_rows.append({"nomi": f"{name} ({act.reason or ''})", "summa": float(act.amount), "sana": act.created_at})

    elif report_type == 'jarima':
        actions = FinanceAction.objects.filter(action_type='PENALTY')
        if hasattr(FinanceAction, 'organization_id'):
            actions = actions.filter(organization_id=organization_id)

        if get_params.get('start_date'):
            actions = actions.filter(created_at__gte=get_params.get('start_date'))
        if get_params.get('end_date'):
            actions = actions.filter(created_at__lte=get_params.get('end_date'))

        total_sum = actions.aggregate(total=Sum('amount'))['total'] or 0
        for act in actions:
            name = f"{act.get_target_type_display()}: {act.employee}"
            labels_data[name] = labels_data.get(name, 0) + float(act.amount)
            table_rows.append({"nomi": f"{name} - {act.reason or ''}", "summa": float(act.amount), "sana": act.created_at})

    return {
        "total_amount": total_sum,
        "chart_data": {
            "labels": list(labels_data.keys()),
            "values": list(labels_data.values())
        },
        "table_data": table_rows
    }


def get_financial_reports_data(org_id=None, branch_id=None, start_date_str=None, end_date_str=None, cashbox_id=None):
    """
    Asosiy moliyaviy hisobot: kartochkalar, chiziqli grafik va pie-chart agregatsiyasini hisoblaydi.
    """
    from common.utils import parse_flexible_date

    tx_filters = Q(organization_id=org_id) if org_id else Q()
    if branch_id and str(branch_id).lower() != 'all':
        tx_filters &= (Q(branch_id=branch_id) | Q(branch_id__isnull=True) | Q(cashbox__branch_id=branch_id))

    queryset = Transaction.objects.filter(tx_filters)

    start_date_iso = parse_flexible_date(start_date_str) if start_date_str else None
    end_date_iso = parse_flexible_date(end_date_str) if end_date_str else None

    if start_date_iso:
        try:
            start_d = datetime.strptime(start_date_iso, '%Y-%m-%d').date()
            start_dt = datetime.combine(start_d, time.min)
            start_dt = timezone.make_aware(start_dt) if timezone.is_naive(start_dt) else start_dt
            queryset = queryset.filter(created_at__gte=start_dt)
        except Exception:
            pass

    if end_date_iso:
        try:
            end_d = datetime.strptime(end_date_iso, '%Y-%m-%d').date()
            end_dt = datetime.combine(end_d, time.max)
            end_dt = timezone.make_aware(end_dt) if timezone.is_naive(end_dt) else end_dt
            queryset = queryset.filter(created_at__lte=end_dt)
        except Exception:
            pass

    if cashbox_id and str(cashbox_id).lower() != 'all':
        try:
            queryset = queryset.filter(cashbox_id=int(cashbox_id))
        except ValueError:
            pass

    total_income = queryset.filter(type='INCOME').aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    total_expense = queryset.filter(type='EXPENSE').aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

    income_breakdown = {}
    expense_breakdown = {}
    daily_data = {}

    if queryset.exists():
        for tx in queryset.order_by('created_at'):
            if not tx.created_at:
                continue
            date_key = tx.created_at.strftime('%d.%m')
            if date_key not in daily_data:
                daily_data[date_key] = {'kirim': 0, 'chiqim': 0}

            amt = float(tx.amount or 0)
            if tx.type == 'INCOME':
                daily_data[date_key]['kirim'] += amt
                desc = tx.description or "Boshqa kirimlar"
                income_breakdown[desc] = income_breakdown.get(desc, 0) + amt
            else:
                daily_data[date_key]['chiqim'] += amt
                desc = tx.description or "Boshqa chiqimlar"
                expense_breakdown[desc] = expense_breakdown.get(desc, 0) + amt
    else:
        # Fallback to model tables if transactions table does not yet have migrated records
        p_filter = Q(organization_id=org_id) if org_id else Q()
        e_filter = Q(organization_id=org_id) if org_id else Q()
        s_filter = Q(organization_id=org_id, status='paid') if org_id else Q(status='paid')
        t_filter = Q(organization_id=org_id) if org_id else Q()

        if branch_id and str(branch_id).lower() != 'all':
            p_filter &= (Q(branch_id=branch_id) | Q(branch_id__isnull=True))
            e_filter &= (Q(branch_id=branch_id) | Q(branch_id__isnull=True))
            s_filter &= (Q(branch_id=branch_id) | Q(branch_id__isnull=True))
            t_filter &= (Q(branch_id=branch_id) | Q(branch_id__isnull=True))

        if start_date_iso:
            p_filter &= Q(date__gte=start_date_iso)
            e_filter &= Q(date__gte=start_date_iso)
            s_filter &= Q(date__gte=start_date_iso)
            t_filter &= Q(paid_at__date__gte=start_date_iso)

        if end_date_iso:
            p_filter &= Q(date__lte=end_date_iso)
            e_filter &= Q(date__lte=end_date_iso)
            s_filter &= Q(date__lte=end_date_iso)
            t_filter &= Q(paid_at__date__lte=end_date_iso)

        payments = Payment.objects.filter(p_filter, amount__gt=0).order_by('date')
        for p in payments:
            d_key = p.date.strftime('%d.%m') if p.date else (p.created_at.strftime('%d.%m') if p.created_at else '01.01')
            if d_key not in daily_data:
                daily_data[d_key] = {'kirim': 0, 'chiqim': 0}
            amt = float(p.amount or 0)
            daily_data[d_key]['kirim'] += amt
            cat_name = p.payment_type or "Talaba to'lovi"
            income_breakdown[cat_name] = income_breakdown.get(cat_name, 0) + amt

        expenses = Expense.objects.filter(e_filter).order_by('date')
        for e in expenses:
            d_key = e.date.strftime('%d.%m') if e.date else (e.created_at.strftime('%d.%m') if e.created_at else '01.01')
            if d_key not in daily_data:
                daily_data[d_key] = {'kirim': 0, 'chiqim': 0}
            amt = float(e.amount or 0)
            daily_data[d_key]['chiqim'] += amt
            cat_name = e.category or "Xarajat"
            expense_breakdown[cat_name] = expense_breakdown.get(cat_name, 0) + amt

        salaries = Salary.objects.filter(s_filter).order_by('date')
        for s in salaries:
            d_key = s.date.strftime('%d.%m') if s.date else '01.01'
            if d_key not in daily_data:
                daily_data[d_key] = {'kirim': 0, 'chiqim': 0}
            amt = float(s.amount or 0)
            daily_data[d_key]['chiqim'] += amt
            expense_breakdown["Xodimlar maoshi"] = expense_breakdown.get("Xodimlar maoshi", 0) + amt

        tsalaries = TeacherSalaryPayment.objects.filter(t_filter).order_by('paid_at')
        for ts in tsalaries:
            d_key = ts.paid_at.strftime('%d.%m') if ts.paid_at else '01.01'
            if d_key not in daily_data:
                daily_data[d_key] = {'kirim': 0, 'chiqim': 0}
            amt = float(ts.amount or 0)
            daily_data[d_key]['chiqim'] += amt
            expense_breakdown["O'qituvchilar maoshi"] = expense_breakdown.get("O'qituvchilar maoshi", 0) + amt

        total_income = sum(Decimal(str(v['kirim'])) for v in daily_data.values())
        total_expense = sum(Decimal(str(v['chiqim'])) for v in daily_data.values())

    balance = total_income - total_expense

    return {
        "cards": {
            "total_income": float(total_income),
            "total_expense": float(total_expense),
            "balance": float(balance),
            "net_profit": float(balance)
        },
        "linear_chart": {
            "labels": list(daily_data.keys()),
            "datasets": [
                {
                    "label": "Kirim",
                    "data": [v['kirim'] for v in daily_data.values()],
                    "borderColor": "#10b981",
                    "backgroundColor": "rgba(16, 185, 129, 0.05)"
                },
                {
                    "label": "Chiqim",
                    "data": [v['chiqim'] for v in daily_data.values()],
                    "borderColor": "#ef4444",
                    "backgroundColor": "rgba(239, 68, 68, 0.05)"
                }
            ],
            "kirim_line": [v['kirim'] for v in daily_data.values()],
            "chiqim_line": [v['chiqim'] for v in daily_data.values()]
        },
        "pie_chart": {
            "kirim": {
                "labels": list(income_breakdown.keys()),
                "values": list(income_breakdown.values()),
                "datasets": [{
                    "data": list(income_breakdown.values()),
                    "backgroundColor": ["#10b981", "#059669", "#34d399", "#6ee7b7", "#0fb9b1"]
                }]
            },
            "chiqim": {
                "labels": list(expense_breakdown.keys()),
                "values": list(expense_breakdown.values()),
                "datasets": [{
                    "data": list(expense_breakdown.values()),
                    "backgroundColor": ["#ef4444", "#dc2626", "#f87171", "#fca5a5", "#ea580c"]
                }]
            }
        }
    }

def get_cash_flow_report_data(org_id=None, branch_id=None, from_date=None, to_date=None, cashbox_id=None):
    """
    Pul oqimi (Cash Flow) hisoboti ma'lumotlarini hisoblaydi.
    """
    tx_filters = Q(organization_id=org_id) if org_id else Q()
    if branch_id and str(branch_id).lower() != 'all':
        tx_filters &= (Q(branch_id=branch_id) | Q(cashbox__branch_id=branch_id))

    queryset = Transaction.objects.filter(tx_filters)

    if from_date:
        try:
            queryset = queryset.filter(created_at__gte=datetime.strptime(from_date, '%Y-%m-%d'))
        except ValueError:
            pass
    if to_date:
        try:
            queryset = queryset.filter(created_at__lte=datetime.combine(datetime.strptime(to_date, '%Y-%m-%d'), time.max))
        except ValueError:
            pass

    if cashbox_id:
        try:
            queryset = queryset.filter(cashbox_id=int(cashbox_id))
        except ValueError:
            pass

    incomes = list(queryset.filter(type='INCOME').values('description').annotate(total=Sum('amount')))
    expenses = list(queryset.filter(type='EXPENSE').values('description').annotate(total=Sum('amount')))

    total_income = sum(item['total'] for item in incomes) or Decimal('0.00')
    total_expense = sum(item['total'] for item in expenses) or Decimal('0.00')

    if total_income == 0 and total_expense == 0 and org_id:
        p_filter = Q(organization_id=org_id)
        e_filter = Q(organization_id=org_id)
        if branch_id and str(branch_id).lower() != 'all':
            p_filter &= (Q(branch_id=branch_id) | Q(branch__id=branch_id))
            e_filter &= (Q(branch_id=branch_id) | Q(branch__id=branch_id))
        if from_date:
            p_filter &= Q(date__gte=from_date)
            e_filter &= Q(date__gte=from_date)
        if to_date:
            p_filter &= Q(date__lte=to_date)
            e_filter &= Q(date__lte=to_date)

        total_income = Payment.objects.filter(p_filter, amount__gt=0).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
        total_expense = Expense.objects.filter(e_filter).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

        if total_income > 0:
            incomes = [{"description": "O'quvchilar to'lovi", "total": total_income}]
        if total_expense > 0:
            expenses = [{"description": "Boshqa xarajatlar", "total": total_expense}]

    return {
        "kirimlar": [
            {"kategoriya": item['description'] or "Boshqa kirim", "summa": float(item['total'])}
            for item in incomes
        ],
        "chiqimlar": [
            {"kategoriya": item['description'] or "Boshqa xarajat", "summa": float(item['total'])}
            for item in expenses
        ],
        "jami_kirim": float(total_income),
        "jami_chiqim": float(total_expense),
        "sof_pul_oqimi": float(total_income - total_expense),
        "net_profit": float(total_income - total_expense)
    }


def get_pnl_report_data(org_id=None, branch_id=None, from_date=None, to_date=None):
    """
    Foyda va Zarar (PnL) hisobotini hisoblaydi.
    """
    p_filter = Q(organization_id=org_id)
    if branch_id:
        p_filter &= (Q(branch_id=branch_id) | Q(branch__isnull=True))
    if from_date:
        p_filter &= Q(date__gte=from_date)
    if to_date:
        p_filter &= Q(date__lte=to_date)

    total_income = Payment.objects.filter(p_filter, amount__gt=0).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

    if total_income == 0 and org_id:
        tx_inc_filter = Q(organization_id=org_id, type='INCOME')
        if branch_id:
            tx_inc_filter &= (Q(branch_id=branch_id) | Q(branch_id__isnull=True))
        if from_date:
            tx_inc_filter &= Q(created_at__gte=from_date)
        if to_date:
            tx_inc_filter &= Q(created_at__lte=to_date)
        total_income = Transaction.objects.filter(tx_inc_filter).exclude(description__startswith='Davomat #').aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

    e_filter = Q(organization_id=org_id)
    t_filter = Q(organization_id=org_id)
    calc_filter = Q(organization_id=org_id)

    if branch_id:
        e_filter &= (Q(branch_id=branch_id) | Q(branch_id__isnull=True))
        t_filter &= (Q(branch_id=branch_id) | Q(branch_id__isnull=True))
        calc_filter &= (Q(branch_id=branch_id) | Q(branch_id__isnull=True))

    if from_date:
        e_filter &= Q(date__gte=from_date)
        t_filter &= Q(paid_at__date__gte=from_date)
        try:
            calc_filter &= Q(period__gte=from_date[:7])
        except Exception:
            pass
    if to_date:
        e_filter &= Q(date__lte=to_date)
        t_filter &= Q(paid_at__date__lte=to_date)
        try:
            calc_filter &= Q(period__lte=to_date[:7])
        except Exception:
            pass

    expenses_val = Expense.objects.filter(e_filter).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    tsalaries_val = TeacherSalaryPayment.objects.filter(t_filter).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

    teacher_accrued = Decimal('0.00')
    calcs = TeacherSalaryCalculation.objects.filter(calc_filter)
    for c in calcs:
        serializer = TeacherSalaryCalculationSerializer(c)
        teacher_accrued += Decimal(str(serializer.data.get('total_earned') or 0))

    teacher_expenses = max(tsalaries_val, teacher_accrued)
    total_expense = expenses_val + teacher_expenses
    net_profit = max(Decimal('0.00'), total_income - total_expense)

    # Payment methods breakdown
    naqd_inc = Payment.objects.filter(p_filter, amount__gt=0, payment_method__icontains='naqd').aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    naqd_exp = Expense.objects.filter(e_filter, payment_method__icontains='naqd').aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

    card_inc = Payment.objects.filter(p_filter, amount__gt=0).filter(
        Q(payment_method__icontains='plastik') | Q(payment_method__icontains='card') | Q(payment_method__icontains='terminal') | Q(payment_method__icontains='click') | Q(payment_method__icontains='payme') | Q(payment_method__icontains='uzum')
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    card_exp = Expense.objects.filter(e_filter).filter(
        Q(payment_method__icontains='plastik') | Q(payment_method__icontains='card') | Q(payment_method__icontains='terminal')
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

    bank_inc = Payment.objects.filter(p_filter, amount__gt=0).filter(
        Q(payment_method__icontains='bank') | Q(payment_method__icontains='hisob')
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    bank_exp = Expense.objects.filter(e_filter).filter(
        Q(payment_method__icontains='bank') | Q(payment_method__icontains='hisob')
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

    by_payment_method = {
        "naqd": {
            "income": float(naqd_inc),
            "expense": float(naqd_exp),
            "net_profit": float(naqd_inc - naqd_exp)
        },
        "plastik": {
            "income": float(card_inc),
            "expense": float(card_exp),
            "net_profit": float(card_inc - card_exp)
        },
        "bank": {
            "income": float(bank_inc),
            "expense": float(bank_exp),
            "net_profit": float(bank_inc - bank_exp)
        }
    }

    return {
        "total_income": float(total_income),
        "total_expense": float(total_expense),
        "expenses": float(expenses_val),
        "teacher_salaries": float(teacher_expenses),
        "net_profit": float(net_profit),
        "sof_foyda": float(net_profit),
        "by_payment_method": by_payment_method
    }


def get_employee_finance_balance_report(org_id, branch_id=None):
    """
    Xodimlarning oylik, bonus, jarima va avans balansi hisoboti.
    """
    User = get_user_model()
    employees_qs = User.objects.filter(organization_id=org_id).exclude(role='student').exclude(is_superuser=True)
    if branch_id and str(branch_id).lower() != "all":
        employees_qs = employees_qs.filter(Q(branch_id=branch_id) | Q(branch__isnull=True))

    rows = []
    total_salary = 0
    total_bonus = 0
    total_advance = 0
    total_penalty = 0

    for emp in employees_qs:
        salary_amount = Salary.objects.filter(employee=emp, status='paid').aggregate(total=Sum('amount'))['total'] or 0
        bonus_amount = Bonus.objects.filter(employee=emp).aggregate(total=Sum('amount'))['total'] or 0
        penalty_amount = Fine.objects.filter(employee=emp).aggregate(total=Sum('amount'))['total'] or 0

        advance_amount = Transaction.objects.filter(
            employee=emp, type='EXPENSE', category='SALARY'
        ).aggregate(total=Sum('amount'))['total'] or 0

        # Teacher salary payments fallback
        if salary_amount == 0 and getattr(emp, 'role', '') == 'teacher':
            from finance.models import TeacherSalaryPayment, TeacherSalaryCalculation
            ts_paid = TeacherSalaryPayment.objects.filter(teacher=emp).aggregate(total=Sum('amount'))['total'] or 0
            ts_calc = TeacherSalaryCalculation.objects.filter(teacher=emp).aggregate(total=Sum('calculated_amount'))['total'] or 0
            salary_amount = ts_calc or ts_paid

        final_salary = float(salary_amount or 0)
        b_val = float(bonus_amount or 0)
        a_val = float(advance_amount or 0)
        p_val = float(penalty_amount or 0)

        total_salary += final_salary
        total_bonus += b_val
        total_advance += a_val
        total_penalty += p_val

        full_name = f"{getattr(emp, 'first_name', '')} {getattr(emp, 'last_name', '')}".strip() or emp.username
        emp_phone = getattr(emp, 'phone', None) or getattr(emp, 'phone_number', '-') or '-'

        rows.append({
            "id": emp.id,
            "full_name": full_name,
            "fullName": full_name,
            "name": full_name,
            "phone": emp_phone,
            "branch": emp.branch_id,
            "branch_id": emp.branch_id,
            "salary": final_salary,
            "bonus": b_val,
            "advance": a_val,
            "penalty": p_val,
            "ish_haqi": final_salary,
            "avans": a_val,
            "jarima": p_val
        })

    return {
        "results": rows,
        "table_data": rows,
        "data": rows,
        "totals": {
            "salary": total_salary,
            "bonus": total_bonus,
            "advance": total_advance,
            "penalty": total_penalty
        }
    }


def get_revenue_plan_report(org_id, branch_id=None, date_str='Bugun'):
    """
    Kutilayotgan tushum va qarzlar rejasi hisoboti.
    """
    debtors = Student.objects.filter(organization_id=org_id, balance__lt=0)
    if branch_id and str(branch_id).lower() != 'all':
        debtors = debtors.filter(branch_id=branch_id)

    debtors_count = debtors.count()
    debtors_sum = abs(float(debtors.aggregate(total=Sum('balance'))['total'] or 0))

    tx_filters = Q(cashbox__organization_id=org_id, type='INCOME')
    if branch_id and str(branch_id).lower() != 'all':
        tx_filters &= (Q(cashbox__branch_id=branch_id) | Q(branch_id=branch_id))

    paid_sum = float(Transaction.objects.filter(tx_filters).aggregate(total=Sum('amount'))['total'] or 0)
    if paid_sum == 0:
        p_filter = Q(organization_id=org_id, amount__gt=0)
        if branch_id and str(branch_id).lower() != 'all':
            p_filter &= (Q(branch_id=branch_id) | Q(branch__isnull=True))
        paid_sum = float(Payment.objects.filter(p_filter).aggregate(total=Sum('amount'))['total'] or 0)

    display_date = date_str if date_str and date_str != 'Bugun' else 'Joriy davr'

    return [
        {"title": f"{display_date} holatiga", "target": f"{display_date} holatiga", "student_count": debtors_count, "students_count": debtors_count, "amount": debtors_sum + paid_sum, "expected_amount": debtors_sum + paid_sum},
        {"title": "Eski oydan qarzdor bo'lib o'tgan o'quvchilar summasi", "target": "Eski oydan qarzdor bo'lib o'tgan o'quvchilar summasi", "student_count": debtors_count, "students_count": debtors_count, "amount": debtors_sum, "expected_amount": debtors_sum},
        {"title": "Eski oydan o'quvchilar to'lab o'tgan summa", "target": "Eski oydan o'quvchilar to'lab o'tgan summa", "student_count": 0, "students_count": 0, "amount": 0, "expected_amount": 0},
        {"title": "Shu oyda to'langan summa", "target": "Shu oyda to'langan summa", "student_count": 0, "students_count": 0, "amount": paid_sum, "expected_amount": paid_sum},
        {"title": "Qolgan kutilayotgan tushum", "target": "Qolgan kutilayotgan tushum", "student_count": debtors_count, "students_count": debtors_count, "amount": debtors_sum, "expected_amount": debtors_sum},
    ]


def get_unpaid_lessons_report(org_id, branch_id=None):
    """
    To'lanmagan darslar hisoboti.
    """
    students_qs = Student.objects.filter(organization_id=org_id, balance__lt=0).prefetch_related('student_groups__group')
    if branch_id and str(branch_id).lower() != 'all':
        students_qs = students_qs.filter(branch_id=branch_id)

    rows = []
    for index, student in enumerate(students_qs, start=1):
        balance_val = abs(float(student.balance))
        groups_str = "-"
        active_groups = [sg.group.name for sg in student.student_groups.all() if sg.group]
        if active_groups:
            groups_str = ", ".join(active_groups)

        rows.append({
            "id": index,
            "name": f"{student.first_name} {student.last_name or ''}".strip(),
            "student_name": f"{student.first_name} {student.last_name or ''}".strip(),
            "fullName": f"{student.first_name} {student.last_name or ''}".strip(),
            "groups": groups_str,
            "unpaid_lessons": int(balance_val / 60000) or 1,
            "unpaid_lessons_count": int(balance_val / 60000) or 1,
            "total_unpaid_amount": balance_val,
            "total_unpaid": balance_val,
            "unpaid_amount": balance_val,
            "branch": student.branch_id,
            "branch_id": student.branch_id
        })

    return {
        "total_count": len(rows),
        "table_data": rows,
        "results": rows,
        "data": rows
    }


def get_cancelled_payments_report(org_id, branch_id=None):
    """
    Bekor qilingan to'lovlar hisoboti.
    """
    tx_qs = Transaction.objects.filter(
        Q(cashbox__organization_id=org_id) | Q(organization_id=org_id),
        Q(description__icontains="bekor") | Q(type='EXPENSE', category='REFUND') | Q(description__icontains="qaytar")
    )
    if branch_id and str(branch_id).lower() != 'all':
        tx_qs = tx_qs.filter(Q(cashbox__branch_id=branch_id) | Q(branch_id=branch_id))

    rows = []
    for index, tx in enumerate(tx_qs, start=1):
        st_name = "Noma'lum"
        if tx.student:
            st_name = f"{tx.student.first_name} {tx.student.last_name or ''}".strip()

        tx_branch = tx.branch_id or (tx.cashbox.branch_id if tx.cashbox else None)

        rows.append({
            "id": index,
            "name": st_name,
            "student_name": st_name,
            "payment_date": tx.created_at.strftime('%Y-%m-%d') if tx.created_at else "",
            "amount": float(tx.amount),
            "unpaid_lessons": 0,
            "total_unpaid": float(tx.amount),
            "teacher": "-",
            "group": "-",
            "description": tx.description or "To'lov bekor qilingan / Qaytarilgan",
            "reason": tx.description or "To'lov bekor qilingan / Qaytarilgan",
            "branch": tx_branch,
            "branch_id": tx_branch
        })

    return {
        "total_count": len(rows),
        "table_data": rows,
        "results": rows,
        "data": rows
    }


def _get_student_group_details(student):
    if not student:
        return "-", "-"
    student_groups = []
    if hasattr(student, 'group_students') and student.group_students.exists():
        student_groups = student.group_students.all()
    elif hasattr(student, 'student_groups') and student.student_groups.exists():
        student_groups = student.student_groups.all()

    if student_groups:
        group_names = []
        course_names = []
        for sg in student_groups:
            if sg.group:
                g_name = getattr(sg.group, 'name', None) or str(sg.group)
                group_names.append(g_name)
                if getattr(sg.group, 'course', None):
                    c_name = getattr(sg.group.course, 'name', "-")
                    course_names.append(c_name)

        final_groups = ", ".join(list(set(group_names))) if group_names else "-"
        final_courses = ", ".join(list(set(course_names))) if course_names else "-"
        return final_courses, final_groups
    return "-", "-"


def get_discounts_and_bonuses_report(org_id, branch_id=None, start_date=None, end_date=None, student_search=None, group_id=None, course_id=None):
    """
    Chegirmalar va bonuslar hisoboti.
    """
    if hasattr(Transaction, 'organization'):
        base_txs = Transaction.objects.filter(organization_id=org_id)
    else:
        base_txs = Transaction.objects.filter(cashbox__organization_id=org_id)

    if branch_id:
        if hasattr(Transaction, 'branch'):
            base_txs = base_txs.filter(branch_id=branch_id)
        else:
            base_txs = base_txs.filter(cashbox__branch_id=branch_id)

    if start_date:
        try:
            base_txs = base_txs.filter(created_at__date__gte=datetime.strptime(start_date.split('T')[0], '%Y-%m-%d').date())
        except (ValueError, TypeError):
            pass
    if end_date:
        try:
            base_txs = base_txs.filter(created_at__date__lte=datetime.strptime(end_date.split('T')[0], '%Y-%m-%d').date())
        except (ValueError, TypeError):
            pass

    if student_search:
        base_txs = base_txs.filter(
            Q(student__first_name__icontains=student_search) |
            Q(student__last_name__icontains=student_search) |
            Q(description__icontains=student_search)
        )

    if group_id and group_id != 'Barchasi':
        base_txs = base_txs.filter(student__student_groups__group_id=group_id)

    if course_id and course_id != 'Barchasi':
        base_txs = base_txs.filter(student__student_groups__group__course_id=course_id)

    discount_filter = (
        Q(category='VOUCHER') |
        Q(description__icontains='chegirma') |
        Q(description__icontains='voucher') |
        Q(source_payment__comment__icontains='chegirma') |
        Q(source_payment__comment__icontains='voucher')
    )

    bonus_filter = (
        Q(category='BONUS') |
        Q(description__icontains='bonus') |
        Q(source_payment__comment__icontains='bonus')
    )

    discount_txs = base_txs.filter(discount_filter).select_related('student', 'source_payment').prefetch_related(
        'student__student_groups__group__course'
    )
    bonus_txs = base_txs.filter(bonus_filter).select_related('student', 'source_payment').prefetch_related(
        'student__student_groups__group__course'
    )

    rows = []
    index = 1

    for tx in discount_txs:
        st_name = "Umumiy Chegirma"
        course_name, group_name = "-", "-"
        if tx.student:
            st_name = f"{tx.student.first_name} {tx.student.last_name or ''}".strip()
            course_name, group_name = _get_student_group_details(tx.student)

        tx_branch_id = tx.branch_id or (tx.cashbox.branch_id if tx.cashbox else None)
        rows.append({
            "id": index,
            "name": st_name,
            "student_name": st_name,
            "student": st_name,
            "course": course_name,
            "group": group_name,
            "total_discount": float(tx.amount),
            "discount": float(tx.amount),
            "bonus": 0.0,
            "branch": tx_branch_id,
            "branch_id": tx_branch_id,
        })
        index += 1

    for tx in bonus_txs:
        st_name = "Umumiy Bonus"
        course_name, group_name = "-", "-"
        if tx.student:
            st_name = f"{tx.student.first_name} {tx.student.last_name or ''}".strip()
            course_name, group_name = _get_student_group_details(tx.student)

        tx_branch_id = tx.branch_id or (tx.cashbox.branch_id if tx.cashbox else None)
        rows.append({
            "id": index,
            "name": st_name,
            "student_name": st_name,
            "student": st_name,
            "course": course_name,
            "group": group_name,
            "total_discount": 0.0,
            "discount": 0.0,
            "bonus": float(tx.amount),
            "branch": tx_branch_id,
            "branch_id": tx_branch_id,
        })
        index += 1

    total_discounts = sum(r['total_discount'] for r in rows)
    total_bonuses = sum(r['bonus'] for r in rows)

    return {
        "total_bonuses": float(total_bonuses),
        "total_discounts": float(total_discounts),
        "summary": {
            "total_bonuses": float(total_bonuses),
            "total_discounts": float(total_discounts)
        },
        "total_count": len(rows),
        "table_data": rows
    }
