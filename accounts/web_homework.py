"""Lossless, inert storage for browser-based homework projects."""
import html
import json

PREFIX = 'LMS_WEB_PROJECT_V1\n'


def valid_project(p):
    if not isinstance(p, dict) or not all(isinstance(v, str) for v in p.values()):
        return False
    if sum(len(v) for v in p.values()) > 150_000:
        return False
    if set(p) == {'html', 'css', 'js'}:
        return True
    if not {'language', 'code'} <= set(p) or not set(p) <= {'language', 'code', 'version', 'stdin'}:
        return False
    return (0 < len(p['language'].strip()) <= 60 and len(p['language']) <= 60
            and ('version' not in p or (p['language'] == 'python' and p['version'] in {'3.12', '3.13', '3.14'}))
            and len(p.get('stdin', '')) <= 20000)


def decode_project(content):
    if (not isinstance(content, str) or len(content) > 1_000_000
            or not content.startswith('<pre>' + PREFIX) or not content.endswith('</pre>')):
        return None
    try:
        project = json.loads(html.unescape(content[5:-6])[len(PREFIX):])
        if valid_project(project):
            return project
    except (ValueError, TypeError, AttributeError, RecursionError):
        pass
    return None


def encode_project(raw):
    if not isinstance(raw, str) or len(raw) > 1_000_000:
        raise ValueError('Kod juda uzun.')
    try:
        project = json.loads(raw)
    except (ValueError, TypeError, RecursionError):
        raise ValueError('Kod formati noto‘g‘ri.')
    if not valid_project(project):
        raise ValueError('Kod loyihasi formati yoki hajmi noto\u2018g\u2018ri.')
    if not all(isinstance(v, str) for v in project.values()):
        raise ValueError('Kod matn ko‘rinishida bo‘lishi kerak.')
    if not any(v.strip() for k, v in project.items() if k in {'code', 'html', 'css', 'js'}):
        raise ValueError('Avval kod yozing.')
    if sum(len(v) for v in project.values()) > 150_000:
        raise ValueError('Kod juda uzun (maksimum 150 000 belgi).')
    return '<pre>' + PREFIX + html.escape(json.dumps(project, ensure_ascii=False)) + '</pre>'


def project_source(project):
    if 'language' in project:
        return f"--- {project['language']} {project.get('version', '')} ---\n{project['code']}"
    return '\n\n'.join(f'--- {name} ---\n{project[key]}' for key, name in (
        ('html', 'index.html'), ('css', 'style.css'), ('js', 'script.js')))
