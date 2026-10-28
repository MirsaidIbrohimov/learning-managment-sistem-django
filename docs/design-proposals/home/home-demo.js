/* FAQAT PROTOTIP: namunaviy ma'lumotlar va rol almaştirgiç. LMS'da bularning hammasi Django şablonidan keladi. */
(function () {
  const $ = s => document.querySelector(s);
  const fill = (sel, items, tpl) => { const el = $(sel); if (el) el.innerHTML = items.map(tpl).join(''); };
  const av = (n, bg) => `<div class="av"${bg ? ` style="background:${bg}"` : ''}>${n}</div>`;

  /* ── Öquvçi ── */
  fill('#missions', [['Bitta video dars köring', 100, '+5', 1], ['Testdan 80% dan yuqori oling', 100, '+10', 1], ['Uy vazifasini topşiring', 40, '+15', 0], ['Kun savoliga javob bering', 0, '+10', 0]],
    ([t, p, c, d]) => `<div class="mi${d ? ' done' : ''}"><span class="ck"><i class="bi bi-check-lg"></i></span><div class="tx"><b>${t}</b><div class="pb"><i data-w="${p}"></i></div></div><span class="rw">${c}</span></div>`);
  fill('#continue', [['Backend — Python & Django', 'Bölim 4: Modellar', 64, '#047857,#a3e635', 'hdd-stack'], ['Frontend Development', 'Bölim 2: Flexbox', 38, '#2563eb,#22d3ee', 'window'], ['Ingliz tili IT uçun', 'Unit 6: Git terms', 81, '#0f766e,#2dd4bf', 'translate']],
    ([n, s, p, c, i]) => `<div class="crs" data-tilt><div class="cv" style="background:linear-gradient(135deg,${c})"><span class="tag">${p}%</span><i class="bi bi-${i}"></i></div><div class="bd"><h3>${n}</h3><small>${s}</small><div class="pb"><i data-w="${p}"></i></div><div class="ft"><a href="#"><i class="bi bi-play-fill"></i> Davom etiş</a></div></div></div>`);
  fill('#rating', [[1, 'Madina S.', 2480], [2, 'Jasur T.', 2210], [3, 'Dilnoza R.', 1990], [4, 'Siz', 1250, 1], [5, 'Bekzod A.', 1180]],
    ([r, n, c, me]) => `<div class="li${me ? ' me' : ''}"><span class="rank">${r <= 3 ? ['🥇', '🥈', '🥉'][r - 1] : r}</span>${av(n[0])}<div class="tx"><b>${n}</b></div><span class="rt"><b style="color:var(--gold)">${c.toLocaleString('ru')}</b> coin</span></div>`);
  fill('#ach', [['rocket-takeoff', 'Birinçi dars'], ['fire', '7 kun streak'], ['bullseye', '100% test'], ['coin', '1000 coin'], ['people', 'Jamoa'], ['trophy', 'Jumanji', 1], ['mortarboard', 'Sertifikat', 1], ['gem', 'Premium', 1]],
    ([i, t, l]) => `<div class="${l ? 'lock' : ''}"><i class="bi bi-${l ? 'lock' : i}"></i>${t}</div>`);
  const heat = $('#heat'); if (heat) heat.innerHTML = Array.from({ length: 126 }, (_, k) => `<i data-l="${k > 118 ? 0 : [0, 1, 1, 2, 2, 3, 4][(k * 7 + (k % 5) * 3) % 7]}"></i>`).join('');

  /* ── Öqituvçi ── */
  fill('#tCourses', [['Backend — Python & Django', 42, 140, '#047857,#a3e635', 'hdd-stack'], ['Frontend Development', 36, 120, '#2563eb,#22d3ee', 'window'], ['Python asoslari', 30, 48, '#6d28d9,#c084fc', 'filetype-py'], ['Git & GitHub', 20, 24, '#be185d,#fb7185', 'git']],
    ([n, s, l, c, i]) => `<div class="crs" data-tilt><div class="cv" style="background:linear-gradient(135deg,${c})"><i class="bi bi-${i}"></i></div><div class="bd"><h3>${n}</h3><div class="stats"><span><i class="bi bi-people"></i> ${s} öquvçi</span><span><i class="bi bi-collection-play"></i> ${l} dars</span></div><div class="ft"><a href="#">Darslar</a><a href="#">Natijalar</a></div></div></div>`);
  fill('#subs', [['Aziz N.', 'Uy vazifasi: Django forms', '10 daq', 'warn', 'Kutilmoqda'], ['Sevara M.', 'Speaking: Self introduction', '35 daq', 'warn', 'Kutilmoqda'], ['Otabek R.', 'Uy vazifasi: Flexbox layout', '1 soat', 'bad', 'Qayta topşiriş'], ['Malika Q.', 'Uy vazifasi: Git branching', '2 soat', 'warn', 'Kutilmoqda']],
    ([n, t, w, k, s]) => `<a class="li" href="#">${av(n[0])}<div class="tx"><b>${n}</b><small>${t}</small></div><div class="rt"><span class="chip3 ${k}">${s}</span><small>${w} oldin</small></div></a>`);
  fill('#risk', [['Bobur X.', 'Backend', 9], ['Nigora T.', 'Frontend', 7], ['Sardor K.', 'Python asoslari', 5]],
    ([n, c, d]) => `<div class="li">${av(n[0], 'linear-gradient(135deg,#e11d48,#f59e0b)')}<div class="tx"><b>${n}</b><small>${c}</small></div><span class="rt chip3 bad">${d} kun faolsiz</span></div>`);
  fill('#topSt', [[1, 'Madina S.', 2480], [2, 'Jasur T.', 2210], [3, 'Dilnoza R.', 1990]],
    ([r, n, c]) => `<div class="li"><span class="rank">${['🥇', '🥈', '🥉'][r - 1]}</span>${av(n[0])}<div class="tx"><b>${n}</b></div><span class="rt"><b style="color:var(--gold)">${c.toLocaleString('ru')}</b> coin</span></div>`);
  fill('#tests', [['Aziz N.', 'Django ORM testi', 92, 1], ['Sevara M.', 'Flexbox testi', 58, 0], ['Otabek R.', 'Python funksiyalar', 81, 1]],
    ([n, t, s, ok]) => `<div class="li">${av(n[0])}<div class="tx"><b>${n}</b><small>${t}</small></div><span class="rt chip3 ${ok ? 'ok' : 'bad'}">${s}% · ${ok ? 'ötdi' : 'ötmadi'}</span></div>`);

  /* ── Admin ── */
  fill('#pend', [['inbox', 9, 'Yangi arizalar', 1], ['credit-card', 5, 'Tölov çeklari', 1], ['person-plus', 3, 'Kursga sörovlar'], ['award', 2, 'Sertifikat sörovlari'], ['gem', 4, 'Premium sörovlari'], ['shield-exclamation', 0, 'Xavfsizlik']],
    ([i, c, l, hot]) => `<a href="#" class="${hot ? 'hot' : ''}"><i class="bi bi-${i}"></i><strong data-count="${c}">${c}</strong><span>${l}</span></a>`);
  fill('#apps', [['Sardor', 'Karimov', 'Backend', '10:24'], ['Lola', 'Ahmedova', 'UI/UX', '09:51'], ['Javohir', 'Ergaşev', 'Kurs belgilanmagan', 'kecha']],
    ([f, l, c, t]) => `<a class="li" href="#">${av(f[0], 'linear-gradient(135deg,#db2777,#f59e0b)')}<div class="tx"><b>${f} ${l}</b><small>${c}</small></div><span class="rt">${t}</span></a>`);
  fill('#topC', [['Backend — Python & Django', 312], ['Frontend Development', 268], ['Kompyuter savodxonligi', 190]],
    ([n, s], k) => `<div class="li"><span class="rank">${k + 1}</span><div class="tx"><b>${n}</b></div><span class="rt"><b>${s}</b> öquvçi</span></div>`);
  fill('#topT', [['Jasur Karimov', 'Backend', 4.9], ['Dilşod Rahimov', 'Frontend', 4.8], ['Nilufar Aliyeva', 'Ingliz tili', 4.7]],
    ([n, c, r]) => `<div class="li">${av(n[0])}<div class="tx"><b>${n}</b><small>${c}</small></div><span class="rt"><i class="bi bi-star-fill" style="color:var(--gold)"></i> ${r}</span></div>`);
  fill('#users', [['Aziz Nurmatov', 'Öquvçi', '12 daq'], ['Sevara Mirzayeva', 'Öquvçi', '1 soat'], ['Kamola Yusupova', 'Öqituvçi', 'kecha']],
    ([n, r, t]) => `<a class="li" href="#">${av(n[0])}<div class="tx"><b>${n}</b><small>${r}</small></div><span class="rt">${t}</span></a>`);
  fill('#act', [['Jasur Karimov', 'Uy vazifasini baholadi', 'check2-circle'], ['Admin', 'Yangi kurs qöşdi', 'plus-circle'], ['Madina S.', 'Coin dökonidan xarid', 'bag'], ['Tizim', 'Şubhali kiriş bloklandi', 'shield-lock']],
    ([n, a, i]) => `<div class="li">${av(`<i class="bi bi-${i}"></i>`, 'var(--field);color:var(--acc);border:1px solid var(--line)')}<div class="tx"><b>${n}</b><small>${a}</small></div></div>`);

  /* ── Yordamçi ── */
  fill('#pend2', [['inbox', 9, 'Arizalar', 1], ['life-preserver', 4, 'Yordam sörovlari', 1], ['journal-check', 3, 'Vazifalar'], ['alarm', 3, 'Muddati ötgan ijara']],
    ([i, c, l, hot]) => `<a href="#" class="${hot ? 'hot' : ''}"><i class="bi bi-${i}"></i><strong data-count="${c}">${c}</strong><span>${l}</span></a>`);
  fill('#apps2', [['Sardor', 'Karimov', 'Backend', '10:24'], ['Lola', 'Ahmedova', 'UI/UX', '09:51'], ['Javohir', 'Ergaşev', 'Kurs belgilanmagan', 'kecha']],
    ([f, l, c, t]) => `<a class="li" href="#">${av(f[0], 'linear-gradient(135deg,#db2777,#f59e0b)')}<div class="tx"><b>${f} ${l}</b><small>${c}</small></div><span class="rt">${t}</span></a>`);
  fill('#help', [['Bobur X.', 'Video oçilmayapti', '15 daq'], ['Nigora T.', 'Test natijasi körinmayapti', '1 soat'], ['Sardor K.', 'Parolni unutdim', '3 soat']],
    ([n, s, t]) => `<a class="li" href="#">${av(n[0])}<div class="tx"><b>${n}</b><small>${s}</small></div><span class="rt">${t}</span></a>`);
  fill('#myAct', [['Ariza qabul qilindi', '10:40'], ['Kitob ijaraga berildi', '09:15'], ['Öquvçi ma’lumoti yangilandi', 'kecha']],
    ([a, t]) => `<div class="li">${av('<i class="bi bi-check2"></i>', 'var(--lime)')}<div class="tx"><b>${a}</b></div><span class="rt">${t}</span></div>`);

  const quick = (sel, list) => fill(sel, list, ([i, l]) => `<a href="#"><i class="bi bi-${i}"></i>${l}</a>`);
  quick('#tQuick', [['plus-circle', 'Dars qöşiş'], ['clipboard-check', 'Vazifalar'], ['mic', 'Speaking'], ['ui-checks', 'Testlar'], ['people', 'Öquvçilar'], ['wallet2', 'Daromad']]);
  quick('#aQuick', [['person-plus', 'Foydalanuvçi'], ['journal-plus', 'Kurs qöşiş'], ['collection', 'Guruhlar'], ['credit-card', 'Tölovlar'], ['megaphone', 'E’lon'], ['shield-lock', 'Xavfsizlik']]);
  quick('#sQuick', [['person-plus', 'Öquvçi'], ['inbox', 'Arizalar'], ['book', 'Kitoblar'], ['life-preserver', 'Yordam'], ['journal-check', 'Vazifalar'], ['clock-history', 'Jurnal']]);

  /* ── Hero: rolga qarab ── */
  const HERO = {
    student: { badges: '<span class="bdg">Öquvçi</span><span class="bdg prem"><i class="bi bi-gem"></i> Premium</span>', name: 'Ali', msg: 'Bugun 2 ta vazifa qoldi. Keyingi dars 1 soatdan keyin boşlanadi — tayyormisiz?',
      act: '<div class="hero3-act"><a class="btn3 acc" href="#" data-mag><i class="bi bi-play-fill"></i> Darsni davom ettiriş</a><a class="btn3" href="#" data-mag><i class="bi bi-calendar-week"></i> Dars jadvali</a></div>',
      chips: [['1 250 coin', 'Balans', 'coin'], ['12 kun', 'Ketma-ket faollik', 'fire'], ['LVL 13', '1 250 XP', 'lightning-charge']] },
    teacher: { badges: '<span class="bdg">Öqituvçi</span>', name: 'Jasur', msg: '17 ta topşiriq tekşirişingizni kutmoqda. Bugun 2 ta darsingiz bor.',
      act: '<div class="search3"><i class="bi bi-search"></i><input placeholder="Öquvçi qidiriş..." aria-label="Öquvçi qidiriş"><kbd>Ctrl K</kbd></div>',
      chips: [['17 ta', 'Tekşiriş kutilmoqda', 'clipboard-check'], ['6 onlayn', 'Öquvçilarim', 'people'], ['78%', 'Örtaça ball', 'graph-up-arrow']] },
    admin: { badges: '<span class="bdg">Administrator</span>', name: 'Admin', msg: 'Bugun 214 ta kiriş, 38 kişi onlayn. 9 ta yangi ariza körib çiqilişini kutmoqda.',
      act: '<div class="search3"><i class="bi bi-search"></i><input placeholder="Foydalanuvçi, kurs yoki guruh qidiriş..." aria-label="Foydalanuvçi qidiriş"><kbd>Ctrl K</kbd></div>',
      chips: [['38 onlayn', 'Hozir saytda', 'broadcast'], ['214', 'Bugungi kirişlar', 'box-arrow-in-right'], ['+9', 'Şu hafta yangi', 'person-plus']] },
    assistant: { badges: '<span class="bdg">Yordamçi</span>', name: 'Dilnoza', msg: '9 ta yangi ariza va 4 ta yordam sörovi bor. 3 ta kitob ijarasi muddati ötgan.',
      act: '<div class="search3"><i class="bi bi-search"></i><input placeholder="Öquvçi qidiriş..." aria-label="Öquvçi qidiriş"><kbd>Ctrl K</kbd></div>',
      chips: [['16 ta', 'Kutilayotgan işlar', 'hourglass-split'], ['38 onlayn', 'Hozir saytda', 'broadcast'], ['36', 'Şu hafta amallarim', 'check2-square']] },
  };
  function hero(role) {
    const h = HERO[role], hr = new Date().getHours();
    const greet = hr < 12 ? 'Xayrli tong' : hr < 18 ? 'Xayrli kun' : 'Xayrli keç';
    $('#heroBadges').innerHTML = h.badges; $('#heroMsg').textContent = h.msg; $('#heroAct').innerHTML = h.act;
    $('#heroTitle').innerHTML = `<span class="split">${greet}, ${h.name} 👋</span>`;
    h.chips.forEach(([b, s, i], k) => { $('#c' + (k + 1) + 'b').textContent = b; $('#c' + (k + 1) + 's').textContent = s; $('#c' + (k + 1) + 'i').className = 'bi bi-' + i; });
  }
  hero('student');

  /* ── Rol almaştiriş ── */
  document.querySelectorAll('.roles button').forEach(b => b.addEventListener('click', () => {
    document.querySelectorAll('.roles button').forEach(x => x.classList.toggle('on', x === b));
    const next = document.querySelector(`.role[data-role="${b.dataset.r}"]`), cur = document.querySelector('.role.on');
    if (cur === next) return;
    const swap = () => {
      cur.classList.remove('on'); next.classList.add('on'); hero(b.dataset.r);
      window.HomeMotion && HomeMotion.enter(next);
      window.scrollTo({ top: 0, behavior: 'smooth' });
    };
    window.gsap ? gsap.to(cur, { opacity: 0, y: 20, duration: .25, onComplete: () => { gsap.set(cur, { clearProps: 'all' }); swap(); } }) : swap();
  }));

  /* Kun savoli (prototipda faqat köriniş) */
  document.querySelectorAll('#qod button').forEach(btn => btn.addEventListener('click', () => {
    const all = document.querySelectorAll('#qod button'); if ([...all].some(x => x.classList.contains('right') || x.classList.contains('wrong'))) return;
    all.forEach(x => { if (x.dataset.ok === '1') x.classList.add('right'); });
    const ok = btn.dataset.ok === '1'; if (!ok) btn.classList.add('wrong');
    const r = $('#qodRes'); r.textContent = ok ? '🎉 Töğri! +10 coin qöşildi' : 'Afsus, töğri javob: 3. Ertaga yana urinib köring!'; r.style.color = ok ? 'var(--lime)' : 'var(--red)';
    if (ok && window.ProfileOrb) ProfileOrb.burst();
  }));

  document.getElementById('tt').onclick = () => { const h = document.documentElement, t = h.getAttribute('data-bs-theme') === 'dark' ? 'light' : 'dark'; h.setAttribute('data-bs-theme', t); localStorage.setItem('theme', t); };
})();
