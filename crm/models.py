from django.db import models
from django.conf import settings
from organizations.models import TenantModel
from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver


class Pipeline(TenantModel):
    name = models.CharField(max_length=150)
    order = models.IntegerField(default=0)

    class Meta:
        ordering = ['order']

    def __str__(self):
        return self.name


class Source(TenantModel):
    name = models.CharField(max_length=150)

    def __str__(self):
        return self.name


class LostReason(TenantModel):
    reason = models.CharField(max_length=255)

    def __str__(self):
        return self.reason


class Section(TenantModel):
    name = models.CharField(max_length=150)
    pipeline = models.ForeignKey(Pipeline, on_delete=models.SET_NULL, null=True, blank=True, related_name="sections")

    def __str__(self):
        return self.name


class LeadForm(TenantModel):
    name = models.CharField(max_length=150, verbose_name="Forma nomi")
    pipeline = models.ForeignKey(Pipeline, on_delete=models.SET_NULL, null=True, blank=True)
    section = models.ForeignKey(Section, on_delete=models.SET_NULL, null=True, blank=True)
    source = models.ForeignKey(Source, on_delete=models.SET_NULL, null=True, blank=True)
    fields = models.JSONField(
        default=list,
        blank=True,
        help_text="""[{"name": "name", "label": "Ism", "required": true}]"""
    )
    cover_image = models.ImageField(upload_to='lead_forms/covers/', null=True, blank=True)
    logo_image = models.ImageField(upload_to='lead_forms/logos/', null=True, blank=True)
    header_text = models.CharField(max_length=255, null=True, blank=True, verbose_name="Asosiy matn")
    success_text = models.TextField(default="Ma'lumotlaringiz muvaffaqiyatli yuborildi!",
                                    verbose_name="Yuborilgandan keyingi matn")
    theme_color = models.CharField(max_length=30, default="#e28743", verbose_name="Forma rangi (Hex code)")

    def __str__(self):
        return self.name


class LeadComment(TenantModel):
    lead = models.ForeignKey('Lead', on_delete=models.CASCADE, related_name="lead_comments")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Comment by {self.user} on {self.created_at.strftime('%Y-%m-%d %H:%M')}"


class Lead(TenantModel):
    STATUS_CHOICES = (
        ('open', 'Open'),
        ('won', 'Won'),
        ('lost', 'Lost'),
        ('first_lesson', 'Birinchi darsga yozilganlar'),
    )
    name = models.CharField(max_length=255)
    phone = models.CharField(max_length=50)
    email = models.EmailField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='open')

    pipeline = models.ForeignKey(Pipeline, on_delete=models.SET_NULL, null=True, blank=True, related_name="leads")
    source = models.ForeignKey(Source, on_delete=models.SET_NULL, null=True, blank=True, related_name="leads")
    lost_reason = models.ForeignKey(LostReason, on_delete=models.SET_NULL, null=True, blank=True, related_name="leads")
    section = models.ForeignKey(Section, on_delete=models.SET_NULL, null=True, blank=True, related_name="leads")

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_leads"
    )
    comment = models.TextField(null=True, blank=True)

    contacted_at = models.DateTimeField(null=True, blank=True)
    next_contact_at = models.DateTimeField(null=True, blank=True)
    reminder_time = models.DateTimeField(null=True, blank=True)
    notes = models.JSONField(default=list, blank=True)
    reminder_deadline = models.DateTimeField(null=True, blank=True, help_text="Lidning muddati (Sana va vaqt)")

    # 🚀 2-RASM UCHUN: Referal tizimi (Ushbu lidni qaysi o'quvchi tavsiya qildi/tashlab berdi)
    # Eslatma: 'academics.Student' o'rniga o'zingizning o'quvchi model yo'lingizni yozing
    referred_by = models.ForeignKey(
        'academics.Student',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='referred_crm_leads',
        verbose_name="Referal bergan o'quvchi"
    )

    # 🚀 4-RASM UCHUN: Mas'ul moderator biriktirish
    moderator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='responsible_crm_leads',
        verbose_name="Biriktirilgan moderator"
    )

    # 🚀 4-RASM UCHUN: Talabaning qarzdorlik limiti (Default: 0.00 UZS)
    debt_limit = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0.00,
        verbose_name="Qarzdorlik limiti"
    )

    # 🚀 4-RASM UCHUN: Talaba va Ota-ona uchun tizim kirish login-parollari
    student_login = models.CharField(max_length=150, null=True, blank=True, unique=True)
    student_password = models.CharField(max_length=128, null=True, blank=True)

    parent_login = models.CharField(max_length=150, null=True, blank=True, unique=True)
    parent_password = models.CharField(max_length=128, null=True, blank=True)

    is_archived = models.BooleanField(default=False)
    archive_reason = models.TextField(null=True, blank=True)
    archive_date = models.DateTimeField(null=True, blank=True)
    archived_by = models.CharField(max_length=255, null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=['organization', 'branch', 'status']),
            models.Index(fields=['organization', 'is_archived']),
            models.Index(fields=['organization', 'phone']),
            models.Index(fields=['organization', 'created_at']),
            models.Index(fields=['organization', 'pipeline', 'section']),
        ]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if self.phone:
            from common.utils import normalize_uz_phone
            normalized = normalize_uz_phone(self.phone)
            if normalized:
                self.phone = normalized
        super().save(*args, **kwargs)


class CRMActivity(TenantModel):
    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name="activities")
    activity_type = models.CharField(max_length=50)
    notes = models.TextField()
    date = models.DateField()

    def __str__(self):
        return f"{self.activity_type} - {self.lead.name}"


class CRMLeadsHistory(TenantModel):
    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name="history")
    change_details = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"History: {self.lead.name} at {self.created_at}"


class CRMLeadLost(TenantModel):
    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name="lost_records")
    lost_reason = models.ForeignKey(LostReason, on_delete=models.SET_NULL, null=True, blank=True,
                                    related_name="lost_records")
    notes = models.TextField(null=True, blank=True)

    def __str__(self):
        return f"Lost: {self.lead.name}"


@receiver(pre_save, sender=Lead)
def track_lead_changes(sender, instance, **kwargs):
    if not instance.pk:
        instance._old_status = None
        instance._old_name = None
        instance._old_phone = None
        instance._old_section = None
        instance._old_moderator_id = None
        return

    try:
        old_instance = Lead.objects.get(pk=instance.pk)
        instance._old_status = old_instance.status
        instance._old_name = old_instance.name
        instance._old_phone = old_instance.phone
        instance._old_section = old_instance.section
        instance._old_moderator_id = old_instance.moderator_id
    except Lead.DoesNotExist:
        pass


@receiver(post_save, sender=Lead)
def save_lead_history(sender, instance, created, **kwargs):
    changes = []

    if created:
        changes.append(f"Yangi lid yaratildi. Ismi: '{instance.name}', Telefon: {instance.phone}")
    else:
        if hasattr(instance, '_old_name') and instance._old_name != instance.name:
            changes.append(f"Lid ismi o'zgartirildi: '{instance._old_name}' -> '{instance.name}'")

        if hasattr(instance, '_old_phone') and instance._old_phone != instance.phone:
            changes.append(f"Telefon raqami o'zgargan: '{instance._old_phone}' -> '{instance.phone}'")

        if hasattr(instance, '_old_status') and instance._old_status != instance.status:
            changes.append(f"Lid holati (Status) o'zgardi: '{instance._old_status}' -> '{instance.status}'")

        if hasattr(instance, '_old_section') and instance._old_section != instance.section:
            old_sec = instance._old_section.name if instance._old_section else "Yo'q"
            new_sec = instance.section.name if instance.section else "Yo'q"
            changes.append(f"Bo'lim o'zgartirildi: '{old_sec}' -> '{new_sec}'")

    if changes:
        full_log = " | ".join(changes)
        CRMLeadsHistory.objects.create(
            organization=instance.organization,
            lead=instance,
            change_details=full_log
        )

    # Moderator biriktirilganda xodimgaga Telegram bildirishnoma yuborish
    old_mod = getattr(instance, '_old_moderator_id', None)
    should_notify = False
    if created and instance.moderator:
        should_notify = True
    elif not created and instance.moderator and old_mod != instance.moderator_id:
        should_notify = True

    if should_notify and instance.moderator:
        try:
            from communication.models import Notification
            lang = getattr(instance.moderator, 'telegram_language', 'uz') or 'uz'
            if lang == 'ru':
                title = f"🎯 Назначен новый лид: {instance.name}"
                msg = f"Вам назначен новый лид: {instance.name}\n📞 Телефон: {instance.phone}"
            else:
                title = f"🎯 Yangi lid biriktirildi: {instance.name}"
                msg = f"Sizga yangi lid biriktirildi: {instance.name}\n📞 Telefon: {instance.phone}"

            Notification.objects.create(
                organization=instance.organization,
                user=instance.moderator,
                title=title,
                message=msg,
                type='info'
            )
        except Exception as e:
            print(f"Error notifying lead moderator: {str(e)}")

    if created and instance.organization:
        try:
            from finance.models import send_telegram_payment_notification
            from django.utils import timezone as django_timezone
            created_at = getattr(instance, 'created_at', None) or django_timezone.now()
            exact_time = django_timezone.localtime(created_at).strftime("%d.%m.%Y %H:%M:%S")
            section_name = instance.section.name if instance.section else "Asosiy"
            mod_name = (instance.moderator.get_full_name() or instance.moderator.username) if instance.moderator else "Biriktirilmagan"
            text = (
                f"<b>🎯 Yangi Lid Keldi (CRM)!</b>\n\n"
                f"👤 <b>Mijoz:</b> {instance.name}\n"
                f"📞 <b>Telefon:</b> {instance.phone or 'Kiritilmagan'}\n"
                f"📌 <b>Bo'lim:</b> {section_name}\n"
                f"🧑‍💼 <b>Mas'ul xodim:</b> {mod_name}\n"
                f"🕒 <b>Vaqti:</b> <code>{exact_time}</code>"
            )
            send_telegram_payment_notification(instance.organization, text, 'other_payments')
        except Exception as e:
            print(f"Error sending lead notification to report bot: {str(e)}")