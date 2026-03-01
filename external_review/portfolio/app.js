/* ============================================================
   Options Scanner — Portfolio Standalone
   Sub-tab switching, expandable rows, filters, theme toggle
   ============================================================ */

(function () {
    'use strict';

    // ============================================================
    // THEME TOGGLE
    // ============================================================
    const themeToggle = document.getElementById('theme-toggle');

    function setTheme(isDark) {
        if (isDark) {
            document.body.classList.add('dark');
            if (themeToggle) themeToggle.textContent = '☀️';
        } else {
            document.body.classList.remove('dark');
            if (themeToggle) themeToggle.textContent = '🌙';
        }
        localStorage.setItem('theme', isDark ? 'dark' : 'light');
    }

    // Load saved theme
    const savedTheme = localStorage.getItem('theme');
    if (savedTheme === 'dark') {
        setTheme(true);
    }

    if (themeToggle) {
        themeToggle.addEventListener('click', () => {
            const isDark = document.body.classList.contains('dark');
            setTheme(!isDark);
        });
    }

    // ============================================================
    // SUB-TAB SWITCHING
    // ============================================================
    const subTabs = document.querySelectorAll('.sub-tab');
    const subPanels = document.querySelectorAll('.sub-panel');
    const mobileDropdown = document.getElementById('mobileSubDropdown');

    function switchSubView(subId) {
        // Update desktop sub-tabs
        subTabs.forEach(t => t.classList.remove('active'));
        const activeTab = document.querySelector(`.sub-tab[data-sub="${subId}"]`);
        if (activeTab) activeTab.classList.add('active');

        // Update panels
        subPanels.forEach(p => p.classList.remove('active'));
        const targetPanel = document.getElementById(`sub-${subId}`);
        if (targetPanel) targetPanel.classList.add('active');

        // Sync mobile dropdown
        if (mobileDropdown) {
            mobileDropdown.value = subId;
        }
    }

    // Desktop sub-tab click handlers
    subTabs.forEach(tab => {
        tab.addEventListener('click', () => {
            switchSubView(tab.dataset.sub);
        });
    });

    // Mobile dropdown handler
    if (mobileDropdown) {
        mobileDropdown.addEventListener('change', () => {
            switchSubView(mobileDropdown.value);
        });
    }

    // ============================================================
    // EXPANDABLE TABLE ROWS
    // ============================================================
    document.querySelectorAll('.port-clickable-row').forEach(row => {
        row.addEventListener('click', (e) => {
            // Don't toggle if clicking a button
            if (e.target.closest('button')) return;

            const expandId = row.dataset.expand;
            const expandedRow = document.getElementById(expandId);
            if (!expandedRow) return;

            const isVisible = expandedRow.style.display !== 'none';

            if (isVisible) {
                expandedRow.style.display = 'none';
                row.classList.remove('expanded');
            } else {
                expandedRow.style.display = '';
                row.classList.add('expanded');
            }
        });
    });

    // ============================================================
    // FILTER PILL TOGGLES
    // ============================================================
    // Trade History filters
    document.querySelectorAll('.port-filter-row .port-pill-filter').forEach(pill => {
        pill.addEventListener('click', () => {
            pill.parentElement.querySelectorAll('.port-pill-filter').forEach(p => p.classList.remove('active'));
            pill.classList.add('active');
        });
    });

    // Performance period filters
    document.querySelectorAll('.port-period-filters .port-pill-filter').forEach(pill => {
        pill.addEventListener('click', () => {
            pill.parentElement.querySelectorAll('.port-pill-filter').forEach(p => p.classList.remove('active'));
            pill.classList.add('active');
        });
    });

    // ============================================================
    // SETTINGS: MODE TOGGLE INTERACTION
    // ============================================================
    document.querySelectorAll('.port-mode-toggle').forEach(toggle => {
        const buttons = toggle.querySelectorAll('.port-mode-opt');
        buttons.forEach(btn => {
            btn.addEventListener('click', () => {
                buttons.forEach(b => {
                    b.classList.remove('active-green', 'inactive');
                    b.classList.add('inactive');
                });
                btn.classList.remove('inactive');
                btn.classList.add('active-green');
            });
        });
    });

})();
