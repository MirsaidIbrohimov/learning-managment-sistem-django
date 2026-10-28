from django.db import models
from django.conf import settings


class TeacherCertificate(models.Model):
    teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='teacher_certificates',
        limit_choices_to={'role': 'teacher'},
        verbose_name="Öqituvçi"
    )
    title = models.CharField(max_length=300, verbose_name="Sertifikat nomi")
    file = models.FileField(upload_to='teacher_certificates/', verbose_name="Sertifikat fayli")
    description = models.TextField(blank=True, null=True, verbose_name="Tavsif")
    is_visible = models.BooleanField(default=True, verbose_name="Körinadi")
    issued_date = models.DateField(null=True, blank=True, verbose_name="Berilgan sana")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Öqituvçi sertifikati"
        verbose_name_plural = "Öqituvçi sertifikatlari"

    def __str__(self):
        return f"{self.teacher.full_name} - {self.title}"


class TeacherSalary(models.Model):
    SALARY_TYPES = (
        ('oylik', 'Oylik maoş'),
        ('kpi', 'KPI bonus'),
        ('bayram', 'Bayram puli'),
        ('bonus', 'Bonus'),
        ('jarima', 'Jarima'),
        ('boshqa', 'Boşqa'),
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
        verbose_name="Öqituvçi"
    )
    salary_type = models.CharField(max_length=20, choices=SALARY_TYPES, default='oylik', verbose_name="Turi")
    amount = models.DecimalField(max_digits=15, decimal_places=0, verbose_name="Summa (söm)")
    month = models.IntegerField(choices=MONTH_CHOICES, verbose_name="Oy")
    year = models.IntegerField(verbose_name="Yil")
    description = models.CharField(max_length=500, blank=True, verbose_name="Izoh")
    receipt = models.FileField(upload_to='salary_receipts/', null=True, blank=True, verbose_name="Chek/Kvitansiya")
    is_paid = models.BooleanField(default=False, verbose_name="Tölangan")
    paid_date = models.DateField(null=True, blank=True, verbose_name="Tölangan sana")
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
        verbose_name = "Öqituvçi oyligi"
        verbose_name_plural = "Öqituvçi oyliklari"

    def __str__(self):
        return f"{self.teacher.full_name} - {self.get_month_display()} {self.year} - {self.get_salary_type_display()}"

    @property
    def month_name(self):
        return dict(self.MONTH_CHOICES).get(self.month, '')


class TeacherAttendance(models.Model):
    STATUS_CHOICES = (
        ('present', 'Kelgan'),
        ('absent', 'Kelmagan'),
        ('late', 'Keçikkan'),
        ('sick', 'Kasal'),
        ('vacation', 'Ta\'til'),
        ('business', 'Xizmat safari'),
    )
    
    teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='attendances',
        limit_choices_to={'role': 'teacher'},
        verbose_name="Öqituvçi"
    )
    date = models.DateField(verbose_name="Sana")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='present', verbose_name="Holati")
    check_in_time = models.TimeField(null=True, blank=True, verbose_name="Kiriş vaqti")
    check_out_time = models.TimeField(null=True, blank=True, verbose_name="Çiqiş vaqti")
    notes = models.TextField(blank=True, null=True, verbose_name="Izoh")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='created_attendances',
        verbose_name="Kim tomonidan qöşilgan"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-date', '-created_at']
        unique_together = ['teacher', 'date']  # Bir öqituvçi bir kunda faqat bitta davomat yozuvi
        verbose_name = "Öqituvçi davomati"
        verbose_name_plural = "Öqituvçilar davomati"

    def __str__(self):
        return f"{self.teacher.full_name} - {self.date} - {self.get_status_display()}"


class TeacherStudentAction(models.Model):
    """Öqituvçi (yoki admin) tomonidan öquvçi ustida bajarilgan amallar jurnali.

    Admin panelda kim, kimga, qaysi kursda nima qilgani körinib turişi uçun.
    """
    ACTION_CHOICES = (
        ('coin_give', "Coin berdi"),
        ('coin_take', "Coin ayirdi"),
        ('enroll', "Kursga qöşdi"),
        ('remove', "Kursdan çiqardi"),
        ('approve_enroll', "Yoziliş sörovini tasdiqladi"),
        ('reject_enroll', "Yoziliş sörovini rad etdi"),
        ('approve_unenroll', "Çiqiş sörovini tasdiqladi"),
        ('reject_unenroll', "Çiqiş sörovini rad etdi"),
    )

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        related_name='teacher_student_actions', verbose_name="Bajaruvçi",
    )
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='received_teacher_actions', verbose_name="Öquvçi",
    )
    profession = models.ForeignKey(
        'accounts.Profession', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='teacher_student_actions', verbose_name="Kurs",
    )
    action = models.CharField(max_length=20, choices=ACTION_CHOICES, db_index=True, verbose_name="Amal")
    amount = models.PositiveIntegerField(default=0, verbose_name="Coin miqdori")
    note = models.CharField(max_length=500, blank=True, verbose_name="Izoh")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Öqituvçi amali"
        verbose_name_plural = "Öqituvçi amallari"

    def __str__(self):
        actor = self.actor.full_name if self.actor else '—'
        return f"{actor} → {self.student.full_name}: {self.get_action_display()}"
