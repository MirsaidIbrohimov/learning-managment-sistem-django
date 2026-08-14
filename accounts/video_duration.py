"""Video davomiyligini SERVER tomonda aniqlash (anti-cheat asosi).

Ko'rish talabi (`VideoProgress.required_seconds`) davomiylikdan hisoblanadi.
Agar davomiylik mijozdan olinsa, o'quvchi konsoldan `duration_seconds: 10`
yuborib talabni bir soniyaga tushirib, videoni bir zumda "ko'rilgan" qilib
qo'ya olardi. Shuning uchun davomiylikni server o'zi YouTube/Vimeo'dan oladi va
DB'da qulflaydi — mijoz bu qiymatga ta'sir qila olmaydi.
"""

import re
from datetime import timedelta

import requests
from django.conf import settings
from django.utils import timezone

FETCH_TIMEOUT = 6          # soniya — so'rov yo'lida turgani uchun qisqa
RETRY_AFTER   = timedelta(minutes=10)   # muvaffaqiyatsiz urinishni takrorlash oralig'i
MIN_PLAUSIBLE = 5          # bundan qisqa qiymat xato deb hisoblanadi
MAX_PLAUSIBLE = 24 * 3600

_UA = (
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
    '(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
)

# YouTube sahifasidagi davomiylik: ytInitialPlayerResponse ichida keladi.
_YT_PATTERNS = (
    re.compile(r'"lengthSeconds"\s*:\s*"?(\d+)"?'),
    re.compile(r'"approxDurationMs"\s*:\s*"(\d+)"'),
)

# Pleerning ochiq (kalitsiz emas, lekin hammaga ma'lum) InnerTube kaliti — brauzer
# ham xuddi shu so'rovni yuboradi.
_INNERTUBE_KEY = 'AIzaSyAO_FJ2SlqU8Q4STEHLGCilw_Y9_11qcW8'
_INNERTUBE_CLIENT = {'clientName': 'WEB', 'clientVersion': '2.20240401.00.00', 'hl': 'en'}

# ISO 8601 davomiylik (YouTube Data API): PT4H26M52S
_ISO_DURATION = re.compile(
    r'^P(?:(?P<days>\d+)D)?T(?:(?P<hours>\d+)H)?(?:(?P<minutes>\d+)M)?(?:(?P<seconds>\d+)S)?$'
)


def _parse_iso_duration(text):
    match = _ISO_DURATION.match((text or '').strip())
    if not match:
        return 0
    parts = {key: int(value or 0) for key, value in match.groupdict().items()}
    return (
        parts['days'] * 86400 + parts['hours'] * 3600
        + parts['minutes'] * 60 + parts['seconds']
    )


def _youtube_api_duration(video_id):
    """Asosiy manba: YouTube Data API v3 (`videos.list`).

    Kalit faqat kvotani belgilaydi — egalikni emas, shuning uchun YouTube'dagi
    har qanday ochiq video o'qiladi. Har bir video uchun natija DB'da
    qulflanadi, ya'ni amalda video soniga teng so'rov ketadi (kvota: 1 birlik).
    """
    api_key = getattr(settings, 'YOUTUBE_API_KEY', '')
    if not api_key:
        return 0
    response = requests.get(
        'https://www.googleapis.com/youtube/v3/videos',
        params={'part': 'contentDetails', 'id': video_id, 'key': api_key},
        timeout=FETCH_TIMEOUT,
    )
    response.raise_for_status()
    items = response.json().get('items') or []
    if not items:
        return 0
    return _parse_iso_duration((items[0].get('contentDetails') or {}).get('duration'))


def _youtube_innertube_duration(video_id):
    """Zaxira: YouTube pleer API'si (kalitsiz, lekin ko'p so'rovda bloklanadi).

    `watch` sahifasini o'qishdan ishonchliroq (429/captcha bermaydi) va
    playabilityStatus "UNPLAYABLE" bo'lsa ham `videoDetails.lengthSeconds`
    keladi. Lekin server IP'si bir necha so'rovdan keyin "LOGIN_REQUIRED"
    olishi mumkin — shuning uchun asosiy manba emas.
    """
    response = requests.post(
        'https://www.youtube.com/youtubei/v1/player',
        params={'key': _INNERTUBE_KEY},
        json={'videoId': video_id, 'context': {'client': _INNERTUBE_CLIENT}},
        headers={'User-Agent': _UA, 'Content-Type': 'application/json'},
        timeout=FETCH_TIMEOUT,
    )
    response.raise_for_status()
    details = response.json().get('videoDetails') or {}
    return int(details.get('lengthSeconds') or 0)


def _youtube_page_duration(video_id):
    """Oxirgi zaxira: `watch` sahifasidan o'qish (server IP'da 429 ehtimoli yuqori)."""
    response = requests.get(
        f'https://www.youtube.com/watch?v={video_id}',
        headers={'User-Agent': _UA, 'Accept-Language': 'en-US,en;q=0.9'},
        timeout=FETCH_TIMEOUT,
    )
    response.raise_for_status()
    page = response.text
    for index, pattern in enumerate(_YT_PATTERNS):
        match = pattern.search(page)
        if match:
            value = int(match.group(1))
            return value // 1000 if index else value   # approxDurationMs — millisekund
    return 0


def _vimeo_oembed_duration(video_id):
    response = requests.get(
        'https://vimeo.com/api/oembed.json',
        params={'url': f'https://vimeo.com/{video_id}'},
        headers={'User-Agent': _UA},
        timeout=FETCH_TIMEOUT,
    )
    response.raise_for_status()
    return int(response.json().get('duration') or 0)


def _vimeo_config_duration(video_id):
    """Zaxira yo'l: oembed faqat ochiq videolarni biladi, pleer config esa
    embed qilinadigan (shu jumladan ro'yxatda ko'rinmaydigan) videolarni ham."""
    response = requests.get(
        f'https://player.vimeo.com/video/{video_id}/config',
        headers={'User-Agent': _UA, 'Referer': 'https://player.vimeo.com/'},
        timeout=FETCH_TIMEOUT,
    )
    response.raise_for_status()
    return int(((response.json().get('video') or {}).get('duration')) or 0)


def _fetch_duration(video):
    """Manbalarni navbat bilan sinaydi; birinchi ishonchli natijani qaytaradi."""
    video_id = video.get_video_id()
    if not video_id:
        return 0

    sources = (
        (_vimeo_oembed_duration, _vimeo_config_duration) if video.is_vimeo
        else (_youtube_api_duration, _youtube_innertube_duration, _youtube_page_duration)
    )
    for source in sources:
        try:
            seconds = source(video_id)
        except Exception:
            continue
        if MIN_PLAUSIBLE <= seconds <= MAX_PLAUSIBLE:
            return seconds
    return 0


def resolve_verified_duration(video):
    """Serverda tasdiqlangan davomiylikni (soniya) qaytaradi; 0 — aniqlanmadi.

    Muvaffaqiyatli natija DB'da qulflanadi, shuning uchun tashqi so'rov har bir
    video uchun amalda bir marta ketadi. Xatolikda `duration_checked_at` yoziladi
    va `RETRY_AFTER` o'tmaguncha qayta urinilmaydi (har heartbeat'da YouTube'ga
    chiqib so'rovni sekinlashtirmaslik uchun).

    DIQQAT: tashqi HTTP so'rovi bor — DB tranzaksiyasi ichida chaqirmang.
    """
    from .models import VideoLesson

    if video.verified_duration_seconds:
        return video.verified_duration_seconds

    now = timezone.now()
    if video.duration_checked_at and now - video.duration_checked_at < RETRY_AFTER:
        return 0

    seconds = _fetch_duration(video)

    fields = {'duration_checked_at': now}
    if seconds:
        fields['verified_duration_seconds'] = seconds
        if not video.duration:
            # `duration` (daqiqa) coin miqdori va statistika uchun ishlatiladi.
            fields['duration'] = max(1, round(seconds / 60))

    VideoLesson.objects.filter(pk=video.pk).update(**fields)
    for name, value in fields.items():
        setattr(video, name, value)
    return seconds
