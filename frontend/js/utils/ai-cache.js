/**
 * Shared AI Cache Module
 * 
 * Centralized cache for AI analysis results, shared between
 * opportunities.js (Trade button) and analysis-detail.js (Reasoning Engine).
 * 
 * Features:
 * - TTL: entries expire after 5 minutes
 * - Normalized keys: prevents mismatches between components
 * - Force-refresh: bypass cache when user wants fresh data
 */
window.aiCache = {
    _store: {},
    TTL_MS: 5 * 60 * 1000, // 5 minutes

    /**
     * Build a normalized cache key.
     * Both components MUST use this to avoid key mismatches.
     */
    buildKey(ticker, strike, type, expiry) {
        return `${String(ticker).toUpperCase().trim()}_${Number(strike)}_${String(type).toUpperCase().trim()}_${String(expiry).trim()}`;
    },

    /**
     * Get cached AI result. Returns null if missing or expired.
     */
    get(key) {
        const entry = this._store[key];
        if (!entry) return null;
        if (Date.now() - entry.timestamp > this.TTL_MS) {
            console.log(`[AI-CACHE] Expired: ${key} (age: ${Math.round((Date.now() - entry.timestamp) / 1000)}s)`);
            delete this._store[key];
            return null;
        }
        console.log(`[AI-CACHE] Hit: ${key} (age: ${Math.round((Date.now() - entry.timestamp) / 1000)}s)`);
        return entry.data;
    },

    /**
     * Store AI result with current timestamp.
     */
    set(key, data) {
        this._store[key] = { data: data, timestamp: Date.now() };
        console.log(`[AI-CACHE] Stored: ${key}`);
    },

    /**
     * Check if a key exists and is not expired.
     */
    has(key) {
        return this.get(key) !== null;
    },

    /**
     * Clear all cached entries.
     */
    clear() {
        this._store = {};
        console.log('[AI-CACHE] Cleared all entries');
    }
};
