/**
 * Risk Dashboard Component
 * Feature: automated-trading
 * 
 * Manages the Risk Dashboard tab: portfolio heat, win rate,
 * tilt status, and weekly performance report.
 * Uses mock data for the feature branch.
 */

const riskDashboard = (() => {
    // Mock risk metrics
    const mockMetrics = {
        heat: {
            current: 4.1,
            limit: 6.0,
            positions: [
                { ticker: 'NVDA', heat: 1.6 },
                { ticker: 'AMD', heat: 1.3 },
                { ticker: 'TSLA', heat: 1.2 }
            ]
        },
        winRate: {
            wins: 16,
            losses: 9,
            total: 25,
            pct: 64
        },
        tilt: {
            consecutiveLosses: 1,
            maxBeforeWarning: 3,
            maxBeforeDanger: 5,
            status: 'clear' // clear, warning, danger
        },
        weeklyReport: {
            period: 'Feb 10 - Feb 16, 2026',
            trades: 8,
            winRate: '75%',
            avgWin: '+$142',
            avgLoss: '-$68',
            expectancy: '+$89.50',
            maxDrawdown: '-2.3%',
            bestTrade: 'NVDA +$210',
            worstTrade: 'INTC -$95'
        }
    };

    function render() {
        const container = document.getElementById('risk-content');
        if (!container) return;

        const m = mockMetrics;
        const heatPct = (m.heat.current / m.heat.limit * 100).toFixed(0);
        const heatColor = m.heat.current <= 3 ? 'var(--secondary)' :
            m.heat.current <= 5 ? 'var(--accent)' : 'var(--danger)';
        const heatBarColor = m.heat.current <= 3 ? 'var(--secondary)' :
            m.heat.current <= 5 ? 'var(--accent)' : 'var(--danger)';

        const tiltColor = m.tilt.status === 'clear' ? 'var(--secondary)' :
            m.tilt.status === 'warning' ? 'var(--accent)' : 'var(--danger)';
        const tiltEmoji = m.tilt.status === 'clear' ? '✅' :
            m.tilt.status === 'warning' ? '⚠️' : '🛑';
        const tiltText = m.tilt.status === 'clear' ? 'CLEAR' :
            m.tilt.status === 'warning' ? 'CAUTION' : 'STOP TRADING';

        const html = `
            <!-- Risk Metric Cards -->
            <div class="risk-cards">
                <!-- Portfolio Heat -->
                <div class="risk-card">
                    <div class="risk-card-header">
                        <span class="risk-card-title">🔥 Portfolio Heat</span>
                        <span style="font-size: 0.8rem; color: ${heatColor};">${m.heat.current <= m.heat.limit ? '✅ SAFE' : '🚨 OVER LIMIT'}</span>
                    </div>
                    <div class="risk-card-value" style="color: ${heatColor};">${m.heat.current}%</div>
                    <div class="risk-card-sub">of ${m.heat.limit}% limit (${m.heat.positions.length} positions)</div>
                    <div class="heat-bar-container">
                        <div class="heat-bar-fill" style="width: ${Math.min(heatPct, 100)}%; background: ${heatBarColor};"></div>
                        <div class="heat-bar-limit" style="left: 100%;">
                            <span class="heat-bar-limit-label">${m.heat.limit}%</span>
                        </div>
                    </div>
                    <div style="margin-top: 0.75rem; font-size: 0.75rem; color: var(--text-muted);">
                        ${m.heat.positions.map(p => `${p.ticker}: ${p.heat}%`).join(' · ')}
                    </div>
                </div>

                <!-- Win Rate -->
                <div class="risk-card">
                    <div class="risk-card-header">
                        <span class="risk-card-title">📊 Win Rate</span>
                        <span style="font-size: 0.8rem; color: var(--text-muted);">Last ${m.winRate.total} trades</span>
                    </div>
                    <div class="risk-card-value" style="color: ${m.winRate.pct >= 55 ? 'var(--secondary)' : 'var(--accent)'};">${m.winRate.pct}%</div>
                    <div class="risk-card-sub">${m.winRate.wins}W / ${m.winRate.losses}L</div>
                    <div class="winrate-bar">
                        <div class="winrate-bar-win" style="width: ${m.winRate.pct}%;"></div>
                        <div class="winrate-bar-loss" style="width: ${100 - m.winRate.pct}%;"></div>
                    </div>
                </div>

                <!-- Tilt Status -->
                <div class="risk-card">
                    <div class="risk-card-header">
                        <span class="risk-card-title">🧠 Tilt Status</span>
                        <span style="font-size: 0.8rem; color: ${tiltColor};">${tiltEmoji} ${tiltText}</span>
                    </div>
                    <div class="risk-card-value" style="color: ${tiltColor};">${m.tilt.consecutiveLosses}</div>
                    <div class="risk-card-sub">consecutive losses (${m.tilt.maxBeforeWarning} = warning, ${m.tilt.maxBeforeDanger} = stop)</div>
                </div>
            </div>

            <!-- Weekly Report -->
            <div class="weekly-report">
                <h3>📋 Weekly Performance Report — ${m.weeklyReport.period}</h3>
                <div class="report-grid">
                    <div class="report-metric">
                        <div class="report-metric-label">Trades</div>
                        <div class="report-metric-value">${m.weeklyReport.trades}</div>
                    </div>
                    <div class="report-metric">
                        <div class="report-metric-label">Win Rate</div>
                        <div class="report-metric-value" style="color: var(--secondary);">${m.weeklyReport.winRate}</div>
                    </div>
                    <div class="report-metric">
                        <div class="report-metric-label">Avg Win</div>
                        <div class="report-metric-value" style="color: var(--secondary);">${m.weeklyReport.avgWin}</div>
                    </div>
                    <div class="report-metric">
                        <div class="report-metric-label">Avg Loss</div>
                        <div class="report-metric-value" style="color: var(--danger);">${m.weeklyReport.avgLoss}</div>
                    </div>
                    <div class="report-metric">
                        <div class="report-metric-label">Expectancy</div>
                        <div class="report-metric-value" style="color: var(--secondary);">${m.weeklyReport.expectancy}</div>
                    </div>
                    <div class="report-metric">
                        <div class="report-metric-label">Max Drawdown</div>
                        <div class="report-metric-value" style="color: var(--accent);">${m.weeklyReport.maxDrawdown}</div>
                    </div>
                    <div class="report-metric">
                        <div class="report-metric-label">Best Trade</div>
                        <div class="report-metric-value" style="color: var(--secondary);">${m.weeklyReport.bestTrade}</div>
                    </div>
                    <div class="report-metric">
                        <div class="report-metric-label">Worst Trade</div>
                        <div class="report-metric-value" style="color: var(--danger);">${m.weeklyReport.worstTrade}</div>
                    </div>
                </div>
            </div>
        `;

        container.innerHTML = html;
    }

    function init() {
        render();
    }

    return {
        init,
        render
    };
})();
