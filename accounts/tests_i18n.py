"""Sayt tili: standart tilda hech narsa yuklanmaydi, boşqa tilda dvigatel ulanadi, lug'at butun va xatosiz."""
import json
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.template import Context, Template
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from accounts.management.commands.i18n_extract import from_js, from_markup, from_python, normalize
from accounts.management.commands.i18n_validate import compile_catalog, problems
from accounts.models import NavigationPreference
from accounts.tests_weather_effect import login

User = get_user_model()
RUNTIME = 'i18n/i18n-runtime.js'


class LanguageShellTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='lang_user', password='x', role='student', phone='+998900000811',
            is_profile_completed=True, birth_date='2000-01-01', is_premium=True,
        )
        login(self.client, self.user)

    def page(self):
        return self.client.get(reverse('site_settings')).content.decode()

    def use(self, language):
        NavigationPreference.objects.update_or_create(user=self.user, defaults={'language': language})

    def test_default_language_loads_nothing(self):
        html = self.page()
        self.assertNotIn(RUNTIME, html)
        self.assertNotIn('i18n/ru.json', html)
        self.assertNotIn('data-i18n-pending', html)

    def test_old_latin_uses_runtime_without_catalog(self):
        self.use('uz')
        html = self.page()
        self.assertIn(RUNTIME, html)
        self.assertIn('data-lang="uz"', html)
        self.assertNotIn('data-catalog', html)

    def test_russian_and_english_load_only_their_catalog(self):
        for language, other in (('ru', 'en'), ('en', 'ru')):
            with self.subTest(language=language):
                self.use(language)
                html = self.page()
                self.assertIn(f'data-lang="{language}"', html)
                self.assertIn(f'i18n/{language}.json', html)
                self.assertNotIn(f'i18n/{other}.json', html)

    def test_language_needs_premium(self):
        self.use('ru')
        User.objects.filter(pk=self.user.pk).update(is_premium=False)
        self.assertNotIn(RUNTIME, self.page())
        self.assertEqual(NavigationPreference.objects.get(user=self.user).language, 'ru')

    def test_language_is_saved_to_account(self):
        response = self.client.post(reverse('save_navigation_preferences'), json.dumps({'language': 'en'}),
                                    content_type='application/json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(NavigationPreference.objects.get(user=self.user).language, 'en')

    def test_unknown_language_rejected(self):
        response = self.client.post(reverse('save_navigation_preferences'), json.dumps({'language': 'de'}),
                                    content_type='application/json')
        self.assertEqual(response.status_code, 400)

    def test_every_logged_in_shell_includes_language(self):
        root = Path(settings.BASE_DIR)
        for shell in ('accounts/templates/accounts/base.html', 'teacher/templates/teacher/base_teacher.html',
                      'accounts/templates/accounts/admin/base_admin.html', 'quiz/templates/quiz/base_quiz.html',
                      'accounts/templates/accounts/yordamchi/base_yordamchi.html', 'kurslarim/templates/kurslarim/base.html'):
            with self.subTest(shell=shell):
                self.assertIn('partials/i18n/_head.html', (root / shell).read_text(encoding='utf-8'))


class StaffGreetingTests(TestCase):
    def test_greeting_comes_from_server_and_is_not_swapped_by_script(self):
        teacher = User.objects.create_user(
            username='greet_teacher', password='x', role='teacher', phone='+998900000812',
            first_name='Ali', is_profile_completed=True, birth_date='2000-01-01',
        )
        login(self.client, teacher)
        html = self.client.get(reverse('home')).content.decode()
        self.assertNotIn('data-greet', html)
        self.assertRegex(html, r'id="heroTitle"><span class="split">Xayrli (?:tun|tong|kun|keç), Ali')

    def test_greeting_follows_the_hour(self):
        template = Template("{% include 'accounts/dashboard/_greeting.html' %}")
        for hour, expected in ((3, 'Xayrli tun'), (9, 'Xayrli tong'), (14, 'Xayrli kun'), (20, 'Xayrli keç')):
            with self.subTest(hour=hour), patch('django.template.defaulttags.datetime') as clock:
                clock.now.return_value = datetime(2026, 1, 1, hour, 0)
                self.assertEqual(template.render(Context()), expected)


class CatalogTests(SimpleTestCase):
    def load(self, name):
        return json.loads((Path(settings.BASE_DIR) / name).read_text(encoding='utf-8'))

    def test_translations_are_complete_and_valid(self):
        source = self.load('i18n/source.json')
        for language in ('ru', 'en'):
            with self.subTest(language=language):
                translated = self.load(f'i18n/{language}.json')
                self.assertEqual([text for text in source if text not in translated], [])
                self.assertEqual(problems(language, source, translated), [])

    def test_published_catalog_matches_translations(self):
        source = self.load('i18n/source.json')
        aliases = self.load('i18n/aliases.json')
        for language in ('ru', 'en'):
            with self.subTest(language=language):
                built = compile_catalog(self.load(f'i18n/{language}.json'), source, aliases)
                self.assertEqual(built, self.load(f'static/i18n/{language}.json'))

    def test_problems_catches_broken_placeholders_and_html(self):
        source = {'Sizda {0} ta': 1, 'Saqlaş': 1}
        found = problems('ru', source, {'Sizda {0} ta': 'У вас', 'Saqlaş': '<b>Сохранить</b>'})
        self.assertEqual({reason for _, reason in found}, {'joy belgilari mos emas', 'HTML qöşilgan'})


class ExtractTests(SimpleTestCase):
    def test_template_variable_becomes_placeholder(self):
        self.assertIn('Sizda {0} ta xabar', from_markup('<p>Sizda \x00 ta xabar</p>').texts)

    def test_script_and_style_are_not_page_text(self):
        parser = from_markup('<style>.a{color:red}</style><script>var a = 1;</script><b>Salom dunyo</b>')
        self.assertEqual(parser.texts, {'Salom dunyo'})

    def test_old_alphabet_key_is_normalized(self):
        self.assertEqual(normalize("Bo'lim   nomi"), 'Bölim nomi')

    def test_python_messages_and_fstrings(self):
        found = from_python('messages.success(request, f"{name} öçirildi.")\nmessages.error(request, "Xatolik yuz berdi")')
        self.assertEqual(found, {'{0} öçirildi.', 'Xatolik yuz berdi'})

    def test_python_docstring_is_ignored(self):
        self.assertEqual(from_python('"""Bu öçirilgan hujjat."""\nx = 1'), set())

    def test_js_code_strings_are_ignored(self):
        found = from_js("el.classList.add('active'); toast('Saqlab bölmadi'); var s = '.card > a';")
        self.assertEqual(found, {'Saqlab bölmadi'})
