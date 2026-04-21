const express = require('express');
const path = require('path');
const helmet = require('helmet');
const compression = require('compression');
const rateLimit = require('express-rate-limit');

const app = express();
const PORT = process.env.PORT || 3000;

// Security
app.use(helmet({
    contentSecurityPolicy: {
        directives: {
            defaultSrc: ["'self'"],
            scriptSrc: ["'self'", "'unsafe-inline'", "'unsafe-eval'", "https://cdnjs.cloudflare.com", "https://cdn.jsdelivr.net", "https://unpkg.com"],
            styleSrc: ["'self'", "'unsafe-inline'", "https://fonts.googleapis.com", "https://cdnjs.cloudflare.com", "https://cdn.jsdelivr.net"],
            fontSrc: ["'self'", "https://fonts.gstatic.com", "https://cdnjs.cloudflare.com"],
            imgSrc: ["'self'", "data:", "https:", "blob:"],
            connectSrc: ["'self'"],
            workerSrc: ["'self'", "blob:"],
        },
    },
}));

// Compression for SEO speed
app.use(compression());

// Rate limiting
const limiter = rateLimit({
    windowMs: 15 * 60 * 1000,
    max: 100,
});
app.use('/api/', limiter);

// Static files
app.use(express.static(path.join(__dirname, 'public'), {
    maxAge: '1d',
    etag: true,
}));

// Body parser
app.use(express.json());
app.use(express.urlencoded({ extended: true }));

// View engine
app.set('view engine', 'ejs');
app.set('views', path.join(__dirname, 'views'));

// SEO: Robots.txt
app.get('/robots.txt', (req, res) => {
    res.type('text/plain');
    res.send(`User-agent: *
Allow: /
Sitemap: https://itc-academy.uz/sitemap.xml`);
});

// SEO: Sitemap
app.get('/sitemap.xml', (req, res) => {
    res.type('application/xml');
    res.send(`<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url>
    <loc>https://itc-academy.uz/</loc>
    <lastmod>${new Date().toISOString().split('T')[0]}</lastmod>
    <changefreq>weekly</changefreq>
    <priority>1.0</priority>
  </url>
  <url>
    <loc>https://itc-academy.uz/#courses</loc>
    <changefreq>weekly</changefreq>
    <priority>0.8</priority>
  </url>
  <url>
    <loc>https://itc-academy.uz/#about</loc>
    <changefreq>monthly</changefreq>
    <priority>0.7</priority>
  </url>
  <url>
    <loc>https://itc-academy.uz/#contact</loc>
    <changefreq>monthly</changefreq>
    <priority>0.6</priority>
  </url>
</urlset>`);
});

// Routes
app.get('/', (req, res) => {
    res.render('index', {
        title: 'IT Creative Academy - Zamonaviy IT ta\'lim markazi',
        description: 'IT Creative Academy - Dasturlash, Web Development, Mobile Development va boshqa IT yo\'nalishlar bo\'yicha professional ta\'lim. O\'zbekistonda eng zamonaviy o\'quv markaz.',
        keywords: 'IT kurslar, dasturlash kurslari, web development, IT Creative, o\'quv markaz, Qarshi, programming, kodlash',
        url: 'https://itc-academy.uz',
    });
});

// API: Application form
app.post('/api/application', (req, res) => {
    const { firstName, lastName, phone, courseInterest, message } = req.body;

    if (!firstName || !lastName || !phone) {
        return res.status(400).json({ success: false, message: 'Iltimos, barcha maydonlarni to\'ldiring' });
    }

    // Here you could save to database or send to Django API
    console.log('New application:', { firstName, lastName, phone, courseInterest, message });

    res.json({ success: true, message: 'Arizangiz qabul qilindi! Tez orada siz bilan bog\'lanamiz.' });
});

// 404
app.use((req, res) => {
    res.status(404).render('404', { title: '404 - Sahifa topilmadi' });
});

app.listen(PORT, () => {
    console.log(`🚀 IT Creative Academy Landing running on http://localhost:${PORT}`);
});
