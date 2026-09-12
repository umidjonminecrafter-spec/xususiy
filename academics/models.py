from django.db import models
from django.conf import settings
from organizations.models import TenantModel

from organizations.models import Organization
from django.utils import timezone
import datetime

class TelegramVerification(models.Model):
    PURPOSE_CHOICES = (
        ('register', 'Ro‘yxatdan o‘tish'),
        ('forgot', 'Parolni tiklash'),
    )

    # O'quvchining telefon raqami (bu orqali bazadan o'quvchini topamiz)
    phone = models.CharField(max_length=50)
    # Tasdiqlash uchun 6 xonali random kod
    code = models.CharField(max_length=6)
    # Qaysi maqsadda yuborilgani
    purpose = models.CharField(max_length=20, choices=PURPOSE_CHOICES)
    # Kod yaratilgan vaqt
    created_at = models.DateTimeField(auto_now_add=True)
    # Kod ishlatildimi yoki yo'q
    is_verified = models.BooleanField(default=False)

    def is_valid(self):
        # Kod faqat 2 daqiqa davomida amal qiladi
        expiry_time = self.created_at + datetime.timedelta(minutes=2)
        return timezone.now() <= expiry_time and not self.is_verified

    def __str__(self):
        return f"{self.phone} - {self.code} ({self.purpose})"


class Course(TenantModel):
    name = models.CharField(max_length=255)
    description = models.TextField(null=True, blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    duration_weeks = models.IntegerField(default=12)
    code = models.CharField(max_length=50, null=True, blank=True)
    lesson_time = models.CharField(max_length=50, null=True, blank=True)
    image = models.ImageField(upload_to='course_images/', null=True, blank=True)
    color = models.CharField(max_length=30, blank=True, default='', verbose_name="Fan rangi (HEX/RGB)")
    is_active = models.BooleanField(default=True, verbose_name="Faol / Nofaol")

    def __str__(self):
        return self.name

class Room(TenantModel):
    name = models.CharField(max_length=100)
    capacity = models.IntegerField(default=30)
    comment = models.CharField(max_length=255, null=True, blank=True)

    def __str__(self):
        return self.name

class Student(TenantModel):
    first_name = models.CharField(max_length=150)
    last_name = models.CharField(max_length=150, null=True, blank=True)
    phone = models.CharField(max_length=50)
    email = models.EmailField(null=True, blank=True)
    balance = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    photo = models.ImageField(upload_to='student_photos/', null=True, blank=True)
    telegram_chat_id = models.CharField(max_length=100, null=True, blank=True, verbose_name="Telegram Chat ID")
    category = models.CharField(max_length=255, null=True, blank=True)
    birth_date = models.DateField(null=True, blank=True)
    application = models.TextField(null=True, blank=True)
    language = models.CharField(max_length=100, null=True, blank=True)
    payment_date = models.DateField(null=True, blank=True)
    address = models.TextField(null=True, blank=True)
    target_university = models.CharField(max_length=255, null=True, blank=True)

    # organization qatorini BUTUNLAY olib tashla

    father_name = models.CharField(max_length=255, null=True, blank=True)
    father_phone = models.CharField(max_length=50, null=True, blank=True)
    father_email = models.EmailField(null=True, blank=True)
    father_telegram_chat_id = models.CharField(max_length=100, null=True, blank=True, verbose_name="Otasining Telegram Chat IDsi")

    mother_name = models.CharField(max_length=255, null=True, blank=True)
    mother_phone = models.CharField(max_length=50, null=True, blank=True)
    mother_email = models.EmailField(null=True, blank=True)
    mother_telegram_chat_id = models.CharField(max_length=100, null=True, blank=True, verbose_name="Onasining Telegram Chat IDsi")
    referred_by = models.CharField(max_length=255, null=True, blank=True, verbose_name="Kim tavsiya qildi")
    moderator = models.IntegerField(null=True, blank=True,)  # Agar ID bo'lsa
    debt_limit = models.DecimalField(max_digits=10, decimal_places=2, default=0.00, null=True, blank=True,
                                     verbose_name="Qarzdorlik limiti")
    student_login = models.CharField(null=True, blank=True,)
    parent_login = models.CharField(null=True, blank=True,)
    is_archived = models.BooleanField(default=False)

    class Meta:
        indexes = [
            models.Index(fields=['organization', 'branch', 'is_archived']),
            models.Index(fields=['organization', 'phone']),
            models.Index(fields=['organization', 'balance']),
            models.Index(fields=['organization', 'created_at']),
        ]

    def __str__(self):
        if self.last_name:
            return f"{self.first_name} {self.last_name}"
        return self.first_name

    @property
    def full_name(self):
        if self.last_name:
            return f"{self.first_name} {self.last_name}"
        return self.first_name

    def save(self, *args, **kwargs):
        from common.utils import normalize_uz_phone
        if self.phone:
            normalized = normalize_uz_phone(self.phone)
            if normalized:
                self.phone = normalized
        if self.father_phone:
            normalized = normalize_uz_phone(self.father_phone)
            if normalized:
                self.father_phone = normalized
        if self.mother_phone:
            normalized = normalize_uz_phone(self.mother_phone)
            if normalized:
                self.mother_phone = normalized

        if self.pk:
            try:
                orig = Student.objects.get(pk=self.pk)
                if orig.phone != self.phone:
                    self.telegram_chat_id = None
                if orig.father_phone != self.father_phone:
                    self.father_telegram_chat_id = None
                if orig.mother_phone != self.mother_phone:
                    self.mother_telegram_chat_id = None
            except Student.DoesNotExist:
                pass
        super().save(*args, **kwargs)


class StudentFieldSetting(TenantModel):

    FIELD_CHOICES = [
        ("last_name", "Familiya"),
        ("email", "Elektron pochta"),
        ("photo", "Rasm"),
        ("category", "Kategoriya"),
        ("birth_date", "Tug'ilgan sana"),
        ("application", "So'rovnoma"),
        ("language", "Til"),
        ("payment_date", "To'lov sanasi"),
        ("address", "Uy manzili"),
        ("target_university", "Maqsad qilgan universitet"),
        ("organization", "Tashkilot"),
        ("father_name", "Otasining ismi"),
        ("father_phone", "Otasining telefon raqami"),
        ("father_email", "Otasining elektron pochtasi"),
        ("mother_name", "Onasining ismi"),
        ("mother_phone", "Onasining telefon raqami"),
        ("mother_email", "Onasining elektron pochtasi"),
    ]
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="student_field_settings"
    )

    field_name = models.CharField(
        max_length=100,
        choices=FIELD_CHOICES
    )
    is_required = models.BooleanField(default=False)


class Group(TenantModel):
    STATUS_CHOICES = (
        ('active', 'Active'),
        ('archived', 'Archived'),
        ('upcoming', 'Upcoming'),
        ('pending', 'Pending'),  # 🚀 QO'SHILDI: Kutayotgan statusi
    )
    EDUCATION_TYPE_CHOICES = (
        ('online', 'Online'),
        ('offline', 'Offline'),
    )

    name = models.CharField(max_length=255)
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="groups")
    room = models.ForeignKey(Room, on_delete=models.SET_NULL, null=True, blank=True, related_name="groups")
    teacher = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                related_name="teaching_groups")

    # 🚀 QO'SHILDI: Yordamchi o'qituvchi maydoni
    assistant_teacher = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                          related_name="assisting_groups")

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')

    # 🚀 QO'SHILDI: Ta'lim turi va Telegram guruh linki
    education_type = models.CharField(max_length=20, choices=EDUCATION_TYPE_CHOICES, default='offline')
    telegram_link = models.URLField(null=True, blank=True, max_length=500)

    # 🚀 O'ZGARTIRILDI: Dars kunlarini ko'p tanlovli ro'yxat (JSON) ko'rinishida saqlash
    # Masalan: ["Dushanba", "Chorshanba", "Juma"] yoki ["Mon", "Fri"]
    days = models.JSONField(default=list, blank=True, help_text="Dars kunlari ro'yxati")
    day_type = models.CharField(max_length=50, null=True, blank=True)  # eski maydon saqlandi

    start_time = models.TimeField(null=True, blank=True)
    end_time = models.TimeField(null=True, blank=True)  # 🚀 QO'SHILDI: Dars tugash vaqti
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=['organization', 'branch', 'status']),
            models.Index(fields=['course', 'status']),
            models.Index(fields=['teacher', 'status']),
            models.Index(fields=['organization', 'created_at']),
        ]

    def __str__(self):
        return self.name

class StudentGroup(TenantModel):
    # TO'G'RILANDI: on_delete=models.SET_NULL qilindi.
    student = models.ForeignKey(Student, on_delete=models.SET_NULL, null=True, blank=True, related_name="student_groups")
    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name="group_students")
    joined_at = models.DateTimeField(auto_now_add=True)
    price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=['organization', 'group', 'student']),
            models.Index(fields=['student', 'group']),
        ]

    def save(self, *args, **kwargs):
        # Guruhdagi kursning joriy narxini muzlatib saqlaymiz (agar narx berilmagan bo'lsa)
        if self.price is None and self.group and self.group.course:
            self.price = self.group.course.price
        
        # Guruhning filialini va tashkilotini StudentGroup'ga ham o'rnatamiz
        if self.group:
            if not self.branch_id and self.group.branch_id:
                self.branch_id = self.group.branch_id
            if not self.organization_id and self.group.organization_id:
                self.organization_id = self.group.organization_id

        super().save(*args, **kwargs)

    def __str__(self):
        student_name = self.student if self.student else "O'chirilgan Talaba"
        return f"{student_name} in {self.group}"

class GroupTeacher(TenantModel):
    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name="group_teachers")
    teacher = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="teacher_groups")

    class Meta:
        unique_together = ('group', 'teacher')

    def save(self, *args, **kwargs):
        if self.group:
            if not self.branch_id and self.group.branch_id:
                self.branch_id = self.group.branch_id
            if not self.organization_id and self.group.organization_id:
                self.organization_id = self.group.organization_id
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.teacher} for {self.group}"

class TeacherSalaryPayment(TenantModel):
    teacher = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="salary_payments")
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    paid_at = models.DateTimeField(auto_now_add=True)
    period = models.CharField(max_length=20) # e.g. "2026-05"

    def __str__(self):
        return f"{self.teacher} - {self.amount} for {self.period}"

class Attendance(TenantModel):
    STATUS_CHOICES = (
        ('present', 'Present'),
        ('absent', 'Absent'),
        ('late', 'Late'),
        ('excused', 'Excused'),
    )
    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name="attendances")
    # TO'G'RILANDI: on_delete=models.SET_NULL qilindi. Eski davomatlar o'chib ketmaydi.
    student = models.ForeignKey(Student, on_delete=models.SET_NULL, null=True, blank=True, related_name="attendances")
    date = models.DateField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='present')
    grade = models.IntegerField(null=True, blank=True)
    reason = models.CharField(max_length=255, null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=['organization', 'group', 'date']),
            models.Index(fields=['student', 'date']),
            models.Index(fields=['group', 'date', 'status']),
        ]

    def save(self, *args, **kwargs):
        if self.group:
            if not self.branch_id and self.group.branch_id:
                self.branch_id = self.group.branch_id
            if not self.organization_id and self.group.organization_id:
                self.organization_id = self.group.organization_id
        super().save(*args, **kwargs)

    def __str__(self):
        student_name = self.student if self.student else "O'chirilgan Talaba"
        return f"{student_name} - {self.group} ({self.date}): {self.status}"

class LessonSchedule(TenantModel):
    DAY_TYPE_CHOICES = (
        ('even', 'Even Days (Juft kunlar)'),
        ('odd', 'Odd Days (Toq kunlar)'),
    )
    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name="schedules")
    room_name = models.CharField(max_length=255)
    teacher = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="schedules")
    start_time = models.TimeField()
    end_time = models.TimeField()
    day_type = models.CharField(max_length=10, choices=DAY_TYPE_CHOICES, default='even')

    def __str__(self):
        return f"{self.group} - {self.room_name} ({self.start_time}-{self.end_time})"

    @classmethod
    def _sync_group_start_time(cls, group_id, organization_id):
        if not group_id:
            return

        next_start_time = (
            cls.objects.filter(group_id=group_id, organization_id=organization_id)
            .order_by('start_time', 'id')
            .values_list('start_time', flat=True)
            .first()
        )
        Group.objects.filter(id=group_id).update(start_time=next_start_time)

    def save(self, *args, **kwargs):
        if self.group:
            if not self.branch_id and self.group.branch_id:
                self.branch_id = self.group.branch_id
            if not self.organization_id and self.group.organization_id:
                self.organization_id = self.group.organization_id

        previous_group_id = None
        previous_organization_id = None
        if self.pk:
            previous = LessonSchedule.objects.filter(pk=self.pk).values('group_id', 'organization_id').first()
            if previous:
                previous_group_id = previous['group_id']
                previous_organization_id = previous['organization_id']

        super().save(*args, **kwargs)
        self._sync_group_start_time(self.group_id, self.organization_id)
        if previous_group_id and previous_group_id != self.group_id:
            self._sync_group_start_time(previous_group_id, previous_organization_id)

    def delete(self, *args, **kwargs):
        group_id = self.group_id
        organization_id = self.organization_id
        super().delete(*args, **kwargs)
        self._sync_group_start_time(group_id, organization_id)

class BalanceHistory(TenantModel):
    # TO'G'RILANDI: on_delete=models.SET_NULL qilindi. Moliyaviy loglar saqlanib qoladi!
    student = models.ForeignKey(Student, on_delete=models.SET_NULL, null=True, blank=True, related_name="balance_histories")
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    transaction_type = models.CharField(max_length=255) # deposit, withdrawal, etc.
    date = models.DateField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['organization', 'student', 'date']),
            models.Index(fields=['student', 'date']),
        ]

    def __str__(self):
        student_name = self.student if self.student else "O'chirilgan Talaba"
        return f"{student_name} - {self.amount} ({self.transaction_type})"

class Exam(TenantModel):
    name = models.CharField(max_length=255)
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="exams")
    group = models.ForeignKey('academics.Group', on_delete=models.CASCADE, related_name="exams", null=True, blank=True)
    date = models.DateField()
    min_score = models.IntegerField(default=60)
    max_score = models.IntegerField(default=100)

    def save(self, *args, **kwargs):
        if self.group:
            if not self.branch_id and self.group.branch_id:
                self.branch_id = self.group.branch_id
            if not self.organization_id and self.group.organization_id:
                self.organization_id = self.group.organization_id
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

class ExamResult(TenantModel):
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name="results")
    # TO'G'RILANDI: on_delete=models.SET_NULL qilindi.
    student = models.ForeignKey(Student, on_delete=models.SET_NULL, null=True, blank=True, related_name="exam_results")
    score = models.DecimalField(max_digits=5, decimal_places=2)

    def __str__(self):
        student_name = self.student if self.student else "O'chirilgan Talaba"
        return f"{student_name} - {self.exam.name}: {self.score}"

class LeaveReason(TenantModel):
    reason = models.CharField(max_length=255)

    def __str__(self):
        return self.reason

class LessonTime(TenantModel):
    name = models.CharField(max_length=100)
    start_time = models.TimeField()
    end_time = models.TimeField()

    def __str__(self):
        return f"{self.name} ({self.start_time}-{self.end_time})"


class OnlineLesson(TenantModel):
    title = models.CharField(max_length=255)
    group = models.ForeignKey(Group, on_delete=models.SET_NULL, null=True, blank=True, related_name="online_lessons")

    # 🛠️ TO'G'RILANDI: Bo'sh dars ochilishi uchun video_url ixtiyoriy qilindi
    video_url = models.URLField(null=True, blank=True)
    description = models.TextField(null=True, blank=True, verbose_name="Dars tavsifi")
    is_published = models.BooleanField(default=False)

    # 🛠️ Qaysi davomat kunidan ochilganini bilishimiz uchun bog'liqlik zanjiri:
    attendance_date = models.DateField(null=True, blank=True, verbose_name="Bog'langan dars sanasi")

    def save(self, *args, **kwargs):
        if self.group:
            if not self.branch_id and self.group.branch_id:
                self.branch_id = self.group.branch_id
            if not self.organization_id and self.group.organization_id:
                self.organization_id = self.group.organization_id
        super().save(*args, **kwargs)

    def __str__(self):
        return self.title

class CourseMaterial(TenantModel):
    """Kurs materiallari: video, fayl, havola, rasm va boshqalar"""
    MATERIAL_TYPE_CHOICES = (
        ('video', 'Video'),
        ('file', 'Fayl (PDF, Word va b.)'),
        ('link', 'Havola (Link)'),
        ('image', 'Rasm'),
        ('text', 'Matn'),
    )

    course = models.ForeignKey(
        Course, on_delete=models.CASCADE, related_name='materials',
        verbose_name="Kurs"
    )
    title = models.CharField(max_length=255, verbose_name="Material nomi")
    description = models.TextField(null=True, blank=True, verbose_name="Tavsif")
    material_type = models.CharField(
        max_length=20, choices=MATERIAL_TYPE_CHOICES, default='file',
        verbose_name="Material turi"
    )
    file = models.FileField(
        upload_to='course_materials/', null=True, blank=True,
        verbose_name="Fayl"
    )
    video_url = models.URLField(null=True, blank=True, verbose_name="Video havolasi")
    external_link = models.URLField(null=True, blank=True, verbose_name="Tashqi havola")
    order = models.PositiveIntegerField(default=0, verbose_name="Tartib raqami")
    is_published = models.BooleanField(default=True, verbose_name="Nashr qilinganmi?")

    class Meta:
        ordering = ['order', 'id']

    def __str__(self):
        return f"{self.course.name} - {self.title}"


class StudentGroupLeave(TenantModel):
    # TO'G'RILANDI: on_delete=models.SET_NULL qilindi.
    student = models.ForeignKey(Student, on_delete=models.SET_NULL, null=True, blank=True, related_name="group_leaves")
    student_name = models.CharField(max_length=255, null=True, blank=True)
    student_phone = models.CharField(max_length=50, null=True, blank=True)
    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name="student_leaves")
    leave_reason = models.ForeignKey(LeaveReason, on_delete=models.SET_NULL, null=True, blank=True, related_name="student_leaves")
    leave_date = models.DateField()
    comment = models.TextField(null=True, blank=True)
    refound_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    is_archived = models.BooleanField(default=False)
    is_sent_to_leads = models.BooleanField(default=False)

    def save(self, *args, **kwargs):
        if self.student:
            if not self.student_name:
                self.student_name = f"{self.student.first_name} {self.student.last_name or ''}".strip()
            if not self.student_phone:
                self.student_phone = self.student.phone or ""
        super().save(*args, **kwargs)

    def __str__(self):
        student_name = self.student if self.student else (self.student_name or "O'chirilgan Talaba")
        return f"{student_name} left {self.group}"

class StudentPricing(TenantModel):
    # TO'G'RILANDI: on_delete=models.SET_NULL qilindi.
    student = models.ForeignKey(Student, on_delete=models.SET_NULL, null=True, blank=True, related_name="pricings")
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="student_pricings")
    custom_price = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        student_name = self.student if self.student else "O'chirilgan Talaba"
        return f"{student_name} - {self.course.name}: {self.custom_price}"

class StudentArchive(TenantModel):
    first_name = models.CharField(max_length=150)
    last_name = models.CharField(max_length=150, null=True, blank=True)
    phone = models.CharField(max_length=50)
    email = models.EmailField(null=True, blank=True)
    role = models.CharField(max_length=50, default="Student")
    reason = models.CharField(max_length=255, null=True, blank=True)
    comment = models.TextField(null=True, blank=True)
    archived_by = models.CharField(max_length=255, null=True, blank=True)
    date = models.DateField(auto_now_add=True)

    def __str__(self):
        return f"{self.first_name} {self.last_name or ''} (Archived)"

class Holiday(TenantModel):
    name = models.CharField(max_length=255)
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    student_impact = models.BooleanField(default=False)
    staff_impact = models.BooleanField(default=False)

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.end_date and self.end_date < self.start_date:
            raise ValidationError("End date cannot be earlier than start date.")

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class Homework(TenantModel):
    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name="homeworks")
    title = models.CharField(max_length=255)
    text = models.TextField(null=True, blank=True)
    image = models.ImageField(upload_to='group_homeworks/images/', null=True, blank=True)
    video = models.FileField(upload_to='group_homeworks/videos/', null=True, blank=True)
    file = models.FileField(upload_to='group_homeworks/files/', null=True, blank=True)
    due_date = models.DateField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="group_homeworks_created",
    )

    def save(self, *args, **kwargs):
        if self.group:
            if not self.branch_id and self.group.branch_id:
                self.branch_id = self.group.branch_id
            if not self.organization_id and self.group.organization_id:
                self.organization_id = self.group.organization_id
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.group.name} - {self.title}"



from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver

@receiver(post_save, sender=Exam)
def exam_internal_notification(sender, instance, created, **kwargs):
    """
    Yangi imtihon yaratilganda guruh o'qituvchilariga tizim ichida bildirishnoma yuboradi.
    """
    if created:
        group = instance.group
        course_name = instance.course.name if instance.course else "Kurs nomi noma'lum"

        if group:
            title = f"Yangi imtihon e'lon qilindi: {instance.name}"
            message = (
                f"Sizning '{group.name}' guruhingiz uchun '{course_name}' kursi bo'yicha imtihon belgilandi.\n"
                f"Sana: {instance.date}\n"
                f"O'tish bali: {instance.min_score} / Max ball: {instance.max_score}"
            )

            from communication.models import Notification

            teachers_to_notify = []
            if group.teacher:
                teachers_to_notify.append(group.teacher)

            additional_teachers = group.group_teachers.select_related('teacher').all()
            for gt in additional_teachers:
                if gt.teacher and gt.teacher not in teachers_to_notify:
                    teachers_to_notify.append(gt.teacher)

            for teacher in teachers_to_notify:
                Notification.objects.create(
                    organization=instance.organization,
                    user=teacher,
                    title=title,
                    message=message,
                    type='info',
                    is_read=False
                )


@receiver(post_save, sender=Holiday)
def holiday_internal_notification(sender, instance, created, **kwargs):
    """
    Yangi dam olish kuni (Bayram) e'lon qilinganda xodimlarga bildirishnoma yuboradi.
    """
    if created and instance.staff_impact:
        end_date_str = f" dan {instance.end_date} gacha" if instance.end_date else " kuni"
        title = f"Diqqat: Dam olish kuni — {instance.name}"
        message = (
            f"Hurmatli hamkasblar, tizimda yangi dam olish kuni e'lon qilindi.\n"
            f"Bayram: {instance.name}\n"
            f"Muddati: {instance.start_date}{end_date_str}.\n"
            f"Shu munosabat bilan dars jadvallaringizni muvofiqlashtirishingizni so'raymiz."
        )

        from django.contrib.auth import get_user_model
        from communication.models import Notification
        User = get_user_model()

        users = User.objects.filter(is_active=True, organization=instance.organization)

        notifications_pool = []
        for user in users:
            notifications_pool.append(
                Notification(
                    organization=instance.organization,
                    user=user,
                    title=title,
                    message=message,
                    type='info',
                    is_read=False
                )
            )

        if notifications_pool:
            Notification.objects.bulk_create(notifications_pool)


class BotMessageTemplate(TenantModel):
    # 🎯 SHABLON QAYSI AUDITORIYA UCHUN EKANLIGINI FILTRLASH
    AUDIENCE_CHOICES = (
        ('leads', 'Lidlar (CRM)'),
        ('students', 'Talabalar (Academics)'),
        ('staff', 'Xodimlar (Staff)'),
    )

    TEMPLATE_TYPES = (
        ('telegram', 'Telegram'),
        ('sms', 'SMS'),
        # CRM (Lidlar) uchun shablonlar
        ('lead_marketing', 'Lid: Reklama/Aksiya xabari'),
        ('lead_holiday', 'Lid: Bayram tabrigi'),
        ('lead_followup', 'Lid: Qayta aloqa/Eslatma'),

        # Talabalar uchun shablonlar
        ('remind', 'Talaba: Dars eslatmasi (Darsga chaqiriq)'),
        ('payment_due', 'Talaba: To‘lov vaqti kelganda ogohlantirish'),
        ('payment_success', 'Talaba: To‘lov muvaffaqiyatli bo‘lganda chek'),
        ('news', 'Talaba: Umumiy yangiliklar'),

        # Ota-onalar uchun shablonlar
        ('parent_check_in', 'Ota-ona: Farzandi darsga kelganda'),
        ('parent_check_out', 'Ota-ona: Dars tugaganda (ketganda)'),
        ('parent_exam_result', 'Ota-ona: Imtihon baholari chiqganda'),
        ('parent_payment_due', 'Ota-ona: To‘lov vaqti kelganda'),

        # Xodimlar uchun shablonlar
        ('staff_general_news', 'Xodimlar: Boshliqdan umumiy xabar/topshiriq'),
        ('staff_salary_remind', 'Xodimlar: Oylik to‘lov eslatmasi'),
        ('staff_holiday_remind', 'Xodimlar: Bayram va dam olish kuni eslatmasi'),
    )

    title = models.CharField(max_length=150, verbose_name="Shablon nomi")
    target_audience = models.CharField(max_length=20, choices=AUDIENCE_CHOICES, default='students',
                                       verbose_name="Kimlar uchun")
    template_type = models.CharField(max_length=30, choices=TEMPLATE_TYPES, verbose_name="Turi")
    text = models.TextField(
        verbose_name="Xabar matni",
        help_text="O'zgaruvchilarni jingalak qavs ichida yozing, masalan: {first_name}, {balance}, {section_name}"
    )
    is_active = models.BooleanField(default=True, verbose_name="Faolmi?")

    class Meta:
        # unique_together olib tashlandi, chunki bitta turda bir nechta marketing SMS shablonlari bo'lishi mumkin (Rasmda ko'ringandek)
        verbose_name = "Bot Xabar Shabloni"
        verbose_name_plural = "Bot Xabar Shablonlari"

    def __str__(self):
        return f"[{self.get_target_audience_display()}] {self.title}"

# NOTE: notify_parent_attendance olib tashlandi — notify_attendance_saved (pastda)
# ham o'quvchi botiga, ham ota-ona botiga xabar yuboradi. Bu dublikat edi.

class StudentEvaluationLevel(TenantModel):
    """O'quvchilarni baholash darajalari (Nomi, Min/Max foiz va Rangi)"""
    name = models.CharField(max_length=255) # Masalan: "A'lochi", "Yaxshi"
    min_percent = models.PositiveIntegerField(default=0)
    max_percent = models.PositiveIntegerField(default=100)
    color = models.CharField(max_length=50, default="#FFFFFF") # HEX color code uchun

    def __str__(self):
        return f"{self.name} ({self.min_percent}% - {self.max_percent}%)"


class GroupLesson(TenantModel):
    """Guruhning yo'qlamadan mustaqil, kalendardagi har bitta dars kuni"""
    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name="lessons")
    date = models.DateField(verbose_name="Dars sanasi")

    # Mavzu va izoh
    title = models.CharField(max_length=255, null=True, blank=True, verbose_name="Dars mavzusi")
    description = models.TextField(null=True, blank=True, verbose_name="Dars izohi")

    # Bekor qilish va ko'chirish maydonlari
    is_canceled = models.BooleanField(default=False, verbose_name="Dars bekor qilinganmi?")
    original_date = models.DateField(null=True, blank=True, verbose_name="Asl sanasi")

    def __str__(self):
        return f"{self.group.name} - {self.date} - {self.title or 'Mavzusiz'}"



@receiver(post_save, sender=GroupLesson)
def sync_group_lesson_with_lms(sender, instance, created, **kwargs):
    if not instance.title:
        return

    # Guruh dars kuniga qarab LMS darsini qidiramiz
    online_lesson = OnlineLesson.objects.filter(
        group=instance.group,
        video_url__isnull=True, # faqat avtomat ochilgan bo'sh darslarni topish uchun
        title=instance.title
    ).first()

    if not online_lesson:
        OnlineLesson.objects.create(
            organization=instance.organization,
            group=instance.group,
            title=instance.title,
            is_published=True
        )


import datetime




def generate_group_lessons(group_instance):
    """Guruhning boshlanish va tugash sanasi oralig'idagi dars kunlarini yaratadi"""
    if not group_instance.start_date or not group_instance.end_date:
        return

    current_date = group_instance.start_date
    delta = datetime.timedelta(days=1)

    # Kunlarni matn ko'rinishiga keltiramiz
    day_type = ""
    if isinstance(group_instance.days, list):
        day_type = " ".join([str(d).lower().strip() for d in group_instance.days])
    elif group_instance.days:
        day_type = str(group_instance.days).lower().strip()

    if not day_type and group_instance.day_type:
        day_type = str(group_instance.day_type).lower().strip()

    lessons_to_create = []

    while current_date <= group_instance.end_date:
        weekday = current_date.weekday()
        should_create = False

        # Juft kunlar: Tue (Seshanba=1), Thu (Payshanba=3), Sat (Shanba=5)
        if any(x in day_type for x in ['seshanba', 'payshanba', 'shanba', 'tue', 'thu', 'sat', '2', '4', '6']):
            if weekday in [1, 3, 5]:
                should_create = True
        # Toq kunlar: Mon (Dushanba=0), Wed (Chorshanba=2), Fri (Juma=4)
        elif any(x in day_type for x in ['dushanba', 'chorshanba', 'juma', 'mon', 'wed', 'fri', '1', '3', '5']):
            if weekday in [0, 2, 4]:
                should_create = True
        else:
            if weekday != 6:  # Yakshanbadan tashqari hammasi
                should_create = True

        if should_create:
            if not GroupLesson.objects.filter(group=group_instance, date=current_date).exists():
                lessons_to_create.append(
                    GroupLesson(
                        organization=group_instance.organization,
                        group=group_instance,
                        date=current_date
                    )
                )
        current_date += delta

    if lessons_to_create:
        GroupLesson.objects.bulk_create(lessons_to_create)


@receiver(post_save, sender=Group)
def trigger_lesson_generation(sender, instance, created, **kwargs):
    """Guruh saqlanganda LessonSchedule va GroupLessonni avtomat yaratadi (Admin panel uchun ham)"""
    # Agar view orqali _sync_lesson_schedules allaqachon ishlagan bo'lsa, qayta yaratmaymiz
    if getattr(instance, '_skip_signal_sync', False):
        return

    try:
        # 1. Taqvim kunlarini yaratish
        generate_group_lessons(instance)

        # 2. Dars jadvalini yaratish mantiqi
        LessonSchedule.objects.filter(group=instance).delete()

        if instance.start_time and instance.end_time:
            days_combined = ""
            if isinstance(instance.days, list):
                days_combined = " ".join([str(d).lower().strip() for d in instance.days])
            elif instance.days:
                days_combined = str(instance.days).lower().strip()

            if not days_combined and instance.day_type:
                days_combined = str(instance.day_type).lower().strip()

            # Juft kunlar: Seshanba(Tue), Payshanba(Thu), Shanba(Sat) -> even
            is_even = any(
                x in days_combined for x in ['seshanba', 'payshanba', 'shanba', 'tue', 'thu', 'sat', '2', '4', '6'])
            # Toq kunlar: Dushanba(Mon), Chorshanba(Wed), Juma(Fri) -> odd
            is_odd = any(x in days_combined for x in ['dushanba', 'chorshanba', 'juma', 'mon', 'wed', 'fri', '1', '3', '5'])

            if is_even and not is_odd:
                calculated_day_type = 'even'   # Seshanba-Payshanba-Shanba = Juft kunlar
            else:
                calculated_day_type = 'odd'    # Dushanba-Chorshanba-Juma = Toq kunlar

            LessonSchedule.objects.create(
                organization=instance.organization,
                group=instance,
                room_name=instance.room.name if instance.room else "Xona biriktirilmagan",
                teacher=instance.teacher,
                start_time=instance.start_time,
                end_time=instance.end_time,
                day_type=calculated_day_type
            )
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"trigger_lesson_generation signalida xatolik: {e}")


# ================= TALABA DAVOMATIGA QARAB BALANSDAN PUL YECHISH VA KASSA INTEGRATSIYASI =================
from django.db.models.signals import pre_save, post_save, post_delete
from django.dispatch import receiver

def get_lessons_in_month(group, year, month):
    # 1. First, try to count from GroupLesson table
    count = GroupLesson.objects.filter(
        group=group,
        date__year=year,
        date__month=month
    ).count()
    if count > 0:
        return count
    
    # 2. If 0, compute based on group days schedule
    import calendar
    _, num_days = calendar.monthrange(year, month)
    
    # Normalize group days
    day_type = ""
    if isinstance(group.days, list):
        day_type = " ".join([str(d).lower().strip() for d in group.days])
    elif group.days:
        day_type = str(group.days).lower().strip()

    if not day_type and group.day_type:
        day_type = str(group.day_type).lower().strip()
        
    count = 0
    for d in range(1, num_days + 1):
        curr_date = datetime.date(year, month, d)
        weekday = curr_date.weekday()
        
        should_count = False
        # Juft kunlar: Seshanba, Payshanba, Shanba (Tue, Thu, Sat)
        if any(x in day_type for x in ['seshanba', 'payshanba', 'shanba', 'tue', 'thu', 'sat', '2', '4', '6']):
            if weekday in [1, 3, 5]:
                should_count = True
        # Toq kunlar: Dushanba, Chorshanba, Juma (Mon, Wed, Fri)
        elif any(x in day_type for x in ['dushanba', 'chorshanba', 'juma', 'mon', 'wed', 'fri', '1', '3', '5']):
            if weekday in [0, 2, 4]:
                should_count = True
        else:
            if weekday != 6: # Yakshanbadan tashqari
                should_count = True
                
        if should_count:
            count += 1
            
    if count > 0:
        return count
    return 12  # default fallback if no schedule is found


def charge_attendance(student, group, date, attendance_id, organization):
    from decimal import Decimal
    from finance.models import Cashbox, Transaction
    
    # Calculate monthly price
    monthly_price = Decimal('0.00')
    sg = StudentGroup.objects.filter(student=student, group=group).first()
    if sg and sg.price is not None:
        monthly_price = Decimal(str(sg.price))
    elif group.course:
        monthly_price = Decimal(str(group.course.price))

    # Apply Auto-Discount from settings if enabled
    try:
        from finance.models import FinanceSetting
        setting = FinanceSetting.objects.filter(organization=organization).first()
        if setting and setting.is_auto_discount_enabled:
            groups_count = StudentGroup.objects.filter(student=student).count()
            discount_percent = Decimal('0.00')
            if groups_count == 2:
                discount_percent = Decimal(str(setting.two_groups_discount_percent))
            elif groups_count == 3:
                discount_percent = Decimal(str(setting.three_groups_discount_percent))
            elif groups_count >= 4:
                discount_percent = Decimal(str(setting.four_groups_discount_percent))
            
            if discount_percent > 0:
                monthly_price = monthly_price * (Decimal('1.00') - (discount_percent / Decimal('100.00')))
    except Exception as e:
        print(f"Error applying auto discount: {str(e)}")
        
    # Get lessons count in month
    lessons_in_month = get_lessons_in_month(group, date.year, date.month)
    lesson_cost = monthly_price / Decimal(lessons_in_month)
    lesson_cost = round(lesson_cost, 2)
    
    # Get or create Cashbox (preferring the group's branch)
    group_branch_id = getattr(group, 'branch_id', None)
    cashbox = None
    if group_branch_id:
        cashbox = Cashbox.objects.filter(organization=organization, branch_id=group_branch_id, is_archived=False).first()
    if not cashbox:
        cashbox = Cashbox.objects.filter(organization=organization, is_archived=False).first()
    if not cashbox:
        cashbox = Cashbox.objects.filter(organization=organization).first()
    if not cashbox:
        cashbox = Cashbox.objects.create(organization=organization, name="Asosiy kassa", branch_id=group_branch_id)
        
    # Check if transaction already exists
    desc_prefix = f"Davomat #{attendance_id}:"
    tx = Transaction.objects.filter(description__startswith=desc_prefix).first()
    
    if tx:
        old_amount = tx.amount
        diff = lesson_cost - old_amount
        
        # Agar ko'proq pul yechilishi kerak bo'lsa, balansi yetishini tekshiramiz
        if diff > 0 and Decimal(str(student.balance)) < diff:
            print(f"[BALANCE_WARNING] Talaba {student} balansida mablag' yetarli emas: "
                  f"balans={student.balance}, kerak={diff}")
        
        # Update transaction
        tx.amount = lesson_cost
        tx.cashbox = cashbox
        tx.student = student
        tx.description = f"{desc_prefix} {student} - {group.name} ({date})"
        tx.save()
        
        # Adjust student's balance
        student.balance = Decimal(str(student.balance)) - diff
        student.save(update_fields=['balance'])
        
        # BalanceHistory yaratish (telegram xabar uchun)
        if diff != 0:
            try:
                BalanceHistory.objects.create(
                    organization=organization,
                    student=student,
                    amount=-diff,
                    transaction_type=f"Davomat yangilandi ({group.name})"
                )
            except Exception:
                pass
    else:
        # Balans yetishini tekshirish
        if Decimal(str(student.balance)) < lesson_cost:
            print(f"[BALANCE_WARNING] Talaba {student} balansida mablag' yetarli emas: "
                  f"balans={student.balance}, kerak={lesson_cost}")
        
        # Create new transaction
        Transaction.objects.create(
            organization=organization,
            branch_id=group_branch_id,
            cashbox=cashbox,
            amount=lesson_cost,
            type='INCOME',
            category='DIRECT',
            student=student,
            description=f"{desc_prefix} {student} - {group.name} ({date})"
        )
        
        # Deduct from student's balance
        student.balance = Decimal(str(student.balance)) - lesson_cost
        student.save(update_fields=['balance'])

        try:
            BalanceHistory.objects.create(
                organization=organization,
                student=student,
                amount=-lesson_cost,
                transaction_type=f"Davomat ({group.name})"
            )
        except Exception:
            pass

    # Update teacher salary calculation if they have a percentage rule
    if group.teacher:
        teacher = group.teacher
        percentage = None
        if teacher.salary_percentage:
            percentage = Decimal(str(teacher.salary_percentage.percent))
        else:
            from finance.models import TeacherSalaryRule
            period = f"{date.year:04d}-{date.month:02d}"
            rule = TeacherSalaryRule.objects.filter(
                organization=organization,
                teacher=teacher,
                period=period,
                is_active=True
            ).first()
            if rule and rule.rule_type == 'percentage':
                percentage = Decimal(str(rule.rate))
        
        if percentage is not None:
            teacher_share = lesson_cost * (percentage / Decimal('100.00'))
            teacher_share = round(teacher_share, 2)
            
            from finance.models import TeacherSalaryCalculation
            period = f"{date.year:04d}-{date.month:02d}"
            calc, _ = TeacherSalaryCalculation.objects.get_or_create(
                organization=organization,
                teacher=teacher,
                period=period,
                defaults={'calculated_amount': Decimal('0.00')}
            )
            
            # Update details and calculate the new sum
            details = calc.details or {}
            attendance_charges = details.get('attendance_charges', {})
            attendance_charges[str(attendance_id)] = str(teacher_share)
            details['attendance_charges'] = attendance_charges
            
            # Recalculate sum of all charges
            total_sum = Decimal('0.00')
            for val in attendance_charges.values():
                total_sum += Decimal(str(val))
                
            calc.details = details
            calc.calculated_amount = total_sum
            calc.save()


def refund_attendance(student, group, date, attendance_id, organization):
    from decimal import Decimal
    from finance.models import Transaction
    
    desc_prefix = f"Davomat #{attendance_id}:"
    tx = Transaction.objects.filter(description__startswith=desc_prefix).first()
    
    if tx:
        amount_to_refund = tx.amount
        
        # Delete transaction first (signals will update cashbox balance automatically)
        tx.delete()
        
        # Refund student's balance
        student.balance = Decimal(str(student.balance)) + amount_to_refund
        student.save(update_fields=['balance'])
        
        # BalanceHistory yaratish — telegram xabar uchun
        try:
            BalanceHistory.objects.create(
                organization=organization,
                student=student,
                amount=amount_to_refund,
                transaction_type=f"Davomat qaytarildi ({group.name})"
            )
        except Exception:
            pass

    # Remove teacher salary calculation for this attendance
    if group.teacher:
        teacher = group.teacher
        from finance.models import TeacherSalaryCalculation
        period = f"{date.year:04d}-{date.month:02d}"
        calc = TeacherSalaryCalculation.objects.filter(
            organization=organization,
            teacher=teacher,
            period=period
        ).first()
        
        if calc and calc.details and 'attendance_charges' in calc.details:
            attendance_charges = calc.details['attendance_charges']
            if str(attendance_id) in attendance_charges:
                del attendance_charges[str(attendance_id)]
                
                # Recalculate sum of all charges
                total_sum = Decimal('0.00')
                for val in attendance_charges.values():
                    total_sum += Decimal(str(val))
                    
                calc.details['attendance_charges'] = attendance_charges
                calc.calculated_amount = total_sum
                calc.save()


@receiver(pre_save, sender=Attendance)
def attendance_pre_save(sender, instance, **kwargs):
    if instance.pk:
        try:
            old = Attendance.objects.get(pk=instance.pk)
            instance._old_status = old.status
            try:
                instance._old_student = old.student
            except Student.DoesNotExist:
                instance._old_student = None
            instance._old_group = old.group
            instance._old_date = old.date
        except Attendance.DoesNotExist:
            instance._old_status = None
            instance._old_student = None
            instance._old_group = None
            instance._old_date = None
    else:
        instance._old_status = None
        instance._old_student = None
        instance._old_group = None
        instance._old_date = None


@receiver(post_save, sender=Attendance)
def attendance_post_save(sender, instance, created, **kwargs):
    try:
        student = instance.student
    except Student.DoesNotExist:
        student = None
        
    # We only charge/refund if organization and student are valid
    if not student or not instance.group or not instance.organization:
        return
    
    # Check if the new state is billable
    new_is_billable = instance.status in ['present', 'late']
    
    # Determine the old state
    if created:
        old_is_billable = False
        old_student = None
        old_group = None
        old_date = None
    else:
        old_status = getattr(instance, '_old_status', None)
        old_is_billable = old_status in ['present', 'late'] if old_status else False
        old_student = getattr(instance, '_old_student', None)
        old_group = getattr(instance, '_old_group', None)
        old_date = getattr(instance, '_old_date', None)

    # If student/group/date changed on update, we reverse the old billable state (if it was billable)
    # and apply the new billable state.
    student_changed = old_student and old_student != student
    group_changed = old_group and old_group != instance.group
    date_changed = old_date and old_date != instance.date
    
    if not created and (student_changed or group_changed or date_changed):
        # Reverse old billable state for the old student/group/date
        if old_is_billable and old_student:
            # Refund the old student
            refund_attendance(
                student=old_student,
                group=old_group or instance.group,
                date=old_date or instance.date,
                attendance_id=instance.id,
                organization=instance.organization
            )
        # Apply new billable state for the new student/group/date
        if new_is_billable:
            charge_attendance(
                student=student,
                group=instance.group,
                date=instance.date,
                attendance_id=instance.id,
                organization=instance.organization
            )
    else:
        # Normal transition for same student/group/date
        if old_is_billable and not new_is_billable:
            # Refund
            refund_attendance(
                student=student,
                group=instance.group,
                date=instance.date,
                attendance_id=instance.id,
                organization=instance.organization
            )
        elif not old_is_billable and new_is_billable:
            # Charge
            charge_attendance(
                student=student,
                group=instance.group,
                date=instance.date,
                attendance_id=instance.id,
                organization=instance.organization
            )
        elif old_is_billable and new_is_billable:
            # Re-charge / update transaction
            charge_attendance(
                student=student,
                group=instance.group,
                date=instance.date,
                attendance_id=instance.id,
                organization=instance.organization
            )


@receiver(post_delete, sender=Attendance)
def attendance_post_delete(sender, instance, **kwargs):
    try:
        student = instance.student
    except Student.DoesNotExist:
        student = None
        
    if student and instance.group and instance.organization:
        was_billable = instance.status in ['present', 'late']
        if was_billable:
            refund_attendance(
                student=student,
                group=instance.group,
                date=instance.date,
                attendance_id=instance.id,
                organization=instance.organization
            )


@receiver(post_save, sender=BalanceHistory)
def notify_balance_change(sender, instance, created, **kwargs):
    """
    Har qanday balans o'zgarishida (yechish YOKI qo'shish) o'quvchi va ota-ona botiga xabar yuboradi.
    """
    if created and instance.student and instance.amount and instance.amount != 0:
        try:
            from academics.telegram_bot import send_telegram_message, get_student_bot_token
            from organizations.models import TelegramNotificationSetting
            from accounts.models import User
            from django.db.models import Q
            from django.utils import timezone as django_timezone

            student = instance.student
            amount_formatted = f"{int(abs(instance.amount)):,}".replace(",", " ")
            reason = instance.transaction_type or "Balans o'zgarishi"
            is_deduction = instance.amount < 0

            # Format exact time (HH:MM:SS)
            created_at = getattr(instance, 'created_at', None) or django_timezone.now()
            exact_time = django_timezone.localtime(created_at).strftime("%d.%m.%Y %H:%M:%S")

            # Who did it (Operator/Admin/Teacher)
            operator_name = getattr(instance, '_operator_name', None)
            if not operator_name and hasattr(instance, 'created_by') and instance.created_by:
                operator_name = instance.created_by.get_full_name() or instance.created_by.username
            if not operator_name and hasattr(instance.student, 'organization') and instance.student.organization:
                owner = User.objects.filter(organization=instance.student.organization, role__in=['owner', 'admin']).first()
                if owner:
                    operator_name = owner.get_full_name() or owner.username
            if not operator_name:
                operator_name = "Administrator / Tizim"

            # Resolve student_chat_id
            student_chat_id = getattr(student, 'telegram_chat_id', None)
            if not student_chat_id and student.phone:
                digits = "".join(c for c in student.phone if c.isdigit())
                last_9 = digits[-9:] if len(digits) >= 9 else digits
                matched_user = User.objects.filter(
                    Q(phone=student.phone) | Q(username=student.phone) |
                    (Q(phone__icontains=last_9) if last_9 else Q()) |
                    (Q(username__icontains=last_9) if last_9 else Q())
                ).filter(role='student', telegram_chat_id__isnull=False).first()
                if matched_user:
                    student_chat_id = matched_user.telegram_chat_id

            balance_formatted = f"{int(student.balance):,}".replace(",", " ")

            if student_chat_id:
                student_token = get_student_bot_token(instance.organization)

                if is_deduction:
                    st_msg = (
                        f"<b>📉 Balansingizdan pul yechildi!</b>\n\n"
                        f"💸 <b>Yechilgan summa:</b> {amount_formatted} UZS\n"
                        f"📝 <b>Sabab:</b> {reason}\n"
                        f"👤 <b>Yechgan:</b> {operator_name}\n"
                        f"🕒 <b>Vaqti:</b> <code>{exact_time}</code>\n"
                        f"💵 <b>Yangi balansingiz:</b> {balance_formatted} UZS"
                    )
                else:
                    st_msg = (
                        f"<b>📈 Balansingiz to'ldirildi!</b>\n\n"
                        f"💰 <b>Qo'shilgan summa:</b> {amount_formatted} UZS\n"
                        f"📝 <b>Sabab:</b> {reason}\n"
                        f"🕒 <b>Vaqti:</b> <code>{exact_time}</code>\n"
                        f"💵 <b>Yangi balansingiz:</b> {balance_formatted} UZS"
                    )
                send_telegram_message(student_token, student_chat_id, st_msg)

            # Also notify parent bot if linked
            setting = TelegramNotificationSetting.objects.filter(organization=instance.organization).first()
            parent_token = setting.parent_bot_token or setting.bot_token if setting else None
            if parent_token:
                if is_deduction:
                    parent_msg = (
                        f"<b>📉 Farzandingiz balansidan pul yechildi!</b>\n\n"
                        f"👶 <b>Farzand:</b> {student.first_name} {student.last_name or ''}\n"
                        f"💸 <b>Yechilgan summa:</b> {amount_formatted} UZS\n"
                        f"📝 <b>Sabab:</b> {reason}\n"
                        f"👤 <b>Yechgan:</b> {operator_name}\n"
                        f"🕒 <b>Vaqti:</b> <code>{exact_time}</code>\n"
                        f"💵 <b>Balans:</b> {balance_formatted} UZS"
                    )
                else:
                    parent_msg = (
                        f"<b>📈 Farzandingiz balansiga pul tushdi!</b>\n\n"
                        f"👶 <b>Farzand:</b> {student.first_name} {student.last_name or ''}\n"
                        f"💰 <b>Qo'shilgan summa:</b> {amount_formatted} UZS\n"
                        f"📝 <b>Sabab:</b> {reason}\n"
                        f"🕒 <b>Vaqti:</b> <code>{exact_time}</code>\n"
                        f"💵 <b>Balans:</b> {balance_formatted} UZS"
                    )
                if student.father_telegram_chat_id:
                    send_telegram_message(parent_token, student.father_telegram_chat_id, parent_msg)
                if student.mother_telegram_chat_id:
                    send_telegram_message(parent_token, student.mother_telegram_chat_id, parent_msg)

        except Exception as e:
            print(f"Error sending balance change telegram notification: {str(e)}")


@receiver(post_save, sender=ExamResult)
def notify_exam_result(sender, instance, created, **kwargs):
    if instance.student and instance.exam:
        try:
            from academics.telegram_bot import send_telegram_message, get_student_bot_token
            from organizations.models import TelegramNotificationSetting
            from accounts.models import User
            from django.db.models import Q
            from django.utils import timezone as django_timezone

            student = instance.student
            exam = instance.exam
            score_val = float(instance.score)
            max_score = getattr(exam, 'max_score', 100)
            min_score = getattr(exam, 'min_score', 60)

            status_str = "✅ O'tdi (Muvaffaqiyatli)" if score_val >= min_score else "⚠️ O'ta olmadi"

            created_at = getattr(instance, 'created_at', None) or django_timezone.now()
            exact_time = django_timezone.localtime(created_at).strftime("%d.%m.%Y %H:%M:%S")

            student_chat_id = getattr(student, 'telegram_chat_id', None)
            if not student_chat_id and student.phone:
                digits = "".join(c for c in student.phone if c.isdigit())
                last_9 = digits[-9:] if len(digits) >= 9 else digits
                matched_user = User.objects.filter(
                    Q(phone=student.phone) | Q(username=student.phone) |
                    (Q(phone__icontains=last_9) if last_9 else Q()) |
                    (Q(username__icontains=last_9) if last_9 else Q())
                ).filter(role='student', telegram_chat_id__isnull=False).first()
                if matched_user:
                    student_chat_id = matched_user.telegram_chat_id

            if student_chat_id:
                student_token = get_student_bot_token(instance.organization)
                st_msg = (
                    f"<b>🏆 Imtihon Bahosi E'lon Qilindi!</b>\n\n"
                    f"📚 <b>Imtihon nomi:</b> {exam.name}\n"
                    f"⭐ <b>Qo'yilgan baho/bal:</b> <code>{score_val}</code> / {max_score}\n"
                    f"📊 <b>Natija:</b> {status_str}\n"
                    f"🕒 <b>Vaqti:</b> <code>{exact_time}</code>"
                )
                send_telegram_message(student_token, student_chat_id, st_msg)

            setting = TelegramNotificationSetting.objects.filter(organization=instance.organization).first()
            parent_token = setting.parent_bot_token or setting.bot_token if setting else None
            if parent_token:
                parent_msg = (
                    f"<b>🏆 Farzandingiz Imtihon Bahosi!</b>\n\n"
                    f"👶 <b>Farzand:</b> {student.first_name} {student.last_name or ''}\n"
                    f"📚 <b>Imtihon nomi:</b> {exam.name}\n"
                    f"⭐ <b>Baho/bal:</b> <code>{score_val}</code> / {max_score}\n"
                    f"📊 <b>Natija:</b> {status_str}\n"
                    f"🕒 <b>Vaqti:</b> <code>{exact_time}</code>"
                )
                if student.father_telegram_chat_id:
                    send_telegram_message(parent_token, student.father_telegram_chat_id, parent_msg)
                if student.mother_telegram_chat_id:
                    send_telegram_message(parent_token, student.mother_telegram_chat_id, parent_msg)

        except Exception as e:
            print(f"Error sending exam result telegram notification: {str(e)}")


@receiver(post_save, sender=Homework)
def notify_homework_created(sender, instance, created, **kwargs):
    if created and instance.group:
        try:
            from academics.telegram_bot import send_telegram_message, get_student_bot_token
            from academics.models import StudentGroup
            from organizations.models import TelegramNotificationSetting
            from accounts.models import User
            from django.db.models import Q
            from django.utils import timezone as django_timezone

            group = instance.group
            teacher_name = "O'qituvchi"
            if instance.created_by:
                teacher_name = instance.created_by.get_full_name() or instance.created_by.username
            elif group.teacher:
                teacher_name = group.teacher.get_full_name() or group.teacher.username

            created_at = getattr(instance, 'created_at', None) or django_timezone.now()
            exact_time = django_timezone.localtime(created_at).strftime("%d.%m.%Y %H:%M:%S")
            due_date_str = str(instance.due_date) if instance.due_date else "Belgilanmagan"

            student_groups = StudentGroup.objects.filter(group=group).select_related('student')
            for sg in student_groups:
                student = sg.student
                if not student:
                    continue

                student_chat_id = getattr(student, 'telegram_chat_id', None)
                if not student_chat_id and student.phone:
                    digits = "".join(c for c in student.phone if c.isdigit())
                    last_9 = digits[-9:] if len(digits) >= 9 else digits
                    matched_user = User.objects.filter(
                        Q(phone=student.phone) | Q(username=student.phone) |
                        (Q(phone__icontains=last_9) if last_9 else Q()) |
                        (Q(username__icontains=last_9) if last_9 else Q())
                    ).filter(role='student', telegram_chat_id__isnull=False).first()
                    if matched_user:
                        student_chat_id = matched_user.telegram_chat_id

                if student_chat_id:
                    student_token = get_student_bot_token(instance.organization)
                    st_msg = (
                        f"<b>📝 Yangi Uy Vazifasi Berildi!</b>\n\n"
                        f"👥 <b>Guruh:</b> {group.name}\n"
                        f"📚 <b>Mavzu:</b> {instance.title}\n"
                        f"📝 <b>Topshiriq:</b> {instance.text or 'Tavsif berilmagan'}\n"
                        f"📅 <b>Topshirish muddati:</b> {due_date_str}\n"
                        f"👤 <b>O'qituvchi:</b> {teacher_name}\n"
                        f"🕒 <b>Vaqti:</b> <code>{exact_time}</code>"
                    )
                    send_telegram_message(student_token, student_chat_id, st_msg)

                setting = TelegramNotificationSetting.objects.filter(organization=instance.organization).first()
                parent_token = setting.parent_bot_token or setting.bot_token if setting else None
                if parent_token:
                    parent_msg = (
                        f"<b>📝 Farzandingizga Yangi Uy Vazifasi Berildi!</b>\n\n"
                        f"👶 <b>Farzand:</b> {student.first_name} {student.last_name or ''}\n"
                        f"👥 <b>Guruh:</b> {group.name}\n"
                        f"📚 <b>Mavzu:</b> {instance.title}\n"
                        f"📅 <b>Topshirish muddati:</b> {due_date_str}\n"
                        f"👤 <b>O'qituvchi:</b> {teacher_name}\n"
                        f"🕒 <b>Vaqti:</b> <code>{exact_time}</code>"
                    )
                    if student.father_telegram_chat_id:
                        send_telegram_message(parent_token, student.father_telegram_chat_id, parent_msg)
                    if student.mother_telegram_chat_id:
                        send_telegram_message(parent_token, student.mother_telegram_chat_id, parent_msg)

        except Exception as e:
            print(f"Error sending homework telegram notification: {str(e)}")


@receiver(post_save, sender=Attendance)
def notify_attendance_saved(sender, instance, created, **kwargs):
    if instance.student and instance.group:
        try:
            from academics.telegram_bot import send_telegram_message, get_student_bot_token
            from organizations.models import TelegramNotificationSetting
            from accounts.models import User
            from django.db.models import Q
            from django.utils import timezone as django_timezone

            student = instance.student
            group = instance.group

            status_map = {
                'present': "✅ Keldi (Darsda)",
                'late': "⏰ Kechikdi",
                'absent': "❌ Kelmadi (Sababsiz)",
                'excused': "📋 Sababli kelmadi"
            }
            status_text = status_map.get(instance.status, instance.status)

            teacher_name = "O'qituvchi"
            if group.teacher:
                teacher_name = group.teacher.get_full_name() or group.teacher.username

            created_at = getattr(instance, 'created_at', None) or django_timezone.now()
            exact_time = django_timezone.localtime(created_at).strftime("%d.%m.%Y %H:%M:%S")

            grade_str = str(instance.grade) if instance.grade is not None else "Qo'yilmagan"
            reason_str = instance.reason if instance.reason else "Yo'q"

            student_chat_id = getattr(student, 'telegram_chat_id', None)
            if not student_chat_id and student.phone:
                digits = "".join(c for c in student.phone if c.isdigit())
                last_9 = digits[-9:] if len(digits) >= 9 else digits
                matched_user = User.objects.filter(
                    Q(phone=student.phone) | Q(username=student.phone) |
                    (Q(phone__icontains=last_9) if last_9 else Q()) |
                    (Q(username__icontains=last_9) if last_9 else Q())
                ).filter(role='student', telegram_chat_id__isnull=False).first()
                if matched_user:
                    student_chat_id = matched_user.telegram_chat_id

            if student_chat_id:
                student_token = get_student_bot_token(instance.organization)
                st_msg = (
                    f"<b>📊 Davomat Qayd Etildi!</b>\n\n"
                    f"👥 <b>Guruh:</b> {group.name}\n"
                    f"📌 <b>Holatingiz:</b> {status_text}\n"
                    f"📅 <b>Dars sanasi:</b> {instance.date}\n"
                    f"⭐ <b>Dars bahosi:</b> {grade_str}\n"
                    f"📝 <b>Izoh:</b> {reason_str}\n"
                    f"👤 <b>O'qituvchi:</b> {teacher_name}\n"
                    f"🕒 <b>Vaqti:</b> <code>{exact_time}</code>"
                )
                send_telegram_message(student_token, student_chat_id, st_msg)

            setting = TelegramNotificationSetting.objects.filter(organization=instance.organization).first()
            parent_token = setting.parent_bot_token or setting.bot_token if setting else None
            if parent_token:
                parent_msg = (
                    f"<b>📊 Farzandingiz Davomati Qayd Etildi!</b>\n\n"
                    f"👶 <b>Farzand:</b> {student.first_name} {student.last_name or ''}\n"
                    f"👥 <b>Guruh:</b> {group.name}\n"
                    f"📌 <b>Holati:</b> {status_text}\n"
                    f"📅 <b>Dars sanasi:</b> {instance.date}\n"
                    f"⭐ <b>Baho:</b> {grade_str}\n"
                    f"👤 <b>O'qituvchi:</b> {teacher_name}\n"
                    f"🕒 <b>Vaqti:</b> <code>{exact_time}</code>"
                )
                if student.father_telegram_chat_id:
                    send_telegram_message(parent_token, student.father_telegram_chat_id, parent_msg)
                if student.mother_telegram_chat_id:
                    send_telegram_message(parent_token, student.mother_telegram_chat_id, parent_msg)

        except Exception as e:
            print(f"Error sending attendance telegram notification: {str(e)}")


@receiver(post_save, sender=Student)
def notify_new_student_to_report_bot(sender, instance, created, **kwargs):
    if created and instance.organization:
        try:
            from finance.models import send_telegram_payment_notification
            from django.utils import timezone as django_timezone
            created_at = getattr(instance, 'created_at', None) or django_timezone.now()
            exact_time = django_timezone.localtime(created_at).strftime("%d.%m.%Y %H:%M:%S")
            branch_name = instance.branch.name if getattr(instance, 'branch', None) else "Asosiy Filial"
            text = (
                f"<b>🎓 Yangi Talaba Qabul Qilindi!</b>\n\n"
                f"👤 <b>Talaba:</b> {instance.first_name} {instance.last_name or ''}\n"
                f"📞 <b>Telefon:</b> {instance.phone or 'Kiritilmagan'}\n"
                f"📍 <b>Filial:</b> {branch_name}\n"
                f"💵 <b>Boshlang'ich balans:</b> {int(instance.balance):,} UZS".replace(",", " ") + "\n"
                f"🕒 <b>Vaqti:</b> <code>{exact_time}</code>"
            )
            send_telegram_payment_notification(instance.organization, text, 'other_payments')
        except Exception as e:
            print(f"Error sending student notification to report bot: {str(e)}")

