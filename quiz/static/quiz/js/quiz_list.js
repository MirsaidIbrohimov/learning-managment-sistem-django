/**
 * Quiz list page: paginated table with publish/archive/restore actions.
 * Pairs with quiz/templates/quiz/quiz_list.html.
 */
(function () {
    'use strict';

    const STATUS_LABELS = {
        draft: ['Qoralama', 'bg-secondary'],
        published: ['Chop etilgan', 'bg-success'],
        archived: ['Arxivlangan', 'bg-warning text-dark'],
    };

    let page = 1;
    let statusFilter = '';
    let searchQuery = '';
    const tableBody = document.getElementById('quizTableBody');
    const rowTemplate = document.getElementById('quizRowTemplate');
    const resultCount = document.getElementById('quizResultCount');

    const statEls = {
        total: document.getElementById('quizStatTotal'),
        published: document.getElementById('quizStatPublished'),
        draft: document.getElementById('quizStatDraft'),
        archived: document.getElementById('quizStatArchived'),
    };

    async function loadStats() {
        try {
            const data = await window.QuizApi.get('quizzes/stats/');
            if (statEls.total) statEls.total.textContent = data.total;
            if (statEls.published) statEls.published.textContent = data.published;
            if (statEls.draft) statEls.draft.textContent = data.draft;
            if (statEls.archived) statEls.archived.textContent = data.archived;
        } catch (_) { /* stats are decorative, don't break the page */ }
    }

    async function loadQuizzes() {
        tableBody.innerHTML = '<tr><td colspan="6" class="text-center text-muted py-4">Yuklanmoqda...</td></tr>';
        try {
            const data = await window.QuizApi.get(`quizzes/?page=${page}`);
            renderRows(data.results);
            updatePagination(data);
        } catch (err) {
            tableBody.innerHTML = `<tr><td colspan="6" class="text-center text-danger py-4">${err.message}</td></tr>`;
        }
    }

    function renderRows(quizzes) {
        tableBody.innerHTML = '';
        if (!quizzes.length) {
            tableBody.innerHTML = '<tr><td colspan="6" class="text-center text-muted py-4">Hali test yaratilmagan.</td></tr>';
            return;
        }
        for (const quiz of quizzes) {
            const node = rowTemplate.content.cloneNode(true);
            const editLink = node.querySelector('.quiz-edit-link');
            editLink.textContent = quiz.title;
            editLink.href = `/quiz/quizzes/${quiz.id}/edit/`;

            node.querySelector('.quiz-lesson-cell').textContent = quiz.lesson ? `Dars #${quiz.lesson}` : 'Mustaqil test';
            node.querySelector('.quiz-questions-cell').textContent = `${quiz.question_count_actual} ta savol`;
            node.querySelector('.quiz-time-cell').textContent = `${quiz.settings.time_limit_minutes} daqiqa`;

            const [label, cls] = STATUS_LABELS[quiz.status] || [quiz.status, 'bg-secondary'];
            const statusBadge = node.querySelector('.quiz-status-cell');
            statusBadge.textContent = label;
            statusBadge.className = `badge ${cls}`;

            const publishBtn = node.querySelector('.quiz-publish-btn');
            const archiveBtn = node.querySelector('.quiz-archive-btn');
            const restoreBtn = node.querySelector('.quiz-restore-btn');
            publishBtn.classList.toggle('d-none', quiz.status === 'published');
            archiveBtn.classList.toggle('d-none', quiz.status === 'archived');
            restoreBtn.classList.toggle('d-none', quiz.status !== 'archived');

            publishBtn.addEventListener('click', () => transition(quiz.id, 'publish'));
            archiveBtn.addEventListener('click', () => transition(quiz.id, 'archive'));
            restoreBtn.addEventListener('click', () => transition(quiz.id, 'restore'));

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

    function updatePagination(data) {
        const pageSize = 20;
        const start = (page - 1) * pageSize + 1;
        const end = Math.min(page * pageSize, data.count);
        resultCount.textContent = data.count ? `${start}-${end} / ${data.count} ta test` : '';
        document.getElementById('quizPrevPage').disabled = !data.previous;
        document.getElementById('quizNextPage').disabled = !data.next;
    }

    document.getElementById('quizPrevPage').addEventListener('click', () => {
        if (page > 1) { page -= 1; loadQuizzes(); }
    });
    document.getElementById('quizNextPage').addEventListener('click', () => {
        page += 1; loadQuizzes();
    });

    loadQuizzes();
    loadStats();
})();
