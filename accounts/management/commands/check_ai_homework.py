"""
1 soat tahrirlash muddati tugagan vazifalarni AI bilan tekshirish.
Har 5 daqiqada cron/scheduler orqali ishga tushiriladi:
  python manage.py check_ai_homework
"""
from datetime import timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone


class Command(BaseCommand):
    help = "Tahrirlash muddati tugagan vazifalarni AI bilan tekshiradi"

    def handle(self, *args, **options):
        from accounts.models import HomeworkSubmission, Message
        from coin.models import ActivityLog
        from telegram_bot.utils import notify_admins
        from accounts.views import (
            _read_submission_content,
            _check_ai_generated,
            _check_similarity_with_others,
            _get_ai_grade,
        )

        one_hour_ago = timezone.now() - timedelta(hours=1)

        submissions = HomeworkSubmission.objects.select_related(
            'homework__lesson__profession', 'student'
        ).filter(
            homework__ai_check=True,
            homework__lesson__profession__ai_check_enabled=True,
            ai_checked=False,
            status='pending',
            submitted_at__lte=one_hour_ago,
        )

        count = 0
        for sub in submissions:
            hw = sub.homework
            student_answer = _read_submission_content(sub)

            if not student_answer:
                if sub.submission_type == 'file' and sub.file:
                    import os
                    if os.path.splitext(sub.file.name)[1].lower() == '.pdf':
                        sub.ai_feedback = "📄 Suniy Intellekt PDF formatni qo'llab-quvvatlamaydi. Faqat matn yoki kod fayllarini tekshira oladi."
                sub.ai_checked = True
                sub.save(update_fields=['ai_checked', 'ai_feedback'])
                continue

            try:
                ai_warning = ""
                has_suspicion = False

                ai_check = _check_ai_generated(
                    hw.description, student_answer,
                    student=sub.student, current_submission_pk=sub.pk
                )
                if ai_check and ai_check['is_ai'] and ai_check['confidence'] >= 75:
                    has_suspicion = True
                    confidence = ai_check['confidence']
                    ai_warning += (
                        f"\n\n🔍 AI tekshiruvi: Javobda suniy intellekt belgilari aniqlandi "
                        f"(ishonch: {confidence}%).\n"
                        f"📋 Sabab: {ai_check['reason']}"
                    )

                similarity_result = _check_similarity_with_others(hw, sub, student_answer)
                if similarity_result and similarity_result['is_plagiat']:
                    has_suspicion = True
                    ai_warning += (
                        f"\n\n🔄 O'xshashlik: {similarity_result['similar_to']} bilan "
                        f"{similarity_result['similarity']}% o'xshash.\n"
                        f"📋 {similarity_result['reason']}"
                    )

                if has_suspicion:
                    feedback_text = (
                        "⏳ Vazifangiz ustoz tekshiruviga yuborildi.\n"
                        "Sabab: Javobda shubhali belgilar aniqlandi."
                    )
                    sub.ai_feedback = feedback_text + ai_warning
                    sub.feedback = feedback_text
                    sub.ai_checked = True
                    sub.save(update_fields=['ai_feedback', 'feedback', 'ai_checked'])

                    teachers = hw.lesson.profession.teachers.all()
                    for teacher in teachers:
                        Message.objects.create(
                            title="🔍 Shubhali vazifa — tekshirish kerak",
                            content=(
                                f"👤 O'quvchi: {sub.student.full_name}\n"
                                f"📚 Kurs: {hw.lesson.profession.name}\n"
                                f"📖 Vazifa: {hw.lesson.title}\n"
                                f"{ai_warning}\n\n"
                                f"⚠️ AI shubhali belgilar topdi, shuning uchun baho qo'yilmadi. "
                                f"Iltimos, vazifani tekshirib, o'zingiz baholang."
                            ),
                            message_type='personal', recipient=teacher,
                            sender=sub.student
                        )
                    notify_admins(
                        f"🔍 <b>Shubhali vazifa</b>\n\n"
                        f"👤 {sub.student.first_name} {sub.student.last_name}\n"
                        f"📚 {hw.lesson.profession.name} / {hw.lesson.title}\n"
                        f"⚠️ Baho qo'yilmadi — ustoz tekshirishi kerak"
                        f"{ai_warning}"
                    )
                else:
                    ai_result = _get_ai_grade(hw.description, student_answer)
                    if ai_result:
                        sub.grade = ai_result['grade']
                        sub.status = ai_result['status']
                        sub.graded_at = timezone.now()
                        feedback_text = f"🤖 AI xulosasi:\n{ai_result['feedback']}"
                        sub.ai_feedback = feedback_text
                        sub.feedback = feedback_text
                        sub.ai_checked = True
                        sub.save(update_fields=[
                            'grade', 'status', 'graded_at',
                            'ai_feedback', 'feedback', 'ai_checked'
                        ])

                        if ai_result['status'] == 'graded':
                            if not sub.coin_awarded:
                                coin_amount = 5
                                if not sub.is_late:
                                    coin_amount = 10
                                if ai_result['grade'] >= 9:
                                    coin_amount += 5
                                elif ai_result['grade'] >= 8:
                                    coin_amount += 3
                                if sub.student.is_premium:
                                    coin_amount *= 2
                                sub.student.add_coins(coin_amount, f"Vazifa baholandi: {hw.lesson.title}")
                                sub.coin_awarded = True
                                sub.save(update_fields=['coin_awarded'])
                                ActivityLog.objects.create(
                                    user=sub.student, action_type='homework_graded',
                                    description=f"Vazifa AI baholadi: {hw.lesson.title} - Baho: {ai_result['grade']}, +{coin_amount} coin"
                                )
                            from accounts.views import _notify_ai_graded
                            _notify_ai_graded(sub, ai_result)
                        else:
                            from accounts.views import _notify_ai_revision
                            _notify_ai_revision(sub, ai_result)
                    else:
                        sub.ai_checked = True
                        sub.save(update_fields=['ai_checked'])

                count += 1

            except Exception as e:
                import traceback
                self.stderr.write(f"Xatolik (submission #{sub.pk}): {e}")
                traceback.print_exc()

        self.stdout.write(f"Tekshirildi: {count} ta vazifa")
