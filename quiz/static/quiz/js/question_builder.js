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
 */
(function () {
    'use strict';

    const RULES = {
        single_choice: { requiresOptions: true, minOptions: 2, correctRule: 'exactly_one' },
        true_false: { requiresOptions: true, minOptions: 2, maxOptions: 2, correctRule: 'exactly_one', fixedLabels: ["To'g'ri", "Noto'g'ri"] },
        multiple_choice: { requiresOptions: true, minOptions: 2, correctRule: 'at_least_one' },
        short_answer: { requiresOptions: false },
        essay: { requiresOptions: false },
    };

    const app = document.getElementById('qbApp');
    const questionId = app.dataset.questionId || null;
    const isEdit = Boolean(questionId);

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
    };
    const optionRowTpl = document.getElementById('qbOptionRowTemplate');
    const shortAnswerRowTpl = document.getElementById('qbShortAnswerRowTemplate');

    let options = []; // [{text, is_correct}]

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

    function renderOptions() {
        els.optionsList.innerHTML = '';
        const rules = currentRules();
        options.forEach((opt, index) => {
            const node = optionRowTpl.content.cloneNode(true);
            const textInput = node.querySelector('.qb-option-text');
            const checkbox = node.querySelector('.qb-correct-check');
            const removeBtn = node.querySelector('.qb-remove-option');

            textInput.value = opt.text;
            textInput.disabled = Boolean(rules.fixedLabels);
            checkbox.checked = opt.is_correct;
            textInput.addEventListener('input', (e) => { options[index].text = e.target.value; });
            checkbox.addEventListener('change', () => setCorrect(index));
            removeBtn.addEventListener('click', () => removeOption(index));
            if (rules.fixedLabels || (rules.maxOptions && options.length <= rules.minOptions)) {
                removeBtn.classList.add('d-none');
            }
            els.optionsList.appendChild(node);
        });

        els.addOptionBtn.classList.toggle('d-none', Boolean(rules.fixedLabels));
        const canAddMore = !rules.maxOptions || options.length < rules.maxOptions;
        els.addOptionBtn.disabled = !canAddMore;

        if (rules.correctRule === 'exactly_one') {
            els.optionsHint.textContent = "Faqat bitta variant to'g'ri javob sifatida belgilanishi kerak.";
        } else if (rules.correctRule === 'at_least_one') {
            els.optionsHint.textContent = "Kamida bitta variant to'g'ri javob sifatida belgilanishi kerak.";
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
                .map((o, i) => ({ text: o.text.trim(), is_correct: o.is_correct, order: i }))
                .filter((o) => o.text.length > 0);
        } else if (els.type.value === 'short_answer') {
            payload.metadata = { correct_answers: getShortAnswers() };
        }
        return payload;
    }

    function clientSideValidate(payload) {
        if (!payload.text) return "Savol matni bo'sh bo'lishi mumkin emas.";
        const rules = currentRules();
        if (rules.requiresOptions) {
            if (payload.options.length < rules.minOptions) {
                return `Kamida ${rules.minOptions} ta javob variant kiritilishi kerak.`;
            }
            const correctCount = payload.options.filter((o) => o.is_correct).length;
            if (rules.correctRule === 'exactly_one' && correctCount !== 1) {
                return "Aniq bitta variant to'g'ri javob sifatida belgilanishi kerak.";
            }
            if (rules.correctRule === 'at_least_one' && correctCount < 1) {
                return "Kamida bitta variant to'g'ri javob sifatida belgilanishi kerak.";
            }
            const texts = payload.options.map((o) => o.text.toLowerCase());
            if (new Set(texts).size !== texts.length) {
                return "Javob variantlari takrorlanmasligi kerak.";
            }
        }
        if (els.type.value === 'short_answer' && !(payload.metadata.correct_answers || []).length) {
            return "Kamida bitta to'g'ri javob kiritilishi kerak.";
        }
        return null;
    }

    async function loadExisting() {
        if (!isEdit) return;
        try {
            const question = await window.QuizApi.get(`questions/${questionId}/`);
            els.title.textContent = "Savolni tahrirlash";
            els.text.value = question.text;
            els.explanation.value = question.explanation || '';
            els.type.value = question.type;
            els.difficulty.value = question.difficulty;
            els.points.value = question.points_default;
            els.status.value = question.status;

            if (RULES[question.type].requiresOptions) {
                options = (question.options || []).map((o) => ({ text: o.text, is_correct: o.is_correct }));
                renderOptions();
            } else if (question.type === 'short_answer') {
                els.shortAnswersList.innerHTML = '';
                const answers = (question.metadata && question.metadata.correct_answers) || [];
                (answers.length ? answers : ['']).forEach((a) => addShortAnswer(a));
            }
            syncPanelsToType();
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
            } else {
                const created = await window.QuizApi.post('questions/', payload);
                window.QuizApi.toast('Savol yaratildi.');
                window.location.href = `/quiz/questions/${created.id}/edit/`;
                return;
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

    if (isEdit) {
        loadExisting();
    } else {
        syncPanelsToType();
    }
})();
