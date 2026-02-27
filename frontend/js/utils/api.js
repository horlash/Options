// API Base URL
const API_BASE_URL = '/api';

// API Client
const api = {
    // Helper for requests
    async request(endpoint, options = {}) {
        const url = `${API_BASE_URL}${endpoint}`;
        const defaultHeaders = {
            'Content-Type': 'application/json'
        };

        const config = {
            ...options,
            headers: {
                ...defaultHeaders,
                ...options.headers
            }
        };

        try {
            const response = await fetch(url, config);

            // Handle Auth Challenge specifically if needed, but browser handles Basic Auth prompt usually
            if (response.status === 401) {
                console.warn("Unauthorized request to " + endpoint);
                // toast.error("Please log in"); // managed by browser
            }

            // F27 FIX: Check Content-Type before parsing as JSON
            const contentType = response.headers.get('content-type') || '';
            if (!contentType.includes('application/json')) {
                const text = await response.text();
                console.error(`Non-JSON response from ${endpoint}:`, text.substring(0, 200));
                return { success: false, error: `Server returned ${response.status} (non-JSON)` };
            }

            return await response.json();
        } catch (error) {
            console.error(`API Request failed: ${endpoint}`, error);
            return { success: false, error: error.message };
        }
    },

    async healthCheck() {
        return this.request('/health');
    },

    async getWatchlist() {
        return this.request('/watchlist');
    },

    async addToWatchlist(ticker) {
        return this.request('/watchlist', {
            method: 'POST',
            body: JSON.stringify({ ticker })
        });
    },

    async removeFromWatchlist(ticker) {
        return this.request(`/watchlist/${ticker}`, { method: 'DELETE' });
    },

    async runScan() {
        return this.request('/scan', { method: 'POST' });
    },

    async scanTicker(ticker, direction = 'BOTH') {
        return this.request(`/scan/${ticker}`, {
            method: 'POST',
            body: JSON.stringify({ direction })
        });
    },

    async runDailyScan(weeksOut = 0) {
        return this.request('/scan/daily', {
            method: 'POST',
            body: JSON.stringify({ weeks_out: weeksOut })
        });
    },

    async scanTickerDaily(ticker, weeksOut = 0) {
        return this.request(`/scan/daily/${ticker}`, {
            method: 'POST',
            body: JSON.stringify({ weeks_out: weeksOut })
        });
    },

    async scan0DTE(ticker) {
        return this.request(`/scan/0dte/${ticker}`, {
            method: 'POST'
        });
    },

    async getTickers() {
        return this.request('/tickers');
    },

    async runSectorScan(sector, minCap, minVol, weeksOut, industry) {
        return this.request('/scan/sector', {
            method: 'POST',
            body: JSON.stringify({
                sector: sector,
                min_market_cap: minCap,
                min_volume: minVol,
                weeks_out: weeksOut,
                industry: industry
            })
        });
    },

    async getOpportunities() {
        return this.request('/opportunities');
    },

    async getAnalysis(ticker, expiry = null) {
        const qs = expiry ? `?expiry=${encodeURIComponent(expiry)}` : '';
        return this.request(`/analysis/${ticker}${qs}`);
    },

    async getHistory() {
        return this.request('/history');
    },

    async addHistory(ticker) {
        return this.request('/history', {
            method: 'POST',
            body: JSON.stringify({ ticker })
        });
    }
};
