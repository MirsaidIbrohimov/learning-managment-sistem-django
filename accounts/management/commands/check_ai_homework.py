"""
1 soat tahrirlash muddati tugagan vazifalarni AI bilan tekshirish.
Har 5 daqiqada cron/scheduler orqali ishga tushiriladi:
  python manage.py check_ai_homework
"""
from datetime import timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone


def _calculate_penalty(ai_check, similarity_result):
    """Jarima coinlarini hisoblash (max 50)"""
    penalty = 0
    reasons = []

    if ai_check and ai_check.get('is_ai') and ai_check.get('confidence', 0) >= 75:
        confidence = ai_check['confidence']
        if confidence >= 95:
            penalty += 30
        elif confidence >= 85:
            penalty += 20
        else:
            penalty += 10
        reasons.append(f"Suniy intellekt (AI) yordamida yozilgan ({confidence}% ishonch)")

    if similarity_result and similarity_result.get('is_plagiat'):
        sim = similarity_result['similarity']
        similar_to = similarity_result.get('similar_to', 'boshqa o\'quvchi')
        if sim >= 95:
            penalty += 25
        elif sim >= 90:
            penalty += 15
        else:
            penalty += 10
        reasons.append(f"{similar_to} ning javobidan ko'chirilgan ({sim}% o'xshash)")

    return min(penalty, 50), reasons


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
            _get_student_academic_context,
            _notify_ai_penalty,
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
                ai_check_result = None
                similarity_result = None

                # O'quvchining o'quv faoliyatini yig'ish
                academic_ctx = _get_student_academic_context(sub.student, hw)

                # 1. AI yordamida yozilganligini tekshirish
                ai_check_result = _check_ai_generated(
                    hw.description, student_answer,
                    student=sub.student,
                    current_submission_pk=sub.pk,
                    academic_context=academic_ctx,
                )

                # Kuchli o'quvchilar uchun chegarani oshirish
                ai_threshold = 85 if academic_ctx.get('is_strong_student') else 75

                if ai_check_result and ai_check_result['is_ai'] and ai_check_result['confidence'] >= ai_threshold:
                    has_suspicion = True
                    confidence = ai_check_result['confidence']
                    ai_warning += (
                        f"\n\n🔍 AI tekshiruvi: Javobda suniy intellekt belgilari aniqlandi "
                        f"(ishonch: {confidence}%).\n"
                        f"📋 Sabab: {ai_check_result['reason']}"
                    )

                # 2. Plagiat tekshirish
                similarity_result = _check_similarity_with_others(hw, sub, student_answer)
                if similarity_result and similarity_result['is_plagiat']:
                    has_suspicion = True
                    ai_warning += (
                        f"\n\n🔄 O'xshashlik: {similarity_result['similar_to']} bilan "
                        f"{similarity_result['similarity']}% o'xshash.\n"
                        f"📋 {similarity_result['reason']}"
                    )

                if has_suspicion:
                    # Jarima hisoblash
                    penalty_coins, suspicion_reasons = _calculate_penalty(ai_check_result, similarity_result)

                    # Coinni ayirish
                    if penalty_coins > 0:
                        sub.student.remove_coins(
                            penalty_coins,
                            f"Vazifada aldov aniqlandi: {hw.lesson.title}"
                        )
                        ActivityLog.objects.create(
                            user=sub.student,
                            action_type='homework_graded',
                            description=(
                                f"Vazifada aldov: {hw.lesson.title}. "
                                f"Jarima: -{penalty_coins} coin. "
                                f"Sabab: {'; '.join(suspicion_reasons)}"
                            )
                        )

                    # Feedback tayyorlash
                    reasons_text = '; '.join(suspicion_reasons)
                    penalty_line = f"\n💸 Jarima: -{penalty_coins} coin ayirildi." if penalty_coins > 0 else ""
                    feedback_text = (
                        f"⚠️ Vazifangizda shubhali belgilar aniqlandi va qayta ishlashga qaytarildi.\n"
                        f"🔍 Sabab: {reasons_text}"
                        f"{penalty_line}\n\n"
                        f"📝 Iltimos, vazifani O'ZINGIZ bajaring va qayta yuboring!"
                    )

                    sub.ai_feedback = feedback_text + ai_warning
                    sub.feedback = feedback_text
                    sub.ai_checked = True
                    sub.status = 'revision'   # qayta ishlashga yuborish
                    sub.revision_count += 1
                    sub.save(update_fields=[
                        'ai_feedback', 'feedback', 'ai_checked', 'status', 'revision_count'
                    ])

                    # O'quvchiga xabar
                    _notify_ai_penalty(sub, penalty_coins, suspicion_reasons)

                    # Ustozlarga xabar
                    teachers = hw.lesson.profession.teachers.all()
                    for teacher in teachers:
                        Message.objects.create(
                            title="🔍 Shubhali vazifa — tekshirish kerak",
                            content=(
                                f"👤 O'quvchi: {sub.student.full_name}\n"
                                f"📚 Kurs: {hw.lesson.profession.name}\n"
                                f"📖 Vazifa: {hw.lesson.title}\n"
                                f"{ai_warning}\n\n"
                                f"{'💸 Jarima: -' + str(penalty_coins) + ' coin ayirildi.' if penalty_coins > 0 else ''}\n"
                                f"📝 Vazifa 'qayta ishlash' statusiga o'tkazildi. "
                                f"Agar noto'g'ri aniqlanganini hisoblasangiz, o'zingiz baholang."
                            ),
                            message_type='personal', recipient=teacher,
                            sender=sub.student
                        )
                    notify_admins(
                        f"🔍 <b>Shubhali vazifa</b>\n\n"
                        f"👤 {sub.student.first_name} {sub.student.last_name}\n"
                        f"📚 {hw.lesson.profession.name} / {hw.lesson.title}\n"
                        f"{'💸 Jarima: -' + str(penalty_coins) + ' coin' if penalty_coins > 0 else ''}\n"
                        f"⚠️ Statusga o'tkazildi: qayta ishlash"
                        f"{ai_warning}"
                    )
                else:
                    # Shubha yo'q — AI baholaydi
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
                                coin_amount = 5 if sub.is_late else 10
                                if ai_result['grade'] >= 9:
                                    coin_amount += 5
                                elif ai_result['grade'] >= 8:
                                    coin_amount += 3
                                if sub.student.is_premium:
                                    coin_amount *= 2
                                sub.student.add_coins(
                                    coin_amount,
                                    f"Vazifa baholandi: {hw.lesson.title}"
                                )
                                sub.coin_awarded = True
                                sub.save(update_fields=['coin_awarded'])
                                ActivityLog.objects.create(
                                    user=sub.student,
                                    action_type='homework_graded',
                                    description=(
                                        f"Vazifa AI baholadi: {hw.lesson.title} "
                                        f"— Baho: {ai_result['grade']}, +{coin_amount} coin"
                                    )
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
