"""AI sörovlarini veb-jarayondan taşqarida (fon oqimida) bajariş.

Muammo: Passenger'da har bir Python jarayoni bir vaqtda faqat BITTA sörovga
xizmat qiladi. AI javobi 10–60 soniya (ommaviy tekşiruv — daqiqalar) kutilsa,
öşa jarayon band bölib qoladi va boşqa foydalanuvçilar navbatda turadi.

Yeçim:
* ``@ai_offload`` — AJAX view'ni fon oqimida işga tuşiradi va darhol
  ``202`` + ``X-AI-Job`` sarlavhasini qaytaradi. Natija ``AIJob`` jadvaliga
  yoziladi (boşqa jarayon ham öqiy oladi).
* ``static/js/ai-jobs.js`` — ``fetch`` qobiği: ``202`` kelsa natija tayyor
  bölgunça ``job_status`` ni söraydi va ASL javobni qaytaradi. Şu sabab
  sahifalardagi mavjud JS kodi özgarmaydi.
* Qobiq ``X-AI-Async: 1`` sarlavhasini yuboradi; u bölmasa (oddiy forma,
  jQuery, testlar) view avvalgidek sinxron işlaydi.
* ``submit(fn, ...)`` — oddiy funksiyani fonda bajariş (forma POST'lari uçun).
"""
import logging
import os
import random
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from functools import wraps

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.db import close_old_connections, connections
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils import timezone

logger = logging.getLogger(__name__)

ASYNC_HEADER = 'HTTP_X_AI_ASYNC'
STALE_AFTER = timedelta(minutes=15)   # şundan keyin ham tayyor bölmasa — jarayon ölgan deb hisoblanadi
KEEP_JOBS_FOR = timedelta(days=1)

_lock = threading.Lock()
_executor = None
_executor_pid = None


def _inline():
    """Testlarda fon oqimi işlatilmaydi: test tranzaksiyasi boşqa oqimga körinmaydi."""
    return getattr(settings, 'AI_JOBS_INLINE', getattr(settings, 'RUNNING_TESTS', False))


def _get_executor():
    # Passenger jarayonlarni fork qiladi; fork'dan oldin yaratilgan oqimlar
    # bola jarayonga ötmaydi — şuning uçun har jarayon öz pool'ini yaratadi.
    global _executor, _executor_pid
    with _lock:
        if _executor is None or _executor_pid != os.getpid():
            _executor = ThreadPoolExecutor(
                max_workers=getattr(settings, 'AI_JOB_WORKERS', 4),
                thread_name_prefix='ai-job',
            )
            _executor_pid = os.getpid()
        return _executor


def _guarded(fn, args, kwargs):
    close_old_connections()
    try:
        fn(*args, **kwargs)
    except Exception:
        logger.exception('AI fon vazifasi xatosi: %s', getattr(fn, '__name__', fn))
    finally:
        connections.close_all()  # faqat şu oqimning ulanişlari yopiladi


def submit(fn, *args, **kwargs):
    """``fn`` ni fon oqimida bajaradi (testlarda — darhol)."""
    if _inline():
        try:
            fn(*args, **kwargs)
        except Exception:
            logger.exception('AI fon vazifasi xatosi: %s', getattr(fn, '__name__', fn))
        return
    _get_executor().submit(_guarded, fn, args, kwargs)


def _render(view, args, kwargs, drf_view):
    """View'ni bajarib, (status, content_type, body) qaytaradi."""
    try:
        response = view(*args, **kwargs)
    except Exception as exc:
        if drf_view is None:
            logger.exception('AI fon view xatosi: %s', getattr(view, '__name__', view))
            response = JsonResponse({'error': "Içki xatolik yuz berdi. Keyinroq qayta urinib köring."},
                                    status=500)
        else:
            response = drf_view.handle_exception(exc)
    if drf_view is not None:
        response = drf_view.finalize_response(args[1], response, *args[2:], **kwargs)
    if hasattr(response, 'render') and not getattr(response, 'is_rendered', True):
        response.render()
    if getattr(response, 'streaming', False):
        body = b''.join(response.streaming_content)
    else:
        body = response.content
    return response.status_code, response.get('Content-Type', ''), body.decode('utf-8', 'replace')


def _finish(job_id, view, args, kwargs, drf_view):
    from .models import AIJob
    try:
        status, content_type, body = _render(view, args, kwargs, drf_view)
    except Exception:
        logger.exception('AI fon view natijasini olişda xato')
        status, content_type = 500, 'application/json'
        body = '{"error": "Içki xatolik yuz berdi. Keyinroq qayta urinib köring."}'
    AIJob.objects.filter(pk=job_id).update(
        status='done', response_status=status, content_type=content_type[:100],
        body=body, finished_at=timezone.now(),
    )


def ai_offload(view):
    """AJAX view'ni fonga köçiradi (funksiya view yoki DRF action uçun).

    Ruxsat tekşiruvçi dekoratorlar (login_required va h.k.) TAŞQARIDA
    qolişi kerak — ular sinxron işlaydi, faqat view tanasi fonga ötadi.
    """
    @wraps(view)
    def wrapper(*args, **kwargs):
        drf_view = args[0] if args and hasattr(args[0], 'finalize_response') else None
        request = args[1] if drf_view is not None else args[0]
        django_request = getattr(request, '_request', request)

        if django_request.META.get(ASYNC_HEADER) != '1' or not django_request.user.is_authenticated:
            return view(*args, **kwargs)

        # Javob qaytgaç sörov tanasi va yuklangan fayllar yopiladi —
        # kerakli ma'lumot oldindan öqib qöyiladi; fayl bölsa sinxron qoladi.
        if drf_view is not None:
            request.data  # noqa: B018 — tanani hozir parse qiliş
            has_files = bool(request.FILES)
        else:
            has_files = bool(django_request.FILES)
        if has_files:
            return view(*args, **kwargs)

        from .models import AIJob
        if random.random() < 0.02:
            AIJob.objects.filter(created_at__lt=timezone.now() - KEEP_JOBS_FOR).delete()
        job = AIJob.objects.create(id=uuid.uuid4(), user=django_request.user, path=django_request.path[:300])
        submit(_finish, job.pk, view, args, kwargs, drf_view)

        response = JsonResponse({'ai_job': str(job.pk), 'status': 'pending'}, status=202)
        response['X-AI-Job'] = reverse('ai_yordamchi:job_status', args=[job.pk])
        return response
    return wrapper


@login_required
def job_status(request, job_id):
    """Tayyor bölsa asl javobni, aks holda 202 qaytaradi."""
    from .models import AIJob
    job = get_object_or_404(AIJob, pk=job_id, user=request.user)
    if job.status != 'done':
        if timezone.now() - job.created_at > STALE_AFTER:
            return JsonResponse({'error': "AI javobi juda uzoq keçikdi. Qayta urinib köring."}, status=504)
        response = JsonResponse({'ai_job': str(job.pk), 'status': 'pending'}, status=202)
        response['X-AI-Job'] = request.path
        response['Cache-Control'] = 'no-store'
        return response
    response = HttpResponse(job.body, status=job.response_status,
                            content_type=job.content_type or 'application/json')
    response['Cache-Control'] = 'no-store'
    return response
