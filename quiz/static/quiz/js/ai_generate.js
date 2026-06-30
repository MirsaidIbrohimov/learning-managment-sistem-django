/**
 * AI-generate page: drives the preview/edit/commit cycle.
 * Backend: POST /api/v1/quiz/questions/ai-preview/  ← reads form, returns draft
 *          POST /api/v1/quiz/questions/ai-commit/   ← saves user-approved batch
 *
 * Defensive design: the preview list is the source of truth. We never trust
 * the server's "_errors" flag at commit time -- the server re-validates --
 * but we do show errors in the UI so the teacher can fix them before saving.
 */
(function () {
    'use strict';

    const app = document.getElementById('aiApp');
    if (!app) return;

    const quizId = app.dataset.quizId || null;
    const lessonTitle = app.dataset.lessonTitle || '';

    const els = {
        topic: document.getElementById('aiTopic'),
        context: document.getElementById('aiContext'),
        count: document.getElementById('aiCount'),
        optionsCount: document.getElementById('aiOptionsCount'),
        type: document.getElementById('aiType'),
        difficulty: document.getElementById('aiDifficulty'),
        generateBtn: document.getElementById('aiGenerateBtn'),
        previewBody: document.getElementById('aiPreviewBody'),
        previewWrap: document.getElementById('aiPreviewWrap'),
        saveBtn: document.getElementById('aiSaveBtn'),
        selectedSummary: document.getElementById('aiSelectedSummary'),
    };
    const cardTpl = document.getElementById('aiPreviewCardTpl');
    const optionTpl = document.getElementById('aiOptionRowTpl');

    let drafts = []; // [{text, type, difficulty, explanation, options:[{text,is_correct}], _errors:[]}]

    const TYPE_LABEL = {
        single_choice: 'Bitta tanlov',
        multiple_choice: "Ko'p tanlov",
        true_false: "To'g'ri / Noto'g'ri",
    };

    // ── Generate ───────────────────────────────────────────────────────────
    els.generateBtn.addEventListener('click', async () => {
        const topic = els.topic.value.trim();
        if (!topic) {
            QuizApi.toast('Mavzu kiritilmagan.', 'error');
            els.topic.focus();
            return;
        }
        const payload = {
            topic,
            context: els.context.value.trim(),
            count: parseInt(els.count.value, 10) || 5,
            options_per_question: parseInt(els.optionsCount.value, 10) || 4,
            question_type: els.type.value,
            difficulty: els.difficulty.value,
        };

        setLoading(true);
        try {
            const data = await QuizApi.post('questions/ai-preview/', payload);
            drafts = (data.questions || []).map(normaliseDraft);
            if (!drafts.length) {
                QuizApi.toast('AI bo\'sh natija qaytardi. Yana urinib ko\'ring.', 'error');
                renderEmpty('Hech narsa qaytmadi.');
                return;
            }
            renderDrafts();
            QuizApi.toast(`${drafts.length} ta savol yaratildi. Ko'rib chiqing va saqlang.`, 'success');
        } catch (e) {
            const errs = e.payload && Array.isArray(e.payload.errors) ? e.payload.errors.join(' ') : e.message;
            QuizApi.toast('Xatolik: ' + errs, 'error');
            renderEmpty(errs);
        } finally {
            setLoading(false);
        }
    });

    // ── Save ───────────────────────────────────────────────────────────────
    els.saveBtn.addEventListener('click', async () => {
        const selected = drafts.filter((d) => d._selected !== false);
        const valid = selected.filter((d) => d._errors.length === 0);
        if (!valid.length) {
            QuizApi.toast("Hech qaysi tanlangan savol to'liq emas. Xatoliklarni tuzating.", 'error');
            return;
        }
        if (selected.length > valid.length) {
            const skipped = selected.length - valid.length;
            const ok = confirm(`${valid.length} ta savol saqlanadi. ${skipped} ta xato bo'lgani uchun o'tkazib yuboriladi. Davom etamizmi?`);
            if (!ok) return;
        }

        const payload = { questions: valid.map(stripDraft) };
        if (quizId) payload.quiz_id = parseInt(quizId, 10);

        els.saveBtn.disabled = true;
        els.saveBtn.innerHTML = '<i class="bi bi-hourglass-split"></i> Saqlanmoqda...';
        try {
            const data = await QuizApi.post('questions/ai-commit/', payload);
            let msg = `${data.created} ta savol bazaga qo'shildi`;
            if (data.attached) msg += `, ${data.attached} tasi testga ulandi`;
            QuizApi.toast(msg + '.', 'success');
            if (data.rejected && data.rejected.length) {
                console.warn('Rejected questions:', data.rejected);
            }
            // Redirect: if we came from a quiz, return to its builder
            setTimeout(() => {
                if (quizId) {
                    window.location.href = `/quiz/quizzes/${quizId}/edit/`;
                } else {
                    window.location.href = '/quiz/questions/';
                }
            }, 800);
        } catch (e) {
            QuizApi.toast('Saqlashda xatolik: ' + e.message, 'error');
            els.saveBtn.disabled = false;
            els.saveBtn.innerHTML = '<i class="bi bi-check2-circle"></i> Tanlanganlarni saqlash';
        }
    });

    // ── Rendering ──────────────────────────────────────────────────────────
    function setLoading(loading) {
        els.generateBtn.disabled = loading;
        els.generateBtn.innerHTML = loading
            ? '<i class="bi bi-hourglass-split"></i> Yaratilmoqda...'
            : '<i class="bi bi-magic"></i> Yaratish';
        if (loading) {
            els.previewBody.innerHTML = `
                <div class="qz-empty">
                    <div class="qz-empty-icon" style="background:linear-gradient(135deg,rgb(255 159 10 / 14%),rgb(245 158 11 / 8%));color:#f59e0b;">
                        <i class="bi bi-cpu"></i>
                    </div>
                    <h4>AI savollar yaratmoqda...</h4>
                    <p>Bu 10-30 soniya davom etishi mumkin.</p>
                </div>`;
        }
    }

    function renderEmpty(msg) {
        drafts = [];
        els.previewBody.innerHTML = `
            <div class="qz-empty">
                <div class="qz-empty-icon" style="background:rgb(239 68 68 / 10%);color:#ef4444;">
                    <i class="bi bi-exclamation-triangle"></i>
                </div>
                <h4>Natija topilmadi</h4>
                <p>${escapeHtml(msg || "Yana urinib ko'ring.")}</p>
            </div>`;
        els.saveBtn.classList.add('d-none');
        els.selectedSummary.classList.add('d-none');
    }

    function renderDrafts() {
        els.previewBody.innerHTML = '';
        drafts.forEach((draft, idx) => {
            const node = cardTpl.content.firstElementChild.cloneNode(true);
            node.dataset.idx = idx;
            mountCard(node, draft, idx);
            els.previewBody.appendChild(node);
        });
        updateSummary();
    }

    function mountCard(node, draft, idx) {
        node.querySelector('.ai-card-num').textContent = String(idx + 1);
        node.querySelector('.ai-card-type').textContent = TYPE_LABEL[draft.type] || draft.type;
        const textArea = node.querySelector('.ai-card-text');
        textArea.value = draft.text;
        textArea.addEventListener('input', () => {
            draft.text = textArea.value;
            revalidateAndPaint(node, draft);
        });

        const explanation = node.querySelector('.ai-card-explanation');
        explanation.value = draft.explanation || '';
        explanation.addEventListener('input', () => { draft.explanation = explanation.value; });

        const optionsWrap = node.querySelector('.ai-card-options');
        draft.options.forEach((opt) => optionsWrap.appendChild(buildOptionRow(opt, draft, node)));

        node.querySelector('.ai-card-add-option').addEventListener('click', () => {
            const newOpt = { text: '', is_correct: false };
            draft.options.push(newOpt);
            optionsWrap.appendChild(buildOptionRow(newOpt, draft, node));
            revalidateAndPaint(node, draft);
        });

        const checkbox = node.querySelector('.ai-card-check');
        checkbox.checked = draft._selected !== false;
        checkbox.addEventListener('change', () => {
            draft._selected = checkbox.checked;
            node.style.opacity = checkbox.checked ? '1' : '.5';
            updateSummary();
        });

        node.querySelector('.ai-card-remove').addEventListener('click', () => {
            drafts.splice(idx, 1);
            renderDrafts();
        });

        revalidateAndPaint(node, draft);
    }

    function buildOptionRow(opt, draft, cardNode) {
        const row = optionTpl.content.firstElementChild.cloneNode(true);
        const textInput = row.querySelector('.ai-opt-text');
        const correctCheck = row.querySelector('.ai-opt-correct');
        const removeBtn = row.querySelector('.ai-opt-remove');

        textInput.value = opt.text;
        textInput.addEventListener('input', () => {
            opt.text = textInput.value;
            revalidateAndPaint(cardNode, draft);
        });

        correctCheck.checked = !!opt.is_correct;
        correctCheck.addEventListener('change', () => {
            opt.is_correct = correctCheck.checked;
            // Auto-flip type if user makes it multi-correct in a single_choice
            if (draft.type === 'single_choice' && correctCheck.checked) {
                draft.options.forEach((o) => { if (o !== opt) o.is_correct = false; });
                // Re-render option rows to reflect cleared checks
                Array.from(cardNode.querySelectorAll('.ai-opt-correct')).forEach((cb, i) => {
                    cb.checked = !!draft.options[i].is_correct;
                });
            }
            updateOptionRowStyle(row, opt);
            revalidateAndPaint(cardNode, draft);
        });
        updateOptionRowStyle(row, opt);

        removeBtn.addEventListener('click', () => {
            const i = draft.options.indexOf(opt);
            if (i >= 0) draft.options.splice(i, 1);
            row.remove();
            revalidateAndPaint(cardNode, draft);
        });
        return row;
    }

    function updateOptionRowStyle(row, opt) {
        if (opt.is_correct) row.classList.add('is-correct');
        else row.classList.remove('is-correct');
    }

    function revalidateAndPaint(cardNode, draft) {
        draft._errors = validateDraft(draft);
        const errSpan = cardNode.querySelector('.ai-card-errors');
        if (draft._errors.length) {
            errSpan.textContent = draft._errors[0];
            errSpan.classList.remove('d-none');
            cardNode.style.borderColor = 'rgb(239 68 68 / 35%)';
        } else {
            errSpan.classList.add('d-none');
            cardNode.style.borderColor = '';
        }
        updateSummary();
    }

    function updateSummary() {
        const total = drafts.length;
        const selected = drafts.filter((d) => d._selected !== false);
        const ok = selected.filter((d) => d._errors.length === 0).length;
        els.selectedSummary.textContent = `${ok} / ${selected.length} tanlangan to'g'ri (${total} jami)`;
        els.selectedSummary.classList.toggle('d-none', total === 0);
        els.saveBtn.classList.toggle('d-none', total === 0);
        els.saveBtn.disabled = ok === 0;
    }

    // ── Validation (mirrors quiz/importers.py _validate_row) ──────────────
    function validateDraft(d) {
        const errors = [];
        if (!d.text || !d.text.trim()) errors.push("Savol matni bo'sh.");
        const nonEmpty = d.options.filter((o) => o.text && o.text.trim());
        if (nonEmpty.length < 2) errors.push('Kamida 2 ta variant kerak.');
        const correct = nonEmpty.filter((o) => o.is_correct);
        if (correct.length === 0) errors.push("To'g'ri javob belgilanmagan.");
        if (d.type === 'single_choice' && correct.length > 1) errors.push("Faqat bitta to'g'ri javob bo'lishi kerak.");
        const seen = new Set();
        for (const o of nonEmpty) {
            const t = o.text.trim().toLowerCase();
            if (seen.has(t)) { errors.push('Takror variant bor.'); break; }
            seen.add(t);
        }
        return errors;
    }

    function normaliseDraft(raw) {
        return {
            text: raw.text || '',
            type: raw.type || 'single_choice',
            difficulty: raw.difficulty || 'medium',
            explanation: raw.explanation || '',
            options: (raw.options || []).map((o) => ({
                text: o.text || '',
                is_correct: !!o.is_correct,
            })),
            _errors: Array.isArray(raw._errors) ? raw._errors : [],
            _selected: true,
        };
    }

    function stripDraft(d) {
        return {
            text: d.text,
            type: d.type,
            difficulty: d.difficulty,
            explanation: d.explanation,
            options: d.options.filter((o) => o.text && o.text.trim()),
        };
    }

    function escapeHtml(s) {
        return String(s).replace(/[&<>"']/g, (c) => ({
            '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
        }[c]));
    }

    // Pre-fill topic from lesson title if blank
    if (!els.topic.value && lessonTitle) els.topic.value = lessonTitle;
})();
