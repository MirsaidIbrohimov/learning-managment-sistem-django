// ============================================
// IT Creative Academy - Main JavaScript
// Three.js 3D + Animations
// ============================================

// === IMPROVED PRELOADER ===
(function() {
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

// === THREE.JS HERO 3D SCENE ===
function initHero3D() {
    const container = document.getElementById('hero-model');
    if (!container) return;

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(75, container.clientWidth / container.clientHeight, 0.1, 1000);
    const renderer = new THREE.WebGLRenderer({ alpha: true, antialias: true });
    
    renderer.setSize(container.clientWidth, container.clientHeight);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    container.appendChild(renderer.domElement);

    // Lighting
    const ambientLight = new THREE.AmbientLight(0x404040, 0.5);
    scene.add(ambientLight);

    const pointLight1 = new THREE.PointLight(0x00d4ff, 2, 100);
    pointLight1.position.set(5, 5, 5);
    scene.add(pointLight1);

    const pointLight2 = new THREE.PointLight(0x7b2ff7, 2, 100);
    pointLight2.position.set(-5, -5, 5);
    scene.add(pointLight2);

    const pointLight3 = new THREE.PointLight(0xff6b6b, 1, 100);
    pointLight3.position.set(0, 5, -5);
    scene.add(pointLight3);

    // Materials
    const wireMaterial = new THREE.MeshPhongMaterial({
        color: 0x00d4ff,
        wireframe: true,
        transparent: true,
        opacity: 0.6,
    });

    const glassMaterial = new THREE.MeshPhongMaterial({
        color: 0x7b2ff7,
        transparent: true,
        opacity: 0.3,
        shininess: 100,
    });

    const glowMaterial = new THREE.MeshPhongMaterial({
        color: 0x00d4ff,
        emissive: 0x00d4ff,
        emissiveIntensity: 0.3,
        transparent: true,
        opacity: 0.7,
    });

    // Main Torus Knot
    const torusKnotGeo = new THREE.TorusKnotGeometry(2, 0.6, 100, 16);
    const torusKnot = new THREE.Mesh(torusKnotGeo, wireMaterial);
    scene.add(torusKnot);

    // Floating Icosahedron
    const icoGeo = new THREE.IcosahedronGeometry(1.2, 0);
    const ico = new THREE.Mesh(icoGeo, glassMaterial);
    ico.position.set(3, 2, -2);
    scene.add(ico);

    // Small Octahedrons
    const octaGeo = new THREE.OctahedronGeometry(0.5, 0);
    const octaMat = new THREE.MeshPhongMaterial({ color: 0xff6b6b, wireframe: true, transparent: true, opacity: 0.5 });
    
    const octahedrons = [];
    for (let i = 0; i < 5; i++) {
        const octa = new THREE.Mesh(octaGeo, octaMat.clone());
        octa.position.set(
            (Math.random() - 0.5) * 8,
            (Math.random() - 0.5) * 8,
            (Math.random() - 0.5) * 4
        );
        octa.scale.setScalar(Math.random() * 0.5 + 0.3);
        scene.add(octa);
        octahedrons.push(octa);
    }

    // Particle system
    const particlesGeo = new THREE.BufferGeometry();
    const particlesCount = 500;
    const posArray = new Float32Array(particlesCount * 3);
    
    for (let i = 0; i < particlesCount * 3; i++) {
        posArray[i] = (Math.random() - 0.5) * 20;
    }
    
    particlesGeo.setAttribute('position', new THREE.BufferAttribute(posArray, 3));
    const particlesMat = new THREE.PointsMaterial({
        size: 0.03,
        color: 0x00d4ff,
        transparent: true,
        opacity: 0.6,
    });
    
    const particlesMesh = new THREE.Points(particlesGeo, particlesMat);
    scene.add(particlesMesh);

    // Ring
    const ringGeo = new THREE.TorusGeometry(3.5, 0.05, 16, 100);
    const ringMat = new THREE.MeshPhongMaterial({ color: 0x00d4ff, emissive: 0x00d4ff, emissiveIntensity: 0.5, transparent: true, opacity: 0.4 });
    const ring = new THREE.Mesh(ringGeo, ringMat);
    ring.rotation.x = Math.PI / 3;
    scene.add(ring);

    camera.position.z = 7;

    // Mouse interaction
    let mouseX = 0, mouseY = 0;
    document.addEventListener('mousemove', (e) => {
        mouseX = (e.clientX / window.innerWidth) * 2 - 1;
        mouseY = -(e.clientY / window.innerHeight) * 2 + 1;
    });

    // Animation loop
    function animate() {
        requestAnimationFrame(animate);

        const time = Date.now() * 0.001;

        // Main torus knot rotation
        torusKnot.rotation.x += 0.003;
        torusKnot.rotation.y += 0.005;

        // Icosahedron
        ico.rotation.x += 0.01;
        ico.rotation.y += 0.008;
        ico.position.y = 2 + Math.sin(time) * 0.5;

        // Octahedrons
        octahedrons.forEach((octa, i) => {
            octa.rotation.x += 0.005 + i * 0.002;
            octa.rotation.y += 0.008 + i * 0.001;
            octa.position.y += Math.sin(time + i) * 0.003;
        });

        // Ring rotation
        ring.rotation.z += 0.002;

        // Particles rotation
        particlesMesh.rotation.y += 0.0005;
        particlesMesh.rotation.x += 0.0002;

        // Mouse follow
        torusKnot.rotation.x += mouseY * 0.005;
        torusKnot.rotation.y += mouseX * 0.005;

        // Light animation
        pointLight1.position.x = Math.sin(time) * 5;
        pointLight1.position.y = Math.cos(time) * 5;
        pointLight2.position.x = Math.cos(time * 0.7) * 5;
        pointLight2.position.y = Math.sin(time * 0.7) * 5;

        renderer.render(scene, camera);
    }

    animate();

    // Resize
    window.addEventListener('resize', () => {
        camera.aspect = container.clientWidth / container.clientHeight;
        camera.updateProjectionMatrix();
        renderer.setSize(container.clientWidth, container.clientHeight);
    });
}

// === THREE.JS ABOUT 3D SCENE ===
function initAbout3D() {
    const container = document.getElementById('about-model');
    if (!container) return;

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(75, container.clientWidth / container.clientHeight, 0.1, 1000);
    const renderer = new THREE.WebGLRenderer({ alpha: true, antialias: true });
    
    renderer.setSize(container.clientWidth, container.clientHeight);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    container.appendChild(renderer.domElement);

    // Lighting
    const ambient = new THREE.AmbientLight(0x404040, 0.5);
    scene.add(ambient);
    const light1 = new THREE.PointLight(0x00d4ff, 2, 100);
    light1.position.set(3, 3, 3);
    scene.add(light1);
    const light2 = new THREE.PointLight(0x7b2ff7, 2, 100);
    light2.position.set(-3, -3, 3);
    scene.add(light2);

    // Laptop-like shape (simplified)
    // Screen
    const screenGeo = new THREE.BoxGeometry(3, 2, 0.1);
    const screenMat = new THREE.MeshPhongMaterial({
        color: 0x111133,
        emissive: 0x00d4ff,
        emissiveIntensity: 0.1,
        transparent: true,
        opacity: 0.8,
    });
    const screen = new THREE.Mesh(screenGeo, screenMat);
    screen.position.y = 1;
    scene.add(screen);

    // Screen content (code lines)
    const lineGeo = new THREE.BoxGeometry(2.4, 0.08, 0.02);
    const lineMat = new THREE.MeshPhongMaterial({ color: 0x00d4ff, emissive: 0x00d4ff, emissiveIntensity: 0.5 });
    
    for (let i = 0; i < 6; i++) {
        const line = new THREE.Mesh(
            new THREE.BoxGeometry(Math.random() * 1.5 + 0.8, 0.06, 0.02),
            new THREE.MeshPhongMaterial({
                color: i % 2 === 0 ? 0x00d4ff : 0x7b2ff7,
                emissive: i % 2 === 0 ? 0x00d4ff : 0x7b2ff7,
                emissiveIntensity: 0.3,
            })
        );
        line.position.set(-0.3 + Math.random() * 0.3, 1.5 - i * 0.25, 0.06);
        scene.add(line);
    }

    // Keyboard base
    const baseGeo = new THREE.BoxGeometry(3.2, 0.1, 2);
    const baseMat = new THREE.MeshPhongMaterial({ color: 0x1a1a3e, shininess: 50 });
    const base = new THREE.Mesh(baseGeo, baseMat);
    base.position.y = -0.1;
    base.rotation.x = -0.2;
    scene.add(base);

    // Floating code symbols
    const symbols = ['{ }', '< />', 'fn()', '[ ]', '==='];
    const textMeshes = [];
    
    // Use simple shapes instead of text (since TextGeometry needs fonts)
    for (let i = 0; i < 8; i++) {
        const geo = i % 2 === 0 
            ? new THREE.TetrahedronGeometry(0.15, 0)
            : new THREE.DodecahedronGeometry(0.12, 0);
        const mat = new THREE.MeshPhongMaterial({
            color: [0x00d4ff, 0x7b2ff7, 0x00ff88, 0xff6b6b][i % 4],
            wireframe: true,
            transparent: true,
            opacity: 0.5,
        });
        const mesh = new THREE.Mesh(geo, mat);
        mesh.position.set(
            (Math.random() - 0.5) * 6,
            (Math.random() - 0.5) * 4,
            (Math.random() - 0.5) * 3
        );
        scene.add(mesh);
        textMeshes.push(mesh);
    }

    // Particles
    const pGeo = new THREE.BufferGeometry();
    const pCount = 200;
    const pPos = new Float32Array(pCount * 3);
    for (let i = 0; i < pCount * 3; i++) {
        pPos[i] = (Math.random() - 0.5) * 15;
    }
    pGeo.setAttribute('position', new THREE.BufferAttribute(pPos, 3));
    const pMat = new THREE.PointsMaterial({ size: 0.02, color: 0x7b2ff7, transparent: true, opacity: 0.5 });
    const particles = new THREE.Points(pGeo, pMat);
    scene.add(particles);

    camera.position.z = 5;
    camera.position.y = 1;

    function animate() {
        requestAnimationFrame(animate);
        const time = Date.now() * 0.001;

        screen.rotation.y = Math.sin(time * 0.3) * 0.1;
        base.rotation.y = Math.sin(time * 0.3) * 0.1;

        textMeshes.forEach((m, i) => {
            m.rotation.x += 0.01 + i * 0.002;
            m.rotation.y += 0.008;
            m.position.y += Math.sin(time + i * 0.5) * 0.003;
        });

        particles.rotation.y += 0.0003;

        light1.position.x = Math.sin(time * 0.5) * 4;
        light2.position.x = Math.cos(time * 0.5) * 4;

        renderer.render(scene, camera);
    }

    animate();

    window.addEventListener('resize', () => {
        camera.aspect = container.clientWidth / container.clientHeight;
        camera.updateProjectionMatrix();
        renderer.setSize(container.clientWidth, container.clientHeight);
    });
}

// === HERO BACKGROUND PARTICLES (Canvas) ===
function initHeroBackground() {
    const canvas = document.getElementById('hero-canvas');
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    let width = canvas.width = window.innerWidth;
    let height = canvas.height = window.innerHeight;

    const particles = [];
    const particleCount = 80;

    class Particle {
        constructor() {
            this.reset();
        }
        reset() {
            this.x = Math.random() * width;
            this.y = Math.random() * height;
            this.size = Math.random() * 2 + 0.5;
            this.speedX = (Math.random() - 0.5) * 0.5;
            this.speedY = (Math.random() - 0.5) * 0.5;
            this.opacity = Math.random() * 0.5 + 0.1;
        }
        update() {
            this.x += this.speedX;
            this.y += this.speedY;
            if (this.x < 0 || this.x > width) this.speedX *= -1;
            if (this.y < 0 || this.y > height) this.speedY *= -1;
        }
        draw() {
            ctx.beginPath();
            ctx.arc(this.x, this.y, this.size, 0, Math.PI * 2);
            ctx.fillStyle = `rgba(0, 212, 255, ${this.opacity})`;
            ctx.fill();
        }
    }

    for (let i = 0; i < particleCount; i++) {
        particles.push(new Particle());
    }

    function drawLines() {
        for (let i = 0; i < particles.length; i++) {
            for (let j = i + 1; j < particles.length; j++) {
                const dx = particles[i].x - particles[j].x;
                const dy = particles[i].y - particles[j].y;
                const dist = Math.sqrt(dx * dx + dy * dy);
                if (dist < 150) {
                    ctx.beginPath();
                    ctx.moveTo(particles[i].x, particles[i].y);
                    ctx.lineTo(particles[j].x, particles[j].y);
                    ctx.strokeStyle = `rgba(0, 212, 255, ${0.1 * (1 - dist / 150)})`;
                    ctx.lineWidth = 0.5;
                    ctx.stroke();
                }
            }
        }
    }

    function animate() {
        requestAnimationFrame(animate);
        ctx.clearRect(0, 0, width, height);
        particles.forEach(p => {
            p.update();
            p.draw();
        });
        drawLines();
    }

    animate();

    window.addEventListener('resize', () => {
        width = canvas.width = window.innerWidth;
        height = canvas.height = window.innerHeight;
    });
}

// === NAVBAR SCROLL EFFECT ===
function initNavbar() {
    const navbar = document.querySelector('.navbar');
    const hamburger = document.querySelector('.hamburger');
    const navLinks = document.querySelector('.nav-links');

    window.addEventListener('scroll', () => {
        if (window.scrollY > 50) {
            navbar.classList.add('scrolled');
        } else {
            navbar.classList.remove('scrolled');
        }
    });

    // Mobile menu
    if (hamburger) {
        hamburger.addEventListener('click', () => {
            hamburger.classList.toggle('active');
            navLinks.classList.toggle('active');
        });

        // Close on link click
        navLinks.querySelectorAll('a').forEach(link => {
            link.addEventListener('click', () => {
                hamburger.classList.remove('active');
                navLinks.classList.remove('active');
            });
        });
    }
}

// === SCROLL REVEAL ===
function initScrollReveal() {
    const reveals = document.querySelectorAll('.reveal');

    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                entry.target.classList.add('active');
            }
        });
    }, {
        threshold: 0.15,
        rootMargin: '0px 0px -50px 0px',
    });

    reveals.forEach(el => observer.observe(el));
}

// === COUNTER ANIMATION ===
function initCounters() {
    const counters = document.querySelectorAll('[data-count]');

    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                const el = entry.target;
                const target = parseInt(el.getAttribute('data-count'));
                const suffix = el.getAttribute('data-suffix') || '';
                const duration = 2000;
                const start = 0;
                const startTime = performance.now();

                function update(currentTime) {
                    const elapsed = currentTime - startTime;
                    const progress = Math.min(elapsed / duration, 1);
                    // Ease out cubic
                    const eased = 1 - Math.pow(1 - progress, 3);
                    const current = Math.floor(eased * target);
                    el.textContent = current + suffix;
                    if (progress < 1) requestAnimationFrame(update);
                }

                requestAnimationFrame(update);
                observer.unobserve(el);
            }
        });
    }, { threshold: 0.5 });

    counters.forEach(el => observer.observe(el));
}

// === CONTACT FORM ===
function initContactForm() {
    const form = document.getElementById('applicationForm');
    if (!form) return;

    form.addEventListener('submit', async (e) => {
        e.preventDefault();

        const submitBtn = form.querySelector('.form-submit');
        const messageDiv = form.querySelector('.form-message');
        const originalText = submitBtn.innerHTML;

        submitBtn.disabled = true;
        submitBtn.innerHTML = '<span class="spinner"></span> Yuborilmoqda...';

        const formData = {
            firstName: form.firstName.value.trim(),
            lastName: form.lastName.value.trim(),
            phone: form.phone.value.trim(),
            courseInterest: form.courseInterest.value,
            message: form.message ? form.message.value.trim() : '',
        };

        try {
            const response = await fetch('/api/application', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(formData),
            });

            const data = await response.json();

            messageDiv.className = 'form-message ' + (data.success ? 'success' : 'error');
            messageDiv.textContent = data.message;
            messageDiv.style.display = 'block';

            if (data.success) {
                form.reset();
            }
        } catch (error) {
            messageDiv.className = 'form-message error';
            messageDiv.textContent = 'Xatolik yuz berdi. Iltimos, qaytadan urinib ko\'ring.';
            messageDiv.style.display = 'block';
        }

        submitBtn.disabled = false;
        submitBtn.innerHTML = originalText;

        setTimeout(() => {
            messageDiv.style.display = 'none';
        }, 5000);
    });
}

// === BACK TO TOP ===
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

// === CSS PARTICLES ===
function initParticles() {
    const container = document.querySelector('.particles-container');
    if (!container) return;

    for (let i = 0; i < 30; i++) {
        const particle = document.createElement('div');
        particle.className = 'particle';
        particle.style.left = Math.random() * 100 + '%';
        particle.style.animationDuration = (Math.random() * 15 + 10) + 's';
        particle.style.animationDelay = (Math.random() * 10) + 's';
        particle.style.width = (Math.random() * 4 + 1) + 'px';
        particle.style.height = particle.style.width;
        container.appendChild(particle);
    }
}

// === SMOOTH SCROLL FOR ANCHOR LINKS ===
function initSmoothScroll() {
    document.querySelectorAll('a[href^="#"]').forEach(anchor => {
        anchor.addEventListener('click', function(e) {
            e.preventDefault();
            const target = document.querySelector(this.getAttribute('href'));
            if (target) {
                const offset = 80;
                const top = target.getBoundingClientRect().top + window.pageYOffset - offset;
                window.scrollTo({ top, behavior: 'smooth' });
            }
        });
    });
}

// === TILT EFFECT FOR CARDS ===
function initTiltEffect() {
    const cards = document.querySelectorAll('.course-card, .advantage-card');
    
    cards.forEach(card => {
        card.addEventListener('mousemove', (e) => {
            const rect = card.getBoundingClientRect();
            const x = e.clientX - rect.left;
            const y = e.clientY - rect.top;
            const centerX = rect.width / 2;
            const centerY = rect.height / 2;
            const rotateX = (y - centerY) / 20;
            const rotateY = (centerX - x) / 20;
            
            card.style.transform = `perspective(1000px) rotateX(${rotateX}deg) rotateY(${rotateY}deg) translateY(-10px)`;
        });

        card.addEventListener('mouseleave', () => {
            card.style.transform = 'perspective(1000px) rotateX(0) rotateY(0) translateY(0)';
        });
    });
}

// === TYPING EFFECT ===
function initTypingEffect() {
    const el = document.querySelector('.typing-text');
    if (!el) return;

    const texts = ['Dasturlash', 'Web Development', 'Mobile Apps', 'AI & ML', 'Design'];
    let textIndex = 0;
    let charIndex = 0;
    let isDeleting = false;

    function type() {
        const currentText = texts[textIndex];
        
        if (isDeleting) {
            el.textContent = currentText.substring(0, charIndex - 1);
            charIndex--;
        } else {
            el.textContent = currentText.substring(0, charIndex + 1);
            charIndex++;
        }

        let speed = isDeleting ? 50 : 100;

        if (!isDeleting && charIndex === currentText.length) {
            speed = 2000;
            isDeleting = true;
        } else if (isDeleting && charIndex === 0) {
            isDeleting = false;
            textIndex = (textIndex + 1) % texts.length;
            speed = 500;
        }

        setTimeout(type, speed);
    }

    type();
}

// === THEME TOGGLE (DARK/LIGHT) ===
function initThemeToggle() {
    const toggle = document.querySelector('.theme-toggle');
    if (!toggle) return;
    
    // Check saved preference
    const saved = localStorage.getItem('itc-theme');
    if (saved === 'light') {
        document.body.classList.add('light-mode');
    }
    
    toggle.addEventListener('click', () => {
        document.body.classList.toggle('light-mode');
        const isLight = document.body.classList.contains('light-mode');
        localStorage.setItem('itc-theme', isLight ? 'light' : 'dark');
    });
}

// === FAQ ACCORDION ===
function initFAQ() {
    const faqItems = document.querySelectorAll('.faq-item');
    
    faqItems.forEach(item => {
        const question = item.querySelector('.faq-question');
        question.addEventListener('click', () => {
            const isActive = item.classList.contains('active');
            
            // Close all
            faqItems.forEach(i => i.classList.remove('active'));
            
            // Toggle clicked
            if (!isActive) {
                item.classList.add('active');
            }
        });
    });
}

// === INITIALIZE EVERYTHING ===
document.addEventListener('DOMContentLoaded', () => {
    initThemeToggle();
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
    initFAQ();
});
