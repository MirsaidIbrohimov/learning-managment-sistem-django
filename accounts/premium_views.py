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



# Rasm muharriri sahifalari: orqa fon va profil banneri bir xil muharrirdan foydalanadi.
MEDIA_PAGES = {
    'wallpaper': {
        'url_name': 'wallpaper_customize',
        'title': "Orqa fonni bezaş",
        'icon': 'bi-image',
        'intro': "Saytning orqa foniga öz rasmingizni qöying, filtr va sozlamalar bilan moslang.",
        'format': "Tavsiya etiladigan format: 1920×1080 px yoki kattaroq (16:9, gorizontal), JPG yoki WEBP, 10 MB gaça.",
        'saved': "Orqa fon saqlandi! 🖼",
        'removed': "Orqa fon olib taşlandi.",
    },
    'banner': {
        'url_name': 'banner_customize',
        'title': "Banner rasmi",
        'icon': 'bi-card-image',
        'intro': "Profil banneringizga öz rasmingizni qöying — u profilingiz, reyting va çatdagi ma'lumot panelida körinadi.",
        'format': ("Tavsiya etiladigan format: 1500×500 px (3:1, keng gorizontal), JPG yoki WEBP, 5 MB atrofida. "
                   "Muhim qismini (yuz, yozuv) markazga joylang — kiçik ekranlarda çetlari kesilişi mumkin."),
        'saved': "Banner rasmi saqlandi! 🖼",
        'removed': "Banner rasmi olib taşlandi.",
    },
}


def _media_customize(request, kind):
    from django.core.exceptions import ValidationError

    from . import wallpaper as wp

    page = MEDIA_PAGES[kind]
    field, style_field, max_side, _ = wp.KINDS[kind]
    user = request.user
    allowed = wp.can_use_wallpaper(user)
    image = getattr(user, field)

    if request.method == 'POST':
        if not allowed:
            messages.error(request, f"{page['title']} faqat Premium a'zolar uçun. 💎")
            return redirect('coin:buy_premium_page')
        old = image.name if image else None
        if request.POST.get('action') == 'remove':
            setattr(user, field, None)
            setattr(user, style_field, {})
            user.save(update_fields=[field, style_field])
            if old:
                image.storage.delete(old)
            messages.success(request, page['removed'])
            return redirect(page['url_name'])

        upload = request.FILES.get('image') or request.FILES.get(field)
        if upload:
            try:
                content = wp.process_upload(upload, max_side)
                image.save(f'{user.pk}_{content.name}', content, save=False)
            except ValidationError as e:
                messages.error(request, e.messages[0])
                return redirect(page['url_name'])
        elif not image:
            messages.error(request, "Avval rasm tanlang.")
            return redirect(page['url_name'])
        setattr(user, style_field, wp.clean_style(request.POST, kind))
        user.save(update_fields=[field, style_field])
        if upload and old and old != image.name:
            image.storage.delete(old)
        messages.success(request, page['saved'])
        return redirect(page['url_name'])

    return render(request, 'accounts/wallpaper_customize.html', {
        'kind': kind,
        'page': page,
        'can_use_wallpaper': allowed,
        'wp_style': wp.clean_style(getattr(user, style_field) or {}, kind),
        'wp_defaults': wp.defaults(kind),
        'wp_url': image.url if image else '',
        'positions': (('center', "Markaz"), ('top', "Yuqori"), ('bottom', "Pastki"), ('left', "Çap"), ('right', "Öng")),
    })


@login_required
def wallpaper_customize(request):
    """🖼 Orqa fonni bezaş: rasm, filtrlar va sozlamalar (Premium + admin/öqituvçi)."""
    return _media_customize(request, 'wallpaper')


@login_required
def banner_customize(request):
    """🖼 Profil banneri uçun rasm (Premium + admin/öqituvçi)."""
    return _media_customize(request, 'banner')


@login_required
def premium_settings_view(request):
    """💎 Premium sozlamalar: 3D shakl va sessiya xavfsizligi (faolsizlik muddati, IP özgarişi)."""
    from . import premium_settings as ps
    from .models import PremiumSettings
    from .security import get_client_ip

    user = request.user
    active = is_active_premium(user)

    if request.method == 'POST':
        if not active:
            messages.error(request, "Bu sozlamalar faqat Premium a'zolar uçun. 💎")
            return redirect('coin:buy_premium_page')
        section = request.POST.get('section')
        changes = ps.clean(request.POST)
        if section == 'security':
            changes = {k: v for k, v in changes.items() if k == 'idle_timeout_minutes'}
            changes['logout_on_ip_change'] = request.POST.get('logout_on_ip_change') == 'on'
            msg = "Xavfsizlik sozlamalari saqlandi. 🔒"
        elif section == 'loader':
            changes = {k: v for k, v in changes.items() if k.startswith('loader_')}
            msg = "Yuklaniş animatsiyasi saqlandi! ✨"
        else:
            changes = {k: v for k, v in changes.items() if k.startswith('orb_')}
            msg = "3D shakl saqlandi! ✨"
        ps.save(user, changes)
        messages.success(request, msg)
        return redirect(f"{request.path}#{section if section in ('security', 'loader') else 'shape'}")

    return render(request, 'accounts/premium_settings.html', {
        'is_active_premium': active,
        'prefs': ps.stored(user),
        'shapes': PremiumSettings.SHAPE_CHOICES,
        'palettes': PremiumSettings.PALETTE_CHOICES,
        'speeds': PremiumSettings.SPEED_CHOICES,
        'idle_choices': PremiumSettings.IDLE_CHOICES,
        'client_ip': get_client_ip(request),
    })
