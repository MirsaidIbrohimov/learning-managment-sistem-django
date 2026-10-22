from datetime import timedelta

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import (
    CourseEnrollment, CustomUser, DirectMessage, GroupChatMessage, GroupChatRead, Message, Profession, UserSession,
)


class NotifyRecentTests(TestCase):
    """Qo'ng'iroq paneli: suhbatlar va xabarlardan oxirgi 3 tadan, faqat o'qilmaganlari."""

    def setUp(self):
        cache.clear()
        cache.set('birthday_check_done', True, 86400)
        self.user = CustomUser.objects.create_user(
            username='bell-user', phone='+998900000021', password='x', role='student',
            is_profile_completed=True, birth_date=timezone.localdate() - timedelta(days=7000))
        self.other = CustomUser.objects.create_user(
            username='bell-other', phone='+998900000022', password='x', role='student', first_name='Ali')
        self.course = Profession.objects.create(name='Guruh', photo='t.jpg', description='d')
        CourseEnrollment.objects.create(user=self.user, profession=self.course)
        self.client.force_login(self.user)
        UserSession.objects.create(user=self.user, session_key=self.client.session.session_key,
                                   expires_at=timezone.now() + timedelta(hours=2))

    def feed(self):
        return self.client.get(reverse('api_notify_feed')).json()['recent']

    def test_only_unread_last_three_of_each(self):
        for i in range(5):
            DirectMessage.objects.create(sender=self.other, recipient=self.user, message=f'dm {i}', is_read=i in (0, 4))
        GroupChatMessage.objects.create(profession=self.course, sender=self.user, message="o'zim")
        for i in range(5):
            Message.objects.create(recipient=self.user, title=f'Xabar {i}', content='c', is_read=i == 4)
        recent = self.feed()
        self.assertEqual([c['body'] for c in recent['chats']], ['dm 3', 'dm 2', 'dm 1'])
        self.assertEqual([m['title'] for m in recent['messages']], ['Xabar 3', 'Xabar 2', 'Xabar 1'])

    def test_group_messages_after_last_read_only(self):
        now = timezone.now()
        old = GroupChatMessage.objects.create(profession=self.course, sender=self.other, message='eski')
        GroupChatMessage.objects.filter(pk=old.pk).update(created_at=now - timedelta(minutes=2))
        GroupChatRead.objects.create(profession=self.course, user=self.user, last_read_at=now - timedelta(minutes=1))
        GroupChatMessage.objects.create(profession=self.course, sender=self.other, message='yangi')
        bodies = [c['body'] for c in self.feed()['chats']]
        self.assertEqual(len(bodies), 1)
        self.assertIn('yangi', bodies[0])

    def test_mark_all_read_clears_panel(self):
        DirectMessage.objects.create(sender=self.other, recipient=self.user, message='salom')
        GroupChatMessage.objects.create(profession=self.course, sender=self.other, message='guruh')
        Message.objects.create(recipient=self.user, title='X', content='c')
        response = self.client.post(reverse('api_notify_mark_all_read'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.feed(), {'chats': [], 'messages': []})
        self.assertFalse(DirectMessage.objects.filter(is_read=False).exists())
        self.assertFalse(Message.objects.filter(recipient=self.user, is_read=False).exists())

    def test_mark_all_read_requires_post_and_leaves_others(self):
        stranger = CustomUser.objects.create_user(username='s3', phone='+998900000023', password='x', role='student')
        DirectMessage.objects.create(sender=self.other, recipient=stranger, message='maxfiy')
        self.assertEqual(self.client.get(reverse('api_notify_mark_all_read')).status_code, 405)
        self.client.post(reverse('api_notify_mark_all_read'))
        self.assertTrue(DirectMessage.objects.filter(recipient=stranger, is_read=False).exists())
