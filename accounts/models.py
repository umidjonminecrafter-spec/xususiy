from django.contrib.auth.models import AbstractUser
from django.db import models
from organizations.models import Organization, TenantModel
from django.core.exceptions import ValidationError


class WeeklyLessonHour(TenantModel):
    name = models.CharField(max_length=255, blank=True, null=True, verbose_name="Nomi / Tavsifi")
    hours = models.DecimalField(max_digits=6, decimal_places=2, verbose_name="Haftalik dars soati")

    class Meta:
        ordering = ['hours']
        verbose_name = "Haftalik dars soati"
        verbose_name_plural = "Haftalik dars soatlari"

    def __str__(self):
        return f"{self.hours} soat" if not self.name else f"{self.name} ({self.hours} soat)"



class User(AbstractUser):
    ROLE_CHOICES = (
        ('owner', 'Owner'),
        ('admin', 'Admin'),
        ('manager', 'Manager'),
        ('teacher', 'Teacher'),
        ('receptionist', 'Receptionist'),
        ('employee', 'Employee'),
        ('student', 'Student'),
    )

    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="users",
        null=True,
        blank=True
    )
    branch = models.ForeignKey(
        'organizations.Branch',
        on_delete=models.SET_NULL,
        related_name="users",
        null=True,
        blank=True
    )
    branches = models.ManyToManyField(
        'organizations.Branch',
        related_name="assigned_users",
        blank=True,
        verbose_name="Biriktirilgan filiallar"
    )
    phone = models.CharField(max_length=50, null=True, blank=True)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='employee')
    position = models.CharField(max_length=100, null=True, blank=True)
    birth_date = models.DateField(null=True, blank=True)
    gender = models.CharField(max_length=10, null=True, blank=True)
    photo = models.ImageField(upload_to='user_photos/', null=True, blank=True)
    telegram_chat_id = models.CharField(max_length=100, null=True, blank=True, verbose_name="Telegram Chat ID")
    telegram_language = models.CharField(max_length=5, default='uz', choices=[('uz', "O'zbekcha"), ('ru', 'Русский')], verbose_name="Telegram tili")

    hourly_rate = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0.0,
        null=True,
        blank=True,
        verbose_name="1 soat dars narxi (soatbay)"
    )
    weekly_hours = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        default=0.0,
        verbose_name="Haftalik dars soati"
    )
    salary_type = models.CharField(
        max_length=20,
        choices=[
            ('percentage', 'Foizli'),
            ('hourly', 'Soatbay'),
            ('fixed', "O'zgarmas oylik"),
            ('unassigned', "Belgilanmagan"),
            ('none', "Belgilanmagan"),
        ],
        default='percentage',
        null=True,
        blank=True,
        verbose_name="Oylik hisoblash turi"
    )

    fixed_salary = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0.0,
        null=True,
        blank=True,
        verbose_name="Qat'iy oylik summa (so'm)"
    )

    specialization = models.CharField(max_length=255, null=True, blank=True, verbose_name="Fan / Mutaxassislik")

    # 🚀 O'qituvchi xodim yaratilayotganda moliya foiz stavkasini biriktirish (1-rasm)
    salary_percentage = models.ForeignKey(
        'finance.StaffSalaryPercent',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="teachers",
        verbose_name="Oladigan foizi"
    )
    weekly_lesson_hour = models.ForeignKey(
        'accounts.WeeklyLessonHour',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="teachers",
        verbose_name="Haftalik dars soati ma'lumotnomasi"
    )

    def clean(self):
        super().clean()

    def save(self, *args, **kwargs):
        if self.phone:
            from common.utils import normalize_uz_phone
            normalized = normalize_uz_phone(self.phone)
            if normalized:
                self.phone = normalized
        if self.pk:
            try:
                orig = User.objects.get(pk=self.pk)
                if orig.phone != self.phone:
                    self.telegram_chat_id = None
            except User.DoesNotExist:
                pass
        super().save(*args, **kwargs)

    class Meta:
        indexes = [
            models.Index(fields=['organization', 'role', 'is_active']),
            models.Index(fields=['organization', 'phone']),
            models.Index(fields=['organization', 'branch']),
        ]

    def __str__(self):
        return f"{self.username} ({self.role})"


class PasswordResetSession(models.Model):
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="password_reset_sessions",
        verbose_name="Foydalanuvchi"
    )
    phone = models.CharField(max_length=50, verbose_name="Telefon raqam")
    token = models.CharField(max_length=64, unique=True, db_index=True, verbose_name="Sessiya tokeni")
    otp_code = models.CharField(max_length=6, verbose_name="6 xonali tasdiqlash kodi")
    is_verified = models.BooleanField(default=False, verbose_name="Telegram orqali tasdiqlanganmi")
    is_used = models.BooleanField(default=False, verbose_name="Parol tiklashda ishlatilganmi")
    attempts = models.IntegerField(default=0, verbose_name="Urinishlar soni")
    expires_at = models.DateTimeField(verbose_name="Amal qilish muddati")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Yaratilgan vaqt")

    class Meta:
        verbose_name = "Parolni tiklash sessiyasi"
        verbose_name_plural = "Parolni tiklash sessiyalari"
        ordering = ['-created_at']

    def __str__(self):
        return f"Reset for {self.phone} ({self.token[:8]}...) - Verified: {self.is_verified}"

    def is_expired(self):
        from django.utils import timezone
        return timezone.now() > self.expires_at