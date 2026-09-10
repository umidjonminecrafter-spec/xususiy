from rest_framework import serializers
from django.contrib.auth import get_user_model
from organizations.models import Organization, Branch

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

    def get_branches_detail(self, obj):
        return [{"id": b.id, "name": b.name} for b in obj.branches.all()]

    class Meta:
        model = User
        fields = ('id', 'username', 'email', 'first_name', 'last_name', 'phone', 'role', 'position', 'organization',
                  'organization_name', 'branch', 'branch_name', 'photo', 'salary_percentage', 'branches', 'branches_detail')
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
        if not phone:
            raise serializers.ValidationError({"phone": "Telefon raqami kiritilishi shart."})

        cleaned = ''.join(c for c in phone if c.isdigit())

        if len(cleaned) == 9:
            cleaned = '998' + cleaned

        if not cleaned.startswith('998') or len(cleaned) != 12:
            raise serializers.ValidationError({
                "phone": "Telefon raqami noto'g'ri formatda. Loyihada O'zbekiston raqamlari (+998XXXXXXXXX) qabul qilinadi."
            })

        formatted_phone = '+' + cleaned
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

    def get_groups(self, obj):
        return [g.id for g in self._get_teacher_groups(obj)]

    def get_groups_detail(self, obj):
        return [{"id": g.id, "name": g.name} for g in self._get_teacher_groups(obj)]

    class Meta:
        model = User
        fields = ('id', 'username', 'password', 'email', 'first_name', 'last_name', 'phone', 'role', 'position',
                  'organization', 'branch', 'birth_date', 'gender', 'photo', 'salary_percentage',
                  'salary_percentage_detail', 'branches', 'branches_detail', 'groups', 'groups_detail')
        read_only_fields = ('id', 'organization', 'branch')

    # 🚀 1-YANGILIK: Abdulmajidga xatolik chiroyli "400 Bad Request" bo'lib borishi uchun:
    def validate(self, attrs):
        role = attrs.get('role')
        salary_percentage = attrs.get('salary_percentage')

        # to_internal_value dan kelgan rolni ham tekshiramiz
        if role == 'teacher' and not salary_percentage:
            raise serializers.ValidationError({
                "salary_percentage": "O'qituvchi yaratish uchun ish haqi foizini yuborish majburiy!"
            })

        # Telefon raqam formatini va takrorlanmasligini qo'lda tekshiramiz (frontedga xato 'phone' maydonida borishi uchun)
        phone = attrs.get('phone')
        if phone:
            import re
            if not re.match(r'^\+998\d{9}$', phone):
                raise serializers.ValidationError({
                    "phone": "Telefon raqami noto'g'ri formatda. Loyihada O'zbekiston raqamlari (+998XXXXXXXXX) qabul qilinadi."
                })
            
            # Tashkilot kontekstini olamiz
            request = self.context.get('request')
            view = self.context.get('view')
            org_id = None
            if self.instance:
                org_id = self.instance.organization_id
            if not org_id and view and hasattr(view, 'get_organization_id'):
                org_id = view.get_organization_id()
            if not org_id and request and request.user:
                org_id = getattr(request.user, 'organization_id', None)

            from django.db.models import Q
            from academics.models import Student

            # 1. Boshqa xodimlar ro'yxatida tekshiramiz (shu tashkilotda, student bo'lmaganlar)
            qs = User.objects.filter(
                Q(phone=phone) | Q(username=phone) | Q(username__startswith=f"{phone}_")
            ).exclude(role='student')
            if org_id:
                qs = qs.filter(organization_id=org_id)
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError({
                    "phone": "Ushbu telefon raqamli xodim tizimda allaqachon ro'yxatdan o'tgan."
                })

            # 2. Talabalar ro'yxatida tekshiramiz (shu tashkilotda)
            student_qs = Student.objects.filter(phone=phone)
            if org_id:
                student_qs = student_qs.filter(organization_id=org_id)
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
            cleaned = ''.join(c for c in str(phone) if c.isdigit())
            if len(cleaned) == 9:
                cleaned = '998' + cleaned
            if cleaned.startswith('998') and len(cleaned) == 12:
                formatted_phone = '+' + cleaned
            else:
                formatted_phone = '+' + cleaned if cleaned else phone
            
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
        rep['gender'] = 'Erkak' if instance.gender == 'M' else ('Ayol' if instance.gender == 'F' else 'Erkak')
        return rep