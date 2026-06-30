/**
 * Question Bank list page: search/filter/paginate the question bank,
 * bulk archive/delete, duplicate, and link out to the builder for
 * create/edit. Pairs with quiz/templates/quiz/question_bank.html.
 */
(function () {
    'use strict';

    const TYPE_LABELS = {
        single_choice: 'Bitta tanlov',
        multiple_choice: "Ko'p tanlov",
        true_false: "To'g'ri/Noto'g'ri",
        short_answer: 'Qisqa javob',
        essay: 'Esse',
    };
    const STATUS_LABELS = {
        draft: ['Qoralama', 'bg-secondary'],
        published: ['Chop etilgan', 'bg-success'],
        archived: ['Arxivlangan', 'bg-warning text-dark'],
    };

    const state = { page: 1, search: '', type: '', status: '' };
    let debounceTimer = null;

    const tableBody = document.getElementById('qTableBody');
    const rowTemplate = document.getElementById('qRowTemplate');
    const resultCount = document.getElementById('qResultCount');
    const selectAll = document.getElementById('qSelectAll');
    const bulkArchiveBtn = document.getElementById('qBulkArchive');
    const bulkDeleteBtn = document.getElementById('qBulkDelete');

    function buildQuery() {
        const params = new URLSearchParams({ page: state.page });
        if (state.search) params.set('search', state.search);
        if (state.type) params.set('type', state.type);
        if (state.status) params.set('status', state.status);
        return params.toString();
    }

    async function loadQuestions() {
        tableBody.innerHTML = '<tr><td colspan="7" class="text-center text-muted py-4">Yuklanmoqda...</td></tr>';
        try {
            const data = await window.QuizApi.get(`questions/?${buildQuery()}`);
            renderRows(data.results);
            updatePagination(data);
        } catch (err) {
            tableBody.innerHTML = `<tr><td colspan="7" class="text-center text-danger py-4">${err.message}</td></tr>`;
        }
    }

    function renderRows(questions) {
        tableBody.innerHTML = '';
        if (!questions.length) {
            tableBody.innerHTML = '<tr><td colspan="7" class="text-center text-muted py-4">Savollar topilmadi.</td></tr>';
            return;
        }
        for (const question of questions) {
            const row = rowTemplate.content.cloneNode(true);
            const tr = row.querySelector('tr');
            tr.dataset.id = question.id;

            row.querySelector('.q-text-cell').textContent = question.text;
            const typeBadge = row.querySelector('.q-type-cell');
            typeBadge.textContent = TYPE_LABELS[question.type] || question.type;

            row.querySelector('.q-difficulty-cell').textContent =
                { easy: 'Oson', medium: "O'rta", hard: 'Qiyin' }[question.difficulty] || question.difficulty;

            const [label, cls] = STATUS_LABELS[question.status] || [question.status, 'bg-secondary'];
            const statusBadge = row.querySelector('.q-status-cell');
            statusBadge.textContent = label;
            statusBadge.className = `badge ${cls}`;

            row.querySelector('.q-usage-cell').textContent = `${question.usage_count}x ishlatilgan`;
            row.querySelector('.q-edit-link').href = `/quiz/questions/${question.id}/edit/`;
            row.querySelector('.q-duplicate-btn').addEventListener('click', () => duplicateQuestion(question.id));

            tableBody.appendChild(row);
        }
        refreshBulkButtons();
    }

    function updatePagination(data) {
        const pageSize = 20;
        const start = (state.page - 1) * pageSize + 1;
        const end = Math.min(state.page * pageSize, data.count);
        resultCount.textContent = data.count ? `${start}-${end} / ${data.count} ta savol` : '';
        document.getElementById('qPrevPage').disabled = !data.previous;
        document.getElementById('qNextPage').disabled = !data.next;
    }

    async function duplicateQuestion(id) {
        try {
            await window.QuizApi.post(`questions/${id}/duplicate/`);
            window.QuizApi.toast("Savol nusxalandi.");
            loadQuestions();
        } catch (err) {
            window.QuizApi.toast(err.message, 'error');
        }
    }

    function selectedIds() {
        return Array.from(tableBody.querySelectorAll('.q-row-check:checked')).map(
            (cb) => Number(cb.closest('tr').dataset.id)
        );
    }

    function refreshBulkButtons() {
        const hasSelection = selectedIds().length > 0;
        bulkArchiveBtn.disabled = !hasSelection;
        bulkDeleteBtn.disabled = !hasSelection;
    }

    tableBody.addEventListener('change', (e) => {
        if (e.target.classList.contains('q-row-check')) refreshBulkButtons();
    });

    selectAll.addEventListener('change', () => {
        tableBody.querySelectorAll('.q-row-check').forEach((cb) => { cb.checked = selectAll.checked; });
        refreshBulkButtons();
    });

    bulkArchiveBtn.addEventListener('click', async () => {
        const ids = selectedIds();
        if (!ids.length || !confirm(`${ids.length} ta savolni arxivlashni tasdiqlaysizmi?`)) return;
        try {
            await window.QuizApi.post('questions/bulk-update-status/', { ids, status: 'archived' });
            window.QuizApi.toast('Tanlangan savollar arxivlandi.');
            loadQuestions();
        } catch (err) {
            window.QuizApi.toast(err.message, 'error');
        }
    });

    bulkDeleteBtn.addEventListener('click', async () => {
        const ids = selectedIds();
        if (!ids.length || !confirm(`${ids.length} ta savolni butunlay o'chirishni tasdiqlaysizmi? Bu amalni qaytarib bo'lmaydi.`)) return;
        try {
            await window.QuizApi.post('questions/bulk-delete/', { ids });
            window.QuizApi.toast('Tanlangan savollar o\'chirildi.');
            loadQuestions();
        } catch (err) {
            window.QuizApi.toast(err.message, 'error');
        }
    });

    document.getElementById('qSearch').addEventListener('input', (e) => {
        clearTimeout(debounceTimer);
        debounceTimer = setTimeout(() => {
            state.search = e.target.value.trim();
            state.page = 1;
            loadQuestions();
        }, 300);
    });
    document.getElementById('qTypeFilter').addEventListener('change', (e) => {
        state.type = e.target.value;
        state.page = 1;
        loadQuestions();
    });
    document.getElementById('qStatusFilter').addEventListener('change', (e) => {
        state.status = e.target.value;
        state.page = 1;
        loadQuestions();
    });
    document.getElementById('qPrevPage').addEventListener('click', () => {
        if (state.page > 1) { state.page -= 1; loadQuestions(); }
    });
    document.getElementById('qNextPage').addEventListener('click', () => {
        state.page += 1; loadQuestions();
    });

    async function loadStats() {
        try {
            const data = await window.QuizApi.get('questions/stats/');
            document.getElementById('qStatTotal').textContent    = data.total     ?? '—';
            document.getElementById('qStatPublished').textContent = data.published ?? '—';
            document.getElementById('qStatDraft').textContent    = data.draft      ?? '—';
            document.getElementById('qStatArchived').textContent  = data.archived   ?? '—';
        } catch (_) {
            // leave placeholders as-is on error
        }
    }

    loadStats();
    loadQuestions();
})();
