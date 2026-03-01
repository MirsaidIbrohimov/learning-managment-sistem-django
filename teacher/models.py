from django.db import models
from django.conf import settings


class TeacherCertificate(models.Model):
    teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='teacher_certificates',
        limit_choices_to={'role': 'teacher'},
        verbose_name="O'qituvchi"
    )
    title = models.CharField(max_length=300, verbose_name="Sertifikat nomi")
    file = models.FileField(upload_to='teacher_certificates/', verbose_name="Sertifikat fayli")
    description = models.TextField(blank=True, null=True, verbose_name="Tavsif")
    is_visible = models.BooleanField(default=True, verbose_name="Ko'rinadi")
    issued_date = models.DateField(null=True, blank=True, verbose_name="Berilgan sana")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = "O'qituvchi sertifikati"
        verbose_name_plural = "O'qituvchi sertifikatlari"

    def __str__(self):
        return f"{self.teacher.full_name} - {self.title}"


class TeacherSalary(models.Model):
    SALARY_TYPES = (
        ('oylik', 'Oylik maosh'),
        ('kpi', 'KPI bonus'),
        ('bayram', 'Bayram puli'),
        ('bonus', 'Bonus'),
        ('jarima', 'Jarima'),
        ('boshqa', 'Boshqa'),
    )

    MONTH_CHOICES = (
        (1, 'Yanvar'), (2, 'Fevral'), (3, 'Mart'), (4, 'Aprel'),
        (5, 'May'), (6, 'Iyun'), (7, 'Iyul'), (8, 'Avgust'),
        (9, 'Sentyabr'), (10, 'Oktyabr'), (11, 'Noyabr'), (12, 'Dekabr'),
    )

    teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='salaries',
        limit_choices_to={'role': 'teacher'},
        verbose_name="O'qituvchi"
    )
    salary_type = models.CharField(max_length=20, choices=SALARY_TYPES, default='oylik', verbose_name="Turi")
    amount = models.DecimalField(max_digits=15, decimal_places=0, verbose_name="Summa (so'm)")
    month = models.IntegerField(choices=MONTH_CHOICES, verbose_name="Oy")
    year = models.IntegerField(verbose_name="Yil")
    description = models.CharField(max_length=500, blank=True, verbose_name="Izoh")
    receipt = models.FileField(upload_to='salary_receipts/', null=True, blank=True, verbose_name="Chek/Kvitansiya")
    is_paid = models.BooleanField(default=False, verbose_name="To'langan")
    paid_date = models.DateField(null=True, blank=True, verbose_name="To'langan sana")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='created_salaries',
        verbose_name="Kim tomonidan"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-year', '-month', '-created_at']
        verbose_name = "O'qituvchi oyligi"
        verbose_name_plural = "O'qituvchi oyliklari"

    def __str__(self):
        return f"{self.teacher.full_name} - {self.get_month_display()} {self.year} - {self.get_salary_type_display()}"

    @property
    def month_name(self):
        return dict(self.MONTH_CHOICES).get(self.month, '')
