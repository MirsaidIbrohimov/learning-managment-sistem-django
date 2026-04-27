from rest_framework.permissions import BasePermission


class IsAdmin(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == 'admin'


class IsTeacher(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role in ('admin', 'teacher')


class IsStudent(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == 'student'


class IsProfileCompleted(BasePermission):
    message = "Profilingizni to'ldiring."

    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        if request.user.role == 'student' and not request.user.is_profile_completed:
            return False
        return True
