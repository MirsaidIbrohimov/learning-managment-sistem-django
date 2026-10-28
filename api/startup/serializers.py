"""MY StartUp API serializerlari — faqat öqiş uçun.

Yoziş amallari (vazifa topşiriş, tasdiqlaş, taklif) ataylab REST'ga
çiqarilmagan: ular XP/coin beradi va `startup.services` içidagi
`transaction.atomic` oqimiga boğliq. API kengaytirilganda öşa servis
funksiyalari qayta işlatilişi kerak, mantiq takrorlanmasin.
"""

from rest_framework import serializers

from startup.models import (
    PitchDeck,
    Startup,
    StartupFinance,
    StartupMember,
    StartupMetric,
    StartupStage,
    StartupTask,
)


class UserBriefSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    username = serializers.CharField()
    full_name = serializers.CharField()
    photo = serializers.SerializerMethodField()

    def get_photo(self, obj):
        return obj.photo.url if getattr(obj, 'photo', None) else None


class StartupCardSerializer(serializers.ModelSerializer):
    """Oçiq karta — har qanday tizimga kirgan foydalanuvçi köra oladi."""

    owner = UserBriefSerializer(read_only=True)
    category_display = serializers.CharField(source='get_category_display', read_only=True)
    stage_label = serializers.CharField(source='current_stage_label', read_only=True)
    stage_index = serializers.IntegerField(read_only=True)
    member_count = serializers.IntegerField(read_only=True, default=0)
    logo = serializers.SerializerMethodField()

    class Meta:
        model = Startup
        fields = [
            'id', 'name', 'slug', 'logo', 'owner', 'short_description',
            'category', 'category_display', 'current_stage', 'stage_label',
            'stage_index', 'progress', 'total_xp', 'status', 'member_count',
            'created_at',
        ]

    def get_logo(self, obj):
        return obj.logo.url if obj.logo else None


class StartupDetailSerializer(StartupCardSerializer):
    profession = serializers.CharField(source='profession.name', read_only=True, default=None)

    class Meta(StartupCardSerializer.Meta):
        fields = StartupCardSerializer.Meta.fields + [
            'description', 'problem', 'solution', 'target_audience',
            'business_model', 'competitors', 'profession',
            'website', 'github_url', 'telegram_url', 'instagram_url',
        ]


class LeaderboardEntrySerializer(StartupCardSerializer):
    rank = serializers.IntegerField(read_only=True)
    period_xp = serializers.IntegerField(read_only=True, default=None)
    is_mine = serializers.BooleanField(read_only=True, default=False)

    class Meta(StartupCardSerializer.Meta):
        fields = StartupCardSerializer.Meta.fields + ['rank', 'period_xp', 'is_mine']


class StageSerializer(serializers.ModelSerializer):
    class Meta:
        model = StartupStage
        fields = ['id', 'key', 'title', 'order', 'weight', 'is_completed', 'completed_at']


class TaskSerializer(serializers.ModelSerializer):
    stage_title = serializers.CharField(source='stage.title', read_only=True, default=None)
    assigned_to = UserBriefSerializer(read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    is_overdue = serializers.BooleanField(read_only=True)

    class Meta:
        model = StartupTask
        fields = [
            'id', 'title', 'description', 'stage', 'stage_title', 'assigned_to',
            'status', 'status_display', 'priority', 'points', 'deadline',
            'is_overdue', 'created_at', 'completed_at',
        ]


class MemberSerializer(serializers.ModelSerializer):
    user = UserBriefSerializer(read_only=True)
    role_display = serializers.CharField(source='get_role_display', read_only=True)

    class Meta:
        model = StartupMember
        fields = ['id', 'user', 'role', 'role_display', 'status', 'joined_at']


class MetricSerializer(serializers.ModelSerializer):
    class Meta:
        model = StartupMetric
        fields = ['id', 'key', 'value', 'date', 'note']


class FinanceSerializer(serializers.ModelSerializer):
    type_display = serializers.CharField(source='get_type_display', read_only=True)

    class Meta:
        model = StartupFinance
        fields = ['id', 'type', 'type_display', 'amount', 'description', 'date']


class PitchDeckSerializer(serializers.ModelSerializer):
    filled_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = PitchDeck
        fields = ['filled_count', 'updated_at'] + list(PitchDeck.SECTION_FIELDS)
