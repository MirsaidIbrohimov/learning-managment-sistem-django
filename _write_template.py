#!/usr/bin/env python
# Temporary script to write the template file
import os

content = """{% extends 'accounts/base.html' %}

{% block title %}{{ dictionary.lesson.title }} - So'zlar boshqaruvi{% endblock %}

{% block extra_css %}
<style>
:root {
    --md-bg: #f2f2f7;
    --md-card: rgba(255,255,255,0.85);
    --md-border: rgba(0,0,0,0.06);
    --md-text: #1d1d1f;
    --md-secondary: #86868b;
    --md-accent: #8b5cf6;
    --md-accent-light: rgba(139,92,246,0.08);
    --md-success: #34c759;
    --md-danger: #ff3b30;
    --md-shadow: 0 8px 30px rgba(0,0,0,0.08);
}
[data-bs-theme="dark"] {
    --md-bg: #000000;
    --md-card: rgba(28,28,30,0.85);
    --md-border: rgba(255,255,255,0.08);
    --md-text: #f5f5f7;
    --md-secondary: #98989d;
    --md-accent-light: rgba(139,92,246,0.18);
    --md-shadow: 0 8px 30px rgba(0,0,0,0.3);
}

.md-page { max-width: 960px; margin: 0 auto; padding: 1.5rem 1rem 3rem; }

.md-back {
    display: inline-flex; align-items: center; gap: 0.5rem;
    padding: 0.6rem 1.25rem; border-radius: 14px;
    background: var(--md-card); backdrop-filter: blur(20px);
    border: 1px solid var(--md-border); color: var(--md-accent);
    text-decoration: none; font-weight: 600; font-size: 0.9rem;
    transition: all 0.25s; margin-bottom: 1.5rem;
}
.md-back:hover { transform: translateX(-4px); color: var(--md-accent); }

.md-card {
    background: var(--md-card); backdrop-filter: blur(20px);
    border: 1px solid var(--md-border); border-radius: 24px;
    overflow: hidden; box-shadow: var(--md-shadow);
    margin-bottom: 1.5rem;
}

.md-header {
    background: linear-gradient(135deg, #8b5cf6, #6d28d9);
    padding: 2rem 1.75rem; text-align: center;
}
.md-header h3 { color: #fff; font-size: 1.3rem; font-weight: 700; margin: 0; }
.md-header p { color: rgba(255,255,255,0.8); font-size: 0.85rem; margin: 0.25rem 0 0; }
.md-header-icon {
    width: 70px; height: 70px; border-radius: 20px;
    background: rgba(255,255,255,0.2); backdrop-filter: blur(10px);
    display: flex; align-items: center; justify-content: center;
    margin: 0 auto 1rem; font-size: 2rem; color: #fff;
}

.md-body { padding: 1.75rem; }

.md-actions {
    display: flex; gap: 0.75rem; margin-bottom: 1.5rem; flex-wrap: wrap;
}
.md-btn {
    display: inline-flex; align-items: center; gap: 0.5rem;
    padding: 0.7rem 1.25rem; border-radius: 14px; border: none;
    font-weight: 600; font-size: 0.88rem; cursor: pointer;
    text-decoration: none; transition: all 0.25s;
}
.md-btn-primary { background: var(--md-accent); color: #fff; }
.md-btn-primary:hover { opacity: 0.9; transform: translateY(-2px); color: #fff; }
.md-btn-outline {
    background: var(--md-accent-light); color: var(--md-accent);
    border: 1px solid rgba(139,92,246,0.2);
}
.md-btn-outline:hover { background: var(--md-accent); color: #fff; }

.md-add-form {
    background: var(--md-accent-light); border-radius: 18px;
    padding: 1.25rem; margin-bottom: 1rem;
}
.md-add-form .form-control, .md-add-form .form-select {
    border-radius: 12px !important; border: 1.5px solid var(--md-border) !important;
    background: var(--md-card) !important; padding: 0.65rem 1rem !important;
    color: var(--md-text) !important; font-size: 0.9rem;
}
.md-add-form .form-control:focus, .md-add-form .form-select:focus {
    border-color: var(--md-accent) !important;
    box-shadow: 0 0 0 3px var(--md-accent-light) !important;
}
.md-add-grid {
    display: grid; grid-template-columns: 1fr 1fr; gap: 0.75rem;
    margin-bottom: 0.75rem;
}
.md-add-full { margin-bottom: 0.75rem; }
.md-add-label { font-size: 0.8rem; font-weight: 600; color: var(--md-text); margin-bottom: 0.3rem; }
.md-section-title {
    font-size: 0.9rem; font-weight: 700; color: var(--md-text);
    margin-bottom: 0.75rem; display: flex; align-items: center; gap: 0.5rem;
}

/* AI Generation Section */
.md-ai-form {
    background: linear-gradient(135deg, rgba(139,92,246,0.08), rgba(109,40,217,0.08));
    border: 1.5px solid rgba(139,92,246,0.2);
    border-radius: 18px; padding: 1.25rem; margin-bottom: 1.5rem;
}
.md-ai-form .md-ai-grid {
    display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 0.75rem;
    margin-bottom: 0.75rem;
}
.md-ai-form .form-control, .md-ai-form .form-select {
    border-radius: 12px !important; border: 1.5px solid var(--md-border) !important;
    background: var(--md-card) !important; padding: 0.65rem 1rem !important;
    color: var(--md-text) !important; font-size: 0.9rem;
}
.md-ai-form .form-control:focus, .md-ai-form .form-select:focus {
    border-color: var(--md-accent) !important;
    box-shadow: 0 0 0 3px var(--md-accent-light) !important;
}
.md-ai-loading {
    display: none; align-items: center; justify-content: center;
    gap: 0.75rem; padding: 1.5rem; color: var(--md-accent);
    font-weight: 600; font-size: 0.9rem;
}
.md-ai-loading.active { display: flex; }
.md-ai-spinner {
    width: 24px; height: 24px; border: 3px solid var(--md-accent-light);
    border-top-color: var(--md-accent); border-radius: 50%;
    animation: mdSpin 0.8s linear infinite;
}
@keyframes mdSpin {
    to { transform: rotate(360deg); }
}

/* Word Table */
.md-table-wrap {
    overflow-x: auto; border-radius: 16px;
    border: 1px solid var(--md-border);
}
.md-table {
    width: 100%; border-collapse: collapse; min-width: 500px;
}
.md-table thead th {
    padding: 0.85rem 1rem; font-size: 0.78rem;
    text-transform: uppercase; letter-spacing: 0.5px;
    color: var(--md-secondary); font-weight: 700;
    border-bottom: 2px solid var(--md-border);
    text-align: left; white-space: nowrap;
    background: var(--md-accent-light);
}
.md-table tbody tr {
    transition: background 0.2s;
}
.md-table tbody tr:hover { background: var(--md-accent-light); }
.md-table tbody td {
    padding: 0.75rem 1rem; font-size: 0.9rem;
    color: var(--md-text);
    border-bottom: 1px solid var(--md-border);
    vertical-align: middle;
}
.md-table .td-num {
    width: 45px; text-align: center; font-weight: 700;
    color: var(--md-accent); font-size: 0.85rem;
}
.md-table .td-term { font-weight: 700; }
.md-table .td-translation { color: var(--md-accent); font-weight: 500; }
.md-table .td-example { font-size: 0.82rem; color: var(--md-secondary); font-style: italic; }
.md-table .td-action { width: 50px; text-align: center; }

.md-word-delete {
    width: 34px; height: 34px; border-radius: 10px;
    background: rgba(255,59,48,0.08); color: var(--md-danger);
    border: none; display: inline-flex; align-items: center; justify-content: center;
    cursor: pointer; transition: all 0.2s;
}
.md-word-delete:hover { background: var(--md-danger); color: #fff; }

.md-empty {
    text-align: center; padding: 3rem 1rem; color: var(--md-secondary);
}
.md-empty i { font-size: 3rem; margin-bottom: 1rem; display: block; opacity: 0.3; }
.md-empty p { font-size: 0.9rem; margin: 0; }

.md-count {
    display: inline-flex; align-items: center; gap: 0.4rem;
    padding: 0.3rem 0.85rem; border-radius: 20px;
    background: rgba(255,255,255,0.2); color: #fff;
    font-size: 0.78rem; font-weight: 600; margin-top: 0.5rem;
}

@media (max-width: 767px) {
    .md-add-grid { grid-template-columns: 1fr; }
    .md-ai-form .md-ai-grid { grid-template-columns: 1fr; }
}
</style>
{%% endblock %%}

{%% block content %%}
<div class="md-page">
    <a href="{%% url 'manage_lessons' dictionary.lesson.profession.pk %%}" class="md-back">
        <i class="bi bi-arrow-left"></i> Orqaga
    </a>

    <div class="md-card">
        <div class="md-header">
            <div class="md-header-icon"><i class="bi bi-book-fill"></i></div>
            <h3>{{ dictionary.lesson.title }}</h3>
            <p>{{ dictionary.lesson.profession.name }}</p>
            <div class="md-count"><i class="bi bi-hash"></i> {{ words|length }} ta so'z</div>
        </div>

        <div class="md-body">
            <div class="md-actions">
                <a href="{%% url 'import_dictionary_words' dictionary.pk %%}" class="md-btn md-btn-outline">
                    <i class="bi bi-file-earmark-excel"></i> Excel dan import
                </a>
            </div>

            <!-- Manual word add form -->
            <div class="md-add-form">
                <div class="md-section-title">
                    <i class="bi bi-plus-circle-fill" style="color: var(--md-accent);"></i> So'z qo'shish
                </div>
                <form method="POST" action="{%% url 'add_dictionary_word' dictionary.pk %%}">
                    {%% csrf_token %%}
                    <div class="md-add-grid">
                        <div>
                            <div class="md-add-label">Yozilishi *</div>
                            <input type="text" name="term" class="form-control" placeholder="Masalan: variable" required>
                        </div>
                        <div>
                            <div class="md-add-label">Tarjimasi *</div>
                            <input type="text" name="translation" class="form-control" placeholder="Masalan: o'zgaruvchi" required>
                        </div>
                    </div>
                    <div class="md-add-full">
                        <div class="md-add-label">Misol (ixtiyoriy)</div>
                        <input type="text" name="example" class="form-control" placeholder="Masalan: x = 5 \u2014 bu yerda x variable hisoblanadi">
                    </div>
                    <button type="submit" class="md-btn md-btn-primary" style="width:100%%;">
                        <i class="bi bi-plus-lg"></i> So'z qo'shish
                    </button>
                </form>
            </div>

            <!-- AI Generation form -->
            <div class="md-ai-form">
                <div class="md-section-title">
                    <i class="bi bi-robot" style="color: var(--md-accent);"></i> AI orqali lug'at yaratish
                </div>
                <form method="POST" action="{%% url 'ai_generate_dictionary' dictionary.pk %%}" id="aiGenForm">
                    {%% csrf_token %%}
                    <div class="md-ai-grid">
                        <div>
                            <div class="md-add-label">Til *</div>
                            <input type="text" name="language" class="form-control" placeholder="Masalan: Ingliz tili" required>
                        </div>
                        <div>
                            <div class="md-add-label">So'zlar soni *</div>
                            <input type="number" name="count" class="form-control" min="1" max="50" value="10" required>
                        </div>
                        <div>
                            <div class="md-add-label">Daraja *</div>
                            <select name="level" class="form-control form-select" required>
                                <option value="Boshlang'ich">Boshlang'ich</option>
                                <option value="O'rta" selected>O'rta</option>
                                <option value="Yuqori">Yuqori</option>
                                <option value="Professional">Professional</option>
                            </select>
                        </div>
                    </div>
                    <button type="submit" class="md-btn md-btn-primary" style="width:100%%;" id="aiGenBtn">
                        <i class="bi bi-stars"></i> AI bilan yaratish
                    </button>
                </form>
                <div class="md-ai-loading" id="aiLoading">
                    <div class="md-ai-spinner"></div>
                    <span>AI so'zlar yaratmoqda...</span>
                </div>
            </div>

            <!-- Words Table -->
            {%% if words %%}
            <div class="md-table-wrap">
                <table class="md-table">
                    <thead>
                        <tr>
                            <th style="width:45px;">#</th>
                            <th>Yozilishi</th>
                            <th>Tarjimasi</th>
                            <th>Misol</th>
                            <th style="width:50px;"></th>
                        </tr>
                    </thead>
                    <tbody>
                        {%% for word in words %%}
                        <tr>
                            <td class="td-num">{{ forloop.counter }}</td>
                            <td class="td-term">{{ word.term }}</td>
                            <td class="td-translation">{{ word.translation }}</td>
                            <td class="td-example">
                                {%% if word.example %%}
                                <i class="bi bi-lightbulb text-warning me-1"></i>{{ word.example }}
                                {%% else %%}
                                <span class="text-muted">\u2014</span>
                                {%% endif %%}
                            </td>
                            <td class="td-action">
                                <form method="POST" action="{%% url 'delete_dictionary_word' word.pk %%}" onsubmit="return confirm('Bu so\\'zni o\\'chirmoqchimisiz?')">
                                    {%% csrf_token %%}
                                    <button type="submit" class="md-word-delete" title="O'chirish">
                                        <i class="bi bi-trash-fill"></i>
                                    </button>
                                </form>
                            </td>
                        </tr>
                        {%% endfor %%}
                    </tbody>
                </table>
            </div>
            {%% else %%}
                <div class="md-empty">
                    <i class="bi bi-book"></i>
                    <p>Hali so'zlar qo'shilmagan</p>
                    <p style="font-size:0.8rem; margin-top:0.5rem;">Yuqoridagi formadan, Excel import yoki AI orqali qo'shing</p>
                </div>
            {%% endif %%}
        </div>
    </div>
</div>
{%% endblock %%}

{%% block extra_js %%}
<script>
(function() {
    var form = document.getElementById('aiGenForm');
    var btn = document.getElementById('aiGenBtn');
    var loading = document.getElementById('aiLoading');
    if (form) {
        form.addEventListener('submit', function() {
            btn.disabled = true;
            btn.style.opacity = '0.5';
            loading.classList.add('active');
        });
    }
})();
</script>
{%% endblock %%}
"""

# Fix the doubled %% back to single % for Django template tags
content = content.replace('%%', '%')

target = r'c:\Users\User\Videos\learning-managment-sistem-django\accounts\templates\accounts\manage\manage_dictionary.html'
with open(target, 'w', encoding='utf-8') as f:
    f.write(content)

print('File written successfully!')
print(f'Size: {os.path.getsize(target)} bytes')
