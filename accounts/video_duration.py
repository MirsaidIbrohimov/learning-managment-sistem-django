"""Video davomiyligini SERVER tomonda aniqlaş (anti-cheat asosi).

Köriş talabi (`VideoProgress.required_seconds`) davomiylikdan hisoblanadi.
Agar davomiylik mijozdan olinsa, öquvçi konsoldan `duration_seconds: 10`
yuborib talabni bir soniyaga tuşirib, videoni bir zumda "körilgan" qilib
qöya olardi. Şuning uçun davomiylikni server özi YouTube/Vimeo'dan oladi va
DB'da qulflaydi — mijoz bu qiymatga ta'sir qila olmaydi.
"""

import re
import threading
from datetime import timedelta

import requests
from django.conf import settings
from django.db import close_old_connections
from django.db.models import Q
from django.utils import timezone

FETCH_TIMEOUT = 6          # soniya — sörov yölida turgani uçun qisqa
RETRY_AFTER   = timedelta(minutes=10)   # muvaffaqiyatsiz urinişni takrorlaş oraliği
MIN_PLAUSIBLE = 5          # bundan qisqa qiymat xato deb hisoblanadi
MAX_PLAUSIBLE = 24 * 3600

_UA = (
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
    '(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
)

# YouTube sahifasidagi davomiylik: ytInitialPlayerResponse içida keladi.
_YT_PATTERNS = (
    re.compile(r'"lengthSeconds"\s*:\s*"?(\d+)"?'),
    re.compile(r'"approxDurationMs"\s*:\s*"(\d+)"'),
)

# Pleerning oçiq (kalitsiz emas, lekin hammaga ma'lum) InnerTube kaliti — brauzer
# ham xuddi şu sörovni yuboradi.
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

    Kalit faqat kvotani belgilaydi — egalikni emas, şuning uçun YouTube'dagi
    har qanday oçiq video öqiladi. Har bir video uçun natija DB'da
    qulflanadi, ya'ni amalda video soniga teng sörov ketadi (kvota: 1 birlik).
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
    """Zaxira: YouTube pleer API'si (kalitsiz, lekin köp sörovda bloklanadi).

    `watch` sahifasini öqişdan işonçliroq (429/captcha bermaydi) va
    playabilityStatus "UNPLAYABLE" bölsa ham `videoDetails.lengthSeconds`
    keladi. Lekin server IP'si bir neça sörovdan keyin "LOGIN_REQUIRED"
    olişi mumkin — şuning uçun asosiy manba emas.
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
    """Oxirgi zaxira: `watch` sahifasidan öqiş (server IP'da 429 ehtimoli yuqori)."""
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


def _vimeo_oembed_duration(video):
    response = requests.get(
        'https://vimeo.com/api/oembed.json',
        # Unlisted Vimeo videos require the original URL including its hash.
        params={'url': video.get_vimeo_url()},
        headers={'User-Agent': _UA},
        timeout=FETCH_TIMEOUT,
    )
    response.raise_for_status()
    return int(response.json().get('duration') or 0)


def _vimeo_config_duration(video):
    """Zaxira yöl: oembed faqat oçiq videolarni biladi, pleer config esa
    embed qilinadigan (şu jumladan röyxatda körinmaydigan) videolarni ham."""
    video_id = video.get_video_id()
    private_hash = video.get_vimeo_hash()
    params = {'h': private_hash} if private_hash else None
    response = requests.get(
        f'https://player.vimeo.com/video/{video_id}/config',
        params=params,
        headers={'User-Agent': _UA, 'Referer': 'https://player.vimeo.com/'},
        timeout=FETCH_TIMEOUT,
    )
    response.raise_for_status()
    return int(((response.json().get('video') or {}).get('duration')) or 0)


def _fetch_duration(video):
    """Manbalarni navbat bilan sinaydi; birinçi işonçli natijani qaytaradi."""
    video_id = video.get_video_id()
    if not video_id:
        return 0

    if video.is_vimeo:
        sources = (_vimeo_oembed_duration, _vimeo_config_duration)
        source_arg = video
    else:
        sources = (_youtube_api_duration, _youtube_innertube_duration, _youtube_page_duration)
        source_arg = video_id
    for source in sources:
        try:
            seconds = source(source_arg)
        except Exception:
            continue
        if MIN_PLAUSIBLE <= seconds <= MAX_PLAUSIBLE:
            return seconds
    return 0


def _claim_duration_check(video):
    """Tekşiruvni bitta workerga atomik biriktiradi; vaqtni yoki None qaytaradi."""
    from .models import VideoLesson

    now = timezone.now()
    retry_before = now - RETRY_AFTER
    claimed = VideoLesson.objects.filter(
        pk=video.pk,
        verified_duration_seconds=0,
    ).filter(
        Q(duration_checked_at__isnull=True) | Q(duration_checked_at__lte=retry_before)
    ).update(duration_checked_at=now)
    if not claimed:
        return None
    video.duration_checked_at = now
    return now


def _save_duration_result(video, seconds, checked_at):
    from .models import VideoLesson

    fields = {'duration_checked_at': checked_at}
    if seconds:
        fields['verified_duration_seconds'] = seconds
        # `duration` (daqiqa) coin miqdori, statistika va eski sahifalarda
        # işlatiladi. Qölda kiritilgan eski qiymat haqiqiy provider
        # davomiyligidan farq qilişi mumkin, şuning uçun uni ham yangilaymiz.
        fields['duration'] = max(1, round(seconds / 60))

    VideoLesson.objects.filter(pk=video.pk).update(**fields)
    for name, value in fields.items():
        setattr(video, name, value)


def resolve_verified_duration(video):
    """Davomiylikni hozir aniqlaydi; oddiy HTTP request içida çaqirmang.

    Muvaffaqiyatli natija DB'da qulflanadi, şuning uçun taşqi sörov har bir
    video uçun amalda bir marta ketadi. Xatolikda `duration_checked_at` yoziladi
    va `RETRY_AFTER` ötmagunça qayta urinilmaydi (har heartbeat'da YouTube'ga
    çiqib sörovni sekinlaştirmaslik uçun).

    DIQQAT: taşqi HTTP sörovi bor — DB tranzaksiyasi içida çaqirmang.
    """
    if video.verified_duration_seconds:
        return video.verified_duration_seconds

    checked_at = _claim_duration_check(video)
    if checked_at is None:
        return 0

    seconds = _fetch_duration(video)
    _save_duration_result(video, seconds, checked_at)
    return seconds


def schedule_verified_duration(video):
    """Taşqi davomiylik tekşiruvini requestni bloklamasdan bir marta boşlaydi."""
    if video.verified_duration_seconds:
        return False

    checked_at = _claim_duration_check(video)
    if checked_at is None:
        return False

    video_id = video.pk

    def _resolve():
        from .models import VideoLesson

        close_old_connections()
        try:
            fresh_video = VideoLesson.objects.get(pk=video_id)
            seconds = _fetch_duration(fresh_video)
            _save_duration_result(fresh_video, seconds, checked_at)
        finally:
            close_old_connections()

    threading.Thread(target=_resolve, daemon=True).start()
    return True
