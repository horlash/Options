// Opportunities component
const opportunities = {
    currentResults: [],
    currentFilter: 'all',
    currentProfitFilter: 15, // Default >15% (User Requested Lower Barrier)

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

        // --- DEMO MODE TRIGGER (Empty State) ---
        if (!results || results.length === 0) {
            const demoOpp = {
                ticker: "NVDA",
                current_price: 726.13,
                option_type: "Call",
                strike_price: 700.00,
                expiration_date: "2025-01-17T00:00:00",
                premium: 45.20,
                days_to_expiry: 340,
                open_interest: 15400,
                implied_volatility: 0.42,
                opportunity_score: 94,
                data_source: "Schwab",
                play_type: "tactical",
                profit_potential: 85,
                break_even: 745.20,
                has_earnings_risk: false,
                // Additive Badges Demo
                fundamental_analysis: { badges: ["Smart Money 🏦", "EPS Growth ↗", "Analyst Buy ⭐"] }
            };

            container.innerHTML = `
                <div class="empty-state" style="margin-bottom: 2rem;">
                    <div class="empty-state-icon">🔍</div>
                    <p>No active scan results. Showing a <strong>Demo Card</strong> below:</p>
                </div>
                ${this.createCard(demoOpp)}
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

        // 3. Render
        if (filtered.length === 0) {
            container.innerHTML = `<div class="empty-state"><p>No results match filters.</p></div>`;
        } else {
            container.innerHTML = filtered.map((opp, index) => this.createCard(opp, index)).join('');

            // Add Click Listeners for Details Modal
            container.querySelectorAll('.opportunity-card').forEach(card => {
                card.addEventListener('click', () => {
                    const index = card.dataset.index;
                    const opp = filtered[index];

                    if (opp && analysisDetail) {
                        console.log(`[UI] Card clicked for ${opp.ticker} (Context: ${opp.strike_price} ${opp.option_type})`);
                        analysisDetail.show(opp.ticker, opp);
                    }
                });
            });
        }

        this.updateCount(filtered.length);
        console.log(`[RENDER] Final display count: ${filtered.length}`);
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

        // Additive Fundamental Badges (Full Text)
        let fundBadgesHtml = '';
        if (opp.fundamental_analysis && opp.fundamental_analysis.badges) {
            opp.fundamental_analysis.badges.forEach(b => {
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
            </div>
        `;
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
