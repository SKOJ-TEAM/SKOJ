document.addEventListener('DOMContentLoaded', function () {
    var navigation = document.getElementById('navigation');
    function updateNavigationHeight() {
        document.documentElement.style.setProperty('--site-nav-height', navigation.offsetHeight + 'px');
    }
    updateNavigationHeight();
    if (window.ResizeObserver) {
        new ResizeObserver(updateNavigationHeight).observe(navigation);
    } else {
        window.addEventListener('resize', updateNavigationHeight);
        document.getElementById('navicon').addEventListener('click', updateNavigationHeight);
    }

    document.querySelectorAll('[data-responsive-details]').forEach(function (details) {
        var compact = window.matchMedia('(max-width: ' + details.dataset.responsiveDetails + 'px)');
        function updateDetails() {
            // Preserve a user's choice until the layout actually crosses this breakpoint.
            details.open = !compact.matches;
        }
        updateDetails();
        compact.addEventListener('change', updateDetails);
    });
});
