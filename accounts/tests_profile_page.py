from datetime import date, timedelta

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import CustomUser, UserSession


class ProfilePageRolesTests(TestCase):
    """Profil sahifasi har bir rol uchun o'z bo'limlari bilan ochilishi kerak."""

    def open_profile(self, role, **extra):
        cache.clear()
        cache.set('birthday_check_done', True, 86400)
        user = CustomUser.objects.create_user(username=f'pf-{role}', password='x', role=role,
                                              first_name='Ali', last_name='Valiyev', **extra)
        self.client.force_login(user)
        UserSession.objects.create(user=user, session_key=self.client.session.session_key,
                                   expires_at=timezone.now() + timedelta(hours=2))
        response = self.client.get(reverse('profile'))
        self.assertEqual(response.status_code, 200)
        return response

    def test_student_sees_learning_sections(self):
        response = self.open_profile('student', student_id=20250001, is_profile_completed=True,
                                     birth_date=date(2008, 5, 12))
        self.assertContains(response, 'css/profile-motion.css')
        self.assertContains(response, 'id="courses"')
        self.assertContains(response, 'id="certificates"')
        self.assertContains(response, 'id="sidNumber"')
        self.assertContains(response, 'O‘quv yo‘lingiz shu yerdan boshlanadi')

    def test_teacher_sees_workspace(self):
        response = self.open_profile('teacher')
        self.assertContains(response, reverse('teacher:dashboard'))
        self.assertNotContains(response, 'id="courses"')

    def test_admin_sees_management(self):
        response = self.open_profile('admin')
        self.assertContains(response, reverse('admin_dashboard'))
        self.assertContains(response, 'id="personal-info"')


class HomeAndNavbarRolesTests(TestCase):
    """Bosh sahifa va yangi yon panel navbar har bir rol uchun ochilishi kerak."""

    def open_home(self, role, **extra):
        cache.clear()
        cache.set('birthday_check_done', True, 86400)
        user = CustomUser.objects.create_user(username=f'home-{role}', password='x', role=role,
                                              first_name='Ali', last_name='Valiyev', **extra)
        self.client.force_login(user)
        UserSession.objects.create(user=user, session_key=self.client.session.session_key,
                                   expires_at=timezone.now() + timedelta(hours=2))
        response = self.client.get(reverse('home'))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        # Navbar: yon panel, bildirishnomalar (notify.js id'lari), Ctrl+K va mobil dock
        for marker in ('id="nrRail"', 'id="mainNavbar"', 'id="nbBellBtn"', 'id="nbBellList"',
                       'id="themeToggleTop"', 'id="nrCmd"', 'nr-dock', 'id="nbMobilePanel"'):
            self.assertIn(marker, html)
        self.assertIn('css/home-motion.css', html)
        return html

    def test_student_home(self):
        html = self.open_home('student', is_profile_completed=True, birth_date=date(2008, 5, 12))
        self.assertIn(reverse('my_study_schedule'), html)
        self.assertNotIn(reverse('admin_dashboard'), html)

    def test_teacher_home(self):
        html = self.open_home('teacher')
        self.assertIn(reverse('teacher:my_students'), html)
        self.assertIn(reverse('teacher:dashboard'), html)

    def test_admin_home(self):
        html = self.open_home('admin')
        self.assertIn(reverse('admin_users'), html)
        self.assertNotIn(reverse('my_study_schedule'), html)

    def test_assistant_home(self):
        html = self.open_home('assistant_admin')
        self.assertIn(reverse('yordamchi_students'), html)
