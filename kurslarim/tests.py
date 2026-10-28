from datetime import timedelta
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import (
    CourseEnrollment, CustomUser, Homework, Lesson, PaymentStatus, Profession, Section, TezCheckPaymentOrder,
    UserSession, VideoLesson, VideoProgress,
)
from quiz.models import AnswerOption, Question, QuestionType, Quiz, QuizQuestion, QuizSettings


class PortalTests(TestCase):
    def setUp(self):
        cache.clear()
        cache.set('birthday_check_done', True, 86400)
        notifier = patch('telegram_bot.utils.notify_admins')
        notifier.start()
        self.addCleanup(notifier.stop)
        duration = patch('accounts.views._ensure_gating_duration')
        duration.start()
        self.addCleanup(duration.stop)
        self.student = CustomUser.objects.create_user(
            username='portal-student', phone='+998900000011', password='x', role='student',
            is_profile_completed=True, birth_date=timezone.localdate() - timedelta(days=7000))
        self.course = self.make_course('Sold course')
        self.other = self.make_course('Other course')
        self.s1 = Section.objects.create(profession=self.course, title='Bir', order=1)
        self.s2 = Section.objects.create(profession=self.course, title='Ikki', order=2)
        self.video = Lesson.objects.create(profession=self.course, section=self.s1, title='Video', lesson_type='video', order=1)
        VideoLesson.objects.create(lesson=self.video, youtube_url='https://youtu.be/abcdefghijk', duration=1)
        self.homework = Lesson.objects.create(profession=self.course, section=self.s1, title='Vazifa', lesson_type='homework', order=2)
        Homework.objects.create(lesson=self.homework, description='Yozing')
        self.test = Lesson.objects.create(profession=self.course, section=self.s2, title='Test', lesson_type='test', order=1)
        self.quiz = Quiz.objects.create(lesson=self.test, title='Quiz', status=Quiz.Status.PUBLISHED)
        QuizSettings.objects.create(quiz=self.quiz, time_limit_minutes=10, passing_score=50)
        question = Question.objects.create(type=QuestionType.SINGLE_CHOICE, text='2+2=?')
        AnswerOption.objects.create(question=question, text='4', is_correct=True, order=0)
        QuizQuestion.objects.create(quiz=self.quiz, question=question, order=0)
        self.other_lesson = Lesson.objects.create(profession=self.other, title='Boşqa', lesson_type='homework')
        Homework.objects.create(lesson=self.other_lesson, description='x')

        today = timezone.localdate()
        TezCheckPaymentOrder.objects.create(
            student=self.student, purpose='course', course=self.course, status='paid', amount_minor=100000,
            billing_month=today.month, billing_year=today.year, external_reference='portal-paid', paid_at=timezone.now())
        CourseEnrollment.objects.create(user=self.student, profession=self.course)
        CourseEnrollment.objects.create(user=self.student, profession=self.other)
        self.client.force_login(self.student)
        UserSession.objects.create(user=self.student, session_key=self.client.session.session_key,
                                   expires_at=timezone.now() + timedelta(hours=2))

    def make_course(self, name):
        return Profession.objects.create(name=name, photo='t.jpg', description='d', is_paid=True,
                                         one_time_payment=True, one_time_price=1000, daily_section_limit=False)

    def block(self, *, payment=True):
        CustomUser.objects.filter(pk=self.student.pk).update(is_blocked=True)
        PaymentStatus.objects.update_or_create(user=self.student, defaults={'auto_blocked': payment})

    def test_payment_blocked_student_uses_portal_only(self):
        self.block()
        self.assertEqual(self.client.get(reverse('kurslarim:my_courses')).status_code, 200)
        self.assertEqual(self.client.get(reverse('kurslarim:course', args=[self.course.pk])).status_code, 200)
        response = self.client.get(reverse('kurslarim:lesson', args=[self.video.pk]))
        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        self.assertIn(reverse('kurslarim:video_beat', args=[self.video.pk]), body)
        self.assertIn('kp-nav', body)  # portal sarlavhasi, asosiy menyu emas
        # Asosiy tizim sahifalari va API'lari yopiqligiça qoladi.
        self.assertRedirects(self.client.get(reverse('profession_detail', args=[self.course.pk])),
                             reverse('payment_wall'), fetch_redirect_response=False)
        self.assertEqual(self.client.get(f'/api/hw/{self.homework.pk}/').status_code, 403)
        self.assertEqual(self.client.get(reverse('kurslarim:hw_detail', args=[self.homework.pk])).status_code, 200)
        page = self.client.get(reverse('kurslarim:lesson', args=[self.homework.pk])).content.decode()
        self.assertIn("HW_API_ROOT = '" + reverse('kurslarim:hw_root'), page)

    def test_non_payment_block_keeps_portal_closed(self):
        self.block(payment=False)
        self.assertRedirects(self.client.get(reverse('kurslarim:my_courses')), reverse('payment_wall'),
                             fetch_redirect_response=False)

    def test_course_not_bought_is_hidden(self):
        self.block()
        self.assertEqual(self.client.get(reverse('kurslarim:course', args=[self.other.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse('kurslarim:lesson', args=[self.other_lesson.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse('kurslarim:hw_detail', args=[self.other_lesson.pk])).status_code, 404)

    def test_refunded_course_closes_portal(self):
        TezCheckPaymentOrder.objects.filter(student=self.student).update(status='refunded')
        self.assertEqual(self.client.get(reverse('kurslarim:course', args=[self.course.pk])).status_code, 404)

    def test_sections_follow_main_sequence(self):
        url = reverse('kurslarim:lesson', args=[self.test.pk])
        self.assertRedirects(self.client.get(url), reverse('kurslarim:course', args=[self.course.pk]),
                             fetch_redirect_response=False)
        response = self.client.post(reverse('kurslarim:attempt-list'), {'quiz_id': self.quiz.pk},
                                    content_type='application/json')
        self.assertEqual(response.status_code, 404)
        VideoProgress.objects.create(user=self.student, video=self.video.video, watched=True)
        from accounts.models import HomeworkSubmission
        HomeworkSubmission.objects.create(homework=self.homework.homework, student=self.student,
                                          submission_type='text', text_content='ok', status='accepted')
        self.assertEqual(self.client.get(url).status_code, 200)

    def test_quiz_attempt_through_portal_api(self):
        self.block()
        VideoProgress.objects.create(user=self.student, video=self.video.video, watched=True)
        from accounts.models import HomeworkSubmission
        HomeworkSubmission.objects.create(homework=self.homework.homework, student=self.student,
                                          submission_type='text', text_content='ok', status='accepted')
        page = self.client.get(reverse('kurslarim:lesson', args=[self.test.pk])).content.decode()
        self.assertIn(reverse('kurslarim:quiz_api_root'), page)
        response = self.client.post(reverse('kurslarim:attempt-list'), {'quiz_id': self.quiz.pk},
                                    content_type='application/json')
        self.assertEqual(response.status_code, 201)
        attempt_id = response.json()['id']
        self.assertEqual(self.client.post(reverse('kurslarim:attempt-submit', args=[attempt_id])).status_code, 200)

    def test_rejoin_after_unenroll_without_payment(self):
        CourseEnrollment.objects.filter(user=self.student, profession=self.course).delete()
        self.assertEqual(self.client.get(reverse('kurslarim:course', args=[self.course.pk])).status_code, 404)
        self.client.post(reverse('kurslarim:rejoin', args=[self.course.pk]))
        self.assertEqual(self.client.get(reverse('kurslarim:course', args=[self.course.pk])).status_code, 200)

    def test_payment_wall_lists_purchased_courses(self):
        self.block()
        VideoProgress.objects.create(user=self.student, video=self.video.video, watched=True)
        body = self.client.get(reverse('payment_wall')).content.decode()
        self.assertIn(reverse('kurslarim:my_courses'), body)
        self.assertIn(reverse('kurslarim:lesson', args=[self.homework.pk]), body)  # davom ettiriladigan dars
        self.assertNotIn(self.other.name, body)
