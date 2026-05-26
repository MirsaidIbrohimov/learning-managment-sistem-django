from rest_framework import serializers

from accounts.models import AssistantRole, AssistantActionLog
from accounts.permissions_registry import is_valid_permission, all_permission_codes


class AssistantRoleSerializer(serializers.ModelSerializer):
    users_count = serializers.SerializerMethodField()

    class Meta:
        model = AssistantRole
        fields = [
            'id', 'code', 'name', 'description', 'permissions',
            'is_system', 'is_active', 'users_count',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['is_system', 'created_at', 'updated_at']

    def get_users_count(self, obj):
        return obj.users.count()

    def validate_permissions(self, value):
        if not isinstance(value, list):
            raise serializers.ValidationError("permissions list bo'lishi kerak")
        invalid = [p for p in value if not (isinstance(p, str) and is_valid_permission(p))]
        if invalid:
            raise serializers.ValidationError(f"Noto'g'ri permission kodlari: {invalid}")
        return value

    def validate(self, data):
        # is_system rollar uchun code o'zgartirib bo'lmaydi
        if self.instance and self.instance.is_system:
            if 'code' in data and data['code'] != self.instance.code:
                raise serializers.ValidationError("Tizim rolining kodini o'zgartirib bo'lmaydi")
        return data


class AssistantActionLogSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source='user.full_name', read_only=True, default=None)
    user_username = serializers.CharField(source='user.username', read_only=True, default=None)

    class Meta:
        model = AssistantActionLog
        fields = [
            'id', 'user', 'user_name', 'user_username',
            'action_code', 'target_type', 'target_id',
            'description', 'ip_address', 'extra', 'created_at',
        ]
