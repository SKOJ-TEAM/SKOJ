document.addEventListener('DOMContentLoaded', function () {
    var navigation = document.getElementById('navigation');
    var navList = document.getElementById('nav-list');
    var navToggle = document.getElementById('navicon');
    function onMediaChange(query, callback) {
        if (query.addEventListener) query.addEventListener('change', callback);
        else query.addListener(callback);
    }
    function updateNavigationHeight() {
        document.documentElement.style.setProperty('--site-nav-height', navigation.offsetHeight + 'px');
    }
    function closeMenu() {
        navList.classList.remove('show');
        navToggle.setAttribute('aria-expanded', 'false');
        updateNavigationHeight();
    }
    navToggle.addEventListener('click', function (event) {
        event.stopPropagation();
        var expanded = navList.classList.toggle('show');
        navToggle.setAttribute('aria-expanded', expanded ? 'true' : 'false');
        updateNavigationHeight();
    });
    document.addEventListener('click', function (event) {
        if (!navList.contains(event.target)) closeMenu();
    });
    document.addEventListener('keydown', function (event) {
        if (event.key === 'Escape' && navList.classList.contains('show')) {
            closeMenu();
            navToggle.focus();
        }
    });
    onMediaChange(window.matchMedia('(max-width: 1100px)'), closeMenu);
    updateNavigationHeight();
    if (window.ResizeObserver) {
        new ResizeObserver(updateNavigationHeight).observe(navigation);
    } else {
        window.addEventListener('resize', updateNavigationHeight);
    }

    document.querySelectorAll('[data-responsive-details]').forEach(function (details) {
        var compact = window.matchMedia('(max-width: ' + details.dataset.responsiveDetails + 'px)');
        function updateDetails() {
            // Preserve a user's choice until the layout actually crosses this breakpoint.
            details.open = !compact.matches;
        }
        updateDetails();
        onMediaChange(compact, updateDetails);
    });
});
