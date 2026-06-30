"""
Page (HTML shell) routes for the unified question builder UI, mounted at
/quiz/... in config/urls.py. Kept separate from quiz/urls.py, which mounts
the JSON API at /api/v1/quiz/... -- different app_name so the two route
tables never collide in {% url %} lookups.
"""
from django.urls import path

from .page_views import (
    AIGenerateView, ImportView, QuestionBankView, QuestionBuilderView,
    QuizBuilderView, QuizListView, QuizTakeView,
    QuizRetryPaymentApproveView, QuizRetryPaymentListView, QuizRetryPaymentRejectView,
    QuizRetryPaymentRequestView,
)

app_name = 'quizui'

urlpatterns = [
    path('questions/', QuestionBankView.as_view(), name='question_bank'),
    path('questions/new/', QuestionBuilderView.as_view(), name='question_create'),
    path('questions/<int:pk>/edit/', QuestionBuilderView.as_view(), name='question_edit'),

    path('quizzes/', QuizListView.as_view(), name='quiz_list'),
    path('quizzes/new/', QuizBuilderView.as_view(), name='quiz_create'),
    path('quizzes/<int:pk>/edit/', QuizBuilderView.as_view(), name='quiz_edit'),

    # AI generation pages -- with or without an attaching quiz context.
    path('ai-generate/', AIGenerateView.as_view(), name='ai_generate'),
    path('quizzes/<int:pk>/ai-generate/', AIGenerateView.as_view(), name='quiz_ai_generate'),

    # Import wizard pages -- same dual entry as AI.
    path('import/', ImportView.as_view(), name='import_questions'),
    path('quizzes/<int:pk>/import/', ImportView.as_view(), name='quiz_import'),

    # Phase 5: student exam-taking page. Additive/parallel -- see
    # QuizTakeView's docstring and docs/QUIZ_MODULE_REDESIGN.md §4.
    path('quizzes/<int:pk>/take/', QuizTakeView.as_view(), name='quiz_take'),

    # Paid-retry flow (replaces accounts.FinalTestPayment) -- see
    # QuizRetryPayment in models.py and docs/QUIZ_MODULE_REDESIGN.md §4.
    path('quizzes/<int:pk>/retry-payment/', QuizRetryPaymentRequestView.as_view(), name='quiz_retry_payment_request'),
    path('retry-payments/', QuizRetryPaymentListView.as_view(), name='quiz_retry_payment_list'),
    path('retry-payments/<int:pk>/approve/', QuizRetryPaymentApproveView.as_view(), name='quiz_retry_payment_approve'),
    path('retry-payments/<int:pk>/reject/', QuizRetryPaymentRejectView.as_view(), name='quiz_retry_payment_reject'),
]
