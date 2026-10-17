import unicodedata

from django import forms
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from .models import (
    CustomUser, Profession, Section, Lesson, VideoLesson, Homework,
    Test, TestQuestion, TestAnswer, HomeworkSubmission, Certificate,
    Dictionary, DictionaryWord
)
from .security import validate_document_upload, validate_upload


def _clean_name_field(name, field_label):
    """Remove emojis, stickers and special characters from name field."""
    # Ko'rinmas va bo'sh belgilarni bloklash (Hangul Filler, braille blank, va h.k.)
    INVISIBLE_CHARS = set('\u3164\u115f\u1160\u2800\u200b\u200c\u200d\u2060\ufeff\u00a0\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a\u205f\u3000\u180e\u034f\u17b4\u17b5\uffa0')
    cleaned = ''
    for char in name:
        if char in INVISIBLE_CHARS:
            continue
        cat = unicodedata.category(char)
        if cat.startswith('L') or cat.startswith('M') or char in " -'\u02bb\u02bc":
            cleaned += char
    cleaned = cleaned.strip()
    if not cleaned or not any(c.isalpha() for c in cleaned):
        raise forms.ValidationError(f"{field_label} faqat harflardan iborat bo'lishi kerak! Bo'sh yoki ko'rinmas belgilar qabul qilinmaydi.")
    return cleaned


class RegisterForm(UserCreationForm):
    first_name = forms.CharField(
        max_length=100,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ismingiz'})
    )
    last_name = forms.CharField(
        max_length=100,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Familiyangiz'})
    )
    username = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Username'})
    )
    email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'email@example.com'})
    )
    phone = forms.CharField(
        max_length=15,
        widget=forms.TextInput(attrs={
            'class': 'form-control', 
            'placeholder': '(XX) XXX XX XX',
            'id': 'id_phone',
        })
    )
    birth_date = forms.DateField(
        required=True,
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'})
    )
    role = forms.ChoiceField(
        choices=[('student', 'O\'quvchi')],
        initial='student',
        required=False,
        widget=forms.HiddenInput(),
        disabled=True,
    )
    password1 = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Parol'})
    )
    password2 = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Parolni tasdiqlang'})
    )

    class Meta:
        model = CustomUser
        # `role` ATAYLAB yo'q: ochiq ro'yxatdan o'tish faqat 'student' yaratadi.
        # Ilgari `role` Meta.fields ichida edi va HiddenInput bo'lgani uchun
        # hujumchi POST da role=teacher yuborib o'zini o'qituvchi qilib
        # ro'yxatdan o'tkaza olardi (privilege escalation). Rol faqat serverda,
        # save() ichida belgilanadi; o'qituvchi/admin rollari admin panelidan
        # beriladi.
        fields = ['first_name', 'last_name', 'username', 'email', 'phone', 'birth_date', 'password1', 'password2']

    def save(self, commit=True):
        user = super().save(commit=False)
        user.role = 'student'
        user.is_staff = False
        user.is_superuser = False
        from .email_verification import stage_email
        stage_email(user, self.cleaned_data['email'])
        user.email = ''
        if commit:
            user.save()
        return user
    
    def clean_first_name(self):
        return _clean_name_field(self.cleaned_data.get('first_name', ''), 'Ism')

    def clean_last_name(self):
        return _clean_name_field(self.cleaned_data.get('last_name', ''), 'Familiya')

    def clean_phone(self):
        phone = self.cleaned_data.get('phone', '').strip()
        # Formatni tozalash - faqat raqamlarni qoldirish
        digits = ''.join(c for c in phone if c.isdigit())
        
        # Agar +998 bilan kiritgan bo'lsa, uni olib tashlash
        if digits.startswith('998') and len(digits) == 12:
            digits = digits[3:]
        
        # 9 ta raqam bo'lishi kerak
        if len(digits) != 9:
            raise forms.ValidationError("Telefon raqami 9 ta raqamdan iborat bo'lishi kerak. Masalan: (97) 521 66 86")
        
        # +998 qo'shib saqlash
        return '+998' + digits


class LoginForm(forms.Form):
    username = forms.CharField(
        widget=forms.TextInput(attrs={
            "class": "form-control ps-5",
            "placeholder": "Username"
        })
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            "class": "form-control ps-5 pe-5",
            "placeholder": "Parol"
        })
    )




class ProfessionForm(forms.ModelForm):
    name = forms.CharField(
        max_length=200,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Kasb nomini kiriting'})
    )
    photo = forms.ImageField(widget=forms.FileInput(attrs={'class': 'form-control'}))
    description = forms.CharField(
        widget=forms.Textarea(attrs={'class': 'form-control', 'placeholder': 'Kasb haqida ma\'lumot', 'rows': 4})
    )
    is_paid = forms.BooleanField(
        required=False,
        initial=True,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        label="Pullik kurs (so'rov keladi)"
    )
    is_mandatory = forms.BooleanField(
        required=False,
        initial=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        label="Majburiy kurs (barcha o'quvchilar uchun)"
    )
    closed_group_link = forms.URLField(
        required=False,
        widget=forms.URLInput(attrs={'class': 'form-control', 'placeholder': 'https://t.me/+... yoki boshqa havola'}),
        label="Yopiq guruh havolasi"
    )
    kind = forms.ChoiceField(
        choices=Profession.KIND_CHOICES,
        initial='course',
        widget=forms.Select(attrs={'class': 'form-select'}),
        label="Turi (Kasb / Kurs)"
    )
    has_certificate = forms.BooleanField(
        required=False,
        initial=True,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        label="Sertifikat beriladi"
    )
    topic_count = forms.IntegerField(
        required=False,
        min_value=0,
        initial=0,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'placeholder': '0 = cheksiz', 'min': 0}),
        label="Mavzular (darslar) soni",
        help_text="0 = cheksiz. Belgilangan sondan ortiq dars qo'shib bo'lmaydi."
    )
    duration_months = forms.IntegerField(
        required=False,
        min_value=0,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Masalan: 6', 'min': 0}),
        label="O'qish davomiyligi (oy)"
    )

    # ─── Ustoz to'lov stavkalari (har kasb uchun alohida) ───
    price_per_video = forms.IntegerField(
        required=False, min_value=0, initial=25000,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'min': 0, 'step': 500, 'placeholder': '25000'}),
        label="Video dars uchun to'lov (so'm)",
        help_text="Ustozga shu kursda har video dars uchun to'lanadi."
    )
    price_per_test = forms.IntegerField(
        required=False, min_value=0, initial=10000,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'min': 0, 'step': 500, 'placeholder': '10000'}),
        label="Test uchun to'lov (so'm)",
        help_text="Ustozga shu kursda har test uchun to'lanadi."
    )
    price_per_homework = forms.IntegerField(
        required=False, min_value=0, initial=10000,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'min': 0, 'step': 500, 'placeholder': '10000'}),
        label="Uyga vazifa uchun to'lov (so'm)",
        help_text="Ustozga shu kursda har uyga vazifa uchun to'lanadi."
    )

    def clean_topic_count(self):
        v = self.cleaned_data.get('topic_count')
        return v if v else 0

    def _clean_rate(self, field, default):
        """Bo'sh qoldirilsa standart qiymatga tushadi (maydon null bo'la olmaydi)."""
        v = self.cleaned_data.get(field)
        return default if v is None else v

    def clean_price_per_video(self):
        return self._clean_rate('price_per_video', 25000)

    def clean_price_per_test(self):
        return self._clean_rate('price_per_test', 10000)

    def clean_price_per_homework(self):
        return self._clean_rate('price_per_homework', 10000)

    class Meta:
        model = Profession
        fields = ['name', 'photo', 'description', 'kind', 'is_paid', 'is_mandatory',
                  'has_certificate', 'topic_count', 'duration_months', 'closed_group_link',
                  'price_per_video', 'price_per_test', 'price_per_homework']


class UserProfileForm(forms.ModelForm):
    first_name = forms.CharField(max_length=100, widget=forms.TextInput(attrs={'class': 'form-control'}))
    last_name = forms.CharField(max_length=100, widget=forms.TextInput(attrs={'class': 'form-control'}))
    email = forms.EmailField(required=False, widget=forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'email@example.com'}))
    phone = forms.CharField(max_length=13, widget=forms.TextInput(attrs={
        'class': 'form-control',
        'placeholder': '+998XXXXXXXXX',
        'maxlength': '13',
        'data-phone': 'true',
    }))
    photo = forms.ImageField(required=False, widget=forms.FileInput(attrs={'class': 'form-control'}))
    bio = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'O\'zingiz haqida...'})
    )
    obektivka = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 4, 'placeholder': 'Obektivka...'})
    )

    address = forms.CharField(required=False, widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Yashash manzilingiz'}))
    birth_date = forms.DateField(required=False, widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}))
    id_card = forms.FileField(required=False, validators=[validate_document_upload], widget=forms.FileInput(attrs={'class': 'form-control'}))
    birth_certificate = forms.FileField(required=False, validators=[validate_document_upload], widget=forms.FileInput(attrs={'class': 'form-control'}))

    class Meta:
        model = CustomUser
        fields = ['first_name', 'last_name', 'email', 'phone', 'address', 'birth_date', 'id_card', 'birth_certificate', 'photo', 'bio', 'obektivka']

    def clean_phone(self):
        phone = self.cleaned_data.get('phone', '').strip()
        phone = phone.replace(' ', '').replace('-', '').replace('(', '').replace(')', '')
        
        if not phone.startswith('+998'):
            if phone.startswith('998'):
                phone = '+' + phone
            elif phone.startswith('9'):
                phone = '+998' + phone
            else:
                raise forms.ValidationError("Telefon raqami +998 bilan boshlanishi kerak")
        
        digits_after_code = phone[4:]
        if not digits_after_code.isdigit():
            raise forms.ValidationError("Telefon raqamida faqat raqamlar bo'lishi kerak")
        
        if len(phone) != 13:
            raise forms.ValidationError("Telefon raqami noto'g'ri formatda. Masalan: +998901234567")
        
        return phone

    def clean_first_name(self):
        return _clean_name_field(self.cleaned_data.get('first_name', ''), 'Ism')

    def clean_last_name(self):
        return _clean_name_field(self.cleaned_data.get('last_name', ''), 'Familiya')


class AdminUserEditForm(forms.ModelForm):
    email = forms.EmailField(required=False, max_length=254, widget=forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'email@example.com'}))
    first_name = forms.CharField(max_length=100, widget=forms.TextInput(attrs={'class': 'form-control'}))
    last_name = forms.CharField(max_length=100, widget=forms.TextInput(attrs={'class': 'form-control'}))
    username = forms.CharField(max_length=150, widget=forms.TextInput(attrs={'class': 'form-control'}))
    phone = forms.CharField(max_length=20, widget=forms.TextInput(attrs={'class': 'form-control'}))
    role = forms.ChoiceField(choices=CustomUser.ROLE_CHOICES, widget=forms.Select(attrs={'class': 'form-control'}))
    profession = forms.ModelChoiceField(
        queryset=Profession.objects.only('id', 'name'), required=False,
        widget=forms.Select(attrs={'class': 'form-control'}), empty_label="Yo'nalishni tanlang"
    )
    assistant_role = forms.ModelChoiceField(
        queryset=None, required=False,
        widget=forms.Select(attrs={'class': 'form-control'}),
        empty_label="— Permission profili (faqat Yordamchi admin uchun) —",
        label="Yordamchi rol",
    )
    photo = forms.ImageField(required=False, widget=forms.FileInput(attrs={'class': 'form-control'}))
    bio = forms.CharField(required=False, widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3}))
    is_blocked = forms.BooleanField(required=False, widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}))
    new_password = forms.CharField(
        required=False,
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Yangi parol'})
    )

    address = forms.CharField(required=False, widget=forms.TextInput(attrs={'class': 'form-control'}))
    birth_date = forms.DateField(required=False, widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}))
    id_card = forms.FileField(required=False, validators=[validate_document_upload], widget=forms.FileInput(attrs={'class': 'form-control'}))
    birth_certificate = forms.FileField(required=False, validators=[validate_document_upload], widget=forms.FileInput(attrs={'class': 'form-control'}))

    gender = forms.ChoiceField(required=False, choices=[('', 'Tanlang')] + list(CustomUser.GENDER_CHOICES), widget=forms.Select(attrs={'class': 'form-control'}))
    nationality = forms.CharField(required=False, max_length=100, widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': "Masalan: O'zbek"}))
    passport_series = forms.CharField(required=False, max_length=10, widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'AA', 'maxlength': '2'}))
    passport_number = forms.CharField(required=False, max_length=20, widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': '1234567', 'maxlength': '7'}))
    jshshir = forms.CharField(required=False, max_length=14, widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': '14 xonali raqam', 'maxlength': '14'}))
    passport_issued_date = forms.DateField(required=False, widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}))
    father_name = forms.CharField(required=False, max_length=200, widget=forms.TextInput(attrs={'class': 'form-control'}))
    father_phone = forms.CharField(required=False, max_length=20, widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': '+998...'}))
    father_deceased = forms.BooleanField(required=False, widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}))
    mother_name = forms.CharField(required=False, max_length=200, widget=forms.TextInput(attrs={'class': 'form-control'}))
    mother_phone = forms.CharField(required=False, max_length=20, widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': '+998...'}))
    mother_deceased = forms.BooleanField(required=False, widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}))
    parent_phone = forms.CharField(required=False, max_length=20, widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': '+998...'}))
    school_name = forms.CharField(required=False, max_length=300, widget=forms.TextInput(attrs={'class': 'form-control'}))
    school_number = forms.CharField(required=False, max_length=50, widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Masalan: 15'}))

    class Meta:
        model = CustomUser
        fields = [
            'first_name', 'last_name', 'username', 'email', 'phone', 'role', 'profession', 'assistant_role',
            'photo', 'bio', 'is_blocked', 'address', 'birth_date', 'id_card', 'birth_certificate',
            'gender', 'nationality', 'passport_series', 'passport_number', 'jshshir', 'passport_issued_date',
            'father_name', 'father_phone', 'father_deceased',
            'mother_name', 'mother_phone', 'mother_deceased',
            'parent_phone', 'school_name', 'school_number',
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from accounts.models import AssistantRole
        self.fields['assistant_role'].queryset = AssistantRole.objects.filter(is_active=True).order_by('name')

    def clean_first_name(self):
        return _clean_name_field(self.cleaned_data.get('first_name', ''), 'Ism')

    def clean_last_name(self):
        return _clean_name_field(self.cleaned_data.get('last_name', ''), 'Familiya')


class ChangePasswordForm(forms.Form):
    old_password = forms.CharField(widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Joriy parol'}))
    new_password1 = forms.CharField(widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Yangi parol'}))
    new_password2 = forms.CharField(widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Yangi parolni tasdiqlang'}))

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get('new_password1') != cleaned_data.get('new_password2'):
            raise forms.ValidationError("Parollar mos kelmaydi!")
        return cleaned_data


class VideoLessonForm(forms.Form):
    title = forms.CharField(
        max_length=300,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Dars nomi'})
    )
    vimeo_url = forms.URLField(
        required=False,
        widget=forms.URLInput(attrs={
            'class': 'form-control',
            'placeholder': 'https://vimeo.com/123456789'
        }),
        label="Vimeo havolasi"
    )
    youtube_url = forms.URLField(
        required=False,
        widget=forms.URLInput(attrs={
            'class': 'form-control',
            'placeholder': 'https://www.youtube.com/watch?v=VIDEO_ID'
        }),
        label="YouTube havolasi"
    )
    # Davomiylikni server o'zi YouTube/Vimeo'dan aniqlaydi (anti-cheat: mijoz
    # aytgan qiymatga ishonib bo'lmaydi). Bu maydon — ZAXIRA: server aniqlay
    # olmasa (private video, kvota tugagan) admin qo'lda kiritadi, aks holda
    # ko'rish talabi hisoblanmay dars yopilmaydi.
    duration = forms.IntegerField(
        required=False,
        min_value=0,
        max_value=1440,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'placeholder': "Bo'sh qoldiring — avtomatik aniqlanadi",
        }),
        label="Davomiyligi (daqiqa)",
        help_text="Faqat server davomiylikni aniqlay olmagan holatda to'ldiring.",
    )

    def clean(self):
        cleaned_data = super().clean()
        vimeo_url = (cleaned_data.get('vimeo_url') or '').strip()
        youtube_url = (cleaned_data.get('youtube_url') or '').strip()

        if vimeo_url and youtube_url:
            raise forms.ValidationError("Faqat bitta havola kiriting: Vimeo YOKI YouTube.")
        if not vimeo_url and not youtube_url:
            raise forms.ValidationError("Vimeo yoki YouTube havolasini kiriting.")

        if vimeo_url and 'vimeo.com' not in vimeo_url:
            raise forms.ValidationError("Vimeo havolasi vimeo.com dan bo'lishi kerak.")
        if youtube_url and 'youtube.com' not in youtube_url and 'youtu.be' not in youtube_url:
            raise forms.ValidationError("YouTube havolasi youtube.com yoki youtu.be dan bo'lishi kerak.")

        return cleaned_data


class HomeworkForm(forms.Form):
    title = forms.CharField(
        max_length=300,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Vazifa nomi'})
    )
    description = forms.CharField(
        widget=forms.Textarea(attrs={'class': 'form-control', 'placeholder': 'Vazifa tavsifi', 'rows': 4})
    )
    ai_check = forms.BooleanField(
        required=False,
        initial=True,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        label="AI tekshirsin"
    )
    handwritten_only = forms.BooleanField(
        required=False,
        initial=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        label="Faqat yozma topshirish (rasm)"
    )


class DictionaryForm(forms.Form):
    title = forms.CharField(
        max_length=300,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': "Lug'at nomi"})
    )
    description = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'class': 'form-control', 'placeholder': "Lug'at haqida qisqa tavsif (ixtiyoriy)", 'rows': 2})
    )


class HomeworkSubmissionForm(forms.ModelForm):
    SUBMISSION_TYPE_CHOICES = (
        ('file', 'Fayl yuklash'),
        ('text', 'Matn yozish'),
    )
    
    submission_type = forms.ChoiceField(
        choices=SUBMISSION_TYPE_CHOICES,
        initial='file',
        widget=forms.RadioSelect(attrs={'class': 'form-check-input'})
    )
    file = forms.FileField(
        required=False,
        validators=[validate_upload],
        widget=forms.FileInput(attrs={'class': 'form-control'})
    )
    text_content = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 10,
            'placeholder': 'Javobingizni bu yerga yozing...',
            'id': 'text-editor'
        })
    )

    class Meta:
        model = HomeworkSubmission
        fields = ['submission_type', 'file', 'text_content']
    
    def clean(self):
        cleaned_data = super().clean()
        submission_type = cleaned_data.get('submission_type')
        file = cleaned_data.get('file')
        text_content = cleaned_data.get('text_content')
        
        if submission_type == 'file' and not file:
            raise forms.ValidationError("Fayl yuklashingiz kerak!")
        if submission_type == 'file' and file and file.size > 5 * 1024 * 1024:
            raise forms.ValidationError("Fayl hajmi 5 MB dan oshmasligi kerak!")
        if submission_type == 'text' and not text_content:
            raise forms.ValidationError("Matn kiritishingiz kerak!")
        
        return cleaned_data


class HomeworkGradeForm(forms.Form):
    grade = forms.IntegerField(
        min_value=1, max_value=10,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Baho (1-10)', 'min': '1', 'max': '10'})
    )
    feedback = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'class': 'form-control', 'placeholder': 'Izoh', 'rows': 3})
    )


class TestForm(forms.Form):
    TEST_TYPE_CHOICES = (
        ('lesson', 'Dars yuzasidan'),
        ('midterm', 'Oraliq test'),
        ('practice', 'Tajriba oshirish'),
        ('final', 'Yakuniy test'),
    )
    
    title = forms.CharField(
        max_length=300,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Test nomi'})
    )
    test_type = forms.ChoiceField(
        choices=TEST_TYPE_CHOICES,
        initial='lesson',
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    time_limit = forms.IntegerField(
        initial=30,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Vaqt (daqiqa)'})
    )
    passing_score = forms.IntegerField(
        initial=60,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'O\'tish bali (%)'})
    )
    allow_retry = forms.BooleanField(
        required=False,
        initial=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )
    shuffle_questions = forms.BooleanField(
        required=False,
        initial=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        label="Savollar tartibini aralashtirish"
    )
    shuffle_answers = forms.BooleanField(
        required=False,
        initial=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        label="Javoblar tartibini aralashtirish"
    )
    question_count = forms.IntegerField(
        initial=0,
        required=False,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'placeholder': '0 = barchasi', 'min': '0'}),
        label="Olinadigan savollar soni"
    )


class TestQuestionForm(forms.ModelForm):
    question_text = forms.CharField(
        widget=forms.Textarea(attrs={'class': 'form-control', 'placeholder': 'Savol matni', 'rows': 3})
    )
    question_image = forms.ImageField(
        required=False,
        widget=forms.FileInput(attrs={'class': 'form-control'})
    )
    answer1 = forms.CharField(
        max_length=500,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': '1-javob'})
    )
    answer2 = forms.CharField(
        max_length=500,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': '2-javob'})
    )
    answer3 = forms.CharField(
        max_length=500,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': '3-javob'})
    )
    correct_answer = forms.ChoiceField(
        choices=[(1, '1-javob'), (2, '2-javob'), (3, '3-javob')],
        widget=forms.RadioSelect(attrs={'class': 'form-check-input'})
    )

    class Meta:
        model = TestQuestion
        fields = ['question_text', 'question_image']


class CertificateForm(forms.ModelForm):
    certificate_id = forms.CharField(
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Masalan: CERT-20260324-1234'}),
        label="Sertifikat ID raqami",
        required=False,
        help_text="Bo'sh qoldirilsa avtomatik yaratiladi",
    )
    file = forms.FileField(
        validators=[validate_document_upload],
        widget=forms.FileInput(attrs={'class': 'form-control', 'accept': '.pdf'}),
        label="Sertifikat fayli (PDF)"
    )
    valid_from = forms.DateField(
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
        label="Berilgan sana",
        required=False,
    )
    valid_until = forms.DateField(
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
        label="Amal qilish muddati",
        required=False,
    )
    status = forms.ChoiceField(
        choices=Certificate.STATUS_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select'}),
        label="Holat",
        initial='active',
    )
    description = forms.CharField(
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Tavsif (ixtiyoriy)'}),
        label="Tavsif",
        required=False,
    )

    class Meta:
        model = Certificate
        fields = ['certificate_id', 'file', 'status', 'valid_from', 'valid_until', 'description']

    def clean_certificate_id(self):
        cert_id = self.cleaned_data.get('certificate_id', '').strip()
        if cert_id:
            qs = Certificate.objects.filter(certificate_id=cert_id)
            if self.instance and self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise forms.ValidationError("Bu ID raqam allaqachon mavjud!")
        return cert_id


class SectionForm(forms.ModelForm):
    title = forms.CharField(
        max_length=200,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': "Bo'lim nomi"})
    )
    description = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'class': 'form-control', 'placeholder': 'Tavsif (ixtiyoriy)', 'rows': 3})
    )
    order = forms.IntegerField(
        initial=0,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Tartib raqami'})
    )

    class Meta:
        model = Section
        fields = ['title', 'description', 'order']


class PasswordResetRequestForm(forms.Form):
    username = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={
            'class': 'form-control ps-5',
            'placeholder': 'Username'
        })
    )
    email = forms.EmailField(
        max_length=254,
        label='Elektron manzil',
        widget=forms.EmailInput(attrs={
            'class': 'form-control ps-5',
            'placeholder': 'siz@example.com',
            'autocomplete': 'email',
            'autocapitalize': 'none',
        }),
    )


class StudentProfileCompleteForm(forms.ModelForm):
    """Profil to'ldirish formasi - login dan keyin majburiy"""
    
    first_name = forms.CharField(
        max_length=100,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ismingiz'})
    )
    last_name = forms.CharField(
        max_length=100,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Familiyangiz'})
    )
    birth_date = forms.DateField(
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
        label="Tug'ilgan kuni"
    )
    gender = forms.ChoiceField(
        choices=[('', 'Tanlang...')] + list(CustomUser.GENDER_CHOICES),
        widget=forms.Select(attrs={'class': 'form-select'}),
        label="Jinsi"
    )
    nationality = forms.CharField(
        max_length=100,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': "Masalan: O'zbek"}),
        label="Millati"
    )
    
    # ── Hujjat: pasport YOKI metrika (bittasi yetarli) ──
    document_type = forms.ChoiceField(
        required=False,
        choices=[('', 'Tanlang...')] + list(CustomUser.DOCUMENT_TYPE_CHOICES),
        widget=forms.Select(attrs={'class': 'form-select'}),
        label="Hujjat turi",
    )

    # Passport fields (pasport tanlanganda majburiy — clean() da tekshiriladi)
    passport_series = forms.CharField(
        required=False, max_length=10,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'AA'}),
        label="Pasport seriyasi"
    )
    passport_number = forms.CharField(
        required=False, max_length=20,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': '1234567'}),
        label="Pasport raqami"
    )
    jshshir = forms.CharField(
        required=False, max_length=14,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': '12345678901234'}),
        label="JSHSHIR (PINFL)"
    )
    passport_issued_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
        label="Pasport berilgan sana"
    )

    # Metrika fields (metrika tanlanganda majburiy — JSHSHIR bo'lmaydi)
    metrka_series = forms.CharField(
        required=False, max_length=10,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'I-GZ'}),
        label="Metrika seriyasi"
    )
    metrka_number = forms.CharField(
        required=False, max_length=20,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': '123456'}),
        label="Metrika raqami"
    )
    
    # Parent fields
    father_name = forms.CharField(
        max_length=200,
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': "Otangizning to'liq ismi"}),
        label="Otasining to'liq ismi"
    )
    father_phone = forms.CharField(
        max_length=20,
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': '+998XXXXXXXXX'}),
        label="Otasining telefon raqami"
    )
    father_deceased = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        label="Otasi vafot etgan"
    )
    mother_name = forms.CharField(
        max_length=200,
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': "Onangizning to'liq ismi"}),
        label="Onasining to'liq ismi"
    )
    mother_phone = forms.CharField(
        max_length=20,
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': '+998XXXXXXXXX'}),
        label="Onasining telefon raqami"
    )
    mother_deceased = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        label="Onasi vafot etgan"
    )
    parent_phone = forms.CharField(
        max_length=20,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': '+998XXXXXXXXX'}),
        label="Asosiy ota-ona telefon raqami"
    )
    
    # School
    school_name = forms.CharField(
        max_length=300,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Maktab nomi'}),
        label="Maktab nomi"
    )
    school_number = forms.CharField(
        max_length=50,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Masalan: 15'}),
        label="Maktab raqami"
    )
    address = forms.CharField(
        max_length=300,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': "To'liq yashash manzili"}),
        label="Yashash manzili"
    )

    class Meta:
        model = CustomUser
        fields = [
            'first_name', 'last_name', 'birth_date', 'gender', 'nationality',
            'document_type',
            'passport_series', 'passport_number', 'jshshir', 'passport_issued_date',
            'metrka_series', 'metrka_number',
            'father_name', 'father_phone', 'father_deceased',
            'mother_name', 'mother_phone', 'mother_deceased',
            'parent_phone',
            'school_name', 'school_number', 'address',
        ]

    def clean_first_name(self):
        return _clean_name_field(self.cleaned_data.get('first_name', ''), 'Ism')

    def clean_last_name(self):
        return _clean_name_field(self.cleaned_data.get('last_name', ''), 'Familiya')

    def clean_jshshir(self):
        # JSHSHIR faqat kiritilgan bo'lsa tekshiriladi (metrikada JSHSHIR bo'lmaydi).
        jshshir = (self.cleaned_data.get('jshshir') or '').strip()
        if jshshir and (not jshshir.isdigit() or len(jshshir) != 14):
            raise forms.ValidationError("JSHSHIR 14 ta raqamdan iborat bo'lishi kerak!")
        return jshshir

    def clean(self):
        """Hujjat turiga qarab (pasport yoki metrika) mos maydonlarni tekshiradi.

        - Pasport: seriya + raqam + JSHSHIR majburiy.
        - Metrika: seriya + raqam majburiy (JSHSHIR yo'q).
        Hujjat turi tanlanmagan bo'lsa hujjat maydonlari majburiy emas — ammo
        bunday holatda profil "to'ldirilmagan" bo'lib qoladi (foydalanuvchi skip qilishi mumkin).
        """
        cleaned = super().clean()
        doc_type = cleaned.get('document_type')

        if doc_type == 'passport':
            if not cleaned.get('passport_series'):
                self.add_error('passport_series', "Pasport seriyasi majburiy.")
            if not cleaned.get('passport_number'):
                self.add_error('passport_number', "Pasport raqami majburiy.")
            if not cleaned.get('jshshir'):
                self.add_error('jshshir', "Pasport uchun JSHSHIR majburiy.")
        elif doc_type == 'metrka':
            if not cleaned.get('metrka_series'):
                self.add_error('metrka_series', "Metrika seriyasi majburiy (masalan: I-GZ).")
            if not cleaned.get('metrka_number'):
                self.add_error('metrka_number', "Metrika raqami majburiy.")

        return cleaned

    def clean_parent_phone(self):
        phone = self.cleaned_data.get('parent_phone', '').strip()
        phone = phone.replace(' ', '').replace('-', '').replace('(', '').replace(')', '')
        if not phone.startswith('+998'):
            if phone.startswith('998'):
                phone = '+' + phone
            elif phone.startswith('9'):
                phone = '+998' + phone
            else:
                raise forms.ValidationError("Telefon raqami +998 bilan boshlanishi kerak")
        digits_after_code = phone[4:]
        if not digits_after_code.isdigit():
            raise forms.ValidationError("Telefon raqamida faqat raqamlar bo'lishi kerak")
        if len(phone) != 13:
            raise forms.ValidationError("Telefon raqami noto'g'ri formatda")
        return phone

    def _clean_optional_phone(self, field_name):
        phone = self.cleaned_data.get(field_name, '').strip()
        if not phone:
            return phone
        phone = phone.replace(' ', '').replace('-', '').replace('(', '').replace(')', '')
        if not phone.startswith('+998'):
            if phone.startswith('998'):
                phone = '+' + phone
            elif phone.startswith('9'):
                phone = '+998' + phone
            else:
                raise forms.ValidationError("Telefon raqami +998 bilan boshlanishi kerak")
        digits_after_code = phone[4:]
        if not digits_after_code.isdigit():
            raise forms.ValidationError("Telefon raqamida faqat raqamlar bo'lishi kerak")
        if len(phone) != 13:
            raise forms.ValidationError("Telefon raqami noto'g'ri formatda")
        return phone

    def clean_father_phone(self):
        return self._clean_optional_phone('father_phone')

    def clean_mother_phone(self):
        return self._clean_optional_phone('mother_phone')
