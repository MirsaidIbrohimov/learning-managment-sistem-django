"""MY StartUp REST API (öqiş uçun).

Ruxsatlar `startup.permissions` dagi AYNAN öşa funksiyalar bilan
tekşiriladi — web view va API bir xil qoidaga böysunadi, aks holda API
IDOR teşigiga aylanadi.
"""

from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from api.permissions import IsNotBlocked
from startup import services
from startup.models import PitchDeck, Startup, StartupTask
from startup.permissions import (
    can_view_private,
    can_view_startup,
    get_active_startup,
    is_active_member,
    is_mentor_of,
    is_owner,
    is_staff_admin,
)
from .serializers import (
    FinanceSerializer,
    LeaderboardEntrySerializer,
    MemberSerializer,
    MetricSerializer,
    PitchDeckSerializer,
    StageSerializer,
    StartupCardSerializer,
    StartupDetailSerializer,
    TaskSerializer,
)

MAX_LIMIT = 100


def _limit(request, default=20):
    raw = request.query_params.get('limit', default)
    try:
        return max(1, min(int(raw), MAX_LIMIT))
    except (TypeError, ValueError):
        return default


def _startup(slug):
    return get_object_or_404(
        Startup.objects.select_related('owner', 'profession'), slug=slug)


def _public(request, slug):
    startup = _startup(slug)
    if not can_view_startup(request.user, startup):
        raise PermissionDenied('Bu startupga ruxsatingiz yöq.')
    return startup


def _private(request, slug):
    startup = _startup(slug)
    if not can_view_private(request.user, startup):
        raise PermissionDenied('Bu bölim faqat jamoa, mentor va admin uçun.')
    return startup


def _access(user, startup):
    return {
        'is_owner': is_owner(user, startup),
        'is_member': is_active_member(user, startup),
        'is_mentor': is_mentor_of(user, startup),
        'is_staff_admin': is_staff_admin(user),
        'can_view_private': can_view_private(user, startup),
    }


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsNotBlocked])
def leaderboard(request):
    """TOP startuplar. Query: period=all|month|week, profession=<id>, limit."""
    period = request.query_params.get('period', 'all')
    if period not in ('all', 'month', 'week'):
        period = 'all'

    profession_id = request.query_params.get('profession') or None
    if profession_id and not str(profession_id).isdigit():
        profession_id = None

    limit = _limit(request, 20)
    my_id = getattr(get_active_startup(request.user), 'id', None)

    rows = list(services.leaderboard_queryset(period, profession_id)[:limit])
    for index, row in enumerate(rows, start=1):
        row.rank = index
        row.is_mine = row.id == my_id

    return Response({
        'period': period,
        'profession': int(profession_id) if profession_id else None,
        'count': len(rows),
        'results': LeaderboardEntrySerializer(rows, many=True).data,
        'my_startup_id': my_id,
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsNotBlocked])
def me(request):
    """Joriy foydalanuvçining faol startupi (yöq bölsa `startup: null`)."""
    startup = get_active_startup(request.user)
    if startup is None:
        joined = (Startup.objects
                  .filter(members__user=request.user, members__status='active')
                  .select_related('owner')
                  .exclude(owner=request.user))
        return Response({
            'startup': None,
            'joined': StartupCardSerializer(joined, many=True).data,
        })

    stats = startup.tasks.aggregate(
        total=Count('id'),
        done=Count('id', filter=Q(status='COMPLETED')),
        open=Count('id', filter=Q(status__in=('TODO', 'IN_PROGRESS', 'REJECTED'))),
        review=Count('id', filter=Q(status='SUBMITTED')),
    )
    return Response({
        'startup': StartupDetailSerializer(startup).data,
        'tasks': stats,
        'finance': services.finance_summary(startup),
        'achievements': list(startup.achievements.values_list('code', flat=True)),
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsNotBlocked])
def detail(request, slug):
    startup = _public(request, slug)
    data = StartupDetailSerializer(startup).data
    data['member_count'] = startup.members.filter(status='active').count()
    data['access'] = _access(request.user, startup)
    if data['access']['can_view_private']:
        data['finance'] = services.finance_summary(startup)
    return Response(data)


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsNotBlocked])
def progress(request, slug):
    startup = _public(request, slug)
    stats = startup.tasks.aggregate(
        total=Count('id'), done=Count('id', filter=Q(status='COMPLETED')))
    return Response({
        'slug': startup.slug,
        'progress': startup.progress,
        'current_stage': startup.current_stage,
        'stage_label': startup.current_stage_label,
        'stage_index': startup.stage_index,
        'total_xp': startup.total_xp,
        'tasks': stats,
        'stages': StageSerializer(startup.stages.all(), many=True).data,
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsNotBlocked])
def tasks(request, slug):
    startup = _private(request, slug)
    queryset = (startup.tasks
                .select_related('stage', 'assigned_to')
                .order_by('stage__order', 'id'))

    status = request.query_params.get('status')
    if status in dict(StartupTask._meta.get_field('status').choices):
        queryset = queryset.filter(status=status)
    if request.query_params.get('mine') == '1':
        queryset = queryset.filter(assigned_to=request.user)

    return Response({
        'count': queryset.count(),
        'results': TaskSerializer(queryset[:_limit(request, 50)], many=True).data,
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsNotBlocked])
def team(request, slug):
    """Faol a'zolar oçiq; kutilayotgan sörovlar faqat yopiq ruxsat bilan."""
    startup = _public(request, slug)
    members = startup.members.filter(status='active').select_related('user')
    payload = {
        'count': members.count(),
        'members': MemberSerializer(members, many=True).data,
        'mentors': [
            {'id': link.mentor_id,
             'username': link.mentor.username,
             'full_name': link.mentor.full_name}
            for link in startup.mentors.filter(is_active=True).select_related('mentor')
        ],
    }
    if can_view_private(request.user, startup):
        pending = startup.members.filter(status='pending').select_related('user')
        payload['pending'] = MemberSerializer(pending, many=True).data
    return Response(payload)


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsNotBlocked])
def metrics(request, slug):
    startup = _private(request, slug)
    return Response({
        'series': services.metric_series(startup),
        'recent': MetricSerializer(startup.metrics.all()[:_limit(request, 30)],
                                   many=True).data,
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsNotBlocked])
def finance(request, slug):
    startup = _private(request, slug)
    return Response({
        'summary': services.finance_summary(startup),
        'entries': FinanceSerializer(startup.finances.all()[:_limit(request, 50)],
                                     many=True).data,
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsNotBlocked])
def pitch(request, slug):
    startup = _private(request, slug)
    deck, _ = PitchDeck.objects.get_or_create(startup=startup)
    return Response(PitchDeckSerializer(deck).data)
