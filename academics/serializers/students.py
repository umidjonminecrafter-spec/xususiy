import re
from rest_framework import serializers
from academics.models import (
    Student, BalanceHistory, StudentPricing, StudentArchive,
    StudentFieldSetting, StudentEvaluationLevel
)
from common.utils import normalize_uz_phone


class StudentProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = Student
        fields = ['first_name', 'last_name', 'phone', 'balance', 'telegram_chat_id']


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


class StudentFieldSettingSerializer(serializers.ModelSerializer):
    class Meta:
        model = StudentFieldSetting
        fields = "__all__"
        read_only_fields = ("organization",)


class StudentEvaluationLevelSerializer(serializers.ModelSerializer):
    class Meta:
        model = StudentEvaluationLevel
        fields = '__all__'
        read_only_fields = ('organization', 'created_at', 'updated_at')


class StudentSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=False)

    class Meta:
        model = Student
        fields = [
            'id', 'first_name', 'last_name', 'phone', 'email', 'balance',
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

        if not self.instance:
            password = attrs.get('password')
            if not password or not str(password).strip():
                errors["password"] = "Yangi talaba uchun parol kiritilishi majburiy."
            elif len(password) < 6:
                errors["password"] = "Parol uzunligi kamida 6 ta belgidan iborat bo'lishi kerak."

        first_name = attrs.get("first_name", self.instance.first_name if self.instance else None)
        phone = attrs.get("phone", self.instance.phone if self.instance else None)

        if not first_name:
            errors["first_name"] = "Bu maydon majburiy."

        if not phone:
            errors["phone"] = "Bu maydon majburiy."
        else:
            if not re.match(r'^\+998\d{9}$', phone):
                errors["phone"] = "Telefon raqami noto'g'ri formatda. Loyihada O'zbekiston raqamlari (+998XXXXXXXXX) qabul qilinadi."
            else:
                from accounts.models import User
                from django.db.models import Q

                request = self.context.get("request")
                org_id = None
                if self.instance:
                    org_id = self.instance.organization_id
                if not org_id and request and hasattr(request, "user") and getattr(request.user, "organization_id", None):
                    org_id = request.user.organization_id

                student_qs = Student.objects.filter(phone=phone)
                if org_id:
                    student_qs = student_qs.filter(organization_id=org_id)
                if self.instance:
                    student_qs = student_qs.exclude(pk=self.instance.pk)

                if student_qs.exists():
                    errors["phone"] = "Ushbu telefon raqamli talaba tizimda allaqachon mavjud."
                else:
                    user_qs = User.objects.filter(
                        Q(phone=phone) | Q(username=phone) | Q(username__startswith=f"{phone}_")
                    ).exclude(role='student')
                    if org_id:
                        user_qs = user_qs.filter(organization_id=org_id)
                    if self.instance and self.instance.phone:
                        user_qs = user_qs.exclude(Q(phone=self.instance.phone) | Q(username=self.instance.phone))

                    if user_qs.exists():
                        errors["phone"] = "Ushbu telefon raqamli xodim tizimda allaqachon ro'yxatdan o'tgan."

        request = self.context.get("request")
        if request and hasattr(request.user, "organization"):
            required_fields = StudentFieldSetting.objects.filter(
                organization=request.user.organization,
                is_required=True
            )
            for setting in required_fields:
                field_name = setting.field_name
                value = attrs.get(field_name, getattr(self.instance, field_name, None) if self.instance else None)
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
                data[field] = normalize_uz_phone(val) or val

        if 'phone_number' in data and 'phone' not in data:
            data['phone'] = data['phone_number']
        return super().to_internal_value(data)

    def create(self, validated_data):
        password = validated_data.pop('password', None)
        phone = validated_data.get('phone')

        student = super().create(validated_data)

        if phone:
            from accounts.models import User
            existing_user = User.objects.filter(username=phone).first()
            if existing_user:
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

        from accounts.models import User
        user = User.objects.filter(username=old_phone).first()
        if user:
            if student.phone:
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
