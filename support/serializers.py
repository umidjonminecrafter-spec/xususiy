from rest_framework import serializers
from support.models import FAQCategory, FAQItem, ChatSession, ChatMessage, SupportTicket
from django.contrib.auth import get_user_model

User = get_user_model()


class UserSimpleSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(source='get_full_name', read_only=True)

    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'full_name']


class FAQCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = FAQCategory
        fields = ['id', 'name', 'description', 'is_active', 'created_at']
        read_only_fields = ['id', 'created_at']


class FAQItemSerializer(serializers.ModelSerializer):
    category_name = serializers.ReadOnlyField(source='category.name')

    class Meta:
        model = FAQItem
        fields = ['id', 'category', 'category_name', 'question', 'answer', 'keywords', 'is_active', 'created_at']
        read_only_fields = ['id', 'category_name', 'created_at']


class ChatMessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ChatMessage
        fields = ['id', 'sender', 'content', 'confidence_score', 'matched_faq', 'created_at']
        read_only_fields = ['id', 'created_at']


class ChatSessionSerializer(serializers.ModelSerializer):
    messages = ChatMessageSerializer(many=True, read_only=True)
    user_detail = UserSimpleSerializer(source='user', read_only=True)

    class Meta:
        model = ChatSession
        fields = ['session_id', 'user', 'user_detail', 'telegram_chat_id', 'messages', 'created_at', 'updated_at']
        read_only_fields = ['session_id', 'user_detail', 'messages', 'created_at', 'updated_at']


class ChatInputSerializer(serializers.Serializer):
    session_id = serializers.UUIDField(required=False, allow_null=True)
    message = serializers.CharField(max_length=2000, required=True)


class SupportTicketSerializer(serializers.ModelSerializer):
    user_detail = UserSimpleSerializer(source='user', read_only=True)
    assigned_admin_detail = UserSimpleSerializer(source='assigned_admin', read_only=True)

    class Meta:
        model = SupportTicket
        fields = [
            'id', 'session', 'user', 'user_detail', 'email', 'title', 'description',
            'status', 'priority', 'assigned_admin', 'assigned_admin_detail',
            'admin_notes', 'resolved_at', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'user_detail', 'assigned_admin_detail', 'resolved_at', 'created_at', 'updated_at']
