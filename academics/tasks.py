import urllib.request
import json
from datetime import datetime, timedelta
from django.db import connection
from django.core.cache import cache
from academics.models import LessonSchedule
from organizations.models import LessonNotificationTemplate, TelegramNotificationSetting


def check_and_send_lesson_reminders():
    # Close old connections to avoid database connection issues in background threads
    connection.close()

    hozir = datetime.now()
    today_date = hozir.date()

    # Get all active Telegram settings
    active_settings = TelegramNotificationSetting.objects.filter(is_active=True).select_related('organization')

    for bot_setting in active_settings:
        org = bot_setting.organization
        if not bot_setting.bot_token or not bot_setting.chat_ids:
            continue

        # Get all active templates for this organization
        shablonlar = LessonNotificationTemplate.objects.filter(organization=org, is_active=True)
        if not shablonlar.exists():
            continue

        # Get all schedules for this organization
        darslar = LessonSchedule.objects.filter(organization=org).select_related(
            'group', 'group__course', 'group__teacher', 'group__branch'
        )

        for dars in darslar:
            guruh = dars.group
            if not guruh:
                continue

            for shablon in shablonlar:
                # Combine schedule times with current date to do timedelta calculations
                try:
                    dars_start_dt = datetime.combine(today_date, dars.start_time)
                    dars_end_dt = datetime.combine(today_date, dars.end_time)
                except Exception as e:
                    print(f"Time combining error for lesson {dars.id}: {str(e)}")
                    continue

                # Determine target datetime based on template_type
                if shablon.template_type == 'before':
                    target_dt = dars_start_dt - timedelta(minutes=shablon.delay_minutes)
                elif shablon.template_type == 'during':
                    target_dt = dars_start_dt + timedelta(minutes=shablon.delay_minutes)
                elif shablon.template_type == 'after':
                    target_dt = dars_end_dt + timedelta(minutes=shablon.delay_minutes)
                else:
                    continue

                # Calculate which date the lesson would occur on, so that target_dt falls on today
                days_diff = (target_dt.date() - today_date).days
                occurrence_date = today_date - timedelta(days=days_diff)

                # Check if the occurrence date matches the lesson schedule's day_type (even/odd)
                occurrence_weekday = occurrence_date.weekday()
                occurrence_day_type = 'even' if occurrence_weekday % 2 == 0 else 'odd'

                if dars.day_type != occurrence_day_type:
                    continue

                # Check if the target send time matches the current time to the exact hour and minute
                if target_dt.hour == hozir.hour and target_dt.minute == hozir.minute:
                    # Cache key to prevent duplicate sending within the same minute
                    cache_key = f"lesson_rem_{dars.id}_{shablon.id}_{occurrence_date}_{target_dt.hour}_{target_dt.minute}"
                    if cache.get(cache_key):
                        continue

                    # Mark in cache immediately before network request to prevent concurrent duplicate sends
                    cache.set(cache_key, True, timeout=600)

                    # Gather information for placeholders
                    ustoz_ismi = f"{guruh.teacher.first_name} {guruh.teacher.last_name or ''}".strip() if guruh.teacher else "Biriktirilmagan"
                    kurs_nomi = guruh.course.name if guruh.course else "Noma'lum"
                    filial_nomi = guruh.branch.name if guruh.branch else "Asosiy Filial"
                    dars_vaqti = f"{dars.start_time.strftime('%H:%M')}-{dars.end_time.strftime('%H:%M')}"
                    xona_nomi = dars.room_name or ""
                    kun_nomi = "Juft kunlar" if dars.day_type == 'even' else "Toq kunlar"
                    sub_kurs_nomi = guruh.course.code or ""

                    # Replace template variables
                    tayyor_matn = shablon.message_text
                    replacements = {
                        "{groupName}": guruh.name,
                        "{teacherName}": ustoz_ismi,
                        "{courseName}": kurs_nomi,
                        "{branchName}": filial_nomi,
                        "{hours}": dars_vaqti,
                        "{roomName}": xona_nomi,
                        "{days}": kun_nomi,
                        "{subCourseName}": sub_kurs_nomi
                    }
                    for key, val in replacements.items():
                        if val is not None:
                            tayyor_matn = tayyor_matn.replace(key, str(val))

                    # Parse chat IDs and send to each
                    chat_ids_list = [cid.strip() for cid in bot_setting.chat_ids.replace(',', ' ').split() if
                                     cid.strip()]

                    for chat_id in chat_ids_list:
                        try:
                            url = f"https://api.telegram.org/bot{bot_setting.bot_token}/sendMessage"
                            payload = {'chat_id': chat_id, 'text': tayyor_matn, 'parse_mode': 'HTML'}
                            data = json.dumps(payload).encode('utf-8')
                            req = urllib.request.Request(
                                url,
                                data=data,
                                headers={'Content-Type': 'application/json'},
                                method='POST'
                            )
                            with urllib.request.urlopen(req, timeout=5) as res:
                                res.read()
                        except Exception as e:
                            print(f"Error sending telegram message to chat {chat_id} for lesson {dars.id}: {str(e)}")


def check_and_send_parent_checkout_notifications():
    # Close old connections
    connection.close()

    hozir = datetime.now()
    today_date = hozir.date()

    # Faol Telegram bot sozlamalari mavjud tashkilotlarni tekshiramiz
    active_settings = TelegramNotificationSetting.objects.filter(is_active=True).select_related('organization')

    for bot_setting in active_settings:
        org = bot_setting.organization
        if not bot_setting.parent_bot_token:
            continue

        # Ushbu tashkilot uchun faol 'parent_check_out' shablonini qidiramiz
        from academics.models import BotMessageTemplate, StudentGroup
        shablon = BotMessageTemplate.objects.filter(
            organization=org, template_type='parent_check_out', is_active=True
        ).first()

        # Agar shablon bo'lmasa, default matn ishlatamiz
        default_text = "Hurmatli ota-ona, farzandingiz {first_name}ning {group_name} guruhi darsi tugadi. 🚪"
        shablon_text = shablon.text if shablon else default_text

        # Ushbu tashkilotning dars jadvallarini tekshiramiz
        darslar = LessonSchedule.objects.filter(organization=org).select_related('group', 'group__course')

        for dars in darslar:
            guruh = dars.group
            if not guruh:
                continue

            try:
                dars_end_dt = datetime.combine(today_date, dars.end_time)
            except Exception:
                continue

            # Target date day_type (even/odd) mosligini tekshiramiz
            occurrence_weekday = today_date.weekday()
            occurrence_day_type = 'even' if occurrence_weekday % 2 == 0 else 'odd'

            if dars.day_type != occurrence_day_type:
                continue

            # Agarda dars joriy soat va daqiqada tugagan bo'lsa
            if dars_end_dt.hour == hozir.hour and dars_end_dt.minute == hozir.minute:
                # Takroran yuborishni oldini olish uchun keshlaymiz
                cache_key = f"parent_checkout_{dars.id}_{today_date}_{dars_end_dt.hour}_{dars_end_dt.minute}"
                if cache.get(cache_key):
                    continue

                cache.set(cache_key, True, timeout=600)

                # Guruhdagi talabalarni olamiz
                student_groups = StudentGroup.objects.filter(group=guruh).select_related('student')
                for sg in student_groups:
                    student = sg.student
                    if not student:
                        continue

                    # Ota yoki onaning telegram_chat_id si borligini tekshiramiz
                    parent_chats = []
                    if student.father_telegram_chat_id:
                        parent_chats.append(student.father_telegram_chat_id)
                    if student.mother_telegram_chat_id:
                        parent_chats.append(student.mother_telegram_chat_id)

                    if not parent_chats:
                        continue

                    # Matndagi o'zgaruvchilarni almashtiramiz
                    tayyor_matn = shablon_text.replace("{first_name}", student.first_name)
                    tayyor_matn = tayyor_matn.replace("{last_name}", student.last_name or "")
                    tayyor_matn = tayyor_matn.replace("{group_name}", guruh.name)
                    tayyor_matn = tayyor_matn.replace("{course_name}", guruh.course.name if guruh.course else "")

                    # Har bir ota-onaga xabarni yuboramiz
                    import requests
                    for chat_id in parent_chats:
                        try:
                            url = f"https://api.telegram.org/bot{bot_setting.parent_bot_token}/sendMessage"
                            payload = {
                                'chat_id': chat_id,
                                'text': tayyor_matn,
                                'parse_mode': 'HTML'
                            }
                            requests.post(url, json=payload, timeout=5)
                        except Exception as e:
                            print(f"Error sending checkout notification to parent {chat_id}: {str(e)}")


def generate_daily_report_message(org, report_date, lang='uz'):
    from django.db.models import Sum, Q
    from datetime import timedelta
    from decimal import Decimal
    from finance.models import Payment, Expense, Salary, Sale
    from academics.models import Student, StudentGroup, StudentGroupLeave, BalanceHistory, TeacherSalaryPayment
    from accounts.models import User

    prev_date = report_date - timedelta(days=1)
    month_start = report_date.replace(day=1)

    # Date filters (checking date or created_at__date so no transaction is missed)
    p_today_q = Q(organization=org) & (Q(date=report_date) | Q(created_at__date=report_date))
    p_prev_q = Q(organization=org) & (Q(date=prev_date) | Q(created_at__date=prev_date))
    p_month_q = Q(organization=org) & (Q(date__gte=month_start, date__lte=report_date) | Q(created_at__date__gte=month_start, created_at__date__lte=report_date))

    rev_today = Payment.objects.filter(p_today_q).aggregate(Sum('amount'))['amount__sum'] or Decimal('0.00')
    rev_prev = Payment.objects.filter(p_prev_q).aggregate(Sum('amount'))['amount__sum'] or Decimal('0.00')
    rev_month = Payment.objects.filter(p_month_q).aggregate(Sum('amount'))['amount__sum'] or Decimal('0.00')
    rev_pct = ((rev_today - rev_prev) / rev_prev * 100) if rev_prev > 0 else Decimal('0.00')

    net_rev_today = rev_today
    net_rev_pct = rev_pct

    # Expenses & Salaries
    exp_today = Expense.objects.filter(Q(organization=org) & (Q(date=report_date) | Q(created_at__date=report_date))).aggregate(Sum('amount'))['amount__sum'] or Decimal('0.00')
    sal_today = Salary.objects.filter(Q(organization=org, status='paid') & (Q(date=report_date) | Q(created_at__date=report_date))).aggregate(Sum('amount'))['amount__sum'] or Decimal('0.00')
    tsal_today = TeacherSalaryPayment.objects.filter(Q(organization=org) & (Q(paid_at__date=report_date) | Q(created_at__date=report_date))).aggregate(Sum('amount'))['amount__sum'] or Decimal('0.00')
    profit_today = rev_today - exp_today - sal_today - tsal_today

    exp_month = Expense.objects.filter(Q(organization=org) & (Q(date__gte=month_start, date__lte=report_date) | Q(created_at__date__gte=month_start, created_at__date__lte=report_date))).aggregate(Sum('amount'))['amount__sum'] or Decimal('0.00')
    sal_month = Salary.objects.filter(Q(organization=org, status='paid') & (Q(date__gte=month_start, date__lte=report_date) | Q(created_at__date__gte=month_start, created_at__date__lte=report_date))).aggregate(Sum('amount'))['amount__sum'] or Decimal('0.00')
    tsal_month = TeacherSalaryPayment.objects.filter(Q(organization=org) & (Q(paid_at__date__gte=month_start, paid_at__date__lte=report_date) | Q(created_at__date__gte=month_start, created_at__date__lte=report_date))).aggregate(Sum('amount'))['amount__sum'] or Decimal('0.00')
    profit_month = rev_month - exp_month - sal_month - tsal_month

    exp_prev = Expense.objects.filter(Q(organization=org) & (Q(date=prev_date) | Q(created_at__date=prev_date))).aggregate(Sum('amount'))['amount__sum'] or Decimal('0.00')
    sal_prev = Salary.objects.filter(Q(organization=org, status='paid') & (Q(date=prev_date) | Q(created_at__date=prev_date))).aggregate(Sum('amount'))['amount__sum'] or Decimal('0.00')
    tsal_prev = TeacherSalaryPayment.objects.filter(Q(organization=org) & (Q(paid_at__date=prev_date) | Q(created_at__date=prev_date))).aggregate(Sum('amount'))['amount__sum'] or Decimal('0.00')
    profit_prev = rev_prev - exp_prev - sal_prev - tsal_prev
    profit_pct = ((profit_today - profit_prev) / profit_prev * 100) if profit_prev != 0 else Decimal('0.00')

    sales_today = Sale.objects.filter(Q(organization=org) & (Q(date=report_date) | Q(created_at__date=report_date))).count() + StudentGroup.objects.filter(Q(organization=org) & (Q(joined_at__date=report_date) | Q(created_at__date=report_date))).count()
    sales_prev = Sale.objects.filter(Q(organization=org) & (Q(date=prev_date) | Q(created_at__date=prev_date))).count() + StudentGroup.objects.filter(Q(organization=org) & (Q(joined_at__date=prev_date) | Q(created_at__date=prev_date))).count()
    sales_month = Sale.objects.filter(Q(organization=org) & (Q(date__gte=month_start, date__lte=report_date) | Q(created_at__date__gte=month_start, created_at__date__lte=report_date))).count() + StudentGroup.objects.filter(Q(organization=org) & (Q(joined_at__date__gte=month_start, joined_at__date__lte=report_date) | Q(created_at__date__gte=month_start, created_at__date__lte=report_date))).count()
    sales_pct = ((sales_today - sales_prev) / sales_prev * 100) if sales_prev > 0 else Decimal('0.00')

    ret_today = StudentGroupLeave.objects.filter(organization=org, leave_date=report_date).count()
    ret_prev = StudentGroupLeave.objects.filter(organization=org, leave_date=prev_date).count()
    ret_pct = ((ret_today - ret_prev) / ret_prev * 100) if ret_prev > 0 else Decimal('0.00')

    clients_total = Student.objects.filter(organization=org, is_archived=False).count()
    new_clients_today = Student.objects.filter(organization=org, created_at__date=report_date, is_archived=False).count()
    new_clients_prev = Student.objects.filter(organization=org, created_at__date=prev_date, is_archived=False).count()
    new_clients_month = Student.objects.filter(organization=org, created_at__date__gte=month_start, created_at__date__lte=report_date, is_archived=False).count()
    new_clients_pct = ((new_clients_today - new_clients_prev) / new_clients_prev * 100) if new_clients_prev > 0 else Decimal('0.00')

    ret_clients_today = Payment.objects.filter(p_today_q, student__created_at__date__lt=report_date).values('student').distinct().count()
    ret_clients_prev = Payment.objects.filter(p_prev_q, student__created_at__date__lt=prev_date).values('student').distinct().count()
    ret_clients_pct = ((ret_clients_today - ret_clients_prev) / ret_clients_prev * 100) if ret_clients_prev > 0 else Decimal('0.00')

    payments_today_count = Payment.objects.filter(p_today_q).count()
    payments_prev_count = Payment.objects.filter(p_prev_q).count()
    avg_check_today = rev_today / payments_today_count if payments_today_count > 0 else Decimal('0.00')
    avg_check_prev = rev_prev / payments_prev_count if payments_prev_count > 0 else Decimal('0.00')
    avg_check_pct = ((avg_check_today - avg_check_prev) / avg_check_prev * 100) if avg_check_prev > 0 else Decimal('0.00')

    payments_today = Payment.objects.filter(p_today_q).select_related('student')

    # Sellers / Employees
    sellers_data = []
    employees_today = User.objects.filter(organization=org, payments__in=Payment.objects.filter(p_today_q)).distinct()
    for emp in employees_today:
        emp_payments = Payment.objects.filter(p_today_q, employee=emp)
        emp_rev = emp_payments.aggregate(Sum('amount'))['amount__sum'] or Decimal('0.00')
        emp_count = emp_payments.count()
        emp_avg = emp_rev / emp_count if emp_count > 0 else Decimal('0.00')
        emp_name = f"{emp.first_name} {emp.last_name or ''}".strip() or emp.username
        if lang == 'ru':
            sellers_data.append(
                f"👤 <b>{emp_name}:</b>\n"
                f"   Чистая выручка: {int(emp_rev):,} UZS\n"
                f"   Средний чек: {int(emp_avg):,} UZS".replace(",", " ")
            )
        else:
            sellers_data.append(
                f"👤 <b>{emp_name}:</b>\n"
                f"   Sof tushum: {int(emp_rev):,} UZS\n"
                f"   O'rtacha chek: {int(emp_avg):,} UZS".replace(",", " ")
            )
    sellers_str = "\n".join(sellers_data) if sellers_data else ("Нет активных продавцов за день." if lang == 'ru' else "Kun davomida faol sotuvchilar yo'q.")

    # Debts
    debts_issued = abs(BalanceHistory.objects.filter(Q(organization=org) & (Q(date=report_date) | Q(created_at__date=report_date)), amount__lt=0).aggregate(Sum('amount'))['amount__sum'] or Decimal('0.00'))
    debts_paid = Payment.objects.filter(p_today_q, student__balance__lt=0).aggregate(Sum('amount'))['amount__sum'] or Decimal('0.00')
    remaining_debts = abs(Student.objects.filter(organization=org, balance__lt=0, is_archived=False).aggregate(Sum('balance'))['balance__sum'] or Decimal('0.00'))
    total_debtors = Student.objects.filter(organization=org, balance__lt=0, is_archived=False).count()

    fully_paid_debt = 0
    partially_paid_debt = 0
    for p in payments_today:
        if p.student:
            prev_bal = p.student.balance - p.amount
            if prev_bal < 0:
                if p.student.balance >= 0:
                    fully_paid_debt += 1
                else:
                    partially_paid_debt += 1
    not_paid_debt_count = max(0, total_debtors - fully_paid_debt - partially_paid_debt)

    def fmt_num(val):
        try:
            return f"{int(val):,}".replace(",", " ")
        except:
            return str(val)

    if lang == 'ru':
        msg = (
            f"📋 <b>Ежедневный отчет за {report_date.isoformat()}</b>\n\n"
            f"📈 <b>Продажи</b>\n\n"
            f"<b>Выручка:</b>\n  Сегодня: {fmt_num(rev_today)} UZS ({int(rev_pct)}%)\n  За текущий месяц: {fmt_num(rev_month)} UZS\n\n"
            f"<b>Чистая выручка:</b>\n  Сегодня: {fmt_num(net_rev_today)} UZS\n  За текущий месяц: {fmt_num(rev_month)} UZS\n\n"
            f"<b>Чистая прибыль:</b>\n  Сегодня: {fmt_num(profit_today)} UZS ({int(profit_pct)}%)\n  За текущий месяц: {fmt_num(profit_month)} UZS\n\n"
            f"<b>Кол-во проданных курсов:</b>\n  Сегодня: {sales_today} ед.\n  За текущий месяц: {sales_month} ед.\n\n"
            f"<b>Кол-во отмененных:</b>\n  Сегодня: {ret_today} ед. ({int(ret_pct)}%)\n\n"
            f"👥 <b>Клиенты</b>\n\n"
            f"  Всего активных: {clients_total}\n"
            f"  Новые сегодня: {new_clients_today} ({int(new_clients_pct)}%)\n"
            f"  Новые за месяц: {new_clients_month}\n"
            f"  Возвращающиеся клиенты: {ret_clients_today}\n\n"
            f"📊 <b>Основные показатели</b>\n\n"
            f"<b>Средний чек:</b>\n  Сегодня: {fmt_num(avg_check_today)} UZS ({int(avg_check_pct)}%)\n\n"
            f"🧑‍💼 <b>Продавцы — чистая выручка за день</b>\n\n{sellers_str}\n\n"
            f"💸 <b>Долги</b>\n\n"
            f"  Выдано долгов: {fmt_num(debts_issued)}\n"
            f"  Погашено на сумму: {fmt_num(debts_paid)}\n"
            f"  Общий остаток долгов: {fmt_num(remaining_debts)}\n"
            f"  Всего должников: {total_debtors}\n"
            f"  Частично погасивших: {partially_paid_debt}\n"
            f"  Полностью погасивших: {fully_paid_debt}\n"
            f"  Не погасивших: {not_paid_debt_count}"
        )
    else:
        msg = (
            f"📋 <b>Kunlik hisobot — {report_date.isoformat()}</b>\n\n"
            f"📈 <b>Sotuvlar</b>\n\n"
            f"<b>Tushum:</b>\n  Kunlik: {fmt_num(rev_today)} UZS ({int(rev_pct)}%)\n  Shu oy jami: {fmt_num(rev_month)} UZS\n\n"
            f"<b>Sof tushum:</b>\n  Kunlik: {fmt_num(net_rev_today)} UZS\n  Shu oy jami: {fmt_num(rev_month)} UZS\n\n"
            f"<b>Sof foyda:</b>\n  Kunlik: {fmt_num(profit_today)} UZS ({int(profit_pct)}%)\n  Shu oy jami: {fmt_num(profit_month)} UZS\n\n"
            f"<b>Sotilgan kurslar soni:</b>\n  Kunlik: {sales_today} dona\n  Shu oy jami: {sales_month} dona\n\n"
            f"<b>Bekor qilinganlar:</b>\n  Kunlik: {ret_today} dona ({int(ret_pct)}%)\n\n"
            f"👥 <b>Mijozlar</b>\n\n"
            f"  Jami faol mijozlar: {clients_total}\n"
            f"  Yangi mijozlar (kunlik): {new_clients_today} ({int(new_clients_pct)}%)\n"
            f"  Yangi mijozlar (shu oy): {new_clients_month}\n"
            f"  Qaytgan mijozlar: {ret_clients_today}\n\n"
            f"📊 <b>Asosiy ko'rsatkichlar</b>\n\n"
            f"<b>O'rtacha chek:</b>\n  Kunlik: {fmt_num(avg_check_today)} UZS ({int(avg_check_pct)}%)\n\n"
            f"🧑‍💼 <b>Sotuvchilar bo'yicha tushum</b>\n\n{sellers_str}\n\n"
            f"💸 <b>Qarzdorlik</b>\n\n"
            f"  Yangi qarzdorlik: {fmt_num(debts_issued)}\n"
            f"  Qarzdorlik so'ndirildi: {fmt_num(debts_paid)}\n"
            f"  Qarzdorlik qoldig'i (Jami): {fmt_num(remaining_debts)}\n"
            f"  Jami qarzdorlar: {total_debtors}\n"
            f"  Qisman to'laganlar: {partially_paid_debt}\n"
            f"  To'liq to'laganlar: {fully_paid_debt}\n"
            f"  To'lamaganlar: {not_paid_debt_count}"
        )
    return msg


def send_daily_telegram_reports():
    """
    Har kuni soat 9:00 da PythonAnywhere scheduled task orqali ishga tushadi.
    Kechagi kunning to'liq hisobotini har bir tashkilotning hisobot botiga yuboradi.
    """
    from django.db import connection
    connection.close()

    from django.utils import timezone
    from datetime import timedelta
    from organizations.models import Organization, TelegramNotificationSetting
    from accounts.models import User
    from academics.telegram_bot import send_telegram_message, get_report_bot_token

    yesterday = (timezone.now() - timedelta(days=1)).date()

    # Barcha tashkilotlar uchun hisobot yuboramiz
    for org in Organization.objects.all():
        try:
            report_token = get_report_bot_token(org)
            if not report_token:
                print(f"[DAILY_REPORT] No report bot token for org: {org.name}")
                continue

            # 1. TelegramNotificationSetting dan chat_ids
            chat_ids_set = set()
            try:
                setting = TelegramNotificationSetting.objects.get(organization=org)
                if setting.chat_ids:
                    for cid in setting.chat_ids.replace(',', ' ').split():
                        if cid.strip():
                            chat_ids_set.add(cid.strip())
            except TelegramNotificationSetting.DoesNotExist:
                pass

            # 2. Tashkilotdagi admin/owner/manager larning telegram_chat_id si
            staff_users = User.objects.filter(
                organization=org,
                telegram_chat_id__isnull=False
            ).exclude(role='student')

            for user in staff_users:
                if user.telegram_chat_id and str(user.telegram_chat_id).strip():
                    chat_ids_set.add(str(user.telegram_chat_id).strip())

            if not chat_ids_set:
                print(f"[DAILY_REPORT] No chat IDs for org: {org.name}")
                continue

            # Hisobot matnini yaratamiz (kechagi kun uchun)
            report_msg = generate_daily_report_message(org, yesterday, lang='uz')

            # Har bir chat_id ga report_token orqali yuboramiz
            for chat_id in chat_ids_set:
                try:
                    send_telegram_message(report_token, chat_id, report_msg)
                    print(f"[DAILY_REPORT] Sent to chat_id={chat_id} for org={org.name}")
                except Exception as e:
                    print(f"[DAILY_REPORT_ERR] chat_id={chat_id} org={org.name}: {e}")

        except Exception as e:
            print(f"[DAILY_REPORT_ERR] org={org.name}: {e}")

