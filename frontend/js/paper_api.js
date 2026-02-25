/**
 * Paper Trading API Client
 * =========================
 * Phase 3, Step 3.5: Frontend module for all /api/paper/* endpoints.
 *
 * Usage:
 *   const api = paperApi;
 *   const trades = await api.getTrades('OPEN');
 *   const stats  = await api.getStats();
 */

const paperApi = (() => {
    const BASE = '/api/paper';

    // ─── Generic Fetch Wrapper ────────────────────────────────

    async function _fetch(path, options = {}) {
        const url = `${BASE}${path}`;
        const defaults = {
            headers: { 'Content-Type': 'application/json' },
            credentials: 'same-origin',
        };
        const merged = { ...defaults, ...options };

        try {
            const resp = await fetch(url, merged);

            // Handle optimistic lock conflicts (Point 8)
            if (resp.status === 409) {
                const data = await resp.json();
                if (data.stale) {
                    _showToast('⚠️ Trade updated on another device. Refreshing...', 'warning');
                    // Auto-refresh after 1 second
                    setTimeout(() => {
                        if (typeof portfolio !== 'undefined' && portfolio.init) {
                            portfolio.init();
                        }
                    }, 1000);
                }
                return { success: false, stale: true };
            }

            if (!resp.ok) {
                const errData = await resp.json().catch(() => ({}));
                throw new Error(errData.error || `HTTP ${resp.status}`);
            }

            return await resp.json();
        } catch (err) {
            console.error(`[paperApi] ${options.method || 'GET'} ${url} failed:`, err);
            throw err;
        }
    }

    function _showToast(msg, type = 'info') {
        // Reuse existing toast system if available
        if (typeof showToast === 'function') {
            showToast(msg, type);
        } else {
            console.log(`[Toast/${type}] ${msg}`);
        }
    }

    // ─── Trade Endpoints ──────────────────────────────────────

    /**
     * List trades filtered by status.
     * @param {string} status - OPEN | CLOSED | EXPIRED | CANCELED | ALL
     * @param {number} limit  - Max results (default 100)
     * @returns {Promise<{success, trades[], count, market_status}>}
     */
    async function getTrades(status = 'ALL', limit = 100) {
        return _fetch(`/trades?status=${status}&limit=${limit}`);
    }

    /**
     * Get a single trade with price history.
     * @param {number} tradeId
     * @returns {Promise<{success, trade}>}
     */
    async function getTrade(tradeId) {
        return _fetch(`/trades/${tradeId}`);
    }

    /**
     * Place a new paper trade.
     * @param {Object} tradeData - { ticker, option_type, strike, expiry, entry_price, ... }
     * @returns {Promise<{success, trade}>}
     */
    async function placeTrade(tradeData) {
        return _fetch('/trades', {
            method: 'POST',
            body: JSON.stringify(tradeData),
        });
    }

    /**
     * Close an open trade.
     * @param {number} tradeId
     * @param {number} version - Current version for optimistic locking
     * @returns {Promise<{success, trade}>}
     */
    async function closeTrade(tradeId, version = null) {
        return _fetch(`/trades/${tradeId}/close`, {
            method: 'POST',
            body: JSON.stringify({ version }),
        });
    }

    /**
     * Adjust SL or TP for an open trade.
     * @param {number} tradeId
     * @param {Object} adjustments - { new_sl?, new_tp? }
     * @returns {Promise<{success, trade}>}
     */
    async function adjustTrade(tradeId, adjustments) {
        return _fetch(`/trades/${tradeId}/adjust`, {
            method: 'POST',
            body: JSON.stringify(adjustments),
        });
    }

    // ─── Settings ─────────────────────────────────────────────

    async function getSettings() {
        return _fetch('/settings');
    }

    async function updateSettings(settingsData) {
        return _fetch('/settings', {
            method: 'PUT',
            body: JSON.stringify(settingsData),
        });
    }

    /** Test broker connection using stored credentials. */
    async function testConnection() {
        return _fetch('/settings/test-connection');
    }

    // ─── Stats & Market ───────────────────────────────────────

    /**
     * Get aggregate portfolio stats for the stat cards.
     * @returns {Promise<{success, stats, market_status}>}
     */
    async function getStats() {
        return _fetch('/stats');
    }

    /**
     * Get current market status (open/closed).
     * @returns {Promise<{success, market}>}
     */
    async function getMarketStatus() {
        return _fetch('/market-status');
    }

    // ─── Analytics (Phase 5: Intelligence) ────────────────────

    /**
     * Build date-range query string from optional start/end.
     * @param {string|null} start - YYYY-MM-DD or null
     * @param {string|null} end   - YYYY-MM-DD or null
     * @returns {string} e.g. '?start=2026-01-01&end=2026-02-01' or ''
     */
    function _dateParams(start, end) {
        const params = new URLSearchParams();
        if (start) params.set('start', start);
        if (end) params.set('end', end);
        const qs = params.toString();
        return qs ? `?${qs}` : '';
    }

    /** Get comprehensive summary metrics. */
    async function getAnalyticsSummary(start = null, end = null) {
        return _fetch(`/analytics/summary${_dateParams(start, end)}`);
    }

    /** Get equity curve data for line chart. */
    async function getEquityCurve(start = null, end = null) {
        return _fetch(`/analytics/equity-curve${_dateParams(start, end)}`);
    }

    /** Get max drawdown. */
    async function getDrawdown(start = null, end = null) {
        return _fetch(`/analytics/drawdown${_dateParams(start, end)}`);
    }

    /** Get per-ticker breakdown. */
    async function getByTicker(start = null, end = null) {
        return _fetch(`/analytics/by-ticker${_dateParams(start, end)}`);
    }

    /** Get per-strategy breakdown. */
    async function getByStrategy(start = null, end = null) {
        return _fetch(`/analytics/by-strategy${_dateParams(start, end)}`);
    }

    /** Get monthly P&L for bar chart. */
    async function getMonthlyPnl(start = null, end = null) {
        return _fetch(`/analytics/monthly${_dateParams(start, end)}`);
    }

    /** Get MFE/MAE exit quality analysis. */
    async function getMfeMae(start = null, end = null) {
        return _fetch(`/analytics/mfe-mae${_dateParams(start, end)}`);
    }

    /** Get CSV export URL. */
    function getExportCsvUrl() {
        return `${BASE}/analytics/export/csv`;
    }

    /** Get JSON export URL. */
    function getExportJsonUrl() {
        return `${BASE}/analytics/export/json`;
    }

    // ─── Public API ───────────────────────────────────────────

    return {
        getTrades,
        getTrade,
        placeTrade,
        closeTrade,
        adjustTrade,
        getSettings,
        updateSettings,
        testConnection,
        getStats,
        getMarketStatus,
        // Phase 5: Analytics
        getAnalyticsSummary,
        getEquityCurve,
        getDrawdown,
        getByTicker,
        getByStrategy,
        getMonthlyPnl,
        getMfeMae,
        getExportCsvUrl,
        getExportJsonUrl,
    };
})();
