import calendar
from decimal import Decimal
from django.db.models import Q
from django.utils import timezone
from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field

from academics.models import (
    Group, StudentGroup, GroupTeacher, TeacherSalaryPayment,
    StudentGroupLeave, StudentPricing, Holiday
)
from accounts.serializers import UserSerializer


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

    @extend_schema_field(serializers.ListField(child=serializers.DictField()))
    def get_group_teachers(self, obj):
        request = self.context.get('request')
        if request and getattr(request.user, 'role', None) == 'student':
            return []
        return GroupTeacherSerializer(obj.group_teachers.all(), many=True).data

    @extend_schema_field(serializers.IntegerField())
    def get_student_count(self, obj):
        return obj.group_students.filter(student__isnull=False, student__is_archived=False).count()

    @extend_schema_field(serializers.IntegerField())
    def get_students_count(self, obj):
        return obj.group_students.filter(student__isnull=False, student__is_archived=False).count()

    @extend_schema_field(serializers.ListField(child=serializers.DictField()))
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

    @extend_schema_field(serializers.ListField(child=serializers.DictField()))
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

        if self.instance:
            teacher = teacher or self.instance.teacher
            days = days if 'days' in attrs else self.instance.days
            start_time = start_time or self.instance.start_time
            end_time = end_time or self.instance.end_time

        if teacher and days and start_time and end_time:
            existing_groups = Group.objects.filter(
                teacher=teacher,
                status='active'
            )
            if self.instance:
                existing_groups = existing_groups.exclude(pk=self.instance.pk)

            if isinstance(days, (list, set, tuple)):
                req_days_normalized = [str(d).lower().strip() for d in days if d]
            else:
                req_days_normalized = [str(days).lower().strip()] if days else []

            for g in existing_groups:
                if not (g.start_time and g.end_time and start_time and end_time):
                    continue

                if isinstance(g.days, (list, set, tuple)):
                    g_days_normalized = [str(d).lower().strip() for d in g.days if d]
                else:
                    g_days_normalized = [str(g.days).lower().strip()] if g.days else []

                common_days = set(req_days_normalized) & set(g_days_normalized)
                if common_days:
                    if (start_time < g.end_time) and (end_time > g.start_time):
                        raise serializers.ValidationError({
                            "teacher": "Guruh o'qituvchisi band"
                        })

        return attrs

    def to_internal_value(self, data):
        data = data.copy() if hasattr(data, 'copy') else dict(data)
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

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_student_name(self, obj):
        if obj.student:
            return f"{obj.student.first_name} {obj.student.last_name or ''}".strip()
        return "O'chirilgan Talaba"

    class Meta:
        model = StudentGroup
        fields = '__all__'
        read_only_fields = ('organization', 'created_at', 'updated_at')

    @extend_schema_field(serializers.DecimalField(max_digits=12, decimal_places=2, allow_null=True))
    def get_price(self, obj):
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

    @extend_schema_field(serializers.DictField(allow_null=True))
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

    @extend_schema_field(serializers.CharField(allow_null=True))
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

    def validate(self, attrs):
        amount = attrs.get('amount') if 'amount' in attrs else (self.instance.amount if self.instance else None)
        if amount is not None and Decimal(str(amount)) <= 0:
            raise serializers.ValidationError({"amount": "Oylik to'lovi summasi musbat (0 dan katta) bo'lishi kerak! ⚠️"})
        return attrs


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
