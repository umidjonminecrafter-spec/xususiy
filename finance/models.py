from decimal import Decimal
from django.db import models
from django.conf import settings
from django.utils import timezone
from organizations.models import TenantModel
from academics.models import Student, TeacherSalaryPayment


class ExpenseCategory(TenantModel):
    name = models.CharField(max_length=255)

    def __str__(self):
        return self.name


class ExpenseSubcategory(TenantModel):
    category = models.ForeignKey(ExpenseCategory, on_delete=models.CASCADE, related_name="subcategories")
    name = models.CharField(max_length=255)

    def __str__(self):
        return f"{self.category.name} -> {self.name}"


class TransactionCategory(models.Model):
    organization = models.ForeignKey('organizations.Organization', on_delete=models.CASCADE)
    name = models.CharField(max_length=255)
    type = models.CharField(max_length=10, choices=[('INCOME', 'Kirim'), ('EXPENSE', 'Chiqim')])
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} ({self.type})"


PAYMENT_METHOD_CHOICES = (
    ('naqd', 'Naqd pul'),
    ('plastik', 'Plastik karta'),
    ('bank', "Bank hisobi / O'tkazma"),
)


def normalize_payment_method(method):
    """
    Kiritilgan har qanday to'lov usulini 3 xil asosiy turga (naqd, plastik, bank)
    standartlashtirib beruvchi yagona funksiya.
    """
    if not method:
        return 'naqd'
    m = str(method).lower().strip()
    if m in ('naqd', 'cash', 'cash_payment'):
        return 'naqd'
    elif m in ('plastik', 'card', 'terminal', 'karta', 'humo', 'uzcard', 'click', 'payme', 'uzum'):
        return 'plastik'
    elif m in ('bank', 'transfer', 'hisob_raqam', 'otkazma', "o'tkazma", 'bank_transfer', 'hisob'):
        return 'bank'
    return 'naqd'


class Expense(TenantModel):
    PAYMENT_METHODS = PAYMENT_METHOD_CHOICES

    category = models.ForeignKey(ExpenseCategory, on_delete=models.CASCADE, related_name="expenses")
    subcategory = models.ForeignKey(ExpenseSubcategory, on_delete=models.SET_NULL, null=True, blank=True,
                                    related_name="expenses")
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    payment_method = models.CharField(
        max_length=20,
        choices=PAYMENT_METHOD_CHOICES,
        default='naqd',
        verbose_name="To'lov turi"
    )
    description = models.TextField(null=True, blank=True)
    date = models.DateField()
    cashbox = models.ForeignKey('Cashbox', on_delete=models.SET_NULL, null=True, blank=True, related_name="expenses")

    def __str__(self):
        return f"{self.category.name}: {self.amount} ({self.date})"


class MonthlyIncome(TenantModel):
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    date = models.DateField()

    def __str__(self):
        return f"Income: {self.amount} ({self.date})"


class Payment(TenantModel):
    # TO'G'RILANDI: SET_NULL qilindi - talaba o'chsa to'lov loglari saqlanadi
    student = models.ForeignKey(Student, on_delete=models.SET_NULL, null=True, blank=True, related_name="payments")
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    date = models.DateField()
    cashbox = models.ForeignKey('Cashbox', on_delete=models.SET_NULL, null=True, blank=True, related_name="payments")
    payment_method = models.CharField(max_length=100)  # e.g. Cash, Card, Bank
    employee = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                 related_name="payments")
    comment = models.TextField(null=True, blank=True)

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        if self.student:
            if not self.branch_id and self.student.branch_id:
                self.branch_id = self.student.branch_id
            if not self.organization_id and self.student.organization_id:
                self.organization_id = self.student.organization_id

        # 🚀 Bazaga saqlanadi (buning natijasida self.pk hosil bo'ladi)
        super().save(*args, **kwargs)

        # 🚀 To'lov haqidagi xabar darhol Hisobot botiga va Talaba/Ota-onaga yuboriladi
        if is_new:
            try:
                self.notify_report_bot()
                self._notified_report_bot = True
            except Exception as e_bot:
                print(f"[PAYMENT_NOTIFY_REPORT_BOT_ERR]: {e_bot}")
            try:
                self.notify_student_and_parents()
            except Exception as e_st:
                print(f"[PAYMENT_NOTIFY_STUDENT_ERR]: {e_st}")

    def notify_student_and_parents(self):
        if not self.student:
            return

        from academics.telegram_bot import send_telegram_message, get_student_bot_token
        from organizations.models import TelegramNotificationSetting
        from django.utils import timezone as django_timezone
        from django.db.models import Q

        student = self.student
        student_chat_id = getattr(student, 'telegram_chat_id', None)
        if not student_chat_id and student.phone:
            from accounts.models import User
            digits = "".join(c for c in student.phone if c.isdigit())
            last_9 = digits[-9:] if len(digits) >= 9 else digits
            matched_user = User.objects.filter(
                Q(phone=student.phone) | Q(username=student.phone) |
                (Q(phone__icontains=last_9) if last_9 else Q()) |
                (Q(username__icontains=last_9) if last_9 else Q())
            ).filter(role='student', telegram_chat_id__isnull=False).first()
            if matched_user:
                student_chat_id = matched_user.telegram_chat_id

        amount_formatted = f"{int(self.amount):,}".replace(",", " ")
        pm_map = {
            'naqd': "Naqd pul 💵",
            'cash': "Naqd pul 💵",
            'plastik': "Plastik karta 💳",
            'card': "Plastik karta 💳",
            'bank': "Bank o'tkazmasi 🏦",
        }
        pm_clean = str(self.payment_method or '').lower().strip()
        pm_display = pm_map.get(pm_clean, self.payment_method or "Naqd pul 💵")
        now_str = django_timezone.localtime(django_timezone.now()).strftime("%d.%m.%Y %H:%M")
        employee_name = f"{self.employee.first_name} {self.employee.last_name or ''}".strip() or self.employee.username if self.employee else "Kassa"
        org_name = self.organization.name if self.organization else "SmartTalim"
        branch_str = f" ({self.branch.name})" if getattr(self, 'branch', None) and self.branch else ""
        curr_bal = int(student.balance or 0)
        student_full_name = f"{student.first_name} {student.last_name or ''}".strip()

        # 1. Talaba botiga to'lov cheki yuborish
        if student_chat_id:
            token = get_student_bot_token(self.organization)
            msg = (
                f"🧾 <b>TO'LOV QABUL QILINDI!</b> ✅\n\n"
                f"Hurmatli <b>{student_full_name}</b>, to'lovingiz muvaffaqiyatli qabul qilindi.\n\n"
                f"🧾 <b>Chek raqami:</b> #{self.id or '-'}\n"
                f"🏢 <b>O'quv markaz:</b> {org_name}{branch_str}\n"
                f"💵 <b>To'langan summa:</b> <b>{amount_formatted} UZS</b>\n"
                f"💳 <b>To'lov usuli:</b> {pm_display}\n"
                f"💰 <b>Joriy balansingiz:</b> <code>{curr_bal:,} UZS</code>\n"
                f"🧑‍💼 <b>Qabul qildi:</b> {employee_name}\n"
                f"📅 <b>Sana:</b> {now_str}\n\n"
                f"<i>SmartTalim tizimi orqali tasdiqlangan.</i>"
            ).replace(",", " ")
            send_telegram_message(token, student_chat_id, msg)

        # 2. Ota-ona botiga ham yuborish
        from academics.telegram_bot import get_parent_bot_token
        parent_token = get_parent_bot_token(self.organization)
        if parent_token and (student.father_telegram_chat_id or student.mother_telegram_chat_id):
            parent_msg = (
                f"🧾 <b>TO'LOV QABUL QILINDI!</b> ✅\n\n"
                f"Farzandingiz <b>{student.first_name} {student.last_name or ''}</b> uchun to'lov qabul qilindi.\n\n"
                f"🧾 <b>Chek raqami:</b> #{self.id or '-'}\n"
                f"🏢 <b>O'quv markaz:</b> {org_name}{branch_str}\n"
                f"💵 <b>Summa:</b> <b>{amount_formatted} UZS</b>\n"
                f"💳 <b>To'lov usuli:</b> {pm_display}\n"
                f"💰 <b>Farzandingiz balansi:</b> <code>{curr_bal:,} UZS</code>\n"
                f"📅 <b>Sana:</b> {now_str}\n\n"
                f"<i>SmartTalim tizimi orqali tasdiqlangan.</i>"
            ).replace(",", " ")
            if student.father_telegram_chat_id:
                send_telegram_message(parent_token, student.father_telegram_chat_id, parent_msg)
            if student.mother_telegram_chat_id:
                send_telegram_message(parent_token, student.mother_telegram_chat_id, parent_msg)

    def notify_report_bot(self):
        organization_name = self.organization.name if self.organization else "Noma'lum"
        branch_name = self.branch.name if hasattr(self, 'branch') and self.branch else "Asosiy Filial"
        student_name = f"{self.student.first_name} {self.student.last_name or ''}".strip() if self.student else "Noma'lum"
        student_phone = getattr(self.student, 'phone', '-') if self.student else '-'
        employee_name = f"{self.employee.first_name} {self.employee.last_name or ''}".strip() or self.employee.username if self.employee else "Tizim"

        try:
            amount_formatted = f"{int(self.amount):,}".replace(",", " ")
        except Exception:
            amount_formatted = str(self.amount)

        pm = str(self.payment_method or '').lower()
        if 'naqd' in pm or 'cash' in pm:
            cash_formatted = amount_formatted
            card_formatted = "0"
        elif 'plastik' in pm or 'card' in pm or 'terminal' in pm:
            cash_formatted = "0"
            card_formatted = amount_formatted
        else:
            cash_formatted = amount_formatted
            card_formatted = "0"

        courses_count = 0
        courses_list = []
        if self.student:
            active_groups = self.student.student_groups.select_related('group', 'group__course').all()
            courses_count = active_groups.count()
            for sg in active_groups:
                c_name = sg.group.course.name if (sg.group and sg.group.course) else ""
                courses_list.append(f"  • {sg.group.name}" + (f" ({c_name})" if c_name else ""))

        courses_str = "\n".join(courses_list) if courses_list else "  • Guruhlar biriktirilmagan"
        cashbox_name = self.cashbox.name if self.cashbox else "Asosiy Kassa"
        comment_str = f"\n📝 <b>Izoh:</b> {self.comment}" if self.comment else ""

        from django.utils import timezone
        now_str = timezone.localtime(timezone.now()).strftime("%d.%m.%Y %H:%M")

        text = (
            f"💰 <b>YANGI TO'LOV QABUL QILINDI!</b> 📥\n\n"
            f"👤 <b>Talaba:</b> {student_name}\n"
            f"📞 <b>Telefon:</b> {student_phone}\n"
            f"💵 <b>To'lov summasi:</b> <b>{amount_formatted} UZS</b>\n"
            f"💳 <b>To'lov turi:</b> {self.payment_method or 'Naqd'}\n"
            f"💵 <b>Naqd:</b> {cash_formatted} UZS | 💳 <b>Plastik:</b> {card_formatted} UZS\n"
            f"🏦 <b>Kassa:</b> {cashbox_name}\n"
            f"🧑‍💼 <b>Qabul qiluvchi:</b> {employee_name}\n"
            f"🏢 <b>Tashkilot:</b> {organization_name}\n"
            f"📍 <b>Filial:</b> {branch_name}\n"
            f"🕒 <b>Sana va vaqt:</b> {now_str}\n"
            f"📚 <b>Guruh(lar)i ({courses_count} ta):</b>\n{courses_str}"
            f"{comment_str}"
        )
        send_telegram_payment_notification(self.organization, text, 'student_payments')

    def __str__(self):
        student_str = self.student if self.student else "O'chirilgan Talaba"
        return f"{student_str} - {self.amount} ({self.date})"


class Sale(TenantModel):
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    date = models.DateField()
    product_or_course = models.CharField(max_length=255)

    def __str__(self):
        return f"{self.product_or_course} - {self.amount} ({self.date})"


class Bonus(TenantModel):
    employee = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="bonuses")
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    reason = models.TextField()
    date = models.DateField()

    def __str__(self):
        return f"Bonus: {self.employee} - {self.amount} ({self.date})"


class Fine(TenantModel):
    employee = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="fines")
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    reason = models.TextField()
    date = models.DateField()

    def __str__(self):
        return f"Fine: {self.employee} - {self.amount} ({self.date})"


class Salary(TenantModel):
    STATUS_CHOICES = (
        ('paid', 'Paid'),
        ('unpaid', 'Unpaid'),
    )
    employee = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="salaries")
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    date = models.DateField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='unpaid')

    def __str__(self):
        return f"Salary: {self.employee} - {self.amount} ({self.status})"


class TeacherSalaryRule(TenantModel):
    RULE_TYPE_CHOICES = (
        ('fixed', 'Fixed Monthly'),
        ('per_student', 'Per Student enrolled'),
        ('per_hour', 'Per Hour taught'),
        ('percentage', 'Percentage of student fees'),
    )
    teacher = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True,
                                related_name="salary_rules")
    rule_type = models.CharField(max_length=50, choices=RULE_TYPE_CHOICES)
    rate = models.DecimalField(max_digits=10, decimal_places=2)
    period = models.CharField(max_length=20)  # e.g. YYYY-MM
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"Rule ({self.rule_type}): {self.teacher} - {self.rate} for {self.period}"


class TeacherSalaryCalculation(TenantModel):
    teacher = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="salary_calculations")
    calculated_amount = models.DecimalField(max_digits=12, decimal_places=2)
    period = models.CharField(max_length=20)  # e.g. YYYY-MM
    details = models.JSONField(default=dict, blank=True)

    def __str__(self):
        return f"Calc: {self.teacher} - {self.calculated_amount} for {self.period}"


class TeacherWorkLog(TenantModel):
    """
    O'qituvchining kundalik dars/soat qaydnomasi.
    Filial rahbari har kuni qaysi o'qituvchi filialda necha soat dars o'tganini yozib boradi.
    Agar boshqa o'qituvchi o'rniga kirgan bo'lsa (zamen), is_substitution=True bo'ladi va
    amalda darsni o'tgan o'qituvchiga dars soati va summasi yoziladi.
    """
    date = models.DateField(default=timezone.now, verbose_name="Dars sanasi")
    teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="work_logs",
        verbose_name="Dars o'tgan o'qituvchi"
    )
    group = models.ForeignKey(
        'academics.Group',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="teacher_work_logs",
        verbose_name="Guruh"
    )
    hours = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=1.00,
        verbose_name="O'tilgan soat"
    )
    hourly_rate = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0.00,
        verbose_name="1 soat dars narxi"
    )
    total_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0.00,
        verbose_name="Jami hisoblangan summa"
    )
    is_substitution = models.BooleanField(
        default=False,
        verbose_name="O'rinbosarlik (zamen) darsimi?"
    )
    original_teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="substituted_work_logs",
        verbose_name="Asl o'qituvchi (zamen bo'lsa)"
    )
    substitution_reason = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        verbose_name="Zamen sababi"
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="logged_teacher_works",
        verbose_name="Kiritgan xodim (filial rahbari)"
    )
    note = models.TextField(null=True, blank=True, verbose_name="Qo'shimcha izoh")

    class Meta:
        verbose_name = "O'qituvchi dars qaydnomasi"
        verbose_name_plural = "O'qituvchilar dars qaydnomalari"
        ordering = ['-date', '-created_at']

    def save(self, *args, **kwargs):
        if not self.hourly_rate or self.hourly_rate == 0:
            if self.is_substitution and self.organization_id:
                try:
                    setting = FinanceSetting.objects.filter(organization_id=self.organization_id).first()
                    if setting and setting.extra_lesson_rate and setting.extra_lesson_rate > 0:
                        self.hourly_rate = setting.extra_lesson_rate
                except Exception:
                    pass
            if (not self.hourly_rate or self.hourly_rate == 0) and self.teacher:
                teacher_rate = getattr(self.teacher, 'hourly_rate', None)
                if teacher_rate:
                    self.hourly_rate = teacher_rate
        self.total_amount = round(Decimal(str(self.hours)) * Decimal(str(self.hourly_rate or 0)), 2)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.date} | {self.teacher} - {self.hours} soat ({self.total_amount} so'm)"


class Cashbox(TenantModel):
    name = models.CharField(max_length=255)
    balance = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    is_archived = models.BooleanField(default=False)

    class Meta:
        verbose_name = "Kassa"
        verbose_name_plural = "Kassalar"

    def __str__(self):
        return self.name


class FinanceSetting(TenantModel):
    """Menejer bonus/jarimalari, Moliya bo'limi, KPI va Talabalar avtochegirmasi sozlamalari"""

    # 1. Menejer bonuslari va jarimalari (Dinamik JSON ro'yxat)
    is_bonus_enabled = models.BooleanField(default=True)
    bonus_types = models.JSONField(default=list, blank=True)  # [{"id": 1, "name": "Nomi", "amount": 50000}]

    is_penalty_enabled = models.BooleanField(default=True)
    penalty_types = models.JSONField(default=list, blank=True)  # [{"id": 1, "name": "Nomi", "amount": 20000}]

    # 2. Moliya bo'limi bonusi Sozlamalari (Foizli va soni bo'yicha)
    is_percent_bonus_enabled = models.BooleanField(default=False)
    student_payment_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0.00)
    debtor_balance_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0.00)

    is_count_bonus_enabled = models.BooleanField(default=False)
    has_money_students_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    debtor_students_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)

    # 3. KPI Sozlamalari
    kpi_settings = models.JSONField(default=dict, blank=True)

    # 5. Talabalar uchun avtochegirma (Faqat bonus_types yoqilgan bo'lsa ishlaydi)
    is_auto_discount_enabled = models.BooleanField(default=False)
    two_groups_discount_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0.00)
    three_groups_discount_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0.00)
    four_groups_discount_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0.00)

    # 6. Qo'shimcha dars (zamen) 1 soat narxi sozlamasi
    extra_lesson_rate = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0.00,
        verbose_name="Qo'shimcha dars (zamen) 1 soat narxi"
    )

    class Meta:
        verbose_name = "Moliya sozlamasi"
        verbose_name_plural = "Moliya sozlamalari"

    def __str__(self):
        return f"Finance Settings - {self.organization.name if self.organization else 'No Org'}"

    def save(self, *args, **kwargs):
        # Talab: Bonus turi o'chsa, avtochegirmani ham majburiy o'chiramiz (yoqish mumkin emas)
        if not self.is_bonus_enabled:
            self.is_auto_discount_enabled = False
        super().save(*args, **kwargs)


class CashTransaction(models.Model):
    TRANSACTION_TYPES = (
        ('kirim', 'Kirim'),
        ('chiqim', 'Chiqim'),
    )

    PAYMENT_METHODS = (
        ('naqd', 'Naqd'),
        ('plastik', 'Plastik'),
        ('terminal', 'Terminal'),
        ('bank', "Bank o'tkazmasi"),
    )

    organization = models.ForeignKey('organizations.Organization', on_delete=models.CASCADE)
    cashbox = models.ForeignKey(Cashbox, on_delete=models.CASCADE, related_name='transactions')
    transaction_type = models.CharField(max_length=10, choices=TRANSACTION_TYPES)
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHODS)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    date = models.DateField()

    # Kim xarajat qilgani yoki qaysi o'quvchi to'lov qilgani
    student = models.ForeignKey('academics.Student', on_delete=models.SET_NULL, null=True, blank=True)
    employee = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    category_name = models.CharField(max_length=255, null=True, blank=True)  # Marker, Hodimga oylik va h.k.
    comment = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Kassa amaliyoti"
        verbose_name_plural = "Kassa amaliyotlari"
        ordering = ['-created_at']


class StaffSalaryPercent(TenantModel):
    """4. Xodimlar va o'qituvchilar uchun oylik foiz stavkalari (Dinamik stavkalar qo'shish)"""
    name = models.CharField(max_length=255)  # Masalan: "Stajor o'qituvchi", "Katta o'qituvchi"
    percent = models.DecimalField(max_digits=5, decimal_places=2, default=0.00)
    comment = models.CharField(max_length=255, null=True, blank=True, verbose_name="Izoh")

    def __str__(self):
        return f"{self.name} ({self.percent}%)"


# ================= MOLIYA KASSA INTEGRATSIYASI SIGNALLARI =================
from django.db.models.signals import pre_save, post_save, post_delete
from django.dispatch import receiver


# ESKI KOD OLIB TASHLANDI: bu yerda avval `update_specific_cashbox` funksiyasi
# Payment/Expense/CashTransaction'dan kassa balansini NOLDAN qayta hisoblardi.
# Muammo: bu formula TeacherSalaryCalculateView, CashTransferAPIView va
# FinanceActionViewSet'da QO'LDA qilingan balans o'zgarishlarini bilmasdi -
# shuning uchun ular keyingi har qanday to'lov/xarajatda "yo'qolib" ketardi.
# Yangi, yagona (single-source-of-truth) yechim fayl OXIRIDA, Transaction
# modeli e'lon qilingandan keyin joylashtirilgan (pastga qarang).


# ================= TELEGRAM BOT ORQALI XABARNOMALAR INTEGRATSIYASI =================

def send_telegram_payment_notification(organization, message_text, setting_type='student_payments'):
    """
    To'lov va moliyaviy amaliyotlar haqida Tashkilot egasi / rahbariga
    Hisobot boti (@smarttalim_report_bot) orqali darhol avtomatik xabar yuboradi.
    Boshqa botlarga bormaydi.
    """
    if not organization:
        return

    try:
        from academics.telegram_bot import get_report_bot_token, send_telegram_message
        from accounts.models import User
        from organizations.models import TelegramNotificationSetting

        token = get_report_bot_token(organization)
        if not token:
            return

        chat_ids_set = set()

        # 1. Tashkilot egasi (role='owner')
        owner_users = User.objects.filter(
            organization=organization,
            role='owner',
            telegram_chat_id__isnull=False
        ).exclude(telegram_chat_id='')
        for u in owner_users:
            chat_ids_set.add(str(u.telegram_chat_id).strip())

        # 2. Superuserlar
        if not chat_ids_set:
            su_users = User.objects.filter(
                organization=organization,
                is_superuser=True,
                telegram_chat_id__isnull=False
            ).exclude(telegram_chat_id='')
            for u in su_users:
                chat_ids_set.add(str(u.telegram_chat_id).strip())

        # 3. TelegramNotificationSetting dagi chat_ids
        try:
            setting = TelegramNotificationSetting.objects.filter(organization=organization).first()
            if setting and setting.chat_ids:
                for cid in setting.chat_ids.replace(',', ' ').split():
                    if cid.strip():
                        chat_ids_set.add(cid.strip())
        except Exception:
            pass

        for cid in chat_ids_set:
            try:
                send_telegram_message(token, cid, message_text)
                print(f"[REPORT_BOT_PAYMENT] Sent to chat_id={cid} org={organization.name}")
            except Exception as e_send:
                print(f"[REPORT_BOT_PAYMENT_ERR] chat_id={cid}: {e_send}")
    except Exception as e:
        print(f"[REPORT_BOT_PAYMENT_ERR] org={getattr(organization, 'name', '')}: {e}")


@receiver(post_save, sender=Payment)
def payment_telegram_notification(sender, instance, created, **kwargs):
    # Agar Payment.save() orqali allaqachon Hisobot botiga yuborilgan bo'lsa, qayta yubormaymiz
    if getattr(instance, '_notified_report_bot', False):
        return

    if created:
        try:
            instance.notify_report_bot()
            instance._notified_report_bot = True
        except Exception as e:
            print(f"[POST_SAVE_PAYMENT_NOTIFY_ERR]: {e}")


@receiver(post_save, sender=Expense)
def expense_telegram_notification(sender, instance, created, **kwargs):
    if created:
        category_name = instance.category.name if instance.category else "Noma'lum"
        subcategory_name = f" -> {instance.subcategory.name}" if instance.subcategory else ""
        branch_name = instance.branch.name if hasattr(instance, 'branch') and instance.branch else "Noma'lum"
        desc_str = f"\n📝 Izoh: {instance.description}" if instance.description else ""

        try:
            amount_formatted = f"{int(instance.amount):,}".replace(",", " ")
        except:
            amount_formatted = str(instance.amount)

        text = (
            f"<b>Chiqim (Xarajat)</b> 📉\n\n"
            f"📁 Kategoriya: {category_name}{subcategory_name}\n"
            f"💰 Summa: {amount_formatted} UZS\n"
            f"🗓 Sana: {instance.date}\n"
            f"🏢 Filial: {branch_name}"
            f"{desc_str}"
        )
        send_telegram_payment_notification(instance.organization, text, 'expenses')


@receiver(post_save, sender=Salary)
def salary_telegram_notification(sender, instance, created, **kwargs):
    if instance.status == 'paid':
        is_newly_paid = False
        if created:
            is_newly_paid = True
        else:
            old_instance = Salary.objects.filter(pk=instance.pk).exclude(status='paid').first()
            if old_instance:
                is_newly_paid = True

        if is_newly_paid:
            employee_name = f"{instance.employee.first_name} {instance.employee.last_name or ''}" if instance.employee else "Noma'lum"
            branch_name = instance.branch.name if hasattr(instance, 'branch') and instance.branch else "Noma'lum"

            try:
                amount_formatted = f"{int(instance.amount):,}".replace(",", " ")
            except:
                amount_formatted = str(instance.amount)

            text = (
                f"<b>Chiqim (Xodim maoshi)</b> 💸\n\n"
                f"👤 Xodim: {employee_name}\n"
                f"💰 Summa: {amount_formatted} UZS\n"
                f"🗓 Sana: {instance.date}\n"
                f"🏢 Filial: {branch_name}"
            )
            send_telegram_payment_notification(instance.organization, text, 'teacher_salaries')

            # Xodimning o'ziga Telegram bildirishnoma yuborish
            if instance.employee:
                try:
                    from communication.models import Notification
                    lang = getattr(instance.employee, 'telegram_language', 'uz') or 'uz'
                    if lang == 'ru':
                        title = "💵 Выплачена зарплата"
                        msg = f"Вам выплачена зарплата в размере {amount_formatted} UZS ({instance.date})."
                    else:
                        title = "💵 Oylik maosh to'landi"
                        msg = f"Sizga {amount_formatted} UZS miqdorida oylik maosh to'landi ({instance.date})."

                    Notification.objects.create(
                        organization=instance.organization,
                        user=instance.employee,
                        title=title,
                        message=msg,
                        type='info'
                    )
                except Exception as e:
                    print(f"Error notifying salary to employee: {str(e)}")


@receiver(post_save, sender=TeacherSalaryPayment)
def teacher_salary_telegram_notification(sender, instance, created, **kwargs):
    if created:
        teacher_name = f"{instance.teacher.first_name} {instance.teacher.last_name or ''}" if instance.teacher else "Noma'lum"
        branch_name = instance.branch.name if hasattr(instance, 'branch') and instance.branch else "Noma'lum"

        try:
            amount_formatted = f"{int(instance.amount):,}".replace(",", " ")
        except:
            amount_formatted = str(instance.amount)

        paid_date = instance.paid_at.date() if hasattr(instance, 'paid_at') and instance.paid_at else getattr(instance, 'date', "Noma'lum")

        text = (
            f"<b>Chiqim (O'qituvchi ish haqi)</b> 💸\n\n"
            f"👨‍🏫 O'qituvchi: {teacher_name}\n"
            f"💰 Summa: {amount_formatted} UZS\n"
            f"🗓 Sana: {paid_date}\n"
            f"🏢 Filial: {branch_name}"
        )
        send_telegram_payment_notification(instance.organization, text, 'teacher_salaries')


@receiver(post_save, sender=MonthlyIncome)
def monthly_income_telegram_notification(sender, instance, created, **kwargs):
    if created:
        branch_name = instance.branch.name if hasattr(instance, 'branch') and instance.branch else "Noma'lum"
        try:
            amount_formatted = f"{int(instance.amount):,}".replace(",", " ")
        except:
            amount_formatted = str(instance.amount)

        text = (
            f"<b>Kirim (Boshqa kirim)</b> 📥\n\n"
            f"💰 Summa: {amount_formatted} UZS\n"
            f"🗓 Sana: {instance.date}\n"
            f"🏢 Filial: {branch_name}"
        )
        send_telegram_payment_notification(instance.organization, text, 'other_payments')


@receiver(post_save, sender=Sale)
def sale_telegram_notification(sender, instance, created, **kwargs):
    if created:
        branch_name = instance.branch.name if hasattr(instance, 'branch') and instance.branch else "Noma'lum"
        try:
            amount_formatted = f"{int(instance.amount):,}".replace(",", " ")
        except:
            amount_formatted = str(instance.amount)

        text = (
            f"<b>Kirim (Sotuv/Kurs)</b> 📥\n\n"
            f"📦 Mahsulot/Kurs: {instance.product_or_course}\n"
            f"💰 Summa: {amount_formatted} UZS\n"
            f"🗓 Sana: {instance.date}\n"
            f"🏢 Filial: {branch_name}"
        )
        send_telegram_payment_notification(instance.organization, text, 'other_payments')


@receiver(post_save, sender=CashTransaction)
def cashtransaction_telegram_notification(sender, instance, created, **kwargs):
    if created and instance.organization:
        # Agar to'lov (Payment) bilan bog'liq bo'lsa, Payment.save() orqali allaqachon to'liq xabar yuborilgan
        if instance.student_id:
            return

        try:
            cashbox_name = instance.cashbox.name if instance.cashbox else "Kassa"
            ttype_str = "Chiqim 📉" if instance.transaction_type == 'chiqim' else "Kirim 📥"
            
            try:
                amount_formatted = f"{int(instance.amount):,}".replace(",", " ")
            except:
                amount_formatted = str(instance.amount)

            from django.utils import timezone as django_timezone
            created_at = getattr(instance, 'created_at', None) or django_timezone.now()
            exact_time = django_timezone.localtime(created_at).strftime("%d.%m.%Y %H:%M:%S")

            person_info = ""
            if instance.student:
                person_info = f"\n👤 <b>Talaba:</b> {instance.student.first_name} {instance.student.last_name or ''}"
            elif instance.employee:
                person_info = f"\n🧑‍💼 <b>Xodim:</b> {instance.employee.get_full_name() or instance.employee.username}"

            category_str = f"\n📁 <b>Kategoriya/Sabab:</b> {instance.category_name}" if instance.category_name else ""
            comment_str = f"\n📝 <b>Izoh:</b> {instance.comment}" if instance.comment else ""

            text = (
                f"<b>Kassa Operatsiyasi ({ttype_str})</b>\n\n"
                f"💼 <b>Kassa:</b> {cashbox_name}\n"
                f"💰 <b>Summa:</b> {amount_formatted} UZS\n"
                f"💳 <b>To'lov turi:</b> {instance.payment_method.capitalize()}"
                f"{person_info}"
                f"{category_str}"
                f"{comment_str}\n"
                f"🗓 <b>Sana:</b> {instance.date}\n"
                f"🕒 <b>Vaqti:</b> <code>{exact_time}</code>"
            )
            send_telegram_payment_notification(instance.organization, text, 'other_payments')
        except Exception as e:
            print(f"Error sending cashtransaction telegram notification: {str(e)}")


# ================= TALABA BALANSI INTEGRATSIYASI SIGNALLARI =================

@receiver(pre_save, sender=Payment)
def payment_pre_save(sender, instance, **kwargs):
    # Set default cashbox if not set
    if not instance.cashbox:
        from finance.models import Cashbox
        branch_id = getattr(instance, 'branch_id', None)
        cashbox = None
        if branch_id:
            cashbox = Cashbox.objects.filter(organization=instance.organization, branch_id=branch_id, is_archived=False).first()
        if not cashbox:
            cashbox = Cashbox.objects.filter(organization=instance.organization, is_archived=False).first()
        if not cashbox:
            cashbox = Cashbox.objects.filter(organization=instance.organization).first()
        if not cashbox:
            cashbox = Cashbox.objects.create(
                organization=instance.organization,
                branch_id=branch_id,
                name="Asosiy kassa"
            )
        instance.cashbox = cashbox

    if instance.pk:
        try:
            old_payment = Payment.objects.get(pk=instance.pk)
            instance._old_amount = old_payment.amount
            instance._old_student = old_payment.student
        except Payment.DoesNotExist:
            instance._old_amount = None
            instance._old_student = None
    else:
        instance._old_amount = None
        instance._old_student = None


@receiver(post_save, sender=Payment)
def payment_student_balance_update(sender, instance, created, **kwargs):
    student = instance.student
    # TO'G'RILANDI: Agar talaba bo'lsa (NULL bo'lmasa) balansi yangilanadi
    if student:
        from decimal import Decimal
        student_balance = Decimal(str(student.balance))
        if created:
            student.balance = student_balance + instance.amount
            student.save(update_fields=['balance'])
        else:
            old_amount = getattr(instance, '_old_amount', None)
            old_student = getattr(instance, '_old_student', None)

            if old_amount is not None:
                if old_student and old_student != instance.student:
                    # Eski talaba hali ham bazada bo'lsa uning balansini to'g'rilaymiz
                    old_student.balance = Decimal(str(old_student.balance)) - old_amount
                    old_student.save(update_fields=['balance'])

                    student.balance = student_balance + instance.amount
                    student.save(update_fields=['balance'])
                else:
                    diff = instance.amount - old_amount
                    if diff != 0:
                        student.balance = student_balance + diff
                        student.save(update_fields=['balance'])


@receiver(post_delete, sender=Payment)
def payment_student_balance_delete(sender, instance, **kwargs):
    student = instance.student
    # TO'G'RILANDI: Agar talaba o'chirilgan bo'lsa, signal xatolik bermay o'tib ketadi.
    if student:
        from decimal import Decimal
        student.balance = Decimal(str(student.balance)) - instance.amount
        student.save(update_fields=['balance'])


from django.contrib.auth import get_user_model

# finance/models.py faylining oxiriga qo'shing:
User = get_user_model()


class Transaction(TenantModel):
    TRANSACTION_TYPES = [
        ('INCOME', 'Kirim'),
        ('EXPENSE', 'Chiqim'),
    ]

    # Qaysi bo'limdan tranzaksiya qo'shilganini bilish uchun
    CATEGORY_CHOICES = [
        ('DIRECT', 'To\'g\'ridan-to\'g\'ri'),
        ('BONUS', 'Bonus'),
        ('PENALTY', 'Jarima'),
        ('VOUCHER', 'Voucher / Chegirma'),
        ('SALARY', 'Oylik to\'lovi'),
    ]

    cashbox = models.ForeignKey('Cashbox', on_delete=models.PROTECT, related_name='finance_transactions')
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    type = models.CharField(max_length=10, choices=TRANSACTION_TYPES)
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default='DIRECT')
    payment_method = models.CharField(
        max_length=20,
        choices=PAYMENT_METHOD_CHOICES,
        default='naqd',
        verbose_name="To'lov turi"
    )

    # Kim tomonidan amalga oshirildi yoki kimga tegishli
    student = models.ForeignKey('academics.Student', on_delete=models.SET_NULL, null=True, blank=True)
    employee = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)

    description = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    # YANGI: Transaction endi YAGONA haqiqat manbai (single source of truth).
    # Payment/Expense/CashTransaction yaratilganda pastdagi signallar orqali
    # shu yerga "ko'zgu" (mirror) yozuv avtomatik qo'shiladi. Shu orqali
    # kassa balansi doim FAQAT shu jadvaldan hisoblanadi va hech qachon
    # ikki xil hisob-kitob usuli bir-biriga zid kelmaydi.
    source_payment = models.OneToOneField(
        'Payment', on_delete=models.CASCADE, null=True, blank=True, related_name='mirrored_transaction'
    )
    source_expense = models.OneToOneField(
        'Expense', on_delete=models.CASCADE, null=True, blank=True, related_name='mirrored_transaction'
    )
    source_cashtransaction = models.OneToOneField(
        'CashTransaction', on_delete=models.CASCADE, null=True, blank=True, related_name='mirrored_transaction'
    )

    class Meta:
        verbose_name = "Kassa tranzaksiyasi"
        verbose_name_plural = "Kassa tranzaksiyalari"
        ordering = ['-created_at']


class FinanceAction(TenantModel):
    ACTION_TYPES = [
        ('BONUS', 'Bonus'),
        ('PENALTY', 'Jarima'),
    ]
    TARGET_TYPES = [
        ('STUDENT', 'Talaba'),
        ('EMPLOYEE', 'Xodim'),
    ]
    action_type = models.CharField(max_length=10, choices=ACTION_TYPES)
    target_type = models.CharField(max_length=10, choices=TARGET_TYPES)

    student = models.ForeignKey('academics.Student', on_delete=models.SET_NULL, null=True, blank=True)
    # Bu yerda to'g'ridan-to'g'ri tizimdagi User (Xodim)ga ulaymiz:
    employee = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)

    amount = models.DecimalField(max_digits=12, decimal_places=2)
    reason = models.TextField(null=True, blank=True)
    transaction = models.OneToOneField(Transaction, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Moliya amali (Bonus/Jarima)"
        verbose_name_plural = "Moliya amallari (Bonus/Jarima)"
        ordering = ['-created_at']


# =====================================================================================
# YAGONA (SINGLE SOURCE OF TRUTH) KASSA BALANSI TIZIMI
# =====================================================================================
# G'OYA: Cashbox.balance HAR DOIM faqat Transaction jadvalidan hisoblanadi.
# Payment, Expense, CashTransaction o'z holicha kassa balansini o'zgartirmaydi -
# ular saqlanganda/o'zgartirilganda/o'chirilganda pastdagi signallar orqali
# mos Transaction yozuvi avtomatik yaratiladi/yangilanadi/o'chiriladi.
# Bonus, Jarima, Oylik to'lovi va Kassalararo o'tkazma views.py'da to'g'ridan-to'g'ri
# Transaction yaratadi - ular ham xuddi shu formula orqali balansga ta'sir qiladi.
# Natijada BUTUN tizimda kassa balansini o'zgartiradigan FAQAT BITTA yo'l qoladi.
# =====================================================================================

def _sync_transaction_mirror(source_field_name, instance, tx_type, category, cashbox, description):
    """
    Payment/Expense/CashTransaction obyekti uchun mos Transaction ('ko'zgu') yozuvini
    yaratadi yoki (agar allaqachon mavjud bo'lsa) yangilaydi.
    """
    if not cashbox:
        # Kassasiz obyekt uchun mos Transaction bo'lishi shart emas - eskisi bo'lsa o'chiramiz
        existing = getattr(instance, 'mirrored_transaction', None)
        if existing:
            existing.delete()
        return

    lookup = {source_field_name: instance}
    tx = Transaction.objects.filter(**lookup).first()

    branch_val = getattr(instance, 'branch_id', None) or (cashbox.branch_id if cashbox else None)
    pm = normalize_payment_method(getattr(instance, 'payment_method', 'naqd'))

    values = {
        'organization': instance.organization,
        'branch_id': branch_val,
        'cashbox': cashbox,
        'amount': instance.amount,
        'type': tx_type,
        'category': category,
        'payment_method': pm,
        'student': getattr(instance, 'student', None),
        'employee': getattr(instance, 'employee', None),
        'description': description,
    }

    if tx:
        for field, value in values.items():
            setattr(tx, field, value)
        tx.save()
    else:
        Transaction.objects.create(**{**values, source_field_name: instance})


def _delete_transaction_mirror(instance):
    existing = getattr(instance, 'mirrored_transaction', None)
    if existing:
        existing.delete()


# O'quvchi to'lovlari (Payment) endi kassaga to'g'ridan-to'g'ri qo'shilmaydi.
# To'lov faqat o'quvchining shaxsiy balansini oshiradi.
# Kassaga pul qo'shish faqat Kassa Kirim (CashTransaction) orqali amalga oshiriladi.



@receiver(post_save, sender=Expense)
def expense_transaction_mirror_sync(sender, instance, created, **kwargs):
    category_name = instance.category.name if instance.category else "Xarajat"
    _sync_transaction_mirror(
        'source_expense', instance, 'EXPENSE', 'DIRECT', instance.cashbox,
        description=f"Xarajat: {category_name}"
    )


@receiver(post_delete, sender=Expense)
def expense_transaction_mirror_delete(sender, instance, **kwargs):
    _delete_transaction_mirror(instance)


@receiver(post_save, sender=CashTransaction)
def cashtransaction_transaction_mirror_sync(sender, instance, created, **kwargs):
    tx_type = 'INCOME' if instance.transaction_type == 'kirim' else 'EXPENSE'
    _sync_transaction_mirror(
        'source_cashtransaction', instance, tx_type, 'DIRECT', instance.cashbox,
        description=instance.comment or instance.category_name or ''
    )


@receiver(post_delete, sender=CashTransaction)
def cashtransaction_transaction_mirror_delete(sender, instance, **kwargs):
    _delete_transaction_mirror(instance)


def update_cashbox_balance(organization):
    """
    Backwards compatibility stub. Kassa balansi endi tranzaksiyalar asosida 
    avtomatik ravishda recompute_cashbox_balance orqali hisoblanadi.
    """
    pass


@receiver(post_save, sender=Transaction)
@receiver(post_delete, sender=Transaction)
def recompute_cashbox_balance(sender, instance, **kwargs):
    """
    Kassa balansini FAQAT Transaction jadvalidan qayta hisoblaydigan
    YAGONA funksiya. Davomat yozuvlari (Davomat #) va o'quvchi to'lovlari (Payment) kassa balansini o'zgartirmaydi.
    """
    from django.db.models import Sum
    from decimal import Decimal

    cashbox = instance.cashbox
    if not cashbox:
        return

    income = Transaction.objects.filter(
        cashbox=cashbox, 
        type='INCOME'
    ).exclude(
        description__startswith='Davomat #'
    ).filter(
        source_payment__isnull=True
    ).aggregate(
        total=Sum('amount')
    )['total'] or Decimal('0.00')

    expense = Transaction.objects.filter(
        cashbox=cashbox, 
        type='EXPENSE'
    ).aggregate(
        total=Sum('amount')
    )['total'] or Decimal('0.00')

    Cashbox.objects.filter(pk=cashbox.pk).update(balance=income - expense)


# ================= O'QITUVCHI OYLIK TO'LOVI BO'YICHA TRANZAKSIYA VA TELEGRAM SINXRONIZATSIYASI =================
from academics.models import TeacherSalaryPayment


def send_teacher_salary_payment_telegram_notification(payment, cashbox=None):
    """
    O'qituvchiga ish haqi to'langanda Xodimlar boti orqali
    o'qituvchining shaxsiy Telegramiga darhol to'liq hisobot yuboradi:
    - To'langan summa
    - Qaysi kundan qaysi kungacha bo'lgan davr uchun
    - To'langan sana va vaqt
    - Filial va kassa
    - Qoldiq balans
    """
    if getattr(payment, '_telegram_notified', False):
        return

    teacher = getattr(payment, 'teacher', None)
    if not teacher or not getattr(teacher, 'telegram_chat_id', None):
        return

    try:
        import calendar
        from academics.telegram_bot import get_staff_bot_token, send_telegram_message

        token = get_staff_bot_token(payment.organization)
        if not token:
            return

        lang = getattr(teacher, 'telegram_language', 'uz')
        period = payment.period or ""

        # Davr sanalarini aniqlaymiz: e.g. "2026-09" -> "01.09.2026 dan 30.09.2026 gacha"
        date_range_str = period
        try:
            parts = period.split('-')
            if len(parts) == 2:
                year, month = int(parts[0]), int(parts[1])
                _, last_day = calendar.monthrange(year, month)
                if lang == 'ru':
                    date_range_str = f"с 01.{month:02d}.{year} по {last_day:02d}.{month:02d}.{year}"
                else:
                    date_range_str = f"01.{month:02d}.{year} dan {last_day:02d}.{month:02d}.{year} gacha"
        except Exception:
            date_range_str = period

        paid_dt = payment.paid_at or payment.created_at or timezone.now()
        paid_date_str = paid_dt.strftime("%d.%m.%Y %H:%M")

        teacher_name = teacher.get_full_name() or teacher.username
        branch_name = payment.branch.name if payment.branch else "Barcha filiallar"
        
        # Kassani aniqlaymiz
        if not cashbox:
            tx = Transaction.objects.filter(
                organization=payment.organization,
                description__endswith=f"(SglID: {payment.id})"
            ).select_related('cashbox').first()
            if tx and tx.cashbox:
                cashbox = tx.cashbox

        cb_name = cashbox.name if cashbox else "Kassa"
        amount_str = f"{int(payment.amount or 0):,} UZS".replace(",", " ")

        # Qoldiq balansni hisoblaymiz
        try:
            from finance.views import calculate_teacher_branch_balances
            bal = calculate_teacher_branch_balances(teacher, payment.organization_id)
            remaining_bal_str = f"{int(bal.get('overall_balance', 0)):,} UZS".replace(",", " ")
        except Exception:
            remaining_bal_str = "0 UZS"

        if lang == 'ru':
            msg = (
                "💰 <b>ВЫПЛАЧЕНА ЗАРАБОТНАЯ ПЛАТА!</b>\n\n"
                f"Уважаемый(ая) <b>{teacher_name}</b>, вам выплачена заработная плата.\n\n"
                f"💵 <b>Сумма выплаты:</b> <code>{amount_str}</code>\n"
                f"📅 <b>Расчетный период:</b> {date_range_str} ({period})\n"
                f"🗓 <b>Дата и время выплаты:</b> {paid_date_str}\n"
                f"🏢 <b>Филиал:</b> {branch_name}\n"
                f"💳 <b>Касса:</b> {cb_name}\n\n"
                f"📊 <b>Ваш текущий баланс:</b> <code>{remaining_bal_str}</code>"
            )
        else:
            msg = (
                "💰 <b>ISH HAQI TO'LANDI!</b>\n\n"
                f"Hurmatli <b>{teacher_name}</b>, sizga ish haqi to'landi.\n\n"
                f"💵 <b>To'langan summa:</b> <code>{amount_str}</code>\n"
                f"📅 <b>Hisoblangan davr:</b> {date_range_str} ({period})\n"
                f"🗓 <b>To'lov sanasi va vaqti:</b> {paid_date_str}\n"
                f"🏢 <b>Filial:</b> {branch_name}\n"
                f"💳 <b>Kassa:</b> {cb_name}\n\n"
                f"📊 <b>Qoldiq balansingiz:</b> <code>{remaining_bal_str}</code>"
            )

        send_telegram_message(token, teacher.telegram_chat_id, msg)
        payment._telegram_notified = True
    except Exception as e:
        print(f"[TEACHER_SALARY_TELEGRAM_ERROR] {str(e)}")


@receiver(post_save, sender=TeacherSalaryPayment)
def teacher_salary_payment_transaction_sync(sender, instance, created, **kwargs):
    # Filial bo'yicha yoki tashkilotning asosiy kassasini topamiz
    cashbox = None
    if instance.branch:
        cashbox = Cashbox.objects.filter(organization=instance.organization, branch=instance.branch, name__icontains="asosiy").first()
        if not cashbox:
            cashbox = Cashbox.objects.filter(organization=instance.organization, branch=instance.branch).first()
    if not cashbox:
        cashbox = Cashbox.objects.filter(organization=instance.organization, name__icontains="asosiy").first()
    if not cashbox:
        cashbox = Cashbox.objects.filter(organization=instance.organization).first()

    if cashbox:
        teacher_name = "Noma'lum"
        if instance.teacher:
            teacher_name = f"{instance.teacher.first_name} {instance.teacher.last_name or ''}".strip() or instance.teacher.username
        desc = f"O'qituvchi maosh to'lovi: {teacher_name} (SglID: {instance.id})"

        tx = Transaction.objects.filter(
            organization=instance.organization,
            description__endswith=f"(SglID: {instance.id})"
        ).first()

        if tx:
            tx.cashbox = cashbox
            if instance.branch:
                tx.branch = instance.branch
            tx.amount = instance.amount
            tx.save()
        else:
            Transaction.objects.create(
                organization=instance.organization,
                branch=instance.branch,
                cashbox=cashbox,
                amount=instance.amount,
                type='EXPENSE',
                category='SALARY',
                employee=instance.teacher,
                description=desc
            )

    # 🚀 O'qituvchi telegramiga to'lov xabarnomasini yuboramiz
    if created:
        send_teacher_salary_payment_telegram_notification(instance, cashbox=cashbox)


@receiver(post_delete, sender=TeacherSalaryPayment)
def teacher_salary_payment_transaction_delete(sender, instance, **kwargs):
    Transaction.objects.filter(
        organization=instance.organization,
        description__endswith=f"(SglID: {instance.id})"
    ).delete()


@receiver(post_save, sender='crm.Lead')
def track_lead_bonus(sender, instance, created, **kwargs):
    if not created or not instance.created_by:
        return

    try:
        from finance.models import FinanceSetting, Cashbox, FinanceAction
        from decimal import Decimal

        # Get settings
        setting = FinanceSetting.objects.filter(organization=instance.organization).first()
        if not setting or not setting.is_bonus_enabled:
            return

        # Search for Lead creation bonus in setting.bonus_types
        bonus_amount = Decimal('0.00')
        for bt in setting.bonus_types:
            name = str(bt.get('name', '')).lower()
            if 'buyurtma' in name or 'lead' in name:
                bonus_amount = Decimal(str(bt.get('amount', '0')))
                break

        if bonus_amount <= 0:
            return

        # Find Cashbox (preferring the Lead's branch)
        branch_id = getattr(instance, 'branch_id', None)
        cashbox = None
        if branch_id:
            cashbox = Cashbox.objects.filter(organization=instance.organization, branch_id=branch_id, is_archived=False).first()
        if not cashbox:
            cashbox = Cashbox.objects.filter(organization=instance.organization, is_archived=False).first()
        if not cashbox:
            cashbox = Cashbox.objects.filter(organization=instance.organization).first()
        if not cashbox:
            cashbox = Cashbox.objects.create(organization=instance.organization, name="Asosiy kassa", branch_id=branch_id)

        reason = f"Buyurtma qo'shilganligi uchun bonus (Lid: {instance.name})"

        # Create FinanceAction (which will automatically handle Transaction and Bonus creation)
        action = FinanceAction(
            organization=instance.organization,
            branch_id=branch_id,
            action_type='BONUS',
            target_type='EMPLOYEE',
            employee=instance.created_by,
            amount=bonus_amount,
            reason=reason
        )
        action._cashbox_id = cashbox.id
        action.save()

    except Exception as e:
        print(f"Error tracking lead bonus: {str(e)}")


@receiver(post_save, sender=Payment)
def payment_bonuses_sync(sender, instance, created, **kwargs):
    if not created:
        return

    try:
        from finance.models import FinanceSetting, Cashbox, FinanceAction
        from django.contrib.auth import get_user_model
        from decimal import Decimal

        User = get_user_model()
        setting = FinanceSetting.objects.filter(organization=instance.organization).first()
        if not setting:
            return

        cashbox = instance.cashbox
        if not cashbox:
            branch_id = getattr(instance, 'branch_id', None)
            if branch_id:
                cashbox = Cashbox.objects.filter(organization=instance.organization, branch_id=branch_id, is_archived=False).first()
            if not cashbox:
                cashbox = Cashbox.objects.filter(organization=instance.organization, is_archived=False).first()
            if not cashbox:
                cashbox = Cashbox.objects.filter(organization=instance.organization).first()
            if not cashbox:
                cashbox = Cashbox.objects.create(organization=instance.organization, name="Asosiy kassa", branch_id=branch_id)

        # 1. First Payment Bonus for Moderator
        if instance.student and instance.student.moderator:
            is_first_payment = Payment.objects.filter(student=instance.student).count() == 1
            if is_first_payment:
                moderator_user = User.objects.filter(id=instance.student.moderator).first()
                if moderator_user and setting.is_bonus_enabled:
                    first_pay_bonus = Decimal('0.00')
                    for bt in setting.bonus_types:
                        name = str(bt.get('name', '')).lower()
                        if 'birinchi' in name or 'first' in name:
                            first_pay_bonus = Decimal(str(bt.get('amount', '0')))
                            break

                    if first_pay_bonus > 0:
                        reason = f"Birinchi to'lov uchun bonus (Talaba: {instance.student.full_name})"
                        
                        action = FinanceAction(
                            organization=instance.organization,
                            branch_id=instance.branch_id,
                            action_type='BONUS',
                            target_type='EMPLOYEE',
                            employee=moderator_user,
                            student=instance.student,
                            amount=first_pay_bonus,
                            reason=reason
                        )
                        action._cashbox_id = cashbox.id
                        action.save()

        # 2. Finance Staff Percentage Bonus for Payment Processor
        if instance.employee and setting.is_percent_bonus_enabled:
            # Check if student was a debtor (balance < 0) before this payment
            was_debtor = False
            if instance.student:
                curr_balance = Decimal(str(instance.student.balance))
                # Current balance has already been updated with instance.amount
                if (curr_balance - instance.amount) < 0:
                    was_debtor = True

            payment_percent = Decimal(str(setting.debtor_balance_percent)) if was_debtor else Decimal(str(setting.student_payment_percent))
            if payment_percent > 0:
                bonus_amt = instance.amount * (payment_percent / Decimal('100.00'))
                bonus_amt = round(bonus_amt, 2)
                if bonus_amt > 0:
                    student_name = instance.student.full_name if instance.student else "O'chirilgan Talaba"
                    desc_type = "qarzdorlik to'lovi" if was_debtor else "kirim to'lovi"
                    reason = f"Kirim to'lovi foiz bonusi ({desc_type} {payment_percent}%) - (Talaba: {student_name})"

                    action = FinanceAction(
                        organization=instance.organization,
                        branch_id=instance.branch_id,
                        action_type='BONUS',
                        target_type='EMPLOYEE',
                        employee=instance.employee,
                        student=instance.student,
                        amount=bonus_amt,
                        reason=reason
                    )
                    action._cashbox_id = cashbox.id
                    action.save()

    except Exception as e:
        print(f"Error tracking payment bonuses: {str(e)}")


@receiver(post_save, sender='academics.StudentGroupLeave')
def track_leave_fine(sender, instance, created, **kwargs):
    if not created or not instance.student or not instance.student.moderator:
        return

    try:
        from decimal import Decimal
        from django.utils import timezone
        from django.contrib.auth import get_user_model
        from finance.models import FinanceSetting, Fine, FinanceAction

        # Check if student left with negative balance (debtor)
        if instance.student.balance >= 0:
            return

        User = get_user_model()
        moderator_user = User.objects.filter(id=instance.student.moderator).first()
        if not moderator_user:
            return

        # Get settings
        setting = FinanceSetting.objects.filter(organization=instance.organization).first()
        if not setting or not setting.is_penalty_enabled:
            return

        # Find penalty amount
        penalty_amount = Decimal('0.00')
        for pt in setting.penalty_types:
            name = str(pt.get('name', '')).lower()
            if "to'lov qilmasdan" in name or 'ketgani' in name or 'unpaid' in name or 'leave' in name:
                penalty_amount = Decimal(str(pt.get('amount', '0')))
                break

        if penalty_amount <= 0:
            return

        reason = f"Talaba to'lov qilmasdan ketganligi uchun jarima (Talaba: {instance.student.full_name})"

        # Create FinanceAction (which will automatically handle Fine creation)
        FinanceAction.objects.create(
            organization=instance.organization,
            branch_id=instance.branch_id,
            action_type='PENALTY',
            target_type='EMPLOYEE',
            employee=moderator_user,
            student=instance.student,
            amount=penalty_amount,
            reason=reason
        )

    except Exception as e:
        print(f"Error tracking leave fine: {str(e)}")


@receiver(post_save, sender=FinanceSetting)
def sync_finance_setting_to_actions(sender, instance, created, **kwargs):
    try:
        from finance.models import FinanceAction, Cashbox, Transaction, Bonus, Fine
        from academics.models import Student, BalanceHistory
        from django.contrib.auth import get_user_model
        from decimal import Decimal
        from django.utils import timezone

        User = get_user_model()
        synced_action_ids = []

        def process_items(items, action_type):
            if not isinstance(items, list):
                return

            for item in items:
                name = item.get('name')
                amount_str = item.get('amount')
                if not name or not amount_str:
                    continue
                try:
                    amount = Decimal(str(amount_str))
                except:
                    continue

                role_str = str(item.get('role', '')).lower()
                target_type = 'STUDENT' if role_str == 'student' else 'EMPLOYEE'

                student_id = item.get('student')
                employee_id = item.get('employee')
                cashbox_id = item.get('cashbox')
                description = item.get('description', '')

                student_obj = None
                if student_id:
                    student_obj = Student.objects.filter(id=student_id, organization=instance.organization).first()
                    student_id = student_obj.id if student_obj else None

                employee_obj = None
                if employee_id:
                    employee_obj = User.objects.filter(id=employee_id, organization=instance.organization).first()
                    employee_id = employee_obj.id if employee_obj else None

                # Find or create corresponding FinanceAction
                action = FinanceAction.objects.filter(
                    organization=instance.organization,
                    action_type=action_type,
                    reason=name,
                    student_id=student_id,
                    employee_id=employee_id
                ).first()

                if not action:
                    action = FinanceAction(
                        organization=instance.organization,
                        action_type=action_type,
                        target_type=target_type,
                        student_id=student_id,
                        employee_id=employee_id,
                        amount=Decimal('0.00'),
                        reason=name
                    )

                action.amount = amount
                action.target_type = target_type
                if cashbox_id:
                    action._cashbox_id = cashbox_id
                if description:
                    action._description = description
                action.save()
                synced_action_ids.append(action.id)

        process_items(instance.bonus_types, 'BONUS')
        process_items(instance.penalty_types, 'PENALTY')

        # Clean up removed FinanceAction objects and reverse their effects
        removed_actions = FinanceAction.objects.filter(
            organization=instance.organization
        ).exclude(id__in=synced_action_ids)

        for action in removed_actions:
            action.delete()

    except Exception as e:
        print(f"Error syncing finance settings to actions: {str(e)}")


@receiver(pre_save, sender=FinanceAction)
def finance_action_pre_save(sender, instance, **kwargs):
    if instance.id:
        try:
            old_obj = FinanceAction.objects.get(id=instance.id)
            instance._old_amount = old_obj.amount
            instance._old_student = old_obj.student
            instance._old_employee = old_obj.employee
            instance._old_action_type = old_obj.action_type
        except FinanceAction.DoesNotExist:
            instance._old_amount = None
            instance._old_student = None
            instance._old_employee = None
            instance._old_action_type = None
    else:
        instance._old_amount = None
        instance._old_student = None
        instance._old_employee = None
        instance._old_action_type = None


@receiver(post_save, sender=FinanceAction)
def finance_action_post_save(sender, instance, created, **kwargs):
    from decimal import Decimal
    from academics.models import BalanceHistory
    from django.utils import timezone

    # 1. Update Student Balance if student is set, or if old_student was set
    old_student = getattr(instance, '_old_student', None)
    old_amount = getattr(instance, '_old_amount', None)
    old_action_type = getattr(instance, '_old_action_type', None)
    
    affected_student_ids = set()
    if instance.student:
        affected_student_ids.add(instance.student.id)
    if not created and old_amount is not None and old_student:
        affected_student_ids.add(old_student.id)
        
    for sid in affected_student_ids:
        # Load a fresh copy from the database to avoid stale cached balances
        stu = Student.objects.select_for_update().get(id=sid)
        
        change = Decimal('0.00')
        
        # Reverse old effect for this student
        if not created and old_amount is not None and old_student and old_student.id == sid:
            if old_action_type == 'BONUS':
                change -= old_amount
                BalanceHistory.objects.create(
                    organization=instance.organization,
                    student=stu,
                    amount=-old_amount,
                    transaction_type=f"Bonus bekor qilindi (tahrir): {instance.reason or ''}"
                )
            else:  # PENALTY
                change += old_amount
                BalanceHistory.objects.create(
                    organization=instance.organization,
                    student=stu,
                    amount=old_amount,
                    transaction_type=f"Jarima bekor qilindi (tahrir): {instance.reason or ''}"
                )
                
        # Apply new effect for this student
        if instance.student and instance.student.id == sid:
            if instance.action_type == 'BONUS':
                change += instance.amount
                BalanceHistory.objects.create(
                    organization=instance.organization,
                    student=stu,
                    amount=instance.amount,
                    transaction_type=f"Bonus: {instance.reason or 'Bonus'}"
                )
            else:  # PENALTY
                change -= instance.amount
                BalanceHistory.objects.create(
                    organization=instance.organization,
                    student=stu,
                    amount=-instance.amount,
                    transaction_type=f"Jarima: {instance.reason or 'Jarima'}"
                )
                
        if change != Decimal('0.00'):
            stu.balance = Decimal(str(stu.balance)) + change
            stu.save(update_fields=['balance'])
            if instance.student and instance.student.id == sid:
                instance.student.balance = stu.balance

    # 2. Update Employee Bonus/Fine objects if employee is set
    if instance.employee:
        from finance.models import Bonus, Fine
        employee = instance.employee
        amount = instance.amount
        
        if created:
            if instance.action_type == 'BONUS':
                desc_reason = instance.reason or "Bonus"
                description = getattr(instance, '_description', None)
                if description:
                    desc_reason = f"{desc_reason}: {description}"
                Bonus.objects.create(
                    organization=instance.organization,
                    employee=employee,
                    amount=amount,
                    reason=desc_reason,
                    date=instance.created_at.date() if instance.created_at else timezone.now().date()
                )
            else:
                desc_reason = instance.reason or "Jarima"
                description = getattr(instance, '_description', None)
                if description:
                    desc_reason = f"{desc_reason}: {description}"
                Fine.objects.create(
                    organization=instance.organization,
                    employee=employee,
                    amount=amount,
                    reason=desc_reason,
                    date=instance.created_at.date() if instance.created_at else timezone.now().date()
                )
        else:
            old_amount = getattr(instance, '_old_amount', None)
            old_employee = getattr(instance, '_old_employee', None)
            old_action_type = getattr(instance, '_old_action_type', None)
            
            # Delete old ones
            if old_employee:
                if old_action_type == 'BONUS':
                    Bonus.objects.filter(
                        organization=instance.organization,
                        employee=old_employee,
                        amount=old_amount,
                        reason__startswith=instance.reason or ""
                    ).delete()
                else:
                    Fine.objects.filter(
                        organization=instance.organization,
                        employee=old_employee,
                        amount=old_amount,
                        reason__startswith=instance.reason or ""
                    ).delete()
            
            # Create new ones
            if instance.action_type == 'BONUS':
                desc_reason = instance.reason or "Bonus"
                description = getattr(instance, '_description', None)
                if description:
                    desc_reason = f"{desc_reason}: {description}"
                Bonus.objects.create(
                    organization=instance.organization,
                    employee=employee,
                    amount=amount,
                    reason=desc_reason,
                    date=instance.created_at.date() if instance.created_at else timezone.now().date()
                )
            else:
                desc_reason = instance.reason or "Jarima"
                description = getattr(instance, '_description', None)
                if description:
                    desc_reason = f"{desc_reason}: {description}"
                Fine.objects.create(
                    organization=instance.organization,
                    employee=employee,
                    amount=amount,
                    reason=desc_reason,
                    date=instance.created_at.date() if instance.created_at else timezone.now().date()
                )

    # 3. Create/Update corresponding Transaction (only for BONUS)
    if instance.action_type == 'BONUS':
        from finance.models import Transaction, Cashbox
        tx = instance.transaction
        
        # Find cashbox
        cashbox_id = getattr(instance, '_cashbox_id', None)
        cashbox_obj = None
        if cashbox_id:
            cashbox_obj = Cashbox.objects.filter(id=cashbox_id, organization=instance.organization).first()
        if not cashbox_obj:
            cashbox_obj = Cashbox.objects.filter(organization=instance.organization, is_archived=False).first()
        if not cashbox_obj:
            cashbox_obj = Cashbox.objects.filter(organization=instance.organization).first()
        if not cashbox_obj:
            cashbox_obj = Cashbox.objects.create(organization=instance.organization, name="Asosiy kassa", branch_id=instance.branch_id)
            
        desc = f"{instance.get_target_type_display()} uchun bonus: {instance.reason or ''}"
        description = getattr(instance, '_description', None)
        if description:
            desc += f" ({description})"
        
        if not tx:
            tx = Transaction.objects.create(
                organization=instance.organization,
                branch_id=instance.branch_id,
                cashbox=cashbox_obj,
                amount=instance.amount,
                type='EXPENSE',
                category='BONUS',
                student=instance.student,
                employee=instance.employee,
                description=desc
            )
            # Disabling signals when updating update_fields to prevent infinite loops
            FinanceAction.objects.filter(id=instance.id).update(transaction=tx)
        else:
            tx.amount = instance.amount
            tx.cashbox = cashbox_obj
            tx.description = desc
            tx.branch_id = instance.branch_id
            tx.save()


@receiver(post_delete, sender=FinanceAction)
def finance_action_post_delete(sender, instance, **kwargs):
    from decimal import Decimal
    from academics.models import BalanceHistory
    
    # 1. Reverse student balance
    if instance.student:
        student = instance.student
        if instance.action_type == 'BONUS':
            student.balance = Decimal(str(student.balance)) - instance.amount
            BalanceHistory.objects.create(
                organization=instance.organization,
                student=student,
                amount=-instance.amount,
                transaction_type=f"Bonus o'chirildi: {instance.reason or ''}"
            )
        else:
            student.balance = Decimal(str(student.balance)) + instance.amount
            BalanceHistory.objects.create(
                organization=instance.organization,
                student=student,
                amount=instance.amount,
                transaction_type=f"Jarima o'chirildi: {instance.reason or ''}"
            )
        student.save(update_fields=['balance'])
        
    # 2. Reverse transaction
    if instance.transaction:
        instance.transaction.delete()
        
    # 3. Delete employee Bonus/Fine
    if instance.employee:
        from finance.models import Bonus, Fine
        if instance.action_type == 'BONUS':
            Bonus.objects.filter(
                organization=instance.organization,
                employee=instance.employee,
                amount=instance.amount,
                reason__startswith=instance.reason or ""
            ).delete()
        else:
            Fine.objects.filter(
                organization=instance.organization,
                employee=instance.employee,
                amount=instance.amount,
                reason__startswith=instance.reason or ""
            ).delete()