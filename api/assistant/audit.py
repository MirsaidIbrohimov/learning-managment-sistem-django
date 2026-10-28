"""Audit logging helper."""

import logging
from typing import Optional

from accounts.models import AssistantActionLog

audit_logger = logging.getLogger('api.audit')


def _client_ip(request):
    """Audit jurnaliga yoziş uçun IP.

    Avval `X-Forwarded-For` ning ENG ÇAP qiymati olinardi — u butunlay
    mijoz nazoratida, ya'ni admin amallari jurnalida IP soxtalaştirilişi
    mumkin edi. `get_client_ip` işonçli proxy sonini hisobga oladi.
    """
    if not request:
        return None
    from accounts.security import get_client_ip
    return get_client_ip(request)


def log_action(request, action_code: str, *,
               target=None, target_type: str = '', target_id=None,
               description: str = '', extra: Optional[dict] = None):
    """Admin/assistant tomonidan bajarilgan amalni jurnalga yoziş.

    Misol:
        log_action(request, 'users.block', target=user, description=f"{user.username} bloklandi")
    """
    user = getattr(request, 'user', None) if request else None
    if user is not None and not user.is_authenticated:
        user = None

    t_type = target_type
    t_id = str(target_id) if target_id is not None else ''
    if target is not None:
        if not t_type:
            t_type = target.__class__.__name__
        if not t_id:
            t_id = str(getattr(target, 'pk', '') or '')

    try:
        AssistantActionLog.objects.create(
            user=user,
            action_code=action_code,
            target_type=t_type[:80],
            target_id=t_id[:64],
            description=description[:500] if description else '',
            ip_address=_client_ip(request),
            extra=extra or {},
        )
    except Exception as e:  # noqa
        audit_logger.error(f"log_action failed: {e}")

    who = user.username if user else 'system'
    audit_logger.info(f"AUDIT {who} {action_code} {t_type}#{t_id} - {description}")
