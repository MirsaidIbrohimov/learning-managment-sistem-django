from rest_framework.routers import DefaultRouter

from .views import AttemptViewSet, QuestionViewSet, QuizViewSet

app_name = 'quiz'

router = DefaultRouter()
router.register('questions', QuestionViewSet, basename='question')
router.register('quizzes', QuizViewSet, basename='quiz')
router.register('attempts', AttemptViewSet, basename='attempt')

urlpatterns = router.urls
