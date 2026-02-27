// ═══════════════════════════════════════════════════════
function showToast(message, type = 'info', duration = 3500) {
    // Ensure container exists
    let container = document.getElementById('toast-container');
    if (!container) {
        container = document.createElement('div');
        container.id = 'toast-container';
        container.style.cssText = `
            position: fixed;
            bottom: 1.5rem;
            right: 1.5rem;
            z-index: 9999;
            display: flex;
            flex-direction: column;
            gap: 0.5rem;
            pointer-events: none;
        `;
        document.body.appendChild(container);
    }

    const colors = {
        success: { bg: 'linear-gradient(135deg,#059669,#10b981)', icon: '✅', border: '#10b981' },
        error: { bg: 'linear-gradient(135deg,#b91c1c,#ef4444)', icon: '❌', border: '#ef4444' },
        warning: { bg: 'linear-gradient(135deg,#b45309,#f59e0b)', icon: '⚠️', border: '#f59e0b' },
        info: { bg: 'linear-gradient(135deg,#1d4ed8,#6366f1)', icon: 'ℹ️', border: '#6366f1' },
    };
    const c = colors[type] || colors.info;

    const toast = document.createElement('div');
    toast.style.cssText = `
        background: ${c.bg};
        border: 1px solid ${c.border};
        border-radius: 10px;
        padding: 0.75rem 1.25rem;
        color: #fff;
        font-size: 0.9rem;
        font-weight: 600;
        display: flex;
        align-items: center;
        gap: 0.6rem;
        box-shadow: 0 8px 24px rgba(0,0,0,0.4);
        pointer-events: auto;
        min-width: 220px;
        max-width: 340px;
        opacity: 0;
        transform: translateY(12px);
        transition: opacity 0.25s ease, transform 0.25s ease;
        cursor: pointer;
    `;
    toast.innerHTML = `<span style="font-size:1.1rem">${c.icon}</span><span>${message}</span>`;
    toast.addEventListener('click', () => _removeToast(toast));

    container.appendChild(toast);

    // Trigger entrance animation
    requestAnimationFrame(() => {
        requestAnimationFrame(() => {
            toast.style.opacity = '1';
            toast.style.transform = 'translateY(0)';
        });
    });

    // Auto-remove after duration
    setTimeout(() => _removeToast(toast), duration);

    function _removeToast(el) {
        el.style.opacity = '0';
        el.style.transform = 'translateY(8px)';
        setTimeout(() => { if (el.parentNode) el.parentNode.removeChild(el); }, 280);
    }
}

// Main application initialization
// Feature: automated-trading (tab switching + new component init)

// Tab Switching
function switchTab(tabId, btn) {
    document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
    document.querySelectorAll('.nav-tab').forEach(t => t.classList.remove('active'));
    const panel = document.getElementById('tab-' + tabId);
    if (panel) panel.classList.add('active');
    if (btn) btn.classList.add('active');

    // Toggle body class so CSS knows whether a sub-tab row is visible
    if (tabId === 'portfolio') {
        document.body.classList.add('has-subtabs');
    } else {
        document.body.classList.remove('has-subtabs');
    }

    // Lazy render when switching to a tab
    if (tabId === 'portfolio' && typeof portfolio !== 'undefined') {
        portfolio.render();
    }
    if (tabId === 'risk' && typeof riskDashboard !== 'undefined') {
        riskDashboard.render();
    }
}
document.addEventListener('DOMContentLoaded', async () => {
    console.log('Options Scanner initialized');

    // Fetch and display logged-in username next to logout button
    try {
        const meResp = await fetch('/api/me');
        if (meResp.ok) {
            const meData = await meResp.json();
            const userSpan = document.getElementById('logged-in-user');
            if (userSpan && meData.username) {
                userSpan.textContent = meData.username;
            }
        }
    } catch (e) {
        console.warn('Could not fetch current user:', e);
    }

    // Initialize tabs with dynamic dates
    if (typeof scanner !== 'undefined') {
        scanner.init();
    }

    // Initialize filter buttons
    if (typeof opportunities !== 'undefined') {
        opportunities.init();
    }

    // Set up event listeners immediately so buttons work
    try {
        setupEventListeners();
        console.log('Event listeners set up successfully');
    } catch (error) {
        console.error('Error setting up event listeners:', error);
    }

    // Check if API is available
    if (typeof api === 'undefined') {
        console.error('API client not loaded');
        if (typeof toast !== 'undefined') {
            toast.error('System error: API client not loaded');
        }
        return;
    }

    // Check API health
    try {
        const health = await api.healthCheck();
        console.log('API Status:', health);
        if (typeof toast !== 'undefined') {
            toast.success('Connected to backend');
        }
    } catch (error) {
        console.error('API connection failed:', error);
        if (typeof toast !== 'undefined') {
            toast.error('Failed to connect to backend. Make sure the server is running.');
        }
    }

    // Load initial data
    if (typeof watchlist !== 'undefined') {
        await watchlist.init();
    }

    // Load history
    renderHistory();

    // Initialize trading components
    if (typeof portfolio !== 'undefined') {
        portfolio.init();
    }
    if (typeof riskDashboard !== 'undefined') {
        riskDashboard.init();
    }

    // Trade modal overlay click to close
    const tradeOverlay = document.getElementById('trade-modal-overlay');
    if (tradeOverlay) {
        tradeOverlay.addEventListener('click', (e) => {
            if (e.target === tradeOverlay) {
                tradeModal.close();
            }
        });
    }
});

async function renderHistory() {
    const historyContainer = document.getElementById('search-history');
    if (!historyContainer) return;

    try {
        const resp = await api.getHistory();
        if (resp.success && resp.history && resp.history.length > 0) {
            historyContainer.innerHTML = resp.history.map(ticker =>
                `<div class="history-tag" onclick="handleHistoryClick('${ticker}')">${ticker}</div>`
            ).join('');
        } else {
            historyContainer.innerHTML = '<div class="empty-state-small">No recent searches</div>';
        }
    } catch (e) {
        console.error("Failed to load history", e);
        historyContainer.innerHTML = '<div class="empty-state-small">History unavailable</div>';
    }
}

async function updateHistory(ticker) {
    try {
        await api.addHistory(ticker);
        renderHistory();
    } catch (e) {
        console.error("Failed to update history", e);
    }
}

window.handleHistoryClick = (ticker) => {
    document.getElementById('quick-scan-input').value = ticker;
    scanner.scanTicker(ticker);
};

function setupEventListeners() {


    // Quick scan form
    const quickScanForm = document.getElementById('quick-scan-form');
    if (quickScanForm) {
        quickScanForm.addEventListener('submit', (e) => {
            e.preventDefault();
            const input = document.getElementById('quick-scan-input');
            const ticker = input.value.trim().toUpperCase();

            if (ticker) {
                // Validate before saving to history or scanning
                if (!scanner.isValidTicker(ticker)) {
                    toast.error(`Unknown ticker "${ticker}". Use the autocomplete to find valid symbols.`);
                    return;
                }
                updateHistory(ticker);
                scanner.scanTicker(ticker);
                input.value = '';
            } else {
                // BUG-6 FIX: Show error for empty search
                toast.error('Please enter a ticker symbol');
            }
        });
    }

    // Mode Toggle
    const modeLeaps = document.getElementById('mode-leaps');
    const modeWeekly0 = document.getElementById('mode-weekly-0');
    const modeWeekly1 = document.getElementById('mode-weekly-1');
    const modeWeekly2 = document.getElementById('mode-weekly-2');

    // Helper to switch active class
    const setActive = (activeBtn) => {
        // Include new 0DTE button in the list to clear
        const mode0dte = document.getElementById('mode-0dte');
        [modeLeaps, modeWeekly0, modeWeekly1, modeWeekly2, mode0dte].forEach(btn => {
            if (btn) btn.classList.remove('active');
        });
        if (activeBtn) activeBtn.classList.add('active');
    };

    if (modeLeaps) {
        modeLeaps.addEventListener('click', () => {
            scanner.setMode('leaps');
            setActive(modeLeaps);
        });
    }

    if (modeWeekly0) {
        modeWeekly0.addEventListener('click', () => {
            scanner.setMode('weekly-0');
            setActive(modeWeekly0);
        });
    }

    if (modeWeekly1) {
        modeWeekly1.addEventListener('click', () => {
            scanner.setMode('weekly-1');
            setActive(modeWeekly1);
        });
    }

    if (modeWeekly2) {
        modeWeekly2.addEventListener('click', () => {
            scanner.setMode('weekly-2');
            setActive(modeWeekly2);
        });
    }

    // NEW: 0DTE Mode
    const mode0dte = document.getElementById('mode-0dte');
    if (mode0dte) {
        mode0dte.addEventListener('click', () => {
            scanner.setMode('0dte');
            setActive(mode0dte);
        });
    }

    // Sort select
    const sortSelect = document.getElementById('sort-select');
    if (sortSelect) {
        sortSelect.addEventListener('change', (e) => {
            opportunities.sort(e.target.value);
        });
    }

    // Ticker filter
    const tickerFilter = document.getElementById('ticker-filter');
    if (tickerFilter) {
        tickerFilter.addEventListener('change', (e) => {
            opportunities.setFilter(e.target.value);
        });
    }

    // Modal close
    const closeModalBtn = document.getElementById('close-modal');
    if (closeModalBtn) {
        closeModalBtn.addEventListener('click', () => {
            analysisDetail.hide();
        });
    }

    // Close modal on overlay click (click on backdrop area outside modal-content)
    const modal = document.getElementById('analysis-modal');
    modal.addEventListener('click', (e) => {
        if (e.target === modal) {
            analysisDetail.hide();
        }
    });
}
