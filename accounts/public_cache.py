"""Cache public landing DATA, preserving fresh CSRF tokens and user responses."""
from django.conf import settings
from django.core.cache import cache


def landing_data():
    from accounts.models import CustomUser, Profession
    from blog.models import Post

    ttl = settings.LANDING_CACHE_SECONDS
    key = 'landing-public-data:v1'
    data = cache.get(key) if ttl else None
    if data is None:
        data = {
            'professions': list(Profession.objects.filter(is_blocked=False)[:6]),
            'posts': list(Post.objects.filter(is_published=True)[:3]),
            'total_students': CustomUser.objects.filter(role='student').count(),
            'total_courses': Profession.objects.count(),
        }
        if ttl:
            cache.set(key, data, ttl)
    return data
