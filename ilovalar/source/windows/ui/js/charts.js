// Yengil SVG grafikalar (taşqi kutubxonasiz).
// Qoidalar: bitta seriya — bitta urğu rangi (--chart), ustun ≤ 24px, tepasi 4px yumaloq,
// asosi tekis; grid 1px, sokin; har bir ustun — tooltip uçun hit-zona; jadval körinişi bor.
import { esc, num } from './ui.js';

const NS = 'http://www.w3.org/2000/svg';

/** 1 234 → "1.2K" (oq tuzilmali qisqa format, faqat ox belgilari uçun). */
function compact(n) {
  if (Math.abs(n) >= 1000) return `${(n / 1000).toFixed(n % 1000 === 0 ? 0 : 1)}K`;
  return String(n);
}

/** Toza ox qadamlari: 0, step, 2·step … ≥ max. */
function niceTicks(max, count = 3) {
  if (max <= 0) return [0, 1];
  const raw = max / count;
  const mag = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= raw) || raw;
  const ticks = [];
  for (let v = 0; v <= max + step * 0.001; v += step) ticks.push(Math.round(v));
  if (ticks[ticks.length - 1] < max) ticks.push(Math.round(ticks[ticks.length - 1] + step));
  return ticks;
}

/** Ustun yöli: tepasi r radiusli yumaloq, asosi tekis. */
function barPath(x, y, w, h, r) {
  if (h <= 0) return '';
  const rr = Math.min(r, w / 2, h);
  return `M${x},${y + h}V${y + rr}Q${x},${y} ${x + rr},${y}H${x + w - rr}Q${x + w},${y} ${x + w},${y + rr}V${y + h}Z`;
}

/**
 * Ustunli grafik.
 * @param {HTMLElement} host
 * @param {{label:string, tip:string, value:number}[]} data
 * @param {{unit?:string, label?:string}} opts
 */
export function columnChart(host, data, { unit = 'coin', label = '' } = {}) {
  host.classList.add('chart');
  host.innerHTML = `<svg role="img" aria-label="${esc(label)}"></svg><div class="chart-tip" role="status"></div>`;
  const svg = host.querySelector('svg');
  const tip = host.querySelector('.chart-tip');

  const draw = () => {
    const W = host.clientWidth;
    const H = host.clientHeight || 220;
    if (!W) return;
    const pad = { l: 40, r: 8, t: 12, b: 26 };
    const iw = W - pad.l - pad.r;
    const ih = H - pad.t - pad.b;
    const max = Math.max(...data.map((d) => d.value), 0);
    const ticks = niceTicks(max);
    const top = ticks[ticks.length - 1] || 1;
    const band = iw / data.length;
    const bw = Math.min(24, Math.max(4, band * 0.62));
    const y = (v) => pad.t + ih - (v / top) * ih;
    const showEvery = band < 26 ? 2 : 1;

    let out = '';
    // Grid va Y ox belgilari
    ticks.forEach((t) => {
      const yy = Math.round(y(t)) + 0.5;
      out += `<line class="grid-line" x1="${pad.l}" x2="${W - pad.r}" y1="${yy}" y2="${yy}"/>`;
      out += `<text class="axis-text" x="${pad.l - 8}" y="${yy + 4}" text-anchor="end">${compact(t)}</text>`;
    });
    // Ustunlar va hit-zonalar
    data.forEach((d, i) => {
      const cx = pad.l + band * i + band / 2;
      const h = Math.max(0, (d.value / top) * ih);
      // Nol qiymat ham körinsin: 2px "çiziq" (hajm emas, belgi)
      out += d.value > 0
        ? `<path class="bar" d="${barPath(cx - bw / 2, pad.t + ih - h, bw, h, 4)}"/>`
        : `<rect class="bar-zero" x="${cx - bw / 2}" y="${pad.t + ih - 2}" width="${bw}" height="2" rx="1"/>`;
      if (i % showEvery === (data.length - 1) % showEvery) {
        out += `<text class="axis-text" x="${cx}" y="${H - 8}" text-anchor="middle">${esc(d.label)}</text>`;
      }
      out += `<rect class="hit" data-i="${i}" x="${pad.l + band * i}" y="${pad.t}" width="${band}" height="${ih}" tabindex="0" aria-label="${esc(`${d.tip}: ${num(d.value)} ${unit}`)}"/>`;
    });
    svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
    svg.setAttribute('width', W);
    svg.setAttribute('height', H);
    svg.innerHTML = out;
  };

  const show = (el) => {
    const i = Number(el.dataset.i);
    const d = data[i];
    svg.querySelectorAll('.bar, .bar-zero').forEach((b, j) => b.classList.toggle('dim', j !== i));
    tip.replaceChildren();
    const v = document.createElement('b');
    v.textContent = `${num(d.value)} ${unit}`;
    const l = document.createElement('span');
    l.textContent = d.tip;
    tip.append(v, l);
    tip.classList.add('show');
    const r = el.getBoundingClientRect();
    const hr = host.getBoundingClientRect();
    const x = r.left - hr.left + r.width / 2 - tip.offsetWidth / 2;
    tip.style.left = `${Math.max(0, Math.min(hr.width - tip.offsetWidth, x))}px`;
    tip.style.top = '-6px';
  };
  const hide = () => {
    tip.classList.remove('show');
    svg.querySelectorAll('.dim').forEach((b) => b.classList.remove('dim'));
  };
  svg.addEventListener('pointerover', (e) => { if (e.target.classList?.contains('hit')) show(e.target); });
  svg.addEventListener('focusin', (e) => { if (e.target.classList?.contains('hit')) show(e.target); });
  svg.addEventListener('pointerleave', hide);
  svg.addEventListener('focusout', hide);

  const ro = new ResizeObserver(() => draw());
  ro.observe(host);
  draw();
  return { destroy: () => ro.disconnect() };
}

/** Grafik ma'lumotining jadval körinişi (tooltip faqat qulaylik — qiymatlar şu yerda ham bor). */
export function dataTable(data, { unit = 'coin', head = 'Sana' } = {}) {
  return `<table class="data-table"><thead><tr><th>${esc(head)}</th><th class="num-col">${esc(unit)}</th></tr></thead>
    <tbody>${data.map((d) => `<tr><td>${esc(d.tip)}</td><td class="num-col">${num(d.value)}</td></tr>`).join('')}</tbody></table>`;
}
