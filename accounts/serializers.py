from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field
from django.contrib.auth import get_user_model
from organizations.models import Organization, Branch
from common.utils import normalize_uz_phone

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    organization_name = serializers.CharField(source='organization.name', read_only=True)
    branch_name = serializers.CharField(source='branch.name', read_only=True)
    branches = serializers.PrimaryKeyRelatedField(
        queryset=Branch.objects.all(),
        many=True,
        required=False
    )
    branches_detail = serializers.SerializerMethodField(read_only=True)

    @extend_schema_field(serializers.ListField(child=serializers.DictField()))
    def get_branches_detail(self, obj):
        return [{"id": b.id, "name": b.name} for b in obj.branches.all()]

    class Meta:
        model = User
        fields = ('id', 'username', 'email', 'first_name', 'last_name', 'phone', 'role', 'position', 'organization',
                  'organization_name', 'branch', 'branch_name', 'photo', 'salary_percentage', 'hourly_rate',
                  'fixed_salary', 'salary_type', 'weekly_hours', 'branches', 'branches_detail')
        read_only_fields = ('id', 'role', 'organization', 'branch')


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)
    organization_name = serializers.CharField(write_only=True, required=False)
    full_name = serializers.CharField(write_only=True, required=True)
    phone = serializers.CharField(required=True)

    class Meta:
        model = User
        fields = ('password', 'email', 'phone', 'organization_name', 'full_name')

    def validate(self, attrs):
        phone = attrs.get('phone', '')
        formatted_phone = normalize_uz_phone(phone)
        if not formatted_phone or len(formatted_phone) != 13:
            raise serializers.ValidationError({
                "phone": "Telefon raqami noto'g'ri formatda. Loyihada O'zbekiston raqamlari (+998XXXXXXXXX) qabul qilinadi."
            })

        attrs['phone'] = formatted_phone
        attrs['username'] = formatted_phone

        full_name = attrs.get('full_name', '')
        if not full_name or not full_name.strip():
            raise serializers.ValidationError({"full_name": "Ism va Familiya kiritilishi shart."})

        return attrs

    def create(self, validated_data):
        full_name = validated_data.pop('full_name', '')
        org_name = validated_data.pop('organization_name', '')

        first_name = validated_data.get('first_name', '')
        last_name = validated_data.get('last_name', '')

        if full_name and not (first_name or last_name):
            parts = full_name.split(maxsplit=1)
            first_name = parts[0]
            if len(parts) > 1:
                last_name = parts[1]

        organization = None
        if org_name:
            organization = Organization.objects.create(name=org_name)

        username = f"{validated_data['phone']}_{organization.id}" if organization else validated_data['username']

        user = User.objects.create_user(
            username=username,
            password=validated_data['password'],
            email=validated_data.get('email', ''),
            first_name=first_name,
            last_name=last_name,
            phone=validated_data.get('phone', ''),
            role='owner',
            organization=organization,
            branch=None
        )
        return user


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(required=True)
    new_password = serializers.CharField(required=True)

    def validate_old_password(self, value):
        user = self.context['request'].user
        if not user.check_password(value):
            raise serializers.ValidationError("Old password is not correct.")
        return value


from finance.serializers import StaffSalaryPercentSerializer  # 👈 Moliya serializeridan import qilamiz
from finance.models import StaffSalaryPercent


class EmployeeSerializer(serializers.ModelSerializer):
    username = serializers.CharField(required=False)
    password = serializers.CharField(write_only=True, required=False)

    salary_percentage_detail = StaffSalaryPercentSerializer(source='salary_percentage', read_only=True)
    salary_percentage = serializers.PrimaryKeyRelatedField(
        queryset=StaffSalaryPercent.objects.all(),
        write_only=True,
        required=False,
        allow_null=True
    )
    branches = serializers.PrimaryKeyRelatedField(
        queryset=Branch.objects.all(),
        many=True,
        required=False
    )
    branches_detail = serializers.SerializerMethodField(read_only=True)
    groups = serializers.SerializerMethodField(read_only=True)
    groups_detail = serializers.SerializerMethodField(read_only=True)
    weekly_hours = serializers.DecimalField(max_digits=8, decimal_places=2, required=False, allow_null=True)

    @extend_schema_field(serializers.ListField(child=serializers.DictField()))
    def get_branches_detail(self, obj):
        return [{"id": b.id, "name": b.name} for b in obj.branches.all()]

    def _get_teacher_groups(self, obj):
        from academics.models import Group
        # Teacher or assistant teacher or additional teacher via GroupTeacher relation
        group_list = list(
            Group.objects.filter(teacher=obj) |
            Group.objects.filter(assistant_teacher=obj) |
            Group.objects.filter(group_teachers__teacher=obj)
        )
        seen = set()
        unique_groups = []
        for g in group_list:
            if g.id not in seen:
                seen.add(g.id)
                unique_groups.append(g)
        return unique_groups

    @extend_schema_field(serializers.ListField(child=serializers.IntegerField()))
    def get_groups(self, obj):
        return [g.id for g in self._get_teacher_groups(obj)]

    @extend_schema_field(serializers.ListField(child=serializers.DictField()))
    def get_groups_detail(self, obj):
        return [{"id": g.id, "name": g.name} for g in self._get_teacher_groups(obj)]

    class Meta:
        model = User
        fields = ('id', 'username', 'password', 'email', 'first_name', 'last_name', 'phone', 'role', 'position',
                  'organization', 'branch', 'birth_date', 'gender', 'photo', 'salary_percentage',
                  'salary_percentage_detail', 'salary_type', 'hourly_rate', 'fixed_salary', 'weekly_hours',
                  'branches', 'branches_detail', 'groups', 'groups_detail')
        read_only_fields = ('id', 'organization', 'branch')

    def validate(self, attrs):
        role = attrs.get('role')

        # Telefon raqam formatini va takrorlanmasligini qo'lda tekshiramiz (frontedga xato 'phone' maydonida borishi uchun)
        phone = attrs.get('phone')
        if phone:
            import re
            if not re.match(r'^\+998\d{9}$', phone):
                raise serializers.ValidationError({
                    "phone": "Telefon raqami noto'g'ri formatda. Loyihada O'zbekiston raqamlari (+998XXXXXXXXX) qabul qilinadi."
                })
            
            # Tashkilot kontekstini aniq olamiz
            request = self.context.get('request')
            view = self.context.get('view')
            org_id = None
            if self.instance and self.instance.organization_id:
                org_id = self.instance.organization_id
            if not org_id and 'organization' in attrs:
                org_val = attrs.get('organization')
                org_id = org_val.id if hasattr(org_val, 'id') else org_val
            if not org_id and view and hasattr(view, 'get_organization_id'):
                org_id = view.get_organization_id()
            if not org_id and request:
                org_header = None
                if hasattr(request, 'headers') and request.headers:
                    org_header = request.headers.get('X-Org-ID') or request.headers.get('X-Organization-ID')
                if org_header and str(org_header).isdigit():
                    org_id = int(org_header)
                if not org_id and hasattr(request, 'user') and getattr(request.user, 'organization_id', None):
                    org_id = request.user.organization_id

            from django.db.models import Q
            from academics.models import Student

            # Faqat SHU TASHKILOT (org_id) doirasidagi faol xodimlar va talabalarni tekshiramiz
            if org_id:
                # 1. Boshqa faol xodimlar ro'yxatida tekshiramiz (shu tashkilotda, faol, student bo'lmaganlar)
                qs = User.objects.filter(
                    organization_id=org_id,
                    is_active=True
                ).filter(
                    Q(phone=phone) | Q(username=phone) | Q(username=f"{phone}_{org_id}")
                ).exclude(role='student')

                if self.instance:
                    qs = qs.exclude(pk=self.instance.pk)

                if qs.exists():
                    raise serializers.ValidationError({
                        "phone": "Ushbu telefon raqamli xodim tizimda allaqachon ro'yxatdan o'tgan."
                    })

                # 2. Talabalar ro'yxatida tekshiramiz (shu tashkilotda, faol talabalar)
                student_qs = Student.objects.filter(
                    organization_id=org_id,
                    phone=phone,
                    is_archived=False
                )
                if student_qs.exists():
                    raise serializers.ValidationError({
                        "phone": "Ushbu telefon raqamli talaba tizimda allaqachon mavjud."
                    })

        # Xavfsizlik qoidalari:
        request = self.context.get('request')
        if request and request.user:
            current_user = request.user
            
            # 1. Tahrirlanayotgan xodim Owner bo'lsa va joriy foydalanuvchi Owner yoki Superuser bo'lmasa:
            if self.instance and self.instance.role == 'owner' and not (current_user.is_superuser or current_user.role == 'owner'):
                raise serializers.ValidationError({"detail": "Tashkilot egasi (Owner) ma'lumotlarini o'zgartirish huquqingiz yo'q!"})

            # 2. Hech kim o'zining rolini o'zi o'zgartira olmaydi (o'zini tahrirlayotgan bo'lsa)
            if self.instance and self.instance == current_user and 'role' in attrs:
                if attrs['role'] != self.instance.role:
                    raise serializers.ValidationError({"role": "O'z rolingizni o'zingiz o'zgartira olmaysiz!"})

            # 3. Owner roliga faqat amaldagi Owner yoki Superuser tayinlay oladi
            if role == 'owner' and not (current_user.is_superuser or current_user.role == 'owner'):
                raise serializers.ValidationError({"role": "Faqat tashkilot egasi (Owner) yangi Owner tayinlay oladi!"})

            # 4. Admin roliga faqat Owner yoki Superuser (yoki amaldagi Admin) tayinlay oladi
            if role == 'admin' and not (current_user.is_superuser or current_user.role in ['owner', 'admin']):
                raise serializers.ValidationError({"role": "Ushbu rolni berish uchun huquqingiz yetarli emas!"})

        return attrs

    def to_internal_value(self, data):
        # Telefon raqamini to'liq tozalab, standart formatga keltiramiz (+998XXXXXXXXX)
        data = data.copy() if hasattr(data, 'copy') else dict(data)
        phone = data.get('phone') or data.get('phone_number')
        if phone:
            formatted_phone = normalize_uz_phone(phone) or phone
            data['phone'] = formatted_phone
            data['username'] = formatted_phone

        full_name = data.get('full_name')
        if full_name and not (data.get('first_name') or data.get('last_name')):
            parts = full_name.split(maxsplit=1)
            data['first_name'] = parts[0]
            data['last_name'] = parts[1] if len(parts) > 1 else ''

        position = data.get('position')
        # BUGFIX: Faqat yangi yaratilayotganda (create) position bo'yicha rolni avtomatik aniqlaymiz.
        # Mavjud foydalanuvchini tahrirlayotganda (update) rolni o'zgartirmaymiz.
        if position and not data.get('role') and not self.instance:
            pos = position.lower()
            if 'teacher' in pos or "o'qituvchi" in pos or "oʻqituvchi" in pos or "o’qituvchi" in pos or "o`qituvchi" in pos:
                data['role'] = 'teacher'
            elif any(x in pos for x in ['ceo', 'director', 'admin']):
                data['role'] = 'admin'
            elif any(x in pos for x in ['manager', 'marketer']):
                data['role'] = 'manager'
            elif 'reception' in pos:
                data['role'] = 'receptionist'
            else:
                data['role'] = 'employee'

        # Haftalik dars soati validatsiyasi (faqat raqam kiritilishi shart, harflar taqiqlanadi)
        raw_weekly_hours = data.get('weekly_hours')
        if raw_weekly_hours is None and 'weekly_lesson_hours' in data:
            raw_weekly_hours = data.get('weekly_lesson_hours')
        elif raw_weekly_hours is None and 'dars_soati' in data:
            raw_weekly_hours = data.get('dars_soati')
        elif raw_weekly_hours is None and 'haftalik_dars_soati' in data:
            raw_weekly_hours = data.get('haftalik_dars_soati')
        elif raw_weekly_hours is None and 'haftalik_soat' in data:
            raw_weekly_hours = data.get('haftalik_soat')
        elif raw_weekly_hours is None and 'lesson_hours' in data:
            raw_weekly_hours = data.get('lesson_hours')

        if raw_weekly_hours is not None:
            val_str = str(raw_weekly_hours).strip()
            if val_str != '':
                try:
                    float(val_str)
                    data['weekly_hours'] = val_str
                except ValueError:
                    raise serializers.ValidationError({
                        "weekly_hours": "Haftalik dars soatiga faqat raqam kiritilishi shart. Harf kiritish taqiqlangan."
                    })
            else:
                data['weekly_hours'] = 0

        # salary_type normalizatsiyasi (har qanday oylik turi nomini to'g'ri qabul qilish)
        sal_type = data.get('salary_type')
        if sal_type is not None:
            st = str(sal_type).lower().strip()
            if st in ['belgilanmagan', 'unassigned', 'none', 'null', 'false', '0', '']:
                data['salary_type'] = 'unassigned'
            elif any(x in st for x in ['foiz', 'percent']):
                data['salary_type'] = 'percentage'
            elif any(x in st for x in ['soat', 'hour']):
                data['salary_type'] = 'hourly'
            elif any(x in st for x in ['qat', 'oylik', 'fixed', 'summa']):
                data['salary_type'] = 'fixed'

        # Qat'iy oylik summa (fixed_salary) va soatbay stavkani (hourly_rate) tozalash
        raw_fixed_salary = data.get('fixed_salary')
        if raw_fixed_salary is None and 'monthly_salary' in data:
            raw_fixed_salary = data.get('monthly_salary')
        elif raw_fixed_salary is None and 'salary_amount' in data:
            raw_fixed_salary = data.get('salary_amount')
        elif raw_fixed_salary is None and 'fixed_amount' in data:
            raw_fixed_salary = data.get('fixed_amount')

        if raw_fixed_salary is not None:
            val_clean = str(raw_fixed_salary).replace(' ', '').replace(',', '').strip()
            if val_clean != '':
                try:
                    data['fixed_salary'] = float(val_clean)
                except ValueError:
                    pass

        if 'hourly_rate' in data and data['hourly_rate'] is not None:
            hr_clean = str(data['hourly_rate']).replace(' ', '').replace(',', '').strip()
            if hr_clean != '':
                try:
                    data['hourly_rate'] = float(hr_clean)
                except ValueError:
                    pass

        # salary_percentage va turli oylik variantlarini moslashtirish
        raw_pct = data.get('salary_percentage')
        if raw_pct is not None and str(raw_pct).strip() != '':
            pct_clean = str(raw_pct).replace('%', '').replace(' ', '').replace(',', '').strip()
            try:
                pct_num = float(pct_clean)
            except ValueError:
                pct_num = None

            current_st = data.get('salary_type')
            if current_st == 'fixed':
                if pct_num is not None and ('fixed_salary' not in data or data.get('fixed_salary') in [0, 0.0, None]):
                    data['fixed_salary'] = pct_num
                data['salary_percentage'] = None
            elif current_st == 'hourly':
                if pct_num is not None and ('hourly_rate' not in data or data.get('hourly_rate') in [0, 0.0, None]):
                    data['hourly_rate'] = pct_num
                data['salary_percentage'] = None
            elif current_st == 'unassigned':
                data['salary_percentage'] = None
                data['fixed_salary'] = 0.0
                data['hourly_rate'] = 0.0
            else:
                if pct_num is not None and pct_num > 100 and ('fixed_salary' not in data or data.get('fixed_salary') in [0, 0.0, None]):
                    data['salary_type'] = 'fixed'
                    data['fixed_salary'] = pct_num
                    data['salary_percentage'] = None
                elif pct_num is not None:
                    # StaffSalaryPercent PK bormi yoki mavjud percent bormi tekshiramiz
                    if not StaffSalaryPercent.objects.filter(pk=pct_clean).exists():
                        request = self.context.get('request')
                        view = self.context.get('view')
                        org_id = None
                        if self.instance:
                            org_id = self.instance.organization_id
                        if not org_id and view and hasattr(view, 'get_organization_id'):
                            org_id = view.get_organization_id()
                        if not org_id and request and request.user:
                            org_id = getattr(request.user, 'organization_id', None)

                        ssp = None
                        if org_id:
                            ssp = StaffSalaryPercent.objects.filter(organization_id=org_id, percent=pct_num).first()
                        if not ssp:
                            ssp = StaffSalaryPercent.objects.filter(percent=pct_num).first()
                        if not ssp and org_id and 0 <= pct_num <= 100:
                            ssp = StaffSalaryPercent.objects.create(
                                organization_id=org_id,
                                percent=pct_num,
                                name=f"{int(pct_num) if pct_num.is_integer() else pct_num}%"
                            )
                        if ssp:
                            data['salary_percentage'] = ssp.id
                        else:
                            data['salary_percentage'] = None
                    if 'salary_type' not in data:
                        data['salary_type'] = 'percentage'
        else:
            if data.get('salary_type') == 'fixed' and data.get('fixed_salary'):
                data['salary_percentage'] = None
            elif data.get('salary_type') == 'hourly' and data.get('hourly_rate'):
                data['salary_percentage'] = None
            elif data.get('salary_type') == 'unassigned':
                data['salary_percentage'] = None

        return super().to_internal_value(data)

    # 🚀 2-YANGILIK: create mantiqini xavfsiz va aniq saqlaydigan qildik
    def create(self, validated_data):
        password = validated_data.pop('password', None) or 'smarttalim123'
        salary_percentage = validated_data.pop('salary_percentage', None)  # alohida sug'urib olamiz
        branches = validated_data.pop('branches', [])

        # Username formatini tashkilot ID si bilan birlashtiramiz
        org = validated_data.get('organization')
        org_id = org.id if org else None
        phone = validated_data.get('phone', '')
        if phone and org_id:
            validated_data['username'] = f"{phone}_{org_id}"
        else:
            validated_data['username'] = phone or validated_data.get('username', '')

        # Userni yaratamiz
        user = User.objects.create_user(
            password=password,
            **validated_data
        )

        # Foizni majburiy ravishda bog'lab saqlaymiz
        if salary_percentage:
            user.salary_percentage = salary_percentage
            
        if branches:
            user.branches.set(branches)
            user.branch = branches[0]
        elif validated_data.get('branch'):
            user.branches.set([validated_data.get('branch')])
            
        user.save()
        return user

    def update(self, instance, validated_data):
        password = validated_data.pop('password', None)
        branches = validated_data.pop('branches', None)

        phone = validated_data.get('phone')
        org = validated_data.get('organization') or instance.organization
        org_id = org.id if org else None
        if phone:
            if org_id:
                validated_data['username'] = f"{phone}_{org_id}"
            else:
                validated_data['username'] = phone
        
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
            
        if password:
            instance.set_password(password)
            
        if branches is not None:
            instance.branches.set(branches)
            if branches:
                instance.branch = branches[0]
            else:
                instance.branch = None
                
        instance.save()
        return instance

    def to_representation(self, instance):
        # Sizning mavjud to_representation kodingiz (o'zgarishsiz qoladi)
        rep = super().to_representation(instance)
        rep['full_name'] = f"{instance.first_name} {instance.last_name}".strip() or instance.username
        if instance.position:
            rep['position'] = instance.position
        else:
            role_to_pos = {
                'owner': 'Owner',
                'admin': 'Administrator',
                'manager': 'Manager',
                'teacher': 'Teacher',
                'receptionist': 'Receptionist',
                'employee': 'Xodim',
                'student': 'Talaba'
            }
            rep['position'] = role_to_pos.get(instance.role, 'Xodim')
        wh = float(instance.weekly_hours or 0)
        rep['weekly_hours'] = wh
        rep['weekly_lesson_hours'] = wh
        rep['dars_soati'] = wh
        rep['haftalik_dars_soati'] = wh
        rep['gender'] = 'Erkak' if instance.gender == 'M' else ('Ayol' if instance.gender == 'F' else 'Erkak')
        return rep


class PasswordResetRequestSerializer(serializers.Serializer):
    phone = serializers.CharField(required=True, max_length=50)

    def validate_phone(self, value):
        from academics.telegram_bot import normalize_phone
        norm = normalize_phone(value)
        if not norm:
            raise serializers.ValidationError("Noto'g'ri telefon raqam formati kiritildi.")
        return norm


class PasswordResetConfirmSerializer(serializers.Serializer):
    session_token = serializers.CharField(required=True, max_length=64)
    otp_code = serializers.CharField(required=False, allow_blank=True, max_length=10)
    new_password = serializers.CharField(required=True, min_length=6, write_only=True)
    confirm_password = serializers.CharField(required=False, allow_blank=True, min_length=6, write_only=True)

    def validate(self, attrs):
        new_pwd = attrs.get('new_password')
        confirm_pwd = attrs.get('confirm_password')
        if confirm_pwd and new_pwd != confirm_pwd:
            raise serializers.ValidationError({"confirm_password": "Yangi parollar bir-biriga mos kelmadi."})
        return attrs