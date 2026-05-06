import logging

from rest_framework.permissions import BasePermission

security_logger = logging.getLogger('django.security')


class IsAdmin(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == 'admin'


class IsTeacher(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role in ('admin', 'teacher')


class IsStudent(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == 'student'


class IsNotBlocked(BasePermission):
    """Bloklangan foydalanuvchilarni API dan cheklash"""
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
    message = "Profilingizni to'ldiring."

    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        if request.user.role == 'student' and not request.user.is_profile_completed:
            return False
        return True


class IsOwnerOrAdmin(BasePermission):
    """Object-level permission: faqat o'z ma'lumotlari yoki admin"""
    def has_object_permission(self, request, view, obj):
        if request.user.role == 'admin':
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
