"""
1 soat tahrirlash muddati tugagan vazifalarni AI bilan tekshirish.
Har 5 daqiqada cron/scheduler orqali ishga tushiriladi:
  python manage.py check_ai_homework
"""
from datetime import timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone


def _calculate_penalty(ai_check, similarity_result):
    """Jarima coinlarini hisoblash (max 30).

    Muhim: jarima FAQAT juda yuqori ishonchda qo'llaniladi (>= 95%).
    85–94% oralig'ida jarima QO'LLANMAYDI — ustozga xabar beriladi, tekshiradi.
    Bu false-positive holatlarda o'quvchini nohaqdan jarimalashdan saqlaydi.
    """
    penalty = 0
    reasons = []

    # AI belgilari — faqat 95%+ ishonchda jarima
    if ai_check and ai_check.get('is_ai') and ai_check.get('confidence', 0) >= 95:
        confidence = ai_check['confidence']
        if confidence >= 98:
            penalty += 15
        else:
            penalty += 10
        reasons.append(f"Suniy intellekt (AI) yordamida yozilgan ({confidence}% ishonch)")

    # Plagiat — faqat 95%+ o'xshashlikda jarima
    if similarity_result and similarity_result.get('is_plagiat'):
        sim = similarity_result['similarity']
        similar_to = similarity_result.get('similar_to', 'boshqa o\'quvchi')
        if sim >= 98:
            penalty += 15
        elif sim >= 95:
            penalty += 10
        else:
            # 90–94% — xabar bor, jarima yo'q
            pass
        if sim >= 95:
            reasons.append(f"{similar_to} ning javobidan ko'chirilgan ({sim}% o'xshash)")

    return min(penalty, 30), reasons


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

                # Ikki bosqichli chegara (false-positive'ni sezilarli kamaytirish uchun):
                #   • strong_gate: shu chegaradan past bo'lsa — AVTOMATIK ravishda
                #     "shubha yo'q" hisoblanadi, o'quvchi hech qanday jarima olmaydi.
                #   • hard_gate:  faqat shu chegaradan yuqori bo'lsa — vazifa qayta
                #     ishlashga qaytariladi va coin jarimasi qo'llaniladi.
                #   • oraliq (strong_gate ≤ conf < hard_gate): ustoz/adminga xabar
                #     beriladi, lekin o'quvchining statusi va coini TEGILMAYDI.
                is_strong = academic_ctx.get('is_strong_student')
                strong_gate = 92 if is_strong else 85     # xabar boshlanadigan chegara
                hard_gate   = 96 if is_strong else 95     # jarima boshlanadigan chegara

                ai_confidence = 0
                ai_is_suspect = False   # 85–95 oraliq: xabar bor, jarima yo'q
                ai_is_penalty = False   # 95+ : real jarima
                if ai_check_result and ai_check_result['is_ai']:
                    ai_confidence = ai_check_result['confidence']
                    if ai_confidence >= hard_gate:
                        ai_is_penalty = True
                    elif ai_confidence >= strong_gate:
                        ai_is_suspect = True

                if ai_is_penalty or ai_is_suspect:
                    has_suspicion = True
                    ai_warning += (
                        f"\n\n🔍 AI tekshiruvi: Javobda suniy intellekt belgilari aniqlandi "
                        f"(ishonch: {ai_confidence}%).\n"
                        f"📋 Sabab: {ai_check_result['reason']}"
                    )

                # 2. Plagiat tekshirish
                similarity_result = _check_similarity_with_others(hw, sub, student_answer)
                sim_is_penalty = False
                sim_is_suspect = False
                if similarity_result and similarity_result['is_plagiat']:
                    sim = similarity_result['similarity']
                    if sim >= 95:
                        sim_is_penalty = True
                    elif sim >= 90:
                        sim_is_suspect = True
                    if sim_is_penalty or sim_is_suspect:
                        has_suspicion = True
                        ai_warning += (
                            f"\n\n🔄 O'xshashlik: {similarity_result['similar_to']} bilan "
                            f"{sim}% o'xshash.\n"
                            f"📋 {similarity_result['reason']}"
                        )

                # "Real" jarima kerakmi? Faqat yuqori ishonch bo'lsagina
                is_hard_case = ai_is_penalty or sim_is_penalty

                if has_suspicion and not is_hard_case:
                    # 🟡 ORALIQ ZONA: xabar bor, jarima YO'Q, status ham o'zgarmaydi.
                    # Ustoz o'zi qarab chiqadi — o'quvchini nohaqdan jazolamaymiz.
                    teachers = hw.lesson.profession.teachers.all()
                    for teacher in teachers:
                        Message.objects.create(
                            title="🟡 Vazifada shubha (jarima yo'q) — ustoz tekshirsin",
                            content=(
                                f"👤 O'quvchi: {sub.student.full_name}\n"
                                f"📚 Kurs: {hw.lesson.profession.name}\n"
                                f"📖 Vazifa: {hw.lesson.title}\n"
                                f"{ai_warning}\n\n"
                                f"⚠️ Ishonch chegarasi past — jarima QO'LLANMADI.\n"
                                f"👀 Iltimos, o'zingiz tekshiring va qaror qiling."
                            ),
                            message_type='personal', recipient=teacher,
                            sender=sub.student,
                        )
                    sub.ai_checked = True
                    # ai_feedback'ga ichki eslatma yozamiz — o'quvchiga ko'rsatilmaydi,
                    # ustoz submission oynasida ko'radi.
                    sub.ai_feedback = f"🟡 Shubhali belgilar (past ishonch):{ai_warning}"
                    sub.save(update_fields=['ai_checked', 'ai_feedback'])
                    count += 1
                    continue

                if is_hard_case:
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
