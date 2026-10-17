"""Lossless, inert storage for browser-based homework projects."""
import html
import json

PREFIX = 'LMS_WEB_PROJECT_V1\n'


def decode_project(content):
    if not content or not content.startswith('<pre>' + PREFIX):
        return None
    try:
        project = json.loads(html.unescape(content[5:-6])[len(PREFIX):])
        if set(project) == {'html', 'css', 'js'} and all(isinstance(v, str) for v in project.values()):
            return project
    except (ValueError, TypeError, AttributeError):
        pass
    return None


def encode_project(raw):
    if len(raw) > 1_000_000:
        raise ValueError('Kod juda uzun.')
    try:
        project = json.loads(raw)
    except (ValueError, TypeError):
        raise ValueError('Kod formati noto‘g‘ri.')
    if not isinstance(project, dict) or set(project) != {'html', 'css', 'js'}:
        raise ValueError('HTML, CSS va JavaScript bo‘limlari kerak.')
    if not all(isinstance(v, str) for v in project.values()):
        raise ValueError('Kod matn ko‘rinishida bo‘lishi kerak.')
    if not any(v.strip() for v in project.values()):
        raise ValueError('Avval kod yozing.')
    if sum(len(v) for v in project.values()) > 150_000:
        raise ValueError('Kod juda uzun (maksimum 150 000 belgi).')
    return '<pre>' + PREFIX + html.escape(json.dumps(project, ensure_ascii=False)) + '</pre>'


def project_source(project):
    return '\n\n'.join(f'--- {name} ---\n{project[key]}' for key, name in (
        ('html', 'index.html'), ('css', 'style.css'), ('js', 'script.js')))
