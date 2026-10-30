from django.core.management.base import BaseCommand

from accounts.course_bundles import sync_bundle
from accounts.models import CourseBundle


class Command(BaseCommand):
    help = ("Birlashgan kurslarni tekşiradi: kursni tugatgan öquvçilarni qolgan kurslarga yozadi "
            "va hammasini tugatganlarga sertifikat beradi.")

    def handle(self, *args, **options):
        for bundle in CourseBundle.objects.filter(is_active=True):
            before = bundle.certificates.count()
            checked = sync_bundle(bundle)
            self.stdout.write(f'{bundle.name}: {checked} ta öquvçi tekşirildi, '
                              f'{bundle.certificates.count() - before} ta yangi sertifikat.')
