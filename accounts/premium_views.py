"""💎 Premium profil bezaklari sahifasi (ramka, ism rangi, banner, oltin mavzu)."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from .models import CustomUser
from .premium_bonus import is_active_premium

DECO_FIELDS = {
    'profile_frame': CustomUser.PROFILE_FRAME_CHOICES,
    'name_color': CustomUser.NAME_COLOR_CHOICES,
    'profile_banner': CustomUser.PROFILE_BANNER_CHOICES,
}


@login_required
def premium_customize(request):
    user = request.user
    active = is_active_premium(user)

    if request.method == 'POST':
        if not active:
            messages.error(request, "Profilni bezaş faqat Premium a'zolar uçun. 💎")
            return redirect('coin:buy_premium_page')
        for field, choices in DECO_FIELDS.items():
            value = request.POST.get(field)
            if value in dict(choices):
                setattr(user, field, value)
        user.gold_theme = request.POST.get('gold_theme') == 'on'
        user.save(update_fields=[*DECO_FIELDS, 'gold_theme'])
        messages.success(request, "Profil bezaklari saqlandi! ✨")
        return redirect('profile')

    return render(request, 'accounts/premium_customize.html', {
        'is_active_premium': active,
        'frames': CustomUser.PROFILE_FRAME_CHOICES,
        'name_colors': CustomUser.NAME_COLOR_CHOICES,
        'banners': CustomUser.PROFILE_BANNER_CHOICES,
    })
