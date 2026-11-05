"""🖼 Orqa fon rasmi: Premium öquvçi va admin/öqituvçi qöya oladi, oddiy öquvçi yöq."""
import io
import shutil
import tempfile
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.tests_weather_effect import login
from accounts.wallpaper import clean_style, get_wallpaper

User = get_user_model()
MEDIA = tempfile.mkdtemp()


def image(name='bg.png', fmt='PNG', size=(40, 30)):
    from PIL import Image
    buf = io.BytesIO()
    Image.new('RGBA', size, (200, 30, 90, 255)).save(buf, fmt)
    return SimpleUploadedFile(name, buf.getvalue(), content_type='image/png')


@override_settings(MEDIA_ROOT=MEDIA)
class MediaTestBase(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)

    _n = 0

    def user(self, role='student', **kw):
        MediaTestBase._n += 1
        n = MediaTestBase._n
        u = User.objects.create_user(username=f'wp{n}', password='x', role=role, phone=f'+9989000081{n:02d}',
                                     is_profile_completed=True, birth_date='2000-01-01', **kw)
        login(self.client, u)
        return u


class WallpaperTests(MediaTestBase):
    def save(self, **data):
        return self.client.post(reverse('wallpaper_customize'), data)

    def test_premium_student_uploads_with_filters(self):
        u = self.user(is_premium=True)
        resp = self.save(wallpaper=image(), brightness='80', blur='5', hue='999', position='top')
        self.assertRedirects(resp, reverse('wallpaper_customize'), fetch_redirect_response=False)
        u.refresh_from_db()
        self.assertTrue(u.wallpaper.name.endswith('.jpg'))  # JPEG qilib qayta saqlanadi
        self.assertEqual((u.wallpaper_style['brightness'], u.wallpaper_style['blur'],
                          u.wallpaper_style['hue'], u.wallpaper_style['position']), (80, 5, 360, 'top'))
        page = self.client.get(reverse('profile')).content.decode()
        self.assertIn('id="itcWallpaper"', page)
        self.assertIn('blur(5px)', page)

    def test_teacher_and_admin_without_premium(self):
        for role in ('teacher', 'admin'):
            u = self.user(role=role)
            self.save(wallpaper=image())
            u.refresh_from_db()
            self.assertTrue(u.wallpaper, role)
            self.assertIsNotNone(get_wallpaper(u))

    def test_regular_student_cannot_save(self):
        u = self.user()
        resp = self.save(wallpaper=image())
        self.assertRedirects(resp, reverse('coin:buy_premium_page'), fetch_redirect_response=False)
        u.refresh_from_db()
        self.assertFalse(u.wallpaper)
        self.assertEqual(self.client.get(reverse('wallpaper_customize')).status_code, 200)  # körib sinaş mumkin

    def test_expired_premium_hides_but_keeps(self):
        u = self.user(is_premium=True)
        self.save(wallpaper=image())
        User.objects.filter(pk=u.pk).update(premium_expires_at=timezone.now() - timedelta(days=1))
        u.refresh_from_db()
        self.assertTrue(u.wallpaper)
        self.assertIsNone(get_wallpaper(u))

    def test_rejects_non_image(self):
        u = self.user(is_premium=True)
        self.save(wallpaper=SimpleUploadedFile('x.png', b'<?php echo 1; ?>', content_type='image/png'))
        u.refresh_from_db()
        self.assertFalse(u.wallpaper)

    def test_remove(self):
        u = self.user(is_premium=True)
        self.save(wallpaper=image())
        u.refresh_from_db()
        path = u.wallpaper.path
        self.client.post(reverse('wallpaper_customize'), {'action': 'remove'})
        u.refresh_from_db()
        self.assertFalse(u.wallpaper)
        import os
        self.assertFalse(os.path.exists(path))

    def test_style_injection_is_neutralised(self):
        s = clean_style({'position': "center;background:url(x)", 'blur': '1px);}', 'dim': '-5'})
        self.assertEqual((s['position'], s['blur'], s['dim']), ('center', 0, 0))


@override_settings(MEDIA_ROOT=MEDIA)
class BannerImageTests(WallpaperTests):
    def save(self, **data):
        if 'wallpaper' in data:
            data['image'] = data.pop('wallpaper')
        return self.client.post(reverse('banner_customize'), data)

    def test_premium_student_uploads_with_filters(self):
        u = self.user(is_premium=True)
        self.save(wallpaper=image(), sepia='40', position='bottom')
        u.refresh_from_db()
        self.assertTrue(u.banner_image.name.startswith('banners/'))
        self.assertEqual((u.banner_style['sepia'], u.banner_style['position'], u.banner_style['dim']), (40, 'bottom', 10))
        self.assertFalse(u.wallpaper)
        page = self.client.get(reverse('profile')).content.decode()
        self.assertIn('pd-bnr-img', page)
        self.assertIn('sepia(40%)', page)

    def test_teacher_and_admin_without_premium(self):
        from accounts.wallpaper import get_banner
        for role in ('teacher', 'admin'):
            u = self.user(role=role)
            self.save(wallpaper=image())
            u.refresh_from_db()
            self.assertIsNotNone(get_banner(u), role)

    def test_regular_student_cannot_save(self):
        u = self.user()
        resp = self.save(wallpaper=image())
        self.assertRedirects(resp, reverse('coin:buy_premium_page'), fetch_redirect_response=False)
        u.refresh_from_db()
        self.assertFalse(u.banner_image)
        self.assertEqual(self.client.get(reverse('banner_customize')).status_code, 200)

    def test_expired_premium_hides_but_keeps(self):
        from accounts.premium_deco import deco_classes
        u = self.user(is_premium=True)
        self.save(wallpaper=image())
        User.objects.filter(pk=u.pk).update(premium_expires_at=timezone.now() - timedelta(days=1))
        u.refresh_from_db()
        self.assertTrue(u.banner_image)
        d = deco_classes(u)
        self.assertIsNone(d['banner_img'])
        self.assertNotIn('pd-bnr-img', d['banner'])

    def test_rejects_non_image(self):
        u = self.user(is_premium=True)
        self.save(wallpaper=SimpleUploadedFile('x.png', b'<?php echo 1; ?>', content_type='image/png'))
        u.refresh_from_db()
        self.assertFalse(u.banner_image)

    def test_remove(self):
        import os
        u = self.user(is_premium=True)
        self.save(wallpaper=image())
        u.refresh_from_db()
        path = u.banner_image.path
        self.client.post(reverse('banner_customize'), {'action': 'remove'})
        u.refresh_from_db()
        self.assertFalse(u.banner_image)
        self.assertFalse(os.path.exists(path))

    def test_api_returns_banner_for_leaderboard(self):
        from accounts.premium_deco import deco_classes
        u = self.user(is_premium=True)
        self.save(wallpaper=image(), blur='3')
        u.refresh_from_db()
        d = deco_classes(u)
        self.assertEqual(d['banner'], 'pd-bnr pd-bnr-img')
        self.assertIn('blur(3px)', d['banner_img']['filter'])


@override_settings(MEDIA_ROOT=MEDIA)
class BannerEverywhereAndChatTests(MediaTestBase):
    def setUp(self):
        from accounts.models import DirectMessage
        self.teacher = self.user(role='teacher')
        self.client.post(reverse('banner_customize'), {'image': image(), 'hue': '90'})
        self.student = self.user(is_premium=True)  # oxirgi login — öquvçi
        DirectMessage.objects.create(sender=self.teacher, recipient=self.student, message='Salom')

    def test_chat_sidebar_returns_partner_card_with_banner(self):
        resp = self.client.get(reverse('api_chat_sidebar'), HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        item = next(i for i in resp.json()['items'] if i['kind'] == 'dm')
        self.assertEqual((item['role'], item['username']), ('teacher', self.teacher.username))
        self.assertEqual(item['profile_url'], reverse('teacher_public_profile', args=[self.teacher.pk]))
        self.assertIn('hue-rotate(90deg)', item['banner']['filter'])

    def test_chat_page_renders_new_layout(self):
        page = self.client.get(reverse('direct_chat', args=[self.teacher.pk])).content.decode()
        for marker in ('mz-scene', 'id="mzQuick"', 'id="mzInfoActs"', 'id="mzHeadPill"', 'id="mzSideCount"'):
            self.assertIn(marker, page)

    def test_teacher_public_profile_shows_banner(self):
        page = self.client.get(reverse('teacher_public_profile', args=[self.teacher.pk])).content.decode()
        self.assertIn('pd-bimg', page)
        self.assertIn('hue-rotate(90deg)', page)
