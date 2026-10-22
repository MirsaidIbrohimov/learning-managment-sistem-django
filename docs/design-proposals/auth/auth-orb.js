/* IT Creative — auth sahifalari uchun 3D "Reactive Orb".
 * Klassik skript: Three.js sahifadagi importmap orqali dinamik import qilinadi.
 * Natija: window.AuthOrb = { pulse(), setSecret(bool), setTint(hex|null), burst(), spin(), theme() }
 */
(function () {
  const stub = { pulse() {}, setSecret() {}, setTint() {}, burst() {}, spin() {}, theme() {} };
  window.AuthOrb = stub;

  async function init() {
    const THREE = await import('three');
    const { RoomEnvironment } = await import('three/addons/environments/RoomEnvironment.js');
    const root = document.documentElement;
    const stage = document.querySelector('[data-orb-stage]');
    const canvas = document.getElementById('gl');
    const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
    const small = innerWidth < 700;

    const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
    renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
    renderer.setSize(innerWidth, innerHeight);
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(45, innerWidth / innerHeight, .1, 100);
    camera.position.set(0, 0, 8);
    scene.environment = new THREE.PMREMGenerator(renderer).fromScene(new RoomEnvironment(), .04).texture;
    scene.add(new THREE.AmbientLight(0xffffff, .5));
    const l1 = new THREE.PointLight(0x22d3ee, 40, 30); l1.position.set(4, 3, 4); scene.add(l1);
    const l2 = new THREE.PointLight(0xa78bfa, 40, 30); l2.position.set(-4, -2, 3); scene.add(l2);

    // Fon zarrachalari
    const PN = small ? 600 : 1400, pos = new Float32Array(PN * 3);
    for (let i = 0; i < PN; i++) {
      const r = 6 + Math.random() * 10, t = Math.random() * Math.PI * 2, p = Math.acos(2 * Math.random() - 1);
      pos.set([r * Math.sin(p) * Math.cos(t), r * Math.sin(p) * Math.sin(t), r * Math.cos(p) - 4], i * 3);
    }
    const pGeo = new THREE.BufferGeometry(); pGeo.setAttribute('position', new THREE.BufferAttribute(pos, 3));
    const pMat = new THREE.PointsMaterial({ size: .035, transparent: true, depthWrite: false });
    const stars = new THREE.Points(pGeo, pMat); scene.add(stars);

    // Orb: Fibonacci shar bo'ylab joylashgan kichik sharlar
    const N = small ? 450 : 820, R = 1.55, ga = Math.PI * (3 - Math.sqrt(5));
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

    const st = { radius: 0, expand: 1, spinY: 0, tint: new THREE.Color(0xf472b6), tintT: new THREE.Color(0xf472b6), secret: 0, secretT: 0 };
    const ripples = [];
    const mouse = { x: -9, y: -9, sx: 0, sy: 0 };
    addEventListener('pointermove', e => { mouse.x = e.clientX / innerWidth * 2 - 1; mouse.y = -(e.clientY / innerHeight * 2 - 1); });

    const cA = new THREE.Color(), cB = new THREE.Color(), cS = new THREE.Color(0x22d3ee), col = new THREE.Color();
    const ray = new THREE.Raycaster(), loc = new THREE.Vector3(), d = new THREE.Object3D();
    function theme() {
      const light = root.dataset.theme === 'light';
      pMat.color.set(light ? 0x6d28d9 : 0x9ad8ff); pMat.opacity = light ? .45 : .8;
      cA.set(light ? 0x7c3aed : 0x4c1d95); cB.set(light ? 0x0891b2 : 0x22d3ee);
    }
    theme();

    // Orbni sahna (stage) elementi markaziga joylashtirish
    function place() {
      // Matn bloki (stage-copy) egallagan joydan tashqaridagi bo'sh joyga joylashadi
      const r = stage.getBoundingClientRect(), copy = stage.querySelector('.stage-copy');
      const copyH = copy && copy.offsetParent ? copy.offsetHeight + 24 : 0, freeH = r.height - copyH;
      const halfH = Math.tan(THREE.MathUtils.degToRad(22.5)) * 8, halfW = halfH * camera.aspect;
      const cx = (r.left + r.width / 2) / innerWidth * 2 - 1, cy = -((r.top + freeH / 2) / innerHeight * 2 - 1);
      g.position.set(cx * halfW, cy * halfH, 0);
      const px = Math.min(r.width, freeH) * .4;
      return (px * 2 * halfH / innerHeight) / R;
    }

    const clock = new THREE.Clock();
    function tick() {
      const dt = Math.min(clock.getDelta(), .05), t = clock.elapsedTime;
      const fit = place();
      st.secret += (st.secretT - st.secret) * Math.min(1, dt * 5);
      st.tint.lerp(st.tintT, Math.min(1, dt * 4));
      g.scale.setScalar(Math.max(.001, fit * st.radius * (1 - st.secret * .16)));
      mouse.sx += (Math.max(-1, Math.min(1, mouse.x)) - mouse.sx) * .05; mouse.sy += (Math.max(-1, Math.min(1, mouse.y)) - mouse.sy) * .05;
      g.rotation.y = t * (.15 + st.secret * .6) + st.spinY + mouse.sx * .4; g.rotation.x = Math.sin(t * .3) * .15 - mouse.sy * .25;
      g.updateMatrixWorld(true);

      ray.setFromCamera({ x: mouse.x, y: mouse.y }, camera);
      const h = ray.intersectObject(hit)[0]; if (h) g.worldToLocal(loc.copy(h.point));
      for (let k = ripples.length - 1; k >= 0; k--) if (t - ripples[k].t0 > 2.2) ripples.splice(k, 1);

      const k6 = Math.min(1, dt * 6);
      for (let i = 0; i < N; i++) {
        const p = P[i];
        let target = h ? Math.max(0, 1 - p.distanceTo(loc) / .9) : 0;
        for (const rp of ripples) {             // klaviatura bosilganda tarqaladigan to'lqin
          const front = (t - rp.t0) * 2.6, dd = p.distanceTo(rp.p) - front;
          target = Math.max(target, Math.exp(-dd * dd * 9) * (1 - (t - rp.t0) / 2.2) * .9);
        }
        amt[i] += (target - amt[i]) * k6; const a = amt[i];
        const wave = Math.sin(t * 1.5 + p.y * 3 + p.x * 2) * .5 + .5;
        d.position.copy(p).multiplyScalar(st.expand * (1 + a * .18));
        d.scale.setScalar(.75 + wave * .35 + a * 1.9); d.updateMatrix();
        im.setMatrixAt(i, d.matrix);
        col.copy(cA).lerp(cB, wave * .35 + st.secret * .45).lerp(st.secret > .5 ? cS : st.tint, a);
        im.setColorAt(i, col);
      }
      im.instanceMatrix.needsUpdate = true; im.instanceColor.needsUpdate = true;
      stars.rotation.y = t * .015 + mouse.sx * .05;
      camera.position.x += (mouse.sx * .3 - camera.position.x) * .05; camera.position.y += (mouse.sy * .2 - camera.position.y) * .05; camera.lookAt(0, 0, 0);
      renderer.render(scene, camera);
      requestAnimationFrame(tick);
    }
    addEventListener('resize', () => { renderer.setSize(innerWidth, innerHeight); camera.aspect = innerWidth / innerHeight; camera.updateProjectionMatrix(); });

    const api = {
      pulse() { if (ripples.length < 6) ripples.push({ p: P[(Math.random() * N) | 0], t0: clock.elapsedTime }); },
      setSecret(on) { st.secretT = on ? 1 : 0; },
      setTint(hex) { st.tintT.set(hex == null ? 0xf472b6 : hex); },
      burst() { gsap.timeline().to(st, { expand: 1.45, duration: .35, ease: 'power3.out' }).to(st, { expand: 1, duration: 1.2, ease: 'elastic.out(1,.4)' }); },
      spin() { gsap.to(st, { spinY: st.spinY + Math.PI, duration: 1.4, ease: 'expo.inOut' }); },
      theme,
    };
    window.AuthOrb = api;
    gsap.to(st, { radius: 1, duration: reduce ? 0 : 2, ease: 'elastic.out(1,.55)', delay: .2 });
    tick();
  }

  init().catch(err => console.warn('3D orb yuklanmadi:', err));
})();
