from django.test import Client
from accounts.models import CustomUser, VideoLesson

t = CustomUser.objects.filter(role='teacher').first()
c = Client()
c.force_login(t)

r = c.get('/teacher/earnings/', follow=True)
print('earnings status:', r.status_code, 'chain:', r.redirect_chain[:2])
print('has "Video testlar":', 'Video testlar'.encode() in r.content)

v = VideoLesson.objects.filter(lesson__profession__teachers=t).first()
print('teacher video pk:', v and v.pk)
if v:
    r2 = c.get('/video-quiz/teacher/video/%d/' % v.pk, follow=True)
    print('manager status:', r2.status_code, 'chain:', r2.redirect_chain[:2])
    print('has readonly reward-info:', b'vm-reward-info' in r2.content)
    print('has editable fReward input:', b'id="fReward"' in r2.content)
