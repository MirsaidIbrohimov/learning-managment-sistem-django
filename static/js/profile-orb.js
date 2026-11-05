/* IT Creative — profil va bosh sahifa hero'si uçun 3D "Reactive Orb" (konteyner içida).
 * Klassik skript: Three.js sahifadagi importmap orqali dinamik import qilinadi.
 * <div data-pf-orb data-shape="sphere" data-palette="aurora" data-speed="normal"> içiga öz canvas'ini qöyadi.
 * Shakl, rang va tezlikni Premium a'zo "Premium sozlamalar"da tanlaydi (accounts/premium_settings.py).
 * Körinmaganda çizişni töxtatadi. Mavzu: <html data-bs-theme="dark|light">.
 * API: window.ProfileOrb.set({shape, palette, speed}) — shakllar orasida silliq ötadi.
 * Shakllar: static/js/orb-shapes.js (undan oldin yuklanadi).
 */
(function () {
  const host = document.querySelector('[data-pf-orb]');
  if (!host || !window.OrbShapes) return;

  const { shapes: SHAPES, palettes: PALETTES, frac } = window.OrbShapes;   // static/js/orb-shapes.js
  const SPEEDS = { off: 0, slow: .06, normal: .15, fast: .4 };

  async function init() {
    const THREE = await import('three');
    const { RoomEnvironment } = await import('three/addons/environments/RoomEnvironment.js');
    const root = document.documentElement;
    const small = innerWidth < 700;

    const canvas = document.createElement('canvas'); canvas.setAttribute('aria-hidden', 'true'); host.prepend(canvas);
    const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
    renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(40, 1, .1, 100);
    camera.position.set(0, 0, 7.2);
    scene.environment = new THREE.PMREMGenerator(renderer).fromScene(new RoomEnvironment(), .04).texture;
    scene.add(new THREE.AmbientLight(0xffffff, .5));
    const l1 = new THREE.PointLight(0x22d3ee, 40, 30); l1.position.set(4, 3, 4); scene.add(l1);
    const l2 = new THREE.PointLight(0xa78bfa, 40, 30); l2.position.set(-4, -2, 3); scene.add(l2);

    const N = small ? 420 : 760, R = 1.55;
    const g = new THREE.Group(); scene.add(g);
    const im = new THREE.InstancedMesh(new THREE.SphereGeometry(.075, 16, 12),
      new THREE.MeshPhysicalMaterial({ metalness: .2, roughness: .25, clearcoat: 1 }), N);
    const opts = {
      shape: SHAPES[host.dataset.shape] ? host.dataset.shape : 'sphere',
      palette: PALETTES[host.dataset.palette] ? host.dataset.palette : 'aurora',
      speed: host.dataset.speed in SPEEDS ? host.dataset.speed : 'normal',
    };
    const build = name => Array.from({ length: N }, (_, i) => new THREE.Vector3(...SHAPES[name](i, N)));
    const T = build(opts.shape), P = T.map(v => v.clone()), amt = new Float32Array(N);
    const hit = new THREE.Mesh(new THREE.SphereGeometry(R * 1.05, 24, 16), new THREE.MeshBasicMaterial({ visible: false }));
    g.add(im, hit);

    const st = { scale: 0, expand: 1, spin: 0 };
    const mouse = { x: -9, y: -9, sx: 0, sy: 0 };
    addEventListener('pointermove', e => {
      const r = host.getBoundingClientRect();
      mouse.x = (e.clientX - r.left) / r.width * 2 - 1; mouse.y = -((e.clientY - r.top) / r.height * 2 - 1);
    });

    const cA = new THREE.Color(), cB = new THREE.Color(), cC = new THREE.Color(), col = new THREE.Color();
    const ray = new THREE.Raycaster(), loc = new THREE.Vector3(), d = new THREE.Object3D();
    const ripples = [];
    function theme() {
      const pal = PALETTES[opts.palette], dark = root.getAttribute('data-bs-theme') === 'dark';
      cA.set(pal[dark ? 1 : 0][0]); cB.set(pal[dark ? 1 : 0][1]); cC.set(pal[2]);
    }
    theme();
    new MutationObserver(theme).observe(root, { attributes: true, attributeFilter: ['data-bs-theme'] });

    function resize() {
      const w = host.clientWidth, h = host.clientHeight; if (!w || !h) return;
      renderer.setSize(w, h, false); camera.aspect = w / h; camera.updateProjectionMatrix();
    }
    new ResizeObserver(resize).observe(host); resize();

    let visible = true, running = false;
    new IntersectionObserver(es => { visible = es[0].isIntersecting; if (visible && !running) { running = true; clock.getDelta(); requestAnimationFrame(tick); } }).observe(host);

    const clock = new THREE.Clock();
    function tick() {
      if (!visible) { running = false; return; }
      const dt = Math.min(clock.getDelta(), .05), t = clock.elapsedTime;
      const fit = Math.min(1, camera.aspect * .95);         // tor konteynerda siğişi uçun
      g.scale.setScalar(Math.max(.001, st.scale * fit));
      mouse.sx += (Math.max(-1, Math.min(1, mouse.x)) - mouse.sx) * .05; mouse.sy += (Math.max(-1, Math.min(1, mouse.y)) - mouse.sy) * .05;
      st.spin += dt * SPEEDS[opts.speed];
      g.rotation.y = st.spin + mouse.sx * .5; g.rotation.x = Math.sin(t * .3) * .15 - mouse.sy * .3;
      g.updateMatrixWorld(true);
      ray.setFromCamera({ x: mouse.x, y: mouse.y }, camera);
      const h = ray.intersectObject(hit)[0]; if (h) g.worldToLocal(loc.copy(h.point));
      for (let k = ripples.length - 1; k >= 0; k--) if (t - ripples[k].t0 > 2.2) ripples.splice(k, 1);
      const k6 = Math.min(1, dt * 6), morph = Math.min(1, dt * 3.2), rainbow = opts.palette === 'rainbow';
      for (let i = 0; i < N; i++) {
        const p = P[i].lerp(T[i], morph);
        let target = h ? Math.max(0, 1 - p.distanceTo(loc) / .9) : 0;
        for (const rp of ripples) { const dd = p.distanceTo(rp.p) - (t - rp.t0) * 2.6; target = Math.max(target, Math.exp(-dd * dd * 9) * (1 - (t - rp.t0) / 2.2) * .9); }
        amt[i] += (target - amt[i]) * k6; const a = amt[i];
        const wave = Math.sin(t * 1.5 + p.y * 3 + p.x * 2) * .5 + .5;
        d.position.copy(p).multiplyScalar(st.expand * (1 + a * .18));
        d.scale.setScalar(.75 + wave * .35 + a * 1.9); d.updateMatrix();
        im.setMatrixAt(i, d.matrix);
        if (rainbow) col.setHSL(frac(i / N + t * .04), .75, root.getAttribute('data-bs-theme') === 'dark' ? .55 : .5).lerp(cC, a);
        else col.copy(cA).lerp(cB, wave * .35).lerp(cC, a);
        im.setColorAt(i, col);
      }
      im.instanceMatrix.needsUpdate = true; im.instanceColor.needsUpdate = true;
      renderer.render(scene, camera);
      requestAnimationFrame(tick);
    }

    const api = window.ProfileOrb = {
      pulse() { if (ripples.length < 6) ripples.push({ p: P[(Math.random() * N) | 0].clone(), t0: clock.elapsedTime }); },
      burst() { if (!window.gsap) return; gsap.timeline().to(st, { expand: 1.4, duration: .35, ease: 'power3.out' }).to(st, { expand: 1, duration: 1.2, ease: 'elastic.out(1,.4)' }); },
      // Sozlamalar sahifasidagi jonli namuna uçun
      set(next) {
        if (next.shape && SHAPES[next.shape] && next.shape !== opts.shape) {
          opts.shape = next.shape;
          build(opts.shape).forEach((v, i) => T[i].copy(v));
          api.burst();
        }
        if (next.palette && PALETTES[next.palette]) { opts.palette = next.palette; theme(); }
        if (next.speed && next.speed in SPEEDS) opts.speed = next.speed;
      },
    };
    if (window.gsap) gsap.to(st, { scale: 1, duration: 2, ease: 'elastic.out(1,.55)', delay: .3 }); else st.scale = 1;
    running = true; requestAnimationFrame(tick);
  }

  init().catch(err => console.warn('Profil 3D orb yuklanmadi:', err));
})();
