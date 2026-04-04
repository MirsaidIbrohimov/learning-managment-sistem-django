from django.core.management.base import BaseCommand
from django.conf import settings


class Command(BaseCommand):
    help = "Cron job sozlash uchun yo'riqnoma ko'rsatish"

    def handle(self, *args, **options):
        site_url = getattr(settings, 'SITE_URL', 'https://itcreative.uz').rstrip('/')

        self.stdout.write(self.style.SUCCESS("""
╔══════════════════════════════════════════════════════╗
║  TELEGRAM BOT KEEP-ALIVE SOZLASH                     ║
╚══════════════════════════════════════════════════════╝

Bot to'xtab qolmasligi uchun quyidagi usullardan BIRINI tanlang:

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1-USUL: CRON JOB (tavsiya etiladi)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Hosting panelingizda Cron Jobs bo'limiga kiring va
har 5 daqiqada ishlaydigan cron qo'shing:

  */5 * * * * curl -s {site_url}/telegram/health/ > /dev/null 2>&1

Yoki Django management command bilan:

  */5 * * * * cd /path/to/project && python manage.py keep_bot_alive --once

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
2-USUL: TASHQI MONITORING XIZMATLARI (bepul)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Quyidagi bepul xizmatlardan foydalaning:

a) UptimeRobot (https://uptimerobot.com):
   - Ro'yxatdan o'ting
   - "Add New Monitor" bosing
   - Monitor Type: HTTP(s)
   - URL: {site_url}/telegram/health/
   - Monitoring Interval: 5 minutes

b) cron-job.org (https://cron-job.org):
   - Ro'yxatdan o'ting
   - "Create Cronjob" bosing
   - URL: {site_url}/telegram/health/
   - Schedule: Har 5 daqiqada

c) Freshping (https://freshping.io):
   - Bepul 50 ta check
   - URL: {site_url}/telegram/health/

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ESLATMA
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Health check URL: {site_url}/telegram/health/
Webhook URL: {site_url}/telegram/webhook/
""".format(site_url=site_url)))
