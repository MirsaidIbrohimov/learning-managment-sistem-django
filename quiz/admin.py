from django.contrib import admin

from .models import (
    AnswerOption, Attempt, AttemptAnswer, Question, Quiz, QuizQuestion, QuizSettings,
)


class AnswerOptionInline(admin.TabularInline):
    model = AnswerOption
    extra = 2


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ['id', 'short_text', 'type', 'status', 'difficulty', 'usage_count', 'created_by', 'created_at']
    list_filter = ['type', 'status', 'difficulty']
    search_fields = ['text']
    inlines = [AnswerOptionInline]
    readonly_fields = ['usage_count', 'last_used_at', 'legacy_test_question_id', 'created_at', 'updated_at']

    def short_text(self, obj):
        return obj.text[:60]
    short_text.short_description = 'Question'


class QuizSettingsInline(admin.StackedInline):
    model = QuizSettings
    can_delete = False


class QuizQuestionInline(admin.TabularInline):
    model = QuizQuestion
    extra = 0
    autocomplete_fields = ['question']


@admin.register(Quiz)
class QuizAdmin(admin.ModelAdmin):
    list_display = ['id', 'title', 'lesson', 'status', 'created_by', 'created_at']
    list_filter = ['status']
    search_fields = ['title']
    inlines = [QuizSettingsInline, QuizQuestionInline]
    readonly_fields = ['legacy_test_id', 'created_at', 'updated_at']


class AttemptAnswerInline(admin.TabularInline):
    model = AttemptAnswer
    extra = 0
    readonly_fields = ['question', 'response', 'is_correct', 'points_awarded', 'answered_at']
    can_delete = False


@admin.register(Attempt)
class AttemptAdmin(admin.ModelAdmin):
    """
    Read-mostly: attempts are written by the exam API, not edited by hand.
    Exists for support/debugging (e.g. confirming a student's coin award or
    investigating a stuck in-progress attempt), not as a data-entry screen.
    """
    list_display = ['id', 'student', 'quiz', 'status', 'attempt_number', 'score', 'passed', 'coin_awarded', 'started_at']
    list_filter = ['status', 'passed', 'coin_awarded']
    search_fields = ['student__username', 'student__first_name', 'student__last_name', 'quiz__title']
    autocomplete_fields = ['quiz', 'student']
    inlines = [AttemptAnswerInline]
    readonly_fields = [
        'resume_token', 'question_ids', 'option_order', 'started_at',
        'legacy_test_result_id',
    ]
