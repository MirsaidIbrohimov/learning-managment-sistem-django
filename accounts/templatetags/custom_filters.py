from django import template
from django.utils.safestring import mark_safe

register = template.Library()

@register.filter
def get_item(dictionary, key):
    """Get item from dictionary by key."""
    if dictionary and isinstance(dictionary, dict):
        return dictionary.get(key)
    return None


@register.filter
def get_course_token(course_token_map, profession_pk):
    """Get student course token UUID from course_token_map by profession pk."""
    if course_token_map and isinstance(course_token_map, dict):
        return course_token_map.get(profession_pk)
    return None


@register.filter
def get_token(token_map, lesson_pk):
    """Get student lesson token UUID from token_map by lesson pk."""
    if token_map and isinstance(token_map, dict):
        token_obj = token_map.get(lesson_pk)
        if token_obj:
            return token_obj.token
    return None


@register.filter
def render_code(text):
    """Detect code blocks, backtick code, and auto-detect programming patterns."""
    import re
    from django.utils.html import escape

    if not text:
        return ''

    text = str(text)

    CODE_INLINE = (
        'style="background:rgba(99,102,241,0.1);color:#6366f1;'
        "padding:0.15rem 0.45rem;border-radius:6px;font-size:0.88em;"
        "font-family:'SF Mono','Fira Code',monospace;\""
    )
    CODE_BLOCK = (
        'style="background:#1e293b;color:#e2e8f0;padding:1rem;'
        'border-radius:12px;font-size:0.88rem;overflow-x:auto;'
        "margin:0.75rem 0;font-family:'SF Mono','Fira Code',monospace;\""
    )

    # --- Phase 1: Extract backtick blocks before escaping ---
    placeholders = {}
    counter = [0]

    def _placeholder(html):
        key = f'\x00CODEBLOCK{counter[0]}\x00'
        counter[0] += 1
        placeholders[key] = html
        return key

    # Triple backtick code blocks
    def _replace_block(m):
        code = escape(m.group(1).strip())
        return _placeholder(f'<pre {CODE_BLOCK}><code>{code}</code></pre>')

    text = re.sub(r'```(.*?)```', _replace_block, text, flags=re.DOTALL)

    # Inline backtick code
    def _replace_inline(m):
        code = escape(m.group(1))
        return _placeholder(f'<code {CODE_INLINE}>{code}</code>')

    text = re.sub(r'`([^`]+)`', _replace_inline, text)

    # --- Phase 2: Escape remaining text ---
    escaped = escape(text)

    # --- Phase 3: Auto-detect code patterns (no backticks needed) ---
    # Function/method calls: print(), len(), range(10), obj.method()
    def _auto_code(m):
        code = m.group(0)
        return _placeholder(f'<code {CODE_INLINE}>{code}</code>')

    # word(...) or word.word(...)
    escaped = re.sub(
        r'(?<![&\w])([a-zA-Z_]\w*(?:\.[a-zA-Z_]\w*)*\([^)]*\))',
        _auto_code, escaped
    )

    # HTML tags: <div>, </p>, <h1 class="x">
    escaped = re.sub(
        r'(&lt;/?[a-zA-Z][a-zA-Z0-9]*(?:\s[^&]*?)?&gt;)',
        _auto_code, escaped
    )

    # Python/JS keyword lines ending with colon: if x > 5:, for i in range(10):, while True:, def foo():
    escaped = re.sub(
        r'(?:^|(?<=<br>)|(?<=\n))\s*((?:if|elif|else|for|while|def|class|try|except|finally|with)\b.+:)\s*(?=$|<br>|\n)',
        _auto_code, escaped
    )

    # import/from statements: import os, from x import y
    escaped = re.sub(
        r'(?:^|(?<=<br>)|(?<=\n))\s*((?:from\s+\w+\s+)?import\s+\w[\w.,\s]*)',
        _auto_code, escaped
    )

    # return/print statements standalone: return x, return True
    escaped = re.sub(
        r'(?:^|(?<=<br>)|(?<=\n))\s*(return\s+(?:True|False|None|\d+|&quot;.*?&quot;|&#x27;.*?&#x27;|\w+\(.*?\)|\w+))',
        _auto_code, escaped
    )

    # Operators in context: x == 5, a != b, x <= 10, x += 1
    escaped = re.sub(
        r'(\b[a-zA-Z_]\w*\s*(?:==|!=|&lt;=|&gt;=|\+=|-=|\*=|/=)\s*(?:\w+|&quot;.*?&quot;|&#x27;.*?&#x27;))',
        _auto_code, escaped
    )

    # Variable assignment: x = 5, name = "hello" (short left side = code)
    escaped = re.sub(
        r'(?:^|(?<=<br>)|(?<=\n))\s*([a-zA-Z_]\w{0,15}\s*=\s*(?:&quot;[^&]*&quot;|&#x27;[^&]*&#x27;|\d+\.?\d*|\[.*?\]|\{.*?\}|True|False|None|[a-zA-Z_]\w*\([^)]*\)))',
        _auto_code, escaped
    )

    # --- Phase 4: Restore placeholders & newlines ---
    escaped = escaped.replace('\n', '<br>')

    for key, html in placeholders.items():
        escaped = escaped.replace(escape(key), html)
        escaped = escaped.replace(key, html)

    return mark_safe(escaped)


@register.filter
def space_num(value):
    """Format number with space thousands separator: 100000 → 100 000"""
    try:
        n = int(float(str(value).replace(' ', '').replace(',', '.')))
        return f"{n:,}".replace(',', ' ')
    except (ValueError, TypeError):
        return value


@register.filter
def abs_value(value):
    """Return absolute value of number."""
    if value is None:
        return 0
    try:
        return abs(int(value))
    except (ValueError, TypeError):
        return value


@register.filter
def premium_name(user):
    """Display user's full name with premium badge if applicable."""
    if user is None:
        return ""
    
    name = user.full_name if hasattr(user, 'full_name') else str(user)
    
    if hasattr(user, 'is_premium') and user.is_premium:
        return mark_safe(f'{name} <i class="bi bi-patch-check-fill" style="color:#f59e0b;font-size:0.85em;" title="Premium"></i>')
    return name

@register.filter
def chr(value):
    """Convert integer to character (ASCII)."""
    try:
        return __builtins__['chr'](int(value))
    except (ValueError, TypeError, KeyError):
        try:
            import builtins
            return builtins.chr(int(value))
        except:
            return ''
