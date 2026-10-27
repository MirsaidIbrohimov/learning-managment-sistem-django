/**
 * Keeps --qt-nav-offset (see quiz_shell.css) equal to the space the shell's
 * sticky navbar occupies, so the exam header with the timer sticks right
 * below it. accounts/base.html auto-hides the navbar on scroll-down
 * (.nav-hidden), in which case the header moves up to the top.
 */
(function () {
    'use strict';

    const page = document.querySelector('.qt-page');
    const nav = document.querySelector('#mainNavbar, .kp-nav');
    if (!page || !nav) return;

    function sync() {
        let offset = 0;
        if (!nav.classList.contains('nav-hidden')) {
            const style = getComputedStyle(nav);
            if (style.position === 'sticky' || style.position === 'fixed') {
                offset = (parseFloat(style.top) || 0) + nav.offsetHeight;
            }
        }
        page.style.setProperty('--qt-nav-offset', `${offset}px`);
    }

    sync();
    window.addEventListener('resize', sync);
    new MutationObserver(sync).observe(nav, { attributes: true, attributeFilter: ['class'] });
})();
