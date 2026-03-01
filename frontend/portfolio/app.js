/* ============================================================
   Options Scanner — Portfolio (API-Wired)
   Full backend integration with /api/paper endpoints
   ============================================================ */

(function () {
    'use strict';

    const API_BASE = '/api/paper';

    // ============================================================
    // HELPERS
    // ============================================================
    function $(sel, ctx) { return (ctx || document).querySelector(sel); }
    function $$(sel, ctx) { return Array.from((ctx || document).querySelectorAll(sel)); }

    function fmt(n, decimals = 2) {
        if (n == null) return 'N/A';
        return '$' + Number(n).toLocaleString('en-US', { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
    }
    function fmtPnl(n) {
        if (n == null) return 'N/A';
        const sign = n >= 0 ? '+' : '';
        return sign + fmt(n);
    }
    function pnlClass(n) { return n >= 0 ? 'green' : 'red'; }
    function daysLeft(expiry) {
        if (!expiry) return '—';
        const exp = new Date(expiry + 'T16:00:00');
        const now = new Date();
        const diff = Math.ceil((exp - now) / 86400000);
        return diff > 0 ? diff : 0;
    }
    function fmtDate(iso) {
        if (!iso) return '—';
        return new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
    }
    function fmtDateFull(iso) {
        if (!iso) return '—';
        return new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
    }
    function daysBetween(a, b) {
        if (!a || !b) return '—';
        return Math.ceil(Math.abs(new Date(b) - new Date(a)) / 86400000) + 'd';
    }

    async function apiFetch(path, opts = {}) {
        try {
            const res = await fetch(API_BASE + path, {
                credentials: 'include',
                headers: { 'Content-Type': 'application/json', ...(opts.headers || {}) },
                ...opts,
            });
            if (res.status === 401) {
                window.location.href = '/login';
                return null;
            }
            const data = await res.json();
            if (!data.success) throw new Error(data.error || 'API error');
            return data;
        } catch (e) {
            console.error(`API ${path} failed:`, e);
            throw e;
        }
    }

    // ============================================================
    // STATE
    // ============================================================
    let currentSettings = {};
    let openTrades = [];
    let closedTrades = [];

    // ============================================================
    // THEME TOGGLE
    // ============================================================
    const themeToggle = $('#theme-toggle');
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
    const savedTheme = localStorage.getItem('theme');
    if (savedTheme === 'dark' || !savedTheme) setTheme(true);
    if (themeToggle) {
        themeToggle.addEventListener('click', () => {
            setTheme(!document.body.classList.contains('dark'));
        });
    }

    // ============================================================
    // SUB-TAB SWITCHING
    // ============================================================
    const subTabs = $$('.sub-tab');
    const subPanels = $$('.sub-panel');
    const mobileDropdown = $('#mobileSubDropdown');

    function switchSubView(subId) {
        subTabs.forEach(t => t.classList.remove('active'));
        const activeTab = $(`.sub-tab[data-sub="${subId}"]`);
        if (activeTab) activeTab.classList.add('active');
        subPanels.forEach(p => p.classList.remove('active'));
        const targetPanel = $('#sub-' + subId);
        if (targetPanel) targetPanel.classList.add('active');
        if (mobileDropdown) mobileDropdown.value = subId;

        // Lazy-load data for each tab
        if (subId === 'open-positions') loadOpenPositions();
        if (subId === 'trade-history') loadTradeHistory();
        if (subId === 'performance') loadPerformance();
        if (subId === 'settings') loadSettings();
    }

    subTabs.forEach(tab => {
        tab.addEventListener('click', () => switchSubView(tab.dataset.sub));
    });
    if (mobileDropdown) {
        mobileDropdown.addEventListener('change', () => switchSubView(mobileDropdown.value));
    }

    // ============================================================
    // 1. OPEN POSITIONS
    // ============================================================
    async function loadOpenPositions() {
        const container = $('#positions-table-body');
        const statsContainer = $('#stat-cards');
        if (!container) return;

        container.innerHTML = '<tr><td colspan="9" style="text-align:center;padding:32px;">Loading positions...</td></tr>';

        try {
            const [tradesData, statsData] = await Promise.all([
                apiFetch('/trades?status=OPEN'),
                apiFetch('/stats'),
            ]);

            openTrades = tradesData.trades || [];
            const stats = statsData.stats || {};

            // Render stat cards
            if (statsContainer) {
                statsContainer.innerHTML = `
                    <div class="port-stat-card">
                        <div class="port-stat-label">Portfolio Value</div>
                        <div class="port-stat-value">${fmt(stats.portfolio_value)}</div>
                    </div>
                    <div class="port-stat-card">
                        <div class="port-stat-label">Today's P&L</div>
                        <div class="port-stat-value ${pnlClass(stats.todays_pnl)}">${fmtPnl(stats.todays_pnl)}</div>
                    </div>
                    <div class="port-stat-card">
                        <div class="port-stat-label">Open Positions</div>
                        <div class="port-stat-value">${stats.open_positions || 0}</div>
                    </div>
                    <div class="port-stat-card">
                        <div class="port-stat-label">Cash Available</div>
                        <div class="port-stat-value">${fmt(stats.cash_available)}</div>
                    </div>
                `;
            }

            // Update header stats
            const hdrPortfolio = $('#hdr-portfolio-val');
            const hdrToday = $('#hdr-today-pnl');
            const hdrOpen = $('#hdr-open-count');
            if (hdrPortfolio) hdrPortfolio.innerHTML = `Portfolio: <b>${fmt(stats.portfolio_value)}</b>`;
            if (hdrToday) hdrToday.innerHTML = `Today: <b class="${pnlClass(stats.todays_pnl)}">${fmtPnl(stats.todays_pnl)}</b>`;
            if (hdrOpen) hdrOpen.innerHTML = `Open: <b>${stats.open_positions || 0}</b>`;

            // Render positions
            if (openTrades.length === 0) {
                container.innerHTML = '<tr><td colspan="9" style="text-align:center;padding:32px;color:var(--text-muted);">No open positions. Scan for opportunities and place a trade!</td></tr>';
                return;
            }

            container.innerHTML = openTrades.map((t, i) => renderPositionRow(t, i)).join('');
            wirePositionActions();
        } catch (e) {
            container.innerHTML = `<tr><td colspan="9" style="text-align:center;padding:32px;color:var(--red);">Failed to load positions: ${e.message}</td></tr>`;
        }
    }

    function renderPositionRow(t, idx) {
        const greeks = (t.trade_context || {}).greeks || {};
        const volume = (t.trade_context || {}).volume || '—';
        const oi = (t.trade_context || {}).open_interest || '—';
        const breakEven = t.option_type === 'CALL'
            ? (t.strike + t.entry_price).toFixed(2)
            : (t.strike - t.entry_price).toFixed(2);
        const maxLoss = (t.entry_price * t.qty * 100).toFixed(0);
        const slPrice = t.sl_price ? fmt(t.sl_price) : '—';
        const tpPrice = t.tp_price ? fmt(t.tp_price) : '—';
        const aiNote = t.ai_verdict ? `AI: "${t.ai_verdict}" (Score: ${t.ai_score || '—'})` : '';

        return `
            <tr class="port-clickable-row ${idx === 0 ? 'expanded' : ''}" data-expand="pos-${t.id}" data-trade-id="${t.id}">
                <td><strong>${t.ticker}</strong></td>
                <td data-label="Type">${t.option_type}</td>
                <td data-label="Strike">${fmt(t.strike)}</td>
                <td data-label="Entry">${fmt(t.entry_price)}</td>
                <td data-label="Current">${t.current_price ? fmt(t.current_price) : '—'}</td>
                <td data-label="P&L" class="${pnlClass(t.unrealized_pnl)}">${fmtPnl(t.unrealized_pnl)}</td>
                <td data-label="SL / TP">${slPrice} / ${tpPrice}</td>
                <td data-label="Status"><span class="port-pill green">Active ✓</span></td>
                <td class="port-action-btns">
                    <button class="port-btn port-btn-sm btn-adjust" data-id="${t.id}">Adjust</button>
                    <button class="port-btn port-btn-sm port-btn-danger btn-close" data-id="${t.id}">Close</button>
                </td>
            </tr>
            <tr class="port-expanded-row" id="pos-${t.id}" ${idx === 0 ? '' : 'style="display:none;"'}>
                <td colspan="9">
                    <div class="port-expanded-content">
                        <div class="port-expanded-section">
                            <h4>Contract Details</h4>
                            <div class="port-detail-row"><span class="label">Strike</span><span class="value">${fmt(t.strike)}</span></div>
                            <div class="port-detail-row"><span class="label">Expiry</span><span class="value">${fmtDateFull(t.expiry)}</span></div>
                            <div class="port-detail-row"><span class="label">Days Left</span><span class="value">${daysLeft(t.expiry)}</span></div>
                            <div class="port-detail-row"><span class="label">Break Even</span><span class="value">$${breakEven}</span></div>
                            ${aiNote ? `<div class="port-ai-note">${aiNote}</div>` : ''}
                        </div>
                        <div class="port-expanded-section">
                            <h4>Greeks & Activity</h4>
                            <div class="port-detail-row"><span class="label">Delta</span><span class="value">${greeks.delta?.toFixed(3) || t.delta_at_entry?.toFixed(3) || '—'}</span></div>
                            <div class="port-detail-row"><span class="label">Gamma</span><span class="value">${greeks.gamma?.toFixed(4) || '—'}</span></div>
                            <div class="port-detail-row"><span class="label">Theta</span><span class="value">${greeks.theta?.toFixed(3) || '—'}</span></div>
                            <div class="port-detail-row"><span class="label">Vega</span><span class="value">${greeks.vega?.toFixed(3) || '—'}</span></div>
                            <div class="port-detail-row"><span class="label">IV</span><span class="value">${greeks.iv ? (greeks.iv * 100).toFixed(1) + '%' : (t.iv_at_entry ? (t.iv_at_entry * 100).toFixed(1) + '%' : '—')}</span></div>
                            <div class="port-detail-row"><span class="label">Volume</span><span class="value">${typeof volume === 'number' ? volume.toLocaleString() : volume}</span></div>
                            <div class="port-detail-row"><span class="label">Open Interest</span><span class="value">${typeof oi === 'number' ? oi.toLocaleString() : oi}</span></div>
                        </div>
                        <div class="port-expanded-section">
                            <h4>Risk Management</h4>
                            <div class="port-detail-row"><span class="label">SL Price</span><span class="value">${slPrice}</span></div>
                            <div class="port-detail-row"><span class="label">TP Price</span><span class="value">${tpPrice}</span></div>
                            <div class="port-detail-row"><span class="label">Max Loss</span><span class="value red">$${maxLoss}</span></div>
                            <div class="port-detail-row"><span class="label">Qty</span><span class="value">${t.qty}</span></div>
                            <div class="port-detail-row"><span class="label">Strategy</span><span class="value">${t.strategy || '—'}</span></div>
                        </div>
                    </div>
                </td>
            </tr>
        `;
    }

    function wirePositionActions() {
        // Expandable rows
        $$('.port-clickable-row').forEach(row => {
            row.addEventListener('click', (e) => {
                if (e.target.closest('button')) return;
                const expandId = row.dataset.expand;
                const expandedRow = $('#' + expandId);
                if (!expandedRow) return;
                const isVisible = expandedRow.style.display !== 'none';
                expandedRow.style.display = isVisible ? 'none' : '';
                row.classList.toggle('expanded', !isVisible);
            });
        });

        // Close buttons
        $$('.btn-close').forEach(btn => {
            btn.addEventListener('click', async (e) => {
                e.stopPropagation();
                const id = btn.dataset.id;
                const trade = openTrades.find(t => t.id == id);
                if (!trade) return;
                if (!confirm(`Close ${trade.ticker} ${trade.option_type} ${fmt(trade.strike)} position?`)) return;

                btn.disabled = true;
                btn.textContent = 'Closing...';
                try {
                    await apiFetch(`/trades/${id}/close`, {
                        method: 'POST',
                        body: JSON.stringify({ close_reason: 'MANUAL' }),
                    });
                    loadOpenPositions();
                } catch (e) {
                    alert('Failed to close: ' + e.message);
                    btn.disabled = false;
                    btn.textContent = 'Close';
                }
            });
        });

        // Adjust buttons
        $$('.btn-adjust').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                const id = btn.dataset.id;
                const trade = openTrades.find(t => t.id == id);
                if (!trade) return;
                showAdjustModal(trade);
            });
        });
    }

    function showAdjustModal(trade) {
        const existing = $('#adjust-modal');
        if (existing) existing.remove();

        const modal = document.createElement('div');
        modal.id = 'adjust-modal';
        modal.className = 'port-modal-overlay';
        modal.innerHTML = `
            <div class="port-modal">
                <h3>Adjust ${trade.ticker} ${trade.option_type} ${fmt(trade.strike)}</h3>
                <div class="port-settings-row"><span class="port-setting-label">Stop Loss</span><input type="number" step="0.01" id="adj-sl" value="${trade.sl_price || ''}" class="port-settings-input" placeholder="SL price"></div>
                <div class="port-settings-row"><span class="port-setting-label">Take Profit</span><input type="number" step="0.01" id="adj-tp" value="${trade.tp_price || ''}" class="port-settings-input" placeholder="TP price"></div>
                <div style="display:flex;gap:8px;margin-top:16px;">
                    <button class="port-btn port-btn-primary" id="adj-save">Save</button>
                    <button class="port-btn" id="adj-cancel">Cancel</button>
                </div>
            </div>
        `;
        document.body.appendChild(modal);

        $('#adj-cancel').onclick = () => modal.remove();
        modal.onclick = (e) => { if (e.target === modal) modal.remove(); };

        $('#adj-save').onclick = async () => {
            const sl = parseFloat($('#adj-sl').value) || null;
            const tp = parseFloat($('#adj-tp').value) || null;
            try {
                await apiFetch(`/trades/${trade.id}/adjust`, {
                    method: 'PUT',
                    body: JSON.stringify({ sl_price: sl, tp_price: tp }),
                });
                modal.remove();
                loadOpenPositions();
            } catch (e) {
                alert('Adjust failed: ' + e.message);
            }
        };
    }

    // ============================================================
    // 2. TRADE HISTORY
    // ============================================================
    let historyFilter = 'ALL';

    async function loadTradeHistory() {
        const container = $('#history-table-body');
        const summaryContainer = $('#history-summary');
        if (!container) return;

        container.innerHTML = '<tr><td colspan="7" style="text-align:center;padding:32px;">Loading trade history...</td></tr>';

        try {
            const data = await apiFetch('/trades?status=CLOSED&limit=100');
            closedTrades = data.trades || [];
            const statsData = await apiFetch('/stats');
            const stats = statsData.stats || {};

            // Summary bar
            if (summaryContainer) {
                summaryContainer.innerHTML = `
                    <div class="port-summary-box"><div class="port-sum-label">Total Closed</div><div class="port-sum-value">${stats.total_trades || 0}</div></div>
                    <div class="port-summary-box"><div class="port-sum-label">Win Rate</div><div class="port-sum-value ${pnlClass(stats.win_rate - 50)}">${stats.win_rate?.toFixed(0) || 0}%</div></div>
                    <div class="port-summary-box"><div class="port-sum-label">Realized P&L</div><div class="port-sum-value ${pnlClass(stats.total_realized)}">${fmtPnl(stats.total_realized)}</div></div>
                `;
            }

            renderFilteredHistory();
        } catch (e) {
            container.innerHTML = `<tr><td colspan="7" style="text-align:center;padding:32px;color:var(--red);">Failed to load history: ${e.message}</td></tr>`;
        }
    }

    function renderFilteredHistory() {
        const container = $('#history-table-body');
        if (!container) return;

        let filtered = closedTrades;
        if (historyFilter === 'WINS') filtered = closedTrades.filter(t => (t.realized_pnl || 0) > 0);
        else if (historyFilter === 'LOSSES') filtered = closedTrades.filter(t => (t.realized_pnl || 0) < 0);
        else if (historyFilter === 'EXPIRED') filtered = closedTrades.filter(t => t.close_reason === 'EXPIRED');
        else if (historyFilter === 'SL') filtered = closedTrades.filter(t => t.close_reason === 'SL_HIT');
        else if (historyFilter === 'TP') filtered = closedTrades.filter(t => t.close_reason === 'TP_HIT');

        if (filtered.length === 0) {
            container.innerHTML = '<tr><td colspan="7" style="text-align:center;padding:32px;color:var(--text-muted);">No trades match this filter.</td></tr>';
            return;
        }

        container.innerHTML = filtered.map((t, i) => renderHistoryRow(t, i)).join('');
        wireHistoryRows();
    }

    function renderHistoryRow(t, idx) {
        const reasonMap = { 'TP_HIT': ['TP Hit ✓', 'green'], 'SL_HIT': ['SL Hit ✗', 'red'], 'MANUAL': ['Manual Close', ''], 'EXPIRED': ['Expired', ''] };
        const [reasonLabel, reasonClass] = reasonMap[t.close_reason] || [t.close_reason || '—', ''];

        return `
            <tr class="port-clickable-row ${idx === 0 ? 'expanded' : ''}" data-expand="hist-${t.id}">
                <td><strong>${t.ticker}</strong></td>
                <td data-label="Type">${t.option_type}</td>
                <td data-label="Entry → Exit">${fmt(t.entry_price)} → ${t.exit_price ? fmt(t.exit_price) : '—'}</td>
                <td data-label="P&L" class="${pnlClass(t.realized_pnl)}">${fmtPnl(t.realized_pnl)}</td>
                <td data-label="Held">${daysBetween(t.created_at, t.closed_at)}</td>
                <td data-label="Reason"><span class="port-pill ${reasonClass}">${reasonLabel}</span></td>
                <td data-label="Date">${fmtDate(t.closed_at)}</td>
            </tr>
            <tr class="port-expanded-row" id="hist-${t.id}" ${idx === 0 ? '' : 'style="display:none;"'}>
                <td colspan="7">
                    <div class="port-expanded-content">
                        <div class="port-expanded-section">
                            <h4>Execution Details</h4>
                            <div class="port-detail-row"><span class="label">Entry Date</span><span class="value">${fmtDateFull(t.created_at)}</span></div>
                            <div class="port-detail-row"><span class="label">Exit Date</span><span class="value">${fmtDateFull(t.closed_at)}</span></div>
                            <div class="port-detail-row"><span class="label">Entry Fill</span><span class="value">${fmt(t.entry_price)}</span></div>
                            <div class="port-detail-row"><span class="label">Exit Fill</span><span class="value">${t.exit_price ? fmt(t.exit_price) : '—'}</span></div>
                            <div class="port-detail-row"><span class="label">Strike</span><span class="value">${fmt(t.strike)}</span></div>
                            <div class="port-detail-row"><span class="label">Expiry</span><span class="value">${fmtDateFull(t.expiry)}</span></div>
                        </div>
                        <div class="port-expanded-section">
                            <h4>Trade Metrics</h4>
                            <div class="port-detail-row"><span class="label">Strategy</span><span class="value">${t.strategy || '—'}</span></div>
                            <div class="port-detail-row"><span class="label">Qty</span><span class="value">${t.qty}</span></div>
                            <div class="port-detail-row"><span class="label">AI Score</span><span class="value">${t.ai_score || '—'}</span></div>
                            <div class="port-detail-row"><span class="label">AI Verdict</span><span class="value">${t.ai_verdict || '—'}</span></div>
                        </div>
                    </div>
                </td>
            </tr>
        `;
    }

    function wireHistoryRows() {
        $$('#sub-trade-history .port-clickable-row').forEach(row => {
            row.addEventListener('click', (e) => {
                if (e.target.closest('button')) return;
                const expandId = row.dataset.expand;
                const expandedRow = $('#' + expandId);
                if (!expandedRow) return;
                expandedRow.style.display = expandedRow.style.display === 'none' ? '' : 'none';
                row.classList.toggle('expanded');
            });
        });
    }

    // Wire filter pills
    document.addEventListener('click', (e) => {
        if (!e.target.matches('#history-filters .port-pill-filter')) return;
        $$('#history-filters .port-pill-filter').forEach(p => p.classList.remove('active'));
        e.target.classList.add('active');
        const map = { 'All': 'ALL', 'Wins': 'WINS', 'Losses': 'LOSSES', 'Expired': 'EXPIRED', 'SL Hit': 'SL', 'TP Hit': 'TP' };
        historyFilter = map[e.target.textContent] || 'ALL';
        renderFilteredHistory();
    });

    // ============================================================
    // 3. PERFORMANCE
    // ============================================================
    async function loadPerformance() {
        const kpiContainer = $('#perf-kpi-cards');
        const chartsGrid = $('#perf-charts-grid');
        const breakdownGrid = $('#perf-breakdown-grid');
        if (!kpiContainer) return;

        kpiContainer.innerHTML = '<div style="text-align:center;padding:24px;">Loading analytics...</div>';

        try {
            const [statsData, byTickerData, byStratData] = await Promise.all([
                apiFetch('/stats'),
                apiFetch('/analytics/by-ticker').catch(() => ({ success: true, data: [] })),
                apiFetch('/analytics/by-strategy').catch(() => ({ success: true, data: [] })),
            ]);

            const stats = statsData.stats || {};
            const expectancy = stats.total_trades > 0 ? (stats.total_pnl / stats.total_trades) : 0;

            // KPI Cards
            kpiContainer.innerHTML = `
                <div class="port-kpi-card"><div class="port-kpi-label">Total P&L</div><div class="port-kpi-value ${pnlClass(stats.total_pnl)}">${fmtPnl(stats.total_pnl)}</div></div>
                <div class="port-kpi-card"><div class="port-kpi-label">Win Rate</div><div class="port-kpi-value">${stats.win_rate?.toFixed(0) || 0}%</div></div>
                <div class="port-kpi-card"><div class="port-kpi-label">Profit Factor</div><div class="port-kpi-value">${stats.profit_factor?.toFixed(1) || '—'}</div></div>
                <div class="port-kpi-card"><div class="port-kpi-label">Expectancy</div><div class="port-kpi-value ${pnlClass(expectancy)}">${fmtPnl(expectancy)}/trade</div></div>
                <div class="port-kpi-card"><div class="port-kpi-label">Total Trades</div><div class="port-kpi-value">${stats.total_trades || 0}</div></div>
            `;

            // Win/Loss donut (inline SVG)
            const winPct = stats.win_rate || 0;
            const lossPct = 100 - winPct;
            const winArc = (winPct / 100) * 283;
            const lossArc = (lossPct / 100) * 283;

            if (chartsGrid) {
                chartsGrid.innerHTML = `
                    <div class="port-chart-placeholder">
                        <div class="port-chart-label">Win / Loss Distribution</div>
                        <svg viewBox="0 0 120 120" style="max-width:140px;height:140px;">
                            <circle cx="60" cy="60" r="45" fill="none" stroke="#e2e8f0" stroke-width="18" class="doughnut-track"/>
                            <circle cx="60" cy="60" r="45" fill="none" stroke="var(--green)" stroke-width="18"
                                stroke-dasharray="${winArc} ${lossArc}" stroke-dashoffset="0" transform="rotate(-90 60 60)"/>
                            <circle cx="60" cy="60" r="45" fill="none" stroke="var(--red)" stroke-width="18"
                                stroke-dasharray="${lossArc} ${winArc}" stroke-dashoffset="${-winArc}" transform="rotate(-90 60 60)"/>
                            <text x="60" y="56" text-anchor="middle" font-size="14" font-weight="700" fill="var(--text)" font-family="Inter,sans-serif">${winPct.toFixed(0)}%</text>
                            <text x="60" y="72" text-anchor="middle" font-size="8" fill="var(--text-muted)" font-family="Inter,sans-serif">Win Rate</text>
                        </svg>
                    </div>
                    <div class="port-chart-placeholder">
                        <div class="port-chart-label">Stats</div>
                        <div style="padding:12px;">
                            <div class="port-detail-row"><span class="label">Wins</span><span class="value green">${stats.wins || 0}</span></div>
                            <div class="port-detail-row"><span class="label">Losses</span><span class="value red">${stats.losses || 0}</span></div>
                            <div class="port-detail-row"><span class="label">Consecutive Losses</span><span class="value">${stats.consecutive_losses || 0}</span></div>
                            <div class="port-detail-row"><span class="label">Realized P&L</span><span class="value ${pnlClass(stats.total_realized)}">${fmtPnl(stats.total_realized)}</span></div>
                            <div class="port-detail-row"><span class="label">Unrealized P&L</span><span class="value ${pnlClass(stats.total_unrealized)}">${fmtPnl(stats.total_unrealized)}</span></div>
                        </div>
                    </div>
                `;
            }

            // Breakdown tables
            if (breakdownGrid) {
                const byTicker = byTickerData.data || [];
                const byStrat = byStratData.data || [];

                breakdownGrid.innerHTML = `
                    <div class="port-breakdown-card">
                        <div class="port-breakdown-header">By Strategy</div>
                        <table class="port-table">
                            <thead><tr><th>Strategy</th><th>Trades</th><th>Win %</th><th>P&L</th></tr></thead>
                            <tbody>
                                ${byStrat.length > 0 ? byStrat.map(s => `
                                    <tr>
                                        <td>${s.strategy || '—'}</td>
                                        <td data-label="Trades">${s.total || 0}</td>
                                        <td data-label="Win %">${s.win_rate?.toFixed(0) || 0}%</td>
                                        <td data-label="P&L" class="${pnlClass(s.pnl)}">${fmtPnl(s.pnl)}</td>
                                    </tr>
                                `).join('') : '<tr><td colspan="4" style="text-align:center;">No data yet</td></tr>'}
                            </tbody>
                        </table>
                    </div>
                    <div class="port-breakdown-card">
                        <div class="port-breakdown-header">By Ticker</div>
                        <table class="port-table">
                            <thead><tr><th>Ticker</th><th>P&L</th></tr></thead>
                            <tbody>
                                ${byTicker.length > 0 ? byTicker.map(t => `
                                    <tr>
                                        <td><strong>${t.ticker || '—'}</strong></td>
                                        <td data-label="P&L" class="${pnlClass(t.pnl)}">${fmtPnl(t.pnl)}</td>
                                    </tr>
                                `).join('') : '<tr><td colspan="2" style="text-align:center;">No data yet</td></tr>'}
                            </tbody>
                        </table>
                    </div>
                `;
            }
        } catch (e) {
            kpiContainer.innerHTML = `<div style="text-align:center;padding:24px;color:var(--red);">Failed to load analytics: ${e.message}</div>`;
        }
    }

    // ============================================================
    // 4. SETTINGS
    // ============================================================
    async function loadSettings() {
        const grid = $('#settings-grid');
        if (!grid) return;

        try {
            const data = await apiFetch('/settings');
            currentSettings = data.settings || {};
            renderSettings(currentSettings);
        } catch (e) {
            grid.innerHTML = `<div style="text-align:center;padding:24px;color:var(--red);">Failed to load settings: ${e.message}</div>`;
        }
    }

    function renderSettings(s) {
        // Populate input values
        const fields = {
            'set-account-balance': s.account_balance,
            'set-daily-loss': s.daily_loss_limit,
            'set-max-positions': s.max_positions,
            'set-default-sl': s.default_sl_pct,
            'set-default-tp': s.default_tp_pct,
            'set-max-daily': s.max_daily_trades,
            'set-tradier-id': s.tradier_account_id || '',
        };
        Object.entries(fields).forEach(([id, val]) => {
            const el = $('#' + id);
            if (el) el.value = val;
        });

        // Toggle switches
        const toggles = {
            'set-auto-close': s.auto_close_expiry,
            'set-require-confirm': s.require_trade_confirm,
            'set-alert-bracket': s.alert_on_bracket_hit,
        };
        Object.entries(toggles).forEach(([id, val]) => {
            const el = $('#' + id);
            if (el) el.checked = !!val;
        });

        // Broker mode
        $$('.port-mode-opt[data-mode]').forEach(btn => {
            btn.classList.remove('active-green');
            btn.classList.add('inactive');
            if (btn.dataset.mode === s.broker_mode) {
                btn.classList.remove('inactive');
                btn.classList.add('active-green');
            }
        });

        // Connection status
        const statusDot = $('#broker-status');
        if (statusDot) {
            const connected = s.broker_mode === 'TRADIER_SANDBOX' ? s.has_sandbox_token : s.has_live_token;
            statusDot.textContent = connected ? 'Connected' : 'Not Connected';
            statusDot.className = 'port-status-dot ' + (connected ? '' : 'disconnected');
        }
    }

    // Save settings handler
    document.addEventListener('click', async (e) => {
        if (!e.target.matches('#btn-save-settings')) return;

        const btn = e.target;
        btn.disabled = true;
        btn.textContent = 'Saving...';

        try {
            const payload = {
                account_balance: parseFloat($('#set-account-balance')?.value) || 5000,
                daily_loss_limit: parseFloat($('#set-daily-loss')?.value) || 500,
                max_positions: parseInt($('#set-max-positions')?.value) || 5,
                default_sl_pct: parseFloat($('#set-default-sl')?.value) || 20,
                default_tp_pct: parseFloat($('#set-default-tp')?.value) || 50,
                max_daily_trades: parseInt($('#set-max-daily')?.value) || 10,
                auto_close_expiry: $('#set-auto-close')?.checked ?? true,
                require_trade_confirm: $('#set-require-confirm')?.checked ?? true,
                alert_on_bracket_hit: $('#set-alert-bracket')?.checked ?? true,
            };

            await apiFetch('/settings', {
                method: 'PUT',
                body: JSON.stringify(payload),
            });

            btn.textContent = '✅ Saved!';
            setTimeout(() => { btn.textContent = '💾 Save Settings'; btn.disabled = false; }, 2000);
        } catch (e) {
            alert('Save failed: ' + e.message);
            btn.textContent = '💾 Save Settings';
            btn.disabled = false;
        }
    });

    // Broker mode toggle
    document.addEventListener('click', (e) => {
        if (!e.target.matches('.port-mode-opt[data-mode]')) return;
        $$('.port-mode-opt[data-mode]').forEach(b => {
            b.classList.remove('active-green');
            b.classList.add('inactive');
        });
        e.target.classList.remove('inactive');
        e.target.classList.add('active-green');
    });

    // ============================================================
    // 5. EXPORT
    // ============================================================
    document.addEventListener('click', (e) => {
        if (e.target.matches('.btn-export-csv')) {
            window.open(API_BASE + '/analytics/export/csv', '_blank');
        }
        if (e.target.matches('.btn-export-json')) {
            window.open(API_BASE + '/analytics/export/json', '_blank');
        }
    });

    // ============================================================
    // TAB NAVIGATION (Scanner ↔ Portfolio)
    // ============================================================
    document.addEventListener('click', (e) => {
        if (e.target.matches('.app-tab[data-tab="scanner"]') || e.target.textContent === 'Scanner') {
            window.location.href = '/';
        }
    });

    // ============================================================
    // INIT: Load open positions on page load
    // ============================================================
    loadOpenPositions();

})();
