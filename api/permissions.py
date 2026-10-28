import logging
from typing import Optional

from rest_framework.permissions import BasePermission

security_logger = logging.getLogger('django.security')


class IsAdmin(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == 'admin'


class IsAssistantAdmin(BasePermission):
    """Faqat yordamçi admin (assistant_admin) ruxsati"""
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == 'assistant_admin'


class IsAdminOrAssistant(BasePermission):
    """Admin yoki yordamçi admin ruxsati - API orqali boşqariş uçun"""
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role in ('admin', 'assistant_admin')


class HasAssistantPerm(BasePermission):
    """Foydalanuvçida muayyan granular permission borligini tekşiradi.

    Foydalaniş (DRF view'da):
        permission_classes = [IsAuthenticated, IsNotBlocked, HasAssistantPerm.require('users.view')]

    Yoki view'da `required_perm = 'users.view'` atributini belgilaş mumkin
    va şunda HasAssistantPerm darhol qöllaniladi.
    """
    required_perm: Optional[str] = None
    message = "Sizda bu amal uçun ruxsat yöq."

    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        # Faqat admin yoki assistant_admin foydalanişi mumkin
        if request.user.role not in ('admin', 'assistant_admin'):
            return False
        # Permission kodini oliş
        perm = self.required_perm or getattr(view, 'required_perm', None)
        if perm is None:
            # Permission kodi belgilanmagan -> faqat admin uçun oçiq
            return request.user.is_admin
        return request.user.has_assistant_perm(perm)

    @classmethod
    def require(cls, perm_code: str):
        """Permission klassini ma'lum kod bilan dinamik yaratiş."""
        return type(
            f'HasPerm_{perm_code.replace(".", "_")}',
            (cls,),
            {'required_perm': perm_code},
        )


class IsTeacher(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role in ('admin', 'teacher')


class IsStudent(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == 'student'


class IsNotBlocked(BasePermission):
    """Bloklangan foydalanuvçilarni API dan çeklaş"""
    message = "Sizning akkauntingiz bloklangan."

    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        if hasattr(request.user, 'is_blocked') and request.user.is_blocked:
            security_logger.warning(
                f"Blocked user API attempt: user={request.user.username}, "
                f"path={request.path}, method={request.method}"
            )
            return False
        return True


class IsProfileCompleted(BasePermission):
    message = "Profilingizni töldiring."

    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        if request.user.role == 'student' and not request.user.is_profile_completed:
            return False
        return True


class IsOwnerOrAdmin(BasePermission):
    """Object-level permission: faqat öz ma'lumotlari yoki admin"""
    def has_object_permission(self, request, view, obj):
        if request.user.role in ('admin', 'assistant_admin'):
            return True
        owner_fields = ['user', 'student', 'sender', 'recipient']
        for field in owner_fields:
            if hasattr(obj, field) and getattr(obj, field) == request.user:
                return True
        if obj == request.user:
            return True
        return False


from rest_framework.throttling import UserRateThrottle


class LoginRateThrottle(UserRateThrottle):
    scope = 'login'


class CoinTransferRateThrottle(UserRateThrottle):
    scope = 'coin_transfer'
