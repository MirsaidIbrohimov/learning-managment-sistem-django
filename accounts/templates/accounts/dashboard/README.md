# Dashboard component partials

Reusable, defensively-coded include partials for the premium student dashboard.

## Setup

Load the styleşeet once in the page (e.g. in `{% block extra_css %}`):

```django
<link rel="stylesheet" href="{% static 'css/dashboard.css' %}">
```

Wrap your dashboard markup in an element with the `.dash` class so the design tokens apply (light + dark are both handled via `[data-bs-theme="dark"] .dash`):

```django
<div class="dash">
  ... include partials here ...
</div>
```

All partials are self-contained: no `<script>`, no external CSS, no Bootstrap JS.
Every field is guarded — missing data renders a fallback or empty state, never an error.
All visible text is Uzbek (latin).

## Layout helpers (from dashboard.css)

- `.dash-card` / `.dash-card-glass` — surface container; `.dash-card-head`, `.dash-card-title`, `.dash-chip` (`.is-accent/.is-success/.is-warning/.is-danger`).
- `.dash-cols cols-sm-2 cols-md-3 cols-md-4 cols-lg-4` — responsive grid wrappers.
- Skeleton: `.skeleton`, `.skeleton-text` (`.w-60`/`.w-40`), `.skeleton-card`.
- States: `.dash-empty`, `.dash-error`.

---

## Partials

### 1. `_stat_card.html` — variable: `stat`
StatsCard with gradient icon, value, label.
`stat = {label, value, icon, color, hint?}`
- `icon`: bootstrap-icon name without `bi-` prefix (e.g. `book`).
- `color`: one of `accent`(default) `accent2` `success` `warning` `danger`.
- Skeleton variant: pass `skeleton=True` (no `stat` needed).
```django
{% include 'accounts/dashboard/_stat_card.html' with stat=mystat %}
{% include 'accounts/dashboard/_stat_card.html' with skeleton=True %}
```

### 2. `_course_card.html` — variable: `course`
Netflix continue-watching style card.
`course = {id, name, photo, teacher, is_paid, progress?, lesson_count?, reason?, url}`
- `photo` falsy → gradient + first letter fallback.
- `progress` present (0–100) → progress bar shown. Button = "Davom etiş".
- Pass `recommend=True` to render as a recommendation (button "Köriş", shows `reason`).
```django
{% include 'accounts/dashboard/_course_card.html' with course=c %}
{% include 'accounts/dashboard/_course_card.html' with course=c recommend=True %}
```

### 3. `_mission_card.html` — variable: `mission`
Daily/weekly mission with progress ring.
`mission = {key, title, icon, target, current, reward_xp, done, pct}`
- `pct`: number 0–100 (drives the conic-gradient ring via `--pct`).
- `done=True` → green completed ring + check badge.
```django
{% include 'accounts/dashboard/_mission_card.html' with mission=m %}
```

### 4. `_achievement_card.html` — variable: `badge`
Earned/locked badge tile.
`badge = {key, title, icon, desc, earned, earned_label}`
- `earned` falsy → `.is-locked` (greyed + lock overlay).
- `earned=True` → colored with glow + `earned_label` (default "Qölga kiritildi").
```django
{% include 'accounts/dashboard/_achievement_card.html' with badge=b %}
```

### 5. `_leader_row.html` — variable: `row`
Leaderboard row.
`row = {rank, is_me, photo, name, points, level?}`
- `rank` 1/2/3 → trophy/award medal colors.
- `is_me=True` → highlighted row + "Siz" chip.
- `photo` falsy → initial avatar.
```django
{% include 'accounts/dashboard/_leader_row.html' with row=r %}
```

### 6. `_event_card.html` — variable: `event`
Calendar-style event card.
`event = {title, type, datetime_label, day, month, url, icon}`
- `day` (big) + `month` (small) form the date block.
```django
{% include 'accounts/dashboard/_event_card.html' with event=e %}
```

### 7. `_announcement_card.html` — variable: `ann`
Announcement with unread indicator.
`ann = {title, body, date_label, is_unread, badge, url}`
- `is_unread=True` → red dot + red accent bar.
- `body` truncated to 120 chars.
- `badge`: pass a color keyword used as chip class — `accent` `success` `warning` `danger`.
  (The badge text is the keyword itself; for a custom label, adjust the integrator data or extend the partial.)
```django
{% include 'accounts/dashboard/_announcement_card.html' with ann=a %}
```

### 8. `_quick_tile.html` — variable: `tile`
Quick-action icon tile.
`tile = {label, url, icon, color}`
- `color`: `accent`(default) `accent2` `success` `warning` `danger`.
```django
{% include 'accounts/dashboard/_quick_tile.html' with tile=t %}
```

### 9. `_heatmap.html` — variable: `days` (+ optional `total`, `active_days`)
GitHub-style activity grid (7 rows, columns = weeks).
`days = [{date, count, level}, ...]` where `level` is 0–4.
- Range buttons (7/30/90) are presentational with `data-range` attrs for the parent JS to wire; default active = 90. The container is `[data-heatmap]`.
- Empty `days` → empty state.
```django
{% include 'accounts/dashboard/_heatmap.html' with days=heatmap_days total=hm_total active_days=hm_active %}
```

### 10. `_section_header.html` — variable: `title` (+ optional `subtitle`, `action_url`, `action_label`, `icon`)
Reusable section header with optional "see all" action.
```django
{% include 'accounts/dashboard/_section_header.html' with title='Kurslarim' subtitle='Davom etayotgan' action_url=url action_label='Hammasi' %}
```

### 11. `_empty.html` — variables: `icon`, `text` (+ optional `cta_url`, `cta_label`)
Reusable empty state.
`icon` = bootstrap-icon name without `bi-` prefix.
```django
{% include 'accounts/dashboard/_empty.html' with icon='inbox' text='Hozircha kurs yo\'q' cta_url=url cta_label='Kurs tanlash' %}
```

---

## Looping example

```django
<div class="dash-cols cols-md-3">
  {% for c in continue_courses %}
    {% include 'accounts/dashboard/_course_card.html' with course=c %}
  {% empty %}
    {% include 'accounts/dashboard/_empty.html' with icon='play-circle' text='Davom etadigan kurs yo\'q' %}
  {% endfor %}
</div>
```

## Notes
- Custom-property passthrough is used for rings/bars (`style="--pct:..."`). Keep that intact.
- Respects `prefers-reduced-motion` (transforms/animations disabled).
- No localStorage, no Bootstrap JS dependency.
