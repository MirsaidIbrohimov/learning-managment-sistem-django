from django.contrib import admin
from .models import TeacherCertificate, TeacherSalary, TeacherAttendance, TeacherStudentAction


class TeacherCertificateInline(admin.TabularInline):
    model = TeacherCertificate
    extra = 1
    fields = ['title', 'file', 'description', 'is_visible', 'issued_date']


@admin.register(TeacherCertificate)
class TeacherCertificateAdmin(admin.ModelAdmin):
    list_display = ['teacher', 'title', 'is_visible', 'issued_date', 'created_at']
    list_filter = ['is_visible', 'created_at']
    search_fields = ['teacher__first_name', 'teacher__last_name', 'title']
    list_editable = ['is_visible']


@admin.register(TeacherSalary)
class TeacherSalaryAdmin(admin.ModelAdmin):
    list_display = ['teacher', 'salary_type', 'amount', 'month', 'year', 'is_paid', 'paid_date', 'created_at']
    list_filter = ['salary_type', 'is_paid', 'month', 'year', 'created_at']
    search_fields = ['teacher__first_name', 'teacher__last_name', 'description']
    list_editable = ['is_paid']
    ordering = ['-year', '-month', '-created_at']
    
    def save_model(self, request, obj, form, change):
        if not change:  # If creating a new record
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(TeacherAttendance)
class TeacherAttendanceAdmin(admin.ModelAdmin):
    list_display = ['teacher', 'date', 'status', 'check_in_time', 'check_out_time', 'created_by', 'created_at']
    list_filter = ['status', 'date', 'created_at']
    search_fields = ['teacher__first_name', 'teacher__last_name', 'notes']
    list_editable = ['status']
    ordering = ['-date', '-created_at']
    date_hierarchy = 'date'
    
    def save_model(self, request, obj, form, change):
        if not change:  # If creating a new record
            obj.created_by = request.user
        super().save_model(request, obj, form, change)



@admin.register(TeacherStudentAction)
class TeacherStudentActionAdmin(admin.ModelAdmin):
    list_display = ['created_at', 'actor', 'action', 'student', 'profession', 'amount', 'note']
    list_filter = ['action', 'profession', 'created_at']
    search_fields = ['actor__first_name', 'actor__last_name', 'student__first_name', 'student__last_name',
                     'student__phone', 'note']
    raw_id_fields = ['actor', 'student']
    date_hierarchy = 'created_at'
    readonly_fields = ['actor', 'student', 'profession', 'action', 'amount', 'note', 'created_at']

    def has_add_permission(self, request):
        return False
