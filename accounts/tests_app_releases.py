import hashlib
import shutil
import tempfile
from datetime import date, timedelta

from django.core.cache import cache
from django.core.files.storage import FileSystemStorage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import AppRelease, CustomUser, UserSession

APK = b'PK\x03\x04' + b'\x00' * 2048
EXE = b'MZ' + b'\x90' * 2048
MSI = b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1' + b'\x00' * 2048


class AppReleasesTests(TestCase):
    """Ilovalar boshqaruvi: admin yuklash/tahrirlash/almashtirish/yashirish/o'chirish, foydalanuvchi yuklab olishi va navbar."""

    def setUp(self):
        cache.clear()
        cache.set('birthday_check_done', True, 86400)
        self.tmp = tempfile.mkdtemp()
        self.field = AppRelease._meta.get_field('file')
        self._storage = self.field.storage
        self.field.storage = FileSystemStorage(location=self.tmp)

    def tearDown(self):
        self.field.storage = self._storage
        shutil.rmtree(self.tmp, ignore_errors=True)
        cache.clear()

    def login(self, role, client=None):
        client = client or self.client
        extra = {'is_profile_completed': True, 'birth_date': date(2008, 5, 12)} if role == 'student' else {}
        user = CustomUser.objects.create_user(username=f'app-{role}', password='x', role=role,
                                              phone=f'+99891{sum(map(ord, role)):07d}', **extra)
        client.force_login(user)
        UserSession.objects.create(user=user, session_key=client.session.session_key,
                                   expires_at=timezone.now() + timedelta(hours=2))
        return user

    def upload(self, platform='android', version='1.0.0', content=APK, name='app.apk', **extra):
        data = {'platform': platform, 'version': version, 'title': 'ITC Academy', 'notes': 'Yangi',
                'is_published': 'on', 'hide_previous': 'on', 'file': SimpleUploadedFile(name, content)}
        data.update(extra)
        return self.client.post(reverse('admin_app_releases'), data)

    # ── Ruxsatlar ──
    def test_only_admin_can_manage(self):
        for role in ('student', 'teacher'):
            with self.subTest(role=role):
                client = Client()
                self.login(role, client)
                self.assertRedirects(client.get(reverse('admin_app_releases')), reverse('home'), fetch_redirect_response=False)
                client.post(reverse('admin_app_releases'), {'platform': 'android', 'version': '9', 'file': SimpleUploadedFile('a.apk', APK)})
        self.assertFalse(AppRelease.objects.exists())

    def test_toggle_and_delete_require_post(self):
        self.login('admin')
        self.upload()
        pk = AppRelease.objects.get().pk
        self.assertEqual(self.client.get(reverse('admin_app_release_toggle', args=[pk])).status_code, 405)
        self.assertEqual(self.client.get(reverse('admin_app_release_delete', args=[pk])).status_code, 405)

    # ── Yuklash va tekshiruv ──
    def test_upload_valid_apk(self):
        admin = self.login('admin')
        self.assertRedirects(self.upload(), reverse('admin_app_releases'), fetch_redirect_response=False)
        rel = AppRelease.objects.get()
        self.assertEqual((rel.platform, rel.version, rel.is_published, rel.uploaded_by), ('android', '1.0.0', True, admin))
        self.assertEqual(rel.sha256, hashlib.sha256(APK).hexdigest())
        self.assertEqual(rel.file_size, len(APK))
        self.assertTrue(rel.file.name.endswith('.apk'))  # SafeMediaStorage kabi .txt ga aylantirilmaydi
        self.assertTrue(rel.file.storage.exists(rel.file.name))

    def test_upload_windows_exe_and_msi(self):
        self.login('admin')
        self.upload('windows', '1.0.0', EXE, 'setup.exe')
        self.upload('windows', '1.0.1', MSI, 'setup.msi', hide_previous='')
        self.assertEqual(AppRelease.objects.filter(platform='windows', is_published=True).count(), 2)

    def test_invalid_files_rejected(self):
        self.login('admin')
        cases = [
            ('android', EXE, 'setup.exe'),          # noto'g'ri kengaytma
            ('android', EXE, 'fake.apk'),           # kengaytma to'g'ri, imzo yo'q
            ('windows', APK, 'fake.exe'),
            ('windows', b'MZ', 'tiny.exe'),         # bo'sh/buzilgan
            ('android', APK, 'app.apk.php'),
        ]
        for platform, content, name in cases:
            with self.subTest(name=name):
                self.assertEqual(self.upload(platform, '2.0', content, name).status_code, 400)
        self.assertEqual(self.upload('ios', '1', APK, 'a.apk').status_code, 400)
        self.assertEqual(self.upload(version='').status_code, 400)
        self.assertFalse(AppRelease.objects.exists())

    def test_hide_previous_versions(self):
        self.login('admin')
        self.upload(version='1.0.0')
        self.upload(version='1.1.0')
        self.assertEqual(list(AppRelease.objects.filter(is_published=True).values_list('version', flat=True)), ['1.1.0'])

    # ── Tahrirlash / almashtirish / yashirish / o'chirish ──
    def test_edit_and_replace_file(self):
        self.login('admin')
        self.upload()
        rel = AppRelease.objects.get()
        AppRelease.objects.filter(pk=rel.pk).update(download_count=5)
        old_name = rel.file.name
        new_apk = APK + b'new'
        response = self.client.post(reverse('admin_app_release_edit', args=[rel.pk]), {
            'version': '1.0.1', 'title': 'ITC Academy', 'min_os': 'Android 8+', 'notes': 'Tuzatishlar',
            'is_published': 'on', 'platform': 'windows', 'file': SimpleUploadedFile('new.apk', new_apk)})
        self.assertRedirects(response, reverse('admin_app_releases'), fetch_redirect_response=False)
        rel.refresh_from_db()
        self.assertEqual((rel.version, rel.platform, rel.min_os, rel.download_count), ('1.0.1', 'android', 'Android 8+', 0))
        self.assertEqual(rel.sha256, hashlib.sha256(new_apk).hexdigest())
        self.assertFalse(rel.file.storage.exists(old_name))
        self.assertTrue(rel.file.storage.exists(rel.file.name))

    def test_edit_without_file_keeps_file(self):
        self.login('admin')
        self.upload()
        rel = AppRelease.objects.get()
        self.client.post(reverse('admin_app_release_edit', args=[rel.pk]), {'version': '1.0.0-b', 'notes': 'x'})
        updated = AppRelease.objects.get()
        self.assertEqual((updated.version, updated.file.name, updated.is_published), ('1.0.0-b', rel.file.name, False))

    def test_toggle_and_delete(self):
        self.login('admin')
        self.upload()
        rel = AppRelease.objects.get()
        self.client.post(reverse('admin_app_release_toggle', args=[rel.pk]))
        self.assertFalse(AppRelease.objects.get().is_published)
        name = rel.file.name
        self.client.post(reverse('admin_app_release_delete', args=[rel.pk]))
        self.assertFalse(AppRelease.objects.exists())
        self.assertFalse(rel.file.storage.exists(name))

    # ── Foydalanuvchi: yuklab olish va navbar ──
    def test_download(self):
        self.login('admin')
        self.upload()
        rel = AppRelease.objects.get()
        student = Client()
        self.login('student', student)
        response = student.get(reverse('app_release_download', args=[rel.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/vnd.android.package-archive')
        self.assertIn('attachment; filename="ITC-Academy-Android-1.0.0.apk"', response['Content-Disposition'])
        self.assertEqual(b''.join(response.streaming_content), APK)
        self.assertEqual(AppRelease.objects.get().download_count, 1)
        self.assertEqual(Client().get(reverse('app_release_download', args=[rel.pk])).status_code, 302)  # login kerak

    def test_hidden_release_not_downloadable_by_users(self):
        self.login('admin')
        self.upload(is_published='')
        rel = AppRelease.objects.get()
        self.assertEqual(self.client.get(reverse('app_release_download', args=[rel.pk])).status_code, 200)  # admin tekshira oladi
        student = Client()
        self.login('student', student)
        self.assertEqual(student.get(reverse('app_release_download', args=[rel.pk])).status_code, 404)

    def test_navbar_and_apps_page(self):
        student = Client()
        self.login('student', student)
        html = student.get(reverse('home')).content.decode()
        # Hali ilova yo'q: ikonka bor, barcha platformalar "Tez kunda"
        self.assertIn('nr-apps-pop', html)
        self.assertEqual(html.count('class="nr-apps-soon"'), 5)
        for label in ('Android', 'Windows', 'iOS', 'macOS', 'Linux'):
            self.assertIn(label, html)
        self.login('admin')
        self.upload()
        self.upload('windows', '2.0', EXE, 'setup.exe')
        html = student.get(reverse('home')).content.decode()
        self.assertEqual(html.count('class="nr-apps-soon"'), 3)  # iOS, macOS, Linux
        for rel in AppRelease.objects.all():
            self.assertIn(reverse('app_release_download', args=[rel.pk]), html)
        page = student.get(reverse('apps_page'))
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, 'Yuklab olish', count=2)
        self.assertContains(page, 'ap-btn ap-btn-soon', count=3)  # sahifa kartalari (navbar menyusidan tashqari)

    def test_other_platform_formats(self):
        self.login('admin')
        dmg = b'\x00' * 4096 + b'koly' + b'\x00' * 508
        ok = [('macos', dmg, 'ITC.dmg'), ('macos', b'xar!' + b'\x00' * 2048, 'ITC.pkg'),
              ('linux', b'\x7fELF' + b'\x00' * 2048, 'ITC-Academy.AppImage'),
              ('linux', b'!<arch>\n' + b'\x00' * 2048, 'itc.deb'), ('ios', APK, 'ITC.ipa')]
        for platform, content, name in ok:
            with self.subTest(name=name):
                self.assertEqual(self.upload(platform, '1.0', content, name).status_code, 302)
        bad = [('macos', b'\x00' * 5000, 'fake.dmg'), ('linux', EXE, 'fake.deb'), ('ios', APK, 'app.apk')]
        for platform, content, name in bad:
            with self.subTest(name=name):
                self.assertEqual(self.upload(platform, '1.0', content, name).status_code, 400)
        self.assertEqual(AppRelease.objects.count(), len(ok))
