/**
 * Question Builder: create/edit a single bank question.
 *
 * The headline feature of the Phase 1 redesign lives here -- answer option
 * rows are a plain JS array rendered into the DOM, with no upper bound, so
 * "exactly 3 options" (the old accounts app) and "exactly 4" (the old
 * teacher app) both go away in favour of "as many as the question needs".
 *
 * Client-side validation intentionally mirrors quiz/serializers.py
 * QUESTION_TYPE_RULES so the user sees the same rule before submitting
 * that the API would otherwise reject after a round trip.
 *
 * Three additions on top of the original Phase 1 builder:
 *  - Quiz-scoped create (data-quiz-id set): saving attaches the new question
 *    to that quiz in the same request and returns to its builder.
 *  - Quick-add mode: after saving a *new* question, the form resets instead
 *    of navigating away, so a teacher can enter several questions back to
 *    back without re-opening the page each time.
 *  - Image upload for the question itself and for individual options. Only
 *    available once a row has a real database id (i.e. after the first
 *    save) -- there's nothing to attach a file to before that, so the
 *    create-mode form shows a "save first" hint instead of a broken control.
 */
(function () {
    'use strict';

    const RULES = {
        single_choice: { requiresOptions: true, minOptions: 2, correctRule: 'exactly_one' },
        true_false: { requiresOptions: true, minOptions: 2, maxOptions: 2, correctRule: 'exactly_one', fixedLabels: ["Töğri", "Notöğri"] },
        multiple_choice: { requiresOptions: true, minOptions: 2, correctRule: 'at_least_one' },
        short_answer: { requiresOptions: false },
        essay: { requiresOptions: false },
    };

    const MAX_IMAGE_SIZE = 5 * 1024 * 1024; // 5 MB — mirrors quiz/views.py MAX_IMAGE_UPLOAD_SIZE

    const app = document.getElementById('qbApp');
    let questionId = app.dataset.questionId || null;
    let isEdit = Boolean(questionId);
    const quizId = app.dataset.quizId || null;

    const els = {
        title: document.getElementById('qbTitle'),
        text: document.getElementById('qbText'),
        explanation: document.getElementById('qbExplanation'),
        type: document.getElementById('qbType'),
        difficulty: document.getElementById('qbDifficulty'),
        points: document.getElementById('qbPoints'),
        status: document.getElementById('qbStatus'),
        saveBtn: document.getElementById('qbSaveBtn'),
        errorSummary: document.getElementById('qbErrorSummary'),
        optionsPanel: document.getElementById('qbOptionsPanel'),
        optionsList: document.getElementById('qbOptionsList'),
        optionsHint: document.getElementById('qbOptionsHint'),
        addOptionBtn: document.getElementById('qbAddOption'),
        shortAnswerPanel: document.getElementById('qbShortAnswerPanel'),
        shortAnswersList: document.getElementById('qbShortAnswersList'),
        addShortAnswerBtn: document.getElementById('qbAddShortAnswer'),
        essayPanel: document.getElementById('qbEssayPanel'),
        quickToggleWrap: document.getElementById('qbQuickToggleWrap'),
        quickMode: document.getElementById('qbQuickMode'),
        quickCounter: document.getElementById('qbQuickCounter'),
        quickFinishBtn: document.getElementById('qbQuickFinishBtn'),
        imageHint: document.getElementById('qbImageHint'),
        imageControl: document.getElementById('qbImageControl'),
        imagePreview: document.getElementById('qbImagePreview'),
        imageUploadBtn: document.getElementById('qbImageUploadBtn'),
        imageRemoveBtn: document.getElementById('qbImageRemoveBtn'),
        imageInput: document.getElementById('qbImageInput'),
    };
    const optionRowTpl = document.getElementById('qbOptionRowTemplate');
    const shortAnswerRowTpl = document.getElementById('qbShortAnswerRowTemplate');

    let options = []; // [{id, text, is_correct, image}] -- id/image only present once persisted
    let quickCount = 0;

    function currentRules() {
        return RULES[els.type.value];
    }

    function addOption(text = '', isCorrect = false) {
        options.push({ text, is_correct: isCorrect });
        renderOptions();
    }

    function removeOption(index) {
        options.splice(index, 1);
        renderOptions();
    }

    function setCorrect(index) {
        const rules = currentRules();
        if (rules.correctRule === 'exactly_one') {
            options = options.map((o, i) => ({ ...o, is_correct: i === index }));
        } else {
            options[index].is_correct = !options[index].is_correct;
        }
        renderOptions();
    }

    function validateImageFile(file) {
        if (!/\.(jpe?g|png)$/i.test(file.name)) {
            return "Faqat .jpg, .jpeg, .png fayllar qabul qilinadi.";
        }
        if (file.size > MAX_IMAGE_SIZE) {
            return "Rasm hajmi 5 MB dan oşmasligi kerak.";
        }
        return null;
    }

    async function uploadOptionImage(opt, file, thumbEl, uploadBtnEl, removeBtnEl) {
        const err = validateImageFile(file);
        if (err) { window.QuizApi.toast(err, 'error'); return; }
        const formData = new FormData();
        formData.append('image', file);
        try {
            const data = await window.QuizApi.upload(`questions/${questionId}/options/${opt.id}/image/`, formData);
            opt.image = data.image;
            thumbEl.src = data.image;
            thumbEl.classList.remove('d-none');
            removeBtnEl.classList.remove('d-none');
            window.QuizApi.toast('Rasm yuklandi.');
        } catch (e) {
            window.QuizApi.toast(e.message, 'error');
        }
    }

    async function removeOptionImage(opt, thumbEl, removeBtnEl) {
        try {
            await window.QuizApi.delete(`questions/${questionId}/options/${opt.id}/image/`);
            opt.image = null;
            thumbEl.src = '';
            thumbEl.classList.add('d-none');
            removeBtnEl.classList.add('d-none');
        } catch (e) {
            window.QuizApi.toast(e.message, 'error');
        }
    }

    function renderOptions() {
        els.optionsList.innerHTML = '';
        const rules = currentRules();
        options.forEach((opt, index) => {
            const node = optionRowTpl.content.cloneNode(true);
            const textInput = node.querySelector('.qb-option-text');
            const checkbox = node.querySelector('.qb-correct-check');
            const removeBtn = node.querySelector('.qb-remove-option');
            const imageBtn = node.querySelector('.qb-option-image-btn');
            const imageRemoveBtn = node.querySelector('.qb-option-image-remove');
            const imageInput = node.querySelector('.qb-option-image-input');
            const thumb = node.querySelector('.qb-option-thumb');

            textInput.value = opt.text;
            textInput.disabled = Boolean(rules.fixedLabels);
            checkbox.checked = opt.is_correct;
            textInput.addEventListener('input', (e) => { options[index].text = e.target.value; });
            checkbox.addEventListener('change', () => setCorrect(index));
            removeBtn.addEventListener('click', () => removeOption(index));
            if (rules.fixedLabels || (rules.maxOptions && options.length <= rules.minOptions)) {
                removeBtn.classList.add('d-none');
            }

            // Image upload needs a real option id to attach the file to --
            // only available once this row has been saved at least once.
            if (isEdit && opt.id) {
                imageBtn.classList.remove('d-none');
                if (opt.image) {
                    thumb.src = opt.image;
                    thumb.classList.remove('d-none');
                    imageRemoveBtn.classList.remove('d-none');
                }
                imageBtn.addEventListener('click', () => imageInput.click());
                imageInput.addEventListener('change', async () => {
                    const file = imageInput.files[0];
                    imageInput.value = '';
                    if (!file) return;
                    await uploadOptionImage(opt, file, thumb, imageBtn, imageRemoveBtn);
                });
                imageRemoveBtn.addEventListener('click', () => removeOptionImage(opt, thumb, imageRemoveBtn));
            }

            els.optionsList.appendChild(node);
        });

        els.addOptionBtn.classList.toggle('d-none', Boolean(rules.fixedLabels));
        const canAddMore = !rules.maxOptions || options.length < rules.maxOptions;
        els.addOptionBtn.disabled = !canAddMore;

        if (rules.correctRule === 'exactly_one') {
            els.optionsHint.textContent = "Faqat bitta variant töğri javob sifatida belgilanişi kerak.";
        } else if (rules.correctRule === 'at_least_one') {
            els.optionsHint.textContent = "Kamida bitta variant töğri javob sifatida belgilanişi kerak.";
        } else {
            els.optionsHint.textContent = '';
        }
    }

    function addShortAnswer(text = '') {
        const node = shortAnswerRowTpl.content.cloneNode(true);
        node.querySelector('.qb-short-answer-text').value = text;
        node.querySelector('.qb-remove-short-answer').addEventListener('click', (e) => {
            e.target.closest('div.d-flex').remove();
        });
        els.shortAnswersList.appendChild(node);
    }

    function getShortAnswers() {
        return Array.from(els.shortAnswersList.querySelectorAll('.qb-short-answer-text'))
            .map((input) => input.value.trim())
            .filter(Boolean);
    }

    function syncPanelsToType() {
        const rules = currentRules();
        els.optionsPanel.closest('.card').classList.toggle('d-none', !rules.requiresOptions);
        els.shortAnswerPanel.classList.toggle('d-none', els.type.value !== 'short_answer');
        els.essayPanel.classList.toggle('d-none', els.type.value !== 'essay');

        if (rules.requiresOptions && options.length === 0) {
            if (rules.fixedLabels) {
                options = rules.fixedLabels.map((label, i) => ({ text: label, is_correct: i === 0 }));
            } else {
                addOption('', false);
                addOption('', false);
                return; // addOption already re-renders
            }
        }
        renderOptions();

        if (els.type.value === 'short_answer' && els.shortAnswersList.children.length === 0) {
            addShortAnswer();
        }
    }

    // ── Question image (edit mode only — needs a saved question id) ───────
    function syncImageBlockVisibility() {
        els.imageHint.classList.toggle('d-none', isEdit);
        els.imageControl.classList.toggle('d-none', !isEdit);
    }

    els.imageUploadBtn.addEventListener('click', () => els.imageInput.click());
    els.imageInput.addEventListener('change', async () => {
        const file = els.imageInput.files[0];
        els.imageInput.value = '';
        if (!file) return;
        const err = validateImageFile(file);
        if (err) { window.QuizApi.toast(err, 'error'); return; }
        const formData = new FormData();
        formData.append('image', file);
        try {
            const data = await window.QuizApi.upload(`questions/${questionId}/image/`, formData);
            els.imagePreview.src = data.image;
            els.imagePreview.classList.remove('d-none');
            els.imageRemoveBtn.classList.remove('d-none');
            window.QuizApi.toast('Rasm yuklandi.');
        } catch (e) {
            window.QuizApi.toast(e.message, 'error');
        }
    });
    els.imageRemoveBtn.addEventListener('click', async () => {
        try {
            await window.QuizApi.delete(`questions/${questionId}/image/`);
            els.imagePreview.src = '';
            els.imagePreview.classList.add('d-none');
            els.imageRemoveBtn.classList.add('d-none');
        } catch (e) {
            window.QuizApi.toast(e.message, 'error');
        }
    });

    // ── Quick-add mode (create-only) ───────────────────────────────────────
    function updateQuickUI() {
        els.quickCounter.textContent = `Qöşildi: ${quickCount}`;
        els.quickCounter.classList.toggle('d-none', quickCount === 0);
        els.quickFinishBtn.classList.toggle('d-none', quickCount === 0);
    }

    function resetFormForNext() {
        els.text.value = '';
        els.explanation.value = '';
        options = [];
        syncPanelsToType();
        els.errorSummary.classList.add('d-none');
        updateQuickUI();
        els.text.focus();
    }

    function backTarget() {
        return quizId ? `/quiz/quizzes/${quizId}/edit/` : '/quiz/questions/';
    }

    if (!isEdit) {
        els.quickToggleWrap.classList.remove('d-none');
        els.quickFinishBtn.addEventListener('click', () => { window.location.href = backTarget(); });
    }

    // ── Build / validate / save ────────────────────────────────────────────
    function buildPayload() {
        const payload = {
            type: els.type.value,
            text: els.text.value.trim(),
            explanation: els.explanation.value.trim(),
            difficulty: els.difficulty.value,
            points_default: Number(els.points.value) || 1,
            status: els.status.value,
        };
        const rules = currentRules();
        if (rules.requiresOptions) {
            payload.options = options
                .map((o, i) => {
                    const row = { text: o.text.trim(), is_correct: o.is_correct, order: i };
                    if (o.id) row.id = o.id;
                    return row;
                })
                .filter((o) => o.text.length > 0);
        } else if (els.type.value === 'short_answer') {
            payload.metadata = { correct_answers: getShortAnswers() };
        }
        if (quizId && !isEdit) payload.quiz_id = Number(quizId);
        return payload;
    }

    function clientSideValidate(payload) {
        if (!payload.text) return "Savol matni böş bölişi mumkin emas.";
        const rules = currentRules();
        if (rules.requiresOptions) {
            if (payload.options.length < rules.minOptions) {
                return `Kamida ${rules.minOptions} ta javob variant kiritilişi kerak.`;
            }
            const correctCount = payload.options.filter((o) => o.is_correct).length;
            if (rules.correctRule === 'exactly_one' && correctCount !== 1) {
                return "Aniq bitta variant töğri javob sifatida belgilanişi kerak.";
            }
            if (rules.correctRule === 'at_least_one' && correctCount < 1) {
                return "Kamida bitta variant töğri javob sifatida belgilanişi kerak.";
            }
            const texts = payload.options.map((o) => o.text.toLowerCase());
            if (new Set(texts).size !== texts.length) {
                return "Javob variantlari takrorlanmasligi kerak.";
            }
        }
        if (els.type.value === 'short_answer' && !(payload.metadata.correct_answers || []).length) {
            return "Kamida bitta töğri javob kiritilişi kerak.";
        }
        return null;
    }

    async function loadExisting() {
        if (!isEdit) return;
        try {
            const question = await window.QuizApi.get(`questions/${questionId}/`);
            els.title.textContent = "Savolni tahrirlaş";
            els.text.value = question.text;
            els.explanation.value = question.explanation || '';
            els.type.value = question.type;
            els.difficulty.value = question.difficulty;
            els.points.value = question.points_default;
            els.status.value = question.status;

            if (RULES[question.type].requiresOptions) {
                options = (question.options || []).map((o) => ({
                    id: o.id, text: o.text, is_correct: o.is_correct, image: o.image || null,
                }));
                renderOptions();
            } else if (question.type === 'short_answer') {
                els.shortAnswersList.innerHTML = '';
                const answers = (question.metadata && question.metadata.correct_answers) || [];
                (answers.length ? answers : ['']).forEach((a) => addShortAnswer(a));
            }
            syncPanelsToType();

            if (question.image) {
                els.imagePreview.src = question.image;
                els.imagePreview.classList.remove('d-none');
                els.imageRemoveBtn.classList.remove('d-none');
            }
        } catch (err) {
            window.QuizApi.toast(err.message, 'error');
        }
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
                await window.QuizApi.patch(`questions/${questionId}/`, payload);
                window.QuizApi.toast('Savol yangilandi.');
                // Options may have been added/removed -- re-sync ids/images
                // from the server response instead of trusting local state.
                await loadExisting();
            } else {
                const created = await window.QuizApi.post('questions/', payload);
                quickCount += 1;
                if (els.quickMode.checked) {
                    const attachedMsg = quizId ? ' va testga qöşildi' : '';
                    window.QuizApi.toast(`Savol saqlandi${attachedMsg} (${quickCount}-ta). Keyingisini kiriting.`);
                    resetFormForNext();
                } else {
                    window.QuizApi.toast(quizId ? "Savol yaratildi va testga qöşildi." : 'Savol yaratildi.');
                    setTimeout(() => {
                        window.location.href = quizId ? backTarget() : `/quiz/questions/${created.id}/edit/`;
                    }, 600);
                    return;
                }
            }
        } catch (err) {
            els.errorSummary.classList.remove('d-none');
            els.errorSummary.textContent = err.message;
        } finally {
            els.saveBtn.disabled = false;
        }
    }

    els.type.addEventListener('change', () => { options = []; syncPanelsToType(); });
    els.addOptionBtn.addEventListener('click', () => addOption());
    els.addShortAnswerBtn.addEventListener('click', () => addShortAnswer());
    els.saveBtn.addEventListener('click', save);

    if (!isEdit && quizId) {
        els.saveBtn.innerHTML = '<i class="bi bi-check2"></i> Saqlaş va testga qöşiş';
    }

    syncImageBlockVisibility();
    if (isEdit) {
        loadExisting();
    } else {
        syncPanelsToType();
    }
})();
