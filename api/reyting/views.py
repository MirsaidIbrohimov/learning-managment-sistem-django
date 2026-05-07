import logging

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.db.models import Q, Sum
from django.core.cache import cache
from accounts.models import CustomUser, Profession, HomeworkSubmission
from api.permissions import IsNotBlocked

logger = logging.getLogger(__name__)


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsNotBlocked])
def leaderboard_api(request):
    """
    Leaderboard API - returns JSON data for the leaderboard.
    Query params: tab (coins/score), profession (id), q (search text), limit (default 100)
    """
    tab = request.query_params.get('tab', 'coins')
    profession_id = request.query_params.get('profession', '')
    search_query = request.query_params.get('q', '').strip()
    limit = min(int(request.query_params.get('limit', 100)), 200)

    logger.info(
        "Leaderboard API accessed by user=%s tab=%s profession=%s",
        request.user.pk, tab, profession_id,
    )

    professions_data = list(Profession.objects.values('id', 'name'))

    if tab == 'score':
        cache_key = f'lb_api_score_{profession_id or "all"}_{search_query}'
        cached = cache.get(cache_key)

        if not cached:
            students_qs = CustomUser.objects.filter(role='student', is_blocked=False)
            if profession_id:
                students_qs = students_qs.filter(enrollments__profession_id=profession_id).distinct()
            if search_query:
                students_qs = students_qs.filter(
                    Q(first_name__icontains=search_query) |
                    Q(last_name__icontains=search_query) |
                    Q(username__icontains=search_query)
                )

            student_ids = list(students_qs.values_list('id', flat=True))

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
            cached = scored_data
            cache.set(cache_key, cached, 120)

        user_rank = None
        user_score = 0
        if request.user.role == 'student':
            for i, s in enumerate(cached):
                if s['id'] == request.user.pk:
                    user_rank = i + 1
                    user_score = s['score']
                    break

        top_ids = [s['id'] for s in cached[:limit]]
        students_map = {s.pk: s for s in CustomUser.objects.filter(pk__in=top_ids).only(
            'id', 'username', 'first_name', 'last_name', 'photo', 'is_premium', 'coins'
        )}

        students_list = []
        for idx, s in enumerate(cached[:limit]):
            student = students_map.get(s['id'])
            if student:
                students_list.append({
                    'rank': idx + 1,
                    'first_name': student.first_name,
                    'last_name': student.last_name,
                    'full_name': student.full_name,
                    'initials': student.get_initials(),
                    'photo': student.photo.url if student.photo else None,
                    'is_premium': student.is_premium,
                    'is_you': student.pk == request.user.pk,
                    'value': s['score'],
                })

        return Response({
            'tab': tab,
            'students': students_list,
            'professions': professions_data,
            'user_rank': user_rank,
            'user_value': user_score,
            'user_in_list': user_rank is not None,
            'total': len(cached),
        })

    # Coins tab (default)
    students_qs = CustomUser.objects.filter(role='student', is_blocked=False).order_by('-coins')

    if profession_id:
        students_qs = students_qs.filter(enrollments__profession_id=profession_id).distinct().order_by('-coins')
    if search_query:
        students_qs = students_qs.filter(
            Q(first_name__icontains=search_query) |
            Q(last_name__icontains=search_query) |
            Q(username__icontains=search_query)
        )

    user_rank = None
    if request.user.role == 'student':
        all_ids = list(students_qs.values_list('pk', flat=True))
        if request.user.pk in all_ids:
            user_rank = all_ids.index(request.user.pk) + 1
        else:
            all_ranked = list(CustomUser.objects.filter(role='student', is_blocked=False).order_by('-coins').values_list('pk', flat=True))
            if request.user.pk in all_ranked:
                user_rank = all_ranked.index(request.user.pk) + 1

    students_data = students_qs[:limit]
    students_list = []
    for idx, student in enumerate(students_data):
        students_list.append({
            'rank': idx + 1,
            'first_name': student.first_name,
            'last_name': student.last_name,
            'full_name': student.full_name,
            'initials': student.get_initials(),
            'photo': student.photo.url if student.photo else None,
            'is_premium': student.is_premium,
            'is_you': student.pk == request.user.pk,
            'value': student.coins,
        })

    return Response({
        'tab': tab,
        'students': students_list,
        'professions': professions_data,
        'user_rank': user_rank,
        'user_value': request.user.coins if request.user.role == 'student' else 0,
        'user_in_list': user_rank is not None,
        'total': students_qs.count(),
    })
