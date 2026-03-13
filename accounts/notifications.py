"""
Avtomatik xabar yuborish tizimi
Rag'batlantiruvchi va ogohlantiruvchi xabarlar
"""
from django.utils import timezone
from datetime import timedelta
from django.db.models import Avg, Count, Sum
from .models import (
    Message, CustomUser, CourseEnrollment, Lesson, VideoProgress,
    TestResult, HomeworkSubmission, Homework, Test, VideoLesson
)


def send_notification(user, title, content, message_type='motivation'):
    """Xabar yuborish"""
    Message.objects.create(
        recipient=user,
        sender=None,
        title=title,
        content=content,
        message_type=message_type
    )


def check_first_lesson_completed(user, lesson):
    """Birinchi darsni tugatganini tekshirish"""
    # Faqat birinchi marta video ko'rganda
    total_watched = VideoProgress.objects.filter(user=user, watched=True).count()
    if total_watched == 1:
        send_notification(
            user,
            "🚀 Tabriklaymiz! O'rganishni boshladingiz!",
            f"Siz birinchi darsingizni tugatdingiz! Bu ajoyib boshlang'ich. Davom eting va yangi bilimlar oling!",
            'achievement'
        )


def check_first_test_passed(user, test_result):
    """Birinchi testdan o'tganini tekshirish"""
    passed_tests = TestResult.objects.filter(student=user, passed=True).count()
    if passed_tests == 1 and test_result.passed:
        send_notification(
            user,
            "🎯 Birinchi yutuq! Oldinga!",
            f"Siz birinchi testingizdan muvaffaqiyatli o'tdingiz! Ball: {test_result.score}%. Bundan ham yaxshisiga erishishingiz mumkin!",
            'achievement'
        )


def _notify_admin_progress(user, profession, milestone):
    """Admin xabarlar bo'limiga va Telegram orqali kurs progress xabarini yuborish"""
    from telegram_bot.utils import notify_admins

    emoji_map = {25: '🌱', 50: '⭐', 75: '🔥', 90: '🏆'}
    emoji = emoji_map.get(milestone, '📊')

    # Adminlarga tizim ichida xabar
    admins = CustomUser.objects.filter(role='admin')
    for admin in admins:
        Message.objects.create(
            recipient=admin,
            sender=None,
            title=f"{emoji} {user.full_name} — {profession.name} {milestone}% tugatdi!",
            content=(
                f"O'quvchi: {user.full_name} (@{user.username})\n"
                f"Kurs: {profession.name}\n"
                f"Progress: {milestone}% bajarildi\n\n"
                f"{'Tabriklaymiz! Kurs deyarli tugadi! 🎉' if milestone >= 90 else 'O`quvchi yaxshi rivojlanmoqda.'}"
            ),
            message_type='system'
        )

    # Telegram orqali adminlarga
    bot_text = (
        f"{emoji} <b>Kurs progress xabari</b>\n\n"
        f"👤 O'quvchi: <b>{user.full_name}</b> (@{user.username})\n"
        f"📚 Kurs: <b>{profession.name}</b>\n"
        f"📊 Progress: <b>{milestone}%</b> bajarildi\n\n"
        f"{'🎉 Kurs deyarli tugadi!' if milestone >= 90 else '✅ O`quvchi yaxshi rivojlanmoqda.'}"
    )
    notify_admins(bot_text)


def check_course_progress_milestones(user, profession):
    """Kurs progressi bosqichlarini tekshirish (25%, 50%, 75%, 90%)"""
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
    
    completed_tests = TestResult.objects.filter(
        student=user,
        test__lesson__profession=profession,
        passed=True
    ).values('test__lesson_id').distinct().count()
    
    completed_homeworks = HomeworkSubmission.objects.filter(
        student=user,
        homework__lesson__profession=profession,
        status__in=['accepted', 'graded']
    ).values('homework__lesson_id').distinct().count()
    
    completed = watched_videos + completed_tests + completed_homeworks
    
    # Video + test + homework soni
    total_videos = VideoLesson.objects.filter(lesson__profession=profession).count()
    total_tests = Test.objects.filter(lesson__profession=profession).count()
    total_homeworks = Homework.objects.filter(lesson__profession=profession).count()
    total_items = total_videos + total_tests + total_homeworks
    
    if total_items == 0:
        return
    
    progress = (completed / total_items) * 100
    
    # Avvalgi xabarlar yuborilganmi tekshirish
    existing_titles = Message.objects.filter(
        recipient=user,
        message_type='motivation',
        title__icontains=profession.name
    ).values_list('title', flat=True)
    existing_str = str(existing_titles)

    milestones = [
        (90, "🏆", f"{profession.name} kursining 90% tugadi!", f"Ajoyib! Kurs deyarli tugadi! Oxirgi qadamlarni ham bajaring va sertifikatingizni oling! 🎓🏆"),
        (75, "🔥", f"{profession.name} kursining 75% tugadi!", f"Siz allaqachon kursning 3/4 qismini tugatdingiz! Oxirigacha oz qoldi, davom eting! 💪"),
        (50, "🎉", f"{profession.name} kursining yarmiga yetdingiz!", f"Siz kursning 50% ni tugatdingiz! Ajoyib natija, davom eting! 💪"),
        (25, "✨", f"{profession.name} kursining 25% tugadi!", f"Yaxshi boshlang'ich! Siz allaqachon kursning chorak qismini tugatdingiz. Oldinga! 🚀"),
    ]

    for threshold, emoji, title, content in milestones:
        pct_str = f"{threshold}%"
        if progress >= threshold and pct_str not in existing_str:
            send_notification(user, f"{emoji} {title}", content, 'motivation')
            _notify_admin_progress(user, profession, threshold)
            break


def check_coin_reward(user, amount):
    """Coin olganini bildirish"""
    send_notification(
        user,
        f"🪙 Bugun +{amount} coin oldingiz!",
        f"Siz {amount} coin ishlab oldingiz! Coinlarni do'konda turli sovg'alarga almashtirishingiz mumkin.",
        'achievement'
    )


def check_test_difficulty(user, test_result):
    """Ko'p testdan yiqilganini tekshirish"""
    lesson = test_result.test.lesson
    
    # Shu testdan necha marta yiqilgan
    failed_attempts = TestResult.objects.filter(
        student=user,
        test=test_result.test,
        passed=False
    ).count()
    
    if failed_attempts >= 2 and not test_result.passed:
        send_notification(
            user,
            f"📚 {lesson.title} mavzusida qiyinchilik",
            f"Bu mavzuda qiyinchilik bor ko'rinadi. Darsni qayta ko'rib chiqishni va savollarni o'qituvchiga berishni tavsiya qilamiz. Har qanday qiyinchilik - o'rganish imkoniyati!",
            'recommendation'
        )


def check_homework_reminder(user, homework):
    """Uyga vazifa eslatmasi"""
    # Vazifa topshirilmagan va deadline yaqin
    if homework.deadline:
        days_left = (homework.deadline - timezone.now().date()).days
        if days_left <= 2 and days_left >= 0:
            # Allaqachon eslatma yuborilganmi
            exists = Message.objects.filter(
                recipient=user,
                message_type='reminder',
                title__icontains=homework.lesson.title,
                created_at__date=timezone.now().date()
            ).exists()
            
            if not exists:
                send_notification(
                    user,
                    f"⏰ Uyga vazifa muddati yaqinlashmoqda!",
                    f"'{homework.lesson.title}' darsining uyga vazifasi {days_left} kun ichida tugaydi. Topshirishni unutmang!",
                    'reminder'
                )


def check_inactivity(user):
    """Faolsizlikni tekshirish (3+ kun)"""
    if not user.last_activity:
        return
    
    days_inactive = (timezone.now() - user.last_activity).days
    
    if days_inactive >= 3:
        # Bugun allaqachon xabar yuborilganmi
        today_reminder = Message.objects.filter(
            recipient=user,
            message_type='warning',
            title__icontains="faollik yo'q",
            created_at__date=timezone.now().date()
        ).exists()
        
        if not today_reminder:
            send_notification(
                user,
                f"🙂 {days_inactive} kundan beri faollik yo'q",
                f"Siz {days_inactive} kundan beri platformada faol emassiz. O'rganishni davom ettiraylikmi? Sizni kutib qolyapmiz!",
                'warning'
            )


def check_progress_decrease(user, profession):
    """Progress pasayishini tekshirish"""
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
    
    # Agar avval faol bo'lib, hozir sekinlashgan bo'lsa
    if previous_activity > 3 and recent_activity == 0:
        exists = Message.objects.filter(
            recipient=user,
            message_type='warning',
            title__icontains="sekinlash",
            created_at__gte=week_ago
        ).exists()
        
        if not exists:
            send_notification(
                user,
                f"📉 {profession.name} kursida sekinlashdingiz",
                f"Avval yaxshi edingiz, hozir sekinlashdingiz. Yordam kerakmi? O'qituvchiga murojaat qilishingiz mumkin.",
                'warning'
            )


def check_streak_achievement(user, streak_days):
    """Ketma-ket kunlar yutuqi"""
    milestones = [3, 7, 14, 30]
    
    if streak_days in milestones:
        send_notification(
            user,
            f"🔥 {streak_days} kun ketma-ket o'qidingiz!",
            f"Ajoyib! Siz {streak_days} kun ketma-ket platformada faol bo'ldingiz. Bu katta yutuq, davom eting!",
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
                f"Tabriklaymiz! Siz reytingda {rank}-o'rindasiz! Davom eting va 1-o'ringa chiqing!",
                'achievement'
            )


def check_homework_graded(user, submission, grade):
    """Uyga vazifa baholandi"""
    send_notification(
        user,
        f"📝 Uyga vazifa baholandi!",
        f"'{submission.homework.lesson.title}' darsining vazifasi tekshirildi. Baho: {grade}. Natijani ko'ring!",
        'system'
    )


def check_teacher_comment(user, lesson_title, teacher_name):
    """O'qituvchi izoh qoldirdi"""
    send_notification(
        user,
        f"💬 O'qituvchi izoh qoldirdi",
        f"{teacher_name} sizning '{lesson_title}' vazifangizga izoh yozdi. Ko'rib chiqing!",
        'system'
    )


def check_new_device_login(user, device_name, ip_address):
    """Yangi qurilmadan login"""
    send_notification(
        user,
        f"🔐 Yangi qurilmadan kirildi",
        f"Hisobingizga '{device_name}' qurilmasidan kirildi (IP: {ip_address}). Agar bu siz bo'lmasangiz, parolingizni o'zgartiring!",
        'security'
    )


def check_password_changed(user):
    """Parol o'zgartirildi"""
    send_notification(
        user,
        f"🔒 Parol muvaffaqiyatli yangilandi",
        f"Xavfsizlik uchun parolingiz yangilandi. Agar bu siz bo'lmasangiz, darhol biz bilan bog'laning!",
        'security'
    )


def notify_new_lesson_added(profession, lesson_title):
    """Yangi dars qo'shildi - barcha yozilganlarga xabar"""
    enrollments = CourseEnrollment.objects.filter(profession=profession)
    
    for enrollment in enrollments:
        send_notification(
            enrollment.user,
            f"📢 Yangi dars qo'shildi!",
            f"'{profession.name}' kursiga yangi dars qo'shildi: '{lesson_title}'. Ko'rib chiqing!",
            'system'
        )


def recommend_similar_courses(user):
    """O'xshash kurslarni tavsiya qilish"""
    # User qaysi kursda o'qiyotganini aniqlash
    enrollments = user.enrollments.all()
    if not enrollments.exists():
        return
    
    from .models import Profession
    
    # Yozilmagan kurslar
    enrolled_profession_ids = enrollments.values_list('profession_id', flat=True)
    other_professions = Profession.objects.exclude(pk__in=enrolled_profession_ids)[:3]
    
    if other_professions:
        profession_names = ", ".join([p.name for p in other_professions])
        
        # Oxirgi 7 kunda shu xabar yuborilganmi
        exists = Message.objects.filter(
            recipient=user,
            message_type='recommendation',
            title__icontains="tavsiya",
            created_at__gte=timezone.now() - timedelta(days=7)
        ).exists()
        
        if not exists:
            send_notification(
                user,
                f"👀 Sizga o'xshash o'quvchilar nima o'qiyapti",
                f"Sizga quyidagi kurslarni tavsiya qilamiz: {profession_names}. Ko'rib chiqing!",
                'recommendation'
            )


# ============ Video ko'rganda chaqiriladigan funksiya ============
def on_video_watched(user, video_progress):
    """Video ko'rilganda"""
    lesson = video_progress.video.lesson
    profession = lesson.profession
    
    # Birinchi dars tekshirish
    check_first_lesson_completed(user, lesson)
    
    # Kurs progressi tekshirish
    check_course_progress_milestones(user, profession)


# ============ Test topshirilganda chaqiriladigan funksiya ============
def on_test_completed(user, test_result):
    """Test topshirilganda"""
    # Birinchi test
    check_first_test_passed(user, test_result)
    
    # Qiyinchilik tekshirish
    if not test_result.passed:
        check_test_difficulty(user, test_result)
    
    # Kurs progressi
    profession = test_result.test.lesson.profession
    check_course_progress_milestones(user, profession)


# ============ Vazifa baholanganda chaqiriladigan funksiya ============
def on_homework_graded(user, submission, grade):
    """Vazifa baholanganda"""
    check_homework_graded(user, submission, grade)
    
    # Kurs progressi
    profession = submission.homework.lesson.profession
    check_course_progress_milestones(user, profession)
