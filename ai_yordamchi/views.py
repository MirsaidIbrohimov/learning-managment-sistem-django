from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse, StreamingHttpResponse
from django.views.decorators.http import require_POST
from django.conf import settings
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Q
from django.urls import reverse
from django.utils import timezone
from urllib.parse import urlencode
import base64
import json
import re
from .jobs import ai_offload

from .models import ChatSession, ChatMessage, ChatFolder
from coin.models import CoinTransaction, ActivityLog

# ============================================================
#  CONFIG
# ============================================================
DAILY_MSG_LIMIT = {'premium': 120, 'regular': 60}
DAILY_IMG_LIMIT = {'premium': 5, 'regular': 3}
# AI rasm çiziş — faqat Premium a'zolar uçun, kuniga şunça ta.
DAILY_GEN_LIMIT = 3
IMAGE_GEN_PROMPT_MAX = 1000

OPENAI_MODEL = "gpt-4o-mini"
OPENAI_MAX_TOKENS = 4096
OPENAI_TEMPERATURE = 0.2

IMAGE_EXTS = ('.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp')
# `.php`, `.bat`, `.ini`, `.cfg`, `.env` ATAYLAB olib taşlandi:
#   - `.php`/`.bat` — `media/` içida bajarilib ketiş xavfi (accounts.security);
#   - `.env`/`.ini`/`.cfg` — konfiguratsiya fayllari, ularning mazmuni AI ga
#     (ya'ni taşqi provayderga) yuborilardi; maxfiy kalitlar çiqib ketmasin.
TEXT_EXTS = (
    '.py', '.js', '.ts', '.html', '.css', '.json', '.xml', '.sql', '.txt',
    '.md', '.csv', '.java', '.rb', '.c', '.cpp', '.h', '.go', '.rs',
    '.sh', '.yaml', '.yml', '.toml', '.log',
)

AI_MAX_UPLOAD_BYTES = 5 * 1024 * 1024   # 5 MB


def _validate_ai_upload(uploaded, images_only=False):
    """AI çatga yuklangan faylni tekşiradi. Xato matnini yoki `None` qaytaradi.

    Avval heç qanday tekşiruv yöq edi: `.htaccess`, `.exe` yoki çeksiz
    hajmli fayl töğridan-töğri `media/` ga tuşardi.
    """
    import os

    from accounts.security import (
        DANGEROUS_EXTENSIONS, _extension_chain, _image_bytes_are_real,
        _safe_filename,
    )

    if not uploaded:
        return None

    if uploaded.size > AI_MAX_UPLOAD_BYTES:
        mb = uploaded.size / (1024 * 1024)
        return f"Fayl hajmi juda katta: {mb:.1f} MB (maksimum 5 MB)."

    raw_name = uploaded.name or ''
    if '\x00' in raw_name:
        return "Fayl nomi xavfli belgilar öz içiga olgan."
    if os.path.basename(raw_name).startswith('.'):
        return "Nuqta bilan boşlanadigan fayl nomlari ruxsat etilmagan."

    for chain_ext in _extension_chain(raw_name):
        if chain_ext in DANGEROUS_EXTENSIONS:
            return f"Yaşirin xavfli kengaytma: {chain_ext}"

    ext = os.path.splitext(raw_name)[1].lower()
    if ext in DANGEROUS_EXTENSIONS:
        return f"'{ext}' kengaytmali fayllar ruxsat etilmagan."

    allowed = IMAGE_EXTS if images_only else (IMAGE_EXTS + TEXT_EXTS)
    if ext not in allowed:
        return f"Ruxsat etilmagan fayl turi: {ext}"

    if ext in IMAGE_EXTS and not _image_bytes_are_real(uploaded):
        return "Fayl haqiqiy rasm emas."

    uploaded.name = _safe_filename(raw_name)
    return None

# Single source of truth for the assistant persona + formatting rules.
SYSTEM_PROMPT = """Siz LMS öquv platformasining AI yordamçisisiz. Har doim Özbek tilida javob bering.

MUALLIF: Sizni Husan Suyunov Şavkat öğli yaratgan (husanbek-coder.uz).
Telefon: +998975216686 | Telegram: @husanbek_coder | GitHub: https://github.com/xusanbek0039
U IT Creative Zomin asosçisi va rahbari, Full-Stack dasturçi.

RASM TAHLILI:
Foydalanuvçi rasm yuborsa, uni körib tahlil qiling. Rasmdagi matn, kod, xato xabar,
diagramma yoki formulani öqing va şunga asosan javob bering. HEÇ QAÇON
"rasmni köra olmayman" demang - siz rasmlarni köra olasiz.

KOD YOZIŞ QOIDALARI (JUDA MUHIM):
1. Har qanday kodni FAQAT markdown code block içida yozing: ```til_nomi ... ```
2. Kod blokini har doim ``` bilan yoping - oçiq qoldirmang.
3. Til nomini töğri yozing: python, javascript, html, css, sql, json, bash, java, php,
   ruby, typescript, cpp, c, go, rust.
4. Bir neçta fayl bölsa, har birini alohida sarlavha va alohida code block bilan bering.
5. Kod töliq va işlaydigan bölsin; izohlarni kod taşqarisida yozing.

JAVOB STRUKTURASI:
- Avval qisqa tuşuntiriş (1-3 gap).
- Keyin kod yoki misollar.
- Oxirida qisqa "Eslatma" yoki "Qanday işlatiş" bölimi (kerak bölsa).

FORMATLAŞ:
- Havolalarni markdown körinişida bering: [matn](https://example.com).
- Muhim sözlar uçun **qalin**, urğu uçun *yotiq*, qisqa kod uçun `inline`.
- Röyxat va jadvallar uçun markdown işlating.

USLUB: Sodda, döstona, boşlovçilar uçun tuşunarli, qisqa va aniq."""


# ============================================================
#  USAGE / LIMITS
# ============================================================
def get_daily_usage(user):
    """Bugungi (xabar, rasm) soni — Toşkent sanasi böyiça, öçirilgan suhbatlar ham hisobda."""
    from .usage import get_usage
    return get_usage(user)


def get_user_limits(user):
    """Return the limit/usage snapshot used across the UI."""
    is_prem = getattr(user, 'is_premium', False)
    tier = 'premium' if is_prem else 'regular'
    msg_limit = DAILY_MSG_LIMIT[tier]
    img_limit = DAILY_IMG_LIMIT[tier]
    msg_used, img_used = get_daily_usage(user)
    from accounts.premium_bonus import is_active_premium
    from .usage import get_generated_count
    can_generate = is_active_premium(user)
    gen_used = get_generated_count(user)
    return {
        'is_premium': is_prem,
        'msg_limit': msg_limit,
        'img_limit': img_limit,
        'msg_used': msg_used,
        'img_used': img_used,
        'msg_left': max(0, msg_limit - msg_used),
        'img_left': max(0, img_limit - img_used),
        'can_generate': can_generate,
        'gen_limit': DAILY_GEN_LIMIT,
        'gen_used': gen_used,
        'gen_left': max(0, DAILY_GEN_LIMIT - gen_used) if can_generate else 0,
    }


# ============================================================
#  OPENAI HELPERS
# ============================================================
def get_openai_client():
    """Return a configured OpenAI client, or None when unavailable."""
    api_key = getattr(settings, 'OPENAI_API_KEY', None)
    if not api_key or not api_key.strip():
        return None
    try:
        from openai import OpenAI
        return OpenAI(api_key=api_key.strip(), timeout=60)
    except ImportError:
        print("ERROR: 'openai' paketi örnatilmagan. `pip install openai` bajaring.")
        return None
    except Exception as e:
        print(f"ERROR: OpenAI client yaratişda xatolik: {e}")
        return None


def _service_unavailable_text():
    """User-facing message when the AI service cannot be reached."""
    api_key = getattr(settings, 'OPENAI_API_KEY', None)
    if not api_key or not api_key.strip():
        return ("⚠️ AI xizmati hozirça sozlanmagan. Administrator bilan boğlaning "
                "(OPENAI_API_KEY topilmadi).")
    return "⚠️ AI xizmatiga ulanib bölmadi. Iltimos, birozdan söng qayta urinib köring."


def validate_and_reformat_response(response_text, user_query=""):
    """Close any unbalanced code fences and turn bare URLs into markdown links."""
    if not response_text:
        return response_text

    # Close an unterminated code block.
    if len(re.findall(r'```', response_text)) % 2 != 0:
        response_text += '\n```'

    # Wrap bare URLs (not already inside a markdown link) as markdown links.
    url_pattern = r'(?<!\]\()(?<!\])(https?://[^\s\)\]<>]+)'
    response_text = re.sub(url_pattern, lambda m: f'[{m.group(1)}]({m.group(1)})', response_text)
    return response_text


def _build_history(session):
    """Build the OpenAI çat history from a session's stored messages."""
    history = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages_list = list(session.messages.all())
    total = len(messages_list)

    for idx, msg in enumerate(messages_list):
        if msg.role != 'user':
            if msg.content:
                history.append({"role": "assistant", "content": msg.content})
            continue

        # Reinforce formatting only on the newest user turn.
        is_last_user = (idx == total - 1) or (
            idx < total - 1 and messages_list[idx + 1].role == 'assistant'
        )
        fmt = ("\n\n⚠️ MUHIM: Kodlar faqat ```til_nomi va ``` orasida, "
               "linklar URL formatida bölsin!") if is_last_user else ""
        user_text = (msg.content or '') + fmt

        # Inline the content of small text/code files.
        if msg.file and msg.file_name and msg.file_name.lower().endswith(TEXT_EXTS):
            try:
                file_content = msg.file.read().decode('utf-8', errors='replace')
                msg.file.seek(0)
                ext = msg.file_name.rsplit('.', 1)[-1] if '.' in msg.file_name else 'txt'
                user_text += f"\n\nFayl: {msg.file_name}\n```{ext}\n{file_content}\n```"
            except Exception:
                pass

        if msg.image:
            try:
                msg.image.open('rb')
                raw = msg.image.read()
                msg.image.close()
                image_data = base64.b64encode(raw).decode('utf-8')
                name = (msg.image.name or '').lower()
                if name.endswith('.png'):
                    mime = 'image/png'
                elif name.endswith('.gif'):
                    mime = 'image/gif'
                elif name.endswith('.webp'):
                    mime = 'image/webp'
                else:
                    mime = 'image/jpeg'
                parts = [{
                    "type": "text",
                    "text": user_text if user_text.strip() else "Bu rasmni tahlil qiling va tuşuntiring.",
                }, {
                    "type": "image_url",
                    "image_url": {"url": f"data:{mime};base64,{image_data}", "detail": "high"},
                }]
                history.append({"role": "user", "content": parts})
            except Exception as img_err:
                print(f"IMAGE READ ERROR: {img_err}")
                if user_text.strip():
                    history.append({
                        "role": "user",
                        "content": user_text + "\n\n(Rasm yuklandi, lekin öqişda xatolik yuz berdi)",
                    })
        elif user_text.strip():
            history.append({"role": "user", "content": user_text})

    _inject_rag_context(history, messages_list)
    return history


def _inject_rag_context(history, messages_list):
    """Ground the answer in course material when relevant (best-effort, never fatal).

    No-ops when the knowledge base is empty or embeddings are unavailable, so the
    çat keeps working even before `build_ai_knowledge` has been run.
    """
    try:
        last_user = ''
        for msg in reversed(messages_list):
            if msg.role == 'user' and msg.content:
                last_user = msg.content
                break
        if not last_user:
            return
        from . import rag
        context = rag.build_context(rag.retrieve(last_user))
        if context:
            history.insert(1, {"role": "system", "content": (
                "Quyida platformadagi kurs materiallaridan tegişli parçalar berilgan. "
                "Agar savol şularga aloqador bölsa, javobni aynan şu materiallarga "
                "tayangan holda bering (kerak bölsa dars nomini eslating). Aloqador "
                "bölmasa, umumiy bilimingizdan foydalaning.\n\nKURS MATERIALLARI:\n" + context)})
    except Exception as e:
        print(f"RAG augment error: {e}")


def _complete_sync(session):
    """Non-streaming completion (used as a no-JS fallback). Returns reply text."""
    client = get_openai_client()
    if not client:
        return _service_unavailable_text()
    try:
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=_build_history(session),
            max_tokens=OPENAI_MAX_TOKENS,
            temperature=OPENAI_TEMPERATURE,
        )
        return validate_and_reformat_response(response.choices[0].message.content or '')
    except Exception as e:
        print(f"OpenAI Error (sync): {e}")
        return f"⚠️ AI bilan boğlanişda xatolik: {e}"


def _sse(payload):
    """Serialize a dict as one Server-Sent Event frame."""
    return "data: " + json.dumps(payload, ensure_ascii=False) + "\n\n"


def _is_ajax(request):
    """True for fetch/XHR requests (used to choose JSON vs redirect responses)."""
    return request.headers.get('X-Requested-With') == 'XMLHttpRequest'


# ============================================================
#  PAGES
# ============================================================
@login_required
def chat_home(request):
    """List the user's çat sessions, optionally filtered by folder/pinned."""
    active = request.GET.get('folder', 'all')
    sessions = ChatSession.objects.filter(user=request.user, is_active=True).select_related('folder')

    if active == 'pinned':
        sessions = sessions.filter(is_pinned=True)
    elif active.isdigit():
        sessions = sessions.filter(folder_id=active)

    folders = (ChatFolder.objects.filter(user=request.user)
               .annotate(session_count=Count('sessions', filter=Q(sessions__is_active=True))))

    return render(request, 'ai_yordamchi/chat_home.html', {
        'sessions': sessions,
        'folders': folders,
        'active_folder': active,
        'pinned_count': ChatSession.objects.filter(user=request.user, is_active=True, is_pinned=True).count(),
        'limits': get_user_limits(request.user),
    })


@login_required
def new_session(request):
    """Create a new çat session and open it.

    An optional ``?q=`` query param (e.g. from an "AI'dan söraş" button on a
    lesson/quiz page) pre-fills the composer so the student can review and send.
    """
    session = ChatSession.objects.create(user=request.user)
    q = request.GET.get('q', '').strip()
    if q:
        url = reverse('ai_yordamchi:chat_session', args=[session.pk])
        params = {'prefill': q[:1500]}
        # Boş sahifadagi "Bilasizmi?" tugmasi savolni darhol yuboradi.
        if request.GET.get('autosend') == '1':
            params['autosend'] = '1'
        return redirect(f"{url}?{urlencode(params)}")
    return redirect('ai_yordamchi:chat_session', pk=session.pk)


@login_required
def chat_session(request, pk):
    """Çat interface for a single session."""
    session = get_object_or_404(ChatSession, pk=pk, user=request.user)
    return render(request, 'ai_yordamchi/chat_session.html', {
        'session': session,
        'chat_messages': session.messages.all(),
        'user_coins': request.user.coins,
        'limits': get_user_limits(request.user),
        'prefill': request.GET.get('prefill', ''),
        'autosend': request.GET.get('autosend') == '1',
    })


# ============================================================
#  MESSAGING
# ============================================================
@login_required
@require_POST
def send_message(request, pk):
    """Persist a user's message (and spend a coin). AI reply is streamed separately.

    AJAX clients receive the saved message id, then open the `stream_response`
    endpoint to receive the reply token-by-token. Non-JS clients fall back to a
    synchronous completion so the feature still works without JavaScript.
    """
    session = get_object_or_404(ChatSession, pk=pk, user=request.user)
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'

    content = request.POST.get('content', '').strip()
    image = request.FILES.get('image')
    file = request.FILES.get('file')

    def fail(message, status=400):
        if is_ajax:
            return JsonResponse({'error': message}, status=status)
        messages.error(request, message)
        return redirect('ai_yordamchi:chat_session', pk=pk)

    if not content and not image and not file:
        return fail("Xabar, rasm yoki fayl yuborişingiz kerak.")

    # Fayl `media/` ga saqlanadi va mazmuni AI ga uzatiladi — avval tekşiriladi.
    for uploaded, images_only in ((image, True), (file, False)):
        problem = _validate_ai_upload(uploaded, images_only=images_only)
        if problem:
            return fail(problem)

    is_premium = getattr(request.user, 'is_premium', False)
    from accounts import curiosity
    curiosity_free = curiosity.is_free_question(request, content) and not image and not file
    # Boş sahifadagi qiziqarli savolga javob tangasiz (kunlik limit baribir hisoblanadi).
    charge = not is_premium and not curiosity_free
    if charge and request.user.coins < 1:
        return fail("Sizda yetarli coin yöq. AI bilan suhbatlaşiş uçun 1 coin kerak.")

    limits = get_user_limits(request.user)
    if limits['msg_left'] <= 0:
        cap = limits['msg_limit']
        return fail(f"Kunlik xabar limitingiz tugadi ({cap}/{cap}). Ertaga qayta urinib köring.")

    has_image = bool(image) or (file and file.name.lower().endswith(IMAGE_EXTS))
    if has_image and limits['img_left'] <= 0:
        cap = limits['img_limit']
        return fail(f"Kunlik rasm limitingiz tugadi ({cap}/{cap}). Ertaga qayta urinib köring.")

    # An uploaded image may arrive via the image field or the generic file field.
    uploaded_image = image
    uploaded_file = None
    uploaded_file_name = ''
    if file:
        uploaded_file_name = file.name
        if file.name.lower().endswith(IMAGE_EXTS):
            uploaded_image = file
        else:
            uploaded_file = file

    coin_cost = 1 if charge else 0
    from .usage import reserve
    with transaction.atomic():
        # Limit atomar band qilinadi: parallel sörovlar ham kunlik çegaradan oşmaydi.
        if not reserve(request.user, limits['msg_limit'], limits['img_limit'], with_image=bool(has_image)):
            cap = limits['img_limit'] if has_image else limits['msg_limit']
            kind = 'rasm' if has_image else 'xabar'
            return fail(f"Kunlik {kind} limitingiz tugadi ({cap}/{cap}). Ertaga qayta urinib köring.")
        if charge:
            locked_user = request.user.__class__.objects.select_for_update().get(pk=request.user.pk)
            if locked_user.coins < 1:
                transaction.set_rollback(True)  # band qilingan limit ham qaytariladi
                return fail("Sizda yetarli coin yöq. AI bilan suhbatlaşiş uçun 1 coin kerak.")
            locked_user.coins -= 1
            locked_user.save(update_fields=['coins'])
            CoinTransaction.objects.create(
                user=locked_user, amount=1, action='remove',
                reason="AI yordamçi bilan suhbat",
            )
            request.user.coins = locked_user.coins

        user_message = ChatMessage(
            session=session,
            role='user',
            content=content,
            image=uploaded_image,
            file=uploaded_file,
            file_name=uploaded_file_name,
            coins_spent=coin_cost,
        )
        user_message._usage_reserved = True  # limit yuqorida band qilindi
        user_message.save()

    ActivityLog.objects.create(
        user=request.user,
        action_type='earn_coins',
        description="AI yordamçi bilan suhbatlaşdi" + (" (-1 coin)" if charge else ""),
        ip_address=get_client_ip(request),
    )

    if curiosity_free:
        curiosity.consume(request)

    if session.messages.count() == 1 and content:
        session.title = content[:50] + ('...' if len(content) > 50 else '')
        session.save(update_fields=['title', 'updated_at'])

    if is_ajax:
        return JsonResponse({
            'success': True,
            'user_message_id': user_message.pk,
            'coins': request.user.coins,
        })

    # No-JS fallback: generate synchronously in-request, then reload the page.
    ChatMessage.objects.create(session=session, role='assistant', content=_complete_sync(session))
    return redirect('ai_yordamchi:chat_session', pk=pk)


def _generate_image_bytes(prompt):
    """OpenAI orqali rasm çizadi va PNG baytlarini qaytaradi (xatoda istisno)."""
    from openai import OpenAI
    import urllib.request

    model = getattr(settings, 'AI_IMAGE_MODEL', '') or 'gpt-image-2'
    client = OpenAI(api_key=settings.OPENAI_API_KEY.strip(), timeout=180)
    params = {'model': model, 'prompt': prompt, 'size': '1024x1024', 'n': 1}
    if model.startswith('dall-e'):
        params['response_format'] = 'b64_json'
    result = client.images.generate(**params)
    item = result.data[0]
    if getattr(item, 'b64_json', None):
        return base64.b64decode(item.b64_json)
    with urllib.request.urlopen(item.url, timeout=60) as resp:  # zaxira: URL qaytgan bölsa
        return resp.read()


@login_required
@require_POST
@ai_offload
def generate_image(request, pk):
    """Premium a'zo uçun matn tavsifidan rasm çizadi (kuniga DAILY_GEN_LIMIT ta)."""
    import uuid
    from django.core.files.base import ContentFile
    from accounts.premium_bonus import is_active_premium
    from accounts.security import safe_error
    from .usage import reserve_generation, release_generation

    session = get_object_or_404(ChatSession, pk=pk, user=request.user)
    if not is_active_premium(request.user):
        return JsonResponse({'error': "Rasm çiziş faqat Premium a'zolar uçun.",
                             'premium_required': True}, status=403)

    prompt = request.POST.get('prompt', '').strip()
    if not prompt:
        return JsonResponse({'error': "Qanday rasm çiziş kerakligini yozing."}, status=400)
    if len(prompt) > IMAGE_GEN_PROMPT_MAX:
        return JsonResponse({'error': f"Tavsif juda uzun (maksimum {IMAGE_GEN_PROMPT_MAX} belgi)."}, status=400)
    if not (getattr(settings, 'OPENAI_API_KEY', '') or '').strip():
        return JsonResponse({'error': _service_unavailable_text()}, status=503)

    # Örin API çaqiruvidan oldin band qilinadi — parallel sörovlar limitdan oşmaydi.
    if not reserve_generation(request.user, DAILY_GEN_LIMIT):
        return JsonResponse({'error': f"Bugungi rasm çiziş limitingiz tugadi "
                                      f"({DAILY_GEN_LIMIT}/{DAILY_GEN_LIMIT}). Ertaga qayta urinib köring."},
                            status=429)
    try:
        image_bytes = _generate_image_bytes(prompt)
    except Exception as e:
        release_generation(request.user)
        code = getattr(e, 'code', '') or ''
        if code in ('content_policy_violation', 'moderation_blocked'):
            msg = "Bu tavsif böyiça rasm çizib bölmaydi (xavfsizlik qoidalari). Boşqaça yozib köring."
        else:
            msg = safe_error(e, 'ai_generate_image', "Rasm çizişda xatolik yuz berdi. Keyinroq qayta urinib köring.")
        return JsonResponse({'error': msg}, status=502)

    with transaction.atomic():
        user_message = ChatMessage(session=session, role='user', content=f"🎨 {prompt}")
        user_message._usage_reserved = True  # xabar limitiga emas, rasm çiziş limitiga yoziladi
        user_message.save()
        reply = ChatMessage(session=session, role='assistant', content=f"🎨 Rasm tayyor: *{prompt[:200]}*")
        reply.image.save(f"ai_{uuid.uuid4().hex[:16]}.png", ContentFile(image_bytes), save=False)
        reply.save()

    if session.messages.count() == 2:
        session.title = f"🎨 {prompt[:46]}" + ('...' if len(prompt) > 46 else '')
        session.save(update_fields=['title', 'updated_at'])

    ActivityLog.objects.create(
        user=request.user,
        action_type='earn_coins',
        description="AI yordamçi bilan rasm çizdi",
        ip_address=get_client_ip(request),
    )
    limits = get_user_limits(request.user)
    return JsonResponse({
        'success': True,
        'message_id': reply.pk,
        'content': reply.content,
        'image_url': reply.image.url,
        'time': timezone.localtime(reply.created_at).strftime('%H:%M'),
        'gen_left': limits['gen_left'],
        'gen_limit': limits['gen_limit'],
    })


@login_required
@ai_offload
def stream_response(request, pk):
    """Stream the AI reply for the latest unanswered user message via SSE.

    The OpenAI call runs inside this request (no background thread), so the only
    database write happens on this connection - avoiding the SQLite write-lock
    contention that previously caused silent "no reply" failures under Passenger.
    """
    session = get_object_or_404(ChatSession, pk=pk, user=request.user)
    last = session.messages.last()

    def event_stream():
        # Guard against duplicate generation (e.g. page refresh / double submit).
        if not last or last.role != 'user':
            yield _sse({'type': 'done', 'skipped': True})
            return

        client = get_openai_client()
        buffer = []
        try:
            if not client:
                text = _service_unavailable_text()
                buffer.append(text)
                yield _sse({'type': 'delta', 'text': text})
            else:
                stream = client.chat.completions.create(
                    model=OPENAI_MODEL,
                    messages=_build_history(session),
                    max_tokens=OPENAI_MAX_TOKENS,
                    temperature=OPENAI_TEMPERATURE,
                    stream=True,
                )
                for chunk in stream:
                    if not chunk.choices:
                        continue
                    delta = chunk.choices[0].delta.content
                    if delta:
                        buffer.append(delta)
                        yield _sse({'type': 'delta', 'text': delta})
        except Exception as e:
            print(f"OpenAI Error (stream): {e}")
            err = f"\n\n⚠️ AI bilan boğlanişda xatolik: {e}"
            buffer.append(err)
            yield _sse({'type': 'delta', 'text': err})

        final = validate_and_reformat_response(''.join(buffer).strip(), last.content)
        if final:
            msg = ChatMessage.objects.create(session=session, role='assistant', content=final)
            yield _sse({
                'type': 'done',
                'message_id': msg.pk,
                'time': msg.created_at.strftime('%H:%M'),
                'content': final,
            })
        else:
            yield _sse({'type': 'done', 'message_id': None})

    response = StreamingHttpResponse(event_stream(), content_type='text/event-stream')
    response['Cache-Control'] = 'no-cache'
    response['X-Accel-Buffering'] = 'no'  # prevent nginx/proxy buffering
    return response


@login_required
@require_POST
def clear_history(request, pk):
    """Delete all messages in a session."""
    session = get_object_or_404(ChatSession, pk=pk, user=request.user)
    session.messages.all().delete()
    session.title = "Yangi suhbat"
    session.save(update_fields=['title', 'updated_at'])
    messages.success(request, "Suhbat tarixi tozalandi.")
    return redirect('ai_yordamchi:chat_session', pk=pk)


@login_required
@require_POST
def delete_session(request, pk):
    """Delete a çat session."""
    session = get_object_or_404(ChatSession, pk=pk, user=request.user)
    session.delete()
    if _is_ajax(request):
        return JsonResponse({'success': True})
    messages.success(request, "Suhbat öçirildi.")
    return redirect('ai_yordamchi:chat_home')


# ============================================================
#  MESSAGE RATING
# ============================================================
@login_required
@require_POST
def rate_message(request, pk):
    """Set 👍 (1) / 👎 (-1) on an assistant message; same value toggles it off."""
    msg = get_object_or_404(ChatMessage, pk=pk, session__user=request.user, role='assistant')
    try:
        value = int(request.POST.get('value', 0))
    except (TypeError, ValueError):
        value = 0
    msg.rating = None if value == msg.rating or value not in (1, -1) else value
    msg.save(update_fields=['rating'])
    return JsonResponse({'success': True, 'rating': msg.rating})


# ============================================================
#  SESSION ORGANIZE (rename / pin / move)
# ============================================================
@login_required
@require_POST
def rename_session(request, pk):
    """Rename a çat session."""
    session = get_object_or_404(ChatSession, pk=pk, user=request.user)
    title = request.POST.get('title', '').strip()
    if not title:
        return JsonResponse({'error': "Nom böş bölişi mumkin emas."}, status=400)
    session.title = title[:200]
    session.save(update_fields=['title'])
    if _is_ajax(request):
        return JsonResponse({'success': True, 'title': session.title})
    return redirect('ai_yordamchi:chat_home')


@login_required
@require_POST
def toggle_pin(request, pk):
    """Pin / unpin a session (pinned sessions sort first)."""
    session = get_object_or_404(ChatSession, pk=pk, user=request.user)
    session.is_pinned = not session.is_pinned
    session.save(update_fields=['is_pinned'])
    return JsonResponse({'success': True, 'is_pinned': session.is_pinned})


@login_required
@require_POST
def move_session(request, pk):
    """Move a session into a folder (empty folder_id removes it from any folder)."""
    session = get_object_or_404(ChatSession, pk=pk, user=request.user)
    folder_id = request.POST.get('folder_id', '').strip()
    if folder_id:
        session.folder = get_object_or_404(ChatFolder, pk=folder_id, user=request.user)
    else:
        session.folder = None
    session.save(update_fields=['folder'])
    return JsonResponse({'success': True, 'folder_id': session.folder_id})


# ============================================================
#  FOLDERS
# ============================================================
@login_required
@require_POST
def create_folder(request):
    """Create a new folder."""
    name = request.POST.get('name', '').strip()
    if not name:
        return JsonResponse({'error': "Papka nomi böş bölişi mumkin emas."}, status=400)
    color = (request.POST.get('color', '') or '#6366f1').strip()
    folder = ChatFolder.objects.create(user=request.user, name=name[:100], color=color[:20])
    return JsonResponse({'success': True, 'id': folder.pk, 'name': folder.name, 'color': folder.color})


@login_required
@require_POST
def rename_folder(request, pk):
    """Rename a folder."""
    folder = get_object_or_404(ChatFolder, pk=pk, user=request.user)
    name = request.POST.get('name', '').strip()
    if not name:
        return JsonResponse({'error': "Papka nomi böş bölişi mumkin emas."}, status=400)
    folder.name = name[:100]
    folder.save(update_fields=['name'])
    return JsonResponse({'success': True, 'id': folder.pk, 'name': folder.name})


@login_required
@require_POST
def delete_folder(request, pk):
    """Delete a folder (its sessions are kept, just un-foldered)."""
    folder = get_object_or_404(ChatFolder, pk=pk, user=request.user)
    folder.delete()
    if _is_ajax(request):
        return JsonResponse({'success': True})
    return redirect('ai_yordamchi:chat_home')


# ============================================================
#  ADMIN
# ============================================================
def admin_required(view_func):
    """Restrict a view to admin users."""
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated or not request.user.is_admin:
            messages.error(request, "Bu sahifaga faqat adminlar kira oladi.")
            return redirect('home')
        return view_func(request, *args, **kwargs)
    return wrapper


@login_required
@admin_required
def admin_chats(request):
    """Admin: browse all çat sessions."""
    sessions = ChatSession.objects.select_related('user').prefetch_related('messages').all()

    user_id = request.GET.get('user')
    if user_id:
        sessions = sessions.filter(user_id=user_id)

    is_active_filter = request.GET.get('is_active')
    if is_active_filter is not None:
        sessions = sessions.filter(is_active=is_active_filter == '1')

    total_sessions = ChatSession.objects.count()
    active_sessions = ChatSession.objects.filter(is_active=True).count()

    paginator = Paginator(sessions, 20)
    sessions_page = paginator.get_page(request.GET.get('page'))

    return render(request, 'ai_yordamchi/admin/chats.html', {
        'sessions': sessions_page,
        'total_sessions': total_sessions,
        'active_sessions': active_sessions,
        'inactive_sessions': total_sessions - active_sessions,
    })


@login_required
@admin_required
def admin_chat_detail(request, pk):
    """Admin: view a single çat session's messages."""
    session = get_object_or_404(ChatSession, pk=pk)
    return render(request, 'ai_yordamchi/admin/chat_detail.html', {
        'session': session,
        'chat_messages': session.messages.all(),
    })


# ============================================================
#  UTILS
# ============================================================
def get_client_ip(request):
    """Best-effort client IP for activity logging.

    `X-Forwarded-For` ning eng çap qiymati mijoz nazoratida — soxtalaştiriş
    mumkin edi. Umumiy `accounts.security.get_client_ip` işonçli proxy
    sonidan kelib çiqib töğri qiymatni oladi.
    """
    from accounts.security import get_client_ip as _get_client_ip
    return _get_client_ip(request)
