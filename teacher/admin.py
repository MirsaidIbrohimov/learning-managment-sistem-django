from django.contrib import admin
from .models import TeacherCertificate


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

