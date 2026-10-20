# Django tezligi: stagingda tekshirish va bosqichma-bosqich yoqish

Bu fayllar loyiha ichida tayyorlandi; productionga ulanilmadi, Redis o‘rnatilmadi,
Nginx/Apache qayta yuklanmadi va yuklama testi yuborilmadi. Avval staging.
Asl DB SQLite bo‘lib qoladi, backup ham uni qo‘llaydi. 100+ MB DB hajmi
o‘zi RPS sababini aniqlamaydi: query, write lock, process quota va queue muhim.

## Nima o‘zgardi

- `config/settings.py`: DEBUG endi `.env`dan, default False. Redis default o‘chiq;
  DB session mavjud, istalsa Redis `cached_db` yoqiladi. `settings/production.py`
  mavjud sozlamalarni import qiladi, DEBUG=True bo‘lsa ishga tushishni rad etadi.
- Landing HTML umumiy cache qilinmaydi: unda CSRF forma, shaxsiy kabinet va
  session bor. Faqat ommaviy kurslar/postlar/statistika 60 soniyaga cache qilinadi.
  Yangilanish/bloklash shu TTLgacha kech ko‘rinishi mumkin. `LANDING_CACHE_SECONDS=0`
  buni o‘chiradi; TTLni o‘zgartirganda eski kalitni o‘chirish yoki muddati tugashini kutish kerak.
- Blog sahifasida author join va like/comment count aggregation qo‘shildi;
  izohlar user bilan bitta queryda keladi. Dashboard kurs ustozlari batch
  prefetch qilinadi; har enrollment uchun `.first()` querysi olib tashlandi.
- `cache_page` faqat `robots.txt` va `sitemap.xml`ga qo‘yildi. Shaxsiy kabinet,
  login, ariza, to‘lov, API va CSRF sahifalarini umumiy cache qilish mumkin emas.
- Redis default cache rate limit uchun ham ishlatiladi: xatolar jim yashirilmaydi.
  Redis ishlamasa shu cachega bog‘liq requestlar 500 berishi mumkin; tez rollback bor.
  Sessiya `cached_db` bo‘lgani uchun DBda saqlanadi, Redis tozalansa login yo‘qolmaydi.
- Passenger jarayonlari ko‘payganda eski AI/email background threadlar ham
  takrorlanishini hisobga olib, ularni tashqi yagona cron workerga ko‘chirish
  flaglari qo‘shildi. Default eski behavior saqlanadi.

## 0. Baseline va quota

Staging URLni ishlating. 17 ms ping ICMP vaqti, TTFB esa DNS/TCP/TLS, queue,
Python va DBni ham o‘z ichiga oladi. 50 ms tashqi TTFB yoki 50–200 RPS
kafolatlanmaydi. `EXPIRED` TTL tugab upstreamdan yangilashni anglatadi;
o‘zi konfiguratsiya xatosi emas. Private request uchun `BYPASS` to‘g‘ri natija.
50 ta request / 78 s o‘lchovi faqat haqiqiy concurrency, statuslar va aynan bir
endpoint bilan taqqoslansa foydali; redirect/login HTMLni muvaffaqiyat deb sanamang.

```bash
source /home/itcacade/virtualenv/lmsv1/3.10/bin/activate
cd /home/itcacade/lmsv1
python --version
python -m pip check
python scripts/benchmark_http.py https://STAGING_DOMAIN/ --requests 50 --concurrency 1 > baseline-home-c1.json
python scripts/benchmark_http.py https://STAGING_DOMAIN/ --requests 50 --concurrency 5 > baseline-home-c5.json
python scripts/benchmark_http.py https://STAGING_DOMAIN/blog/ --requests 50 --concurrency 5 > baseline-blog-c5.json
curl -sS -o /dev/null -w 'status=%{http_code} connect=%{time_connect}s tls=%{time_appconnect}s ttfb=%{time_starttransfer}s total=%{time_total}s\n' https://STAGING_DOMAIN/
```

Benchmark redirectni kuzatmaydi, faqat 2xxni successful RPSga sanaydi. Header
vaqti to‘liq header olinishigacha, aniq birinchi bayt emas; aniq TTFB uchun curl.
Har request yangi connection ochadi, shuning uchun natijani keep-alive test bilan
aralashtirmang. Uy/bosh sahifa, blog, ommaviy cache HIT, login qilingan sahifa
uchun alohida natija yozing. Dastlab 1 va 5 concurrency, keyin 10/25/50.
Backup/cron va boshqa yuklamalar vaqtini, CPU, account LVE/process/IO quota,
Passenger queue, request statuslari va cache statuslarini ham yozing.
377 GiB RAM butun serverga tegishli; cPanel hisobiga berilgan resurs bundan kam bo‘lishi mumkin.

## 1. Release va test

Oldingi release/commitni alohida saqlang. Haqiqiy `.env`ni repositoryga qo‘shmang.
Stagingda `.env`ga `DEBUG=False`, amaldagi `DJANGO_SECRET_KEY`, staging host/origin
qiymatlarini administrator kiritsin; production sirlarini test logiga chiqarmang.
Oldingi DEBUG qotirilgan edi: endi bu flag haqiqatan HTTPS/cookie sozlamalariga ta’sir qiladi.

```bash
python -m pip install -r requirements.txt
python -m pip check
python manage.py check --settings=settings.production
python manage.py check --deploy --settings=settings.production
python manage.py test accounts.test_performance config.test_public_cache blog.tests backup.tests --verbosity 2
```

Test runner alohida test DB yaratishi kerak; staging DB foydalanuvchisi ruxsatlarini
tekshiring. Unit testlarda cache alohida LocMem, production Redis tozalanmaydi.
Bu muhitda Python virtualenv yo‘llari buzilganligi sabab testlar bajarilmadi;
Nginx/Apache binary ham mavjud emas. Yuqoridagi staging tekshiruvlari majburiy.

WSGI va manage.py odatdagidek `config.settings` bilan ham ishlaydi. Ixtiyoriy
qat’iy production entry uchun cPanel Python App environment orqali
`DJANGO_SETTINGS_MODULE=settings.production` qo‘ying. `.env`ga shu modul nomini
yozishning o‘zi yetarli emas: WSGI settings modulini `.env` yuklanishidan oldin
tanlashi mumkin. Existing `passenger_wsgi.py`, `.htaccess`, host va DB yo‘llari saqlandi.
Kod/query o‘zgarishidan keyin baseline buyruqlarni takrorlab `queries-*.json`ga yozing.

Rollback: oldingi kod release va requirements lock/snapshotga qayting, shu venv
dependencylarini tiklang va cPanel Python App orqali restart qiling. Hech qanday
DB migration qo‘shilmadi, schema/data rollback kerak emas. DEBUGni productionda
Truega qaytarish tezlik rollback usuli emas.

## 2. Redis (hosting administrator yoki alohida staging Ubuntu)

Shared cPanel terminalida `sudo` bo‘lmasligi mumkin: Redis endpoint/ACLni hosting
administratoridan oling. Quyidagi buyruqlar **faqat boshqariladigan staging VMda**:

```bash
sudo apt-get update
sudo apt-get install redis-server
sudo systemctl status redis-server
```

`config/redis.conf.example`ni mavjud dedicated Redis konfiguratsiyasi bilan
birlashtiring. Avval konfiguratsiya backupini oling; umumiy Redis fayli ustidan
yozmang. Loopback bind/protected-mode, 128 MB maxmemory, noeviction namunasi
berilgan. Multi-tenant cPanelda ACL yoki private Unix socket shart; localhostning
o‘zi boshqa hosting userlardan himoya qilmaydi. Maxmemory barcha Redis DBlar
orasida umumiy: `/1` va `/2` alohida memory quota emas. Redis to‘lsa noeviction
yozishni rad etadi; memory/error monitoring va rollback kerak.
Redis restart faqat shu instancega ta’sir qilishini tekshirgach administrator bajarsin.

Staging `.env`da mavjud sirlarni saqlagan holda:

```dotenv
USE_REDIS_CACHE=true
REDIS_CACHE_URL=redis://127.0.0.1:6379/1
REDIS_SESSION_URL=redis://127.0.0.1:6379/2
REDIS_SESSIONS_ENABLED=false
CACHE_KEY_PREFIX=lms-staging-release1
LANDING_CACHE_SECONDS=60
```

ACL/password bo‘lsa haqiqiy URLni faqat private `.env`ga yozing (URL encodingni
hisobga oling). Staging/prod turli dedicated Redis namespace/ACL ishlatsin.

```bash
python manage.py check_performance_cache
python manage.py check --settings=settings.production
# Keyin cPanel Python App restart va baseline benchmarklarni takrorlang.
```

Endi `REDIS_SESSIONS_ENABLED=true` bilan yana restart qiling. Staging foydalanuvchi
bilan login/logout, ikkita browserdagi alohida account, CSRF POST, parol tiklash va
sessiya amal qilishini tekshiring. Django session migratsiyasi allaqachon mavjud
bo‘lishi kerak. Cache qayta to‘lishi/birinchi requestlar warmup vaqtini alohida o‘lchang.
Key prefixni almashtirish rate limit hisoblagichlarini ham yangidan boshlaydi;
productionda har o‘lchov uchun prefixni almashtirmang yoki cache.clear/FLUSHDB qilmang.

Rollback: avval `REDIS_SESSIONS_ENABLED=false`, zarur bo‘lsa
`USE_REDIS_CACHE=false` va app restart. DB sessionlar saqlanadi. Existing Redisni
tozalash/to‘xtatish shart emas. Redisdan LocMemga qaytish rate limitni yana
process-local qiladi; bu avvalgi holat, doimiy ko‘p-process yechim sifatida qoldirmang.

## 3. Nginx/Engintron cache

Bu repo ichidagi `.htaccess` Apache Passenger borligini ko‘rsatadi; demak eng
ehtimoliy topology Nginx/Engintron -> Apache -> Passenger. Administrator real
upstream, TLS termination va include contextni tekshirsin:

```bash
sudo nginx -t
sudo nginx -T > /root/lms-nginx-before.txt 2>&1
sudo apachectl -t
sudo passenger-status
```

`nginx -T` dumpini yopiq saqlang, ommaviy chatga yubormang. **Har qanday Nginx
tahriridan oldin** haqiqiy fayl va persistent custom include fayllarining backupi:

```bash
stamp=$(date +%Y%m%d_%H%M%S)
sudo tar -czf "/root/lms-nginx-before-$stamp.tar.gz" -C /etc nginx
# Apache/Passenger include'ining haqiqiy yo‘lini aniqlab, uni ham alohida backup qiling:
sudo cp -a /ACTUAL/PASSENGER_INCLUDE.conf "/root/lms-passenger-before-$stamp.conf"
```

Repo template fayllarini avtomatik copy qilib butun nginx.conf/vhost ustidan
yozmang. Engintron/cPanel regeneratsiyasidan saqlanadigan custom include orqali:

| Fayl | Context va qo‘llanish |
|---|---|
| `config/nginx/site.conf` | `http {}`: cache zone va bypass maplar |
| `config/nginx/public-locations.conf` | Mavjud sayt `server {}`: faqat robots/sitemap |
| `config/nginx/private-location-cache.conf` | Mavjud dynamic/private proxy location ichida cache off |

`127.0.0.1:8080` namunaviy Apache upstream, ko‘r-ko‘rona ishlatmang. Mavjud
security headerlar, TLS va proxy ishonch sozlamalarini saqlang. Nginxning ko‘p
versiyalarida location ichidagi `add_header` yuqoridan meros olingan security
headerlarni almashtiradi: shu locationlarga mavjud security include'ni qayta qo‘shing.
Cache katalogini haqiqiy Nginx worker user uchun yarating; disk quota va 64 MB
cache limiti ham umumiy disk hisobiga kiradi. Oldingi Engintron umumiy GET cache
qoidalarini **barcha boshqa dynamic locationlarda** o‘chiring/bypass qiling;
faqat yangi robots location qo‘shish eski private cache muammosini hal qilmaydi.

```bash
sudo nginx -t
# Faqat staging config test muvaffaqiyatli bo‘lgach:
sudo systemctl reload nginx
curl -sS -D - -o /dev/null https://STAGING_DOMAIN/robots.txt
curl -sS -D - -o /dev/null https://STAGING_DOMAIN/robots.txt
curl -sS -D - -o /dev/null -H 'Cookie: itc_sid=staging-test' https://STAGING_DOMAIN/robots.txt
curl -sS -D - -o /dev/null -H 'Authorization: Bearer staging-test' https://STAGING_DOMAIN/robots.txt
curl -sS -D - -o /dev/null 'https://STAGING_DOMAIN/robots.txt?test=1'
curl -sS -D - -o /dev/null https://STAGING_DOMAIN/
curl -sS -D - -o /dev/null https://STAGING_DOMAIN/login/
```

Robots cookie/query/authsiz takrorlanganda MISS -> HIT kutiladi (oldindan warm
bo‘lsa birinchi ham HIT); cookie/auth/query bilan BYPASS. Uy/login/private sahifalar
BYPASS bo‘lishi kerak. `Set-Cookie`, `Cache-Control: private/no-store`, `Vary`ni
e’tiborsiz qoldiradigan `proxy_ignore_headers` qo‘shmang. Logged-in ikki account
orasida shaxsiy ma’lumot almashmasligini browserda ham tekshiring. 5 daqiqadan
keyingi EXPIRED oddiy TTL yangilanishidir. Home uchun Nginx HIT bu o‘zgarishda
maqsad emas, uning public data cache'i DB yukini kamaytiradi.

Rollback: faqat o‘zgartirilgan config/custom includelarni backupdan qaytaring;
butun `/etc/nginx` arxivini boshqa administrator o‘zgarishlari ustidan ochmang.
`nginx -t` muvaffaqiyatli bo‘lgach reload. Private sahifalarni cache qilgan eski
configga qaytmang; xavfsiz vaqtinchalik variant dynamic cache'ni o‘chirib turish.

## 4. Passenger concurrency va background workerlar

Server RAMiga qarab yuzlab process qo‘ymang. `passenger-status`, account
CPU/process/RSS limitlari va queue orqali 2 -> 4 jarayonni stagingda sinang.
4 process template xolos: amaldagi pool 6 yoki undan katta bo‘lsa bu raqam uni
oshirmaydi. Har ilova ulushini va global pool boshqa saytlarga ta’sirini hisoblang.
`passenger_max_requests=1000` memory recycling uchun, throughput kafolati emas.
Har recycle cold start keltiradi; memory leak bo‘lmasa 0 bilan ham solishtiring.

Oldingi startup har processda template scan va AI/email thread ishga tushiradi.
Avval **stagingda** alohida yagona cron workerlarni rejalashtiring (yo‘llar stagingga
moslansin, `flock` mavjud bo‘lsin; loglarga 600 huquq/logrotate):

```cron
* * * * * cd /home/itcacade/lmsv1 && /usr/bin/flock -n /home/itcacade/lms-email.lock /home/itcacade/virtualenv/lmsv1/3.10/bin/python manage.py send_email_notifications >> /home/itcacade/lms-email.log 2>&1
*/5 * * * * cd /home/itcacade/lmsv1 && /usr/bin/flock -n /home/itcacade/lms-ai.lock /home/itcacade/virtualenv/lmsv1/3.10/bin/python manage.py check_ai_homework >> /home/itcacade/lms-ai.log 2>&1
```

Commandlarni bir marta stagingda qo‘lda sinang; AI tashqi API xarajati va test
email yuborilishi mumkin, staging recipient/API hisoblarini ishlating. So‘ng:

```dotenv
RUN_INPROCESS_WORKERS=false
RUN_STARTUP_TEMPLATE_REPAIR=false
```

Encodingni release vaqtida tekshiring; kerak bo‘lsa mavjud `fix_encoding` commandni
stagingda qo‘lda ishlating. Web-processlar qayta ishga tushgach cronlar yagona
worker bo‘lib qolganini va email/AI ishlashini tekshiring. Deploy o'tishidagi
birinchi worker ishga tushishini nazorat qiling.

Apache Passenger uchun `config/passenger.conf` (global va VirtualHost qismlari
alohida), Nginx ichida haqiqiy Passenger module bo‘lsa **faqat alternativ**
`config/passenger-nginx.conf` ishlatiladi. Nginx proxyga Passenger directive
qo‘yish mod_passenger workerlarini boshqarmaydi. .htaccessga global pool yozmang.

```bash
sudo apachectl -t
# Hosting administratori persistent cPanel include'ni tekshirib Apache reload/restart qiladi.
sudo passenger-status
python scripts/benchmark_http.py https://STAGING_DOMAIN/ --requests 50 --concurrency 10 > passenger-home-c10.json
python scripts/benchmark_http.py https://STAGING_DOMAIN/ --requests 50 --concurrency 50 > passenger-home-c50.json
```

SQLite `database is locked`, disk IO, queue yoki 5xx ortsa processlarni ko‘paytirishni
to‘xtating, oldingi poolga qayting. SQLite WAL rejimi yoki DB migratsiyasi avtomatik
qo‘shilmadi. Backupni 02:00 da qoldiring, load testni backup bilan bir vaqtda qilmang.

Rollback: oldingi pool/min/max-requests qiymatlarini config backupdan tiklang,
syntax check va administrator restart. Cron worker yo‘lidan qaytish kerak bo‘lsa,
avval shu yangi cronlarni o‘chirib faol ishlar tugashini kuting, keyin
`RUN_INPROCESS_WORKERS=true` va restart; ikki turini birga qoldirmang.

## 5. Query profiling va qabul mezoni

Private, tashqi tarmoqdan yopiq stagingda:

```bash
python -m pip install -r requirements-dev.txt
# Faqat shu lokal private staging process uchun, production .envni almashtirmasdan:
DEBUG=True DJANGO_SETTINGS_MODULE=settings.staging_debug python manage.py runserver 127.0.0.1:8000 --noreload
```

SSH tunnel orqali localhostda oching. Toolbar SQL panelida endpointlar bo‘yicha
query count, takroriy query va vaqtni yozing. Productionda toolbar/DEBUG yoqilmang.
Toolbar profiling bilan olingan latencyni release benchmarkga aralashtirmang.
Real sekin SQLni `QuerySet.explain()` orqali stagingda tekshiring; dalilsiz indeks
yoki butun bazaga prefetch qo‘shmang.

Har bosqichdan keyin bir xil URL, bir xil request/concurrency, warmup, mijoz
joylashuvi va statuslar bilan JSON natijalarni taqqoslang. 2xx successful RPS,
p50/p95 header latency, curl TTFB, 5xx/timeout, CPU/RSS/IO va Passenger queue
qayd etilsin. Cached public endpointdagi RPS authenticated Django RPS o‘rnini bosmaydi.
Stagingda barcha funksional testlar o‘tsa, cross-user cache yo‘q bo‘lsa va xatolar
ko‘paymasdan o‘lchangan yaxshilanish bo‘lsa release ko‘rib chiqiladi. Hozircha
50 ms yoki 50–200 RPS erishildi degan da’vo yo‘q; natijaga qarab keyingi
bottleneck optimallashtiriladi, productionda cheksiz load test qilinmaydi.

Manbalar: [Django sessions](https://docs.djangoproject.com/en/5.1/topics/http/sessions/),
[django-redis](https://github.com/jazzband/django-redis),
[Nginx proxy cache](https://nginx.org/en/docs/http/ngx_http_proxy_module.html),
[Passenger Apache](https://www.phusionpassenger.com/docs/references/config_reference/apache/),
[Passenger Nginx](https://www.phusionpassenger.com/docs/references/config_reference/nginx/),
[Redis configuration](https://redis.io/docs/latest/operate/oss_and_stack/management/config/),
[Debug Toolbar](https://django-debug-toolbar.readthedocs.io/en/stable/installation.html).
