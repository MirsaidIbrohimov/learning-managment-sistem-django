# MY StartUp — LMS uchun startup platformasi moduli

## Context

IT Shaharcha Zomin LMS'ga (`Django 5.2`, SQLite, cPanel/Passenger) yangi `startup/` app
qo'shiladi. Maqsad: o'quvchi LMS ichida real startup yuritsin — IDEA'dan FUNDING'gacha
10 bosqichli roadmap, jamoa yig'ish, task topshirish, mentor tasdiqlashi, XP, leaderboard,
moliya va pitch deck.

Mavjud LMS to'liq ishlab turgan production tizim (70+ model, 269 URL, 13 middleware),
shuning uchun asosiy talab — **hech qanday regressiya bo'lmasligi**: `CustomUser`
o'zgarmaydi, mavjud URL/template/CSS buzilmaydi, migratsiya faqat yangi jadvallarni
yaratadi.

### Tahlil xulosasi (mavjud arxitektura)

| Soha | Holat |
|---|---|
| Django / DB | 5.2.10, SQLite (`db.sqlite3`), `DEFAULT_AUTO_FIELD=BigAutoField` |
| User | `accounts.CustomUser(AbstractUser)`, `role` ∈ `admin / assistant_admin / teacher / student`. **Mentor roli yo'q** |
| Rol tekshiruvi | Dekorator YO'Q — view ichida `@login_required` + `request.user.role` / `user.is_admin` propertylari |
| Object-level perm | `quiz/permissions.py` — oddiy funksiyalar (`can_access_quiz(user, quiz)`); DRF uchun `api/permissions.py` BasePermission klasslari |
| Gamifikatsiya | `CustomUser.coins` + `CustomUser.add_coins()/remove_coins()/try_spend_coins()` — atomik `F()` UPDATE, `coin.CoinTransaction` yozadi. Dashboard "XP" deb `user.coins`ni ko'rsatadi |
| Yutuq naqshi | `games.UserAchievement` — ta'rif kodda, DB faqat `code` saqlaydi, `unique_together` |
| Notification | `accounts.notifications.send_notification(user, title, content, message_type)` → `accounts.Message` |
| Task/submit naqshi | `accounts.Homework` + `HomeworkSubmission` (status choices, `graded_by`, `coin_awarded` flag, `UniqueConstraint`) |
| App strukturasi | `services.py`/`signals.py` YO'Q; FBV + `@login_required`; template'lar `<app>/templates/<app>/` ichida |
| URL | Har app'da `app_name` (faqat `accounts`da yo'q); `config/urls.py` da `include()` |
| Frontend | **Bootstrap 5.3.2 + Bootstrap Icons** (Tailwind emas). Base: `accounts/templates/accounts/base.html`, bloklar: `title`, `extra_css`, `content`, `extra_js` |
| Dizayn tokenlari | `static/css/base.css` `:root` — `--card --border --text --text-muted --primary --success --warning --danger`; dark mode `[data-theme="dark"]` + `localStorage.theme` |
| Navigatsiya | Sidebar emas, navbar (`nb-*` klasslar). Menyu **4 joyda** takrorlanadi |
| Admin | Jazzmin, `@admin.register` + `list_display/list_filter/search_fields` |
| DRF | `APIView` + `.as_view()` (ViewSet/router emas), `app_name='api'`, prefix `/api/v1/` |
| Test | `django.test.TestCase` / `APIClient`, `*/tests.py` |

### Tasdiqlangan qarorlar

1. **Mentor** = mavjud `teacher`/`admin` roli + `StartupMentor` biriktirish modeli. `CustomUser` TEGILMAYDI.
2. **XP** = `StartupXPTransaction` (startup hisobi, leaderboard uchun) **+** task tasdiqlanganda o'quvchiga `user.add_coins()` orqali LMS coin.
3. **Render** = server-render (Django context) + kichik DRF qatlam (leaderboard filtri, metrics chart).
4. **Ko'lam** = 1-bosqichda ishlaydigan yadro; mentor paneli / finance UI / metrics / pitch / achievements UI / DRF API — 2-bosqich.

### Aniqlangan ikki tuzoq (integratsiya xavfi)

1. **`SectionBlockMiddleware`** (`accounts/middleware.py:338`) URL nomini **substring** bo'yicha bloklaydi:
   `'leaderboard' in url_name` → "reyting" bo'limi bloklanganda ishlamaydi. Shuning uchun startup URL nomlarida
   `leaderboard, rating, profile, homework, messages, settings, devices, help, books` **substring'lari ishlatilmaydi**
   (leaderboard → `top`).
2. **`DeviceLimitMiddleware`** testlarda `force_login()`ni yetarli deb hisoblamaydi — `UserSession` qatori shart
   (`quiz/tests.py:1053` `_login()` helper naqshi ko'chiriladi). `ProfileCompletionMiddleware` sababli test
   userlari `is_profile_completed=True` + `birth_date` bilan yaratiladi.

---

## 1-bosqich: Ishlaydigan yadro

### 1.1 App skeleti

Yangi `startup/` app: `__init__.py`, `apps.py` (`StartupConfig`, `default_auto_field=BigAutoField`),
`models.py`, `admin.py`, `forms.py`, `permissions.py`, `services.py`, `urls.py`, `views.py`,
`tests.py`, `migrations/`, `templates/startup/`, `static/startup/css/startup.css`.

`config/settings.py` → `INSTALLED_APPS`ga `'startup'` (ro'yxat oxiriga, alifbo tartibida
`quiz`dan keyin). `config/urls.py` → `path('startup/', include('startup.urls'))`
**`path('', include('accounts.urls'))`dan oldin** (accounts'da catch-all yo'q, lekin tartib xavfsizroq).

### 1.2 Modellar (`startup/models.py`)

Barcha 13 model **1-bosqichda** yaratiladi — production'da (cPanel) bir marta migratsiya
qilish uchun. UI'si 2-bosqichda bo'lgan modellar 1-kundan Django admin orqali boshqariladi
(spec #15 talabi).

Konvensiya: `verbose_name` uzbekcha, `created_at/updated_at`, `__str__`, `Meta.indexes`.

| Model | Asosiy maydonlar | Muhim jihat |
|---|---|---|
| `Startup` | `name, slug, logo, owner→CustomUser, short_description, description, problem, solution, target_audience, category, business_model, competitors, website, github_url, telegram_url, instagram_url, current_stage, progress, status, total_xp, profession→Profession(null)` | `UniqueConstraint(owner, condition=Q(status='active'))` — MVP'da 1 aktiv startup, kelajakda ko'p startup uchun ochiq. `total_xp` denormalizatsiya (leaderboard `annotate`siz). `profession` = "My Academy" filtri (mavjud model reuse) |
| `StageTemplate` | `key, title, order, weight, is_active` | Global roadmap shabloni — progress hard-code emas, admin tahrirlaydi |
| `TaskTemplate` | `stage_template→StageTemplate, title, description, priority, points, order, is_active` | |
| `StartupStage` | `startup, key, title, order, weight, is_completed, completed_at` | `unique_together(startup, key)`. Startup yaratilganda shablondan nusxalanadi |
| `StartupTask` | `startup, stage, title, description, assigned_to(null), created_by(null), deadline, status, priority, points, attachment, source_template(null), created_at, completed_at` | `status`: `TODO/IN_PROGRESS/SUBMITTED/APPROVED/REJECTED/COMPLETED`. Index `(startup,status)`, `(assigned_to,status)` |
| `StartupTaskSubmission` | `task, submitted_by, description, file, link, github_url, demo_url, status, reviewed_by(null), reviewed_at, review_comment, submitted_at` | `HomeworkSubmission` naqshi |
| `StartupMember` | `startup, user, role, status, invited_by(null), joined_at` | `unique_together(startup, user)`. `status`: `pending/active/rejected/left`. `invited_by` invite'ni join-request'dan ajratadi |
| `StartupMentor` | `startup, mentor, assigned_at, is_active` | `unique_together(startup, mentor)` |
| `StartupXPTransaction` | `startup, user(null), amount, reason, description, dedupe_key, created_at` | **`dedupe_key` unique** → XP ikki marta berilmaydi (`task:<id>:approved`) |
| `StartupFeedback` | `startup, mentor, task(null), message, rating(1-5), created_at` | `MinValue/MaxValueValidator` |
| `StartupFinance` | `startup, type(REVENUE/EXPENSE), amount(Decimal 14,0), description, date, created_by, created_at` | UZS — `PaymentStatus.monthly_fee` naqshi (`decimal_places=0`) |
| `StartupMetric` | `startup, key, value, date, note, created_by` | Index `(startup, key, -date)` |
| `StartupAchievement` | `startup, code, unlocked_at` | `unique_together(startup, code)` — `games.UserAchievement` naqshi |
| `StartupActivity` | `startup, user(null), action_type, description, created_at` | `coin.ActivityLog` naqshi — audit/analytics |
| `PitchDeck` | `startup(OneToOne)` + 10 matn bo'limi (`problem … investment_ask`), `updated_at` | PDF eksport uchun tayyor struktura |

Kategoriyalar (`AI, EdTech, FinTech, AgriTech, HealthTech, E-commerce, Cyber Security, SaaS, Mobile, Web, Other`)
va bosqichlar (`IDEA … FUNDING`) modul darajasidagi `CHOICES` konstantalari.

### 1.3 `startup/permissions.py` — oddiy funksiyalar (`quiz/permissions.py` naqshi)

```
get_active_startup(user)          member_of(user, startup) -> StartupMember | None
is_owner(user, startup)           is_active_member(user, startup)
is_mentor_of(user, startup)       is_staff_admin(user)      # admin | assistant_admin
can_view_startup(user, startup)   # ochiq karta: nom, logo, tavsif, stage, progress, jamoa
can_view_private(user, startup)   # tasklar, moliya, metrics, feedback, pitch
can_edit_startup(user, startup)   # owner | admin
can_manage_tasks(user, startup)   # owner | mentor | admin
can_submit_task(user, task)       # assigned_to | aktiv a'zo
can_review_submission(user, startup)  # mentor | admin — OWNER EMAS
```

**Xavfsizlik yadrosi:** `can_review_submission` egani ataylab chiqarib tashlaydi — aks holda
o'quvchi o'z taskini o'zi tasdiqlab cheksiz XP/coin yig'adi. Ruxsat yo'q bo'lsa
`PermissionDenied` → mavjud `templates/403.html`.

### 1.4 `startup/services.py` — biznes logika (view'lar yupqa qoladi)

- `create_startup(owner, form_data)` — `transaction.atomic`: Startup + `seed_roadmap()` + `+100 XP` + `StartupMember(founder, active)` + activity + notification
- `seed_roadmap(startup)` — `StageTemplate`/`TaskTemplate` → `StartupStage`/`StartupTask`
- `recompute_progress(startup)` — bajarilgan task `points` / umumiy `points`, bosqich `weight` bilan tortilgan; `current_stage`ni eng oldingi tugallanmagan bosqichga suradi; `progress` + `current_stage` saqlanadi
- `award_xp(startup, amount, reason, dedupe_key, user=None)` — `dedupe_key` unique bo'lgani uchun idempotent; `total_xp`ni `F()` bilan oshiradi; `user` berilsa `user.add_coins()`
- `submit_task(task, user, payload)` / `review_submission(submission, reviewer, action, comment)` — approve → task `COMPLETED` + XP + progress + achievement + notification
- `request_join / invite_member / respond_to_membership`
- `check_achievements(startup)` — kodlar: `first_idea, team_builder, mvp_builder, ten_tasks, first_customer, first_revenue, top_startup`
- `log_activity(startup, user, action_type, description)`
- `finance_summary(startup)` — `Sum` bilan revenue/expense/profit
- `leaderboard_queryset(period, profession)` — `select_related('owner','profession')` + `annotate(Count('members'))`, `-total_xp`

### 1.5 URL'lar (`startup/urls.py`, `app_name = 'startup'`, prefix `/startup/`)

```
''                                    dashboard      # startup bo'lsa panel, bo'lmasa bo'sh holat
'create/'                             create
'explore/'                            explore        # barcha startuplar, paginated
'top/'                                top            # leaderboard (nom ataylab 'top')
'<slug:slug>/'                        detail
'<slug:slug>/edit/'                   edit
'<slug:slug>/roadmap/'                roadmap
'<slug:slug>/tasks/'                  task_list
'<slug:slug>/tasks/<int:pk>/'         task_detail
'<slug:slug>/tasks/<int:pk>/submit/'  task_submit     # POST
'<slug:slug>/tasks/<int:pk>/review/'  task_review     # POST, mentor|admin
'<slug:slug>/team/'                   team
'<slug:slug>/team/join/'              team_join       # POST
'<slug:slug>/team/<int:pk>/respond/'  team_respond    # POST, owner
```

Barcha o'zgartiruvchi amallar `@require_POST` + CSRF (Django default) + object-level tekshiruv.
`slug` ishlatiladi (ketma-ket ID enumeratsiyasi emas), lekin ruxsat baribar har so'rovda tekshiriladi.

### 1.6 Template'lar (`startup/templates/startup/`)

`accounts/base.html`dan `{% extends %}`, Bootstrap 5 + `bi-*` ikonkalar, `startup.css`
faqat `--card/--border/--text/--primary` tokenlaridan foydalanadi → dark mode avtomatik ishlaydi.

`dashboard.html` (progress ring, stage, XP, jamoa, coin, joriy tasklar, deadline'lar, faollik),
`empty.html` (startup yo'q holati + "Startup yaratish"), `create.html`, `edit.html`,
`detail.html`, `roadmap.html`, `tasks.html`, `task_detail.html`, `team.html`, `top.html`,
`explore.html`, `_card.html`/`_progress.html` (qayta ishlatiladigan bo'laklar).

### 1.7 Navbar integratsiyasi — `accounts/templates/accounts/base.html`, 4 nuqta

| Joy | Satr | Nima qo'shiladi |
|---|---|---|
| Desktop `nb-links` | ~547 | `<a class="nb-link">🚀 MY StartUp` (talaba/o'qituvchi uchun) |
| User dropdown `<ul>` | ~664 | `dropdown-item` + `dd-icon` |
| Mobil slide panel | ~730 | `nb-mobile-link` |
| Mobil offcanvas grid | ~1237 | `mob-menu-item` + `mob-menu-icon` |

Active holat mavjud naqsh bilan: `{% if request.resolver_match.app_names and 'startup' in request.resolver_match.app_names %}active{% endif %}`.
Startup bor/yo'qligini ko'rsatish uchun `startup/context_processors.py` → `my_startup`
(`TEMPLATES.OPTIONS.context_processors`ga qo'shiladi, mavjud `accounts.context_processors.*` yonida;
so'rov soni: bitta `select_related` query, faqat autentifikatsiyalangan foydalanuvchi uchun).

### 1.8 Admin (`startup/admin.py`)

13 model uchun `@admin.register`, `list_display/list_filter/search_fields/readonly_fields`,
`StartupMemberInline` + `StartupTaskInline`, `autocomplete_fields` (N+1 oldini olish uchun
`list_select_related`). Jazzmin ikonkalari `JAZZMIN_SETTINGS['icons']`ga qo'shiladi.

### 1.9 Seed (`startup/management/commands/seed_startup_roadmap.py`)

Idempotent (`update_or_create`) — 10 bosqich va spec'dagi task shablonlari (IDEA, VALIDATION,
CUSTOMER_DISCOVERY, BUSINESS_MODEL, PROTOTYPE, MVP, LAUNCH, REVENUE, GROWTH, FUNDING).
Data-migration emas: qayta ishga tushirish xavfsiz va admin keyin tahrirlashi mumkin.

### 1.10 Testlar (`startup/tests.py`)

`TestCase` + `_login()` helper (`force_login` + `UserSession`, `quiz/tests.py:1053` naqshi):

- `StartupCreationTests` — yaratish, slug unikalligi, 1 aktiv startup cheklovi, roadmap seed, +100 XP
- `PermissionTests` — a'zo bo'lmagan `tasks/` → 403; egasi bo'lmagan `edit/` → 403; noto'g'ri slug → 404; **egasi o'z submission'ini tasdiqlay olmaydi**
- `TeamTests` — join request, accept/reject, takroriy request
- `TaskFlowTests` — submit → mentor approve → XP + coin + progress
- `XPDedupeTests` — ikki marta approve → bitta XP qatori, coin bir marta
- `ProgressTests` — 0 → 100%, stage avtomatik suriladi
- `LeaderboardTests` — `-total_xp` tartibi, pagination
- `FinanceTests` — revenue − expense = profit

---

## 2-bosqich (yadro tasdiqlangandan keyin)

Mentor dashboard'i, finance UI, metrics + Chart.js, pitch deck sahifasi (+PDF eksport),
achievements UI, DRF API (`/api/v1/startup/...` — `APIView` + `api/permissions.py` reuse),
`SectionBlockMiddleware.BLOCKED_PATTERNS`ga `'startup'` bo'limini qo'shish, Telegram bildirishnomalari.

---

## Tekshirish (verification)

```bash
venv/Scripts/python.exe manage.py check
venv/Scripts/python.exe manage.py makemigrations startup
venv/Scripts/python.exe manage.py migrate
venv/Scripts/python.exe manage.py seed_startup_roadmap
venv/Scripts/python.exe manage.py test startup      # yangi modul
venv/Scripts/python.exe manage.py test accounts quiz # regressiya yo'qligini tasdiqlash
```

Brauzerda (memory'dagi retsept: Chrome + CDP, Playwright bu mashinada bloklangan;
`itc_sid` cookie + `UserSession` qatori): Login → MY StartUp → Create → Dashboard →
Roadmap → Task submit → Mentor approve → XP/progress o'zgarishi → Team join/accept → Top.
Dark/light mode va mobil ko'rinish tekshiriladi.

**Migratsiya xavfsizligi:** faqat `CREATE TABLE` — mavjud jadvallarga `ALTER` yo'q,
`CustomUser`ga tegilmaydi, hech qanday ma'lumot o'chirilmaydi.
Deploy'dan keyin cPanel'da restart shart (`tmp/restart.txt`) — template keshi.
