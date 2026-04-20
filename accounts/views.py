from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import HttpResponse, JsonResponse
from django.db.models import Count, Q, Sum, Avg
from django.db import models, transaction
from django.utils import timezone
from datetime import timedelta
import json
import random
from .forms import (
    RegisterForm, LoginForm, ProfessionForm, UserProfileForm, 
    AdminUserEditForm, ChangePasswordForm, VideoLessonForm, HomeworkForm, DictionaryForm,
    HomeworkSubmissionForm, HomeworkGradeForm, TestForm, TestQuestionForm, CertificateForm,
    SectionForm, PasswordResetRequestForm
)
from .models import (
    Profession, Section, CustomUser, CourseEnrollment, CourseEnrollmentRequest, CourseUnenrollRequest, Lesson, VideoLesson, VideoProgress,
    Homework, HomeworkSubmission, Test, TestQuestion, TestAnswer, TestResult,
    TestUserAnswer, Dictionary, DictionaryWord, Certificate, CertificateRequest, Message, PaymentStatus, PaymentRecord, HelpRequest, Discount,
    UserDevice, UserSession, HTMLDeploy, SystemReport, PasswordResetRequest,
    Parent, ParentMessage, PremiumRequest, BlockedSection, MaintenanceMode,
    CourseApplication, SpeakingTask, SpeakingSubmission, LoginAttempt, DailySectionAccess,
    DailyLessonAccess, FinalTestPayment
)
from django.contrib.auth.hashers import make_password
from coin.models import ActivityLog, CoinTransaction

from django.core.management import call_command
from django.core.cache import cache
from telegram_bot.utils import notify_admins, notify_user, notify_group


def _reset_course_progress(user, profession):
    """O'quvchi kursdan chiqib qayta yozilganda barcha progressni tozalash.
    Video progress, homework submissions, test results, speaking submissions va sertifikatlarni o'chiradi."""
    # Video progress
    VideoProgress.objects.filter(
        user=user,
        video__lesson__profession=profession
    ).delete()

    # Homework submissions (va ularga bog'liq messages, revisions cascade bilan o'chadi)
    HomeworkSubmission.objects.filter(
        student=user,
        homework__lesson__profession=profession
    ).delete()

    # Test results (va ularga bog'liq user_answers cascade bilan o'chadi)
    TestResult.objects.filter(
        student=user,
        test__lesson__profession=profession
    ).delete()

    # Speaking submissions
    SpeakingSubmission.objects.filter(
        student=user,
        speaking_task__lesson__profession=profession
    ).delete()

    # Sertifikatlarni bekor qilish
    Certificate.objects.filter(
        student=user,
        profession=profession
    ).delete()


def _generate_ai_article(lesson_title, profession_name):
    """Video mavzusiga qarab AI maqola yaratish (background da ishlamaydi, sync)"""
    from django.conf import settings
    api_key = getattr(settings, 'OPENAI_API_KEY', None)
    if not api_key or not api_key.strip():
        return None
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key.strip(), timeout=60)
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Sen tajribali IT o'qituvchisan. O'zbek tilida professional maqola yoz. "
                        "HTML formatda yoz (h2, h3, p, ul, li, strong, em, code taglardan foydalan). "
                        "Maqola 400-600 so'z bo'lsin. Mavzuni chuqur tushuntir, misollar keltir. "
                        "Boshida qisqa kirish, keyin asosiy tushunchalar, oxirida xulosa bo'lsin. "
                        "Faqat HTML content qaytar, <html>, <body>, <head> taglarini ISHLATMA."
                    )
                },
                {
                    "role": "user",
                    "content": f"Kurs: {profession_name}\nMavzu: {lesson_title}\n\nShu mavzu bo'yicha o'quv maqolasi yoz."
                }
            ],
            max_tokens=2000,
            temperature=0.7,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"AI maqola xatolik: {e}")
        return None


def generate_ai_homework(request):
    """Bo'lim nomiga qarab AI orqali uyga vazifa yaratish"""
    if not (request.user.is_authenticated and (request.user.is_admin or request.user.is_teacher)):
        return JsonResponse({'error': 'Ruxsat yo\'q'}, status=403)
    
    if request.method != 'POST':
        return JsonResponse({'error': 'POST talab qilinadi'}, status=405)
    
    import json
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        data = request.POST
    
    section_id = data.get('section_id')
    profession_id = data.get('profession_id')
    
    section_name = ''
    profession_name = ''
    
    if section_id:
        try:
            section = Section.objects.get(pk=section_id)
            section_name = section.title
            profession_name = section.profession.name
        except Section.DoesNotExist:
            pass
    
    if not profession_name and profession_id:
        try:
            profession = Profession.objects.get(pk=profession_id)
            profession_name = profession.name
        except Profession.DoesNotExist:
            pass
    
    if not section_name and not profession_name:
        return JsonResponse({'error': 'Bo\'lim yoki kurs tanlanmagan'}, status=400)
    
    from django.conf import settings
    api_key = getattr(settings, 'OPENAI_API_KEY', None)
    if not api_key or not api_key.strip():
        return JsonResponse({'error': 'AI xizmati sozlanmagan'}, status=500)
    
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key.strip(), timeout=60)
        
        topic = section_name if section_name else profession_name
        prompt_context = f"Kurs: {profession_name}" if profession_name else ""
        if section_name:
            prompt_context += f"\nBo'lim: {section_name}"
        
        example_homework = (
            '<h3>📌 Vazifa maqsadi</h3>'
            '<p>Bu vazifada HTML asosiy teglarini o\'rganasiz. Sarlavhalar, ro\'yxatlar va havolalar yaratishni mashq qilasiz.</p>'
            '<h3>📝 Topshiriqlar</h3>'
            '<p><strong>1-topshiriq: Shaxsiy sahifa yarating.</strong> O\'zingiz haqingizda HTML sahifa yarating. '
            'Sahifada h1 teg bilan ismingiz, h2 bilan "Men haqimda" sarlavhasi va p tegda 3-4 jumla yozing. '
            'Misol: <code>&lt;h1&gt;Ali Valiyev&lt;/h1&gt;</code></p>'
            '<p><strong>2-topshiriq: Jadval tuzing.</strong> 4 qatorli va 3 ustunli jadval yarating. '
            'Jadvalda o\'zingiz va oila a\'zolaringiz haqida ma\'lumot kiriting (ism, yosh, kasb). '
            'table, tr, th, td teglarini ishlating.</p>'
            '<p><strong>3-topshiriq: Ro\'yxat yarating.</strong> Sevimli filmlaringiz tartibli ro\'yxatini (ol) va '
            'sevimli ovqatlaringiz tartivsiz ro\'yxatini (ul) yarating. Har bir ro\'yxatda kamida 5 ta element bo\'lsin.</p>'
            '<p><strong>4-topshiriq: Havola va rasm qo\'shing.</strong> Sahifangizga 2 ta havola (a teg) va '
            '1 ta rasm (img teg) qo\'shing. Rasmga alt atribut yozing.</p>'
            '<h3>✅ Baholash mezonlari</h3>'
            '<p><strong>To\'g\'ri bajarilishi (4 ball):</strong> Barcha teglar to\'g\'ri yopilgan, sahifa brauzerde xatosiz ochiladi.</p>'
            '<p><strong>Kod sifati (3 ball):</strong> Kod tartibli yozilgan, indentatsiya to\'g\'ri, teglar bir xil stilida.</p>'
            '<p><strong>Ijodkorlik (3 ball):</strong> Qo\'shimcha teglar ishlatilgan, sahifa mazmunli va chiroyli.</p>'
            '<p><strong>Umumiy ball: 10</strong></p>'
        )

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Sen tajribali IT o'qituvchisan. Senden uyga vazifa yozish so'raladi. "
                        "O'zbek tilida yoz. Faqat HTML formatda javob qaytar.\n\n"
                        "MUHIM QOIDALAR:\n"
                        "- Faqat <h3>, <p>, <strong>, <em>, <code> teglarini ishlat\n"
                        "- <ol>, <ul>, <li> teglarini ISHLATMA! O'rniga <p> ichida yoz\n"
                        "- <html>, <body>, <head> teglarini ISHLATMA\n"
                        "- Har bir topshiriqni alohida <p> tegda yoz\n"
                        "- Har bir <p> ichida kamida 2-3 jumla bo'lsin\n"
                        "- Topshiriqlarda ANIQ kod misollari keltir\n\n"
                        "Namuna:\n" + example_homework + "\n\n"
                        "Xuddi shu formatda yoz. Topshiriqlar soni 4 ta. Umumiy ball 10."
                    )
                },
                {
                    "role": "user",
                    "content": f"{prompt_context}\n\nShu mavzu uchun uyga vazifa yoz. "
                               f"Har bir topshiriqni <p> tegda batafsil yoz, aniq ko'rsatma va kod misoli bo'lsin."
                }
            ],
            max_tokens=2500,
            temperature=0.7,
        )
        
        homework_content = response.choices[0].message.content.strip()
        title = f"{topic} - Uyga vazifa"
        
        return JsonResponse({
            'success': True,
            'title': title,
            'description': homework_content,
        })
    except Exception as e:
        return JsonResponse({'error': f'AI xatolik: {str(e)}'}, status=500)


def generate_ai_test(request):
    """AI orqali test savollari yaratish"""
    if not (request.user.is_authenticated and (request.user.is_admin or request.user.is_teacher)):
        return JsonResponse({'error': 'Ruxsat yo\'q'}, status=403)
    
    if request.method != 'POST':
        return JsonResponse({'error': 'POST talab qilinadi'}, status=405)
    
    import json
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        data = request.POST
    
    test_id = data.get('test_id')
    question_count = data.get('question_count', 5)
    
    try:
        question_count = int(question_count)
        if question_count < 1:
            question_count = 1
        elif question_count > 50:
            question_count = 50
    except (ValueError, TypeError):
        question_count = 5
    
    if not test_id:
        return JsonResponse({'error': 'Test tanlanmagan'}, status=400)
    
    try:
        test = Test.objects.select_related('lesson__section', 'lesson__profession').get(pk=test_id)
    except Test.DoesNotExist:
        return JsonResponse({'error': 'Test topilmadi'}, status=404)
    
    lesson_title = test.lesson.title
    profession_name = test.lesson.profession.name
    section_name = test.lesson.section.title if test.lesson.section else ''
    
    topic = section_name if section_name else lesson_title
    
    from django.conf import settings
    api_key = getattr(settings, 'OPENAI_API_KEY', None)
    if not api_key or not api_key.strip():
        return JsonResponse({'error': 'AI xizmati sozlanmagan (OPENAI_API_KEY topilmadi)'}, status=500)
    
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key.strip(), timeout=120)
        
        prompt_context = f"Kurs: {profession_name}"
        if section_name:
            prompt_context += f"\nBo'lim: {section_name}"
        prompt_context += f"\nDars: {lesson_title}"
        
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Sen tajribali IT o'qituvchisan. Senden test savollari yaratish so'raladi. "
                        "O'zbek tilida yoz. Faqat JSON formatda javob qaytar, boshqa hech narsa yozma.\n\n"
                        "Har bir savol uchun 3 ta variant (A, B, C) bo'lsin.\n"
                        "To'g'ri javob faqat A, B yoki C bo'lsin.\n"
                        "Savollar real amaliy bo'lsin, kodli misollar ham bo'lishi mumkin.\n"
                        "Javoblar bir-biriga yaqin va chalg'ituvchi bo'lsin, LEKIN har bir savolda A, B, C variantlari bir-biridan FARQLI bo'lishi SHART. "
                        "Hech qachon ikki yoki uch variant bir xil matnli bo'lmasin!\n"
                        "Izoh 1-2 gap bilan tushuntirsin.\n\n"
                        "JSON formati:\n"
                        "[\n"
                        "  {\n"
                        '    "question": "Savol matni",\n'
                        '    "a": "A varianti",\n'
                        '    "b": "B varianti",\n'
                        '    "c": "C varianti",\n'
                        '    "correct": "A",\n'
                        '    "explanation": "Izoh"\n'
                        "  }\n"
                        "]\n\n"
                        "MUHIM: Faqat JSON array qaytar. Markdown yoki boshqa text qo'shma."
                    )
                },
                {
                    "role": "user",
                    "content": f"{prompt_context}\n\nShu mavzu bo'yicha {question_count} ta test savoli yarat."
                }
            ],
            max_tokens=4000,
            temperature=0.7,
        )
        
        ai_text = response.choices[0].message.content.strip()
        
        # Clean markdown code blocks if present
        if ai_text.startswith('```'):
            lines = ai_text.split('\n')
            # Remove first line (```json) and last line (```)
            lines = [l for l in lines if not l.strip().startswith('```')]
            ai_text = '\n'.join(lines)
        
        questions_data = json.loads(ai_text)
        
        if not isinstance(questions_data, list):
            return JsonResponse({'error': 'AI noto\'g\'ri format qaytardi'}, status=500)
        
        from django.db import transaction
        created_count = 0
        
        with transaction.atomic():
            existing_count = test.questions.count()
            for i, qd in enumerate(questions_data):
                q_text = qd.get('question', '').strip()
                opt_a = qd.get('a', '').strip()
                opt_b = qd.get('b', '').strip()
                opt_c = qd.get('c', '').strip()
                correct = qd.get('correct', '').strip().upper()
                explanation = qd.get('explanation', '').strip()
                
                if not q_text or not opt_a or not opt_b or not opt_c or correct not in ('A', 'B', 'C'):
                    continue
                
                # Dublikat variantlarni tekshirish
                options = [opt_a.lower(), opt_b.lower(), opt_c.lower()]
                if len(set(options)) < 3:
                    # Agar variantlar ichida bir xili bo'lsa, bu savolni o'tkazib yuboramiz
                    continue
                
                question = TestQuestion.objects.create(
                    test=test,
                    question_text=q_text,
                    explanation=explanation,
                    order=existing_count + i + 1,
                )
                for letter, text in [('A', opt_a), ('B', opt_b), ('C', opt_c)]:
                    TestAnswer.objects.create(
                        question=question,
                        answer_text=text,
                        is_correct=(letter == correct),
                    )
                created_count += 1
        
        return JsonResponse({
            'success': True,
            'created_count': created_count,
            'message': f'{created_count} ta savol muvaffaqiyatli yaratildi!'
        })
    except json.JSONDecodeError:
        return JsonResponse({'error': 'AI javobini o\'qishda xatolik. Qayta urinib ko\'ring.'}, status=500)
    except Exception as e:
        return JsonResponse({'error': f'AI xatolik: {str(e)}'}, status=500)


@login_required
def generate_ai_article_view(request, pk):
    """AJAX: AI maqola yaratish yoki qayta yaratish"""
    if not (request.user.is_admin or request.user.is_teacher):
        return JsonResponse({'error': 'Ruxsat yo\'q'}, status=403)
    
    lesson = get_object_or_404(Lesson, pk=pk)
    
    if request.method == 'POST':
        ai_article = _generate_ai_article(lesson.title, lesson.profession.name)
        if ai_article:
            lesson.ai_article = ai_article
            lesson.save(update_fields=['ai_article'])
            return JsonResponse({'success': True, 'article': ai_article})
        return JsonResponse({'error': 'AI maqola yaratishda xatolik'}, status=500)
    
    return JsonResponse({'error': 'POST kerak'}, status=405)


def send_course_notification(profession, title, content, sender=None):
    """Kursga yozilgan barcha o'quvchilarga xabar yuborish (sayt + Telegram)"""
    import threading
    
    enrollments = CourseEnrollment.objects.filter(profession=profession).select_related('user')
    
    teacher_name = ""
    if sender:
        teacher_name = f"{sender.first_name} {sender.last_name}"
    
    telegram_ids = []
    for enrollment in enrollments:
        Message.objects.create(
            sender=sender,
            recipient=enrollment.user,
            title=title,
            content=content,
            message_type='system'
        )
        if enrollment.user.telegram_id:
            telegram_ids.append(enrollment.user.telegram_id)
    
    def _send_telegram():
        for tid in telegram_ids:
            telegram_text = (
                f"📢 <b>{title}</b>\n\n"
                f"{content}\n\n"
            )
            if teacher_name:
                telegram_text += f"👨‍🏫 O'qituvchi: {teacher_name}\n"
            telegram_text += f"🔗 Saytga kiring va ko'ring!"
            notify_user(tid, telegram_text)
        
        notify_group(
            f"📢 <b>{title}</b>\n\n"
            f"📚 Kurs: {profession.name}\n"
            + (f"👨‍🏫 O'qituvchi: {teacher_name}\n\n" if teacher_name else "\n")
            + content
        )
    
    threading.Thread(target=_send_telegram, daemon=True).start()


def register_view(request):
    if request.user.is_authenticated:
        return redirect('home')
    
    if request.method == 'POST':
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            notify_admins(
                f"👤 <b>Yangi foydalanuvchi ro'yxatdan o'tdi!</b>\n\n"
                f"📛 {user.first_name} {user.last_name}\n"
                f"🆔 @{user.username}\n"
                f"📱 {user.phone}\n"
                f"🎓 {user.get_role_display()}"
            )
            notify_group(
                f"🎉 <b>Safimizga yangi foydalanuvchi qo'shildi!</b>\n\n"
                f"👤 {user.first_name} {user.last_name}\n"
                f"🎓 {user.get_role_display()}\n\n"
                f"🚀 Xush kelibsiz!"
            )
            messages.success(request, "Ro'yxatdan muvaffaqiyatli o'tdingiz!")
            return redirect('home')
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f"{error}")
    else:
        form = RegisterForm()
    
    return render(request, 'accounts/register.html', {'form': form})



def _login_render(request, form, login_mode):
    """Login sahifasini render qilish"""
    return render(request, 'accounts/login.html', {
        'form': form,
        'login_mode': login_mode,
    })


def _parse_user_agent(ua):
    """User-Agent dan qurilma nomi, turi, brauzer va OS ni aniqlash"""
    # Qurilma turi
    if 'Mobile' in ua or 'Android' in ua and 'Tablet' not in ua:
        device_type = 'mobile'
    elif 'Tablet' in ua or 'iPad' in ua:
        device_type = 'tablet'
    else:
        device_type = 'desktop'

    # OS
    if 'iPhone' in ua or 'iPad' in ua:
        os_name = 'iOS'
    elif 'Android' in ua:
        os_name = 'Android'
    elif 'Windows' in ua:
        os_name = 'Windows'
    elif 'Macintosh' in ua or 'Mac OS' in ua:
        os_name = 'MacOS'
    elif 'Linux' in ua:
        os_name = 'Linux'
    else:
        os_name = "Noma'lum"

    # Brauzer
    if 'Edg' in ua:
        browser = 'Edge'
    elif 'OPR' in ua or 'Opera' in ua:
        browser = 'Opera'
    elif 'Chrome' in ua:
        browser = 'Chrome'
    elif 'Firefox' in ua:
        browser = 'Firefox'
    elif 'Safari' in ua:
        browser = 'Safari'
    else:
        browser = "Noma'lum"

    device_name = f"{os_name} - {browser}"
    return device_name, device_type, browser, os_name


def _get_device_id(user, ua, ip_address):
    """User-Agent va IP dan qurilma ID yaratish"""
    import hashlib
    device_id_raw = f"{user.pk}-{ua}-{ip_address}"
    return hashlib.md5(device_id_raw.encode()).hexdigest()


def _register_device_and_session(request, user):
    """Login paytida qurilma va sessiyani ro'yxatdan o'tkazish.
    
    Qoidalar:
    - Max 3 ta qurilma saqlanadi. 4-chi bo'lsa, None qaytaradi (limit oynasi ochiladi)
    - Faqat 1 ta qurilma online bo'ladi. Boshqa sessiyalar o'chiriladi.
    """
    from django.contrib.sessions.models import Session as DjangoSession
    
    ua = request.META.get('HTTP_USER_AGENT', '')
    ip_address = request.META.get('REMOTE_ADDR', '')
    device_name, device_type, browser, os_name = _parse_user_agent(ua)
    device_id = _get_device_id(user, ua, ip_address)

    # Bu qurilma allaqachon ro'yxatdan o'tganmi?
    device = UserDevice.objects.filter(user=user, device_id=device_id, is_active=True).first()

    if not device:
        # Yangi qurilma — faol qurilmalar sonini tekshirish
        active_devices = UserDevice.objects.filter(user=user, is_active=True)
        if active_devices.count() >= 3:
            # 4-chi qurilma — limit! Login qilingan, lekin device yaratilmaydi
            return False
        
        # Yangi qurilma yaratish
        device, created = UserDevice.objects.get_or_create(
            user=user,
            device_id=device_id,
            defaults={
                'device_name': device_name,
                'device_type': device_type,
                'browser': browser,
                'os': os_name,
                'ip_address': ip_address,
                'is_active': True,
            }
        )
        if not created:
            device.is_active = True
            device.save(update_fields=['is_active', 'last_login'])
    else:
        device.ip_address = ip_address
        device.save(update_fields=['ip_address', 'last_login'])

    # Sessiyani yaratish
    if not request.session.session_key:
        request.session.create()

    # ✅ FAQAT 1 TA ONLINE: barcha eski sessiyalarni o'chirish
    old_sessions = UserSession.objects.filter(user=user, is_active=True)
    old_session_keys = list(old_sessions.values_list('session_key', flat=True))
    DjangoSession.objects.filter(session_key__in=old_session_keys).delete()
    old_sessions.update(is_active=False)

    # Yangi sessiya yaratish
    UserSession.objects.create(
        user=user,
        device=device,
        session_key=request.session.session_key,
        ip_address=ip_address,
        expires_at=timezone.now() + timedelta(seconds=7200),
        is_active=True,
    )

    return True


def _record_failed_login(ip_address, username='', user_agent=''):
    """Muvaffaqiyatsiz login urinishini yozish"""
    LoginAttempt.objects.create(
        ip_address=ip_address,
        username=username[:150],
        was_successful=False,
        user_agent=user_agent[:500],
    )


def _record_successful_login(ip_address, username='', user_agent=''):
    """Muvaffaqiyatli loginni yozish va eski urinishlarni tozalash"""
    LoginAttempt.objects.create(
        ip_address=ip_address,
        username=username[:150],
        was_successful=True,
        user_agent=user_agent[:500],
    )
    LoginAttempt.clear_attempts(ip_address)


def login_view(request):
    from django.conf import settings as django_settings

    if request.user.is_authenticated:
        return redirect('home')

    ip_address = request.META.get('REMOTE_ADDR', '')
    user_agent = request.META.get('HTTP_USER_AGENT', '')
    max_attempts = getattr(django_settings, 'LOGIN_MAX_ATTEMPTS', 5)
    lockout_minutes = getattr(django_settings, 'LOGIN_LOCKOUT_DURATION', 15)

    login_mode = request.POST.get('login_mode', 'username') if request.method == 'POST' else 'username'

    if request.method == 'POST':
        form = LoginForm(request.POST)

        # 🤖 Honeypot — botlar uchun tuzoq (yashirin maydon to'ldirilsa, bu bot)
        honeypot = request.POST.get('website_url', '')
        if honeypot:
            import time
            time.sleep(2)
            messages.error(request, "Username yoki parol noto'g'ri ❌")
            return _login_render(request, form, login_mode)

        # 🔒 Brute-force himoya — IP bloklangan bo'lsa, kirishga ruxsat bermaslik
        if LoginAttempt.is_ip_blocked(ip_address, max_attempts, lockout_minutes):
            remaining = LoginAttempt.get_remaining_lockout_time(ip_address, max_attempts, lockout_minutes)
            remaining_min = remaining // 60 + 1
            messages.error(request, f"Juda ko'p noto'g'ri urinish! {remaining_min} daqiqadan keyin qayta urinib ko'ring. 🔒")
            # Admin'ga xabar berish
            try:
                notify_admins(
                    f"🚨 <b>Brute-force hujumi aniqlandi!</b>\n\n"
                    f"🌐 IP: {ip_address}\n"
                    f"🕐 {timezone.now().strftime('%d.%m.%Y %H:%M')}\n"
                    f"📱 UA: {user_agent[:100]}\n"
                    f"⚠️ {max_attempts} marta noto'g'ri urinish — IP bloklandi"
                )
            except Exception:
                pass
            return _login_render(request, form, login_mode)

        # Telegram kod orqali login
        if login_mode == 'telegram':
            telegram_code = request.POST.get('telegram_code', '').strip()
            if not telegram_code:
                messages.error(request, "Iltimos, kodni kiriting! ⚠️")
                return _login_render(request, form, 'telegram')

            from telegram_bot.models import TelegramLoginCode
            try:
                login_code = TelegramLoginCode.objects.get(code=telegram_code, is_used=False)
            except TelegramLoginCode.DoesNotExist:
                _record_failed_login(ip_address, f'telegram_code:{telegram_code[:6]}', user_agent)
                messages.error(request, "Kod noto'g'ri yoki allaqachon ishlatilgan! ❌")
                return _login_render(request, form, 'telegram')

            if login_code.is_expired:
                messages.error(request, "Kod muddati tugagan! Botdan yangi kod oling. ⏰")
                return _login_render(request, form, 'telegram')

            try:
                user = CustomUser.objects.get(telegram_id=login_code.telegram_id)
            except CustomUser.DoesNotExist:
                messages.error(request, "Foydalanuvchi topilmadi! ❌")
                return _login_render(request, form, 'telegram')

            login_code.is_used = True
            login_code.save()

        elif login_mode == 'phone':
            phone = request.POST.get('phone', '').strip()
            password = request.POST.get('password', '').strip()

            if not phone or not password:
                messages.error(request, "Iltimos, barcha maydonlarni to'ldiring ⚠️")
                return _login_render(request, form, 'phone')

            try:
                phone_user = CustomUser.objects.get(phone=phone)
                user = authenticate(request, username=phone_user.username, password=password)
            except CustomUser.DoesNotExist:
                user = None

            if user is None:
                _record_failed_login(ip_address, f'phone:{phone[:20]}', user_agent)
                messages.error(request, "Telefon raqam yoki parol noto'g'ri ❌")
                return _login_render(request, form, 'phone')

        elif form.is_valid():
            username = form.cleaned_data.get('username')
            password = form.cleaned_data.get('password')

            user = authenticate(request, username=username, password=password)

            if user is None:
                _record_failed_login(ip_address, username, user_agent)
                messages.error(request, "Username yoki parol noto'g'ri ❌")
                return _login_render(request, form, login_mode)
        else:
            messages.error(request, "Iltimos, barcha maydonlarni to'g'ri to'ldiring ⚠️")
            return _login_render(request, form, login_mode)

        # ⛔ Bloklangan user
        if hasattr(user, "is_blocked") and user.is_blocked:
            messages.error(request, "Sizning akkauntingiz bloklangan 🚫")
            return _login_render(request, form, login_mode)

        # ✅ Login successful — urinishlarni tozalash
        _record_successful_login(ip_address, user.username, user_agent)
        login(request, user)

        user.last_activity = timezone.now()
        user.save(update_fields=["last_activity"])

        # 📱 Qurilma va sessiya ro'yxatdan o'tkazish
        device_ok = _register_device_and_session(request, user)
        if not device_ok and not user.is_admin:
            # 4-chi qurilma — limit oynasini ko'rsatish (admin uchun cheklov yo'q)
            request.session['device_limit_exceeded'] = True
            return redirect('device_limit')
        
        # 💎 Premium kunlik bonus: 5 coin
        today = timezone.now().date()
        if user.is_premium and user.last_daily_login != today:
            user.last_daily_login = today
            user.save(update_fields=["last_daily_login"])
            user.add_coins(5, "Premium kunlik bonus")
            messages.success(request, "💎 Premium bonus: +5 coin qo'shildi!")

        ip_address = request.META.get('REMOTE_ADDR', '')
        ActivityLog.objects.create(
            user=user,
            action_type='login',
            description="Tizimga kirdi",
            ip_address=ip_address
        )

        if user.telegram_id:
            ua = request.META.get('HTTP_USER_AGENT', '')
            if 'iPhone' in ua or 'iPad' in ua:
                device = '📱 iPhone/iPad'
            elif 'Android' in ua:
                device = '📱 Android'
            elif 'Windows' in ua:
                device = '💻 Windows'
            elif 'Macintosh' in ua or 'Mac OS' in ua:
                device = '💻 MacOS'
            elif 'Linux' in ua:
                device = '💻 Linux'
            else:
                device = '🌐 Noma\'lum qurilma'

            if 'Chrome' in ua and 'Edg' not in ua:
                browser = 'Chrome'
            elif 'Firefox' in ua:
                browser = 'Firefox'
            elif 'Safari' in ua and 'Chrome' not in ua:
                browser = 'Safari'
            elif 'Edg' in ua:
                browser = 'Edge'
            elif 'Opera' in ua or 'OPR' in ua:
                browser = 'Opera'
            else:
                browser = ''

            notify_user(
                user.telegram_id,
                f"🔐 <b>Hisobingizga kirildi!</b>\n\n"
                f"👤 {user.full_name}\n"
                f"🖥 Qurilma: {device}\n"
                f"{'🌍 Brauzer: ' + browser + chr(10) if browser else ''}"
                f"🌐 IP: {ip_address}\n"
                f"🕐 {timezone.now().strftime('%d.%m.%Y %H:%M')}\n\n"
                f"⚠️ Agar bu siz bo'lmasangiz, darhol parolingizni o'zgartiring!"
            )

        messages.success(request, "Tizimga muvaffaqiyatli kirdingiz! 🎉")

        # Premium reklama (premium bo'lmagan studentlar uchun)
        if user.role == 'student' and not user.is_premium:
            request.session['show_premium_ad'] = True

        # AI yordamchi reklama (har safar login qilganda)
        request.session['show_ai_ad'] = True

        return redirect('home')

    else:
        form = LoginForm()

    return _login_render(request, form, 'username')


@login_required
def device_limit_view(request):
    """Qurilmalar soni limitdan oshganida ko'rsatiladigan sahifa.
    
    Foydalanuvchi 3 ta qurilmada ro'yxatdan o'tgan, 4-chi qurilmadan 
    kirmoqchi — bitta qurilmani o'chirishi kerak.
    """
    if not request.session.get('device_limit_exceeded'):
        return redirect('home')

    # Faol qurilmalarni ko'rsatish
    active_devices = UserDevice.objects.filter(user=request.user, is_active=True)

    # Agar limit ostiga tushgan bo'lsa (admin o'chirgan bo'lishi mumkin)
    if active_devices.count() < 3:
        request.session.pop('device_limit_exceeded', None)
        return redirect('home')

    return render(request, 'accounts/device_limit.html', {
        'active_devices': active_devices,
    })


@login_required
def force_logout_device(request, pk):
    """Qurilma limitdan oshganda, bitta qurilmani o'chirish va o'rniga yangisini qo'shish"""
    if request.method != 'POST':
        return redirect('device_limit')

    from django.contrib.sessions.models import Session as DjangoSession

    device_to_remove = get_object_or_404(
        UserDevice, pk=pk, user=request.user, is_active=True
    )

    # Bu qurilmaning barcha sessiyalarini o'chirish
    device_sessions = device_to_remove.sessions.filter(is_active=True)
    session_keys = list(device_sessions.values_list('session_key', flat=True))
    DjangoSession.objects.filter(session_key__in=session_keys).delete()
    device_sessions.update(is_active=False)

    # Qurilmani deaktivatsiya qilish
    device_to_remove.is_active = False
    device_to_remove.save(update_fields=['is_active'])

    # Endi yangi qurilmani ro'yxatdan o'tkazish (hozirgi qurilma)
    remaining_count = UserDevice.objects.filter(user=request.user, is_active=True).count()
    if remaining_count < 3:
        device_ok = _register_device_and_session(request, request.user)
        if device_ok:
            request.session.pop('device_limit_exceeded', None)
            messages.success(request, "Qurilma muvaffaqiyatli almashtirildi! ✅")
            return redirect('home')

    messages.success(request, "Qurilma o'chirildi. Yana bitta qurilmani tanlang.")
    return redirect('device_limit')


def logout_view(request):
    if request.user.is_authenticated:
        # Sessiyani deaktivatsiya qilish
        current_session_key = request.session.session_key
        if current_session_key:
            UserSession.objects.filter(
                user=request.user, session_key=current_session_key
            ).update(is_active=False)

        ActivityLog.objects.create(
            user=request.user,
            action_type='logout',
            description="Tizimdan chiqdi",
            ip_address=request.META.get('REMOTE_ADDR')
        )

    logout(request)
    messages.success(request, "Tizimdan muvaffaqiyatli chiqdingiz 👋")
    return redirect('login')


@login_required
def home_view(request):
    # --- Asosiy ma'lumotlar ---
    professions = Profession.objects.prefetch_related('teachers').annotate(
        lesson_count=Count('lessons')
    ).all()[:6]

    total_students = CustomUser.objects.filter(role='student').count()
    total_courses = Profession.objects.count()
    total_lessons = Lesson.objects.count()

    # --- O'quvchi uchun kurslari ---
    my_enrollments = []
    dashboard_courses = []
    quick_courses = []
    if request.user.is_teacher:
        quick_courses = list(request.user.teaching_professions.all()[:3])
    elif request.user.is_admin:
        quick_courses = list(Profession.objects.all()[:3])
    if request.user.is_student or request.user.is_admin:
        my_enrollments = request.user.enrollments.select_related('profession').all()[:4]
        if my_enrollments:
            prof_ids = [e.profession_id for e in my_enrollments]
            
            # Bulk: barcha kurslar uchun total countlar
            video_counts = dict(VideoLesson.objects.filter(
                lesson__profession_id__in=prof_ids
            ).values_list('lesson__profession_id').annotate(c=Count('id')).values_list('lesson__profession_id', 'c'))
            test_counts = dict(Test.objects.filter(
                lesson__profession_id__in=prof_ids
            ).values_list('lesson__profession_id').annotate(c=Count('id')).values_list('lesson__profession_id', 'c'))
            hw_counts = dict(Homework.objects.filter(
                lesson__profession_id__in=prof_ids
            ).values_list('lesson__profession_id').annotate(c=Count('id')).values_list('lesson__profession_id', 'c'))
            
            # Bulk: foydalanuvchi progressi
            watched_counts = dict(VideoProgress.objects.filter(
                user=request.user, watched=True,
                video__lesson__profession_id__in=prof_ids
            ).values_list('video__lesson__profession_id').annotate(c=Count('id')).values_list('video__lesson__profession_id', 'c'))
            passed_counts = dict(TestResult.objects.filter(
                student=request.user, passed=True,
                test__lesson__profession_id__in=prof_ids
            ).values_list('test__lesson__profession_id').annotate(c=Count('test_id', distinct=True)).values_list('test__lesson__profession_id', 'c'))
            done_hw_counts = dict(HomeworkSubmission.objects.filter(
                student=request.user,
                homework__lesson__profession_id__in=prof_ids,
                status__in=['accepted', 'graded']
            ).values_list('homework__lesson__profession_id').annotate(c=Count('homework_id', distinct=True)).values_list('homework__lesson__profession_id', 'c'))
            
            for enrollment in my_enrollments:
                pid = enrollment.profession_id
                total_items = video_counts.get(pid, 0) + test_counts.get(pid, 0) + hw_counts.get(pid, 0)
                if total_items == 0:
                    progress = 0
                else:
                    completed = watched_counts.get(pid, 0) + passed_counts.get(pid, 0) + done_hw_counts.get(pid, 0)
                    progress = min(100, round((completed / total_items) * 100))
                dashboard_courses.append({
                    'name': enrollment.profession.name,
                    'progress': progress,
                })

    # ⚠️ MUHIM:
    # unread_messages_count BU YERDA HISOBLANMAYDI!
    # Navbar uchun qiymat context processor orqali keladi.

    context = {
        'professions': professions,
        'total_students': total_students,
        'total_courses': total_courses,
        'total_lessons': total_lessons,
        'my_enrollments': my_enrollments,
        'dashboard_courses': dashboard_courses,
        'quick_courses': quick_courses,
    }

    return render(request, 'accounts/home.html', context)

@login_required
def professions_view(request):
    professions = Profession.objects.prefetch_related('teachers').all()
    enrolled_ids = []
    if request.user.is_authenticated and request.user.is_student:
        enrolled_ids = list(request.user.enrollments.values_list('profession_id', flat=True))
        # Sort: enrolled courses first, then the rest
        professions = sorted(professions, key=lambda p: (p.pk not in enrolled_ids, p.pk))

        # Har bir kurs uchun progress hisoblash
        if enrolled_ids:
            for p in professions:
                if p.pk not in enrolled_ids:
                    p.progress = None
                    continue

                total_videos = VideoLesson.objects.filter(lesson__profession_id=p.pk).count()
                total_tests = Test.objects.filter(lesson__profession_id=p.pk).count()
                total_homeworks = Homework.objects.filter(lesson__profession_id=p.pk).count()
                total_items = total_videos + total_tests + total_homeworks

                if total_items == 0:
                    p.progress = 0
                    continue

                watched = VideoProgress.objects.filter(
                    user=request.user, video__lesson__profession_id=p.pk, watched=True
                ).count()
                passed_tests = TestResult.objects.filter(
                    student=request.user, test__lesson__profession_id=p.pk, passed=True
                ).values('test_id').distinct().count()
                done_hw = HomeworkSubmission.objects.filter(
                    student=request.user, homework__lesson__profession_id=p.pk,
                    status__in=['accepted', 'graded']
                ).values('homework_id').distinct().count()

                completed = watched + passed_tests + done_hw
                p.progress = min(round((completed / total_items) * 100), 100)

    from django.core.paginator import Paginator
    paginator = Paginator(professions, 6)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(request, 'accounts/professions.html', {
        'professions': page_obj,
        'all_professions': professions,
        'enrolled_ids': enrolled_ids,
    })


@login_required
def profession_detail(request, pk):
    profession = get_object_or_404(Profession, pk=pk)
    is_enrolled = False
    enrollment_request = None
    unenroll_request = None
    
    # Bloklangan kursga kirish cheklovi (faqat o'quvchilar uchun)
    if profession.is_blocked and request.user.is_student:
        messages.warning(request, f"'{profession.name}' kursi vaqtincha bloklangan. {profession.blocked_reason or ''}")
        return redirect('professions')
    
    is_teaching = False
    if request.user.is_student:
        is_enrolled = CourseEnrollment.objects.filter(user=request.user, profession=profession).exists() or request.user.profession == profession
        if is_enrolled:
            unenroll_request = CourseUnenrollRequest.objects.filter(user=request.user, profession=profession, status='pending').first()
        else:
            enrollment_request = CourseEnrollmentRequest.objects.filter(user=request.user, profession=profession).first()
    elif request.user.is_teacher:
        is_teaching = request.user.teaching_professions.filter(pk=profession.pk).exists()
    
    sections = []
    lessons_without_section = []
    lesson_progress = {}
    daily_section_today = None
    daily_limit_section_name = None
    section_daily_locked = {}
    lesson_is_locked = {}
    daily_lesson_today = None
    
    if is_enrolled or is_teaching or request.user.is_admin:
        sections = profession.sections.filter(is_active=True).prefetch_related('lessons')
        lessons_without_section = profession.lessons.filter(section__isnull=True)
        
        # Get user progress for lessons
        if request.user.is_authenticated:
            # Video progress
            watched_videos = VideoProgress.objects.filter(
                user=request.user, 
                watched=True,
                video__lesson__profession=profession
            ).values_list('video__lesson_id', flat=True)
            
            # Test results - eng oxirgi natijani olish
            test_results = TestResult.objects.filter(
                student=request.user,
                test__lesson__profession=profession
            ).order_by('test__lesson_id', '-completed_at')
            
            # Har bir test uchun eng oxirgi natijani saqlash
            latest_test_results = {}
            for tr in test_results:
                if tr.test.lesson_id not in latest_test_results:
                    latest_test_results[tr.test.lesson_id] = tr
            
            # Homework submissions - eng oxirgi topshiriqni olish
            hw_submissions = HomeworkSubmission.objects.filter(
                student=request.user,
                homework__lesson__profession=profession
            ).order_by('homework__lesson_id', '-submitted_at')
            
            latest_hw_submissions = {}
            for hw in hw_submissions:
                if hw.homework.lesson_id not in latest_hw_submissions:
                    latest_hw_submissions[hw.homework.lesson_id] = hw
            
            for vid in watched_videos:
                lesson_progress[vid] = {'completed': True, 'type': 'video'}
            
            for lesson_id, tr in latest_test_results.items():
                lesson_progress[lesson_id] = {
                    'completed': tr.passed,
                    'type': 'test',
                    'passed': tr.passed,
                    'score': tr.score,
                    'attempted': True,
                }
            
            for lesson_id, hw in latest_hw_submissions.items():
                is_completed = hw.status in ('accepted', 'graded')
                lesson_progress[lesson_id] = {
                    'completed': is_completed,
                    'type': 'homework',
                    'graded': hw.grade is not None,
                    'status': hw.status,
                    'attempted': True,
                }
            
            # Speaking submissions
            speaking_submissions = SpeakingSubmission.objects.filter(
                student=request.user,
                speaking_task__lesson__profession=profession
            ).order_by('speaking_task__lesson_id', '-submitted_at')
            
            latest_speaking = {}
            for sp in speaking_submissions:
                if sp.speaking_task.lesson_id not in latest_speaking:
                    latest_speaking[sp.speaking_task.lesson_id] = sp
            
            for lesson_id, sp in latest_speaking.items():
                is_completed = sp.status in ('graded',)
                lesson_progress[lesson_id] = {
                    'completed': is_completed,
                    'type': 'speaking',
                    'graded': sp.grade is not None,
                    'status': sp.status,
                    'attempted': True,
                }
        
        # Kunlik bo'lim cheklovi ma'lumotlarini olish
        daily_section_today = None
        daily_limit_section_name = None
        accessed_section_ids = set()
        if request.user.is_student and not request.user.is_admin and profession.daily_section_limit:
            from datetime import date
            today = date.today()
            # Oldin kirilgan barcha bo'limlar (har qanday kunda)
            accessed_section_ids = set(
                DailySectionAccess.objects.filter(
                    user=request.user, profession=profession
                ).values_list('section_id', flat=True)
            )
            today_access = DailySectionAccess.objects.filter(
                user=request.user, profession=profession, accessed_date=today
            ).select_related('section').first()
            if today_access:
                daily_section_today = today_access.section_id
                daily_limit_section_name = today_access.section.title

        section_is_locked = {}
        if request.user.is_student and not request.user.is_admin:
            pass  # section lock dars darajasidan kelib chiqadi — pastda hisoblanadi
        else:
            # Admin va o'qituvchi uchun barcha bo'limlar ochiq
            for section in sections:
                section_is_locked[section.id] = False
            section_is_locked['no_section'] = False
            section_daily_locked = {s.id: False for s in sections}
    
    # ===== BO'LIM DARAJASIDA QULFLASH MANTIGI =====
    # Qoidalar:
    #   1. Tugatilgan bo'limlar → har doim OCHIQ (takrorlash uchun)
    #   2. Boshlangan bo'lim (kamida 1 dars bajarilgan) → OCHIQ (davom ettirish)
    #   3. Yangi bo'lim (boshlanmagan, oldingi tugatilgan) → kunlik cheklash
    #      - Bugun boshqa bo'limga kirilgan bo'lsa → ERTAGA ochiladi
    #      - Kirilmagan bo'lsa → OCHIQ
    #   4. Qolgan bo'limlar → QULFLANGAN (oldingi tugatilmagan)
    if request.user.is_student and not request.user.is_admin and (is_enrolled):
        from datetime import date
        today = date.today()
        completed_lesson_ids = set(
            lid for lid, prog in lesson_progress.items() if prog.get('completed')
        )

        ordered_sections = list(sections)

        # Har bir bo'lim holati
        section_completed = {}
        section_started = {}
        for section in ordered_sections:
            section_lessons = [l for l in section.lessons.all() if l.lesson_type != 'dictionary']
            if not section_lessons:
                section_completed[section.id] = True
                section_started[section.id] = True
            else:
                section_completed[section.id] = all(l.pk in completed_lesson_ids for l in section_lessons)
                section_started[section.id] = any(l.pk in completed_lesson_ids for l in section_lessons)

        # Bugungi DailySectionAccess
        today_section_access = None
        if profession.daily_section_limit:
            today_section_access = DailySectionAccess.objects.filter(
                user=request.user, profession=profession, accessed_date=today
            ).select_related('section').first()

        section_is_locked = {}
        section_daily_locked = {}
        for idx, section in enumerate(ordered_sections):
            if section_completed[section.id]:
                # 1. Tugatilgan → ochiq
                section_is_locked[section.id] = False
                section_daily_locked[section.id] = False
            elif section_started[section.id]:
                # 2. Boshlangan → ochiq
                section_is_locked[section.id] = False
                section_daily_locked[section.id] = False
            else:
                # 3-4. Boshlanmagan bo'lim
                prev_completed = (idx == 0) or section_completed[ordered_sections[idx - 1].id]

                if not prev_completed:
                    # 4. Oldingi tugatilmagan → qulflangan
                    section_is_locked[section.id] = True
                    section_daily_locked[section.id] = False
                else:
                    # 3. Oldingi tugatilgan → kunlik cheklash
                    if profession.daily_section_limit and today_section_access and today_section_access.section_id != section.id:
                        # Bugun boshqa bo'limga kirilgan → ertaga
                        section_is_locked[section.id] = False
                        section_daily_locked[section.id] = True
                    else:
                        # Bugun hech narsaga kirilmagan yoki aynan shu bo'limga → ochiq
                        section_is_locked[section.id] = False
                        section_daily_locked[section.id] = False

        # Darslar holati — bo'lim holatiga qarab
        for section in ordered_sections:
            s_locked = section_is_locked.get(section.id)
            s_daily = section_daily_locked.get(section.id)
            section_lessons = [l for l in section.lessons.all() if l.lesson_type != 'dictionary']

            if s_locked:
                for l in section_lessons:
                    lesson_is_locked[l.pk] = 'sequential'
            elif s_daily:
                for l in section_lessons:
                    lesson_is_locked[l.pk] = 'daily'
            else:
                for l in section_lessons:
                    lesson_is_locked[l.pk] = False

        # Daily limit banner
        if today_section_access:
            daily_section_today = today_section_access.section_id
            daily_limit_section_name = today_section_access.section.title

        # Bo'limsiz darslar
        if lessons_without_section:
            no_sec_lessons = [l for l in lessons_without_section if l.lesson_type != 'dictionary']
            has_open = any(lesson_is_locked.get(l.pk) is False or lesson_is_locked.get(l.pk) is None for l in no_sec_lessons)
            section_is_locked['no_section'] = not has_open
        else:
            section_is_locked['no_section'] = False

    # Kursdoshlar - shu kursga yozilgan o'quvchilar
    classmates = []
    if is_enrolled or is_teaching or request.user.is_admin:
        classmates = CustomUser.objects.filter(
            enrollments__profession=profession,
            role='student'
        ).exclude(pk=request.user.pk).order_by('-last_activity', '-coins')[:20]
    
    course_teachers = profession.teachers.all()

    # Kurs tugatilganligini tekshirish va sertifikat so'rovi
    course_completed = False
    certificate = None
    certificate_request = None
    if is_enrolled and request.user.is_student:
        # Barcha bo'limlardagi barcha darslar (lug'at bundan mustasno) tugatilganmi
        all_lessons = Lesson.objects.filter(profession=profession).exclude(lesson_type='dictionary')
        # Bo'limlar mavjud lekin ichida dars yo'q bo'lsa — kurs tugallanmagan
        course_sections = profession.sections.filter(is_active=True)
        has_empty_section = any(
            not s.lessons.exists() for s in course_sections
        ) if course_sections.exists() else False
        if all_lessons.exists() and not has_empty_section:
            completed_ids = set(
                lid for lid, prog in lesson_progress.items() if prog.get('completed')
            )
            all_done = all(lesson.pk in completed_ids for lesson in all_lessons)
            course_completed = all_done
        
        # Sertifikat mavjudmi
        certificate = Certificate.objects.filter(student=request.user, profession=profession).first()
        # Sertifikat so'rovi mavjudmi
        certificate_request = CertificateRequest.objects.filter(student=request.user, profession=profession).first()

    return render(request, 'accounts/profession_detail.html', {
        'profession': profession,
        'is_enrolled': is_enrolled,
        'is_teaching': is_teaching,
        'enrollment_request': enrollment_request,
        'unenroll_request': unenroll_request,
        'sections': sections,
        'lessons_without_section': lessons_without_section,
        'lesson_progress': lesson_progress,
        'section_is_locked': section_is_locked if (is_enrolled or is_teaching or request.user.is_admin) else {},
        'section_daily_locked': section_daily_locked if (is_enrolled or is_teaching or request.user.is_admin) else {},
        'daily_section_today': daily_section_today if (is_enrolled and request.user.is_student) else None,
        'daily_limit_section_name': daily_limit_section_name if (is_enrolled and request.user.is_student) else None,
        'classmates': classmates,
        'course_teachers': course_teachers,
        'course_completed': course_completed,
        'has_empty_section': has_empty_section if is_enrolled and request.user.is_student else False,
        'certificate': certificate,
        'certificate_request': certificate_request,
        'lesson_is_locked': lesson_is_locked,
    })


@login_required
def course_statistics(request, pk):
    profession = get_object_or_404(Profession, pk=pk)
    is_enrolled = CourseEnrollment.objects.filter(user=request.user, profession=profession).exists() or request.user.profession == profession
    if not (is_enrolled or request.user.is_admin or request.user.is_teacher):
        messages.error(request, "Bu kursga yozilmagansiz!")
        return redirect('profession_detail', pk=pk)

    enrolled_students = CustomUser.objects.filter(
        enrollments__profession=profession, role='student'
    ).order_by('-coins')

    total_students = enrolled_students.count()

    lessons = Lesson.objects.filter(profession=profession)
    total_lessons = lessons.count()
    total_tests = lessons.filter(lesson_type='test').count()
    total_homeworks = lessons.filter(lesson_type='homework').count()
    total_videos = lessons.filter(lesson_type='video').count()

    test_results = TestResult.objects.filter(test__lesson__profession=profession)
    avg_test_score = test_results.aggregate(avg=Avg('score'))['avg'] or 0
    total_test_attempts = test_results.count()
    passed_tests = test_results.filter(passed=True).count()
    pass_rate = round(passed_tests / total_test_attempts * 100, 1) if total_test_attempts else 0

    hw_submissions = HomeworkSubmission.objects.filter(homework__lesson__profession=profession)
    total_hw_submitted = hw_submissions.count()
    graded_hw = hw_submissions.filter(status='graded')
    avg_hw_grade = graded_hw.aggregate(avg=Avg('grade'))['avg'] or 0

    student_ids = list(enrolled_students.values_list('id', flat=True))

    # Bulk test statistikasi
    from collections import defaultdict
    test_stats = defaultdict(lambda: {'count': 0, 'passed': 0, 'total_score': 0, 'avg_score': 0})
    for row in TestResult.objects.filter(
        student_id__in=student_ids, test__lesson__profession=profession
    ).values('student_id').annotate(
        count=Count('id'),
        passed=Count('id', filter=Q(passed=True)),
        total_score=Sum('score'),
        avg_score=Avg('score'),
    ):
        test_stats[row['student_id']] = {
            'count': row['count'],
            'passed': row['passed'],
            'total_score': row['total_score'] or 0,
            'avg_score': row['avg_score'] or 0,
        }

    # Bulk homework statistikasi
    hw_stats = defaultdict(lambda: {'count': 0, 'graded_avg': 0, 'graded_total': 0, 'accepted_count': 0})
    for row in HomeworkSubmission.objects.filter(
        student_id__in=student_ids, homework__lesson__profession=profession
    ).values('student_id').annotate(
        count=Count('id'),
        graded_avg=Avg('grade', filter=Q(status='graded')),
        graded_total=Sum('grade', filter=Q(status='graded')),
        accepted_count=Count('id', filter=Q(status__in=['accepted', 'graded'])),
    ):
        hw_stats[row['student_id']] = {
            'count': row['count'],
            'graded_avg': row['graded_avg'] or 0,
            'graded_total': row['graded_total'] or 0,
            'accepted_count': row['accepted_count'],
        }

    # Bulk video progress
    video_stats = dict(
        VideoProgress.objects.filter(
            user_id__in=student_ids, watched=True,
            video__lesson__profession=profession
        ).values('user_id').annotate(c=Count('id')).values_list('user_id', 'c')
    )

    total_possible = total_tests + total_homeworks + total_videos

    student_stats = []
    for student in enrolled_students:
        sid = student.id
        ts = test_stats[sid]
        hs = hw_stats[sid]
        vw = video_stats.get(sid, 0)

        completed = ts.get('passed', 0) + hs.get('accepted_count', 0) + vw
        progress = round(completed / total_possible * 100) if total_possible else 0

        s_total_score = ts.get('total_score', 0) + hs.get('graded_total', 0)

        student_stats.append({
            'student': student,
            'test_count': ts.get('count', 0),
            'test_avg': round(ts.get('avg_score', 0), 1),
            'passed_tests': ts.get('passed', 0),
            'hw_count': hs.get('count', 0),
            'hw_avg': round(hs.get('graded_avg', 0), 1),
            'videos_watched': vw,
            'progress': min(progress, 100),
            'coins': student.coins,
            'total_score': s_total_score,
        })

    student_stats.sort(key=lambda x: x['total_score'], reverse=True)

    for i, s in enumerate(student_stats):
        s['rank'] = i + 1

    return render(request, 'accounts/course_statistics.html', {
        'profession': profession,
        'total_students': total_students,
        'total_lessons': total_lessons,
        'total_tests': total_tests,
        'total_homeworks': total_homeworks,
        'total_videos': total_videos,
        'avg_test_score': round(avg_test_score, 1),
        'pass_rate': pass_rate,
        'total_test_attempts': total_test_attempts,
        'total_hw_submitted': total_hw_submitted,
        'avg_hw_grade': round(avg_hw_grade, 1),
        'student_stats': student_stats,
    })


@login_required
def enroll_course(request, pk):
    if not request.user.is_student:
        messages.error(request, "Faqat o'quvchilar kursga yozilishi mumkin!")
        return redirect('professions')
    
    profession = get_object_or_404(Profession, pk=pk)
    
    # Majburiy kurs — avtomatik yozilgan bo'lishi kerak
    if profession.is_mandatory:
        CourseEnrollment.objects.get_or_create(user=request.user, profession=profession)
        messages.info(request, f"'{profession.name}' majburiy kurs — siz avtomatik yozilgansiz!")
        return redirect('profession_detail', pk=pk)
    
    # Allaqachon yozilganmi?
    if CourseEnrollment.objects.filter(user=request.user, profession=profession).exists():
        messages.info(request, f"Siz allaqachon '{profession.name}' kursiga yozilgansiz!")
        return redirect('profession_detail', pk=pk)
    
    # Bepul kurs - to'g'ridan-to'g'ri yozish (GET yoki POST)
    if not profession.is_paid:
        # Eski so'rovlarni tozalash (qayta yozilishga to'sqinlik qilmasligi uchun)
        CourseUnenrollRequest.objects.filter(user=request.user, profession=profession).delete()
        CourseEnrollmentRequest.objects.filter(user=request.user, profession=profession).delete()
        _, created = CourseEnrollment.objects.get_or_create(user=request.user, profession=profession)
        if created:
            # Qayta yozilish bo'lsa — eski progressni tozalash
            _reset_course_progress(request.user, profession)
        notify_admins(
            f"📚 <b>Kursga yozildi!</b>\n\n"
            f"👤 {request.user.first_name} {request.user.last_name}\n"
            f"📖 {profession.name}\n"
            f"💰 Bepul kurs"
        )
        messages.success(request, f"'{profession.name}' kursiga muvaffaqiyatli yozildingiz! O'qishni boshlashingiz mumkin.")
        return redirect('profession_detail', pk=pk)
    
    # Pullik kurs - so'rov yuborish
    existing_request = CourseEnrollmentRequest.objects.filter(user=request.user, profession=profession).first()
    
    if existing_request:
        if existing_request.status == 'pending':
            messages.info(request, f"Sizning '{profession.name}' kursiga so'rovingiz admin tomonidan ko'rib chiqilmoqda.")
            return redirect('profession_detail', pk=pk)
        elif existing_request.status in ('approved', 'rejected'):
            # Eski so'rovni o'chirib, qayta so'rov yuborishga ruxsat berish
            existing_request.delete()
    
    if request.method == 'POST':
        reason = request.POST.get('reason', '').strip()
        if not reason:
            messages.error(request, "Iltimos, kursga yozilish sababini yozing!")
            return render(request, 'accounts/enroll_confirm.html', {'profession': profession})
        messages.success(request, f"'{profession.name}' kursiga yozilish so'rovi yuborildi! Admin tasdiqlashini kuting.")
        CourseEnrollmentRequest.objects.create(user=request.user, profession=profession, reason=reason)
        notify_admins(
            f"📋 <b>Kursga yozilish so'rovi!</b>\n\n"
            f"👤 {request.user.first_name} {request.user.last_name}\n"
            f"📖 {profession.name}\n"
            f"💰 Pullik kurs — tasdiq kutilmoqda"
        )
        return redirect('profession_detail', pk=pk)
    
    return render(request, 'accounts/enroll_confirm.html', {'profession': profession})


@login_required
def unenroll_course(request, pk):
    if not request.user.is_student:
        messages.error(request, "Faqat o'quvchilar kursdan chiqishi mumkin!")
        return redirect('professions')
    
    profession = get_object_or_404(Profession, pk=pk)
    enrollment = CourseEnrollment.objects.filter(user=request.user, profession=profession).first()
    is_enrolled = enrollment or request.user.profession == profession
    
    if not is_enrolled:
        messages.warning(request, "Siz bu kursga yozilmagansiz!")
        return redirect('professions')
    
    if profession.is_mandatory:
        messages.error(request, f"'{profession.name}' majburiy kurs — undan chiqish mumkin emas!")
        return redirect('profession_detail', pk=pk)
    
    # Allaqachon kutilayotgan so'rov bormi?
    existing = CourseUnenrollRequest.objects.filter(user=request.user, profession=profession, status='pending').first()
    if existing:
        messages.info(request, "Sizning kursdan chiqish so'rovingiz allaqachon yuborilgan. Admin tasdiqlashini kuting.")
        return redirect('profession_detail', pk=pk)
    
    if request.method == 'POST':
        reason = request.POST.get('reason', '').strip()
        if not reason:
            messages.error(request, "Iltimos, kursdan chiqish sababini yozing!")
            return redirect('profession_detail', pk=pk)
        
        # Eski yakunlangan so'rovlarni o'chirish (rejected yoki approved)
        CourseUnenrollRequest.objects.filter(
            user=request.user, profession=profession
        ).exclude(status='pending').delete()
        
        CourseUnenrollRequest.objects.create(
            user=request.user,
            profession=profession,
            reason=reason,
        )
        notify_admins(
            f"🚪 <b>Kursdan chiqish so'rovi!</b>\n\n"
            f"👤 {request.user.first_name} {request.user.last_name}\n"
            f"📖 {profession.name}\n"
            f"📝 Sabab: {reason[:200]}"
        )
        messages.success(request, f"Kursdan chiqish so'rovi yuborildi. Admin ko'rib chiqishini kuting.")
        return redirect('profession_detail', pk=pk)
    
    return redirect('profession_detail', pk=pk)


@login_required
def request_certificate(request, pk):
    """O'quvchi: Kursni tugatdim - sertifikat so'rovi yuborish"""
    if not request.user.is_student:
        messages.error(request, "Faqat o'quvchilar sertifikat so'rovi yuborishi mumkin!")
        return redirect('profession_detail', pk=pk)
    
    profession = get_object_or_404(Profession, pk=pk)
    enrollment = CourseEnrollment.objects.filter(user=request.user, profession=profession).exists()
    if not enrollment and request.user.profession != profession:
        messages.warning(request, "Siz bu kursga yozilmagansiz!")
        return redirect('profession_detail', pk=pk)
    
    # Allaqachon sertifikat berilganmi
    if Certificate.objects.filter(student=request.user, profession=profession).exists():
        messages.info(request, "Sizga bu kurs uchun allaqachon sertifikat berilgan!")
        return redirect('profession_detail', pk=pk)
    
    # Allaqachon so'rov bormi
    existing = CertificateRequest.objects.filter(student=request.user, profession=profession, status='pending').first()
    if existing:
        messages.info(request, "Sizning sertifikat so'rovingiz allaqachon yuborilgan. Admin tasdiqlashini kuting.")
        return redirect('profession_detail', pk=pk)
    
    # Bo'limlar ichida dars yo'q bo'lsa — so'rov yuborish mumkin emas
    course_sections = profession.sections.filter(is_active=True)
    if course_sections.exists() and any(not s.lessons.exists() for s in course_sections):
        messages.error(request, "Kurs hali to'liq yuklanmagan. Ustoz barcha bo'limlarga dars qo'shishi kerak!")
        return redirect('profession_detail', pk=pk)
    
    # Kurs tugatilganligini tekshirish
    all_lessons = Lesson.objects.filter(profession=profession).exclude(lesson_type='dictionary')
    if all_lessons.exists():
        watched_videos = set(VideoProgress.objects.filter(
            user=request.user, watched=True, video__lesson__profession=profession
        ).values_list('video__lesson_id', flat=True))
        passed_tests = set(TestResult.objects.filter(
            student=request.user, test__lesson__profession=profession, passed=True
        ).values_list('test__lesson_id', flat=True))
        accepted_homeworks = set(HomeworkSubmission.objects.filter(
            student=request.user, homework__lesson__profession=profession,
            status__in=['accepted', 'graded']
        ).values_list('homework__lesson_id', flat=True))
        graded_speakings = set(SpeakingSubmission.objects.filter(
            student=request.user, speaking_task__lesson__profession=profession,
            status='graded'
        ).values_list('speaking_task__lesson_id', flat=True))
        completed_ids = watched_videos | passed_tests | accepted_homeworks | graded_speakings
        
        for lesson in all_lessons:
            if lesson.pk not in completed_ids:
                messages.error(request, "Kursni tugatish uchun barcha darslarni (video, test, vazifa) bajarishingiz kerak!")
                return redirect('profession_detail', pk=pk)
    
    if request.method == 'POST':
        # Eski rad etilgan so'rovlarni o'chirish
        CertificateRequest.objects.filter(
            student=request.user, profession=profession
        ).exclude(status='pending').delete()
        
        CertificateRequest.objects.create(
            student=request.user,
            profession=profession,
        )
        
        from telegram_bot.utils import notify_admins
        notify_admins(
            f"🎓 <b>Sertifikat so'rovi!</b>\n\n"
            f"👤 {request.user.full_name}\n"
            f"📖 {profession.name}\n"
            f"📋 O'quvchi kursni tugatdi va sertifikat so'rovi yubordi."
        )
        
        messages.success(request, "Sertifikat so'rovingiz yuborildi! Admin ko'rib chiqishini kuting. 🎓")
        return redirect('profession_detail', pk=pk)
    
    return redirect('profession_detail', pk=pk)


@login_required
def admin_certificate_requests(request):
    """Admin: Sertifikat so'rovlarini ko'rish"""
    if not request.user.is_admin:
        return redirect('home')
    
    cert_requests = CertificateRequest.objects.select_related('student', 'profession', 'reviewed_by').all()
    
    status_filter = request.GET.get('status', '')
    if status_filter:
        cert_requests = cert_requests.filter(status=status_filter)
    
    return render(request, 'accounts/admin/certificate_requests.html', {
        'cert_requests': cert_requests,
        'status_filter': status_filter,
        'pending_count': CertificateRequest.objects.filter(status='pending').count(),
    })


@login_required
def approve_certificate_request(request, pk):
    """Admin: Sertifikat so'rovini tasdiqlash - sertifikat berish sahifasiga yo'naltirish"""
    if not request.user.is_admin:
        return redirect('home')
    
    cert_req = get_object_or_404(CertificateRequest, pk=pk)
    
    if request.method == 'POST':
        cert_req.status = 'approved'
        cert_req.reviewed_by = request.user
        cert_req.reviewed_at = timezone.now()
        cert_req.save()
        
        messages.success(request, f"{cert_req.student.full_name} ning sertifikat so'rovi tasdiqlandi! Endi sertifikat bering.")
        return redirect(f"{reverse('admin_certificate_issue')}?student={cert_req.student.pk}&profession={cert_req.profession.pk}")
    
    return redirect('admin_certificate_requests')


@login_required
def reject_certificate_request(request, pk):
    """Admin: Sertifikat so'rovini rad etish"""
    if not request.user.is_admin:
        return redirect('home')
    
    cert_req = get_object_or_404(CertificateRequest, pk=pk)
    
    if request.method == 'POST':
        admin_message = request.POST.get('admin_message', "Sertifikat so'rovi rad etildi.")
        cert_req.status = 'rejected'
        cert_req.admin_message = admin_message
        cert_req.reviewed_by = request.user
        cert_req.reviewed_at = timezone.now()
        cert_req.save()
        
        Message.objects.create(
            title="Sertifikat so'rovi rad etildi",
            content=f"Sizning '{cert_req.profession.name}' kursi uchun sertifikat so'rovingiz rad etildi.\n\nSabab: {admin_message}",
            message_type='personal',
            recipient=cert_req.student,
            sender=request.user
        )
        
        if cert_req.student.telegram_id:
            from telegram_bot.utils import notify_user
            notify_user(
                cert_req.student.telegram_id,
                f"❌ <b>Sertifikat so'rovi rad etildi</b>\n\n"
                f"📖 <b>{cert_req.profession.name}</b>\n"
                f"📝 Sabab: {admin_message}"
            )
        
        messages.success(request, f"{cert_req.student.full_name} ning sertifikat so'rovi rad etildi.")
    
    return redirect('admin_certificate_requests')


# Lesson views
def _is_section_locked_for_student(user, section, profession):
    """O'quvchi uchun bo'lim qulflanganmi - oldingi bo'limdagi barcha darslar bajarilganmi"""
    if not user.is_student or user.is_teacher or user.is_admin:
        return False
    sections = profession.sections.filter(is_active=True).prefetch_related('lessons').order_by('order')
    sections_list = list(sections)
    try:
        section_idx = next(i for i, s in enumerate(sections_list) if s.id == section.id)
    except StopIteration:
        return False
    if section_idx == 0:
        return False
    # Oldingi bo'limlardagi barcha darslarni tekshirish
    watched_videos = set(VideoProgress.objects.filter(
        user=user, watched=True,
        video__lesson__profession=profession
    ).values_list('video__lesson_id', flat=True))
    passed_tests = set(TestResult.objects.filter(
        student=user, test__lesson__profession=profession, passed=True
    ).values_list('test__lesson_id', flat=True))
    accepted_homeworks = set(HomeworkSubmission.objects.filter(
        student=user, homework__lesson__profession=profession,
        status__in=['accepted', 'graded']
    ).values_list('homework__lesson_id', flat=True))
    completed_lesson_ids = watched_videos | passed_tests | accepted_homeworks
    for prev_section in sections_list[:section_idx]:
        for prev_lesson in prev_section.lessons.all():
            if prev_lesson.lesson_type == 'dictionary':
                continue
            if prev_lesson.pk not in completed_lesson_ids:
                return True
    return False


@login_required
def lesson_view(request, pk):
    lesson = get_object_or_404(Lesson, pk=pk)
    profession = lesson.profession
    
    if request.user.is_student:
        if not CourseEnrollment.objects.filter(user=request.user, profession=profession).exists():
            messages.error(request, "Avval kursga yoziling!")
            return redirect('profession_detail', pk=profession.pk)

        # Lug'at darslariga cheklovsiz kirish
        if lesson.lesson_type != 'dictionary':
            from datetime import date
            today = date.today()

            # Bajarilgan darslarni aniqlash
            watched_videos = set(VideoProgress.objects.filter(
                user=request.user, watched=True,
                video__lesson__profession=profession
            ).values_list('video__lesson_id', flat=True))
            passed_tests = set(TestResult.objects.filter(
                student=request.user, test__lesson__profession=profession, passed=True
            ).values_list('test__lesson_id', flat=True))
            accepted_homeworks = set(HomeworkSubmission.objects.filter(
                student=request.user, homework__lesson__profession=profession,
                status__in=['accepted', 'graded']
            ).values_list('homework__lesson_id', flat=True))
            graded_speakings = set(SpeakingSubmission.objects.filter(
                student=request.user, speaking_task__lesson__profession=profession,
                status='graded'
            ).values_list('speaking_task__lesson_id', flat=True))
            completed_lesson_ids = watched_videos | passed_tests | accepted_homeworks | graded_speakings

            # Agar bu dars allaqachon bajarilgan bo'lsa — erkin kirish
            if lesson.pk not in completed_lesson_ids:
                current_section = lesson.section
                if current_section:
                    section_lessons_ids = set(
                        current_section.lessons.exclude(lesson_type='dictionary').values_list('pk', flat=True)
                    )
                    section_started = bool(section_lessons_ids & completed_lesson_ids)
                    section_completed = section_lessons_ids.issubset(completed_lesson_ids)

                    if not section_completed and not section_started:
                        # === YANGI BO'LIM — cheklovlar qo'llanadi ===
                        # Oldingi bo'lim tugatilganmi?
                        all_sections = list(profession.sections.filter(is_active=True).order_by('order', 'created_at'))
                        section_idx = None
                        for idx, s in enumerate(all_sections):
                            if s.id == current_section.id:
                                section_idx = idx
                                break

                        if section_idx is not None and section_idx > 0:
                            prev_section = all_sections[section_idx - 1]
                            prev_section_lessons = set(
                                prev_section.lessons.exclude(lesson_type='dictionary').values_list('pk', flat=True)
                            )
                            if not prev_section_lessons.issubset(completed_lesson_ids):
                                messages.warning(request, "Avval oldingi bo'limdagi barcha darslarni bajaring! 🔒")
                                return redirect('profession_detail', pk=profession.pk)

                        # Kunlik cheklash: bugun boshqa bo'limga kirilganmi?
                        if profession.daily_section_limit:
                            today_section_access = DailySectionAccess.objects.filter(
                                user=request.user, profession=profession, accessed_date=today
                            ).select_related('section').first()
                            if today_section_access and today_section_access.section_id != current_section.id:
                                messages.warning(request, f"Bugun siz faqat \"{today_section_access.section.title}\" bo'limini o'qiyolasiz. Yangi bo'limga ertaga kirishingiz mumkin! 📚")
                                return redirect('profession_detail', pk=profession.pk)

                    # Tugatilmagan bo'limga kirganida DailySectionAccess yozish
                    # (boshlangan yoki yangi — farqi yo'q)
                    # Bu bo'limni bugun tugatsa, keyingi bo'lim ertaga ochiladi
                    if not section_completed and profession.daily_section_limit:
                        today_access = DailySectionAccess.objects.filter(
                            user=request.user, profession=profession, accessed_date=today
                        ).first()
                        if not today_access:
                            DailySectionAccess.objects.create(
                                user=request.user, profession=profession,
                                section=current_section, accessed_date=today
                            )
    
    context = {'lesson': lesson, 'profession': profession}
    
    # Keyingi darsni topish
    next_lesson = None
    if lesson.section:
        next_lesson = Lesson.objects.filter(
            profession=profession,
            section=lesson.section,
            order__gt=lesson.order
        ).first()
        if not next_lesson:
            next_section = Section.objects.filter(
                profession=profession,
                is_active=True,
                order__gt=lesson.section.order
            ).first()
            if next_section:
                next_lesson = Lesson.objects.filter(
                    profession=profession,
                    section=next_section
                ).first()
    else:
        next_lesson = Lesson.objects.filter(
            profession=profession,
            section__isnull=True,
            order__gt=lesson.order
        ).first()
    context['next_lesson'] = next_lesson
    
    if lesson.lesson_type == 'video':
        video = lesson.video
        progress, _ = VideoProgress.objects.get_or_create(user=request.user, video=video)
        # AI maqola yaratish (birinchi marta) — faqat threadda, requestni bloklamaymiz
        if not lesson.ai_article:
            import threading
            _lesson_id = lesson.pk
            _title = lesson.title
            _prof_name = profession.name
            def _bg_generate():
                try:
                    from accounts.models import Lesson as _Lesson
                    art = _generate_ai_article(_title, _prof_name)
                    if art:
                        _Lesson.objects.filter(pk=_lesson_id, ai_article__isnull=True).update(ai_article=art)
                except Exception:
                    pass
            threading.Thread(target=_bg_generate, daemon=True).start()
        context['video'] = video
        context['progress'] = progress
        return render(request, 'accounts/lessons/video_lesson.html', context)
    
    elif lesson.lesson_type == 'homework':
        homework = lesson.homework
        submission = HomeworkSubmission.objects.filter(homework=homework, student=request.user).first()
        context['homework'] = homework
        context['submission'] = submission
        context['form'] = HomeworkSubmissionForm()
        return render(request, 'accounts/lessons/homework_lesson.html', context)
    
    elif lesson.lesson_type == 'test':
        test = lesson.test
        result = TestResult.objects.filter(test=test, student=request.user).order_by('-completed_at').first()
        context['test'] = test
        context['result'] = result
        if test.test_type == 'final':
            # Yakuniy test uchun qo'shimcha ma'lumotlar
            pending_payment = FinalTestPayment.objects.filter(
                student=request.user, test=test, status='pending'
            ).exists() if result else False
            approved_payment = FinalTestPayment.objects.filter(
                student=request.user, test=test, status='approved'
            ).exists() if result else False
            context['pending_payment'] = pending_payment
            context['approved_payment'] = approved_payment
            return render(request, 'accounts/lessons/final_test_lesson.html', context)
        return render(request, 'accounts/lessons/test_lesson.html', context)
    
    elif lesson.lesson_type == 'dictionary':
        dictionary = lesson.dictionary
        words = dictionary.words.all()
        search = request.GET.get('q', '').strip()
        if search:
            words = words.filter(
                models.Q(term__icontains=search) | models.Q(translation__icontains=search)
            )
        context['dictionary'] = dictionary
        context['words'] = words
        context['search'] = search
        return render(request, 'accounts/lessons/dictionary_lesson.html', context)
    
    elif lesson.lesson_type == 'speaking':
        speaking_task = lesson.speaking_task
        submission = SpeakingSubmission.objects.filter(speaking_task=speaking_task, student=request.user).first()
        context['speaking_task'] = speaking_task
        context['submission'] = submission
        return render(request, 'accounts/lessons/speaking_lesson.html', context)
    
    return redirect('profession_detail', pk=profession.pk)


@login_required
def submit_speaking(request, pk):
    """Speaking vazifani topshirish"""
    speaking_task = get_object_or_404(SpeakingTask, pk=pk)
    
    if request.method != 'POST':
        return redirect('lesson_view', pk=speaking_task.lesson.pk)
    
    existing = SpeakingSubmission.objects.filter(speaking_task=speaking_task, student=request.user).first()
    if existing:
        messages.info(request, "Siz bu vazifani allaqachon topshirgansiz!")
        return redirect('lesson_view', pk=speaking_task.lesson.pk)
    
    audio_file = request.FILES.get('audio_file')
    if not audio_file:
        messages.error(request, "Audio faylni yuklang!")
        return redirect('lesson_view', pk=speaking_task.lesson.pk)
    
    submission = SpeakingSubmission.objects.create(
        speaking_task=speaking_task,
        student=request.user,
        audio_file=audio_file,
    )
    
    # AI avtomatik tekshiruv
    if speaking_task.ai_check and speaking_task.lesson.profession.ai_check_enabled:
        try:
            from teacher.views import _ai_grade_speaking
            ai_result = _ai_grade_speaking(submission)
            if ai_result:
                submission.grade = ai_result['grade']
                submission.feedback = f"🤖 AI xulosasi:\n{ai_result['feedback']}"
                submission.ai_feedback = ai_result['feedback']
                submission.pronunciation_score = ai_result.get('pronunciation', 0)
                submission.fluency_score = ai_result.get('fluency', 0)
                submission.grammar_score = ai_result.get('grammar', 0)
                submission.vocabulary_score = ai_result.get('vocabulary', 0)
                submission.status = ai_result['status']
                submission.graded_at = timezone.now()
                submission.save()
                
                if ai_result['status'] == 'graded' and not submission.coin_awarded:
                    coin_amount = 10
                    if ai_result['grade'] >= 9:
                        coin_amount += 5
                    elif ai_result['grade'] >= 8:
                        coin_amount += 3
                    if request.user.is_premium:
                        coin_amount *= 2
                    request.user.add_coins(coin_amount, f"Speaking vazifa baholandi: {speaking_task.lesson.title}")
                    submission.coin_awarded = True
                    submission.save(update_fields=['coin_awarded'])
                    ActivityLog.objects.create(
                        user=request.user, action_type='homework_graded',
                        description=f"Speaking AI baholadi: {speaking_task.lesson.title} - Baho: {ai_result['grade']}, +{coin_amount} coin"
                    )
                
                messages.success(request, f"Speaking vazifa topshirildi va AI baholadi: {ai_result['grade']} ball!")
                return redirect('lesson_view', pk=speaking_task.lesson.pk)
            else:
                messages.warning(request, "Speaking vazifa topshirildi, lekin AI tekshirishda xatolik yuz berdi. Ustoz tekshiradi.")
        except Exception as e:
            import traceback
            print(f"Speaking AI tekshiruv xatolik: {e}")
            traceback.print_exc()
            messages.warning(request, "Speaking vazifa topshirildi, lekin AI tekshirishda xatolik yuz berdi. Ustoz tekshiradi.")
    else:
        messages.success(request, "Speaking vazifa muvaffaqiyatli topshirildi!")
    
    return redirect('lesson_view', pk=speaking_task.lesson.pk)


@login_required
def mark_video_watched(request, pk):
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST only'})
    
    video = get_object_or_404(VideoLesson, pk=pk)
    progress, _ = VideoProgress.objects.get_or_create(user=request.user, video=video)
    
    coin_amount = 2 if request.user.is_premium else 1
    awarded = False
    
    if not progress.watched:
        progress.watched = True
        progress.watched_at = timezone.now()
        progress.save()
        
        if not progress.coin_awarded:
            request.user.add_coins(coin_amount, f"Video darslik ko'rildi: {video.lesson.title}")
            progress.coin_awarded = True
            progress.save()
            awarded = True
        
        # Avtomatik xabar yuborish
        from .notifications import on_video_watched
        on_video_watched(request.user, progress)
    
    return JsonResponse({
        'success': True,
        'coins': request.user.coins,
        'coin_amount': coin_amount if awarded else 0,
        'is_premium': request.user.is_premium,
    })


def _notify_ai_graded(submission, ai_result):
    """AI baholaganda o'quvchi, guruh va adminlarga xabar"""
    student = submission.student
    profession = submission.homework.lesson.profession.name
    lesson = submission.homework.lesson.title
    grade = ai_result['grade']
    feedback = ai_result['feedback']

    # Saytda shaxsiy xabar
    Message.objects.create(
        recipient=student,
        title=f"⏰ Tahrirlash muddati tugadi — vazifa baholandi",
        content=f"'{lesson}' vazifangiz uchun 1 soatlik tahrirlash muddati tugadi.\n\n🏆 Baho: {grade}/10\n\n💬 AI izohi:\n{feedback}",
        message_type='system'
    )

    notify_user(
        student.telegram_id,
        f"⏰ <b>Tahrirlash muddati tugadi!</b>\n"
        f"✅ <b>Vazifangiz AI tomonidan baholandi!</b>\n\n"
        f"📚 {profession}\n"
        f"📖 {lesson}\n"
        f"🏆 Baho: <b>{grade}/10</b>\n\n"
        f"💬 <b>AI izohi:</b>\n{feedback}"
    )
    notify_admins(
        f"✅ <b>Uy vazifasi AI baholadi!</b>\n\n"
        f"👤 {student.first_name} {student.last_name}\n"
        f"📚 {profession} / {lesson}\n"
        f"🏆 Baho: <b>{grade}/10</b>\n"
        f"💬 {feedback[:200]}"
    )


def _notify_ai_revision(submission, ai_result):
    """AI qayta ishlashga yuborganda o'quvchi, guruh va adminlarga xabar"""
    student = submission.student
    profession = submission.homework.lesson.profession.name
    lesson = submission.homework.lesson.title
    grade = ai_result['grade']
    feedback = ai_result['feedback']

    # Saytda shaxsiy xabar
    Message.objects.create(
        recipient=student,
        title=f"⏰ Tahrirlash muddati tugadi — vazifa qayta ishlash kerak",
        content=f"'{lesson}' vazifangiz uchun 1 soatlik tahrirlash muddati tugadi.\n\n🏆 Baho: {grade}/10\n\n💬 Sabab:\n{feedback}\n\nIltimos, tuzatib qayta yuboring!",
        message_type='warning'
    )

    notify_user(
        student.telegram_id,
        f"⏰ <b>Tahrirlash muddati tugadi!</b>\n"
        f"⚠️ <b>Vazifangiz qayta ishlash kerak!</b>\n\n"
        f"📚 {profession}\n"
        f"📖 {lesson}\n"
        f"🏆 Baho: <b>{grade}/10</b>\n\n"
        f"💬 <b>Sabab:</b>\n{feedback}\n\n"
        f"📝 Iltimos, tuzatib qayta yuboring!"
    )
    notify_admins(
        f"⚠️ <b>Uy vazifasi AI qaytardi!</b>\n\n"
        f"👤 {student.first_name} {student.last_name}\n"
        f"📚 {profession} / {lesson}\n"
        f"🏆 Baho: <b>{grade}/10</b>\n"
        f"💬 {feedback[:200]}"
    )


def _schedule_ai_check(submission_pk):
    """O'quvchi vazifa yuborgandan 1 soat keyin AI tekshiruvini rejalashtirish"""
    import threading

    def _run_ai_check(sub_pk):
        from django import db
        from accounts.models import HomeworkSubmission
        from coin.models import ActivityLog

        try:
            sub = HomeworkSubmission.objects.select_related(
                'homework__lesson__profession', 'student'
            ).get(pk=sub_pk)
        except HomeworkSubmission.DoesNotExist:
            return
        finally:
            db.close_old_connections()

        if sub.ai_checked or sub.status != 'pending':
            return

        hw = sub.homework
        student_answer = _read_submission_content(sub)

        if not student_answer:
            if sub.submission_type == 'file' and sub.file:
                import os
                if os.path.splitext(sub.file.name)[1].lower() == '.pdf':
                    sub.ai_feedback = "📄 Suniy Intellekt PDF formatni qo'llab-quvvatlamaydi. Faqat matn yoki kod fayllarini tekshira oladi."
            sub.ai_checked = True
            sub.save(update_fields=['ai_checked', 'ai_feedback'])
            return

        try:
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

                if ai_result['status'] == 'graded' and not sub.coin_awarded:
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
                    _notify_ai_graded(sub, ai_result)
                elif ai_result['status'] == 'revision':
                    _notify_ai_revision(sub, ai_result)
            else:
                sub.ai_checked = True
                sub.save(update_fields=['ai_checked'])
        except Exception as e:
            print(f"AI auto-check error (submission #{sub_pk}): {e}")
        finally:
            db.close_old_connections()

    timer = threading.Timer(3600, _run_ai_check, args=[submission_pk])
    timer.daemon = True
    timer.start()


def _notify_homework_submitted(student, homework):
    """Yangi vazifa yuborilganda faqat kurs o'qituvchilariga xabar"""
    hw_text = homework.description[:50] if homework.description else ""
    profession = homework.lesson.profession
    lesson = homework.lesson.title

    # Faqat shu kursga biriktirilgan o'qituvchilarga xabar yuborish
    teachers = profession.teachers.all()
    for teacher in teachers:
        # Saytda shaxsiy xabar
        Message.objects.create(
            recipient=teacher,
            title=f"📝 Yangi uy vazifasi: {lesson}",
            content=f"{student.first_name} {student.last_name} '{profession.name}' kursining '{lesson}' darsiga uy vazifasini yubordi. Tekshirishni kutmoqda.",
            message_type='personal'
        )
        # Telegram xabar
        if teacher.telegram_id:
            notify_user(
                teacher.telegram_id,
                f"📝 <b>Yangi uy vazifasi yuborildi!</b>\n\n"
                f"👤 {student.first_name} {student.last_name}\n"
                f"📚 Kurs: {profession.name}\n"
                f"📖 Dars: {lesson}\n"
                f"📋 {hw_text}\n\n"
                f"👨‍🏫 Tekshirishni unutmang!"
            )

    # Agar kursga o'qituvchi biriktirilmagan bo'lsa, adminlarga xabar
    if not teachers.exists():
        notify_admins(
            f"📝 <b>Yangi uy vazifasi yuborildi!</b>\n\n"
            f"👤 {student.first_name} {student.last_name}\n"
            f"📚 Kurs: {profession.name}\n"
            f"📖 Dars: {lesson}\n"
            f"📋 {hw_text}\n\n"
            f"⚠️ Bu kursga o'qituvchi biriktirilmagan!"
        )


def _notify_homework_graded(grader, submission, grade):
    """Vazifa baholanganda o'quvchi, guruh va adminlarga xabar"""
    student = submission.student
    profession = submission.homework.lesson.profession.name
    lesson = submission.homework.lesson.title
    feedback = submission.feedback or ""

    notify_user(
        student.telegram_id,
        f"✅ <b>Uy vazifangiz baholandi!</b>\n\n"
        f"📚 Kurs: {profession}\n"
        f"📖 Dars: {lesson}\n"
        f"📊 Baho: <b>{grade}</b> ball\n"
        f"👨‍🏫 Baholadi: {grader.first_name} {grader.last_name}\n"
        f"{'💬 Izoh: ' + feedback[:100] if feedback else ''}"
    )
    notify_admins(
        f"✅ <b>Uy vazifasi baholandi!</b>\n\n"
        f"👤 {student.first_name} {student.last_name}\n"
        f"📚 {profession} → {lesson}\n"
        f"📊 Baho: {grade} ball\n"
        f"👨‍🏫 {grader.first_name} {grader.last_name}"
    )


def _normalize_code(text):
    """Kodni normallashtirish — bo'sh joylar, izohlar, katta-kichik harflarni tenglashtirish"""
    import re
    lines = text.splitlines()
    cleaned = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        # Izohlarni olib tashlash
        line = re.sub(r'#.*$', '', line).strip()
        line = re.sub(r'//.*$', '', line).strip()
        if not line:
            continue
        # Bo'sh joylarni birlashtirish, kichik harfga
        line = re.sub(r'\s+', ' ', line).lower()
        cleaned.append(line)
    return '\n'.join(cleaned)


def _calculate_similarity(text1, text2):
    """Ikki matnni solishtirish — SequenceMatcher + token-based"""
    from difflib import SequenceMatcher
    import re

    if not text1 or not text2:
        return 0

    norm1 = _normalize_code(text1)
    norm2 = _normalize_code(text2)

    if not norm1 or not norm2:
        return 0

    # Qisqa kodlarni plagiat deb belgilamaslik (10 qatordan kam = oddiy vazifa)
    lines1 = norm1.splitlines()
    lines2 = norm2.splitlines()
    min_lines = min(len(lines1), len(lines2))
    if min_lines < 5:
        return 0

    # 1. SequenceMatcher — umumiy o'xshashlik
    seq_ratio = SequenceMatcher(None, norm1, norm2).ratio() * 100

    # 2. Qator-bo'yicha taqqoslash — NOYOB qatorlar (print("salom") kabi umumiy qatorlarni filtrlash)
    common_patterns = {
        'print(', 'input(', 'if ', 'else:', 'elif ', 'for ', 'while ',
        'def ', 'return', 'import ', 'class ', 'pass', 'break', 'continue',
        'true', 'false', 'none', '= int(', '= str(', '= float(',
    }
    set1 = set(lines1)
    set2 = set(lines2)
    # Umumiy pattern bo'lgan qatorlarni chiqarib tashlash
    unique1 = {l for l in set1 if not any(p in l for p in common_patterns)}
    unique2 = {l for l in set2 if not any(p in l for p in common_patterns)}
    if unique1 and unique2:
        common = unique1 & unique2
        total = max(len(unique1), len(unique2))
        line_ratio = (len(common) / total) * 100
    else:
        line_ratio = 0

    # 3. Token-based
    tokens1 = re.findall(r'[a-zA-Z_]\w*|[^\s\w]', norm1)
    tokens2 = re.findall(r'[a-zA-Z_]\w*|[^\s\w]', norm2)
    if tokens1 and tokens2:
        token_ratio = SequenceMatcher(None, tokens1, tokens2).ratio() * 100
    else:
        token_ratio = 0

    # O'rtacha olish (max emas!) — bitta yuqori chiqsa ham boshqalari pasaytiradi
    similarity = (seq_ratio + line_ratio + token_ratio) / 3

    # Qisqa kodlarda similarity ni pasaytirish (10 qatordan kam bo'lsa 20% kamaytirish)
    if min_lines < 10:
        similarity *= 0.8

    return round(similarity, 1)


def _check_similarity_with_others(homework, current_submission, student_answer):
    """Boshqa o'quvchilarning javoblari bilan o'xshashlikni tekshirish — lokal algoritm"""

    other_submissions = HomeworkSubmission.objects.filter(
        homework=homework
    ).exclude(
        pk=current_submission.pk
    ).exclude(
        status='revision'
    ).select_related('student').order_by('-submitted_at')[:30]

    if not other_submissions:
        return None

    best_match = {'similarity': 0, 'student': '', 'student_id': None}

    for sub in other_submissions:
        content = _read_submission_content(sub)
        if not content or len(content.strip()) <= 20:
            continue

        sim = _calculate_similarity(student_answer, content)

        if sim > best_match['similarity']:
            best_match = {
                'similarity': sim,
                'student': sub.student.full_name if hasattr(sub.student, 'full_name') else f"{sub.student.first_name} {sub.student.last_name}",
                'student_id': sub.student.pk,
            }

    if best_match['similarity'] < 85:
        return {
            'is_plagiat': False,
            'similarity': int(best_match['similarity']),
            'similar_to': best_match['student'],
            'reason': '',
        }

    sim_pct = int(best_match['similarity'])
    if sim_pct >= 95:
        reason = f"Javob {best_match['student']} ning javobiga deyarli bir xil (faqat bo'sh joylar yoki o'zgaruvchi nomlari farq qiladi)"
    elif sim_pct >= 90:
        reason = f"Javobning asosiy tuzilishi va mantiqi {best_match['student']} ning javobi bilan juda o'xshash"
    else:
        reason = f"Javob {best_match['student']} ning javobiga o'xshash ko'rinadi"

    return {
        'is_plagiat': True,
        'similarity': sim_pct,
        'similar_to': best_match['student'],
        'reason': reason,
    }


def _get_student_writing_profile(student, current_submission_pk=None):
    """O'quvchining oldingi qabul qilingan javoblaridan yozish uslubini yig'ish"""
    previous_subs = HomeworkSubmission.objects.filter(
        student=student,
        status__in=['accepted', 'graded'],
    ).exclude(
        pk=current_submission_pk
    ).order_by('-submitted_at')[:10]

    previous_answers = []
    for sub in previous_subs:
        content = _read_submission_content(sub)
        if content and len(content.strip()) > 20:
            snippet = content[:800] if len(content) > 800 else content
            previous_answers.append(snippet)
        if len(previous_answers) >= 5:
            break

    return previous_answers


def _check_ai_generated(homework_description, student_answer, student=None, current_submission_pk=None):
    """Javob suniy intellekt yordamida yozilganligini tekshirish — QATTIQ REJIM + o'quvchi profili"""
    import json
    from django.conf import settings
    api_key = getattr(settings, 'OPENAI_API_KEY', None)
    if not api_key or not api_key.strip():
        return None

    # O'quvchining oldingi javoblarini yig'ish
    previous_answers = []
    if student:
        previous_answers = _get_student_writing_profile(student, current_submission_pk)

    # Oldingi javoblar bo'limini tayyorlash
    profile_section = ""
    if previous_answers:
        profile_section = (
            "\n\n📊 O'QUVCHINING OLDINGI QABUL QILINGAN JAVOBLARI (uslub namunasi):\n"
            "Bu javoblar o'qituvchi tomonidan tekshirilgan va qabul qilingan — bu o'quvchining HAQIQIY yozish uslubi.\n"
            "Hozirgi javobni SHU uslub bilan solishtiring!\n\n"
        )
        for i, ans in enumerate(previous_answers, 1):
            profile_section += f"--- Oldingi javob #{i} ---\n{ans}\n\n"
        profile_section += (
            "🔑 MUHIM TAHLIL QOIDALARI:\n"
            "- Agar hozirgi javob oldingi javoblardan KESKIN FARQ QILSA (uslub, murakkablik, til, sifat) → bu AI belgisi!\n"
            "- Agar o'quvchi oldin oddiy kod yozgan, endi birdan professional darajada yozsa → AI!\n"
            "- Agar o'quvchi oldin o'zbekcha o'zgaruvchi ishlatgan, endi professional inglizcha → AI!\n"
            "- Agar o'quvchi oldin izohsiz yozgan, endi har qatorga izoh yozgan → AI!\n"
            "- Agar o'quvchi oldin xatolar qilgan, endi mukammal kod yozgan → AI!\n"
            "- Agar uslub o'xshash bo'lsa va tabiiy rivojlanish ko'rinsa → bu AI EMAS\n"
        )
    else:
        profile_section = (
            "\n\n⚠️ Bu o'quvchining BIRINCHI topshirig'i — oldingi javoblar mavjud emas.\n"
            "Shuning uchun faqat AI belgilariga qarab tekshiring.\n"
        )

    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key.strip(), timeout=60)
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Siz o'quv platformasining AI tekshiruvchisisiz. "
                        "Boshlang'ich dasturlash o'quvchilarining javoblarini tekshirasiz.\n\n"
                        "⚠️ MUHIM: Siz faqat ANIQ AI belgilari bo'lgandagina flaglashingiz kerak. "
                        "Shubha bo'lsa — o'quvchi foydasiga hal qiling! "
                        "O'quvchilar o'rganmoqda, ular ham yaxshi kod yozishi mumkin.\n\n"
                        "🔍 FAQAT shu hollarda AI deb belgilang (kamida 3 tasi bir vaqtda bo'lishi kerak):\n"
                        "1. AI IBORALARI: 'Here is', 'Let me', 'certainly', 'I'd be happy to', "
                        "'Let's break this down', 'Note that', 'Feel free' kabi iboralar\n"
                        "2. CHATGPT FORMATI: Markdown (###, **bold**), qadam-baqadam raqamlangan tushuntirish\n"
                        "3. PROFESSIONAL INGLIZCHA IZOHLAR: Har qatorga mukammal inglizcha comment yozilgan\n"
                        "4. COPY-PASTE BELGILARI: Vazifaga aloqasi yo'q import yoki funksiyalar mavjud\n"
                        "5. TO'LIQ KO'CHIRMA: Javob internet yoki AI dan to'liq ko'chirilgani aniq ko'rinadi\n\n"
                        "✅ Bu AI EMAS — haqiqiy o'quvchi belgilari (bularni AI deb BELGILAMANG):\n"
                        "- O'quvchi yaxshi kod yozgan — bu normal, o'rgangan bo'lishi mumkin\n"
                        "- Javob qisqa va to'g'ri — bu AI degani emas\n"
                        "- try/except, class ishlatgan — darsda o'rgangan bo'lishi mumkin\n"
                        "- Izohlar yozgan — bu yaxshi odatni o'rgangan degani\n"
                        "- Oldingi javoblardan yaxshiroq yozgan — bu TABIIY rivojlanish\n"
                        "- Kichik xatolar, typo bor — haqiqiy o'quvchi belgisi\n"
                        "- O'zbekcha o'zgaruvchi nomlari ishlatgan\n\n"
                        "Faqat JSON formatda javob bering:\n"
                        '{"is_ai": true/false, "confidence": <0-100>, "reason": "<o\'zbek tilida sabab>", '
                        '"style_match": "<oldingi javoblar bilan solishtirish>"}\n\n'
                        "- is_ai: faqat 3+ aniq belgi bo'lganda true\n"
                        "- confidence: 75 dan past bo'lsa is_ai: false bo'lishi KERAK\n"
                        "- reason: O'zbek tilida qisqa izoh\n"
                        "- style_match: Oldingi javoblar bilan solishtirish"
                    )
                },
                {
                    "role": "user",
                    "content": (
                        f"Vazifa tavsifi:\n{homework_description}\n\n"
                        f"O'quvchining hozirgi javobi:\n{student_answer}"
                        f"{profile_section}"
                    )
                }
            ],
            max_tokens=500,
            temperature=0.05,
        )
        result_text = response.choices[0].message.content.strip()
        if result_text.startswith('```'):
            result_text = result_text.split('\n', 1)[1].rsplit('```', 1)[0].strip()
        result = json.loads(result_text)
        reason = result.get('reason', '')
        style_match = result.get('style_match', '')
        if style_match:
            reason = f"{reason}\n📊 Uslub tahlili: {style_match}"
        return {
            'is_ai': bool(result.get('is_ai', False)),
            'confidence': min(100, max(0, int(result.get('confidence', 0)))),
            'reason': reason,
        }
    except Exception as e:
        print(f"AI check error: {e}")
        return None


def _get_ai_homework_feedback(homework_description, student_answer):
    """Premium foydalanuvchilar uchun AI xulosasi olish"""
    from django.conf import settings
    api_key = getattr(settings, 'OPENAI_API_KEY', None)
    if not api_key or not api_key.strip():
        return None
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key.strip(), timeout=30)
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Siz o'quv platformasining AI tekshiruvchisisiz. O'zbek tilida javob bering. "
                        "O'quvchining uyga vazifasini tekshiring va qisqa xulosa bering:\n"
                        "1. Javob to'g'ri yoki noto'g'ri ekanligini ayting\n"
                        "2. Qisqa tushuntirish bering (3-5 gap)\n"
                        "3. Agar xato bo'lsa, to'g'ri yo'nalishni ko'rsating\n"
                        "4. Rag'batlantiruvchi ohangda yozing\n"
                        "Javobni 150 so'zdan oshirmang."
                    )
                },
                {
                    "role": "user",
                    "content": (
                        f"Vazifa tavsifi:\n{homework_description}\n\n"
                        f"O'quvchining javobi:\n{student_answer}"
                    )
                }
            ],
            max_tokens=500,
            temperature=0.3,
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"AI homework feedback error: {e}")
        return None


def _get_ai_grade(homework_description, student_answer):
    """AI yordamida vazifani baholash: ball, status va izoh qaytaradi"""
    import json
    from django.conf import settings
    api_key = getattr(settings, 'OPENAI_API_KEY', None)
    if not api_key or not api_key.strip():
        return None
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key.strip(), timeout=45)
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Siz o'quv platformasining AI baholovchisisiz. O'quvchining uyga vazifasini tekshiring va baholang.\n\n"
                        "Faqat JSON formatda javob bering, boshqa hech narsa yozmang:\n"
                        '{"grade": <1-10 orasida son>, "status": "<graded yoki revision>", "feedback": "<o\'zbek tilida izoh>"}\n\n'
                        "Qoidalar:\n"
                        "- grade: 1 dan 10 gacha son. Vazifa sifatiga qarab adolatli baho qo'ying\n"
                        "- status: FAQAT javob bo'sh, umuman noto'g'ri yoki vazifaga UMUMAN aloqasi bo'lmasa 'revision' qo'ying\n"
                        "- status: agar javob qisman bo'lsa ham, to'g'ri yo'nalishda bo'lsa 'graded' qo'ying\n"
                        "- feedback: O'zbek tilida 2-4 gapda izoh yozing. Nimasi yaxshi, nimasi yomon, qanday yaxshilash mumkinligini ayting\n"
                        "- Agar javob bo'sh yoki umuman bog'liq bo'lmasa: grade=1, status=revision\n"
                        "- Agar javob qisman to'g'ri bo'lsa: grade=4-6, status=graded\n"
                        "- Agar javob yaxshi bo'lsa: grade=7-9, status=graded\n"
                        "- Agar javob mukammal bo'lsa: grade=10, status=graded\n\n"
                        "⚠️ MUHIM: 'revision' statusini JUDA KAM ishlating! Faqat javob BUTUNLAY noto'g'ri bo'lganda.\n"
                        "Agar o'quvchi harakat qilgan va biror narsa yozgan bo'lsa — 'graded' qo'ying, past baho bering.\n"
                        "Har safar bir xil javobga BIR XIL baho bering — izchil bo'ling!"
                    )
                },
                {
                    "role": "user",
                    "content": (
                        f"Vazifa tavsifi:\n{homework_description}\n\n"
                        f"O'quvchining javobi:\n{student_answer}"
                    )
                }
            ],
            max_tokens=500,
            temperature=0.1,
        )
        result_text = response.choices[0].message.content.strip()
        # JSON ni parse qilish
        if result_text.startswith('```'):
            result_text = result_text.split('\n', 1)[1].rsplit('```', 1)[0].strip()
        result = json.loads(result_text)
        grade = max(1, min(10, int(result.get('grade', 5))))
        status = result.get('status', 'graded')
        if status not in ('graded', 'revision'):
            status = 'graded'
        feedback = result.get('feedback', '')
        return {'grade': grade, 'status': status, 'feedback': feedback}
    except Exception as e:
        print(f"AI grade error: {e}")
        return None


def _read_submission_content(submission):
    """Submission mazmunini o'qish (matn, fayl yoki rasm)"""
    if submission.submission_type == 'text' and submission.text_content:
        return submission.text_content
    elif submission.submission_type == 'file' and submission.file:
        import os
        file_ext = os.path.splitext(submission.file.name)[1].lower()
        CODE_EXTENSIONS = (
            '.py', '.js', '.html', '.css', '.java', '.c', '.cpp',
            '.json', '.xml', '.sql', '.txt', '.jsx', '.ts', '.tsx',
            '.php', '.rb', '.go', '.rs', '.swift', '.kt', '.sh',
            '.bat', '.ps1', '.yaml', '.yml', '.md', '.csv',
        )
        IMAGE_EXTENSIONS = ('.png', '.jpg', '.jpeg', '.gif', '.webp')
        if file_ext == '.pdf':
            return None
        elif file_ext in IMAGE_EXTENSIONS:
            return _read_image_with_ai(submission.file)
        elif file_ext in CODE_EXTENSIONS:
            try:
                submission.file.seek(0)
                content = submission.file.read().decode('utf-8', errors='replace')
                if len(content) > 5000:
                    content = content[:5000] + "\n... (qolgan qismi qisqartirildi)"
                return content
            except Exception:
                return None
    return None


def _read_image_with_ai(file_field):
    """Rasm faylni OpenAI Vision orqali o'qib matn sifatida qaytarish"""
    import base64
    from django.conf import settings
    api_key = getattr(settings, 'OPENAI_API_KEY', None)
    if not api_key or not api_key.strip():
        return None
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key.strip(), timeout=30)
        file_field.seek(0)
        image_data = base64.b64encode(file_field.read()).decode('utf-8')
        import os
        ext = os.path.splitext(file_field.name)[1].lower().strip('.')
        if ext == 'jpg':
            ext = 'jpeg'
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Bu rasmdagi barcha matn, kod yoki javoblarni aynan yoz. Faqat rasmdagi kontentni qaytar, boshqa hech narsa qo'shma."},
                        {"type": "image_url", "image_url": {"url": f"data:image/{ext};base64,{image_data}"}}
                    ]
                }
            ],
            max_tokens=2000,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"Image read error: {e}")
        return None


@login_required
def submit_homework(request, pk):
    homework = get_object_or_404(Homework, pk=pk)
    
    if request.method == 'POST':
        # Agar oldin topshirilgan bo'lsa, qayta yaratmaslik
        existing = HomeworkSubmission.objects.filter(homework=homework, student=request.user).first()
        if existing:
            messages.info(request, "Siz bu vazifani allaqachon topshirgansiz!")
            return redirect('lesson_view', pk=homework.lesson.pk)
        
        submission_type = request.POST.get('submission_type', 'file')
        submission = None
        
        # Faqat fayl rejimida matn qabul qilinmaydi
        if homework.file_only:
            submission_type = 'file'
        
        # Yozma topshirish rejimida faqat rasm fayl qabul qilinadi
        if homework.handwritten_only:
            submission_type = 'file'
            uploaded_file = request.FILES.get('file')
            if uploaded_file:
                import os
                ext = os.path.splitext(uploaded_file.name)[1].lower()
                if ext not in ('.jpg', '.jpeg', '.png'):
                    messages.error(request, "Faqat rasm formatida (.jpg, .jpeg, .png) qabul qilinadi!")
                    return redirect('lesson_view', pk=homework.lesson.pk)
        
        if submission_type == 'file':
            form = HomeworkSubmissionForm(request.POST, request.FILES)
            if form.is_valid():
                submission = form.save(commit=False)
                submission.homework = homework
                submission.student = request.user
                submission.submission_type = 'file'
                submission.save()
                messages.success(request, "Vazifa muvaffaqiyatli yuborildi!")
                _notify_homework_submitted(request.user, homework)
        else:
            text_content = request.POST.get('text_content', '').strip()
            if text_content:
                submission = HomeworkSubmission.objects.create(
                    homework=homework,
                    student=request.user,
                    submission_type='text',
                    text_content=text_content
                )
                messages.success(request, "Vazifa muvaffaqiyatli yuborildi!")
                _notify_homework_submitted(request.user, homework)
            else:
                messages.error(request, "Matn kiritishingiz kerak!")
        
        # AI tekshiruv — 1 soat tahrirlash muddati tugagandan keyin avtomatik ishlaydi
        if submission and homework.ai_check and homework.lesson.profession.ai_check_enabled:
            _schedule_ai_check(submission.pk)
    
    return redirect('lesson_view', pk=homework.lesson.pk)


@login_required
def edit_homework(request, pk):
    """Topshiriqni 1 soat ichida tahrirlash"""
    submission = get_object_or_404(HomeworkSubmission, pk=pk, student=request.user)
    
    if not submission.can_edit:
        messages.error(request, "Tahrirlash muddati tugagan (1 soat)!")
        return redirect('lesson_view', pk=submission.homework.lesson.pk)
    
    if request.method == 'POST':
        submission_type = request.POST.get('submission_type', submission.submission_type)
        
        if submission_type == 'file':
            new_file = request.FILES.get('file')
            if new_file:
                submission.file = new_file
                submission.submission_type = 'file'
                submission.save()
                messages.success(request, "Topshiriq muvaffaqiyatli tahrirlandi!")
            else:
                messages.error(request, "Fayl tanlang!")
        else:
            text_content = request.POST.get('text_content', '').strip()
            if text_content:
                submission.text_content = text_content
                submission.submission_type = 'text'
                submission.save()
                messages.success(request, "Topshiriq muvaffaqiyatli tahrirlandi!")
            else:
                messages.error(request, "Matn kiriting!")
    
    return redirect('lesson_view', pk=submission.homework.lesson.pk)


@login_required
def start_test(request, pk):
    test = get_object_or_404(Test, pk=pk)
    
    profession = test.lesson.profession
    
    if request.user.is_student:
        if not CourseEnrollment.objects.filter(user=request.user, profession=profession).exists():
            messages.error(request, "Avval kursga yoziling!")
            return redirect('profession_detail', pk=profession.pk)
    
    # Check if already taken and retry not allowed
    existing_result = TestResult.objects.filter(test=test, student=request.user).first()
    if existing_result:
        if test.test_type == 'final':
            # Yakuniy test: qayta ishlash uchun tasdiqlangan to'lov kerak
            approved_payment = FinalTestPayment.objects.filter(
                student=request.user, test=test, status='approved'
            ).first()
            if not approved_payment:
                messages.info(request, "Yakuniy testni qayta ishlash uchun to'lov qilishingiz kerak (65,000 so'm).")
                return redirect('final_test_payment', pk=test.pk)
            # To'lovni ishlatilgan deb belgilash
            approved_payment.delete()
        elif not test.allow_retry:
            messages.info(request, "Siz bu testni allaqachon topshirgansiz.")
            return redirect('test_result', pk=existing_result.pk)
    
    # Sessiya kalitlari
    sq_key = f'test_{test.pk}_questions'
    st_key = f'test_{test.pk}_start'
    sa_key = f'test_{test.pk}_answer_order'
    token_key = f'test_{test.pk}_submit_token'
    
    # Davom etayotgan test bormi? (sahifa yangilanganda qayta aralashtirmaslik)
    active_question_ids = request.session.get(sq_key)
    submit_token = request.session.get(token_key)
    
    if active_question_ids and not submit_token:
        # Test hali davom etmoqda — mavjud savollarni qayta yuklash
        questions_qs = TestQuestion.objects.filter(
            pk__in=active_question_ids
        ).prefetch_related('answers')
        question_map = {q.pk: q for q in questions_qs}
        questions = [question_map[qid] for qid in active_question_ids if qid in question_map]
        
        # Javoblar tartibini tiklash
        answer_order = request.session.get(sa_key, {})
        for q in questions:
            ordered_ids = answer_order.get(str(q.pk))
            if ordered_ids:
                answer_map = {a.pk: a for a in q.answers.all()}
                ordered_answers = [answer_map[aid] for aid in ordered_ids if aid in answer_map]
                q._prefetched_objects_cache['answers'] = ordered_answers
        
        # Qolgan vaqtni hisoblash
        start_time_str = request.session.get(st_key)
        remaining = test.time_limit * 60
        if start_time_str:
            from datetime import datetime as dt
            try:
                started = dt.fromisoformat(start_time_str)
                elapsed = (timezone.now() - started).total_seconds()
                remaining = max(0, test.time_limit * 60 - int(elapsed))
            except (ValueError, TypeError):
                pass
        
        if remaining <= 0:
            # Vaqt tugagan — avtomatik yuborish uchun formga yo'naltirish
            request.session.pop(sq_key, None)
            request.session.pop(st_key, None)
            request.session.pop(sa_key, None)
            return redirect('lesson_view', pk=test.lesson.pk)
        
        template = 'accounts/lessons/final_test_take.html' if test.test_type == 'final' else 'accounts/lessons/test_take.html'
        return render(request, template, {
            'test': test,
            'questions': questions,
            'remaining_time': remaining,
        })
    
    # ===== Yangi test boshlash =====
    
    # Qayta topshirish uchun coin yechish
    if existing_result and test.allow_retry and test.test_type != 'final':
        retry_cost = 3 if request.user.is_premium else 10
        request.user.remove_coins(retry_cost, f"Test qayta topshirish: {test.lesson.title}")
    
    all_questions = list(test.questions.all().distinct().prefetch_related('answers'))
    
    import random
    
    # Savollar sonini cheklash (question_count > 0 bo'lsa)
    if test.question_count and test.question_count > 0 and len(all_questions) > test.question_count:
        questions = random.sample(all_questions, test.question_count)
    else:
        questions = all_questions[:]
    
    if test.shuffle_questions:
        random.shuffle(questions)
    
    if test.shuffle_answers:
        for q in questions:
            answers_list = list(q.answers.all())
            random.shuffle(answers_list)
            q._prefetched_objects_cache['answers'] = answers_list
    
    # Sessiyaga saqlash
    request.session[sq_key] = [q.pk for q in questions]
    request.session[st_key] = timezone.now().isoformat()
    request.session.pop(token_key, None)
    
    # Javoblar tartibini saqlash
    answer_order = {}
    for q in questions:
        cached = getattr(q, '_prefetched_objects_cache', {}).get('answers')
        if cached is not None:
            answer_order[str(q.pk)] = [a.pk for a in cached]
        else:
            answer_order[str(q.pk)] = [a.pk for a in q.answers.all()]
    request.session[sa_key] = answer_order
    
    remaining = test.time_limit * 60
    
    template = 'accounts/lessons/final_test_take.html' if test.test_type == 'final' else 'accounts/lessons/test_take.html'
    return render(request, template, {
        'test': test,
        'questions': questions,
        'remaining_time': remaining,
    })


@login_required
def submit_test(request, pk):
    test = get_object_or_404(Test, pk=pk)
    
    if request.method != 'POST':
        return redirect('start_test', pk=pk)
    
    # Takroriy yuborishni oldini olish (POST refresh)
    submit_token = request.session.get(f'test_{test.pk}_submit_token')
    if submit_token:
        # Allaqachon yuborilgan — oxirgi natijaga yo'naltirish
        last_result = TestResult.objects.filter(test=test, student=request.user).order_by('-id').first()
        if last_result:
            return redirect('test_result', pk=last_result.pk)
    request.session[f'test_{test.pk}_submit_token'] = True
    
    # Sessiyani tozalash (qayta start_test ga kirganda yangi test boshlanishi uchun)
    request.session.pop(f'test_{test.pk}_answer_order', None)
    
    start_time = request.session.get(f'test_{test.pk}_start')
    started_at = timezone.now()
    if start_time:
        from datetime import datetime
        started_at = datetime.fromisoformat(start_time)
        
        # Server-side vaqt tekshiruvi — vaqt tugagan bo'lsa ham natijani qabul qilish
        # lekin vaqt limitidan 60 sekund ko'p o'tgan bo'lsa ogohlantirish
        elapsed_seconds = (timezone.now() - started_at).total_seconds()
        allowed_seconds = test.time_limit * 60 + 60  # 60 sekund tolerantlik (network delay)
        if elapsed_seconds > allowed_seconds:
            messages.warning(request, "Vaqt chegarasi o'tgan! Natijalar server vaqti bilan tekshirildi.")
    
    # Sessiyadan tanlangan savollarni olish
    shown_question_ids = request.session.get(f'test_{test.pk}_questions')
    if shown_question_ids:
        questions = test.questions.filter(pk__in=shown_question_ids)
    else:
        questions = test.questions.all()
    
    correct = 0
    total = questions.count()
    
    result = TestResult.objects.create(
        test=test,
        student=request.user,
        score=0,
        total_questions=total,
        correct_answers=0,
        started_at=started_at,
        passed=False
    )
    
    for question in questions:
        answer_id = request.POST.get(f'question_{question.pk}')
        selected_answer = None
        is_correct = False
        
        if answer_id:
            try:
                selected_answer = TestAnswer.objects.get(pk=answer_id)
                is_correct = selected_answer.is_correct
                if is_correct:
                    correct += 1
            except TestAnswer.DoesNotExist:
                pass
        
        TestUserAnswer.objects.create(
            result=result,
            question=question,
            selected_answer=selected_answer,
            is_correct=is_correct
        )
    
    score = int((correct / total) * 100) if total > 0 else 0
    result.score = score
    result.correct_answers = correct
    result.passed = score >= test.passing_score
    result.save()
    
    # Testdan o'tsa - kirish puli qaytariladi
    existing_results_count = TestResult.objects.filter(
        test=test, student=request.user
    ).exclude(pk=result.pk).count()
    
    if result.passed:
        # Avval coin olinganmi tekshirish
        already_got_coin = TestResult.objects.filter(
            test=test, student=request.user, coin_awarded=True
        ).exclude(pk=result.pk).exists()
        
        if not already_got_coin:
            # Birinchi marta o'tmoqda — coin berish
            if correct > 0:
                request.user.add_coins(correct, f"Test to'g'ri javoblar ({correct} ta): {test.lesson.title}")
            result.coin_awarded = True
            result.save()
        
        # Kirish pulini qaytarish (qayta topshirgan bo'lsa)
        if existing_results_count > 0:
            refund_amount = 5 if request.user.is_premium else 10
            request.user.add_coins(refund_amount, f"Test muvaffaqiyatli - kirish puli qaytarildi: {test.lesson.title}")
        
        total_earned = (correct if not already_got_coin else 0) + (5 if request.user.is_premium and existing_results_count > 0 else 10 if existing_results_count > 0 else 0)
        
        # Activity log
        ActivityLog.objects.create(
            user=request.user,
            action_type='submit_test',
            description=f"Test topshirdi: {test.lesson.title} - {correct}/{total} to'g'ri" + (f", +{total_earned} coin" if total_earned > 0 else "")
        )
        
        if already_got_coin:
            if existing_results_count > 0:
                refund_amount = 5 if request.user.is_premium else 10
                messages.success(request, f"Tabriklaymiz! Test muvaffaqiyatli! Siz bu test uchun coin allaqachon olib bo'lgansiz. {refund_amount} coin qaytarildi!")
            else:
                messages.success(request, f"Tabriklaymiz! Test muvaffaqiyatli!")
        elif existing_results_count > 0:
            refund_amount = 5 if request.user.is_premium else 10
            messages.success(request, f"Tabriklaymiz! Test muvaffaqiyatli! +{correct} coin (to'g'ri javoblar) va {refund_amount} coin qaytarildi!")
        else:
            messages.success(request, f"Tabriklaymiz! Test muvaffaqiyatli! +{correct} coin oldingiz (to'g'ri javoblar)!")
    else:
        # Testdan o'tmadi - coin berilmaydi
        ActivityLog.objects.create(
            user=request.user,
            action_type='submit_test',
            description=f"Test topshirdi (muvaffaqiyatsiz): {test.lesson.title} - {correct}/{total} to'g'ri"
        )
        messages.warning(request, f"Testdan o'ta olmadingiz. {correct}/{total} to'g'ri javob.")
    
    # Avtomatik xabar yuborish
    from .notifications import on_test_completed
    on_test_completed(request.user, result)
    
    # Telegram xabarlar
    passed_text = "✅ Muvaffaqiyatli" if result.passed else "❌ Muvaffaqiyatsiz"
    notify_user(
        request.user.telegram_id,
        f"📊 <b>Test natijasi!</b>\n\n"
        f"📚 Kurs: {test.lesson.profession.name}\n"
        f"📖 Dars: {test.lesson.title}\n"
        f"✏️ Natija: {correct}/{total} to'g'ri ({score}%)\n"
        f"{passed_text}"
    )
    return redirect('test_result', pk=result.pk)


@login_required
def test_result(request, pk):
    result = get_object_or_404(TestResult, pk=pk)
    user_answers = result.user_answers.all().select_related('question', 'selected_answer')
    
    lesson = result.test.lesson
    profession = lesson.profession
    section = lesson.section
    
    video_lesson = None
    homework_lesson = None
    same_section_lessons = Lesson.objects.filter(profession=profession, section=section) if section else Lesson.objects.filter(profession=profession)
    for l in same_section_lessons:
        if l.lesson_type == 'video' and not video_lesson:
            video_lesson = l
        elif l.lesson_type == 'homework' and not homework_lesson:
            homework_lesson = l
    
    return render(request, 'accounts/lessons/test_result.html', {
        'result': result,
        'user_answers': user_answers,
        'video_lesson': video_lesson,
        'homework_lesson': homework_lesson,
    })


# Profile views
@login_required
def profile_view(request):
    certificates = Certificate.objects.filter(student=request.user).select_related('profession')
    enrollments = request.user.enrollments.all().select_related('profession')
    
    # Tugallangan kurslar (sertifikat berilgan)
    completed_profession_ids = certificates.values_list('profession_id', flat=True)
    completed_courses = []
    active_courses = []
    
    for enrollment in enrollments:
        if enrollment.profession_id in completed_profession_ids:
            cert = certificates.filter(profession_id=enrollment.profession_id).first()
            completed_courses.append({
                'enrollment': enrollment,
                'certificate': cert,
            })
        else:
            active_courses.append(enrollment)
    
    # Deploy qilgan loyihalar
    deploys = HTMLDeploy.objects.filter(user=request.user, is_active=True).order_by('-created_at')[:6]
    
    # Coin statistika
    from coin.models import CoinTransaction
    total_earned_coins = CoinTransaction.objects.filter(user=request.user, action='add').aggregate(total=Sum('amount'))['total'] or 0
    total_spent_coins = CoinTransaction.objects.filter(user=request.user, action__in=['remove', 'purchase']).aggregate(total=Sum('amount'))['total'] or 0
    
    # Ball statistika
    test_results = TestResult.first_attempts().filter(student=request.user)
    total_tests_taken = test_results.count()
    avg_test_score = round(test_results.aggregate(avg=Avg('score'))['avg'] or 0, 1)
    
    hw_submissions = HomeworkSubmission.objects.filter(student=request.user)
    total_homeworks_submitted = hw_submissions.count()
    avg_homework_grade = round(hw_submissions.filter(grade__isnull=False).aggregate(avg=Avg('grade'))['avg'] or 0, 1)
    
    return render(request, 'accounts/profile.html', {
        'certificates': certificates,
        'enrollments': enrollments,
        'completed_courses': completed_courses,
        'active_courses': active_courses,
        'deploys': deploys,
        'total_earned_coins': total_earned_coins,
        'total_spent_coins': total_spent_coins,
        'total_tests_taken': total_tests_taken,
        'avg_test_score': avg_test_score,
        'total_homeworks_submitted': total_homeworks_submitted,
        'avg_homework_grade': avg_homework_grade,
    })


@login_required
def site_settings(request):
    """Sayt sozlamalari sahifasi"""
    return render(request, 'accounts/settings.html')


@login_required
def save_weather_effect(request):
    if request.method == 'POST':
        import json
        try:
            data = json.loads(request.body)
            effect = data.get('effect', 'auto')
        except (json.JSONDecodeError, AttributeError):
            effect = request.POST.get('effect', 'auto')

        allowed = ('off', 'auto', 'winter', 'spring', 'summer', 'autumn')
        if effect not in allowed:
            effect = 'auto'

        request.user.weather_effect = effect
        request.user.save(update_fields=['weather_effect'])
        return JsonResponse({'status': 'ok'})

    return JsonResponse({'status': 'error'}, status=400)


@login_required
def classmates_view(request, pk):
    """Kursdoshlar ro'yxati"""
    profession = get_object_or_404(Profession, pk=pk)
    
    # O'qituvchi faqat o'zi tayinlangan kurslarga kirishi mumkin
    if request.user.is_teacher and not request.user.teaching_professions.filter(pk=profession.pk).exists():
        messages.error(request, "Sizda bu kursga kirish huquqi yo'q!")
        return redirect('professions')
    
    # Faqat premium foydalanuvchilar, admin va o'qituvchilar kirishi mumkin
    if not request.user.is_admin and not request.user.is_teacher:
        if not request.user.is_premium:
            messages.warning(request, "Kursdoshlar bo'limi faqat Premium foydalanuvchilar uchun! 💎")
            return redirect('profession_detail', pk=pk)
        if not CourseEnrollment.objects.filter(user=request.user, profession=profession).exists():
            messages.error(request, "Avval kursga yoziling!")
            return redirect('profession_detail', pk=pk)
    
    # Kursdoshlar
    classmates = CustomUser.objects.filter(
        enrollments__profession=profession,
        role='student'
    ).exclude(pk=request.user.pk).order_by('-coins', 'first_name')
    
    return render(request, 'accounts/classmates.html', {
        'profession': profession,
        'classmates': classmates,
    })


@login_required
def student_public_profile(request, pk):
    """Boshqa o'quvchining umumiy profili"""
    student = get_object_or_404(CustomUser, pk=pk)
    
    # Faqat o'quvchilar ko'rinishi mumkin
    if student.role != 'student':
        messages.error(request, "Bu sahifa mavjud emas!")
        return redirect('home')
    
    # Umumiy kurslar
    user_profession_ids = request.user.enrollments.values_list('profession_id', flat=True)
    student_enrollments = CourseEnrollment.objects.filter(user=student).select_related('profession')
    
    common_courses = []
    for enrollment in student_enrollments:
        if enrollment.profession_id in user_profession_ids:
            common_courses.append(enrollment.profession)
    
    # Sertifikatlar
    certificates = Certificate.objects.filter(student=student).select_related('profession')
    
    # Tugallangan kurslar soni
    completed_count = certificates.count()
    
    # Deploy qilingan sahifalar
    deploys = HTMLDeploy.objects.filter(user=student, is_active=True).order_by('-created_at')
    
    # Barcha kurslar (yozilgan)
    all_enrollments = student_enrollments
    
    # Coin statistika
    total_earned_coins = CoinTransaction.objects.filter(user=student, action='add').aggregate(total=Sum('amount'))['total'] or 0
    total_spent_coins = CoinTransaction.objects.filter(user=student, action__in=['remove', 'purchase']).aggregate(total=Sum('amount'))['total'] or 0
    
    # Ball statistika
    test_results_qs = TestResult.first_attempts().filter(student=student)
    total_tests_taken = test_results_qs.count()
    avg_test_score = round(test_results_qs.aggregate(avg=Avg('score'))['avg'] or 0, 1)
    
    hw_submissions = HomeworkSubmission.objects.filter(student=student)
    total_homeworks_submitted = hw_submissions.count()
    avg_homework_grade = round(hw_submissions.filter(grade__isnull=False).aggregate(avg=Avg('grade'))['avg'] or 0, 1)
    
    return render(request, 'accounts/student_public_profile.html', {
        'student': student,
        'common_courses': common_courses,
        'certificates': certificates,
        'completed_count': completed_count,
        'deploys': deploys,
        'all_enrollments': all_enrollments,
        'total_earned_coins': total_earned_coins,
        'total_spent_coins': total_spent_coins,
        'total_tests_taken': total_tests_taken,
        'avg_test_score': avg_test_score,
        'total_homeworks_submitted': total_homeworks_submitted,
        'avg_homework_grade': avg_homework_grade,
    })


@login_required
def teacher_public_profile(request, pk):
    """O'qituvchining umumiy profili (o'quvchilar uchun)"""
    from teacher.models import TeacherCertificate
    teacher = get_object_or_404(CustomUser, pk=pk, role='teacher')
    courses = teacher.teaching_professions.all()
    certificates = TeacherCertificate.objects.filter(teacher=teacher, is_visible=True)

    return render(request, 'accounts/teacher_public_profile.html', {
        'teacher': teacher,
        'courses': courses,
        'certificates': certificates,
    })


@login_required
def profile_edit_view(request):
    if request.method == 'POST':
        form = UserProfileForm(request.POST, request.FILES, instance=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, "Profil muvaffaqiyatli yangilandi!")
            return redirect('profile')
    else:
        form = UserProfileForm(instance=request.user)
    
    return render(request, 'accounts/profile_edit.html', {'form': form})


@login_required
def change_password_view(request):
    if request.method == 'POST':
        form = ChangePasswordForm(request.POST)
        if form.is_valid():
            if not request.user.check_password(form.cleaned_data['old_password']):
                messages.error(request, "Joriy parol noto'g'ri!")
            else:
                request.user.set_password(form.cleaned_data['new_password1'])
                request.user.save()
                login(request, request.user)
                
                # Xavfsizlik xabari
                from .notifications import check_password_changed
                check_password_changed(request.user)
                
                messages.success(request, "Parol muvaffaqiyatli o'zgartirildi!")
                return redirect('profile')
    else:
        form = ChangePasswordForm()
    
    return render(request, 'accounts/change_password.html', {'form': form})


@login_required
def student_statistics(request, pk=None):
    if pk and (request.user.is_admin or request.user.is_teacher):
        student = get_object_or_404(CustomUser, pk=pk)
    else:
        student = request.user
    
    period = request.GET.get('period', 'all')
    now = timezone.now()
    
    if period == 'week':
        start_date = now - timedelta(days=7)
    elif period == 'month':
        start_date = now - timedelta(days=30)
    else:
        start_date = None
    
    # Videos watched
    videos_query = VideoProgress.objects.filter(user=student, watched=True)
    if start_date:
        videos_query = videos_query.filter(watched_at__gte=start_date)
    videos_watched = videos_query.count()
    
    # Test results
    tests_query = TestResult.first_attempts().filter(student=student)
    if start_date:
        tests_query = tests_query.filter(completed_at__gte=start_date)
    test_results = tests_query
    avg_score = tests_query.aggregate(avg=Avg('score'))['avg'] or 0
    
    # Homework submissions
    hw_query = HomeworkSubmission.objects.filter(student=student)
    if start_date:
        hw_query = hw_query.filter(submitted_at__gte=start_date)
    homework_count = hw_query.count()
    
    context = {
        'student': student,
        'period': period,
        'videos_watched': videos_watched,
        'test_results': test_results,
        'avg_score': round(avg_score, 1),
        'homework_count': homework_count,
        'coins': student.coins,
    }
    
    return render(request, 'accounts/student_statistics.html', context)


@login_required
def export_student_pdf(request, pk=None):
    if pk and (request.user.is_admin or request.user.is_teacher):
        student = get_object_or_404(CustomUser, pk=pk)
    else:
        student = request.user
    
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from io import BytesIO
    
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    elements = []
    styles = getSampleStyleSheet()
    
    elements.append(Paragraph(f"O'quvchi statistikasi: {student.full_name}", styles['Heading1']))
    elements.append(Paragraph(f"Sana: {timezone.now().strftime('%d.%m.%Y')}", styles['Normal']))
    elements.append(Spacer(1, 20))
    
    # General info
    info_data = [
        ['Ko\'rsatkich', 'Qiymat'],
        ['Jami coinlar', str(student.coins)],
        ['Ko\'rilgan videolar', str(VideoProgress.objects.filter(user=student, watched=True).count())],
        ['Test natijalari', str(TestResult.objects.filter(student=student).count())],
        ['Topshirilgan vazifalar', str(HomeworkSubmission.objects.filter(student=student).count())],
    ]
    
    table = Table(info_data, colWidths=[250, 150])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0d6efd')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#dee2e6')),
        ('PADDING', (0, 0), (-1, -1), 8),
    ]))
    elements.append(table)
    
    doc.build(elements)
    buffer.seek(0)
    
    response = HttpResponse(buffer, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="student_stats_{student.username}.pdf"'
    return response


@login_required
def export_system_pdf(request):
    if not request.user.is_admin:
        messages.error(request, "Bu sahifaga kirish huquqingiz yo'q!")
        return redirect('home')
    
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from io import BytesIO
    
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=30, bottomMargin=30)
    elements = []
    styles = getSampleStyleSheet()
    
    heading_style = ParagraphStyle(
        'CustomHeading',
        parent=styles['Heading2'],
        spaceAfter=10,
        spaceBefore=20,
        textColor=colors.HexColor('#0d6efd')
    )
    
    def create_table(data, col_widths=None):
        if col_widths is None:
            col_widths = [300, 150]
        table = Table(data, colWidths=col_widths)
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0d6efd')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#dee2e6')),
            ('PADDING', (0, 0), (-1, -1), 8),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('ALIGN', (1, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8f9fa')]),
        ]))
        return table
    
    elements.append(Paragraph("Tizim Statistikasi - To'liq Hisobot", styles['Title']))
    elements.append(Paragraph(f"Hisobot sanasi: {timezone.now().strftime('%d.%m.%Y %H:%M')}", styles['Normal']))
    elements.append(Spacer(1, 20))
    
    total_students = CustomUser.objects.filter(role='student').count()
    total_teachers = CustomUser.objects.filter(role='teacher').count()
    total_admins = CustomUser.objects.filter(role='admin').count()
    total_users = CustomUser.objects.count()
    
    elements.append(Paragraph("1. Foydalanuvchilar statistikasi", heading_style))
    user_data = [
        ["Ko'rsatkich", 'Soni'],
        ['Jami foydalanuvchilar', str(total_users)],
        ["O'quvchilar", str(total_students)],
        ["O'qituvchilar", str(total_teachers)],
        ['Adminlar', str(total_admins)],
    ]
    elements.append(create_table(user_data))
    elements.append(Spacer(1, 15))
    
    total_courses = Profession.objects.count()
    courses_with_students = Profession.objects.annotate(
        student_count=Count('enrollments')
    ).order_by('-student_count')
    
    elements.append(Paragraph("2. Kurslar va talabalar", heading_style))
    course_data = [['Kurs nomi', "O'quvchilar soni"]]
    for course in courses_with_students[:10]:
        course_data.append([course.name[:40], str(course.student_count)])
    if total_courses > 10:
        course_data.append(['...va yana', f'{total_courses - 10} ta kurs'])
    elements.append(create_table(course_data))
    elements.append(Spacer(1, 15))
    
    total_lessons = Lesson.objects.count()
    total_videos = VideoLesson.objects.count()
    total_tests = Test.objects.count()
    total_homeworks_created = Homework.objects.count()
    
    elements.append(Paragraph("3. Dars materiallari", heading_style))
    lesson_data = [
        ["Ko'rsatkich", 'Soni'],
        ['Jami darslar', str(total_lessons)],
        ['Videodarslar', str(total_videos)],
        ['Testlar', str(total_tests)],
        ['Uy vazifalari', str(total_homeworks_created)],
    ]
    elements.append(create_table(lesson_data))
    elements.append(Spacer(1, 15))
    
    total_test_results = TestResult.objects.count()
    passed_tests = TestResult.objects.filter(passed=True).count()
    failed_tests = total_test_results - passed_tests
    avg_score = TestResult.objects.aggregate(avg=Avg('score'))['avg'] or 0
    
    elements.append(Paragraph("4. Test natijalari", heading_style))
    test_data = [
        ["Ko'rsatkich", 'Qiymat'],
        ["Jami topshirilgan testlar", str(total_test_results)],
        ["Muvaffaqiyatli o'tganlar", str(passed_tests)],
        ["Muvaffaqiyatsiz", str(failed_tests)],
        ["O'rtacha ball", f"{avg_score:.1f}%"],
    ]
    elements.append(create_table(test_data))
    elements.append(Spacer(1, 15))
    
    total_submissions = HomeworkSubmission.objects.count()
    pending_homeworks = HomeworkSubmission.objects.filter(grade__isnull=True).count()
    graded_homeworks = HomeworkSubmission.objects.filter(grade__isnull=False).count()
    avg_grade = HomeworkSubmission.objects.filter(grade__isnull=False).aggregate(avg=Avg('grade'))['avg'] or 0
    
    elements.append(Paragraph("5. Uy vazifalari holati", heading_style))
    hw_data = [
        ["Ko'rsatkich", 'Qiymat'],
        ['Jami topshirilgan vazifalar', str(total_submissions)],
        ['Baholanmagan (kutilmoqda)', str(pending_homeworks)],
        ['Baholangan', str(graded_homeworks)],
        ["O'rtacha baho", f"{avg_grade:.1f}"],
    ]
    elements.append(create_table(hw_data))
    elements.append(Spacer(1, 15))
    
    total_coins = CustomUser.objects.aggregate(Sum('coins'))['coins__sum'] or 0
    total_transactions = CoinTransaction.objects.count()
    avg_coins_per_user = total_coins / total_users if total_users > 0 else 0
    
    elements.append(Paragraph("6. Coin statistikasi", heading_style))
    coin_data = [
        ["Ko'rsatkich", 'Qiymat'],
        ['Jami tarqatilgan coinlar', str(total_coins)],
        ['Coin tranzaksiyalari', str(total_transactions)],
        ["Har bir foydalanuvchiga o'rtacha", f"{avg_coins_per_user:.1f}"],
    ]
    elements.append(create_table(coin_data))
    elements.append(Spacer(1, 15))
    
    total_enrollments = CourseEnrollment.objects.count()
    
    elements.append(Paragraph("7. Kursga yozilish statistikasi", heading_style))
    enroll_data = [
        ["Ko'rsatkich", 'Soni'],
        ["Jami yozilishlar", str(total_enrollments)],
    ]
    elements.append(create_table(enroll_data))
    elements.append(Spacer(1, 15))
    
    elements.append(Paragraph("8. Oxirgi 7 kunlik registratsiya", heading_style))
    reg_data = [['Sana', "Yangi foydalanuvchilar"]]
    for i in range(6, -1, -1):
        day = timezone.now().date() - timedelta(days=i)
        count = CustomUser.objects.filter(
            date_joined__date=day
        ).count()
        reg_data.append([day.strftime('%d.%m.%Y'), str(count)])
    elements.append(create_table(reg_data))
    
    doc.build(elements)
    buffer.seek(0)
    
    response = HttpResponse(buffer, content_type='application/pdf')
    response['Content-Disposition'] = 'attachment; filename="system_statistics.pdf"'
    return response


@login_required
def leaderboard(request):
    tab = request.GET.get('tab', 'coins')
    profession_id = request.GET.get('profession')
    search_query = request.GET.get('q', '').strip()

    professions = Profession.objects.all()

    if tab == 'score':
        from accounts.models import HomeworkSubmission

        cache_key = f'leaderboard_score_{profession_id or "all"}_{search_query}'
        cached = cache.get(cache_key)
        if cached:
            cached['professions'] = professions
            # user rank hisoblash
            user_rank = None
            user_score = 0
            if request.user.role == 'student':
                for i, s in enumerate(cached.get('_scored_data', [])):
                    if s['id'] == request.user.pk:
                        user_rank = i + 1
                        user_score = s['score']
                        break
            cached['user_rank'] = user_rank
            cached['user_in_list'] = user_rank is not None
            cached['user_score'] = user_score
            return render(request, 'accounts/leaderboard.html', cached)

        students_qs = CustomUser.objects.filter(role='student')
        if profession_id:
            students_qs = students_qs.filter(enrollments__profession_id=profession_id).distinct()
        if search_query:
            students_qs = students_qs.filter(
                Q(first_name__icontains=search_query) |
                Q(last_name__icontains=search_query) |
                Q(username__icontains=search_query)
            )

        student_ids = list(students_qs.values_list('id', flat=True))

        # Uy vazifasi ballari bo'yicha score hisoblash
        hw_filter = Q(student_id__in=student_ids, status='graded', grade__isnull=False)
        if profession_id:
            hw_filter &= Q(homework__lesson__profession_id=profession_id)

        hw_scores = dict(
            HomeworkSubmission.objects.filter(hw_filter)
            .values('student_id')
            .annotate(total_grade=Sum('grade'))
            .values_list('student_id', 'total_grade')
        )

        scored_data = []
        for sid in student_ids:
            total_hw_score = hw_scores.get(sid, 0) or 0
            if total_hw_score > 0 or not search_query:
                scored_data.append({'id': sid, 'score': total_hw_score})

        scored_data.sort(key=lambda s: s['score'], reverse=True)

        top_ids = [s['id'] for s in scored_data[:100]]
        students_map = {s.pk: s for s in CustomUser.objects.filter(pk__in=top_ids)}
        students_list = []
        for s in scored_data[:100]:
            student = students_map.get(s['id'])
            if student:
                student.score = s['score']
                students_list.append(student)

        user_rank = None
        user_score = 0
        if request.user.role == 'student':
            for i, s in enumerate(scored_data):
                if s['id'] == request.user.pk:
                    user_rank = i + 1
                    user_score = s['score']
                    break

        result = {
            'students': students_list,
            'professions': professions,
            'selected_profession': profession_id,
            'search_query': search_query,
            'user_rank': user_rank,
            'user_in_list': user_rank is not None,
            'tab': tab,
            'user_score': user_score,
            '_scored_data': scored_data,
        }
        cache.set(cache_key, result, 120)
        return render(request, 'accounts/leaderboard.html', result)

    # Coins tab (default)
    students = CustomUser.objects.filter(role='student').order_by('-coins')

    if profession_id:
        students = students.filter(enrollments__profession_id=profession_id).distinct()

    if search_query:
        students = students.filter(
            Q(first_name__icontains=search_query) |
            Q(last_name__icontains=search_query) |
            Q(username__icontains=search_query)
        )

    user_rank = None
    user_in_list = False
    students_list = students[:100]
    if request.user.role == 'student':
        all_students_ids = list(students.values_list('pk', flat=True))
        if request.user.pk in all_students_ids:
            user_rank = all_students_ids.index(request.user.pk) + 1
            user_in_list = True
        else:
            all_ranked = CustomUser.objects.filter(role='student').order_by('-coins').values_list('pk', flat=True)
            all_ranked_list = list(all_ranked)
            if request.user.pk in all_ranked_list:
                user_rank = all_ranked_list.index(request.user.pk) + 1

    return render(request, 'accounts/leaderboard.html', {
        'students': students_list,
        'professions': professions,
        'selected_profession': profession_id,
        'search_query': search_query,
        'user_rank': user_rank,
        'user_in_list': user_in_list,
        'tab': tab,
    })


# Messages views
@login_required
def messages_view(request):
    # Shaxsiy xabarlar
    personal_messages = Message.objects.filter(recipient=request.user)
    
    # Umumiy xabarlar
    if request.user.is_student:
        general_messages = Message.objects.filter(
            Q(message_type='all') | Q(message_type='students'),
            recipient__isnull=True
        )
    elif request.user.is_teacher:
        general_messages = Message.objects.filter(
            Q(message_type='all') | Q(message_type='teachers'),
            recipient__isnull=True
        )
    else:
        general_messages = Message.objects.filter(message_type='all', recipient__isnull=True)
    
    all_messages = (personal_messages | general_messages).distinct().order_by('-created_at')
    
    # O'qilmagan xabarlar sonini yangilash
    unread_count = all_messages.filter(is_read=False).count()
    
    read_count = personal_messages.filter(is_read=True).count()
    total_count = all_messages.count()
    
    return render(request, 'accounts/messages.html', {
        'messages_list': all_messages,
        'unread_count': unread_count,
        'read_count': read_count,
        'total_count': total_count,
    })


@login_required
def message_detail(request, pk):
    message = get_object_or_404(Message, pk=pk)
    
    # Faqat o'ziga tegishli xabarlarni ko'rish
    if message.recipient and message.recipient != request.user:
        if not request.user.is_admin:
            messages.error(request, "Bu xabarga kirish huquqingiz yo'q!")
            return redirect('messages')
    
    # O'qilgan deb belgilash
    if not message.is_read and message.recipient == request.user:
        message.is_read = True
        message.save()
    
    return render(request, 'accounts/message_detail.html', {'message': message})


@login_required
def mark_message_read(request, pk):
    message = get_object_or_404(Message, pk=pk, recipient=request.user)
    message.is_read = True
    message.save()
    return JsonResponse({'success': True})


@login_required
def mark_all_messages_read(request):
    if request.method == 'POST':
        Message.objects.filter(recipient=request.user, is_read=False).update(is_read=True)
        general_q = Q(recipient__isnull=True, is_read=False)
        if request.user.is_student:
            general_q &= Q(message_type__in=['all', 'students'])
        elif request.user.is_teacher:
            general_q &= Q(message_type__in=['all', 'teachers'])
        else:
            general_q &= Q(message_type='all')
        Message.objects.filter(general_q).update(is_read=True)
    return redirect('messages')


@login_required
def delete_read_messages(request):
    if request.method == 'POST':
        mode = request.POST.get('mode', 'read')
        if mode == 'all':
            # Shaxsiy xabarlarni o'chirish
            personal_deleted = Message.objects.filter(recipient=request.user).delete()[0]
            # Umumiy xabarlarni ham o'chirish
            if request.user.is_student:
                general_q = Q(message_type__in=['all', 'students'], recipient__isnull=True)
            elif request.user.is_teacher:
                general_q = Q(message_type__in=['all', 'teachers'], recipient__isnull=True)
            else:
                general_q = Q(message_type='all', recipient__isnull=True)
            general_deleted = Message.objects.filter(general_q).delete()[0]
            total = personal_deleted + general_deleted
            messages.success(request, f"{total} ta xabar o'chirildi!")
        else:
            deleted_count = Message.objects.filter(recipient=request.user, is_read=True).delete()[0]
            messages.success(request, f"{deleted_count} ta o'qilgan xabar o'chirildi!")
    return redirect('messages')


# Admin: Send message
@login_required
def admin_send_message(request):
    if not request.user.is_admin:
        return redirect('home')
    
    if request.method == 'POST':
        title = request.POST.get('title')
        content = request.POST.get('content')
        message_type = request.POST.get('message_type')
        recipient_id = request.POST.get('recipient')
        
        if message_type == 'personal' and recipient_id:
            recipient = get_object_or_404(CustomUser, pk=recipient_id)
            Message.objects.create(
                title=title,
                content=content,
                message_type='personal',
                recipient=recipient,
                sender=request.user
            )
            notify_user(
                recipient.telegram_id,
                f"📩 <b>Yangi xabar!</b>\n\n"
                f"📌 {title}\n"
                f"💬 {content[:150]}"
            )
            messages.success(request, f"{recipient.full_name}ga xabar yuborildi!")
        else:
            # Umumiy xabar
            if message_type in ['students', 'teachers']:
                role = 'student' if message_type == 'students' else 'teacher'
                users = CustomUser.objects.filter(role=role)
                for user in users:
                    Message.objects.create(
                        title=title,
                        content=content,
                        message_type=message_type,
                        recipient=user,
                        sender=request.user
                    )
            else:
                # Barchaga
                users = CustomUser.objects.exclude(role='admin')
                for user in users:
                    Message.objects.create(
                        title=title,
                        content=content,
                        message_type='all',
                        recipient=user,
                        sender=request.user
                    )
            messages.success(request, "Xabar muvaffaqiyatli yuborildi!")
        
        return redirect('admin_messages')
    
    users = CustomUser.objects.exclude(role='admin')
    return render(request, 'accounts/admin/send_message.html', {'users': users})


@login_required
def admin_messages(request):
    if not request.user.is_admin:
        return redirect('home')
    
    all_messages = Message.objects.all().order_by('-created_at')
    paginator = Paginator(all_messages, 25)
    page = request.GET.get('page')
    all_messages = paginator.get_page(page)
    return render(request, 'accounts/admin/messages.html', {'messages_list': all_messages})

from django.core.paginator import Paginator

# Admin: Payment management
@login_required
def admin_payments(request):
    if not request.user.is_admin:
        return redirect('home')

    from datetime import date
    today = date.today()
    selected_month = int(request.GET.get('month', today.month))
    selected_year = int(request.GET.get('year', today.year))
    search_query = request.GET.get('q', '').strip()
    filter_status = request.GET.get('status', '')

    qs = CustomUser.objects.filter(role='student').select_related('payment_status')

    # Har bir studentga PaymentStatus yaratish
    existing_ids = set(PaymentStatus.objects.filter(user__role='student').values_list('user_id', flat=True))
    all_student_ids = set(qs.values_list('id', flat=True))
    missing = all_student_ids - existing_ids
    if missing:
        PaymentStatus.objects.bulk_create([
            PaymentStatus(user_id=uid) for uid in missing
        ], ignore_conflicts=True)
        qs = CustomUser.objects.filter(role='student').select_related('payment_status')

    # PaymentRecord yaratish (tanlangan oy uchun)
    existing_record_ids = set(
        PaymentRecord.objects.filter(month=selected_month, year=selected_year)
        .values_list('user_id', flat=True)
    )
    missing_records = all_student_ids - existing_record_ids
    if missing_records:
        fees = {ps.user_id: ps.monthly_fee for ps in PaymentStatus.objects.filter(user_id__in=missing_records)}
        PaymentRecord.objects.bulk_create([
            PaymentRecord(user_id=uid, month=selected_month, year=selected_year, amount=fees.get(uid, 200000))
            for uid in missing_records
        ], ignore_conflicts=True)

    # Search
    if search_query:
        qs = qs.filter(
            Q(first_name__icontains=search_query) |
            Q(last_name__icontains=search_query) |
            Q(username__icontains=search_query) |
            Q(phone__icontains=search_query)
        )

    # Records dict
    records = PaymentRecord.objects.filter(month=selected_month, year=selected_year).select_related('user')
    records_dict = {r.user_id: r for r in records}

    # Filter by status
    if filter_status == 'paid':
        qs = qs.filter(pk__in=[r.user_id for r in records if r.is_paid])
    elif filter_status == 'unpaid':
        qs = qs.filter(pk__in=[r.user_id for r in records if not r.is_paid])
    elif filter_status == 'blocked':
        qs = qs.filter(is_blocked=True)

    students_list = list(qs.order_by('first_name', 'last_name'))
    for s in students_list:
        s.current_record = records_dict.get(s.pk)

    paginator = Paginator(students_list, 30)
    students = paginator.get_page(request.GET.get('page'))

    # Stats
    all_records = PaymentRecord.objects.filter(month=selected_month, year=selected_year)
    total_students = CustomUser.objects.filter(role='student').count()
    total_expected = all_records.aggregate(t=Sum('amount'))['t'] or 0
    total_paid_sum = all_records.filter(is_paid=True).aggregate(t=Sum('paid_amount'))['t'] or 0
    total_paid_count = all_records.filter(is_paid=True).count()
    total_unpaid = all_records.filter(is_paid=False).count()
    blocked_count = CustomUser.objects.filter(role='student', is_blocked=True).count()
    total_debt = max(0, total_expected - total_paid_sum)

    # Oylik tarix (6 oy)
    MONTH_SHORT = {1:'Yan',2:'Fev',3:'Mar',4:'Apr',5:'May',6:'Iyn',7:'Iyl',8:'Avg',9:'Sen',10:'Okt',11:'Noy',12:'Dek'}
    monthly_history = []
    for i in range(5, -1, -1):
        m = selected_month - i
        y = selected_year
        while m <= 0:
            m += 12
            y -= 1
        mr = PaymentRecord.objects.filter(month=m, year=y)
        monthly_history.append({
            'month': m, 'year': y,
            'name': MONTH_SHORT.get(m, ''),
            'paid': mr.filter(is_paid=True).aggregate(s=Sum('paid_amount'))['s'] or 0,
            'expected': mr.aggregate(s=Sum('amount'))['s'] or 0,
            'paid_count': mr.filter(is_paid=True).count(),
            'total_count': mr.count(),
        })

    months = [(i, PaymentRecord.MONTH_NAMES[i]) for i in range(1, 13)]
    years = list(range(2024, today.year + 2))

    return render(request, 'accounts/admin/payments.html', {
        'students': students,
        'total_students': total_students,
        'total_expected': total_expected,
        'total_paid_sum': total_paid_sum,
        'total_paid_count': total_paid_count,
        'total_unpaid': total_unpaid,
        'blocked_count': blocked_count,
        'selected_month': selected_month,
        'selected_year': selected_year,
        'months': months,
        'years': years,
        'search_query': search_query,
        'filter_status': filter_status,
        'monthly_history': monthly_history,
        'total_debt': total_debt,
        'today': today,
    })


@login_required
def admin_mark_paid(request, pk):
    if not request.user.is_admin:
        return redirect('home')

    from datetime import date
    user = get_object_or_404(CustomUser, pk=pk)
    payment_status, _ = PaymentStatus.objects.get_or_create(user=user)

    month = int(request.POST.get('month', date.today().month))
    year = int(request.POST.get('year', date.today().year))
    paid_amount = request.POST.get('paid_amount', '')
    notes = request.POST.get('notes', '')

    record, _ = PaymentRecord.objects.get_or_create(
        user=user, month=month, year=year,
        defaults={'amount': payment_status.monthly_fee}
    )
    record.paid_amount = int(paid_amount) if paid_amount else record.amount
    record.is_paid = True
    record.paid_date = date.today()
    record.notes = notes
    record.recorded_by = request.user
    record.save()

    payment_status.is_paid = True
    payment_status.last_payment_date = date.today()
    payment_status.save()

    if user.is_blocked and payment_status.auto_blocked:
        user.is_blocked = False
        user.save()
        payment_status.auto_blocked = False
        payment_status.save()
        Message.objects.create(
            title="✅ Hisobingiz ochildi",
            content="To'lov qabul qilindi. Hisobingiz faollashtirildi.",
            message_type='system', recipient=user, sender=request.user
        )

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'success': True, 'name': user.full_name, 'paid_amount': record.paid_amount, 'debt': record.debt})
    messages.success(request, f"{user.full_name} to'lovi belgilandi!")
    return redirect(f'/dashboard/payments/?month={month}&year={year}')


@login_required
def admin_mark_unpaid(request, pk):
    if not request.user.is_admin:
        return redirect('home')

    from datetime import date
    user = get_object_or_404(CustomUser, pk=pk)
    month = int(request.POST.get('month', date.today().month))
    year = int(request.POST.get('year', date.today().year))

    record = PaymentRecord.objects.filter(user=user, month=month, year=year).first()
    if record:
        record.is_paid = False
        record.paid_amount = 0
        record.paid_date = None
        record.save()

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'success': True, 'name': user.full_name})
    messages.warning(request, f"{user.full_name} to'lovi bekor qilindi!")
    return redirect(f'/dashboard/payments/?month={month}&year={year}')


@login_required
def send_payment_reminder(request, pk):
    if not request.user.is_admin:
        return redirect('home')

    student = get_object_or_404(CustomUser, pk=pk, role='student')
    Message.objects.create(
        sender=request.user, recipient=student,
        title="💳 To'lov eslatmasi",
        content=f"Hurmatli {student.full_name},\n\nSizning oylik to'lovingiz muddati yaqinlashmoqda. Iltimos, o'z vaqtida to'lov qilishni unutmang.\n\nHurmat bilan,\nIT Creative jamoasi",
        message_type='payment'
    )
    notify_user(
        student.telegram_id,
        f"💳 <b>To'lov eslatmasi</b>\n\n"
        f"Hurmatli {student.full_name},\n\n"
        f"Sizning oylik to'lovingiz muddati yaqinlashmoqda.\n"
        f"Iltimos, o'z vaqtida to'lov qilishni unutmang.\n\n"
        f"🏫 IT Creative jamoasi"
    )
    notify_group(
        f"💳 <b>To'lov eslatmasi yuborildi</b>\n\n"
        f"👤 {student.full_name}ga to'lov eslatmasi yuborildi."
    )
    messages.success(request, f"{student.full_name}ga eslatma yuborildi!")
    month = request.GET.get('month', '')
    year = request.GET.get('year', '')
    return redirect(f'/dashboard/payments/?month={month}&year={year}' if month else 'admin_payments')


@login_required
def send_bulk_payment_reminders(request):
    if not request.user.is_admin:
        return redirect('home')

    if request.method == 'POST':
        from datetime import date
        today = date.today()
        m = int(request.POST.get('month', today.month))
        y = int(request.POST.get('year', today.year))
        unpaid_ids = PaymentRecord.objects.filter(
            month=m, year=y, is_paid=False
        ).values_list('user_id', flat=True)
        unpaid_students = CustomUser.objects.filter(pk__in=unpaid_ids, role='student')

        count = 0
        for student in unpaid_students:
            Message.objects.create(
                sender=request.user, recipient=student,
                title="💳 To'lov eslatmasi",
                content=f"Hurmatli {student.full_name},\n\nSizning oylik to'lovingiz muddati yaqinlashmoqda. Iltimos, o'z vaqtida to'lov qilishni unutmang.\n\nHurmat bilan,\nIT Creative jamoasi",
                message_type='payment'
            )
            notify_user(
                student.telegram_id,
                f"💳 <b>To'lov eslatmasi</b>\n\n"
                f"Hurmatli {student.full_name},\n\n"
                f"Sizning oylik to'lovingiz muddati yaqinlashmoqda.\n"
                f"Iltimos, o'z vaqtida to'lov qilishni unutmang.\n\n"
                f"🏫 IT Creative jamoasi"
            )
            count += 1

        notify_group(
            f"💳 <b>Ommaviy to'lov eslatmasi</b>\n\n"
            f"📊 {count} ta o'quvchiga to'lov eslatmasi yuborildi."
        )
        messages.success(request, f"{count} ta o'quvchiga eslatma yuborildi!")

    return redirect(f'/dashboard/payments/?month={m}&year={y}')


@login_required
def admin_toggle_block_payment(request, pk):
    if not request.user.is_admin:
        return redirect('home')

    user = get_object_or_404(CustomUser, pk=pk, role='student')
    payment_status, _ = PaymentStatus.objects.get_or_create(user=user)

    if user.is_blocked:
        user.is_blocked = False
        user.save()
        payment_status.auto_blocked = False
        payment_status.save()
        Message.objects.create(
            title="✅ Hisobingiz ochildi",
            content="Admin hisobingizni ochdi. O'qishingizni davom eting!",
            message_type='system', recipient=user, sender=request.user
        )
        if user.telegram_id:
            notify_user(
                user.telegram_id,
                f"✅ <b>Hisobingiz blokdan chiqarildi!</b>\n\n"
                f"👤 {user.full_name}\n\n"
                f"🎉 Hisobingiz ochildi. O'qishingizni davom eting!"
            )
        messages.success(request, f"{user.full_name} blokdan ochildi!")
    else:
        user.is_blocked = True
        user.save()
        payment_status.auto_blocked = True
        payment_status.save()
        Message.objects.create(
            title="🚫 Hisobingiz bloklandi",
            content="To'lov qilinmaganligi sababli hisobingiz vaqtincha bloklandi.",
            message_type='payment', recipient=user, sender=request.user
        )
        if user.telegram_id:
            notify_user(
                user.telegram_id,
                f"🚫 <b>Hisobingiz bloklandi!</b>\n\n"
                f"👤 {user.full_name}\n\n"
                f"❌ To'lov qilinmaganligi sababli hisobingiz vaqtincha bloklandi.\n"
                f"💳 To'lovni amalga oshiring yoki adminstratsiya bilan bog'laning."
            )
        messages.warning(request, f"{user.full_name} bloklandi!")

    month = request.GET.get('month', '')
    year = request.GET.get('year', '')
    return redirect(f'/dashboard/payments/?month={month}&year={year}' if month else 'admin_payments')


@login_required
def bulk_payment_action(request):
    if not request.user.is_admin:
        return redirect('home')

    if request.method == 'POST':
        from datetime import date
        today = date.today()
        ids_str = request.POST.get('selected_ids', '')
        action = request.POST.get('action', '')
        month = request.POST.get('month', str(today.month))
        year = request.POST.get('year', str(today.year))

        if not ids_str:
            messages.warning(request, "Hech qanday o'quvchi tanlanmadi!")
            return redirect(f'/dashboard/payments/?month={month}&year={year}')

        student_ids = [int(x) for x in ids_str.split(',') if x.strip().isdigit()]
        students = CustomUser.objects.filter(pk__in=student_ids, role='student')

        if action == 'block':
            count = 0
            for student in students:
                if not student.is_blocked:
                    student.is_blocked = True
                    student.save()
                    ps, _ = PaymentStatus.objects.get_or_create(user=student)
                    ps.auto_blocked = True
                    ps.save()
                    Message.objects.create(
                        title="🚫 Hisobingiz bloklandi",
                        content="To'lov qilinmaganligi sababli hisobingiz vaqtincha bloklandi.",
                        message_type='payment', recipient=student, sender=request.user
                    )
                    count += 1
            messages.warning(request, f"{count} ta o'quvchi bloklandi!")

        elif action == 'unblock':
            count = 0
            for student in students:
                if student.is_blocked:
                    student.is_blocked = False
                    student.save()
                    ps, _ = PaymentStatus.objects.get_or_create(user=student)
                    ps.auto_blocked = False
                    ps.save()
                    Message.objects.create(
                        title="✅ Hisobingiz ochildi",
                        content="Admin hisobingizni ochdi. O'qishingizni davom eting!",
                        message_type='system', recipient=student, sender=request.user
                    )
                    count += 1
            messages.success(request, f"{count} ta o'quvchi blokdan ochildi!")

        elif action == 'set_fee':
            fee = int(request.POST.get('monthly_fee', 200000))
            count = 0
            for student in students:
                ps, _ = PaymentStatus.objects.get_or_create(user=student)
                ps.monthly_fee = fee
                ps.save()
                PaymentRecord.objects.filter(
                    user=student, month=int(month), year=int(year), is_paid=False
                ).update(amount=fee)
                count += 1
            messages.success(request, f"{count} ta o'quvchiga {fee:,} so'm oylik belgilandi!")

        elif action == 'remind':
            count = 0
            for student in students:
                Message.objects.create(
                    sender=request.user, recipient=student,
                    title="💳 To'lov eslatmasi",
                    content=f"Hurmatli {student.full_name},\n\nSizning oylik to'lovingiz muddati yaqinlashmoqda. Iltimos, o'z vaqtida to'lov qilishni unutmang.\n\nHurmat bilan,\nIT Creative jamoasi",
                    message_type='payment'
                )
                count += 1
            messages.success(request, f"{count} ta o'quvchiga eslatma yuborildi!")

        return redirect(f'/dashboard/payments/?month={month}&year={year}')

    return redirect('admin_payments')


@login_required
def admin_set_monthly_fee(request, pk):
    if not request.user.is_admin:
        return redirect('home')

    user = get_object_or_404(CustomUser, pk=pk, role='student')
    payment_status, _ = PaymentStatus.objects.get_or_create(user=user)

    if request.method == 'POST':
        fee = request.POST.get('monthly_fee', 200000)
        payment_status.monthly_fee = int(fee)
        payment_status.save()

        month = request.GET.get('month', '')
        year = request.GET.get('year', '')
        if month and year:
            PaymentRecord.objects.filter(
                user=user, month=int(month), year=int(year), is_paid=False
            ).update(amount=int(fee))

        messages.success(request, f"{user.full_name} oylik to'lovi {int(fee):,} so'm qilib belgilandi!")
        return redirect(f'/dashboard/payments/?month={month}&year={year}' if month else 'admin_payments')

    month = request.GET.get('month', '')
    year = request.GET.get('year', '')
    return redirect(f'/dashboard/payments/?month={month}&year={year}' if month else 'admin_payments')


@login_required
def admin_payment_history(request, pk):
    if not request.user.is_admin:
        return redirect('home')

    user = get_object_or_404(CustomUser, pk=pk, role='student')
    records = PaymentRecord.objects.filter(user=user).order_by('-year', '-month')
    payment_status, _ = PaymentStatus.objects.get_or_create(user=user)

    total_expected = records.aggregate(t=Sum('amount'))['t'] or 0
    total_paid = records.filter(is_paid=True).aggregate(t=Sum('paid_amount'))['t'] or 0

    return render(request, 'accounts/admin/payment_history.html', {
        'student': user,
        'records': records,
        'payment_status': payment_status,
        'total_expected': total_expected,
        'total_paid': total_paid,
        'total_debt': max(0, total_expected - total_paid),
    })


@login_required
def export_payments_pdf(request):
    if not request.user.is_admin:
        return redirect('home')

    from datetime import date
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.units import mm
    from io import BytesIO

    today = date.today()
    selected_month = int(request.GET.get('month', today.month))
    selected_year = int(request.GET.get('year', today.year))

    MONTH_NAMES = {
        1: 'Yanvar', 2: 'Fevral', 3: 'Mart', 4: 'Aprel',
        5: 'May', 6: 'Iyun', 7: 'Iyul', 8: 'Avgust',
        9: 'Sentyabr', 10: 'Oktyabr', 11: 'Noyabr', 12: 'Dekabr'
    }
    month_name = MONTH_NAMES.get(selected_month, '')

    records = PaymentRecord.objects.filter(
        month=selected_month, year=selected_year
    ).select_related('user', 'user__payment_status')

    total_expected = sum(r.amount for r in records)
    total_paid = sum(r.paid_amount for r in records if r.is_paid)
    total_debt = total_expected - total_paid

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4), topMargin=20, bottomMargin=20, leftMargin=20, rightMargin=20)
    elements = []
    styles = getSampleStyleSheet()

    heading = ParagraphStyle('PH', parent=styles['Heading2'], textColor=colors.HexColor('#0d6efd'), spaceAfter=6)

    elements.append(Paragraph(f"To'lovlar hisoboti — {month_name} {selected_year}", styles['Title']))
    elements.append(Paragraph(f"Hisobot sanasi: {today.strftime('%d.%m.%Y')}", styles['Normal']))
    elements.append(Spacer(1, 12))

    # Summary table
    elements.append(Paragraph("Umumiy ma'lumot", heading))
    summary_data = [
        ["Ko'rsatkich", 'Qiymat'],
        ['Jami o\'quvchilar', str(records.count())],
        ['To\'langan', str(records.filter(is_paid=True).count())],
        ['To\'lanmagan', str(records.filter(is_paid=False).count())],
        ['Kutilgan summa', f"{total_expected:,.0f} so'm"],
        ['Yig\'ilgan summa', f"{total_paid:,.0f} so'm"],
        ['Jami qarz', f"{total_debt:,.0f} so'm"],
    ]
    t = Table(summary_data, colWidths=[200, 180])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0d6efd')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#dee2e6')),
        ('PADDING', (0, 0), (-1, -1), 8),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8f9fa')]),
    ]))
    elements.append(t)
    elements.append(Spacer(1, 16))

    # Detail table
    elements.append(Paragraph("Batafsil to'lov jadvali", heading))
    detail_data = [['#', 'Ism Familiya', 'Telefon', 'Oylik to\'lov', 'To\'langan', 'Qarz', 'Holat', 'Sana', 'Izoh']]
    col_widths = [25, 130, 90, 80, 80, 80, 70, 70, 120]

    for i, r in enumerate(records.order_by('user__first_name', 'user__last_name'), 1):
        detail_data.append([
            str(i),
            r.user.full_name,
            r.user.phone or '',
            f"{r.amount:,.0f}",
            f"{r.paid_amount:,.0f}" if r.is_paid else '0',
            f"{max(0, r.amount - r.paid_amount):,.0f}" if not r.is_paid else '0',
            'To\'langan' if r.is_paid else 'To\'lanmagan',
            r.paid_date.strftime('%d.%m.%Y') if r.paid_date else '-',
            (r.notes or '')[:30],
        ])

    dt = Table(detail_data, colWidths=col_widths)
    dt.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0d6efd')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#dee2e6')),
        ('PADDING', (0, 0), (-1, -1), 6),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('FONTSIZE', (0, 0), (-1, 0), 9),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8f9fa')]),
        ('ALIGN', (0, 0), (0, -1), 'CENTER'),
        ('ALIGN', (3, 0), (5, -1), 'RIGHT'),
        ('ALIGN', (6, 0), (6, -1), 'CENTER'),
    ]))

    # Color paid/unpaid rows
    for i, r in enumerate(records.order_by('user__first_name', 'user__last_name'), 1):
        if r.is_paid:
            dt.setStyle(TableStyle([('BACKGROUND', (6, i), (6, i), colors.HexColor('#d1e7dd'))]))
        else:
            dt.setStyle(TableStyle([('BACKGROUND', (6, i), (6, i), colors.HexColor('#f8d7da'))]))

    elements.append(dt)
    doc.build(elements)
    buffer.seek(0)

    response = HttpResponse(buffer, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="tolovlar_{month_name}_{selected_year}.pdf"'
    return response


# Teacher/Admin: Manage lessons
@login_required
def manage_lessons(request, pk):
    if not (request.user.is_admin or request.user.is_teacher):
        messages.error(request, "Sizda bu sahifaga kirish huquqi yo'q!")
        return redirect('home')
    
    profession = get_object_or_404(Profession, pk=pk)
    
    if request.user.is_teacher and not request.user.teaching_professions.filter(pk=profession.pk).exists():
        messages.error(request, "Sizda bu kursga kirish huquqi yo'q!")
        return redirect('professions')
    sections = profession.sections.all().prefetch_related('lessons')
    lessons_without_section = profession.lessons.filter(section__isnull=True)
    
    return render(request, 'accounts/manage/lessons.html', {
        'profession': profession,
        'sections': sections,
        'lessons_without_section': lessons_without_section,
    })


@login_required
def add_lesson(request, pk):
    if not (request.user.is_admin or request.user.is_teacher):
        return redirect('home')
    
    profession = get_object_or_404(Profession, pk=pk)
    
    if request.user.is_teacher and not request.user.teaching_professions.filter(pk=profession.pk).exists():
        messages.error(request, "Sizda bu kursga kirish huquqi yo'q!")
        return redirect('professions')
    lesson_type = request.GET.get('type', 'video')
    section_id = request.GET.get('section')
    section = None
    
    if section_id:
        section = get_object_or_404(Section, pk=section_id, profession=profession)
    
    if request.method == 'POST':
        section_id_post = request.POST.get('section')
        if section_id_post:
            section = get_object_or_404(Section, pk=section_id_post, profession=profession)
        
        if lesson_type == 'video':
            form = VideoLessonForm(request.POST)
            if form.is_valid():
                lesson = Lesson.objects.create(
                    profession=profession,
                    section=section,
                    title=form.cleaned_data['title'],
                    lesson_type='video',
                    created_by=request.user
                )
                vimeo_url = form.cleaned_data.get('vimeo_url') or ''
                youtube_url = form.cleaned_data.get('youtube_url') or ''
                VideoLesson.objects.create(
                    lesson=lesson,
                    video_url=vimeo_url or None,
                    youtube_url=youtube_url or None,
                    duration=form.cleaned_data.get('duration') or 0
                )
                # AI maqola yaratish
                ai_article = _generate_ai_article(lesson.title, profession.name)
                if ai_article:
                    lesson.ai_article = ai_article
                    lesson.save(update_fields=['ai_article'])
                # Xabar yuborish
                send_course_notification(
                    profession=profession,
                    title=f"🎬 Yangi video dars: {lesson.title}",
                    content=f"'{profession.name}' kursiga yangi video dars qo'shildi:\n\n📚 {lesson.title}\n\nDarsni ko'rish uchun kursga kiring!",
                    sender=request.user
                )
                messages.success(request, "Video darslik qo'shildi!")
                return redirect('profession_detail', pk=pk)
        
        elif lesson_type == 'homework':
            form = HomeworkForm(request.POST)
            if form.is_valid():
                lesson = Lesson.objects.create(
                    profession=profession,
                    section=section,
                    title=form.cleaned_data['title'],
                    lesson_type='homework',
                    created_by=request.user
                )
                Homework.objects.create(
                    lesson=lesson,
                    description=form.cleaned_data['description'],
                    ai_check=form.cleaned_data.get('ai_check', False),
                    handwritten_only=form.cleaned_data.get('handwritten_only', False),
                )
                # Xabar yuborish
                send_course_notification(
                    profession=profession,
                    title=f"📝 Yangi uyga vazifa: {lesson.title}",
                    content=f"'{profession.name}' kursiga yangi uyga vazifa qo'shildi:\n\n📚 {lesson.title}\n\nVazifani bajarish uchun kursga kiring!",
                    sender=request.user
                )
                messages.success(request, "Uyga vazifa qo'shildi!")
                return redirect('profession_detail', pk=pk)
        
        elif lesson_type == 'test':
            form = TestForm(request.POST)
            if form.is_valid():
                lesson = Lesson.objects.create(
                    profession=profession,
                    section=section,
                    title=form.cleaned_data['title'],
                    lesson_type='test',
                    created_by=request.user
                )
                Test.objects.create(
                    lesson=lesson,
                    test_type=form.cleaned_data['test_type'],
                    time_limit=form.cleaned_data['time_limit'],
                    passing_score=form.cleaned_data['passing_score'],
                    allow_retry=form.cleaned_data.get('allow_retry', False),
                    shuffle_questions=form.cleaned_data.get('shuffle_questions', False),
                    shuffle_answers=form.cleaned_data.get('shuffle_answers', False),
                    question_count=form.cleaned_data.get('question_count') or 0,
                )
                # Xabar yuborish
                send_course_notification(
                    profession=profession,
                    title=f"📋 Yangi test: {lesson.title}",
                    content=f"'{profession.name}' kursiga yangi test qo'shildi:\n\n📚 {lesson.title}\n\nTestni yechish uchun kursga kiring!",
                    sender=request.user
                )
                messages.success(request, "Test qo'shildi! Endi savollarni qo'shing.")
                return redirect('manage_test_questions', pk=lesson.test.pk)
        
        elif lesson_type == 'dictionary':
            form = DictionaryForm(request.POST)
            if form.is_valid():
                lesson = Lesson.objects.create(
                    profession=profession,
                    section=section,
                    title=form.cleaned_data['title'],
                    lesson_type='dictionary',
                    created_by=request.user
                )
                Dictionary.objects.create(
                    lesson=lesson,
                    description=form.cleaned_data.get('description') or ''
                )
                send_course_notification(
                    profession=profession,
                    title=f"📖 Yangi lug'at: {lesson.title}",
                    content=f"'{profession.name}' kursiga yangi lug'at qo'shildi:\n\n📚 {lesson.title}\n\nLug'atni ko'rish uchun kursga kiring!",
                    sender=request.user
                )
                messages.success(request, "Lug'at qo'shildi! Endi so'zlarni qo'shing.")
                return redirect('manage_dictionary', pk=lesson.dictionary.pk)
        
        elif lesson_type == 'speaking':
            title = request.POST.get('title', '').strip()
            description = request.POST.get('description', '').strip()
            target_level = request.POST.get('target_level', 'beginner')
            max_duration = request.POST.get('max_duration', 120)
            max_score = request.POST.get('max_score', 10)
            ai_check = request.POST.get('ai_check') == 'on'
            criteria = request.POST.get('criteria', '').strip()
            due_date = request.POST.get('due_date')
            
            if not title:
                messages.error(request, "Vazifa nomini kiriting.")
                return redirect(request.get_full_path())
            if not description:
                messages.error(request, "Vazifa tavsifini kiriting.")
                return redirect(request.get_full_path())
            
            try:
                max_duration = int(max_duration)
                max_score = int(max_score)
            except (ValueError, TypeError):
                max_duration = 120
                max_score = 10
            
            lesson = Lesson.objects.create(
                profession=profession,
                section=section,
                title=title,
                lesson_type='speaking',
                created_by=request.user,
            )
            
            from accounts.models import SpeakingTask
            SpeakingTask.objects.create(
                lesson=lesson,
                description=description,
                target_level=target_level,
                max_duration=max_duration,
                max_score=max_score,
                ai_check=ai_check,
                criteria=criteria if criteria else None,
                due_date=due_date if due_date else None,
            )
            
            send_course_notification(
                profession=profession,
                title=f"🎤 Yangi Speaking vazifa: {title}",
                content=f"'{profession.name}' kursiga yangi Speaking vazifa qo'shildi:\n\n🎤 {title}\n\nVazifani bajarish uchun kursga kiring!",
                sender=request.user
            )
            messages.success(request, f"'{title}' speaking vazifasi yaratildi!")
            return redirect('profession_detail', pk=pk)
    else:
        if lesson_type == 'video':
            form = VideoLessonForm()
        elif lesson_type == 'homework':
            form = HomeworkForm()
        elif lesson_type == 'dictionary':
            form = DictionaryForm()
        elif lesson_type == 'speaking':
            form = None
        else:
            form = TestForm()
    
    sections = profession.sections.filter(is_active=True)
    
    return render(request, 'accounts/manage/add_lesson.html', {
        'profession': profession,
        'lesson_type': lesson_type,
        'form': form,
        'section': section,
        'sections': sections,
    })


@login_required
def edit_lesson(request, pk):
    if not (request.user.is_admin or request.user.is_teacher):
        return redirect('home')
    
    lesson = get_object_or_404(Lesson, pk=pk)
    
    if request.user.is_teacher and not request.user.teaching_professions.filter(pk=lesson.profession.pk).exists():
        messages.error(request, "Sizda bu kursga kirish huquqi yo'q!")
        return redirect('professions')
    
    if request.method == 'POST':
        if lesson.lesson_type == 'video':
            form = VideoLessonForm(request.POST)
            if form.is_valid():
                lesson.title = form.cleaned_data['title']
                lesson.ai_article = request.POST.get('ai_article', '').strip() or None
                lesson.save(update_fields=['title', 'ai_article'])
                lesson.video.video_url = form.cleaned_data.get('vimeo_url') or None
                lesson.video.youtube_url = form.cleaned_data.get('youtube_url') or None
                lesson.video.duration = form.cleaned_data.get('duration') or 0
                lesson.video.save()
                # Xabar yuborish
                send_course_notification(
                    profession=lesson.profession,
                    title=f"🔄 Video dars yangilandi: {lesson.title}",
                    content=f"'{lesson.profession.name}' kursidagi video dars yangilandi:\n\n📚 {lesson.title}\n\nYangilangan darsni ko'rish uchun kursga kiring!",
                    sender=request.user
                )
                messages.success(request, "Dars yangilandi!")
                return redirect('manage_lessons', pk=lesson.profession.pk)
        elif lesson.lesson_type == 'homework':
            form = HomeworkForm(request.POST)
            if form.is_valid():
                lesson.title = form.cleaned_data['title']
                lesson.save()
                lesson.homework.description = form.cleaned_data['description']
                lesson.homework.ai_check = form.cleaned_data.get('ai_check', False)
                lesson.homework.handwritten_only = form.cleaned_data.get('handwritten_only', False)
                lesson.homework.save()
                # Xabar yuborish
                send_course_notification(
                    profession=lesson.profession,
                    title=f"🔄 Uyga vazifa yangilandi: {lesson.title}",
                    content=f"'{lesson.profession.name}' kursidagi uyga vazifa yangilandi:\n\n📚 {lesson.title}\n\nVazifani ko'rish uchun kursga kiring!",
                    sender=request.user
                )
                messages.success(request, "Vazifa yangilandi!")
                return redirect('manage_lessons', pk=lesson.profession.pk)
    else:
        if lesson.lesson_type == 'video':
            form = VideoLessonForm(initial={
                'title': lesson.title,
                'vimeo_url': lesson.video.video_url or '',
                'youtube_url': lesson.video.youtube_url or '',
                'duration': lesson.video.duration,
            })
        elif lesson.lesson_type == 'homework':
            form = HomeworkForm(initial={
                'title': lesson.title,
                'description': lesson.homework.description,
                'ai_check': lesson.homework.ai_check,
                'handwritten_only': lesson.homework.handwritten_only,
            })
        elif lesson.lesson_type == 'dictionary':
            if hasattr(lesson, 'dictionary') and lesson.dictionary:
                return redirect('manage_dictionary', pk=lesson.dictionary.pk)
            else:
                return redirect('manage_lessons', pk=lesson.profession.pk)
        else:
            if hasattr(lesson, 'test') and lesson.test:
                return redirect('manage_test_questions', pk=lesson.test.pk)
            else:
                return redirect('manage_lessons', pk=lesson.profession.pk)
    
    return render(request, 'accounts/manage/edit_lesson.html', {
        'lesson': lesson,
        'form': form,
    })


@login_required
def delete_lesson(request, pk):
    if not (request.user.is_admin or request.user.is_teacher):
        return redirect('home')
    
    lesson = get_object_or_404(Lesson, pk=pk)
    
    if request.user.is_teacher and not request.user.teaching_professions.filter(pk=lesson.profession.pk).exists():
        messages.error(request, "Sizda bu kursga kirish huquqi yo'q!")
        return redirect('professions')
    profession = lesson.profession
    profession_pk = profession.pk
    lesson_title = lesson.title
    lesson_type = lesson.lesson_type
    
    if request.method == 'POST':
        # Xabar yuborish
        type_names = {'video': 'Video dars', 'homework': 'Uyga vazifa', 'test': 'Test', 'dictionary': "Lug'at"}
        type_name = type_names.get(lesson_type, 'Dars')
        send_course_notification(
            profession=profession,
            title=f"🗑️ {type_name} o'chirildi",
            content=f"'{profession.name}' kursidan quyidagi dars o'chirildi:\n\n📚 {lesson_title}\n\nBu dars endi mavjud emas.",
            sender=request.user
        )
        lesson.delete()
        messages.success(request, "Dars o'chirildi!")
        return redirect('manage_lessons', pk=profession_pk)
    
    return render(request, 'accounts/manage/delete_lesson.html', {'lesson': lesson})


# Test management
@login_required
def manage_test_questions(request, pk):
    if not (request.user.is_admin or request.user.is_teacher):
        return redirect('home')
    
    test = get_object_or_404(Test, pk=pk)
    questions = test.questions.all()
    
    return render(request, 'accounts/manage/test_questions.html', {
        'test': test,
        'questions': questions,
    })


@login_required
def add_test_question(request, pk):
    if not (request.user.is_admin or request.user.is_teacher):
        return redirect('home')
    
    test = get_object_or_404(Test, pk=pk)
    
    if request.method == 'POST':
        form = TestQuestionForm(request.POST, request.FILES)
        if form.is_valid():
            question = TestQuestion.objects.create(
                test=test,
                question_text=form.cleaned_data['question_text'],
                question_image=form.cleaned_data.get('question_image')
            )
            
            answers = [
                form.cleaned_data['answer1'],
                form.cleaned_data['answer2'],
                form.cleaned_data['answer3'],
            ]
            correct = int(form.cleaned_data['correct_answer'])
            
            for i, answer_text in enumerate(answers, 1):
                TestAnswer.objects.create(
                    question=question,
                    answer_text=answer_text,
                    is_correct=(i == correct)
                )
            
            messages.success(request, "Savol qo'shildi!")
            
            if 'add_another' in request.POST:
                return redirect('add_test_question', pk=pk)
            return redirect('manage_test_questions', pk=pk)
    else:
        form = TestQuestionForm()
    
    return render(request, 'accounts/manage/add_question.html', {
        'test': test,
        'form': form,
    })


@login_required
def delete_test_question(request, pk):
    if not (request.user.is_admin or request.user.is_teacher):
        return redirect('home')
    
    question = get_object_or_404(TestQuestion, pk=pk)
    test_pk = question.test.pk
    
    if request.method == 'POST':
        question.delete()
        messages.success(request, "Savol o'chirildi!")
    
    return redirect('manage_test_questions', pk=test_pk)


@login_required
def import_test_questions(request, pk):
    if not (request.user.is_admin or request.user.is_teacher):
        return redirect('home')

    test = get_object_or_404(Test, pk=pk)
    errors = []
    success_count = 0

    if request.method == 'POST':
        file = request.FILES.get('excel_file')

        if not file:
            errors.append("Fayl tanlanmadi.")
        elif not file.name.endswith('.xlsx'):
            errors.append("Faqat .xlsx formatdagi fayllar qabul qilinadi.")
        else:
            try:
                import openpyxl
            except ImportError:
                errors.append("openpyxl kutubxonasi o'rnatilmagan. pip install openpyxl")

            if not errors:
                try:
                    wb = openpyxl.load_workbook(file, read_only=True)
                    ws = wb.active

                    headers = [str(cell.value or '').strip().lower() for cell in next(ws.iter_rows(min_row=1, max_row=1))]

                    required_cols = {
                        'savol': None,
                        'a': None,
                        'b': None,
                        'c': None,
                        "to'g'ri javob": None,
                    }
                    explanation_col = None

                    for i, h in enumerate(headers):
                        if h in ('savol', 'question_text', 'question', 'savol matni'):
                            required_cols['savol'] = i
                        elif h in ('a', 'option_a', 'variant_a', 'javob_a', '1-javob'):
                            required_cols['a'] = i
                        elif h in ('b', 'option_b', 'variant_b', 'javob_b', '2-javob'):
                            required_cols['b'] = i
                        elif h in ('c', 'option_c', 'variant_c', 'javob_c', '3-javob'):
                            required_cols['c'] = i
                        elif h in ("to'g'ri javob", 'correct_option', 'correct', 'javob', "to'g'ri"):
                            required_cols["to'g'ri javob"] = i
                        elif h in ('izoh', 'explanation', 'tushuntirish'):
                            explanation_col = i

                    missing = [k for k, v in required_cols.items() if v is None]
                    if missing:
                        errors.append(f"Excel faylda quyidagi ustunlar topilmadi: {', '.join(missing)}")
                        errors.append(f"Topilgan ustunlar: {', '.join(headers)}")

                    if not errors:
                        questions_data = []

                        for row_num, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
                            row = list(row)
                            max_col = max(v for v in required_cols.values() if v is not None)
                            if explanation_col is not None:
                                max_col = max(max_col, explanation_col)
                            if len(row) <= max_col:
                                row.extend([None] * (max_col - len(row) + 1))

                            q_text = str(row[required_cols['savol']] or '').strip()
                            opt_a = str(row[required_cols['a']] or '').strip()
                            opt_b = str(row[required_cols['b']] or '').strip()
                            opt_c = str(row[required_cols['c']] or '').strip()
                            correct = str(row[required_cols["to'g'ri javob"]] or '').strip().upper()

                            explanation = ''
                            if explanation_col is not None:
                                explanation = str(row[explanation_col] or '').strip()

                            if not q_text and not opt_a and not opt_b and not opt_c and not correct:
                                continue

                            row_errors = []

                            if not q_text:
                                row_errors.append("savol bo'sh")
                            if not opt_a:
                                row_errors.append("A varianti bo'sh")
                            if not opt_b:
                                row_errors.append("B varianti bo'sh")
                            if not opt_c:
                                row_errors.append("C varianti bo'sh")
                            if correct not in ('A', 'B', 'C'):
                                row_errors.append(f"to'g'ri javob '{correct}' noto'g'ri (faqat A/B/C)")

                            if row_errors:
                                errors.append(f"Qator {row_num}: {', '.join(row_errors)}")
                            else:
                                questions_data.append({
                                    'question_text': q_text,
                                    'option_a': opt_a,
                                    'option_b': opt_b,
                                    'option_c': opt_c,
                                    'correct': correct,
                                    'explanation': explanation,
                                })

                        if not questions_data and not errors:
                            errors.append("Excelda hech qanday savol topilmadi.")

                        if not errors:
                            existing_texts = set(
                                test.questions.values_list('question_text', flat=True)
                            )
                            seen_texts = set()
                            unique_data = []
                            skipped = 0
                            for qd in questions_data:
                                qt = qd['question_text']
                                if qt in existing_texts or qt in seen_texts:
                                    skipped += 1
                                    continue
                                seen_texts.add(qt)
                                unique_data.append(qd)

                            with transaction.atomic():
                                existing_count = test.questions.count()
                                for i, qd in enumerate(unique_data):
                                    question = TestQuestion.objects.create(
                                        test=test,
                                        question_text=qd['question_text'],
                                        explanation=qd.get('explanation', ''),
                                        order=existing_count + i + 1,
                                    )
                                    options = [
                                        ('A', qd['option_a']),
                                        ('B', qd['option_b']),
                                        ('C', qd['option_c']),
                                    ]
                                    for letter, text in options:
                                        TestAnswer.objects.create(
                                            question=question,
                                            answer_text=text,
                                            is_correct=(letter == qd['correct']),
                                        )
                                success_count = len(unique_data)
                            msg = f"{success_count} ta savol muvaffaqiyatli import qilindi!"
                            if skipped:
                                msg += f" ({skipped} ta takroriy savol o'tkazib yuborildi)"
                            messages.success(request, msg)
                            return redirect('manage_test_questions', pk=test.pk)

                    wb.close()
                except Exception as e:
                    errors.append(f"Faylni o'qishda xatolik: {str(e)}")

    return render(request, 'accounts/manage/import_questions.html', {
        'test': test,
        'errors': errors,
        'success_count': success_count,
    })


@login_required
def manage_dictionary(request, pk):
    if not (request.user.is_admin or request.user.is_teacher):
        return redirect('home')
    dictionary = get_object_or_404(Dictionary, pk=pk)
    words = dictionary.words.all()
    return render(request, 'accounts/manage/manage_dictionary.html', {
        'dictionary': dictionary,
        'words': words,
    })


@login_required
def add_dictionary_word(request, pk):
    if not (request.user.is_admin or request.user.is_teacher):
        return redirect('home')
    dictionary = get_object_or_404(Dictionary, pk=pk)
    if request.method == 'POST':
        term = request.POST.get('term', '').strip()
        translation = request.POST.get('translation', '').strip()
        example = request.POST.get('example', '').strip()
        if term and translation:
            max_order = dictionary.words.count()
            DictionaryWord.objects.create(
                dictionary=dictionary,
                term=term,
                translation=translation,
                example=example or None,
                order=max_order + 1,
            )
            messages.success(request, f"'{term}' so'zi qo'shildi!")
        else:
            messages.error(request, "So'z va tarjimani kiriting!")
    return redirect('manage_dictionary', pk=pk)


@login_required
def delete_dictionary_word(request, pk):
    if not (request.user.is_admin or request.user.is_teacher):
        return redirect('home')
    word = get_object_or_404(DictionaryWord, pk=pk)
    dict_pk = word.dictionary.pk
    if request.method == 'POST':
        word.delete()
        messages.success(request, "So'z o'chirildi!")
    return redirect('manage_dictionary', pk=dict_pk)


@login_required
def import_dictionary_words(request, pk):
    if not (request.user.is_admin or request.user.is_teacher):
        return redirect('home')
    dictionary = get_object_or_404(Dictionary, pk=pk)
    errors = []
    success_count = 0

    if request.method == 'POST':
        file = request.FILES.get('excel_file')
        if not file:
            errors.append("Fayl tanlanmadi.")
        elif not file.name.endswith('.xlsx'):
            errors.append("Faqat .xlsx formatdagi fayllar qabul qilinadi.")
        else:
            try:
                import openpyxl
            except ImportError:
                errors.append("openpyxl kutubxonasi o'rnatilmagan.")

            if not errors:
                try:
                    wb = openpyxl.load_workbook(file, read_only=True)
                    ws = wb.active
                    headers = [str(cell.value or '').strip().lower() for cell in next(ws.iter_rows(min_row=1, max_row=1))]

                    term_col = None
                    translation_col = None
                    example_col = None

                    for i, h in enumerate(headers):
                        if h in ("so'z", 'soz', 'term', 'atama', 'word', "so'z / atama", 'yozilishi'):
                            term_col = i
                        elif h in ('tarjima', 'translation', "ma'no", "ma'nosi", "tarjima / ma'nosi", 'tarjimasi'):
                            translation_col = i
                        elif h in ('misol', 'example', 'namuna', 'gap'):
                            example_col = i

                    if term_col is None:
                        errors.append("'So'z' ustuni topilmadi. Ustun nomi: so'z, term, atama, word")
                    if translation_col is None:
                        errors.append("'Tarjima' ustuni topilmadi. Ustun nomi: tarjima, translation, ma'no")
                    if errors:
                        errors.append(f"Topilgan ustunlar: {', '.join(headers)}")

                    if not errors:
                        words_data = []
                        max_col = max(c for c in [term_col, translation_col, example_col] if c is not None)
                        for row_num, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
                            row = list(row)
                            if len(row) <= max_col:
                                row.extend([None] * (max_col - len(row) + 1))

                            term = str(row[term_col] or '').strip()
                            translation = str(row[translation_col] or '').strip()
                            example = ''
                            if example_col is not None:
                                example = str(row[example_col] or '').strip()

                            if not term and not translation:
                                continue

                            if not term:
                                errors.append(f"Qator {row_num}: so'z bo'sh")
                            elif not translation:
                                errors.append(f"Qator {row_num}: tarjima bo'sh")
                            else:
                                words_data.append({
                                    'term': term,
                                    'translation': translation,
                                    'example': example,
                                })

                        if not words_data and not errors:
                            errors.append("Excelda hech qanday so'z topilmadi.")

                        if not errors:
                            with transaction.atomic():
                                existing_count = dictionary.words.count()
                                for i, wd in enumerate(words_data):
                                    DictionaryWord.objects.create(
                                        dictionary=dictionary,
                                        term=wd['term'],
                                        translation=wd['translation'],
                                        example=wd['example'] or None,
                                        order=existing_count + i + 1,
                                    )
                                success_count = len(words_data)
                            messages.success(request, f"{success_count} ta so'z muvaffaqiyatli import qilindi!")
                            return redirect('manage_dictionary', pk=dictionary.pk)

                    wb.close()
                except Exception as e:
                    errors.append(f"Faylni o'qishda xatolik: {str(e)}")

    return render(request, 'accounts/manage/import_dictionary.html', {
        'dictionary': dictionary,
        'errors': errors,
        'success_count': success_count,
    })


@login_required
def ai_generate_dictionary(request, pk):
    if not (request.user.is_admin or request.user.is_teacher):
        return redirect('home')

    dictionary = get_object_or_404(Dictionary, pk=pk)

    if request.method != 'POST':
        messages.error(request, "Noto'g'ri so'rov turi.")
        return redirect('manage_dictionary', pk=dictionary.pk)

    language = request.POST.get('language', '').strip()
    level = request.POST.get('level', '').strip()
    try:
        count = int(request.POST.get('count', 10))
    except (ValueError, TypeError):
        count = 10
    count = min(count, 50)

    if not language or not level:
        messages.error(request, "Til va daraja ko'rsatilishi shart.")
        return redirect('manage_dictionary', pk=dictionary.pk)

    from django.conf import settings
    api_key = getattr(settings, 'OPENAI_API_KEY', None)
    if not api_key or not api_key.strip():
        messages.error(request, "AI xizmati sozlanmagan (OPENAI_API_KEY topilmadi)")
        return redirect('manage_dictionary', pk=dictionary.pk)

    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key.strip(), timeout=120)
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Siz tajribali til o'qituvchisisiz. "
                        "Faqat JSON array formatida javob bering, boshqa hech qanday matn qo'shmang. "
                        "Har bir element quyidagi formatda bo'lsin:\n"
                        '{"term": "maqsad tildagi so\'z", '
                        '"translation": "O\'zbek tilidagi tarjimasi", '
                        '"example": "Maqsad tildagi misol gap | O\'zbek tilidagi tarjimasi"}'
                    ),
                },
                {
                    "role": "user",
                    "content": f"{language} tilidan {level} darajada {count} ta so'z yarat.",
                },
            ],
            max_tokens=4000,
            temperature=0.7,
        )
        ai_text = response.choices[0].message.content.strip()

        if ai_text.startswith('```'):
            lines = ai_text.split('\n')
            lines = [l for l in lines if not l.strip().startswith('```')]
            ai_text = '\n'.join(lines)

        words_data = json.loads(ai_text)

        if not isinstance(words_data, list):
            messages.error(request, "AI noto'g'ri formatda javob qaytardi.")
            return redirect('manage_dictionary', pk=dictionary.pk)

        with transaction.atomic():
            existing_count = dictionary.words.count()
            for i, wd in enumerate(words_data):
                DictionaryWord.objects.create(
                    dictionary=dictionary,
                    term=wd.get('term', ''),
                    translation=wd.get('translation', ''),
                    example=wd.get('example', '') or None,
                    order=existing_count + i + 1,
                )

        messages.success(request, f"AI yordamida {len(words_data)} ta so'z muvaffaqiyatli yaratildi!")
    except json.JSONDecodeError:
        messages.error(request, "AI javobini o'qishda xatolik yuz berdi. Qaytadan urinib ko'ring.")
    except Exception as e:
        messages.error(request, f"AI so'z yaratishda xatolik: {str(e)}")

    return redirect('manage_dictionary', pk=dictionary.pk)


# Homework submissions for teachers
@login_required
def homework_submissions(request):
    if not (request.user.is_admin or request.user.is_teacher):
        return redirect('home')
    
    search_query = request.GET.get('q', '').strip()
    status_filter = request.GET.get('status', '')
    profession_filter = request.GET.get('profession', '')
    sort_by = request.GET.get('sort', '')
    
    submissions = HomeworkSubmission.objects.select_related(
        'homework__lesson__profession', 'student'
    ).prefetch_related('messages')
    
    # O'qituvchi faqat o'z kurslaridagi vazifalarni ko'rsin
    if request.user.is_teacher and not request.user.is_admin:
        teaching_ids = request.user.teaching_professions.values_list('pk', flat=True)
        submissions = submissions.filter(homework__lesson__profession_id__in=teaching_ids)
    
    if search_query:
        from django.db.models import Q
        submissions = submissions.filter(
            Q(student__first_name__icontains=search_query) |
            Q(student__last_name__icontains=search_query) |
            Q(student__username__icontains=search_query) |
            Q(homework__lesson__title__icontains=search_query)
        )
    
    if status_filter == 'ai_checked':
        submissions = submissions.exclude(ai_feedback__isnull=True).exclude(ai_feedback='')
    elif status_filter:
        submissions = submissions.filter(status=status_filter)
    else:
        submissions = submissions.exclude(status='graded')
    
    if profession_filter:
        submissions = submissions.filter(homework__lesson__profession_id=profession_filter)
    
    if sort_by == 'oldest':
        submissions = submissions.order_by('submitted_at')
    elif sort_by == 'name':
        submissions = submissions.order_by('student__first_name', 'student__last_name')
    else:
        submissions = submissions.order_by('-submitted_at')
    
    total_count = submissions.count()
    
    paginator = Paginator(submissions, 25)
    page = request.GET.get('page')
    submissions = paginator.get_page(page)
    
    # O'qituvchi uchun faqat o'z kurslari bo'yicha statistika
    if request.user.is_teacher and not request.user.is_admin:
        hw_qs = HomeworkSubmission.objects.filter(homework__lesson__profession_id__in=teaching_ids)
        stats = {
            'pending': hw_qs.filter(status='pending').count(),
            'reviewing': hw_qs.filter(status='reviewing').count(),
            'revision': hw_qs.filter(status='revision').count(),
            'accepted': hw_qs.filter(status='accepted').count(),
            'graded': hw_qs.filter(status='graded').count(),
            'ai_checked': hw_qs.exclude(ai_feedback__isnull=True).exclude(ai_feedback='').count(),
        }
        professions = Profession.objects.filter(pk__in=teaching_ids)
    else:
        stats = {
            'pending': HomeworkSubmission.objects.filter(status='pending').count(),
            'reviewing': HomeworkSubmission.objects.filter(status='reviewing').count(),
            'revision': HomeworkSubmission.objects.filter(status='revision').count(),
            'accepted': HomeworkSubmission.objects.filter(status='accepted').count(),
            'graded': HomeworkSubmission.objects.filter(status='graded').count(),
            'ai_checked': HomeworkSubmission.objects.exclude(ai_feedback__isnull=True).exclude(ai_feedback='').count(),
        }
        professions = Profession.objects.all()
    
    # Kurslar bo'yicha vazifalar sonini hisoblash
    # Faqat uyga vazifasi bor kurslarni ko'rsatish
    if not professions.exists():
        profession_ids = HomeworkSubmission.objects.values_list(
            'homework__lesson__profession_id', flat=True
        ).distinct()
        professions = Profession.objects.filter(pk__in=profession_ids)
    
    profession_stats = []
    for prof in professions:
        base_qs = HomeworkSubmission.objects.filter(homework__lesson__profession=prof)
        p_pending = base_qs.filter(status='pending').count()
        p_total = base_qs.exclude(status='graded').count()
        profession_stats.append({
            'profession': prof,
            'total': p_total,
            'pending': p_pending,
        })
    
    return render(request, 'accounts/manage/homework_submissions.html', {
        'submissions': submissions,
        'stats': stats,
        'professions': professions,
        'profession_stats': profession_stats,
        'search_query': search_query,
        'status_filter': status_filter,
        'profession_filter': profession_filter,
        'sort_by': sort_by,
        'total_count': total_count,
    })


@login_required
def grade_homework(request, pk):
    if not (request.user.is_admin or request.user.is_teacher):
        return redirect('home')
    
    submission = get_object_or_404(HomeworkSubmission, pk=pk)
    
    if request.user.is_teacher and not request.user.teaching_professions.filter(pk=submission.homework.lesson.profession.pk).exists():
        messages.error(request, "Sizda bu kursga kirish huquqi yo'q!")
        return redirect('professions')
    was_graded = submission.grade is not None
    chat_messages = submission.messages.all().order_by('created_at')
    revisions = submission.revisions.all()
    
    # Xabarlarni o'qilgan deb belgilash
    submission.messages.filter(is_read=False).exclude(sender=request.user).update(is_read=True)
    
    if request.method == 'POST':
        action = request.POST.get('action')
        
        # Xabar yuborish
        if action == 'send_message':
            message_text = request.POST.get('message', '').strip()
            message_file = request.FILES.get('message_file')
            if message_text or message_file:
                from .models import HomeworkMessage
                HomeworkMessage.objects.create(
                    submission=submission,
                    sender=request.user,
                    message=message_text,
                    file=message_file
                )
                messages.success(request, "Xabar yuborildi!")
            return redirect('grade_homework', pk=pk)
        
        # Status o'zgartirish
        elif action == 'set_reviewing':
            submission.status = 'reviewing'
            submission.save()
            messages.info(request, "Status: Ko'rib chiqilmoqda")
            return redirect('grade_homework', pk=pk)
        
        # Qayta ishlashga yuborish
        elif action == 'request_revision':
            revision_note = request.POST.get('revision_note', '')
            submission.status = 'revision'
            submission.feedback = revision_note
            submission.save()
            
            # Xabar qoldirish
            from .models import HomeworkMessage
            HomeworkMessage.objects.create(
                submission=submission,
                sender=request.user,
                message=f"⚠️ Qayta ishlash kerak: {revision_note}"
            )
            
            # Notification
            Message.objects.create(
                title="Vazifani qayta ishlang",
                content=f"'{submission.homework.lesson.title}' vazifangizni qayta ishlashingiz kerak.\n\nIzoh: {revision_note}",
                message_type='warning',
                recipient=submission.student
            )
            
            notify_user(
                submission.student.telegram_id,
                f"⚠️ <b>Vazifangiz qayta ishlash kerak!</b>\n\n"
                f"📚 {submission.homework.lesson.profession.name}\n"
                f"📖 {submission.homework.lesson.title}\n"
                f"💬 Izoh: {revision_note}\n\n"
                f"📝 Iltimos, tuzatib qayta yuboring!"
            )
            notify_group(
                f"🔄 <b>Uy vazifasi qaytarildi!</b>\n\n"
                f"👤 O'quvchi: {submission.student.first_name} {submission.student.last_name}\n"
                f"📚 Kurs: {submission.homework.lesson.profession.name}\n"
                f"📖 Dars: {submission.homework.lesson.title}\n"
                f"💬 Sabab: {revision_note}\n\n"
                f"👨‍🏫 Qaytardi: {request.user.first_name} {request.user.last_name}"
            )
            notify_admins(
                f"🔄 <b>Uy vazifasi qaytarildi!</b>\n\n"
                f"👤 {submission.student.first_name} {submission.student.last_name}\n"
                f"📚 {submission.homework.lesson.profession.name} → {submission.homework.lesson.title}\n"
                f"💬 {revision_note}\n"
                f"👨‍🏫 {request.user.first_name} {request.user.last_name}"
            )
            messages.warning(request, "O'quvchiga qayta ishlash so'rovi yuborildi!")
            return redirect('grade_homework', pk=pk)
        
        # Qabul qilish
        elif action == 'accept':
            submission.status = 'accepted'
            submission.save()
            messages.success(request, "Vazifa qabul qilindi!")
            return redirect('grade_homework', pk=pk)
        
        # Avtomatik baholash (qabul + 5 ball)
        elif action == 'auto_grade':
            import random
            auto_feedbacks = [
                "Barakalla! Juda yaxshi ishlagan ekansiz! 👏",
                "Juda ajoyib! Davom eting! 🌟",
                "Zo'r natija! Sizdan mamnunmiz! 💪",
                "Hammasi joyida! Yaxshi ish! ✨",
                "A'lo darajada bajarilgan! Rahmat! 🎯",
                "Ajoyib! Mehnatlaringiz uchun rahmat! 🏆",
                "Juda chiroyli ishlangansiz! Davom eting! 🚀",
                "Yaxshi qilgansiz! Buni ko'rib xursand bo'ldim! 😊",
                "Super! Sizning sa'y-harakatlaringiz ko'rinib turibdi! 💫",
                "Zo'r! Ishingiz hammaga o'rnak bo'ladi! 🎉",
            ]
            submission.status = 'graded'
            submission.grade = 5
            submission.feedback = random.choice(auto_feedbacks)
            submission.graded_by = request.user
            submission.graded_at = timezone.now()
            submission.save()
            
            if not submission.coin_awarded:
                coin_amount = 5
                if not submission.is_late:
                    coin_amount = 10
                if submission.student.is_premium:
                    coin_amount *= 2
                submission.student.add_coins(coin_amount, f"Vazifa baholandi: {submission.homework.lesson.title}")
                submission.coin_awarded = True
                submission.save()
                
                ActivityLog.objects.create(
                    user=submission.student,
                    action_type='homework_graded',
                    description=f"Vazifa avtomatik baholandi: {submission.homework.lesson.title} - Baho: 5, +{coin_amount} coin"
                )
            
            from .notifications import on_homework_graded
            on_homework_graded(submission.student, submission, 5)
            _notify_homework_graded(request.user, submission, 5)
            
            messages.success(request, "Vazifa avtomatik baholandi: 5 ball!")
            return redirect('homework_submissions')
        
        # AI bilan baholash
        elif action == 'ai_grade':
            student_answer = _read_submission_content(submission)
            if not student_answer:
                messages.error(request, "AI bu fayl formatini tekshira olmaydi (faqat matn va kod fayllari).")
                return redirect('grade_homework', pk=pk)
            
            ai_result = _get_ai_grade(submission.homework.description, student_answer)
            if not ai_result:
                messages.error(request, "AI bilan bog'lanishda xatolik yuz berdi. Qayta urinib ko'ring.")
                return redirect('grade_homework', pk=pk)
            
            submission.grade = ai_result['grade']
            submission.feedback = f"🤖 AI xulosasi:\n{ai_result['feedback']}"
            submission.status = ai_result['status']
            submission.graded_by = request.user
            submission.graded_at = timezone.now()
            submission.save()
            
            if ai_result['status'] == 'graded' and not submission.coin_awarded:
                coin_amount = 5
                if not submission.is_late:
                    coin_amount = 10
                if submission.grade >= 9:
                    coin_amount += 5
                elif submission.grade >= 8:
                    coin_amount += 3
                if submission.student.is_premium:
                    coin_amount *= 2
                submission.student.add_coins(coin_amount, f"Vazifa baholandi: {submission.homework.lesson.title}")
                submission.coin_awarded = True
                submission.save()
                ActivityLog.objects.create(
                    user=submission.student,
                    action_type='homework_graded',
                    description=f"Vazifa AI baholadi: {submission.homework.lesson.title} - Baho: {submission.grade}, +{coin_amount} coin"
                )
            
            if ai_result['status'] == 'graded':
                _notify_ai_graded(submission, ai_result)
                messages.success(request, f"AI baholadi: {submission.grade} ball!")
                return redirect('homework_submissions')
            else:
                Message.objects.create(
                    title="Vazifani qayta ishlang",
                    content=f"'{submission.homework.lesson.title}' vazifangizni qayta ishlashingiz kerak.\n\nAI izohi: {ai_result['feedback']}",
                    message_type='warning',
                    recipient=submission.student
                )
                _notify_ai_revision(submission, ai_result)
                messages.warning(request, f"AI xulosasi: qayta ishlash kerak ({submission.grade} ball)")
                return redirect('grade_homework', pk=pk)
        
        # Baholash
        elif action == 'grade':
            grade = request.POST.get('grade')
            feedback = request.POST.get('feedback', '')
            feedback_file = request.FILES.get('feedback_file')
            
            if grade:
                submission.grade = min(int(grade), 10)
                submission.feedback = feedback
                if feedback_file:
                    submission.feedback_file = feedback_file
                submission.status = 'graded'
                submission.graded_by = request.user
                submission.graded_at = timezone.now()
                submission.save()
                
                # Coin berish
                if not submission.coin_awarded:
                    # Vaqtida topshirganlar uchun bonus
                    coin_amount = 5
                    if not submission.is_late:
                        coin_amount = 10
                    
                    # Yaxshi baho uchun bonus
                    if submission.grade >= 9:
                        coin_amount += 5
                    elif submission.grade >= 8:
                        coin_amount += 3
                    
                    # Premium 2x bonus
                    if submission.student.is_premium:
                        coin_amount *= 2
                    
                    submission.student.add_coins(coin_amount, f"Vazifa baholandi: {submission.homework.lesson.title}")
                    submission.coin_awarded = True
                    submission.save()
                    
                    ActivityLog.objects.create(
                        user=submission.student,
                        action_type='homework_graded',
                        description=f"Vazifa baholandi: {submission.homework.lesson.title} - Baho: {submission.grade}, +{coin_amount} coin"
                    )
                
                # Notification
                from .notifications import on_homework_graded
                on_homework_graded(submission.student, submission, submission.grade)
                _notify_homework_graded(request.user, submission, submission.grade)
                notify_user(
                    submission.student.telegram_id,
                    f"✅ <b>Vazifangiz baholandi!</b>\n\n"
                    f"📚 {submission.homework.lesson.profession.name}\n"
                    f"📖 {submission.homework.lesson.title}\n"
                    f"🏆 Baho: <b>{submission.grade}/10</b>\n"
                    f"👨‍🏫 Baholadi: {request.user.first_name} {request.user.last_name}\n\n"
                    f"{'💬 <b>Izoh:</b>' + chr(10) + feedback if feedback else ''}"
                )
                
                messages.success(request, f"Vazifa baholandi: {submission.grade} ball!")
                return redirect('homework_submissions')
    
    return render(request, 'accounts/manage/grade_homework.html', {
        'submission': submission,
        'chat_messages': chat_messages,
        'revisions': revisions,
    })


@login_required
def homework_chat(request, pk):
    """O'quvchi uchun vazifa chat sahifasi"""
    submission = get_object_or_404(HomeworkSubmission, pk=pk, student=request.user)
    chat_messages = submission.messages.all().order_by('created_at')
    revisions = submission.revisions.all()
    
    # Xabarlarni o'qilgan deb belgilash
    submission.messages.filter(is_read=False).exclude(sender=request.user).update(is_read=True)
    
    if request.method == 'POST':
        action = request.POST.get('action')
        
        # Xabar yuborish
        if action == 'send_message':
            message_text = request.POST.get('message', '').strip()
            message_file = request.FILES.get('message_file')
            if message_text or message_file:
                from .models import HomeworkMessage
                HomeworkMessage.objects.create(
                    submission=submission,
                    sender=request.user,
                    message=message_text,
                    file=message_file
                )
                messages.success(request, "Xabar yuborildi!")
            return redirect('homework_chat', pk=pk)
        
        # Qayta topshirish
        elif action == 'resubmit':
            new_file = request.FILES.get('new_file')
            new_text = request.POST.get('new_text_content', '').strip()
            note = request.POST.get('note', '')
            
            has_new_content = new_file or new_text
            
            if has_new_content:
                # Qayta topshirish uchun coin yechish
                resubmit_cost = 3 if request.user.is_premium else 5
                request.user.remove_coins(resubmit_cost, f"Uyga vazifa qayta topshirish: {submission.homework.lesson.title}")
                
                from .models import HomeworkRevision
                # Eski faylni revision sifatida saqlash (agar fayl mavjud bo'lsa)
                if submission.file:
                    HomeworkRevision.objects.create(
                        submission=submission,
                        file=submission.file,
                        note=f"Versiya {submission.version}"
                    )
                
                # Yangi kontentni yuklash
                if new_file:
                    submission.file = new_file
                    submission.submission_type = 'file'
                elif new_text:
                    submission.text_content = new_text
                    submission.submission_type = 'text'
                
                submission.version += 1
                submission.revision_count += 1
                submission.status = 'pending'
                submission.submitted_at = timezone.now()
                submission.save()
                
                # Xabar qoldirish
                from .models import HomeworkMessage
                msg_text = f"📎 Qayta ishlangan versiya yuklandi (v{submission.version})."
                if note:
                    msg_text += f" {note}"
                HomeworkMessage.objects.create(
                    submission=submission,
                    sender=request.user,
                    message=msg_text
                )
                
                # O'qituvchi va adminlarga xabar yuborish (Telegram + sayt)
                hw = submission.homework
                profession = hw.lesson.profession
                student = request.user
                
                # Sayt xabari — adminlarga
                notify_admins(
                    f"🔄 <b>Vazifa qayta topshirildi!</b>\n\n"
                    f"👤 {student.first_name} {student.last_name}\n"
                    f"📚 {profession.name} / {hw.lesson.title}\n"
                    f"📎 Versiya: v{submission.version}\n"
                    f"{'💬 Izoh: ' + note[:150] if note else ''}"
                )
                
                # Kurs o'qituvchilariga xabar
                course_teachers = profession.teachers.filter(
                    telegram_id__isnull=False
                )
                for teacher in course_teachers:
                    notify_user(
                        teacher.telegram_id,
                        f"🔄 <b>Vazifa qayta topshirildi!</b>\n\n"
                        f"👤 O'quvchi: {student.first_name} {student.last_name}\n"
                        f"📚 Kurs: {profession.name}\n"
                        f"📖 Dars: {hw.lesson.title}\n"
                        f"📎 Versiya: v{submission.version}\n"
                        f"{'💬 Izoh: ' + note[:150] if note else ''}\n\n"
                        f"👨‍🏫 Tekshirishni kutmoqda!"
                    )
                
                # Saytda xabar yaratish (o'qituvchilar va adminlar ko'rishi uchun)
                Message.objects.create(
                    recipient=None,
                    title=f"🔄 Vazifa qayta topshirildi: {hw.lesson.title}",
                    content=(
                        f"{student.first_name} {student.last_name} '{profession.name}' kursining "
                        f"'{hw.lesson.title}' darsiga vazifani qayta topshirdi (v{submission.version}). "
                        f"Tekshirishni kutmoqda."
                    ),
                    message_type='all'
                )
                
                messages.success(request, "Vazifa qayta topshirildi!")
            else:
                messages.error(request, "Fayl yoki matn kiriting!")
            return redirect('homework_chat', pk=pk)
    
    resubmit_cost = 3 if request.user.is_premium else 5
    return render(request, 'accounts/homework_chat.html', {
        'submission': submission,
        'chat_messages': chat_messages,
        'revisions': revisions,
        'resubmit_cost': resubmit_cost,
    })


@login_required
def my_test_results(request):
    """O'quvchining barcha test natijalari (bugungi + barchasi, paginator bilan)"""
    from django.core.paginator import Paginator
    from datetime import date

    today = date.today()
    all_results = TestResult.objects.filter(
        student=request.user
    ).select_related('test__lesson__profession').order_by('-completed_at')

    today_results = all_results.filter(completed_at__date=today)

    stats = {
        'total': all_results.count(),
        'today': today_results.count(),
        'passed': all_results.filter(passed=True).count(),
        'failed': all_results.filter(passed=False).count(),
        'avg_score': all_results.aggregate(avg=Avg('score'))['avg'] or 0,
    }

    paginator = Paginator(all_results, 15)
    page = request.GET.get('page')
    results_page = paginator.get_page(page)

    return render(request, 'accounts/my_test_results.html', {
        'today_results': today_results,
        'results': results_page,
        'stats': stats,
    })


@login_required
def my_homework_list(request):
    """O'quvchining barcha vazifalari"""
    submissions = HomeworkSubmission.objects.filter(student=request.user).select_related(
        'homework__lesson__profession'
    ).prefetch_related('messages').order_by('-submitted_at')
    
    # Statistika
    stats = {
        'total': submissions.count(),
        'pending': submissions.filter(status__in=['pending', 'reviewing']).count(),
        'revision': submissions.filter(status='revision').count(),
        'graded': submissions.filter(status='graded').count(),
        'avg_grade': submissions.filter(grade__isnull=False).aggregate(avg=Avg('grade'))['avg'] or 0,
    }
    
    return render(request, 'accounts/my_homeworks.html', {
        'submissions': submissions,
        'stats': stats,
    })


@login_required
def admin_test_analytics(request):
    if not (request.user.is_admin or request.user.is_teacher):
        return redirect('home')
    
    from django.db.models import Count, Avg, Q, F
    
    professions = Profession.objects.prefetch_related(
        'lessons__test__results', 'lessons__test__questions'
    ).all()
    
    # Umumiy statistika
    total_tests = Test.objects.count()
    total_attempts = TestResult.first_attempts().count()
    total_passed = TestResult.first_attempts().filter(passed=True).count()
    avg_score = TestResult.first_attempts().aggregate(avg=Avg('score'))['avg'] or 0
    pass_rate = round((total_passed / total_attempts * 100) if total_attempts > 0 else 0, 1)
    
    # Bugun ishlangan testlar
    from datetime import date
    today = date.today()
    today_results = TestResult.objects.filter(
        completed_at__date=today
    ).select_related('test__lesson__profession', 'student').order_by('-completed_at')
    
    # Oxirgi natijalar (paginator bilan)
    from django.core.paginator import Paginator
    all_recent = TestResult.objects.select_related(
        'test__lesson__profession', 'student'
    ).order_by('-completed_at')
    paginator = Paginator(all_recent, 20)
    page = request.GET.get('page')
    recent_results = paginator.get_page(page)
    
    # Kurs tanlanganda
    selected_profession_id = request.GET.get('profession')
    selected_test_id = request.GET.get('test')
    selected_profession = None
    profession_tests = []
    selected_test = None
    test_results = []
    test_stats = {}
    
    if selected_profession_id:
        try:
            selected_profession = Profession.objects.get(pk=selected_profession_id)
            first_attempt_ids = TestResult.first_attempts().values_list('id', flat=True)
            profession_tests = Test.objects.filter(
                lesson__profession=selected_profession
            ).select_related('lesson').annotate(
                attempt_count=Count('results', filter=Q(results__id__in=first_attempt_ids)),
                pass_count=Count('results', filter=Q(results__passed=True, results__id__in=first_attempt_ids)),
                avg_score=Avg('results__score', filter=Q(results__id__in=first_attempt_ids))
            )
        except Profession.DoesNotExist:
            pass
    
    if selected_test_id:
        try:
            selected_test = Test.objects.select_related('lesson__profession').get(pk=selected_test_id)
            selected_profession = selected_test.lesson.profession
            test_results = TestResult.first_attempts().filter(
                test=selected_test
            ).select_related('student').order_by('-completed_at')
            
            total_t = test_results.count()
            passed_t = test_results.filter(passed=True).count()
            test_stats = {
                'total': total_t,
                'passed': passed_t,
                'failed': total_t - passed_t,
                'pass_rate': round((passed_t / total_t * 100) if total_t > 0 else 0, 1),
                'avg_score': round(test_results.aggregate(avg=Avg('score'))['avg'] or 0, 1),
                'best_score': test_results.order_by('-score').first(),
                'worst_score': test_results.order_by('score').first(),
            }
            
            # Savol bo'yicha tahlil
            question_analysis = []
            for question in selected_test.questions.prefetch_related('answers').all():
                total_answered = TestUserAnswer.objects.filter(
                    question=question,
                    result__test=selected_test
                ).count()
                correct_count = TestUserAnswer.objects.filter(
                    question=question,
                    result__test=selected_test,
                    is_correct=True
                ).count()
                wrong_count = total_answered - correct_count
                
                # Har bir javob variantining tanlangan soni
                answer_stats = []
                for answer in question.answers.all():
                    selected_count = TestUserAnswer.objects.filter(
                        question=question,
                        selected_answer=answer,
                        result__test=selected_test
                    ).count()
                    answer_stats.append({
                        'answer': answer,
                        'count': selected_count,
                        'percent': round((selected_count / total_answered * 100) if total_answered > 0 else 0),
                    })
                
                error_rate = round((wrong_count / total_answered * 100) if total_answered > 0 else 0)
                question_analysis.append({
                    'question': question,
                    'total': total_answered,
                    'correct': correct_count,
                    'wrong': wrong_count,
                    'error_rate': error_rate,
                    'answer_stats': answer_stats,
                })
            
            # Eng ko'p xato qilingan savollarni birinchi qo'yish
            question_analysis.sort(key=lambda x: x['error_rate'], reverse=True)
            
            # Also get profession_tests for this profession
            profession_tests = Test.objects.filter(
                lesson__profession=selected_profession
            ).select_related('lesson').annotate(
                attempt_count=Count('results', filter=Q(results__id__in=first_attempt_ids)),
                pass_count=Count('results', filter=Q(results__passed=True, results__id__in=first_attempt_ids)),
                avg_score=Avg('results__score', filter=Q(results__id__in=first_attempt_ids))
            )
        except Test.DoesNotExist:
            pass
    
    return render(request, 'accounts/admin/test_analytics.html', {
        'professions': professions,
        'total_tests': total_tests,
        'total_attempts': total_attempts,
        'total_passed': total_passed,
        'pass_rate': pass_rate,
        'avg_score': round(avg_score, 1),
        'today_results': today_results,
        'recent_results': recent_results,
        'selected_profession': selected_profession,
        'profession_tests': profession_tests,
        'selected_test': selected_test,
        'test_results': test_results,
        'test_stats': test_stats,
        'question_analysis': question_analysis if selected_test_id else [],
    })


@login_required
def admin_test_result_detail(request, pk):
    """Admin/Teacher: O'quvchining test natijasi - savol-javob tahlili"""
    if not (request.user.is_admin or request.user.is_teacher):
        return redirect('home')
    
    result = get_object_or_404(TestResult.objects.select_related(
        'test__lesson__profession', 'student'
    ), pk=pk)
    
    # Teacher faqat o'z kurslaridagi natijalarni ko'ra olsin
    if request.user.is_teacher and not request.user.is_admin:
        teaching_ids = request.user.teaching_professions.values_list('pk', flat=True)
        if result.test.lesson.profession_id not in teaching_ids:
            messages.error(request, "Sizda bu natijani ko'rish huquqi yo'q!")
            return redirect('home')
    
    user_answers = result.user_answers.all().select_related(
        'question', 'selected_answer'
    ).order_by('question__order')
    
    # Har bir savol uchun to'g'ri javobni ham olish
    answer_details = []
    for ua in user_answers:
        correct_answer = ua.question.answers.filter(is_correct=True).first()
        answer_details.append({
            'question': ua.question,
            'selected': ua.selected_answer,
            'correct_answer': correct_answer,
            'is_correct': ua.is_correct,
        })
    
    # Determine back URL
    back_url = request.META.get('HTTP_REFERER', '')
    
    return render(request, 'accounts/admin/test_result_detail.html', {
        'result': result,
        'answer_details': answer_details,
        'back_url': back_url,
    })


# Test results for teachers
@login_required
def all_test_results(request):
    if not (request.user.is_admin or request.user.is_teacher):
        return redirect('home')
    
    results = TestResult.objects.all().select_related('test__lesson__profession', 'student')
    
    return render(request, 'accounts/manage/test_results.html', {'results': results})


# Certificates
@login_required
def issue_certificate(request, pk):
    if not request.user.is_admin:
        return redirect('home')
    
    student = get_object_or_404(CustomUser, pk=pk)
    professions = Profession.objects.all()
    
    if request.method == 'POST':
        form = CertificateForm(request.POST, request.FILES)
        profession_id = request.POST.get('profession')
        
        if form.is_valid() and profession_id:
            profession = get_object_or_404(Profession, pk=profession_id)
            cert = form.save(commit=False)
            cert.student = student
            cert.profession = profession
            cert.issued_by = request.user
            cert.save()
            
            # O'quvchiga chiroyli tabrik xabari yuborish
            Message.objects.create(
                recipient=student,
                sender=request.user,
                title="🎓🎉 Tabriklaymiz! Sertifikat berildi!",
                content=(
                    f"🌟🌟🌟 TABRIKLAYMIZ! 🌟🌟🌟\n\n"
                    f"Hurmatli {student.full_name}!\n\n"
                    f"🎓 Sizga \"{profession.name}\" yo'nalishi bo'yicha SERTIFIKAT berildi!\n\n"
                    f"📋 Ma'lumotlar:\n"
                    f"   🆔 ID raqam: {student.id}\n"
                    f"   📚 Yo'nalish: {profession.name}\n"
                    f"   🏅 Sertifikat ID: {cert.certificate_id}\n"
                    f"   📅 Berilgan sana: {cert.valid_from}\n"
                    f"   ✅ Holat: {cert.get_status_display()}\n\n"
                    f"🎊 Siz bu yo'nalishni muvaffaqiyatli tugatdingiz! Bu sizning mehnat va bilimingizning natijasi.\n\n"
                    f"🚀 Yangi kurslarda ham kutib qolamiz! IT Creative Academy sizga yanada ko'proq bilim va tajriba taqdim etishga tayyor.\n\n"
                    f"📜 Sertifikatingizni profil sahifangizdagi \"Sertifikatlarim\" bo'limida ko'rishingiz mumkin.\n\n"
                    f"💜 Hurmat bilan,\nIT Creative Academy jamoasi"
                ),
                message_type='achievement'
            )
            
            # Telegram orqali chiroyli tabrik xabari
            if student.telegram_id:
                telegram_text = (
                    f"🎓🎉🎊 <b>TABRIKLAYMIZ!</b> 🎊🎉🎓\n\n"
                    f"Hurmatli <b>{student.full_name}</b>!\n\n"
                    f"✨ Sizga <b>«{profession.name}»</b> yo'nalishi bo'yicha <b>SERTIFIKAT</b> berildi!\n\n"
                    f"📋 <b>Ma'lumotlar:</b>\n"
                    f"┌ 🆔 ID raqam: <b>{student.id}</b>\n"
                    f"├ 📚 Yo'nalish: <b>{profession.name}</b>\n"
                    f"├ 🏅 Sertifikat: <b>{cert.certificate_id}</b>\n"
                    f"└ 📅 Sana: <b>{cert.valid_from}</b>\n\n"
                    f"🌟 Siz bu yo'nalishni muvaffaqiyatli tugatdingiz! Bu sizning mehnat va bilimingizning natijasi.\n\n"
                    f"🚀 <b>Yangi kurslarda ham kutib qolamiz!</b>\n"
                    f"IT Creative Academy sizga yanada ko'proq bilim va tajriba taqdim etishga tayyor.\n\n"
                    f"💜 <i>IT Creative Academy jamoasi</i>"
                )
                notify_user(student.telegram_id, telegram_text)
            
            # Adminlarga xabar
            notify_admins(
                f"🎓 <b>Sertifikat berildi!</b>\n\n"
                f"👤 O'quvchi: <b>{student.full_name}</b>\n"
                f"📚 Yo'nalish: <b>{profession.name}</b>\n"
                f"🏅 Sertifikat: <b>{cert.certificate_id}</b>"
            )
            
            # Guruhga tabrik
            notify_group(
                f"🎓🎉 <b>TABRIKLAYMIZ!</b> 🎉🎓\n\n"
                f"🌟 <b>{student.full_name}</b> 🌟\n\n"
                f"<b>«{profession.name}»</b> yo'nalishini muvaffaqiyatli tugatdi va <b>SERTIFIKAT</b> oldi! 🏅\n\n"
                f"🎊 Tabriklaymiz va yangi kurslarda kutib qolamiz! 🚀\n\n"
                f"💜 <b>IT Creative Academy</b>"
            )
            
            messages.success(request, f"Sertifikat berildi! ID: {cert.certificate_id}")
            return redirect('admin_user_view', pk=pk)
    else:
        form = CertificateForm()
    
    return render(request, 'accounts/manage/issue_certificate.html', {
        'student': student,
        'professions': professions,
        'form': form,
    })


def verify_certificate(request):
    """Sertifikatni tekshirish - login talab qilinmaydi"""
    certificate = None
    searched = False
    error = None
    student_results = None
    
    cert_id = request.GET.get('id', '').strip()
    if cert_id:
        searched = True
        try:
            certificate = Certificate.objects.select_related('student', 'profession', 'issued_by').get(certificate_id=cert_id)
            
            student = certificate.student
            profession = certificate.profession
            
            # Kurs darslari
            lessons = Lesson.objects.filter(profession=profession)
            total_lessons = lessons.count()
            
            # Test natijalari
            test_results = TestResult.objects.filter(
                student=student,
                test__lesson__profession=profession
            ).select_related('test__lesson')
            tests_taken = test_results.count()
            tests_passed = test_results.filter(passed=True).count()
            avg_test_score = test_results.aggregate(avg=Avg('score'))['avg'] or 0
            
            # Uyga vazifa natijalari
            hw_submissions = HomeworkSubmission.objects.filter(
                student=student,
                homework__lesson__profession=profession,
                status__in=['accepted', 'graded']
            ).select_related('homework__lesson')
            hw_count = hw_submissions.count()
            avg_hw_grade = hw_submissions.aggregate(avg=Avg('grade'))['avg'] or 0
            
            # Speaking natijalari
            speaking_subs = SpeakingSubmission.objects.filter(
                student=student,
                speaking_task__lesson__profession=profession,
                status='graded'
            ).select_related('speaking_task__lesson')
            speaking_count = speaking_subs.count()
            avg_speaking_grade = speaking_subs.aggregate(avg=Avg('grade'))['avg'] or 0
            
            # Umumiy o'rtacha ball hisoblash
            all_scores = []
            if tests_taken > 0:
                all_scores.append(avg_test_score)
            if hw_count > 0:
                all_scores.append(avg_hw_grade * 10)  # 10-ballik -> 100-ballik
            if speaking_count > 0:
                all_scores.append(avg_speaking_grade * 10)
            overall_avg = sum(all_scores) / len(all_scores) if all_scores else 0
            
            student_results = {
                'total_lessons': total_lessons,
                'tests_taken': tests_taken,
                'tests_passed': tests_passed,
                'avg_test_score': round(avg_test_score, 1),
                'hw_count': hw_count,
                'avg_hw_grade': round(avg_hw_grade, 1),
                'speaking_count': speaking_count,
                'avg_speaking_grade': round(avg_speaking_grade, 1),
                'overall_avg': round(overall_avg, 1),
                'test_results': test_results[:10],
            }
            
        except Certificate.DoesNotExist:
            error = "Bu ID raqamga mos sertifikat topilmadi."
    
    return render(request, 'accounts/verify_certificate.html', {
        'certificate': certificate,
        'searched': searched,
        'error': error,
        'cert_id': cert_id,
        'student_results': student_results,
    })


# Admin Panel Views
@login_required
def admin_dashboard(request):
    if not request.user.is_admin:
        messages.error(request, "Sizda admin paneliga kirish huquqi yo'q!")
        return redirect('home')
    
    total_users = CustomUser.objects.count()
    total_teachers = CustomUser.objects.filter(role='teacher').count()
    total_students = CustomUser.objects.filter(role='student').count()
    total_professions = Profession.objects.count()
    blocked_users = CustomUser.objects.filter(is_blocked=True).count()
    online_users = CustomUser.objects.filter(
        last_activity__gte=timezone.now() - timedelta(seconds=300)
    ).count()
    
    # Qo'shimcha statistika
    total_lessons = Lesson.objects.count()
    total_videos = VideoLesson.objects.count()
    total_tests = Test.objects.count()
    total_homeworks = Homework.objects.count()
    total_enrollments = CourseEnrollment.objects.count()
    total_certificates = Certificate.objects.count()
    total_coins = CustomUser.objects.aggregate(total=Sum('coins'))['total'] or 0
    
    # Test natijalari (cached)
    test_cache = cache.get('admin_test_stats')
    if test_cache is None:
        fa = TestResult.first_attempts()
        test_cache = {
            'total': fa.count(),
            'passed': fa.filter(passed=True).count(),
            'avg': fa.aggregate(avg=Avg('score'))['avg'] or 0,
        }
        cache.set('admin_test_stats', test_cache, 300)
    total_test_results = test_cache['total']
    passed_tests = test_cache['passed']
    avg_test_score = test_cache['avg']
    
    # Uyga vazifalar
    pending_homeworks = HomeworkSubmission.objects.filter(status='pending').count()
    graded_homeworks = HomeworkSubmission.objects.filter(status='graded').count()
    
    # Mahsulot statistikasi
    from coin.models import Product, ProductPurchase
    total_products = Product.objects.count()
    active_products = Product.objects.filter(is_active=True).count()
    total_purchases = ProductPurchase.objects.count()
    total_coins_spent = ProductPurchase.objects.aggregate(total=Sum('coins_spent'))['total'] or 0
    
    # Deploy statistikasi
    total_deploys = HTMLDeploy.objects.count()
    active_deploys = HTMLDeploy.objects.filter(is_active=True).count()
    inactive_deploys = HTMLDeploy.objects.filter(is_active=False).count()
    total_deploy_views = HTMLDeploy.objects.aggregate(total=Sum('views_count'))['total'] or 0
    
    # Ota-onalar statistikasi
    total_parents = Parent.objects.count()
    active_parents = Parent.objects.filter(is_active=True).count()
    
    # Oxirgi harakatlar
    recent_activities = ActivityLog.objects.select_related('user').order_by('-created_at')[:10]
    
    profession_stats = Profession.objects.annotate(
        student_count=Count('enrollments', filter=Q(enrollments__user__role='student')),
        teacher_count=Count('students', filter=Q(students__role='teacher'))
    )
    
    recent_users = CustomUser.objects.filter(last_activity__isnull=False).order_by('-last_activity')[:10]
    
    # Oxirgi 7 kun statistikasi
    today = timezone.now().date()
    week_ago = today - timedelta(days=6)
    
    user_counts = dict(
        CustomUser.objects.filter(date_joined__date__gte=week_ago)
        .values_list('date_joined__date')
        .annotate(c=Count('id'))
        .values_list('date_joined__date', 'c')
    )
    enrollment_counts = dict(
        CourseEnrollment.objects.filter(enrolled_at__date__gte=week_ago)
        .values_list('enrolled_at__date')
        .annotate(c=Count('id'))
        .values_list('enrolled_at__date', 'c')
    )
    
    daily_stats = []
    for i in range(6, -1, -1):
        day = today - timedelta(days=i)
        daily_stats.append({
            'date': day,
            'users': user_counts.get(day, 0),
            'enrollments': enrollment_counts.get(day, 0),
        })
    
    # Texnik xizmat rejimi
    maintenance = MaintenanceMode.get_instance()
    
    context = {
        'maintenance': maintenance,
        'total_users': total_users,
        'total_teachers': total_teachers,
        'total_students': total_students,
        'total_professions': total_professions,
        'blocked_users': blocked_users,
        'online_users': online_users,
        'total_lessons': total_lessons,
        'total_videos': total_videos,
        'total_tests': total_tests,
        'total_homeworks': total_homeworks,
        'total_enrollments': total_enrollments,
        'total_certificates': total_certificates,
        'total_coins': total_coins,
        'total_test_results': total_test_results,
        'passed_tests': passed_tests,
        'avg_test_score': round(avg_test_score, 1),
        'pending_homeworks': pending_homeworks,
        'graded_homeworks': graded_homeworks,
        'profession_stats': profession_stats,
        'recent_users': recent_users,
        'daily_stats': daily_stats,
        'total_products': total_products,
        'active_products': active_products,
        'total_purchases': total_purchases,
        'total_coins_spent': total_coins_spent,
        'total_deploys': total_deploys,
        'active_deploys': active_deploys,
        'inactive_deploys': inactive_deploys,
        'total_deploy_views': total_deploy_views,
        'recent_activities': recent_activities,
        'total_parents': total_parents,
        'active_parents': active_parents,
    }
    return render(request, 'accounts/admin/dashboard.html', context)


@login_required
def toggle_maintenance(request):
    """Texnik xizmat rejimini yoqish/o'chirish"""
    if not request.user.is_admin:
        return redirect('home')
    
    maintenance = MaintenanceMode.get_instance()
    maintenance.is_active = not maintenance.is_active
    maintenance.activated_by = request.user
    
    if request.method == 'POST':
        custom_message = request.POST.get('maintenance_message', '').strip()
        if custom_message:
            maintenance.message = custom_message
    
    maintenance.save()
    
    if maintenance.is_active:
        notify_group(
            f"🔧 <b>Texnik xizmat rejimi yoqildi!</b>\n\n"
            f"⚠️ Sayt vaqtincha ishlamaydi.\n"
            f"📝 {maintenance.message}\n\n"
            f"👤 Admin: <b>{request.user.full_name}</b>"
        )
        for u in CustomUser.objects.filter(telegram_id__isnull=False, is_blocked=False):
            notify_user(
                u.telegram_id,
                f"🔧 <b>Texnik xizmat rejimi yoqildi!</b>\n\n"
                f"⚠️ Sayt vaqtincha ishlamaydi.\n"
                f"📝 {maintenance.message}\n\n"
                f"⏳ Iltimos, keyinroq urinib ko'ring."
            )
    else:
        notify_group(
            f"✅ <b>Sayt yana ishlayapti!</b>\n\n"
            f"🎉 Texnik xizmat rejimi o'chirildi.\n"
            f"🚀 Saytga kirishingiz mumkin!\n\n"
            f"👤 Admin: <b>{request.user.full_name}</b>"
        )
        for u in CustomUser.objects.filter(telegram_id__isnull=False, is_blocked=False):
            notify_user(
                u.telegram_id,
                f"✅ <b>Sayt yana ishlayapti!</b>\n\n"
                f"🎉 Texnik ishlar tugadi.\n"
                f"🚀 Saytga kirishingiz mumkin!"
            )
    
    status = "yoqildi" if maintenance.is_active else "o'chirildi"
    messages.success(request, f"Texnik xizmat rejimi {status}!")
    return redirect('admin_dashboard')


@login_required
def admin_professions(request):
    if not request.user.is_admin:
        return redirect('home')
    
    professions = Profession.objects.prefetch_related('enrollments__user', 'teachers').annotate(
        student_count=Count('enrollments', filter=Q(enrollments__user__role='student')),
        teacher_count=Count('students', filter=Q(students__role='teacher'))
    )
    all_students = CustomUser.objects.filter(role='student').order_by('first_name', 'last_name')
    return render(request, 'accounts/admin/professions.html', {'professions': professions, 'all_students': all_students})


def _enroll_all_students_mandatory(profession):
    """Majburiy kursga barcha o'quvchilarni avtomatik yozish"""
    students = CustomUser.objects.filter(role='student')
    created_count = 0
    for student in students:
        _, created = CourseEnrollment.objects.get_or_create(user=student, profession=profession)
        if created:
            created_count += 1
            if student.telegram_id:
                notify_user(
                    student.telegram_id,
                    f"📌 <b>Majburiy kurs tayinlandi!</b>\n\n"
                    f"📖 <b>{profession.name}</b>\n\n"
                    f"📚 Siz ushbu kursga avtomatik yozildingiz. O'qishni boshlang!"
                )
    if created_count:
        notify_admins(
            f"📌 <b>Majburiy kurs belgilandi!</b>\n\n"
            f"📖 {profession.name}\n"
            f"👥 {created_count} ta o'quvchi avtomatik yozildi"
        )


@login_required
def admin_profession_add(request):
    if not request.user.is_admin:
        return redirect('home')
    
    if request.method == 'POST':
        form = ProfessionForm(request.POST, request.FILES)
        if form.is_valid():
            profession = form.save()
            if profession.is_mandatory:
                _enroll_all_students_mandatory(profession)
            messages.success(request, "Kasb muvaffaqiyatli qo'shildi!")
            return redirect('admin_professions')
    else:
        form = ProfessionForm()
    
    return render(request, 'accounts/admin/profession_form.html', {'form': form, 'title': "Kasb qo'shish"})


@login_required
def admin_profession_edit(request, pk):
    if not request.user.is_admin:
        return redirect('home')
    
    profession = get_object_or_404(Profession, pk=pk)
    was_mandatory = profession.is_mandatory
    
    if request.method == 'POST':
        form = ProfessionForm(request.POST, request.FILES, instance=profession)
        if form.is_valid():
            profession = form.save()
            if profession.is_mandatory and not was_mandatory:
                _enroll_all_students_mandatory(profession)
            messages.success(request, "Kasb muvaffaqiyatli tahrirlandi!")
            return redirect('admin_professions')
    else:
        form = ProfessionForm(instance=profession)
    
    return render(request, 'accounts/admin/profession_form.html', {'form': form, 'title': "Kasbni tahrirlash", 'profession': profession})


@login_required
def admin_profession_delete(request, pk):
    if not request.user.is_admin:
        return redirect('home')
    
    profession = get_object_or_404(Profession, pk=pk)
    
    if request.method == 'POST':
        profession.delete()
        messages.success(request, "Kasb muvaffaqiyatli o'chirildi!")
        return redirect('admin_professions')
    
    return render(request, 'accounts/admin/profession_delete.html', {'profession': profession})


@login_required
def admin_profession_toggle_block(request, pk):
    """Kasbni bloklash/blokdan chiqarish"""
    if not request.user.is_admin:
        return redirect('home')
    
    profession = get_object_or_404(Profession, pk=pk)
    
    if request.method == 'POST':
        profession.is_blocked = not profession.is_blocked
        if profession.is_blocked:
            profession.blocked_reason = request.POST.get('blocked_reason', '').strip() or "Vaqtincha to'xtatilgan"
            messages.warning(request, f"'{profession.name}' kursi bloklandi!")
        else:
            profession.blocked_reason = None
            messages.success(request, f"'{profession.name}' kursi blokdan chiqarildi!")
        profession.save()
    
    return redirect('admin_professions')


@login_required
def admin_profession_toggle_daily_limit(request, pk):
    """Kunlik bo'lim cheklovini yoqish/o'chirish"""
    if not request.user.is_admin:
        return redirect('home')
    
    profession = get_object_or_404(Profession, pk=pk)
    
    if request.method == 'POST':
        profession.daily_section_limit = not profession.daily_section_limit
        profession.save()
        if profession.daily_section_limit:
            messages.success(request, f"'{profession.name}' uchun kunlik bo'lim cheklovi yoqildi! 🔒")
        else:
            messages.success(request, f"'{profession.name}' uchun kunlik bo'lim cheklovi o'chirildi! 🔓")
    
    return redirect('admin_professions')


@login_required
def admin_remove_student_from_course(request, profession_pk, user_pk):
    if not request.user.is_admin:
        return redirect('home')
    
    profession = get_object_or_404(Profession, pk=profession_pk)
    student = get_object_or_404(CustomUser, pk=user_pk)
    
    if request.method == 'POST':
        enrollment = CourseEnrollment.objects.filter(user=student, profession=profession).first()
        if enrollment:
            enrollment.delete()
            if student.profession == profession:
                student.profession = None
                student.save(update_fields=['profession'])
            messages.success(request, f"{student.full_name} '{profession.name}' kursidan chiqarildi!")
        else:
            messages.warning(request, f"{student.full_name} bu kursga yozilmagan!")
    
    return redirect('admin_professions')


@login_required
def admin_add_student_to_course(request, profession_pk):
    """Admin: O'quvchini kursga qo'shish"""
    if not request.user.is_admin:
        return redirect('home')
    
    profession = get_object_or_404(Profession, pk=profession_pk)
    
    if request.method == 'POST':
        user_pk = request.POST.get('user_pk')
        if user_pk:
            student = get_object_or_404(CustomUser, pk=user_pk, role='student')
            if CourseEnrollment.objects.filter(user=student, profession=profession).exists():
                messages.info(request, f"{student.full_name} allaqachon '{profession.name}' kursiga yozilgan!")
            else:
                CourseEnrollment.objects.create(user=student, profession=profession)
                # Eski so'rovlarni tozalash (qayta yozilishga to'sqinlik qilmasligi uchun)
                CourseEnrollmentRequest.objects.filter(user=student, profession=profession).delete()
                CourseUnenrollRequest.objects.filter(user=student, profession=profession).delete()
                # Qayta yozilish bo'lsa — eski progressni tozalash
                _reset_course_progress(student, profession)
                messages.success(request, f"{student.full_name} '{profession.name}' kursiga muvaffaqiyatli qo'shildi!")
    
    return redirect('admin_professions')


@login_required
def admin_users(request):
    if not request.user.is_admin:
        return redirect('home')
    
    search_query = request.GET.get('q', '').strip()
    role_filter = request.GET.get('role', '')
    profession_filter = request.GET.get('profession', '')
    status_filter = request.GET.get('status', '')
    sort_by = request.GET.get('sort', '')
    
    users = CustomUser.objects.all()
    
    if search_query:
        from django.db.models import Q
        users = users.filter(
            Q(first_name__icontains=search_query) |
            Q(last_name__icontains=search_query) |
            Q(username__icontains=search_query) |
            Q(phone__icontains=search_query)
        )
    
    if role_filter:
        users = users.filter(role=role_filter)
    if profession_filter:
        users = users.filter(profession_id=profession_filter)
    if status_filter == 'blocked':
        users = users.filter(is_blocked=True)
    elif status_filter == 'active':
        users = users.filter(is_blocked=False)
    
    if sort_by == 'name':
        users = users.order_by('first_name', 'last_name')
    elif sort_by == 'name_desc':
        users = users.order_by('-first_name', '-last_name')
    elif sort_by == 'newest':
        users = users.order_by('-date_joined')
    elif sort_by == 'oldest':
        users = users.order_by('date_joined')
    elif sort_by == 'activity':
        users = users.order_by('-last_activity')
    else:
        users = users.order_by('-date_joined')
    
    total_count = users.count()
    professions = Profession.objects.all()
    
    paginator = Paginator(users, 25)
    page = request.GET.get('page')
    users = paginator.get_page(page)
    
    active_filters = sum([
        bool(role_filter),
        bool(profession_filter),
        bool(status_filter),
    ])
    
    return render(request, 'accounts/admin/users.html', {
        'users': users,
        'professions': professions,
        'search_query': search_query,
        'role_filter': role_filter,
        'profession_filter': profession_filter,
        'status_filter': status_filter,
        'sort_by': sort_by,
        'total_count': total_count,
        'active_filters': active_filters,
    })


@login_required
def admin_user_view(request, pk):
    if not request.user.is_admin:
        return redirect('home')
    
    user = get_object_or_404(CustomUser, pk=pk)
    certificates = Certificate.objects.filter(student=user)
    
    # O'quvchi tahlili
    analysis_data = []
    
    if user.role == 'student':
        enrollments = user.enrollments.all().select_related('profession')
        
        for enrollment in enrollments:
            profession = enrollment.profession
            
            # Darslar
            total_lessons = Lesson.objects.filter(profession=profession).count()
            
            # Video progress
            watched_videos = VideoProgress.objects.filter(
                user=user,
                video__lesson__profession=profession,
                watched=True
            ).count()
            total_videos = VideoLesson.objects.filter(lesson__profession=profession).count()
            
            # Test natijalari
            test_results = TestResult.objects.filter(
                student=user,
                test__lesson__profession=profession
            )
            tests_taken = test_results.count()
            avg_test_score = test_results.aggregate(avg=Avg('score'))['avg'] or 0
            passed_tests = test_results.filter(passed=True).count()
            
            # Homework
            homework_submissions = HomeworkSubmission.objects.filter(
                student=user,
                homework__lesson__profession=profession
            )
            total_homeworks = Homework.objects.filter(lesson__profession=profession).count()
            submitted_homeworks = homework_submissions.count()
            graded_homeworks = homework_submissions.filter(status='graded').count()
            pending_homeworks = homework_submissions.filter(status='pending').count()
            avg_homework_grade = homework_submissions.filter(grade__isnull=False).aggregate(avg=Avg('grade'))['avg'] or 0
            
            # Umumiy progress
            completed_items = watched_videos + tests_taken + submitted_homeworks
            total_items = total_videos + Test.objects.filter(lesson__profession=profession).count() + total_homeworks
            overall_progress = (completed_items / total_items * 100) if total_items > 0 else 0
            
            # Qaysi darslarda to'xtab qolgan
            stuck_lessons = []
            lessons = Lesson.objects.filter(profession=profession).order_by('section__order', 'order')
            for lesson in lessons:
                # Video lesson uchun tekshirish (OneToOne relation)
                has_video = hasattr(lesson, 'video') and lesson.video is not None
                lesson_videos = 1 if has_video else 0
                watched = VideoProgress.objects.filter(user=user, video__lesson=lesson, watched=True).count()
                has_test = Test.objects.filter(lesson=lesson).exists()
                test_passed = TestResult.objects.filter(student=user, test__lesson=lesson).exists()
                has_hw = Homework.objects.filter(lesson=lesson).exists()
                hw_submitted = HomeworkSubmission.objects.filter(student=user, homework__lesson=lesson).exists()
                
                # Agar video ko'rilmagan yoki test topshirilmagan bo'lsa
                if (lesson_videos > 0 and watched < lesson_videos) or (has_test and not test_passed) or (has_hw and not hw_submitted):
                    stuck_lessons.append({
                        'lesson': lesson,
                        'video_progress': f"{watched}/{lesson_videos}",
                        'test_done': test_passed if has_test else None,
                        'hw_done': hw_submitted if has_hw else None,
                    })
            
            analysis_data.append({
                'profession': profession,
                'enrollment': enrollment,
                'overall_progress': round(overall_progress, 1),
                'total_lessons': total_lessons,
                'watched_videos': watched_videos,
                'total_videos': total_videos,
                'tests_taken': tests_taken,
                'avg_test_score': round(avg_test_score, 1),
                'passed_tests': passed_tests,
                'total_homeworks': total_homeworks,
                'submitted_homeworks': submitted_homeworks,
                'graded_homeworks': graded_homeworks,
                'pending_homeworks': pending_homeworks,
                'avg_homework_grade': round(avg_homework_grade, 1),
                'stuck_lessons': stuck_lessons[:5],  # Oxirgi 5 ta
            })
    
    # Coin statistikasi
    coin_earned = CoinTransaction.objects.filter(user=user, action='add').aggregate(total=Sum('amount'))['total'] or 0
    coin_spent = CoinTransaction.objects.filter(user=user, action__in=['remove', 'purchase']).aggregate(total=Sum('amount'))['total'] or 0
    
    # Oxirgi faolliklar
    recent_activities = ActivityLog.objects.filter(user=user).order_by('-created_at')[:10]
    
    return render(request, 'accounts/admin/user_view.html', {
        'user_obj': user,
        'certificates': certificates,
        'analysis_data': analysis_data,
        'coin_earned': coin_earned,
        'coin_spent': coin_spent,
        'recent_activities': recent_activities,
    })


@login_required
def admin_add_teacher(request):
    """O'qituvchi qo'shish"""
    if not request.user.is_admin:
        return redirect('home')
    
    professions = Profession.objects.all()
    
    if request.method == 'POST':
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        username = request.POST.get('username', '').strip()
        phone = request.POST.get('phone', '').strip()
        password = request.POST.get('password', '').strip()
        selected_professions = request.POST.getlist('professions')
        
        # Validation
        if not all([first_name, last_name, username, phone, password]):
            messages.error(request, "Barcha maydonlarni to'ldiring!")
            return render(request, 'accounts/admin/add_teacher.html', {
                'professions': professions,
            })
        
        if CustomUser.objects.filter(username=username).exists():
            messages.error(request, "Bu username allaqachon band!")
            return render(request, 'accounts/admin/add_teacher.html', {
                'professions': professions,
            })
        
        if CustomUser.objects.filter(phone=phone).exists():
            messages.error(request, "Bu telefon raqam allaqachon ro'yxatdan o'tgan!")
            return render(request, 'accounts/admin/add_teacher.html', {
                'professions': professions,
            })
        
        teacher = CustomUser.objects.create_user(
            username=username,
            password=password,
            first_name=first_name,
            last_name=last_name,
            phone=phone,
            role='teacher',
        )
        
        # Assign teaching professions
        if selected_professions:
            teacher.teaching_professions.set(selected_professions)
            # Set primary profession to first selected
            teacher.profession = Profession.objects.filter(pk=selected_professions[0]).first()
            teacher.save()
        
        # Save certificates
        cert_titles = request.POST.getlist('cert_title')
        cert_files = request.FILES.getlist('cert_file')
        if cert_titles and cert_files:
            from teacher.models import TeacherCertificate
            for title, file in zip(cert_titles, cert_files):
                if title.strip() and file:
                    TeacherCertificate.objects.create(
                        teacher=teacher,
                        title=title.strip(),
                        file=file,
                    )
        
        messages.success(request, f"O'qituvchi {teacher.full_name} muvaffaqiyatli qo'shildi!")
        return redirect('admin_users')
    
    return render(request, 'accounts/admin/add_teacher.html', {
        'professions': professions,
    })


@login_required
def admin_user_edit(request, pk):
    if not request.user.is_admin:
        return redirect('home')
    
    user = get_object_or_404(CustomUser, pk=pk)
    
    professions = Profession.objects.all()
    
    if request.method == 'POST':
        form = AdminUserEditForm(request.POST, request.FILES, instance=user)
        if form.is_valid():
            user = form.save()
            new_password = request.POST.get('new_password')
            if new_password:
                user.set_password(new_password)
                user.save()
            
            # O'qituvchi kurslarini yangilash
            if user.role == 'teacher':
                selected_professions = request.POST.getlist('teaching_professions')
                user.teaching_professions.set(selected_professions)
            
            messages.success(request, "Foydalanuvchi muvaffaqiyatli yangilandi!")
            return redirect('admin_users')
    else:
        form = AdminUserEditForm(instance=user)
    
    return render(request, 'accounts/admin/user_edit.html', {
        'form': form,
        'user_obj': user,
        'professions': professions,
    })


@login_required
def admin_user_block(request, pk):
    if not request.user.is_admin:
        return redirect('home')
    
    user = get_object_or_404(CustomUser, pk=pk)
    
    if user.is_admin:
        messages.error(request, "Admin foydalanuvchini bloklash mumkin emas!")
        return redirect('admin_users')
    
    user.is_blocked = not user.is_blocked
    user.save()
    
    if user.is_blocked:
        notify_group(
            f"🚫 <b>Foydalanuvchi bloklandi!</b>\n\n"
            f"👤 {user.full_name}\n"
            f"📋 Role: {user.get_role_display()}\n"
            f"🔒 Admin <b>{request.user.full_name}</b> tomonidan bloklandi."
        )
        if user.telegram_id:
            notify_user(
                user.telegram_id,
                f"🚫 <b>Hisobingiz bloklandi!</b>\n\n"
                f"👤 {user.full_name}\n"
                f"📋 Rol: {user.get_role_display()}\n\n"
                f"❌ Sizning hisobingiz admin tomonidan bloklandi.\n"
                f"📞 Qo'shimcha ma'lumot uchun adminstratsiya bilan bog'laning."
            )
    else:
        notify_group(
            f"✅ <b>Foydalanuvchi blokdan chiqarildi!</b>\n\n"
            f"👤 {user.full_name}\n"
            f"📋 Role: {user.get_role_display()}\n"
            f"🔓 Admin <b>{request.user.full_name}</b> tomonidan blokdan chiqarildi."
        )
        if user.telegram_id:
            notify_user(
                user.telegram_id,
                f"✅ <b>Hisobingiz blokdan chiqarildi!</b>\n\n"
                f"👤 {user.full_name}\n\n"
                f"🎉 Hisobingiz ochildi. Endi tizimdan foydalanishingiz mumkin."
            )
    
    messages.success(request, f"{user.full_name} {'bloklandi' if user.is_blocked else 'blokdan chiqarildi'}!")
    return redirect('admin_users')


@login_required
def admin_user_delete(request, pk):
    if not request.user.is_admin:
        return redirect('home')
    
    user = get_object_or_404(CustomUser, pk=pk)
    
    if user.is_admin:
        messages.error(request, "Admin foydalanuvchini o'chirish mumkin emas!")
        return redirect('admin_users')
    
    if request.method == 'POST':
        user.delete()
        messages.success(request, "Foydalanuvchi o'chirildi!")
        return redirect('admin_users')
    
    return render(request, 'accounts/admin/user_delete.html', {'user_obj': user})


@login_required
def admin_statistics(request):
    if not request.user.is_admin:
        return redirect('home')
    
    today = timezone.now().date()
    now = timezone.now()
    
    # ===== BASIC COUNTS =====
    total_users = CustomUser.objects.count()
    total_teachers = CustomUser.objects.filter(role='teacher').count()
    total_students = CustomUser.objects.filter(role='student').count()
    total_admins = CustomUser.objects.filter(role='admin').count()
    blocked_users = CustomUser.objects.filter(is_blocked=True).count()
    online_users = CustomUser.objects.filter(
        last_activity__gte=now - timedelta(seconds=300)
    ).count()
    
    # ===== GROWTH: this month vs last month =====
    this_month_start = today.replace(day=1)
    last_month_end = this_month_start - timedelta(days=1)
    last_month_start = last_month_end.replace(day=1)
    
    new_users_this_month = CustomUser.objects.filter(date_joined__date__gte=this_month_start).count()
    new_users_last_month = CustomUser.objects.filter(
        date_joined__date__gte=last_month_start,
        date_joined__date__lt=this_month_start
    ).count()
    
    if new_users_last_month > 0:
        growth_percent = round(((new_users_this_month - new_users_last_month) / new_users_last_month) * 100)
    else:
        growth_percent = 100 if new_users_this_month > 0 else 0
    
    # ===== PROFESSION STATS =====
    profession_stats = Profession.objects.annotate(
        student_count=Count('enrollments', filter=Q(enrollments__user__role='student')),
        teacher_count=Count('students', filter=Q(students__role='teacher')),
        total=Count('enrollments')
    ).order_by('-total')
    
    # ===== DAILY REGISTRATIONS (last 7 days for chart) =====
    daily_registrations = []
    for i in range(6, -1, -1):
        day = today - timedelta(days=i)
        count = CustomUser.objects.filter(date_joined__date=day).count()
        daily_registrations.append({'date': day, 'count': count})
    
    # Monthly registrations for last 6 months (for bar chart)
    monthly_registrations = []
    month_names = ['', 'Yan', 'Fev', 'Mar', 'Apr', 'May', 'Iyn', 'Iyl', 'Avg', 'Sen', 'Okt', 'Noy', 'Dek']
    for i in range(5, -1, -1):
        m_date = today - timedelta(days=i*30)
        m_start = m_date.replace(day=1)
        if m_date.month == 12:
            m_end = m_date.replace(year=m_date.year+1, month=1, day=1)
        else:
            m_end = m_date.replace(month=m_date.month+1, day=1)
        count = CustomUser.objects.filter(date_joined__date__gte=m_start, date_joined__date__lt=m_end).count()
        monthly_registrations.append({
            'month': month_names[m_date.month],
            'year': m_date.year,
            'count': count,
        })
    max_monthly = max((m['count'] for m in monthly_registrations), default=1) or 1
    for m in monthly_registrations:
        m['pct'] = round(m['count'] / max_monthly * 100)
    
    # ===== TEST ANALYTICS =====
    total_tests = Test.objects.count()
    total_test_results = TestResult.objects.count()
    avg_test_score = TestResult.objects.aggregate(avg=Avg('score'))['avg'] or 0
    test_pass_rate = 0
    if total_test_results > 0:
        passed_tests = TestResult.objects.filter(passed=True).count()
        test_pass_rate = round((passed_tests / total_test_results) * 100)
    
    # ===== HOMEWORK ANALYTICS =====
    total_hw_submissions = HomeworkSubmission.objects.count()
    hw_pending = HomeworkSubmission.objects.filter(status='pending').count()
    hw_graded = HomeworkSubmission.objects.filter(status='graded').count()
    hw_accepted = HomeworkSubmission.objects.filter(status='accepted').count()
    hw_avg_grade = HomeworkSubmission.objects.filter(
        grade__isnull=False
    ).aggregate(avg=Avg('grade'))['avg'] or 0
    
    # ===== VIDEO ANALYTICS =====
    total_videos = VideoLesson.objects.count()
    total_video_minutes = VideoLesson.objects.aggregate(total=Sum('duration'))['total'] or 0
    videos_watched = VideoProgress.objects.filter(watched=True).count()
    
    # ===== LESSON COUNTS =====
    total_lessons = Lesson.objects.count()
    video_lessons_count = Lesson.objects.filter(lesson_type='video').count()
    test_lessons_count = Lesson.objects.filter(lesson_type='test').count()
    hw_lessons_count = Lesson.objects.filter(lesson_type='homework').count()
    
    # ===== PAYMENT ANALYTICS =====
    current_month = today.month
    current_year = today.year
    paid_this_month = PaymentRecord.objects.filter(
        month=current_month, year=current_year, is_paid=True
    ).count()
    unpaid_this_month = PaymentRecord.objects.filter(
        month=current_month, year=current_year, is_paid=False
    ).count()
    total_revenue_this_month = PaymentRecord.objects.filter(
        month=current_month, year=current_year
    ).aggregate(total=Sum('paid_amount'))['total'] or 0
    
    # ===== TOP STUDENTS (by test scores) =====
    top_students = CustomUser.objects.filter(
        role='student',
        test_results__isnull=False
    ).annotate(
        avg_score=Avg('test_results__score'),
        tests_taken=Count('test_results')
    ).order_by('-avg_score')[:5]
    
    # ===== RECENT ACTIVITY =====
    recent_test_results = TestResult.objects.select_related(
        'student', 'test__lesson__profession'
    ).order_by('-completed_at')[:8]
    
    recent_submissions = HomeworkSubmission.objects.select_related(
        'student', 'homework__lesson__profession'
    ).order_by('-submitted_at')[:8]
    
    # ===== PREMIUM STATS =====
    premium_users = CustomUser.objects.filter(is_premium=True).count()
    
    context = {
        'total_users': total_users,
        'total_teachers': total_teachers,
        'total_students': total_students,
        'total_admins': total_admins,
        'blocked_users': blocked_users,
        'online_users': online_users,
        'new_users_this_month': new_users_this_month,
        'growth_percent': growth_percent,
        'profession_stats': profession_stats,
        'daily_registrations': daily_registrations,
        'monthly_registrations': monthly_registrations,
        # Test analytics
        'total_tests': total_tests,
        'total_test_results': total_test_results,
        'avg_test_score': round(avg_test_score, 1),
        'test_pass_rate': test_pass_rate,
        # Homework analytics
        'total_hw_submissions': total_hw_submissions,
        'hw_pending': hw_pending,
        'hw_graded': hw_graded,
        'hw_accepted': hw_accepted,
        'hw_avg_grade': round(hw_avg_grade, 1),
        # Video analytics
        'total_videos': total_videos,
        'total_video_minutes': total_video_minutes,
        'videos_watched': videos_watched,
        # Lesson counts
        'total_lessons': total_lessons,
        'video_lessons_count': video_lessons_count,
        'test_lessons_count': test_lessons_count,
        'hw_lessons_count': hw_lessons_count,
        # Payment
        'paid_this_month': paid_this_month,
        'unpaid_this_month': unpaid_this_month,
        'total_revenue_this_month': total_revenue_this_month,
        # Top students
        'top_students': top_students,
        # Recent activity
        'recent_test_results': recent_test_results,
        'recent_submissions': recent_submissions,
        # Premium
        'premium_users': premium_users,
    }
    
    return render(request, 'accounts/admin/statistics.html', context)


@login_required
def admin_export_pdf(request):
    if not request.user.is_admin:
        return redirect('home')
    
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from io import BytesIO
    
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    elements = []
    styles = getSampleStyleSheet()
    
    elements.append(Paragraph("LMS Statistika Hisoboti", styles['Heading1']))
    elements.append(Paragraph(f"Sana: {timezone.now().strftime('%d.%m.%Y %H:%M')}", styles['Normal']))
    elements.append(Spacer(1, 20))
    
    total_users = CustomUser.objects.count()
    total_teachers = CustomUser.objects.filter(role='teacher').count()
    total_students = CustomUser.objects.filter(role='student').count()
    
    stats_data = [
        ['Ko\'rsatkich', 'Soni'],
        ['Jami foydalanuvchilar', str(total_users)],
        ['O\'quvchilar', str(total_students)],
        ['O\'qituvchilar', str(total_teachers)],
    ]
    
    table = Table(stats_data, colWidths=[250, 150])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0d6efd')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#dee2e6')),
        ('PADDING', (0, 0), (-1, -1), 8),
    ]))
    elements.append(table)
    
    doc.build(elements)
    buffer.seek(0)
    
    response = HttpResponse(buffer, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="LMS_Stats_{timezone.now().strftime("%Y%m%d")}.pdf"'
    return response


# Section management views
@login_required
def add_section(request, pk):
    if not (request.user.is_admin or request.user.is_teacher):
        return redirect('home')
    
    profession = get_object_or_404(Profession, pk=pk)
    
    if request.user.is_teacher and not request.user.teaching_professions.filter(pk=profession.pk).exists():
        messages.error(request, "Sizda bu kursga kirish huquqi yo'q!")
        return redirect('professions')
    
    if request.method == 'POST':
        form = SectionForm(request.POST)
        if form.is_valid():
            section = form.save(commit=False)
            section.profession = profession
            section.save()
            messages.success(request, "Bo'lim muvaffaqiyatli qo'shildi!")
            return redirect('manage_lessons', pk=pk)
    else:
        form = SectionForm()
    
    return render(request, 'accounts/manage/add_section.html', {
        'profession': profession,
        'form': form,
    })


@login_required
def edit_section(request, pk):
    if not (request.user.is_admin or request.user.is_teacher):
        return redirect('home')
    
    section = get_object_or_404(Section, pk=pk)
    
    if request.user.is_teacher and not request.user.teaching_professions.filter(pk=section.profession.pk).exists():
        messages.error(request, "Sizda bu kursga kirish huquqi yo'q!")
        return redirect('professions')
    
    if request.method == 'POST':
        form = SectionForm(request.POST, instance=section)
        if form.is_valid():
            form.save()
            messages.success(request, "Bo'lim muvaffaqiyatli yangilandi!")
            return redirect('manage_lessons', pk=section.profession.pk)
    else:
        form = SectionForm(instance=section)
    
    return render(request, 'accounts/manage/edit_section.html', {
        'section': section,
        'form': form,
    })


@login_required
def delete_section(request, pk):
    if not (request.user.is_admin or request.user.is_teacher):
        return redirect('home')
    
    section = get_object_or_404(Section, pk=pk)
    
    if request.user.is_teacher and not request.user.teaching_professions.filter(pk=section.profession.pk).exists():
        messages.error(request, "Sizda bu kursga kirish huquqi yo'q!")
        return redirect('professions')
    
    profession_pk = section.profession.pk
    
    if request.method == 'POST':
        section.delete()
        messages.success(request, "Bo'lim o'chirildi!")
        return redirect('manage_lessons', pk=profession_pk)
    
    return render(request, 'accounts/manage/delete_section.html', {'section': section})


# ============== ADMIN: SECTIONS ==============

@login_required
def admin_sections(request):
    if not request.user.is_admin:
        return redirect('home')
    
    sections = Section.objects.all().select_related('profession').prefetch_related('lessons')
    
    profession_id = request.GET.get('profession')
    if profession_id:
        sections = sections.filter(profession_id=profession_id)
    
    q = request.GET.get('q')
    if q:
        sections = sections.filter(title__icontains=q)
    
    professions = Profession.objects.all()
    
    paginator = Paginator(sections, 25)
    page = request.GET.get('page')
    sections = paginator.get_page(page)
    
    return render(request, 'accounts/admin/sections.html', {
        'sections': sections,
        'professions': professions,
    })


@login_required
def admin_section_add(request):
    if not request.user.is_admin:
        return redirect('home')
    
    if request.method == 'POST':
        profession_id = request.POST.get('profession')
        title = request.POST.get('title')
        description = request.POST.get('description', '')
        order = request.POST.get('order', 0)
        is_active = 'is_active' in request.POST
        
        if profession_id and title:
            Section.objects.create(
                profession_id=profession_id,
                title=title,
                description=description,
                order=int(order),
                is_active=is_active
            )
            messages.success(request, "Bo'lim qo'shildi!")
            return redirect('admin_sections')
    
    professions = Profession.objects.all()
    return render(request, 'accounts/admin/section_form.html', {'professions': professions})


@login_required
def admin_section_edit(request, pk):
    if not request.user.is_admin:
        return redirect('home')
    
    section = get_object_or_404(Section, pk=pk)
    
    if request.method == 'POST':
        section.profession_id = request.POST.get('profession')
        section.title = request.POST.get('title')
        section.description = request.POST.get('description', '')
        section.order = int(request.POST.get('order', 0))
        section.is_active = 'is_active' in request.POST
        section.save()
        messages.success(request, "Bo'lim yangilandi!")
        return redirect('admin_sections')
    
    professions = Profession.objects.all()
    return render(request, 'accounts/admin/section_form.html', {
        'section': section,
        'professions': professions,
    })


@login_required
def admin_section_delete(request, pk):
    if not request.user.is_admin:
        return redirect('home')
    
    section = get_object_or_404(Section, pk=pk)
    
    if request.method == 'POST':
        section.delete()
        messages.success(request, "Bo'lim o'chirildi!")
        return redirect('admin_sections')
    
    return render(request, 'accounts/admin/section_delete.html', {'section': section})


# ==================== COIN BOSHQARUVI ====================
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.shortcuts import render, redirect
from django.core.paginator import Paginator
from django.db import transaction

@login_required
def admin_manage_coins(request):

    # 🔐 Admin check
    if not request.user.is_admin:
        messages.error(request, "Sizda bu sahifaga kirish huquqi yo'q!")
        return redirect('home')

    # 📌 Studentlar queryset
    users_qs = CustomUser.objects.filter(
        role='student'
    ).order_by('-coins', 'first_name')

    # =========================
    # FILTRLAR
    # =========================
    search_q = request.GET.get('q', '').strip()
    course_filter = request.GET.get('course', '')
    coin_filter = request.GET.get('coin_range', '')
    sort_by = request.GET.get('sort', '-coins')

    if search_q:
        users_qs = users_qs.filter(
            models.Q(first_name__icontains=search_q) |
            models.Q(last_name__icontains=search_q) |
            models.Q(username__icontains=search_q) |
            models.Q(phone__icontains=search_q)
        )

    if course_filter:
        users_qs = users_qs.filter(enrollments__profession_id=course_filter).distinct()

    if coin_filter == '0':
        users_qs = users_qs.filter(coins=0)
    elif coin_filter == '1-50':
        users_qs = users_qs.filter(coins__gte=1, coins__lte=50)
    elif coin_filter == '51-200':
        users_qs = users_qs.filter(coins__gte=51, coins__lte=200)
    elif coin_filter == '200+':
        users_qs = users_qs.filter(coins__gt=200)

    if sort_by == 'coins':
        users_qs = users_qs.order_by('coins', 'first_name')
    elif sort_by == '-coins':
        users_qs = users_qs.order_by('-coins', 'first_name')
    elif sort_by == 'name':
        users_qs = users_qs.order_by('first_name', 'last_name')
    elif sort_by == '-name':
        users_qs = users_qs.order_by('-first_name', '-last_name')

    # =========================
    # POST ACTION (Coin berish/ayirish)
    # =========================
    if request.method == 'POST':

        user_id = request.POST.get('user_id')
        amount = request.POST.get('amount')
        action = request.POST.get('action')
        reason = request.POST.get('reason', '').strip()
        bulk_ids = request.POST.getlist('bulk_user_ids')

        try:
            amount = int(amount)
            if amount <= 0:
                raise ValueError("Amount must be positive")

            # Guruhga coin berish
            if bulk_ids and action in ('add', 'remove'):
                with transaction.atomic():
                    bulk_users = CustomUser.objects.filter(pk__in=bulk_ids).select_for_update()
                    count = 0
                    for u in bulk_users:
                        if action == 'add':
                            u.coins += amount
                        else:
                            u.coins -= amount
                        u.save(update_fields=['coins'])
                        text = f"Sizga {amount} coin berildi! 🎉" if action == 'add' else f"Sizdan {amount} coin ayirildi."
                        if reason:
                            text += f"\n\nSabab: {reason}"
                        Message.objects.create(
                            sender=request.user, recipient=u,
                            title="Coin rag'batlantirish" if action == 'add' else "Coin ayirildi",
                            content=text, message_type='system'
                        )
                        count += 1
                    verb = "berildi" if action == 'add' else "ayirildi"
                    emoji = "🎁" if action == 'add' else "📤"
                    reason_text = f"\n📝 Sabab: {reason}" if reason else ""
                    coin_msg = (
                        f"{emoji} <b>Coin {verb}!</b>\n\n"
                        f"👥 {count} ta o'quvchiga {amount} coin {verb}{reason_text}"
                    )
                    notify_admins(coin_msg)
                    notify_group(coin_msg)
                    messages.success(request, f"{count} ta o'quvchiga {amount} coin {verb}!")

            elif user_id:
                with transaction.atomic():
                    user = CustomUser.objects.select_for_update().get(pk=user_id)
                    if action == 'add':
                        user.coins += amount
                        user.save(update_fields=['coins'])
                        text = f"Sizga {amount} coin rag'batlantirish sifatida berildi!"
                        if reason:
                            text += f"\n\nSabab: {reason}"
                        Message.objects.create(
                            sender=request.user, recipient=user,
                            title="Coin rag'batlantirish", content=text, message_type='system'
                        )
                        coin_msg = (
                            f"🎁 <b>Coin berildi!</b>\n\n"
                            f"👤 {user.first_name} {user.last_name}\n"
                            f"🪙 +{amount} coin (Jami: {user.coins})\n"
                            f"📝 Sabab: {reason or 'belgilanmagan'}"
                        )
                        notify_admins(coin_msg)
                        notify_group(coin_msg)
                        notify_user(user.telegram_id, coin_msg)
                        messages.success(request, f"{user.full_name}ga {amount} coin berildi!")
                    elif action == 'remove':
                        user.coins -= amount
                        user.save(update_fields=['coins'])
                        text = f"Sizdan {amount} coin ayirildi."
                        if reason:
                            text += f"\n\nSabab: {reason}"
                        Message.objects.create(
                            sender=request.user, recipient=user,
                            title="Coin ayirildi", content=text, message_type='system'
                        )
                        coin_msg = (
                            f"📤 <b>Coin ayirildi!</b>\n\n"
                            f"👤 {user.first_name} {user.last_name}\n"
                            f"🪙 -{amount} coin (Qoldi: {user.coins})\n"
                            f"📝 Sabab: {reason or 'belgilanmagan'}"
                        )
                        notify_admins(coin_msg)
                        notify_group(coin_msg)
                        notify_user(user.telegram_id, coin_msg)
                        messages.success(request, f"{user.full_name}dan {amount} coin ayirildi! (Qoldi: {user.coins})")

        except (ValueError, CustomUser.DoesNotExist):
            messages.error(request, "Xatolik yuz berdi!")

        # 🔥 Qaysi sahifada bo‘lsa o‘sha sahifaga qaytadi
        params = request.GET.urlencode()
        if params:
            return redirect(f"{request.path}?{params}")
        return redirect('admin_manage_coins')

    # =========================
    # STATISTIKA
    # =========================
    all_students = CustomUser.objects.filter(role='student')
    total_coins = all_students.aggregate(total=models.Sum('coins'))['total'] or 0
    avg_coins = all_students.aggregate(avg=models.Avg('coins'))['avg'] or 0
    max_coins_user = all_students.order_by('-coins').first()
    zero_coin_count = all_students.filter(coins=0).count()

    stats = {
        'total_students': all_students.count(),
        'total_coins': total_coins,
        'avg_coins': round(avg_coins, 1),
        'max_coins': max_coins_user.coins if max_coins_user else 0,
        'max_coins_user': max_coins_user,
        'zero_coin_count': zero_coin_count,
    }

    courses = Profession.objects.all().order_by('name')

    # =========================
    # PAGINATION
    # =========================
    paginator = Paginator(users_qs, 25)
    page_number = request.GET.get('page')
    users = paginator.get_page(page_number)

    context = {
        'users': users,
        'stats': stats,
        'courses': courses,
        'search_q': search_q,
        'course_filter': course_filter,
        'coin_filter': coin_filter,
        'sort_by': sort_by,
    }

    return render(request, 'accounts/admin/manage_coins.html', context)


# ==================== YORDAM SO'ROVLARI ====================

@login_required
def help_page(request):
    my_requests = HelpRequest.objects.filter(user=request.user).order_by('-created_at')
    return render(request, 'accounts/help_page.html', {
        'my_requests': my_requests,
    })


@login_required
def submit_help_request(request):
    if request.method == 'POST':
        import logging
        from django.utils import timezone
        from datetime import timedelta
        logger = logging.getLogger(__name__)

        subject = request.POST.get('subject', '').strip()
        message = request.POST.get('message', '').strip()
        image = request.FILES.get('image')
        
        logger.info(f"Help Request Received - User: {request.user.username}, Subject: {subject}, Image: {image}")

        if not subject or not message:
            return JsonResponse({'success': False, 'error': "Mavzu va xabar to'ldirilishi shart!"})

        # Backend Debounce: Check for recent duplicate
        recent_duplicate = HelpRequest.objects.filter(
            user=request.user,
            subject=subject,
            created_at__gte=timezone.now() - timedelta(seconds=10)
        ).exists()

        if recent_duplicate:
            logger.warning(f"Duplicate request detected for user {request.user.username}")
            return JsonResponse({'success': False, 'error': "Siz bu xabarni yaqinda yubordingiz. Biroz kuting."})

        
        help_request = HelpRequest.objects.create(
            user=request.user,
            subject=subject,
            message=message,
            image=image
        )
        notify_admins(
            f"🆘 <b>Yangi yordam so'rovi!</b>\n\n"
            f"👤 {request.user.first_name} {request.user.last_name}\n"
            f"📌 {subject}\n"
            f"💬 {message[:100]}"
        )
        
        logger.info(f"Help Request Created - ID: {help_request.id}, Image Path: {help_request.image.name if help_request.image else 'None'}")
        
        return JsonResponse({'success': True, 'message': "Xabaringiz yuborildi! Tez orada javob beramiz."})
    
    return JsonResponse({'success': False, 'error': 'Noto\'g\'ri so\'rov'})


@login_required
def admin_help_requests(request):
    if not request.user.is_admin:
        messages.error(request, "Sizda bu sahifaga kirish huquqi yo'q!")
        return redirect('home')
    
    status_filter = request.GET.get('status', '')
    requests_list = HelpRequest.objects.select_related('user').all()
    
    if status_filter:
        requests_list = requests_list.filter(status=status_filter)
    
    context = {
        'requests': requests_list,
        'status_filter': status_filter,
        'pending_count': HelpRequest.objects.filter(status='pending').count(),
    }
    return render(request, 'accounts/admin/help_requests.html', context)


@login_required
def admin_help_request_detail(request, pk):
    if not request.user.is_admin:
        messages.error(request, "Sizda bu sahifaga kirish huquqi yo'q!")
        return redirect('home')
    
    help_request = get_object_or_404(HelpRequest, pk=pk)
    
    if request.method == 'POST':
        status = request.POST.get('status')
        admin_response = request.POST.get('admin_response', '').strip()
        
        if status:
            help_request.status = status
        if admin_response:
            help_request.admin_response = admin_response
        help_request.save()
        
        messages.success(request, "So'rov yangilandi!")
        return redirect('admin_help_request_detail', pk=pk)
    
    return render(request, 'accounts/admin/help_request_detail.html', {'help_request': help_request})


# ==================== TO'LOV ESLATMASI ====================

@login_required
def send_payment_reminder(request, pk):
    if not request.user.is_admin:
        messages.error(request, "Sizda bu sahifaga kirish huquqi yo'q!")
        return redirect('home')
    
    student = get_object_or_404(CustomUser, pk=pk, role='student')
    
    Message.objects.create(
        sender=request.user,
        recipient=student,
        title="To'lov eslatmasi",
        content=f"Hurmatli {student.full_name},\n\nSizning oylik to'lovingiz muddati yaqinlashmoqda. Iltimos, o'z vaqtida to'lov qilishni unutmang.\n\nHurmat bilan,\nIT Creative jamoasi",
        message_type='payment'
    )
    notify_user(
        student.telegram_id,
        f"💳 <b>To'lov eslatmasi</b>\n\n"
        f"Hurmatli {student.full_name},\n\n"
        f"Sizning oylik to'lovingiz muddati yaqinlashmoqda.\n"
        f"Iltimos, o'z vaqtida to'lov qilishni unutmang.\n\n"
        f"🏫 IT Creative jamoasi"
    )
    notify_group(
        f"💳 <b>To'lov eslatmasi yuborildi</b>\n\n"
        f"👤 {student.full_name}ga to'lov eslatmasi yuborildi."
    )
    
    messages.success(request, f"{student.full_name}ga to'lov eslatmasi yuborildi!")
    return redirect('admin_payments')


@login_required
def send_bulk_payment_reminders(request):
    if not request.user.is_admin:
        messages.error(request, "Sizda bu sahifaga kirish huquqi yo'q!")
        return redirect('home')
    
    if request.method == 'POST':
        unpaid_students = CustomUser.objects.filter(role='student').exclude(
            payment_status__is_paid=True
        )
        
        count = 0
        for student in unpaid_students:
            Message.objects.create(
                sender=request.user,
                recipient=student,
                title="To'lov eslatmasi",
                content=f"Hurmatli {student.full_name},\n\nSizning oylik to'lovingiz muddati yaqinlashmoqda. Iltimos, o'z vaqtida to'lov qilishni unutmang.\n\nHurmat bilan,\nIT Creative jamoasi",
                message_type='payment'
            )
            notify_user(
                student.telegram_id,
                f"💳 <b>To'lov eslatmasi</b>\n\n"
                f"Hurmatli {student.full_name},\n\n"
                f"Sizning oylik to'lovingiz muddati yaqinlashmoqda.\n"
                f"Iltimos, o'z vaqtida to'lov qilishni unutmang.\n\n"
                f"🏫 IT Creative jamoasi"
            )
            count += 1
        
        notify_group(
            f"💳 <b>Ommaviy to'lov eslatmasi</b>\n\n"
            f"📊 {count} ta o'quvchiga to'lov eslatmasi yuborildi."
        )
        messages.success(request, f"{count} ta o'quvchiga to'lov eslatmasi yuborildi!")
    
    return redirect('admin_payments')


# ==================== CHEGIRMALAR (SKIDKALAR) ====================

@login_required
def admin_discounts(request):
    if not request.user.is_admin:
        messages.error(request, "Sizda bu sahifaga kirish huquqi yo'q!")
        return redirect('home')
    
    discounts = Discount.objects.select_related('profession').all()
    
    profession_id = request.GET.get('profession')
    if profession_id:
        discounts = discounts.filter(profession_id=profession_id)
    
    status_filter = request.GET.get('status')
    if status_filter == 'active':
        discounts = discounts.filter(is_active=True)
    elif status_filter == 'inactive':
        discounts = discounts.filter(is_active=False)
    
    q = request.GET.get('q')
    if q:
        discounts = discounts.filter(name__icontains=q)
    
    professions = Profession.objects.all()
    
    context = {
        'discounts': discounts,
        'professions': professions,
        'total_discounts': Discount.objects.count(),
        'active_discounts': Discount.objects.filter(is_active=True).count(),
        'inactive_discounts': Discount.objects.filter(is_active=False).count(),
    }
    return render(request, 'accounts/admin/discounts.html', context)


@login_required
def admin_discount_add(request):
    if not request.user.is_admin:
        messages.error(request, "Sizda bu sahifaga kirish huquqi yo'q!")
        return redirect('home')
    
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        description = request.POST.get('description', '').strip()
        discount_type = request.POST.get('discount_type', 'percentage')
        discount_value = request.POST.get('discount_value', 0)
        min_coins_required = request.POST.get('min_coins_required', 0)
        profession_id = request.POST.get('profession')
        is_active = 'is_active' in request.POST
        valid_from = request.POST.get('valid_from') or None
        valid_until = request.POST.get('valid_until') or None
        
        if name and discount_value:
            Discount.objects.create(
                name=name,
                description=description,
                discount_type=discount_type,
                discount_value=int(discount_value),
                min_coins_required=int(min_coins_required) if min_coins_required else 0,
                profession_id=profession_id if profession_id else None,
                is_active=is_active,
                valid_from=valid_from,
                valid_until=valid_until
            )
            messages.success(request, "Chegirma muvaffaqiyatli qo'shildi!")
            return redirect('admin_discounts')
        else:
            messages.error(request, "Chegirma nomi va qiymati kiritilishi shart!")
    
    professions = Profession.objects.all()
    return render(request, 'accounts/admin/discount_form.html', {'professions': professions})


@login_required
def admin_discount_edit(request, pk):
    if not request.user.is_admin:
        messages.error(request, "Sizda bu sahifaga kirish huquqi yo'q!")
        return redirect('home')
    
    discount = get_object_or_404(Discount, pk=pk)
    
    if request.method == 'POST':
        discount.name = request.POST.get('name', '').strip()
        discount.description = request.POST.get('description', '').strip()
        discount.discount_type = request.POST.get('discount_type', 'percentage')
        discount.discount_value = int(request.POST.get('discount_value', 0))
        discount.min_coins_required = int(request.POST.get('min_coins_required', 0) or 0)
        profession_id = request.POST.get('profession')
        discount.profession_id = profession_id if profession_id else None
        discount.is_active = 'is_active' in request.POST
        valid_from = request.POST.get('valid_from')
        valid_until = request.POST.get('valid_until')
        discount.valid_from = valid_from if valid_from else None
        discount.valid_until = valid_until if valid_until else None
        discount.save()
        
        messages.success(request, "Chegirma muvaffaqiyatli yangilandi!")
        return redirect('admin_discounts')
    
    professions = Profession.objects.all()
    return render(request, 'accounts/admin/discount_form.html', {
        'discount': discount,
        'professions': professions,
    })


@login_required
def admin_discount_delete(request, pk):
    if not request.user.is_admin:
        messages.error(request, "Sizda bu sahifaga kirish huquqi yo'q!")
        return redirect('home')
    
    discount = get_object_or_404(Discount, pk=pk)
    
    if request.method == 'POST':
        discount.delete()
        messages.success(request, "Chegirma o'chirildi!")
        return redirect('admin_discounts')
    
    return render(request, 'accounts/admin/discount_delete.html', {'discount': discount})


# ==================== CODING / HTML DEPLOY ====================

@login_required
def my_deploys(request):
    """O'quvchining deploy qilgan sahifalari"""
    deploys = HTMLDeploy.objects.filter(user=request.user)
    return render(request, 'accounts/coding/my_deploys.html', {
        'deploys': deploys,
        'is_premium': request.user.is_premium,
        'user_coins': request.user.coins,
    })


@login_required
def create_deploy(request):
    """Yangi HTML deploy qilish"""
    # Premium tekshiruvi - premium bo'lmaganlar 15 coin to'laydi
    if not request.user.is_premium:
        if request.user.coins < 15:
            messages.error(request, "Sizda yetarli coin yo'q! Deploy qilish uchun 15 coin kerak.")
            return redirect('my_deploys')
    
    import os
    import zipfile
    import shutil
    from django.conf import settings
    
    if request.method == 'POST':
        title = request.POST.get('title', '').strip()
        folder_name = request.POST.get('folder_name', '').strip()
        description = request.POST.get('description', '').strip()
        profession_id = request.POST.get('profession')
        entry_file = request.POST.get('entry_file', 'index.html').strip()
        
        # Fayl yuklash
        uploaded_file = request.FILES.get('uploaded_file')
        html_content = request.POST.get('html_content', '').strip()
        
        if not title or not folder_name:
            messages.error(request, "Loyiha nomi va papka nomini kiriting!")
            return redirect('create_deploy')
        
        # Papka nomini tozalash
        folder_name = folder_name.lower().replace(' ', '_').replace('.', '_')
        
        # Mavjudligini tekshirish
        if HTMLDeploy.objects.filter(user=request.user, folder_name=folder_name).exists():
            messages.error(request, f"'{folder_name}' nomli loyiha allaqachon mavjud!")
            return redirect('create_deploy')
        
        deploy_type = 'html'
        
        if uploaded_file:
            file_name = uploaded_file.name.lower()
            
            # ZIP fayl
            if file_name.endswith('.zip'):
                deploy_type = 'project'
                
                # Papka yaratish
                deploy_folder = os.path.join(settings.MEDIA_ROOT, 'deploys', request.user.username, folder_name)
                
                # Eski papkani o'chirish
                if os.path.exists(deploy_folder):
                    shutil.rmtree(deploy_folder)
                os.makedirs(deploy_folder, exist_ok=True)
                
                # ZIP ni ochish
                try:
                    import tempfile
                    with tempfile.NamedTemporaryFile(delete=False, suffix='.zip') as tmp:
                        for chunk in uploaded_file.chunks():
                            tmp.write(chunk)
                        tmp_path = tmp.name
                    
                    with zipfile.ZipFile(tmp_path, 'r') as zip_ref:
                        # Barcha fayllarni olish (__MACOSX dan boshqa)
                        all_files = [f for f in zip_ref.namelist() if not f.startswith('__MACOSX') and not f.startswith('._')]
                        
                        # HTML fayllarni topish
                        html_files = [f for f in all_files if f.lower().endswith('.html')]
                        
                        if not html_files:
                            messages.error(request, "ZIP ichida HTML fayl topilmadi!")
                            os.unlink(tmp_path)
                            return redirect('create_deploy')
                        
                        # Fayllarni chiqarish
                        for file_info in zip_ref.infolist():
                            if file_info.filename.startswith('__MACOSX') or file_info.filename.startswith('._'):
                                continue
                            
                            # Fayl nomini tozalash (papka prefiksini olib tashlash)
                            original_name = file_info.filename
                            
                            # Agar bitta asosiy papka ichida bo'lsa, uni olib tashlash
                            parts = original_name.split('/')
                            if len(parts) > 1 and parts[0] and not parts[0].endswith('.html'):
                                # Birinchi papkani olib tashlash
                                clean_name = '/'.join(parts[1:])
                            else:
                                clean_name = original_name
                            
                            if not clean_name or clean_name.endswith('/'):
                                continue
                            
                            # Fayl yo'lini yaratish
                            target_path = os.path.join(deploy_folder, clean_name)
                            target_dir = os.path.dirname(target_path)
                            
                            if target_dir and not os.path.exists(target_dir):
                                os.makedirs(target_dir, exist_ok=True)
                            
                            # Faylni yozish
                            with zip_ref.open(file_info) as source, open(target_path, 'wb') as target:
                                target.write(source.read())
                        
                        # Entry file ni aniqlash
                        if not entry_file or entry_file == 'index.html':
                            # Deploy papkasida index.html bormi?
                            if os.path.exists(os.path.join(deploy_folder, 'index.html')):
                                entry_file = 'index.html'
                            else:
                                # Birinchi HTML faylni olish
                                for root, dirs, files in os.walk(deploy_folder):
                                    for f in files:
                                        if f.lower().endswith('.html'):
                                            rel_path = os.path.relpath(os.path.join(root, f), deploy_folder)
                                            entry_file = rel_path.replace('\\', '/')
                                            break
                                    if entry_file != 'index.html':
                                        break
                    
                    os.unlink(tmp_path)
                    
                except Exception as e:
                    messages.error(request, f"ZIP faylni ochishda xato: {str(e)}")
                    if os.path.exists(deploy_folder):
                        shutil.rmtree(deploy_folder)
                    return redirect('create_deploy')
            
            # HTML fayl
            elif file_name.endswith('.html') or file_name.endswith('.htm'):
                html_content = uploaded_file.read().decode('utf-8', errors='ignore')
                entry_file = folder_name + '.html'
            else:
                messages.error(request, "Faqat .html yoki .zip fayllar qabul qilinadi!")
                return redirect('create_deploy')
        
        elif not html_content:
            messages.error(request, "HTML kod yoki fayl yuklang!")
            return redirect('create_deploy')
        
        # Deploy yaratish
        deploy = HTMLDeploy.objects.create(
            user=request.user,
            profession_id=profession_id if profession_id else None,
            title=title,
            deploy_type=deploy_type,
            folder_name=folder_name,
            entry_file=entry_file,
            html_content=html_content if deploy_type == 'html' else None,
            description=description,
        )
        
        # Premium bo'lmaganlardan coin yechish
        if not request.user.is_premium:
            request.user.remove_coins(15, f"'{title}' loyihasini deploy qilish")
        
        # Barcha foydalanuvchilarga xabar yuborish
        all_users = CustomUser.objects.filter(role='student', is_blocked=False).exclude(pk=request.user.pk)
        for user in all_users:
            Message.objects.create(
                sender=request.user,
                recipient=user,
                title=f"🚀 Yangi loyiha: {title}",
                content=f"{request.user.full_name} yangi loyiha ishga tushirdi!\n\n📦 {title}\n\n🔗 Ko'rish uchun: {deploy.get_url()}",
                message_type='system'
            )
        
        # Activity log
        ActivityLog.objects.create(
            user=request.user,
            action_type='deploy_create',
            description=f"'{title}' loyihasini deploy qildi",
            ip_address=request.META.get('REMOTE_ADDR')
        )
        
        messages.success(request, f"Loyiha muvaffaqiyatli deploy qilindi! URL: {deploy.get_url()}")
        return redirect('my_deploys')
    
    professions = Profession.objects.all()
    return render(request, 'accounts/coding/create_deploy.html', {'professions': professions})


@login_required
def edit_deploy(request, pk):
    """Deploy qilingan sahifani tahrirlash"""
    deploy = get_object_or_404(HTMLDeploy, pk=pk, user=request.user)
    
    if request.method == 'POST':
        deploy.title = request.POST.get('title', '').strip()
        deploy.description = request.POST.get('description', '').strip()
        profession_id = request.POST.get('profession')
        deploy.profession_id = profession_id if profession_id else None
        
        # Fayl yuklash yoki matn kiritish
        html_file = request.FILES.get('html_file')
        html_content = request.POST.get('html_content', '').strip()
        
        if html_file:
            deploy.html_content = html_file.read().decode('utf-8', errors='ignore')
        elif html_content:
            deploy.html_content = html_content
        
        deploy.is_active = 'is_active' in request.POST
        deploy.save()
        
        # Activity log
        ActivityLog.objects.create(
            user=request.user,
            action_type='deploy_edit',
            description=f"'{deploy.title}' loyihasini tahrirladi",
            ip_address=request.META.get('REMOTE_ADDR')
        )
        
        messages.success(request, "Sahifa yangilandi!")
        return redirect('my_deploys')
    
    professions = Profession.objects.all()
    return render(request, 'accounts/coding/edit_deploy.html', {
        'deploy': deploy,
        'professions': professions,
    })


@login_required
def delete_deploy(request, pk):
    """Deploy qilingan sahifani o'chirish"""
    import os
    import shutil
    
    deploy = get_object_or_404(HTMLDeploy, pk=pk, user=request.user)
    
    if request.method == 'POST':
        deploy_title = deploy.title
        
        # Agar loyiha bo'lsa, papkani o'chirish
        if deploy.deploy_type == 'project':
            folder_path = deploy.get_folder_path()
            if os.path.exists(folder_path):
                shutil.rmtree(folder_path)
        
        deploy.delete()
        
        # Activity log
        ActivityLog.objects.create(
            user=request.user,
            action_type='deploy_delete',
            description=f"'{deploy_title}' loyihasini o'chirdi",
            ip_address=request.META.get('REMOTE_ADDR')
        )
        
        messages.success(request, "Loyiha o'chirildi!")
        return redirect('my_deploys')
    
    return render(request, 'accounts/coding/delete_deploy.html', {'deploy': deploy})


def view_deployed_page(request, username, folder_name, filepath=None):
    """Deploy qilingan sahifani ko'rsatish (login talab qilinmaydi)"""
    import os
    import mimetypes
    from django.conf import settings
    
    user = get_object_or_404(CustomUser, username=username)
    deploy = get_object_or_404(HTMLDeploy, user=user, folder_name=folder_name, is_active=True)
    
    # Ko'rishlar sonini oshirish (faqat asosiy sahifa uchun)
    if not filepath or filepath == deploy.entry_file:
        deploy.views_count += 1
        deploy.save(update_fields=['views_count'])
    
    # HTML fayl (oddiy deploy)
    if deploy.deploy_type == 'html':
        return HttpResponse(deploy.html_content, content_type='text/html')
    
    # Loyiha (ZIP dan)
    if not filepath:
        filepath = deploy.entry_file
    
    # filepath ni tozalash (/ va \ ni to'g'rilash)
    filepath = filepath.replace('\\', '/').lstrip('/')
    
    # Fayl yo'lini tuzish
    deploy_folder = deploy.get_folder_path()
    file_path = os.path.join(deploy_folder, filepath.replace('/', os.sep))
    
    # Xavfsizlik tekshiruvi - papkadan tashqariga chiqmaslik
    try:
        real_path = os.path.realpath(file_path)
        real_deploy_folder = os.path.realpath(deploy_folder)
        if not real_path.startswith(real_deploy_folder):
            return HttpResponse("Ruxsat berilmagan", status=403)
    except:
        return HttpResponse("Xato yo'l", status=400)
    
    if not os.path.exists(file_path):
        # index.html ni izlash
        possible_index = os.path.join(deploy_folder, 'index.html')
        if os.path.exists(possible_index):
            file_path = possible_index
        else:
            return HttpResponse(f"Fayl topilmadi: {filepath}", status=404)
    
    # MIME turini aniqlash
    mime_type, _ = mimetypes.guess_type(file_path)
    if not mime_type:
        if file_path.endswith('.css'):
            mime_type = 'text/css'
        elif file_path.endswith('.js'):
            mime_type = 'application/javascript'
        elif file_path.endswith('.html') or file_path.endswith('.htm'):
            mime_type = 'text/html'
        elif file_path.endswith('.json'):
            mime_type = 'application/json'
        elif file_path.endswith('.svg'):
            mime_type = 'image/svg+xml'
        else:
            mime_type = 'application/octet-stream'
    
    # Faylni o'qish va qaytarish
    try:
        with open(file_path, 'rb') as f:
            content = f.read()
        return HttpResponse(content, content_type=mime_type)
    except Exception as e:
        return HttpResponse(f"Faylni o'qishda xato: {str(e)}", status=500)


# ==================== ADMIN: HTML DEPLOYS ====================

@login_required
def admin_deploys(request):
    """Admin: Barcha deploylar"""
    if not request.user.is_admin:
        messages.error(request, "Sizda bu sahifaga kirish huquqi yo'q!")
        return redirect('home')
    
    deploys = HTMLDeploy.objects.select_related('user', 'profession').all()
    
    # Filterlar
    user_id = request.GET.get('user')
    if user_id:
        deploys = deploys.filter(user_id=user_id)
    
    status = request.GET.get('status')
    if status == 'active':
        deploys = deploys.filter(is_active=True)
    elif status == 'inactive':
        deploys = deploys.filter(is_active=False)
    
    q = request.GET.get('q')
    if q:
        deploys = deploys.filter(title__icontains=q)
    
    users = CustomUser.objects.filter(deploys__isnull=False).distinct()
    
    context = {
        'deploys': deploys,
        'users': users,
        'total_deploys': HTMLDeploy.objects.count(),
        'active_deploys': HTMLDeploy.objects.filter(is_active=True).count(),
        'total_views': HTMLDeploy.objects.aggregate(total=Sum('views_count'))['total'] or 0,
    }
    return render(request, 'accounts/admin/deploys.html', context)


@login_required
def admin_deploy_toggle(request, pk):
    """Admin: Deploy faolligini o'zgartirish"""
    if not request.user.is_admin:
        return redirect('home')
    
    deploy = get_object_or_404(HTMLDeploy, pk=pk)
    deploy.is_active = not deploy.is_active
    deploy.save()
    
    status = "faollashtirildi" if deploy.is_active else "o'chirildi"
    messages.success(request, f"'{deploy.title}' {status}!")
    return redirect('admin_deploys')


@login_required
def admin_deploy_delete(request, pk):
    """Admin: Deployni o'chirish"""
    if not request.user.is_admin:
        return redirect('home')
    
    deploy = get_object_or_404(HTMLDeploy, pk=pk)
    
    if request.method == 'POST':
        deploy.delete()
        messages.success(request, "Deploy o'chirildi!")
        return redirect('admin_deploys')
    
    return render(request, 'accounts/admin/deploy_delete.html', {'deploy': deploy})


# ==================== ADMIN: DARSLAR STATISTIKASI ====================

@login_required
def admin_lesson_statistics(request):
    if not request.user.is_admin:
        messages.error(request, "Sizda bu sahifaga kirish huquqi yo'q!")
        return redirect('home')
    
    profession_id = request.GET.get('profession')
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    search_query = request.GET.get('q', '')
    
    # Sana filterlari
    if date_from:
        try:
            date_from = timezone.datetime.strptime(date_from, '%Y-%m-%d').date()
        except:
            date_from = None
    if date_to:
        try:
            date_to = timezone.datetime.strptime(date_to, '%Y-%m-%d').date()
        except:
            date_to = None
    
    # ==================== UMUMIY STATISTIKA ====================
    total_lessons = Lesson.objects.count()
    total_video_lessons = Lesson.objects.filter(lesson_type='video').count()
    total_test_lessons = Lesson.objects.filter(lesson_type='test').count()
    total_homework_lessons = Lesson.objects.filter(lesson_type='homework').count()
    
    # Faol o'quvchilar (oxirgi 7 kunda)
    week_ago = timezone.now() - timedelta(days=7)
    active_students = CustomUser.objects.filter(
        role='student', 
        is_blocked=False,
        last_activity__gte=week_ago
    ).count()
    total_students = CustomUser.objects.filter(role='student', is_blocked=False).count()
    
    # Ko'rilgan darslar soni
    total_video_views = VideoProgress.objects.filter(watched=True).count()
    total_test_attempts = TestResult.first_attempts().count()
    total_homework_submissions = HomeworkSubmission.objects.count()
    
    # O'rtacha test bali
    avg_test_score = TestResult.first_attempts().aggregate(avg=Avg('score'))['avg'] or 0
    
    # Tugallangan darslar foizi
    total_possible_views = CourseEnrollment.objects.count() * total_video_lessons if total_video_lessons > 0 else 1
    completion_percent = (total_video_views / total_possible_views * 100) if total_possible_views > 0 else 0
    
    # ==================== KUNLIK FAOLLIK (oxirgi 30 kun) ====================
    thirty_days_ago = timezone.now() - timedelta(days=30)
    daily_activity = []
    for i in range(30):
        day = timezone.now().date() - timedelta(days=29-i)
        day_start = timezone.make_aware(timezone.datetime.combine(day, timezone.datetime.min.time()))
        day_end = timezone.make_aware(timezone.datetime.combine(day, timezone.datetime.max.time()))
        
        videos_watched = VideoProgress.objects.filter(watched_at__range=(day_start, day_end)).count()
        tests_taken = TestResult.objects.filter(completed_at__range=(day_start, day_end)).count()
        homeworks_sent = HomeworkSubmission.objects.filter(submitted_at__range=(day_start, day_end)).count()
        
        daily_activity.append({
            'date': day.strftime('%d.%m'),
            'videos': videos_watched,
            'tests': tests_taken,
            'homeworks': homeworks_sent,
            'total': videos_watched + tests_taken + homeworks_sent
        })
    
    # ==================== BARCHA DARSLAR ====================
    lessons = Lesson.objects.select_related('profession', 'section').all()
    if profession_id:
        lessons = lessons.filter(profession_id=profession_id)
    if search_query:
        lessons = lessons.filter(title__icontains=search_query)
    
    # ==================== VIDEO DARSLAR STATISTIKASI ====================
    video_lessons = lessons.filter(lesson_type='video')
    video_stats = []
    for lesson in video_lessons:
        try:
            video = lesson.video
            total_enrolled = CourseEnrollment.objects.filter(profession=lesson.profession).count()
            
            video_progress_qs = VideoProgress.objects.filter(video=video)
            if date_from:
                video_progress_qs = video_progress_qs.filter(watched_at__date__gte=date_from)
            if date_to:
                video_progress_qs = video_progress_qs.filter(watched_at__date__lte=date_to)
            
            watched_count = video_progress_qs.filter(watched=True).count()
            total_views = video_progress_qs.count()
            not_watched = total_enrolled - watched_count
            completion_rate = (watched_count / total_enrolled * 100) if total_enrolled > 0 else 0
            
            # Kim ko'rmagan
            watched_user_ids = video_progress_qs.filter(watched=True).values_list('user_id', flat=True)
            not_watched_users = CustomUser.objects.filter(
                enrollments__profession=lesson.profession
            ).exclude(pk__in=watched_user_ids)[:5]
            
            video_stats.append({
                'lesson': lesson,
                'total_enrolled': total_enrolled,
                'total_views': total_views,
                'watched': watched_count,
                'not_watched': not_watched,
                'completion_rate': round(completion_rate, 1),
                'not_watched_users': not_watched_users,
            })
        except:
            pass
    
    video_stats_sorted = sorted(video_stats, key=lambda x: x['completion_rate'])
    
    # ==================== TEST STATISTIKASI ====================
    test_lessons = lessons.filter(lesson_type='test')
    test_stats = []
    hardest_questions = []
    
    for lesson in test_lessons:
        try:
            test = lesson.test
            total_enrolled = CourseEnrollment.objects.filter(profession=lesson.profession).count()
            
            results_qs = TestResult.objects.filter(test=test)
            if date_from:
                results_qs = results_qs.filter(completed_at__date__gte=date_from)
            if date_to:
                results_qs = results_qs.filter(completed_at__date__lte=date_to)
            
            completed_count = results_qs.values('student').distinct().count()
            total_attempts = results_qs.count()
            not_completed = total_enrolled - completed_count
            completion_rate = (completed_count / total_enrolled * 100) if total_enrolled > 0 else 0
            
            avg_score = results_qs.aggregate(avg=Avg('score'))['avg'] or 0
            passed_count = results_qs.filter(passed=True).count()
            failed_count = results_qs.filter(passed=False).count()
            pass_rate = (passed_count / total_attempts * 100) if total_attempts > 0 else 0
            
            # Qayta topshirganlar
            retry_students = results_qs.values('student').annotate(
                attempt_count=Count('id')
            ).filter(attempt_count__gt=1).count()
            
            # Kim yechmagan
            completed_user_ids = results_qs.values_list('student_id', flat=True)
            not_completed_users = CustomUser.objects.filter(
                enrollments__profession=lesson.profession
            ).exclude(pk__in=completed_user_ids)[:5]
            
            # Kim o'ta olmadi
            failed_users = CustomUser.objects.filter(
                test_results__test=test,
                test_results__passed=False
            ).distinct()[:5]
            
            test_stats.append({
                'lesson': lesson,
                'test': test,
                'total_enrolled': total_enrolled,
                'completed': completed_count,
                'total_attempts': total_attempts,
                'not_completed': not_completed,
                'completion_rate': round(completion_rate, 1),
                'avg_score': round(avg_score, 1),
                'passed_count': passed_count,
                'failed_count': failed_count,
                'pass_rate': round(pass_rate, 1),
                'retry_students': retry_students,
                'not_completed_users': not_completed_users,
                'failed_users': failed_users,
            })
            
            # Eng qiyin savollar
            for question in test.questions.all():
                total_answered = TestUserAnswer.objects.filter(question=question).count()
                wrong_answers = TestUserAnswer.objects.filter(question=question, is_correct=False).count()
                if total_answered > 0:
                    error_rate = (wrong_answers / total_answered * 100)
                    if error_rate > 40:
                        hardest_questions.append({
                            'question': question,
                            'test': test,
                            'total_answered': total_answered,
                            'wrong_count': wrong_answers,
                            'error_rate': round(error_rate, 1),
                        })
        except:
            pass
    
    test_stats_sorted = sorted(test_stats, key=lambda x: x['avg_score'])
    hardest_questions = sorted(hardest_questions, key=lambda x: x['error_rate'], reverse=True)[:15]
    
    # ==================== UY VAZIFASI STATISTIKASI ====================
    homework_lessons = lessons.filter(lesson_type='homework')
    homework_stats = []
    for lesson in homework_lessons:
        try:
            homework = lesson.homework
            total_enrolled = CourseEnrollment.objects.filter(profession=lesson.profession).count()
            
            submissions_qs = HomeworkSubmission.objects.filter(homework=homework)
            if date_from:
                submissions_qs = submissions_qs.filter(submitted_at__date__gte=date_from)
            if date_to:
                submissions_qs = submissions_qs.filter(submitted_at__date__lte=date_to)
            
            submitted_count = submissions_qs.values('student').distinct().count()
            not_submitted = total_enrolled - submitted_count
            completion_rate = (submitted_count / total_enrolled * 100) if total_enrolled > 0 else 0
            
            avg_grade = submissions_qs.filter(grade__isnull=False).aggregate(avg=Avg('grade'))['avg'] or 0
            pending_count = submissions_qs.filter(status='pending').count()
            graded_count = submissions_qs.filter(status='graded').count()
            
            # Kim topshirmagan
            submitted_user_ids = submissions_qs.values_list('student_id', flat=True)
            not_submitted_users = CustomUser.objects.filter(
                enrollments__profession=lesson.profession
            ).exclude(pk__in=submitted_user_ids)[:5]
            
            homework_stats.append({
                'lesson': lesson,
                'homework': homework,
                'total_enrolled': total_enrolled,
                'submitted': submitted_count,
                'not_submitted': not_submitted,
                'completion_rate': round(completion_rate, 1),
                'avg_grade': round(avg_grade, 1),
                'pending_count': pending_count,
                'graded_count': graded_count,
                'not_submitted_users': not_submitted_users,
            })
        except:
            pass
    
    homework_stats_sorted = sorted(homework_stats, key=lambda x: x['completion_rate'])
    
    # ==================== O'QUVCHILAR FAOLLIGI ====================
    # Passiv o'quvchilar - oxirgi 7 kunda faollik ko'rsatmaganlar
    passive_students = CustomUser.objects.filter(
        role='student',
        is_blocked=False
    ).filter(
        Q(last_activity__lt=week_ago) | Q(last_activity__isnull=True)
    ).order_by('last_activity')[:20]
    
    # Qiynalayotgan o'quvchilar - testlardan past ball olganlar
    struggling_students = CustomUser.objects.filter(
        role='student',
        test_results__score__lt=50
    ).annotate(
        low_score_count=Count('test_results', filter=Q(test_results__score__lt=50)),
        avg_score=Avg('test_results__score')
    ).filter(low_score_count__gte=2).order_by('-low_score_count')[:15]
    
    # ==================== TOP DARSLAR ====================
    top_video_lessons = sorted(video_stats, key=lambda x: x['watched'], reverse=True)[:10]
    top_test_lessons = sorted(test_stats, key=lambda x: x['total_attempts'], reverse=True)[:10]
    
    # ==================== SERTIFIKATGA YAQIN O'QUVCHILAR ====================
    near_certificate_students = []
    for profession in Profession.objects.all():
        total_lessons_in_course = profession.lessons.exclude(lesson_type='dictionary').count()
        if total_lessons_in_course == 0:
            continue
            
        enrolled_students = CustomUser.objects.filter(enrollments__profession=profession)
        for student in enrolled_students:
            # Video progress
            videos_watched = VideoProgress.objects.filter(
                user=student,
                video__lesson__profession=profession,
                watched=True
            ).count()
            # Tests passed
            tests_passed = TestResult.objects.filter(
                student=student,
                test__lesson__profession=profession,
                passed=True
            ).values('test').distinct().count()
            # Homework graded
            homework_done = HomeworkSubmission.objects.filter(
                student=student,
                homework__lesson__profession=profession,
                status='graded'
            ).values('homework').distinct().count()
            
            total_done = videos_watched + tests_passed + homework_done
            progress = (total_done / total_lessons_in_course * 100) if total_lessons_in_course > 0 else 0
            
            if 70 <= progress < 100:
                near_certificate_students.append({
                    'student': student,
                    'profession': profession,
                    'progress': round(progress, 1),
                    'remaining': total_lessons_in_course - total_done,
                })
    
    near_certificate_students = sorted(near_certificate_students, key=lambda x: x['progress'], reverse=True)[:10]
    
    # ==================== SMART ALERTS ====================
    alerts = []
    
    # 7 kun kirmagan o'quvchilar
    inactive_count = passive_students.count()
    if inactive_count > 0:
        alerts.append({
            'type': 'warning',
            'icon': 'bi-clock-history',
            'title': f'{inactive_count} ta o\'quvchi 7+ kun kirmagan',
            'description': 'Bu o\'quvchilarga eslatma yuborishni o\'ylab ko\'ring.',
        })
    
    # Testdan o'ta olmayotganlar
    struggling_count = struggling_students.count()
    if struggling_count > 0:
        alerts.append({
            'type': 'danger',
            'icon': 'bi-exclamation-triangle',
            'title': f'{struggling_count} ta o\'quvchi testlardan qiynalmoqda',
            'description': 'Bu o\'quvchilarga qo\'shimcha yordam kerak bo\'lishi mumkin.',
        })
    
    # Past tugallash darajasidagi darslar
    low_completion_lessons = [v for v in video_stats if v['completion_rate'] < 30]
    if len(low_completion_lessons) > 0:
        alerts.append({
            'type': 'info',
            'icon': 'bi-camera-video-off',
            'title': f'{len(low_completion_lessons)} ta video dars kam ko\'rilmoqda',
            'description': 'Bu darslar kontentini tekshirib ko\'ring.',
        })
    
    # Tekshirilmagan uy vazifalari
    pending_hw_count = HomeworkSubmission.objects.filter(status='pending').count()
    if pending_hw_count > 0:
        alerts.append({
            'type': 'primary',
            'icon': 'bi-journal-text',
            'title': f'{pending_hw_count} ta uy vazifasi tekshirilmagan',
            'description': 'Uy vazifalarini baholash kutilmoqda.',
        })
    
    professions = Profession.objects.all()
    
    context = {
        # Umumiy statistika
        'total_lessons': total_lessons,
        'total_video_lessons': total_video_lessons,
        'total_test_lessons': total_test_lessons,
        'total_homework_lessons': total_homework_lessons,
        'active_students': active_students,
        'total_students': total_students,
        'total_video_views': total_video_views,
        'total_test_attempts': total_test_attempts,
        'total_homework_submissions': total_homework_submissions,
        'avg_test_score': round(avg_test_score, 1),
        'completion_percent': round(completion_percent, 1),
        
        # Kunlik faollik
        'daily_activity': daily_activity,
        
        # Darslar statistikasi
        'video_stats': video_stats_sorted,
        'test_stats': test_stats_sorted,
        'homework_stats': homework_stats_sorted,
        'hardest_questions': hardest_questions,
        
        # O'quvchilar
        'passive_students': passive_students,
        'struggling_students': struggling_students,
        'near_certificate_students': near_certificate_students,
        
        # Top darslar
        'top_video_lessons': top_video_lessons,
        'top_test_lessons': top_test_lessons,
        
        # Alerts
        'alerts': alerts,
        
        # Filterlar
        'professions': professions,
        'selected_profession': profession_id,
        'date_from': date_from,
        'date_to': date_to,
        'search_query': search_query,
    }
    
    return render(request, 'accounts/admin/lesson_statistics.html', context)


# ==================== QURILMALAR BOSHQARUVI ====================

@login_required
def my_devices(request):
    devices = request.user.devices.filter(is_active=True).order_by('-last_login')
    current_session_key = request.session.session_key
    
    # Find current device
    current_device = None
    for device in devices:
        active_session = device.sessions.filter(session_key=current_session_key, is_active=True).first()
        if active_session:
            current_device = device
            break
    
    return render(request, 'accounts/devices.html', {
        'devices': devices,
        'current_device': current_device,
    })


@login_required
def remove_device(request, pk):
    if request.method != 'POST':
        return redirect('my_devices')
    
    device = get_object_or_404(UserDevice, pk=pk, user=request.user)
    current_session_key = request.session.session_key
    
    # Check if it's the current device
    is_current = device.sessions.filter(session_key=current_session_key, is_active=True).exists()
    
    if is_current:
        messages.error(request, "Joriy qurilmani o'chirib bo'lmaydi!")
        return redirect('my_devices')
    
    # Delete all sessions for this device (so user gets logged out)
    from django.contrib.sessions.models import Session
    
    # Get session keys for this device
    session_keys = list(device.sessions.values_list('session_key', flat=True))
    
    # Delete Django sessions
    Session.objects.filter(session_key__in=session_keys).delete()
    
    # Delete custom sessions
    device.sessions.all().delete()
    device.is_active = False
    device.save()
    
    messages.success(request, f"'{device.device_name}' qurilmasi o'chirildi!")
    return redirect('my_devices')


@login_required
def logout_device(request, pk):
    if request.method != 'POST':
        return redirect('my_devices')
    
    device = get_object_or_404(UserDevice, pk=pk, user=request.user)
    current_session_key = request.session.session_key
    
    # Check if it's the current device
    is_current = device.sessions.filter(session_key=current_session_key, is_active=True).exists()
    
    if is_current:
        messages.error(request, "Joriy qurilmadan chiqish uchun 'Chiqish' tugmasini ishlating!")
        return redirect('my_devices')
    
    # Delete all active sessions for this device (so user gets logged out)
    from django.contrib.sessions.models import Session
    
    # Get active session keys for this device
    active_session_keys = list(device.sessions.filter(is_active=True).values_list('session_key', flat=True))
    
    # Delete Django sessions
    Session.objects.filter(session_key__in=active_session_keys).delete()
    
    # Update custom sessions
    device.sessions.filter(is_active=True).update(is_active=False)
    
    messages.success(request, f"'{device.device_name}' qurilmasidan chiqildi!")
    return redirect('my_devices')


@login_required
def trust_device(request, pk):
    device = get_object_or_404(UserDevice, pk=pk, user=request.user)
    device.is_trusted = not device.is_trusted
    device.save()
    
    if device.is_trusted:
        messages.success(request, f"'{device.device_name}' ishonchli qurilma sifatida belgilandi!")
    else:
        messages.success(request, f"'{device.device_name}' ishonchli qurilmalar ro'yxatidan chiqarildi!")
    
    return redirect('my_devices')


@login_required
def logout_all_devices(request):
    if request.method == 'POST':
        from django.contrib.sessions.models import Session
        current_session_key = request.session.session_key
        
        sessions_to_kill = UserSession.objects.filter(
            user=request.user, is_active=True
        ).exclude(session_key=current_session_key)
        
        keys_to_kill = list(sessions_to_kill.values_list('session_key', flat=True))
        Session.objects.filter(session_key__in=keys_to_kill).delete()
        sessions_to_kill.update(is_active=False)
        
        messages.success(request, "Barcha boshqa qurilmalardan chiqildi!")
    
    return redirect('my_devices')


@login_required
def remove_all_devices(request):
    """Joriy qurilmadan tashqari barcha qurilmalarni o'chirish"""
    if request.method == 'POST':
        from django.contrib.sessions.models import Session
        current_session_key = request.session.session_key
        
        # Joriy qurilmani aniqlash
        current_session = UserSession.objects.filter(
            user=request.user, session_key=current_session_key, is_active=True
        ).select_related('device').first()
        current_device = current_session.device if current_session else None
        
        # Boshqa qurilmalarni olish
        other_devices = UserDevice.objects.filter(user=request.user, is_active=True)
        if current_device:
            other_devices = other_devices.exclude(pk=current_device.pk)
        
        # Sessiyalarni o'chirish
        for device in other_devices:
            session_keys = list(device.sessions.filter(is_active=True).values_list('session_key', flat=True))
            Session.objects.filter(session_key__in=session_keys).delete()
            device.sessions.filter(is_active=True).update(is_active=False)
        
        count = other_devices.count()
        other_devices.update(is_active=False)
        
        messages.success(request, f"{count} ta qurilma o'chirildi!")
    
    return redirect('my_devices')


@login_required
def bulk_remove_devices(request):
    """Tanlangan qurilmalarni o'chirish"""
    if request.method == 'POST':
        from django.contrib.sessions.models import Session
        current_session_key = request.session.session_key
        device_ids = request.POST.getlist('device_ids')
        
        if not device_ids:
            messages.error(request, "Hech qanday qurilma tanlanmadi!")
            return redirect('my_devices')
        
        # Joriy qurilmani aniqlash
        current_session = UserSession.objects.filter(
            user=request.user, session_key=current_session_key, is_active=True
        ).select_related('device').first()
        current_device_pk = current_session.device.pk if current_session and current_session.device else None
        
        removed = 0
        for device_id in device_ids:
            try:
                device = UserDevice.objects.get(pk=int(device_id), user=request.user, is_active=True)
            except (UserDevice.DoesNotExist, ValueError):
                continue
            
            # Joriy qurilmani o'chirib bo'lmaydi
            if current_device_pk and device.pk == current_device_pk:
                continue
            
            session_keys = list(device.sessions.filter(is_active=True).values_list('session_key', flat=True))
            Session.objects.filter(session_key__in=session_keys).delete()
            device.sessions.filter(is_active=True).update(is_active=False)
            device.is_active = False
            device.save(update_fields=['is_active'])
            removed += 1
        
        if removed:
            messages.success(request, f"{removed} ta qurilma o'chirildi!")
        else:
            messages.error(request, "Joriy qurilmani o'chirib bo'lmaydi!")
    
    return redirect('my_devices')


# ==================== ADMIN: QURILMALAR ====================

@login_required
def admin_user_devices(request, pk):
    if not request.user.is_admin:
        messages.error(request, "Sizda bu sahifaga kirish huquqi yo'q!")
        return redirect('home')
    
    user = get_object_or_404(CustomUser, pk=pk)
    devices = user.devices.filter(is_active=True).order_by('-last_login')
    active_sessions = UserSession.objects.filter(user=user, is_active=True)
    
    return render(request, 'accounts/admin/user_devices.html', {
        'target_user': user,
        'devices': devices,
        'active_sessions': active_sessions,
    })


@login_required
def admin_logout_user_device(request, user_pk, device_pk):
    if not request.user.is_admin:
        messages.error(request, "Sizda bu sahifaga kirish huquqi yo'q!")
        return redirect('home')
    
    device = get_object_or_404(UserDevice, pk=device_pk, user_id=user_pk)
    device.sessions.filter(is_active=True).update(is_active=False)
    
    messages.success(request, f"'{device.device_name}' qurilmasidan chiqildi!")
    return redirect('admin_user_devices', pk=user_pk)


@login_required
def admin_logout_all_user_devices(request, pk):
    if not request.user.is_admin:
        messages.error(request, "Sizda bu sahifaga kirish huquqi yo'q!")
        return redirect('home')
    
    if request.method == 'POST':
        user = get_object_or_404(CustomUser, pk=pk)
        UserSession.objects.filter(user=user, is_active=True).update(is_active=False)
        messages.success(request, f"{user.full_name}ning barcha qurilmalaridan chiqildi!")
    
    return redirect('admin_user_devices', pk=pk)


# ============ SYSTEM REPORTS ============
@login_required
def admin_reports(request):
    """Oylik hisobotlar ro'yxati"""
    if not request.user.is_admin:
        messages.error(request, "Sizda bu sahifaga kirish huquqi yo'q!")
        return redirect('home')
    
    reports = SystemReport.objects.all()
    
    # Filter by type
    report_type = request.GET.get('type')
    if report_type:
        reports = reports.filter(report_type=report_type)
    
    return render(request, 'accounts/admin/reports.html', {'reports': reports})


@login_required
def generate_report(request):
    """Yangi hisobot yaratish"""
    if not request.user.is_admin:
        messages.error(request, "Sizda bu sahifaga kirish huquqi yo'q!")
        return redirect('home')
    
    if request.method == 'POST':
        report_type = request.POST.get('report_type', 'monthly')
        date_from_str = request.POST.get('date_from')
        date_to_str = request.POST.get('date_to')
        
        from datetime import datetime
        
        if date_from_str and date_to_str:
            date_from = datetime.strptime(date_from_str, '%Y-%m-%d').date()
            date_to = datetime.strptime(date_to_str, '%Y-%m-%d').date()
        else:
            # Default: oxirgi bir oy
            date_to = timezone.now().date()
            if report_type == 'weekly':
                date_from = date_to - timedelta(days=7)
            elif report_type == 'daily':
                date_from = date_to
            else:  # monthly
                date_from = date_to - timedelta(days=30)
        
        # Hisobot nomini yaratish
        type_names = {'daily': 'Kunlik', 'weekly': 'Haftalik', 'monthly': 'Oylik', 'custom': 'Maxsus'}
        title = f"{type_names.get(report_type, 'Hisobot')} hisobot - {date_from.strftime('%d.%m.%Y')} - {date_to.strftime('%d.%m.%Y')}"
        
        # Statistikalarni yig'ish
        # Umumiy
        total_users = CustomUser.objects.count()
        total_students = CustomUser.objects.filter(role='student').count()
        total_teachers = CustomUser.objects.filter(role='teacher').count()
        new_users = CustomUser.objects.filter(date_joined__date__gte=date_from, date_joined__date__lte=date_to).count()
        
        total_courses = Profession.objects.count()
        total_lessons = Lesson.objects.count()
        total_videos = VideoLesson.objects.count()
        total_tests = Test.objects.count()
        total_homeworks = Homework.objects.count()
        
        # Davr ichida
        new_enrollments = CourseEnrollment.objects.filter(enrolled_at__date__gte=date_from, enrolled_at__date__lte=date_to).count()
        test_submissions = TestResult.objects.filter(completed_at__date__gte=date_from, completed_at__date__lte=date_to).count()
        homework_submissions = HomeworkSubmission.objects.filter(submitted_at__date__gte=date_from, submitted_at__date__lte=date_to).count()
        video_views = VideoProgress.objects.filter(watched_at__date__gte=date_from, watched_at__date__lte=date_to, watched=True).count()
        
        # Deploy
        total_deploys = HTMLDeploy.objects.count()
        new_deploys = HTMLDeploy.objects.filter(created_at__date__gte=date_from, created_at__date__lte=date_to).count()
        deploy_views = HTMLDeploy.objects.aggregate(total=Sum('views_count'))['total'] or 0
        
        # Coin
        total_coins = CustomUser.objects.aggregate(total=Sum('coins'))['total'] or 0
        coins_earned = CoinTransaction.objects.filter(
            action='add',
            created_at__date__gte=date_from,
            created_at__date__lte=date_to
        ).aggregate(total=Sum('amount'))['total'] or 0
        coins_spent = CoinTransaction.objects.filter(
            action__in=['remove', 'purchase'],
            created_at__date__gte=date_from,
            created_at__date__lte=date_to
        ).aggregate(total=Sum('amount'))['total'] or 0
        
        # Sertifikat
        total_certificates = Certificate.objects.count()
        new_certificates = Certificate.objects.filter(issued_at__date__gte=date_from, issued_at__date__lte=date_to).count()
        
        # Harakatlar
        total_activities = ActivityLog.objects.filter(created_at__date__gte=date_from, created_at__date__lte=date_to).count()
        
        # Report yaratish
        report = SystemReport.objects.create(
            title=title,
            report_type=report_type,
            date_from=date_from,
            date_to=date_to,
            total_users=total_users,
            total_students=total_students,
            total_teachers=total_teachers,
            new_users=new_users,
            total_courses=total_courses,
            total_lessons=total_lessons,
            total_videos=total_videos,
            total_tests=total_tests,
            total_homeworks=total_homeworks,
            new_enrollments=new_enrollments,
            test_submissions=test_submissions,
            homework_submissions=homework_submissions,
            video_views=video_views,
            total_deploys=total_deploys,
            new_deploys=new_deploys,
            deploy_views=deploy_views,
            total_coins=total_coins,
            coins_earned=coins_earned,
            coins_spent=abs(coins_spent),
            total_certificates=total_certificates,
            new_certificates=new_certificates,
            total_activities=total_activities,
            created_by=request.user,
        )
        
        # PDF yaratish
        generate_report_pdf(report)
        
        messages.success(request, f"'{title}' hisoboti muvaffaqiyatli yaratildi!")
        return redirect('admin_reports')
    
    return render(request, 'accounts/admin/generate_report.html')


def generate_report_pdf(report):
    """Hisobot uchun PDF yaratish"""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from io import BytesIO
    from django.core.files.base import ContentFile
    
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=30, bottomMargin=30)
    elements = []
    styles = getSampleStyleSheet()
    
    heading_style = ParagraphStyle(
        'CustomHeading',
        parent=styles['Heading2'],
        spaceAfter=10,
        spaceBefore=20,
        textColor=colors.HexColor('#0d6efd')
    )
    
    def create_table(data, col_widths=None):
        if col_widths is None:
            col_widths = [300, 150]
        table = Table(data, colWidths=col_widths)
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0d6efd')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#dee2e6')),
            ('PADDING', (0, 0), (-1, -1), 8),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('ALIGN', (1, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8f9fa')]),
        ]))
        return table
    
    # Title
    elements.append(Paragraph(report.title, styles['Title']))
    elements.append(Paragraph(f"Davr: {report.date_from.strftime('%d.%m.%Y')} - {report.date_to.strftime('%d.%m.%Y')}", styles['Normal']))
    elements.append(Paragraph(f"Yaratilgan: {report.created_at.strftime('%d.%m.%Y %H:%M')}", styles['Normal']))
    elements.append(Spacer(1, 20))
    
    # 1. Foydalanuvchilar
    elements.append(Paragraph("1. Foydalanuvchilar statistikasi", heading_style))
    user_data = [
        ["Ko'rsatkich", 'Soni'],
        ['Jami foydalanuvchilar', str(report.total_users)],
        ["O'quvchilar", str(report.total_students)],
        ["O'qituvchilar", str(report.total_teachers)],
        ['Yangi foydalanuvchilar (davr)', str(report.new_users)],
    ]
    elements.append(create_table(user_data))
    elements.append(Spacer(1, 15))
    
    # 2. Kurslar
    elements.append(Paragraph("2. Kurslar va darslar", heading_style))
    course_data = [
        ["Ko'rsatkich", 'Soni'],
        ['Jami kurslar', str(report.total_courses)],
        ['Jami darslar', str(report.total_lessons)],
        ['Videodarslar', str(report.total_videos)],
        ['Testlar', str(report.total_tests)],
        ['Uy vazifalari', str(report.total_homeworks)],
    ]
    elements.append(create_table(course_data))
    elements.append(Spacer(1, 15))
    
    # 3. Davr faoliyati
    elements.append(Paragraph("3. Davr faoliyati", heading_style))
    activity_data = [
        ["Ko'rsatkich", 'Soni'],
        ['Yangi yozilishlar', str(report.new_enrollments)],
        ['Test topshiruvlar', str(report.test_submissions)],
        ['Vazifa topshiruvlar', str(report.homework_submissions)],
        ["Video ko'rishlar", str(report.video_views)],
        ['Jami harakatlar', str(report.total_activities)],
    ]
    elements.append(create_table(activity_data))
    elements.append(Spacer(1, 15))
    
    # 4. Deploy
    elements.append(Paragraph("4. Coding / Deploy", heading_style))
    deploy_data = [
        ["Ko'rsatkich", 'Soni'],
        ['Jami loyihalar', str(report.total_deploys)],
        ['Yangi loyihalar (davr)', str(report.new_deploys)],
        ["Jami ko'rishlar", str(report.deploy_views)],
    ]
    elements.append(create_table(deploy_data))
    elements.append(Spacer(1, 15))
    
    # 5. Coinlar
    elements.append(Paragraph("5. Coin statistikasi", heading_style))
    coin_data = [
        ["Ko'rsatkich", 'Qiymat'],
        ['Jami coinlar (hozir)', str(report.total_coins)],
        ['Ishlangan coinlar (davr)', str(report.coins_earned)],
        ['Sarflangan coinlar (davr)', str(report.coins_spent)],
    ]
    elements.append(create_table(coin_data))
    elements.append(Spacer(1, 15))
    
    # 6. Sertifikatlar
    elements.append(Paragraph("6. Sertifikatlar", heading_style))
    cert_data = [
        ["Ko'rsatkich", 'Soni'],
        ['Jami sertifikatlar', str(report.total_certificates)],
        ['Yangi sertifikatlar (davr)', str(report.new_certificates)],
    ]
    elements.append(create_table(cert_data))
    
    doc.build(elements)
    
    # PDF faylni saqlash
    pdf_content = buffer.getvalue()
    buffer.close()
    
    filename = f"report_{report.report_type}_{report.date_from}_{report.date_to}.pdf"
    report.pdf_file.save(filename, ContentFile(pdf_content))
    report.save()


@login_required
def download_report(request, pk):
    """Hisobotni PDF sifatida yuklab olish"""
    if not request.user.is_admin:
        messages.error(request, "Sizda bu sahifaga kirish huquqi yo'q!")
        return redirect('home')
    
    report = get_object_or_404(SystemReport, pk=pk)
    
    if not report.pdf_file:
        # PDF mavjud bo'lmasa, yaratish
        generate_report_pdf(report)
    
    response = HttpResponse(report.pdf_file.read(), content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{report.title}.pdf"'
    return response


@login_required
def delete_report(request, pk):
    """Hisobotni o'chirish"""
    if not request.user.is_admin:
        messages.error(request, "Sizda bu sahifaga kirish huquqi yo'q!")
        return redirect('home')
    
    report = get_object_or_404(SystemReport, pk=pk)
    
    if request.method == 'POST':
        # PDF faylni ham o'chirish
        if report.pdf_file:
            report.pdf_file.delete()
        report.delete()
        messages.success(request, "Hisobot o'chirildi!")
    
    return redirect('admin_reports')


@login_required
def view_report(request, pk):
    """Hisobotni ko'rish"""
    if not request.user.is_admin:
        messages.error(request, "Sizda bu sahifaga kirish huquqi yo'q!")
        return redirect('home')
    
    report = get_object_or_404(SystemReport, pk=pk)
    return render(request, 'accounts/admin/view_report.html', {'report': report})


# ============ KURSGA YOZILISH SO'ROVLARI ============

@login_required
def admin_enrollment_requests(request):
    """Admin: Kursga yozilish so'rovlarini ko'rish"""
    if not request.user.is_admin:
        messages.error(request, "Sizda bu sahifaga kirish huquqi yo'q!")
        return redirect('home')
    
    status_filter = request.GET.get('status', 'pending')
    profession_filter = request.GET.get('profession')
    search = request.GET.get('q')
    
    tab = request.GET.get('tab', 'enroll')  # 'enroll' yoki 'unenroll'
    
    requests_qs = CourseEnrollmentRequest.objects.select_related('user', 'profession')
    
    if status_filter:
        requests_qs = requests_qs.filter(status=status_filter)
    
    if profession_filter:
        requests_qs = requests_qs.filter(profession_id=profession_filter)
    
    if search:
        requests_qs = requests_qs.filter(
            Q(user__first_name__icontains=search) |
            Q(user__last_name__icontains=search) |
            Q(user__phone__icontains=search)
        )
    
    # Kursdan chiqish so'rovlari
    unenroll_qs = CourseUnenrollRequest.objects.select_related('user', 'profession')
    if status_filter:
        unenroll_qs = unenroll_qs.filter(status=status_filter)
    if profession_filter:
        unenroll_qs = unenroll_qs.filter(profession_id=profession_filter)
    if search:
        unenroll_qs = unenroll_qs.filter(
            Q(user__first_name__icontains=search) |
            Q(user__last_name__icontains=search) |
            Q(user__phone__icontains=search)
        )
    
    professions = Profession.objects.all()
    pending_count = CourseEnrollmentRequest.objects.filter(status='pending').count()
    approved_count = CourseEnrollmentRequest.objects.filter(status='approved').count()
    rejected_count = CourseEnrollmentRequest.objects.filter(status='rejected').count()
    
    unenroll_pending = CourseUnenrollRequest.objects.filter(status='pending').count()
    unenroll_approved = CourseUnenrollRequest.objects.filter(status='approved').count()
    unenroll_rejected = CourseUnenrollRequest.objects.filter(status='rejected').count()
    
    context = {
        'enrollment_requests': requests_qs,
        'unenroll_requests': unenroll_qs,
        'professions': professions,
        'status_filter': status_filter,
        'profession_filter': profession_filter,
        'search': search,
        'tab': tab,
        'pending_count': pending_count,
        'approved_count': approved_count,
        'rejected_count': rejected_count,
        'unenroll_pending': unenroll_pending,
        'unenroll_approved': unenroll_approved,
        'unenroll_rejected': unenroll_rejected,
    }
    return render(request, 'accounts/admin/enrollment_requests.html', context)


@login_required
def approve_enrollment_request(request, pk):
    """Admin: So'rovni qabul qilish"""
    if not request.user.is_admin:
        messages.error(request, "Sizda bu sahifaga kirish huquqi yo'q!")
        return redirect('home')
    
    enrollment_request = get_object_or_404(CourseEnrollmentRequest, pk=pk)
    
    if request.method == 'POST':
        enrollment_request.status = 'approved'
        enrollment_request.reviewed_by = request.user
        enrollment_request.save()
        
        # Eski chiqish so'rovlarini tozalash
        CourseUnenrollRequest.objects.filter(
            user=enrollment_request.user, profession=enrollment_request.profession
        ).delete()
        
        # Kursga yozish
        _, created = CourseEnrollment.objects.get_or_create(
            user=enrollment_request.user,
            profession=enrollment_request.profession
        )
        if created:
            # Qayta yozilish bo'lsa — eski progressni tozalash
            _reset_course_progress(enrollment_request.user, enrollment_request.profession)
        
        # Foydalanuvchiga xabar yuborish
        Message.objects.create(
            title=f"Kursga qabul qilindingiz!",
            content=f"Sizning '{enrollment_request.profession.name}' kursiga yozilish so'rovingiz qabul qilindi. Endi o'qishni boshlashingiz mumkin!",
            message_type='student',
            recipient=enrollment_request.user,
            sender=request.user
        )
        
        if enrollment_request.user.telegram_id:
            notify_user(
                enrollment_request.user.telegram_id,
                f"✅ <b>Kursga qabul qilindingiz!</b>\n\n"
                f"📖 <b>{enrollment_request.profession.name}</b>\n\n"
                f"🎉 So'rovingiz tasdiqlandi. Endi o'qishni boshlashingiz mumkin!"
            )
        
        messages.success(request, f"{enrollment_request.user.full_name} - {enrollment_request.profession.name} kursiga qabul qilindi!")
    
    return redirect('admin_enrollment_requests')


@login_required
def reject_enrollment_request(request, pk):
    """Admin: So'rovni rad etish"""
    if not request.user.is_admin:
        messages.error(request, "Sizda bu sahifaga kirish huquqi yo'q!")
        return redirect('home')
    
    enrollment_request = get_object_or_404(CourseEnrollmentRequest, pk=pk)
    
    if request.method == 'POST':
        admin_message = request.POST.get('admin_message', "Sizga ushbu kursni o'qish imkoniyati berilmadi.")
        
        enrollment_request.status = 'rejected'
        enrollment_request.admin_message = admin_message
        enrollment_request.reviewed_by = request.user
        enrollment_request.save()
        
        # Foydalanuvchiga xabar yuborish
        Message.objects.create(
            title=f"Kursga yozilish so'rovi rad etildi",
            content=f"Sizning '{enrollment_request.profession.name}' kursiga yozilish so'rovingiz rad etildi.\n\nSabab: {admin_message}",
            message_type='student',
            recipient=enrollment_request.user,
            sender=request.user
        )
        
        if enrollment_request.user.telegram_id:
            notify_user(
                enrollment_request.user.telegram_id,
                f"❌ <b>Kursga yozilish rad etildi</b>\n\n"
                f"📖 <b>{enrollment_request.profession.name}</b>\n\n"
                f"📝 Sabab: {admin_message[:300]}"
            )
        
        messages.warning(request, f"{enrollment_request.user.full_name} - {enrollment_request.profession.name} so'rovi rad etildi!")
    
    return redirect('admin_enrollment_requests')


@login_required
def admin_unenroll_requests(request):
    """Admin: Kursdan chiqish so'rovlari"""
    if not request.user.is_admin:
        messages.error(request, "Sizda bu sahifaga kirish huquqi yo'q!")
        return redirect('home')

    status_filter = request.GET.get('status', 'pending')
    requests_qs = CourseUnenrollRequest.objects.select_related('user', 'profession')

    if status_filter:
        requests_qs = requests_qs.filter(status=status_filter)

    pending_count = CourseUnenrollRequest.objects.filter(status='pending').count()
    approved_count = CourseUnenrollRequest.objects.filter(status='approved').count()
    rejected_count = CourseUnenrollRequest.objects.filter(status='rejected').count()

    context = {
        'unenroll_requests': requests_qs,
        'status_filter': status_filter,
        'pending_count': pending_count,
        'approved_count': approved_count,
        'rejected_count': rejected_count,
    }
    return render(request, 'accounts/admin/unenroll_requests.html', context)


@login_required
def approve_unenroll_request(request, pk):
    """Admin: Kursdan chiqish so'rovini tasdiqlash"""
    if not request.user.is_admin:
        return redirect('home')

    unenroll_req = get_object_or_404(CourseUnenrollRequest, pk=pk)

    if request.method == 'POST':
        unenroll_req.status = 'approved'
        unenroll_req.reviewed_by = request.user
        unenroll_req.save()

        # Kurs darslaridan olingan coinlarni hisoblash
        course_lessons = Lesson.objects.filter(profession=unenroll_req.profession)
        lesson_titles = list(course_lessons.values_list('title', flat=True))
        
        total_coins_earned = 0
        if lesson_titles:
            q_filter = Q()
            for title in lesson_titles:
                q_filter |= Q(reason__icontains=title)
            
            coin_sum = CoinTransaction.objects.filter(
                user=unenroll_req.user,
                action='add',
            ).filter(q_filter).aggregate(total=Sum('amount'))
            total_coins_earned = coin_sum['total'] or 0
        
        # Kurs bo'yicha ball (baho) larni hisoblash
        hw_grades_count = HomeworkSubmission.objects.filter(
            student=unenroll_req.user,
            homework__lesson__profession=unenroll_req.profession,
            status='graded'
        ).count()
        
        test_results_count = TestResult.objects.filter(
            student=unenroll_req.user,
            test__lesson__profession=unenroll_req.profession,
        ).count()
        
        # Coinlarni ayirish
        if total_coins_earned > 0:
            unenroll_req.user.remove_coins(
                total_coins_earned,
                f"Kursdan chiqish ({unenroll_req.profession.name}) - olingan coinlar qaytarildi"
            )

        # Kursdan chiqarish
        CourseEnrollment.objects.filter(user=unenroll_req.user, profession=unenroll_req.profession).delete()
        if unenroll_req.user.profession == unenroll_req.profession:
            unenroll_req.user.profession = None
            unenroll_req.user.save(update_fields=['profession'])

        # Xabar tarkibi
        coin_info = ""
        if total_coins_earned > 0:
            coin_info += f"\n\n🪙 Kursdan olingan {total_coins_earned} coin ayirildi."
        if hw_grades_count > 0 or test_results_count > 0:
            coin_info += f"\n📊 {hw_grades_count} ta vazifa bahosi va {test_results_count} ta test natijasi bekor qilindi."

        Message.objects.create(
            title="Kursdan chiqish tasdiqlandi",
            content=f"Sizning '{unenroll_req.profession.name}' kursidan chiqish so'rovingiz tasdiqlandi.{coin_info}",
            message_type='personal',
            recipient=unenroll_req.user,
            sender=request.user
        )

        if unenroll_req.user.telegram_id:
            tg_coin_info = ""
            if total_coins_earned > 0:
                tg_coin_info += f"\n🪙 Kursdan olingan <b>{total_coins_earned}</b> coin ayirildi."
            if hw_grades_count > 0 or test_results_count > 0:
                tg_coin_info += f"\n📊 {hw_grades_count} ta vazifa bahosi va {test_results_count} ta test natijasi bekor qilindi."
            
            notify_user(
                unenroll_req.user.telegram_id,
                f"✅ <b>Kursdan chiqish tasdiqlandi</b>\n\n"
                f"📖 <b>{unenroll_req.profession.name}</b>\n\n"
                f"📋 So'rovingiz tasdiqlandi. Siz ushbu kursdan chiqarildingiz.{tg_coin_info}"
            )

        coin_msg = f" ({total_coins_earned} coin ayirildi)" if total_coins_earned > 0 else ""
        messages.success(request, f"{unenroll_req.user.full_name} - {unenroll_req.profession.name} kursidan chiqarildi!{coin_msg}")

    return redirect('admin_unenroll_requests')


@login_required
def reject_unenroll_request(request, pk):
    """Admin: Kursdan chiqish so'rovini rad etish"""
    if not request.user.is_admin:
        return redirect('home')

    unenroll_req = get_object_or_404(CourseUnenrollRequest, pk=pk)

    if request.method == 'POST':
        admin_message = request.POST.get('admin_message', "Kursdan chiqish rad etildi.")
        unenroll_req.status = 'rejected'
        unenroll_req.admin_message = admin_message
        unenroll_req.reviewed_by = request.user
        unenroll_req.save()

        Message.objects.create(
            title="Kursdan chiqish rad etildi",
            content=f"Sizning '{unenroll_req.profession.name}' kursidan chiqish so'rovingiz rad etildi.\n\nSabab: {admin_message}",
            message_type='personal',
            recipient=unenroll_req.user,
            sender=request.user
        )

        if unenroll_req.user.telegram_id:
            notify_user(
                unenroll_req.user.telegram_id,
                f"❌ <b>Kursdan chiqish rad etildi</b>\n\n"
                f"📖 <b>{unenroll_req.profession.name}</b>\n\n"
                f"📝 Sabab: {admin_message[:300]}"
            )

        messages.warning(request, f"{unenroll_req.user.full_name} - chiqish so'rovi rad etildi!")

    return redirect('admin_unenroll_requests')


def password_reset_request_view(request):
    if request.user.is_authenticated:
        return redirect('home')
    
    if request.method == 'POST':
        form = PasswordResetRequestForm(request.POST)
        if form.is_valid():
            username = form.cleaned_data['username']
            new_password = form.cleaned_data['new_password1']
            
            try:
                user = CustomUser.objects.get(username=username)
            except CustomUser.DoesNotExist:
                messages.error(request, "Bunday username topilmadi!")
                return render(request, 'accounts/password_reset_request.html', {'form': form})
            
            existing_request = PasswordResetRequest.objects.filter(user=user, status='pending').first()
            if existing_request:
                messages.warning(request, "Sizning parol tiklash so'rovingiz allaqachon yuborilgan va ko'rib chiqilmoqda!")
                return redirect('login')
            
            from django.contrib.auth.hashers import make_password
            hashed_password = make_password(new_password)
            
            PasswordResetRequest.objects.create(
                user=user,
                new_password=hashed_password
            )
            notify_admins(
                f"🔑 <b>Parol tiklash so'rovi!</b>\n\n"
                f"👤 {user.first_name} {user.last_name}\n"
                f"🆔 @{user.username}"
            )
            
            messages.success(request, "Parol tiklash so'rovi yuborildi! Admin tasdiqlashini kuting.")
            return redirect('login')
        else:
            for error in form.non_field_errors():
                messages.error(request, error)
    else:
        form = PasswordResetRequestForm()
    
    return render(request, 'accounts/password_reset_request.html', {'form': form})


@login_required
def admin_password_reset_requests(request):
    if not request.user.is_admin:
        messages.error(request, "Sizda bu sahifaga kirish huquqi yo'q!")
        return redirect('home')
    
    status_filter = request.GET.get('status', '')
    search = request.GET.get('q', '')
    
    requests_qs = PasswordResetRequest.objects.select_related('user', 'reviewed_by')
    
    if status_filter:
        requests_qs = requests_qs.filter(status=status_filter)
    
    if search:
        requests_qs = requests_qs.filter(
            Q(user__username__icontains=search) |
            Q(user__first_name__icontains=search) |
            Q(user__last_name__icontains=search) |
            Q(user__phone__icontains=search)
        )
    
    pending_count = PasswordResetRequest.objects.filter(status='pending').count()
    approved_count = PasswordResetRequest.objects.filter(status='approved').count()
    rejected_count = PasswordResetRequest.objects.filter(status='rejected').count()
    
    context = {
        'password_requests': requests_qs,
        'pending_count': pending_count,
        'approved_count': approved_count,
        'rejected_count': rejected_count,
        'status_filter': status_filter,
        'search': search,
    }
    
    return render(request, 'accounts/admin/password_reset_requests.html', context)


@login_required
def approve_password_reset(request, pk):
    if not request.user.is_admin:
        return redirect('home')
    
    reset_request = get_object_or_404(PasswordResetRequest, pk=pk, status='pending')
    
    if request.method == 'POST':
        user = reset_request.user
        user.password = reset_request.new_password
        user.save()
        
        reset_request.status = 'approved'
        reset_request.reviewed_by = request.user
        reset_request.save()
        
        Message.objects.create(
            title="Parolingiz o'zgartirildi",
            content="Sizning parol tiklash so'rovingiz tasdiqlandi. Endi yangi parol bilan tizimga kirishingiz mumkin.",
            message_type='security',
            recipient=user,
            sender=request.user
        )
        
        messages.success(request, f"{user.full_name} uchun parol muvaffaqiyatli o'zgartirildi!")
    
    return redirect('admin_password_reset_requests')


@login_required
def reject_password_reset(request, pk):
    if not request.user.is_admin:
        return redirect('home')
    
    reset_request = get_object_or_404(PasswordResetRequest, pk=pk, status='pending')
    
    if request.method == 'POST':
        admin_message = request.POST.get('admin_message', "Sizning parol tiklash so'rovingiz rad etildi.")
        
        reset_request.status = 'rejected'
        reset_request.admin_message = admin_message
        reset_request.reviewed_by = request.user
        reset_request.save()
        
        Message.objects.create(
            title="Parol tiklash so'rovi rad etildi",
            content=f"Sizning parol tiklash so'rovingiz rad etildi.\n\nSabab: {admin_message}",
            message_type='security',
            recipient=reset_request.user,
            sender=request.user
        )
        
        messages.warning(request, f"{reset_request.user.full_name} ning parol tiklash so'rovi rad etildi!")
    
    return redirect('admin_password_reset_requests')


@login_required
def admin_parents(request):
    if not request.user.is_admin:
        return redirect('home')
    
    parents = Parent.objects.all()
    
    q = request.GET.get('q', '')
    status = request.GET.get('status', '')
    
    if q:
        parents = parents.filter(
            Q(first_name__icontains=q) |
            Q(last_name__icontains=q) |
            Q(phone__icontains=q) |
            Q(username__icontains=q) |
            Q(email__icontains=q)
        )
    
    if status == 'active':
        parents = parents.filter(is_active=True)
    elif status == 'inactive':
        parents = parents.filter(is_active=False)
    
    context = {
        'parents': parents,
        'q': q,
        'status': status,
    }
    
    return render(request, 'accounts/admin/parents.html', context)


@login_required
def admin_parent_add(request):
    if not request.user.is_admin:
        return redirect('home')
    
    students = CustomUser.objects.filter(role='student')
    
    if request.method == 'POST':
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        phone = request.POST.get('phone', '').strip()
        email = request.POST.get('email', '').strip() or None
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        children_ids = request.POST.getlist('children')
        
        if Parent.objects.filter(username=username).exists():
            messages.error(request, "Bu username allaqachon mavjud!")
        elif Parent.objects.filter(phone=phone).exists():
            messages.error(request, "Bu telefon raqam allaqachon mavjud!")
        else:
            parent = Parent.objects.create(
                first_name=first_name,
                last_name=last_name,
                phone=phone,
                email=email,
                username=username,
                password=make_password(password)
            )
            
            if children_ids:
                parent.children.set(children_ids)
            
            messages.success(request, "Ota-ona muvaffaqiyatli qo'shildi!")
            return redirect('admin_parents')
    
    context = {
        'children': students,
        'selected_children': [],
        'title': "Ota-ona qo'shish",
    }
    
    return render(request, 'accounts/admin/parent_form.html', context)


@login_required
def admin_parent_edit(request, pk):
    if not request.user.is_admin:
        return redirect('home')
    
    parent = get_object_or_404(Parent, pk=pk)
    students = CustomUser.objects.filter(role='student')
    
    if request.method == 'POST':
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        phone = request.POST.get('phone', '').strip()
        email = request.POST.get('email', '').strip() or None
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        children_ids = request.POST.getlist('children')
        
        if Parent.objects.filter(username=username).exclude(pk=pk).exists():
            messages.error(request, "Bu username allaqachon mavjud!")
        elif Parent.objects.filter(phone=phone).exclude(pk=pk).exists():
            messages.error(request, "Bu telefon raqam allaqachon mavjud!")
        else:
            parent.first_name = first_name
            parent.last_name = last_name
            parent.phone = phone
            parent.email = email
            parent.username = username
            
            if password:
                parent.password = make_password(password)
            
            parent.save()
            parent.children.set(children_ids)
            
            messages.success(request, "Ota-ona muvaffaqiyatli tahrirlandi!")
            return redirect('admin_parents')
    
    context = {
        'parent': parent,
        'children': students,
        'selected_children': list(parent.children.values_list('id', flat=True)),
        'title': "Ota-onani tahrirlash",
    }
    
    return render(request, 'accounts/admin/parent_form.html', context)


@login_required
def admin_parent_view(request, pk):
    if not request.user.is_admin:
        return redirect('home')
    
    parent = get_object_or_404(Parent, pk=pk)
    children = parent.children.all()
    parent_messages = ParentMessage.objects.filter(parent=parent).order_by('-created_at')
    
    children_data = []
    for child in children:
        enrollments = child.enrollments.all().select_related('profession')
        
        child_info = {
            'user': child,
            'enrollments': [],
        }
        
        for enrollment in enrollments:
            profession = enrollment.profession
            
            total_videos = VideoLesson.objects.filter(lesson__profession=profession).count()
            watched_videos = VideoProgress.objects.filter(
                user=child,
                video__lesson__profession=profession,
                watched=True
            ).count()
            
            test_results = TestResult.objects.filter(
                student=child,
                test__lesson__profession=profession
            )
            tests_taken = test_results.count()
            avg_test_score = test_results.aggregate(avg=Avg('score'))['avg'] or 0
            
            homework_submissions = HomeworkSubmission.objects.filter(
                student=child,
                homework__lesson__profession=profession
            )
            total_homeworks = Homework.objects.filter(lesson__profession=profession).count()
            submitted_homeworks = homework_submissions.count()
            avg_homework_grade = homework_submissions.filter(grade__isnull=False).aggregate(avg=Avg('grade'))['avg'] or 0
            
            total_items = total_videos + Test.objects.filter(lesson__profession=profession).count() + total_homeworks
            completed_items = watched_videos + tests_taken + submitted_homeworks
            overall_progress = (completed_items / total_items * 100) if total_items > 0 else 0
            
            child_info['enrollments'].append({
                'profession': profession,
                'overall_progress': round(overall_progress, 1),
                'watched_videos': watched_videos,
                'total_videos': total_videos,
                'tests_taken': tests_taken,
                'avg_test_score': round(avg_test_score, 1),
                'submitted_homeworks': submitted_homeworks,
                'total_homeworks': total_homeworks,
                'avg_homework_grade': round(avg_homework_grade, 1),
            })
        
        children_data.append(child_info)
    
    context = {
        'parent': parent,
        'children_data': children_data,
        'parent_messages': parent_messages,
    }
    
    return render(request, 'accounts/admin/parent_view.html', context)


@login_required
def admin_parent_toggle(request, pk):
    if not request.user.is_admin:
        return redirect('home')
    
    if request.method == 'POST':
        parent = get_object_or_404(Parent, pk=pk)
        parent.is_active = not parent.is_active
        parent.save()
        
        status_text = "faollashtirildi" if parent.is_active else "o'chirildi"
        messages.success(request, f"{parent.full_name} {status_text}!")
    
    return redirect('admin_parents')


@login_required
def admin_parent_delete(request, pk):
    if not request.user.is_admin:
        return redirect('home')
    
    parent = get_object_or_404(Parent, pk=pk)
    
    if request.method == 'POST':
        parent_name = parent.full_name
        parent.delete()
        messages.success(request, f"{parent_name} muvaffaqiyatli o'chirildi!")
        return redirect('admin_parents')
    
    return redirect('admin_parents')


# ============ KITOBXONA / BOOK RENTAL ============

from .models import Book, BookRental

@login_required
def admin_books(request):
    """Kitoblar ro'yxati"""
    if not (request.user.is_admin or request.user.is_teacher):
        return redirect('home')
    
    books = Book.objects.all()
    
    # Qidiruv
    search = request.GET.get('search', '')
    if search:
        books = books.filter(
            Q(title__icontains=search) | Q(author__icontains=search)
        )
    
    # Saralash
    sort = request.GET.get('sort', 'title')
    sort_map = {
        'title': 'title',
        '-title': '-title',
        'author': 'author',
        '-author': '-author',
        'available': '-available_copies',
        '-available': 'available_copies',
        'newest': '-created_at',
        'oldest': 'created_at',
    }
    books = books.order_by(sort_map.get(sort, 'title'))
    
    # Statistikalar
    total_books = Book.objects.count()
    total_copies = sum(b.total_copies for b in Book.objects.all())
    available_total = sum(b.available_copies for b in Book.objects.all())
    
    context = {
        'books': books,
        'search': search,
        'sort': sort,
        'total_books': total_books,
        'total_copies': total_copies,
        'available_total': available_total,
    }
    return render(request, 'accounts/admin/books.html', context)


@login_required
def admin_book_add(request):
    """Yangi kitob qo'shish"""
    if not (request.user.is_admin or request.user.is_teacher):
        return redirect('home')
    
    if request.method == 'POST':
        title = request.POST.get('title')
        author = request.POST.get('author')
        isbn = request.POST.get('isbn', '')
        description = request.POST.get('description', '')
        total_copies = int(request.POST.get('total_copies', 1))
        cover_image = request.FILES.get('cover_image')
        
        book = Book.objects.create(
            title=title,
            author=author,
            isbn=isbn,
            description=description,
            total_copies=total_copies,
            available_copies=total_copies,
            cover_image=cover_image
        )
        
        messages.success(request, f"'{book.title}' kitobi muvaffaqiyatli qo'shildi!")
        return redirect('admin_books')
    
    return render(request, 'accounts/admin/book_form.html', {'action': 'add'})


@login_required
def admin_book_edit(request, pk):
    """Kitobni tahrirlash"""
    if not (request.user.is_admin or request.user.is_teacher):
        return redirect('home')
    
    book = get_object_or_404(Book, pk=pk)
    
    if request.method == 'POST':
        book.title = request.POST.get('title')
        book.author = request.POST.get('author')
        book.isbn = request.POST.get('isbn', '')
        book.description = request.POST.get('description', '')
        new_total = int(request.POST.get('total_copies', 1))
        
        # Mavjud nusxalarni yangilash
        difference = new_total - book.total_copies
        book.total_copies = new_total
        book.available_copies = max(0, book.available_copies + difference)
        
        if request.FILES.get('cover_image'):
            book.cover_image = request.FILES.get('cover_image')
        
        book.save()
        messages.success(request, f"'{book.title}' kitobi yangilandi!")
        return redirect('admin_books')
    
    context = {
        'book': book,
        'action': 'edit'
    }
    return render(request, 'accounts/admin/book_form.html', context)


@login_required
def admin_book_delete(request, pk):
    """Kitobni o'chirish"""
    if not request.user.is_admin:
        return redirect('home')
    
    book = get_object_or_404(Book, pk=pk)
    
    if request.method == 'POST':
        title = book.title
        book.delete()
        messages.success(request, f"'{title}' kitobi o'chirildi!")
    
    return redirect('admin_books')


@login_required
def admin_book_rentals(request):
    """Kitob ijaralari ro'yxati"""
    if not (request.user.is_admin or request.user.is_teacher):
        return redirect('home')
    
    rentals = BookRental.objects.select_related('book', 'student', 'given_by').all()
    
    # Filter
    status = request.GET.get('status', '')
    if status:
        rentals = rentals.filter(status=status)
    
    search = request.GET.get('search', '')
    if search:
        rentals = rentals.filter(
            Q(book__title__icontains=search) |
            Q(student__first_name__icontains=search) |
            Q(student__last_name__icontains=search)
        )
    
    # Saralash
    sort = request.GET.get('sort', 'newest')
    sort_map = {
        'newest': '-created_at',
        'oldest': 'created_at',
        'book': 'book__title',
        'student': 'student__first_name',
        'return': 'return_date',
        '-return': '-return_date',
    }
    rentals = rentals.order_by(sort_map.get(sort, '-created_at'))
    
    # Statistikalar
    from datetime import date
    today = date.today()
    stats = {
        'total': BookRental.objects.filter(status='active').count(),
        'overdue': BookRental.objects.filter(status='active', return_date__lt=today).count(),
        'returned_today': BookRental.objects.filter(actual_return_date=today).count(),
    }
    
    context = {
        'rentals': rentals,
        'stats': stats,
        'status': status,
        'search': search,
        'sort': sort,
    }
    return render(request, 'accounts/admin/book_rentals.html', context)


@login_required
def admin_give_book(request):
    """O'quvchiga kitob berish"""
    if not (request.user.is_admin or request.user.is_teacher):
        return redirect('home')
    
    if request.method == 'POST':
        book_id = request.POST.get('book_id')
        student_id = request.POST.get('student_id')
        return_date = request.POST.get('return_date')
        notes = request.POST.get('notes', '')
        
        book = get_object_or_404(Book, pk=book_id)
        student = get_object_or_404(CustomUser, pk=student_id, role='student')
        
        if not book.is_available:
            messages.error(request, f"'{book.title}' kitobi hozirda mavjud emas!")
            return redirect('admin_give_book')
        
        # Ijara yaratish
        rental = BookRental.objects.create(
            book=book,
            student=student,
            given_by=request.user,
            return_date=return_date,
            notes=notes
        )
        
        # Mavjud nusxani kamaytirish
        book.available_copies -= 1
        book.save()
        
        # O'quvchiga xabar yuborish: "Ijaraga shu kitob berildi, qaytarish sanasi kelmoqda"
        from datetime import datetime
        return_date_str = datetime.strptime(return_date, '%Y-%m-%d').strftime('%d.%m.%Y')
        Message.objects.create(
            sender=request.user,
            recipient=student,
            title="📚 Kitob ijarasi",
            content=f"Sizga '{book.title}' ({book.author}) kitobi ijaraga berildi. Qaytarish sanasi kelmoqda: {return_date_str}\n\nIltimos, kitobni o'z vaqtida kutubxonaga qaytaring!",
            message_type='system'
        )
        
        # Ota-onalarga xabar: farzandining ijaradagi kitobi va qaytarish sanasi
        for parent in student.parents.filter(is_active=True):
            ParentMessage.objects.create(
                parent=parent,
                child=student,
                subject="📚 Farzandingiz kitob oldi",
                message=f"Farzandingiz {student.full_name} '{book.title}' ({book.author}) kitobini ijaraga oldi.\n\nQaytarish sanasi: {return_date_str}\n\nIltimos, farzandingizga kitobni o'z vaqtida qaytarishni eslatib qo'ying!"
            )
        
        notify_admins(
            f"📚 <b>Kitob ijaraga berildi!</b>\n\n"
            f"📖 {book.title} ({book.author})\n"
            f"👤 {student.full_name}\n"
            f"📅 Qaytarish: {return_date_str}\n"
            f"👨‍💼 Berdi: {request.user.full_name}"
        )
        notify_group(
            f"📚 <b>Kutubxona yangiligi</b>\n\n"
            f"📖 «{book.title}» kitobi {student.full_name}ga ijaraga berildi.\n"
            f"📅 Qaytarish sanasi: {return_date_str}"
        )
        notify_user(
            student.telegram_id,
            f"📚 Sizga kitob ijaraga berildi!\n\n"
            f"📖 <b>{book.title}</b> ({book.author})\n"
            f"📅 Qaytarish sanasi: {return_date_str}\n\n"
            f"⏰ Iltimos, kitobni o'z vaqtida qaytaring!"
        )
        messages.success(request, f"'{book.title}' kitobi {student.full_name}ga berildi!")
        return redirect('admin_book_rentals')
    
    books = Book.objects.filter(available_copies__gt=0)
    students = CustomUser.objects.filter(role='student', is_blocked=False).order_by('first_name')
    
    from datetime import date
    context = {
        'books': books,
        'students': students,
        'today': date.today(),
    }
    return render(request, 'accounts/admin/give_book.html', context)


@login_required
def admin_return_book(request, pk):
    """Kitobni qaytarilgan deb belgilash"""
    if not (request.user.is_admin or request.user.is_teacher):
        return redirect('home')
    
    rental = get_object_or_404(BookRental, pk=pk)
    
    if request.method == 'POST':
        rental.mark_returned(request.user)
        
        # O'quvchiga xabar
        Message.objects.create(
            sender=request.user,
            recipient=rental.student,
            title="✅ Kitob qaytarildi",
            content=f"'{rental.book.title}' ({rental.book.author}) kitobi muvaffaqiyatli qaytarildi. Rahmat!",
            message_type='system'
        )
        
        notify_admins(
            f"✅ <b>Kitob qaytarildi!</b>\n\n"
            f"📖 {rental.book.title} ({rental.book.author})\n"
            f"👤 {rental.student.full_name}\n"
            f"👨‍💼 Qabul qildi: {request.user.full_name}"
        )
        notify_group(
            f"✅ <b>Kutubxona yangiligi</b>\n\n"
            f"📖 «{rental.book.title}» kitobi {rental.student.full_name} tomonidan qaytarildi."
        )
        messages.success(request, f"'{rental.book.title}' qaytarildi!")
    
    return redirect('admin_book_rentals')


# O'quvchi uchun
@login_required
def my_book_rentals(request):
    """O'quvchining ijaradagi kitoblari"""
    rentals = BookRental.objects.filter(student=request.user).select_related('book', 'given_by')
    
    # Faol va muddati o'tgan (hali qaytarilmagan) kitoblar
    active_rentals = rentals.filter(status__in=['active', 'overdue'])
    returned_rentals = rentals.filter(status='returned')
    
    context = {
        'active_rentals': active_rentals,
        'returned_rentals': returned_rentals,
    }
    return render(request, 'accounts/my_book_rentals.html', context)


def send_book_reminders():
    """Kitob qaytarish eslatmalari - cron job yoki management command orqali chaqiriladi"""
    from datetime import date, timedelta
    
    today = date.today()
    three_days_later = today + timedelta(days=3)
    
    # 3 kun oldin eslatma
    rentals_3days = BookRental.objects.filter(
        status='active',
        return_date=three_days_later,
        reminder_sent_3days=False
    )
    
    for rental in rentals_3days:
        # O'quvchiga xabar: "Iltimos ushbu yozuvchini shu nomli kitobini kutubxonaga qaytaring"
        Message.objects.create(
            recipient=rental.student,
            title="⏰ Kitob qaytarish eslatmasi",
            content=f"Hurmatli {rental.student.full_name}!\n\n'{rental.book.title}' ({rental.book.author}) kitobini qaytarish muddati 3 kun qoldi.\n\nIltimos, ushbu {rental.book.author} yozuvchining '{rental.book.title}' nomli kitobini kutubxonaga qaytaring!\n\nQaytarish sanasi: {rental.return_date.strftime('%d.%m.%Y')}",
            message_type='system'
        )
        
        # Ota-onaga xabar: farzandining ijaradagi kitobi qaytarish sanasi
        for parent in rental.student.parents.filter(is_active=True):
            ParentMessage.objects.create(
                parent=parent,
                child=rental.student,
                subject="⏰ Kitob qaytarish eslatmasi (3 kun qoldi)",
                message=f"Farzandingiz {rental.student.full_name} '{rental.book.title}' ({rental.book.author}) kitobini ijaraga olgan. Qaytarish sanasi: {rental.return_date.strftime('%d.%m.%Y')}\n\nIltimos, ushbu {rental.book.author} yozuvchining '{rental.book.title}' nomli kitobini kutubxonaga qaytaring deb farzandingizga aytib qo'ying!"
            )
        
        rental.reminder_sent_3days = True
        rental.save()
    
    # Bugungi eslatma
    rentals_today = BookRental.objects.filter(
        status='active',
        return_date=today,
        reminder_sent_today=False
    )
    
    for rental in rentals_today:
        # O'quvchiga xabar: "Iltimos ushbu yozuvchini shu nomli kitobini kutubxonaga qaytaring"
        Message.objects.create(
            recipient=rental.student,
            title="🚨 Kitobni bugun qaytaring!",
            content=f"Hurmatli {rental.student.full_name}!\n\n'{rental.book.title}' ({rental.book.author}) kitobini BUGUN qaytarishingiz kerak!\n\nIltimos, ushbu {rental.book.author} yozuvchining '{rental.book.title}' nomli kitobini kutubxonaga qaytaring!",
            message_type='system'
        )
        
        # Ota-onaga xabar: farzandining ijaradagi kitobi bugun qaytarish kerak
        for parent in rental.student.parents.filter(is_active=True):
            ParentMessage.objects.create(
                parent=parent,
                child=rental.student,
                subject="🚨 Kitobni bugun qaytaring!",
                message=f"Farzandingiz {rental.student.full_name} '{rental.book.title}' ({rental.book.author}) kitobini BUGUN qaytarishi kerak!\n\nIltimos, ushbu {rental.book.author} yozuvchining '{rental.book.title}' nomli kitobini kutubxonaga qaytaring deb aytib qo'ying!"
            )
        
        rental.reminder_sent_today = True
        rental.save()
    
    # Muddati o'tganlarni belgilash
    BookRental.objects.filter(
        status='active',
        return_date__lt=today
    ).update(status='overdue')


# ============== ADMIN: OTA-ONA PAROL SO'ROVLARI ==============

@login_required
def admin_parent_password_requests(request):
    if not request.user.is_admin:
        return redirect('home')
    
    from .models import ParentPasswordResetRequest
    
    requests_list = ParentPasswordResetRequest.objects.select_related('parent').all()
    
    status_filter = request.GET.get('status')
    if status_filter:
        requests_list = requests_list.filter(status=status_filter)
    
    context = {
        'requests': requests_list,
        'pending_count': ParentPasswordResetRequest.objects.filter(status='pending').count(),
    }
    return render(request, 'accounts/admin/parent_password_requests.html', context)


@login_required
def approve_parent_password_reset(request, pk):
    if not request.user.is_admin:
        return redirect('home')
    
    from .models import ParentPasswordResetRequest
    from django.contrib.auth.hashers import make_password
    
    reset_request = get_object_or_404(ParentPasswordResetRequest, pk=pk)
    
    if reset_request.status == 'pending':
        reset_request.parent.password = make_password(reset_request.new_password)
        reset_request.parent.save()
        
        reset_request.status = 'approved'
        reset_request.reviewed_by = request.user
        reset_request.reviewed_at = timezone.now()
        reset_request.save()
        
        messages.success(request, f"{reset_request.parent.full_name} paroli yangilandi!")
    
    return redirect('admin_parent_password_requests')


@login_required
def reject_parent_password_reset(request, pk):
    if not request.user.is_admin:
        return redirect('home')
    
    from .models import ParentPasswordResetRequest
    
    reset_request = get_object_or_404(ParentPasswordResetRequest, pk=pk)
    
    if reset_request.status == 'pending':
        reset_request.status = 'rejected'
        reset_request.reviewed_by = request.user
        reset_request.reviewed_at = timezone.now()
        reset_request.save()
        
        messages.info(request, f"{reset_request.parent.full_name} parol so'rovi rad etildi.")
    
    return redirect('admin_parent_password_requests')


@login_required
def admin_premium_management(request):
    if not request.user.is_admin:
        messages.error(request, "Sizda bu sahifaga kirish huquqi yo'q!")
        return redirect('home')

    tab = request.GET.get('tab', 'requests')
    search = request.GET.get('search', '').strip()
    filter_type = request.GET.get('filter', 'all')
    status_filter = request.GET.get('status', 'pending')

    pending_requests = PremiumRequest.objects.filter(status='pending').select_related('user')
    all_requests = PremiumRequest.objects.all().select_related('user', 'reviewed_by')

    if status_filter and status_filter != 'all':
        all_requests = all_requests.filter(status=status_filter)

    users_qs = CustomUser.objects.filter(role='student').order_by('-premium_purchased_at', 'first_name')

    if filter_type == 'premium':
        users_qs = users_qs.filter(is_premium=True)
    elif filter_type == 'not_premium':
        users_qs = users_qs.filter(is_premium=False)
    elif filter_type == 'expiring':
        from datetime import timedelta as td
        users_qs = users_qs.filter(
            is_premium=True,
            premium_expires_at__lte=timezone.now() + td(days=3),
            premium_expires_at__gt=timezone.now()
        )

    if search:
        users_qs = users_qs.filter(
            Q(first_name__icontains=search) |
            Q(last_name__icontains=search) |
            Q(username__icontains=search) |
            Q(phone__icontains=search)
        )

    if request.method == 'POST':
        action = request.POST.get('action')
        user_id = request.POST.get('user_id')

        try:
            with transaction.atomic():
                if action == 'give_premium':
                    user = CustomUser.objects.select_for_update().get(pk=user_id, role='student')
                    plan = request.POST.get('plan', 'monthly')
                    from accounts.models import PremiumRequest as PR
                    days = PR.PLAN_DAYS.get(plan, 30)

                    now = timezone.now()
                    if user.is_premium and user.premium_expires_at and user.premium_expires_at > now:
                        user.premium_expires_at = user.premium_expires_at + timedelta(days=days)
                    else:
                        user.is_premium = True
                        user.premium_purchased_at = now
                        user.premium_expires_at = now + timedelta(days=days)

                    user.save(update_fields=['is_premium', 'premium_purchased_at', 'premium_expires_at'])

                    plan_name = dict(PR.PLAN_CHOICES).get(plan, plan)
                    Message.objects.create(
                        sender=request.user,
                        recipient=user,
                        title="Premium berildi ✅",
                        content=f"Sizga admin tomonidan {plan_name} Premium obuna berildi!\nMuddati: {user.premium_expires_at.strftime('%d.%m.%Y %H:%M')} gacha.",
                        message_type='system'
                    )
                    messages.success(request, f"{user.full_name}ga {plan_name} Premium berildi!")

                elif action == 'remove_premium':
                    user = CustomUser.objects.select_for_update().get(pk=user_id, role='student')
                    if user.is_premium:
                        user.is_premium = False
                        user.premium_purchased_at = None
                        user.premium_expires_at = None
                        user.save(update_fields=['is_premium', 'premium_purchased_at', 'premium_expires_at'])

                        Message.objects.create(
                            sender=request.user,
                            recipient=user,
                            title="Premium olib tashlandi",
                            content="Sizning Premium obunangiz admin tomonidan olib tashlandi.",
                            message_type='system'
                        )
                        messages.success(request, f"{user.full_name}dan Premium olib tashlandi!")

        except CustomUser.DoesNotExist:
            messages.error(request, "Foydalanuvchi topilmadi!")

        return redirect(f"{request.path}?tab={tab}&filter={filter_type}&search={search}")

    premium_count = CustomUser.objects.filter(role='student', is_premium=True).count()
    total_students = CustomUser.objects.filter(role='student').count()
    pending_count = PremiumRequest.objects.filter(status='pending').count()
    expiring_soon = CustomUser.objects.filter(
        role='student', is_premium=True,
        premium_expires_at__lte=timezone.now() + timedelta(days=3),
        premium_expires_at__gt=timezone.now()
    ).count()

    paginator = Paginator(users_qs, 25)
    page_number = request.GET.get('page')
    users = paginator.get_page(page_number)

    context = {
        'users': users,
        'premium_count': premium_count,
        'total_students': total_students,
        'pending_count': pending_count,
        'expiring_soon': expiring_soon,
        'pending_requests': pending_requests,
        'all_requests': all_requests[:100],
        'search': search,
        'filter_type': filter_type,
        'tab': tab,
        'status_filter': status_filter,
    }

    return render(request, 'accounts/admin/premium_management.html', context)


@login_required
def approve_premium_request(request, pk):
    if not request.user.is_admin:
        return redirect('home')

    prem_req = get_object_or_404(PremiumRequest, pk=pk)

    if prem_req.status != 'pending':
        messages.info(request, "Bu so'rov allaqachon ko'rib chiqilgan.")
        return redirect('admin_premium_management')

    with transaction.atomic():
        prem_req.status = 'approved'
        prem_req.reviewed_by = request.user
        prem_req.reviewed_at = timezone.now()
        prem_req.save()

        user = CustomUser.objects.select_for_update().get(pk=prem_req.user_id)
        days = prem_req.duration_days
        now = timezone.now()

        if user.is_premium and user.premium_expires_at and user.premium_expires_at > now:
            user.premium_expires_at = user.premium_expires_at + timedelta(days=days)
        else:
            user.is_premium = True
            user.premium_purchased_at = now
            user.premium_expires_at = now + timedelta(days=days)

        user.save(update_fields=['is_premium', 'premium_purchased_at', 'premium_expires_at'])

        Message.objects.create(
            sender=request.user,
            recipient=user,
            title="Premium tasdiqlandi ✅",
            content=f"Sizning {prem_req.get_plan_display()} Premium so'rovingiz tasdiqlandi!\nMuddati: {user.premium_expires_at.strftime('%d.%m.%Y %H:%M')} gacha amal qiladi.",
            message_type='system'
        )

    messages.success(request, f"{prem_req.user.full_name}ning Premium so'rovi tasdiqlandi!")
    return redirect('admin_premium_management')


@login_required
def reject_premium_request(request, pk):
    if not request.user.is_admin:
        return redirect('home')

    prem_req = get_object_or_404(PremiumRequest, pk=pk)

    if prem_req.status != 'pending':
        messages.info(request, "Bu so'rov allaqachon ko'rib chiqilgan.")
        return redirect('admin_premium_management')

    with transaction.atomic():
        prem_req.status = 'rejected'
        prem_req.reviewed_by = request.user
        prem_req.reviewed_at = timezone.now()
        prem_req.save()

        user = CustomUser.objects.select_for_update().get(pk=prem_req.user_id)
        user.coins += prem_req.price
        user.save(update_fields=['coins'])

        from coin.models import CoinTransaction
        CoinTransaction.objects.create(
            user=user,
            amount=prem_req.price,
            action='add',
            reason=f"Premium so'rov rad etildi - {prem_req.price} coin qaytarildi"
        )

        Message.objects.create(
            sender=request.user,
            recipient=user,
            title="Premium so'rov rad etildi",
            content=f"Sizning {prem_req.get_plan_display()} Premium so'rovingiz rad etildi.\n{prem_req.price} coin hisobingizga qaytarildi.",
            message_type='system'
        )

    messages.success(request, f"{prem_req.user.full_name}ning Premium so'rovi rad etildi. Coinlar qaytarildi.")
    return redirect('admin_premium_management')


# ============== SECTION MANAGEMENT ==============

@login_required
def admin_sections_management(request):
    """Bo'limlar boshqaruvi - saytdagi barcha bo'limlarni bloklab/yoqlab qo'yish"""
    if not request.user.is_admin:
        return redirect('home')
    
    # Database dan bloklangan bo'limlarni o'qish
    blocked_db = BlockedSection.objects.all()
    
    # Har bo'lim uchun default dict yaratish
    sections_dict = {}
    
    # Barcha bo'limlar uchun default status qo'yish
    for section_code, section_name in BlockedSection.SECTION_CHOICES:
        sections_dict[section_code] = {
            'is_blocked': False,
            'reason': '',
            'blocked_by': None,
            'blocked_at': None,
        }
    
    # Database dan bloklangan bo'limlarni update qilish
    for bs in blocked_db:
        sections_dict[bs.section] = {
            'is_blocked': bs.is_blocked,
            'reason': bs.reason,
            'blocked_by': bs.blocked_by,
            'blocked_at': bs.blocked_at,
        }
    
    # Template uchun underscore kalit bilan ham saqlash (hyphenli kalitlar template da ishlamaydi)
    sections_dict_safe = {}
    for key, value in sections_dict.items():
        safe_key = key.replace('-', '_')
        sections_dict_safe[safe_key] = value
    
    # Statistika hisoblash
    total_sections = len(BlockedSection.SECTION_CHOICES)
    blocked_count = BlockedSection.objects.filter(is_blocked=True).count()
    active_count = total_sections - blocked_count
    
    context = {
        'blocked_sections': sections_dict_safe,
        'total_sections': total_sections,
        'blocked_count': blocked_count,
        'active_count': active_count,
    }
    
    return render(request, 'accounts/admin/sections_management.html', context)


@login_required
def toggle_section_block(request, section):
    """Bo'limni bloklab yoki yoqlab qo'yish - DATABASE ga saqlash"""
    import sys
    print(f"DEBUG: toggle_section_block called - User: {request.user}, Admin: {request.user.is_admin}", file=sys.stderr)
    
    if not request.user.is_admin:
        print(f"DEBUG: User not admin", file=sys.stderr)
        return JsonResponse({'error': 'Ruxsatmangan'}, status=403)
    
    if request.method != 'POST':
        print(f"DEBUG: Not POST - Method: {request.method}", file=sys.stderr)
        return JsonResponse({'error': 'POST so\'rovi kerak'}, status=400)
    
    try:
        # Database dan bloklangan bo'limni topib yoki yaratib
        blocked_section, created = BlockedSection.objects.get_or_create(section=section)
        
        reason = request.POST.get('reason', 'Tuzatish ishlari olib borilmoqda')
        
        # Toggle status
        if blocked_section.is_blocked:
            # Yoqib qo'yish
            blocked_section.is_blocked = False
            blocked_section.reason = ''
            blocked = False
            message = f"{section} yoqildi"
        else:
            # Bloklab qo'yish
            blocked_section.is_blocked = True
            blocked_section.reason = reason
            blocked_section.blocked_by = request.user
            blocked = True
            message = f"{section} bloklandi: {reason}"
        
        # Database ga saqlash
        blocked_section.save()
        
        # Aktivligi log - faqat action_type va description field lar
        # ActivityLog model 'action' emas 'action_type' field boradi
        # va 'details' field yo'q, faqat description bo'ladi
        try:
            ActivityLog.objects.create(
                user=request.user,
                action_type='deploy_edit',  # Deploy related action, yoki custom qo'shish kerak
                description=message
            )
        except Exception as e:
            # Log error ignore qil
            pass
        
        return JsonResponse({
            'success': True,
            'blocked': blocked,
            'message': message
        })
    
    except Exception as e:
        import sys
        print(f"DEBUG: Exception - {str(e)}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=400)


@login_required
def clear_premium_ad(request):
    request.session.pop('show_premium_ad', None)
    return JsonResponse({'ok': True})


@login_required
def clear_ai_ad(request):
    request.session.pop('show_ai_ad', None)
    return JsonResponse({'ok': True})


# ============ ADMIN: O'QITUVCHILAR BOSHQARUVI ============

@login_required
def admin_teachers(request):
    if not request.user.is_admin:
        return redirect('home')
    from teacher.models import TeacherCertificate, TeacherSalary
    from datetime import datetime

    search_query = request.GET.get('q', '').strip()
    teachers = CustomUser.objects.filter(role='teacher').order_by('-date_joined')
    if search_query:
        teachers = teachers.filter(
            Q(first_name__icontains=search_query) | Q(last_name__icontains=search_query) |
            Q(username__icontains=search_query) | Q(phone__icontains=search_query)
        )

    now = timezone.now()
    week_ago = now - timedelta(days=7)
    month_ago = now - timedelta(days=30)
    current_month = now.month
    current_year = now.year

    teachers_data = []
    for t in teachers:
        professions = t.teaching_professions.all()
        courses_count = professions.count()
        students_count = sum(p.enrollments.filter(user__role='student').count() for p in professions)
        certs_count = TeacherCertificate.objects.filter(teacher=t).count()

        # Lessons created by this teacher
        lessons_created = Lesson.objects.filter(created_by=t).count()
        lessons_this_month = Lesson.objects.filter(created_by=t, created_at__gte=month_ago).count()
        lessons_this_week = Lesson.objects.filter(created_by=t, created_at__gte=week_ago).count()

        # Homework graded
        hw_graded_total = HomeworkSubmission.objects.filter(graded_by=t).count()
        hw_graded_month = HomeworkSubmission.objects.filter(graded_by=t, graded_at__gte=month_ago).count()
        hw_graded_week = HomeworkSubmission.objects.filter(graded_by=t, graded_at__gte=week_ago).count()
        hw_pending = HomeworkSubmission.objects.filter(
            homework__lesson__profession__in=professions, status='pending'
        ).count()

        # Speaking graded
        sp_graded_total = SpeakingSubmission.objects.filter(graded_by=t).count()
        sp_graded_month = SpeakingSubmission.objects.filter(graded_by=t, graded_at__gte=month_ago).count()

        # Online activity
        is_online = t.is_online
        last_activity = t.last_activity
        total_online_minutes = t.total_online_time or 0

        # Activity log
        activities_week = ActivityLog.objects.filter(user=t, created_at__gte=week_ago).count()
        activities_month = ActivityLog.objects.filter(user=t, created_at__gte=month_ago).count()
        login_count_week = ActivityLog.objects.filter(user=t, action_type='login', created_at__gte=week_ago).count()
        login_count_month = ActivityLog.objects.filter(user=t, action_type='login', created_at__gte=month_ago).count()

        # Dictionary words added
        dict_words_total = DictionaryWord.objects.filter(
            dictionary__lesson__profession__in=professions
        ).count()

        # Salary / income
        salary_total = TeacherSalary.objects.filter(teacher=t, is_paid=True).aggregate(
            total=Sum('amount')
        )['total'] or 0
        salary_month = TeacherSalary.objects.filter(
            teacher=t, is_paid=True, month=current_month, year=current_year
        ).aggregate(total=Sum('amount'))['total'] or 0
        salary_unpaid = TeacherSalary.objects.filter(teacher=t, is_paid=False).aggregate(
            total=Sum('amount')
        )['total'] or 0

        # Videos uploaded
        videos_count = VideoLesson.objects.filter(lesson__created_by=t).count()

        # Tests created
        tests_count = Test.objects.filter(lesson__created_by=t).count()

        teachers_data.append({
            'user': t,
            'courses_count': courses_count,
            'students_count': students_count,
            'certs_count': certs_count,
            'lessons_created': lessons_created,
            'lessons_this_month': lessons_this_month,
            'lessons_this_week': lessons_this_week,
            'hw_graded_total': hw_graded_total,
            'hw_graded_month': hw_graded_month,
            'hw_graded_week': hw_graded_week,
            'hw_pending': hw_pending,
            'sp_graded_total': sp_graded_total,
            'sp_graded_month': sp_graded_month,
            'is_online': is_online,
            'last_activity': last_activity,
            'total_online_minutes': total_online_minutes,
            'activities_week': activities_week,
            'activities_month': activities_month,
            'login_count_week': login_count_week,
            'login_count_month': login_count_month,
            'dict_words_total': dict_words_total,
            'salary_total': salary_total,
            'salary_month': salary_month,
            'salary_unpaid': salary_unpaid,
            'videos_count': videos_count,
            'tests_count': tests_count,
        })
    return render(request, 'accounts/admin/teachers.html', {
        'teachers_data': teachers_data, 'search_query': search_query, 'total_count': len(teachers_data),
    })


@login_required
def export_teachers_pdf(request):
    if not request.user.is_admin:
        return redirect('home')
    from teacher.models import TeacherSalary
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from io import BytesIO

    now = timezone.now()
    week_ago = now - timedelta(days=7)
    month_ago = now - timedelta(days=30)

    teachers = CustomUser.objects.filter(role='teacher').order_by('first_name')

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4), topMargin=25, bottomMargin=25,
                            leftMargin=20, rightMargin=20)
    elements = []
    styles = getSampleStyleSheet()

    heading_style = ParagraphStyle(
        'CustomHeading', parent=styles['Heading2'],
        spaceAfter=10, spaceBefore=15, textColor=colors.HexColor('#10b981')
    )
    small_style = ParagraphStyle(
        'Small', parent=styles['Normal'], fontSize=7, leading=9,
    )

    elements.append(Paragraph("O'qituvchilar statistikasi - To'liq hisobot", styles['Title']))
    elements.append(Paragraph(f"Sana: {now.strftime('%d.%m.%Y %H:%M')}", styles['Normal']))
    elements.append(Spacer(1, 15))

    # Summary table
    header = [
        Paragraph('O\'qituvchi', small_style),
        Paragraph('Kurslar', small_style),
        Paragraph('O\'quv.', small_style),
        Paragraph('Darslar', small_style),
        Paragraph('Hafta/Oy', small_style),
        Paragraph('Vazifa teksh.', small_style),
        Paragraph('Hafta/Oy', small_style),
        Paragraph('Kutilmoqda', small_style),
        Paragraph('Speaking', small_style),
        Paragraph('Videolar', small_style),
        Paragraph('Testlar', small_style),
        Paragraph('Lug\'at', small_style),
        Paragraph('Login H/O', small_style),
        Paragraph('Online (daq)', small_style),
        Paragraph('Daromad (so\'m)', small_style),
    ]
    data = [header]

    for t in teachers:
        professions = t.teaching_professions.all()
        courses_count = professions.count()
        students_count = sum(p.enrollments.filter(user__role='student').count() for p in professions)
        lessons_total = Lesson.objects.filter(created_by=t).count()
        lessons_week = Lesson.objects.filter(created_by=t, created_at__gte=week_ago).count()
        lessons_month = Lesson.objects.filter(created_by=t, created_at__gte=month_ago).count()
        hw_total = HomeworkSubmission.objects.filter(graded_by=t).count()
        hw_week = HomeworkSubmission.objects.filter(graded_by=t, graded_at__gte=week_ago).count()
        hw_month = HomeworkSubmission.objects.filter(graded_by=t, graded_at__gte=month_ago).count()
        hw_pending = HomeworkSubmission.objects.filter(
            homework__lesson__profession__in=professions, status='pending'
        ).count()
        sp_total = SpeakingSubmission.objects.filter(graded_by=t).count()
        videos = VideoLesson.objects.filter(lesson__created_by=t).count()
        tests = Test.objects.filter(lesson__created_by=t).count()
        dict_words = DictionaryWord.objects.filter(dictionary__lesson__profession__in=professions).count()
        login_w = ActivityLog.objects.filter(user=t, action_type='login', created_at__gte=week_ago).count()
        login_m = ActivityLog.objects.filter(user=t, action_type='login', created_at__gte=month_ago).count()
        online_min = t.total_online_time or 0
        salary_total = TeacherSalary.objects.filter(teacher=t, is_paid=True).aggregate(
            total=Sum('amount'))['total'] or 0

        row = [
            Paragraph(t.full_name, small_style),
            Paragraph(str(courses_count), small_style),
            Paragraph(str(students_count), small_style),
            Paragraph(str(lessons_total), small_style),
            Paragraph(f"{lessons_week}/{lessons_month}", small_style),
            Paragraph(str(hw_total), small_style),
            Paragraph(f"{hw_week}/{hw_month}", small_style),
            Paragraph(str(hw_pending), small_style),
            Paragraph(str(sp_total), small_style),
            Paragraph(str(videos), small_style),
            Paragraph(str(tests), small_style),
            Paragraph(str(dict_words), small_style),
            Paragraph(f"{login_w}/{login_m}", small_style),
            Paragraph(str(online_min), small_style),
            Paragraph(f"{salary_total:,.0f}", small_style),
        ]
        data.append(row)

    col_widths = [85, 40, 40, 40, 45, 50, 45, 50, 45, 45, 40, 40, 50, 55, 70]
    table = Table(data, colWidths=col_widths, repeatRows=1)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#10b981')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#dee2e6')),
        ('PADDING', (0, 0), (-1, -1), 4),
        ('ALIGN', (1, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f0fdf4')]),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 7),
    ]))
    elements.append(table)

    doc.build(elements)
    buffer.seek(0)
    response = HttpResponse(buffer, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="teachers_stats_{now.strftime("%Y%m%d")}.pdf"'
    return response


@login_required
def admin_teacher_profile(request, pk):
    if not request.user.is_admin:
        return redirect('home')
    from teacher.models import TeacherCertificate

    teacher = get_object_or_404(CustomUser, pk=pk, role='teacher')
    courses = teacher.teaching_professions.all()
    certificates = TeacherCertificate.objects.filter(teacher=teacher, is_visible=True)

    total_students = 0
    courses_data = []
    for p in courses:
        sc = p.enrollments.filter(user__role='student').count()
        total_students += sc
        courses_data.append({'profession': p, 'student_count': sc})

    context = {
        'teacher': teacher,
        'courses': courses,
        'courses_data': courses_data,
        'certificates': certificates,
        'total_students': total_students,
        'certificates_count': certificates.count(),
        'courses_count': courses.count(),
    }
    return render(request, 'accounts/admin/teacher_profile.html', context)


@login_required
def admin_teacher_certificates(request):
    if not request.user.is_admin:
        return redirect('home')
    from teacher.models import TeacherCertificate
    teacher_id = request.GET.get('teacher', '')
    certs = TeacherCertificate.objects.all().select_related('teacher')
    if teacher_id:
        try: certs = certs.filter(teacher_id=int(teacher_id))
        except (ValueError, TypeError): pass
    teachers = CustomUser.objects.filter(role='teacher').order_by('first_name')
    return render(request, 'accounts/admin/teacher_certificates.html', {
        'certificates': certs, 'teachers': teachers, 'teacher_id': teacher_id,
    })


@login_required
def admin_teacher_certificate_add(request):
    if not request.user.is_admin:
        return redirect('home')
    from teacher.models import TeacherCertificate
    teachers = CustomUser.objects.filter(role='teacher').order_by('first_name')
    if request.method == 'POST':
        teacher_id = request.POST.get('teacher')
        title = request.POST.get('title', '').strip()
        description = request.POST.get('description', '')
        issued_date = request.POST.get('issued_date') or None
        file = request.FILES.get('file')
        if not title or not file or not teacher_id:
            messages.error(request, "O'qituvchi, nom va faylni kiriting.")
            return render(request, 'accounts/admin/teacher_certificate_form.html', {'teachers': teachers})
        teacher = get_object_or_404(CustomUser, pk=teacher_id, role='teacher')
        TeacherCertificate.objects.create(
            teacher=teacher, title=title, description=description, issued_date=issued_date, file=file,
        )
        messages.success(request, f"{teacher.full_name}ga sertifikat qo'shildi!")
        return redirect('admin_teacher_certificates')
    return render(request, 'accounts/admin/teacher_certificate_form.html', {'teachers': teachers})


@login_required
def admin_teacher_certificate_delete(request, pk):
    if not request.user.is_admin:
        return redirect('home')
    from teacher.models import TeacherCertificate
    cert = get_object_or_404(TeacherCertificate, pk=pk)
    if request.method == 'POST':
        cert.delete()
        messages.success(request, "Sertifikat o'chirildi!")
    return redirect('admin_teacher_certificates')


def ariza_view(request):
    """Kursga yozilish arizasi — ochiq sahifa"""
    professions = Profession.objects.filter(is_blocked=False)
    success = False
    
    if request.method == 'POST':
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        raw_phone = request.POST.get('phone', '').strip()
        phone_digits = ''.join(c for c in raw_phone if c.isdigit())
        if phone_digits.startswith('998') and len(phone_digits) == 12:
            phone_digits = phone_digits[3:]
        phone = '+998' + phone_digits if phone_digits else raw_phone
        course_interest = request.POST.get('course_interest', '').strip()
        
        if first_name and last_name and phone:
            application = CourseApplication.objects.create(
                first_name=first_name,
                last_name=last_name,
                phone=phone,
                course_interest=course_interest
            )
            
            notify_admins(
                f"📋 <b>Yangi ariza keldi!</b>\n\n"
                f"👤 {first_name} {last_name}\n"
                f"📱 {phone}\n"
                f"📚 Kurs: {course_interest or 'Belgilanmagan'}\n\n"
                f"📞 Tez orada bog'laning!"
            )
            success = True
    
    return render(request, 'accounts/ariza.html', {
        'professions': professions,
        'success': success,
    })


@login_required
def admin_applications(request):
    """Admin: Arizalar ro'yxati"""
    if not request.user.is_admin:
        return redirect('home')
    
    applications = CourseApplication.objects.all()
    
    status_filter = request.GET.get('status', '')
    if status_filter:
        applications = applications.filter(status=status_filter)
    
    q = request.GET.get('q', '').strip()
    if q:
        from django.db.models import Q
        applications = applications.filter(
            Q(first_name__icontains=q) |
            Q(last_name__icontains=q) |
            Q(phone__icontains=q) |
            Q(course_interest__icontains=q)
        )
    
    from django.core.paginator import Paginator
    paginator = Paginator(applications, 20)
    page = request.GET.get('page')
    applications = paginator.get_page(page)
    
    context = {
        'applications': applications,
        'status_filter': status_filter,
        'search': q,
        'total_new': CourseApplication.objects.filter(status='new').count(),
        'total_all': CourseApplication.objects.count(),
    }
    return render(request, 'accounts/admin/applications.html', context)


@login_required
def admin_application_status(request, pk):
    """Admin: Ariza statusini o'zgartirish"""
    if not request.user.is_admin:
        return redirect('home')
    
    application = get_object_or_404(CourseApplication, pk=pk)
    
    if request.method == 'POST':
        new_status = request.POST.get('status')
        note = request.POST.get('admin_note', '')
        if new_status in dict(CourseApplication.STATUS_CHOICES):
            application.status = new_status
            application.admin_note = note
            application.save()
            messages.success(request, "Ariza holati yangilandi!")
    
    return redirect('admin_applications')


@login_required
def admin_certificates(request):
    """Admin: O'quvchi sertifikatlarini boshqarish"""
    if not request.user.is_admin:
        return redirect('home')
    
    certificates = Certificate.objects.select_related('student', 'profession', 'issued_by').all()
    
    # Filter by status
    status_filter = request.GET.get('status', '')
    if status_filter:
        certificates = certificates.filter(status=status_filter)
    
    # Filter by profession
    profession_filter = request.GET.get('profession', '')
    if profession_filter:
        certificates = certificates.filter(profession_id=profession_filter)
    
    # Search
    q = request.GET.get('search', '').strip()
    if q:
        certificates = certificates.filter(
            Q(student__first_name__icontains=q) |
            Q(student__last_name__icontains=q) |
            Q(student__username__icontains=q) |
            Q(certificate_id__icontains=q)
        )
    
    # Stats
    total_certificates = Certificate.objects.count()
    active_certificates = Certificate.objects.filter(status='active').count()
    expired_certificates = Certificate.objects.filter(status='expired').count()
    revoked_certificates = Certificate.objects.filter(status='revoked').count()
    frozen_certificates = Certificate.objects.filter(status='frozen').count()
    
    professions = Profession.objects.all()
    students = CustomUser.objects.filter(role='student').order_by('first_name', 'last_name')
    
    from django.core.paginator import Paginator
    paginator = Paginator(certificates, 20)
    page = request.GET.get('page')
    certificates = paginator.get_page(page)
    
    context = {
        'certificates': certificates,
        'status_filter': status_filter,
        'profession_filter': profession_filter,
        'search': q,
        'total_certificates': total_certificates,
        'active_certificates': active_certificates,
        'expired_certificates': expired_certificates,
        'revoked_certificates': revoked_certificates,
        'frozen_certificates': frozen_certificates,
        'professions': professions,
        'students': students,
    }
    return render(request, 'accounts/admin/certificates.html', context)


@login_required
def admin_certificate_issue(request):
    """Admin: Yangi sertifikat berish"""
    if not request.user.is_admin:
        return redirect('home')
    
    students = CustomUser.objects.filter(role='student').order_by('first_name', 'last_name')
    professions = Profession.objects.all()
    
    if request.method == 'POST':
        form = CertificateForm(request.POST, request.FILES)
        student_id = request.POST.get('student')
        profession_id = request.POST.get('profession')
        
        if form.is_valid() and student_id and profession_id:
            student = get_object_or_404(CustomUser, pk=student_id, role='student')
            profession = get_object_or_404(Profession, pk=profession_id)
            cert = form.save(commit=False)
            cert.student = student
            cert.profession = profession
            cert.issued_by = request.user
            cert.save()
            
            # O'quvchiga chiroyli tabrik xabari yuborish
            Message.objects.create(
                recipient=student,
                sender=request.user,
                title="🎓🎉 Tabriklaymiz! Sertifikat berildi!",
                content=(
                    f"🌟🌟🌟 TABRIKLAYMIZ! 🌟🌟🌟\n\n"
                    f"Hurmatli {student.full_name}!\n\n"
                    f"🎓 Sizga \"{profession.name}\" yo'nalishi bo'yicha SERTIFIKAT berildi!\n\n"
                    f"📋 Ma'lumotlar:\n"
                    f"   🆔 ID raqam: {student.id}\n"
                    f"   📚 Yo'nalish: {profession.name}\n"
                    f"   🏅 Sertifikat ID: {cert.certificate_id}\n"
                    f"   📅 Berilgan sana: {cert.valid_from}\n"
                    f"   ✅ Holat: {cert.get_status_display()}\n\n"
                    f"🎊 Siz bu yo'nalishni muvaffaqiyatli tugatdingiz! Bu sizning mehnat va bilimingizning natijasi.\n\n"
                    f"🚀 Yangi kurslarda ham kutib qolamiz! IT Creative Academy sizga yanada ko'proq bilim va tajriba taqdim etishga tayyor.\n\n"
                    f"📜 Sertifikatingizni profil sahifangizdagi \"Sertifikatlarim\" bo'limida ko'rishingiz mumkin.\n\n"
                    f"💜 Hurmat bilan,\nIT Creative Academy jamoasi"
                ),
                message_type='achievement'
            )
            
            # Telegram orqali chiroyli tabrik xabari
            if student.telegram_id:
                telegram_text = (
                    f"🎓🎉🎊 <b>TABRIKLAYMIZ!</b> 🎊🎉🎓\n\n"
                    f"Hurmatli <b>{student.full_name}</b>!\n\n"
                    f"✨ Sizga <b>«{profession.name}»</b> yo'nalishi bo'yicha <b>SERTIFIKAT</b> berildi!\n\n"
                    f"📋 <b>Ma'lumotlar:</b>\n"
                    f"┌ 🆔 ID raqam: <b>{student.id}</b>\n"
                    f"├ 📚 Yo'nalish: <b>{profession.name}</b>\n"
                    f"├ 🏅 Sertifikat: <b>{cert.certificate_id}</b>\n"
                    f"└ 📅 Sana: <b>{cert.valid_from}</b>\n\n"
                    f"🌟 Siz bu yo'nalishni muvaffaqiyatli tugatdingiz! Bu sizning mehnat va bilimingizning natijasi.\n\n"
                    f"🚀 <b>Yangi kurslarda ham kutib qolamiz!</b>\n"
                    f"IT Creative Academy sizga yanada ko'proq bilim va tajriba taqdim etishga tayyor.\n\n"
                    f"💜 <i>IT Creative Academy jamoasi</i>"
                )
                notify_user(student.telegram_id, telegram_text)
            
            # Adminlarga xabar
            notify_admins(
                f"🎓 <b>Sertifikat berildi!</b>\n\n"
                f"👤 O'quvchi: <b>{student.full_name}</b>\n"
                f"📚 Yo'nalish: <b>{profession.name}</b>\n"
                f"🏅 Sertifikat: <b>{cert.certificate_id}</b>"
            )
            
            # Guruhga tabrik
            notify_group(
                f"🎓🎉 <b>TABRIKLAYMIZ!</b> 🎉🎓\n\n"
                f"🌟 <b>{student.full_name}</b> 🌟\n\n"
                f"<b>«{profession.name}»</b> yo'nalishini muvaffaqiyatli tugatdi va <b>SERTIFIKAT</b> oldi! 🏅\n\n"
                f"🎊 Tabriklaymiz va yangi kurslarda kutib qolamiz! 🚀\n\n"
                f"💜 <b>IT Creative Academy</b>"
            )
            
            messages.success(request, f"Sertifikat muvaffaqiyatli berildi! ID: {cert.certificate_id}")
            return redirect('admin_certificates')
        else:
            messages.error(request, "Iltimos, barcha maydonlarni to'ldiring!")
    else:
        form = CertificateForm()
    
    return render(request, 'accounts/admin/certificate_form.html', {
        'students': students,
        'professions': professions,
        'form': form,
        'is_edit': False,
    })


@login_required
def admin_certificate_status(request, pk):
    """Admin: Sertifikat holatini o'zgartirish"""
    if not request.user.is_admin:
        return redirect('home')
    
    cert = get_object_or_404(Certificate, pk=pk)
    
    if request.method == 'POST':
        new_status = request.POST.get('status')
        if new_status in dict(Certificate.STATUS_CHOICES):
            old_status = cert.get_status_display()
            cert.status = new_status
            cert.save()
            
            # O'quvchiga xabar
            status_display = cert.get_status_display()
            Message.objects.create(
                recipient=cert.student,
                sender=request.user,
                title="📋 Sertifikat holati o'zgardi",
                content=f"Sizning \"{cert.profession.name}\" kursi bo'yicha sertifikatingiz holati o'zgardi.\n\nSertifikat ID: {cert.certificate_id}\nOldingi holat: {old_status}\nYangi holat: {status_display}",
                message_type='system'
            )
            
            messages.success(request, f"Sertifikat holati \"{status_display}\" ga o'zgartirildi!")
    
    return redirect('admin_certificates')


@login_required
def admin_certificate_delete(request, pk):
    """Admin: Sertifikatni o'chirish"""
    if not request.user.is_admin:
        return redirect('home')
    
    cert = get_object_or_404(Certificate, pk=pk)
    
    if request.method == 'POST':
        cert.delete()
        messages.success(request, "Sertifikat o'chirildi!")
    
    return redirect('admin_certificates')


@login_required
def final_test_payment(request, pk):
    """Yakuniy test uchun to'lov cheki yuklash"""
    test = get_object_or_404(Test, pk=pk, test_type='final')
    
    # Birinchi marta bo'lsa — bepul
    existing_result = TestResult.objects.filter(test=test, student=request.user).exists()
    if not existing_result:
        return redirect('start_test', pk=test.pk)
    
    # Allaqachon kutilayotgan to'lov bormi
    pending_payment = FinalTestPayment.objects.filter(
        student=request.user, test=test, status='pending'
    ).first()
    
    if request.method == 'POST' and not pending_payment:
        receipt = request.FILES.get('receipt_image')
        if receipt:
            FinalTestPayment.objects.create(
                student=request.user,
                test=test,
                receipt_image=receipt,
            )
            messages.success(request, "To'lov cheki yuklandi! Admin tasdiqlashini kuting.")
            return redirect('lesson_view', pk=test.lesson.pk)
        else:
            messages.error(request, "Iltimos, to'lov chekini yuklang.")
    
    approved_payment = FinalTestPayment.objects.filter(
        student=request.user, test=test, status='approved'
    ).exists()
    
    context = {
        'test': test,
        'pending_payment': pending_payment,
        'approved_payment': approved_payment,
    }
    return render(request, 'accounts/lessons/final_test_payment.html', context)


@login_required
def admin_final_test_payments(request):
    """Admin panel: Yakuniy test to'lovlarini boshqarish"""
    if request.user.role not in ('admin', 'teacher'):
        return redirect('home')
    
    status_filter = request.GET.get('status', 'pending')
    payments = FinalTestPayment.objects.select_related('student', 'test__lesson__profession', 'reviewed_by')
    
    if status_filter:
        payments = payments.filter(status=status_filter)
    
    # O'qituvchi faqat o'z kurslaridagi testlarni ko'radi
    if request.user.role == 'teacher':
        professions = request.user.teaching_professions.all()
        payments = payments.filter(test__lesson__profession__in=professions)
    
    context = {
        'payments': payments[:100],
        'status_filter': status_filter,
        'pending_count': FinalTestPayment.objects.filter(status='pending').count() if request.user.role == 'admin' else FinalTestPayment.objects.filter(status='pending', test__lesson__profession__in=request.user.teaching_professions.all()).count(),
    }
    
    if request.user.role == 'teacher':
        return render(request, 'teacher/final_test_payments.html', context)
    return render(request, 'accounts/admin/final_test_payments.html', context)


@login_required
def approve_final_test_payment(request, pk):
    """Yakuniy test to'lovini tasdiqlash"""
    if request.user.role not in ('admin', 'teacher'):
        return redirect('home')
    
    payment = get_object_or_404(FinalTestPayment, pk=pk)
    
    # O'qituvchi faqat o'z kursi
    if request.user.role == 'teacher':
        professions = request.user.teaching_professions.all()
        if payment.test.lesson.profession not in professions:
            messages.error(request, "Sizda bu to'lovni tasdiqlash huquqi yo'q.")
            return redirect('admin_final_test_payments')
    
    if request.method == 'POST':
        payment.status = 'approved'
        payment.reviewed_by = request.user
        payment.reviewed_at = timezone.now()
        payment.save()
        messages.success(request, f"{payment.student.full_name}ning to'lovi tasdiqlandi!")
    
    return redirect('admin_final_test_payments')


@login_required
def reject_final_test_payment(request, pk):
    """Yakuniy test to'lovini rad etish"""
    if request.user.role not in ('admin', 'teacher'):
        return redirect('home')
    
    payment = get_object_or_404(FinalTestPayment, pk=pk)
    
    if request.user.role == 'teacher':
        professions = request.user.teaching_professions.all()
        if payment.test.lesson.profession not in professions:
            messages.error(request, "Sizda bu to'lovni rad etish huquqi yo'q.")
            return redirect('admin_final_test_payments')
    
    if request.method == 'POST':
        payment.status = 'rejected'
        payment.reviewed_by = request.user
        payment.reviewed_at = timezone.now()
        payment.reject_reason = request.POST.get('reason', '')
        payment.save()
        messages.success(request, f"{payment.student.full_name}ning to'lovi rad etildi.")
    
    return redirect('admin_final_test_payments')


@login_required
def admin_ai_checker(request):
    """AI Tekshiruvchi vazifalar boshqaruvi"""
    if not request.user.is_admin:
        return redirect('home')
    
    professions = Profession.objects.all()
    
    # Filter by profession
    profession_id = request.GET.get('course', '')
    
    # Homework vazifalar
    homeworks = Homework.objects.select_related('lesson__profession').all().order_by('lesson__profession__name', 'lesson__title')
    
    # Speaking vazifalar
    speaking_tasks = SpeakingTask.objects.select_related('lesson__profession').all().order_by('lesson__profession__name', 'lesson__title')
    
    if profession_id:
        try:
            homeworks = homeworks.filter(lesson__profession_id=int(profession_id))
            speaking_tasks = speaking_tasks.filter(lesson__profession_id=int(profession_id))
        except (ValueError, TypeError):
            pass
    
    # Statistika
    total_hw = homeworks.count()
    ai_on_hw = homeworks.filter(ai_check=True).count()
    ai_off_hw = total_hw - ai_on_hw
    
    total_sp = speaking_tasks.count()
    ai_on_sp = speaking_tasks.filter(ai_check=True).count()
    ai_off_sp = total_sp - ai_on_sp
    
    # Kurslar bo'yicha guruhlab
    from collections import OrderedDict
    hw_by_course = OrderedDict()
    for hw in homeworks:
        course_name = hw.lesson.profession.name
        if course_name not in hw_by_course:
            hw_by_course[course_name] = {
                'tasks': [], 'ai_enabled': hw.lesson.profession.ai_check_enabled,
                'id': hw.lesson.profession.pk,
            }
        hw_by_course[course_name]['tasks'].append(hw)
    
    sp_by_course = OrderedDict()
    for sp in speaking_tasks:
        course_name = sp.lesson.profession.name
        if course_name not in sp_by_course:
            sp_by_course[course_name] = {
                'tasks': [], 'ai_enabled': sp.lesson.profession.ai_check_enabled,
                'id': sp.lesson.profession.pk,
            }
        sp_by_course[course_name]['tasks'].append(sp)
    
    context = {
        'professions': professions,
        'hw_by_course': hw_by_course,
        'sp_by_course': sp_by_course,
        'total_hw': total_hw,
        'ai_on_hw': ai_on_hw,
        'ai_off_hw': ai_off_hw,
        'total_sp': total_sp,
        'ai_on_sp': ai_on_sp,
        'ai_off_sp': ai_off_sp,
        'selected_course': profession_id,
    }
    return render(request, 'accounts/admin/ai_checker.html', context)


@login_required
def admin_ai_checker_toggle(request):
    """AI tekshiruvchini yoqish/o'chirish (AJAX)"""
    if not request.user.is_admin:
        return JsonResponse({'error': "Ruxsat yo'q"}, status=403)
    
    if request.method != 'POST':
        return JsonResponse({'error': 'POST kerak'}, status=400)
    
    task_type = request.POST.get('type')  # 'homework' or 'speaking'
    task_id = request.POST.get('id')
    action = request.POST.get('action')  # 'on', 'off', 'all_on', 'all_off'
    
    if action in ('all_on', 'all_off'):
        new_val = action == 'all_on'
        profession_id = request.POST.get('profession_id', '')
        
        hw_qs = Homework.objects.all()
        sp_qs = SpeakingTask.objects.all()
        
        if profession_id:
            try:
                hw_qs = hw_qs.filter(lesson__profession_id=int(profession_id))
                sp_qs = sp_qs.filter(lesson__profession_id=int(profession_id))
            except (ValueError, TypeError):
                pass
        
        hw_updated = hw_qs.update(ai_check=new_val)
        sp_updated = sp_qs.update(ai_check=new_val)
        
        status_word = "yoqildi" if new_val else "o'chirildi"
        return JsonResponse({
            'success': True,
            'message': f"Barcha vazifalar AI tekshiruvi {status_word} ({hw_updated + sp_updated} ta)",
            'new_state': new_val,
        })
    
    try:
        task_id = int(task_id)
    except (ValueError, TypeError):
        return JsonResponse({'error': "Noto'g'ri ID"}, status=400)
    
    if task_type == 'homework':
        obj = get_object_or_404(Homework, pk=task_id)
    elif task_type == 'speaking':
        obj = get_object_or_404(SpeakingTask, pk=task_id)
    else:
        return JsonResponse({'error': "Noto'g'ri tur"}, status=400)
    
    obj.ai_check = action == 'on'
    obj.save(update_fields=['ai_check'])
    
    status_text = "Yoqildi" if obj.ai_check else "O'chirildi"
    return JsonResponse({
        'success': True,
        'new_state': obj.ai_check,
        'message': f"{status_text}: {obj.lesson.title}",
    })


@login_required
def admin_ai_course_toggle(request):
    """Kurs uchun AI tekshiruvchini yoqish/o'chirish (Admin override)"""
    if not request.user.is_admin:
        return JsonResponse({'error': "Ruxsat yo'q"}, status=403)
    
    if request.method != 'POST':
        return JsonResponse({'error': 'POST kerak'}, status=400)
    
    profession_id = request.POST.get('profession_id')
    try:
        profession = Profession.objects.get(pk=int(profession_id))
    except (Profession.DoesNotExist, ValueError, TypeError):
        return JsonResponse({'error': 'Kurs topilmadi'}, status=404)
    
    profession.ai_check_enabled = not profession.ai_check_enabled
    profession.save(update_fields=['ai_check_enabled'])
    
    status_text = "yoqildi" if profession.ai_check_enabled else "o'chirildi"
    return JsonResponse({
        'success': True,
        'new_state': profession.ai_check_enabled,
        'message': f"'{profession.name}' kursi uchun AI tekshiruvchi {status_text}",
    })


@login_required
def admin_file_only_toggle(request):
    """Faqat fayl qabul qilishni yoqish/o'chirish (AJAX)"""
    if not request.user.is_admin and request.user.role != 'teacher':
        return JsonResponse({'error': "Ruxsat yo'q"}, status=403)

    if request.method != 'POST':
        return JsonResponse({'error': 'POST kerak'}, status=400)

    hw_id = request.POST.get('id')
    try:
        hw_id = int(hw_id)
    except (ValueError, TypeError):
        return JsonResponse({'error': "Noto'g'ri ID"}, status=400)

    if request.user.is_admin:
        hw = get_object_or_404(Homework, pk=hw_id)
    else:
        professions = request.user.teaching_professions.all()
        hw = get_object_or_404(Homework, pk=hw_id, lesson__profession__in=professions)

    hw.file_only = not hw.file_only
    hw.save(update_fields=['file_only'])

    status_text = "yoqildi" if hw.file_only else "o'chirildi"
    return JsonResponse({
        'success': True,
        'new_state': hw.file_only,
        'message': f"Faqat fayl rejimi {status_text}: {hw.lesson.title}",
    })

