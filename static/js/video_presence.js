/* Position each attention check once; keep it reachable after viewport changes. */
(function () {
    'use strict';
    let previous = -1;
    window.videoNeedsNativeControls = function () {
        return !!(window.matchMedia && window.matchMedia('(pointer: coarse)').matches);
    };
    window.focusVideoControl = function (element) {
        if (!element || typeof element.focus !== 'function') return;
        try { element.focus({preventScroll: true}); }
        catch (_) { try { element.focus(); } catch (_) {} }
    };
    window.placeVideoPresence = function (overlay) {
        const modal = overlay.querySelector('.vl-presence-modal');
        const anchors = [[0, 0], [0.5, 0], [1, 0], [0, 0.5], [1, 0.5], [0, 1], [0.5, 1], [1, 1]];
        const choices = anchors.map((_, index) => index).filter(index => index !== previous);
        previous = choices[Math.floor(Math.random() * choices.length)];
        const anchor = anchors[previous];
        overlay.classList.add('vl-presence-roaming');
        function position() {
            const bounds = overlay.getBoundingClientRect();
            const viewport = window.visualViewport;
            const left = Math.max(0, viewport ? viewport.offsetLeft - bounds.left : -bounds.left);
            const top = Math.max(0, viewport ? viewport.offsetTop - bounds.top : -bounds.top);
            const right = Math.min(bounds.width, (viewport ? viewport.offsetLeft + viewport.width : window.innerWidth) - bounds.left);
            const bottom = Math.min(bounds.height, (viewport ? viewport.offsetTop + viewport.height : window.innerHeight) - bounds.top);
            const width = Math.max(1, right - left);
            const height = Math.max(1, bottom - top);
            const gap = Math.min(20, width / 20, height / 20);
            modal.style.width = Math.max(1, Math.min(360, width - gap * 2)) + 'px';
            modal.style.maxHeight = Math.max(1, height - gap * 2) + 'px';
            const x = left + gap + Math.max(0, width - gap * 2 - modal.offsetWidth) * anchor[0];
            const y = top + gap + Math.max(0, height - gap * 2 - modal.offsetHeight) * anchor[1];
            modal.style.left = Math.round(x) + 'px';
            modal.style.top = Math.round(y) + 'px';
        }
        function trapFocus(event) {
            if (event.key === 'Tab') {
                event.preventDefault();
                window.focusVideoControl(modal.querySelector('button'));
            }
        }
        position();
        window.addEventListener('resize', position);
        document.addEventListener('fullscreenchange', position);
        document.addEventListener('webkitfullscreenchange', position);
        overlay.addEventListener('keydown', trapFocus);
        if (window.visualViewport) {
            window.visualViewport.addEventListener('resize', position);
            window.visualViewport.addEventListener('scroll', position);
        }
        const observer = window.ResizeObserver ? new ResizeObserver(position) : null;
        if (observer) observer.observe(modal);
        return function () {
            window.removeEventListener('resize', position);
            document.removeEventListener('fullscreenchange', position);
            document.removeEventListener('webkitfullscreenchange', position);
            overlay.removeEventListener('keydown', trapFocus);
            if (window.visualViewport) {
                window.visualViewport.removeEventListener('resize', position);
                window.visualViewport.removeEventListener('scroll', position);
            }
            if (observer) observer.disconnect();
        };
    };
})();
