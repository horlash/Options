// Analysis Detail Modal
window.analysisDetail = {
    async show(ticker, context = null) {
        const modal = document.getElementById('analysis-modal');
        const detailContainer = document.getElementById('analysis-detail');

        modal.classList.remove('hidden');
        detailContainer.innerHTML = '<p class="text-center">Loading analysis...</p>';

        // Store the specific trade context (e.g., 335 Call)
        this.selectedTradeContext = context;
        if (context) {
            console.log(`[AnalysisDetail] Context stored: ${context.strike_price} ${context.option_type}`);
        } else {
            console.log("[AnalysisDetail] No context passed (Generic Ticker Mode)");
        }

        try {
            const expiry = context ? context.expiration_date : null;
            const result = await api.getAnalysis(ticker, expiry);

            if (result.success) {
                this.render(result.analysis);
            } else {
                detailContainer.innerHTML = '<p class="text-center">Failed to load analysis</p>';
            }
        } catch (error) {
            console.error('Error loading analysis:', error);
            detailContainer.innerHTML = '<p class="text-center">Error loading analysis</p>';
        }
    },

    hide() {
        const modal = document.getElementById('analysis-modal');
        modal.classList.add('hidden');
        this.selectedTradeContext = null; // Clear context on close
    },

    render(analysis) {
        if (!analysis) return;
        this.currentAnalysisReport = analysis; // Store full report (Renamed for clarity)

        const detailContainer = document.getElementById('analysis-detail');

        const indicators = analysis.indicators;
        const sentiment = analysis.sentiment_analysis;

        detailContainer.innerHTML = `
            <h2 style="margin-bottom: 0.5rem; font-size: 2rem;">${analysis.ticker} - Detailed Analysis</h2>
            ${this.selectedTradeContext ?
                `<p style="margin-bottom: 2rem; color: var(--accent); font-size: 1.1rem; font-weight: bold;">
                    Target: ${this.selectedTradeContext.option_type} $${this.selectedTradeContext.strike_price} (Exp: ${new Date(this.selectedTradeContext.expiration_date).toLocaleDateString('en-US', { timeZone: 'UTC' })})
                 </p>`
                : '<div style="margin-bottom: 2rem;"></div>'}
            
            <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 1.5rem; margin-bottom: 2rem;">
                <div class="metric">
                    <span class="metric-label">Current Price</span>
                    <span class="metric-value">$${analysis.current_price.toFixed(2)}</span>
                </div>
                <div class="metric">
                    <span class="metric-label">Technical Score</span>
                    <span class="metric-value">${analysis.technical_score.toFixed(0)}/100</span>
                </div>
                <div class="metric">
                    <span class="metric-label">Sentiment Score</span>
                    <span class="metric-value">${analysis.sentiment_score.toFixed(0)}/100</span>
                </div>
            </div>
            
            <h3 style="margin: 2rem 0 1rem; font-size: 1.5rem;">Technical Indicators</h3>
            <div style="background: var(--bg-card); padding: 1.5rem; border-radius: var(--radius-md); margin-bottom: 2rem;">
                <div style="display: grid; gap: 1rem;">
                    <div>
                        <strong>RSI:</strong> ${indicators.rsi.value?.toFixed(2) || 'N/A'} 
                        <span style="color: ${this.getSignalColor(indicators.rsi.signal)}">(${indicators.rsi.signal})</span>
                    </div>
                    <div>
                        <strong>MACD:</strong> 
                        <span style="color: ${this.getSignalColor(indicators.macd.signal)}">(${indicators.macd.signal})</span>
                    </div>
                    <div>
                        <strong>Bollinger Bands:</strong> 
                        <span style="color: ${this.getSignalColor(indicators.bollinger_bands.signal)}">(${indicators.bollinger_bands.signal})</span>
                    </div>
                    <div>
                        <strong>Moving Averages:</strong> 
                        <span style="color: ${this.getSignalColor(indicators.moving_averages.signal)}">(${indicators.moving_averages.signal})</span>
                    </div>
                    <div>
                        <strong>Volume:</strong> 
                        <span style="color: ${this.getSignalColor(indicators.volume.signal)}">(${indicators.volume.signal})</span>
                    </div>
                </div>
            </div>
            
            <h3 style="margin: 2rem 0 1rem; font-size: 1.5rem;">News Sentiment</h3>
            <div style="background: var(--bg-card); padding: 1.5rem; border-radius: var(--radius-md); margin-bottom: 2rem;">
                <p><strong>Articles Analyzed:</strong> ${sentiment.article_count}</p>
                ${sentiment.positive_count !== undefined ?
                `<p><strong>Positive:</strong> ${sentiment.positive_count} | 
                   <strong>Negative:</strong> ${sentiment.negative_count} | 
                   <strong>Neutral:</strong> ${sentiment.neutral_count}</p>`
                : ''}
                <p><strong>Overall Sentiment:</strong> ${sentiment.weighted_score.toFixed(2)}</p>
            </div>
            
            <div id="ai-analysis-section">
                <div style="display: flex; justify-content: space-between; align-items: center; margin: 2rem 0 1rem;">
                    <h3 style="margin: 0; font-size: 1.5rem;">AI Reasoning</h3>
                    <button onclick="analysisDetail.runAIAnalysis('${analysis.ticker}')" 
                            style="background: var(--accent); color: white; border: none; padding: 0.5rem 1rem; border-radius: var(--radius-sm); cursor: pointer; font-size: 0.875rem;">
                        ⚡ Run Reasoning Engine
                    </button>
                </div>
                <div id="ai-result-container" style="background: var(--bg-card); padding: 1.5rem; border-radius: var(--radius-md); border: 1px dashed var(--border);">
                    <p style="color: var(--text-muted); text-align: center;">Click to generate a deep-dive risk analysis using the Senior Risk Manager persona.</p>
                </div>
            </div>

            <h3 style="margin: 2rem 0 1rem; font-size: 1.5rem;">Top LEAP Opportunities</h3>
            <div style="display: grid; gap: 1rem;">
                ${analysis.opportunities.slice(0, 5).map(opp => `
                    <div style="background: var(--bg-card); padding: 1rem; border-radius: var(--radius-sm);">
                        <div style="display: flex; justify-content: space-between; margin-bottom: 0.5rem;">
                            <strong>${opp.option_type} $${opp.strike_price.toFixed(2)}</strong>
                            <span style="color: var(--secondary);">+${opp.profit_potential.toFixed(0)}%</span>
                        </div>
                        <p style="font-size: 0.875rem; color: var(--text-muted);">
                            Exp: ${new Date(opp.expiration_date).toLocaleDateString()} | 
                            Premium: $${opp.premium.toFixed(2)} | 
                            Score: ${opp.opportunity_score.toFixed(0)}/100 |
                            Strat: ${opp.strategy || 'N/A'}
                        </p>
                    </div>
                `).join('')}
            </div>
        `;
    },

    async runAIAnalysis(ticker, forceRefresh = false) {
        const container = document.getElementById('ai-result-container');

        // Build cache key from trade context
        let cacheKey = null;
        if (this.selectedTradeContext) {
            cacheKey = aiCache.buildKey(
                ticker,
                this.selectedTradeContext.strike_price,
                this.selectedTradeContext.option_type,
                this.selectedTradeContext.expiration_date
            );

            // Check shared cache (skip if force-refreshing)
            if (!forceRefresh && cacheKey) {
                const cached = aiCache.get(cacheKey);
                if (cached) {
                    console.log(`[AI-DETAIL] Using shared cached result for ${cacheKey}`);
                    this.renderAIResult(cached, ticker);
                    return;
                }
            }
        }

        container.innerHTML = `
            <div class="text-center">
                <p style="color: var(--accent);">🧠 Reasoning Engine Active...</p>
                <p style="font-size: 0.875rem; color: var(--text-muted);">Analyzing macro conditions, news, and volatility...</p>
            </div>
        `;

        try {
            // Determine strategy from current scan mode
            let strategy = 'LEAP';
            if (scanner.scanMode === '0dte') {
                strategy = '0DTE';
            } else if (scanner.scanMode.startsWith('weekly')) {
                strategy = 'WEEKLY';
            }

            const payload = {
                strategy: strategy,
                ticker: ticker
            };

            // Use the specific trade context if we have it (from clicking a card)
            if (this.selectedTradeContext) {
                console.log("[AI] Using specific trade context:", this.selectedTradeContext);
                payload.expiry = this.selectedTradeContext.expiration_date;
                payload.strike = this.selectedTradeContext.strike_price;
                payload.type = this.selectedTradeContext.option_type;
            } else {
                console.log("[AI] Using generic ticker context (no specific trade selected)");
            }

            const response = await fetch(`/api/analysis/ai/${ticker}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            const data = await response.json();

            if (data.success && data.ai_analysis) {
                // Store in shared cache
                if (cacheKey) {
                    aiCache.set(cacheKey, data.ai_analysis);
                }
                this.renderAIResult(data.ai_analysis, ticker);
            } else {
                container.innerHTML = `<p class="text-danger">Analysis Failed: ${data.error || 'Unknown error'}</p>`;
            }
        } catch (e) {
            console.error(e);
            container.innerHTML = `<p class="text-danger">Network Error</p>`;
        }
    },

    renderAIResult(analysis, ticker) {
        const container = document.getElementById('ai-result-container');
        const verdictColor = analysis.verdict === 'SAFE' ? 'var(--secondary)' : 'var(--danger)';

        // Enhanced Markdown Parsing
        const formatText = (text) => {
            if (!text) return '';
            let formatted = text
                // Bold
                .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
                // Bullet points (simple dash or asterisk at start of line)
                .replace(/^[\*\-]\s+(.*)$/gm, '<li>$1</li>')
                // Newlines to breaks (but avoid double breaks if we wrapped in li)
                .replace(/\n/g, '<br>');

            // Wrap in ul if we found list items (simple hack)
            if (formatted.includes('<li>')) {
                formatted = formatted.replace(/((?:<li>.*<\/li>\s*)+)/g, '<ul style="margin: 0.5rem 0 0.5rem 1.5rem; padding-left: 1rem;">$1</ul>');
            }
            return formatted;
        };

        container.style.border = '1px solid var(--border)';
        container.innerHTML = `
            <div style="display: flex; justify-content: space-between; align-items: start; margin-bottom: 1.5rem; border-bottom: 1px solid var(--border); padding-bottom: 1rem;">
                <div>
                    <h4 style="margin: 0; font-size: 1.25rem;">Verdict: <span style="color: ${verdictColor}">${analysis.verdict}</span></h4>
                    <p style="margin: 0.5rem 0 0; color: var(--text-muted); font-size: 0.875rem;">Conviction Score: ${analysis.score}/100</p>
                </div>
                ${ticker ? `<button onclick="analysisDetail.runAIAnalysis('${ticker}', true)" 
                        style="background: transparent; color: var(--text-muted); border: 1px solid var(--border); padding: 0.35rem 0.75rem; border-radius: var(--radius-sm); cursor: pointer; font-size: 0.75rem; white-space: nowrap;"
                        title="Force refresh — bypass cache and re-run AI analysis">
                    🔄 Re-run
                </button>` : ''}
            </div>
            
            <div style="margin-bottom: 1.5rem; background: rgba(255, 77, 77, 0.05); padding: 1rem; border-radius: var(--radius-sm); border-left: 3px solid var(--danger);">
                <h5 style="color: var(--danger); margin: 0 0 0.5rem 0; display: flex; align-items: center;">
                    <span style="margin-right:0.5rem;">🐻</span> Bear Case / Risks
                </h5>
                <div style="font-size: 0.95rem; line-height: 1.6; color: var(--text-light);">
                    ${formatText(analysis.bear_case)}
                </div>
            </div>

            <div style="background: rgba(255, 255, 255, 0.02); padding: 1rem; border-radius: var(--radius-sm); border-left: 3px solid var(--accent);">
                <h5 style="color: var(--accent); margin: 0 0 0.5rem 0; display: flex; align-items: center;">
                    <span style="margin-right:0.5rem;">🧠</span> Final Thesis
                </h5>
                <div style="font-size: 0.95rem; line-height: 1.6; color: var(--text-light);">
                    ${formatText(analysis.analysis)}
                </div>
            </div>
        `;
    },

    getSignalColor(signal) {
        // Bullish signals (green)
        if (['bullish', 'oversold', 'near oversold', 'pullback bullish', 'weakening bearish'].includes(signal)) {
            return 'var(--secondary)';
        }
        // Bearish signals (red)
        if (['bearish', 'overbought', 'near overbought', 'breakdown', 'rally bearish', 'weakening bullish'].includes(signal)) {
            return 'var(--danger)';
        }
        // Special signals (amber/warning)
        if (signal === 'squeeze' || signal === 'surging') {
            return '#f59e0b';
        }
        // Volume signals
        if (signal === 'strong') return 'var(--secondary)';
        if (signal === 'weak') return 'var(--danger)';
        // Neutral / normal
        return 'var(--text-muted)';
    }
};
