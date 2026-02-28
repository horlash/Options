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
                    // Don't open detail if a button was clicked
                    if (e.target.closest('.trade-btn') || e.target.closest('.analyze-btn')) return;

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

            // Analyze button handlers — open analysis detail
            container.querySelectorAll('.analyze-btn').forEach(btn => {
                btn.addEventListener('click', (e) => {
                    e.stopPropagation();
                    const idx = btn.dataset.analyzeIndex;
                    const opp = filtered[idx];
                    if (opp && typeof analysisDetail !== 'undefined') {
                        console.log(`[UI] Analyze clicked for ${opp.ticker}`);
                        analysisDetail.show(opp.ticker, opp);
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
                // AI failed — show error modal
                console.error('[TRADE] AI analysis failed:', data.error);
                this._showAISummary(opp, { error: data.error || 'AI analysis returned no result' });
                btnElement.innerHTML = '❌ AI Failed — Retry';
                btnElement.disabled = false;
                btnElement.style.opacity = '1';
            }
        } catch (err) {
            console.error('[TRADE] Network error:', err);
            this._showAISummary(opp, { error: `Network error: ${err.message || 'Connection failed'}` });
            btnElement.innerHTML = '❌ Network Error — Retry';
            btnElement.disabled = false;
            btnElement.style.opacity = '1';
        }
    },

    // --- DUAL-GATE: Process AI Result (Gate 2) ---
    _processAIResult(opp, aiResult) {
        const aiScore = aiResult.score || 0;
        const aiVerdict = aiResult.verdict || 'UNKNOWN';

        console.log(`[TRADE] Gate 2: AI Score=${aiScore}, Verdict=${aiVerdict}`);

        // Always show AI summary screen — user decides to proceed or not
        this._showAISummary(opp, aiResult);

        // Update the trade button to reflect AI result
        this._updateTradeButtonAfterAI(opp, aiScore, aiVerdict);
    },

    // Unified AI Summary Screen — shown for ALL results (safe, risky, avoid)
    _showAISummary(opp, aiResult) {
        const overlay = document.getElementById('trade-modal-overlay');
        if (!overlay) return;

        const score = aiResult.score || 0;
        const rawVerdict = aiResult.verdict || 'UNKNOWN';
        // Map backend verdicts to user-friendly labels
        const verdictMap = {'SAFE': 'FAVORABLE', 'FAVORABLE': 'FAVORABLE', 'RISKY': 'RISKY', 'AVOID': 'AVOID'};
        const verdict = verdictMap[rawVerdict] || rawVerdict;
        const summary = aiResult.summary || '';
        const risks = aiResult.risks || [];
        const thesis = aiResult.thesis || '';
        const isError = !!aiResult.error;

        let scoreColor, headerGradient, bgGlow;
        if (isError) {
            scoreColor = '#6b7280'; headerGradient = 'linear-gradient(135deg, #374151 0%, #1f2937 100%)'; bgGlow = 'rgba(107,114,128,0.1)';
        } else if (score >= 66) {
            scoreColor = '#22c55e'; headerGradient = 'linear-gradient(135deg, #16a34a 0%, #15803d 100%)'; bgGlow = 'rgba(34,197,94,0.1)';
        } else if (score >= 41) {
            scoreColor = '#f59e0b'; headerGradient = 'linear-gradient(135deg, #d97706 0%, #b45309 100%)'; bgGlow = 'rgba(245,158,11,0.1)';
        } else {
            scoreColor = '#ef4444'; headerGradient = 'linear-gradient(135deg, #dc2626 0%, #991b1b 100%)'; bgGlow = 'rgba(239,68,68,0.1)';
        }

        const risksHtml = risks.length > 0 ? risks.map(r => `<div style="display:flex;gap:0.5rem;align-items:flex-start;margin-bottom:0.4rem;"><span style="color:${scoreColor};flex-shrink:0;">⚠</span><span>${r}</span></div>`).join('') : '';

        if (isError) {
            overlay.innerHTML = `
                <div class="trade-modal" style="max-width: 480px;">
                    <div class="modal-header-trade" style="background: ${headerGradient};">
                        <h2>❌ No Analysis Available</h2>
                        <button class="modal-close-trade" onclick="document.getElementById('trade-modal-overlay').classList.remove('show')">×</button>
                    </div>
                    <div class="modal-body-trade" style="text-align:center;padding:2rem 1.5rem;">
                        <div style="font-size:3rem;margin-bottom:1rem;">🔌</div>
                        <div style="color:var(--text-light);font-size:1.1rem;font-weight:600;margin-bottom:0.75rem;">AI Analysis Failed</div>
                        <div style="background:rgba(107,114,128,0.1);padding:1rem;border-radius:var(--radius-sm);border-left:3px solid #6b7280;color:var(--text-muted);font-size:0.85rem;line-height:1.5;text-align:left;">
                            ${aiResult.error || 'Unknown error'}
                        </div>
                        <button onclick="document.getElementById('trade-modal-overlay').classList.remove('show')" style="margin-top:1.5rem;padding:0.75rem 2rem;border-radius:var(--radius-sm);border:1px solid var(--border);background:var(--bg-card);color:var(--text-light);cursor:pointer;font-size:0.95rem;">← Back</button>
                    </div>
                </div>`;
            overlay.classList.add('show');
            return;
        }

        overlay.innerHTML = `
            <div class="trade-modal" style="max-width: 520px;">
                <div class="modal-header-trade" style="background: ${headerGradient};">
                    <h2>${opp.ticker} ${opp.option_type} $${opp.strike_price.toFixed(2)} — AI Analysis</h2>
                    <button class="modal-close-trade" onclick="document.getElementById('trade-modal-overlay').classList.remove('show')">×</button>
                </div>
                <div class="modal-body-trade" style="padding:1.5rem;">
                    <div style="text-align:center;margin-bottom:1.25rem;">
                        <div style="display:inline-flex;align-items:center;justify-content:center;width:80px;height:80px;border-radius:50%;border:3px solid ${scoreColor};background:${bgGlow};font-size:2rem;font-weight:900;color:${scoreColor};">${score}</div>
                        <div style="margin-top:0.5rem;font-weight:700;color:${scoreColor};font-size:1.1rem;">${verdict}</div>
                        <div style="color:var(--text-muted);font-size:0.8rem;">AI Conviction Score</div>
                    </div>
                    ${thesis ? `<div style="background:${bgGlow};padding:0.85rem 1rem;border-radius:var(--radius-sm);border-left:3px solid ${scoreColor};margin-bottom:1rem;font-size:0.9rem;line-height:1.5;color:var(--text-light);"><strong>Thesis:</strong> ${thesis}</div>` : ''}
                    ${summary ? `<div style="color:var(--text-muted);font-size:0.88rem;line-height:1.6;margin-bottom:1rem;">${summary}</div>` : ''}
                    ${risksHtml ? `<div style="margin-bottom:1rem;"><div style="font-weight:600;color:var(--text-light);font-size:0.85rem;margin-bottom:0.5rem;">Key Risks:</div><div style="font-size:0.85rem;color:var(--text-muted);line-height:1.5;">${risksHtml}</div></div>` : ''}
                    <div style="display:flex;gap:0.75rem;margin-top:1.5rem;">
                        <button onclick="document.getElementById('trade-modal-overlay').classList.remove('show')" style="flex:1;padding:0.75rem;border-radius:var(--radius-sm);border:1px solid var(--border);background:var(--bg-card);color:var(--text-light);cursor:pointer;font-size:0.95rem;font-weight:500;">← Back</button>
                        <button onclick="opportunities._proceedToTrade('${opp.ticker}', ${opp.strike_price}, '${opp.option_type}', '${opp.expiration_date}')" style="flex:1;padding:0.75rem;border-radius:var(--radius-sm);border:none;background:${score >= 41 ? scoreColor : 'rgba(239,68,68,0.2)'};color:#fff;cursor:pointer;font-size:0.95rem;font-weight:700;${score < 41 ? 'color:var(--danger);border:1px solid var(--danger);' : ''}">${score >= 66 ? '✅ Proceed to Trade' : score >= 41 ? '⚠️ Proceed with Caution' : '⚠️ Override & Trade'}</button>
                    </div>
                </div>
            </div>`;
        overlay.classList.add('show');
    },

    // Open trade modal from the AI summary screen
    _proceedToTrade(ticker, strike, optType, expiry) {
        const overlay = document.getElementById('trade-modal-overlay');
        if (overlay) overlay.classList.remove('show');

        const opp = (this._currentFiltered || []).find(o => o.ticker === ticker && o.strike_price === strike && o.option_type === optType);
        if (!opp) return;

        const cacheKey = aiCache.buildKey(ticker, strike, optType, expiry);
        const aiResult = aiCache.get(cacheKey) || {};
        const dateObj = new Date(opp.expiration_date);
        const expiryStr = dateObj.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric', timeZone: 'UTC' });

        let strategy = 'LEAP';
        if (typeof scanner !== 'undefined') {
            if (scanner.scanMode === '0dte') strategy = '0DTE';
            else if (scanner.scanMode && scanner.scanMode.startsWith('weekly')) strategy = 'WEEKLY';
        }

        if (typeof tradeModal !== 'undefined') {
            tradeModal.open({
                ticker: opp.ticker, price: opp.current_price,
                strike: opp.strike_price.toFixed(2), expiry: expiryStr,
                daysLeft: opp.days_to_expiry, premium: opp.premium,
                type: opp.option_type === 'Call' ? 'CALL' : 'PUT',
                score: aiResult.score || 0, aiVerdict: aiResult.verdict || 'UNKNOWN',
                aiScore: aiResult.score || 0, aiConviction: aiResult.score || 0,
                cardScore: opp.opportunity_score, hasEarnings: opp.has_earnings_risk || false,
                badges: opp.play_type || '', strategy: strategy,
                delta: opp.greeks?.delta || 0, iv: opp.greeks?.iv || opp.implied_volatility || 0,
                technicalScore: opp.technical_score || 0, sentimentScore: opp.sentiment_score || 0,
                gateVerdict: (aiResult.score || 0) >= 66 ? 'GO' : 'CAUTION',
                aiWarning: (aiResult.score || 0) < 41 ? `🚫 OVERRIDE: AI scored ${aiResult.score || 0}/100 — High risk` : undefined
            });
        }
    },

    // Update trade button visual after AI completes
    _updateTradeButtonAfterAI(opp, aiScore, aiVerdict) {
        const cards = document.querySelectorAll('.opportunity-card');
        cards.forEach(card => {
            const idx = card.dataset.index;
            const filtered = this._currentFiltered || [];
            const cardOpp = filtered[idx];
            if (!cardOpp || cardOpp.ticker !== opp.ticker || cardOpp.strike_price !== opp.strike_price) return;

            const btnContainer = card.querySelector('.card-trade-area');
            if (!btnContainer) {
                console.warn('[AI Badge] Could not find .card-trade-area for card', idx);
                return;
            }

            const isCall = opp.option_type === 'Call';
            const btnClass = isCall ? 'trade-btn-call' : 'trade-btn-put';
            const analyzeBtn = `<button class="action-btn analyze-btn" data-analyze-index="${idx}">🔍 Analyze</button>`;

            if (aiScore >= 66) {
                btnContainer.innerHTML = `
                    <div class="card-actions">${analyzeBtn}<button class="action-btn trade-btn ${btnClass}" data-trade-index="${idx}">✅ Trade ${aiScore}</button></div>
                    <div class="edge-gate-label" style="color: var(--secondary);">AI: FAVORABLE (${aiScore}/100) — Dual Gate ✅</div>`;
            } else if (aiScore >= 41) {
                btnContainer.innerHTML = `
                    <div class="card-actions">${analyzeBtn}<button class="action-btn trade-btn ${btnClass}" data-trade-index="${idx}" style="opacity: 0.85;">⚠️ Trade ${aiScore}</button></div>
                    <div class="edge-gate-label" style="color: var(--accent);">AI: RISKY (${aiScore}/100) — Proceed with Caution</div>`;
            } else {
                btnContainer.innerHTML = `
                    <div class="card-actions">${analyzeBtn}<button class="action-btn trade-btn trade-btn-disabled" style="background: rgba(220,38,38,0.15); border-color: var(--danger); color: var(--danger);" data-trade-index="${idx}">🚫 AVOID ${aiScore}</button></div>
                    <div class="edge-gate-label" style="color: var(--danger);">AI recommends against this trade</div>`;
            }

            // Re-attach click handlers
            const newTradeBtn = btnContainer.querySelector('.trade-btn:not(.trade-btn-disabled)');
            if (newTradeBtn) {
                newTradeBtn.addEventListener('click', (e) => { e.stopPropagation(); this._handleTradeClick(opp, idx, newTradeBtn); });
            }
            const newAnalyzeBtn = btnContainer.querySelector('.analyze-btn');
            if (newAnalyzeBtn) {
                newAnalyzeBtn.addEventListener('click', (e) => { e.stopPropagation(); if (typeof analysisDetail !== 'undefined') analysisDetail.show(opp.ticker, opp); });
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

        // Scan-type badge based on current scanner mode
        let scanBadgeHtml = '';
        if (typeof scanner !== 'undefined') {
            if (scanner.scanMode === 'leaps') {
                scanBadgeHtml = '<span class="scan-type-badge badge-leap">LEAP</span>';
            } else if (scanner.scanMode === '0dte') {
                scanBadgeHtml = '<span class="scan-type-badge badge-0dte">0DTE</span>';
            } else {
                scanBadgeHtml = '<span class="scan-type-badge badge-weekly">Weekly</span>';
            }
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

        // Trading Systems collapsible section
        const tsCount = opp.trading_systems ? Object.keys(opp.trading_systems).length : 0;
        const tsScore = opp.technical_score || 0;
        let tradingSystemsHtml = '';
        if (tsCount > 0) {
            const tsId = `ts-${index}`;
            let tsPillsHtml = '';
            for (const [name, data] of Object.entries(opp.trading_systems || {})) {
                const signal = data.signal || data;
                const pillColor = signal === 'BUY' ? 'var(--secondary)' : signal === 'SELL' ? 'var(--danger)' : 'var(--text-muted)';
                tsPillsHtml += `<span style="display:inline-block;padding:2px 8px;margin:2px 4px 2px 0;border-radius:4px;font-size:0.7rem;font-weight:600;background:rgba(255,255,255,0.05);border:1px solid ${pillColor};color:${pillColor};">${name}: ${signal}</span>`;
            }
            tradingSystemsHtml = `
                <div class="trading-systems-toggle" onclick="this.classList.toggle('expanded');this.nextElementSibling.classList.toggle('show');">
                    <span class="ts-header">Trading Systems</span>
                    <span class="ts-summary">${tsCount} Systems · Score: ${tsScore}/100</span>
                    <span class="ts-chevron">▶</span>
                </div>
                <div class="trading-systems-content" id="${tsId}">
                    ${tsPillsHtml}
                </div>
            `;
        }

        return `
            <div class="opportunity-card ${cardClass}" data-ticker="${opp.ticker}" data-index="${index}">
                
                <!-- HEADER: Color Coded -->
                <div class="card-header">
                    <div style="display:flex; align-items:baseline;">
                        <span class="ticker-symbol">${opp.ticker}</span>
                        <span class="price-display">$${opp.current_price ? opp.current_price.toFixed(2) : '-.--'}</span>
                        ${scanBadgeHtml}
                    </div>
                    <span class="score-badge-large ${opp.opportunity_score >= 66 ? 'score-high' : opp.opportunity_score >= 41 ? 'score-mid' : 'score-low'}">${opp.opportunity_score.toFixed(0)}<span class="score-out-of">/100</span></span>
                </div>

                <!-- BODY: Hero Action -->
                <div class="card-body">
                    <div class="hero-action">
                        <span class="action-type">${actionText}</span>
                        <div class="action-text ${textClass}">
                            $${opp.strike_price.toFixed(2)}
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
                            <span class="m-label">Premium</span>
                            <span class="m-value">$${opp.premium.toFixed(2)}</span>
                        </div>
                        <div class="metric-row">
                            <span class="m-label">Break Even</span>
                            <span class="m-value">$${breakEven ? breakEven.toFixed(2) : '-'}</span>
                        </div>
                        <div class="metric-row">
                            <span class="m-label">Days Left</span>
                            <span class="m-value">${opp.days_to_expiry} day${opp.days_to_expiry !== 1 ? 's' : ''}</span>
                        </div>
                        <div class="metric-row">
                            <span class="m-label">Volume</span>
                            <span class="m-value">${(opp.volume || 0).toLocaleString()}</span>
                        </div>
                        <div class="metric-row">
                            <span class="m-label">Open Int</span>
                            <span class="m-value">${(opp.open_interest || 0).toLocaleString()}</span>
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

                <!-- TRADING SYSTEMS (collapsible) -->
                ${tradingSystemsHtml}

                <!-- TRADE BUTTON (Gate 1: Card Score) -->
                <div class="card-trade-area" style="padding: 0 1.25rem 0.75rem;">
                    ${this._renderTradeButton(opp, index)}
                </div>
            </div>
        `;
    },

    // --- GATE 1: Card Score Threshold (≥41 to enable) ---
    _renderTradeButton(opp, index) {
        const score = opp.opportunity_score;
        const isCall = opp.option_type === 'Call';
        const btnClass = isCall ? 'trade-btn-call' : 'trade-btn-put';
        const analyzeBtn = `<button class="action-btn analyze-btn" data-analyze-index="${index}">🔍 Analyze</button>`;

        // Check if we have a cached AI result
        const cacheKey = aiCache.buildKey(opp.ticker, opp.strike_price, opp.option_type, opp.expiration_date);
        const cached = aiCache.get(cacheKey);

        if (cached) {
            const aiScore = cached.score || 0;
            const aiVerdict = cached.verdict || 'UNKNOWN';
            if (aiScore >= 66) {
                return `
                    <div class="card-actions">
                        ${analyzeBtn}
                        <button class="action-btn trade-btn ${btnClass}" data-trade-index="${index}">
                            ✅ Trade ${aiScore}
                        </button>
                    </div>
                    <div class="edge-gate-label" style="color: var(--secondary);">AI: FAVORABLE (${aiScore}/100) — Dual Gate ✅</div>
                `;
            } else if (aiScore >= 41) {
                return `
                    <div class="card-actions">
                        ${analyzeBtn}
                        <button class="action-btn trade-btn ${btnClass}" data-trade-index="${index}" style="opacity: 0.85;">
                            ⚠️ Trade ${aiScore}
                        </button>
                    </div>
                    <div class="edge-gate-label" style="color: var(--accent);">AI: RISKY (${aiScore}/100) — Proceed with Caution</div>
                `;
            } else {
                return `
                    <div class="card-actions">
                        ${analyzeBtn}
                        <button class="action-btn trade-btn trade-btn-disabled" style="background: rgba(220,38,38,0.15); border-color: var(--danger); color: var(--danger);" data-trade-index="${index}">
                            🚫 AVOID ${aiScore}
                        </button>
                    </div>
                    <div class="edge-gate-label" style="color: var(--danger);">AI recommends against this trade</div>
                `;
            }
        }

        // No AI result yet — Gate 1 check
        if (score >= 41) {
            return `
                <div class="card-actions">
                    ${analyzeBtn}
                    <button class="action-btn trade-btn ${btnClass}" data-trade-index="${index}">
                        ⚡ Trade
                    </button>
                </div>
                <div class="edge-gate-label">Card Score ${score.toFixed(0)}/100 — Click Trade to run AI check</div>
            `;
        } else {
            return `
                <div class="card-actions">
                    ${analyzeBtn}
                    <button class="action-btn trade-btn trade-btn-disabled" disabled>
                        🔒 Locked
                    </button>
                </div>
                <div class="edge-gate-label" style="color: var(--text-muted);">Card Score ${score.toFixed(0)}/100 — Below 41 threshold</div>
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
