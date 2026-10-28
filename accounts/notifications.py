"""
Avtomatik xabar yuboriş tizimi
Rağbatlantiruvçi va ogohlantiruvçi xabarlar
"""
from django.utils import timezone
from datetime import timedelta
from django.db.models import Avg, Count, Sum
from .models import (
    Message, CustomUser, CourseEnrollment, Lesson, VideoProgress,
    TestResult, HomeworkSubmission, Homework, VideoLesson
)


def send_notification(user, title, content, message_type='motivation'):
    """Xabar yuboriş"""
    Message.objects.create(
        recipient=user,
        sender=None,
        title=title,
        content=content,
        message_type=message_type
    )


def check_first_lesson_completed(user, lesson):
    """Birinçi darsni tugatganini tekşiriş"""
    # Faqat birinçi marta video körganda
    total_watched = VideoProgress.objects.filter(user=user, watched=True).count()
    if total_watched == 1:
        send_notification(
            user,
            "🚀 Tabriklaymiz! Örganişni boşladingiz!",
            f"Siz birinçi darsingizni tugatdingiz! Bu ajoyib boşlanğiç. Davom eting va yangi bilimlar oling!",
            'achievement'
        )


def check_first_test_passed(user, test_result):
    """Birinçi testdan ötganini tekşiriş"""
    passed_tests = TestResult.objects.filter(student=user, passed=True).count()
    if passed_tests == 1 and test_result.passed:
        send_notification(
            user,
            "🎯 Birinçi yutuq! Oldinga!",
            f"Siz birinçi testingizdan muvaffaqiyatli ötdingiz! Ball: {test_result.score}%. Bundan ham yaxşisiga erişişingiz mumkin!",
            'achievement'
        )


def _notify_admin_progress(user, profession, milestone):
    """Admin xabarlar bölimiga va Telegram orqali kurs progress xabarini yuboriş"""
    from telegram_bot.utils import notify_admins

    # Allaqaçon şu milestone uçun xabar yuborilganmi tekşiriş
    check_title = f"{user.full_name} — {profession.name} {milestone}%"
    already_sent = Message.objects.filter(
        message_type='system',
        title__icontains=check_title
    ).exists()
    if already_sent:
        return

    emoji_map = {25: '🌱', 50: '⭐', 75: '🔥', 90: '🏆'}
    emoji = emoji_map.get(milestone, '📊')

    # Adminlarga tizim içida xabar
    admins = CustomUser.objects.filter(role='admin')
    for admin in admins:
        Message.objects.create(
            recipient=admin,
            sender=None,
            title=f"{emoji} {user.full_name} — {profession.name} {milestone}% tugatdi!",
            content=(
                f"Öquvçi: {user.full_name} (@{user.username})\n"
                f"Kurs: {profession.name}\n"
                f"Progress: {milestone}% bajarildi\n\n"
                f"{'Tabriklaymiz! Kurs deyarli tugadi! 🎉' if milestone >= 90 else 'O`quvchi yaxshi rivojlanmoqda.'}"
            ),
            message_type='system'
        )

    # Telegram orqali adminlarga
    bot_text = (
        f"{emoji} <b>Kurs progress xabari</b>\n\n"
        f"👤 Öquvçi: <b>{user.full_name}</b> (@{user.username})\n"
        f"📚 Kurs: <b>{profession.name}</b>\n"
        f"📊 Progress: <b>{milestone}%</b> bajarildi\n\n"
        f"{'🎉 Kurs deyarli tugadi!' if milestone >= 90 else '✅ O`quvchi yaxshi rivojlanmoqda.'}"
    )
    notify_admins(bot_text)


def notify_admin_video_duration_unknown(video):
    """Video davomiyligi serverda aniqlanmadi — dars yopilmaydi, admin aralaşişi kerak.

    Davomiylik bölmasa köriş talabini hisoblab bölmaydi va "Kördim" bloklanadi
    (mijoz aytgan davomiylikka işoniş — anti-cheat teşigi). Şuning uçun admin
    darhol xabardor qilinadi: kurs bölimida `duration` (daqiqa) qölda kiritilsa
    dars yana işlaydi.
    """
    title = f"⚠️ Video davomiyligi aniqlanmadi: {video.lesson.title}"
    if Message.objects.filter(message_type='system', title=title).exists():
        return

    lesson = video.lesson
    content = (
        f"Dars: {lesson.title}\n"
        f"Kurs: {lesson.profession.name if lesson.profession_id else '—'}\n"
        f"Havola: {video.youtube_url or video.video_url or '—'}\n\n"
        "Server YouTube/Vimeo'dan video davomiyligini olişga urinib kördi, lekin "
        "aniqlay olmadi. Davomiylik bölmasa köriş vaqtini tekşirib bölmaydi, "
        "şuning uçun öquvçilar bu darsni YOPA OLMAYDI.\n\n"
        "Yeçim: darsni tahrirlab \"Davomiyligi (daqiqa)\" maydonini töldiring."
    )

    for admin in CustomUser.objects.filter(role='admin'):
        Message.objects.create(
            recipient=admin,
            sender=None,
            title=title,
            content=content,
            message_type='system',
        )

    try:
        from telegram_bot.utils import notify_admins
        notify_admins(
            f"⚠️ <b>Video davomiyligi aniqlanmadi</b>\n\n"
            f"📚 Dars: <b>{lesson.title}</b>\n"
            f"🔗 {video.youtube_url or video.video_url or '—'}\n\n"
            f"Öquvçilar bu darsni yopa olmaydi. Darsdagi "
            f"\"Davomiyligi (daqiqa)\" maydonini töldiring."
        )
    except Exception:
        pass


def check_course_progress_milestones(user, profession):
    """Kurs progressi bosqiçlarini tekşiriş (25%, 50%, 75%, 90%)"""
    # Umumiy darslar
    total_lessons = Lesson.objects.filter(profession=profession).count()
    if total_lessons == 0:
        return
    
    # Tugatilgan darslar
    watched_videos = VideoProgress.objects.filter(
        user=user,
        video__lesson__profession=profession,
        watched=True
    ).count()
    
    passed_test_lesson_ids = set(TestResult.objects.filter(
        student=user,
        test__lesson__profession=profession,
        passed=True
    ).values_list('test__lesson_id', flat=True))

    from quiz.models import Attempt as QuizAttempt
    passed_test_lesson_ids.update(QuizAttempt.objects.filter(
        student=user,
        passed=True,
        status__in=[QuizAttempt.Status.SUBMITTED, QuizAttempt.Status.GRADED],
        quiz__lesson__profession=profession,
    ).exclude(quiz__lesson_id=None).values_list('quiz__lesson_id', flat=True))
    completed_tests = len(passed_test_lesson_ids)
    
    completed_homeworks = HomeworkSubmission.objects.filter(
        student=user,
        homework__lesson__profession=profession,
        status__in=['accepted', 'graded']
    ).values('homework_id').distinct().count()
    
    completed = watched_videos + completed_tests + completed_homeworks
    
    # Video + test + homework soni
    total_videos = VideoLesson.objects.filter(lesson__profession=profession).count()
    total_tests = Lesson.objects.filter(profession=profession, lesson_type='test').count()
    total_homeworks = Homework.objects.filter(lesson__profession=profession).count()
    total_items = total_videos + total_tests + total_homeworks
    
    if total_items == 0:
        return
    
    progress = (completed / total_items) * 100
    
    milestones = [
        (90, "🏆", f"{profession.name} kursining 90% tugadi!", f"Ajoyib! Kurs deyarli tugadi! Oxirgi qadamlarni ham bajaring va sertifikatingizni oling! 🎓🏆"),
        (75, "🔥", f"{profession.name} kursining 75% tugadi!", f"Siz allaqaçon kursning 3/4 qismini tugatdingiz! Oxirigaça oz qoldi, davom eting! 💪"),
        (50, "🎉", f"{profession.name} kursining yarmiga yetdingiz!", f"Siz kursning 50% ni tugatdingiz! Ajoyib natija, davom eting! 💪"),
        (25, "✨", f"{profession.name} kursining 25% tugadi!", f"Yaxşi boşlanğiç! Siz allaqaçon kursning çorak qismini tugatdingiz. Oldinga! 🚀"),
    ]

    for threshold, emoji, title, content in milestones:
        if progress >= threshold:
            # Öquvçiga şu milestone allaqaçon yuborilganmi
            already_sent_to_user = Message.objects.filter(
                recipient=user,
                message_type='motivation',
                title__icontains=f"{profession.name} kursining {threshold}%"
            ).exists()
            if not already_sent_to_user:
                send_notification(user, f"{emoji} {title}", content, 'motivation')
                _notify_admin_progress(user, profession, threshold)
            break


def check_coin_reward(user, amount):
    """Coin olganini bildiriş"""
    send_notification(
        user,
        f"🪙 Bugun +{amount} coin oldingiz!",
        f"Siz {amount} coin işlab oldingiz! Coinlarni dökonda turli sovğalarga almaştirişingiz mumkin.",
        'achievement'
    )


def check_test_difficulty(user, test_result):
    """Köp testdan yiqilganini tekşiriş"""
    lesson = test_result.test.lesson
    
    # Şu testdan neça marta yiqilgan
    failed_attempts = TestResult.objects.filter(
        student=user,
        test=test_result.test,
        passed=False
    ).count()
    
    if failed_attempts >= 2 and not test_result.passed:
        send_notification(
            user,
            f"📚 {lesson.title} mavzusida qiyinçilik",
            f"Bu mavzuda qiyinçilik bor körinadi. Darsni qayta körib çiqişni va savollarni öqituvçiga berişni tavsiya qilamiz. Har qanday qiyinçilik - örganiş imkoniyati!",
            'recommendation'
        )


def check_homework_reminder(user, homework):
    """Uyga vazifa eslatmasi"""
    # Vazifa topşirilmagan va deadline yaqin
    if homework.deadline:
        days_left = (homework.deadline - timezone.now().date()).days
        if days_left <= 2 and days_left >= 0:
            # Allaqaçon eslatma yuborilganmi
            exists = Message.objects.filter(
                recipient=user,
                message_type='reminder',
                title__icontains=homework.lesson.title,
                created_at__date=timezone.now().date()
            ).exists()
            
            if not exists:
                send_notification(
                    user,
                    f"⏰ Uyga vazifa muddati yaqinlaşmoqda!",
                    f"'{homework.lesson.title}' darsining uyga vazifasi {days_left} kun içida tugaydi. Topşirişni unutmang!",
                    'reminder'
                )


def check_inactivity(user):
    """Faolsizlikni tekşiriş (3+ kun)"""
    if not user.last_activity:
        return
    
    days_inactive = (timezone.now() - user.last_activity).days
    
    if days_inactive >= 3:
        # Bugun allaqaçon xabar yuborilganmi
        today_reminder = Message.objects.filter(
            recipient=user,
            message_type='warning',
            title__icontains="faollik yöq",
            created_at__date=timezone.now().date()
        ).exists()
        
        if not today_reminder:
            send_notification(
                user,
                f"🙂 {days_inactive} kundan beri faollik yöq",
                f"Siz {days_inactive} kundan beri platformada faol emassiz. Örganişni davom ettiraylikmi? Sizni kutib qolyapmiz!",
                'warning'
            )


def check_progress_decrease(user, profession):
    """Progress pasayişini tekşiriş"""
    # Oxirgi 7 kundagi faollik
    week_ago = timezone.now() - timedelta(days=7)
    two_weeks_ago = timezone.now() - timedelta(days=14)
    
    recent_activity = VideoProgress.objects.filter(
        user=user,
        video__lesson__profession=profession,
        watched_at__gte=week_ago
    ).count()
    
    previous_activity = VideoProgress.objects.filter(
        user=user,
        video__lesson__profession=profession,
        watched_at__gte=two_weeks_ago,
        watched_at__lt=week_ago
    ).count()
    
    # Agar avval faol bölib, hozir sekinlaşgan bölsa
    if previous_activity > 3 and recent_activity == 0:
        exists = Message.objects.filter(
            recipient=user,
            message_type='warning',
            title__icontains="sekinlaş",
            created_at__gte=week_ago
        ).exists()
        
        if not exists:
            send_notification(
                user,
                f"📉 {profession.name} kursida sekinlaşdingiz",
                f"Avval yaxşi edingiz, hozir sekinlaşdingiz. Yordam kerakmi? Öqituvçiga murojaat qilişingiz mumkin.",
                'warning'
            )


def check_streak_achievement(user, streak_days):
    """Ketma-ket kunlar yutuqi"""
    milestones = [3, 7, 14, 30]
    
    if streak_days in milestones:
        send_notification(
            user,
            f"🔥 {streak_days} kun ketma-ket öqidingiz!",
            f"Ajoyib! Siz {streak_days} kun ketma-ket platformada faol böldingiz. Bu katta yutuq, davom eting!",
            'achievement'
        )


def check_leaderboard_achievement(user, rank):
    """Reyting yutugi"""
    if rank <= 10:
        exists = Message.objects.filter(
            recipient=user,
            message_type='achievement',
            title__icontains="Top-10",
            created_at__gte=timezone.now() - timedelta(days=7)
        ).exists()
        
        if not exists:
            send_notification(
                user,
                f"😎 Siz Top-10 ga kirdingiz!",
                f"Tabriklaymiz! Siz reytingda {rank}-örindasiz! Davom eting va 1-öringa çiqing!",
                'achievement'
            )


def check_homework_graded(user, submission, grade):
    """Uyga vazifa baholandi"""
    send_notification(
        user,
        f"📝 Uyga vazifa baholandi!",
        f"'{submission.homework.lesson.title}' darsining vazifasi tekşirildi. Baho: {grade}. Natijani köring!",
        'system'
    )


def check_teacher_comment(user, lesson_title, teacher_name):
    """Öqituvçi izoh qoldirdi"""
    send_notification(
        user,
        f"💬 Öqituvçi izoh qoldirdi",
        f"{teacher_name} sizning '{lesson_title}' vazifangizga izoh yozdi. Körib çiqing!",
        'system'
    )


def check_new_device_login(user, device_name, ip_address):
    """Yangi qurilmadan login"""
    send_notification(
        user,
        f"🔐 Yangi qurilmadan kirildi",
        f"Hisobingizga '{device_name}' qurilmasidan kirildi (IP: {ip_address}). Agar bu siz bölmasangiz, parolingizni özgartiring!",
        'security'
    )


def check_password_changed(user):
    """Parol özgartirildi"""
    send_notification(
        user,
        f"🔒 Parol muvaffaqiyatli yangilandi",
        f"Xavfsizlik uçun parolingiz yangilandi. Agar bu siz bölmasangiz, darhol biz bilan boğlaning!",
        'security'
    )


def notify_new_lesson_added(profession, lesson_title):
    """Yangi dars qöşildi - barça yozilganlarga xabar"""
    enrollments = CourseEnrollment.objects.filter(profession=profession)
    
    for enrollment in enrollments:
        send_notification(
            enrollment.user,
            f"📢 Yangi dars qöşildi!",
            f"'{profession.name}' kursiga yangi dars qöşildi: '{lesson_title}'. Körib çiqing!",
            'system'
        )


def recommend_similar_courses(user):
    """Öxşaş kurslarni tavsiya qiliş"""
    # User qaysi kursda öqiyotganini aniqlaş
    enrollments = user.enrollments.all()
    if not enrollments.exists():
        return
    
    from .models import Profession
    
    # Yozilmagan kurslar
    enrolled_profession_ids = enrollments.values_list('profession_id', flat=True)
    other_professions = Profession.objects.exclude(pk__in=enrolled_profession_ids)[:3]
    
    if other_professions:
        profession_names = ", ".join([p.name for p in other_professions])
        
        # Oxirgi 7 kunda şu xabar yuborilganmi
        exists = Message.objects.filter(
            recipient=user,
            message_type='recommendation',
            title__icontains="tavsiya",
            created_at__gte=timezone.now() - timedelta(days=7)
        ).exists()
        
        if not exists:
            send_notification(
                user,
                f"👀 Sizga öxşaş öquvçilar nima öqiyapti",
                f"Sizga quyidagi kurslarni tavsiya qilamiz: {profession_names}. Körib çiqing!",
                'recommendation'
            )


# ============ Video körganda çaqiriladigan funksiya ============
def on_video_watched(user, video_progress):
    """Video körilganda"""
    lesson = video_progress.video.lesson
    profession = lesson.profession
    
    # Birinçi dars tekşiriş
    check_first_lesson_completed(user, lesson)
    
    # Kurs progressi tekşiriş
    check_course_progress_milestones(user, profession)


# ============ Test topşirilganda çaqiriladigan funksiya ============
def on_test_completed(user, test_result):
    """Test topşirilganda"""
    # Birinçi test
    check_first_test_passed(user, test_result)
    
    # Qiyinçilik tekşiriş
    if not test_result.passed:
        check_test_difficulty(user, test_result)
    
    # Kurs progressi
    profession = test_result.test.lesson.profession
    check_course_progress_milestones(user, profession)


# ============ Vazifa baholanganda çaqiriladigan funksiya ============
def on_homework_graded(user, submission, grade):
    """Vazifa baholanganda"""
    check_homework_graded(user, submission, grade)
    
    # Kurs progressi
    profession = submission.homework.lesson.profession
    check_course_progress_milestones(user, profession)
