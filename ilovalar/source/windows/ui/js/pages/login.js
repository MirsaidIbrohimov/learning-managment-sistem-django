import { auth, openExternal, SITE } from '../api.js';
import { icon } from '../icons.js';
import { $, esc } from '../ui.js';
import { lastLogin } from '../store.js';
import { languagePicker } from '../i18n.js';

// Kiriş usullari belgilari (brend ranglarida)
const BRAND = {
  google: '<svg viewBox="0 0 24 24" class="brand"><path fill="#EA4335" d="M12 10.2v3.9h5.5c-.2 1.3-1.6 3.9-5.5 3.9-3.3 0-6-2.7-6-6.1s2.7-6.1 6-6.1c1.9 0 3.1.8 3.8 1.5l2.6-2.5C16.8 3.3 14.6 2.3 12 2.3 6.6 2.3 2.3 6.6 2.3 12S6.6 21.7 12 21.7c5.6 0 9.3-3.9 9.3-9.4 0-.6-.1-1.1-.2-1.6H12z"/></svg>',
  github: '<svg viewBox="0 0 24 24" class="brand"><path fill="currentColor" d="M12 2a10 10 0 0 0-3.2 19.5c.5.1.7-.2.7-.5v-1.7c-2.8.6-3.4-1.3-3.4-1.3-.5-1.2-1.1-1.5-1.1-1.5-.9-.6.1-.6.1-.6 1 .1 1.5 1 1.5 1 .9 1.5 2.4 1.1 2.9.8.1-.7.4-1.1.6-1.3-2.2-.3-4.6-1.1-4.6-5a3.9 3.9 0 0 1 1-2.7c-.1-.3-.4-1.3.1-2.7 0 0 .8-.3 2.8 1a9.6 9.6 0 0 1 5 0c1.9-1.3 2.8-1 2.8-1 .5 1.4.2 2.4.1 2.7a3.9 3.9 0 0 1 1 2.7c0 3.9-2.4 4.7-4.6 5 .4.3.7.9.7 1.9v2.8c0 .3.2.6.7.5A10 10 0 0 0 12 2z"/></svg>',
  telegram: '<svg viewBox="0 0 24 24" class="brand"><circle cx="12" cy="12" r="10" fill="#229ED9"/><path fill="#fff" d="M17.4 7.6 15.6 16.5c-.1.6-.5.8-1 .5l-2.8-2.1-1.4 1.3c-.2.2-.3.3-.6.3l.2-2.9 5.2-4.7c.2-.2-.1-.3-.4-.1l-6.4 4-2.8-.9c-.6-.2-.6-.6.1-.9l10.8-4.2c.5-.2.9.1.9.8z"/></svg>',
  email: '<svg viewBox="0 0 24 24" class="brand"><rect x="2" y="4" width="20" height="16" rx="3" fill="#8b5cf6"/><path d="m3 7 9 6 9-6" fill="none" stroke="#fff" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>',
};

/** Server xato kodi → foydalanuvçiga tuşunarli matn. */
function authError(ex) {
  const code = ex?.data?.code;
  if (code === 'role' || code === 'blocked' || code === 'rate_limited') return ex.message;
  if (code === 'invalid' || ex?.status === 400) return "Login yoki parol notöğri";
  if (code === 'denied') return "Kiriş rad etildi";
  if (code === 'expired' || code === 'consumed') return "Kutiş vaqti tugadi. Qaytadan urinib köring";
  return ex?.message || "Kutilmagan xatolik";
}

export function renderLogin(root, onSuccess) {
  root.innerHTML = `
  <div class="auth-wrap">
    <section class="auth-art">
      <div class="orb o1"></div><div class="orb o2"></div><div class="orb o3"></div>
      <div class="grid-lines"></div>
      <div class="auth-logo"><img src="assets/logo.png" alt=""> IT Creative Academy</div>
      <h1>Bilim — eng <span class="auth-hl">işonçli</span> sarmoya.</h1>
      <p class="lead">Kurslaringiz, reytingingiz, coinlaringiz va sertifikatlaringiz — barçasi bitta ilovada, tez va qulay.</p>
      <div class="auth-feats">
        <div class="auth-feat">${icon('courses')} Video darslar</div>
        <div class="auth-feat">${icon('trophy')} Jonli reyting</div>
        <div class="auth-feat">${icon('shop')} Coin dökon</div>
        <div class="auth-feat">${icon('award')} Sertifikatlar</div>
      </div>
    </section>
    <section class="auth-form-side">
      <div class="auth-lang">${languagePicker()}</div>
      <div class="auth-form" id="auth-box"></div>
    </section>
  </div>`;

  const box = $('#auth-box', root);
  let polling = null; // brauzer kutiş holati

  const stopPolling = () => {
    if (!polling) return;
    clearTimeout(polling.timer);
    clearInterval(polling.clock);
    polling = null;
  };

  // ───────── Asosiy ekran: sayt orqali yoki login/parol ─────────
  const showChoice = (errorText = '') => {
    stopPolling();
    box.innerHTML = `
      <div><h2>Xuş kelibsiz 👋</h2></div>
      <p class="sub">Davom etiş uçun hisobingizga kiring</p>
      <div class="auth-err" id="auth-err">${icon('alert')}<span></span></div>
      <button class="btn btn-lg sso-btn" id="sso" type="button">
        <span class="sso-icons">${BRAND.google}${BRAND.github}${BRAND.telegram}${BRAND.email}</span>
        <span class="sso-text"><b>Sayt orqali kiriş</b><small>Google, GitHub, Telegram, email kodi va boşqalar</small></span>
        ${icon('ext')}
      </button>
      <div class="auth-or"><span>yoki login va parol bilan</span></div>
      <form id="login-form" class="col" style="gap:14px" autocomplete="on" novalidate>
        <div class="field">
          <label for="u">Login yoki telefon</label>
          <div class="input-wrap">${icon('user')}<input class="input" id="u" name="username" autocomplete="username" placeholder="Foydalanuvçi nomi yoki +998…" spellcheck="false" required></div>
        </div>
        <div class="field">
          <label for="p">Parol</label>
          <div class="input-wrap">${icon('lock')}<input class="input" id="p" name="password" type="password" autocomplete="current-password" placeholder="••••••••" required>
            <button type="button" class="btn btn-ghost btn-icon btn-sm suffix" id="toggle-pw" data-tip="Parolni körsatiş">${icon('eye')}</button>
          </div>
        </div>
        <button class="btn btn-primary btn-lg" type="submit" id="login-btn">Kiriş ${icon('arrowR')}</button>
      </form>
      <div class="auth-foot">Ilova faqat öquvçilar uçun · Hisobingiz yöqmi? <a id="reg">Saytda röyxatdan öting</a></div>
      <div class="auth-foot" style="margin-top:-6px"><a id="forgot" class="muted-link">Parolni unutdingizmi?</a></div>`;

    const form = $('#login-form', box);
    const u = $('#u', box);
    const p = $('#p', box);
    const btn = $('#login-btn', box);
    const err = $('#auth-err', box);
    const showErr = (msg) => {
      err.querySelector('span').textContent = msg;
      err.classList.remove('show');
      void err.offsetWidth; // animatsiyani qayta boşlaş
      err.classList.add('show');
    };
    if (errorText) showErr(errorText);

    $('#sso', box).addEventListener('click', startBrowser);
    $('#toggle-pw', box).addEventListener('click', (e) => {
      const show = p.type === 'password';
      p.type = show ? 'text' : 'password';
      e.currentTarget.innerHTML = icon(show ? 'eyeOff' : 'eye');
      p.focus();
    });
    $('#reg', box).addEventListener('click', () => openExternal(`${SITE}/register/`));
    $('#forgot', box).addEventListener('click', () => openExternal(`${SITE}/login/`));

    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      err.classList.remove('show');
      if (!u.value.trim() || !p.value) {
        showErr("Login va parolni kiriting");
        (u.value.trim() ? p : u).focus();
        return;
      }
      btn.disabled = true;
      btn.innerHTML = `${icon('loader', 'spin')} Tekşirilmoqda…`;
      try {
        await auth.login(u.value.trim(), p.value);
        lastLogin.set(u.value.trim());
        btn.innerHTML = `${icon('check')} Muvaffaqiyatli`;
        await onSuccess({ fresh: true });
      } catch (ex) {
        showErr(authError(ex));
        btn.disabled = false;
        btn.innerHTML = `Kiriş ${icon('arrowR')}`;
        p.select();
      }
    });

    // Oxirgi login eslab qolinadi (parol emas)
    const remembered = lastLogin.get();
    if (remembered) u.value = remembered;
    setTimeout(() => (remembered ? p : u).focus(), 80);
  };

  // ───────── Brauzer orqali kiriş: kod körsatiladi, tasdiq kutiladi ─────────
  async function startBrowser() {
    const btn = $('#sso', box);
    btn.disabled = true;
    let info;
    try {
      info = await auth.startBrowser();
    } catch (ex) {
      showChoice(authError(ex));
      return;
    }
    const deadline = Date.now() + (Number(info.expires_in) || 600) * 1000;
    box.innerHTML = `
      <div class="sso-wait">
        <div class="sso-wait-ico">${icon('globe')}</div>
        <h2>Brauzerda tasdiqlang</h2>
        <p class="sub">Brauzerda ITC Academy sayti oçildi. Saytga istalgan usulda kiring va quyidagi kod bilan bir xil kodni körib «Tasdiqlaş» ni bosing.</p>
        <div class="sso-code" translate="no">${esc(info.user_code || '')}</div>
        <div class="sso-status"><span class="spin-dot"></span><span>Tasdiq kutilmoqda…</span><b id="sso-left"></b></div>
        <div class="auth-err" id="auth-err">${icon('alert')}<span></span></div>
        <div class="row" style="justify-content:center;gap:10px">
          <button class="btn" id="reopen" type="button">${icon('ext')} Brauzerni qayta oçiş</button>
          <button class="btn btn-ghost" id="cancel" type="button">Bekor qiliş</button>
        </div>
      </div>`;
    const left = $('#sso-left', box);
    const tick = () => {
      const s = Math.max(0, Math.round((deadline - Date.now()) / 1000));
      left.textContent = `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
    };
    tick();
    polling = { timer: 0, clock: setInterval(tick, 1000) };
    $('#reopen', box).addEventListener('click', () => openExternal(info.url));
    $('#cancel', box).addEventListener('click', () => { auth.cancelBrowser(); showChoice(); });

    const interval = Math.max(1, Number(info.interval) || 2) * 1000;
    const poll = async () => {
      if (!polling) return;
      if (Date.now() > deadline) {
        auth.cancelBrowser();
        showChoice("Kutiş vaqti tugadi. Qaytadan urinib köring");
        return;
      }
      try {
        const status = await auth.pollBrowser();
        if (!polling) return;
        if (status === 'approved') {
          stopPolling();
          box.querySelector('.sso-status').innerHTML = `${icon('checkCircle')} <span>Tasdiqlandi! Kirilmoqda…</span>`;
          await onSuccess({ fresh: true });
          return;
        }
      } catch (ex) {
        // Tarmoq uzilişi — vaqt tugaguncha qayta urinamiz
        if (ex.status !== 0) {
          showChoice(authError(ex));
          return;
        }
      }
      if (polling) polling.timer = setTimeout(poll, interval);
    };
    polling.timer = setTimeout(poll, interval);
  }

  showChoice();
}
