/**
 * Portfolio Component
 * Feature: automated-trading
 * 
 * Manages the Portfolio tab: mock positions, P&L calculations,
 * stat cards, positions table, and action button handlers.
 */

const portfolio = (() => {
    // Mock portfolio data
    let positions = [
        {
            id: 1,
            ticker: 'NVDA',
            type: 'Call',
            strike: 150,
            entry: 4.20,
            current: 5.10,
            sl: 3.15,
            tp: 6.30,
            qty: 1,
            openDate: '2026-02-14'
        },
        {
            id: 2,
            ticker: 'AMD',
            type: 'Call',
            strike: 180,
            entry: 3.50,
            current: 3.20,
            sl: 2.45,
            tp: 5.25,
            qty: 1,
            openDate: '2026-02-15'
        },
        {
            id: 3,
            ticker: 'TSLA',
            type: 'Put',
            strike: 340,
            entry: 6.80,
            current: 8.20,
            sl: 4.76,
            tp: 10.20,
            qty: 1,
            openDate: '2026-02-13'
        }
    ];

    let nextId = 4;

    function getAccountStats() {
        const totalPnL = positions.reduce((sum, p) => {
            return sum + ((p.current - p.entry) * p.qty * 100);
        }, 0);

        const todayPnL = 85; // mock
        const accountValue = 5280;
        const cash = 3540;

        return {
            accountValue,
            allTimePct: ((accountValue - 5000) / 5000 * 100).toFixed(1),
            todayPnL,
            todayPct: ((todayPnL / accountValue) * 100).toFixed(1),
            openPositions: positions.length,
            maxPositions: 5,
            cash,
            cashPct: ((cash / accountValue) * 100).toFixed(0)
        };
    }

    function getPositionStatus(pos) {
        const pnlPct = ((pos.current - pos.entry) / pos.entry * 100);

        if (pnlPct >= 15) {
            // Check if SL has been moved to break-even
            if (pos.sl >= pos.entry) {
                return { emoji: '🟢', text: '→ Break-even SL active', color: 'var(--secondary)' };
            }
            return { emoji: '🟢', text: 'Winning', color: 'var(--secondary)' };
        } else if (pnlPct >= 0) {
            return { emoji: '🟢', text: 'Winning', color: 'var(--secondary)' };
        } else if (pnlPct >= -15) {
            return { emoji: '🟡', text: 'Dipping', color: 'var(--accent)' };
        } else {
            return { emoji: '🔴', text: 'At Risk', color: 'var(--danger)' };
        }
    }

    function render() {
        const container = document.getElementById('portfolio-content');
        if (!container) return;

        const stats = getAccountStats();

        const statsHtml = `
            <div class="portfolio-stats">
                <div class="port-stat-card">
                    <div class="port-stat-label">Account Value</div>
                    <div class="port-stat-value" style="color: var(--text-primary);">$${stats.accountValue.toLocaleString()}</div>
                    <div class="port-stat-sub" style="color: var(--secondary);">+${stats.allTimePct}% All Time</div>
                </div>
                <div class="port-stat-card">
                    <div class="port-stat-label">Today's P&L</div>
                    <div class="port-stat-value" style="color: ${stats.todayPnL >= 0 ? 'var(--secondary)' : 'var(--danger)'};">
                        ${stats.todayPnL >= 0 ? '+' : ''}$${stats.todayPnL}
                    </div>
                    <div class="port-stat-sub" style="color: ${stats.todayPnL >= 0 ? 'var(--secondary)' : 'var(--danger)'};">
                        ${stats.todayPnL >= 0 ? '+' : ''}${stats.todayPct}%
                    </div>
                </div>
                <div class="port-stat-card">
                    <div class="port-stat-label">Open Positions</div>
                    <div class="port-stat-value" style="color: var(--primary-light);">${stats.openPositions}</div>
                    <div class="port-stat-sub">of ${stats.maxPositions} max</div>
                </div>
                <div class="port-stat-card">
                    <div class="port-stat-label">Cash Available</div>
                    <div class="port-stat-value" style="color: var(--text-primary);">$${stats.cash.toLocaleString()}</div>
                    <div class="port-stat-sub">${stats.cashPct}% cash</div>
                </div>
            </div>
        `;

        let tableHtml = '';
        if (positions.length > 0) {
            const rows = positions.map(pos => {
                const pnl = (pos.current - pos.entry) * pos.qty * 100;
                const pnlPct = ((pos.current - pos.entry) / pos.entry * 100).toFixed(0);
                const status = getPositionStatus(pos);
                const isProfit = pnl >= 0;
                const typeColor = pos.type === 'Call' ? 'var(--secondary)' : 'var(--danger)';

                return `
                    <tr>
                        <td class="pos-ticker">${pos.ticker}</td>
                        <td style="color: ${typeColor}">${pos.type}</td>
                        <td>$${pos.strike}</td>
                        <td>$${pos.entry.toFixed(2)}</td>
                        <td>$${pos.current.toFixed(2)}</td>
                        <td class="${isProfit ? 'pos-pnl-pos' : 'pos-pnl-neg'}">
                            ${isProfit ? '+' : ''}$${pnl.toFixed(0)} (${isProfit ? '+' : ''}${pnlPct}%)
                        </td>
                        <td>$${pos.sl.toFixed(2)} / $${pos.tp.toFixed(2)}</td>
                        <td><span class="pos-status" style="color: ${status.color};">${status.emoji} ${status.text}</span></td>
                        <td>
                            <button class="pos-action-btn" onclick="portfolio.showAction('Adjust SL', '${pos.ticker}')">Adjust SL</button>
                            <button class="pos-action-btn close-btn" onclick="portfolio.showAction('Close', '${pos.ticker}')">Close</button>
                        </td>
                    </tr>
                `;
            }).join('');

            tableHtml = `
                <table class="positions-table">
                    <thead>
                        <tr>
                            <th>Ticker</th>
                            <th>Type</th>
                            <th>Strike</th>
                            <th>Entry</th>
                            <th>Current</th>
                            <th>P&L</th>
                            <th>SL / TP</th>
                            <th>Status</th>
                            <th>Actions</th>
                        </tr>
                    </thead>
                    <tbody>${rows}</tbody>
                </table>
            `;
        } else {
            tableHtml = `
                <div class="portfolio-empty">
                    <div class="portfolio-empty-icon">💼</div>
                    <p>No open positions yet. Scan for opportunities and place your first trade!</p>
                </div>
            `;
        }

        container.innerHTML = statsHtml + tableHtml;
    }

    function addPosition(data) {
        positions.push({
            id: nextId++,
            ticker: data.ticker,
            type: data.type === 'CALL' ? 'Call' : 'Put',
            strike: parseFloat(data.strike),
            entry: data.entry,
            current: data.current || data.entry,
            sl: data.sl,
            tp: data.tp,
            qty: 1,
            openDate: new Date().toISOString().split('T')[0]
        });
        render(); // Re-render to show new position
    }

    function showAction(action, ticker) {
        // Mock — just show a toast
        if (typeof toast !== 'undefined' && toast.success) {
            toast.success(`${action} for ${ticker} — Feature coming in production build`);
        } else {
            alert(`${action} for ${ticker} — Feature coming in production build`);
        }
    }

    function init() {
        render();
    }

    return {
        init,
        render,
        addPosition,
        showAction,
        getAccountStats
    };
})();
