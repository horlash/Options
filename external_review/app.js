/* ============================================
   Options Scanner — Portfolio & Risk Wireframe
   Tab switching + expandable rows + mobile dropdown
   ============================================ */

(function() {
  'use strict';

  // ---- Theme Toggle (Dark / Light) ----
  const themeToggle = document.getElementById('themeToggle');
  const shell = document.querySelector('.scanner-shell');
  
  function setTheme(theme) {
    if (theme === 'dark') {
      shell.setAttribute('data-theme', 'dark');
      themeToggle.innerHTML = '<span class="theme-icon">☀️</span> Light';
    } else {
      shell.removeAttribute('data-theme');
      themeToggle.innerHTML = '<span class="theme-icon">🌙</span> Dark';
    }
  }

  themeToggle.addEventListener('click', () => {
    const isDark = shell.hasAttribute('data-theme');
    setTheme(isDark ? 'light' : 'dark');
  });

  // ---- View Tab Switching (1-5) ----
  const viewTabs = document.querySelectorAll('.view-tab');
  const viewPanels = document.querySelectorAll('.view-panel');
  const appTabs = document.querySelectorAll('.app-tab[data-app]');
  const subTabsContainer = document.getElementById('subTabs');
  const subTabs = document.querySelectorAll('.sub-tab');
  const modeBanner = document.querySelector('.mode-banner');
  const mobileViewDropdown = document.getElementById('mobileViewDropdown');

  function switchView(viewNum) {
    // Update view tabs (desktop)
    viewTabs.forEach(t => t.classList.remove('active'));
    const activeTab = document.querySelector(`.view-tab[data-view="${viewNum}"]`);
    if (activeTab) activeTab.classList.add('active');

    // Update view panels
    viewPanels.forEach(p => p.classList.remove('active'));
    document.getElementById(`view-${viewNum}`).classList.add('active');

    // Sync mobile dropdown
    if (mobileViewDropdown) {
      mobileViewDropdown.value = viewNum;
    }

    // Update app tabs based on view
    appTabs.forEach(t => t.classList.remove('active'));
    if (viewNum <= 4) {
      // Portfolio sub-views
      document.querySelector('.app-tab[data-app="portfolio"]').classList.add('active');
      subTabsContainer.style.display = 'flex';
      modeBanner.style.display = 'block';

      // Update sub-tabs
      const subMap = { 1: 'open-positions', 2: 'trade-history', 3: 'performance', 4: 'settings' };
      subTabs.forEach(s => s.classList.remove('active'));
      const targetSub = document.querySelector(`.sub-tab[data-sub="${subMap[viewNum]}"]`);
      if (targetSub) targetSub.classList.add('active');
    } else if (viewNum === 5) {
      // Risk Dashboard
      document.querySelector('.app-tab[data-app="risk"]').classList.add('active');
      subTabsContainer.style.display = 'none';
      modeBanner.style.display = 'block';
    }
  }

  // View tab click handlers (desktop)
  viewTabs.forEach(tab => {
    tab.addEventListener('click', () => {
      switchView(parseInt(tab.dataset.view));
    });
  });

  // Mobile dropdown handler
  if (mobileViewDropdown) {
    mobileViewDropdown.addEventListener('change', () => {
      switchView(parseInt(mobileViewDropdown.value));
    });
  }

  // App tab click handlers
  appTabs.forEach(tab => {
    tab.addEventListener('click', () => {
      if (tab.classList.contains('disabled')) return;
      const app = tab.dataset.app;
      if (app === 'portfolio') {
        switchView(1);
      } else if (app === 'risk') {
        switchView(5);
      }
    });
  });

  // Sub-tab click handlers
  subTabs.forEach(tab => {
    tab.addEventListener('click', () => {
      const subMap = { 'open-positions': 1, 'trade-history': 2, 'performance': 3, 'settings': 4 };
      const viewNum = subMap[tab.dataset.sub];
      if (viewNum) switchView(viewNum);
    });
  });

  // ---- Expandable Table Rows ----
  document.querySelectorAll('.clickable-row').forEach(row => {
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

  // ---- Filter Pill Toggle (Trade History) ----
  document.querySelectorAll('.filter-row .pill').forEach(pill => {
    pill.addEventListener('click', () => {
      // Deactivate siblings
      pill.parentElement.querySelectorAll('.pill').forEach(p => p.classList.remove('active'));
      pill.classList.add('active');
    });
  });

  // ---- Period Filter Toggle (Performance) ----
  document.querySelectorAll('.period-filters .pill').forEach(pill => {
    pill.addEventListener('click', () => {
      pill.parentElement.querySelectorAll('.pill').forEach(p => p.classList.remove('active'));
      pill.classList.add('active');
    });
  });

})();
