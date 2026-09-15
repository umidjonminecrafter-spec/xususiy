import calendar
from decimal import Decimal
from django.db.models import Q
from django.utils import timezone
from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field

from academics.models import (
    Course, Group, StudentGroup, GroupTeacher, TeacherSalaryPayment,
    StudentGroupLeave, StudentPricing, Holiday
)
from accounts.serializers import UserSerializer


class GroupSerializer(serializers.ModelSerializer):
    course_name = serializers.CharField(source='course.name', read_only=True)
    room_name = serializers.SerializerMethodField(read_only=True)
    teacher_name = serializers.SerializerMethodField(read_only=True)
    student_count = serializers.SerializerMethodField(read_only=True)
    students_count = serializers.SerializerMethodField(read_only=True)
    students = serializers.SerializerMethodField(read_only=True)
    group_teachers = serializers.SerializerMethodField(read_only=True)
    exam_dates = serializers.SerializerMethodField(read_only=True)

    name = serializers.CharField(required=False, allow_blank=True)
    course = serializers.PrimaryKeyRelatedField(
        queryset=Course.objects.all(),
        required=False,
        allow_null=True
    )

    class Meta:
        model = Group
        fields = '__all__'
        read_only_fields = ('organization', 'created_at', 'updated_at')

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_teacher_name(self, obj):
        if obj.teacher:
            parts = [obj.teacher.first_name, obj.teacher.last_name]
            full_name = " ".join([p for p in parts if p]).strip()
            return full_name if full_name else (obj.teacher.username or obj.teacher.phone or "")
        return ""

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_room_name(self, obj):
        if obj.room:
            return obj.room.name
        return ""

    @extend_schema_field(serializers.ListField(child=serializers.DictField()))
    def get_group_teachers(self, obj):
        request = self.context.get('request')
        user = getattr(request, 'user', None) if request else None
        if user and getattr(user, 'role', None) == 'student':
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
        user = getattr(request, 'user', None) if request else None
        if user and getattr(user, 'role', None) == 'student':
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
        from accounts.models import User
        from organizations.models import Branch
        from academics.models import Course, Room
        from django.db.models import Q

        data = data.copy() if hasattr(data, 'copy') else dict(data)

        # 1. Teacher normalization (handle ID, dict, list, or name string)
        teacher_raw = data.get('teacher') or data.get('sinf_rahbar') or data.get('sinf_rahbari') or data.get('class_teacher')
        if isinstance(teacher_raw, dict) and 'id' in teacher_raw:
            teacher_raw = teacher_raw['id']
        elif isinstance(teacher_raw, (list, tuple)):
            teacher_raw = teacher_raw[0] if teacher_raw else None

        if teacher_raw:
            if str(teacher_raw).isdigit():
                t_obj = User.objects.filter(id=int(teacher_raw)).first()
                data['teacher'] = t_obj.id if t_obj else None
            else:
                name_str = str(teacher_raw).strip()
                t_obj = User.objects.filter(
                    Q(first_name__icontains=name_str) |
                    Q(last_name__icontains=name_str) |
                    Q(username__icontains=name_str)
                ).first()
                data['teacher'] = t_obj.id if t_obj else None
        else:
            data['teacher'] = None

        # 2. Branch normalization (handle ID, dict, or name string)
        branch_raw = data.get('branch') or data.get('bino') or data.get('building') or data.get('branch_id')
        if isinstance(branch_raw, dict) and 'id' in branch_raw:
            branch_raw = branch_raw['id']
        elif isinstance(branch_raw, (list, tuple)):
            branch_raw = branch_raw[0] if branch_raw else None

        if branch_raw:
            if str(branch_raw).isdigit():
                b_obj = Branch.objects.filter(id=int(branch_raw)).first()
                data['branch'] = b_obj.id if b_obj else None
            else:
                b_str = str(branch_raw).strip()
                b_obj = Branch.objects.filter(name__icontains=b_str).first()
                data['branch'] = b_obj.id if b_obj else None
        else:
            data['branch'] = None

        # 3. Room normalization
        room_raw = data.get('room') or data.get('xona') or data.get('room_id')
        if isinstance(room_raw, dict) and 'id' in room_raw:
            room_raw = room_raw['id']
        if room_raw:
            if str(room_raw).isdigit():
                r_obj = Room.objects.filter(id=int(room_raw)).first()
                data['room'] = r_obj.id if r_obj else None
            else:
                r_obj = Room.objects.filter(name__icontains=str(room_raw).strip()).first()
                data['room'] = r_obj.id if r_obj else None
        else:
            data['room'] = None

        # 4. Course normalization
        course_raw = data.get('course') or data.get('fan') or data.get('course_id')
        if isinstance(course_raw, dict) and 'id' in course_raw:
            course_raw = course_raw['id']
        if course_raw:
            if str(course_raw).isdigit():
                c_obj = Course.objects.filter(id=int(course_raw)).first()
                data['course'] = c_obj.id if c_obj else None
            else:
                c_obj = Course.objects.filter(name__icontains=str(course_raw).strip()).first()
                data['course'] = c_obj.id if c_obj else None
        else:
            data['course'] = None

        # 5. Grade level and Section normalization
        grade_level_raw = data.get('grade_level') or data.get('sinf_darajasi') or data.get('level') or data.get('grade')
        if grade_level_raw is not None:
            digits = "".join(c for c in str(grade_level_raw) if c.isdigit())
            data['grade_level'] = int(digits) if digits else None

        letter_raw = data.get('letter') or data.get('harf') or data.get('char') or data.get('section')
        if letter_raw:
            data['section'] = str(letter_raw).strip().upper()

        # 6. Capacity normalization
        capacity_raw = data.get('capacity') or data.get('oquvchi_soni') or data.get('max_students') or data.get('student_count') or data.get('students_count')
        if capacity_raw is not None:
            c_digits = "".join(c for c in str(capacity_raw) if c.isdigit())
            data['capacity'] = int(c_digits) if c_digits else None

        # 7. Language normalization
        lang_raw = data.get('language') or data.get('talim_tili') or data.get('lang')
        if lang_raw:
            data['language'] = str(lang_raw).strip()[:20]

        # 8. Name normalization
        name = data.get('name')
        grade_level = data.get('grade_level')
        section = data.get('section')

        if not name:
            if grade_level is not None and section:
                data['name'] = f"{grade_level}-{section}"
            elif grade_level is not None:
                data['name'] = f"{grade_level}-sinf"
            elif section:
                data['name'] = f"Sinf {section}"
            else:
                data['name'] = "Yangi Sinf"

        # Save student IDs list for post-creation enrollment
        self._initial_student_ids = data.get('students') or data.get('student_ids') or data.get('selected_students') or []

        return super().to_internal_value(data)

    def create(self, validated_data):
        group = super().create(validated_data)
        
        # Avtomatik ravishda tanlangan o'quvchilarni sinfga biriktirish
        student_ids = getattr(self, '_initial_student_ids', [])
        if student_ids and isinstance(student_ids, (list, set, tuple)):
            from academics.models import Student, StudentGroup
            from django.utils import timezone
            for s_item in student_ids:
                s_id = s_item.get('id') if isinstance(s_item, dict) else s_item
                if s_id and str(s_id).isdigit():
                    student = Student.objects.filter(id=int(s_id)).first()
                    if student:
                        StudentGroup.objects.get_or_create(
                            organization=group.organization,
                            group=group,
                            student=student,
                            defaults={
                                'branch': group.branch,
                                'joined_date': timezone.now().date(),
                            }
                        )
        return group


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
            st_first = instance.student.first_name or ""
            st_last = instance.student.last_name or ""
            full_name = f"{st_first} {st_last}".strip() or getattr(instance.student, 'name', '') or "O'quvchi"

            request = self.context.get('request')
            user = getattr(request, 'user', None) if request else None
            if user and getattr(user, 'role', None) == 'teacher':
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

            rep['full_name'] = full_name
            rep['student_name'] = full_name
            rep['name'] = full_name
            rep['student_detail'] = {
                'id': instance.student.id,
                'first_name': st_first,
                'last_name': st_last,
                'full_name': full_name,
                'name': full_name,
                'phone': phone,
                'balance': balance,
            }

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
