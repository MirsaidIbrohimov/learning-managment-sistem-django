// Ilovaning harakat tizimi: kirib keliş, ekranga kirganda oçiliş, kursorga ergaşuvçi nur,
// segmentli tablar va mavzu almaşiş. Sozlamada animatsiya öçiq bölsa, heç narsa işlamaydi.

const REVEAL = [
  '.card', '.course-card', '.product', '.book', '.stat', '.pstat', '.badge', '.resume-card', '.section-block',
  '.list-item', '.rank-row', '.pod', '.lesson-row', '.setting', '.cert', '.my-rank-card', '.hub-tile', '.hero',
  '.course-hero', '.lang-card', '.empty',
].join(',');
const GLOW = '.card:not(.hero),.course-card,.product,.book,.resume-card,.pstat,.badge,.hub-tile,.lang-card,.pod';
const TILT = '.course-card,.product,.book,.resume-card,.hub-tile';
const MAX_DELAY_STEPS = 10;
const STEP_MS = 38;

const off = () => document.documentElement.dataset.motion === 'off'
  || matchMedia('(prefers-reduced-motion: reduce)').matches;

const seen = new WeakSet();
let io = null;

function watch(el) {
  if (seen.has(el) || el.closest('.skel') || el.parentElement?.closest('.lesson-row,.list-item')) return;
  seen.add(el);
  el.classList.add('m-wait');
  io.observe(el);
}

function show(el, i) {
  el.style.setProperty('--i', Math.min(i, MAX_DELAY_STEPS));
  el.classList.remove('m-wait');
  el.classList.add('m-in');
  // Animatsiyadan keyin sinf olinadi: hover transformlari bilan toqnaşmasin
  setTimeout(() => {
    el.classList.remove('m-in');
    el.style.removeProperty('--i');
  }, 800 + Math.min(i, MAX_DELAY_STEPS) * STEP_MS);
}

function setupReveal(root) {
  io = new IntersectionObserver((entries) => {
    let i = 0;
    entries.filter((e) => e.isIntersecting).forEach((e) => {
      io.unobserve(e.target);
      show(e.target, i++);
    });
  }, { threshold: 0.01 });

  const queue = (node) => {
    if (node.nodeType !== Node.ELEMENT_NODE) return;
    if (node.matches(REVEAL)) watch(node);
    node.querySelectorAll(REVEAL).forEach(watch);
  };
  new MutationObserver((records) => {
    if (off()) return;
    records.forEach((r) => r.addedNodes.forEach(queue));
    syncTabs();
  }).observe(root, { subtree: true, childList: true });
}

// ───────── Segmentli tablar: tanlangan bölak sirpanib ötadi ─────────
let lastThumb = null;

function placeThumb(thumb, active, animateFrom) {
  const set = (x, w) => {
    thumb.style.width = `${w}px`;
    thumb.style.transform = `translateX(${x}px)`;
  };
  const x = active.offsetLeft;
  const w = active.offsetWidth;
  if (animateFrom) {
    thumb.style.transition = 'none';
    set(animateFrom.x, animateFrom.w);
    requestAnimationFrame(() => requestAnimationFrame(() => {
      thumb.style.transition = '';
      set(x, w);
    }));
  } else {
    set(x, w);
  }
  lastThumb = { x, w };
}

function syncTabs() {
  document.querySelectorAll('.tabs').forEach((tabs) => {
    const active = tabs.querySelector('.tab.active');
    let thumb = tabs.querySelector(':scope > .tab-thumb');
    if (!active) { thumb?.remove(); return; }
    if (!thumb) {
      thumb = document.createElement('i');
      thumb.className = 'tab-thumb';
      tabs.prepend(thumb);
      tabs.classList.add('has-thumb');
      placeThumb(thumb, active, lastThumb);
    } else if (thumb.dataset.at !== active.textContent) {
      placeThumb(thumb, active);
    }
    thumb.dataset.at = active.textContent;
  });
}

// ───────── Kursor: nur va yengil qiyalik ─────────
function setupPointer() {
  let frame = 0;
  let last = null;
  let tilted = null;
  const apply = () => {
    frame = 0;
    if (!last || off()) return;
    const target = last.target.closest?.(GLOW);
    const tiltEl = last.target.closest?.(TILT);
    if (tilted && tilted !== tiltEl) {
      tilted.style.removeProperty('--rx');
      tilted.style.removeProperty('--ry');
    }
    tilted = tiltEl;
    if (!target) return;
    const r = target.getBoundingClientRect();
    target.style.setProperty('--mx', `${last.clientX - r.left}px`);
    target.style.setProperty('--my', `${last.clientY - r.top}px`);
    if (tiltEl) {
      tiltEl.style.setProperty('--ry', `${((last.clientX - r.left) / r.width - 0.5) * 5}deg`);
      tiltEl.style.setProperty('--rx', `${((last.clientY - r.top) / r.height - 0.5) * -5}deg`);
    }
  };
  document.addEventListener('pointermove', (e) => {
    last = e;
    if (!frame) frame = requestAnimationFrame(apply);
  }, { passive: true });
}

/** Mavzu almaşişi: yangi mavzu bosilgan joydan doira bölib oçiladi. */
export function withThemeReveal(event, change) {
  if (off() || !document.startViewTransition) { change(); return; }
  const x = event?.clientX ?? innerWidth / 2;
  const y = event?.clientY ?? 22;
  const radius = Math.hypot(Math.max(x, innerWidth - x), Math.max(y, innerHeight - y));
  const vt = document.startViewTransition(change);
  vt.ready.then(() => {
    document.documentElement.animate(
      { clipPath: [`circle(0 at ${x}px ${y}px)`, `circle(${radius}px at ${x}px ${y}px)`] },
      { duration: 560, easing: 'cubic-bezier(.3,.8,.2,1)', pseudoElement: '::view-transition-new(root)' },
    );
  }).catch(() => {});
}

export function initMotion() {
  setupReveal(document.getElementById('root'));
  setupPointer();
  window.addEventListener('resize', syncTabs);
}
