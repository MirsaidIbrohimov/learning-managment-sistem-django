from django.contrib import admin
from .models import Game, Prompt, Competition, GameAttempt, WordRound, WordGameAttempt, WordSuggestion, BoardMatch


class PromptInline(admin.TabularInline):
    model = Prompt
    extra = 1
    fields = ['text', 'difficulty', 'order', 'is_active']


class WordRoundInline(admin.TabularInline):
    model = WordRound
    extra = 1
    fields = ['letters', 'valid_words', 'difficulty', 'time_limit', 'order', 'is_active']


@admin.register(Game)
class GameAdmin(admin.ModelAdmin):
    list_display = ['title', 'game_type', 'is_active', 'created_at']
    list_filter = ['game_type', 'is_active']
    search_fields = ['title', 'description']
    list_editable = ['is_active']
    prepopulated_fields = {'slug': ('title',)}
    inlines = [PromptInline, WordRoundInline]


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


@admin.register(WordRound)
class WordRoundAdmin(admin.ModelAdmin):
    list_display = ['game', 'letters', 'difficulty', 'word_count', 'time_limit', 'order', 'is_active']
    list_filter = ['game', 'difficulty', 'is_active']
    search_fields = ['letters']
    list_editable = ['is_active', 'order']


@admin.register(WordGameAttempt)
class WordGameAttemptAdmin(admin.ModelAdmin):
    list_display = ['user', 'game', 'word_round', 'competition', 'found_count', 'total_score', 'time_spent', 'created_at']
    list_filter = ['game', 'competition', 'created_at']
    search_fields = ['user__username', 'user__first_name', 'user__last_name']
    readonly_fields = ['user', 'game', 'word_round', 'competition', 'found_words', 'total_score', 'time_spent', 'created_at']


@admin.register(BoardMatch)
class BoardMatchAdmin(admin.ModelAdmin):
    list_display = ['id', 'game', 'white_player', 'black_player', 'status', 'winner',
                    'mode', 'wager_coins', 'move_count', 'created_at', 'ended_at']
    list_filter = ['game', 'status', 'winner', 'mode', 'created_at']
    search_fields = ['white_player__username', 'black_player__username']
    readonly_fields = ['game', 'white_player', 'black_player', 'mode', 'wager_coins', 'coins_settled',
                       'board_state', 'current_turn', 'move_count', 'last_move',
                       'created_at', 'started_at', 'last_activity_at', 'ended_at', 'competition']


@admin.register(WordSuggestion)
class WordSuggestionAdmin(admin.ModelAdmin):
    list_display = ['user', 'word', 'word_round', 'status', 'created_at']
    list_filter = ['status', 'created_at']
    search_fields = ['word', 'user__username', 'user__first_name']
    readonly_fields = ['user', 'word_round', 'word', 'created_at', 'reviewed_at', 'reviewed_by']
