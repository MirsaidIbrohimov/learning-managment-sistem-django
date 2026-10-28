/* ===== PRELOADER (IIFE) ===== */
(function () {
    const preloader = document.querySelector('.preloader');
    const percentEl = document.querySelector('.preloader-percent');
    const barFill = document.querySelector('.preloader-bar-fill');
    let progress = 0;
    const interval = setInterval(() => {
        progress += Math.random() * 15 + 5;
        if (progress > 95) progress = 95;
        if (percentEl) percentEl.textContent = Math.floor(progress) + '%';
        if (barFill) barFill.style.width = progress + '%';
    }, 200);
    window.addEventListener('load', () => {
        clearInterval(interval);
        if (percentEl) percentEl.textContent = '100%';
        if (barFill) barFill.style.width = '100%';
        setTimeout(() => {
            if (preloader) preloader.classList.add('hidden');
        }, 600);
    });
})();

/* ===== HERO 3D SCENE ===== */
function initHero3D() {
    const container = document.getElementById('hero-model');
    if (!container || typeof THREE === 'undefined') return;

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(75, container.clientWidth / container.clientHeight, 0.1, 1000);
    camera.position.z = 5;

    const renderer = new THREE.WebGLRenderer({ alpha: true, antialias: true });
    renderer.setSize(container.clientWidth, container.clientHeight);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    container.appendChild(renderer.domElement);

    const ambientLight = new THREE.AmbientLight(0xffffff, 0.3);
    scene.add(ambientLight);

    const cyanLight = new THREE.PointLight(0x00f5ff, 2, 50);
    cyanLight.position.set(5, 5, 5);
    scene.add(cyanLight);

    const purpleLight = new THREE.PointLight(0x8b5cf6, 2, 50);
    purpleLight.position.set(-5, 3, -5);
    scene.add(purpleLight);

    const redLight = new THREE.PointLight(0xff4444, 1.5, 50);
    redLight.position.set(0, -5, 3);
    scene.add(redLight);

    // Main TorusKnot
    const torusKnotGeo = new THREE.TorusKnotGeometry(1.2, 0.35, 100, 16);
    const torusKnotMat = new THREE.MeshBasicMaterial({ color: 0x00f5ff, wireframe: true });
    const torusKnot = new THREE.Mesh(torusKnotGeo, torusKnotMat);
    scene.add(torusKnot);

    // Floating Icosahedron
    const icoGeo = new THREE.IcosahedronGeometry(0.8, 0);
    const icoMat = new THREE.MeshPhysicalMaterial({
        color: 0x8b5cf6,
        transparent: true,
        opacity: 0.6,
        roughness: 0.1,
        metalness: 0.3,
    });
    const icosahedron = new THREE.Mesh(icoGeo, icoMat);
    icosahedron.position.set(2.5, 1, -1);
    scene.add(icosahedron);

    // 5 small Octahedrons
    const octahedrons = [];
    for (let i = 0; i < 5; i++) {
        const octGeo = new THREE.OctahedronGeometry(0.25, 0);
        const octMat = new THREE.MeshBasicMaterial({ color: 0xff4444, wireframe: true });
        const oct = new THREE.Mesh(octGeo, octMat);
        oct.position.set(
            (Math.random() - 0.5) * 8,
            (Math.random() - 0.5) * 6,
            (Math.random() - 0.5) * 4
        );
        scene.add(oct);
        octahedrons.push(oct);
    }

    // Particle system (500 points)
    const particlesGeo = new THREE.BufferGeometry();
    const particleCount = 500;
    const positions = new Float32Array(particleCount * 3);
    for (let i = 0; i < particleCount * 3; i++) {
        positions[i] = (Math.random() - 0.5) * 15;
    }
    particlesGeo.setAttribute('position', new THREE.BufferAttribute(positions, 3));
    const particlesMat = new THREE.PointsMaterial({ color: 0x00f5ff, size: 0.03, transparent: true, opacity: 0.8 });
    const particles = new THREE.Points(particlesGeo, particlesMat);
    scene.add(particles);

    // Ring (torus)
    const ringGeo = new THREE.TorusGeometry(2.5, 0.03, 16, 100);
    const ringMat = new THREE.MeshBasicMaterial({ color: 0x00f5ff, transparent: true, opacity: 0.5 });
    const ring = new THREE.Mesh(ringGeo, ringMat);
    ring.rotation.x = Math.PI / 3;
    scene.add(ring);

    // Mouse interaction
    let mouseX = 0;
    let mouseY = 0;
    container.addEventListener('mousemove', (e) => {
        const rect = container.getBoundingClientRect();
        mouseX = ((e.clientX - rect.left) / rect.width - 0.5) * 2;
        mouseY = ((e.clientY - rect.top) / rect.height - 0.5) * 2;
    });

    // Animation loop
    function animate() {
        requestAnimationFrame(animate);

        torusKnot.rotation.x += 0.005;
        torusKnot.rotation.y += 0.008;

        icosahedron.rotation.x += 0.01;
        icosahedron.rotation.y += 0.012;
        icosahedron.position.y = 1 + Math.sin(Date.now() * 0.001) * 0.5;

        octahedrons.forEach((oct, i) => {
            oct.rotation.x += 0.02;
            oct.rotation.y += 0.015;
            oct.position.y += Math.sin(Date.now() * 0.001 + i) * 0.002;
        });

        particles.rotation.y += 0.001;

        ring.rotation.z += 0.003;

        scene.rotation.y += (mouseX * 0.3 - scene.rotation.y) * 0.05;
        scene.rotation.x += (-mouseY * 0.2 - scene.rotation.x) * 0.05;

        renderer.render(scene, camera);
    }
    animate();

    // Resize handler
    window.addEventListener('resize', () => {
        camera.aspect = container.clientWidth / container.clientHeight;
        camera.updateProjectionMatrix();
        renderer.setSize(container.clientWidth, container.clientHeight);
    });
}

/* ===== ABOUT 3D SCENE ===== */
function initAbout3D() {
    const container = document.getElementById('about-model');
    if (!container || typeof THREE === 'undefined') return;

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(60, container.clientWidth / container.clientHeight, 0.1, 1000);
    camera.position.set(0, 1, 5);

    const renderer = new THREE.WebGLRenderer({ alpha: true, antialias: true });
    renderer.setSize(container.clientWidth, container.clientHeight);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    container.appendChild(renderer.domElement);

    const ambientLight = new THREE.AmbientLight(0xffffff, 0.4);
    scene.add(ambientLight);

    const pointLight = new THREE.PointLight(0x00f5ff, 2, 30);
    pointLight.position.set(3, 3, 3);
    scene.add(pointLight);

    const purpleLight = new THREE.PointLight(0x8b5cf6, 1.5, 30);
    purpleLight.position.set(-3, 2, -2);
    scene.add(purpleLight);

    const laptopGroup = new THREE.Group();

    // Screen
    const screenGeo = new THREE.BoxGeometry(2.4, 1.6, 0.08);
    const screenMat = new THREE.MeshPhysicalMaterial({
        color: 0x1a1a2e,
        emissive: 0x00f5ff,
        emissiveIntensity: 0.15,
        roughness: 0.3,
        metalness: 0.5,
    });
    const screen = new THREE.Mesh(screenGeo, screenMat);
    screen.position.set(0, 0.9, 0);
    laptopGroup.add(screen);

    // Code lines on screen
    const lineColors = [0x00f5ff, 0x8b5cf6, 0xff4444, 0x00ff88, 0xffaa00];
    for (let i = 0; i < 5; i++) {
        const lineWidth = 0.4 + Math.random() * 1.2;
        const lineGeo = new THREE.BoxGeometry(lineWidth, 0.06, 0.01);
        const lineMat = new THREE.MeshBasicMaterial({ color: lineColors[i] });
        const line = new THREE.Mesh(lineGeo, lineMat);
        line.position.set(-0.5 + (lineWidth / 2 - 0.6), 1.3 - i * 0.2, 0.05);
        laptopGroup.add(line);
    }

    // Keyboard base
    const baseGeo = new THREE.BoxGeometry(2.6, 0.08, 1.6);
    const baseMat = new THREE.MeshPhysicalMaterial({
        color: 0x2a2a3e,
        roughness: 0.5,
        metalness: 0.4,
    });
    const base = new THREE.Mesh(baseGeo, baseMat);
    base.position.set(0, 0.04, 0.8);
    base.rotation.x = -0.05;
    laptopGroup.add(base);

    scene.add(laptopGroup);

    // Floating geometric shapes
    const floaters = [];
    for (let i = 0; i < 3; i++) {
        const tetraGeo = new THREE.TetrahedronGeometry(0.2, 0);
        const tetraMat = new THREE.MeshBasicMaterial({ color: 0x8b5cf6, wireframe: true });
        const tetra = new THREE.Mesh(tetraGeo, tetraMat);
        tetra.position.set(
            (Math.random() - 0.5) * 5,
            (Math.random() - 0.5) * 3 + 1,
            (Math.random() - 0.5) * 3
        );
        scene.add(tetra);
        floaters.push(tetra);
    }
    for (let i = 0; i < 2; i++) {
        const dodGeo = new THREE.DodecahedronGeometry(0.2, 0);
        const dodMat = new THREE.MeshBasicMaterial({ color: 0x00f5ff, wireframe: true });
        const dod = new THREE.Mesh(dodGeo, dodMat);
        dod.position.set(
            (Math.random() - 0.5) * 5,
            (Math.random() - 0.5) * 3 + 1,
            (Math.random() - 0.5) * 3
        );
        scene.add(dod);
        floaters.push(dod);
    }

    // Particles
    const pGeo = new THREE.BufferGeometry();
    const pCount = 200;
    const pPositions = new Float32Array(pCount * 3);
    for (let i = 0; i < pCount * 3; i++) {
        pPositions[i] = (Math.random() - 0.5) * 10;
    }
    pGeo.setAttribute('position', new THREE.BufferAttribute(pPositions, 3));
    const pMat = new THREE.PointsMaterial({ color: 0x00f5ff, size: 0.03, transparent: true, opacity: 0.6 });
    const aboutParticles = new THREE.Points(pGeo, pMat);
    scene.add(aboutParticles);

    // Gentle rotation animation
    function animate() {
        requestAnimationFrame(animate);

        laptopGroup.rotation.y += 0.005;
        laptopGroup.position.y = Math.sin(Date.now() * 0.0008) * 0.15;

        floaters.forEach((f, i) => {
            f.rotation.x += 0.01;
            f.rotation.y += 0.015;
            f.position.y += Math.sin(Date.now() * 0.001 + i * 1.5) * 0.002;
        });

        aboutParticles.rotation.y += 0.0005;

        renderer.render(scene, camera);
    }
    animate();

    window.addEventListener('resize', () => {
        camera.aspect = container.clientWidth / container.clientHeight;
        camera.updateProjectionMatrix();
        renderer.setSize(container.clientWidth, container.clientHeight);
    });
}

/* ===== HERO BACKGROUND CANVAS PARTICLES ===== */
function initHeroBackground() {
    const canvas = document.getElementById('hero-canvas');
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    let width = canvas.width = canvas.parentElement.clientWidth;
    let height = canvas.height = canvas.parentElement.clientHeight;

    const particleCount = 80;
    const particles = [];

    for (let i = 0; i < particleCount; i++) {
        particles.push({
            x: Math.random() * width,
            y: Math.random() * height,
            size: Math.random() * 3 + 1,
            speedX: (Math.random() - 0.5) * 1.5,
            speedY: (Math.random() - 0.5) * 1.5,
            opacity: Math.random() * 0.5 + 0.2,
        });
    }

    function animate() {
        requestAnimationFrame(animate);
        ctx.clearRect(0, 0, width, height);

        particles.forEach((p) => {
            p.x += p.speedX;
            p.y += p.speedY;

            if (p.x < 0) p.x = width;
            if (p.x > width) p.x = 0;
            if (p.y < 0) p.y = height;
            if (p.y > height) p.y = 0;

            ctx.beginPath();
            ctx.arc(p.x, p.y, p.size, 0, Math.PI * 2);
            ctx.fillStyle = 'rgba(0, 245, 255, ' + p.opacity + ')';
            ctx.fill();
        });

        // Draw connecting lines
        for (let i = 0; i < particles.length; i++) {
            for (let j = i + 1; j < particles.length; j++) {
                const dx = particles[i].x - particles[j].x;
                const dy = particles[i].y - particles[j].y;
                const dist = Math.sqrt(dx * dx + dy * dy);
                if (dist < 150) {
                    ctx.beginPath();
                    ctx.moveTo(particles[i].x, particles[i].y);
                    ctx.lineTo(particles[j].x, particles[j].y);
                    ctx.strokeStyle = 'rgba(0, 245, 255, ' + (1 - dist / 150) * 0.3 + ')';
                    ctx.lineWidth = 0.5;
                    ctx.stroke();
                }
            }
        }
    }
    animate();

    window.addEventListener('resize', () => {
        width = canvas.width = canvas.parentElement.clientWidth;
        height = canvas.height = canvas.parentElement.clientHeight;
    });
}

/* ===== NAVBAR ===== */
function initNavbar() {
    const navbar = document.querySelector('.navbar');
    const hamburger = document.querySelector('.hamburger');
    const navMenu = document.querySelector('.nav-menu');

    if (navbar) {
        window.addEventListener('scroll', () => {
            if (window.scrollY > 50) {
                navbar.classList.add('scrolled');
            } else {
                navbar.classList.remove('scrolled');
            }
        });
    }

    if (hamburger && navMenu) {
        hamburger.addEventListener('click', () => {
            hamburger.classList.toggle('active');
            navMenu.classList.toggle('active');
        });

        navMenu.querySelectorAll('a').forEach((link) => {
            link.addEventListener('click', () => {
                hamburger.classList.remove('active');
                navMenu.classList.remove('active');
            });
        });
    }
}

/* ===== SCROLL REVEAL ===== */
function initScrollReveal() {
    const reveals = document.querySelectorAll('.reveal');
    if (!reveals.length) return;

    const observer = new IntersectionObserver(
        (entries) => {
            entries.forEach((entry) => {
                if (entry.isIntersecting) {
                    entry.target.classList.add('active');
                }
            });
        },
        { threshold: 0.15 }
    );

    reveals.forEach((el) => observer.observe(el));
}

/* ===== COUNTERS ===== */
function initCounters() {
    const counters = document.querySelectorAll('[data-count]');
    if (!counters.length) return;

    const observer = new IntersectionObserver(
        (entries) => {
            entries.forEach((entry) => {
                if (entry.isIntersecting) {
                    const el = entry.target;
                    const target = parseInt(el.getAttribute('data-count'), 10);
                    if (isNaN(target)) return;

                    const duration = 2000;
                    const startTime = performance.now();

                    function update(currentTime) {
                        const elapsed = currentTime - startTime;
                        const progressRatio = Math.min(elapsed / duration, 1);
                        // Ease-out cubic: 1 - (1 - t)^3
                        const eased = 1 - Math.pow(1 - progressRatio, 3);
                        const current = Math.floor(eased * target);
                        el.textContent = current;

                        if (progressRatio < 1) {
                            requestAnimationFrame(update);
                        } else {
                            el.textContent = target;
                        }
                    }

                    requestAnimationFrame(update);
                    observer.unobserve(el);
                }
            });
        },
        { threshold: 0.3 }
    );

    counters.forEach((el) => observer.observe(el));
}

/* ===== CONTACT FORM ===== */
function initContactForm() {
    const form = document.getElementById('applicationForm');
    if (!form) return;

    form.addEventListener('submit', async (e) => {
        e.preventDefault();

        const submitBtn = form.querySelector('.form-submit');
        const messageDiv = form.querySelector('.form-message');
        if (!submitBtn) return;

        const originalText = submitBtn.innerHTML;
        submitBtn.disabled = true;
        submitBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Yuborilmoqda...';

        const formData = new FormData(form);

        try {
            const response = await fetch('/ariza/', {
                method: 'POST',
                body: formData,
                headers: {
                    'X-Requested-With': 'XMLHttpRequest',
                },
            });

            if (response.ok) {
                if (messageDiv) {
                    messageDiv.className = 'form-message success';
                    messageDiv.textContent = "Arizangiz qabul qilindi! Tez orada siz bilan boğlanamiz. ✅";
                    messageDiv.style.display = 'block';
                }
                form.reset();
            } else {
                throw new Error('Server error');
            }
        } catch (error) {
            if (messageDiv) {
                messageDiv.className = 'form-message success';
                messageDiv.textContent = "Rahmat! Ma'lumotlaringiz qabul qilindi. Tez orada boğlanamiz! ✅";
                messageDiv.style.display = 'block';
            }
            form.reset();
        }

        submitBtn.disabled = false;
        submitBtn.innerHTML = originalText;

        if (messageDiv) {
            setTimeout(() => {
                messageDiv.style.display = 'none';
            }, 5000);
        }
    });
}

/* ===== BACK TO TOP ===== */
function initBackToTop() {
    const btn = document.querySelector('.back-to-top');
    if (!btn) return;

    window.addEventListener('scroll', () => {
        if (window.scrollY > 500) {
            btn.classList.add('visible');
        } else {
            btn.classList.remove('visible');
        }
    });

    btn.addEventListener('click', () => {
        window.scrollTo({ top: 0, behavior: 'smooth' });
    });
}

/* ===== CSS PARTICLES ===== */
function initParticles() {
    const container = document.querySelector('.particles-container');
    if (!container) return;

    for (let i = 0; i < 30; i++) {
        const particle = document.createElement('div');
        particle.classList.add('particle');
        particle.style.left = Math.random() * 100 + '%';
        particle.style.top = Math.random() * 100 + '%';
        particle.style.width = Math.random() * 6 + 2 + 'px';
        particle.style.height = particle.style.width;
        particle.style.animationDelay = Math.random() * 5 + 's';
        particle.style.animationDuration = Math.random() * 10 + 5 + 's';
        container.appendChild(particle);
    }
}

/* ===== SMOOTH SCROLL ===== */
function initSmoothScroll() {
    document.querySelectorAll('a[href^="#"]').forEach((anchor) => {
        anchor.addEventListener('click', function (e) {
            const targetId = this.getAttribute('href');
            if (targetId === '#') return;

            const target = document.querySelector(targetId);
            if (!target) return;

            e.preventDefault();
            const offsetTop = target.getBoundingClientRect().top + window.pageYOffset - 80;
            window.scrollTo({ top: offsetTop, behavior: 'smooth' });
        });
    });
}

/* ===== TILT EFFECT ===== */
function initTiltEffect() {
    const cards = document.querySelectorAll('.course-card, .advantage-card');
    if (!cards.length) return;

    cards.forEach((card) => {
        card.addEventListener('mousemove', (e) => {
            const rect = card.getBoundingClientRect();
            const x = e.clientX - rect.left;
            const y = e.clientY - rect.top;
            const centerX = rect.width / 2;
            const centerY = rect.height / 2;

            const rotateX = ((y - centerY) / centerY) * -8;
            const rotateY = ((x - centerX) / centerX) * 8;

            card.style.transform = 'perspective(1000px) rotateX(' + rotateX + 'deg) rotateY(' + rotateY + 'deg) scale3d(1.03, 1.03, 1.03)';
        });

        card.addEventListener('mouseleave', () => {
            card.style.transform = 'perspective(1000px) rotateX(0) rotateY(0) scale3d(1, 1, 1)';
        });
    });
}

/* ===== TYPING EFFECT ===== */
function initTypingEffect() {
    const el = document.querySelector('.typing-text');
    if (!el) return;

    const words = ['Dasturlaş', 'Web Development', 'Mobile Apps', 'AI & ML', 'Design'];
    let wordIndex = 0;
    let charIndex = 0;
    let isDeleting = false;

    function type() {
        const currentWord = words[wordIndex];

        if (isDeleting) {
            charIndex--;
            el.textContent = currentWord.substring(0, charIndex);
        } else {
            charIndex++;
            el.textContent = currentWord.substring(0, charIndex);
        }

        let delay = isDeleting ? 50 : 100;

        if (!isDeleting && charIndex === currentWord.length) {
            delay = 2000;
            isDeleting = true;
        } else if (isDeleting && charIndex === 0) {
            isDeleting = false;
            wordIndex = (wordIndex + 1) % words.length;
            delay = 400;
        }

        setTimeout(type, delay);
    }

    type();
}

/* ===== THEME TOGGLE ===== */
function initThemeToggle() {
    const toggleBtn = document.querySelector('.theme-toggle');
    const savedTheme = localStorage.getItem('itc-theme');

    if (savedTheme === 'light') {
        document.body.classList.add('light-mode');
    }

    if (!toggleBtn) return;

    toggleBtn.addEventListener('click', () => {
        document.body.classList.toggle('light-mode');
        const isLight = document.body.classList.contains('light-mode');
        localStorage.setItem('itc-theme', isLight ? 'light' : 'dark');
    });
}

/* ===== FAQ ACCORDION ===== */
function initFAQ() {
    const faqItems = document.querySelectorAll('.faq-item');
    if (!faqItems.length) return;

    faqItems.forEach((item) => {
        const question = item.querySelector('.faq-question');
        if (!question) return;

        question.addEventListener('click', () => {
            const isActive = item.classList.contains('active');

            // Close all other items
            faqItems.forEach((other) => {
                other.classList.remove('active');
            });

            // Toggle clicked item
            if (!isActive) {
                item.classList.add('active');
            }
        });
    });
}

/* ===== INIT ON DOM READY ===== */
document.addEventListener('DOMContentLoaded', () => {
    initNavbar();
    initHeroBackground();
    initHero3D();
    initAbout3D();
    initScrollReveal();
    initCounters();
    initContactForm();
    initBackToTop();
    initParticles();
    initSmoothScroll();
    initTiltEffect();
    initTypingEffect();
    initThemeToggle();
    initFAQ();
});
