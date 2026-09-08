from rest_framework import serializers
from academics.models import (
    Course, Room, Student, Group, StudentGroup, GroupTeacher, TeacherSalaryPayment, Attendance, LessonSchedule,
    BalanceHistory, Exam, ExamResult, LeaveReason, LessonTime, OnlineLesson, StudentGroupLeave, StudentPricing,
    StudentArchive, Holiday, Homework, StudentEvaluationLevel, CourseMaterial,
    Building, SchoolClass, ClassStudent, Parent, StudentAddress, StudentAppeal
)
from accounts.serializers import UserSerializer
from .models import StudentFieldSetting, GroupLesson
from .models import Student, BotMessageTemplate


# 1. Profil va balans uchun serializer
class StudentProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = Student
        fields = ['first_name', 'last_name', 'phone', 'balance', 'telegram_chat_id']


# 2. Xabar shablonlari uchun serializer
class BotMessageTemplateSerializer(serializers.ModelSerializer):
    template_type_display = serializers.CharField(source='get_template_type_display', read_only=True)

    class Meta:
        model = BotMessageTemplate
        fields = ['id', 'title', 'template_type', 'template_type_display', 'text', 'is_active']


class CourseSerializer(serializers.ModelSerializer):
    remove_image = serializers.BooleanField(write_only=True, required=False, default=False)

    class Meta:
        model = Course
        fields = '__all__'
        read_only_fields = ('organization', 'created_at', 'updated_at')

    def to_internal_value(self, data):
        data = data.copy() if hasattr(data, 'copy') else dict(data)

        # 1. monthly_price -> price
        if 'monthly_price' in data and 'price' not in data:
            data['price'] = data['monthly_price']

        # 2. comment -> description
        if 'comment' in data and 'description' not in data:
            data['description'] = data['comment']

        # 3. lesson_month -> duration_weeks
        if 'lesson_month' in data and 'duration_weeks' not in data:
            months = int(data['lesson_month']) if data['lesson_month'] else 0
            data['duration_weeks'] = months * 4

        # 4. Auto-generate code if empty or not provided
        if not data.get('code') and not data.get('courseCode'):
            request = self.context.get('request')
            org_id = None
            if request:
                org_id = request.query_params.get('org_id') or request.META.get('HTTP_X_ORG_ID')
                if not org_id and request.user and request.user.is_authenticated:
                    org_id = request.user.organization_id

            if org_id:
                existing_codes = Course.objects.filter(organization_id=org_id).values_list('code', flat=True)
                max_num = 0
                for code_str in existing_codes:
                    if code_str and code_str.isdigit():
                        max_num = max(max_num, int(code_str))
                data['code'] = str(max_num + 1)
            else:
                data['code'] = "1"
        elif 'courseCode' in data and 'code' not in data:
            data['code'] = data['courseCode']

        return super().to_internal_value(data)

    def create(self, validated_data):
        validated_data.pop('remove_image', None)
        return super().create(validated_data)

    def update(self, instance, validated_data):
        remove_image = validated_data.pop('remove_image', False)
        if remove_image and not validated_data.get('image'):
            if instance.image:
                instance.image.delete(save=False)
            instance.image = None
        return super().update(instance, validated_data)

    def to_representation(self, instance):
        rep = super().to_representation(instance)
        rep['monthly_price'] = instance.price
        rep['comment'] = instance.description
        rep['code'] = instance.code
        rep['lesson_time'] = instance.lesson_time
        rep['lesson_month'] = int(instance.duration_weeks / 4) if instance.duration_weeks else 0
        request = self.context.get('request')
        if instance.image:
            image_url = instance.image.url
            rep['image_url'] = request.build_absolute_uri(image_url) if request else image_url
            rep['image_name'] = instance.image.name.split('/')[-1]
        else:
            rep['image_url'] = None
            rep['image_name'] = None
        return rep


class RoomSerializer(serializers.ModelSerializer):
    class Meta:
        model = Room
        fields = '__all__'
        read_only_fields = ('organization', 'created_at', 'updated_at')


class StudentSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=False)
    branch_name = serializers.CharField(source='branch.name', read_only=True, default='')

    class Meta:
        model = Student
        fields = [
            'id', 'branch', 'branch_name', 'first_name', 'last_name', 'phone', 'email', 'balance',
            'school_class',
            'referred_by', 'moderator', 'debt_limit',
            'student_login', 'parent_login', 'password',
            'telegram_chat_id', 'category', 'birth_date', 'application',
            'language', 'payment_date', 'address', 'target_university',
            'father_name', 'father_phone', 'father_email', 'father_telegram_chat_id',
            'mother_name', 'mother_phone', 'mother_email', 'mother_telegram_chat_id',
            'is_archived'
        ]
        read_only_fields = ('organization', 'created_at', 'updated_at')

    def validate(self, attrs):
        errors = {}

        # CREATE paytida password majburiy
        if not self.instance:
            password = attrs.get('password')

            if not password or not str(password).strip():
                errors["password"] = (
                    "Yangi talaba uchun parol kiritilishi majburiy."
                )
            elif len(password) < 6:
                errors["password"] = (
                    "Parol uzunligi kamida 6 ta belgidan iborat bo'lishi kerak."
                )

        # CREATE va UPDATE uchun qiymatlarni olish
        first_name = attrs.get(
            "first_name",
            self.instance.first_name if self.instance else None
        )

        phone = attrs.get(
            "phone",
            self.instance.phone if self.instance else None
        )

        # Har doim majburiy maydonlar
        if not first_name:
            errors["first_name"] = "Bu maydon majburiy."

        if not phone:
            errors["phone"] = "Bu maydon majburiy."
        else:
            # 🚀 TELEFON RAQAM FORMATI VA UNIKALLIGINI TEKSHIRISH
            import re
            if not re.match(r'^\+998\d{9}$', phone):
                errors["phone"] = "Telefon raqami noto'g'ri formatda. Loyihada O'zbekiston raqamlari (+998XXXXXXXXX) qabul qilinadi."
            else:
                from academics.models import Student
                from accounts.models import User
                from django.db.models import Q

                # Tashkilot kontekstini olamiz
                request = self.context.get("request")
                org_id = None
                if self.instance:
                    org_id = self.instance.organization_id
                if not org_id and request and hasattr(request, "user") and getattr(request.user, "organization_id", None):
                    org_id = request.user.organization_id

                # 1. Talabalar ro'yxatida tekshiramiz (shu tashkilotda)
                student_qs = Student.objects.filter(phone=phone)
                if org_id:
                    student_qs = student_qs.filter(organization_id=org_id)
                if self.instance:
                    student_qs = student_qs.exclude(pk=self.instance.pk)

                allow_shared_phone = self.context.get("allow_shared_phone", False)
                if student_qs.exists():
                    # Agar allow_shared_phone bo'lsa va ism boshqa bo'lsa (aka-uka/opa-singil), o'tkazamiz
                    # Agar ism ham bir xil bo'lsa yoki allow_shared_phone ruxsat berilmagan bo'lsa, xatolik beramiz
                    if not allow_shared_phone or student_qs.filter(first_name__iexact=first_name).exists():
                        errors["phone"] = "Ushbu telefon raqamli talaba tizimda allaqachon mavjud."
                else:
                    # 2. Xodimlar/Foydalanuvchilar ro'yxatida tekshiramiz (student bo'lmagan xodimlar)
                    user_qs = User.objects.filter(
                        Q(phone=phone) | Q(username=phone) | Q(username__startswith=f"{phone}_")
                    ).exclude(role='student')
                    if org_id:
                        user_qs = user_qs.filter(organization_id=org_id)
                    if self.instance and self.instance.phone:
                        user_qs = user_qs.exclude(Q(phone=self.instance.phone) | Q(username=self.instance.phone))

                    if user_qs.exists():
                        errors["phone"] = "Ushbu telefon raqamli xodim tizimda allaqachon ro'yxatdan o'tgan."

        # Dinamik required field lar
        request = self.context.get("request")

        if request and hasattr(request.user, "organization"):
            from academics.models import StudentFieldSetting

            required_fields = StudentFieldSetting.objects.filter(
                organization=request.user.organization,
                is_required=True
            )

            for setting in required_fields:
                field_name = setting.field_name

                value = attrs.get(
                    field_name,
                    getattr(self.instance, field_name, None)
                    if self.instance else None
                )

                if value in [None, "", [], {}]:
                    errors[field_name] = "Bu maydon majburiy."

        if errors:
            raise serializers.ValidationError(errors)

        return attrs

    def to_internal_value(self, data):
        data = data.copy()
        if 'full_name' in data and 'first_name' not in data:
            name_parts = data['full_name'].strip().split(' ', 1)
            data['first_name'] = name_parts[0]
            data['last_name'] = name_parts[1] if len(name_parts) > 1 else ''

        for field in ['phone', 'phone_number', 'phone_number2', 'parent_phone']:
            val = data.get(field)
            if val:
                cleaned = ''.join(c for c in str(val) if c.isdigit())
                if len(cleaned) == 9:
                    cleaned = '998' + cleaned
                if cleaned.startswith('998') and len(cleaned) == 12:
                    data[field] = '+' + cleaned
                else:
                    data[field] = '+' + cleaned if cleaned else val

        if 'phone_number' in data and 'phone' not in data:
            data['phone'] = data['phone_number']

        if 'school_class_id' in data and 'school_class' not in data:
            data['school_class'] = data['school_class_id']
        elif 'class_id' in data and 'school_class' not in data:
            data['school_class'] = data['class_id']
        elif 'class' in data and 'school_class' not in data:
            data['school_class'] = data['class']

        return super().to_internal_value(data)

    def create(self, validated_data):
        password = validated_data.pop('password', None)
        phone = validated_data.get('phone')

        student = super().create(validated_data)

        if student.school_class:
            from academics.models import ClassStudent
            ClassStudent.objects.update_or_create(
                student=student,
                school_class=student.school_class,
                defaults={
                    'is_active': True,
                    'organization': student.organization,
                    'branch': student.branch
                }
            )

        if phone:
            from accounts.models import User
            existing_user = User.objects.filter(username=phone).first()
            other_student = Student.objects.filter(phone=phone, organization=student.organization).exclude(id=student.id).first()
            if existing_user and other_student and existing_user.first_name != student.first_name:
                # Aka-uka holati: eski talabaning akkauntini buzmay, yangi unikal username bilan yaratamiz
                unique_username = f"{phone}_{student.id}"
                User.objects.create_user(
                    username=unique_username,
                    password=password or "smarttalim123",
                    email=student.email or '',
                    first_name=student.first_name,
                    last_name=student.last_name or '',
                    phone=student.phone,
                    role='student',
                    organization=student.organization,
                    branch=student.branch
                )
            elif existing_user:
                # Reactivate and update existing user
                existing_user.is_active = True
                existing_user.first_name = student.first_name
                existing_user.last_name = student.last_name or ''
                existing_user.email = student.email or ''
                existing_user.organization = student.organization
                existing_user.branch = student.branch
                if password:
                    existing_user.set_password(password)
                existing_user.save()
            else:
                # Create a new student user
                User.objects.create_user(
                    username=phone,
                    password=password,
                    email=student.email or '',
                    first_name=student.first_name,
                    last_name=student.last_name or '',
                    phone=student.phone,
                    role='student',
                    organization=student.organization,
                    branch=student.branch
                )
        return student

    def update(self, instance, validated_data):
        password = validated_data.pop('password', None)
        old_phone = instance.phone
        student = super().update(instance, validated_data)

        from academics.models import ClassStudent
        if student.school_class:
            ClassStudent.objects.update_or_create(
                student=student,
                school_class=student.school_class,
                defaults={
                    'is_active': True,
                    'organization': student.organization,
                    'branch': student.branch
                }
            )
            ClassStudent.objects.filter(student=student).exclude(school_class=student.school_class).update(is_active=False)
        elif 'school_class' in validated_data and validated_data['school_class'] is None:
            ClassStudent.objects.filter(student=student).update(is_active=False)

        from accounts.models import User
        user = User.objects.filter(username=old_phone).first() or User.objects.filter(username=f"{old_phone}_{instance.id}").first()
        if user:
            if student.phone:
                if User.objects.filter(username=student.phone).exclude(pk=user.pk).exists():
                    user.username = f"{student.phone}_{instance.id}"
                else:
                    user.username = student.phone
                user.phone = student.phone
            user.first_name = student.first_name
            user.last_name = student.last_name or ''
            user.email = student.email or ''
            user.organization = student.organization
            user.branch = student.branch
            if password:
                user.set_password(password)
            user.save()
        return student

    def to_representation(self, instance):
        rep = super().to_representation(instance)
        rep['full_name'] = f"{instance.first_name} {instance.last_name}".strip()

        if instance.school_class:
            rep['school_class_name'] = str(instance.school_class)
            rep['class_name'] = str(instance.school_class)
            rep['school_class_detail'] = {
                'id': instance.school_class.id,
                'name': str(instance.school_class),
                'grade_level': instance.school_class.grade_level,
                'section': instance.school_class.section,
                'language': getattr(instance.school_class, 'language', 'uz'),
                'academic_year': getattr(instance.school_class, 'academic_year', '')
            }
        else:
            rep['school_class_name'] = None
            rep['class_name'] = None
            rep['school_class_detail'] = None

        # Check hide_student_data setting for teachers
        request = self.context.get('request')
        phone = instance.phone
        email = instance.email
        if request and getattr(request.user, 'role', None) == 'teacher':
            from organizations.models import Subscription
            subscription = Subscription.objects.filter(
                organization_id=instance.organization_id,
                is_active=True
            ).first()
            if subscription and subscription.hide_student_data:
                if len(phone) >= 4:
                    phone = phone[:-4] + "****"
                else:
                    phone = "****"
                email = "****"

        rep['phone'] = phone
        rep['phone_number'] = phone
        rep['email'] = email
        rep['groups'] = [{'id': sg.group.id, 'name': sg.group.name} for sg in
                         instance.student_groups.select_related('group')]
        return rep


class GroupSerializer(serializers.ModelSerializer):
    course_name = serializers.CharField(source='course.name', read_only=True)
    room_name = serializers.CharField(source='room.name', read_only=True)
    teacher_name = serializers.CharField(source='teacher.get_full_name', default='', read_only=True)
    student_count = serializers.SerializerMethodField(read_only=True)
    students_count = serializers.SerializerMethodField(read_only=True)
    students = serializers.SerializerMethodField(read_only=True)
    group_teachers = serializers.SerializerMethodField(read_only=True)
    exam_dates = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Group
        fields = '__all__'
        read_only_fields = ('organization', 'created_at', 'updated_at')

    def get_group_teachers(self, obj):
        request = self.context.get('request')
        if request and getattr(request.user, 'role', None) == 'student':
            return []
        from academics.serializers import GroupTeacherSerializer
        return GroupTeacherSerializer(obj.group_teachers.all(), many=True).data

    def get_student_count(self, obj):
        return obj.group_students.filter(student__isnull=False, student__is_archived=False).count()

    def get_students_count(self, obj):
        return obj.group_students.filter(student__isnull=False, student__is_archived=False).count()

    def get_students(self, obj):
        request = self.context.get('request')
        if request and getattr(request.user, 'role', None) == 'student':
            return []
        students_list = []
        for sg in obj.group_students.select_related('student').all():
            if sg.student and not sg.student.is_archived:
                students_list.append({
                    'id': sg.student.id,
                    'name': f"{sg.student.first_name} {sg.student.last_name or ''}".strip(),
                    'phone': sg.student.phone
                })
        return students_list

    def get_exam_dates(self, obj):
        exams = []
        for exam in obj.exams.all().order_by('date', 'id'):
            exams.append({
                'id': exam.id,
                'title': exam.name,
                'name': exam.name,
                'exam_date': exam.date.isoformat() if exam.date else None,
                'date': exam.date.isoformat() if exam.date else None,
            })
        return exams

    def validate(self, attrs):
        teacher = attrs.get('teacher')
        days = attrs.get('days', [])
        start_time = attrs.get('start_time')
        end_time = attrs.get('end_time')

        # Agar update bo'layotgan bo'lsa, joriy guruh ma'lumotlarini fallback qilamiz
        if self.instance:
            teacher = teacher or self.instance.teacher
            days = days if 'days' in attrs else self.instance.days
            start_time = start_time or self.instance.start_time
            end_time = end_time or self.instance.end_time

        # 🚀 O'QITUVCHI BANDLIGINI TEKSHIRISH (Rasmdagi asosiy talab)
        if teacher and days and start_time and end_time:
            # O'qituvchining boshqa barcha faol guruhlarini olamiz
            existing_groups = Group.objects.filter(
                teacher=teacher,
                status='active'
            )
            if self.instance:
                existing_groups = existing_groups.exclude(pk=self.instance.pk)

            # So'rov kunlarini normallashtiramiz
            if isinstance(days, (list, set, tuple)):
                req_days_normalized = [str(d).lower().strip() for d in days if d]
            else:
                req_days_normalized = [str(days).lower().strip()] if days else []

            for g in existing_groups:
                # Agar birortasining vaqti kiritilmagan bo'lsa, solishtirmaymiz
                if not (g.start_time and g.end_time and start_time and end_time):
                    continue

                # Guruh kunlarini normallashtiramiz
                if isinstance(g.days, (list, set, tuple)):
                    g_days_normalized = [str(d).lower().strip() for d in g.days if d]
                else:
                    g_days_normalized = [str(g.days).lower().strip()] if g.days else []

                # Kunlar kesishishini tekshiramiz (kamida bitta kun bir xil bo'lsa)
                common_days = set(req_days_normalized) & set(g_days_normalized)
                if common_days:
                    # Vaqtlar ustma-ust tushishini tekshiramiz:
                    # (StartA < EndB) AND (EndA > StartB) mantiqi kesishishni aniqlaydi
                    if (start_time < g.end_time) and (end_time > g.start_time):
                        raise serializers.ValidationError({
                            "teacher": "Guruh o'qituvchisi band"
                        })

        return attrs
    def to_internal_value(self, data):
        data = data.copy() if hasattr(data, 'copy') else dict(data)

        # Extract first item if teacher is sent as a list/array
        teacher = data.get('teacher')
        if isinstance(teacher, list):
            data['teacher'] = teacher[0] if teacher else None

        return super().to_internal_value(data)


class StudentGroupSerializer(serializers.ModelSerializer):
    student_name = serializers.SerializerMethodField(read_only=True)
    group_name = serializers.CharField(source='group.name', read_only=True)
    course_name = serializers.CharField(source='group.course.name', read_only=True)
    teacher = serializers.SerializerMethodField(read_only=True)
    teacher_name = serializers.SerializerMethodField(read_only=True)
    price = serializers.SerializerMethodField(read_only=True)

    def get_student_name(self, obj):
        if obj.student:
            return f"{obj.student.first_name} {obj.student.last_name or ''}".strip()
        return "O'chirilgan Talaba"

    class Meta:
        model = StudentGroup
        fields = '__all__'
        read_only_fields = ('organization', 'created_at', 'updated_at')

    def get_price(self, obj):
        from decimal import Decimal
        from django.utils import timezone
        import calendar
        from academics.models import StudentPricing, Holiday
        from django.db.models import Q

        # Get base price
        base_price = Decimal('0.00')
        if obj.price is not None:
            base_price = obj.price
        elif obj.group and obj.group.course:
            pricing = StudentPricing.objects.filter(student=obj.student, course=obj.group.course).first()
            if pricing:
                base_price = pricing.custom_price
            else:
                base_price = getattr(obj.group, 'price', None) or obj.group.course.price or Decimal('0.00')
        elif obj.group:
            base_price = getattr(obj.group, 'price', None) or Decimal('0.00')

        # Check for holidays with student_impact=True in the current month
        now = timezone.now().date()
        _, last_day = calendar.monthrange(now.year, now.month)
        month_start = now.replace(day=1)
        month_end = now.replace(day=last_day)

        holidays = Holiday.objects.filter(
            organization_id=obj.organization_id,
            student_impact=True,
            start_date__lte=month_end,
        )
        holidays = holidays.filter(Q(end_date__gte=month_start) | Q(end_date__isnull=True))

        holiday_dates = set()
        for h in holidays:
            start = max(h.start_date, month_start)
            end = min(h.end_date or h.start_date, month_end)
            curr = start
            while curr <= end:
                holiday_dates.add(curr)
                curr += timezone.timedelta(days=1)

        holiday_days = len(holiday_dates)
        if holiday_days > 0 and last_day > 0:
            discount_factor = Decimal(1) - (Decimal(holiday_days) / Decimal(last_day))
            base_price = base_price * discount_factor

        return round(base_price, 2)

    def get_teacher(self, obj):
        if obj.group and obj.group.teacher:
            t = obj.group.teacher
            parts = [t.first_name, t.last_name]
            full_name = " ".join([p for p in parts if p]).strip()
            return {
                'id': t.id,
                'username': t.username,
                'full_name': full_name if full_name else t.username,
                'name': full_name if full_name else t.username,
            }
        return None

    def get_teacher_name(self, obj):
        if obj.group and obj.group.teacher:
            t = obj.group.teacher
            parts = [t.first_name, t.last_name]
            full_name = " ".join([p for p in parts if p]).strip()
            return full_name if full_name else t.username
        return None

    def to_representation(self, instance):
        rep = super().to_representation(instance)
        
        phone = None
        balance = 0.00
        
        if instance.student:
            phone = instance.student.phone
            balance = instance.student.balance
            
            # Check hide_student_data setting for teachers
            request = self.context.get('request')
            if request and getattr(request.user, 'role', None) == 'teacher':
                from organizations.models import Subscription
                subscription = Subscription.objects.filter(
                    organization_id=instance.organization_id,
                    is_active=True
                ).first()
                if subscription and subscription.hide_student_data:
                    if phone and len(phone) >= 4:
                        phone = phone[:-4] + "****"
                    else:
                        phone = "****"
                        
        rep['phone'] = phone
        rep['phone_number'] = phone
        rep['student_phone'] = phone
        rep['student_phone_number'] = phone
        rep['balance'] = balance
        rep['student_balance'] = balance
        
        return rep


class GroupTeacherSerializer(serializers.ModelSerializer):
    teacher_detail = UserSerializer(source='teacher', read_only=True)
    group_name = serializers.CharField(source='group.name', read_only=True)

    class Meta:
        model = GroupTeacher
        fields = '__all__'
        read_only_fields = ('organization', 'created_at', 'updated_at')

    def to_representation(self, instance):
        rep = super().to_representation(instance)
        if instance.group:
            group = instance.group
            rep['group_name'] = group.name
            rep['room_name'] = group.room.name if group.room else None
            rep['course_name'] = group.course.name if group.course else None

            # Fetch students in the group
            students_list = []
            for sg in group.group_students.select_related('student').all():
                if sg.student:
                    students_list.append({
                        'id': sg.student.id,
                        'name': f"{sg.student.first_name} {sg.student.last_name or ''}".strip(),
                        'phone': sg.student.phone
                    })
            rep['students'] = students_list
            rep['students_count'] = len(students_list)
        return rep


class TeacherSalaryPaymentSerializer(serializers.ModelSerializer):
    teacher_name = serializers.CharField(source='teacher.get_full_name', read_only=True)

    class Meta:
        model = TeacherSalaryPayment
        fields = '__all__'
        read_only_fields = ('organization', 'created_at', 'updated_at')


class AttendanceSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source='student.__str__', read_only=True)

    class Meta:
        model = Attendance
        fields = '__all__'
        read_only_fields = ('organization', 'created_at', 'updated_at')

    def validate(self, attrs):
        status = attrs.get('status', getattr(self.instance, 'status', None))
        reason = attrs.get('reason', getattr(self.instance, 'reason', None))

        if status == 'excused' and (not reason or not str(reason).strip()):
            raise serializers.ValidationError({
                "reason": "Talaba darsda sababli qatnashmagan bo'lsa, sababini ko'rsatish majburiy!"
            })
        return attrs

    def to_representation(self, instance):
        rep = super().to_representation(instance)
        sg = StudentGroup.objects.filter(student_id=instance.student_id, group_id=instance.group_id).first()
        rep['student_group'] = sg.id if sg else None
        if instance.date:
            rep['lesson_date'] = instance.date.isoformat() if hasattr(instance.date, 'isoformat') else str(
                instance.date)
        else:
            rep['lesson_date'] = None
        rep['is_present'] = instance.status == 'present'
        rep['is_excused'] = instance.status == 'excused'
        rep['grade'] = instance.grade
        rep['reason'] = instance.reason or ("sababli" if instance.status == 'excused' else "")
        return rep


class LessonScheduleSerializer(serializers.ModelSerializer):
    teacher_detail = UserSerializer(source='teacher', read_only=True)
    teacher_name = serializers.CharField(source='teacher.get_full_name', read_only=True, default='')
    group_name = serializers.CharField(source='group.name', read_only=True)
    course_name = serializers.CharField(source='group.course.name', read_only=True, default='')
    day_type_display = serializers.CharField(source='get_day_type_display', read_only=True)
    group_days = serializers.JSONField(source='group.days', read_only=True, default=list)

    class Meta:
        model = LessonSchedule
        fields = '__all__'
        read_only_fields = ('organization', 'created_at', 'updated_at')


class StudentBalanceSerializer(serializers.ModelSerializer):
    student = serializers.IntegerField(source='id')

    class Meta:
        model = Student
        fields = ('student', 'balance')


class BalanceHistorySerializer(serializers.ModelSerializer):
    class Meta:
        model = BalanceHistory
        fields = '__all__'
        read_only_fields = ('organization',)


class ExamSerializer(serializers.ModelSerializer):
    class Meta:
        model = Exam
        fields = '__all__'
        read_only_fields = ('organization',)

    def to_internal_value(self, data):
        data = data.copy()
        if 'title' in data and 'name' not in data:
            data['name'] = data['title']
        if 'exam_date' in data and 'date' not in data:
            data['date'] = data['exam_date']

        # Automatic course assignment using the group
        if 'group' in data and 'course' not in data and data['group']:
            from academics.models import Group
            try:
                group_obj = Group.objects.get(id=data['group'])
                data['course'] = group_obj.course_id
            except Group.DoesNotExist:
                pass

        return super().to_internal_value(data)

    def to_representation(self, instance):
        rep = super().to_representation(instance)
        rep['title'] = instance.name
        rep['exam_date'] = instance.date

        if instance.group:
            rep['group'] = {
                'id': instance.group.id,
                'name': instance.group.name
            }
        else:
            rep['group'] = None

        return rep


class ExamResultSerializer(serializers.ModelSerializer):
    class Meta:
        model = ExamResult
        fields = '__all__'
        read_only_fields = ('organization',)


class LeaveReasonSerializer(serializers.ModelSerializer):
    class Meta:
        model = LeaveReason
        fields = '__all__'
        read_only_fields = ('organization',)


class LessonTimeSerializer(serializers.ModelSerializer):
    class Meta:
        model = LessonTime
        fields = '__all__'
        read_only_fields = ('organization',)


class OnlineLessonSerializer(serializers.ModelSerializer):
    group_name = serializers.CharField(source='group.name', read_only=True)
    course_name = serializers.CharField(source='group.course.name', read_only=True, default='')
    has_video = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = OnlineLesson
        fields = '__all__'
        read_only_fields = ('organization',)

    def get_has_video(self, obj):
        return bool(obj.video_url)

    def to_representation(self, instance):
        rep = super().to_representation(instance)
        rep['group_name'] = instance.group.name if instance.group else None
        rep['course_name'] = instance.group.course.name if instance.group and instance.group.course else None
        rep['has_video'] = bool(instance.video_url)
        return rep



class StudentGroupLeaveSerializer(serializers.ModelSerializer):
    class Meta:
        model = StudentGroupLeave
        fields = '__all__'
        read_only_fields = ('organization',)

    def to_representation(self, instance):
        rep = super().to_representation(instance)
        if instance.student:
            rep['student'] = {
                'id': instance.student.id,
                'full_name': f"{instance.student.first_name} {instance.student.last_name or ''}".strip(),
                'phone_number': instance.student.phone
            }
        else:
            rep['student'] = {
                'id': None,
                'full_name': instance.student_name or "Noma'lum o'quvchi",
                'phone_number': instance.student_phone or "-"
            }
        if instance.group:
            rep['group'] = {
                'id': instance.group.id,
                'name': instance.group.name,
                'course': {
                    'id': instance.group.course.id if instance.group.course else None,
                    'name': instance.group.course.name if instance.group.course else "Noma'lum"
                } if instance.group.course else None,
                'teacher': {
                    'id': instance.group.teacher.id if instance.group.teacher else None,
                    'full_name': instance.group.teacher.get_full_name() or instance.group.teacher.username if instance.group.teacher else "Noma'lum",
                    'name': instance.group.teacher.first_name if instance.group.teacher else "Noma'lum"
                } if instance.group.teacher else None
            }
        if instance.leave_reason:
            rep['leave_reason'] = {
                'id': instance.leave_reason.id,
                'name': instance.leave_reason.reason
            }
        return rep


class StudentPricingSerializer(serializers.ModelSerializer):
    class Meta:
        model = StudentPricing
        fields = '__all__'
        read_only_fields = ('organization',)


class StudentArchiveSerializer(serializers.ModelSerializer):
    class Meta:
        model = StudentArchive
        fields = '__all__'
        read_only_fields = ('organization',)


class HolidaySerializer(serializers.ModelSerializer):
    class Meta:
        model = Holiday
        fields = '__all__'
        read_only_fields = ('organization', 'created_at', 'updated_at')


class HomeworkSerializer(serializers.ModelSerializer):
    group_name = serializers.CharField(source='group.name', read_only=True, default='')
    teacher_name = serializers.SerializerMethodField(read_only=True)
    created_by_name = serializers.CharField(source='created_by.get_full_name', read_only=True, default='')

    class Meta:
        model = Homework
        fields = '__all__'
        read_only_fields = ('organization', 'created_by', 'created_at', 'updated_at')

    def get_teacher_name(self, obj):
        if obj.teacher:
            return obj.teacher.get_full_name() or getattr(obj.teacher, 'full_name', None) or obj.teacher.username
        if obj.created_by:
            return obj.created_by.get_full_name() or obj.created_by.username
        return ''


class StudentFieldSettingSerializer(serializers.ModelSerializer):
    class Meta:
        model = StudentFieldSetting
        fields = "__all__"
        read_only_fields = ("organization",)
from django.utils import timezone
# 1. Mavzu belgilash uchun serializer
class SetLessonTopicSerializer(serializers.ModelSerializer):
    class Meta:
        model = GroupLesson
        fields = ['title', 'description']
        extra_kwargs = {
            'title': {'required': True, 'allow_blank': False}
        }

# 2. Sanani ko'chirish uchun serializer
class RescheduleLessonSerializer(serializers.Serializer):
    new_date = serializers.DateField(required=True)

    def validate_new_date(self, value):
        # Cheklov: Sanani o'tgan kunga ko'chirib bo'lmaydi
        if value < timezone.now().date():
            raise serializers.ValidationError("Darsni o'tgan sanaga ko'chirish mumkin emas!")
        return value

class GroupLessonListSerializer(serializers.ModelSerializer):
    # LMS bo'limida video dars yuklangan-yuklanmaganini bilish uchun qisqa belgi
    has_online_material = serializers.SerializerMethodField()

    class Meta:
        model = GroupLesson
        fields = [
            'id', 'group', 'date', 'title', 'description',
            'is_canceled', 'original_date', 'has_online_material'
        ]

    def get_has_online_material(self, obj):
        # Agar shu dars kuniga tegishli onlayn dars bo'lsa va unga video yuklangan bo'lsa true qaytadi
        from .models import OnlineLesson
        return OnlineLesson.objects.filter(
            group=obj.group,
            attendance_date=obj.date
        ).exclude(video_url="").exists()



class BirthdayCalendarSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    birth_date = serializers.DateField()
    day = serializers.IntegerField() # Kalendarga joylashtirish oson bo'lishi uchun kunning o'zi (1-31)
    type = serializers.CharField()   # 'student', 'teacher', 'staff' (xodimlar)
    role_display = serializers.CharField() # Interfeysda chiroyli ko'rinishi uchun (Masalan: "O'qituvchi")


class StudentEvaluationLevelSerializer(serializers.ModelSerializer):
    class Meta:
        model = StudentEvaluationLevel
        fields = '__all__'
        read_only_fields = ('organization', 'created_at', 'updated_at')


class CourseMaterialSerializer(serializers.ModelSerializer):
    course_name = serializers.CharField(source='course.name', read_only=True)
    file_url = serializers.SerializerMethodField(read_only=True)
    material_type_display = serializers.CharField(source='get_material_type_display', read_only=True)

    class Meta:
        model = CourseMaterial
        fields = '__all__'
        read_only_fields = ('organization',)

    def validate_course(self, value):
        if value is None:
            raise serializers.ValidationError("Kurs maydoni majburiy. Iltimos, kursni tanlang.")
        return value

    def get_file_url(self, obj):
        if obj.file:
            request = self.context.get('request')
            url = obj.file.url
            return request.build_absolute_uri(url) if request else url
        return None

    def to_representation(self, instance):
        rep = super().to_representation(instance)
        rep['course_name'] = instance.course.name if instance.course else None
        rep['material_type_display'] = instance.get_material_type_display()
        if instance.file:
            request = self.context.get('request')
            url = instance.file.url
            rep['file_url'] = request.build_absolute_uri(url) if request else url
            rep['file_name'] = instance.file.name.split('/')[-1]
        else:
            rep['file_url'] = None
            rep['file_name'] = None
        return rep


# ─────────────────────────────────────────────────────────────
# 1. BINO SERIALIZER
# ─────────────────────────────────────────────────────────────
class BuildingSerializer(serializers.ModelSerializer):
    branch_name = serializers.CharField(source='branch.name', read_only=True, default='')

    class Meta:
        model = Building
        fields = '__all__'
        read_only_fields = ('organization', 'created_at', 'updated_at')


# ─────────────────────────────────────────────────────────────
# 2. SINF SERIALIZER
# ─────────────────────────────────────────────────────────────
class SchoolClassSerializer(serializers.ModelSerializer):
    name = serializers.CharField(read_only=True)
    teacher_name = serializers.SerializerMethodField(read_only=True)
    room_name = serializers.CharField(source='room.name', read_only=True, default='')
    branch_name = serializers.CharField(source='branch.name', read_only=True, default='')
    students_count = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = SchoolClass
        fields = [
            'id', 'branch', 'branch_name', 'name', 'grade_level', 'section', 'language',
            'teacher', 'teacher_name', 'room', 'room_name',
            'academic_year', 'students_count', 'created_at'
        ]
        read_only_fields = ('organization', 'created_at', 'updated_at')

    def get_teacher_name(self, obj):
        if obj.teacher:
            return obj.teacher.get_full_name() or getattr(obj.teacher, 'full_name', None) or obj.teacher.username
        return ''

    def get_students_count(self, obj):
        return obj.students.filter(is_active=True).count()


# ─────────────────────────────────────────────────────────────
# 3. SINF TARKIBIDAGI TALABA SERIALIZER
# ─────────────────────────────────────────────────────────────
class ClassStudentSerializer(serializers.ModelSerializer):
    student_id = serializers.IntegerField(source='student.id', read_only=True)
    full_name = serializers.CharField(source='student.full_name', read_only=True)
    phone = serializers.CharField(source='student.phone', read_only=True)
    balance = serializers.DecimalField(source='student.balance', max_digits=12, decimal_places=2, read_only=True)

    class Meta:
        model = ClassStudent
        fields = ['id', 'student_id', 'full_name', 'phone', 'balance', 'is_active', 'joined_at']
        read_only_fields = ('organization', 'created_at', 'updated_at')


# ─────────────────────────────────────────────────────────────
# 4. OTA-ONA SERIALIZER
# ─────────────────────────────────────────────────────────────
class ParentSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source='student.full_name', read_only=True)
    relation_display = serializers.CharField(source='get_relation_display', read_only=True)

    class Meta:
        model = Parent
        fields = '__all__'
        read_only_fields = ('organization', 'created_at', 'updated_at')


# ─────────────────────────────────────────────────────────────
# 5. O'QUVCHI MANZILI SERIALIZER
# ─────────────────────────────────────────────────────────────
class StudentAddressSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source='student.full_name', read_only=True)

    class Meta:
        model = StudentAddress
        fields = '__all__'
        read_only_fields = ('organization', 'created_at', 'updated_at')


# ─────────────────────────────────────────────────────────────
# 6. O'QUVCHI MUROJAATI SERIALIZER
# ─────────────────────────────────────────────────────────────
class StudentAppealSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source='student.full_name', read_only=True)
    student_phone = serializers.CharField(source='student.phone', read_only=True)
    appeal_type_display = serializers.CharField(source='get_appeal_type_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    responded_by_name = serializers.SerializerMethodField()

    class Meta:
        model = StudentAppeal
        fields = [
            'id', 'student', 'student_name', 'student_phone',
            'appeal_type', 'appeal_type_display',
            'message', 'status', 'status_display',
            'response', 'responded_by', 'responded_by_name', 'responded_at',
            'is_escalated_to_owner', 'escalated_at',
            'satisfaction_poll_sent', 'satisfaction_poll_sent_at',
            'student_satisfied', 'satisfaction_responded_at',
            'organization', 'branch', 'created_at', 'updated_at'
        ]
        read_only_fields = (
            'organization', 'created_at', 'updated_at',
            'is_escalated_to_owner', 'escalated_at',
            'satisfaction_poll_sent', 'satisfaction_poll_sent_at',
            'student_satisfied', 'satisfaction_responded_at'
        )

    def get_responded_by_name(self, obj):
        if obj.responded_by:
            return obj.responded_by.get_full_name() or obj.responded_by.username
        return None