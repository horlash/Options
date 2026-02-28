/**
 * Portfolio Component
 * Feature: automated-trading
 *
 * Manages the Portfolio Hub — matches approved Mockups 1-3 exactly.
 * - Open Positions: Stat cards, SL/TP column, Status badge, 3-col expanded details, risk slider
 * - Trade History: Summary bar, Entry→Exit, inline expansion (Execution/Efficiency/Timestamps)
 * - Performance: KPI cards, charts, breakdown by Strategy/Type/Ticker
 */

const portfolio = (() => {
    // State
    const state = {
        currentView: 'open',
        historyFilter: 'ALL',
        historyTickerFilter: 'ALL',
        historySortKey: null,       // null | 'ticker' | 'type' | 'pnl' | 'held' | 'date'
        historySortDir: 'asc',     // 'asc' | 'desc'
        historyDateFrom: '',        // e.g. '2026-01-01' — empty means no lower bound
        historyDateTo: '',          // e.g. '2026-02-20' — empty means no upper bound
        performancePeriod: '30D',
        autoRefresh: true,
        lastUpdated: null,
        expandedRowId: null,
        expandedHistoryId: null,
        customFrom: '2026-01-01',
        customTo: '2026-02-20',
        refreshInterval: null,
        // ── Settings that propagate across all views ──
        maxPositions: 5,          // loaded from saved settings on init
        dailyLossLimit: 500,      // loaded from saved settings on init
        accountBalance: 5000,
        defaultSlPct: 20,
        defaultTpPct: 50,
        maxDailyTrades: 10,
        theme: 'dark',
        alertOnBracketHit: true,
        autoCloseExpiry: true,
        requireTradeConfirm: true,
        brokerMode: 'TRADIER_SANDBOX',
    };

    // Phase 3: Mock data toggle — set to false when DB is connected
    const USE_MOCK = false;

    // ═══ OPEN POSITIONS (populated from API) ═══
    let openPositions = [];

    // ═══ TRADE HISTORY (populated from API) ═══
    let tradeHistory = [];

    // Helper: compute human-readable hold duration
    function _calcHeld(openDate, closeDate) {
        try {
            const ms = Math.abs(new Date(closeDate) - new Date(openDate));
            const hours = ms / (1000 * 60 * 60);
            if (hours < 24) {
                const h = Math.max(0, Math.round(hours));
                return `${h} ${h === 1 ? 'Hour' : 'Hours'}`;
            }
            const d = parseFloat((hours / 24).toFixed(1));
            return `${d} ${d === 1 ? 'Day' : 'Days'}`;
        } catch { return '—'; }
    }

    // Helper: determine trading session from timestamp
    function _getSession(isoDate) {
        if (!isoDate) return '—';
        try {
            const d = new Date(isoDate);
            const day = d.getUTCDay();
            if (day === 0 || day === 6) return 'Weekend';
            const hour = d.getUTCHours();
            // ET approximation: UTC-5 regular hours = 14:30-21:00 UTC
            if (hour < 13) return 'Pre-Market';
            if (hour >= 21) return 'After-Hours';
            return 'Regular';
        } catch { return '—'; }
    }

    // ═══ INIT ═══
    function init() {
        bindEvents();
        updateTime();
        // Load saved settings first, then fetch live data
        loadSettings().then(() => {
            render();
            refreshData();  // Fetch live positions + stats on startup
        });
        // Phase 6: Fetch mode for banner on startup
        _fetchAndUpdateBanner();

        setInterval(() => {
            if (state.autoRefresh) refreshData();
        }, 15000);
    }

    // Loads all settings from the backend into state
    async function loadSettings() {
        if (USE_MOCK || typeof paperApi === 'undefined') return;
        try {
            const res = await paperApi.getSettings();
            if (res && res.settings) {
                const s = res.settings;
                if (s.max_positions) state.maxPositions = s.max_positions;
                if (s.daily_loss_limit) state.dailyLossLimit = s.daily_loss_limit;
                if (s.account_balance) state.accountBalance = s.account_balance;
                if (s.default_sl_pct != null) state.defaultSlPct = s.default_sl_pct;
                if (s.default_tp_pct != null) state.defaultTpPct = s.default_tp_pct;
                if (s.max_daily_trades != null) state.maxDailyTrades = s.max_daily_trades;
                if (s.theme) state.theme = s.theme;
                if (s.alert_on_bracket_hit != null) state.alertOnBracketHit = s.alert_on_bracket_hit;
                if (s.auto_close_expiry != null) state.autoCloseExpiry = s.auto_close_expiry;
                if (s.require_trade_confirm != null) state.requireTradeConfirm = s.require_trade_confirm;
                if (s.broker_mode) state.brokerMode = s.broker_mode;

                // Apply theme immediately on load
                _applyTheme(state.theme);

                // Pre-fill settings inputs if the settings view is already rendered
                _prefillSettingsInputs();
            }
        } catch (e) {
            console.warn('[portfolio] loadSettings failed (non-fatal):', e);
        }
    }

    // Fills the settings form inputs with current state values (safe to call anytime)
    function _prefillSettingsInputs() {
        const maxEl = document.getElementById('settings-max-pos');
        const lossEl = document.getElementById('settings-daily-loss');
        const balEl = document.getElementById('settings-account-balance');
        const slEl = document.getElementById('settings-default-sl');
        const tpEl = document.getElementById('settings-default-tp');
        const dailyTradesEl = document.getElementById('settings-max-daily-trades');
        if (maxEl) maxEl.value = state.maxPositions;
        if (lossEl) lossEl.value = state.dailyLossLimit;
        if (balEl) balEl.value = state.accountBalance;
        if (slEl) slEl.value = state.defaultSlPct;
        if (tpEl) tpEl.value = state.defaultTpPct;
        if (dailyTradesEl) dailyTradesEl.value = state.maxDailyTrades;

        // Toggles
        const autoCloseEl = document.getElementById('settings-auto-close-expiry');
        const confirmEl = document.getElementById('settings-require-confirm');
        const alertEl = document.getElementById('settings-alert-bracket');
        if (autoCloseEl) autoCloseEl.checked = state.autoCloseExpiry;
        if (confirmEl) confirmEl.checked = state.requireTradeConfirm;
        if (alertEl) alertEl.checked = state.alertOnBracketHit;

        // Theme radio
        const darkEl = document.getElementById('theme-dark');
        const lightEl = document.getElementById('theme-light');
        if (darkEl) darkEl.checked = state.theme === 'dark';
        if (lightEl) lightEl.checked = state.theme === 'light';

        // Account balance: disable in live mode
        if (balEl) balEl.disabled = state.brokerMode === 'TRADIER_LIVE';
    }

    function _applyTheme(theme) {
        document.documentElement.setAttribute('data-theme', theme || 'dark');
    }

    // Updates header badges dynamically from current state + positions
    function updateHeaderStats() {
        // Open trades count
        const tradesEl = document.getElementById('open-trades-count');
        if (tradesEl) tradesEl.textContent = openPositions.length;

        // Heat = invested capital / portfolio value * 100 (matches Risk Dashboard)
        const stats = state.stats || {};
        const portfolioValue = stats.portfolio_value || 0;
        const cashAvailable = stats.cash_available || 0;
        const invested = portfolioValue - cashAvailable;
        const heatPct = portfolioValue > 0
            ? +((invested / portfolioValue) * 100).toFixed(1)
            : 0;
        const heatLimit = 6.0;
        const heatEl = document.getElementById('portfolio-heat');
        if (heatEl) {
            heatEl.textContent = `${heatPct}%`;
            heatEl.style.color = heatPct <= 3 ? 'var(--secondary)'
                : heatPct <= 5 ? 'var(--accent)'
                    : 'var(--danger)';
        }
    }

    function bindEvents() {
        // Tab Switching
        document.querySelectorAll('.p-tab').forEach(btn => {
            btn.addEventListener('click', (e) => {
                switchView(e.target.dataset.view);
            });
        });

        // History Filters (use delegation for ALL filter pills in history view)
        const historyView = document.getElementById('portfolio-view-history');
        if (historyView) {
            historyView.addEventListener('click', (e) => {
                if (e.target.classList.contains('filter-pill') && e.target.dataset.filter) {
                    setHistoryFilter(e.target.dataset.filter);
                }
            });
        }

        // Auto-Refresh Toggle
        const refreshToggle = document.getElementById('portfolio-auto-refresh');
        if (refreshToggle) {
            refreshToggle.addEventListener('change', (e) => {
                state.autoRefresh = e.target.checked;
            });
        }

        // Manual Refresh
        const refreshBtn = document.getElementById('btn-refresh-portfolio');
        if (refreshBtn) {
            refreshBtn.addEventListener('click', () => refreshData(true));
        }

        // Performance Period Filters (Delegated)
        document.body.addEventListener('click', (e) => {
            if (e.target.classList.contains('perf-period-btn')) {
                state.performancePeriod = e.target.dataset.period;
                renderPerformanceView();
            }
        });
    }

    // ═══ LOGIC ═══
    function switchView(viewName) {
        state.currentView = viewName;

        document.querySelectorAll('.p-tab').forEach(btn => {
            btn.classList.toggle('active', btn.dataset.view === viewName);
        });

        document.getElementById('portfolio-view-open').classList.add('hidden');
        document.getElementById('portfolio-view-history').classList.add('hidden');
        document.getElementById('portfolio-view-performance').classList.add('hidden');
        document.getElementById('portfolio-view-settings').classList.add('hidden');

        const target = document.getElementById(`portfolio-view-${viewName}`);
        if (target) target.classList.remove('hidden');

        render();
    }

    function setHistoryFilter(filter) {
        state.historyFilter = filter;
        // Update pill active state
        const historyView = document.getElementById('portfolio-view-history');
        if (historyView) {
            historyView.querySelectorAll('.filter-pill[data-filter]').forEach(btn => {
                btn.classList.toggle('active', btn.dataset.filter === filter);
            });
        }
        renderHistoryTable();
    }

    function refreshData(manual = false) {
        if (USE_MOCK) {
            // Mock mode: simulate random price changes
            setTimeout(() => {
                openPositions.forEach(p => {
                    p.current += (Math.random() - 0.5) * 0.4;
                    p.current = Math.max(0.01, p.current);
                });
                updateTime();
                render();
            }, 300);
            return;
        }

        // Live mode: fetch from API
        Promise.all([
            paperApi.getTrades('OPEN'),
            paperApi.getStats(),
            paperApi.getTrades('CLOSED'),
        ]).then(([tradesRes, statsRes, closedRes]) => {
            if (tradesRes.success && tradesRes.trades) {
                openPositions = tradesRes.trades.map(t => {
                    const ctx = t.trade_context || {};
                    const entry = t.entry_price;
                    const current = t.current_price || entry;
                    return {
                        id: t.id,
                        ticker: t.ticker,
                        type: t.option_type,
                        strike: t.strike,
                        entry: entry,
                        current: current,
                        qty: t.qty,
                        sl: t.sl_price,
                        tp: t.tp_price,
                        expiry: t.expiry,
                        entryDate: t.created_at ? t.created_at.slice(0, 10) : '',
                        version: t.version,
                        status: t.status,
                        contract: `${t.ticker} ${t.strike}${t.option_type.charAt(0)} ${t.expiry}`,
                        aiScore: t.ai_score || 0,
                        algoScore: Math.round(t.card_score || 0),
                        delta: t.delta_at_entry || (ctx.greeks && ctx.greeks.delta) || 0,
                        iv: t.iv_at_entry || (ctx.greeks && ctx.greeks.iv) || 0,
                        strategy: t.strategy,
                        // Fields for inline expansion
                        breakeven: t.option_type === 'CALL' ? t.strike + entry : t.strike - entry,
                        held: t.created_at ? _calcHeld(t.created_at, new Date().toISOString()) : '—',
                        theta: (ctx.greeks && ctx.greeks.theta) || ctx.theta || 0,
                        volume: ctx.volume || 0,
                        oi: ctx.open_interest || 0,
                        oiRatio: ctx.oi_ratio || '—',
                    };
                });
            }
            // Populate trade history from CLOSED trades
            if (closedRes && closedRes.success && closedRes.trades) {
                tradeHistory = closedRes.trades.map(t => {
                    const ctx = t.trade_context || {};
                    const pnl = t.realized_pnl || 0;
                    const pnlPct = t.entry_price > 0 ? (((t.exit_price - t.entry_price) / t.entry_price) * 100) : 0;
                    const mfe = ctx.mfe || 0;
                    const mae = ctx.mae || 0;
                    // Efficiency: how much of the max favorable move was captured
                    const efficiency = mfe > 0 ? ((pnl / (mfe * t.qty * 100)) * 100).toFixed(0) + '%' : '—';
                    return {
                        id: t.id,
                        ticker: t.ticker,
                        type: t.option_type,
                        entryPrice: t.entry_price,
                        exitPrice: t.exit_price || t.entry_price,
                        pnl: pnl,
                        pnlPct: pnlPct,
                        result: pnl > 0 ? 'WIN' : pnl < 0 ? 'LOSS' : 'BREAKEVEN',
                        held: t.created_at && t.closed_at ? _calcHeld(t.created_at, t.closed_at) : '—',
                        reason: t.close_reason || 'Manual',
                        reasonKey: t.close_reason || 'MANUAL',
                        date: t.closed_at ? new Date(t.closed_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) : '—',
                        rawDate: t.closed_at || null,
                        strategy: t.strategy || '—',
                        tradeType: t.strategy || '—',
                        // Expansion fields
                        maxFavorable: mfe,
                        maxAdverse: mae,
                        efficiency: efficiency,
                        efficiencyNote: mfe > 0 ? `Captured ${efficiency} of $${(mfe * t.qty * 100).toFixed(0)} max move` : 'No favorable move recorded',
                        opened: t.created_at ? new Date(t.created_at).toLocaleString('en-US', { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit', timeZone: 'America/New_York' }) : '—',
                        closed: t.closed_at ? new Date(t.closed_at).toLocaleString('en-US', { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit', timeZone: 'America/New_York' }) : '—',
                        session: _getSession(t.created_at),
                    };
                });
            }
            // Store live stats from API for stat cards + risk dashboard
            if (statsRes && statsRes.success && statsRes.stats) {
                state.stats = statsRes.stats;
            }
            updateTime();
            render();
        }).catch(err => {
            console.error('[portfolio] refreshData failed:', err);
            if (manual) {
                if (typeof showToast === 'function') {
                    showToast('Failed to refresh — check connection', 'error');
                }
            }
        });
    }

    // Immediately show a trade as PENDING in the positions table (called right after submit)
    function addPendingPosition(pos) {
        const pendingId = `pending-${Date.now()}`;
        openPositions.unshift({
            id: pendingId,
            ticker: pos.ticker,
            type: pos.type,
            strike: pos.strike,
            entry: pos.entry,
            current: pos.entry,
            qty: pos.qty || 1,
            sl: pos.sl,
            tp: pos.tp,
            status: 'PENDING',
            entryDate: new Date().toISOString().slice(0, 10),
            contract: `${pos.ticker} ${pos.strike}${String(pos.type).charAt(0)} (Pending)`,
        });
        render();
    }

    // Soft refresh — re-fetches data from server without resetting state
    function refresh() {
        refreshData(false);
    }

    function startAutoRefresh() {
        stopAutoRefresh();
        if (state.autoRefresh && !USE_MOCK) {
            state.refreshInterval = setInterval(() => refreshData(false), 15000);
        }
    }

    function stopAutoRefresh() {
        if (state.refreshInterval) {
            clearInterval(state.refreshInterval);
            state.refreshInterval = null;
        }
    }

    function updateTime() {
        const now = new Date();
        const timeStr = now.toLocaleTimeString('en-US', {
            hour: 'numeric', minute: '2-digit', hour12: true
        });
        state.lastUpdated = timeStr;
        const el = document.getElementById('portfolio-last-updated');
        if (el) el.textContent = `${timeStr} ET`;
    }

    // ═══ RENDERERS ═══
    function render() {
        if (state.currentView === 'open') {
            renderStats();
            renderOpenPositionsTable();
        } else if (state.currentView === 'history') {
            renderHistorySummary();
            renderHistoryTable();
        } else if (state.currentView === 'performance') {
            renderPerformanceView();
        } else if (state.currentView === 'settings') {
            renderSettingsView();
        }
    }

    // ─── STAT CARDS (live from API) ───
    function renderStats() {
        const s = state.stats || {};
        const totalVal = s.portfolio_value || 0;
        const dailyPnL = s.todays_pnl || 0;
        const cash = s.cash_available || 0;
        const totalPnL = s.total_pnl || 0;
        // ── Use state values (updated by saveSettings / loadSettings) ──
        const maxPos = s.max_positions || state.maxPositions;
        const dailyLimit = state.dailyLossLimit;
        const cashPct = totalVal > 0 ? ((cash / totalVal) * 100).toFixed(0) : '0';
        const allTimePct = totalVal > 0 ? ((totalPnL / totalVal) * 100).toFixed(1) : '0.0';
        const posCount = s.open_positions != null ? s.open_positions : openPositions.filter(p => p.status !== 'PENDING').length;
        const limitColor = posCount >= maxPos ? 'var(--danger)' : posCount >= maxPos * 0.8 ? 'var(--accent)' : 'var(--text-muted)';

        const container = document.querySelector('#portfolio-view-open .portfolio-stats-row');
        if (!container) return;

        container.innerHTML = `
            <div class="stat-card">
                <h4>Portfolio Value</h4>
                <div class="value">$${totalVal.toLocaleString(undefined, { maximumFractionDigits: 0 })}</div>
                <div class="text-xs text-muted" style="margin-top:0.3rem;">+${allTimePct}% All Time</div>
            </div>
            <div class="stat-card">
                <h4>Today's P&L</h4>
                <div class="value" style="color: ${dailyPnL >= 0 ? 'var(--secondary)' : 'var(--danger)'}">
                    ${dailyPnL >= 0 ? '+' : ''}$${dailyPnL}
                </div>
                <div class="text-xs text-muted" style="margin-top:0.3rem;">vs $${dailyLimit.toLocaleString()} limit</div>
            </div>
            <div class="stat-card">
                <h4>Open Positions</h4>
                <div class="value">${posCount}</div>
                <div class="text-xs text-muted" style="margin-top:0.3rem; color:${limitColor};">of ${maxPos} max</div>
            </div>
            <div class="stat-card">
                <h4>Cash Available</h4>
                <div class="value">$${cash.toLocaleString()}</div>
                <div class="text-xs text-muted" style="margin-top:0.3rem;">${cashPct}% cash</div>
            </div>
        `;

        // Keep header badges in sync
        updateHeaderStats();
    }

    // ─── MOCKUP #1: OPEN POSITIONS TABLE ───
    // Columns: TICKER | TYPE | STRIKE | ENTRY | CURRENT | P&L | SL / TP | STATUS | Actions
    // Expanded: 3-col (Contract & Analysis | Greeks & Activity | Risk Management) + Risk Slider
    function renderOpenPositionsTable() {
        const tbody = document.getElementById('portfolio-body');
        const emptyState = document.getElementById('portfolio-empty-state');
        const table = document.getElementById('portfolio-table');

        if (openPositions.length === 0) {
            table.style.display = 'none';
            emptyState.classList.remove('hidden');
            return;
        }

        table.style.display = 'table';
        emptyState.classList.add('hidden');

        tbody.innerHTML = openPositions.map(pos => {
            const pnl = (pos.current - pos.entry) * pos.qty * 100;
            const pnlPct = ((pos.current - pos.entry) / pos.entry * 100);
            const isProfit = pnl >= 0;

            // Status logic (🟢 Win, 🔴 Loss, 🟡 Dip, ⏳ Pending, ⚖️ Breakeven)
            let statusLabel, statusClass;
            if (pos.status === 'PENDING') {
                statusLabel = '⏳ Pending'; statusClass = 'pending';
            } else if (pnlPct === 0) { statusLabel = '⚖️ Breakeven'; statusClass = 'breakeven'; }
            else if (pnlPct >= 10) { statusLabel = '🟢 Win'; statusClass = 'win'; }
            else if (pnlPct <= -5) { statusLabel = '🔴 Loss'; statusClass = 'loss'; }
            else if (pnlPct < 0) { statusLabel = '🟡 Dip'; statusClass = 'dip'; }
            else { statusLabel = '🟢 Win'; statusClass = 'win'; }

            const isPending = pos.status === 'PENDING';

            const isExpanded = state.expandedRowId === pos.id;

            // TYPE color: CALL=Green(Grn), PUT=Red
            const typeColor = pos.type === 'CALL' ? 'var(--secondary)' : 'var(--danger)';

            let html = `
                <tr class="pos-row ${isExpanded ? 'expanded' : ''}" onclick="portfolio.toggleRow(${pos.id})">
                    <td class="font-bold">${pos.ticker}</td>
                    <td style="color:${typeColor}">${pos.type}</td>
                    <td>$${pos.strike}</td>
                    <td>$${pos.entry.toFixed(2)}</td>
                    <td class="font-bold">$${pos.current.toFixed(2)}</td>
                    <td class="${isProfit ? 'pnl-positive' : 'pnl-negative'}">
                        ${isProfit ? '+' : ''}$${pnl.toFixed(2)} (${isProfit ? '+' : ''}${pnlPct.toFixed(1)}%)
                        ${isProfit ? '🟢' : '🔴'}
                    </td>
                    <td>${pos.sl != null ? `$${pos.sl.toFixed(2)}` : '—'} / ${pos.tp != null ? `$${pos.tp.toFixed(2)}` : '—'}</td>
                    <td><span class="status-badge ${statusClass}">${statusLabel}</span></td>
                    <td>
                        ${isPending
                    ? `<span style="color:var(--text-muted);font-size:0.8rem;">Awaiting fill…</span>`
                    : `<button class="btn-sm btn-secondary" onclick="event.stopPropagation(); portfolio.adjStop(${pos.id})">Adjust SL</button>
                               <button class="btn-sm btn-secondary" onclick="event.stopPropagation(); portfolio.adjTP(${pos.id})">Adjust TP</button>
                               <button class="btn-sm btn-danger" onclick="event.stopPropagation(); portfolio.closePos(${pos.id}, '${pos.ticker}')">Close</button>`
                }
                    </td>
                </tr>
            `;

            // ─── EXPANDED DETAILS (Mockup #1: 3-column + Risk Slider) ───
            if (isExpanded) {
                // Calculate percentages for risk slider
                const slPct = ((pos.sl - pos.entry) / pos.entry * 100).toFixed(0);
                const tpPct = ((pos.tp - pos.entry) / pos.entry * 100).toFixed(0);
                const currPct = ((pos.current - pos.entry) / pos.entry * 100).toFixed(0);

                // Risk slider marker positions (0-100%)
                // SL is leftmost, TP is rightmost
                const range = pos.tp - pos.sl;
                const slPos = 0;
                const tpPos = 100;
                const currPos = Math.max(0, Math.min(100, ((pos.current - pos.sl) / range) * 100));
                const entryPos = Math.max(0, Math.min(100, ((pos.entry - pos.sl) / range) * 100));

                html += `
                    <tr class="details-row">
                        <td colspan="9">
                            <div class="details-panel">
                                <div class="detail-col">
                                    <label>📝 Contract & Analysis</label>
                                    <div class="detail-val">${pos.contract}</div>
                                    <div class="detail-val">AI Score: ${pos.aiScore}/100 ${pos.aiScore >= 70 ? '🟢' : '🔴'}</div>
                                    <div class="detail-val">Algo Score: ${pos.algoScore}/100 ${pos.algoScore >= 70 ? '🟢' : '🔴'}</div>
                                    <div class="detail-val">BreakEven: > $${pos.breakeven.toFixed(2)}</div>
                                    <div class="detail-val">Held: ${pos.held}</div>
                                </div>
                                <div class="detail-col">
                                    <label>📊 Greeks & Activity</label>
                                    <div class="detail-val">Delta: ${(typeof pos.delta === 'number' ? pos.delta.toFixed(2) : pos.delta)} ($${Math.abs(pos.delta * 100).toFixed(0)}/$)</div>
                                    <div class="detail-val">Theta: ${(typeof pos.theta === 'number' ? pos.theta.toFixed(2) : pos.theta)}</div>
                                    <div class="detail-val">IV: ${(typeof pos.iv === 'number' ? pos.iv.toFixed(1) : pos.iv)}%</div>
                                    <div class="detail-val">Vol: ${pos.volume.toLocaleString()}</div>
                                    <div class="detail-val">OI: ${pos.oi.toLocaleString()} (${pos.oiRatio})</div>
                                </div>
                                <div class="detail-col">
                                    <label>⚖️ Risk Management</label>
                                    <div class="detail-val">Entry: $${pos.entry.toFixed(2)}</div>
                                    <div class="detail-val">Curr: $${pos.current.toFixed(2)} ${isProfit ? '🟢' : '🔴'} (${currPct}%)</div>
                                    <div class="detail-val">SL: ${pos.sl != null ? `$${pos.sl.toFixed(2)} (${slPct}%)` : '—'}</div>
                                    <div class="detail-val">TP: ${pos.tp != null ? `$${pos.tp.toFixed(2)} (+${tpPct}%)` : '—'}</div>

                                    <div class="risk-slider">
                                        <div class="marker" style="left:${slPos}%" title="SL"></div>
                                        <div class="marker current" style="left:${currPos}%" title="Current"></div>
                                        <div class="marker" style="left:${entryPos}%" title="Entry"></div>
                                        <div class="marker" style="left:${tpPos}%" title="TP"></div>
                                    </div>
                                    <div class="risk-slider-labels">
                                        <span>🛑 SL ${pos.sl != null ? `$${pos.sl.toFixed(2)}` : '—'}</span>
                                        <span>Current $${pos.current.toFixed(2)}</span>
                                        <span>🎯 TP ${pos.tp != null ? `$${pos.tp.toFixed(2)}` : '—'}</span>
                                    </div>
                                </div>
                            </div>
                        </td>
                    </tr>
                `;
            }
            return html;
        }).join('');
    }

    // ─── MOCKUP #2: HISTORY SUMMARY BAR ───
    function renderHistorySummary() {
        const el = document.getElementById('history-summary');
        if (!el) return;

        const totalClosed = tradeHistory.length;
        const wins = tradeHistory.filter(t => t.result === 'WIN').length;
        const winRate = totalClosed > 0 ? ((wins / totalClosed) * 100).toFixed(0) : 0;
        const realizedPnL = tradeHistory.reduce((acc, t) => acc + t.pnl, 0);
        const pnlColor = realizedPnL >= 0 ? 'var(--secondary)' : 'var(--danger)';

        el.innerHTML = `
            <div class="history-summary-boxes">
                <div class="history-summary-box">
                    <div class="summ-label">Total Closed</div>
                    <div class="summ-val">${totalClosed}</div>
                </div>
                <div class="history-summary-box">
                    <div class="summ-label">Win Rate</div>
                    <div class="summ-val">${winRate}%</div>
                </div>
                <div class="history-summary-box">
                    <div class="summ-label">Realized P&L</div>
                    <div class="summ-val" style="color:${pnlColor}">${realizedPnL >= 0 ? '+' : ''}$${realizedPnL.toLocaleString()}</div>
                </div>
            </div>
        `;

        // ── Populate ticker filter dropdown (UI-83) ──
        const tickerSelect = document.getElementById('history-ticker-filter');
        if (tickerSelect) {
            const uniqueTickers = [...new Set(tradeHistory.map(t => t.ticker))].sort();
            const current = state.historyTickerFilter || 'ALL';
            tickerSelect.innerHTML = '<option value="ALL">All Tickers</option>' +
                uniqueTickers.map(t => `<option value="${t}" ${t === current ? 'selected' : ''}>${t}</option>`).join('');
        }
    }

    // ─── MOCKUP #2: HISTORY TABLE ───
    // Columns: TICKER | TYPE | ENTRY → EXIT | P&L | HELD | REASON | DATE
    // Expanded: 3-col (Execution Details | Exit Efficiency | Timestamps)
    function renderHistoryTable() {
        const tbody = document.getElementById('history-body');
        if (!tbody) return;

        let filtered = tradeHistory;

        // ── Outcome filter ──
        if (state.historyFilter === 'WIN') {
            filtered = filtered.filter(t => t.result === 'WIN');
        } else if (state.historyFilter === 'LOSS') {
            filtered = filtered.filter(t => t.result === 'LOSS');
        } else if (state.historyFilter === 'EXPIRED') {
            filtered = filtered.filter(t => t.reasonKey === 'EXPIRED');
        } else if (state.historyFilter === 'SL_HIT') {
            filtered = filtered.filter(t => t.reasonKey === 'SL_HIT');
        } else if (state.historyFilter === 'TP_HIT') {
            filtered = filtered.filter(t => t.reasonKey === 'TP_HIT');
        }

        // ── Ticker filter (UI-83) ──
        if (state.historyTickerFilter && state.historyTickerFilter !== 'ALL') {
            filtered = filtered.filter(t => t.ticker === state.historyTickerFilter);
        }

        // ── Date range filter ──
        const fromMs = state.historyDateFrom ? new Date(state.historyDateFrom).getTime() : null;
        const toMs = state.historyDateTo ? new Date(state.historyDateTo + 'T23:59:59').getTime() : null;
        if (fromMs || toMs) {
            filtered = filtered.filter(t => {
                const tradeMs = t.rawDate
                    ? new Date(t.rawDate).getTime()
                    : new Date(t.date).getTime();
                if (isNaN(tradeMs)) return true;
                if (fromMs && tradeMs < fromMs) return false;
                if (toMs && tradeMs > toMs) return false;
                return true;
            });
        }

        // ── Sort (UI-84) ──
        if (state.historySortKey) {
            const dir = state.historySortDir === 'asc' ? 1 : -1;
            filtered.sort((a, b) => {
                let va, vb;
                switch (state.historySortKey) {
                    case 'ticker': va = a.ticker; vb = b.ticker; return va.localeCompare(vb) * dir;
                    case 'type': va = a.type; vb = b.type; return va.localeCompare(vb) * dir;
                    case 'pnl': return (a.pnl - b.pnl) * dir;
                    case 'held': return (parseFloat(a.held) - parseFloat(b.held)) * dir;
                    case 'date':
                        va = a.rawDate ? new Date(a.rawDate).getTime() : 0;
                        vb = b.rawDate ? new Date(b.rawDate).getTime() : 0;
                        return (va - vb) * dir;
                    default: return 0;
                }
            });
        }

        // ── Update sort arrows ──
        ['ticker', 'type', 'pnl', 'held', 'date'].forEach(key => {
            const arrow = document.getElementById(`sort-arrow-${key}`);
            if (arrow) {
                arrow.textContent = state.historySortKey === key
                    ? (state.historySortDir === 'asc' ? '▲' : '▼')
                    : '';
            }
        });

        tbody.innerHTML = filtered.map(t => {
            const isWin = t.result === 'WIN';
            const isBreakeven = t.result === 'BREAKEVEN';
            const isExpanded = state.expandedHistoryId === t.id;
            const pnlClass = isWin ? 'pnl-positive' : isBreakeven ? '' : 'pnl-negative';
            const pnlEmoji = isWin ? '🟢' : isBreakeven ? '⚖️' : '🔴';

            let html = `
                <tr class="pos-row ${isExpanded ? 'expanded' : ''}" onclick="portfolio.toggleHistoryRow(${t.id})">
                    <td class="font-bold">${t.ticker}</td>
                    <td style="color:${t.type === 'CALL' ? 'var(--secondary)' : 'var(--danger)'}">${t.type}</td>
                    <td>$${t.entryPrice.toFixed(2)} → $${t.exitPrice.toFixed(2)}</td>
                    <td class="${pnlClass}">
                        ${isWin ? '+' : ''}$${typeof t.pnl === 'number' ? t.pnl.toFixed(2) : t.pnl} ${pnlEmoji}
                    </td>
                    <td>${t.held}</td>
                    <td>${t.reason}</td>
                    <td>${t.date}</td>
                </tr>
            `;

            // ─── EXPANDED HISTORY (Mockup #2: 3-column) ───
            if (isExpanded) {
                html += `
                    <tr class="details-row">
                        <td colspan="7">
                            <div class="details-panel">
                                <div class="detail-col">
                                    <label>⚙️ Execution Details</label>
                                    <div class="detail-val">Type: ${t.type}</div>
                                    <div class="detail-val">Strategy: ${t.strategy}</div>
                                </div>
                                <div class="detail-col">
                                    <label>📉 Exit Efficiency</label>
                                    <div class="detail-val">Max Favorable: ${t.maxFavorable >= 0 ? '+' : ''}$${t.maxFavorable}</div>
                                    <div class="detail-val">Max Adverse: -$${Math.abs(t.maxAdverse)}</div>
                                    <div class="detail-val">Efficiency: ${t.efficiency}</div>
                                    <div class="detail-val text-xs text-muted">(${t.efficiencyNote})</div>
                                </div>
                                <div class="detail-col">
                                    <label>⏱️ Timestamps</label>
                                    <div class="detail-val">Opened: ${t.opened}</div>
                                    <div class="detail-val">Closed: ${t.closed}</div>
                                    <div class="detail-val">Session: ${t.session}</div>
                                </div>
                            </div>
                        </td>
                    </tr>
                `;
            }
            return html;
        }).join('');
    }

    // ─── MOCKUP #3: PERFORMANCE VIEW (Phase 5: Live API + Chart.js) ───
    async function renderPerformanceView() {
        const container = document.getElementById('portfolio-view-performance');
        if (!container) return;

        // Show loading state
        container.innerHTML = `
            <div style="text-align:center; padding:3rem;">
                <div style="font-size:2rem; margin-bottom:0.5rem;">⏳</div>
                <div class="text-muted">Loading analytics...</div>
            </div>
        `;

        try {
            // Fetch all analytics in parallel
            const [summaryRes, equityRes, drawdownRes, tickerRes, strategyRes, monthlyRes] =
                await Promise.all([
                    paperApi.getAnalyticsSummary(),
                    paperApi.getEquityCurve(),
                    paperApi.getDrawdown(),
                    paperApi.getByTicker(),
                    paperApi.getByStrategy(),
                    paperApi.getMonthlyPnl(),
                ]);

            const kpis = summaryRes.summary || {};
            const equityData = equityRes.data || [];
            const drawdown = drawdownRes.drawdown || {};
            const tickers = tickerRes.data || [];
            const strategies = strategyRes.data || [];
            const monthlyData = monthlyRes.data || [];

            const periods = ['30D', 'YTD', 'ALL', 'CUSTOM'];
            const periodLabels = { '30D': 'Last 30 Days', 'YTD': 'YTD', 'ALL': 'All Time', 'CUSTOM': 'Custom' };
            const periodBtns = periods.map(p =>
                `<button class="filter-pill perf-period-btn ${state.performancePeriod === p ? 'active' : ''}" data-period="${p}">${periodLabels[p]}</button>`
            ).join('');

            const totalPnl = kpis.total_pnl || 0;
            const pnlSign = totalPnl >= 0 ? '+' : '';
            const pnlColor = totalPnl >= 0 ? 'var(--secondary)' : 'var(--danger)';
            const pnlIcon = totalPnl >= 0 ? '🟢' : '🔴';

            const ddVal = drawdown.max_drawdown || 0;
            const ddStr = ddVal === 0 ? '$0' : `-$${Math.abs(ddVal).toLocaleString()}`;

            const expectancy = kpis.expectancy || 0;
            const expSign = expectancy >= 0 ? '+' : '';

            container.innerHTML = `
                <!-- Date Range -->
                <div class="history-filters" style="margin-bottom: ${state.performancePeriod === 'CUSTOM' ? '0.5rem' : '1.5rem'};">
                    <span class="text-muted" style="align-self:center; margin-right:0.5rem;">Date Range:</span>
                    ${periodBtns}
                    <div style="margin-left:auto;"><div class="export-dropdown" style="position:relative;">
                        <button class="filter-pill" onclick="portfolio.toggleExportMenu('perf-export-menu')">📥 Export ▼</button>
                        <div id="perf-export-menu" class="export-menu hidden" style="right:0;left:auto;">
                            <a href="${paperApi.getExportCsvUrl()}" download style="display:block;padding:0.5rem 1rem;color:var(--text-primary);text-decoration:none;font-size:0.85rem;">📄 Export CSV</a>
                            <a href="${paperApi.getExportJsonUrl()}" download style="display:block;padding:0.5rem 1rem;color:var(--text-primary);text-decoration:none;font-size:0.85rem;">🗂️ Export JSON</a>
                        </div>
                    </div></div>
                </div>
                ${state.performancePeriod === 'CUSTOM' ? `
                <div class="custom-date-range">
                    <div class="date-input-group">
                        <label>From</label>
                        <input type="date" id="perf-date-from" value="${state.customFrom || '2026-01-01'}">
                    </div>
                    <div class="date-input-group">
                        <label>To</label>
                        <input type="date" id="perf-date-to" value="${state.customTo || '2026-02-20'}">
                    </div>
                    <button class="modal-btn modal-btn-confirm" style="padding:0.45rem 1rem; font-size:0.8rem; align-self:flex-end;" onclick="portfolio.applyCustomRange()">Apply</button>
                </div>
                ` : ''}

                <!-- KPI Cards (5 columns) -->
                <div class="portfolio-stats-row">
                    <div class="stat-card">
                        <h4>Total P&L</h4>
                        <div class="value" style="color:${pnlColor}">${pnlSign}$${Math.abs(totalPnl).toLocaleString()} ${pnlIcon}</div>
                        <div class="text-xs text-muted">${kpis.total_trades || 0} trades</div>
                    </div>
                    <div class="stat-card">
                        <h4>Win Rate</h4>
                        <div class="value">${kpis.win_rate || 0}%</div>
                        <div class="text-xs text-muted">${kpis.wins || 0}W / ${kpis.losses || 0}L</div>
                    </div>
                    <div class="stat-card">
                        <h4>Profit Factor</h4>
                        <div class="value">${kpis.profit_factor || 0}</div>
                        <div class="text-xs text-muted">Avg: +$${kpis.avg_win || 0} / $${kpis.avg_loss || 0}</div>
                    </div>
                    <div class="stat-card">
                        <h4>Expectancy</h4>
                        <div class="value">${expSign}$${Math.abs(expectancy).toFixed(2)}</div>
                        <div class="text-xs text-muted">Per trade avg</div>
                    </div>
                    <div class="stat-card">
                        <h4>Max Drawdown</h4>
                        <div class="value" style="color:var(--danger)">${ddStr} 🔴</div>
                        <div class="text-xs text-muted">${drawdown.drawdown_date || 'N/A'}</div>
                    </div>
                </div>

                <!-- Win/Loss Pie Chart (UI-92) -->
                <div class="perf-grid" style="grid-template-columns:1fr 1fr 1fr;">
                    <div class="chart-box">
                        <div class="chart-header">Win / Loss Distribution</div>
                        <div style="padding:0.5rem; display:flex; justify-content:center;">
                            ${(kpis.wins + kpis.losses) > 0
                    ? '<canvas id="winloss-chart" width="260" height="260"></canvas>'
                    : '<div class="chart-placeholder"><div style="text-align:center;"><div style="font-size:2rem;">🥧</div><div class="text-muted">No closed trades yet</div></div></div>'
                }
                        </div>
                    </div>
                    <div class="chart-box">
                        <div class="chart-header">Equity Curve</div>
                        <div style="padding:0.5rem;">
                            ${equityData.length > 0
                    ? '<canvas id="equity-chart" height="200"></canvas>'
                    : '<div class="chart-placeholder"><div style="text-align:center;"><div style="font-size:2rem;">📈</div><div class="text-muted">No closed trades yet</div></div></div>'
                }
                        </div>
                    </div>
                    <div class="chart-box">
                        <div class="chart-header">Monthly P&L</div>
                        <div style="padding:0.5rem;">
                            ${monthlyData.length > 0
                    ? '<canvas id="monthly-chart" height="200"></canvas>'
                    : '<div class="chart-placeholder"><div style="text-align:center;"><div style="font-size:2rem;">📊</div><div class="text-muted">No monthly data yet</div></div></div>'
                }
                        </div>
                    </div>
                </div>

                <!-- Breakdown: Trade Type + Strategy -->
                <div class="perf-grid">
                    <div class="chart-box" style="min-height:auto;">
                        <div class="chart-header">By Strategy</div>
                        ${strategies.length > 0 ? `
                        <table class="breakdown-table">
                            <thead><tr><th>Strategy</th><th>Trades</th><th>Win %</th><th>P&L</th><th>PF</th></tr></thead>
                            ${strategies.map(s => `
                                <tr>
                                    <td>${s.strategy}</td>
                                    <td>${s.trades}</td>
                                    <td>${s.win_rate}%</td>
                                    <td style="color:${(s.total_pnl || 0) >= 0 ? 'var(--secondary)' : 'var(--danger)'}">${(s.total_pnl || 0) >= 0 ? '+' : ''}$${s.total_pnl}</td>
                                    <td>${s.profit_factor || '—'}</td>
                                </tr>
                            `).join('')}
                        </table>` : '<div class="text-muted" style="padding:1rem; text-align:center;">No strategy data</div>'}
                    </div>
                    <div class="chart-box" style="min-height:auto;">
                        <div class="chart-header">By Ticker</div>
                        ${tickers.length > 0 ? `
                        <table class="breakdown-table">
                            <thead><tr><th>Ticker</th><th>Trades</th><th>Win %</th><th>P&L</th><th>Avg</th></tr></thead>
                            ${tickers.map(t => `
                                <tr>
                                    <td class="font-bold">${t.ticker}</td>
                                    <td>${t.trades}</td>
                                    <td>${t.win_rate}%</td>
                                    <td style="color:${(t.total_pnl || 0) >= 0 ? 'var(--secondary)' : 'var(--danger)'}">${(t.total_pnl || 0) >= 0 ? '+' : ''}$${t.total_pnl}</td>
                                    <td class="text-muted">${(t.avg_pnl || 0) >= 0 ? '+' : ''}$${t.avg_pnl}</td>
                                </tr>
                            `).join('')}
                        </table>` : '<div class="text-muted" style="padding:1rem; text-align:center;">No ticker data</div>'}
                    </div>
                </div>
            `;

            // --- Render Chart.js Charts ---
            if (equityData.length > 0) {
                _renderEquityChart(equityData);
            }
            if (monthlyData.length > 0) {
                _renderMonthlyChart(monthlyData);
            }
            if ((kpis.wins + kpis.losses) > 0) {
                _renderWinLossChart(kpis.wins, kpis.losses);
            }

        } catch (err) {
            console.error('[Performance] Failed to load analytics:', err);
            container.innerHTML = `
                <div style="text-align:center; padding:3rem;">
                    <div style="font-size:2rem; margin-bottom:0.5rem;">⚠️</div>
                    <div>Failed to load analytics</div>
                    <div class="text-xs text-muted">${err.message}</div>
                </div>
            `;
        }
    }

    // ─── Chart.js Helpers (Phase 5) ───
    let _equityChartInstance = null;
    let _monthlyChartInstance = null;

    function _renderEquityChart(data) {
        const canvas = document.getElementById('equity-chart');
        if (!canvas || typeof Chart === 'undefined') return;

        if (_equityChartInstance) _equityChartInstance.destroy();

        const labels = data.map(d => d.trade_date);
        const values = data.map(d => d.cumulative_pnl);

        _equityChartInstance = new Chart(canvas, {
            type: 'line',
            data: {
                labels,
                datasets: [{
                    label: 'Cumulative P&L',
                    data: values,
                    borderColor: 'rgba(0, 255, 136, 0.9)',
                    backgroundColor: 'rgba(0, 255, 136, 0.1)',
                    fill: true,
                    tension: 0.3,
                    pointRadius: 3,
                    pointBackgroundColor: 'rgba(0, 255, 136, 1)',
                }],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        callbacks: {
                            label: (ctx) => `$${ctx.parsed.y.toLocaleString()}`,
                        },
                    },
                },
                scales: {
                    x: { ticks: { color: '#888', maxTicksLimit: 8 }, grid: { color: 'rgba(255,255,255,0.05)' } },
                    y: {
                        ticks: {
                            color: '#888',
                            callback: (v) => `$${v}`,
                        },
                        grid: { color: 'rgba(255,255,255,0.05)' },
                    },
                },
            },
        });
    }

    function _renderMonthlyChart(data) {
        const canvas = document.getElementById('monthly-chart');
        if (!canvas || typeof Chart === 'undefined') return;

        if (_monthlyChartInstance) _monthlyChartInstance.destroy();

        const labels = data.map(d => `${d.month} ${d.year}`);
        const values = data.map(d => d.monthly_pnl);
        const colors = values.map(v => v >= 0 ? 'rgba(0, 255, 136, 0.8)' : 'rgba(255, 77, 77, 0.8)');

        _monthlyChartInstance = new Chart(canvas, {
            type: 'bar',
            data: {
                labels,
                datasets: [{
                    label: 'Monthly P&L',
                    data: values,
                    backgroundColor: colors,
                    borderColor: colors.map(c => c.replace('0.8)', '1)')),
                    borderWidth: 1,
                }],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        callbacks: {
                            label: (ctx) => `$${ctx.parsed.y.toLocaleString()}`,
                        },
                    },
                },
                scales: {
                    x: { ticks: { color: '#888' }, grid: { display: false } },
                    y: {
                        ticks: {
                            color: '#888',
                            callback: (v) => `$${v}`,
                        },
                        grid: { color: 'rgba(255,255,255,0.05)' },
                    },
                },
            },
        });
    }

    // ─── Win/Loss Doughnut Chart (UI-92) ───
    let _winLossChartInstance = null;

    function _renderWinLossChart(wins, losses) {
        const canvas = document.getElementById('winloss-chart');
        if (!canvas || typeof Chart === 'undefined') return;

        if (_winLossChartInstance) _winLossChartInstance.destroy();

        _winLossChartInstance = new Chart(canvas, {
            type: 'doughnut',
            data: {
                labels: ['Wins', 'Losses'],
                datasets: [{
                    data: [wins, losses],
                    backgroundColor: ['rgba(0, 255, 136, 0.8)', 'rgba(255, 77, 77, 0.8)'],
                    borderColor: ['rgba(0, 255, 136, 1)', 'rgba(255, 77, 77, 1)'],
                    borderWidth: 2,
                    hoverOffset: 6,
                }],
            },
            options: {
                responsive: true,
                maintainAspectRatio: true,
                cutout: '55%',
                plugins: {
                    legend: {
                        position: 'bottom',
                        labels: {
                            color: '#ccc',
                            padding: 12,
                            usePointStyle: true,
                        },
                    },
                    tooltip: {
                        callbacks: {
                            label: (ctx) => {
                                const total = ctx.dataset.data.reduce((a, b) => a + b, 0);
                                const pct = total > 0 ? ((ctx.parsed / total) * 100).toFixed(1) : 0;
                                return `${ctx.label}: ${ctx.parsed} (${pct}%)`;
                            },
                        },
                    },
                },
            },
        });
    }

    // ═══ PHASE 6: SETTINGS VIEW ═══
    function renderSettingsView() {
        const container = document.getElementById('portfolio-view-settings');
        if (!container) return;

        const isLive = state.brokerMode === 'TRADIER_LIVE';
        const inputStyle = `width: 100%; padding: 0.5rem; border-radius: 6px; border: 1px solid rgba(255,255,255,0.15); background: var(--bg-card); color: var(--text-primary); font-size: 0.85rem;`;
        const labelStyle = `font-size: 0.8rem; color: var(--text-muted); display: block; margin-bottom: 0.25rem;`;
        const sectionStyle = `margin-bottom: 1.5rem; background: var(--bg-card); border: 1px solid var(--border); border-radius: 12px; padding: 1.25rem;`;

        container.innerHTML = `
        <div style="padding: 1rem;">
            <!-- 1. Trading Mode -->
            <div style="${sectionStyle}">
                <h3 style="color: var(--text-primary); margin-bottom: 0.75rem;">🎛️ Trading Mode</h3>
                <div style="display: flex; gap: 1rem;">
                    <div class="mode-card ${!isLive ? 'selected' : ''}" id="mode-sandbox-card" style="flex:1; padding: 1rem; border: 2px solid ${!isLive ? 'var(--primary)' : 'rgba(255,255,255,0.1)'}; border-radius: 8px; background: ${!isLive ? 'rgba(0,180,255,0.05)' : 'transparent'}; cursor: pointer;">
                        <div style="font-size: 1.2rem; margin-bottom: 0.25rem;">🧪 Sandbox</div>
                        <div style="font-size: 0.75rem; color: var(--text-muted);">Fake money (Tradier sandbox)</div>
                    </div>
                    <div class="mode-card ${isLive ? 'selected' : ''}" id="mode-live-card" onclick="portfolio.confirmLiveMode()" style="flex:1; padding: 1rem; border: 2px solid ${isLive ? 'var(--danger)' : 'rgba(255,255,255,0.1)'}; border-radius: 8px; background: ${isLive ? 'rgba(255,50,50,0.08)' : 'rgba(255,50,50,0.03)'}; cursor: pointer;">
                        <div style="font-size: 1.2rem; margin-bottom: 0.25rem;">🔴 Live Trading</div>
                        <div style="font-size: 0.75rem; color: var(--text-muted);">Real money — requires API key</div>
                    </div>
                </div>
            </div>

            <!-- 2. Broker Credentials -->
            <div style="${sectionStyle}">
                <h3 style="color: var(--text-primary); margin-bottom: 0.75rem;">🔑 Broker Credentials</h3>
                <div style="display: grid; gap: 0.75rem;">
                    <div>
                        <label style="${labelStyle}">Tradier API Token</label>
                        <input type="password" id="settings-api-token" placeholder="Enter API token" style="${inputStyle}">
                    </div>
                    <div>
                        <label style="${labelStyle}">Account ID</label>
                        <input type="text" id="settings-account-id" placeholder="Enter Account ID" style="${inputStyle}">
                    </div>
                    <button onclick="portfolio.testBrokerConnection()" class="btn-primary" style="width: fit-content; padding: 0.4rem 1rem; font-size: 0.85rem;">🔌 Test Connection</button>
                    <div id="connection-status" style="font-size: 0.8rem; color: var(--text-muted);"></div>
                </div>
            </div>

            <!-- 3. Portfolio -->
            <div style="${sectionStyle}">
                <h3 style="color: var(--text-primary); margin-bottom: 0.75rem;">💰 Portfolio</h3>
                <div>
                    <label style="${labelStyle}">Account Balance ($) ${isLive ? '<span style="color:var(--accent);">(Live: pulled from broker)</span>' : ''}</label>
                    <input type="number" id="settings-account-balance" value="${state.accountBalance}" min="100" step="100" ${isLive ? 'disabled' : ''} style="${inputStyle} ${isLive ? 'opacity:0.5; cursor:not-allowed;' : ''}">
                    ${isLive ? '<div style="font-size:0.75rem; color:var(--accent); margin-top:0.25rem;">Balance is synced from your broker in live mode</div>' : '<div style="font-size:0.75rem; color:var(--text-muted); margin-top:0.25rem;">This is your starting capital for paper trading</div>'}
                </div>
            </div>

            <!-- 4. Risk Management -->
            <div style="${sectionStyle}">
                <h3 style="color: var(--text-primary); margin-bottom: 0.75rem;">🛡️ Risk Management</h3>
                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 0.75rem;">
                    <div>
                        <label style="${labelStyle}">Max Positions</label>
                        <input type="number" id="settings-max-pos" value="${state.maxPositions}" min="1" max="25" style="${inputStyle}">
                    </div>
                    <div>
                        <label style="${labelStyle}">Daily Loss Limit ($)</label>
                        <input type="number" id="settings-daily-loss" value="${state.dailyLossLimit}" min="50" style="${inputStyle}">
                    </div>
                    <div>
                        <label style="${labelStyle}">Default Stop Loss (%)</label>
                        <input type="number" id="settings-default-sl" value="${state.defaultSlPct}" min="1" max="100" step="1" style="${inputStyle}">
                    </div>
                    <div>
                        <label style="${labelStyle}">Default Take Profit (%)</label>
                        <input type="number" id="settings-default-tp" value="${state.defaultTpPct}" min="1" max="500" step="1" style="${inputStyle}">
                    </div>
                    <div>
                        <label style="${labelStyle}">Max Daily Trades</label>
                        <input type="number" id="settings-max-daily-trades" value="${state.maxDailyTrades}" min="1" max="100" style="${inputStyle}">
                    </div>
                </div>
            </div>

            <!-- 5. Trade Behavior -->
            <div style="${sectionStyle}">
                <h3 style="color: var(--text-primary); margin-bottom: 0.75rem;">📅 Trade Behavior</h3>
                <div style="display: grid; gap: 1rem;">
                    <label style="display:flex; align-items:center; gap:0.75rem; cursor:pointer;">
                        <input type="checkbox" id="settings-auto-close-expiry" ${state.autoCloseExpiry ? 'checked' : ''} class="settings-toggle">
                        <div>
                            <div style="font-size:0.9rem; color:var(--text-primary);">Auto-Close on Expiry</div>
                            <div style="font-size:0.75rem; color:var(--text-muted);">Close positions at last market price on expiry day (ITM options keep value)</div>
                        </div>
                    </label>
                    <label style="display:flex; align-items:center; gap:0.75rem; cursor:pointer;">
                        <input type="checkbox" id="settings-require-confirm" ${state.requireTradeConfirm ? 'checked' : ''} class="settings-toggle">
                        <div>
                            <div style="font-size:0.9rem; color:var(--text-primary);">Require Trade Confirmation <span style="font-size:0.7rem; padding:0.15rem 0.5rem; background:rgba(239,68,68,0.15); color:var(--danger); border-radius:8px;">Live Only</span></div>
                            <div style="font-size:0.75rem; color:var(--text-muted);">Show "Are you sure?" modal before placing real-money trades</div>
                        </div>
                    </label>
                </div>
            </div>

            <!-- 6. Preferences -->
            <div style="${sectionStyle}">
                <h3 style="color: var(--text-primary); margin-bottom: 0.75rem;">⚙️ Preferences</h3>
                <div style="display: grid; gap: 1rem;">
                    <div>
                        <label style="${labelStyle}">Theme</label>
                        <div style="display:flex; gap:0.75rem;">
                            <label style="display:flex; align-items:center; gap:0.4rem; cursor:pointer; font-size:0.9rem; color:var(--text-primary);">
                                <input type="radio" name="theme" id="theme-dark" value="dark" ${state.theme === 'dark' ? 'checked' : ''} onchange="portfolio._previewTheme('dark')">
                                🌙 Dark
                            </label>
                            <label style="display:flex; align-items:center; gap:0.4rem; cursor:pointer; font-size:0.9rem; color:var(--text-primary);">
                                <input type="radio" name="theme" id="theme-light" value="light" ${state.theme === 'light' ? 'checked' : ''} onchange="portfolio._previewTheme('light')">
                                ☀️ Light
                            </label>
                        </div>
                    </div>
                    <label style="display:flex; align-items:center; gap:0.75rem; cursor:pointer;">
                        <input type="checkbox" id="settings-alert-bracket" ${state.alertOnBracketHit ? 'checked' : ''} class="settings-toggle">
                        <div>
                            <div style="font-size:0.9rem; color:var(--text-primary);">🔔 Alert on SL/TP Hit</div>
                            <div style="font-size:0.75rem; color:var(--text-muted);">Browser notification when a bracket order triggers</div>
                        </div>
                    </label>
                </div>
            </div>

            <!-- Save button -->
            <button onclick="portfolio.saveSettings()" class="btn-primary" style="padding: 0.6rem 2rem; font-size: 0.95rem; border-radius: 8px;">💾 Save Settings</button>
        </div>
        `;
    }

    function _previewTheme(theme) {
        _applyTheme(theme);
    }

    async function saveSettings() {
        const token = document.getElementById('settings-api-token')?.value?.trim();
        const accountId = document.getElementById('settings-account-id')?.value?.trim();
        const maxPos = parseFloat(document.getElementById('settings-max-pos')?.value) || 5;
        const dailyLoss = parseFloat(document.getElementById('settings-daily-loss')?.value) || 500;
        const accountBalance = parseFloat(document.getElementById('settings-account-balance')?.value) || 5000;
        const defaultSl = parseFloat(document.getElementById('settings-default-sl')?.value) || 20;
        const defaultTp = parseFloat(document.getElementById('settings-default-tp')?.value) || 50;
        const maxDailyTrades = parseInt(document.getElementById('settings-max-daily-trades')?.value) || 10;
        const autoCloseExpiry = document.getElementById('settings-auto-close-expiry')?.checked ?? true;
        const requireConfirm = document.getElementById('settings-require-confirm')?.checked ?? true;
        const alertBracket = document.getElementById('settings-alert-bracket')?.checked ?? true;
        const theme = document.querySelector('input[name="theme"]:checked')?.value || 'dark';

        try {
            if (typeof paperApi !== 'undefined') {
                const payload = {
                    max_positions: maxPos,
                    daily_loss_limit: dailyLoss,
                    account_balance: accountBalance,
                    default_sl_pct: defaultSl,
                    default_tp_pct: defaultTp,
                    max_daily_trades: maxDailyTrades,
                    auto_close_expiry: autoCloseExpiry,
                    require_trade_confirm: requireConfirm,
                    alert_on_bracket_hit: alertBracket,
                    theme: theme,
                };
                if (token) payload.tradier_sandbox_token = token;
                if (accountId) payload.tradier_account_id = accountId;

                await paperApi.updateSettings(payload);
            }

            // ── Propagate to all views immediately ──
            state.maxPositions = maxPos;
            state.dailyLossLimit = dailyLoss;
            state.accountBalance = accountBalance;
            state.defaultSlPct = defaultSl;
            state.defaultTpPct = defaultTp;
            state.maxDailyTrades = maxDailyTrades;
            state.autoCloseExpiry = autoCloseExpiry;
            state.requireTradeConfirm = requireConfirm;
            state.alertOnBracketHit = alertBracket;
            state.theme = theme;

            // Apply theme
            _applyTheme(theme);

            // Request notification permission if alerts enabled
            if (alertBracket && 'Notification' in window && Notification.permission === 'default') {
                Notification.requestPermission();
            }

            // Re-render whichever view is currently active, plus always update header
            updateHeaderStats();
            if (state.currentView === 'open') {
                renderStats();
            }

            if (typeof showToast === 'function') showToast('Settings saved ✅', 'success');
        } catch (err) {
            console.error('Save settings failed:', err);
            if (typeof showToast === 'function') showToast('Failed to save settings ❌', 'error');
        }
    }

    async function testBrokerConnection() {
        const statusEl = document.getElementById('connection-status');
        if (statusEl) statusEl.innerHTML = '⏳ Testing connection...';

        try {
            if (typeof paperApi !== 'undefined') {
                const result = await paperApi.testConnection();
                if (statusEl) {
                    statusEl.innerHTML = result.success
                        ? '<span style="color: var(--secondary);">✅ Connected successfully</span>'
                        : `<span style="color: var(--danger);">❌ Connection failed: ${result.error || 'Unknown error'}</span>`;
                }
            } else {
                if (statusEl) statusEl.innerHTML = '<span style="color: var(--warning);">⚠️ Paper API not loaded</span>';
            }
        } catch (err) {
            console.error('Connection test failed:', err);
            if (statusEl) statusEl.innerHTML = `<span style="color: var(--danger);">❌ ${err.message}</span>`;
        }
    }

    function confirmLiveMode() {
        // When called from checkbox change, toggle the confirm button
        const checkbox = document.getElementById('modal-confirm-checkbox');
        if (checkbox) {
            const confirmBtn = document.getElementById('modal-confirm-btn');
            if (confirmBtn) confirmBtn.disabled = !checkbox.checked;
            return;
        }

        // When called from mode card click, show confirmation modal
        showModal({
            title: '⚠️ Switch to Live Trading',
            context: 'You are about to switch to LIVE trading mode. Real orders will be placed with real money through your broker.',
            warning: '<strong>This uses real money.</strong> Ensure your API credentials are correct and risk limits are set.',
            checkboxLabel: 'I understand the risks and want to enable live trading',
            confirmLabel: 'Enable Live Trading',
            confirmClass: 'modal-btn modal-btn-danger',
            onConfirm: () => {
                // Switch to live mode
                const sandboxCard = document.getElementById('mode-sandbox-card');
                const liveCard = document.getElementById('mode-live-card');
                if (sandboxCard) { sandboxCard.style.borderColor = 'rgba(255,255,255,0.1)'; sandboxCard.classList.remove('selected'); }
                if (liveCard) { liveCard.style.borderColor = 'var(--danger)'; liveCard.classList.add('selected'); }
                _fetchAndUpdateBanner();
                if (typeof toast !== 'undefined') toast.success('Switched to Live Trading mode');
            },
            onCancel: () => {
                // Revert — keep sandbox selected
            }
        });
    }

    // ═══ PUBLIC ACTIONS ═══
    function toggleRow(id) {
        state.expandedRowId = state.expandedRowId === id ? null : id;
        renderOpenPositionsTable();
    }

    function toggleHistoryRow(id) {
        state.expandedHistoryId = state.expandedHistoryId === id ? null : id;
        renderHistoryTable();
    }

    function adjStop(id) {
        const pos = openPositions.find(p => p.id === id);
        if (!pos) return;
        const pnl = (pos.current - pos.entry) * pos.qty * 100;
        const pnlPct = ((pos.current - pos.entry) / pos.entry * 100).toFixed(1);

        // Badge-aware SL recommendation
        const badge = pos.tradeType || 'WEEKLY';
        let slPctLow, slPctHigh, badgeLabel;
        if (badge === 'LEAP') { slPctLow = 0.70; slPctHigh = 0.75; badgeLabel = 'LEAP: -25% to -30%'; }
        else if (badge === '0DTE') { slPctLow = 0.88; slPctHigh = 0.92; badgeLabel = '0DTE: -8% to -12%'; }
        else { slPctLow = 0.80; slPctHigh = 0.85; badgeLabel = 'WEEKLY: -15% to -20%'; }
        const recLow = (pos.entry * slPctLow).toFixed(2);
        const recHigh = (pos.entry * slPctHigh).toFixed(2);

        showModal({
            title: '🛑 Adjust Stop Loss',
            context: [
                { label: 'Ticker', value: pos.ticker },
                { label: 'Type', value: `${pos.type} $${pos.strike}` },
                { label: 'Badge', value: badge },
                { label: 'Entry', value: `$${pos.entry.toFixed(2)}` },
                { label: 'Current', value: `$${pos.current.toFixed(2)}` },
                { label: 'P&L', value: `${pnl >= 0 ? '+' : ''}$${pnl.toFixed(2)} (${pnlPct}%)`, color: pnl >= 0 ? 'var(--secondary)' : 'var(--danger)' },
                { label: 'Current SL', value: `$${pos.sl.toFixed(2)}` }
            ],
            inputLabel: 'New Stop Loss Price',
            inputValue: pos.sl.toFixed(2),
            inputHint: `${badgeLabel} → Recommended: $${recLow} – $${recHigh}`,
            confirmLabel: 'Update Stop Loss',
            confirmClass: 'modal-btn modal-btn-confirm',
            onConfirm: async (val) => {
                const newSL = parseFloat(val);
                if (isNaN(newSL) || newSL <= 0) return;
                try {
                    const res = await paperApi.adjustTrade(id, { new_sl: newSL });
                    if (res && res.success) {
                        pos.sl = newSL;
                        render();
                        showToast && showToast('SL updated', 'success');
                    } else {
                        showToast && showToast(res?.error || 'Failed to update SL', 'error');
                    }
                } catch (e) {
                    console.error('Adjust SL error:', e);
                    showToast && showToast('Failed to update SL', 'error');
                }
            }
        });
    }

    function adjTP(id) {
        const pos = openPositions.find(p => p.id === id);
        if (!pos) return;
        const pnl = (pos.current - pos.entry) * pos.qty * 100;
        const pnlPct = ((pos.current - pos.entry) / pos.entry * 100).toFixed(1);

        showModal({
            title: '🎯 Adjust Take Profit',
            context: [
                { label: 'Ticker', value: pos.ticker },
                { label: 'Type', value: `${pos.type} $${pos.strike}` },
                { label: 'Entry', value: `$${pos.entry.toFixed(2)}` },
                { label: 'Current', value: `$${pos.current.toFixed(2)}` },
                { label: 'P&L', value: `${pnl >= 0 ? '+' : ''}$${pnl.toFixed(2)} (${pnlPct}%)`, color: pnl >= 0 ? 'var(--secondary)' : 'var(--danger)' },
                { label: 'Current TP', value: `$${pos.tp.toFixed(2)}` }
            ],
            inputLabel: 'New Take Profit Price',
            inputValue: pos.tp.toFixed(2),
            inputHint: `Must be above current price: $${pos.current.toFixed(2)}`,
            confirmLabel: 'Update Take Profit',
            confirmClass: 'modal-btn modal-btn-confirm',
            onConfirm: async (val) => {
                const newTP = parseFloat(val);
                if (isNaN(newTP) || newTP <= 0) return;
                try {
                    const res = await paperApi.adjustTrade(id, { new_tp: newTP });
                    if (res && res.success) {
                        pos.tp = newTP;
                        render();
                        showToast && showToast('TP updated', 'success');
                    } else {
                        showToast && showToast(res?.error || 'Failed to update TP', 'error');
                    }
                } catch (e) {
                    console.error('Adjust TP error:', e);
                    showToast && showToast('Failed to update TP', 'error');
                }
            }
        });
    }

    function closePos(id, ticker) {
        const pos = openPositions.find(p => p.id === id);
        if (!pos) return;
        const pnl = (pos.current - pos.entry) * pos.qty * 100;
        const pnlPct = ((pos.current - pos.entry) / pos.entry * 100).toFixed(1);

        showModal({
            title: `⚠️ Close ${ticker}`,
            context: [
                { label: 'Ticker', value: pos.ticker },
                { label: 'Type', value: `${pos.type} $${pos.strike}` },
                { label: 'Entry', value: `$${pos.entry.toFixed(2)}` },
                { label: 'Market Price', value: `$${pos.current.toFixed(2)}` },
                { label: 'Realized P&L', value: `${pnl >= 0 ? '+' : ''}$${pnl.toFixed(2)} (${pnlPct}%)`, color: pnl >= 0 ? 'var(--secondary)' : 'var(--danger)' }
            ],
            warning: `This will send a <strong>market sell order</strong> for your ${pos.ticker} ${pos.type} $${pos.strike} position. This action cannot be undone.`,
            confirmLabel: 'Close Position',
            confirmClass: 'modal-btn modal-btn-danger',
            onConfirm: () => {
                if (USE_MOCK) {
                    openPositions = openPositions.filter(p => p.id !== id);
                    render();
                    return;
                }
                // Live: call API to close
                paperApi.closeTrade(id, pos.version).then(res => {
                    if (res.success) {
                        openPositions = openPositions.filter(p => p.id !== id);
                        render();
                        if (typeof showToast === 'function') {
                            showToast(`Closed ${ticker} — P&L: $${(res.trade.realized_pnl || 0).toFixed(2)}`, 'success');
                        }
                    }
                }).catch(err => {
                    console.error('Close failed:', err);
                    if (typeof showToast === 'function') showToast('Close failed', 'error');
                });
            }
        });
    }

    // ═══ MODAL SYSTEM ═══
    function showModal({ title, context, inputLabel, inputValue, inputHint, warning, confirmLabel, confirmClass, onConfirm, onCancel, checkboxLabel }) {
        const overlay = document.getElementById('action-modal');
        const titleEl = document.getElementById('modal-title');
        const bodyEl = document.getElementById('modal-body');
        const footerEl = document.getElementById('modal-footer');

        titleEl.textContent = title;

        // Build body
        let bodyHTML = '';

        // Context card (support array or string)
        if (context) {
            if (typeof context === 'string') {
                bodyHTML += `<div class="modal-context"><p style="margin:0;color:var(--text-secondary)">${context}</p></div>`;
            } else if (Array.isArray(context) && context.length > 0) {
                bodyHTML += '<div class="modal-context">';
                context.forEach(c => {
                    const colorStyle = c.color ? ` style="color:${c.color}"` : '';
                    bodyHTML += `
                    <div class="ctx-item">
                        <span class="ctx-label">${c.label}</span>
                        <span class="ctx-value"${colorStyle}>${c.value}</span>
                    </div>`;
                });
                bodyHTML += '</div>';
            }
        }

        // Warning box (for close action)
        if (warning) {
            bodyHTML += `
            <div class="modal-warning">
                <span class="warn-icon">⚠️</span>
                <div>${warning}</div>
            </div>`;
        }

        // Input field with custom stepper (for adjust SL/TP)
        if (inputLabel) {
            bodyHTML += `
            <div class="modal-input-group">
                <label>${inputLabel}</label>
                <div class="modal-stepper">
                    <button type="button" class="step-btn step-btn-down" onclick="portfolio.stepInput(-0.05)">−</button>
                    <input type="number" id="modal-input" step="0.01" min="0" value="${inputValue || ''}">
                    <button type="button" class="step-btn step-btn-up" onclick="portfolio.stepInput(0.05)">+</button>
                </div>
                ${inputHint ? `<div class="modal-input-hint">${inputHint}</div>` : ''}
            </div>`;
        }

        // Checkbox (Phase 6: live mode confirmation)
        if (checkboxLabel) {
            bodyHTML += `
            <div class="modal-checkbox-group">
                <label class="modal-checkbox-label">
                    <input type="checkbox" id="modal-confirm-checkbox" onchange="portfolio.confirmLiveMode()" />
                    <span>${checkboxLabel}</span>
                </label>
            </div>`;
        }

        bodyEl.innerHTML = bodyHTML;

        // Footer buttons
        const needsCheckbox = !!checkboxLabel;
        footerEl.innerHTML = `
        <button class="modal-btn modal-btn-cancel" onclick="portfolio.closeModal()">Cancel</button>
        <button class="modal-btn ${confirmClass}" id="modal-confirm-btn" ${needsCheckbox ? 'disabled' : ''}>${confirmLabel}</button>
    `;

        // Store onCancel callback
        overlay._onCancel = onCancel || null;

        // Wire up confirm
        document.getElementById('modal-confirm-btn').addEventListener('click', () => {
            const inputEl = document.getElementById('modal-input');
            const val = inputEl ? inputEl.value : null;
            onConfirm(val);
            _hideModal();
        });

        // Show
        overlay.classList.remove('hidden');

        // Focus input if present
        setTimeout(() => {
            const inputEl = document.getElementById('modal-input');
            if (inputEl) { inputEl.focus(); inputEl.select(); }
        }, 100);

        // Escape key
        document.addEventListener('keydown', _escHandler);
    }
    function _escHandler(e) {
        if (e.key === 'Escape') _hideModal();
    }

    function _hideModal() {
        const overlay = document.getElementById('action-modal');
        overlay.classList.add('hidden');
        document.removeEventListener('keydown', _escHandler);
    }

    function closeModal(e) {
        // Called directly (from Cancel/X button) — always close
        if (!e) {
            const overlay = document.getElementById('action-modal');
            if (overlay && overlay._onCancel) {
                overlay._onCancel();
                overlay._onCancel = null;
            }
            _hideModal();
            return;
        }
        // Called from overlay click — only close if clicking background (not card)
        if (e.target && !e.target.closest('.modal-card')) {
            const overlay = document.getElementById('action-modal');
            if (overlay._onCancel) {
                overlay._onCancel();
                overlay._onCancel = null;
            }
            _hideModal();
        }
    }
    function stepInput(delta) {
        const input = document.getElementById('modal-input');
        if (!input) return;
        const current = parseFloat(input.value) || 0;
        const newVal = Math.max(0, current + delta);
        input.value = newVal.toFixed(2);
        input.focus();
    }

    // ═══ EXPORT SYSTEM ═══
    function toggleExportMenu(menuId = 'export-menu') {
        const menu = document.getElementById(menuId);
        if (menu) menu.classList.toggle('hidden');

        // Close on click outside
        const handler = (e) => {
            if (!e.target.closest('.export-dropdown')) {
                if (menu) menu.classList.add('hidden');
                document.removeEventListener('click', handler);
            }
        };
        setTimeout(() => document.addEventListener('click', handler), 0);
    }

    function exportHistory(format) {
        // Hide menu
        const menu = document.getElementById('export-menu');
        if (menu) menu.classList.add('hidden');

        // Prepare data
        const data = tradeHistory.map(t => ({
            Ticker: t.ticker,
            Type: t.type,
            Strike: t.strike,
            EntryPrice: t.entryPrice,
            ExitPrice: t.exitPrice,
            PnL: t.pnl,
            Result: t.result,
            HoldTime: t.held,
            CloseReason: t.reason,
            Strategy: t.strategy || '',
            EntryDate: t.entryDate || '',
            ExitDate: t.exitDate || ''
        }));

        let blob, filename;

        if (format === 'json') {
            const json = JSON.stringify(data, null, 2);
            blob = new Blob([json], { type: 'application/json' });
            filename = `trade_history_${new Date().toISOString().slice(0, 10)}.json`;
        } else {
            // CSV
            const headers = Object.keys(data[0]);
            const csvRows = [
                headers.join(','),
                ...data.map(row => headers.map(h => {
                    let val = row[h];
                    // Escape commas and quotes in values
                    if (typeof val === 'string' && (val.includes(',') || val.includes('"'))) {
                        val = `"${val.replace(/"/g, '""')}"`;
                    }
                    return val;
                }).join(','))
            ];
            blob = new Blob([csvRows.join('\n')], { type: 'text/csv' });
            filename = `trade_history_${new Date().toISOString().slice(0, 10)}.csv`;
        }

        // Download
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    }

    // ─── Apply date range filter for the history tab ───
    function applyHistoryDateFilter() {
        const fromEl = document.getElementById('history-date-from');
        const toEl = document.getElementById('history-date-to');
        state.historyDateFrom = fromEl ? fromEl.value : '';
        state.historyDateTo = toEl ? toEl.value : '';
        renderHistoryTable();
    }

    // ─── Reset history date filters ───
    function resetHistoryDateFilter() {
        const fromEl = document.getElementById('history-date-from');
        const toEl = document.getElementById('history-date-to');
        if (fromEl) fromEl.value = '';
        if (toEl) toEl.value = '';
        state.historyDateFrom = '';
        state.historyDateTo = '';
        renderHistoryTable();
    }

    // ─── Apply custom date range for the performance tab ───
    function applyCustomRange() {
        const fromEl = document.getElementById('perf-date-from');
        const toEl = document.getElementById('perf-date-to');
        if (fromEl) state.customFrom = fromEl.value;
        if (toEl) state.customTo = toEl.value;
        renderPerformanceView();
    }

    // ── UI-83: Ticker filter for history ──
    function setHistoryTickerFilter(ticker) {
        state.historyTickerFilter = ticker;
        renderHistoryTable();
    }

    // ── UI-84: Sort history table ──
    function sortHistory(key) {
        if (state.historySortKey === key) {
            state.historySortDir = state.historySortDir === 'asc' ? 'desc' : 'asc';
        } else {
            state.historySortKey = key;
            state.historySortDir = 'asc';
        }
        renderHistoryTable();
    }

    return {
        init,
        toggleRow,
        toggleHistoryRow,
        adjStop,
        adjTP,
        closePos,
        closeModal,
        stepInput,
        applyCustomRange,
        toggleExportMenu,
        exportHistory,
        addPendingPosition,
        refresh,
        render,
        // Phase 6: Settings
        saveSettings,
        testBrokerConnection,
        confirmLiveMode,
        _previewTheme,
        getState: () => state,
        applyHistoryDateFilter,
        resetHistoryDateFilter,
        // UI fixes
        setHistoryTickerFilter,
        sortHistory,
    };

})();
