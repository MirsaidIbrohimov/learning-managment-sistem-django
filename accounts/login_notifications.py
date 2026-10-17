"""Capture only device information actually supplied by the login request."""
import re

from django.utils import timezone


def login_details(request):
    from .security import get_client_ip

    ua = request.META.get('HTTP_USER_AGENT', '')[:4096]
    unknown = "Aniqlanmadi"
    device = unknown
    device_type = unknown
    os_name = unknown
    for pattern, name in (
        (r'(?:iPhone OS|CPU OS) ([\d_]+)', 'iOS'),
        (r'Android[ /]([\d.]+)', 'Android'),
        (r'Windows NT ([\d.]+)', 'Windows NT'),
        (r'Mac OS X[ /]([\d_]+)', 'macOS'),
        (r'CrOS [^;)]+', 'ChromeOS'),
    ):
        match = re.search(pattern, ua)
        if match:
            os_name = name + (' ' + match.group(1).replace('_', '.') if match.lastindex else '')
            break
    if 'iPad' in ua:
        device, device_type = 'Apple iPad', 'Planshet'
    elif 'iPhone' in ua:
        device, device_type = 'Apple iPhone', 'Telefon'
    elif 'Android' in ua:
        device_type = 'Telefon' if 'Mobile' in ua else 'Planshet'
        match = re.search(r'Android[^;)]*;\s*(?:[a-z]{2}(?:[-_][A-Z]{2})?;\s*)?([^;)]+)', ua)
        if match:
            device = re.split(r'\s+Build/', match.group(1))[0].strip() or unknown
            if device == 'K':
                device = unknown
    elif any(token in ua for token in ('Windows', 'Macintosh', 'Linux', 'CrOS')):
        device_type = 'Kompyuter'
        if 'Macintosh' in ua:
            device = 'Apple Mac (model aniqlanmadi)'
        if os_name == unknown and 'Linux' in ua:
            os_name = 'Linux'

    browser = unknown
    for token, name in (
        ('EdgiOS', 'Edge'), ('EdgA', 'Edge'), ('Edg', 'Edge'),
        ('OPR', 'Opera'), ('SamsungBrowser', 'Samsung Internet'),
        ('CriOS', 'Chrome iOS'), ('FxiOS', 'Firefox iOS'),
        ('Chrome', 'Chrome'), ('Firefox', 'Firefox'), ('Version', 'Safari'),
    ):
        match = re.search(r'\b' + token + r'/([\d.]+)', ua)
        if match:
            browser = name + ' ' + match.group(1)
            break
    return {
        'device': device, 'device_type': device_type, 'os': os_name,
        'browser': browser, 'ip': get_client_ip(request) or unknown,
        'time': timezone.localtime().strftime('%d.%m.%Y %H:%M:%S %Z'),
        'user_agent': ua or unknown,
    }
