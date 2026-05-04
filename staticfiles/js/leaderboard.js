/**
 * Leaderboard Module
 * Fetches data from API and renders the leaderboard dynamically.
 * 
 * Required: window.LB_CONFIG = { apiUrl, isPremium, isStaff, userId, userRole, userFullName }
 */
(function() {
    'use strict';

    var CFG = window.LB_CONFIG || {};
    var API_URL = CFG.apiUrl || '/api/v1/reyting/';
    var IS_PREMIUM = CFG.isPremium || false;
    var IS_STAFF = CFG.isStaff || false;
    var USER_ID = CFG.userId || 0;
    var USER_ROLE = CFG.userRole || '';
    var USER_FULL_NAME = CFG.userFullName || '';

    var currentTab = 'coins';
    var currentProfession = '';
    var currentSearch = '';
    var searchTimer = null;
    var abortCtrl = null;

    // Elements
    var tabCoins = document.getElementById('tabCoins');
    var tabScore = document.getElementById('tabScore');
    var searchInput = document.getElementById('lbSearch');
    var pillsContainer = document.getElementById('pillsContainer');
    var lbLoading = document.getElementById('lbLoading');
    var lbContent = document.getElementById('lbContent');
    var lbUserRank = document.getElementById('lbUserRank');
    var lbPodium = document.getElementById('lbPodium');
    var lbList = document.getElementById('lbList');
    var lbEmpty = document.getElementById('lbEmpty');
    var premiumOverlay = document.getElementById('premiumOverlay');

    // ====== HELPERS ======
    function fmtCoins(n) {
        if (n >= 1000000) return (n / 1000000).toFixed(1).replace(/\.0$/, '') + 'M';
        if (n >= 1000) return (n / 1000).toFixed(1).replace(/\.0$/, '') + 'K';
        return n.toString();
    }

    function esc(s) {
        var d = document.createElement('div');
        d.textContent = s || '';
        return d.innerHTML;
    }

    function studentHref(s) {
        if (s.is_you) return '/profile/';
        if (IS_PREMIUM || IS_STAFF) return '/students/' + s.id + '/';
        return '#';
    }

    function canSee(s) {
        return IS_PREMIUM || IS_STAFF || s.is_you;
    }

    function valueIcon() {
        return currentTab === 'score' ? 'bi-mortarboard-fill' : 'bi-coin';
    }

    function valueLabel(v) {
        return currentTab === 'score' ? (v + ' ball') : fmtCoins(v);
    }

    // ====== TABS ======
    if (tabCoins) tabCoins.addEventListener('click', function() { switchTab('coins'); });
    if (tabScore) tabScore.addEventListener('click', function() { switchTab('score'); });

    function switchTab(tab) {
        currentTab = tab;
        if (tabCoins) tabCoins.classList.toggle('active', tab === 'coins');
        if (tabScore) tabScore.classList.toggle('active', tab === 'score');
        fetchData();
    }

    // ====== SEARCH ======
    if (searchInput) {
        searchInput.addEventListener('input', function() {
            clearTimeout(searchTimer);
            searchTimer = setTimeout(function() {
                currentSearch = searchInput.value.trim();
                fetchData();
            }, 350);
        });
    }

    // ====== PILLS ======
    function renderPills(professions) {
        if (!pillsContainer) return;
        var html = '<button class="lb-pill' + (!currentProfession ? ' active' : '') + '" data-prof="">Barchasi</button>';
        professions.forEach(function(p) {
            var active = (String(currentProfession) === String(p.id)) ? ' active' : '';
            html += '<button class="lb-pill' + active + '" data-prof="' + p.id + '">' + esc(p.name) + '</button>';
        });
        pillsContainer.innerHTML = html;

        pillsContainer.querySelectorAll('.lb-pill').forEach(function(btn) {
            btn.addEventListener('click', function() {
                currentProfession = this.dataset.prof;
                pillsContainer.querySelectorAll('.lb-pill').forEach(function(b) { b.classList.remove('active'); });
                this.classList.add('active');
                fetchData();
            });
        });

        initPillsScroll();
    }

    function initPillsScroll() {
        var prevBtn = document.querySelector('.lb-pills-prev');
        var nextBtn = document.querySelector('.lb-pills-next');
        if (!prevBtn || !nextBtn || !pillsContainer) return;

        prevBtn.onclick = function() { pillsContainer.scrollBy({ left: -200, behavior: 'smooth' }); };
        nextBtn.onclick = function() { pillsContainer.scrollBy({ left: 200, behavior: 'smooth' }); };

        function updateVis() {
            prevBtn.style.opacity = pillsContainer.scrollLeft > 0 ? '1' : '0.5';
            prevBtn.style.pointerEvents = pillsContainer.scrollLeft > 0 ? 'auto' : 'none';
            var hasScroll = pillsContainer.scrollWidth > pillsContainer.clientWidth;
            var atEnd = pillsContainer.scrollLeft >= (pillsContainer.scrollWidth - pillsContainer.clientWidth - 10);
            nextBtn.style.opacity = (hasScroll && !atEnd) ? '1' : '0.5';
            nextBtn.style.pointerEvents = (hasScroll && !atEnd) ? 'auto' : 'none';
        }
        pillsContainer.addEventListener('scroll', updateVis);
        updateVis();
    }

    // ====== RENDER ======
    function renderUserRank(data) {
        if (!lbUserRank) return;
        if (!data.user_rank || USER_ROLE !== 'student') {
            lbUserRank.style.display = 'none';
            if (premiumOverlay) premiumOverlay.style.display = 'none';
            return;
        }

        if (premiumOverlay && !IS_PREMIUM && !IS_STAFF) {
            premiumOverlay.style.display = '';
        }

        lbUserRank.style.display = '';
        var icon = currentTab === 'score'
            ? '<i class="bi bi-mortarboard-fill"></i> ' + data.user_value + ' ball'
            : '<i class="bi bi-coin"></i> ' + fmtCoins(data.user_value);
        lbUserRank.innerHTML =
            '<div class="lb-your-rank-card">' +
                '<div class="yr-rank">' + data.user_rank + '</div>' +
                '<div class="yr-info">' +
                    '<div class="yr-label">Sizning o\'rningiz</div>' +
                    '<div class="yr-name">' + esc(USER_FULL_NAME) + '</div>' +
                '</div>' +
                '<div class="yr-coins">' + icon + '</div>' +
            '</div>';
    }

    function renderPodium(students) {
        if (!lbPodium) return;
        if (students.length < 3) { lbPodium.innerHTML = ''; return; }

        var top3 = students.slice(0, 3);
        var order = [top3[1], top3[0], top3[2]];
        var positions = [2, 1, 3];

        var html = '<div class="top-3-podium">';
        order.forEach(function(s, i) {
            var pos = positions[i];
            var blurred = (!canSee(s) && !s.is_you) ? ' lb-blurred-top' : '';
            var href = studentHref(s);
            var avatar = s.photo
                ? '<img src="' + esc(s.photo) + '" alt="' + esc(s.first_name) + '" onclick="openLbPhoto(\'' + esc(s.photo) + '\', \'' + esc(s.full_name) + '\', event)" style="cursor:pointer;">'
                : '<span>' + esc(s.initials) + '</span>';
            html += '<a href="' + href + '" class="top-3-item top-3-position-' + pos + blurred + '">' +
                '<div class="crown-badge">' + pos + '</div>' +
                '<div class="avatar-circle">' + avatar + '</div>' +
                '<div class="player-info">' +
                    '<div class="player-name-top3">' + esc(s.first_name) + '</div>' +
                    '<div class="coins-value"><i class="bi ' + valueIcon() + '"></i> <span>' + valueLabel(s.value) + '</span></div>' +
                '</div></a>';
        });
        html += '</div>';
        lbPodium.innerHTML = html;
    }

    function renderList(students) {
        if (!lbList) return;
        if (students.length <= 3) { lbList.innerHTML = ''; return; }

        var vi = valueIcon();
        var html = '<div class="lb-list-header"><div>#</div><div>Foydalanuvchi</div><div>' +
                   (currentTab === 'score' ? 'Ball' : 'Coin') + '</div><div></div></div>';

        students.slice(3).forEach(function(s, i) {
            var rank = s.rank;
            var delay = (i + 1) * 100;
            var visible = canSee(s);

            if (visible) {
                var isYou = s.is_you ? ' is-you' : '';
                var isPrem = s.is_premium ? ' is-premium' : '';
                var premAvBorder = s.is_premium ? ' premium-avatar-border' : '';
                var premNameCls = s.is_premium ? ' premium-user-name' : '';
                var premCoinCls = s.is_premium ? ' premium-coin-row' : '';

                var avatar = s.photo
                    ? '<img src="' + esc(s.photo) + '" alt="" class="lb-user-avatar' + premAvBorder + '" onclick="openLbPhoto(\'' + esc(s.photo) + '\', \'' + esc(s.full_name) + '\', event)" style="cursor:pointer;">'
                    : '<div class="lb-user-placeholder' + premAvBorder + '">' + esc(s.initials) + '</div>';

                var name = esc(s.full_name);
                if (s.is_premium) name += ' <i class="bi bi-patch-check-fill premium-star"></i>';
                if (s.is_you) name += '<span class="lb-badge">Siz</span>';

                html += '<a href="' + studentHref(s) + '" class="lb-row' + isYou + isPrem + '" style="animation-delay:' + delay + 'ms">' +
                    '<div><span class="lb-rank">' + rank + '</span></div>' +
                    '<div class="lb-user">' + avatar + '<div class="lb-user-info"><div class="lb-user-name' + premNameCls + '">' + name + '</div>' +
                    '<div class="lb-username">@' + esc(s.username) + '</div></div></div>' +
                    '<div><span class="lb-coin' + premCoinCls + '"><i class="bi ' + vi + '"></i> <span>' + valueLabel(s.value) + '</span></span></div>' +
                    '<i class="bi bi-chevron-right lb-chevron"></i></a>';
            } else {
                var avatar2 = s.photo
                    ? '<img src="' + esc(s.photo) + '" alt="" class="lb-user-avatar" onclick="openLbPhoto(\'' + esc(s.photo) + '\', \'' + esc(s.full_name) + '\', event)" style="cursor:pointer;">'
                    : '<div class="lb-user-placeholder">' + esc(s.initials) + '</div>';

                html += '<div class="lb-row lb-blurred" style="animation-delay:' + delay + 'ms">' +
                    '<div><span class="lb-rank">' + rank + '</span></div>' +
                    '<div class="lb-user">' + avatar2 + '<div class="lb-user-info"><div class="lb-user-name">' + esc(s.full_name) + '</div>' +
                    '<div class="lb-username">@' + esc(s.username) + '</div></div></div>' +
                    '<div><span class="lb-coin"><i class="bi ' + vi + '"></i> <span>' + valueLabel(s.value) + '</span></span></div>' +
                    '<div class="lb-lock-icon"><i class="bi bi-lock-fill"></i></div></div>';
            }
        });

        lbList.innerHTML = html;
    }

    // ====== FETCH ======
    function fetchData() {
        if (abortCtrl) abortCtrl.abort();
        abortCtrl = new AbortController();

        if (lbLoading) lbLoading.style.display = '';
        if (lbContent) lbContent.style.display = 'none';

        var params = new URLSearchParams();
        params.set('tab', currentTab);
        if (currentProfession) params.set('profession', currentProfession);
        if (currentSearch) params.set('q', currentSearch);

        fetch(API_URL + '?' + params.toString(), {
            headers: { 'X-Requested-With': 'XMLHttpRequest' },
            credentials: 'same-origin',
            signal: abortCtrl.signal
        })
        .then(function(r) {
            if (!r.ok) throw new Error('HTTP ' + r.status);
            return r.json();
        })
        .then(function(data) {
            if (lbLoading) lbLoading.style.display = 'none';
            if (lbContent) lbContent.style.display = '';

            if (pillsContainer && pillsContainer.children.length === 0) {
                renderPills(data.professions);
            }

            if (data.students.length === 0) {
                if (lbPodium) lbPodium.innerHTML = '';
                if (lbList) lbList.innerHTML = '';
                if (lbUserRank) lbUserRank.style.display = 'none';
                if (premiumOverlay) premiumOverlay.style.display = 'none';
                if (lbEmpty) lbEmpty.style.display = '';
            } else {
                if (lbEmpty) lbEmpty.style.display = 'none';
                renderUserRank(data);
                renderPodium(data.students);
                renderList(data.students);
            }

            // Update URL without reload
            var url = new URL(window.location);
            url.searchParams.set('tab', currentTab);
            if (currentProfession) url.searchParams.set('profession', currentProfession);
            else url.searchParams.delete('profession');
            if (currentSearch) url.searchParams.set('q', currentSearch);
            else url.searchParams.delete('q');
            history.replaceState(null, '', url);
        })
        .catch(function(err) {
            if (err.name === 'AbortError') return;
            if (lbLoading) lbLoading.style.display = 'none';
            if (lbContent) lbContent.style.display = '';
            if (lbList) lbList.innerHTML = '<div class="lb-list"><div class="lb-empty"><div class="lb-empty-icon"><i class="bi bi-exclamation-triangle"></i></div><h4>Xatolik yuz berdi</h4><p>Qayta urinib ko\'ring</p></div></div>';
        });
    }

    // ====== LIGHTBOX ======
    window.openLbPhoto = function(url, name, e) {
        e.preventDefault();
        e.stopPropagation();
        var img = document.getElementById('lbPhotoImg');
        var nameEl = document.getElementById('lbPhotoName');
        var lb = document.getElementById('lbPhotoLightbox');
        if (img) img.src = url;
        if (nameEl) nameEl.innerHTML = '<i class="bi bi-person-circle"></i> ' + name;
        if (lb) lb.classList.add('active');
        document.body.style.overflow = 'hidden';
    };

    window.closeLbPhoto = function(e) {
        if (e.target.closest('.lb-photo-lightbox-img')) return;
        var lb = document.getElementById('lbPhotoLightbox');
        if (lb) lb.classList.remove('active');
        document.body.style.overflow = '';
    };

    window.closePremiumOverlay = function() {
        var overlay = document.getElementById('premiumOverlay');
        if (overlay) {
            overlay.classList.add('hiding');
            setTimeout(function() { overlay.style.display = 'none'; overlay.classList.remove('hiding'); }, 400);
        }
    };

    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape') {
            var lb = document.getElementById('lbPhotoLightbox');
            if (lb && lb.classList.contains('active')) {
                lb.classList.remove('active');
                document.body.style.overflow = '';
            }
        }
    });

    // ====== INIT ======
    var urlParams = new URLSearchParams(window.location.search);
    if (urlParams.get('tab') === 'score') { currentTab = 'score'; switchTab('score'); }
    if (urlParams.get('profession')) currentProfession = urlParams.get('profession');
    if (urlParams.get('q')) { currentSearch = urlParams.get('q'); if (searchInput) searchInput.value = currentSearch; }

    fetchData();
})();
