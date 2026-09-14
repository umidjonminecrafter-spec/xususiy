import calendar
import datetime as dt_module
from decimal import Decimal

from django.db.models import Q
from django.utils import timezone
from django.contrib.auth import get_user_model

from academics.models import (
    StudentGroup, Attendance, LessonSchedule, Holiday,
    TeacherSalaryPayment, get_lessons_in_month
)
from organizations.models import Subscription
from finance.models import (
    TeacherSalaryRule, TeacherSalaryCalculation, Transaction
)

User = get_user_model()


def calculate_staff_holidays(organization_id, month_start, month_end):
    """
    Xodimlar uchun ta'sir qiluvchi bayram kunlari to'plami va sonini hisoblaydi.
    """
    staff_holidays = Holiday.objects.filter(
        organization_id=organization_id,
        staff_impact=True,
        start_date__lte=month_end
    ).filter(Q(end_date__gte=month_start) | Q(end_date__isnull=True))

    holiday_dates = set()
    for h in staff_holidays:
        start = max(h.start_date, month_start)
        end = min(h.end_date or h.start_date, month_end)
        curr = start
        while curr <= end:
            holiday_dates.add(curr)
            curr += timezone.timedelta(days=1)

    return holiday_dates, len(holiday_dates)


def calculate_student_holidays(organization_id, month_start, month_end, last_day):
    """
    Talabalar uchun ta'sir qiluvchi bayram kunlari va chegirma koeffitsientini hisoblaydi.
    """
    student_holidays = Holiday.objects.filter(
        organization_id=organization_id,
        student_impact=True,
        start_date__lte=month_end
    ).filter(Q(end_date__gte=month_start) | Q(end_date__isnull=True))

    stud_holiday_dates = set()
    for h in student_holidays:
        start = max(h.start_date, month_start)
        end = min(h.end_date or h.start_date, month_end)
        curr = start
        while curr <= end:
            stud_holiday_dates.add(curr)
            curr += timezone.timedelta(days=1)

    stud_holiday_days = len(stud_holiday_dates)
    student_discount = Decimal(1)
    if stud_holiday_days > 0 and last_day > 0:
        student_discount = Decimal(1) - (Decimal(stud_holiday_days) / Decimal(last_day))

    return stud_holiday_dates, stud_holiday_days, student_discount


def resolve_teacher_salary_rule(organization_id, teacher, period, year, month, std_rule=None):
    """
    O'qituvchi uchun oylik hisoblash qoidasi (rule_type, rate)ni aniqlaydi.
    1. Ushbu oy (period) uchun maxsus yozilgan TeacherSalaryRule (agar mavjud bo'lsa).
    2. O'qituvchi profilida tanlangan oylik turi (salary_type, fixed_salary, hourly_rate, salary_percentage).
    3. Qiymatlarga ko'ra aniqlash (fixed_salary, hourly_rate, salary_percentage).
    4. Umumiy faol TeacherSalaryRule.
    5. Tashkilot standarti (std_rule).
    6. Standart fallback.
    """
    # 1. Shu davr (period) uchun maxsus qoida bormi?
    rule = TeacherSalaryRule.objects.filter(
        organization_id=organization_id,
        teacher=teacher,
        period=period,
        is_active=True
    ).first()

    if rule:
        return rule.rule_type, rule.rate

    # 2. O'qituvchi profilidagi joriy oylik turi (salary_type)
    st = getattr(teacher, 'salary_type', None)
    fixed_val = getattr(teacher, 'fixed_salary', None)
    hourly_val = getattr(teacher, 'hourly_rate', None)
    percent_obj = getattr(teacher, 'salary_percentage', None)

    if st == 'fixed' and fixed_val and Decimal(str(fixed_val)) > 0:
        return 'fixed', Decimal(str(fixed_val))
    elif (st == 'hourly' or st == 'per_hour') and hourly_val and Decimal(str(hourly_val)) > 0:
        return 'per_hour', Decimal(str(hourly_val))
    elif st == 'percentage' and percent_obj:
        return 'percentage', Decimal(str(percent_obj.percent))
    elif st in ('unassigned', 'none'):
        return 'fixed', Decimal('0.00')

    # 3. Kiritilgan qiymatlar bo'yicha aniqlash
    if fixed_val and Decimal(str(fixed_val)) > 0:
        return 'fixed', Decimal(str(fixed_val))
    elif hourly_val and Decimal(str(hourly_val)) > 0:
        return 'per_hour', Decimal(str(hourly_val))
    elif percent_obj:
        return 'percentage', Decimal(str(percent_obj.percent))

    # 4. Umumiy TeacherSalaryRule
    general_rule = TeacherSalaryRule.objects.filter(
        organization_id=organization_id,
        teacher=teacher,
        is_active=True
    ).order_by('-created_at').first()
    if general_rule:
        return general_rule.rule_type, general_rule.rate

    # 5. Tashkilot standarti
    if std_rule:
        return std_rule.rule_type, std_rule.rate

    # 6. Fallback
    has_atts = Attendance.objects.filter(group__teacher=teacher, date__year=year, date__month=month).exists()
    if has_atts:
        return 'percentage', Decimal('50.00')
    else:
        return 'fixed', Decimal('800.00')


def calculate_fixed_salary(rate, holiday_days_count, last_day):
    """
    Fiksirlangan maoshni bayram kunlari chegirilishini hisobga olgan holda hisoblaydi.
    """
    details = {}
    if holiday_days_count > 0 and last_day > 0:
        discount_factor = Decimal(1) - (Decimal(holiday_days_count) / Decimal(last_day))
        calculated_amount = rate * discount_factor
        details['holiday_days_deducted'] = holiday_days_count
        details['original_rate'] = str(rate)
    else:
        calculated_amount = rate
    return calculated_amount, details


def calculate_per_student_salary(rate, student_count, holiday_days_count, last_day):
    """
    O'quvchilar soniga asoslangan maoshni hisoblaydi.
    """
    base_amount = rate * student_count
    details = {'student_count': student_count}
    if holiday_days_count > 0 and last_day > 0:
        discount_factor = Decimal(1) - (Decimal(holiday_days_count) / Decimal(last_day))
        calculated_amount = base_amount * discount_factor
        details['holiday_days_deducted'] = holiday_days_count
        details['original_rate'] = str(base_amount)
    else:
        calculated_amount = base_amount
    return calculated_amount, details


def calculate_percentage_salary(teacher, organization_id, year, month, rate, student_count):
    """
    Davomat va foizga asoslangan maoshni hisoblaydi.
    """
    attendances = Attendance.objects.filter(
        group__teacher=teacher,
        organization_id=organization_id,
        date__year=year,
        date__month=month,
        status__in=['present', 'late']
    ).select_related('student', 'group')

    details = {
        'student_count': student_count,
        'calculated_from_lessons': True
    }

    if not attendances.exists():
        details['attendance_charges'] = {}
        return Decimal('0.00'), details

    total_earned = Decimal('0.00')
    attendance_charges = {}

    for att in attendances:
        tx = Transaction.objects.filter(description__startswith=f"Davomat #{att.id}:").first()
        if tx and tx.amount > 0:
            lesson_cost = tx.amount
        else:
            monthly_price = Decimal('0.00')
            sg = StudentGroup.objects.filter(student=att.student, group=att.group).first()
            if sg and sg.price is not None:
                monthly_price = sg.price
            elif att.group and att.group.course:
                monthly_price = att.group.course.price

            lessons_in_month = get_lessons_in_month(att.group, att.date.year, att.date.month)
            if lessons_in_month > 0:
                lesson_cost = monthly_price / Decimal(lessons_in_month)
            else:
                lesson_cost = Decimal('0.00')
            lesson_cost = round(lesson_cost, 2)

        share = lesson_cost * (rate / Decimal('100.00'))
        share = round(share, 2)
        total_earned += share
        attendance_charges[str(att.id)] = str(share)

    details['attendance_charges'] = attendance_charges
    return total_earned, details


def calculate_per_hour_salary(teacher, organization_id, month_start, month_end, holiday_dates, holiday_days_count, rate):
    """
    Dars jadvali (soatbay) asosidagi maoshni hisoblaydi.
    """
    schedules = LessonSchedule.objects.filter(group__teacher=teacher, organization_id=organization_id)
    details = {}

    if schedules.exists():
        total_hours = Decimal('0.00')
        even_schedules = [s for s in schedules if s.day_type == 'even']
        odd_schedules = [s for s in schedules if s.day_type == 'odd']

        curr = month_start
        while curr <= month_end:
            if curr in holiday_dates:
                curr += timezone.timedelta(days=1)
                continue

            weekday = curr.weekday()
            day_schedules = []
            if weekday in (1, 3, 5):
                day_schedules = even_schedules
            elif weekday in (0, 2, 4):
                day_schedules = odd_schedules

            for s in day_schedules:
                duration = dt_module.datetime.combine(curr, s.end_time) - dt_module.datetime.combine(curr, s.start_time)
                hours = Decimal(duration.total_seconds()) / Decimal('3600.0')
                total_hours += hours

            curr += timezone.timedelta(days=1)

        hours_taught = total_hours
        details['calculated_via_schedules'] = True
    else:
        teacher_wh = getattr(teacher, 'weekly_hours', None) or (
            teacher.weekly_lesson_hour.hours if getattr(teacher, 'weekly_lesson_hour', None) else None
        )
        if teacher_wh and Decimal(str(teacher_wh)) > 0:
            base_h = Decimal(str(teacher_wh)) * Decimal('4.00')
            hours_taught = max(Decimal('0.00'), base_h - Decimal(holiday_days_count * 2))
            details['calculated_via_weekly_hours'] = True
            details['weekly_hours'] = str(teacher_wh)
        else:
            hours_taught = max(Decimal('0.00'), Decimal('24.00') - Decimal(holiday_days_count * 2))
            details['calculated_via_schedules'] = False

    calculated_amount = rate * hours_taught
    details['hours_taught'] = str(hours_taught)
    if holiday_days_count > 0:
        details['holiday_days_deducted'] = holiday_days_count

    return calculated_amount, details


def reset_teacher_salary_calculations(organization_id, period):
    """
    Ko'rsatilgan davr uchun hisoblangan o'qituvchi oyliklarini 0 ga tushiradi.
    """
    calcs = TeacherSalaryCalculation.objects.filter(organization_id=organization_id, period=period)
    calcs.update(
        calculated_amount=Decimal('0.00'),
        details={'rule_type': 'percentage', 'rate': '50.00', 'attendance_charges': {}}
    )
    TeacherSalaryPayment.objects.filter(organization_id=organization_id, period=period).delete()
    return calcs


def calculate_teacher_salaries(organization_id, period):
    """
    Tashkilot bo'yicha barcha o'qituvchilarning ko'rsatilgan davr uchun oyligini hisoblaydi.
    """
    year, month = map(int, period.split('-'))
    _, last_day = calendar.monthrange(year, month)
    month_start = timezone.datetime(year, month, 1).date()
    month_end = timezone.datetime(year, month, last_day).date()

    teachers = User.objects.filter(organization_id=organization_id, role='teacher')
    subscription = Subscription.objects.filter(
        organization_id=organization_id,
        is_active=True
    ).first()

    std_rule = TeacherSalaryRule.objects.filter(
        organization_id=organization_id,
        teacher__isnull=True,
        period=period,
        is_active=True
    ).first()
    if not std_rule:
        std_rule = TeacherSalaryRule.objects.filter(
            organization_id=organization_id,
            teacher__isnull=True,
            is_active=True
        ).order_by('-created_at').first()

    holiday_dates, holiday_days_count = calculate_staff_holidays(organization_id, month_start, month_end)

    calcs = []
    for teacher in teachers:
        rule_type, rate = resolve_teacher_salary_rule(organization_id, teacher, period, year, month, std_rule)
        details = {"rule_type": rule_type, "rate": str(rate)}

        if rule_type == 'fixed':
            calculated_amount, fix_details = calculate_fixed_salary(rate, holiday_days_count, last_day)
            details.update(fix_details)

        elif rule_type in ('per_student', 'percentage'):
            student_groups = StudentGroup.objects.filter(
                group__teacher=teacher,
                organization_id=organization_id
            )
            if subscription and subscription.ignore_trial_salary:
                student_groups = student_groups.exclude(
                    student__first_name__icontains='trial'
                ).exclude(student__first_name__icontains='sinov')

            student_count = student_groups.count()

            if rule_type == 'per_student':
                calculated_amount, st_details = calculate_per_student_salary(
                    rate, student_count, holiday_days_count, last_day
                )
                details.update(st_details)
            else:
                calculated_amount, pct_details = calculate_percentage_salary(
                    teacher, organization_id, year, month, rate, student_count
                )
                details.update(pct_details)

        elif rule_type == 'per_hour':
            calculated_amount, hour_details = calculate_per_hour_salary(
                teacher, organization_id, month_start, month_end,
                holiday_dates, holiday_days_count, rate
            )
            details.update(hour_details)
        else:
            calculated_amount = Decimal('0.00')

        t_atts = Attendance.objects.filter(
            group__teacher=teacher,
            organization_id=organization_id,
            date__year=year,
            date__month=month
        )
        davomat_present = t_atts.filter(status__in=['present', 'late']).count()
        t_lessons = t_atts.values('group_id', 'date').distinct().count()
        details['davomat_count'] = davomat_present
        details['attendance_count'] = davomat_present
        details['lessons_count'] = t_lessons
        details['total_attendance_count'] = t_atts.count()
        if 'davomat_summa' not in details and calculated_amount > 0 and rule_type == 'percentage':
            details['davomat_summa'] = str(calculated_amount)

        calc, _ = TeacherSalaryCalculation.objects.update_or_create(
            organization_id=organization_id,
            teacher=teacher,
            period=period,
            defaults={'calculated_amount': calculated_amount, 'details': details}
        )
        calcs.append(calc)

    return calcs
