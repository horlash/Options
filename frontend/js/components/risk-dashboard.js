/**
 * Risk Dashboard Component
 * Feature: automated-trading
 * 
 * Manages the Risk Dashboard tab: portfolio heat, win rate,
 * tilt status, and weekly performance report.
 * Fetches live data from paperApi.getStats().
 */

const riskDashboard = (() => {

    async function fetchAndRender() {
        const container = document.getElementById('risk-content');
        if (!container) return;

        // Try to fetch live stats from API
        let stats = null;
        try {
            if (typeof paperApi !== 'undefined') {
                const res = await paperApi.getStats();
                if (res && res.success && res.stats) {
                    stats = res.stats;
                }
            }
        } catch (e) {
            console.warn('[risk-dashboard] Failed to fetch stats:', e);
        }

        // If no stats available, show empty state
        if (!stats) {
            container.innerHTML = `
                <div class="risk-cards">
                    <div class="risk-card" style="grid-column: 1 / -1; text-align: center; padding: 3rem;">
                        <div style="font-size: 2rem; margin-bottom: 1rem;">📊</div>
                        <h3 style="color: var(--text-primary); margin-bottom: 0.5rem;">No Risk Data Available</h3>
                        <p style="color: var(--text-muted);">Place trades to start tracking risk metrics.</p>
                    </div>
                </div>
            `;
            return;
        }

        // Compute risk metrics from live stats
        const openCount = stats.open_positions || 0;
        const maxPos = stats.max_positions || 5;
        const portfolioValue = stats.portfolio_value || 0;
        const cashAvailable = stats.cash_available || 0;
        const invested = portfolioValue - cashAvailable;
        const heatCurrent = portfolioValue > 0 ? +((invested / portfolioValue) * 100).toFixed(1) : 0;
        const heatLimit = 6.0;
        const heatPct = (heatCurrent / heatLimit * 100).toFixed(0);
        const heatColor = heatCurrent <= 3 ? 'var(--secondary)' :
            heatCurrent <= 5 ? 'var(--accent)' : 'var(--danger)';

        const wins = stats.wins || 0;
        const losses = stats.losses || 0;
        const totalTrades = stats.total_trades || 0;
        const winPct = stats.win_rate || 0;

        // Tilt: approximate from consecutive losses (use losses vs total as proxy)
        const consecutiveLosses = losses > 0 && totalTrades > 0 ? Math.min(losses, 5) : 0;
        const maxBeforeWarning = 3;
        const maxBeforeDanger = 5;
        const tiltStatus = consecutiveLosses >= maxBeforeDanger ? 'danger' :
            consecutiveLosses >= maxBeforeWarning ? 'warning' : 'clear';
        const tiltColor = tiltStatus === 'clear' ? 'var(--secondary)' :
            tiltStatus === 'warning' ? 'var(--accent)' : 'var(--danger)';
        const tiltEmoji = tiltStatus === 'clear' ? '✅' :
            tiltStatus === 'warning' ? '⚠️' : '🛑';
        const tiltText = tiltStatus === 'clear' ? 'CLEAR' :
            tiltStatus === 'warning' ? 'CAUTION' : 'STOP TRADING';

        // Weekly report from live stats
        const totalRealized = stats.total_realized || 0;
        const totalUnrealized = stats.total_unrealized || 0;
        const profitFactor = stats.profit_factor || 0;
        const avgWin = wins > 0 ? (totalRealized > 0 ? totalRealized / wins : 0) : 0;
        const avgLoss = losses > 0 ? (totalRealized < 0 ? totalRealized / losses : 0) : 0;

        // ── Semi-circle gauge math ──
        // Arc from 180° to 0° (left to right across top half)
        // circumference of half-circle r=45: π*r = ~141.4
        const gaugeR = 45;
        const gaugeCircumference = Math.PI * gaugeR; // ~141.4
        const gaugeFillPct = Math.min(parseFloat(heatPct), 100) / 100;
        const gaugeDash = gaugeFillPct * gaugeCircumference;
        const gaugeGap = gaugeCircumference - gaugeDash;

        // Tilt dots helper
        const totalDots = maxBeforeDanger;
        const tiltDots = Array.from({ length: totalDots }, (_, i) => {
            const filled = i < consecutiveLosses;
            const cls = filled
                ? (i >= maxBeforeWarning - 1 ? 'tilt-counter-dot filled-danger' : 'tilt-counter-dot filled-warn')
                : 'tilt-counter-dot';
            return `<div class="${cls}"></div>`;
        }).join('');

        // Win rate bar colors
        const wrColor = winPct >= 60 ? '#22c55e' : winPct >= 45 ? '#f59e0b' : '#ef4444';
        const winPctSafe = totalTrades > 0 ? winPct : 0;

        // Tilt badge class
        const tiltBadgeClass = tiltStatus === 'clear' ? 'tilt-balanced'
            : tiltStatus === 'warning' ? 'tilt-bullish' : 'tilt-bearish';

        const html = `
            <!-- Risk Metric Cards (W2 Enhanced) -->
            <div class="risk-cards">
                <!-- Portfolio Heat: Semi-circle gauge -->
                <div class="risk-card" style="text-align:center;">
                    <div class="risk-card-header">
                        <span class="risk-card-title">🔥 Portfolio Heat</span>
                        <span style="font-size: 0.8rem; color: ${heatColor};">${heatCurrent <= heatLimit ? '✅ SAFE' : '🚨 OVER LIMIT'}</span>
                    </div>
                    <!-- Semi-circle SVG gauge -->
                    <svg class="heat-gauge-svg" width="120" height="70" viewBox="0 0 110 60">
                        <!-- Track arc (half circle) -->
                        <path
                            class="gauge-track"
                            d="M 10 55 A 45 45 0 0 1 100 55"
                            fill="none"
                            stroke="rgba(255,255,255,0.08)"
                            stroke-width="10"
                            stroke-linecap="round"
                        />
                        <!-- Fill arc -->
                        <path
                            class="gauge-fill"
                            d="M 10 55 A 45 45 0 0 1 100 55"
                            fill="none"
                            stroke="${heatColor}"
                            stroke-width="10"
                            stroke-linecap="round"
                            stroke-dasharray="${gaugeDash.toFixed(1)} ${(gaugeCircumference + 10).toFixed(1)}"
                        />
                        <text x="55" y="52" class="heat-gauge-value" style="fill:${heatColor}; font-size:1rem; font-weight:800;">${heatCurrent}%</text>
                        <text x="55" y="60" class="heat-gauge-label" style="font-size:0.55rem; fill:rgba(148,163,184,0.9);">of ${heatLimit}% limit</text>
                    </svg>
                    <div class="risk-card-sub" style="margin-top:0.25rem;">${openCount} of ${maxPos} positions open</div>
                </div>

                <!-- Win Rate: horizontal bar -->
                <div class="risk-card">
                    <div class="risk-card-header">
                        <span class="risk-card-title">📊 Win Rate</span>
                        <span style="font-size: 0.8rem; color: var(--text-muted);">Last ${totalTrades} trades</span>
                    </div>
                    <div class="risk-card-value" style="color: ${winPct >= 55 ? 'var(--secondary)' : 'var(--accent)'}; font-size:2rem; font-weight:800; margin-bottom:0.25rem;">${winPct.toFixed(0)}%</div>
                    <div class="risk-winrate-container">
                        <div class="wr-track">
                            <div class="wr-fill" style="width:${winPctSafe}%; background: linear-gradient(90deg, ${wrColor}, ${wrColor}cc);"></div>
                        </div>
                        <div class="wr-labels">
                            <span style="color:var(--secondary);">${wins}W</span>
                            <span style="color:var(--danger);">${losses}L</span>
                        </div>
                    </div>
                </div>

                <!-- Tilt Status: counter dots + badge -->
                <div class="risk-card" style="text-align:center;">
                    <div class="risk-card-header">
                        <span class="risk-card-title">🧠 Tilt Status</span>
                    </div>
                    <span class="risk-tilt-badge ${tiltBadgeClass}">${tiltEmoji} ${tiltText}</span>
                    <div class="risk-card-sub" style="margin-top:0.5rem;">${consecutiveLosses} consecutive losses</div>
                    <div class="tilt-counter-display" title="${maxBeforeWarning} = caution, ${maxBeforeDanger} = stop">
                        ${tiltDots}
                    </div>
                    <div style="font-size:0.65rem; color:var(--text-muted); margin-top:0.35rem;">${maxBeforeWarning} = caution &nbsp;|&nbsp; ${maxBeforeDanger} = stop</div>
                </div>
            </div>

            <!-- Risk Rules Section -->
            <div class="weekly-report" style="margin-top: var(--spacing-md);">
                <h3>⚖️ Risk Rules — Current Status</h3>
                <div class="report-grid">
                    <div class="report-metric">
                        <div class="report-metric-label">Max Positions</div>
                        <div class="report-metric-value">${openCount}/${maxPos}</div>
                    </div>
                    <div class="report-metric">
                        <div class="report-metric-label">Daily Loss Used</div>
                        <div class="report-metric-value" style="color: ${Math.abs(totalRealized) > 500 ? 'var(--danger)' : 'var(--secondary)'};">$${Math.abs(totalRealized < 0 ? totalRealized : 0).toFixed(0)}/$500</div>
                    </div>
                    <div class="report-metric">
                        <div class="report-metric-label">Daily Trades</div>
                        <div class="report-metric-value">${totalTrades}/10</div>
                    </div>
                    <div class="report-metric">
                        <div class="report-metric-label">Portfolio Concentration</div>
                        <div class="report-metric-value">${openCount > 0 ? 'Active' : 'None'}</div>
                    </div>
                    <div class="report-metric">
                        <div class="report-metric-label">Sector Exposure</div>
                        <div class="report-metric-value">${openCount > 0 ? 'Diversified' : 'N/A'}</div>
                    </div>
                    <div class="report-metric">
                        <div class="report-metric-label">Last Updated</div>
                        <div class="report-metric-value">${new Date().toLocaleTimeString('en-US', {hour: '2-digit', minute: '2-digit'})}</div>
                    </div>
                </div>
            </div>

            <!-- Performance Summary -->
            <div class="weekly-report" style="margin-top: var(--spacing-md);">
                <h3>📋 Performance Summary</h3>
                <div class="report-grid">
                    <div class="report-metric">
                        <div class="report-metric-label">Total Trades</div>
                        <div class="report-metric-value">${totalTrades}</div>
                    </div>
                    <div class="report-metric">
                        <div class="report-metric-label">Win Rate</div>
                        <div class="report-metric-value" style="color: ${winPct >= 55 ? 'var(--secondary)' : 'var(--accent)'};">${winPct.toFixed(0)}%</div>
                    </div>
                    <div class="report-metric">
                        <div class="report-metric-label">Avg Win</div>
                        <div class="report-metric-value" style="color: var(--secondary);">+$${avgWin.toFixed(0)}</div>
                    </div>
                    <div class="report-metric">
                        <div class="report-metric-label">Avg Loss</div>
                        <div class="report-metric-value" style="color: var(--danger);">-$${Math.abs(avgLoss).toFixed(0)}</div>
                    </div>
                    <div class="report-metric">
                        <div class="report-metric-label">Profit Factor</div>
                        <div class="report-metric-value" style="color: ${profitFactor >= 1.5 ? 'var(--secondary)' : 'var(--accent)'};">${profitFactor.toFixed(2)}</div>
                    </div>
                    <div class="report-metric">
                        <div class="report-metric-label">Total P&L</div>
                        <div class="report-metric-value" style="color: ${(totalRealized + totalUnrealized) >= 0 ? 'var(--secondary)' : 'var(--danger)'};">${(totalRealized + totalUnrealized) >= 0 ? '+' : ''}$${(totalRealized + totalUnrealized).toFixed(0)}</div>
                    </div>
                    <div class="report-metric">
                        <div class="report-metric-label">Realized</div>
                        <div class="report-metric-value" style="color: ${totalRealized >= 0 ? 'var(--secondary)' : 'var(--danger)'};">${totalRealized >= 0 ? '+' : ''}$${totalRealized.toFixed(0)}</div>
                    </div>
                    <div class="report-metric">
                        <div class="report-metric-label">Unrealized</div>
                        <div class="report-metric-value" style="color: ${totalUnrealized >= 0 ? 'var(--secondary)' : 'var(--danger)'};">${totalUnrealized >= 0 ? '+' : ''}$${totalUnrealized.toFixed(0)}</div>
                    </div>
                </div>
            </div>
        `;

        container.innerHTML = html;
    }

    function render() {
        fetchAndRender();
    }

    function init() {
        render();
    }

    return {
        init,
        render
    };
})();
