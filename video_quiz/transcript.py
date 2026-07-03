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
    """Xom YouTube video_id uchun transkript oladi."""
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
    except ImportError:
        return '', "`youtube-transcript-api` kutubxonasi o'rnatilmagan.", []

    api = YouTubeTranscriptApi()
    fetched = None
    try:
        fetched = api.fetch(video_id, languages=PREFERRED_LANGS)
    except Exception:
        # Ustuvor tillarda topilmadi — mavjud har qanday transkriptni sinab ko'ramiz
        try:
            transcript_list = api.list(video_id)
            transcript = None
            try:
                transcript = transcript_list.find_transcript(PREFERRED_LANGS)
            except Exception:
                for t in transcript_list:  # birinchi mavjud (odatda avtomatik)
                    transcript = t
                    break
            if transcript is None:
                return '', "Bu video uchun transkript (subtitr) topilmadi.", []
            fetched = transcript.fetch()
        except Exception as e:
            return '', _friendly_error(e), []

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
