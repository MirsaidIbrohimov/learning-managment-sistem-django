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
        lessonSearch: document.getElementById('qzLessonSearch'),
        lessonResults: document.getElementById('qzLessonResults'),
        lessonSelected: document.getElementById('qzLessonSelected'),
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

    function showSelectedLesson(label) {
        els.lessonSelected.innerHTML = `Tanlangan dars: ${label} <a href="#" class="qz-lesson-clear">(bekor qilish)</a>`;
        els.lessonSelected.classList.remove('d-none');
        els.lessonSearch.value = '';
        els.lessonResults.classList.add('d-none');
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
    }

    function runLessonSearch() {
        const term = els.lessonSearch.value.trim();
        const params = new URLSearchParams();
        if (term) params.set('search', term);
        if (quizId) params.set('current_quiz_id', quizId);
        els.lessonResults.classList.remove('d-none');
        els.lessonResults.innerHTML = '<div class="px-3 py-2 text-muted small">Yuklanmoqda...</div>';
        window.QuizApi.get(`quizzes/available-lessons/?${params.toString()}`)
            .then((lessons) => {
                if (!lessons.length) {
                    els.lessonResults.innerHTML = term
                        ? '<div class="px-3 py-3 text-muted small text-center">Mos dars topilmadi.</div>'
                        : '<div class="px-3 py-3 text-muted small text-center">Bo\'sh.</div>';
                    return;
                }
                renderGroupedLessons(lessons);
            })
            .catch((err) => {
                els.lessonResults.innerHTML = `<div class="px-3 py-2 text-danger small">${escapeHtml(err.message)}</div>`;
            });
    }

    function renderGroupedLessons(lessons) {
        // Group by profession → section (within profession). Lessons without
        // a section land in a synthetic "Boshqa darslar" bucket per profession
        // so the picker still shows them visibly.
        const byProf = new Map();
        for (const l of lessons) {
            if (!byProf.has(l.profession_id)) {
                byProf.set(l.profession_id, { name: l.profession_name, sections: new Map() });
            }
            const prof = byProf.get(l.profession_id);
            const secKey = l.section_id || '__none__';
            const secLabel = l.section_name || "Bo'limsiz darslar";
            if (!prof.sections.has(secKey)) {
                prof.sections.set(secKey, { name: secLabel, lessons: [] });
            }
            prof.sections.get(secKey).lessons.push(l);
        }

        const frag = document.createDocumentFragment();
        for (const [, prof] of byProf) {
            const profHeader = document.createElement('div');
            profHeader.className = 'qz-lp-prof';
            profHeader.innerHTML = `<i class="bi bi-mortarboard-fill"></i> <span>${escapeHtml(prof.name)}</span>`;
            frag.appendChild(profHeader);

            for (const [, sec] of prof.sections) {
                const secHeader = document.createElement('div');
                secHeader.className = 'qz-lp-section';
                secHeader.innerHTML = `<i class="bi bi-folder2"></i> ${escapeHtml(sec.name)} <span class="qz-lp-count">${sec.lessons.length}</span>`;
                frag.appendChild(secHeader);
                for (const lesson of sec.lessons) {
                    const item = document.createElement('button');
                    item.type = 'button';
                    item.className = 'qz-lp-lesson';
                    const legacyBadge = lesson.has_legacy_test
                        ? '<span class="qz-lp-tag warning"><i class="bi bi-exclamation-triangle-fill"></i> eski testi bor</span>'
                        : '';
                    item.innerHTML = `
                        <span class="qz-lp-lesson-ico"><i class="bi bi-journal-text"></i></span>
                        <span class="qz-lp-lesson-text">${escapeHtml(lesson.title)}</span>
                        ${legacyBadge}
                    `;
                    item.addEventListener('click', () => selectLesson(lesson));
                    frag.appendChild(item);
                }
            }
        }
        els.lessonResults.innerHTML = '';
        els.lessonResults.appendChild(frag);
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

    let lessonSearchDebounce = null;
    els.lessonSearch.addEventListener('input', () => {
        clearTimeout(lessonSearchDebounce);
        lessonSearchDebounce = setTimeout(runLessonSearch, 300);
    });
    els.lessonSearch.addEventListener('focus', () => {
        if (!els.lessonId.value) runLessonSearch();
    });
    els.lessonSelected.addEventListener('click', (e) => {
        if (e.target.closest('.qz-lesson-clear')) {
            e.preventDefault();
            clearLesson();
        }
    });
    document.addEventListener('click', (e) => {
        if (!e.target.closest('#qzLessonSearch') && !e.target.closest('#qzLessonResults')) {
            els.lessonResults.classList.add('d-none');
        }
    });

    async function init() {
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
