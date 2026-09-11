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
        payment_filter = Q(organization_id=organization_id) & (Q(branch_id=branch_id) | Q(branch__isnull=True))
        expense_filter = Q(organization_id=organization_id) & (Q(branch_id=branch_id) | Q(branch__isnull=True))
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

    if branch_id and str(branch_id).isdigit():
        queryset = queryset.filter(branch_id=int(branch_id))

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
    tx_filters = Q(organization_id=org_id) if org_id else Q()
    if branch_id:
        tx_filters &= (Q(branch_id=branch_id) | Q(branch_id__isnull=True) | Q(cashbox__branch_id=branch_id))

    queryset = Transaction.objects.filter(tx_filters)

    if start_date_str:
        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
            queryset = queryset.filter(created_at__gte=start_date)
        except ValueError:
            pass

    if end_date_str:
        try:
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d')
            queryset = queryset.filter(created_at__lte=datetime.combine(end_date, time.max))
        except ValueError:
            pass

    if cashbox_id:
        try:
            queryset = queryset.filter(cashbox_id=int(cashbox_id))
        except ValueError:
            pass

    total_income = queryset.filter(type='INCOME').aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    total_expense = queryset.filter(type='EXPENSE').aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

    # Fallback to model tables if transactions table does not yet have migrated records
    if total_income == 0 and total_expense == 0 and org_id:
        p_filter = Q(organization_id=org_id)
        e_filter = Q(organization_id=org_id)
        s_filter = Q(organization_id=org_id, status='paid')
        t_filter = Q(organization_id=org_id)

        if branch_id:
            p_filter &= (Q(branch_id=branch_id) | Q(branch_id__isnull=True))
            e_filter &= (Q(branch_id=branch_id) | Q(branch_id__isnull=True))
            s_filter &= (Q(branch_id=branch_id) | Q(branch_id__isnull=True))
            t_filter &= (Q(branch_id=branch_id) | Q(branch_id__isnull=True))

        if start_date_str:
            p_filter &= Q(date__gte=start_date_str)
            e_filter &= Q(date__gte=start_date_str)
            s_filter &= Q(date__gte=start_date_str)
            t_filter &= Q(paid_at__date__gte=start_date_str)

        if end_date_str:
            p_filter &= Q(date__lte=end_date_str)
            e_filter &= Q(date__lte=end_date_str)
            s_filter &= Q(date__lte=end_date_str)
            t_filter &= Q(paid_at__date__lte=end_date_str)

        total_income = Payment.objects.filter(p_filter, amount__gt=0).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
        expenses_val = Expense.objects.filter(e_filter).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
        salaries_val = Salary.objects.filter(s_filter).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
        tsalaries_val = TeacherSalaryPayment.objects.filter(t_filter).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
        total_expense = expenses_val + salaries_val + tsalaries_val

    balance = total_income - total_expense

    income_breakdown = {}
    for tx in queryset.filter(type='INCOME'):
        desc = tx.description or "Boshqa kirimlar"
        income_breakdown[desc] = income_breakdown.get(desc, 0) + float(tx.amount)

    expense_breakdown = {}
    for tx in queryset.filter(type='EXPENSE'):
        desc = tx.description or "Boshqa chiqimlar"
        expense_breakdown[desc] = expense_breakdown.get(desc, 0) + float(tx.amount)

    daily_data = {}
    for tx in queryset.order_by('created_at'):
        date_key = tx.created_at.strftime('%d.%m')
        if date_key not in daily_data:
            daily_data[date_key] = {'kirim': 0, 'chiqim': 0}

        if tx.type == 'INCOME':
            daily_data[date_key]['kirim'] += float(tx.amount)
        else:
            daily_data[date_key]['chiqim'] += float(tx.amount)

    return {
        "cards": {
            "total_income": float(total_income),
            "total_expense": float(total_expense),
            "balance": float(balance),
            "net_profit": float(balance)
        },
        "linear_chart": {
            "labels": list(daily_data.keys()),
            "kirim_line": [v['kirim'] for v in daily_data.values()],
            "chiqim_line": [v['chiqim'] for v in daily_data.values()]
        },
        "pie_chart": {
            "kirim": {
                "labels": list(income_breakdown.keys()),
                "values": list(income_breakdown.values())
            },
            "chiqim": {
                "labels": list(expense_breakdown.keys()),
                "values": list(expense_breakdown.values())
            }
        }
    }


def get_cash_flow_report_data(org_id=None, branch_id=None, from_date=None, to_date=None, cashbox_id=None):
    """
    Pul oqimi (Cash Flow) hisoboti ma'lumotlarini hisoblaydi.
    """
    tx_filters = Q(organization_id=org_id) if org_id else Q()
    if branch_id:
        tx_filters &= (Q(branch_id=branch_id) | Q(branch_id__isnull=True) | Q(cashbox__branch_id=branch_id))

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

    incomes = queryset.filter(type='INCOME').values('description').annotate(total=Sum('amount'))
    expenses = queryset.filter(type='EXPENSE').values('description').annotate(total=Sum('amount'))

    total_income = sum(item['total'] for item in incomes) or Decimal('0.00')
    total_expense = sum(item['total'] for item in expenses) or Decimal('0.00')

    if total_income == 0 and total_expense == 0 and org_id:
        p_filter = Q(organization_id=org_id)
        e_filter = Q(organization_id=org_id)
        if branch_id:
            p_filter &= (Q(branch_id=branch_id) | Q(branch_id__isnull=True))
            e_filter &= (Q(branch_id=branch_id) | Q(branch_id__isnull=True))
        if from_date:
            p_filter &= Q(date__gte=from_date)
            e_filter &= Q(date__gte=from_date)
        if to_date:
            p_filter &= Q(date__lte=to_date)
            e_filter &= Q(date__lte=to_date)

        total_income = Payment.objects.filter(p_filter, amount__gt=0).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
        total_expense = Expense.objects.filter(e_filter).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

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

    return {
        "total_income": float(total_income),
        "total_expense": float(total_expense),
        "expenses": float(expenses_val),
        "teacher_salaries": float(teacher_expenses),
        "net_profit": float(net_profit),
        "sof_foyda": float(net_profit)
    }


def get_employee_finance_balance_report(org_id, branch_id=None):
    """
    Xodimlarning oylik, bonus, jarima va avans balansi hisoboti.
    """
    User = get_user_model()
    employees_qs = User.objects.filter(organization_id=org_id).exclude(role='student').exclude(is_superuser=True)
    if branch_id:
        employees_qs = employees_qs.filter(branch_id=branch_id)

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

        final_salary = float(salary_amount)
        b_val = float(bonus_amount)
        a_val = float(advance_amount)
        p_val = float(penalty_amount)

        total_salary += final_salary
        total_bonus += b_val
        total_advance += a_val
        total_penalty += p_val

        full_name = f"{getattr(emp, 'first_name', '')} {getattr(emp, 'last_name', '')}".strip() or emp.username

        rows.append({
            "id": emp.id,
            "full_name": full_name,
            "phone": getattr(emp, 'phone', '-'),
            "salary": f"{final_salary:,.0f} UZS".replace(",", " "),
            "bonus": f"{b_val:,.0f} UZS".replace(",", " "),
            "advance": f"{a_val:,.0f} UZS".replace(",", " "),
            "penalty": f"{p_val:,.0f} UZS".replace(",", " ")
        })

    return {
        "table_data": rows,
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
    if branch_id:
        debtors = debtors.filter(branch_id=branch_id)

    debtors_count = debtors.count()
    debtors_sum = abs(float(debtors.aggregate(total=Sum('balance'))['total'] or 0))

    tx_filters = Q(cashbox__organization_id=org_id, type='INCOME')
    if branch_id:
        tx_filters &= Q(cashbox__branch_id=branch_id)

    paid_sum = float(Transaction.objects.filter(tx_filters).aggregate(total=Sum('amount'))['total'] or 0)

    return [
        {"target": f"{date_str} holatiga", "students_count": debtors_count, "expected_amount": debtors_sum + paid_sum},
        {"target": "Eski oydan qarzdor bo'lib o'tgan o'quvchilar summasi", "students_count": debtors_count, "expected_amount": debtors_sum},
        {"target": "Eski oydan o'quvchilar to'lab o'tgan summa", "students_count": 0, "expected_amount": 0},
        {"target": "Shu oyda to'langan summa", "students_count": 0, "expected_amount": paid_sum},
        {"target": "Qolgan kutilayotgan tushum", "students_count": debtors_count, "expected_amount": debtors_sum},
    ]


def get_unpaid_lessons_report(org_id, branch_id=None):
    """
    To'lanmagan darslar hisoboti.
    """
    students_qs = Student.objects.filter(organization_id=org_id, balance__lt=0).prefetch_related('student_groups__group')
    if branch_id:
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
            "groups": groups_str,
            "unpaid_lessons_count": int(balance_val / 60000) or 1,
            "total_unpaid_amount": balance_val
        })

    return {
        "total_count": len(rows),
        "table_data": rows
    }


def get_cancelled_payments_report(org_id, branch_id=None):
    """
    Bekor qilingan to'lovlar hisoboti.
    """
    tx_qs = Transaction.objects.filter(
        cashbox__organization_id=org_id,
        description__icontains="bekor"
    )
    if branch_id:
        tx_qs = tx_qs.filter(cashbox__branch_id=branch_id)

    rows = []
    for index, tx in enumerate(tx_qs, start=1):
        st_name = "Noma'lum"
        if tx.student:
            st_name = f"{tx.student.first_name} {tx.student.last_name or ''}".strip()

        rows.append({
            "id": index,
            "name": st_name,
            "unpaid_lessons": 0,
            "total_unpaid": float(tx.amount),
            "teacher": "-",
            "group": "-",
            "description": tx.description or "To'lov bekor qilingan"
        })

    return {
        "total_count": len(rows),
        "table_data": rows
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
