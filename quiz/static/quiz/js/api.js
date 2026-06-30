/**
 * Thin fetch() wrapper for the quiz REST API (/api/v1/quiz/...).
 * Shared by every page module so CSRF handling, JSON parsing, and error
 * shape live in exactly one place (DRY) instead of being copy-pasted into
 * each page's script.
 */
(function (window) {
    'use strict';

    const CSRF_TOKEN = document.querySelector('meta[name="csrf-token"]').content;
    const API_ROOT = '/api/v1/quiz/';

    class ApiError extends Error {
        constructor(message, status, payload) {
            super(message);
            this.status = status;
            this.payload = payload;
        }
    }

    /**
     * @param {string} path - relative to /api/v1/quiz/, e.g. "questions/" or "quizzes/3/publish/"
     * @param {object} [options]
     * @param {string} [options.method]
     * @param {object} [options.body] - plain object, will be JSON-encoded
     */
    async function request(path, options = {}) {
        const { method = 'GET', body } = options;
        const response = await fetch(API_ROOT + path, {
            method,
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': CSRF_TOKEN,
                'X-Requested-With': 'XMLHttpRequest',
            },
            credentials: 'same-origin',
            body: body !== undefined ? JSON.stringify(body) : undefined,
        });

        if (response.status === 204) {
            return null;
        }

        const text = await response.text();
        const data = text ? JSON.parse(text) : null;

        if (!response.ok) {
            const message = summarizeApiError(data) || `So'rov bajarilmadi (${response.status})`;
            throw new ApiError(message, response.status, data);
        }
        return data;
    }

    /** Flattens DRF's {field: [errors]} shape into one readable line. */
    function summarizeApiError(data) {
        if (!data) return null;
        if (typeof data.detail === 'string') return data.detail;
        const parts = [];
        for (const [field, value] of Object.entries(data)) {
            const text = Array.isArray(value) ? value.join(' ') : String(value);
            parts.push(field === 'non_field_errors' ? text : `${field}: ${text}`);
        }
        return parts.join(' | ') || null;
    }

    function toast(message, variant = 'success') {
        const stack = document.getElementById('quizToastStack');
        if (!stack) {
            // eslint-disable-next-line no-alert
            alert(message);
            return;
        }
        const el = document.createElement('div');
        el.className = `quizui-toast quizui-toast-${variant}`;
        el.innerHTML = `<i class="bi ${variant === 'success' ? 'bi-check-circle-fill' : 'bi-exclamation-triangle-fill'}"></i> <span></span>`;
        el.querySelector('span').textContent = message;
        stack.appendChild(el);
        requestAnimationFrame(() => el.classList.add('show'));
        setTimeout(() => {
            el.classList.remove('show');
            setTimeout(() => el.remove(), 250);
        }, 4000);
    }

    window.QuizApi = {
        get: (path) => request(path),
        post: (path, body) => request(path, { method: 'POST', body }),
        patch: (path, body) => request(path, { method: 'PATCH', body }),
        delete: (path) => request(path, { method: 'DELETE' }),
        toast,
        ApiError,
    };
})(window);
