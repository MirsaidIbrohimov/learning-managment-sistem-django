/**
 * Quiz list page: searchable/filterable paginated table with
 * edit/results/publish/archive/restore/delete actions.
 * Pairs with quiz/templates/quiz/quiz_list.html.
 *
 * Filter state is mirrored into the page URL (?search=&status=&profession_id=&page=)
 * so going to the builder and pressing Back lands on the same filtered page.
 */
(function () {
    'use strict';

    const STATUS_LABELS = {
        draft: 'Qoralama',
        published: 'Chop etilgan',
        archived: 'Arxivlangan',
    };
    const PAGE_SIZE = 20;

    const initial = new URLSearchParams(window.location.search);
    const state = {
        page: parseInt(initial.get('page'), 10) || 1,
        status: initial.get('status') || '',
        profession: initial.get('profession_id') || '',
        search: initial.get('search') || '',
    };
    let debounceTimer = null;
    let requestSeq = 0;

    const tableBody = document.getElementById('quizTableBody');
    const rowTemplate = document.getElementById('quizRowTemplate');
    const resultCount = document.getElementById('quizResultCount');
    const searchInput = document.getElementById('quizSearch');
    const professionSelect = document.getElementById('quizProfessionFilter');
    const pills = document.querySelectorAll('#quizStatusPills .qz-pill');

    const statEls = {
        total: document.getElementById('quizStatTotal'),
        published: document.getElementById('quizStatPublished'),
        draft: document.getElementById('quizStatDraft'),
        archived: document.getElementById('quizStatArchived'),
    };

    function messageRow(text, cls = 'text-muted') {
        tableBody.innerHTML = '';
        const tr = document.createElement('tr');
        const td = document.createElement('td');
        td.colSpan = 7;
        td.className = `text-center py-4 ${cls}`;
        td.textContent = text;
        tr.appendChild(td);
        tableBody.appendChild(tr);
    }

    function buildParams(includePage = true) {
        const params = new URLSearchParams();
        if (includePage && state.page > 1) params.set('page', state.page);
        if (state.status) params.set('status', state.status);
        if (state.profession) params.set('profession_id', state.profession);
        if (state.search) params.set('search', state.search);
        return params;
    }

    function syncUrl() {
        const qs = buildParams().toString();
        history.replaceState(null, '', window.location.pathname + (qs ? `?${qs}` : ''));
    }

    async function loadStats() {
        try {
            const data = await window.QuizApi.get('quizzes/stats/');
            if (statEls.total) statEls.total.textContent = data.total;
            if (statEls.published) statEls.published.textContent = data.published;
            if (statEls.draft) statEls.draft.textContent = data.draft;
            if (statEls.archived) statEls.archived.textContent = data.archived;
        } catch (_) { /* stats are decorative, don't break the page */ }
    }

    async function loadProfessions() {
        try {
            const tree = await window.QuizApi.get('quizzes/course-tree/');
            for (const p of tree) {
                const opt = document.createElement('option');
                opt.value = p.id;
                opt.textContent = p.name;
                professionSelect.appendChild(opt);
            }
            professionSelect.value = state.profession;
        } catch (_) { /* filter stays as "Barcha kurslar" */ }
    }

    async function loadQuizzes() {
        const seq = ++requestSeq;
        syncUrl();
        messageRow('Yuklanmoqda...');
        const params = buildParams();
        params.set('page', state.page);
        try {
            const data = await window.QuizApi.get(`quizzes/?${params.toString()}`);
            if (seq !== requestSeq) return; // a newer search already fired
            renderRows(data.results);
            updatePagination(data);
        } catch (err) {
            if (seq !== requestSeq) return;
            // Filters narrowed results below the current page -- go back to page 1.
            if (err.status === 404 && state.page > 1) {
                state.page = 1;
                loadQuizzes();
                return;
            }
            messageRow(err.message, 'text-danger');
        }
    }

    function formatDate(iso) {
        if (!iso) return '';
        const d = new Date(iso);
        return d.toLocaleDateString('uz-UZ', { year: 'numeric', month: '2-digit', day: '2-digit' });
    }

    function renderRows(quizzes) {
        tableBody.innerHTML = '';
        if (!quizzes.length) {
            const filtered = state.search || state.status || state.profession;
            messageRow(filtered ? "Filtrga mos test topilmadi." : 'Hali test yaratilmagan.');
            return;
        }
        for (const quiz of quizzes) {
            const node = rowTemplate.content.cloneNode(true);
            const editUrl = `/quiz/quizzes/${quiz.id}/edit/`;

            const editLink = node.querySelector('.quiz-edit-link');
            editLink.textContent = quiz.title;
            editLink.title = quiz.title;
            editLink.href = editUrl;
            node.querySelector('.quiz-created-cell').textContent = formatDate(quiz.created_at);

            const lessonCell = node.querySelector('.quiz-lesson-cell');
            if (quiz.lesson_label) {
                lessonCell.textContent = quiz.lesson_label;
            } else {
                lessonCell.textContent = 'Mustaqil test';
                lessonCell.classList.add('text-muted');
            }
            node.querySelector('.quiz-questions-cell').textContent = `${quiz.question_count_actual} ta`;
            node.querySelector('.quiz-time-cell').textContent = `${quiz.settings.time_limit_minutes} daqiqa`;
            node.querySelector('.quiz-attempts-cell').textContent = `${quiz.attempt_count} ta`;

            const statusBadge = node.querySelector('.quiz-status-cell');
            statusBadge.textContent = STATUS_LABELS[quiz.status] || quiz.status;
            statusBadge.classList.add(quiz.status);

            node.querySelector('.quiz-edit-btn').href = editUrl;
            node.querySelector('.quiz-results-btn').href = `/quiz/test-hulosalari/q${quiz.id}/`;

            const publishBtn = node.querySelector('.quiz-publish-btn');
            const archiveBtn = node.querySelector('.quiz-archive-btn');
            const restoreBtn = node.querySelector('.quiz-restore-btn');
            const deleteBtn = node.querySelector('.quiz-delete-btn');
            publishBtn.classList.toggle('d-none', quiz.status === 'published');
            archiveBtn.classList.toggle('d-none', quiz.status === 'archived');
            restoreBtn.classList.toggle('d-none', quiz.status !== 'archived');
            // Quizzes with attempts can't be deleted (backend refuses) -- archive instead.
            deleteBtn.classList.toggle('d-none', quiz.attempt_count > 0);

            publishBtn.addEventListener('click', () => transition(quiz.id, 'publish'));
            archiveBtn.addEventListener('click', () => transition(quiz.id, 'archive'));
            restoreBtn.addEventListener('click', () => transition(quiz.id, 'restore'));
            deleteBtn.addEventListener('click', () => removeQuiz(quiz));

            tableBody.appendChild(node);
        }
    }

    async function transition(quizId, action) {
        try {
            await window.QuizApi.post(`quizzes/${quizId}/${action}/`);
            window.QuizApi.toast('Holat yangilandi.');
            loadQuizzes();
            loadStats();
        } catch (err) {
            window.QuizApi.toast(err.message, 'error');
        }
    }

    async function removeQuiz(quiz) {
        // eslint-disable-next-line no-alert
        if (!confirm(`"${quiz.title}" testini o'chirmoqchimisiz? Bu amalni qaytarib bo'lmaydi.`)) return;
        try {
            await window.QuizApi.delete(`quizzes/${quiz.id}/`);
            window.QuizApi.toast("Test o'chirildi.");
            loadQuizzes();
            loadStats();
        } catch (err) {
            window.QuizApi.toast(err.message, 'error');
        }
    }

    function updatePagination(data) {
        const start = (state.page - 1) * PAGE_SIZE + 1;
        const end = Math.min(state.page * PAGE_SIZE, data.count);
        resultCount.textContent = data.count ? `${start}-${end} / ${data.count} ta test` : '';
        document.getElementById('quizPrevPage').disabled = !data.previous;
        document.getElementById('quizNextPage').disabled = !data.next;
    }

    function resetAndLoad() {
        state.page = 1;
        loadQuizzes();
    }

    // ── Wire up controls ─────────────────────────────────────────────────
    searchInput.value = state.search;
    searchInput.addEventListener('input', (e) => {
        clearTimeout(debounceTimer);
        debounceTimer = setTimeout(() => {
            const value = e.target.value.trim();
            if (value === state.search) return;
            state.search = value;
            resetAndLoad();
        }, 300);
    });
    searchInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            e.preventDefault();
            clearTimeout(debounceTimer);
            state.search = searchInput.value.trim();
            resetAndLoad();
        }
    });

    pills.forEach((pill) => {
        pill.classList.toggle('active', pill.dataset.status === state.status);
        pill.addEventListener('click', () => {
            pills.forEach((p) => p.classList.remove('active'));
            pill.classList.add('active');
            state.status = pill.dataset.status;
            resetAndLoad();
        });
    });

    professionSelect.addEventListener('change', () => {
        state.profession = professionSelect.value;
        resetAndLoad();
    });

    document.getElementById('quizPrevPage').addEventListener('click', () => {
        if (state.page > 1) { state.page -= 1; loadQuizzes(); }
    });
    document.getElementById('quizNextPage').addEventListener('click', () => {
        state.page += 1; loadQuizzes();
    });

    loadProfessions();
    loadQuizzes();
    loadStats();
})();
