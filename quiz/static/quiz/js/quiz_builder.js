/**
 * Quiz Builder: create/edit a single quiz (title/description/settings) plus
 * attach/detach/reorder questions from the bank.
 *
 * Mirrors the create/edit dual-mode pattern from question_builder.js: a
 * missing quiz id means "create" (settings only, question panel disabled
 * until the first save produces an id), a present id means "edit" (full
 * panel, including lifecycle transitions and question management).
 */
(function () {
    'use strict';

    const STATUS_LABELS = {
        draft: ['Qoralama', 'bg-secondary'],
        published: ['Chop etilgan', 'bg-success'],
        archived: ['Arxivlangan', 'bg-warning text-dark'],
    };
    const TYPE_LABELS = {
        single_choice: "Bitta to'g'ri javob",
        multiple_choice: "Bir nechta to'g'ri javob",
        true_false: "To'g'ri / Noto'g'ri",
        short_answer: 'Qisqa javob',
        essay: 'Esse',
    };

    const app = document.getElementById('qzApp');
    let quizId = app.dataset.quizId || null;
    let isEdit = Boolean(quizId);
    let links = []; // attached QuizQuestion links, kept in `order`

    const els = {
        title: document.getElementById('qzTitle'),
        titleInput: document.getElementById('qzTitleInput'),
        description: document.getElementById('qzDescription'),
        lessonId: document.getElementById('qzLessonId'),
        lessonPicker: document.getElementById('qzLessonPicker'),
        lessonSelected: document.getElementById('qzLessonSelected'),
        courseSelect: document.getElementById('qzCourseSelect'),
        sectionSelect: document.getElementById('qzSectionSelect'),
        lessonListWrap: document.getElementById('qzLessonListWrap'),
        lessonList: document.getElementById('qzLessonList'),
        newLessonTitle: document.getElementById('qzNewLessonTitle'),
        createLessonBtn: document.getElementById('qzCreateLessonBtn'),
        timeLimit: document.getElementById('qzTimeLimit'),
        passingScore: document.getElementById('qzPassingScore'),
        attemptsAllowed: document.getElementById('qzAttemptsAllowed'),
        questionCount: document.getElementById('qzQuestionCount'),
        allowRetry: document.getElementById('qzAllowRetry'),
        shuffleQuestions: document.getElementById('qzShuffleQuestions'),
        shuffleAnswers: document.getElementById('qzShuffleAnswers'),
        negativeMarking: document.getElementById('qzNegativeMarking'),
        saveBtn: document.getElementById('qzSaveBtn'),
        publishBtn: document.getElementById('qzPublishBtn'),
        archiveBtn: document.getElementById('qzArchiveBtn'),
        restoreBtn: document.getElementById('qzRestoreBtn'),
        statusBadge: document.getElementById('qzStatusBadge'),
        errorSummary: document.getElementById('qzErrorSummary'),
        attachBtn: document.getElementById('qzAttachBtn'),
        saveFirstHint: document.getElementById('qzSaveFirstHint'),
        questionsList: document.getElementById('qzQuestionsList'),
        bankSearch: document.getElementById('qzBankSearch'),
        bankResults: document.getElementById('qzBankResults'),
    };
    const questionRowTpl = document.getElementById('qzQuestionRowTemplate');
    const attachModalEl = document.getElementById('qzAttachModal');

    function buildPayload() {
        const lessonValue = els.lessonId.value.trim();
        return {
            lesson: lessonValue ? Number(lessonValue) : null,
            title: els.titleInput.value.trim(),
            description: els.description.value.trim(),
            settings: {
                time_limit_minutes: Number(els.timeLimit.value) || 1,
                passing_score: Number(els.passingScore.value) || 0,
                allow_retry: els.allowRetry.checked,
                attempts_allowed: Number(els.attemptsAllowed.value) || 0,
                shuffle_questions: els.shuffleQuestions.checked,
                shuffle_answers: els.shuffleAnswers.checked,
                question_count: Number(els.questionCount.value) || 0,
                negative_marking: els.negativeMarking.checked,
            },
        };
    }

    function clientSideValidate(payload) {
        if (!payload.title) return "Test nomi bo'sh bo'lishi mumkin emas.";
        if (payload.settings.time_limit_minutes < 1) return "Vaqt chegarasi kamida 1 daqiqa bo'lishi kerak.";
        if (payload.settings.passing_score < 0 || payload.settings.passing_score > 100) {
            return "O'tish bali 0 va 100 orasida bo'lishi kerak.";
        }
        return null;
    }

    function applyStatus(quiz) {
        const [label, cls] = STATUS_LABELS[quiz.status] || [quiz.status, 'bg-secondary'];
        els.statusBadge.textContent = label;
        els.statusBadge.className = `badge ${cls}`;
        els.statusBadge.classList.remove('d-none');
        els.publishBtn.classList.toggle('d-none', quiz.status === 'published');
        els.archiveBtn.classList.toggle('d-none', quiz.status === 'archived');
        els.restoreBtn.classList.toggle('d-none', quiz.status !== 'archived');
    }

    function populateForm(quiz) {
        els.title.textContent = 'Testni tahrirlash';
        els.titleInput.value = quiz.title;
        els.description.value = quiz.description || '';
        els.lessonId.value = quiz.lesson || '';
        if (quiz.lesson && quiz.lesson_label) {
            showSelectedLesson(quiz.lesson_label);
        }
        els.timeLimit.value = quiz.settings.time_limit_minutes;
        els.passingScore.value = quiz.settings.passing_score;
        els.attemptsAllowed.value = quiz.settings.attempts_allowed;
        els.questionCount.value = quiz.settings.question_count;
        els.allowRetry.checked = quiz.settings.allow_retry;
        els.shuffleQuestions.checked = quiz.settings.shuffle_questions;
        els.shuffleAnswers.checked = quiz.settings.shuffle_answers;
        els.negativeMarking.checked = quiz.settings.negative_marking;
        applyStatus(quiz);
    }

    function updatePublishReadiness() {
        if (!els.publishBtn) return;
        const hasQuestions = links.length > 0;
        els.publishBtn.title = hasQuestions ? '' : "Chop etish uchun kamida 1 ta savol qo'shing";
        els.publishBtn.style.opacity = hasQuestions ? '' : '0.55';
    }

    function renderQuestions() {
        els.questionsList.innerHTML = '';
        updatePublishReadiness();
        if (!links.length) {
            els.questionsList.innerHTML =
                '<div class="alert alert-warning py-2 small mb-0">' +
                '<i class="bi bi-exclamation-triangle me-1"></i>' +
                "Hali savol biriktirilmagan. Testni chop etish uchun kamida 1 ta savol qo'shing." +
                '</div>';
            return;
        }
        const sorted = [...links].sort((a, b) => a.order - b.order);
        sorted.forEach((link, index) => {
            const node = questionRowTpl.content.cloneNode(true);
            node.querySelector('.qz-question-text').textContent = link.question.text;
            node.querySelector('.qz-question-type').textContent = TYPE_LABELS[link.question.type] || link.question.type;
            const upBtn = node.querySelector('.qz-move-up');
            const downBtn = node.querySelector('.qz-move-down');
            upBtn.disabled = index === 0;
            downBtn.disabled = index === sorted.length - 1;
            upBtn.addEventListener('click', () => moveQuestion(sorted, index, -1));
            downBtn.addEventListener('click', () => moveQuestion(sorted, index, 1));
            node.querySelector('.qz-detach-btn').addEventListener('click', () => detachQuestion(link.question.id));
            els.questionsList.appendChild(node);
        });
    }

    async function moveQuestion(sorted, index, delta) {
        const targetIndex = index + delta;
        if (targetIndex < 0 || targetIndex >= sorted.length) return;
        const a = sorted[index];
        const b = sorted[targetIndex];
        const order = [{ id: a.id, order: b.order }, { id: b.id, order: a.order }];
        try {
            links = await window.QuizApi.post(`quizzes/${quizId}/questions/reorder/`, { order });
            renderQuestions();
        } catch (err) {
            window.QuizApi.toast(err.message, 'error');
        }
    }

    async function loadQuestions() {
        links = await window.QuizApi.get(`quizzes/${quizId}/questions/`);
        renderQuestions();
    }

    async function attachQuestion(questionId) {
        try {
            await window.QuizApi.post(`quizzes/${quizId}/questions/attach/`, { question_id: questionId });
            window.QuizApi.toast('Savol biriktirildi.');
            await loadQuestions();
            runBankSearch();
        } catch (err) {
            window.QuizApi.toast(err.message, 'error');
        }
    }

    async function detachQuestion(questionId) {
        try {
            await window.QuizApi.post(`quizzes/${quizId}/questions/detach/`, { question_id: questionId });
            window.QuizApi.toast('Savol olib tashlandi.');
            await loadQuestions();
        } catch (err) {
            window.QuizApi.toast(err.message, 'error');
        }
    }

    function runBankSearch() {
        const term = els.bankSearch.value.trim();
        els.bankResults.innerHTML = '<p class="text-muted small px-2">Qidirilmoqda...</p>';
        const attachedIds = new Set(links.map((l) => l.question.id));
        window.QuizApi.get(`questions/?status=published${term ? `&search=${encodeURIComponent(term)}` : ''}`)
            .then((data) => {
                els.bankResults.innerHTML = '';
                const candidates = data.results.filter((q) => !attachedIds.has(q.id));
                if (!candidates.length) {
                    els.bankResults.innerHTML = '<p class="text-muted small px-2">Mos savol topilmadi.</p>';
                    return;
                }
                for (const q of candidates) {
                    const item = document.createElement('div');
                    item.className = 'list-group-item d-flex justify-content-between align-items-center gap-2';
                    item.innerHTML = `
                        <div>
                            <div>${q.text}</div>
                            <span class="badge quizui-type-badge">${TYPE_LABELS[q.type] || q.type}</span>
                        </div>
                        <button class="btn btn-sm btn-primary flex-shrink-0"><i class="bi bi-plus-lg"></i> Qo'shish</button>
                    `;
                    item.querySelector('button').addEventListener('click', () => attachQuestion(q.id));
                    els.bankResults.appendChild(item);
                }
            })
            .catch((err) => {
                els.bankResults.innerHTML = `<p class="text-danger small px-2">${err.message}</p>`;
            });
    }

    let courseTree = []; // [{id, name, sections:[{id, title}]}]

    function showSelectedLesson(label) {
        els.lessonSelected.innerHTML = `Tanlangan dars: ${label} <a href="#" class="qz-lesson-clear">(bekor qilish)</a>`;
        els.lessonSelected.classList.remove('d-none');
        els.lessonPicker.classList.add('d-none');
    }

    function selectLesson(lesson) {
        els.lessonId.value = lesson.id;
        const legacyNote = lesson.has_legacy_test ? ' (eski testi mavjud)' : '';
        showSelectedLesson(`${lesson.profession_name} — ${lesson.title}${legacyNote}`);
    }

    function clearLesson() {
        els.lessonId.value = '';
        els.lessonSelected.classList.add('d-none');
        els.lessonSelected.textContent = '';
        els.lessonPicker.classList.remove('d-none');
    }

    async function loadCourseTree() {
        try {
            courseTree = await window.QuizApi.get('quizzes/course-tree/');
            els.courseSelect.innerHTML = '<option value="">Kurs tanlang...</option>' +
                courseTree.map((p) => `<option value="${p.id}">${escapeHtml(p.name)}</option>`).join('');
        } catch (err) {
            window.QuizApi.toast(err.message, 'error');
        }
    }

    function onCourseChange() {
        const profId = Number(els.courseSelect.value) || null;
        const prof = courseTree.find((p) => p.id === profId);

        els.sectionSelect.innerHTML = '<option value="">Bo\'limsiz</option>' +
            (prof ? prof.sections.map((s) => `<option value="${s.id}">${escapeHtml(s.title)}</option>`).join('') : '');
        els.sectionSelect.disabled = !prof;
        els.newLessonTitle.disabled = !prof;
        els.createLessonBtn.disabled = !prof;

        if (prof) {
            loadExistingLessons();
        } else {
            els.lessonListWrap.classList.add('d-none');
        }
    }

    function onSectionChange() {
        if (els.courseSelect.value) loadExistingLessons();
    }

    async function loadExistingLessons() {
        const profId = els.courseSelect.value;
        const secId = els.sectionSelect.value;
        if (!profId) return;

        const params = new URLSearchParams({ profession_id: profId });
        if (secId) params.set('section_id', secId);
        if (quizId) params.set('current_quiz_id', quizId);

        els.lessonListWrap.classList.remove('d-none');
        els.lessonList.innerHTML = '<div class="text-muted small px-2 py-1">Yuklanmoqda...</div>';
        try {
            const lessons = await window.QuizApi.get(`quizzes/available-lessons/?${params.toString()}`);
            if (!lessons.length) {
                els.lessonList.innerHTML = '<div class="text-muted small px-2 py-1">Bu bo\'limda bo\'sh test darsi yo\'q — pastdan yangisini yarating.</div>';
                return;
            }
            els.lessonList.innerHTML = '';
            for (const lesson of lessons) {
                const item = document.createElement('button');
                item.type = 'button';
                item.className = 'list-group-item list-group-item-action py-1 px-2 small';
                const legacyNote = lesson.has_legacy_test ? ' (eski testi bor)' : '';
                item.textContent = lesson.title + legacyNote;
                item.addEventListener('click', () => selectLesson(lesson));
                els.lessonList.appendChild(item);
            }
        } catch (err) {
            els.lessonList.innerHTML = `<div class="text-danger small px-2">${escapeHtml(err.message)}</div>`;
        }
    }

    async function createLessonSlot() {
        const profId = els.courseSelect.value;
        const secId = els.sectionSelect.value;
        const title = els.newLessonTitle.value.trim();
        if (!profId || !title) {
            window.QuizApi.toast("Kurs va dars nomini kiriting.", 'error');
            return;
        }
        els.createLessonBtn.disabled = true;
        try {
            const lesson = await window.QuizApi.post('quizzes/create-lesson-slot/', {
                profession_id: Number(profId),
                section_id: secId ? Number(secId) : null,
                title,
            });
            window.QuizApi.toast('Yangi dars yaratildi va tanlandi.');
            els.newLessonTitle.value = '';
            selectLesson(lesson);
        } catch (err) {
            window.QuizApi.toast(err.message, 'error');
        } finally {
            els.createLessonBtn.disabled = false;
        }
    }

    function escapeHtml(s) {
        return String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({
            '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
        }[c]));
    }

    function enableQuestionsPanel() {
        els.attachBtn.disabled = false;
        els.saveFirstHint.classList.add('d-none');
    }

    async function save() {
        const payload = buildPayload();
        const error = clientSideValidate(payload);
        els.errorSummary.classList.toggle('d-none', !error);
        els.errorSummary.textContent = error || '';
        if (error) return;

        els.saveBtn.disabled = true;
        try {
            if (isEdit) {
                const updated = await window.QuizApi.patch(`quizzes/${quizId}/`, payload);
                applyStatus(updated);
                window.QuizApi.toast('Test yangilandi.');
            } else {
                const created = await window.QuizApi.post('quizzes/', payload);
                window.QuizApi.toast('Test yaratildi.');
                window.location.href = `/quiz/quizzes/${created.id}/edit/`;
                return;
            }
        } catch (err) {
            els.errorSummary.classList.remove('d-none');
            els.errorSummary.textContent = err.message;
        } finally {
            els.saveBtn.disabled = false;
        }
    }

    async function transition(action) {
        try {
            const updated = await window.QuizApi.post(`quizzes/${quizId}/${action}/`);
            applyStatus(updated);
            window.QuizApi.toast('Holat yangilandi.');
        } catch (err) {
            window.QuizApi.toast(err.message, 'error');
        }
    }

    els.saveBtn.addEventListener('click', save);
    els.publishBtn.addEventListener('click', () => {
        if (links.length === 0) {
            window.QuizApi.toast("Chop etish uchun kamida 1 ta savol qo'shing.", 'error');
            return;
        }
        transition('publish');
    });
    els.archiveBtn.addEventListener('click', () => transition('archive'));
    els.restoreBtn.addEventListener('click', () => transition('restore'));

    let searchDebounce = null;
    els.bankSearch.addEventListener('input', () => {
        clearTimeout(searchDebounce);
        searchDebounce = setTimeout(runBankSearch, 300);
    });
    attachModalEl.addEventListener('show.bs.modal', runBankSearch);

    els.courseSelect.addEventListener('change', onCourseChange);
    els.sectionSelect.addEventListener('change', onSectionChange);
    els.createLessonBtn.addEventListener('click', createLessonSlot);
    els.lessonSelected.addEventListener('click', (e) => {
        if (e.target.closest('.qz-lesson-clear')) {
            e.preventDefault();
            clearLesson();
        }
    });

    async function init() {
        await loadCourseTree();
        if (!isEdit) return;
        try {
            const quiz = await window.QuizApi.get(`quizzes/${quizId}/`);
            populateForm(quiz);
            enableQuestionsPanel();
            await loadQuestions();
        } catch (err) {
            window.QuizApi.toast(err.message, 'error');
        }
    }

    init();
})();
