import json
from datetime import date, timedelta

from django.core.cache import cache
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import CustomUser, NavigationPreference, UserSession


class NavigationPreferencesTests(TestCase):
    """Moslaştiriladigan navigatsiya: saqlaş endpointi, base.html atributlari va rollar."""

    def login(self, role='student', client=None, **extra):
        cache.clear()
        cache.set('birthday_check_done', True, 86400)
        client = client or self.client
        if role == 'student':  # ProfileCompletionMiddleware töldirilmagan profilni yönaltiradi
            extra.setdefault('is_profile_completed', True)
            extra.setdefault('birth_date', date(2008, 5, 12))
        extra.setdefault('phone', f'+99890{sum(map(ord, role)):07d}')  # phone — unique
        user = CustomUser.objects.filter(username=f'nav-{role}').first() or CustomUser.objects.create_user(
            username=f'nav-{role}', password='x', role=role, first_name='Ali', last_name='Valiyev', **extra)
        client.force_login(user)
        UserSession.objects.create(user=user, session_key=client.session.session_key,
                                   expires_at=timezone.now() + timedelta(hours=2))
        return user

    def post(self, data, client=None):
        return (client or self.client).post(reverse('save_navigation_preferences'), data=json.dumps(data),
                                            content_type='application/json')

    def home(self):
        response = self.client.get(reverse('home'))
        self.assertEqual(response.status_code, 200)
        return response.content.decode()

    # ── Endpoint ──
    def test_anonymous_cannot_save(self):
        response = self.post({'layout': 'top'})
        self.assertNotEqual(response.status_code, 200)
        self.assertFalse(NavigationPreference.objects.exists())

    def test_get_not_allowed(self):
        self.login()
        self.assertEqual(self.client.get(reverse('save_navigation_preferences')).status_code, 405)

    def test_save_and_partial_update(self):
        user = self.login()
        response = self.post({'layout': 'hybrid', 'sidebar': 'collapsed', 'theme': 'system', 'motion': False})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['prefs']['layout'], 'hybrid')
        self.post({'layout': 'top'})
        pref = NavigationPreference.objects.get(user=user)
        self.assertEqual((pref.layout, pref.sidebar, pref.theme, pref.motion), ('top', 'collapsed', 'system', False))

    def test_invalid_values_rejected(self):
        self.login()
        self.assertEqual(self.post({'layout': '<script>', 'motion': 'yes', 'role': 'admin'}).status_code, 400)
        response = self.client.post(reverse('save_navigation_preferences'), data='{bad json',
                                    content_type='application/json')
        self.assertEqual(response.status_code, 400)
        self.assertFalse(NavigationPreference.objects.exists())

    def test_csrf_required(self):
        client = Client(enforce_csrf_checks=True)
        self.login(client=client)
        self.assertEqual(self.post({'layout': 'top'}, client=client).status_code, 403)

    # ── base.html ──
    def test_defaults_render_current_compact_nav(self):
        self.login()
        html = self.home()
        self.assertIn('data-layout="compact"', html)
        self.assertIn('data-sb="expanded"', html)
        self.assertIn('id="nsPanel"', html)
        self.assertIn('js/nav-prefs.js', html)
        self.assertIn('css/nav-layouts.css', html)
        # Mavjud navbar elementlari saqlangan
        for marker in ('id="nrRail"', 'id="mainNavbar"', 'id="nbBellBtn"', 'id="themeToggleTop"',
                       'id="nrCmd"', 'nr-dock', 'id="nbMobilePanel"', 'id="mobileProfileMenu"'):
            self.assertIn(marker, html)

    def test_saved_prefs_restored_on_render(self):
        user = self.login()
        NavigationPreference.objects.create(user=user, layout='top', sidebar='collapsed', theme='dark', motion=False)
        html = self.home()
        self.assertIn('data-layout="top"', html)
        self.assertIn('data-sb="collapsed"', html)
        self.assertIn('data-motion="off"', html)
        self.assertIn("srv='dark'", html)

    def test_prefs_are_per_user(self):
        student = self.login('student')
        NavigationPreference.objects.create(user=student, layout='classic')
        other = Client()
        self.login('teacher', client=other)
        html = other.get(reverse('home')).content.decode()
        self.assertIn('data-layout="compact"', html)

    # ── Rollar (yuqori menyu ham yon panel qoidalariga böysunadi) ──
    def test_top_links_respect_roles(self):
        self.login('admin')
        html = self.home()
        self.assertIn('class="nr-tn"', html)
        self.assertNotIn(reverse('my_study_schedule'), html)
        self.assertIn(reverse('admin_dashboard'), html)

    def test_top_links_student(self):
        self.login('student')
        html = self.home()
        self.assertIn(reverse('my_study_schedule'), html)
        self.assertNotIn('Boşqaruv paneli', html)

    # ── Öqituvçi va admin panellari ──
    def panel(self, role, url_name):
        self.login(role, is_staff=role == 'admin')
        response = self.client.get(reverse(url_name))
        self.assertEqual(response.status_code, 200)
        return response.content.decode()

    def test_panels_default_keep_current_sidebar(self):
        for role, url_name in (('teacher', 'teacher:dashboard'), ('admin', 'admin_dashboard')):
            with self.subTest(role=role):
                html = self.panel(role, url_name)
                self.assertIn('data-layout="compact"', html)
                self.assertIn('id="nsPanel"', html)
                self.assertIn('data-ctx="panel"', html)
                self.assertIn('js/panel-nav.js', html)
                self.assertIn('css/panel-layouts.css', html)
                self.assertIn('railSel: "#adminSidebar"', html)
                self.assertNotIn('sidebar-collapsed', html.split('<body', 1)[1].split('>', 1)[0])
                for marker in ('id="adminSidebar"', 'id="sidebarToggle"', 'id="themeToggle"', 'data-nav-settings'):
                    self.assertIn(marker, html)

    def test_panel_renders_saved_prefs(self):
        user = self.login('teacher')
        NavigationPreference.objects.create(user=user, layout='hybrid', sidebar='collapsed', theme='dark')
        html = self.client.get(reverse('teacher:dashboard')).content.decode()
        self.assertIn('data-layout="hybrid"', html)
        self.assertIn('class="panel-teacher pn sidebar-collapsed"', html)
        self.assertIn("srv='dark'", html)

    def test_panel_top_layout_not_collapsed(self):
        user = self.login('admin', is_staff=True)
        NavigationPreference.objects.create(user=user, layout='top', sidebar='collapsed')
        html = self.client.get(reverse('admin_dashboard')).content.decode()
        self.assertIn('data-layout="top"', html)
        self.assertIn('class="panel-admin pn"', html)
