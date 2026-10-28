import os
import shutil
import tempfile
from io import StringIO
from urllib.parse import quote

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase, override_settings

from accounts.models import Profession
from accounts.storage import SafeMediaStorage

PNG = (b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89'
       b'\x00\x00\x00\rIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82')
CYRILLIC = 'Снимок_экрана_2026.png'


class CyrillicMediaTests(TestCase):
    """Kirillça nomli yuklangan fayllar 404 bermasligi kerak."""

    def setUp(self):
        self.media = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.media, ignore_errors=True)
        override = override_settings(MEDIA_ROOT=self.media)
        override.enable()
        self.addCleanup(override.disable)

    def write(self, rel_bytes):
        path = os.path.join(os.fsencode(self.media), *rel_bytes.split(b'/'))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'wb') as fh:
            fh.write(PNG)
        return path

    def test_new_uploads_get_ascii_names(self):
        name = SafeMediaStorage(location=self.media).save(f'homework_submissions/{CYRILLIC}',
                                                        SimpleUploadedFile(CYRILLIC, PNG))
        self.assertTrue(name.isascii(), name)
        self.assertIn('Snimok_ekrana_2026', name)

    def test_existing_cyrillic_file_is_served(self):
        self.write(f'homework_submissions/{CYRILLIC}'.encode('utf-8'))
        response = self.client.get('/media/homework_submissions/' + quote(CYRILLIC))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'image/png')
        self.assertEqual(b''.join(response.streaming_content), PNG)

    def test_double_encoded_name_on_disk_is_served(self):
        mojibake = CYRILLIC.encode('utf-8').decode('latin-1').encode('utf-8')
        self.write(b'homework_submissions/' + mojibake)
        response = self.client.get('/media/homework_submissions/' + quote(CYRILLIC))
        self.assertEqual(response.status_code, 200)

    def test_fallback_never_leaves_media_root(self):
        for url in ('/media/../manage.py', '/media/' + quote('../Снимок.png')):
            with self.subTest(url=url):
                self.assertIn(self.client.get(url).status_code, (400, 404))

    def test_command_renames_files_and_updates_database(self):
        self.write(f'professions/{CYRILLIC}'.encode('utf-8'))
        course = Profession.objects.create(name='K', description='d', photo=f'professions/{CYRILLIC}')

        out = StringIO()
        call_command('fix_media_filenames', stdout=out)  # dry-run: heç narsa özgarmaydi
        course.refresh_from_db()
        self.assertEqual(course.photo.name, f'professions/{CYRILLIC}')
        self.assertIn('1 ta fayl', out.getvalue())

        call_command('fix_media_filenames', '--apply', stdout=StringIO())
        course.refresh_from_db()
        self.assertTrue(course.photo.name.isascii(), course.photo.name)
        self.assertTrue(os.path.isfile(os.path.join(self.media, course.photo.name)))
        self.assertEqual(self.client.get('/media/' + course.photo.name).status_code, 200)
