from rest_framework import serializers
from tasks.models import Board, Column, Item, Comment, TaskPermission, Label, Checklist, ChecklistItem, Attachment, TaskHistory

class ItemSerializer(serializers.ModelSerializer):
    assigned_to_name = serializers.CharField(source='assigned_to.get_full_name', default='', read_only=True)
    column_name = serializers.CharField(source='column.name', read_only=True)

    class Meta:
        model = Item
        fields = '__all__'
        read_only_fields = ('organization', 'created_at', 'updated_at')

    def validate(self, attrs):
        column = attrs.get('column')
        board = attrs.get('board')
        
        # PATCH (partial update) holatida self.instance'dan foydalanamiz
        if not column and self.instance:
            column = self.instance.column
        if not board and self.instance:
            board = self.instance.board
            
        if column and board and column.board_id != board.id:
            raise serializers.ValidationError(
                {"column": "Tanlangan ustun (column) ko'rsatilgan loyiha taxtasiga (board) tegishli emas."}
            )
        return attrs

class ColumnSerializer(serializers.ModelSerializer):
    items = ItemSerializer(many=True, read_only=True)

    class Meta:
        model = Column
        fields = '__all__'
        read_only_fields = ('organization', 'created_at', 'updated_at')

class BoardSerializer(serializers.ModelSerializer):
    columns = ColumnSerializer(many=True, read_only=True)

    class Meta:
        model = Board
        fields = '__all__'
        read_only_fields = ('organization', 'created_at', 'updated_at')

class CommentSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source='user.get_full_name', default='', read_only=True)

    class Meta:
        model = Comment
        fields = '__all__'
        read_only_fields = ('organization', 'user', 'created_at', 'updated_at')

class TaskPermissionSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source='user.get_full_name', default='', read_only=True)
    board_name = serializers.CharField(source='board.name', read_only=True)

    class Meta:
        model = TaskPermission
        fields = '__all__'
        read_only_fields = ('organization', 'created_at', 'updated_at')

class LabelSerializer(serializers.ModelSerializer):
    class Meta:
        model = Label
        fields = '__all__'
        read_only_fields = ('organization', 'created_at', 'updated_at')

class ChecklistSerializer(serializers.ModelSerializer):
    class Meta:
        model = Checklist
        fields = '__all__'
        read_only_fields = ('organization', 'created_at', 'updated_at')

class ChecklistItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = ChecklistItem
        fields = '__all__'
        read_only_fields = ('organization', 'created_at', 'updated_at')

class AttachmentSerializer(serializers.ModelSerializer):
    uploaded_by_name = serializers.CharField(source='uploaded_by.get_full_name', default='', read_only=True)

    class Meta:
        model = Attachment
        fields = '__all__'
        read_only_fields = ('organization', 'uploaded_by', 'created_at', 'updated_at')

class TaskHistorySerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source='user.get_full_name', default='', read_only=True)

    class Meta:
        model = TaskHistory
        fields = '__all__'
        read_only_fields = ('organization', 'created_at', 'updated_at')

