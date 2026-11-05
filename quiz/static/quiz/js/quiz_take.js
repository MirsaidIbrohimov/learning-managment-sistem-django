/**
 * Phase 5 student exam-taking page (quiz/quiz_take.html).
 *
 * Drives all three states -- not-started / in-progress / submitted --
 * client-side against the Attempt REST API (/api/v1/quiz/attempts/...)
 * via the shared QuizApi fetch wrapper (quiz/js/api.js). The server only
 * ever supplies the read-only bootstrap context embedded as JSON; every
 * mutation (start, answer, submit) goes through the API so the backend's
 * _finalize_attempt stays the single source of grading truth.
 *
 * Organized as one IIFE with small, single-purpose functions grouped by
 * concern: screens, intro, exam render, question inputs, timer,
 * anti-cheat, result, review.
 */
(function () {
    'use strict';

    const bootstrap = JSON.parse(document.getElementById('quiz-bootstrap').textContent);

    const state = {
        attempt: null,
        currentIndex: 0,
        warningCount: 0,
        timerInterval: null,
        remainingSeconds: 0,
        saveTimers: {},
        cardsByQuestionId: {},
        antiCheatActive: false,
        intersectionObserver: null,
    };

    const el = {
        screens: {
            intro: document.getElementById('screen-intro'),
            exam: document.getElementById('screen-exam'),
            result: document.getElementById('screen-result'),
            review: document.getElementById('screen-review'),
        },
        btnStart: document.getElementById('btnStartExam'),
        introError: document.getElementById('introError'),
        navGrid: document.getElementById('questionNavGrid'),
        questionsContainer: document.getElementById('questionsContainer'),
        progressFill: document.getElementById('examProgressFill'),
        progressLabel: document.getElementById('examProgressLabel'),
        timerValue: document.getElementById('examTimerValue'),
        timerValueMobile: document.getElementById('examTimerValueMobile'),
        timerCapsule: document.getElementById('examTimer'),
        btnSubmit: document.getElementById('btnSubmitExam'),
        btnSubmitMobile: document.getElementById('btnSubmitExamMobile'),
        submitConfirmModal: document.getElementById('submitConfirmModal'),
        btnCancelSubmit: document.getElementById('btnCancelSubmit'),
        btnConfirmSubmit: document.getElementById('btnConfirmSubmit'),
        resultCard: document.getElementById('resultCard'),
        reviewList: document.getElementById('reviewList'),
        btnBackToResult: document.getElementById('btnBackToResult'),
        fullscreenGate: document.getElementById('fullscreenGate'),
        btnReenterFullscreen: document.getElementById('btnReenterFullscreen'),
        watermark: document.getElementById('watermarkOverlay'),
        warningModal: document.getElementById('warningModal'),
        warningModalTitle: document.getElementById('warningModalTitle'),
        warningModalText: document.getElementById('warningModalText'),
        btnAckWarning: document.getElementById('btnAckWarning'),
    };

    // ============================================================ screens
    function showScreen(name) {
        Object.entries(el.screens).forEach(([key, node]) => {
            node.classList.toggle('qt-screen-active', key === name);
            node.hidden = key !== name;
        });
    }

    function createEl(tag, opts) {
        const node = document.createElement(tag);
        const o = opts || {};
        if (o.className) node.className = o.className;
        if (o.text !== undefined) node.textContent = o.text;
        return node;
    }

    function createButton(className, iconClass, text) {
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = className;
        if (iconClass) {
            const icon = document.createElement('i');
            icon.className = iconClass;
            btn.appendChild(icon);
            btn.appendChild(document.createTextNode(' '));
        }
        btn.appendChild(document.createTextNode(text));
        return btn;
    }

    // ============================================================== intro
    function setIntroBusy(busy) {
        el.btnStart.disabled = busy || Boolean(bootstrap.blocked_reason);
    }

    function showIntroError(message) {
        el.introError.textContent = message;
        el.introError.hidden = false;
    }

    async function handleStartClick() {
        el.introError.hidden = true;
        setIntroBusy(true);
        // Request fullscreen NOW — inside the synchronous user-gesture handler.
        // Browsers drop the activation context after the first `await`, so
        // calling requestFullscreen() after the API call would silently fail
        // in Chrome/Edge and show the gate instead of entering exam mode.
        enterFullscreen();
        try {
            const payload = await QuizApi.post('attempts/', { quiz_id: bootstrap.quiz_id });
            enterExam(payload);
        } catch (err) {
            // If the API call fails, exit fullscreen so the user isn't stuck.
            exitFullscreenIfActive();
            if (err && err.status === 402 && err.payload && err.payload.code === 'payment_required') {
                window.location.href = window.QUIZ_RETRY_URL || `/quiz/quizzes/${err.payload.quiz_id}/retry-payment/`;
                return;
            }
            const msg = (err && err.message) || "Testni boşlab bölmadi.";
            // Show error both inline (intro screen) and as a toast (visible from any screen).
            showIntroError(msg);
            QuizApi.toast(msg, 'error');
        } finally {
            setIntroBusy(false);
        }
    }

    async function resumeExistingAttempt(attemptId) {
        // Called automatically at page load (no user gesture), so we do NOT
        // call enterFullscreen() here — the fullscreen gate will show and the
        // student clicks through it with a real gesture.
        setIntroBusy(true);
        try {
            const payload = await QuizApi.get(`attempts/${attemptId}/resume/`);
            if (payload.status === 'in_progress') {
                enterExam(payload);
            }
        } catch (err) {
            showIntroError((err && err.message) || "Davom etayotgan urinişni yuklab bölmadi.");
        } finally {
            setIntroBusy(false);
        }
    }

    // ========================================================= exam render
    function enterExam(attempt) {
        state.attempt = attempt;
        state.currentIndex = 0;
        state.warningCount = 0;
        renderNavGrid();
        renderQuestions();
        updateProgress();
        startTimer(attempt.remaining_seconds);
        showScreen('exam');
        // Register anti-cheat first so fullscreenchange listener is live before
        // the async fullscreen grant (if any) fires its event.
        enableAntiCheat();
        enableWatermark();
        // Show the gate until fullscreen is confirmed. handleFullscreenChange
        // hides it as soon as document.fullscreenElement is set. In the normal
        // handleStartClick path, fullscreen was already requested synchronously
        // (user-gesture context intact), so this resolves almost immediately.
        // In the auto-resume path (page load, no user gesture), the gate stays
        // visible until the student clicks the button.
        el.fullscreenGate.hidden = Boolean(document.fullscreenElement);
    }

    function hasResponse(question) {
        const r = question.saved_response;
        if (!r) return false;
        if (Array.isArray(r.selected_option_ids)) return r.selected_option_ids.length > 0;
        if (typeof r.text === 'string') return r.text.trim().length > 0;
        return false;
    }

    function answeredQuestionIds() {
        return new Set(state.attempt.questions.filter(hasResponse).map((q) => q.id));
    }

    function renderNavGrid() {
        el.navGrid.innerHTML = '';
        state.attempt.questions.forEach((q, i) => {
            const pill = document.createElement('button');
            pill.type = 'button';
            pill.className = 'qt-nav-pill';
            pill.textContent = String(i + 1);
            pill.addEventListener('click', () => jumpToQuestion(i));
            el.navGrid.appendChild(pill);
        });
        refreshNavGrid();
    }

    function refreshNavGrid() {
        const answered = answeredQuestionIds();
        Array.from(el.navGrid.children).forEach((pill, i) => {
            const q = state.attempt.questions[i];
            pill.classList.toggle('qt-nav-answered', answered.has(q.id));
            pill.classList.toggle('qt-nav-current', i === state.currentIndex);
        });
    }

    function jumpToQuestion(index) {
        state.currentIndex = index;
        refreshNavGrid();
        const card = el.questionsContainer.children[index];
        if (card) card.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }

    function updateProgress() {
        const total = state.attempt.questions.length;
        const answered = answeredQuestionIds().size;
        el.progressFill.style.width = total ? `${Math.round((answered / total) * 100)}%` : '0%';
        el.progressLabel.textContent = `${answered} / ${total}`;
    }

    function observeCurrentQuestion() {
        if (state.intersectionObserver) state.intersectionObserver.disconnect();
        state.intersectionObserver = new IntersectionObserver((entries) => {
            const mostVisible = entries
                .filter((entry) => entry.isIntersecting)
                .sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0];
            if (!mostVisible) return;
            const index = Number(mostVisible.target.dataset.index);
            if (!Number.isNaN(index)) {
                state.currentIndex = index;
                refreshNavGrid();
            }
        }, { threshold: [0.5] });
        Array.from(el.questionsContainer.children).forEach((card) => state.intersectionObserver.observe(card));
    }

    // ------------------------------------------------------ question cards
    function renderQuestions() {
        el.questionsContainer.innerHTML = '';
        state.cardsByQuestionId = {};
        state.attempt.questions.forEach((question, index) => {
            const card = buildQuestionCard(question, index);
            state.cardsByQuestionId[question.id] = card;
            el.questionsContainer.appendChild(card);
        });
        observeCurrentQuestion();
    }

    function buildQuestionCard(question, index) {
        const card = document.createElement('article');
        card.className = 'qt-question-card';
        card.dataset.index = String(index);

        const meta = createEl('div', { className: 'qt-question-meta' });
        meta.appendChild(createEl('span', { text: `Savol ${index + 1} / ${state.attempt.questions.length}` }));
        meta.appendChild(createEl('span', { text: `${question.points} ball` }));
        card.appendChild(meta);

        card.appendChild(createEl('p', { className: 'qt-question-text', text: question.text }));

        if (question.image) {
            const img = document.createElement('img');
            img.className = 'qt-question-image';
            img.src = question.image;
            img.alt = '';
            card.appendChild(img);
        }

        card.appendChild(buildAnswerInput(question));

        if (question.hints && question.hints.length) {
            card.appendChild(buildHintToggle(question.hints));
        }

        const indicator = createEl('div', { className: 'qt-save-indicator' });
        indicator.dataset.role = 'save-indicator';
        card.appendChild(indicator);

        return card;
    }

    function buildHintToggle(hints) {
        const wrap = document.createDocumentFragment();
        const btn = createButton('qt-hint-toggle', 'bi bi-lightbulb', 'Maslahat');
        const box = createEl('div', { className: 'qt-hint-box', text: hints.join(' ') });
        btn.addEventListener('click', () => box.classList.toggle('qt-hint-open'));
        wrap.appendChild(btn);
        wrap.appendChild(box);
        return wrap;
    }

    function buildAnswerInput(question) {
        switch (question.type) {
            case 'single_choice':
            case 'true_false':
                return buildChoiceInput(question, 'radio');
            case 'multiple_choice':
                return buildChoiceInput(question, 'checkbox');
            case 'essay':
                return buildTextarea(question);
            case 'short_answer':
            default:
                return buildTextInput(question);
        }
    }

    function buildChoiceInput(question, inputType) {
        const wrap = document.createElement('div');
        wrap.className = 'qt-options';
        const selected = new Set((question.saved_response && question.saved_response.selected_option_ids) || []);

        question.options.forEach((option) => {
            const label = document.createElement('label');
            label.className = 'qt-option';
            if (selected.has(option.id)) label.classList.add('qt-option-selected');

            const input = document.createElement('input');
            input.type = inputType;
            input.name = `q_${question.id}`;
            input.value = String(option.id);
            input.checked = selected.has(option.id);
            input.addEventListener('change', () => handleChoiceChange(question, wrap));

            label.appendChild(input);
            label.appendChild(createEl('span', { className: 'qt-option-text', text: option.text }));
            wrap.appendChild(label);
        });
        return wrap;
    }

    function handleChoiceChange(question, wrap) {
        const checked = Array.from(wrap.querySelectorAll('input:checked')).map((input) => Number(input.value));
        Array.from(wrap.children).forEach((label) => {
            label.classList.toggle('qt-option-selected', label.querySelector('input').checked);
        });
        question.saved_response = { selected_option_ids: checked };
        saveAnswer(question.id, { selected_option_ids: checked });
    }

    function buildTextInput(question) {
        const input = document.createElement('input');
        input.type = 'text';
        input.className = 'qt-text-input';
        input.placeholder = 'Javobingizni yozing...';
        input.value = (question.saved_response && question.saved_response.text) || '';
        input.addEventListener('input', () => debounceSaveText(question, input.value));
        return input;
    }

    function buildTextarea(question) {
        const textarea = document.createElement('textarea');
        textarea.className = 'qt-textarea';
        textarea.placeholder = 'Batafsil javobingizni yozing...';
        textarea.value = (question.saved_response && question.saved_response.text) || '';
        textarea.addEventListener('input', () => debounceSaveText(question, textarea.value));
        return textarea;
    }

    function debounceSaveText(question, text) {
        question.saved_response = { text };
        if (state.saveTimers[question.id]) clearTimeout(state.saveTimers[question.id]);
        state.saveTimers[question.id] = setTimeout(() => saveAnswer(question.id, { text }), 600);
    }

    async function saveAnswer(questionId, response) {
        const card = state.cardsByQuestionId[questionId];
        const indicator = card ? card.querySelector('[data-role="save-indicator"]') : null;
        try {
            await QuizApi.post(`attempts/${state.attempt.id}/answer/`, { question_id: questionId, response });
            if (indicator) {
                indicator.textContent = 'Saqlandi';
                indicator.classList.add('qt-save-ok');
            }
            refreshNavGrid();
            updateProgress();
        } catch (err) {
            if (indicator) {
                indicator.textContent = (err && err.message) || "Saqlanmadi, qayta urinib köring.";
                indicator.classList.remove('qt-save-ok');
            }
        }
    }

    // =============================================================== timer
    function startTimer(remainingSeconds) {
        state.remainingSeconds = remainingSeconds;
        stopTimer();
        renderTimer();
        state.timerInterval = setInterval(() => {
            state.remainingSeconds -= 1;
            if (state.remainingSeconds <= 0) {
                state.remainingSeconds = 0;
                renderTimer();
                stopTimer();
                autoSubmit('Vaqt tugadi, test avtomatik topşirildi.');
                return;
            }
            renderTimer();
        }, 1000);
    }

    function stopTimer() {
        if (state.timerInterval) {
            clearInterval(state.timerInterval);
            state.timerInterval = null;
        }
    }

    function renderTimer() {
        const minutes = Math.floor(state.remainingSeconds / 60);
        const seconds = state.remainingSeconds % 60;
        const text = `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
        el.timerValue.textContent = text;
        el.timerValueMobile.textContent = text;
        el.timerCapsule.classList.toggle('qt-timer-warning', state.remainingSeconds <= 120 && state.remainingSeconds > 30);
        el.timerCapsule.classList.toggle('qt-timer-danger', state.remainingSeconds <= 30);
    }

    // ============================================================== submit
    function openSubmitConfirm() {
        el.submitConfirmModal.hidden = false;
    }

    function closeSubmitConfirm() {
        el.submitConfirmModal.hidden = true;
    }

    async function confirmSubmit() {
        closeSubmitConfirm();
        await doSubmit();
    }

    async function doSubmit() {
        stopTimer();
        try {
            const result = await QuizApi.post(`attempts/${state.attempt.id}/submit/`, {});
            exitExam();
            renderResult(result);
        } catch (err) {
            // A failed submit must not strand the student with a dead timer
            // -- resume it so they can retry instead of losing the attempt.
            QuizApi.toast((err && err.message) || "Topşirib bölmadi, qayta urinib köring.", 'error');
            startTimer(state.remainingSeconds);
        }
    }

    async function autoSubmit(reason) {
        QuizApi.toast(reason, 'error');
        await doSubmit();
    }

    function exitExam() {
        disableAntiCheat();
        disableWatermark();
        exitFullscreenIfActive();
        el.fullscreenGate.hidden = true;
    }

    // ========================================================== anti-cheat
    function enableAntiCheat() {
        state.antiCheatActive = true;
        document.addEventListener('visibilitychange', handleVisibilityChange);
        window.addEventListener('blur', handleWindowBlur);
        document.addEventListener('fullscreenchange', handleFullscreenChange);
        document.addEventListener('keydown', handleKeydown, true);
        document.addEventListener('contextmenu', blockIfActive);
        document.addEventListener('copy', blockIfActive);
        document.addEventListener('cut', blockIfActive);
        document.addEventListener('paste', blockIfActive);
    }

    function disableAntiCheat() {
        state.antiCheatActive = false;
        document.removeEventListener('visibilitychange', handleVisibilityChange);
        window.removeEventListener('blur', handleWindowBlur);
        document.removeEventListener('fullscreenchange', handleFullscreenChange);
        document.removeEventListener('keydown', handleKeydown, true);
        document.removeEventListener('contextmenu', blockIfActive);
        document.removeEventListener('copy', blockIfActive);
        document.removeEventListener('cut', blockIfActive);
        document.removeEventListener('paste', blockIfActive);
    }

    function blockIfActive(event) {
        if (state.antiCheatActive) event.preventDefault();
    }

    function handleVisibilityChange() {
        if (state.antiCheatActive && document.hidden) {
            registerStrike("Boşqa oyna yoki tabga ötdingiz.");
        }
    }

    function handleWindowBlur() {
        if (state.antiCheatActive) registerStrike("Sahifadan e'tiboringiz çalğidi.");
    }

    function handleFullscreenChange() {
        if (!state.antiCheatActive) return;
        el.fullscreenGate.hidden = Boolean(document.fullscreenElement);
    }

    const BLOCKED_KEYS = new Set(['F12', 'F11', 'PrintScreen']);

    function handleKeydown(event) {
        if (!state.antiCheatActive) return;
        const key = event.key.toUpperCase();
        const isBlockedCombo =
            BLOCKED_KEYS.has(event.key) ||
            (event.ctrlKey && event.shiftKey && ['I', 'J', 'C'].includes(key)) ||
            (event.ctrlKey && ['U', 'S', 'P'].includes(key));
        if (isBlockedCombo) {
            event.preventDefault();
            registerStrike("Ruxsat etilmagan tugmalar birikmasi işlatildi.");
        }
    }

    function registerStrike(message) {
        state.warningCount += 1;
        if (state.warningCount >= 3) {
            showWarningModal('Test avtomatik topşirildi', 'Qoidalar 3 marta buzildi, şuning uçun test avtomatik topşirildi.');
            autoSubmit('Qoidabuzarlik tufayli test avtomatik topşirildi.');
            return;
        }
        const remaining = 3 - state.warningCount;
        showWarningModal(`Ogohlantiriş (${state.warningCount}/3)`, `${message} Yana ${remaining} marta buzilsa, test avtomatik topşiriladi.`);
    }

    function showWarningModal(title, text) {
        el.warningModalTitle.textContent = title;
        el.warningModalText.textContent = text;
        el.warningModal.hidden = false;
    }

    function enterFullscreen() {
        const root = document.documentElement;
        const request = root.requestFullscreen || root.webkitRequestFullscreen || root.msRequestFullscreen;
        if (!request) {
            // Fullscreen API not supported — hide gate and let student proceed.
            el.fullscreenGate.hidden = true;
            return;
        }
        request.call(root).then(() => {
            // Grant confirmed: hide gate immediately rather than waiting for
            // the fullscreenchange event (which fires asynchronously and can
            // cause a visible flicker on slow machines).
            el.fullscreenGate.hidden = true;
        }).catch(() => {
            // Browser refused (e.g. sandboxed iframe, security policy): show
            // gate so the student sees a clear message and can retry.
            el.fullscreenGate.hidden = false;
        });
    }

    function exitFullscreenIfActive() {
        if (document.fullscreenElement) {
            document.exitFullscreen().catch(() => {});
        }
    }

    function enableWatermark() {
        el.watermark.innerHTML = '';
        const label = `${bootstrap.student_name} · ${new Date().toLocaleDateString('uz-UZ')}`;
        for (let i = 0; i < 40; i += 1) {
            el.watermark.appendChild(createEl('span', { text: label }));
        }
        el.watermark.classList.add('qt-watermark-on');
    }

    function disableWatermark() {
        el.watermark.classList.remove('qt-watermark-on');
    }

    // =============================================================== result
    function renderResult(attempt) {
        state.attempt = attempt;
        el.resultCard.innerHTML = '';

        // status stays 'submitted' (not 'graded') while the quiz has an
        // essay question -- _finalize_attempt computes score/passed from
        // the auto-gradable questions only, so that figure is provisional
        // until a teacher grades the essay portion. Say so plainly instead
        // of presenting a partial score as the final verdict.
        const isPending = attempt.status === 'submitted';

        const scoreCircle = createEl('div', { className: `qt-result-score ${attempt.passed ? '' : 'qt-result-fail'}` });
        scoreCircle.appendChild(document.createTextNode(String(attempt.score)));
        scoreCircle.appendChild(createEl('span', { text: '%' }));
        el.resultCard.appendChild(scoreCircle);

        let title = attempt.passed ? "Tabriklaymiz, testdan ötdingiz!" : "Afsuski, testdan öta olmadingiz.";
        if (isPending) title = 'Test topşirildi';
        el.resultCard.appendChild(createEl('h2', { className: 'qt-result-title', text: title }));
        el.resultCard.appendChild(createEl('p', {
            className: 'qt-result-sub',
            text: `${attempt.correct_count} / ${attempt.total_questions} avtomatik baholanadigan savolga töğri javob berdingiz.`,
        }));

        if (attempt.coin_awarded && attempt.coins_earned > 0) {
            const rate = bootstrap.coin_per_correct;
            const bonus = attempt.passed ? ` + ${bootstrap.coin_pass_bonus} coin ötganlik bonusi` : '';
            const coinMsg = createEl('p', { className: 'qt-result-coin' });
            coinMsg.innerHTML = `<i class="bi bi-coin"></i> <strong>+${attempt.coins_earned} coin</strong> qölga kiritdingiz! (${attempt.correct_count} ta töğri × ${rate} coin${bonus})`;
            el.resultCard.appendChild(coinMsg);
        } else if (isPending) {
            el.resultCard.appendChild(createEl('p', {
                className: 'qt-result-sub',
                text: "Bu testda yozma javob mavjud -- yakuniy natija va coin öqituvçi tekşirib çiqgunga qadar kutilmoqda.",
            }));
        } else if (!attempt.coin_awarded && attempt.passed && attempt.attempt_number > 1) {
            el.resultCard.appendChild(createEl('p', {
                className: 'qt-result-sub',
                text: "Coin faqat birinçi muvaffaqiyatli urinişda beriladi.",
            }));
        }

        const actions = createEl('div', { className: 'qt-result-actions' });
        const btnReview = createButton('qt-btn qt-btn-primary', 'bi bi-eye', "Javoblarni köriş");
        btnReview.addEventListener('click', loadReview);
        actions.appendChild(btnReview);

        // retry_payment_required quizzes bypass allow_retry entirely (see
        // AttemptViewSet.create()) -- unlimited retries are always allowed
        // there, each gated on its own approved QuizRetryPayment instead.
        if (bootstrap.allow_retry || bootstrap.retry_payment_required) {
            let retryLabel, retryIcon;
            if (bootstrap.retry_payment_required) {
                retryLabel = "Qayta uriniş (tölov)";
                retryIcon = 'bi bi-credit-card-2-front';
            } else {
                retryLabel = `Qayta uriniş (${bootstrap.retry_cost} coin)`;
                retryIcon = 'bi bi-arrow-repeat';
            }
            const btnRetry = createButton('qt-btn qt-btn-ghost', retryIcon, retryLabel);
            btnRetry.addEventListener('click', handleStartClick);
            actions.appendChild(btnRetry);
        }

        const btnBack = createButton('qt-btn qt-btn-ghost', 'bi bi-arrow-left', 'Orqaga');
        btnBack.addEventListener('click', () => history.back());
        actions.appendChild(btnBack);

        el.resultCard.appendChild(actions);
        showScreen('result');
    }

    // =============================================================== review
    async function loadReview() {
        try {
            const payload = await QuizApi.get(`attempts/${state.attempt.id}/review/`);
            renderReview(payload);
        } catch (err) {
            QuizApi.toast((err && err.message) || "Tafsilotlarni yuklab bölmadi.", 'error');
        }
    }

    function renderReview(payload) {
        el.reviewList.innerHTML = '';
        payload.questions.forEach((question, index) => {
            el.reviewList.appendChild(buildReviewItem(question, index));
        });
        showScreen('review');
    }

    function buildReviewItem(question, index) {
        const correct = question.is_correct;
        const statusClass = correct === true ? 'qt-review-correct' : correct === false ? 'qt-review-incorrect' : '';
        const item = createEl('div', { className: `qt-review-item ${statusClass}` });
        item.appendChild(createEl('p', { className: 'qt-review-q', text: `${index + 1}. ${question.text}` }));
        item.appendChild(buildAnswerRow('Sizning javobingiz: ', describeResponse(question) || '(javob berilmagan)', correct));

        if (correct === false) {
            item.appendChild(buildAnswerRow("Töğri javob: ", describeCorrectAnswer(question), true));
        }

        const note = question.feedback || question.explanation;
        if (note) {
            const prefix = question.feedback ? "Öqituvçi izohi: " : '';
            item.appendChild(createEl('p', { className: 'qt-review-explanation', text: `${prefix}${note}` }));
        }
        return item;
    }

    function buildAnswerRow(label, value, isCorrectValue) {
        const row = createEl('p', { className: 'qt-review-answer' });
        row.appendChild(createEl('span', { className: 'qt-review-answer-label', text: label }));
        const valueClass = isCorrectValue === true ? 'qt-review-correct-text' : isCorrectValue === false ? 'qt-review-incorrect-text' : '';
        row.appendChild(createEl('span', { className: valueClass, text: value }));
        return row;
    }

    function describeResponse(question) {
        const response = question.response;
        if (!response) return '';
        if (Array.isArray(response.selected_option_ids)) {
            const ids = new Set(response.selected_option_ids);
            return question.options.filter((o) => ids.has(o.id)).map((o) => o.text).join(', ');
        }
        if (typeof response.text === 'string') return response.text;
        return '';
    }

    function describeCorrectAnswer(question) {
        const correctOptions = question.options.filter((o) => o.is_correct);
        if (correctOptions.length) return correctOptions.map((o) => o.text).join(', ');
        if (question.correct_answers && question.correct_answers.length) return question.correct_answers.join(' / ');
        return question.explanation || '—';
    }

    // ================================================================= init
    function init() {
        el.btnStart.addEventListener('click', handleStartClick);
        el.btnSubmit.addEventListener('click', openSubmitConfirm);
        el.btnSubmitMobile.addEventListener('click', openSubmitConfirm);
        el.btnCancelSubmit.addEventListener('click', closeSubmitConfirm);
        el.btnConfirmSubmit.addEventListener('click', confirmSubmit);
        el.btnBackToResult.addEventListener('click', () => showScreen('result'));
        el.btnReenterFullscreen.addEventListener('click', enterFullscreen);
        el.btnAckWarning.addEventListener('click', () => { el.warningModal.hidden = true; });

        if (bootstrap.resume_attempt_id) {
            resumeExistingAttempt(bootstrap.resume_attempt_id);
        }
    }

    document.addEventListener('DOMContentLoaded', init);
})();
