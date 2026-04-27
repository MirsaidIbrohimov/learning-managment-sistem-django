const express = require('express');
const path = require('path');

const app = express();
const PORT = process.env.PORT || 3000;
const DJANGO_URL = process.env.DJANGO_URL || 'http://localhost:8000';

app.use(express.static(path.join(__dirname, 'public')));

app.get('/', (req, res) => {
    res.sendFile(path.join(__dirname, 'public', 'index.html'));
});

app.listen(PORT, () => {
    console.log(`🚀 Landing page running at http://localhost:${PORT}`);
    console.log(`🔗 Django backend: ${DJANGO_URL}`);
});
