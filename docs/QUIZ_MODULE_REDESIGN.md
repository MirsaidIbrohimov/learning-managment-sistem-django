# Quiz & Examination Module — Architecture & Phased Redesign Plan

Status: **Phase 1 implemented and live** (schema, legacy data migration, REST API, unified question builder UI — applied to the real `db.sqlite3` on 2026-06-28, verified: 3/3 legacy tests and 10/10 questions migrated, legacy `TestResult`/`TestUserAnswer` untouched). Phases 2–7 not started.
Owner: Husanbek
Scope: Complete redesign of the Test/Quiz system currently embedded in `accounts` + `teacher`.

This document is the single reference for the rebuild. Each phase below is meant to be approved and implemented separately — implementing everything at once is not realistic or safe for a system with live students, scores, and coin payouts.

---

## 1. Decisions already locked in (confirmed 2026-06-28)

These four answers shape every section below. If priorities change, update this section first.

1. **Process:** This roadmap doc first, then implement phase by phase after each is approved.
2. **Data safety:** Existing `Test` / `TestQuestion` / `TestAnswer` / `TestResult` / `TestUserAnswer` rows (real students, scores, coin awards) must be preserved — every schema change needs a migration path, not a fresh start.
3. **AI generator (this round):** Fix the hardcoded-3-option bug and tighten validation/prompting. Do **not** build a lesson-content ingestion pipeline (PDF/slides/video analysis) yet — that's a separate, larger phase, listed under Non-Goals.
4. **Code questions:** Display-only with syntax highlighting. No sandboxed auto-execution/auto-grading of submitted code — that requires new infrastructure (a judge/sandbox service) outside Django and is out of scope for now.

---

## 2. Current state (audit findings)

- Quiz logic is not its own app. It lives inside `accounts/models.py` (2,536 lines total) and `accounts/views.py` (14,804 lines total), as `Test`, `TestQuestion`, `TestAnswer`, `TestResult`, `TestUserAnswer`.
- `teacher/views.py` independently re-implements the same CRUD (`teacher_add_question`, `teacher_manage_questions`, `teacher_delete_question`, `teacher_import_questions`, `teacher_generate_ai_test`). The two copies have already diverged: the `accounts` path hardcodes exactly 3 answers (`TestQuestionForm.answer1/2/3`), the `teacher` path allows up to 4 (`range(1, 5)`).
- Only one question type exists: single-choice MCQ.
- The option limit is a form/view-layer restriction, not a database one — `TestAnswer` is a plain FK to `TestQuestion`, so the schema can already support N options. This makes Phase 1 cheaper than it would otherwise be.
- AI generation already exists (`generate_ai_test`, OpenAI `gpt-4o-mini`) but: hardcodes exactly 3 options (A/B/C), and is grounded only in the lesson/section/course **title**, not actual lesson content — so it can hallucinate.
- Import is a synchronous `.xlsx`-only form upload with fixed column names, plain inline error text, no preview/mapping/summary steps, no CSV/JSON support.
- The student exam flow is session-based, not a real "Attempt" model — state lives in `request.session`, not the database, until final submission. No question navigator, no flagging, no reconnect/resume across devices.
- DRF is installed and lightly used (`api` app has a few read-only endpoints, e.g. `MyTestResultsView`), but there is **no REST API** for quiz/question CRUD, import, or AI generation. Everything is Django forms + redirects + `messages`.
- Permission checks are ad hoc (`if not (request.user.is_admin or request.user.is_teacher))` repeated per view, not centralized.
- **Infra constraint:** production runs SQLite via Passenger/WSGI on shared hosting. No Celery, Redis, or Channels/websockets today. This caps what "scales to thousands of users," async AI calls, and real-time autosave can mean without a separate infra decision (see §6).

---

## 3. Target architecture

### 3.1 New app: `quiz`

A dedicated app, decoupled from `accounts`/`teacher`, owns all quiz/question/attempt logic. `accounts` and `teacher` keep only thin views that call the new API or get removed once the new UI replaces them (see §5 rollout).

**Question Bank layer (reusable across quizzes):**

| Model | Purpose |
|---|---|
| `Question` | Bank-level question: `type` (choice list, extensible — see 3.2), rich content, explanation, hints, difficulty, `points_default`, status (draft/published/archived), category/subject/tags, `code_language`, `metadata` (JSONField for type-specific config: matching pairs, ordering items, blank positions, etc.), `usage_count`, `last_used_at`, `created_by`, version. |
| `AnswerOption` | Choice-type answers. `question` FK, rich text, `is_correct`, `order`, optional image. **No count limit anywhere** — UI adds/removes rows dynamically. |
| `QuestionMedia` | Images/audio/video attached to a question, answer, explanation, or hint. |
| `Category`, `Subject`, `Tag` | For question bank search/filtering. |

**Quiz layer:**

| Model | Purpose |
|---|---|
| `Quiz` | Replaces `Test`. Keeps the existing `lesson` link (now optional, so standalone bank-driven quizzes are possible later) plus title/description. |
| `QuizSettings` | Split out from `Quiz` for clarity: passing score, attempts allowed, negative marking, randomization flags, question groups, time limit, grace period, availability window, IP/browser restrictions, fullscreen requirement, certificate trigger. |
| `QuizQuestion` | Join table (`quiz`, `question`, `order`, `points_override`, `group`) — many-to-many, so one bank question can be reused across quizzes. |

**Attempt layer (replaces session-based state):**

| Model | Purpose |
|---|---|
| `Attempt` | Replaces `TestResult`. Real lifecycle: `status` (in_progress/submitted/graded/abandoned), `started_at`, `expires_at`, `resume_token`, `flagged_questions`, score, attempt number. Lives in the DB from the moment a student starts, not just at submission — this is what enables resume/reconnect. |
| `AttemptAnswer` | Replaces `TestUserAnswer`. `response` is a JSONField generic enough for any question type (selected option ids, free text, matching pairs, ordering sequence, code submission), plus manual-grading fields (`graded_by`, `points_awarded`, `feedback`) for essay/code questions. |

**Import layer:**

| Model | Purpose |
|---|---|
| `ImportJob` | One row per import run: uploaded file, detected mapping, preview data, validation errors, result summary. Backs the step-by-step wizard (§3.5) and the downloadable error report. |

### 3.2 Question types — extensibility approach

Each question type is a small Python class (strategy pattern) registered in a `QUESTION_TYPE_REGISTRY`: it defines its `metadata` schema, how to render it, how to validate a submitted answer, and how to grade it (auto or manual). `Question.type` just stores the registry key. Adding "Drag and Drop" later means adding one new strategy class, not touching `Question`, `AttemptAnswer`, or any migration. This is what satisfies "future question types should require almost no backend modification."

Initial set to ship (Phase 2): Single Choice, Multiple Choice, True/False, Fill in the Blank, Short Answer, Long Answer/Essay, Matching, Ordering, Code Question, Image Question. Audio/Video/Drag-and-Drop/Programming Output/Error Detection follow once the registry pattern is in place — each is incremental at that point.

### 3.3 REST API (DRF, versioned)

All quiz mutation and read paths move under `/api/v1/quiz/`:

- `questions/` — bank CRUD, filter (category/tag/difficulty/type/status), search, pagination; `questions/{id}/duplicate/`; `questions/bulk/` for bulk update/delete.
- `quizzes/` — CRUD, `quizzes/{id}/publish/`, `/archive/`, `/restore/`; `quizzes/{id}/questions/` for attach/detach/reorder.
- `import/` — `POST` creates an `ImportJob`; `import/{id}/preview/`, `/commit/`, `/errors.csv` (downloadable report).
- `ai-generate/` — fixed version of the existing generator (§3.6).
- `attempts/` — student starts an attempt; `attempts/{id}/answer/` autosaves one answer; `/submit/`; `/resume/`; `/review/` for the post-exam summary.

Permissions move to DRF permission classes (`IsTeacherOwnerOrAdmin`, scoped via the existing `teaching_professions` relation; `IsEnrolledStudent` for attempt endpoints) instead of repeated inline checks. Rate limiting applies to `ai-generate/` and `attempts/{id}/submit/`.

### 3.4 Frontend approach

No build pipeline exists today (no webpack/node toolchain in the repo), so the plan avoids introducing one:

- **Rich text:** a JSON-based, plugin-driven editor with no required build step (e.g. Editor.js) — stores question/answer/explanation content as structured blocks, which also maps cleanly onto the question-type registry (a "code block" or "image block" is just another block type).
- **Code highlighting:** highlight.js or Prism via CDN, matching the existing CDN-based asset pattern in this project.
- **Images:** existing `ImageField` pattern, plus one new `media/upload/` endpoint for paste/drag-drop from the editor.
- Question builder, import wizard, and the redesigned student exam page are vanilla JS modules calling the new API — consistent with how `test_take.html` already does its `fetch()`-based submit today, just extended.

### 3.5 Import wizard

Replaces the single-step `.xlsx`-only form with: upload → parse & preview → auto-detect question type & map columns → validate → commit → summary. Supports `.xlsx`, `.csv`, `.json`. The "no Celery yet" constraint (§2) means this runs synchronously per request for now — fine at current file sizes; flagged in §6 as something to revisit if import volume grows.

### 3.6 AI generator — this phase's fix only

Per the locked-in decision (§1.3): make option count dynamic (2–10+, no hardcoded A/B/C), validate the model's JSON output against a schema instead of ad hoc parsing, generalize the existing distractor-uniqueness check beyond 3 options, and add one extra self-review API call before saving (cheap version of "AI reviews its own output" — dedup + wording pass) — all without adding a content-ingestion pipeline.

### 3.7 Student exam experience

Built on the new `Attempt` model instead of `request.session`: state is durable from the first question, so reconnect/resume works by re-fetching attempt state, not by trusting the session. Adds a question navigator (answered/skipped/flagged/current), flagging, and keeps the existing timer/fullscreen/anti-cheat behavior already present in `test_take.html`.

---

## 4. Data migration & compatibility strategy

Because live data must be preserved (§1.2):

1. New `quiz` app and tables are created **alongside** the existing ones — nothing in `accounts`/`teacher` is deleted yet.
2. A one-time management command copies: `Test` → `Quiz` + `QuizSettings`, `TestQuestion` → `Question` (`type=single_choice`) + `QuizQuestion`, `TestAnswer` → `AnswerOption`, `TestResult` → `Attempt` (`status=graded`), `TestUserAnswer` → `AttemptAnswer` (`response={"selected_option_id": ...}`). This is re-runnable and idempotent (skips already-migrated rows) so it can run repeatedly during testing before the real cutover.
3. Old views/URLs keep working against the old models during the transition. The new student exam page and new teacher question builder are rolled out behind a flag (e.g. per-lesson or global setting) so we can compare side-by-side and roll back instantly if something's wrong.
4. Only after a phase has run in production without issues do we remove the corresponding old code path. Nothing old is deleted in the same phase it's replaced.

---

## 5. Phased delivery plan

Each phase ships independently and leaves the system in a working state.

**Phase 1 — Foundation (highest impact, fixes the original complaint). ✅ Done.**
New `quiz` app, new schema (§3.1), data migration command (§4), REST API for question/quiz CRUD with unlimited dynamic options, single unified question builder UI replacing both the `accounts` and `teacher` duplicate code paths. This alone removes the hardcoded-3/4-option inconsistency and the duplicated logic.
Shipped: `Question`/`AnswerOption`/`Quiz`/`QuizSettings`/`QuizQuestion` models + `quiz.0001_initial`; `migrate_legacy_quizzes` (idempotent, dry-run support); `QuestionViewSet`/`QuizViewSet` DRF APIs with centralized `IsAdminOrTeacher` + ownership checks; question builder UI (single/multiple/true-false/short-answer/essay) at `/quiz/questions/`. Known limitation carried into Phase 2: `AnswerOption.image` exists on the schema but has no upload UI yet, and `QuestionSerializer.update()` replaces all options on edit rather than diffing by id — fine today since no caller sets option images, but worth revisiting together when Phase 2 wires up image support.

**Phase 2 — Question types.** Type registry (§3.2) + the initial type set, rich text editor, code blocks with syntax highlighting, image support in questions/answers/explanations.

**Phase 3 — Question Bank & Import.** Search/filter/tagging/categories/usage stats for the bank; redesigned import wizard (§3.5) with CSV/JSON support and downloadable error reports.

**Phase 4 — Quiz/Exam Builder.** Step-by-step wizard (info → questions → randomization → settings → preview → publish), draft mode, autosave.

**Phase 5 — Student exam experience.** `Attempt`-backed exam page (§3.7), navigator, flagging, resume/reconnect, redesigned review/results page with charts and weak/strong topic breakdown.

**Phase 6 — AI generator fix.** Dynamic option count, schema validation, generalized dedup, lightweight self-review pass (§3.6).

**Phase 7 — Hardening pass.** Permission audit via DRF permission classes, N+1 query audit, caching/pagination pass, accessibility and responsive QA, removal of now-dead old code paths once Phases 1–6 are confirmed stable in production.

---

## 6. Explicit non-goals for this round (candidates for a future phase, not decided yet)

- **AI content grounding** — ingesting lesson PDFs/slides/video/notes so the generator works from real material instead of a topic title. Deferred per §1.3.
- **Sandboxed code execution/auto-grading** — running submitted code to auto-grade Programming Output/Error Detection questions. Deferred per §1.4; would need a judge service (e.g. Docker-based) outside the current Django/Passenger deployment.
- **Infra changes** (Postgres instead of SQLite, Celery/Redis for async AI calls and large imports, websockets for real-time features) — not required for Phases 1–7 as scoped, but worth a separate decision if/when concurrent load grows. SQLite's write-locking behavior is the main risk at real scale for simultaneous exam submissions.

---

## 7. Next step

Ready to start **Phase 1** on approval: new `quiz` app skeleton, models, migration command, and the first REST endpoints (`questions/`, `quizzes/`) replacing the dual `accounts`/`teacher` question-CRUD code paths.
