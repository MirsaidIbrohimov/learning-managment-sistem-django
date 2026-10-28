"""Cache public landing DATA, preserving fresh CSRF tokens and user responses."""
from django.conf import settings
from django.core.cache import caches


def get_performance_cache():
    return caches[settings.PERFORMANCE_CACHE_ALIAS]


def landing_data():
    from accounts.models import Certificate, CustomUser, Profession, VideoLesson
    from blog.models import Post

    ttl = settings.LANDING_CACHE_SECONDS
    cache = get_performance_cache()
    key = 'landing-public-data:v2'
    data = cache.get(key) if ttl else None
    if data is None:
        visible = Profession.objects.filter(is_blocked=False)
        data = {
            'professions': list(visible[:12]),
            # Bir martalik tölov bilan sotiladigan kurslar (Profession.is_sold_once bilan bir xil şart)
            'paid_courses': list(visible.filter(is_paid=True, one_time_payment=True, one_time_price__gt=0)[:3]),
            'posts': list(Post.objects.filter(is_published=True)[:3]),
            'total_students': CustomUser.objects.filter(role='student').count(),
            'total_courses': Profession.objects.count(),
            'total_videos': VideoLesson.objects.count(),
            'total_certificates': Certificate.objects.count(),
        }
        if ttl:
            cache.set(key, data, ttl)
    return data
