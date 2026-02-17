// Main application initialization
// Main application initialization
document.addEventListener('DOMContentLoaded', async () => {
    console.log('LEAP Options Scanner initialized');

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
    // Determine mode based on active button? Or just stick to current mode?
    // User: "Any Ticker I search should show up as history"
    // We'll perform a scan for this ticker in current mode
    // Also populate input box?
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
                updateHistory(ticker);
                scanner.scanTicker(ticker);
                input.value = '';
            }
        });
    }

    // Run scan button removed
    // runScanBtn.addEventListener('click', () => {
    //     scanner.run();
    // });

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
    sortSelect.addEventListener('change', (e) => {
        opportunities.sort(e.target.value);
    });

    // Ticker filter
    const tickerFilter = document.getElementById('ticker-filter');
    tickerFilter.addEventListener('change', (e) => {
        opportunities.setFilter(e.target.value);
    });

    // Modal close
    const closeModalBtn = document.getElementById('close-modal');
    closeModalBtn.addEventListener('click', () => {
        analysisDetail.hide();
    });

    // Close modal on overlay click
    const modal = document.getElementById('analysis-modal');
    modal.addEventListener('click', (e) => {
        if (e.target.classList.contains('modal-overlay')) {
            analysisDetail.hide();
        }
    });
}
