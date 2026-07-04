"""
YouTube transkriptini olish yordamchisi (youtube-transcript-api v1.x).

Bu modul video darsdan (yoki xom YouTube video_id'dan) matnli transkript
qaytaradi. AI test generatori uni kontekst sifatida ishlatadi.

Dizayn:
  * DB'ga hech narsa yozmaydi — faqat tashqi YouTube API'ga so'rov yuboradi.
  * Har doim (matn, xatolik, snippetlar) uchligini qaytaradi; xatolikda
    matn bo'sh, snippetlar bo'sh, xatolik esa foydalanuvchiga ko'rsatiladigan
    o'zbekcha xabar bo'ladi.
  * Til ustuvorligi: o'zbek → ingliz → rus, topilmasa mavjud har qanday
    (jumladan avtomatik yaratilgan) transkript olinadi.
"""
from __future__ import annotations

from typing import List, Optional, Tuple

# Transkript qidiriladigan tillar (ustuvorlik tartibida)
PREFERRED_LANGS = ['uz', 'en', 'ru']


def fetch_transcript_text(video, *, max_chars: int = 16000) -> Tuple[str, Optional[str], List[dict]]:
    """VideoLesson uchun transkript oladi.

    (text, error, snippets) qaytaradi. `snippets` — {'text','start','duration'}
    lug'atlar ro'yxati (xatolikda bo'sh).
    """
    if not video:
        return '', "Video topilmadi.", []
    if not getattr(video, 'is_youtube', False):
        return '', "Faqat YouTube videolaridan transkript olish mumkin.", []
    video_id = video.get_video_id()
    if not video_id:
        return '', "Video ID aniqlanmadi.", []
    return fetch_transcript_by_id(video_id, max_chars=max_chars)


def fetch_transcript_by_id(video_id: str, *, max_chars: int = 16000) -> Tuple[str, Optional[str], List[dict]]:
    """Xom YouTube video_id uchun transkript oladi (ko'p bosqichli fallback)."""
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
    except ImportError:
        return '', "`youtube-transcript-api` kutubxonasi o'rnatilmagan.", []

    api = _build_api(YouTubeTranscriptApi)
    fetched, error = _fetch_with_fallbacks(api, video_id)
    if fetched is None:
        return '', error, []

    snippets = []
    for s in fetched:
        text = (getattr(s, 'text', '') or '').replace('\n', ' ').strip()
        if not text:
            continue
        snippets.append({
            'text': text,
            'start': float(getattr(s, 'start', 0) or 0),
            'duration': float(getattr(s, 'duration', 0) or 0),
        })

    full_text = ' '.join(part['text'] for part in snippets)
    full_text = ' '.join(full_text.split())  # ortiqcha bo'shliqlarni tozalash
    if not full_text:
        return '', "Transkript bo'sh chiqdi.", []
    if len(full_text) > max_chars:
        full_text = full_text[:max_chars]
    return full_text, None, snippets


def _build_api(YouTubeTranscriptApi):
    """API instance — .env dagi ixtiyoriy proxy bilan (YouTube IP blokidan qochish).

    Muhitda YT_TRANSCRIPT_PROXY (masalan: http://user:pass@host:port) bo'lsa,
    so'rovlar shu proxy orqali ketadi. Bu — server IP'si YouTube tomonidan
    bloklanganda ko'p videolar subtitri olinmasligini bartaraf etadi.
    """
    import os
    proxy = (os.environ.get('YT_TRANSCRIPT_PROXY') or '').strip()
    if proxy:
        try:
            from youtube_transcript_api.proxies import GenericProxyConfig
            return YouTubeTranscriptApi(
                proxy_config=GenericProxyConfig(http_url=proxy, https_url=proxy)
            )
        except Exception:
            pass  # proxy sozlanmasa — oddiy API bilan davom etamiz
    return YouTubeTranscriptApi()


def _fetch_with_fallbacks(api, video_id):
    """Transkriptni bir necha bosqichda qidiradi. (fetched | None, error) qaytaradi.

    Bosqichlar:
      1) Ustuvor tillar (uz/en/ru) — manual yoki avtomatik;
      2) list() orqali: preferred / generated / manual finder'lar;
      3) mavjud har qanday transkript (odatda avtomatik yaratilgan);
      4) preferred til bo'lmasa — preferred tilga TARJIMA qilishga urinadi.
    IpBlocked/RequestBlocked'da bir marta qayta uriniladi.
    """
    import time
    last_exc = None
    for attempt in range(2):  # 1 ta qayta urinish (IP/transient xatolar uchun)
        # 1) To'g'ridan-to'g'ri ustuvor tillar
        try:
            return api.fetch(video_id, languages=PREFERRED_LANGS), None
        except Exception as e:
            last_exc = e

        # 2) list() orqali kengroq qidiruv
        try:
            tl = api.list(video_id)
        except Exception as e:
            last_exc = e
            if type(e).__name__ in ('IpBlocked', 'RequestBlocked') and attempt == 0:
                time.sleep(1.2)
                continue
            return None, _friendly_error(e)

        # 2a) preferred / generated / manual finder'lar (versiyaga qarab mavjudi ishlaydi)
        for finder in ('find_transcript', 'find_generated_transcript',
                       'find_manually_created_transcript'):
            fn = getattr(tl, finder, None)
            if fn is None:
                continue
            try:
                return fn(PREFERRED_LANGS).fetch(), None
            except Exception:
                pass

        # 2b) mavjud har qanday transkript
        any_tr = None
        try:
            for t in tl:
                any_tr = t
                break
        except Exception:
            any_tr = None

        if any_tr is None:
            return None, "Bu video uchun subtitr (transkript) topilmadi."

        # 3) preferred tilda bo'lmasa — tarjima qilishga urinamiz (AI konteksti uchun)
        try:
            lang_code = getattr(any_tr, 'language_code', '') or ''
            if lang_code not in PREFERRED_LANGS and getattr(any_tr, 'is_translatable', False):
                for lang in PREFERRED_LANGS:
                    try:
                        return any_tr.translate(lang).fetch(), None
                    except Exception:
                        continue
        except Exception:
            pass

        # 4) tarjima bo'lmasa — asl tilida qaytaramiz
        try:
            return any_tr.fetch(), None
        except Exception as e:
            last_exc = e
            if type(e).__name__ in ('IpBlocked', 'RequestBlocked') and attempt == 0:
                time.sleep(1.2)
                continue
            return None, _friendly_error(e)

    return None, _friendly_error(last_exc) if last_exc else "Transkript olinmadi."


def _friendly_error(exc: Exception) -> str:
    """youtube-transcript-api xatoliklarini o'zbekcha xabarga o'giradi."""
    name = type(exc).__name__
    mapping = {
        'TranscriptsDisabled': "Bu videoda subtitrlar o'chirilgan.",
        'NoTranscriptFound': "Bu video uchun transkript topilmadi.",
        'VideoUnavailable': "Video mavjud emas yoki maxfiy.",
        'InvalidVideoId': "Video ID noto'g'ri.",
        'IpBlocked': "YouTube so'rovni blokladi (IP). Keyinroq urinib ko'ring.",
        'RequestBlocked': "YouTube so'rovni blokladi. Keyinroq urinib ko'ring.",
        'AgeRestricted': "Video yosh chekloviga ega — transkript olib bo'lmaydi.",
    }
    return mapping.get(name, f"Transkriptni olishda xatolik: {exc}")


# Bu fayl: YouTube videodan matnli transkript oluvchi yagona yordamchi.
# Ham video-quiz (bitta video), ham quiz (bo'lim bo'yicha bir nechta video)
# generatorlari shu moduldan foydalanadi (DRY).
