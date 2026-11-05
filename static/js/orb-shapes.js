/* IT Creative — 3D shakllar kutubxonasi: profil/bosh sahifa orb'i (profile-orb.js) va
 * sayt yuklaniş animatsiyasi (templates/partials/_morph_loader.html) bir xil shakllardan foydalanadi.
 * OrbShapes.shapes[nom](i, N) → [x, y, z] (taxminan 1.6 radius içida); OrbShapes.palettes[nom] → ranglar.
 */
(function () {
  const GA = Math.PI * (3 - Math.sqrt(5)), PHI = (1 + Math.sqrt(5)) / 2;
  const frac = x => x - Math.floor(x);
  const rnd = i => frac(Math.sin(i * 12.9898 + 78.233) * 43758.5453);   // barqaror "tasodif"

  // Har bir shakl: i-nuqtaning [x, y, z] koordinatasi (taxminan 1.6 radius içida)
  const SHAPES = {
    sphere(i, N) {
      const y = 1 - i / (N - 1) * 2, r = Math.sqrt(1 - y * y), th = GA * i;
      return [Math.cos(th) * r * 1.55, y * 1.55, Math.sin(th) * r * 1.55];
    },
    cube(i, N) {
      const per = Math.ceil(N / 6), side = Math.max(2, Math.ceil(Math.sqrt(per))), face = i % 6, k = Math.floor(i / 6);
      const u = (k % side) / (side - 1) * 2 - 1, v = Math.floor(k / side) / (side - 1) * 2 - 1, s = 1.1;
      const a = u * s, b = v * s;
      return [[s, a, b], [-s, a, b], [a, s, b], [a, -s, b], [a, b, s], [a, b, -s]][face];
    },
    torus(i, N) {
      const cols = Math.round(Math.sqrt(N * 2.6)), rows = Math.ceil(N / cols);
      const u = 2 * Math.PI * (i % cols) / cols, v = 2 * Math.PI * Math.floor(i / cols) / rows + u * .5;
      const R = 1.15, r = .5;
      return [(R + r * Math.cos(v)) * Math.cos(u), r * Math.sin(v), (R + r * Math.cos(v)) * Math.sin(u)];
    },
    heart(i, N) {
      const t = 2 * Math.PI * frac(i * PHI), s = i / (N - 1) * 2 - 1, w = Math.sqrt(1 - s * s * .92);
      const hx = 16 * Math.pow(Math.sin(t), 3), hy = 13 * Math.cos(t) - 5 * Math.cos(2 * t) - 2 * Math.cos(3 * t) - Math.cos(4 * t);
      return [hx * .095 * w, hy * .095 * w + .22, s * .62];
    },
    dna(i, N) {
      const strand = Math.floor(N * .78);
      if (i < strand) {
        const k = Math.floor(i / 2), t = k / (strand / 2), a = t * Math.PI * 4 + (i % 2) * Math.PI;
        return [Math.cos(a) * .78, (t * 2 - 1) * 1.85, Math.sin(a) * .78];
      }
      const j = i - strand, rungs = 14, per = Math.ceil((N - strand) / rungs);
      const t = ((j % rungs) + .5) / rungs, f = Math.floor(j / rungs) / Math.max(1, per - 1) * 2 - 1, a = t * Math.PI * 4;
      return [Math.cos(a) * .78 * f, (t * 2 - 1) * 1.85, Math.sin(a) * .78 * f];
    },
    galaxy(i, N) {
      const t = i / N, arm = i % 3, r = .12 + Math.pow(t, .8) * 1.75;
      const a = r * 2.3 + arm * 2 * Math.PI / 3 + (rnd(i) - .5) * .5;
      return [Math.cos(a) * r + (rnd(i + 1) - .5) * .18, (rnd(i + 2) - .5) * .28 * (1.2 - t), Math.sin(a) * r + (rnd(i + 3) - .5) * .18];
    },
    planet(i, N) {
      const core = Math.floor(N * .55);
      if (i < core) {
        const y = 1 - i / (core - 1) * 2, r = Math.sqrt(1 - y * y), th = GA * i;
        return [Math.cos(th) * r, y, Math.sin(th) * r];
      }
      const j = i - core, a = GA * j * 3.1, rr = 1.42 + rnd(j) * .42, tilt = .42;
      const x = Math.cos(a) * rr, z = Math.sin(a) * rr, y = (rnd(j + 7) - .5) * .05;
      return [x, y * Math.cos(tilt) - z * Math.sin(tilt), y * Math.sin(tilt) + z * Math.cos(tilt)];
    },
    infinity(i, N) {
      const ring = 9, segs = Math.ceil(N / ring), seg = Math.floor(i / ring), k = i % ring;
      const at = t => { const d = 1 + Math.sin(t) ** 2; return [1.75 * Math.cos(t) / d, 1.75 * Math.sin(t) * Math.cos(t) / d]; };
      const t = 2 * Math.PI * seg / segs, p = at(t), q = at(t + .01);
      let nx = -(q[1] - p[1]), ny = q[0] - p[0]; const len = Math.hypot(nx, ny) || 1; nx /= len; ny /= len;
      const a = 2 * Math.PI * k / ring + seg * .35, r = .24;
      return [p[0] + nx * Math.cos(a) * r, p[1] + ny * Math.cos(a) * r, Math.sin(a) * r];
    },
    star(i, N) {
      const y = 1 - i / (N - 1) * 2, r0 = Math.sqrt(1 - y * y), th = GA * i;
      const dir = [Math.cos(th) * r0, y, Math.sin(th) * r0];
      let best = 0;
      for (const v of ICOSA) best = Math.max(best, dir[0] * v[0] + dir[1] * v[1] + dir[2] * v[2]);
      const r = .78 + .95 * Math.pow(best, 18);
      return [dir[0] * r, dir[1] * r, dir[2] * r];
    },
  };
  const ICOSA = [[0, 1, PHI], [0, -1, PHI], [0, 1, -PHI], [0, -1, -PHI], [1, PHI, 0], [-1, PHI, 0], [1, -PHI, 0], [-1, -PHI, 0],
    [PHI, 0, 1], [-PHI, 0, 1], [PHI, 0, -1], [-PHI, 0, -1]].map(v => { const l = Math.hypot(...v); return v.map(c => c / l); });

  // Rang palitralari: [yorug mavzu A, B], [tungi mavzu A, B], hover rangi
  const PALETTES = {
    aurora: [[0x7c3aed, 0x0891b2], [0x4c1d95, 0x22d3ee], 0xf472b6],
    gold: [[0xb45309, 0xf59e0b], [0x92400e, 0xfcd34d], 0xfff1b8],
    fire: [[0xb91c1c, 0xf97316], [0x7f1d1d, 0xfb923c], 0xfde047],
    ocean: [[0x1d4ed8, 0x0891b2], [0x1e3a8a, 0x22d3ee], 0xa5f3fc],
    emerald: [[0x047857, 0x10b981], [0x064e3b, 0x34d399], 0xfde68a],
    sakura: [[0xdb2777, 0xf472b6], [0x9d174d, 0xf9a8d4], 0xc4b5fd],
    rainbow: [[0x7c3aed, 0x0891b2], [0x4c1d95, 0x22d3ee], 0xffffff],
  };

  window.OrbShapes = { shapes: SHAPES, palettes: PALETTES, frac: frac };
})();
