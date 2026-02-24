from django.contrib import admin
from .models import Game, Prompt, Competition, GameAttempt


class PromptInline(admin.TabularInline):
    model = Prompt
    extra = 1
    fields = ['text', 'difficulty', 'order', 'is_active']


@admin.register(Game)
class GameAdmin(admin.ModelAdmin):
    list_display = ['title', 'game_type', 'is_active', 'created_at']
    list_filter = ['game_type', 'is_active']
    search_fields = ['title', 'description']
    list_editable = ['is_active']
    prepopulated_fields = {'slug': ('title',)}
    inlines = [PromptInline]


@admin.register(Prompt)
class PromptAdmin(admin.ModelAdmin):
    list_display = ['game', 'text_short', 'difficulty', 'order', 'is_active']
    list_filter = ['game', 'difficulty', 'is_active']
    search_fields = ['text']
    list_editable = ['is_active', 'order']

    def text_short(self, obj):
        return obj.text[:60] + '...' if len(obj.text) > 60 else obj.text
    text_short.short_description = "Matn"


@admin.register(Competition)
class CompetitionAdmin(admin.ModelAdmin):
    list_display = ['title', 'game', 'start_time', 'end_time', 'is_active', 'max_attempts', 'allow_retry']
    list_filter = ['game', 'is_active']
    search_fields = ['title']
    list_editable = ['is_active']


@admin.register(GameAttempt)
class GameAttemptAdmin(admin.ModelAdmin):
    list_display = ['user', 'game', 'competition', 'wpm', 'accuracy', 'score', 'time_spent', 'created_at']
    list_filter = ['game', 'competition', 'created_at']
    search_fields = ['user__username', 'user__first_name', 'user__last_name']
    readonly_fields = ['user', 'game', 'competition', 'prompt', 'typed_text', 'time_spent', 'wpm', 'accuracy', 'score', 'created_at']
