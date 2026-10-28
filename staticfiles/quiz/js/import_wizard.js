/**
 * Import wizard: upload → preview → commit.
 * Backend: POST /api/v1/quiz/questions/import-preview/  (multipart, returns parsed rows + errors)
 *          POST /api/v1/quiz/questions/import-commit/   (JSON, persists approved rows)
 *
 * The preview step is the user's safety net -- they see exactly what would
 * be created, which rows fail validation, and can opt-out per row.
 */
(function () {
    'use strict';

    const app = document.getElementById('impApp');
    if (!app) return;

    const quizId = app.dataset.quizId || null;

    const els = {
        step1: document.getElementById('impStep1'),
        step2: document.getElementById('impStep2'),
        step3: document.getElementById('impStep3'),
        stage1: document.getElementById('impStage1'),
        stage2: document.getElementById('impStage2'),
        stage3: document.getElementById('impStage3'),
        drop: document.getElementById('impDrop'),
        file: document.getElementById('impFile'),
        previewFile: document.getElementById('impPreviewFile'),
        previewList: document.getElementById('impPreviewList'),
        statOk: document.getElementById('impStatOk'),
        statErr: document.getElementById('impStatErr'),
        reset: document.getElementById('impReset'),
        commitBtn: document.getElementById('impCommitBtn'),
        resultTitle: document.getElementById('impResultTitle'),
        resultMsg: document.getElementById('impResultMsg'),
    };
    const rowTpl = document.getElementById('impRowTpl');

    const CSRF = document.querySelector('meta[name="csrf-token"]').content;
    const TYPE_LABEL = {
        single_choice: 'Bitta tanlov',
        multiple_choice: "Köp tanlov",
        true_false: "Töğri / Notöğri",
    };

    let rows = [];      // [{...row, _selected: true|false}]
    let filename = '';

    // ── Drag-and-drop wiring ──────────────────────────────────────────────
    els.drop.addEventListener('click', () => els.file.click());
    els.drop.addEventListener('dragover', (e) => { e.preventDefault(); els.drop.classList.add('dragover'); });
    els.drop.addEventListener('dragleave', () => els.drop.classList.remove('dragover'));
    els.drop.addEventListener('drop', (e) => {
        e.preventDefault();
        els.drop.classList.remove('dragover');
        if (e.dataTransfer.files.length) {
            els.file.files = e.dataTransfer.files;
            handleFile(e.dataTransfer.files[0]);
        }
    });
    els.file.addEventListener('change', () => {
        if (els.file.files.length) handleFile(els.file.files[0]);
    });

    // ── Reset ──────────────────────────────────────────────────────────────
    els.reset.addEventListener('click', () => {
        els.file.value = '';
        rows = [];
        showStage(1);
    });

    // ── Commit ─────────────────────────────────────────────────────────────
    els.commitBtn.addEventListener('click', async () => {
        const selected = rows.filter((r) => r._selected !== false && (r._errors || []).length === 0);
        if (!selected.length) {
            QuizApi.toast("Heç qaysi qator töğri va tanlangan emas.", 'error');
            return;
        }
        const payload = { questions: selected.map(stripRow) };
        if (quizId) payload.quiz_id = parseInt(quizId, 10);

        els.commitBtn.disabled = true;
        els.commitBtn.innerHTML = '<i class="bi bi-hourglass-split"></i> Saqlanmoqda...';
        try {
            const data = await QuizApi.post('questions/import-commit/', payload);
            els.resultTitle.textContent = data.created > 0 ? 'Saqlandi!' : "Heç narsa saqlanmadi";
            let msg = `${data.created} ta savol bazaga qöşildi`;
            if (data.attached) msg += `, ${data.attached} tasi testga ulandi`;
            msg += '.';
            if (data.rejected && data.rejected.length) {
                msg += ` ${data.rejected.length} ta xato bölgani uçun ötkazib yuborildi.`;
            }
            els.resultMsg.textContent = msg;
            showStage(3);
        } catch (e) {
            QuizApi.toast('Saqlaşda xatolik: ' + e.message, 'error');
            els.commitBtn.disabled = false;
            els.commitBtn.innerHTML = '<i class="bi bi-check2-circle"></i> Töğrilarni saqlaş';
        }
    });

    // ── File handling ──────────────────────────────────────────────────────
    async function handleFile(file) {
        if (!file) return;
        const lower = file.name.toLowerCase();
        if (!/\.(xlsx|csv|json)$/i.test(lower)) {
            QuizApi.toast('Faqat .xlsx, .csv yoki .json qabul qilinadi.', 'error');
            return;
        }
        if (file.size > 5 * 1024 * 1024) {
            QuizApi.toast("Fayl 5 MB dan kiçik bölişi kerak.", 'error');
            return;
        }
        filename = file.name;
        els.drop.style.opacity = '.6';
        try {
            const formData = new FormData();
            formData.append('file', file);
            const response = await fetch('/api/v1/quiz/questions/import-preview/', {
                method: 'POST',
                headers: { 'X-CSRFToken': CSRF, 'X-Requested-With': 'XMLHttpRequest' },
                credentials: 'same-origin',
                body: formData,
            });
            const data = await response.json();
            if (!response.ok) {
                const errs = Array.isArray(data.errors) ? data.errors.join(' ') : (data.detail || `Xatolik (${response.status})`);
                QuizApi.toast(errs, 'error');
                els.drop.style.opacity = '1';
                return;
            }
            rows = (data.questions || []).map((r) => Object.assign({}, r, { _selected: (r._errors || []).length === 0 }));
            els.previewFile.textContent = data.source_filename || filename;
            renderPreview();
            showStage(2);
        } catch (e) {
            QuizApi.toast("Yuklaşda xatolik: " + e.message, 'error');
            els.drop.style.opacity = '1';
        }
    }

    function renderPreview() {
        els.previewList.innerHTML = '';
        rows.forEach((row, idx) => {
            const node = rowTpl.content.firstElementChild.cloneNode(true);
            mountRow(node, row, idx);
            els.previewList.appendChild(node);
        });
        updateStats();
    }

    function mountRow(node, row, idx) {
        node.querySelector('.imp-row-no').textContent = row._row || (idx + 1);
        node.querySelector('.imp-row-text').textContent = row.text || '(böş)';

        const opts = node.querySelector('.imp-row-options');
        opts.innerHTML = '';
        (row.options || []).forEach((o) => {
            const span = document.createElement('span');
            span.className = 'imp-row-opt' + (o.is_correct ? ' correct' : '');
            span.textContent = (o.is_correct ? '✓ ' : '○ ') + (o.text || '(böş)');
            opts.appendChild(span);
        });

        const meta = node.querySelector('.imp-row-meta');
        meta.innerHTML = '';
        const typeBadge = document.createElement('span');
        typeBadge.className = 'qz-badge info';
        typeBadge.textContent = TYPE_LABEL[row.type] || row.type;
        meta.appendChild(typeBadge);
        const diffBadge = document.createElement('span');
        diffBadge.className = 'qz-badge muted';
        diffBadge.textContent = row.difficulty || 'medium';
        meta.appendChild(diffBadge);

        const errs = row._errors || [];
        const errDiv = node.querySelector('.imp-row-errors');
        if (errs.length) {
            node.classList.add('has-error');
            errDiv.innerHTML = errs.map((e) => `<div><i class="bi bi-exclamation-triangle-fill"></i> ${escapeHtml(e)}</div>`).join('');
            errDiv.classList.remove('d-none');
            row._selected = false;
        }

        node.querySelector('.imp-row-skip').addEventListener('click', () => {
            const i = rows.indexOf(row);
            if (i >= 0) rows.splice(i, 1);
            node.remove();
            updateStats();
        });
    }

    function updateStats() {
        const okCount = rows.filter((r) => (r._errors || []).length === 0).length;
        const errCount = rows.length - okCount;
        if (okCount) {
            els.statOk.textContent = `${okCount} ta töğri`;
            els.statOk.classList.remove('d-none');
        } else {
            els.statOk.classList.add('d-none');
        }
        if (errCount) {
            els.statErr.textContent = `${errCount} ta xato`;
            els.statErr.classList.remove('d-none');
        } else {
            els.statErr.classList.add('d-none');
        }
        els.commitBtn.disabled = okCount === 0;
    }

    function stripRow(r) {
        return {
            text: r.text,
            type: r.type,
            difficulty: r.difficulty,
            explanation: r.explanation,
            options: (r.options || []).filter((o) => o.text && o.text.trim()),
        };
    }

    function showStage(n) {
        els.stage1.classList.toggle('d-none', n !== 1);
        els.stage2.classList.toggle('d-none', n !== 2);
        els.stage3.classList.toggle('d-none', n !== 3);
        [els.step1, els.step2, els.step3].forEach((s, i) => {
            s.classList.remove('active', 'done');
            if (i + 1 < n) s.classList.add('done');
            else if (i + 1 === n) s.classList.add('active');
        });
        if (n === 1) {
            els.drop.style.opacity = '1';
            els.commitBtn.disabled = false;
            els.commitBtn.innerHTML = '<i class="bi bi-check2-circle"></i> Töğrilarni saqlaş';
        }
    }

    function escapeHtml(s) {
        return String(s).replace(/[&<>"']/g, (c) => ({
            '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
        }[c]));
    }
})();
