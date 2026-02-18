/**
 * Trade Modal Component
 * Feature: automated-trading
 * 
 * Handles the trade setup modal: opening, closing, risk calculations,
 * price/qty adjustments, pre-trade checks, and trade confirmation.
 * Uses mock data for the feature branch — no live API calls.
 */

const tradeModal = (() => {
    // Mock account state
    const mockAccount = {
        value: 5280,
        cash: 3540,
        openPositions: 3,
        maxPositions: 5,
        dailyLossUsed: 0,
        dailyLossLimit: 150,
        heatPercent: 4.1,
        heatLimit: 6.0,
        holdings: ['NVDA', 'AMD', 'TSLA'] // existing positions
    };

    let currentTrade = null;

    /**
     * Open the trade modal with data from a scan result card
     * @param {Object} data - Card data: ticker, price, strike, expiry, daysLeft, premium, type, score, badges
     */
    function open(data) {
        currentTrade = {
            ...data,
            limitPrice: data.premium,
            qty: 1,
            slPercent: 0.25,
            tpPercent: 0.50
        };

        const modal = document.getElementById('trade-modal-overlay');
        if (!modal) return;

        renderModal();
        modal.classList.add('show');
    }

    function close() {
        const modal = document.getElementById('trade-modal-overlay');
        if (modal) modal.classList.remove('show');
        currentTrade = null;
    }

    function renderModal() {
        if (!currentTrade) return;

        const t = currentTrade;
        const isCall = t.type === 'CALL';
        const totalCost = t.limitPrice * t.qty * 100;
        const slPrice = +(t.limitPrice * (1 - t.slPercent)).toFixed(2);
        const tpPrice = +(t.limitPrice * (1 + t.tpPercent)).toFixed(2);
        const maxLoss = +((t.limitPrice - slPrice) * t.qty * 100).toFixed(2);
        const targetProfit = +((tpPrice - t.limitPrice) * t.qty * 100).toFixed(2);
        const riskReward = (targetProfit / maxLoss).toFixed(1);
        const accountPct = ((maxLoss / mockAccount.value) * 100).toFixed(1);
        const heatAfter = +(mockAccount.heatPercent + (totalCost / mockAccount.value) * 100).toFixed(1);
        const heatStatus = heatAfter <= mockAccount.heatLimit ? `within ${mockAccount.heatLimit}% limit` : `OVER ${mockAccount.heatLimit}% limit!`;

        // Pre-trade checks
        const checks = [
            { pass: mockAccount.cash >= totalCost, text: `Buying power sufficient ($${mockAccount.cash.toLocaleString()} available)` },
            { pass: true, text: 'Bid-Ask spread: 3.2% (healthy)' },
            { pass: true, text: 'Open Interest: 2,450 (liquid)' },
            { pass: t.daysLeft > 5 || !t.hasEarnings, text: t.hasEarnings ? `⚠️ Earnings within ${t.daysLeft}d` : 'No earnings within 5 days' },
            { pass: mockAccount.dailyLossUsed + maxLoss <= mockAccount.dailyLossLimit, text: `Daily loss limit: $${mockAccount.dailyLossUsed} used of $${mockAccount.dailyLossLimit}` },
            { pass: !mockAccount.holdings.includes(t.ticker), text: `No duplicate position for ${t.ticker}` }
        ];

        const actionClass = isCall ? 'order-action-call' : 'order-action-put';
        const actionText = isCall ? 'BUY CALL' : 'BUY PUT';

        const html = `
            <div class="trade-modal">
                <div class="modal-header-trade">
                    <h2>⚡ Trade Setup</h2>
                    <button class="modal-close-trade" onclick="tradeModal.close()">×</button>
                </div>
                <div class="modal-body-trade">
                    <!-- AI Warning Banner (if present) -->
                    ${t.aiWarning ? `
                    <div style="background: rgba(255,77,77,0.1); border: 1px solid var(--danger); border-radius: var(--radius-sm); padding: 0.75rem 1rem; margin-bottom: 0.75rem; font-size: 0.9rem; color: var(--danger); font-weight: 600;">
                        ${t.aiWarning}
                    </div>` : ''}

                    <!-- Order Summary -->
                    <div class="order-summary-bar">
                        <div>
                            <span class="order-ticker">${t.ticker}</span>
                            <span class="order-action-badge ${actionClass}">${actionText}</span>
                        </div>
                        <div style="text-align: right; display: flex; gap: 1rem; align-items: center;">
                            ${t.cardScore ? `
                            <div style="text-align: center;">
                                <div style="font-size: 0.7rem; color: var(--text-muted);">Card</div>
                                <div style="font-size: 1.1rem; font-weight: 700; color: var(--text-muted);">${Math.round(t.cardScore)}</div>
                            </div>` : ''}
                            <div style="text-align: center;">
                                <div style="font-size: 0.7rem; color: var(--text-muted);">${t.aiConviction ? 'AI' : 'Score'}</div>
                                <div style="font-size: 1.5rem; font-weight: 800; color: ${t.score >= 65 ? 'var(--secondary)' : t.score >= 40 ? 'var(--accent)' : 'var(--danger)'};">${Math.round(t.score)}</div>
                            </div>
                            ${t.aiConviction ? `
                            <div style="font-size: 0.75rem; font-weight: 700; color: ${t.score >= 65 ? 'var(--secondary)' : t.score >= 40 ? 'var(--accent)' : 'var(--danger)'};">${t.score >= 65 ? 'PROCEED ✅' : t.score >= 40 ? 'CAUTION ⚠️' : 'AVOID 🚫'}</div>` : ''}
                        </div>
                    </div>

                    <!-- Entry -->
                    <div class="form-section">
                        <div class="form-section-title">Entry</div>
                        <div class="form-row">
                            <div class="form-group">
                                <span class="form-label">Strike Price</span>
                                <input class="form-input" value="$${t.strike}" readonly style="color: var(--primary-light);">
                            </div>
                            <div class="form-group">
                                <span class="form-label">Expiry</span>
                                <input class="form-input" value="${t.expiry} (${t.daysLeft}d)" readonly>
                            </div>
                        </div>
                        <div style="display:grid; grid-template-columns:1fr 1fr; gap:0.5rem; margin-top:0.5rem;">
                            <div class="form-group">
                                <span class="form-label">Limit Price (Mid)</span>
                                <div class="input-with-adjust">
                                    <button class="adjust-btn" onclick="tradeModal.adjustPrice(-0.05)">−</button>
                                    <input class="form-input" value="$${t.limitPrice.toFixed(2)}" id="modal-limit-price" readonly>
                                    <button class="adjust-btn" onclick="tradeModal.adjustPrice(0.05)">+</button>
                                </div>
                            </div>
                            <div class="form-group">
                                <span class="form-label">Qty</span>
                                <div class="input-with-adjust">
                                    <button class="adjust-btn" onclick="tradeModal.adjustQty(-1)">−</button>
                                    <input class="form-input" value="${t.qty}" id="modal-qty" readonly>
                                    <button class="adjust-btn" onclick="tradeModal.adjustQty(1)">+</button>
                                </div>
                            </div>
                        </div>
                    </div>

                    <!-- Bracket Orders -->
                    <div class="form-section">
                        <div class="form-section-title">Bracket Orders (Auto-Attached)</div>
                        <div style="display:grid; grid-template-columns:1fr 1fr; gap:0.5rem;">
                            <div class="form-group">
                                <span class="form-label">Stop Loss (-${(t.slPercent * 100).toFixed(0)}%)</span>
                                <div class="input-with-adjust">
                                    <button class="adjust-btn" onclick="tradeModal.adjustSL(-0.05)">−</button>
                                    <input class="form-input" value="$${slPrice.toFixed(2)}" style="color: var(--danger);" readonly>
                                    <button class="adjust-btn" onclick="tradeModal.adjustSL(0.05)">+</button>
                                </div>
                            </div>
                            <div class="form-group">
                                <span class="form-label">Take Profit (+${(t.tpPercent * 100).toFixed(0)}%)</span>
                                <div class="input-with-adjust">
                                    <button class="adjust-btn" onclick="tradeModal.adjustTP(-0.05)">−</button>
                                    <input class="form-input" value="$${tpPrice.toFixed(2)}" style="color: var(--secondary);" readonly>
                                    <button class="adjust-btn" onclick="tradeModal.adjustTP(0.05)">+</button>
                                </div>
                            </div>
                        </div>
                    </div>

                    <!-- Risk Analysis -->
                    <div class="risk-summary">
                        <div class="risk-summary-title">Risk Analysis</div>
                        <div class="risk-row">
                            <span class="risk-label">Total Cost</span>
                            <span class="risk-value">$${totalCost.toFixed(2)} (${t.qty} × $${t.limitPrice.toFixed(2)} × 100)</span>
                        </div>
                        <div class="risk-row">
                            <span class="risk-label">Max Loss (if SL hits)</span>
                            <span class="risk-value danger">-$${maxLoss.toFixed(2)} (${accountPct}% of account)</span>
                        </div>
                        <div class="risk-row">
                            <span class="risk-label">Target Profit</span>
                            <span class="risk-value success">+$${targetProfit.toFixed(2)} (+${(t.tpPercent * 100).toFixed(0)}%)</span>
                        </div>
                        <div class="risk-row">
                            <span class="risk-label">Risk : Reward</span>
                            <span class="risk-value ${parseFloat(riskReward) >= 1.5 ? 'success' : 'warning'}">1 : ${riskReward} ${parseFloat(riskReward) >= 1.5 ? '✅' : '⚠️'}</span>
                        </div>
                        <div class="risk-row">
                            <span class="risk-label">Portfolio Heat After</span>
                            <span class="risk-value ${heatAfter <= mockAccount.heatLimit ? 'warning' : 'danger'}">${heatAfter}% → ${heatStatus}</span>
                        </div>
                    </div>

                    <!-- Pre-Trade Checks -->
                    <div class="checks-list">
                        ${checks.map(c => `
                            <div class="check-item">
                                <span class="check-icon">${c.pass ? '✅' : '❌'}</span>
                                <span>${c.text}</span>
                            </div>
                        `).join('')}
                    </div>

                    <!-- Confirm -->
                    <div class="confirm-section">
                        <div class="confirm-warning">⚠️ YOU ARE ABOUT TO SPEND $${totalCost.toFixed(2)}<br>Max Risk: $${maxLoss.toFixed(2)}</div>
                        <button class="confirm-btn" onclick="tradeModal.confirm()">
                            ✅ CONFIRM TRADE — ${actionText} ${t.qty}x ${t.ticker}
                        </button>
                        <div class="confirm-hint">Enter to Confirm | Esc to Cancel</div>
                    </div>
                </div>
            </div>
        `;

        document.getElementById('trade-modal-overlay').innerHTML = html;
    }

    function adjustPrice(delta) {
        if (!currentTrade) return;
        currentTrade.limitPrice = Math.max(0.05, +(currentTrade.limitPrice + delta).toFixed(2));
        renderModal();
    }

    function adjustQty(delta) {
        if (!currentTrade) return;
        currentTrade.qty = Math.max(1, Math.min(10, currentTrade.qty + delta));
        renderModal();
    }

    function adjustSL(delta) {
        if (!currentTrade) return;
        const newSL = +(currentTrade.limitPrice * (1 - currentTrade.slPercent) + delta).toFixed(2);
        if (newSL > 0 && newSL < currentTrade.limitPrice) {
            currentTrade.slPercent = +((1 - newSL / currentTrade.limitPrice)).toFixed(4);
            renderModal();
        }
    }

    function adjustTP(delta) {
        if (!currentTrade) return;
        const newTP = +(currentTrade.limitPrice * (1 + currentTrade.tpPercent) + delta).toFixed(2);
        if (newTP > currentTrade.limitPrice) {
            currentTrade.tpPercent = +((newTP / currentTrade.limitPrice - 1)).toFixed(4);
            renderModal();
        }
    }

    function confirm() {
        if (!currentTrade) return;
        const t = currentTrade;
        const isCall = t.type === 'CALL';
        const actionText = isCall ? 'BUY CALL' : 'BUY PUT';

        close();

        // Add to mock portfolio
        if (typeof portfolio !== 'undefined') {
            portfolio.addPosition({
                ticker: t.ticker,
                type: t.type,
                strike: t.strike,
                entry: t.limitPrice,
                current: t.limitPrice,
                sl: +(t.limitPrice * (1 - t.slPercent)).toFixed(2),
                tp: +(t.limitPrice * (1 + t.tpPercent)).toFixed(2)
            });
        }

        // Show toast notifications
        showTradeToast('success', '✅',
            `<span class="toast-bold">Order Submitted!</span><br>${actionText} ${t.qty}x ${t.ticker} $${t.strike} @ $${t.limitPrice.toFixed(2)} — Brackets attached`);

        setTimeout(() => {
            showTradeToast('info', '📋',
                `<span class="toast-bold">Brackets Active</span><br>SL: $${(t.limitPrice * (1 - t.slPercent)).toFixed(2)} | TP: $${(t.limitPrice * (1 + t.tpPercent)).toFixed(2)} — Monitoring started`);
        }, 1500);
    }

    function showTradeToast(type, icon, html) {
        // Use existing toast system if available
        if (typeof toast !== 'undefined' && toast.success) {
            if (type === 'success') toast.success(html.replace(/<[^>]*>/g, ''));
            else if (type === 'info') toast.info ? toast.info(html.replace(/<[^>]*>/g, '')) : toast.success(html.replace(/<[^>]*>/g, ''));
            return;
        }

        // Fallback toast
        let container = document.getElementById('toast-container');
        if (!container) {
            container = document.createElement('div');
            container.id = 'toast-container';
            container.className = 'toast-container';
            document.body.appendChild(container);
        }
        const toastEl = document.createElement('div');
        toastEl.className = `toast ${type}`;
        toastEl.innerHTML = `<span>${icon}</span><span>${html}</span>`;
        container.appendChild(toastEl);
        setTimeout(() => toastEl.remove(), 5000);
    }

    // Keyboard shortcuts
    document.addEventListener('keydown', (e) => {
        const modal = document.getElementById('trade-modal-overlay');
        if (!modal || !modal.classList.contains('show')) return;

        if (e.key === 'Escape') close();
        if (e.key === 'Enter') confirm();
    });

    return {
        open,
        close,
        confirm,
        adjustPrice,
        adjustQty,
        adjustSL,
        adjustTP
    };
})();
