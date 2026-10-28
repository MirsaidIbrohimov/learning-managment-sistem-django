"""Navbar uçun kontekst: foydalanuvçining faol startupi va mentor huquqi.

Talaba uçun bitta `only()` sörov. Mentor bayroği faqat `teacher`/`admin`
rollari uçun hisoblanadi — öquvçilarga qöşimça sörov tuşmaydi.
"""

MENTOR_ROLES = ('teacher', 'admin', 'assistant_admin')


def my_startup(request):
    user = getattr(request, 'user', None)
    if not user or not user.is_authenticated:
        return {'my_startup': None, 'startup_mentor_access': False}

    from .models import Startup, StartupMentor

    startup = (Startup.objects
               .filter(owner=user, status='active')
               .only('id', 'name', 'slug', 'progress', 'current_stage', 'total_xp')
               .first())

    mentor_access = False
    if getattr(user, 'role', None) in MENTOR_ROLES:
        mentor_access = (getattr(user, 'is_admin_or_assistant', False)
                         or StartupMentor.objects.filter(mentor=user, is_active=True).exists())

    return {'my_startup': startup, 'startup_mentor_access': mentor_access}
