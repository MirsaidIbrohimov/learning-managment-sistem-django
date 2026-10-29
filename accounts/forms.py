import unicodedata

from django import forms
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from .models import (
    CustomUser, Profession, Section, Lesson, VideoLesson, Homework,
    Test, TestQuestion, TestAnswer, HomeworkSubmission, Certificate,
    Dictionary, DictionaryWord
)
from .security import validate_document_upload, validate_upload


# Özbekiston operator va şahar kodlari (+998 dan keyingi 2 ta raqam).
UZ_PHONE_CODES = {
    '20', '33', '50', '55', '61', '62', '65', '66', '67', '69', '70', '71', '72', '73', '74', '75',
    '76', '77', '78', '79', '87', '88', '90', '91', '93', '94', '95', '97', '98', '99',
}


def normalize_uz_phone(raw, *, required=True):
    """"(90) 123 45 67", "998901234567", "+998 90 123-45-67" → "+998901234567".

    Faqat Özbekiston raqami qabul qilinadi: +998, keyin operator kodi va 7 ta raqam.
    """
    raw = (raw or '').strip()
    if not raw:
        if required:
            raise forms.ValidationError("Telefon raqamini kiriting.")
        return ''
    if any(ch.isalpha() for ch in raw):
        raise forms.ValidationError("Telefon raqamida faqat raqamlar bölişi kerak.")
    digits = ''.join(ch for ch in raw if ch.isdigit())
    if raw.lstrip().startswith('+') and not digits.startswith('998'):
        raise forms.ValidationError("Faqat Özbekiston raqami qabul qilinadi (+998 bilan boşlanadi).")
    if digits.startswith('998') and len(digits) == 12:
        digits = digits[3:]
    if len(digits) != 9:
        raise forms.ValidationError("Raqam +998 dan keyin 9 ta raqamdan iborat bölişi kerak. Masalan: +998 90 123 45 67")
    if digits[:2] not in UZ_PHONE_CODES:
        raise forms.ValidationError(f"«{digits[:2]}» Özbekiston operator kodi emas. Masalan: 90, 91, 93, 94, 95, 97, 98, 99, 33, 88, 77, 50.")
    return '+998' + digits


def parse_jshshir(value):
    """JŞŞIR (PINFL) dan jins va tuğilgan sanani öqiydi.

    Tuzilişi: 1-raqam — asr va jins (toq = erkak, juft = ayol; 1-2 → 1800-yillar,
    3-4 → 1900-yillar, 5-6 → 2000-yillar), 2-3 — kun, 4-5 — oy, 6-7 — yilning
    oxirgi ikki raqami. Masalan 5300105… → erkak, 30.01.2005.
    Notöğri bölsa ValidationError.
    """
    import datetime

    value = (value or '').strip()
    if not value.isdigit() or len(value) != 14:
        raise forms.ValidationError("JŞŞIR 14 ta raqamdan iborat bölişi kerak.")
    first = int(value[0])
    if not 1 <= first <= 6:
        raise forms.ValidationError("JŞŞIR birinçi raqami 1 dan 6 gaça bölişi kerak (jins va tuğilgan asr).")
    century = {1: 1800, 2: 1800, 3: 1900, 4: 1900, 5: 2000, 6: 2000}[first]
    day, month, year = int(value[1:3]), int(value[3:5]), century + int(value[5:7])
    try:
        birth = datetime.date(year, month, day)
    except ValueError:
        raise forms.ValidationError(
            f"JŞŞIR dagi tuğilgan sana notöğri: {value[1:3]}.{value[3:5]}.{year}. "
            "2-3 raqam — kun, 4-5 — oy, 6-7 — yil bölişi kerak."
        ) from None
    if birth > datetime.date.today():
        raise forms.ValidationError("JŞŞIR dagi tuğilgan sana kelajakda bölişi mumkin emas.")
    return {'gender': 'male' if first % 2 else 'female', 'birth_date': birth}


def check_jshshir_matches(form, jshshir, birth_date, gender, *, jshshir_field='jshshir'):
    """JŞŞIR tuğilgan sana va jins bilan mos kelmasa formaga xato qöşadi."""
    if not jshshir:
        return
    try:
        info = parse_jshshir(jshshir)
    except forms.ValidationError:
        return  # format xatosi clean_jshshir'da allaqaçon çiqarilgan
    if birth_date and birth_date != info['birth_date']:
        form.add_error(jshshir_field, (
            f"JŞŞIR tuğilgan sanangiz bilan mos emas: JŞŞIR böyiça "
            f"{info['birth_date']:%d.%m.%Y}, siz kiritgan sana {birth_date:%d.%m.%Y}."
        ))
    if gender and gender != info['gender']:
        expected = 'erkak' if info['gender'] == 'male' else 'ayol'
        form.add_error(jshshir_field, (
            f"JŞŞIR jinsingiz bilan mos emas: birinçi raqam {jshshir[0]} — {expected} "
            "(toq raqam — erkak, juft raqam — ayol)."
        ))


def _clean_name_field(name, field_label):
    """Remove emojis, stickers and special characters from name field."""
    # Körinmas va böş belgilarni bloklaş (Hangul Filler, braille blank, va h.k.)
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
        raise forms.ValidationError(f"{field_label} faqat harflardan iborat bölişi kerak! Böş yoki körinmas belgilar qabul qilinmaydi.")
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
        widget=forms.DateInput(format='%Y-%m-%d', attrs={'class': 'form-control', 'type': 'date'})
    )
    role = forms.ChoiceField(
        choices=[('student', 'Öquvçi')],
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
        # `role` ATAYLAB yöq: oçiq röyxatdan ötiş faqat 'student' yaratadi.
        # Ilgari `role` Meta.fields içida edi va HiddenInput bölgani uçun
        # hujumçi POST da role=teacher yuborib özini öqituvçi qilib
        # röyxatdan ötkaza olardi (privilege escalation). Rol faqat serverda,
        # save() içida belgilanadi; öqituvchi/admin rollari admin panelidan
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
        return normalize_uz_phone(self.cleaned_data.get('phone'))


class SocialSignupForm(forms.ModelForm):
    """Google/Facebook/GitHub orqali röyxatdan ötiş: email va parol xizmatdan, qolgani şu yerda."""
    first_name = forms.CharField(max_length=100, widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ismingiz'}))
    last_name = forms.CharField(max_length=100, widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Familiyangiz'}))
    username = forms.CharField(max_length=150, widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Username'}))
    phone = forms.CharField(max_length=15, widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': '(XX) XXX XX XX', 'id': 'id_phone'}))
    birth_date = forms.DateField(widget=forms.DateInput(format='%Y-%m-%d', attrs={'class': 'form-control', 'type': 'date'}))

    class Meta:
        model = CustomUser
        fields = ['first_name', 'last_name', 'username', 'phone', 'birth_date']

    def clean_first_name(self):
        return _clean_name_field(self.cleaned_data.get('first_name', ''), 'Ism')

    def clean_last_name(self):
        return _clean_name_field(self.cleaned_data.get('last_name', ''), 'Familiya')

    def clean_username(self):
        username = self.cleaned_data.get('username', '').strip()
        CustomUser.username_validator(username)
        if CustomUser.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError("Bu username band. Boşqasini tanlang.")
        return username

    def clean_phone(self):
        return normalize_uz_phone(self.cleaned_data.get('phone'))


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
        label="Pullik kurs (sörov keladi)"
    )
    is_mandatory = forms.BooleanField(
        required=False,
        initial=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        label="Majburiy kurs (barça öquvçilar uçun)"
    )
    one_time_payment = forms.BooleanField(
        required=False,
        initial=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        label="Bir martalik tölov (sörovsiz, Tezcheck orqali sotiladi)"
    )
    one_time_price = forms.IntegerField(
        required=False,
        min_value=0,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'min': 1000, 'step': 1000, 'placeholder': 'Masalan: 300000'}),
        label="Kurs narxi (söm)"
    )
    closed_group_link = forms.URLField(
        required=False,
        widget=forms.URLInput(attrs={'class': 'form-control', 'placeholder': 'https://t.me/+... yoki boşqa havola'}),
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
        widget=forms.NumberInput(attrs={'class': 'form-control', 'placeholder': '0 = çeksiz', 'min': 0}),
        label="Mavzular (darslar) soni",
        help_text="0 = çeksiz. Belgilangan sondan ortiq dars qöşib bölmaydi."
    )
    duration_months = forms.IntegerField(
        required=False,
        min_value=0,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Masalan: 6', 'min': 0}),
        label="Öqiş davomiyligi (oy)"
    )

    # ─── Ustoz tölov stavkalari (har kasb uçun alohida) ───
    price_per_video = forms.IntegerField(
        required=False, min_value=0, initial=25000,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'min': 0, 'step': 500, 'placeholder': '25000'}),
        label="Video dars uçun tölov (söm)",
        help_text="Ustozga şu kursda har video dars uçun tölanadi."
    )
    price_per_test = forms.IntegerField(
        required=False, min_value=0, initial=10000,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'min': 0, 'step': 500, 'placeholder': '10000'}),
        label="Test uçun tölov (söm)",
        help_text="Ustozga şu kursda har test uçun tölanadi."
    )
    price_per_homework = forms.IntegerField(
        required=False, min_value=0, initial=10000,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'min': 0, 'step': 500, 'placeholder': '10000'}),
        label="Uyga vazifa uçun tölov (söm)",
        help_text="Ustozga şu kursda har uyga vazifa uçun tölanadi."
    )

    def clean_topic_count(self):
        v = self.cleaned_data.get('topic_count')
        return v if v else 0

    def _clean_rate(self, field, default):
        """Böş qoldirilsa standart qiymatga tuşadi (maydon null böla olmaydi)."""
        v = self.cleaned_data.get(field)
        return default if v is None else v

    def clean_price_per_video(self):
        return self._clean_rate('price_per_video', 25000)

    def clean_price_per_test(self):
        return self._clean_rate('price_per_test', 10000)

    def clean_price_per_homework(self):
        return self._clean_rate('price_per_homework', 10000)

    def clean(self):
        cleaned = super().clean()
        price = cleaned.get('one_time_price') or 0
        if cleaned.get('one_time_payment'):
            if price < 1000:
                self.add_error('one_time_price', "Bir martalik tölov uçun narx kamida 1 000 söm bölişi kerak.")
            if cleaned.get('is_mandatory'):
                self.add_error('one_time_payment', "Majburiy kursni sotib bölmaydi.")
            # Sotiladigan kurs har doim pullik hisoblanadi.
            cleaned['is_paid'] = True
        cleaned['one_time_price'] = price
        return cleaned

    class Meta:
        model = Profession
        fields = ['name', 'photo', 'description', 'kind', 'is_paid', 'one_time_payment', 'one_time_price', 'is_mandatory',
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
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Özingiz haqida...'})
    )
    obektivka = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 4, 'placeholder': 'Obektivka...'})
    )

    address = forms.CharField(required=False, widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Yaşaş manzilingiz'}))
    birth_date = forms.DateField(required=False, widget=forms.DateInput(format='%Y-%m-%d', attrs={'class': 'form-control', 'type': 'date'}))
    id_card = forms.FileField(required=False, validators=[validate_document_upload], widget=forms.FileInput(attrs={'class': 'form-control'}))
    birth_certificate = forms.FileField(required=False, validators=[validate_document_upload], widget=forms.FileInput(attrs={'class': 'form-control'}))

    class Meta:
        model = CustomUser
        fields = ['first_name', 'last_name', 'email', 'phone', 'address', 'birth_date', 'id_card', 'birth_certificate', 'photo', 'bio', 'obektivka']

    def clean_phone(self):
        return normalize_uz_phone(self.cleaned_data.get('phone'))

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
        widget=forms.Select(attrs={'class': 'form-control'}), empty_label="Yönalişni tanlang"
    )
    assistant_role = forms.ModelChoiceField(
        queryset=None, required=False,
        widget=forms.Select(attrs={'class': 'form-control'}),
        empty_label="— Permission profili (faqat Yordamçi admin uçun) —",
        label="Yordamçi rol",
    )
    photo = forms.ImageField(required=False, widget=forms.FileInput(attrs={'class': 'form-control'}))
    bio = forms.CharField(required=False, widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3}))
    is_blocked = forms.BooleanField(required=False, widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}))
    new_password = forms.CharField(
        required=False,
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Yangi parol'})
    )

    address = forms.CharField(required=False, widget=forms.TextInput(attrs={'class': 'form-control'}))
    birth_date = forms.DateField(required=False, widget=forms.DateInput(format='%Y-%m-%d', attrs={'class': 'form-control', 'type': 'date'}))
    id_card = forms.FileField(required=False, validators=[validate_document_upload], widget=forms.FileInput(attrs={'class': 'form-control'}))
    birth_certificate = forms.FileField(required=False, validators=[validate_document_upload], widget=forms.FileInput(attrs={'class': 'form-control'}))

    gender = forms.ChoiceField(required=False, choices=[('', 'Tanlang')] + list(CustomUser.GENDER_CHOICES), widget=forms.Select(attrs={'class': 'form-control'}))
    nationality = forms.CharField(required=False, max_length=100, widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': "Masalan: Özbek"}))
    passport_series = forms.CharField(required=False, max_length=10, widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'AA', 'maxlength': '2'}))
    passport_number = forms.CharField(required=False, max_length=20, widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': '1234567', 'maxlength': '7'}))
    jshshir = forms.CharField(required=False, max_length=14, widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': '14 xonali raqam', 'maxlength': '14'}))
    passport_issued_date = forms.DateField(required=False, widget=forms.DateInput(format='%Y-%m-%d', attrs={'class': 'form-control', 'type': 'date'}))
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

    def clean_jshshir(self):
        jshshir = ''.join((self.cleaned_data.get('jshshir') or '').split())
        if jshshir:
            parse_jshshir(jshshir)
        return jshshir

    def clean(self):
        cleaned = super().clean()
        check_jshshir_matches(self, cleaned.get('jshshir'), cleaned.get('birth_date'), cleaned.get('gender'))
        return cleaned


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
    # Davomiylikni server özi YouTube/Vimeo'dan aniqlaydi (anti-cheat: mijoz
    # aytgan qiymatga işonib bölmaydi). Bu maydon — ZAXIRA: server aniqlay
    # olmasa (private video, kvota tugagan) admin qölda kiritadi, aks holda
    # köriş talabi hisoblanmay dars yopilmaydi.
    duration = forms.IntegerField(
        required=False,
        min_value=0,
        max_value=1440,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'placeholder': "Böş qoldiring — avtomatik aniqlanadi",
        }),
        label="Davomiyligi (daqiqa)",
        help_text="Faqat server davomiylikni aniqlay olmagan holatda töldiring.",
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
            raise forms.ValidationError("Vimeo havolasi vimeo.com dan bölişi kerak.")
        if youtube_url and 'youtube.com' not in youtube_url and 'youtu.be' not in youtube_url:
            raise forms.ValidationError("YouTube havolasi youtube.com yoki youtu.be dan bölişi kerak.")

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
        label="AI tekşirsin"
    )
    handwritten_only = forms.BooleanField(
        required=False,
        initial=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        label="Faqat yozma topşiriş (rasm)"
    )


class DictionaryForm(forms.Form):
    title = forms.CharField(
        max_length=300,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': "Luğat nomi"})
    )
    description = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'class': 'form-control', 'placeholder': "Luğat haqida qisqa tavsif (ixtiyoriy)", 'rows': 2})
    )


class HomeworkSubmissionForm(forms.ModelForm):
    SUBMISSION_TYPE_CHOICES = (
        ('file', 'Fayl yuklaş'),
        ('text', 'Matn yoziş'),
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
            raise forms.ValidationError("Fayl yuklaşingiz kerak!")
        if submission_type == 'file' and file and file.size > 5 * 1024 * 1024:
            raise forms.ValidationError("Fayl hajmi 5 MB dan oşmasligi kerak!")
        if submission_type == 'text' and not text_content:
            raise forms.ValidationError("Matn kiritişingiz kerak!")
        
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
        ('practice', 'Tajriba oşiriş'),
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
        widget=forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Ötiş bali (%)'})
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
        label="Savollar tartibini aralaştiriş"
    )
    shuffle_answers = forms.BooleanField(
        required=False,
        initial=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        label="Javoblar tartibini aralaştiriş"
    )
    question_count = forms.IntegerField(
        initial=0,
        required=False,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'placeholder': '0 = barçasi', 'min': '0'}),
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
        help_text="Böş qoldirilsa avtomatik yaratiladi",
    )
    file = forms.FileField(
        validators=[validate_document_upload],
        widget=forms.FileInput(attrs={'class': 'form-control', 'accept': '.pdf'}),
        label="Sertifikat fayli (PDF)"
    )
    valid_from = forms.DateField(
        widget=forms.DateInput(format='%Y-%m-%d', attrs={'class': 'form-control', 'type': 'date'}),
        label="Berilgan sana",
        required=False,
    )
    valid_until = forms.DateField(
        widget=forms.DateInput(format='%Y-%m-%d', attrs={'class': 'form-control', 'type': 'date'}),
        label="Amal qiliş muddati",
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
                raise forms.ValidationError("Bu ID raqam allaqaçon mavjud!")
        return cert_id


class SectionForm(forms.ModelForm):
    title = forms.CharField(
        max_length=200,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': "Bölim nomi"})
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
    """Profil töldiriş formasi - login dan keyin majburiy"""
    
    first_name = forms.CharField(
        max_length=100,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ismingiz'})
    )
    last_name = forms.CharField(
        max_length=100,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Familiyangiz'})
    )
    birth_date = forms.DateField(
        widget=forms.DateInput(format='%Y-%m-%d', attrs={'class': 'form-control', 'type': 'date'}),
        label="Tuğilgan kuni"
    )
    gender = forms.ChoiceField(
        choices=[('', 'Tanlang...')] + list(CustomUser.GENDER_CHOICES),
        widget=forms.Select(attrs={'class': 'form-select'}),
        label="Jinsi"
    )
    nationality = forms.CharField(
        max_length=100,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': "Masalan: Özbek"}),
        label="Millati"
    )
    
    # ── Hujjat: pasport YOKI metrika (bittasi yetarli) ──
    document_type = forms.ChoiceField(
        required=False,
        choices=[('', 'Tanlang...')] + list(CustomUser.DOCUMENT_TYPE_CHOICES),
        widget=forms.Select(attrs={'class': 'form-select'}),
        label="Hujjat turi",
    )

    # Passport fields (pasport tanlanganda majburiy — clean() da tekşiriladi)
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
        label="JŞŞIR (PINFL)"
    )
    passport_issued_date = forms.DateField(
        required=False,
        widget=forms.DateInput(format='%Y-%m-%d', attrs={'class': 'form-control', 'type': 'date'}),
        label="Pasport berilgan sana"
    )

    # Metrika fields (metrika tanlanganda majburiy — JŞŞIR bölmaydi)
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
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': "Otangizning töliq ismi"}),
        label="Otasining töliq ismi"
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
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': "Onangizning töliq ismi"}),
        label="Onasining töliq ismi"
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
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': "Töliq yaşaş manzili"}),
        label="Yaşaş manzili"
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
        # JŞŞIR faqat kiritilgan bölsa tekşiriladi (metrikada JŞŞIR bölmaydi).
        jshshir = ''.join((self.cleaned_data.get('jshshir') or '').split())
        if jshshir:
            parse_jshshir(jshshir)
        return jshshir

    def clean(self):
        """Hujjat turiga qarab (pasport yoki metrika) mos maydonlarni tekşiradi.

        - Pasport: seriya + raqam + JŞŞIR majburiy.
        - Metrika: seriya + raqam majburiy (JŞŞIR yöq).
        Hujjat turi tanlanmagan bölsa hujjat maydonlari majburiy emas — ammo
        bunday holatda profil "töldirilmagan" bölib qoladi (foydalanuvçi skip qilişi mumkin).
        """
        cleaned = super().clean()
        doc_type = cleaned.get('document_type')

        if doc_type == 'passport':
            if not cleaned.get('passport_series'):
                self.add_error('passport_series', "Pasport seriyasi majburiy.")
            if not cleaned.get('passport_number'):
                self.add_error('passport_number', "Pasport raqami majburiy.")
            if not cleaned.get('jshshir'):
                self.add_error('jshshir', "Pasport uçun JŞŞIR majburiy.")
        elif doc_type == 'metrka':
            if not cleaned.get('metrka_series'):
                self.add_error('metrka_series', "Metrika seriyasi majburiy (masalan: I-GZ).")
            if not cleaned.get('metrka_number'):
                self.add_error('metrka_number', "Metrika raqami majburiy.")

        # JŞŞIR içidagi jins va tuğilgan sana kiritilgan ma'lumotlarga mos bölişi şart.
        check_jshshir_matches(self, cleaned.get('jshshir'), cleaned.get('birth_date'), cleaned.get('gender'))
        return cleaned

    def clean_parent_phone(self):
        return normalize_uz_phone(self.cleaned_data.get('parent_phone'))

    def _clean_optional_phone(self, field_name):
        return normalize_uz_phone(self.cleaned_data.get(field_name), required=False)

    def clean_father_phone(self):
        return self._clean_optional_phone('father_phone')

    def clean_mother_phone(self):
        return self._clean_optional_phone('mother_phone')
