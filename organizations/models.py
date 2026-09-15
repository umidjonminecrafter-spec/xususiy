from django.db import models
from django.core.validators import MaxValueValidator, MinValueValidator
from decimal import Decimal, ROUND_HALF_UP


class BaseModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Organization(BaseModel):
    name = models.CharField(max_length=255)
    subdomain = models.CharField(max_length=100, unique=True, null=True, blank=True)
    role_permissions = models.JSONField(default=dict, blank=True)
    available_roles = models.JSONField(default=list, blank=True)
    address = models.TextField(null=True, blank=True)
    phone = models.CharField(max_length=20, null=True, blank=True)
    latitude = models.DecimalField(max_length=50, max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_length=50, max_digits=9, decimal_places=6, null=True, blank=True)

    def __str__(self):
        return self.name


class TenantModel(BaseModel):
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="%(class)ss"
    )
    branch = models.ForeignKey(
        'organizations.Branch',
        on_delete=models.SET_NULL,
        related_name="%(app_label)s_%(class)ss",
        null=True,
        blank=True
    )

    class Meta:
        abstract = True


class Branch(TenantModel):
    name = models.CharField(max_length=255)
    address = models.TextField(null=True, blank=True)
    phone = models.CharField(max_length=50, null=True, blank=True)

    def __str__(self):
        return f"{self.name} ({self.organization.name})"


class Tariff(BaseModel):
    name = models.CharField(max_length=100)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    old_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    months = models.IntegerField(default=1)
    student_limit = models.PositiveIntegerField(default=0)
    discount_enabled = models.BooleanField(default=False)
    discount_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(100)]
    )
    discount_badge = models.CharField(max_length=50, null=True, blank=True)
    features = models.JSONField(default=dict, blank=True)

    @property
    def discount_amount(self):
        if not self.discount_enabled or self.discount_percent <= 0:
            return Decimal("0.00")
        amount = self.price * (self.discount_percent / Decimal("100"))
        return amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    @property
    def final_price(self):
        final = self.price - self.discount_amount
        if final < 0:
            return Decimal("0.00")
        return final.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    def __str__(self):
        return f"{self.name} ({self.months} months)"


class Subscription(TenantModel):
    tariff = models.ForeignKey(Tariff, on_delete=models.SET_NULL, null=True, blank=True)
    start_date = models.DateField()
    end_date = models.DateField()
    is_active = models.BooleanField(default=True)
    balance = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)

    # 🌟 Ish haqi va To'lov sozlamalari
    ignore_trial_salary = models.BooleanField(default=True)
    ignore_archived_salary = models.BooleanField(default=True)
    include_discount_salary = models.BooleanField(default=True)
    salary_with_discount = models.BooleanField(default=True)
    salary_for_archived = models.BooleanField(default=False)
    link_salary_attendance = models.BooleanField(default=False)
    salary_only_teacher_marks = models.BooleanField(default=False)
    salary_only_attended = models.BooleanField(default=False)
    salary_trial_students = models.BooleanField(default=False)
    salary_frozen_students = models.BooleanField(default=False)

    allow_teacher_sms = models.BooleanField(default=True)
    hide_student_data = models.BooleanField(default=False)
    attendance_during_lesson = models.BooleanField(default=False)
    allow_group_overlap = models.BooleanField(default=False)
    show_group_balance = models.BooleanField(default=True)

    uzum_settings = models.CharField(max_length=255, default="", blank=True)
    payment_mode = models.CharField(max_length=100, default="fixed", blank=True)

    def __str__(self):
        return f"Subscription for {self.organization.name}"

    def save(self, *args, **kwargs):
        # Billing yozuvlarini boshqa joyda, bitta markazlashgan oqimda yaratamiz.
        # Bu yerda faqat subscription o'zini saqlaymiz, aks holda history va purchase
        # ikki marta yaralib, hisob-kitob buziladi.
        super().save(*args, **kwargs)


class ReceiptSetting(models.Model):
    organization = models.OneToOneField(
        Organization,
        on_delete=models.CASCADE,
        related_name="receipt_setting"
    )
    image = models.ImageField(upload_to="receipts/", null=True, blank=True)
    hide_logo = models.BooleanField(default=False)
    hide_text_field = models.BooleanField(default=False)
    hide_receipt_number = models.BooleanField(default=False)
    hide_organization_name = models.BooleanField(default=False)
    hide_branch_name = models.BooleanField(default=False)
    hide_student_name = models.BooleanField(default=False)
    hide_phone_number = models.BooleanField(default=False)
    hide_balance = models.BooleanField(default=False)

    def __str__(self):
        return f"Receipt settings for {self.organization.name}"


class BackupSetting(BaseModel):
    organization = models.OneToOneField(
        Organization,
        on_delete=models.CASCADE,
        related_name="backup_setting"
    )
    bot_token = models.CharField(max_length=255, null=True, blank=True)
    chat_id = models.CharField(max_length=100, null=True, blank=True)

    api_id = models.CharField(max_length=100, null=True, blank=True)
    api_hash = models.CharField(max_length=255, null=True, blank=True)
    session_string = models.TextField(null=True, blank=True)

    interval_hours = models.IntegerField(
        choices=[(6, '6 Hours'), (12, '12 Hours'), (24, '24 Hours')],
        default=24
    )
    is_active = models.BooleanField(default=False)
    last_run_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"Backup settings for {self.organization.name}"


class TelegramNotificationSetting(BaseModel):
    organization = models.OneToOneField(
        Organization,
        on_delete=models.CASCADE,
        related_name="telegram_notification_setting"
    )
    bot_token = models.CharField(max_length=255, null=True, blank=True)
    chat_ids = models.TextField(null=True, blank=True, help_text="Vergul bilan ajratilgan chat ID'lar")

    student_payments = models.BooleanField(default=True)
    teacher_salaries = models.BooleanField(default=True)
    expenses = models.BooleanField(default=True)
    other_payments = models.BooleanField(default=True)

    # 4 ta yangi botlar uchun token va usernames
    verification_bot_token = models.CharField(max_length=255, null=True, blank=True)
    verification_bot_username = models.CharField(max_length=255, null=True, blank=True)

    student_bot_token = models.CharField(max_length=255, null=True, blank=True)
    student_bot_username = models.CharField(max_length=255, null=True, blank=True)

    parent_bot_token = models.CharField(max_length=255, null=True, blank=True)
    parent_bot_username = models.CharField(max_length=255, null=True, blank=True)

    staff_bot_token = models.CharField(max_length=255, null=True, blank=True)
    staff_bot_username = models.CharField(max_length=255, null=True, blank=True)

    support_bot_token = models.CharField(max_length=255, null=True, blank=True)
    support_bot_username = models.CharField(max_length=255, null=True, blank=True)
    support_contact_link = models.CharField(
        max_length=255, 
        null=True, 
        blank=True, 
        help_text="Operator Telegram lichkasi (username, masalan: @username)"
    )

    is_active = models.BooleanField(default=False)

    def __str__(self):
        return f"Telegram notification settings for {self.organization.name}"

    def save(self, *args, **kwargs):
        import requests
        bot_fields = [
            ('bot_token', None, 'reports'),
            ('verification_bot_token', 'verification_bot_username', 'verification'),
            ('student_bot_token', 'student_bot_username', 'student'),
            ('parent_bot_token', 'parent_bot_username', 'parent'),
            ('staff_bot_token', 'staff_bot_username', 'staff'),
            ('support_bot_token', 'support_bot_username', 'support'),
        ]

        server_domain = 'etirof.pythonanywhere.com'

        for item in bot_fields:
            token_field = item[0]
            username_field = item[1]
            bot_type = item[2]

            token = (getattr(self, token_field) or '').strip()
            old_token = None
            if self.pk:
                try:
                    old_obj = TelegramNotificationSetting.objects.get(pk=self.pk)
                    old_token = (getattr(old_obj, token_field) or '').strip()
                except TelegramNotificationSetting.DoesNotExist:
                    pass

            if token and token != old_token:
                # 1. Fetch bot username
                try:
                    response = requests.get(f"https://api.telegram.org/bot{token}/getMe", timeout=5)
                    if response.status_code == 200:
                        data = response.json()
                        if data.get('ok') and username_field:
                            username = data['result']['username']
                            setattr(self, username_field, f"@{username}")
                    elif username_field:
                        setattr(self, username_field, None)
                except Exception as e:
                    print(f"Error fetching bot username for field {token_field}: {str(e)}")
                    if username_field:
                        setattr(self, username_field, None)

                # 2. Auto-set webhook so incoming messages work immediately
                try:
                    wh_url = f"https://{server_domain}/api/telegram/webhook/{bot_type}/{token}/"
                    requests.get(f"https://api.telegram.org/bot{token}/setWebhook?url={wh_url}", timeout=5)
                except Exception as e_wh:
                    print(f"Error auto-setting webhook for {bot_type}: {str(e_wh)}")

            elif not token and username_field:
                setattr(self, username_field, None)

        super().save(*args, **kwargs)


class ExamSetting(models.Model):
    organization = models.OneToOneField(
        Organization,
        on_delete=models.CASCADE,
        related_name="exam_setting"
    )
    include_active_students = models.BooleanField(default=True)
    include_trial_students = models.BooleanField(default=True)
    include_archived_students = models.BooleanField(default=False)
    include_frozen_students = models.BooleanField(default=False)
    include_deleted_students = models.BooleanField(default=False)
    is_global = models.BooleanField(default=False)

    def __str__(self):
        return f"Exam settings for {self.organization.name}"


class LessonNotificationTemplate(TenantModel):
    TEMPLATE_TYPES = [
        ('before', 'Dars boshlanishidan oldin'),
        ('during', 'Dars davomida'),
        ('after', 'Dars tugagandan keyin'),
    ]
    name = models.CharField(max_length=255)
    template_type = models.CharField(max_length=20, choices=TEMPLATE_TYPES)
    delay_minutes = models.IntegerField(default=5)
    message_text = models.TextField()
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.name} - {self.organization.name}"



