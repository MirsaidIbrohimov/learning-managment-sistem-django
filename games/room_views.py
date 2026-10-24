""""Sheriklar bilan" poyga xonalari: lobby, xona sahifasi va polling API."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from . import rooms
from .models import TypingRoom, TypingRoomPlayer


def _room(code):
    return get_object_or_404(TypingRoom.objects.select_related('game', 'prompt', 'host'), code=code.upper())


def _int(value, default):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


@login_required
def lobby(request):
    rooms.expire_stale_lobbies()
    open_rooms = (TypingRoom.objects.filter(status='lobby', is_public=True)
                  .select_related('host', 'game').prefetch_related('players')
                  .order_by('-created_at')[:20])
    my_active = (TypingRoom.objects.filter(status__in=('lobby', 'running'), players__user=request.user)
                 .select_related('game').distinct())
    history = (TypingRoomPlayer.objects.filter(user=request.user, room__status='finished')
               .select_related('room', 'room__game', 'room__winner')
               .order_by('-room__finished_at')[:10])
    games = list(rooms.typing_games())
    rules = rooms.wager_rules(games[0]) if games else {'min': 5, 'max': 5000, 'fee_percent': 15}
    return render(request, 'games/student/rooms_lobby.html', {
        'open_rooms': open_rooms,
        'my_active': my_active,
        'history': history,
        'games': games,
        'stakes': [s for s in rooms.STAKE_PRESETS if s == 0 or rules['min'] <= s <= rules['max']],
        'rules': rules,
        'player_counts': range(rooms.MIN_PLAYERS, rooms.MAX_PLAYERS + 1),
        'fee_percent': rules['fee_percent'],
    })


@login_required
@require_POST
def create(request):
    game = rooms.typing_games().filter(pk=_int(request.POST.get('game'), 0)).first() or rooms.typing_games().first()
    if not game:
        messages.error(request, "Hozircha faol yozish o'yini yo'q.")
        return redirect('games:rooms_lobby')
    try:
        room = rooms.create_room(
            request.user, game,
            # O'z miqdori kiritilsa — u ustun (boshqa coinli o'yinlardagidek erkin tikish)
            stake=_int(request.POST.get('custom_stake') or request.POST.get('stake'), 0),
            max_players=_int(request.POST.get('max_players'), 4),
            is_public=request.POST.get('is_public') == 'on',
        )
    except rooms.RoomError as exc:
        messages.error(request, str(exc))
        return redirect('games:rooms_lobby')
    return redirect('games:room_detail', code=room.code)


@login_required
def join_by_code(request):
    code = (request.GET.get('code') or '').strip().upper().replace('XONA', '').replace('·', '').strip()
    if not TypingRoom.objects.filter(code=code).exists():
        messages.error(request, f"\"{code}\" kodli xona topilmadi.")
        return redirect('games:rooms_lobby')
    return redirect('games:room_detail', code=code)


@login_required
def detail(request, code):
    room = _room(code)
    return render(request, 'games/student/room.html', {
        'room': room,
        'invite_url': request.build_absolute_uri(),
        'state': rooms.state(room, request.user),
        'fee_percent': room.fee_percent,
    })


@login_required
def state(request, code):
    return JsonResponse(rooms.state(_room(code), request.user))


def _action(fn):
    @login_required
    @require_POST
    def view(request, code):
        room = _room(code)
        try:
            fn(request, room)
        except rooms.RoomError as exc:
            return JsonResponse({'error': str(exc), 'state': rooms.state(room, request.user)}, status=400)
        return JsonResponse(rooms.state(room, request.user))
    view.__name__ = fn.__name__
    return view


join = _action(lambda request, room: rooms.join(room, request.user))
leave = _action(lambda request, room: rooms.leave(room, request.user))
start = _action(lambda request, room: rooms.start(room, request.user))
progress = _action(lambda request, room: rooms.record_progress(room, request.user, request.POST.get('typed_text', '')[:5000]))
