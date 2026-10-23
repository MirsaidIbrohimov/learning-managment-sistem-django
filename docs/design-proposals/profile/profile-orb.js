/* IT Creative — profil hero'si uchun 3D "Reactive Orb" (konteyner ichida).
 * Klassik skript: Three.js sahifadagi importmap orqali dinamik import qilinadi.
 * <div data-pf-orb> ichiga o'z canvas'ini qo'yadi. Ko'rinmaganda chizishni to'xtatadi.
 * Mavzu: <html data-bs-theme="dark|light">.
 */
(function () {
  const host = document.querySelector('[data-pf-orb]');
  if (!host) return;

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

    const N = small ? 420 : 760, R = 1.55, ga = Math.PI * (3 - Math.sqrt(5));
    const g = new THREE.Group(); scene.add(g);
    const im = new THREE.InstancedMesh(new THREE.SphereGeometry(.075, 16, 12),
      new THREE.MeshPhysicalMaterial({ metalness: .2, roughness: .25, clearcoat: 1 }), N);
    const P = [], amt = new Float32Array(N);
    for (let i = 0; i < N; i++) {
      const y = 1 - i / (N - 1) * 2, r = Math.sqrt(1 - y * y), th = ga * i;
      P.push(new THREE.Vector3(Math.cos(th) * r, y, Math.sin(th) * r).multiplyScalar(R));
    }
    const hit = new THREE.Mesh(new THREE.SphereGeometry(R * 1.05, 24, 16), new THREE.MeshBasicMaterial({ visible: false }));
    g.add(im, hit);

    const st = { scale: 0, expand: 1 };
    const mouse = { x: -9, y: -9, sx: 0, sy: 0 };
    addEventListener('pointermove', e => {
      const r = host.getBoundingClientRect();
      mouse.x = (e.clientX - r.left) / r.width * 2 - 1; mouse.y = -((e.clientY - r.top) / r.height * 2 - 1);
    });

    const cA = new THREE.Color(), cB = new THREE.Color(), cC = new THREE.Color(0xf472b6), col = new THREE.Color();
    const ray = new THREE.Raycaster(), loc = new THREE.Vector3(), d = new THREE.Object3D();
    const ripples = [];
    function theme() {
      const light = root.getAttribute('data-bs-theme') !== 'dark';
      cA.set(light ? 0x7c3aed : 0x4c1d95); cB.set(light ? 0x0891b2 : 0x22d3ee);
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
      const fit = Math.min(1, camera.aspect * .95);         // tor konteynerda sig'ishi uchun
      g.scale.setScalar(Math.max(.001, st.scale * fit));
      mouse.sx += (Math.max(-1, Math.min(1, mouse.x)) - mouse.sx) * .05; mouse.sy += (Math.max(-1, Math.min(1, mouse.y)) - mouse.sy) * .05;
      g.rotation.y = t * .15 + mouse.sx * .5; g.rotation.x = Math.sin(t * .3) * .15 - mouse.sy * .3;
      g.updateMatrixWorld(true);
      ray.setFromCamera({ x: mouse.x, y: mouse.y }, camera);
      const h = ray.intersectObject(hit)[0]; if (h) g.worldToLocal(loc.copy(h.point));
      for (let k = ripples.length - 1; k >= 0; k--) if (t - ripples[k].t0 > 2.2) ripples.splice(k, 1);
      const k6 = Math.min(1, dt * 6);
      for (let i = 0; i < N; i++) {
        const p = P[i];
        let target = h ? Math.max(0, 1 - p.distanceTo(loc) / .9) : 0;
        for (const rp of ripples) { const dd = p.distanceTo(rp.p) - (t - rp.t0) * 2.6; target = Math.max(target, Math.exp(-dd * dd * 9) * (1 - (t - rp.t0) / 2.2) * .9); }
        amt[i] += (target - amt[i]) * k6; const a = amt[i];
        const wave = Math.sin(t * 1.5 + p.y * 3 + p.x * 2) * .5 + .5;
        d.position.copy(p).multiplyScalar(st.expand * (1 + a * .18));
        d.scale.setScalar(.75 + wave * .35 + a * 1.9); d.updateMatrix();
        im.setMatrixAt(i, d.matrix); im.setColorAt(i, col.copy(cA).lerp(cB, wave * .35).lerp(cC, a));
      }
      im.instanceMatrix.needsUpdate = true; im.instanceColor.needsUpdate = true;
      renderer.render(scene, camera);
      requestAnimationFrame(tick);
    }

    window.ProfileOrb = {
      pulse() { if (ripples.length < 6) ripples.push({ p: P[(Math.random() * N) | 0], t0: clock.elapsedTime }); },
      burst() { if (!window.gsap) return; gsap.timeline().to(st, { expand: 1.4, duration: .35, ease: 'power3.out' }).to(st, { expand: 1, duration: 1.2, ease: 'elastic.out(1,.4)' }); },
    };
    if (window.gsap) gsap.to(st, { scale: 1, duration: 2, ease: 'elastic.out(1,.55)', delay: .3 }); else st.scale = 1;
    running = true; requestAnimationFrame(tick);
  }

  init().catch(err => console.warn('Profil 3D orb yuklanmadi:', err));
})();
