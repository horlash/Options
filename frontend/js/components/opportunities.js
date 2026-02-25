// Opportunities component — Dual-Gate Trade System
const opportunities = {
    currentResults: [],
    currentFilter: 'all',
    currentProfitFilter: 15, // Default >15% (User Requested Lower Barrier)
    // AI cache is now shared via window.aiCache (ai-cache.js)

    init() {
        // Initialize profit filter buttons
        document.querySelectorAll('.btn-filter').forEach(btn => {
            const value = parseInt(btn.dataset.value);

            // Set active class if it matches default
            if (value === this.currentProfitFilter) {
                btn.classList.add('active');
            }

            btn.addEventListener('click', (e) => {
                // Remove active class from all
                document.querySelectorAll('.btn-filter').forEach(b => b.classList.remove('active'));
                // Add to clicked
                e.target.classList.add('active');

                this.setProfitFilter(value);
            });
        });
    },

    render(results) {
        console.log(`[RENDER] Called with ${results ? results.length : 0} ticker results`);
        this.currentResults = results;
        this.updateTickerFilter(results);
        const container = document.getElementById('opportunities-container');
        if (!container) return;

        // --- EMPTY STATE (no scan results) ---
        if (!results || results.length === 0) {
            container.innerHTML = `
                <div class="empty-state" style="margin-bottom: 2rem;">
                    <div class="empty-state-icon">🔍</div>
                    <p>No active scan results. Run a scan to discover opportunities.</p>
                </div>
            `;
            this.updateCount(0);
            return;
        }

        // --- REAL MODE ---
        let total = 0;
        let finalHtml = '';

        // 1. Flatten
        const allOpportunities = [];
        results.forEach(result => {
            // Pass fundamental data to children
            let fundData = result.fundamental_analysis;

            // [FIX] Map Backend Badges to Frontend Structure
            if (result.badges && result.badges.length > 0) {
                if (!fundData) fundData = {};
                if (!fundData.badges) fundData.badges = [];
                // Avoid duplicates
                result.badges.forEach(b => {
                    if (!fundData.badges.includes(b)) fundData.badges.push(b);
                });
            }

            if (result.opportunities && result.opportunities.length > 0) {
                result.opportunities.forEach(opp => {
                    // Hydrate
                    if (!opp.fundamental_analysis && fundData) {
                        opp.fundamental_analysis = fundData;
                    }

                    // Add parent metadata if missing
                    if (!opp.ticker) opp.ticker = result.ticker;
                    if (!opp.current_price) opp.current_price = result.current_price;

                    allOpportunities.push(opp);
                });
            }
        });

        // 2. Filter & Sort
        let filtered = allOpportunities;
        console.log(`[RENDER] Total opportunities before filter: ${allOpportunities.length}`);

        // Ticker Filter
        if (this.currentFilter !== 'all') {
            filtered = filtered.filter(opp => opp.ticker === this.currentFilter);
            console.log(`[RENDER] After ticker filter: ${filtered.length}`);
        }

        // Profit Filter - Apply to ALL play types
        console.log(`[RENDER] Applying profit filter: >=${this.currentProfitFilter}%`);
        filtered = filtered.filter(opp => {
            const passes = opp.profit_potential >= this.currentProfitFilter;
            if (!passes) console.log(`[RENDER] Filtered out: ${opp.contract_name} (${opp.profit_potential}%)`);
            return passes;
        });
        console.log(`[RENDER] After profit filter: ${filtered.length}`);

        // Sort (Score by default)
        // Sort based on current criteria
        if (this.currentSort === 'profit') {
            filtered.sort((a, b) => b.profit_potential - a.profit_potential);
            console.log('[RENDER] Sorted by Profit Potential');
        } else if (this.currentSort === 'expiry') {
            filtered.sort((a, b) => new Date(a.expiration_date) - new Date(b.expiration_date));
            console.log('[RENDER] Sorted by Expiry');
        } else {
            // Default: Score
            filtered.sort((a, b) => b.opportunity_score - a.opportunity_score);
            console.log('[RENDER] Sorted by Score (Default)');
        }

        // Store filtered for click handlers
        this._currentFiltered = filtered;

        // 3. Render
        if (filtered.length === 0) {
            container.innerHTML = `<div class="empty-state"><p>No results match filters.</p></div>`;
        } else {
            container.innerHTML = filtered.map((opp, index) => this.createCard(opp, index)).join('');

            // Add Click Listeners for Details Modal
            container.querySelectorAll('.opportunity-card').forEach(card => {
                card.addEventListener('click', (e) => {
                    // Don't open detail if trade button was clicked
                    if (e.target.closest('.trade-btn')) return;

                    const index = card.dataset.index;
                    const opp = filtered[index];

                    if (opp && analysisDetail) {
                        console.log(`[UI] Card clicked for ${opp.ticker} (Context: ${opp.strike_price} ${opp.option_type})`);
                        analysisDetail.show(opp.ticker, opp);
                    }
                });
            });

            // Dual-Gate Trade button handlers
            container.querySelectorAll('.trade-btn:not(.trade-btn-disabled)').forEach(btn => {
                btn.addEventListener('click', (e) => {
                    e.stopPropagation();
                    const idx = btn.dataset.tradeIndex;
                    const opp = filtered[idx];
                    if (opp) {
                        this._handleTradeClick(opp, idx, btn);
                    }
                });
            });
        }

        this.updateCount(filtered.length);
        console.log(`[RENDER] Final display count: ${filtered.length}`);
    },

    // --- DUAL-GATE: AI Auto-Trigger on Trade Click ---
    async _handleTradeClick(opp, idx, btnElement) {
        const cacheKey = aiCache.buildKey(opp.ticker, opp.strike_price, opp.option_type, opp.expiration_date);

        // Check shared cache first (may have been populated by Reasoning Engine)
        const cachedResult = aiCache.get(cacheKey);
        if (cachedResult) {
            console.log(`[TRADE] Using shared cached AI result for ${cacheKey}`);
            this._processAIResult(opp, cachedResult);
            return;
        }

        // Show spinner on the button
        const originalHtml = btnElement.innerHTML;
        btnElement.innerHTML = '🧠 Running AI Analysis...';
        btnElement.disabled = true;
        btnElement.style.opacity = '0.7';

        try {
            // Determine strategy from current scan mode
            let strategy = 'LEAP';
            if (typeof scanner !== 'undefined') {
                if (scanner.scanMode === '0dte') strategy = '0DTE';
                else if (scanner.scanMode && scanner.scanMode.startsWith('weekly')) strategy = 'WEEKLY';
            }

            const payload = {
                strategy: strategy,
                ticker: opp.ticker,
                strike: opp.strike_price,
                type: opp.option_type,
                expiry: opp.expiration_date
            };

            console.log(`[TRADE] Calling AI for ${opp.ticker} ${opp.strike_price} ${opp.option_type}`, payload);

            const response = await fetch(`/api/analysis/ai/${opp.ticker}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            const data = await response.json();

            if (data.success && data.ai_analysis) {
                // Store in shared cache
                aiCache.set(cacheKey, data.ai_analysis);
                this._processAIResult(opp, data.ai_analysis);
            } else {
                // AI failed — show error, restore button
                btnElement.innerHTML = '❌ AI Failed — Retry';
                btnElement.disabled = false;
                btnElement.style.opacity = '1';
                console.error('[TRADE] AI analysis failed:', data.error);
            }
        } catch (err) {
            console.error('[TRADE] Network error:', err);
            btnElement.innerHTML = '❌ Network Error — Retry';
            btnElement.disabled = false;
            btnElement.style.opacity = '1';
        }
    },

    // --- DUAL-GATE: Process AI Result (Gate 2) ---
    _processAIResult(opp, aiResult) {
        const aiScore = aiResult.score || 0;
        const aiVerdict = aiResult.verdict || 'UNKNOWN';
        const aiAnalysis = aiResult.analysis || '';

        console.log(`[TRADE] Gate 2: AI Score=${aiScore}, Verdict=${aiVerdict}`);

        const dateObj = new Date(opp.expiration_date);
        const expiryStr = dateObj.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric', timeZone: 'UTC' });

        if (aiScore >= 65) {
            // ✅ GATE 2 PASSED — High conviction, open trade modal
            console.log(`[TRADE] ✅ Gate 2 PASSED (${aiScore} >= 65). Opening trade modal.`);
            if (typeof tradeModal !== 'undefined') {
                // Determine strategy from current scan mode
                let strategy = 'LEAP';
                if (typeof scanner !== 'undefined') {
                    if (scanner.scanMode === '0dte') strategy = '0DTE';
                    else if (scanner.scanMode && scanner.scanMode.startsWith('weekly')) strategy = 'WEEKLY';
                }
                tradeModal.open({
                    ticker: opp.ticker,
                    price: opp.current_price,
                    strike: opp.strike_price.toFixed(0),
                    expiry: expiryStr,
                    daysLeft: opp.days_to_expiry,
                    premium: opp.premium,
                    type: opp.option_type === 'Call' ? 'CALL' : 'PUT',
                    score: aiScore,
                    aiVerdict: aiVerdict,
                    aiScore: aiScore,
                    aiConviction: aiScore,
                    cardScore: opp.opportunity_score,
                    hasEarnings: opp.has_earnings_risk || false,
                    badges: opp.play_type || '',
                    strategy: strategy,
                    // Pass scanner context for DB persistence
                    delta: opp.greeks?.delta || 0,
                    iv: opp.greeks?.iv || opp.implied_volatility || 0,
                    technicalScore: opp.technical_score || 0,
                    sentimentScore: opp.sentiment_score || 0,
                    gateVerdict: aiScore >= 65 ? 'GO' : 'CAUTION'
                });
            }
        } else if (aiScore >= 40) {
            // ⚠️ Moderate — open modal with caution warning
            console.log(`[TRADE] ⚠️ Gate 2 CAUTION (${aiScore} 40-64). Opening modal with warning.`);
            if (typeof tradeModal !== 'undefined') {
                // Determine strategy from current scan mode
                let strategy = 'LEAP';
                if (typeof scanner !== 'undefined') {
                    if (scanner.scanMode === '0dte') strategy = '0DTE';
                    else if (scanner.scanMode && scanner.scanMode.startsWith('weekly')) strategy = 'WEEKLY';
                }
                tradeModal.open({
                    ticker: opp.ticker,
                    price: opp.current_price,
                    strike: opp.strike_price.toFixed(0),
                    expiry: expiryStr,
                    daysLeft: opp.days_to_expiry,
                    premium: opp.premium,
                    type: opp.option_type === 'Call' ? 'CALL' : 'PUT',
                    score: aiScore,
                    aiVerdict: aiVerdict,
                    aiScore: aiScore,
                    aiConviction: aiScore,
                    cardScore: opp.opportunity_score,
                    hasEarnings: opp.has_earnings_risk || false,
                    badges: opp.play_type || '',
                    aiWarning: `⚠️ Moderate AI Conviction (${aiScore}/100) — Proceed with caution`,
                    strategy: strategy,
                    // Pass scanner context for DB persistence
                    delta: opp.greeks?.delta || 0,
                    iv: opp.greeks?.iv || opp.implied_volatility || 0,
                    technicalScore: opp.technical_score || 0,
                    sentimentScore: opp.sentiment_score || 0,
                    gateVerdict: 'CAUTION'
                });
            }
        } else {
            // 🚫 GATE 2 BLOCKED — AI recommends avoid
            console.log(`[TRADE] 🚫 Gate 2 BLOCKED (${aiScore} < 40). Showing avoid warning.`);
            this._showAIAvoidWarning(opp, aiResult);
        }

        // Update the trade button to reflect AI result
        this._updateTradeButtonAfterAI(opp, aiScore, aiVerdict);
    },

    // Show AI AVOID warning overlay
    _showAIAvoidWarning(opp, aiResult) {
        const overlay = document.getElementById('trade-modal-overlay');
        if (!overlay) return;

        const score = aiResult.score || 0;
        const verdict = aiResult.verdict || 'AVOID';
        // Extract a short summary from the analysis (first 200 chars)
        const summary = (aiResult.analysis || 'No analysis available').substring(0, 300);

        overlay.innerHTML = `
            <div class="trade-modal" style="max-width: 500px;">
                <div class="modal-header-trade" style="background: linear-gradient(135deg, #dc2626 0%, #991b1b 100%);">
                    <h2>🚫 AI Recommends AVOID</h2>
                    <button class="modal-close-trade" onclick="document.getElementById('trade-modal-overlay').classList.remove('show')">×</button>
                </div>
                <div class="modal-body-trade">
                    <div style="text-align: center; padding: 1rem 0;">
                        <div style="font-size: 3rem; font-weight: 900; color: var(--danger);">${score}</div>
                        <div style="color: var(--text-muted); font-size: 0.9rem;">AI Conviction Score</div>
                        <div style="margin-top: 0.5rem; color: var(--danger); font-weight: 700;">${verdict}</div>
                    </div>
                    <div style="background: rgba(255,77,77,0.08); padding: 1rem; border-radius: var(--radius-sm); border-left: 3px solid var(--danger); margin: 1rem 0; font-size: 0.9rem; line-height: 1.5;">
                        ${summary}...
                    </div>
                    <div style="display: flex; gap: 0.75rem; margin-top: 1.5rem;">
                        <button onclick="document.getElementById('trade-modal-overlay').classList.remove('show')" 
                                style="flex: 1; padding: 0.75rem; border-radius: var(--radius-sm); border: 1px solid var(--border); background: var(--bg-card); color: var(--text-light); cursor: pointer; font-size: 0.95rem;">
                            ← Back to Scan
                        </button>
                        <button onclick="opportunities._forceTradeOverride('${opp.ticker}', ${opp.strike_price}, '${opp.option_type}', '${opp.expiration_date}')" 
                                style="flex: 1; padding: 0.75rem; border-radius: var(--radius-sm); border: 1px solid var(--danger); background: transparent; color: var(--danger); cursor: pointer; font-size: 0.95rem;">
                            ⚠️ Override & Trade Anyway
                        </button>
                    </div>
                </div>
            </div>
        `;
        overlay.classList.add('show');
    },

    // Force override when AI says AVOID
    _forceTradeOverride(ticker, strike, optType, expiry) {
        const overlay = document.getElementById('trade-modal-overlay');
        if (overlay) overlay.classList.remove('show');

        // Find the matching opportunity
        const opp = (this._currentFiltered || []).find(o =>
            o.ticker === ticker &&
            o.strike_price === strike &&
            o.option_type === optType
        );
        if (!opp) return;

        const cacheKey = aiCache.buildKey(ticker, strike, optType, expiry);
        const aiResult = aiCache.get(cacheKey) || {};

        const dateObj = new Date(opp.expiration_date);
        const expiryStr = dateObj.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric', timeZone: 'UTC' });

        if (typeof tradeModal !== 'undefined') {
            tradeModal.open({
                ticker: opp.ticker,
                price: opp.current_price,
                strike: opp.strike_price.toFixed(0),
                expiry: expiryStr,
                daysLeft: opp.days_to_expiry,
                premium: opp.premium,
                type: opp.option_type === 'Call' ? 'CALL' : 'PUT',
                score: aiResult.score || 0,
                aiVerdict: aiResult.verdict || 'AVOID',
                aiConviction: aiResult.score || 0,
                cardScore: opp.opportunity_score,
                hasEarnings: opp.has_earnings_risk || false,
                badges: opp.play_type || '',
                aiWarning: `🚫 OVERRIDE: AI scored ${aiResult.score || 0}/100 — High risk trade`
            });
        }
    },

    // Update trade button visual after AI completes
    _updateTradeButtonAfterAI(opp, aiScore, aiVerdict) {
        // Find the card and update its button
        const cards = document.querySelectorAll('.opportunity-card');
        cards.forEach(card => {
            const idx = card.dataset.index;
            const filtered = this._currentFiltered || [];
            const cardOpp = filtered[idx];
            if (!cardOpp || cardOpp.ticker !== opp.ticker || cardOpp.strike_price !== opp.strike_price) return;

            const btnContainer = card.querySelector('[style*="padding: 0 1.25rem 0.75rem"]');
            if (!btnContainer) return;

            const isCall = opp.option_type === 'Call';
            const btnClass = isCall ? 'trade-btn-call' : 'trade-btn-put';

            if (aiScore >= 65) {
                btnContainer.innerHTML = `
                    <button class="trade-btn ${btnClass}" data-trade-index="${idx}">
                        ✅ Trade — AI Score ${aiScore}
                    </button>
                    <div class="edge-gate-label" style="color: var(--secondary);">AI: ${aiVerdict} (${aiScore}/100) — Dual Gate ✅</div>
                `;
            } else if (aiScore >= 40) {
                btnContainer.innerHTML = `
                    <button class="trade-btn ${btnClass}" data-trade-index="${idx}" style="opacity: 0.85;">
                        ⚠️ Trade — AI Score ${aiScore}
                    </button>
                    <div class="edge-gate-label" style="color: var(--accent);">AI: ${aiVerdict} (${aiScore}/100) — Moderate</div>
                `;
            } else {
                btnContainer.innerHTML = `
                    <button class="trade-btn trade-btn-disabled" style="background: rgba(220,38,38,0.15); border-color: var(--danger); color: var(--danger);" data-trade-index="${idx}">
                        🚫 AI: AVOID (${aiScore}/100)
                    </button>
                    <div class="edge-gate-label" style="color: var(--danger);">AI recommends against this trade</div>
                `;
            }

            // Re-attach click handler
            const newBtn = btnContainer.querySelector('.trade-btn');
            if (newBtn && !newBtn.classList.contains('trade-btn-disabled')) {
                newBtn.addEventListener('click', (e) => {
                    e.stopPropagation();
                    this._handleTradeClick(opp, idx, newBtn);
                });
            }
        });
    },

    setProfitFilter(value) {
        this.currentProfitFilter = parseInt(value);
        console.log(`[PROFIT FILTER] Set to ${value}%, currentResults.length: ${this.currentResults.length}`);

        // Update UI label (defensive - don't fail if element missing)
        try {
            const labelEl = document.getElementById('profit-filter-value');
            if (labelEl) {
                labelEl.textContent = value + '%';
            }
        } catch (e) {
            console.warn('[PROFIT FILTER] Could not update label element:', e);
        }

        // Always call render, even if label update failed
        console.log('[PROFIT FILTER] Calling render...');
        this.render(this.currentResults);
        console.log('[PROFIT FILTER] Render complete');
    },

    updateTickerFilter(results) {
        const select = document.getElementById('ticker-filter');
        if (!select) return;

        // Preserve current selection
        const currentSelection = select.value;

        // Clear existing (except "All")
        select.innerHTML = '<option value="all">All Tickers</option>';

        const tickers = new Set();
        results.forEach(r => tickers.add(r.ticker));

        tickers.forEach(t => {
            const option = document.createElement('option');
            option.value = t;
            option.textContent = t;
            select.appendChild(option);
        });

        // Restore selection if valid
        if (tickers.has(currentSelection)) {
            select.value = currentSelection;
        }
    },

    setFilter(ticker) {
        this.currentFilter = ticker;
        this.render(this.currentResults);
    },

    createCard(opp, index) {
        // --- REDESIGN: BOLD & DISTINCT ---
        const isCall = opp.option_type === 'Call';
        const cardClass = isCall ? 'card-call' : 'card-put';
        const textClass = isCall ? 'text-call' : 'text-put';
        const actionText = isCall ? 'BUY CALL' : 'BUY PUT';

        const dateObj = new Date(opp.expiration_date);
        // Fix: Force UTC display to avoid timezone shift (e.g. Thu instead of Fri)
        const expiryDate = dateObj.toLocaleDateString('en-US', {
            month: 'short',
            day: 'numeric',
            year: 'numeric',
            timeZone: 'UTC'
        });

        // Source Logic
        let source = opp.data_source;
        if (!source || source === 'Unknown' || source === 'Market Data' || source === 'Data: Composite') {
            source = '';
        }

        // Break Even Fallback Calculation
        let breakEven = opp.break_even;
        if (!breakEven) {
            breakEven = isCall
                ? (opp.strike_price + opp.premium)
                : (opp.strike_price - opp.premium);
        }

        // Main Badges (Mutually Exclusive)
        let badgesHtml = '';
        if (opp.play_type === 'tactical') badgesHtml += `<span class="badge badge-tactical">⚡ Tactical</span>`;
        if (opp.play_type === 'momentum') badgesHtml += `<span class="badge badge-momentum">🚀 Momentum</span>`;
        if (opp.play_type === 'value') badgesHtml += `<span class="badge badge-value">💎 Value</span>`;
        if (opp.has_earnings_risk) badgesHtml += `<span class="badge badge-earnings">⚠️ Earn</span>`;

        // Additive Fundamental Badges (Full Text) — deduplicate vs play_type
        let fundBadgesHtml = '';
        if (opp.fundamental_analysis && opp.fundamental_analysis.badges) {
            opp.fundamental_analysis.badges.forEach(b => {
                // Skip badges that duplicate the play_type (e.g. "Momentum" when play_type is already "momentum")
                if (opp.play_type && b.toLowerCase() === opp.play_type.toLowerCase()) return;
                fundBadgesHtml += `<span class="badge-fund">${b}</span>`;
            });
        }

        return `
            <div class="opportunity-card ${cardClass}" data-ticker="${opp.ticker}" data-index="${index}">
                
                <!-- HEADER: Color Coded -->
                <div class="card-header">
                    <div style="display:flex; align-items:baseline;">
                        <span class="ticker-symbol">${opp.ticker}</span>
                        <span class="price-display">$${opp.current_price ? opp.current_price.toFixed(2) : '-.--'}</span>
                    </div>
                    <span class="score-badge-large">${opp.opportunity_score.toFixed(0)}</span>
                </div>

                <!-- BODY: Hero Action -->
                <div class="card-body">
                    <div class="hero-action">
                        <span class="action-type">${actionText}</span>
                        <div class="action-text ${textClass}">
                            $${opp.strike_price.toFixed(0)}
                        </div>
                        <div class="profit-pill">
                            +${opp.profit_potential.toFixed(0)}% Potential
                        </div>
                    </div>

                    <!-- METRICS GRID -->
                    <div class="metrics-grid">
                        <div class="metric-row">
                            <span class="m-label">Expiry</span>
                            <span class="m-value">${expiryDate}</span>
                        </div>
                        <div class="metric-row">
                            <span class="m-label">Days Left</span>
                            <span class="m-value">${opp.days_to_expiry}d</span>
                        </div>
                        <div class="metric-row">
                            <span class="m-label">Premium</span>
                            <span class="m-value">$${opp.premium.toFixed(2)}</span>
                        </div>
                        <div class="metric-row">
                            <span class="m-label">Break Even</span>
                            <span class="m-value">$${breakEven ? breakEven.toFixed(2) : '-'}</span>
                        </div>
                    </div>
                </div>

                <!-- FOOTER: Badges & Source -->
                <div class="card-footer">
                    <div style="display:flex; flex-direction:column; width:100%;">
                        <div class="badge-container">
                            ${badgesHtml}
                        </div>
                        <!-- NEW: Fundamental Badges Row -->
                        <div class="fund-badges-container">
                            ${fundBadgesHtml}
                        </div>
                        <span class="source-text">${source}</span>
                    </div>
                </div>

                <!-- TRADE BUTTON (Gate 1: Card Score) -->
                <div style="padding: 0 1.25rem 0.75rem;">
                    ${this._renderTradeButton(opp, index)}
                </div>
            </div>
        `;
    },

    // --- GATE 1: Card Score Threshold (≥40 to enable) ---
    _renderTradeButton(opp, index) {
        const score = opp.opportunity_score;
        const isCall = opp.option_type === 'Call';
        const btnClass = isCall ? 'trade-btn-call' : 'trade-btn-put';

        // Check if we have a cached AI result
        const cacheKey = aiCache.buildKey(opp.ticker, opp.strike_price, opp.option_type, opp.expiration_date);
        const cached = aiCache.get(cacheKey);

        if (cached) {
            // Already have AI result — show final state
            const aiScore = cached.score || 0;
            const aiVerdict = cached.verdict || 'UNKNOWN';
            if (aiScore >= 65) {
                return `
                    <button class="trade-btn ${btnClass}" data-trade-index="${index}">
                        ✅ Trade — AI Score ${aiScore}
                    </button>
                    <div class="edge-gate-label" style="color: var(--secondary);">AI: ${aiVerdict} (${aiScore}/100) — Dual Gate ✅</div>
                `;
            } else if (aiScore >= 40) {
                return `
                    <button class="trade-btn ${btnClass}" data-trade-index="${index}" style="opacity: 0.85;">
                        ⚠️ Trade — AI Score ${aiScore}
                    </button>
                    <div class="edge-gate-label" style="color: var(--accent);">AI: ${aiVerdict} (${aiScore}/100) — Moderate</div>
                `;
            } else {
                return `
                    <button class="trade-btn trade-btn-disabled" style="background: rgba(220,38,38,0.15); border-color: var(--danger); color: var(--danger);" data-trade-index="${index}">
                        🚫 AI: AVOID (${aiScore}/100)
                    </button>
                    <div class="edge-gate-label" style="color: var(--danger);">AI recommends against this trade</div>
                `;
            }
        }

        // No AI result yet — Gate 1 check
        if (score >= 40) {
            return `
                <button class="trade-btn ${btnClass}" data-trade-index="${index}">
                    ⚡ Trade — Run AI Check
                </button>
                <div class="edge-gate-label">Card Score ${score.toFixed(0)} — Click to run AI analysis</div>
            `;
        } else {
            return `
                <button class="trade-btn trade-btn-disabled" disabled>
                    🔒 Trade Locked — Weak Setup
                </button>
                <div class="edge-gate-label" style="color: var(--text-muted);">Card Score ${score.toFixed(0)} — Below 40 threshold</div>
            `;
        }
    },

    updateCount(count) {
        const el = document.getElementById('opportunities-count');
        if (el) el.textContent = count;
    },

    sort(criteria) {
        this.currentSort = criteria;
        this.render(this.currentResults);
    }
};

