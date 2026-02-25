/**
 * Trade Modal Component
 * Feature: automated-trading
 * 
 * Handles the trade setup modal: opening, closing, risk calculations,
 * price/qty adjustments, pre-trade checks, and trade confirmation.
 * Phase 4: Wired to paperApi.placeTrade() for live order placement.
 */

const tradeModal = (() => {
    // Live account state (fetched from API when modal opens)
    let accountState = {
        value: 0,
        cash: 0,
        openPositions: 0,
        maxPositions: 5,
        dailyLossUsed: 0,
        dailyLossLimit: 150,
        heatPercent: 0,
        heatLimit: 6.0,
        holdings: []
    };

    let currentTrade = null;

    /**
     * Fetch live account state from the API
     */
    async function _refreshAccountState() {
        try {
            if (typeof paperApi !== 'undefined') {
                const [statsRes, tradesRes] = await Promise.all([
                    paperApi.getStats(),
                    paperApi.getTrades('OPEN'),
                ]);
                if (statsRes && statsRes.success && statsRes.stats) {
                    const s = statsRes.stats;
                    accountState.value = s.portfolio_value || 0;
                    accountState.cash = s.cash_available || 0;
                    accountState.openPositions = s.open_positions || 0;
                    accountState.maxPositions = s.max_positions || 5;
                }
                if (tradesRes && tradesRes.success && tradesRes.trades) {
                    accountState.holdings = tradesRes.trades.map(t => t.ticker);
                }
            }
        } catch (e) {
            console.warn('[trade-modal] Failed to fetch account state:', e);
        }
    }

    /**
 * Open the trade modal with data from a scan result card
 * @param {Object} data - Card data: ticker, price, strike, expiry, daysLeft, premium, type, score, badges
 */
    async function open(data) {
        currentTrade = {
            ...data,
            limitPrice: data.premium,
            qty: 1,
            slPercent: 0.25,
            tpPercent: 0.50
        };

        const modal = document.getElementById('trade-modal-overlay');
        if (!modal) return;

        // ── CREDENTIAL GATE (Issue 3) ──
        // Check if user has broker credentials before allowing trade
        let hasCredentials = false;
        try {
            if (typeof paperApi !== 'undefined') {
                const settingsRes = await paperApi.getSettings();
                if (settingsRes && settingsRes.settings) {
                    hasCredentials = !!settingsRes.settings.has_sandbox_token;
                }
            }
        } catch (e) {
            console.warn('[trade-modal] Failed to check credentials:', e);
        }

        if (!hasCredentials) {
            // Show Setup Broker panel instead of trade form
            _renderCredentialGate(modal, data);
            modal.classList.add('show');
            return;
        }

        // Credentials found — proceed with normal trade flow
        await _refreshAccountState();
        renderModal();
        modal.classList.add('show');
    }

    /**
     * Render the "Setup Broker" panel when credentials are missing
     */
    function _renderCredentialGate(modal, pendingTradeData) {
        modal.innerHTML = `
        <div class="trade-modal" style="max-width: 480px;">
            <div class="modal-header-trade" style="background: linear-gradient(135deg, #f59e0b 0%, #d97706 100%);">
                <h2>🔑 Setup Broker Credentials</h2>
                <button class="modal-close-trade" onclick="tradeModal.close()">×</button>
            </div>
            <div class="modal-body-trade">
                <div style="background: rgba(245,158,11,0.1); padding: 0.75rem 1rem; border-radius: 8px; border-left: 3px solid #f59e0b; margin-bottom: 1.25rem; font-size: 0.85rem; line-height: 1.5;">
                    ⚠️ You need to configure your Tradier API credentials before placing trades. Enter your sandbox API token and Account ID below.
                </div>

                <div style="display: grid; gap: 0.75rem; margin-bottom: 1rem;">
                    <div>
                        <label style="font-size: 0.8rem; color: var(--text-secondary); display: block; margin-bottom: 0.25rem;">Tradier API Token</label>
                        <input type="password" id="cred-gate-token" placeholder="Enter your Tradier sandbox token"
                               style="width: 100%; padding: 0.5rem; border-radius: 6px; border: 1px solid rgba(255,255,255,0.15); background: var(--bg-card); color: var(--text-primary); font-size: 0.85rem; box-sizing: border-box;">
                    </div>
                    <div>
                        <label style="font-size: 0.8rem; color: var(--text-secondary); display: block; margin-bottom: 0.25rem;">Account ID</label>
                        <input type="text" id="cred-gate-account" placeholder="Enter your Account ID"
                               style="width: 100%; padding: 0.5rem; border-radius: 6px; border: 1px solid rgba(255,255,255,0.15); background: var(--bg-card); color: var(--text-primary); font-size: 0.85rem; box-sizing: border-box;">
                    </div>
                </div>

                <div id="cred-gate-status" style="font-size: 0.8rem; color: var(--text-secondary); min-height: 1.2rem; margin-bottom: 0.75rem;"></div>

                <div style="display: flex; gap: 0.75rem;">
                    <button onclick="tradeModal.close()" 
                            style="flex: 1; padding: 0.6rem; border-radius: 8px; border: 1px solid var(--border); background: var(--bg-card); color: var(--text-light); cursor: pointer; font-size: 0.9rem;">
                        Cancel
                    </button>
                    <button id="cred-gate-save-btn" onclick="tradeModal._saveCredentialsAndProceed()"
                            style="flex: 2; padding: 0.6rem; border-radius: 8px; border: none; background: linear-gradient(135deg, #f59e0b, #d97706); color: white; cursor: pointer; font-size: 0.9rem; font-weight: 600;">
                        🔌 Test & Save Credentials
                    </button>
                </div>
            </div>
        </div>
    `;

        // Store pending trade data for after credential save
        modal._pendingTradeData = pendingTradeData;
    }

    /**
     * Save credentials from the gate panel, test connection, and proceed to trade
     */
    async function _saveCredentialsAndProceed() {
        const token = document.getElementById('cred-gate-token')?.value?.trim();
        const accountId = document.getElementById('cred-gate-account')?.value?.trim();
        const statusEl = document.getElementById('cred-gate-status');
        const saveBtn = document.getElementById('cred-gate-save-btn');

        if (!token || !accountId) {
            if (statusEl) statusEl.innerHTML = '<span style="color: var(--danger);">❌ Both fields are required</span>';
            return;
        }

        // Show saving state
        if (saveBtn) {
            saveBtn.disabled = true;
            saveBtn.innerHTML = '⏳ Testing connection...';
            saveBtn.style.opacity = '0.7';
        }

        try {
            if (typeof paperApi !== 'undefined') {
                // Save credentials
                await paperApi.updateSettings({
                    tradier_sandbox_token: token,
                    tradier_account_id: accountId
                });

                // Test connection
                const testRes = await paperApi.testConnection();
                if (testRes && testRes.success) {
                    if (statusEl) statusEl.innerHTML = '<span style="color: var(--secondary);">✅ Connected! Opening trade...</span>';

                    // Brief delay for UX, then proceed to trade
                    setTimeout(async () => {
                        const modal = document.getElementById('trade-modal-overlay');
                        const pendingData = modal?._pendingTradeData;
                        if (pendingData) {
                            // Re-open with credentials now saved
                            await open(pendingData);
                        }
                    }, 800);
                } else {
                    if (statusEl) statusEl.innerHTML = `<span style="color: var(--danger);">❌ Connection failed: ${testRes?.error || 'Unknown error'}</span>`;
                    if (saveBtn) {
                        saveBtn.disabled = false;
                        saveBtn.innerHTML = '🔌 Test & Save Credentials';
                        saveBtn.style.opacity = '1';
                    }
                }
            }
        } catch (err) {
            console.error('[trade-modal] Credential save failed:', err);
            if (statusEl) statusEl.innerHTML = `<span style="color: var(--danger);">❌ Error: ${err.message}</span>`;
            if (saveBtn) {
                saveBtn.disabled = false;
                saveBtn.innerHTML = '🔌 Test & Save Credentials';
                saveBtn.style.opacity = '1';
            }
        }
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
        const accountPct = accountState.value > 0 ? ((maxLoss / accountState.value) * 100).toFixed(1) : '0.0';
        const heatAfter = accountState.value > 0 ? +(accountState.heatPercent + (totalCost / accountState.value) * 100).toFixed(1) : 0;
        const heatStatus = heatAfter <= accountState.heatLimit ? `within ${accountState.heatLimit}% limit` : `OVER ${accountState.heatLimit}% limit!`;

        // Pre-trade checks
        const checks = [
            { pass: accountState.cash >= totalCost, text: `Buying power sufficient ($${accountState.cash.toLocaleString(undefined, { maximumFractionDigits: 0 })} available)` },
            { pass: true, text: 'Bid-Ask spread: check on broker' },
            { pass: true, text: 'Open Interest: check on broker' },
            { pass: t.daysLeft > 5 || !t.hasEarnings, text: t.hasEarnings ? `⚠️ Earnings within ${t.daysLeft}d` : 'No earnings within 5 days' },
            { pass: accountState.dailyLossUsed + maxLoss <= accountState.dailyLossLimit, text: `Daily loss limit: $${accountState.dailyLossUsed} used of $${accountState.dailyLossLimit}` },
            { pass: !accountState.holdings.includes(t.ticker), text: `No duplicate position for ${t.ticker}` }
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
                            <span class="risk-value ${heatAfter <= accountState.heatLimit ? 'warning' : 'danger'}">${heatAfter}% → ${heatStatus}</span>
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
        const slPrice = +(t.limitPrice * (1 - t.slPercent)).toFixed(2);
        const tpPrice = +(t.limitPrice * (1 + t.tpPercent)).toFixed(2);

        close();

        // Build trade payload with full scanner context
        const tradeData = {
            ticker: t.ticker,
            option_type: t.type,
            strike: t.strike,
            expiry: t.expiry,
            entry_price: t.limitPrice,
            qty: t.qty,
            direction: 'BUY',
            sl_price: slPrice,
            tp_price: tpPrice,
            strategy: t.strategy || 'SCANNER',
            card_score: t.cardScore || t.score,
            ai_score: t.aiScore,
            ai_verdict: t.aiVerdict,
            gate_verdict: t.gateVerdict,
            technical_score: t.technicalScore,
            sentiment_score: t.sentimentScore,
            delta_at_entry: t.delta,
            iv_at_entry: t.iv,
            idempotency_key: `${t.ticker}-${t.strike}-${t.expiry}-${Date.now()}`,
        };

        // Show immediate feedback
        showTradeToast('info', '⏳',
            `<span class="toast-bold">Submitting...</span><br>${actionText} ${t.qty}x ${t.ticker} $${t.strike} @ $${t.limitPrice.toFixed(2)}`);

        // Call live API (Phase 4)
        if (typeof paperApi !== 'undefined') {
            // Immediately add pending row to portfolio view
            if (typeof portfolio !== 'undefined' && portfolio.addPendingPosition) {
                portfolio.addPendingPosition({
                    ticker: t.ticker,
                    type: t.type,
                    strike: t.strike,
                    entry: t.limitPrice,
                    current: t.limitPrice,
                    sl: slPrice,
                    tp: tpPrice,
                    qty: t.qty
                });
            }

            paperApi.placeTrade(tradeData).then(res => {
                if (res.success) {
                    showTradeToast('success', '✅',
                        `<span class="toast-bold">Order Placed!</span><br>${actionText} ${t.qty}x ${t.ticker} $${t.strike} @ $${t.limitPrice.toFixed(2)}`);

                    // Show bracket confirmation
                    setTimeout(() => {
                        const brokerMsg = res.trade?.broker_msg;
                        showTradeToast('info', '📋',
                            `<span class="toast-bold">Brackets Active</span><br>SL: $${slPrice.toFixed(2)} | TP: $${tpPrice.toFixed(2)}${brokerMsg ? '<br>' + brokerMsg : ''}`);
                    }, 1500);

                    // Soft-refresh portfolio data from server (don't wipe pending row)
                    if (typeof portfolio !== 'undefined' && portfolio.refresh) {
                        setTimeout(() => portfolio.refresh(), 2000);
                    }
                }
            }).catch(err => {
                showTradeToast('error', '❌',
                    `<span class="toast-bold">Trade Failed</span><br>${err.message || 'Unknown error'}`);
            });
        } else {
            // Fallback: mock portfolio (dev mode)
            if (typeof portfolio !== 'undefined' && portfolio.addPosition) {
                portfolio.addPosition({
                    ticker: t.ticker, type: t.type, strike: t.strike,
                    entry: t.limitPrice, current: t.limitPrice,
                    sl: slPrice, tp: tpPrice
                });
            }
            showTradeToast('success', '✅',
                `<span class="toast-bold">Order Submitted (Mock)</span><br>${actionText} ${t.qty}x ${t.ticker} $${t.strike}`);
        }
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
        adjustTP,
        _saveCredentialsAndProceed
    };
})();
