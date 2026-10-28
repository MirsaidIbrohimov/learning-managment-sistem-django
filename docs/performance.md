# Django tezligi: stagingda tekşiriş va bosqichma-bosqich yoqiş

Bu fayllar loyiha içida tayyorlandi; productionga ulanilmadi, Redis örnatilmadi,
Nginx/Apache qayta yuklanmadi va yuklama testi yuborilmadi. Avval staging.
Asl DB SQLite bölib qoladi, backup ham uni qöllaydi. 100+ MB DB hajmi
özi RPS sababini aniqlamaydi: query, write lock, process quota va queue muhim.

## Nima özgardi

- `config/settings.py`: DEBUG endi `.env`dan, default False. Redis default öçiq;
  DB session mavjud, istalsa Redis `cached_db` yoqiladi. `settings/production.py`
  mavjud sozlamalarni import qiladi, DEBUG=True bölsa işga tuşişni rad etadi.
- Landing HTML umumiy cache qilinmaydi: unda CSRF forma, şaxsiy kabinet va
  session bor. Faqat ommaviy kurslar/postlar/statistika 60 soniyaga cache qilinadi.
  Yangilanish/bloklash şu TTLgacha keç körinişi mumkin. `LANDING_CACHE_SECONDS=0`
  buni öçiradi; TTLni özgartirganda eski kalitni öçiriş yoki muddati tugaşini kutiş kerak.
- Blog sahifasida author join va like/comment count aggregation qöşildi;
  izohlar user bilan bitta queryda keladi. Dashboard kurs ustozlari batch
  prefetch qilinadi; har enrollment uçun `.first()` querysi olib taşlandi.
- `cache_page` faqat `robots.txt` va `sitemap.xml`ga qöyildi. Şaxsiy kabinet,
  login, ariza, tölov, API va CSRF sahifalarini umumiy cache qiliş mumkin emas.
- Redis default cache rate limit uçun ham işlatiladi: xatolar jim yaşirilmaydi.
  Redis işlamasa şu cachega boğliq requestlar 500 berişi mumkin; tez rollback bor.
  Sessiya `cached_db` bölgani uçun DBda saqlanadi, Redis tozalansa login yöqolmaydi.
- Passenger jarayonlari köpayganda eski AI/email background threadlar ham
  takrorlanişini hisobga olib, ularni taşqi yagona cron workerga köçiriş
  flaglari qöşildi. Default eski behavior saqlanadi.

## 0. Baseline va quota

Staging URLni işlating. 17 ms ping ICMP vaqti, TTFB esa DNS/TCP/TLS, queue,
Python va DBni ham öz içiga oladi. 50 ms taşqi TTFB yoki 50–200 RPS
kafolatlanmaydi. `EXPIRED` TTL tugab upstreamdan yangilaşni anglatadi;
özi konfiguratsiya xatosi emas. Private request uçun `BYPASS` töğri natija.
50 ta request / 78 s ölçovi faqat haqiqiy concurrency, statuslar va aynan bir
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
vaqti töliq header olinişigaça, aniq birinçi bayt emas; aniq TTFB uçun curl.
Har request yangi connection oçadi, şuning uçun natijani keep-alive test bilan
aralaştirmang. Uy/bosh sahifa, blog, ommaviy cache HIT, login qilingan sahifa
uçun alohida natija yozing. Dastlab 1 va 5 concurrency, keyin 10/25/50.
Backup/cron va boşqa yuklamalar vaqtini, CPU, account LVE/process/IO quota,
Passenger queue, request statuslari va cache statuslarini ham yozing.
377 GiB RAM butun serverga tegişli; cPanel hisobiga berilgan resurs bundan kam bölişi mumkin.

## 1. Release va test

Oldingi release/commitni alohida saqlang. Haqiqiy `.env`ni repositoryga qöşmang.
Stagingda `.env`ga `DEBUG=False`, amaldagi `DJANGO_SECRET_KEY`, staging host/origin
qiymatlarini administrator kiritsin; production sirlarini test logiga çiqarmang.
Oldingi DEBUG qotirilgan edi: endi bu flag haqiqatan HTTPS/cookie sozlamalariga ta’sir qiladi.

```bash
python -m pip install -r requirements.txt
python -m pip check
python manage.py check --settings=settings.production
python manage.py check --deploy --settings=settings.production
python manage.py test accounts.test_performance config.test_public_cache blog.tests backup.tests telegram_bot.test_startup --verbosity 2
```

Test runner alohida test DB yaratişi kerak; staging DB foydalanuvçisi ruxsatlarini
tekşiring. Unit testlarda cache alohida LocMem, production Redis tozalanmaydi.
`manage.py test` production `.env`da Redis yoqilgan bölsa ham uni işlatmaydi;
haqiqiy Redis integratsiyasini alohida `check_performance_cache` bilan tekşiring.
Test/backup/cache-diagnostika buyruqlari bot webhook/pollingni boşlamaydi.
`robots_txt` cache testi xato bersa `config/views.py`ning ham yangi `cache_page`
dekoratorlari bilan serverga köçganini tekşiring; faqat test faylini köçiriş yetmaydi.
Bu muhitda Python virtualenv yöllari buzilganligi sabab testlar bajarilmadi;
Nginx/Apache binary ham mavjud emas. Yuqoridagi staging tekşiruvlari majburiy.

WSGI va manage.py odatdagidek `config.settings` bilan ham işlaydi. Ixtiyoriy
qat’iy production entry uçun cPanel Python App environment orqali
`DJANGO_SETTINGS_MODULE=settings.production` qöying. `.env`ga şu modul nomini
yozişning özi yetarli emas: WSGI settings modulini `.env` yuklanişidan oldin
tanlaşi mumkin. Existing `passenger_wsgi.py`, `.htaccess`, host va DB yöllari saqlandi.
Kod/query özgarişidan keyin baseline buyruqlarni takrorlab `queries-*.json`ga yozing.

Rollback: oldingi kod release va requirements lock/snapshotga qayting, şu venv
dependencylarini tiklang va cPanel Python App orqali restart qiling. Heç qanday
DB migration qöşilmadi, schema/data rollback kerak emas. DEBUGni productionda
Truega qaytariş tezlik rollback usuli emas.

## 2. Redis (hosting administrator yoki alohida staging Ubuntu)

Shared cPanel terminalida `sudo` bölmasligi mumkin: Redis endpoint/ACLni hosting
administratoridan oling. Quyidagi buyruqlar **faqat boşqariladigan staging VMda**:

```bash
sudo apt-get update
sudo apt-get install redis-server
sudo systemctl status redis-server
```

`config/redis.conf.example`ni mavjud dedicated Redis konfiguratsiyasi bilan
birlaştiring. Avval konfiguratsiya backupini oling; umumiy Redis fayli ustidan
yozmang. Loopback bind/protected-mode, 128 MB maxmemory, noeviction namunasi
berilgan. Multi-tenant cPanelda ACL yoki private Unix socket şart; localhostning
özi boşqa hosting userlardan himoya qilmaydi. Maxmemory barça Redis DBlar
orasida umumiy: `/1` va `/2` alohida memory quota emas. Redis tölsa noeviction
yozişni rad etadi; memory/error monitoring va rollback kerak.
Redis restart faqat şu instancega ta’sir qilişini tekşirgaç administrator bajarsin.

Staging `.env`da mavjud sirlarni saqlagan holda:

```dotenv
USE_REDIS_CACHE=true
REDIS_CACHE_URL=redis://127.0.0.1:6379/1
REDIS_SESSION_URL=redis://127.0.0.1:6379/2
REDIS_SESSIONS_ENABLED=false
CACHE_KEY_PREFIX=lms-staging-release1
LANDING_CACHE_SECONDS=60
```

ACL/password bölsa haqiqiy URLni faqat private `.env`ga yozing (URL encodingni
hisobga oling). Staging/prod turli dedicated Redis namespace/ACL işlatsin.

```bash
python manage.py check_performance_cache
python manage.py check --settings=settings.production
# Keyin cPanel Python App restart va baseline benchmarklarni takrorlang.
```

Endi `REDIS_SESSIONS_ENABLED=true` bilan yana restart qiling. Staging foydalanuvçi
bilan login/logout, ikkita browserdagi alohida account, CSRF POST, parol tiklaş va
sessiya amal qilişini tekşiring. Django session migratsiyasi allaqaçon mavjud
bölişi kerak. Cache qayta tölishi/birinchi requestlar warmup vaqtini alohida ölçang.
Key prefixni almaştiriş rate limit hisoblagiçlarini ham yangidan boşlaydi;
productionda har ölçov uçun prefixni almaştirmang yoki cache.clear/FLUSHDB qilmang.

Rollback: avval `REDIS_SESSIONS_ENABLED=false`, zarur bölsa
`USE_REDIS_CACHE=false` va app restart. DB sessionlar saqlanadi. Existing Redisni
tozalash/töxtatish şart emas. Redisdan LocMemga qaytiş rate limitni yana
process-local qiladi; bu avvalgi holat, doimiy köp-process yeçim sifatida qoldirmang.

## 3. Nginx/Engintron cache

Bu repo içidagi `.htaccess` Apache Passenger borligini körsatadi; demak eng
ehtimoliy topology Nginx/Engintron -> Apache -> Passenger. Administrator real
upstream, TLS termination va include contextni tekşirsin:

```bash
sudo nginx -t
sudo nginx -T > /root/lms-nginx-before.txt 2>&1
sudo apachectl -t
sudo passenger-status
```

`nginx -T` dumpini yopiq saqlang, ommaviy çatga yubormang. **Har qanday Nginx
tahriridan oldin** haqiqiy fayl va persistent custom include fayllarining backupi:

```bash
stamp=$(date +%Y%m%d_%H%M%S)
sudo tar -czf "/root/lms-nginx-before-$stamp.tar.gz" -C /etc nginx
# Apache/Passenger include'ining haqiqiy yo‘lini aniqlab, uni ham alohida backup qiling:
sudo cp -a /ACTUAL/PASSENGER_INCLUDE.conf "/root/lms-passenger-before-$stamp.conf"
```

Repo template fayllarini avtomatik copy qilib butun nginx.conf/vhost ustidan
yozmang. Engintron/cPanel regeneratsiyasidan saqlanadigan custom include orqali:

| Fayl | Context va qöllaniş |
|---|---|
| `config/nginx/site.conf` | `http {}`: cache zone va bypass maplar |
| `config/nginx/public-locations.conf` | Mavjud sayt `server {}`: faqat robots/sitemap |
| `config/nginx/private-location-cache.conf` | Mavjud dynamic/private proxy location içida cache off |

`127.0.0.1:8080` namunaviy Apache upstream, kör-körona işlatmang. Mavjud
security headerlar, TLS va proxy işonç sozlamalarini saqlang. Nginxning köp
versiyalarida location içidagi `add_header` yuqoridan meros olingan security
headerlarni almaştiradi: şu locationlarga mavjud security include'ni qayta qöşing.
Cache katalogini haqiqiy Nginx worker user uçun yarating; disk quota va 64 MB
cache limiti ham umumiy disk hisobiga kiradi. Oldingi Engintron umumiy GET cache
qoidalarini **barça boşqa dynamic locationlarda** öchiring/bypass qiling;
faqat yangi robots location qöşiş eski private cache muammosini hal qilmaydi.

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
bölsa birinçi ham HIT); cookie/auth/query bilan BYPASS. Uy/login/private sahifalar
BYPASS bölişi kerak. `Set-Cookie`, `Cache-Control: private/no-store`, `Vary`ni
e’tiborsiz qoldiradigan `proxy_ignore_headers` qöşmang. Logged-in ikki account
orasida şaxsiy ma’lumot almaşmasligini browserda ham tekşiring. 5 daqiqadan
keyingi EXPIRED oddiy TTL yangilanişidir. Home uçun Nginx HIT bu özgarişda
maqsad emas, uning public data cache'i DB yukini kamaytiradi.

Rollback: faqat özgartirilgan config/custom includelarni backupdan qaytaring;
butun `/etc/nginx` arxivini boşqa administrator özgarişlari ustidan oçmang.
`nginx -t` muvaffaqiyatli bölgaç reload. Private sahifalarni cache qilgan eski
configga qaytmang; xavfsiz vaqtinçalik variant dynamic cache'ni öçirib turiş.

## 4. Passenger concurrency va background workerlar

Server RAMiga qarab yuzlab process qöymang. `passenger-status`, account
CPU/process/RSS limitlari va queue orqali 2 -> 4 jarayonni stagingda sinang.
4 process template xolos: amaldagi pool 6 yoki undan katta bölsa bu raqam uni
oşirmaydi. Har ilova uluşini va global pool boşqa saytlarga ta’sirini hisoblang.
`passenger_max_requests=1000` memory recycling uçun, throughput kafolati emas.
Har recycle cold start keltiradi; memory leak bölmasa 0 bilan ham soliştiring.

Oldingi startup har processda template scan va AI/email thread işga tuşiradi.
Avval **stagingda** alohida yagona cron workerlarni rejalaştiring (yöllar stagingga
moslansin, `flock` mavjud bölsin; loglarga 600 huquq/logrotate):

```cron
* * * * * cd /home/itcacade/lmsv1 && /usr/bin/flock -n /home/itcacade/lms-email.lock /home/itcacade/virtualenv/lmsv1/3.10/bin/python manage.py send_email_notifications >> /home/itcacade/lms-email.log 2>&1
*/5 * * * * cd /home/itcacade/lmsv1 && /usr/bin/flock -n /home/itcacade/lms-ai.lock /home/itcacade/virtualenv/lmsv1/3.10/bin/python manage.py check_ai_homework >> /home/itcacade/lms-ai.log 2>&1
```

Commandlarni bir marta stagingda qölda sinang; AI taşqi API xarajati va test
email yuborilişi mumkin, staging recipient/API hisoblarini işlating. Söng:

```dotenv
RUN_INPROCESS_WORKERS=false
RUN_STARTUP_TEMPLATE_REPAIR=false
```

Encodingni release vaqtida tekşiring; kerak bölsa mavjud `fix_encoding` commandni
stagingda qölda işlating. Web-processlar qayta işga tuşgaç cronlar yagona
worker bölib qolganini va email/AI işlaşini tekşiring. Deploy ötişidagi
birinçi worker işga tuşişini nazorat qiling.

Apache Passenger uçun `config/passenger.conf` (global va VirtualHost qismlari
alohida), Nginx içida haqiqiy Passenger module bölsa **faqat alternativ**
`config/passenger-nginx.conf` işlatiladi. Nginx proxyga Passenger directive
qöyiş mod_passenger workerlarini boşqarmaydi. .htaccessga global pool yozmang.

```bash
sudo apachectl -t
# Hosting administratori persistent cPanel include'ni tekshirib Apache reload/restart qiladi.
sudo passenger-status
python scripts/benchmark_http.py https://STAGING_DOMAIN/ --requests 50 --concurrency 10 > passenger-home-c10.json
python scripts/benchmark_http.py https://STAGING_DOMAIN/ --requests 50 --concurrency 50 > passenger-home-c50.json
```

SQLite `database is locked`, disk IO, queue yoki 5xx ortsa processlarni köpaytirişni
töxtating, oldingi poolga qayting. SQLite WAL rejimi yoki DB migratsiyasi avtomatik
qöşilmadi. Backupni 02:00 da qoldiring, load testni backup bilan bir vaqtda qilmang.

Rollback: oldingi pool/min/max-requests qiymatlarini config backupdan tiklang,
syntax check va administrator restart. Cron worker yölidan qaytiş kerak bölsa,
avval şu yangi cronlarni öçirib faol işlar tugaşini kuting, keyin
`RUN_INPROCESS_WORKERS=true` va restart; ikki turini birga qoldirmang.

## 5. Query profiling va qabul mezoni

Private, taşqi tarmoqdan yopiq stagingda:

```bash
python -m pip install -r requirements-dev.txt
# Faqat shu lokal private staging process uchun, production .envni almashtirmasdan:
DEBUG=True DJANGO_SETTINGS_MODULE=settings.staging_debug python manage.py runserver 127.0.0.1:8000 --noreload
```

SSH tunnel orqali localhostda oçing. Toolbar SQL panelida endpointlar böyiça
query count, takroriy query va vaqtni yozing. Productionda toolbar/DEBUG yoqilmang.
Toolbar profiling bilan olingan latencyni release benchmarkga aralaştirmang.
Real sekin SQLni `QuerySet.explain()` orqali stagingda tekşiring; dalilsiz indeks
yoki butun bazaga prefetch qöşmang.

Har bosqiçdan keyin bir xil URL, bir xil request/concurrency, warmup, mijoz
joylaşuvi va statuslar bilan JSON natijalarni taqqoslang. 2xx successful RPS,
p50/p95 header latency, curl TTFB, 5xx/timeout, CPU/RSS/IO va Passenger queue
qayd etilsin. Cached public endpointdagi RPS authenticated Django RPS örnini bosmaydi.
Stagingda barça funksional testlar ötsa, cross-user cache yöq bölsa va xatolar
köpaymasdan ölçangan yaxşilaniş bölsa release körib çiqiladi. Hozirça
50 ms yoki 50–200 RPS erişildi degan da’vo yöq; natijaga qarab keyingi
bottleneck optimallaştiriladi, productionda çeksiz load test qilinmaydi.

Manbalar: [Django sessions](https://docs.djangoproject.com/en/5.1/topics/http/sessions/),
[django-redis](https://github.com/jazzband/django-redis),
[Nginx proxy cache](https://nginx.org/en/docs/http/ngx_http_proxy_module.html),
[Passenger Apache](https://www.phusionpassenger.com/docs/references/config_reference/apache/),
[Passenger Nginx](https://www.phusionpassenger.com/docs/references/config_reference/nginx/),
[Redis configuration](https://redis.io/docs/latest/operate/oss_and_stack/management/config/),
[Debug Toolbar](https://django-debug-toolbar.readthedocs.io/en/stable/installation.html).
