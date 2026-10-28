"""Ommaviy huquqiy sahifalar: maxfiylik siyosati va ma'lumotlarni o'chirish yo'riqnomasi.

Facebook (Meta) va Google ilova sozlamalarida shu sahifalar havolasi talab qilinadi,
shuning uchun ular login talab qilmaydi.
"""
from email.utils import parseaddr

from django.conf import settings
from django.shortcuts import render

UPDATED = '28.10.2026'


def _ctx():
    return {
        'updated': UPDATED,
        'site_url': getattr(settings, 'SITE_URL', '') or 'https://itc-academy.uz',
        # DEFAULT_FROM_EMAIL "Nom <a@b.uz>" ko'rinishida bo'lishi mumkin
        'contact_email': parseaddr(getattr(settings, 'DEFAULT_FROM_EMAIL', ''))[1].replace('webmaster@localhost', ''),
    }


def privacy_policy(request):
    return render(request, 'accounts/legal/privacy.html', _ctx())


def data_deletion(request):
    return render(request, 'accounts/legal/data_deletion.html', _ctx())
