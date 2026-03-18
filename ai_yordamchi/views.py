from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.conf import settings
from django.core.paginator import Paginator
from django.utils import timezone
import base64

from .models import ChatSession, ChatMessage
from coin.models import CoinTransaction, ActivityLog

# Daily limits
DAILY_MSG_LIMIT = {'premium': 120, 'regular': 60}
DAILY_IMG_LIMIT = {'premium': 5, 'regular': 3}


def get_daily_usage(user):
    """Get user's daily message and image count."""
    today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
    today_msgs = ChatMessage.objects.filter(
        session__user=user,
        role='user',
        created_at__gte=today_start
    )
    msg_count = today_msgs.count()
    img_count = today_msgs.exclude(image='').exclude(image__isnull=True).count()
    return msg_count, img_count


def get_user_limits(user):
    """Get limits and usage for a user."""
    is_prem = getattr(user, 'is_premium', False)
    tier = 'premium' if is_prem else 'regular'
    msg_limit = DAILY_MSG_LIMIT[tier]
    img_limit = DAILY_IMG_LIMIT[tier]
    msg_used, img_used = get_daily_usage(user)
    return {
        'is_premium': is_prem,
        'msg_limit': msg_limit,
        'img_limit': img_limit,
        'msg_used': msg_used,
        'img_used': img_used,
        'msg_left': max(0, msg_limit - msg_used),
        'img_left': max(0, img_limit - img_used),
    }


def get_openai_client():
    """Get OpenAI client if API key is configured."""
    api_key = getattr(settings, 'OPENAI_API_KEY', None)
    
    # Check if API key exists and is not empty
    if not api_key or not api_key.strip():
        return None
    
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key.strip(), timeout=30)
        return client
    except ImportError:
        print("ERROR: OpenAI paketi o'rnatilmagan. 'pip install openai' buyrug'ini bajaring.")
        return None
    except Exception as e:
        print(f"ERROR: OpenAI client yaratishda xatolik: {str(e)}")
        return None


def validate_and_reformat_response(response_text, user_query):
    """
    Validate va reformat AI javobini.
    - Kod bloklarini to'g'ri yopish
    - Linklarni to'g'ri formatlash
    """
    if not response_text:
        return response_text
    
    import re
    
    # 1. Ochiq qolgan kod bloklarini yopish
    code_block_count = len(re.findall(r'```', response_text))
    if code_block_count % 2 != 0:
        # Ochiq kod bloki bor - yopish
        response_text += '\n```'
    
    # 2. Linklarni to'g'ri formatlash
    # Agar link oddiy matn ichida bo'lsa va markdown link emas bo'lsa
    url_pattern = r'(?<!\[)(?<!\]\()(https?://[^\s\)\]<>]+)(?!\))'
    def replace_url(match):
        url = match.group(1)
        # Agar allaqachon markdown link ichida emas bo'lsa
        return f'[{url}]({url})'
    
    response_text = re.sub(url_pattern, replace_url, response_text)
    
    return response_text


@login_required
def chat_home(request):
    """List user's chat sessions."""
    sessions = ChatSession.objects.filter(user=request.user, is_active=True)
    limits = get_user_limits(request.user)
    return render(request, 'ai_yordamchi/chat_home.html', {
        'sessions': sessions,
        'limits': limits,
    })


@login_required
def new_session(request):
    """Create a new chat session."""
    session = ChatSession.objects.create(user=request.user)
    return redirect('ai_yordamchi:chat_session', pk=session.pk)


@login_required
def chat_session(request, pk):
    """Chat interface with a session."""
    session = get_object_or_404(ChatSession, pk=pk, user=request.user)
    chat_messages = session.messages.all()
    limits = get_user_limits(request.user)
    
    return render(request, 'ai_yordamchi/chat_session.html', {
        'session': session,
        'chat_messages': chat_messages,
        'user_coins': request.user.coins,
        'limits': limits,
    })


@login_required
@require_POST
def send_message(request, pk):
    """Send message to AI and get response."""
    session = get_object_or_404(ChatSession, pk=pk, user=request.user)
    
    content = request.POST.get('content', '').strip()
    image = request.FILES.get('image')
    file = request.FILES.get('file')
    
    if not content and not image and not file:
        messages.error(request, "Xabar, rasm yoki fayl yuborishingiz kerak.")
        return redirect('ai_yordamchi:chat_session', pk=pk)
    
    # Check coins
    is_premium = getattr(request.user, 'is_premium', False)
    
    if not is_premium and request.user.coins < 1:
        messages.error(request, "Sizda yetarli coin yo'q. AI bilan suhbatlashish uchun 1 coin kerak.")
        return redirect('ai_yordamchi:chat_session', pk=pk)
    
    # Check daily limits
    limits = get_user_limits(request.user)
    if limits['msg_left'] <= 0:
        limit_text = "120" if limits['is_premium'] else "60"
        messages.error(request, "Kunlik xabar limitingiz tugadi (" + limit_text + "/" + limit_text + "). Ertaga qayta urinib ko'ring.")
        return redirect('ai_yordamchi:chat_session', pk=pk)
    
    has_image = bool(image) or (file and file.name.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp')))
    if has_image and limits['img_left'] <= 0:
        img_text = "5" if limits['is_premium'] else "3"
        messages.error(request, "Kunlik rasm limitingiz tugadi (" + img_text + "/" + img_text + "). Ertaga qayta urinib ko'ring.")
        return redirect('ai_yordamchi:chat_session', pk=pk)
    
    # Handle file - if it's an image type, save as image field too
    uploaded_image = image
    uploaded_file = None
    uploaded_file_name = ''
    
    if file:
        uploaded_file_name = file.name
        img_exts = ('.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp')
        if file.name.lower().endswith(img_exts):
            uploaded_image = file
        else:
            uploaded_file = file
    
    # Save user message
    coin_cost = 0 if is_premium else 1
    user_message = ChatMessage.objects.create(
        session=session,
        role='user',
        content=content,
        image=uploaded_image,
        file=uploaded_file,
        file_name=uploaded_file_name,
        coins_spent=coin_cost,
    )
    
    # Deduct coin (only for non-premium)
    if not is_premium:
        request.user.coins -= 1
        request.user.save()
        
        CoinTransaction.objects.create(
            user=request.user,
            amount=1,
            action='remove',
            reason="AI yordamchi bilan suhbat"
        )
    
    # Log activity
    ActivityLog.objects.create(
        user=request.user,
        action_type='earn_coins',
        description="AI yordamchi bilan suhbatlashdi" + ("" if is_premium else " (-1 coin)"),
        ip_address=get_client_ip(request)
    )
    
    # Update session title if first message
    if session.messages.count() == 1 and content:
        session.title = content[:50] + ('...' if len(content) > 50 else '')
        session.save()
    
    # Get AI response
    client = get_openai_client()
    
    if not client:
        api_key = getattr(settings, 'OPENAI_API_KEY', None)
        if not api_key or not api_key.strip():
            ai_response = """⚠️ AI xizmati sozlashmagan.

**Muammo:** OPENAI_API_KEY topilmadi yoki bo'sh.

**Yechim:**
1. Loyiha ildizida `.env` faylini yarating (agar yo'q bo'lsa)
2. Quyidagi qatorni qo'shing:
   ```
   OPENAI_API_KEY=sk-sizning-api-kalitingiz
   ```
3. OpenAI API kalitini https://platform.openai.com/api-keys dan oling
4. Serverni qayta ishga tushiring"""
        else:
            # Check if openai package is installed
            try:
                import openai
                ai_response = """⚠️ AI xizmati bilan bog'lanishda muammo.

API kalit mavjud, lekin xizmatga ulanishda xatolik yuz berdi.

**Tekshirish:**
1. API kalitning to'g'riligini tekshiring
2. Internet ulanishini tekshiring
3. Keyinroq urinib ko'ring"""
            except ImportError:
                ai_response = """⚠️ OpenAI paketi o'rnatilmagan.

**Yechim:**
Quyidagi buyruqni bajaring:
```
pip install openai
```

Keyin serverni qayta ishga tushiring."""
    else:
        try:
            # Build messages history
            system_prompt = """Siz LMS o'quv platformasining AI yordamchisisiz. O'zbek tilida javob bering. Sizni Husan Suyunov Shavkat o'g'li yaratgan. 
            husanbek-coder.uz Telefon raqami: +998975216686. Telegrami: @husanbek_coder
            Husan Suyunov IT Creative Zomin asoschisi va rahbari. 
            Husan Suyunov Full-Stack Dasturchi. https://github.com/xusanbek0039            

⚠️ ENG MUHIM QOIDA - KODLAR:
Foydalanuvchi JS, HTML, Python, CSS yoki boshqa tildagi kod so'raganda, ALBATTA kodni markdown code block ichida yozing.
Foydalanuvchi kodni ko'chirib (copy) olishi kerak, shuning uchun HECH QACHON kodni oddiy matn sifatida yozmang.

FORMAT:
```til_nomi
kod shu yerda
```

Masalan:
```python
print("Salom")
```

```javascript
console.log("Salom");
```

```html
<h1>Salom</h1>
```

QOIDALAR:
1. Har qanday kod FAQAT ```til_nomi va ``` orasida bo'lsin
2. Kodni HECH QACHON oddiy matn ichiga qo'shmang
3. Har bir kod blokini albatta ``` bilan yoping
4. Til nomini to'g'ri yozing: python, javascript, html, css, sql, json, bash, java, php, ruby, typescript, cpp, c, go, rust
5. Agar bir nechta fayl bo'lsa, har birini alohida kod blokida yozing
6. Kod to'liq va ishlaydigan bo'lsin

JAVOB FORMATI VA QOIDALAR:

1. STRUKTURA:
   - Avval qisqa va tushunarli tushuntirish (1-3 gap)
   - Keyin kod bloklari yoki misollar
   - Oxirida "Qanday ishlatish" yoki "Eslatma" bo'limi

2. KOD BLOKLARI (MUHIM - BU QOIDALARNI QAT'IY BAJARING):
   - Har doim Markdown formatda yozing va kod bloklarini to'liq yoping
   - Format: ```til_nomi bilan boshlash va ``` bilan tugatish
   - Til nomlari: python, javascript, html, css, sql, json, bash, shell, java, php, ruby
   - Kod ichida faqat kod bo'lsin, izohlar kod tashqarisida
   - Har bir kod bloki to'liq va ishlaydigan bo'lsin
   - Kod bloklarini hech qachon ochiq qoldirmang - har doim ``` bilan yoping
   
   TO'G'RI FORMAT (BU FORMATNI ISHLATING):
   ```python
   def salom():
       print("Salom, Dunyo!")
   ```
   
   YOKI:
   ```javascript
   console.log("Hello, World!");
   ```
   
   XATO FORMAT (BU FORMATNI ISHLATMANG):
   ```python
   def salom():
       print("Salom, Dunyo!")
   (yopilmagan kod bloki)

3. KO'P FAYLLAR (MUHIM - HAR BIR KOD BLOKINI YOPING):
   - Har bir fayl alohida sarlavha bilan:
   - Har bir kod blokini ``` bilan yoping
   
   TO'G'RI FORMAT:
   **HTML (index.html)**
   ```html
   <!DOCTYPE html>
   <html>
   <head>
       <title>Salom</title>
   </head>
   <body>
       <h1>Salom</h1>
   </body>
   </html>
   ```
   
   **CSS (style.css)**
   ```css
   h1 {
       color: red;
       font-size: 2rem;
   }
   ```
   
   **JavaScript (script.js)**
   ```javascript
   console.log("Hello, World!");
   ```

4. HAVOLALAR VA LINKLAR:
   - Har doim to'liq URL bilan: [matn](https://example.com)
   - Tashqi linklar uchun: [matn](https://example.com) - yangi oynada ochiladi
   - Ichki linklar uchun: [matn](#section) yoki [matn](/path)
   - Linklarni aniq va tushunarli qiling

5. FORMATLASH:
   - **Qalin matn** - muhim so'zlar uchun
   - *Yotiq matn* - urg'u berish uchun
   - `kod` - inline kod uchun
   - Ro'yxatlar: - yoki 1. 2. 3.
   - Jadval: Markdown table formatida

6. JADVAL FORMATI:
   ```markdown
   | Ustun 1 | Ustun 2 | Ustun 3 |
   |---------|---------|---------|
   | Ma'lumot 1 | Ma'lumot 2 | Ma'lumot 3 |
   ```

7. USLUB VA TON:
   - Boshlovchilar uchun tushunarli va sodda
   - Do'stona va rag'batlantiruvchi
   - Qisqa va aniq javoblar
   - Misollar bilan tushuntirish
   - Xatolarni oldini olish uchun eslatmalar

8. TAQIQLANGAN (BU XATOLARNI QILMANG):
   - HTML belgilarini escape qilish (< >) - kod bloklarida to'g'ri ishlatilsin
   - \\n yoki \\u000A kabi escape belgilar - oddiy yangi qator ishlating
   - Kod ichida tushuntirish yozish - izohlar kod tashqarisida bo'lsin
   - To'liq bo'lmagan kod bloklari - har doim ``` bilan yoping
   - Ishlanmaydigan kodlar - faqat to'liq va ishlaydigan kod yozing
   - Kod bloklarini ochiq qoldirish - har doim ``` bilan yoping

9. MAXSUS HOLATLAR:
   - Agar kod xatosi bo'lsa, xatoni tushuntiring va to'g'ri kodni ko'rsating
   - Agar bir nechta variant bo'lsa, ularni sanab o'ting
   - Agar resurs kerak bo'lsa, linklar bilan ta'minlang

10. OXIRIDA:
    - "Qanday ishlatish" bo'limi qo'shing
    - Yoki "Eslatma" bo'limi bilan xatolarni oldini oling
    - Qo'shimcha ma'lumot uchun linklar qo'shing

11. KOD BLOKLARI FORMATI (MUHIM - BU QOIDALARNI QAT'IY BAJARING):
    - Har bir kod bloki ```til_nomi bilan boshlanadi va ``` bilan tugaydi
    - Kod bloklarini hech qachon ochiq qoldirmang
    - Har bir kod bloki alohida va to'liq bo'lsin
    - Kod bloklaridan oldin va keyin bo'sh qator qoldiring
    
    TO'G'RI FORMAT (BU FORMATNI ISHLATING):
    
    ```javascript
    console.log("Hello, World!");
    ```
    
    YOKI:
    
    ```html
    <!DOCTYPE html>
    <html>
    <body>
        <h1>Hello, World!</h1>
    </body>
    </html>
    ```
    
    XATO FORMAT (BU FORMATNI ISHLATMANG):
    - Ochiq kod bloki: ```javascript
    - Yopilmagan kod bloki
    - Kod bloklarini birlashtirish"""
            
            history = [
                {"role": "system", "content": system_prompt}
            ]
            
            # History'ni yig'ish
            messages_list = list(session.messages.all())
            total_messages = len(messages_list)
            
            for idx, msg in enumerate(messages_list):
                if msg.role == 'user':
                    # Format qoidasini faqat oxirgi (yangi) user xabariga qo'shish
                    is_last_user_message = idx == total_messages - 1 or (idx < total_messages - 1 and messages_list[idx + 1].role == 'assistant')
                    format_instruction = ""
                    
                    if is_last_user_message:
                        format_instruction = "\n\n⚠️ MUHIM: Javobda kodlar faqat ```til_nomi va ``` orasida, linklar faqat URL formatida bo'lsin!"
                    
                    # Build user message text (content + file content if text file)
                    user_text = (msg.content or '') + format_instruction
                    
                    # Read text file content and append
                    if msg.file and msg.file_name:
                        text_exts = ('.py', '.js', '.ts', '.html', '.css', '.json', '.xml',
                                     '.sql', '.txt', '.md', '.csv', '.java', '.php', '.rb',
                                     '.c', '.cpp', '.h', '.go', '.rs', '.sh', '.bat', '.yaml',
                                     '.yml', '.toml', '.ini', '.cfg', '.env', '.log')
                        if msg.file_name.lower().endswith(text_exts):
                            try:
                                file_content = msg.file.read().decode('utf-8', errors='replace')
                                msg.file.seek(0)
                                ext = msg.file_name.rsplit('.', 1)[-1] if '.' in msg.file_name else 'txt'
                                user_text += f"\n\nFayl: {msg.file_name}\n```{ext}\n{file_content}\n```"
                            except Exception:
                                pass
                    
                    if msg.image:
                        # Handle image message
                        try:
                            image_data = base64.b64encode(msg.image.read()).decode('utf-8')
                            msg.image.seek(0)
                            content_parts = []
                            if user_text.strip():
                                content_parts.append({"type": "text", "text": user_text})
                            content_parts.append({
                                "type": "image_url",
                                "image_url": {"url": f"data:image/jpeg;base64,{image_data}"}
                            })
                            history.append({"role": "user", "content": content_parts})
                        except Exception:
                            if user_text.strip():
                                history.append({"role": "user", "content": user_text})
                    else:
                        if user_text.strip():
                            history.append({"role": "user", "content": user_text})
                else:
                    if msg.content:
                        history.append({"role": "assistant", "content": msg.content})
            
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=history,
                max_tokens=4096,
                temperature=0.2,  # Past temperature - qat'iy format uchun
            )
            
            ai_response = response.choices[0].message.content
            
            # Response validation va reformat (agar kerak bo'lsa)
            if ai_response:
                try:
                    ai_response = validate_and_reformat_response(ai_response, content)
                except Exception as e:
                    print(f"Response reformat error: {str(e)}")
                    # Xatolik bo'lsa ham original javobni qaytarish
            
        except Exception as e:
            import traceback
            print(f"OpenAI Error: {str(e)}")
            print(traceback.format_exc())
            ai_response = f"⚠️ AI bilan bog'lanishda xatolik: {str(e)}"
    
    # Save AI response
    ChatMessage.objects.create(
        session=session,
        role='assistant',
        content=ai_response,
    )
    
    return redirect('ai_yordamchi:chat_session', pk=pk)


@login_required
@require_POST
def clear_history(request, pk):
    """Clear chat history for a session."""
    session = get_object_or_404(ChatSession, pk=pk, user=request.user)
    session.messages.all().delete()
    session.title = "Yangi suhbat"
    session.save()
    messages.success(request, "Suhbat tarixi tozalandi.")
    return redirect('ai_yordamchi:chat_session', pk=pk)


@login_required
@require_POST
def delete_session(request, pk):
    """Delete a chat session."""
    session = get_object_or_404(ChatSession, pk=pk, user=request.user)
    session.delete()
    messages.success(request, "Suhbat o'chirildi.")
    return redirect('ai_yordamchi:chat_home')


def admin_required(view_func):
    """Decorator to require admin role."""
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated or not request.user.is_admin:
            messages.error(request, "Bu sahifaga faqat adminlar kira oladi.")
            return redirect('home')
        return view_func(request, *args, **kwargs)
    return wrapper


@login_required
@admin_required
def admin_chats(request):
    """Admin view to see all chats."""
    sessions = ChatSession.objects.select_related('user').prefetch_related('messages').all()
    
    # Filter by user
    user_id = request.GET.get('user')
    if user_id:
        sessions = sessions.filter(user_id=user_id)
    
    # Filter by active status
    is_active_filter = request.GET.get('is_active')
    if is_active_filter is not None:
        sessions = sessions.filter(is_active=is_active_filter == '1')
    
    # Calculate statistics
    total_sessions = ChatSession.objects.count()
    active_sessions = ChatSession.objects.filter(is_active=True).count()
    inactive_sessions = total_sessions - active_sessions
    
    paginator = Paginator(sessions, 20)
    page = request.GET.get('page')
    sessions_page = paginator.get_page(page)
    
    return render(request, 'ai_yordamchi/admin/chats.html', {
        'sessions': sessions_page,
        'total_sessions': total_sessions,
        'active_sessions': active_sessions,
        'inactive_sessions': inactive_sessions,
    })


@login_required
@admin_required
def admin_chat_detail(request, pk):
    """View specific chat messages."""
    session = get_object_or_404(ChatSession, pk=pk)
    chat_messages = session.messages.all()
    
    return render(request, 'ai_yordamchi/admin/chat_detail.html', {
        'session': session,
        'chat_messages': chat_messages,
    })


def get_client_ip(request):
    """Get client IP address from request."""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip
