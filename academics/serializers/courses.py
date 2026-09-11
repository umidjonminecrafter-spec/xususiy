from rest_framework import serializers
from academics.models import Course, Room, CourseMaterial


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


from drf_spectacular.utils import extend_schema_field


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

    @extend_schema_field(serializers.CharField(allow_null=True))
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
