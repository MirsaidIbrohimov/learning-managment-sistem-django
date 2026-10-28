from django.contrib import admin

from .models import TeacherVideoIncome, VideoQuiz, VideoQuizAttempt, VideoTranscript


@admin.register(VideoQuiz)
class VideoQuizAdmin(admin.ModelAdmin):
    list_display = ('id', 'video', 'trigger_label', 'question', 'correct_option',
                    'reward_coin', 'penalty_coin', 'is_active', 'created_by', 'created_at')
    list_filter = ('is_active', 'created_at')
    search_fields = ('question', 'video__lesson__title')
    list_select_related = ('video__lesson', 'created_by')


@admin.register(VideoQuizAttempt)
class VideoQuizAttemptAdmin(admin.ModelAdmin):
    list_display = ('id', 'quiz', 'student', 'selected_option', 'is_correct',
                    'coins_change', 'answer_ms', 'created_at')
    list_filter = ('is_correct', 'created_at')
    search_fields = ('student__username', 'quiz__question')
    list_select_related = ('quiz', 'student')


@admin.register(TeacherVideoIncome)
class TeacherVideoIncomeAdmin(admin.ModelAdmin):
    list_display = ('id', 'teacher', 'amount', 'note', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('teacher__username', 'note')
    list_select_related = ('teacher',)


@admin.register(VideoTranscript)
class VideoTranscriptAdmin(admin.ModelAdmin):
    list_display = ('id', 'video', 'language', 'text_length', 'fetched_at')
    search_fields = ('video__lesson__title',)
    list_select_related = ('video__lesson',)
    readonly_fields = ('fetched_at',)

    @admin.display(description="Matn uzunligi")
    def text_length(self, obj):
        return len(obj.text)


# Bu fayl: Django admin panelida video-quiz modellarini boşqariş.
