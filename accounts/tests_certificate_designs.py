import io
import shutil
import tempfile
from datetime import timedelta
from unittest import mock

from django.core.cache import cache
from django.core.files.storage import FileSystemStorage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts import certificates
from accounts.models import (
    Certificate, CertificateDesign, CertificateSettings, CustomUser, Profession, UserSession,
)


def png_bytes(w=1200, h=600):
    from PIL import Image
    buf = io.BytesIO()
    Image.new('RGB', (w, h), (240, 230, 200)).save(buf, 'PNG')
    return buf.getvalue()


class CertificateDesignTests(TestCase):
    """Kurs böyiça sertifikat dizayni: standartga qaytiş, admin tahriri, biriktiriş."""

    def setUp(self):
        cache.clear()
        cache.set('birthday_check_done', True, 86400)
        self.tmp = tempfile.mkdtemp()
        self.media = override_settings(MEDIA_ROOT=self.tmp)
        self.media.enable()
        self.storages = []
        for model, name in ((CertificateDesign, 'background'), (Certificate, 'file')):
            field = model._meta.get_field(name)
            self.storages.append((field, field.storage))
            field.storage = FileSystemStorage(location=self.tmp)

        self.admin = CustomUser.objects.create_user(username='cd-admin', password='x', role='admin', phone='+998910000001')
        self.client.force_login(self.admin)
        UserSession.objects.create(user=self.admin, session_key=self.client.session.session_key,
                                   expires_at=timezone.now() + timedelta(hours=2))
        self.course_a = Profession.objects.create(name='Python', photo='a.jpg', description='d')
        self.course_b = Profession.objects.create(name='Frontend', photo='b.jpg', description='d')

    def tearDown(self):
        for field, storage in self.storages:
            field.storage = storage
        self.media.disable()
        shutil.rmtree(self.tmp, ignore_errors=True)
        cache.clear()

    def make_design(self, name='Kök', w=1200, h=600):
        return CertificateDesign.objects.create(
            name=name, background=SimpleUploadedFile('bg.png', png_bytes(w, h), content_type='image/png'))

    def make_cert(self, course, cert_id='ZMT-PY-26001'):
        return Certificate.objects.create(recipient_name='Aliyev Jasur', profession=course,
                                          certificate_id=cert_id, file='certificates/x.pdf')

    # ── PDF generatsiya ──
    def test_course_without_design_uses_standard_template(self):
        cert = self.make_cert(self.course_b)
        with mock.patch.object(certificates, 'render_design_pdf') as custom:
            pdf = certificates.generate_certificate_pdf(cert)
        custom.assert_not_called()
        self.assertTrue(pdf.startswith(b'%PDF'))

    def test_course_with_design_uses_its_background_and_aspect_ratio(self):
        design = self.make_design(w=1200, h=600)
        CertificateSettings.objects.create(profession=self.course_a, series_code='ZMT-PY', design=design)
        cert = self.make_cert(self.course_a)
        pdf = certificates.generate_certificate_pdf(cert)
        self.assertTrue(pdf.startswith(b'%PDF'))
        # Sahifa: A4 albom kengligi (841.89pt), balandlik — rasm nisbatida (1:2)
        self.assertIn(b'/MediaBox [ 0 0 841.8898 420.9449 ]', pdf)

    def test_other_course_keeps_standard_when_one_has_design(self):
        design = self.make_design()
        CertificateSettings.objects.create(profession=self.course_a, series_code='ZMT-PY', design=design)
        self.assertEqual(certificates.get_certificate_design(self.course_a), design)
        self.assertIsNone(certificates.get_certificate_design(self.course_b))

    # ── Admin: yaratiş / tahrirlaş / öçiriş ──
    def test_admin_creates_design_and_rejects_non_image(self):
        bad = self.client.post(reverse('admin_certificate_designs'), {
            'name': 'Yomon', 'background': SimpleUploadedFile('x.png', b'not an image', content_type='image/png')})
        self.assertRedirects(bad, reverse('admin_certificate_designs'), fetch_redirect_response=False)
        self.assertFalse(CertificateDesign.objects.exists())

        resp = self.client.post(reverse('admin_certificate_designs'), {
            'name': 'Yangi', 'background': SimpleUploadedFile('bg.png', png_bytes(), content_type='image/png')})
        design = CertificateDesign.objects.get()
        self.assertRedirects(resp, reverse('admin_certificate_design_edit', args=[design.pk]), fetch_redirect_response=False)
        self.assertEqual(self.client.get(reverse('admin_certificate_design_edit', args=[design.pk])).status_code, 200)

    def test_edit_saves_positions_with_clamping(self):
        design = self.make_design()
        self.client.post(reverse('admin_certificate_design_edit', args=[design.pk]), {
            'name': 'Yangilangan', 'text_color': '#123abc', 'course_format': '{course} KURSI',
            'name_x': '30.5', 'name_y': '140', 'name_size': '500', 'name_font': 'bold',
            'course_x': 'abc', 'show_course': '1', 'show_series': '1',  # show_date yuborilmadi -> yaşiriladi
        })
        design.refresh_from_db()
        self.assertEqual(design.name, 'Yangilangan')
        self.assertEqual(design.text_color, '#123abc')
        self.assertEqual(design.course_format, '{course} KURSI')
        self.assertEqual((design.name_x, design.name_y, design.name_size, design.name_font), (30.5, 100.0, 120, 'bold'))
        self.assertEqual(design.course_x, 50.0)  # notöğri qiymat -> standart
        self.assertTrue(design.show_series)
        self.assertFalse(design.show_date)

    def test_bad_color_is_ignored(self):
        design = self.make_design()
        self.client.post(reverse('admin_certificate_design_edit', args=[design.pk]),
                         {'name': 'X', 'text_color': 'red;}<script>'})
        design.refresh_from_db()
        self.assertEqual(design.text_color, '#141720')

    def test_preview_returns_pdf(self):
        design = self.make_design()
        resp = self.client.get(reverse('admin_certificate_design_preview', args=[design.pk]))
        self.assertEqual(resp['Content-Type'], 'application/pdf')
        self.assertTrue(resp.content.startswith(b'%PDF'))

    def test_delete_returns_courses_to_standard(self):
        design = self.make_design()
        CertificateSettings.objects.create(profession=self.course_a, series_code='ZMT-PY', design=design)
        self.client.post(reverse('admin_certificate_design_delete', args=[design.pk]))
        self.assertFalse(CertificateDesign.objects.exists())
        self.assertIsNone(CertificateSettings.objects.get(profession=self.course_a).design)

    def test_only_admin_can_manage(self):
        design = self.make_design()
        client = Client()
        student = CustomUser.objects.create_user(username='cd-st', password='x', role='teacher', phone='+998910000002')
        client.force_login(student)
        UserSession.objects.create(user=student, session_key=client.session.session_key,
                                   expires_at=timezone.now() + timedelta(hours=2))
        for url in (reverse('admin_certificate_designs'), reverse('admin_certificate_design_edit', args=[design.pk]),
                    reverse('admin_certificate_design_preview', args=[design.pk])):
            with self.subTest(url=url):
                self.assertRedirects(client.get(url), reverse('home'), fetch_redirect_response=False)
        client.post(reverse('admin_certificate_design_delete', args=[design.pk]))
        self.assertTrue(CertificateDesign.objects.exists())

    # ── Kursga biriktiriş ──
    def test_settings_assigns_design_and_optionally_regenerates(self):
        design = self.make_design()
        self.make_cert(self.course_a)
        url = reverse('admin_certificate_settings')
        with mock.patch('accounts.certificates.regenerate_certificate_file', return_value=True) as regen:
            self.client.post(url, {'profession_id': self.course_a.pk, 'series_code': 'zmt-py',
                                   'validity_years': '2', 'design_id': str(design.pk)})
            regen.assert_not_called()  # belgilanmagan — mavjudlari tegilmaydi
            cfg = CertificateSettings.objects.get(profession=self.course_a)
            self.assertEqual((cfg.series_code, cfg.design), ('ZMT-PY', design))

            # Standartga qaytariş + mavjudlarini yangilaş
            self.client.post(url, {'profession_id': self.course_a.pk, 'series_code': 'ZMT-PY',
                                   'validity_years': '2', 'design_id': '', 'regenerate': '1'})
            self.assertEqual(regen.call_count, 1)
        self.assertIsNone(CertificateSettings.objects.get(profession=self.course_a).design)

    def test_certificates_page_lists_designs(self):
        self.make_design(name='Oltin dizayn')
        resp = self.client.get(reverse('admin_certificates'))
        self.assertContains(resp, 'Oltin dizayn')
        self.assertContains(resp, reverse('admin_certificate_designs'))


class VerifyCertificatePageTests(TestCase):
    def setUp(self):
        cache.clear()
        cache.set('birthday_check_done', True, 86400)
        course = Profession.objects.create(name='Python Backend', photo='a.jpg', description='d')
        Certificate.objects.create(recipient_name='Karimova Nilufar', profession=course,
                                   certificate_id='ZMT-PY-26007', status='expired', file='certificates/x.pdf')

    def tearDown(self):
        cache.clear()

    def test_found(self):
        resp = self.client.get(reverse('verify_certificate'), {'id': 'ZMT-PY-26007'})
        self.assertContains(resp, 'Karimova Nilufar')
        self.assertContains(resp, 'Python Backend')
        self.assertContains(resp, 'data-tone="expired"')
        self.assertContains(resp, 'Muddati tugagan')
        self.assertNotContains(resp, 'Yuklab oliş')  # faol bölmagan sertifikat fayli körsatilmaydi

    def test_not_found(self):
        resp = self.client.get(reverse('verify_certificate'), {'id': 'NOPE-1'})
        self.assertContains(resp, 'Sertifikat topilmadi')

    def test_empty(self):
        resp = self.client.get(reverse('verify_certificate'))
        self.assertEqual(resp.status_code, 200)
        self.assertNotContains(resp, 'Sertifikat topilmadi')
