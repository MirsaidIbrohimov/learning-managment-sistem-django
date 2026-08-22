from django.contrib import admin

from .models import (
    PitchDeck,
    StageTemplate,
    Startup,
    StartupAchievement,
    StartupActivity,
    StartupFeedback,
    StartupFinance,
    StartupMember,
    StartupMentor,
    StartupMetric,
    StartupStage,
    StartupTask,
    StartupTaskSubmission,
    StartupXPTransaction,
    TaskTemplate,
)


class TaskTemplateInline(admin.TabularInline):
    model = TaskTemplate
    extra = 1
    fields = ['title', 'priority', 'points', 'order', 'is_active']


@admin.register(StageTemplate)
class StageTemplateAdmin(admin.ModelAdmin):
    list_display = ['order', 'title', 'key', 'weight', 'is_active']
    list_display_links = ['title']
    list_editable = ['order', 'weight', 'is_active']
    list_filter = ['is_active']
    search_fields = ['title', 'key']
    inlines = [TaskTemplateInline]


@admin.register(TaskTemplate)
class TaskTemplateAdmin(admin.ModelAdmin):
    list_display = ['title', 'stage_template', 'priority', 'points', 'order', 'is_active']
    list_filter = ['stage_template', 'priority', 'is_active']
    search_fields = ['title']
    list_select_related = ['stage_template']
    autocomplete_fields = ['stage_template']


class StartupMemberInline(admin.TabularInline):
    model = StartupMember
    extra = 0
    fields = ['user', 'role', 'status', 'invited_by']
    autocomplete_fields = ['user', 'invited_by']


class StartupStageInline(admin.TabularInline):
    model = StartupStage
    extra = 0
    fields = ['order', 'title', 'key', 'weight', 'is_completed']


class StartupMentorInline(admin.TabularInline):
    model = StartupMentor
    extra = 0
    fields = ['mentor', 'is_active']
    autocomplete_fields = ['mentor']


@admin.register(Startup)
class StartupAdmin(admin.ModelAdmin):
    list_display = ['name', 'owner', 'category', 'current_stage', 'progress',
                    'total_xp', 'status', 'created_at']
    list_filter = ['status', 'category', 'current_stage', 'profession']
    search_fields = ['name', 'slug', 'owner__username', 'owner__first_name',
                     'owner__last_name', 'short_description']
    prepopulated_fields = {'slug': ('name',)}
    readonly_fields = ['total_xp', 'progress', 'created_at', 'updated_at']
    list_select_related = ['owner', 'profession']
    autocomplete_fields = ['owner', 'profession']
    date_hierarchy = 'created_at'
    inlines = [StartupStageInline, StartupMemberInline, StartupMentorInline]


@admin.register(StartupStage)
class StartupStageAdmin(admin.ModelAdmin):
    list_display = ['startup', 'order', 'title', 'weight', 'is_completed', 'completed_at']
    list_filter = ['is_completed', 'key']
    search_fields = ['startup__name', 'title']
    list_select_related = ['startup']
    autocomplete_fields = ['startup']


@admin.register(StartupTask)
class StartupTaskAdmin(admin.ModelAdmin):
    list_display = ['title', 'startup', 'stage', 'status', 'priority', 'points',
                    'assigned_to', 'deadline']
    list_filter = ['status', 'priority', 'startup']
    search_fields = ['title', 'startup__name', 'assigned_to__username']
    list_select_related = ['startup', 'stage', 'assigned_to']
    autocomplete_fields = ['startup', 'assigned_to', 'created_by']
    readonly_fields = ['created_at', 'completed_at']


@admin.register(StartupTaskSubmission)
class StartupTaskSubmissionAdmin(admin.ModelAdmin):
    list_display = ['task', 'submitted_by', 'status', 'reviewed_by', 'submitted_at']
    list_filter = ['status', 'submitted_at']
    search_fields = ['task__title', 'submitted_by__username']
    list_select_related = ['task', 'submitted_by', 'reviewed_by']
    autocomplete_fields = ['task', 'submitted_by', 'reviewed_by']
    readonly_fields = ['submitted_at', 'reviewed_at']


@admin.register(StartupMember)
class StartupMemberAdmin(admin.ModelAdmin):
    list_display = ['user', 'startup', 'role', 'status', 'invited_by', 'joined_at']
    list_filter = ['status', 'role']
    search_fields = ['user__username', 'startup__name']
    list_select_related = ['user', 'startup', 'invited_by']
    autocomplete_fields = ['user', 'startup', 'invited_by']


@admin.register(StartupMentor)
class StartupMentorAdmin(admin.ModelAdmin):
    list_display = ['mentor', 'startup', 'is_active', 'assigned_at']
    list_filter = ['is_active']
    search_fields = ['mentor__username', 'startup__name']
    list_select_related = ['mentor', 'startup']
    autocomplete_fields = ['mentor', 'startup']


@admin.register(StartupXPTransaction)
class StartupXPTransactionAdmin(admin.ModelAdmin):
    list_display = ['startup', 'amount', 'reason', 'user', 'created_at']
    list_filter = ['reason', 'created_at']
    search_fields = ['startup__name', 'dedupe_key', 'description']
    list_select_related = ['startup', 'user']
    readonly_fields = ['created_at']


@admin.register(StartupFeedback)
class StartupFeedbackAdmin(admin.ModelAdmin):
    list_display = ['startup', 'mentor', 'task', 'rating', 'created_at']
    list_filter = ['rating', 'created_at']
    search_fields = ['startup__name', 'mentor__username', 'message']
    list_select_related = ['startup', 'mentor', 'task']
    autocomplete_fields = ['startup', 'mentor', 'task']


@admin.register(StartupAchievement)
class StartupAchievementAdmin(admin.ModelAdmin):
    list_display = ['startup', 'code', 'unlocked_at']
    list_filter = ['code']
    search_fields = ['startup__name', 'code']
    list_select_related = ['startup']
    autocomplete_fields = ['startup']


@admin.register(StartupFinance)
class StartupFinanceAdmin(admin.ModelAdmin):
    list_display = ['startup', 'type', 'amount', 'date', 'description', 'created_by']
    list_filter = ['type', 'date']
    search_fields = ['startup__name', 'description']
    list_select_related = ['startup', 'created_by']
    autocomplete_fields = ['startup', 'created_by']
    date_hierarchy = 'date'


@admin.register(StartupMetric)
class StartupMetricAdmin(admin.ModelAdmin):
    list_display = ['startup', 'key', 'value', 'date', 'created_by']
    list_filter = ['key', 'date']
    search_fields = ['startup__name', 'key']
    list_select_related = ['startup', 'created_by']
    autocomplete_fields = ['startup', 'created_by']


@admin.register(PitchDeck)
class PitchDeckAdmin(admin.ModelAdmin):
    list_display = ['startup', 'filled_count', 'updated_at']
    search_fields = ['startup__name']
    list_select_related = ['startup']
    autocomplete_fields = ['startup']


@admin.register(StartupActivity)
class StartupActivityAdmin(admin.ModelAdmin):
    list_display = ['startup', 'action_type', 'user', 'description', 'created_at']
    list_filter = ['action_type', 'created_at']
    search_fields = ['startup__name', 'description']
    list_select_related = ['startup', 'user']
    readonly_fields = ['startup', 'user', 'action_type', 'description', 'created_at']
