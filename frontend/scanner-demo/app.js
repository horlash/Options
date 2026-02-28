/* ============================================================
   app.js — Options Scanner Production App
   All functionality in a single file
   ============================================================ */

'use strict';

// ============================================================
// CONSTANTS & CONFIG
// ============================================================
const API_BASE = '/api';

const INDUSTRIES = {
  'Technology': ['Software - Infrastructure', 'Semiconductors', 'Consumer Electronics', 'Software - Application', 'Information Technology Services', 'Computer Hardware'],
  'Financial Services': ['Banks - Diversified', 'Credit Services', 'Asset Management', 'Capital Markets', 'Insurance - Diversified'],
  'Healthcare': ['Drug Manufacturers - General', 'Healthcare Plans', 'Biotechnology', 'Medical Devices', 'Diagnostics & Research'],
  'Consumer Cyclical': ['Internet Retail', 'Auto Manufacturers', 'Restaurants', 'Footwear & Accessories', 'Apparel Retail'],
  'Consumer Defensive': ['Discount Stores', 'Beverages - Non-Alcoholic', 'Household & Personal Products', 'Grocery Stores'],
  'Energy': ['Oil & Gas Integrated', 'Oil & Gas E&P', 'Oil & Gas Midstream', 'Oil & Gas Equipment & Services'],
  'Industrials': ['Aerospace & Defense', 'Specialty Industrial Machinery', 'Railroads', 'Airlines', 'Farm & Heavy Construction Machinery'],
  'Communication Services': ['Internet Content & Information', 'Telecom Services', 'Entertainment', 'Broadcasting'],
  'Basic Materials': ['Specialty Chemicals', 'Agricultural Inputs', 'Building Materials', 'Steel', 'Copper'],
  'Real Estate': ['REIT - Specialty', 'REIT - Industrial', 'REIT - Residential', 'Real Estate Services'],
  'Utilities': ['Utilities - Regulated Electric', 'Utilities - Diversified', 'Utilities - Renewable']
};

const TS_ICONS = {
  'VIX': '🌊', 'vix': '🌊', 'VIX Regime': '🌊',
  'P/C': '📊', 'pc_ratio': '📊', 'Put/Call': '📊', 'P/C Ratio': '📊',
  'Sector': '📈', 'sector': '📈', 'Sector Rank': '📈',
  'RSI-2': '⚡', 'rsi2': '⚡', 'RSI': '⚡',
  'Minervini': '🎯', 'minervini': '🎯', 'Stage': '🎯',
  'VWAP': '🏛️', 'vwap': '🏛️'
};

// ============================================================
// TOAST SYSTEM
// ============================================================
const toast = {
  container: null,

  init() {
    this.container = document.getElementById('toast-container');
  },

  show(message, type = 'info', duration = 3500) {
    if (!this.container) return;
    const el = document.createElement('div');
    el.className = `toast toast-${type}`;
    const icons = { info: 'ℹ️', success: '✅', error: '❌', warn: '⚠️' };
    el.innerHTML = `<span>${icons[type] || 'ℹ️'}</span><span>${message}</span>`;
    this.container.appendChild(el);
    setTimeout(() => {
      el.classList.add('toast-out');
      setTimeout(() => el.remove(), 250);
    }, duration);
  },

  info(msg) { this.show(msg, 'info'); },
  success(msg) { this.show(msg, 'success'); },
  error(msg) { this.show(msg, 'error', 5000); },
  warn(msg) { this.show(msg, 'warn', 4000); }
};

// ============================================================
// API CLIENT
// ============================================================
const api = {
  async request(endpoint, options = {}) {
    const url = `${API_BASE}${endpoint}`;
    const config = {
      ...options,
      headers: { 'Content-Type': 'application/json', ...(options.headers || {}) }
    };
    try {
      const response = await fetch(url, config);
      if (response.status === 401) {
        window.location.href = '/login';
        return { success: false, error: 'Unauthorized' };
      }
      const contentType = response.headers.get('content-type') || '';
      if (!contentType.includes('application/json')) {
        const text = await response.text();
        console.error(`Non-JSON response from ${endpoint}:`, text.substring(0, 200));
        return { success: false, error: `Server returned ${response.status}` };
      }
      return await response.json();
    } catch (error) {
      console.error(`API Request failed: ${endpoint}`, error);
      return { success: false, error: error.message };
    }
  },

  async healthCheck() { return this.request('/health'); },
  async getWatchlist() { return this.request('/watchlist'); },
  async addToWatchlist(ticker) {
    return this.request('/watchlist', { method: 'POST', body: JSON.stringify({ ticker }) });
  },
  async removeFromWatchlist(ticker) {
    return this.request(`/watchlist/${ticker}`, { method: 'DELETE' });
  },
  async runScan() { return this.request('/scan', { method: 'POST' }); },
  async scanTicker(ticker, direction = 'BOTH') {
    return this.request(`/scan/${ticker}`, { method: 'POST', body: JSON.stringify({ direction }) });
  },
  async runDailyScan(weeksOut = 0) {
    return this.request('/scan/daily', { method: 'POST', body: JSON.stringify({ weeks_out: weeksOut }) });
  },
  async scanTickerDaily(ticker, weeksOut = 0) {
    return this.request(`/scan/daily/${ticker}`, { method: 'POST', body: JSON.stringify({ weeks_out: weeksOut }) });
  },
  async scan0DTE(ticker) {
    return this.request(`/scan/0dte/${ticker}`, { method: 'POST' });
  },
  async runSectorScan(sector, minCap, minVol, weeksOut, industry) {
    return this.request('/scan/sector', {
      method: 'POST',
      body: JSON.stringify({ sector, min_market_cap: minCap, min_volume: minVol, weeks_out: weeksOut, industry })
    });
  },
  async getOpportunities() { return this.request('/opportunities'); },
  async getTickers() { return this.request('/data/tickers.json'); },
  async getMe() { return this.request('/me'); },
  async getAnalysis(ticker, expiry) {
    let url = `/analysis/${ticker}`;
    if (expiry) url += `?expiry=${encodeURIComponent(expiry)}`;
    return this.request(url);
  },
  async getAIAnalysis(ticker, data) {
    return this.request(`/analysis/ai/${ticker}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data)
    });
  },
  async placeTrade(tradeData) {
    return this.request('/paper/trades', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(tradeData)
    });
  }
};

// ============================================================
// SCANNER STATE
// ============================================================
const scanner = {
  isScanning: false,
  scanMode: 'weekly-0',
  tickers: [],
  recentHistory: [],
  currentResults: [],
  currentProfitFilter: 15,
  currentTickerFilter: 'all',
  currentSort: 'score',
  currentOpp: null,       // Selected opportunity for analyze/trade views
  currentAnalysis: null,  // Last analysis response

  // ---- HELPERS ----
  getFridayDate(weeksOut) {
    const today = new Date();
    const day = today.getDay();
    const daysUntilFriday = (5 - day + 7) % 7;
    const target = new Date(today);
    target.setDate(today.getDate() + daysUntilFriday + (weeksOut * 7));
    return target.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
  },

  isValidTicker(ticker) {
    if (!ticker || typeof ticker !== 'string') return false;
    return /^[A-Z]{1,5}$/.test(ticker.trim().toUpperCase());
  },

  // ---- INIT ----
  async init() {
    await this.loadTickers();
    this.initModeButtons();
    this.initSmartSearch();
    this.initSectorScan();
    this.initFilters();
    this.initSort();
    this.initWatchlist();
    this.initTabs();
    this.initLogout();
    this.initThemeToggle();
    this.loadUsername();
    this.setMode('weekly-0');
    this.loadOpportunities();
  },

  // ---- TICKERS (autocomplete data) ----
  async loadTickers() {
    try {
      const res = await fetch('/api/data/tickers.json');
      const data = await res.json();
      this.tickers = data.tickers || [];
    } catch (e) {
      console.warn('Could not load tickers.json:', e);
      this.tickers = [];
    }
  },

  searchTickers(query) {
    if (!query) return [];
    query = query.toUpperCase();
    const symbolMatches = this.tickers.filter(t => t.symbol.toUpperCase().startsWith(query));
    const nameStartMatches = this.tickers.filter(t =>
      !symbolMatches.includes(t) && (t.name || '').toUpperCase().startsWith(query)
    );
    const nameContainsMatches = this.tickers.filter(t =>
      !symbolMatches.includes(t) && !nameStartMatches.includes(t) && (t.name || '').toUpperCase().includes(query)
    );
    return [...symbolMatches, ...nameStartMatches, ...nameContainsMatches].slice(0, 8);
  },

  showAutocomplete(dropdown, matches, onSelect) {
    if (!matches.length) { dropdown.style.display = 'none'; return; }
    dropdown.innerHTML = matches.map(t => `
      <div class="autocomplete-item" data-symbol="${t.symbol}">
        <span class="item-symbol">${t.symbol}</span>
        <span class="item-name">${t.name || ''}</span>
      </div>
    `).join('');
    dropdown.style.display = 'block';
    dropdown.querySelectorAll('.autocomplete-item').forEach(item => {
      item.addEventListener('click', () => {
        onSelect(item.dataset.symbol);
        dropdown.style.display = 'none';
      });
    });
  },

  // ---- SCAN MODE BUTTONS ----
  initModeButtons() {
    const buttons = document.querySelectorAll('.mode-btn');
    buttons.forEach(btn => {
      btn.addEventListener('click', () => {
        const mode = btn.dataset.mode;
        this.setMode(mode);
      });
    });
    // Update button labels with dates
    this.updateModeLabels();
  },

  updateModeLabels() {
    const setLabel = (id, weeksOut) => {
      const btn = document.getElementById(id);
      if (!btn) return;
      const dateStr = this.getFridayDate(weeksOut);
      const labels = { 0: 'This Week', 1: 'Next Week', 2: 'Next 2 Weeks' };
      btn.textContent = `${labels[weeksOut]} (${dateStr})`;
    };
    setLabel('mode-weekly-0', 0);
    setLabel('mode-weekly-1', 1);
    setLabel('mode-weekly-2', 2);
  },

  setMode(mode) {
    this.scanMode = mode;

    // Update active button state
    document.querySelectorAll('.mode-btn').forEach(btn => {
      btn.classList.remove('active', 'mode-0dte-active');
    });
    const activeBtn = document.getElementById(`mode-${mode}`);
    if (activeBtn) {
      if (mode === '0dte') {
        activeBtn.classList.add('active', 'mode-0dte-active');
      } else {
        activeBtn.classList.add('active');
      }
    }

    // Update opportunities header label
    const labelEl = document.getElementById('opportunities-mode-label');
    if (labelEl) {
      if (mode === 'leaps') {
        labelEl.textContent = 'Leaps';
        labelEl.className = 'opp-mode-label';
      } else if (mode === '0dte') {
        labelEl.textContent = '⚡ 0DTE Intraday';
        labelEl.className = 'opp-mode-label urgent';
      } else {
        const btn = document.getElementById(`mode-${mode}`);
        labelEl.textContent = btn ? btn.textContent : 'This Week';
        labelEl.className = 'opp-mode-label';
      }
    }
  },

  // ---- SMART SEARCH ----
  initSmartSearch() {
    const input = document.getElementById('quick-scan-input');
    const dropdown = document.getElementById('autocomplete-list');
    const scanBtn = document.getElementById('btn-scan-ticker');

    if (!input || !dropdown) return;

    input.addEventListener('input', () => {
      const q = input.value.trim();
      if (q.length > 0) {
        const matches = this.searchTickers(q);
        this.showAutocomplete(dropdown, matches, (sym) => {
          input.value = sym;
        });
      } else {
        dropdown.style.display = 'none';
      }
    });

    input.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') this.runTickerScan(input.value.trim().toUpperCase());
    });

    document.addEventListener('click', (e) => {
      if (!input.contains(e.target) && !dropdown.contains(e.target)) {
        dropdown.style.display = 'none';
      }
    });

    if (scanBtn) {
      scanBtn.addEventListener('click', () => {
        this.runTickerScan(input.value.trim().toUpperCase());
      });
    }
  },

  // ---- SECTOR SCAN ----
  initSectorScan() {
    const sectorSelect = document.getElementById('sector-select');
    const industrySelect = document.getElementById('industry-select');
    const extraFilters = document.getElementById('sector-extra-filters');
    const scanBtn = document.getElementById('btn-sector-scan');

    if (!sectorSelect) return;

    sectorSelect.addEventListener('change', () => {
      const sector = sectorSelect.value;
      industrySelect.innerHTML = '<option value="">Any Subsector</option>';
      if (sector && INDUSTRIES[sector]) {
        INDUSTRIES[sector].slice().sort().forEach(ind => {
          const opt = document.createElement('option');
          opt.value = ind;
          opt.textContent = ind;
          industrySelect.appendChild(opt);
        });
        industrySelect.style.display = 'block';
        extraFilters.style.display = 'flex';
      } else {
        industrySelect.style.display = 'none';
        extraFilters.style.display = 'none';
      }
    });

    if (scanBtn) {
      scanBtn.addEventListener('click', () => {
        const sector = sectorSelect.value;
        if (!sector) { toast.error('Please select a sector'); return; }
        if (this.scanMode === '0dte') {
          toast.error('0DTE sector scans are not supported. Use single-ticker 0DTE scan instead.');
          return;
        }
        const industry = industrySelect.value;
        const minCap = document.getElementById('cap-select').value;
        const minVol = document.getElementById('vol-select').value;
        this.runSectorScan(sector, minCap, minVol, industry);
      });
    }
  },

  // ---- FILTERS & SORT ----
  initFilters() {
    document.querySelectorAll('.btn-filter').forEach(btn => {
      const value = parseInt(btn.dataset.value);
      btn.addEventListener('click', () => {
        document.querySelectorAll('.btn-filter').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        this.currentProfitFilter = value;
        this.renderCards();
      });
    });
  },

  initSort() {
    const sortSelect = document.getElementById('sort-select');
    if (sortSelect) {
      sortSelect.addEventListener('change', () => {
        this.currentSort = sortSelect.value;
        this.renderCards();
      });
    }

    const tickerFilter = document.getElementById('ticker-filter');
    if (tickerFilter) {
      tickerFilter.addEventListener('change', () => {
        this.currentTickerFilter = tickerFilter.value;
        this.renderCards();
      });
    }
  },

  // ---- WATCHLIST ----
  initWatchlist() {
    // Wire up BOTH watchlist inputs: main-area and sidebar
    this._wireWatchlistInput('watchlist-input', 'watchlist-autocomplete');
    this._wireWatchlistInput('sidebar-watchlist-input', null);

    // Load watchlist from API on start
    this.loadWatchlist();
  },

  _wireWatchlistInput(inputId, dropdownId) {
    const input = document.getElementById(inputId);
    if (!input) return;
    const dropdown = dropdownId ? document.getElementById(dropdownId) : null;

    if (dropdown) {
      input.addEventListener('input', () => {
        const q = input.value.trim();
        if (q.length > 0) {
          const matches = this.searchTickers(q);
          this.showAutocomplete(dropdown, matches, (sym) => {
            input.value = '';
            this.addToWatchlist(sym);
          });
        } else {
          dropdown.style.display = 'none';
        }
      });

      document.addEventListener('click', (e) => {
        if (!input.contains(e.target) && !dropdown.contains(e.target)) {
          dropdown.style.display = 'none';
        }
      });
    }

    input.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        const ticker = input.value.trim().toUpperCase();
        if (ticker) {
          input.value = '';
          if (dropdown) dropdown.style.display = 'none';
          this.addToWatchlist(ticker);
        }
      }
    });
  },

  async loadWatchlist() {
    try {
      const result = await api.getWatchlist();
      if (result && result.watchlist) {
        this.renderWatchlistChips(result.watchlist);
        this.updateHeaderCount('watchlist', result.watchlist.length);
      } else if (Array.isArray(result)) {
        this.renderWatchlistChips(result);
        this.updateHeaderCount('watchlist', result.length);
      }
    } catch (e) {
      console.warn('Could not load watchlist:', e);
    }
  },

  renderWatchlistChips(tickers) {
    const containers = [
      document.getElementById('watchlist-chips'),
      document.getElementById('sidebar-watchlist-chips')
    ].filter(Boolean);
    if (containers.length === 0) return;

    const tickerStrings = (tickers || []).map(t =>
      (typeof t === 'object' && t.ticker) ? t.ticker : t
    );

    containers.forEach(container => {
      if (tickerStrings.length === 0) {
        container.innerHTML = '<span style="font-size:0.72rem;color:var(--text-light);font-style:italic;">No tickers yet</span>';
        return;
      }
      container.innerHTML = tickerStrings.map(ticker => `
        <span class="chip" data-ticker="${ticker}" style="cursor:pointer;" title="Click to scan ${ticker}">
          <span class="chip-label">${ticker}</span>
          <button class="chip-remove" data-ticker="${ticker}" title="Remove ${ticker}" aria-label="Remove ${ticker}">×</button>
        </span>
      `).join('');

      // Click chip label → scan ticker
      container.querySelectorAll('.chip-label').forEach(label => {
        label.addEventListener('click', (e) => {
          e.stopPropagation();
          const ticker = label.parentElement.dataset.ticker;
          this.runTickerScan(ticker);
        });
      });

      // Click × → remove from watchlist
      container.querySelectorAll('.chip-remove').forEach(btn => {
        btn.addEventListener('click', (e) => {
          e.stopPropagation();
          this.removeFromWatchlist(btn.dataset.ticker);
        });
      });
    });
  },

  async addToWatchlist(ticker) {
    ticker = ticker.trim().toUpperCase();
    if (!this.isValidTicker(ticker)) {
      toast.error(`Invalid ticker format: "${ticker}"`);
      return;
    }
    const result = await api.addToWatchlist(ticker);
    if (result && (result.success || result.watchlist)) {
      toast.success(`${ticker} added to watchlist`);
      this.loadWatchlist();
    } else {
      toast.error(result.error || `Failed to add ${ticker}`);
    }
  },

  async removeFromWatchlist(ticker) {
    const result = await api.removeFromWatchlist(ticker);
    if (result && (result.success || !result.error)) {
      toast.info(`${ticker} removed`);
      this.loadWatchlist();
    } else {
      toast.error(result.error || `Failed to remove ${ticker}`);
    }
  },

  // ---- APP TABS ----
  initTabs() {
    document.querySelectorAll('.app-tab').forEach(tab => {
      tab.addEventListener('click', () => {
        const tabId = tab.dataset.tab;
        document.querySelectorAll('.app-tab').forEach(t => t.classList.remove('active'));
        document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
        tab.classList.add('active');
        const content = document.getElementById(`tab-${tabId}`);
        if (content) content.classList.add('active');
      });
    });
  },

  // ---- LOGOUT ----
  initLogout() {
    const btn = document.getElementById('logout-btn');
    if (btn) {
      btn.addEventListener('click', () => {
        window.location.href = '/logout';
      });
    }
  },

  // ---- LOAD EXISTING OPPORTUNITIES ----
  async loadOpportunities() {
    try {
      const result = await api.getOpportunities();
      if (result && result.opportunities && result.opportunities.length > 0) {
        this.currentResults = result.opportunities;
        this.renderCards();
      }
    } catch (e) {
      console.warn('Could not load existing opportunities:', e);
    }
  },

  // ---- RUN SCANS ----
  async runTickerScan(ticker) {
    if (!ticker) { toast.error('Please enter a ticker symbol'); return; }
    if (!this.isValidTicker(ticker)) {
      toast.error(`Invalid ticker: "${ticker}"`);
      return;
    }
    if (this.isScanning) { toast.info('Scan already in progress'); return; }
    this.isScanning = true;
    this.showProgress();

    try {
      let result;
      if (this.scanMode === 'leaps') {
        toast.info(`Scanning ${ticker} (LEAPS)...`);
        result = await api.scanTicker(ticker, 'BOTH');
      } else if (this.scanMode === '0dte') {
        toast.info(`⚡ Scanning ${ticker} (0DTE)...`);
        result = await api.scan0DTE(ticker);
      } else {
        const weeksOut = parseInt(this.scanMode.split('-')[1]);
        toast.info(`Scanning ${ticker} (Weekly +${weeksOut})...`);
        result = await api.scanTickerDaily(ticker, weeksOut);
      }

      if (result && result.success && result.result) {
        toast.success(`Scan complete for ${ticker}`);
        this.currentResults = [result.result];
        this.addToHistory(`${ticker} · ${this.getModeLabel()}`);
        this.renderCards();
      } else {
        toast.error(result.error || `Failed to scan ${ticker}`);
      }
    } catch (error) {
      toast.error(`Error scanning ${ticker}`);
    } finally {
      this.isScanning = false;
      this.hideProgress();
      document.getElementById('quick-scan-input').value = '';
    }
  },

  async runBulkScan() {
    if (this.isScanning) { toast.info('Scan already in progress'); return; }
    this.isScanning = true;
    this.showProgress();
    try {
      let result;
      if (this.scanMode === 'leaps') {
        toast.info('Starting LEAP scan...');
        result = await api.runScan();
      } else if (this.scanMode === '0dte') {
        toast.error('Bulk 0DTE Scan not supported. Use single-ticker 0DTE scan instead.');
        this.isScanning = false;
        this.hideProgress();
        return;
      } else {
        const weeksOut = parseInt(this.scanMode.split('-')[1]);
        toast.info(`Starting Weekly Scan (+${weeksOut} weeks)...`);
        result = await api.runDailyScan(weeksOut);
      }

      if (result && result.success) {
        toast.success(`Scan complete! Found opportunities in ${result.results.length} tickers`);
        this.currentResults = result.results;
        this.addToHistory(this.getModeLabel());
        this.renderCards();
      } else {
        toast.error(result.error || 'Scan failed');
      }
    } catch (error) {
      toast.error('Error running scan');
    } finally {
      this.isScanning = false;
      this.hideProgress();
    }
  },

  async runSectorScan(sector, minCap, minVol, industry) {
    if (this.isScanning) { toast.info('Scan already in progress'); return; }
    this.isScanning = true;
    this.showProgress();

    let weeksOut = null;
    if (this.scanMode !== 'leaps') {
      weeksOut = parseInt(this.scanMode.split('-')[1]);
    }

    const modeLabel = weeksOut === null ? 'LEAPS' : `Weekly (+${weeksOut})`;
    const indLabel = industry ? ` | ${industry}` : '';
    toast.info(`Scanning Top Picks in ${sector}${indLabel} (${modeLabel})...`);

    try {
      const result = await api.runSectorScan(sector, minCap, minVol, weeksOut, industry);
      if (result && result.success) {
        toast.success(`Found ${result.results.length} sector opportunities!`);
        this.currentResults = result.results;
        this.addToHistory(`${sector}${indLabel} · ${modeLabel}`);
        this.renderCards();
      } else {
        toast.error(result.error || 'Sector scan failed');
      }
    } catch (error) {
      toast.error('Sector scan error');
    } finally {
      this.isScanning = false;
      this.hideProgress();
    }
  },

  getModeLabel() {
    if (this.scanMode === 'leaps') return 'Leaps';
    if (this.scanMode === '0dte') return '0DTE';
    const btn = document.getElementById(`mode-${this.scanMode}`);
    return btn ? btn.textContent : this.scanMode;
  },

  // ---- RECENT HISTORY ----
  addToHistory(label) {
    const now = new Date().toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' });
    this.recentHistory.unshift({ label, time: now });
    if (this.recentHistory.length > 5) this.recentHistory.pop();
    this.renderHistory();
  },

  renderHistory() {
    const container = document.getElementById('recent-history-list');
    if (!container) return;
    if (!this.recentHistory.length) {
      container.innerHTML = '<div class="ctrl-placeholder">No recent scans</div>';
      return;
    }
    container.innerHTML = this.recentHistory.map(h => `
      <div class="history-item">${h.label} <span style="color:var(--text-light);">· ${h.time}</span></div>
    `).join('');
  },

  // ---- PROGRESS ----
  showProgress() {
    const el = document.getElementById('scan-progress');
    if (el) el.classList.remove('hidden');
  },

  hideProgress() {
    const el = document.getElementById('scan-progress');
    if (el) el.classList.add('hidden');
  },

  // ---- HEADER COUNTS ----
  updateHeaderCount(type, count) {
    const ids = {
      watchlist: 'watchlist-count',
      opportunities: 'opportunities-count'
    };
    const el = document.getElementById(ids[type]);
    if (el) el.textContent = count;
  },

  // ---- TICKER FILTER DROPDOWN ----
  updateTickerFilter(results) {
    const select = document.getElementById('ticker-filter');
    if (!select) return;
    const current = select.value;
    select.innerHTML = '<option value="all">All Tickers</option>';
    const tickers = new Set();
    results.forEach(r => r.ticker && tickers.add(r.ticker));
    tickers.forEach(t => {
      const opt = document.createElement('option');
      opt.value = t;
      opt.textContent = t;
      select.appendChild(opt);
    });
    if (tickers.has(current)) select.value = current;
  },

  // ============================================================
  // CARD RENDERING
  // ============================================================
  renderCards() {
    const container = document.getElementById('opportunities-container');
    if (!container) return;

    // 1. Flatten all opportunities
    const allOpps = [];
    (this.currentResults || []).forEach(result => {
      let fundData = result.fundamental_analysis || null;
      if (result.badges && result.badges.length > 0) {
        if (!fundData) fundData = {};
        if (!fundData.badges) fundData.badges = [];
        result.badges.forEach(b => { if (!fundData.badges.includes(b)) fundData.badges.push(b); });
      }
      (result.opportunities || []).forEach(opp => {
        if (!opp.fundamental_analysis && fundData) opp.fundamental_analysis = fundData;
        if (!opp.ticker) opp.ticker = result.ticker;
        if (!opp.current_price) opp.current_price = result.current_price;
        allOpps.push(opp);
      });
    });

    // 2. Update ticker filter options
    this.updateTickerFilter(this.currentResults || []);

    // Empty state (no scan data)
    if (allOpps.length === 0) {
      container.innerHTML = `
        <div class="empty-state">
          <div class="empty-icon">🔍</div>
          <div class="empty-text">No active scan results. Run a scan to discover opportunities.</div>
        </div>`;
      this.updateHeaderCount('opportunities', 0);
      return;
    }

    // 3. Filter by ticker
    let filtered = allOpps;
    if (this.currentTickerFilter !== 'all') {
      filtered = filtered.filter(o => o.ticker === this.currentTickerFilter);
    }

    // 4. Filter by profit potential
    filtered = filtered.filter(o => o.profit_potential >= this.currentProfitFilter);

    // 5. Sort
    if (this.currentSort === 'profit') {
      filtered.sort((a, b) => b.profit_potential - a.profit_potential);
    } else if (this.currentSort === 'expiry') {
      filtered.sort((a, b) => new Date(a.expiration_date) - new Date(b.expiration_date));
    } else {
      filtered.sort((a, b) => b.opportunity_score - a.opportunity_score);
    }

    // No results after filters
    if (filtered.length === 0) {
      container.innerHTML = `
        <div class="empty-state">
          <div class="empty-icon">🔍</div>
          <div class="empty-text">No results match the current filters.</div>
        </div>`;
      this.updateHeaderCount('opportunities', 0);
      return;
    }

    // 6. Render cards
    container.innerHTML = `<div class="cards-grid">${filtered.map((opp, i) => this.createCard(opp, i)).join('')}</div>`;
    this.updateHeaderCount('opportunities', filtered.length);

    // 7. Attach trading systems toggle handlers
    container.querySelectorAll('.ts-header').forEach(header => {
      header.addEventListener('click', () => {
        const section = header.closest('.trading-systems');
        if (!section) return;
        const collapsed = section.classList.contains('collapsed');
        section.classList.toggle('collapsed', !collapsed);
        const chevron = header.querySelector('.ts-chevron');
        if (chevron) chevron.textContent = collapsed ? '▼' : '▶';
      });
    });

    // 8. Attach analyze/trade button handlers
    this.attachCardHandlers();
  },

  createCard(opp, index) {
    const isCall = opp.option_type === 'Call';
    const is0DTE = this.scanMode === '0dte';
    const isWeekly = this.scanMode.startsWith('weekly');
    const isLeap = this.scanMode === 'leaps';
    const score = opp.opportunity_score || 0;

    const cardClass = [
      'opp-card',
      isCall ? 'card-call' : 'card-put',
      is0DTE ? 'card-0dte' : '',
      isWeekly ? 'card-weekly' : ''
    ].filter(Boolean).join(' ');

    const actionText = isCall ? 'BUY CALL' : 'BUY PUT';

    // Score color
    const scoreClass = score >= 66 ? 'score-green' : score >= 41 ? 'score-amber' : 'score-red';

    // Expiry formatting
    const expiryDate = opp.expiration_date
      ? new Date(opp.expiration_date).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric', timeZone: 'UTC' })
      : '—';

    // Urgency for expiry/days
    const urgentClass = is0DTE ? ' urgent' : '';

    // Break even fallback
    let breakEven = opp.break_even;
    if (!breakEven && opp.strike_price && opp.premium) {
      breakEven = isCall ? (opp.strike_price + opp.premium) : (opp.strike_price - opp.premium);
    }

    // Profit potential pill
    const profit = opp.profit_potential || 0;
    const potentialClass = profit >= 25 ? 'green' : profit >= 15 ? 'amber' : 'red';

    // Scan type badge
    let scanBadge = '';
    if (isLeap) scanBadge = '<span class="scan-type-badge badge-leap">LEAP</span>';
    else if (is0DTE) scanBadge = '<span class="scan-type-badge badge-0dte">0DTE</span>';
    else if (isWeekly) scanBadge = '<span class="scan-type-badge badge-weekly">Weekly</span>';

    // Badges
    let badgesHtml = '';
    if (opp.play_type === 'tactical') badgesHtml += `<span class="badge badge-play">⚡ Tactical</span>`;
    if (opp.play_type === 'momentum') badgesHtml += `<span class="badge badge-play">🚀 Momentum</span>`;
    if (opp.play_type === 'value') badgesHtml += `<span class="badge badge-play">💎 Value</span>`;
    if (opp.has_earnings_risk) badgesHtml += `<span class="badge badge-warn">⚠️ Earnings</span>`;
    if (opp.fundamental_analysis && opp.fundamental_analysis.badges) {
      opp.fundamental_analysis.badges.forEach(b => {
        if (!opp.play_type || b.toLowerCase() !== opp.play_type.toLowerCase()) {
          badgesHtml += `<span class="badge">${b}</span>`;
        }
      });
    }

    // Source
    let source = opp.data_source || '';
    if (['Unknown', 'Market Data', 'Data: Composite'].includes(source)) source = '';

    // Trading Systems section
    const tsCount = opp.trading_systems ? Object.keys(opp.trading_systems).length : 0;
    const tsScore = opp.technical_score || score;
    let tradingSystemsHtml = '';
    if (tsCount > 0) {
      let tsPillsHtml = '';
      for (const [name, data] of Object.entries(opp.trading_systems)) {
        const signal = typeof data === 'object' ? (data.signal || data.value || 'N/A') : data;
        const detail = typeof data === 'object' ? (data.detail || data.description || '') : '';
        const sigStr = String(signal).toUpperCase();
        let pillClass = 'ts-pill gray ts-pill-neutral';
        if (sigStr === 'BUY' || sigStr === 'BULLISH' || sigStr === 'NORMAL' || sigStr === 'CALM' || sigStr.includes('ABOVE') || sigStr.includes('TOP')) {
          pillClass = 'ts-pill green ts-pill-green';
        } else if (sigStr === 'SELL' || sigStr === 'BEARISH' || sigStr === 'CRISIS' || sigStr === 'FEAR' || sigStr.includes('BELOW') || sigStr.includes('STAGE 3') || sigStr.includes('STAGE 4')) {
          pillClass = 'ts-pill red ts-pill-red';
        } else if (sigStr === 'CAUTION' || sigStr === 'ELEVATED' || sigStr.includes('EARLY')) {
          pillClass = 'ts-pill amber ts-pill-amber';
        }
        const icon = TS_ICONS[name] || '📋';
        const displayText = detail ? `${icon} ${name}: ${detail}` : `${icon} ${name}: ${signal}`;
        tsPillsHtml += `<span class="${pillClass}">${displayText}</span>`;
      }
      const scoreColorClass = tsScore >= 66 ? 'green' : tsScore >= 41 ? 'amber' : 'red';
      tradingSystemsHtml = `
        <div class="trading-systems collapsed">
          <div class="ts-header">
            <span class="ts-chevron">▶</span>
            <span class="ts-label">Trading Systems</span>
            <span class="ts-summary-inline">${tsCount} System${tsCount !== 1 ? 's' : ''} · Score: ${tsScore}/100</span>
          </div>
          <div class="ts-body">
            <div class="ts-pills">${tsPillsHtml}</div>
            <div class="ts-score-line ${scoreColorClass}">Score: ${tsScore}/100</div>
          </div>
        </div>`;
    }

    // Gate 1: score < 40 = locked
    const isLocked = score < 40;
    const btnClass = isCall ? 'trade-btn-call' : 'trade-btn-put';
    const tradeAreaHtml = isLocked
      ? `<div class="card-actions">
          <button class="btn-analyze">🔍 Analyze</button>
          <button class="btn-trade locked" disabled>🔒 Locked</button>
         </div>
         <div class="gate-label">Score below 40 — trade locked (Gate 1)</div>`
      : `<div class="card-actions">
          <button class="btn-analyze">🔍 Analyze</button>
          <button class="btn-trade ${btnClass}">⚡ Trade</button>
         </div>`;

    return `
      <div class="${cardClass}" data-index="${index}">
        <div class="card-header">
          <div class="card-ticker-row">
            <span class="card-ticker">${opp.ticker}</span>
            <span class="card-price">$${opp.current_price ? opp.current_price.toFixed(2) : '—'}</span>
            ${scanBadge}
          </div>
          <div class="card-score-wrap">
            <div class="card-score ${scoreClass}">${score.toFixed(0)}</div>
            <span class="card-score-label">/100</span>
          </div>
        </div>
        <div class="card-hero">
          <div class="card-action">${actionText} $${opp.strike_price ? opp.strike_price.toFixed(2) : '—'}</div>
          <span class="card-potential ${potentialClass}">+${profit.toFixed(0)}% Potential</span>
        </div>
        <div class="card-metrics">
          <div class="metric">
            <span class="metric-label">Strike</span>
            <span class="metric-val">$${opp.strike_price ? opp.strike_price.toFixed(2) : '—'}</span>
          </div>
          <div class="metric">
            <span class="metric-label">Expiry</span>
            <span class="metric-val${urgentClass}">${expiryDate}</span>
          </div>
          <div class="metric">
            <span class="metric-label">Premium</span>
            <span class="metric-val">$${opp.premium ? opp.premium.toFixed(2) : '—'}</span>
          </div>
          <div class="metric">
            <span class="metric-label">Volume</span>
            <span class="metric-val">${(opp.volume || 0).toLocaleString()}</span>
          </div>
          <div class="metric">
            <span class="metric-label">Open Int</span>
            <span class="metric-val">${(opp.open_interest || 0).toLocaleString()}</span>
          </div>
          <div class="metric">
            <span class="metric-label">IV</span>
            <span class="metric-val">${opp.greeks && opp.greeks.implied_volatility ? (opp.greeks.implied_volatility * 100).toFixed(1) + '%' : (opp.volatility ? (opp.volatility * 100).toFixed(1) + '%' : '—')}</span>
          </div>
        </div>
        ${tradingSystemsHtml}
        <div class="card-footer">
          <div class="card-badges">${badgesHtml}</div>
          <div class="card-source">${source}</div>
          ${tradeAreaHtml}
        </div>
      </div>`;
  },

  // ============================================================
  // USERNAME DISPLAY
  // ============================================================
  async loadUsername() {
    try {
      const result = await api.getMe();
      if (result.success && result.username) {
        const el = document.getElementById('username-display');
        if (el) {
          el.textContent = `👤 ${result.username}`;
          el.style.display = '';
        }
      }
    } catch (e) { /* silent */ }
  },

  // ============================================================
  // DARK MODE TOGGLE
  // ============================================================
  initThemeToggle() {
    const btn = document.getElementById('theme-toggle');
    if (!btn) return;
    // Default to dark mode (matching wireframe) unless user explicitly chose light
    const savedTheme = localStorage.getItem('theme');
    if (savedTheme === 'light') {
      document.body.classList.remove('dark');
      btn.textContent = '☀️ Light';
    } else {
      // Default: dark mode
      document.body.classList.add('dark');
      btn.textContent = '🌙 Dark';
      if (!savedTheme) localStorage.setItem('theme', 'dark');
    }
    btn.addEventListener('click', () => {
      const isDark = document.body.classList.toggle('dark');
      btn.textContent = isDark ? '🌙 Dark' : '☀️ Light';
      localStorage.setItem('theme', isDark ? 'dark' : 'light');
    });
  },

  // ============================================================
  // CARD CLICK HANDLERS
  // ============================================================
  attachCardHandlers() {
    // Analyze buttons
    document.querySelectorAll('.btn-analyze').forEach(btn => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        const card = btn.closest('.opp-card');
        const idx = card ? parseInt(card.dataset.index) : -1;
        const opp = this.getOppByIndex(idx);
        if (opp) this.showAnalyzeView(opp);
      });
    });
    // Trade buttons
    document.querySelectorAll('.btn-trade:not(.locked)').forEach(btn => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        const card = btn.closest('.opp-card');
        const idx = card ? parseInt(card.dataset.index) : -1;
        const opp = this.getOppByIndex(idx);
        if (opp) this.showTradeModal(opp);
      });
    });
  },

  getOppByIndex(idx) {
    // Flatten all opportunities (same logic as renderCards)
    const allOpps = [];
    (this.currentResults || []).forEach(result => {
      let fundData = result.fundamental_analysis || null;
      if (result.badges && result.badges.length > 0) {
        if (!fundData) fundData = {};
        if (!fundData.badges) fundData.badges = [];
        result.badges.forEach(b => { if (!fundData.badges.includes(b)) fundData.badges.push(b); });
      }
      (result.opportunities || []).forEach(opp => {
        if (!opp.fundamental_analysis && fundData) opp.fundamental_analysis = fundData;
        if (!opp.ticker) opp.ticker = result.ticker;
        if (!opp.current_price) opp.current_price = result.current_price;
        allOpps.push(opp);
      });
    });
    return allOpps[idx] || null;
  },

  // ============================================================
  // ANALYZE VIEW
  // ============================================================
  async showAnalyzeView(opp) {
    this.currentOpp = opp;
    const view = document.getElementById('analyze-view');
    if (!view) return;

    const ticker = opp.ticker;
    const isCall = opp.option_type === 'Call';
    const score = opp.opportunity_score || 0;
    const scoreClass = score >= 66 ? 'score-green' : score >= 41 ? 'score-amber' : 'score-red';
    const expiryDate = opp.expiration_date
      ? new Date(opp.expiration_date).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric', timeZone: 'UTC' })
      : '—';

    // Show loading state first
    view.innerHTML = `
      <div class="view-header">
        <button class="back-btn" id="analyze-back">← Back to Results</button>
        <span class="view-ticker">${ticker}</span>
        <span class="view-subtitle">$${opp.current_price ? opp.current_price.toFixed(2) : '—'} · ${opp.option_type} · ${expiryDate}</span>
        <div style="margin-left:auto; display:flex; align-items:baseline; gap:4px;">
          <div class="card-score ${scoreClass}" style="width:44px;height:44px;font-size:1rem;">${score.toFixed(0)}</div>
          <span style="font-size:0.7rem; color:var(--text-light);">/100</span>
        </div>
      </div>
      <div class="view-body">
        <div class="ai-loading">
          <div class="ai-spinner"></div>
          <div style="font-size:0.85rem; color:var(--text-muted);">Loading analysis for ${ticker}...</div>
        </div>
      </div>`;
    view.style.display = 'block';

    // Attach back button
    document.getElementById('analyze-back')?.addEventListener('click', () => {
      view.style.display = 'none';
    });

    // Fetch analysis
    try {
      const result = await api.getAnalysis(ticker, opp.expiration_date);
      this.currentAnalysis = result.success ? result.analysis : null;
      const a = this.currentAnalysis || {};
      const tech = a.technicals || {};
      const sentiment = a.sentiment || {};
      const exitPlan = a.exit_plan || {};
      const ts = a.trading_systems || opp.trading_systems || {};

      // Build technical indicators
      const indicators = [
        { label: 'RSI', value: tech.rsi != null ? Number(tech.rsi).toFixed(1) : '—' },
        { label: 'RSI Signal', value: tech.rsi_signal || '—' },
        { label: 'MACD', value: tech.macd_signal || '—' },
        { label: 'SMA 50', value: tech.sma_50 ? `$${Number(tech.sma_50).toFixed(2)}` : '—' },
        { label: 'SMA 200', value: tech.sma_200 ? `$${Number(tech.sma_200).toFixed(2)}` : '—' },
        { label: 'VWAP', value: tech.vwap ? `$${Number(tech.vwap).toFixed(2)}` : '—' },
        { label: 'BB Signal', value: tech.bb_signal || '—' },
        { label: 'Volume', value: tech.volume_signal || '—' },
        { label: 'ATR', value: tech.atr ? Number(tech.atr).toFixed(2) : '—' },
      ];

      const indicatorsHtml = indicators.map(i => `
        <div class="indicator-item">
          <div class="indicator-label">${i.label}</div>
          <div class="indicator-value">${i.value}</div>
        </div>`).join('');

      // Trading systems pills
      let tsPillsHtml = '';
      for (const [name, data] of Object.entries(ts)) {
        const signal = typeof data === 'object' ? (data.signal || data.value || 'N/A') : data;
        const detail = typeof data === 'object' ? (data.detail || data.description || '') : '';
        const sigStr = String(signal).toUpperCase();
        let pillClass = 'ts-pill gray ts-pill-neutral';
        if (sigStr === 'BUY' || sigStr === 'BULLISH' || sigStr === 'NORMAL' || sigStr === 'CALM' || sigStr.includes('ABOVE') || sigStr.includes('TOP')) {
          pillClass = 'ts-pill green ts-pill-green';
        } else if (sigStr === 'SELL' || sigStr === 'BEARISH' || sigStr === 'CRISIS' || sigStr === 'FEAR' || sigStr.includes('BELOW') || sigStr.includes('STAGE 3') || sigStr.includes('STAGE 4')) {
          pillClass = 'ts-pill red ts-pill-red';
        } else if (sigStr === 'CAUTION' || sigStr === 'ELEVATED' || sigStr.includes('EARLY')) {
          pillClass = 'ts-pill amber ts-pill-amber';
        }
        const icon = TS_ICONS[name] || '📋';
        const displayText = detail ? `${icon} ${name}: ${detail}` : `${icon} ${name}: ${signal}`;
        tsPillsHtml += `<span class="${pillClass}">${displayText}</span>`;
      }

      // Sentiment section
      const sentScore = sentiment.score != null ? Number(sentiment.score) : null;
      const sentSource = sentiment.source || '';
      const sentHtml = sentScore != null ? `
        <div class="ctrl-box" style="margin-bottom:14px;">
          <div class="ctrl-box-title">Sentiment</div>
          <div style="display:flex; align-items:center; gap:12px;">
            <div class="card-score ${sentScore >= 66 ? 'score-green' : sentScore >= 41 ? 'score-amber' : 'score-red'}" style="width:36px;height:36px;font-size:0.9rem;">${sentScore.toFixed(0)}</div>
            <div style="font-size:0.78rem;">${sentSource}</div>
          </div>
        </div>` : '';

      // Exit plan
      const exitHtml = (exitPlan.sl_price || exitPlan.tp_price) ? `
        <div class="ctrl-box" style="margin-bottom:14px;">
          <div class="ctrl-box-title">Exit Plan</div>
          <div style="display:grid; grid-template-columns:1fr 1fr 1fr; gap:8px; font-size:0.78rem;">
            <div><span style="color:var(--text-muted);">Entry</span><br><b>$${exitPlan.entry_price ? Number(exitPlan.entry_price).toFixed(2) : '—'}</b></div>
            <div><span style="color:var(--text-muted);">Stop Loss</span><br><b style="color:var(--red);">$${exitPlan.sl_price ? Number(exitPlan.sl_price).toFixed(2) : '—'}</b></div>
            <div><span style="color:var(--text-muted);">Take Profit</span><br><b style="color:var(--green);">$${exitPlan.tp_price ? Number(exitPlan.tp_price).toFixed(2) : '—'}</b></div>
          </div>
        </div>` : '';

      const btnClass = isCall ? 'btn-primary' : 'btn-primary put';

      // Replace loading with full content
      view.querySelector('.view-body').innerHTML = `
        <div class="ctrl-box" style="margin-bottom:14px;">
          <div class="ctrl-box-title">Technical Indicators</div>
          <div class="indicator-grid">${indicatorsHtml}</div>
        </div>
        ${Object.keys(ts).length > 0 ? `
          <div class="ctrl-box" style="margin-bottom:14px;">
            <div class="ctrl-box-title">Trading Systems</div>
            <div class="ts-pills">${tsPillsHtml}</div>
          </div>` : ''}
        ${sentHtml}
        ${exitHtml}
        <div class="action-row">
          <button class="btn-secondary" id="analyze-ai-btn">🤖 Get AI Analysis</button>
          <button class="${btnClass}" id="analyze-trade-btn">⚡ Trade ${ticker} ${opp.option_type}</button>
        </div>`;

      // Attach action handlers
      document.getElementById('analyze-ai-btn')?.addEventListener('click', () => this.showAIResult(opp));
      document.getElementById('analyze-trade-btn')?.addEventListener('click', () => this.showTradeModal(opp));

    } catch (e) {
      view.querySelector('.view-body').innerHTML = `
        <div style="padding:20px; text-align:center; color:var(--red);">
          Analysis failed: ${e.message || 'Unknown error'}
        </div>
        <div class="action-row" style="padding:0 20px;">
          <button class="btn-secondary" id="analyze-back-err">← Back to Results</button>
        </div>`;
      document.getElementById('analyze-back-err')?.addEventListener('click', () => { view.style.display = 'none'; });
    }
  },

  // ============================================================
  // AI ANALYSIS VIEW
  // ============================================================
  async showAIResult(opp) {
    this.currentOpp = opp;
    const view = document.getElementById('ai-result-view');
    if (!view) return;

    const ticker = opp.ticker;
    const isCall = opp.option_type === 'Call';
    const expiryDate = opp.expiration_date
      ? new Date(opp.expiration_date).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric', timeZone: 'UTC' })
      : '—';

    // Determine strategy from scan mode
    let strategy = 'LEAP';
    if (this.scanMode === '0dte') strategy = '0DTE';
    else if (this.scanMode.startsWith('weekly')) strategy = 'WEEKLY';

    // Show loading
    view.innerHTML = `
      <div class="view-header">
        <button class="back-btn" id="ai-back">← Back to Analyze</button>
        <span class="view-ticker">${ticker}</span>
        <span class="view-subtitle">$${opp.strike_price ? opp.strike_price.toFixed(2) : '—'} ${opp.option_type} · ${expiryDate}</span>
      </div>
      <div class="view-body">
        <div class="ai-loading">
          <div class="ai-spinner"></div>
          <div style="font-size:0.85rem; color:var(--text-muted);">🤖 Consulting Perplexity AI (sonar-pro)...</div>
          <div style="font-size:0.72rem; color:var(--text-light);">This may take 10-15 seconds</div>
        </div>
      </div>`;
    view.style.display = 'block';

    document.getElementById('ai-back')?.addEventListener('click', () => {
      view.style.display = 'none';
    });

    try {
      const result = await api.getAIAnalysis(ticker, {
        strategy,
        expiry: opp.expiration_date,
        strike: opp.strike_price,
        type: opp.option_type
      });

      if (!result.success || !result.ai_analysis) {
        throw new Error(result.error || 'AI analysis unavailable');
      }

      const ai = result.ai_analysis;
      const score = ai.score || 0;
      const verdict = ai.verdict || 'RISKY';
      const scoreClass = score >= 66 ? 'score-green' : score >= 41 ? 'score-amber' : 'score-red';
      const verdictClass = verdict === 'FAVORABLE' ? 'verdict-favorable' : verdict === 'AVOID' ? 'verdict-avoid' : 'verdict-risky';
      const thesisClass = verdict === 'FAVORABLE' ? '' : verdict === 'AVOID' ? ' avoid' : ' risky';
      const summaryText = ai.summary || '';
      const thesis = ai.thesis || '';
      const risks = ai.risks || [];
      const analysis = ai.analysis || '';
      const btnClass = isCall ? 'btn-primary' : 'btn-primary put';

      // Parse analysis sections from markdown
      const sections = this.parseAIAnalysisSections(analysis);

      // Risks HTML
      const risksHtml = risks.length > 0 ? `
        <div class="ctrl-box" style="margin-bottom:14px; border-color:var(--red-border); background:var(--red-bg);">
          <div class="ctrl-box-title" style="color:var(--red);">⚠ Identified Risks</div>
          <ul style="margin:0; padding-left:18px; font-size:0.78rem; line-height:1.8; color:var(--text);">
            ${risks.map(r => `<li>${r}</li>`).join('')}
          </ul>
        </div>` : '';

      // Build sections HTML
      let sectionsHtml = '';
      if (sections.length > 0) {
        sectionsHtml = `
          <div class="ctrl-box" style="margin-bottom:14px;">
            <div class="ctrl-box-title">🤖 Full AI Analysis</div>
            <div style="font-size:0.75rem; line-height:1.8; color:var(--text);">
              ${sections.map(s => `
                <div class="ai-section">
                  <div class="ai-section-title">${s.title}</div>
                  <div class="ai-section-body${s.colorClass ? ' ' + s.colorClass : ''}">${s.content}</div>
                </div>`).join('')}
            </div>
          </div>`;
      } else if (analysis) {
        // Fallback: show raw analysis
        sectionsHtml = `
          <div class="ctrl-box" style="margin-bottom:14px;">
            <div class="ctrl-box-title">🤖 Full AI Analysis</div>
            <div style="font-size:0.75rem; line-height:1.8; color:var(--text); white-space:pre-wrap;">${analysis.replace(/</g, '&lt;').replace(/>/g, '&gt;')}</div>
          </div>`;
      }

      // Update header with verdict + score
      view.querySelector('.view-header').innerHTML = `
        <button class="back-btn" id="ai-back2">← Back to Analyze</button>
        <span class="view-ticker">${ticker}</span>
        <span class="view-subtitle">$${opp.strike_price ? opp.strike_price.toFixed(2) : '—'} ${opp.option_type} · ${expiryDate}</span>
        <span class="scan-type-badge badge-${strategy.toLowerCase()}">${strategy}</span>
        <span class="verdict-badge ${verdictClass}" style="margin-left:auto;">✓ ${verdict}</span>
        <div style="display:flex; align-items:baseline; gap:4px;">
          <div class="card-score ${scoreClass}" style="width:44px;height:44px;font-size:1rem;">${score}</div>
          <span style="font-size:0.7rem; color:var(--text-light);">/100</span>
        </div>`;

      // Render body
      view.querySelector('.view-body').innerHTML = `
        ${thesis ? `<div class="thesis-callout${thesisClass}">💡 <strong>Thesis:</strong> ${thesis}</div>` : ''}
        ${summaryText ? `
          <div class="ctrl-box" style="margin-bottom:14px;">
            <div class="ctrl-box-title">Summary</div>
            <div style="font-size:0.78rem; line-height:1.7; color:var(--text);">${summaryText}</div>
          </div>` : ''}
        ${risksHtml}
        ${sectionsHtml}
        <div class="data-sources">
          <span>🧠 <b>Model:</b> Perplexity sonar-pro</span>
          <span>🎭 <b>Persona:</b> ${strategy === '0DTE' ? '0DTE Sniper' : strategy === 'WEEKLY' ? 'Weekly Swing Trader' : 'LEAPS Value Investor'}</span>
          <span>📰 <b>News:</b> Finnhub</span>
          <span>📊 <b>Technicals:</b> Schwab API</span>
          <span>🌡️ <b>Temp:</b> 0.1</span>
        </div>
        <div class="action-row">
          <button class="btn-secondary" id="ai-back-btn">← Back to Analyze</button>
          <button class="${btnClass}" id="ai-trade-btn">⚡ Trade ${ticker} ${opp.option_type}</button>
        </div>`;

      // Handlers
      document.getElementById('ai-back2')?.addEventListener('click', () => { view.style.display = 'none'; });
      document.getElementById('ai-back-btn')?.addEventListener('click', () => { view.style.display = 'none'; });
      document.getElementById('ai-trade-btn')?.addEventListener('click', () => this.showTradeModal(opp));

    } catch (e) {
      view.querySelector('.view-body').innerHTML = `
        <div style="padding:20px; text-align:center; color:var(--red);">
          AI Analysis failed: ${e.message || 'Unknown error'}
        </div>
        <div class="action-row" style="padding:0;">
          <button class="btn-secondary" id="ai-back-err">← Back</button>
        </div>`;
      document.getElementById('ai-back-err')?.addEventListener('click', () => { view.style.display = 'none'; });
    }
  },

  parseAIAnalysisSections(text) {
    // Parse numbered sections from Perplexity markdown
    const sections = [];
    const sectionRegex = /(?:^|\n)(?:#{1,3}\s*)?(\d+)\.\s*\*{0,2}(.+?)\*{0,2}\s*(?:\n|$)([\s\S]*?)(?=\n(?:#{1,3}\s*)?\d+\.\s*\*{0,2}|$)/g;
    let match;
    while ((match = sectionRegex.exec(text)) !== null) {
      const title = `${match[1]}. ${match[2].replace(/\*/g, '').trim()}`;
      let content = match[3].trim();
      // Clean markdown
      content = content.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
      content = content.replace(/\n/g, '<br>');
      let colorClass = '';
      const titleLower = title.toLowerCase();
      if (titleLower.includes('news') || titleLower.includes('bull')) colorClass = 'green';
      else if (titleLower.includes('risk') || titleLower.includes('bear')) colorClass = 'red';
      else if (titleLower.includes('viability') || titleLower.includes('trade')) colorClass = 'amber';
      sections.push({ title, content, colorClass });
    }
    return sections;
  },

  // ============================================================
  // TRADE MODAL
  // ============================================================
  showTradeModal(opp) {
    this.currentOpp = opp;
    const overlay = document.getElementById('trade-modal-overlay');
    const modal = document.getElementById('trade-modal');
    if (!overlay || !modal) return;

    const isCall = opp.option_type === 'Call';
    const premium = opp.premium || 0;
    const exitPlan = (this.currentAnalysis && this.currentAnalysis.exit_plan) || {};
    const entryPrice = exitPlan.entry_price || premium;
    const slPrice = exitPlan.sl_price || (premium * 0.7).toFixed(2);
    const tpPrice = exitPlan.tp_price || (premium * 1.5).toFixed(2);
    const expiryDate = opp.expiration_date
      ? new Date(opp.expiration_date).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric', timeZone: 'UTC' })
      : '—';

    const btnClass = isCall ? 'btn-confirm-call' : 'btn-confirm-put';
    const btnText = isCall ? '✅ Confirm Call Trade' : '✅ Confirm Put Trade';

    modal.innerHTML = `
      <div class="trade-modal-header">
        <div style="font-size:1rem; font-weight:800;">⚡ Trade ${opp.ticker} ${opp.option_type}</div>
        <div style="font-size:0.78rem; color:var(--text-muted); margin-top:4px;">
          $${opp.strike_price ? opp.strike_price.toFixed(2) : '—'} ${opp.option_type} · ${expiryDate}
        </div>
      </div>
      <div class="trade-modal-body">
        <div style="display:grid; grid-template-columns:1fr 1fr; gap:8px; font-size:0.78rem; margin-bottom:14px;">
          <div><span style="color:var(--text-muted);">Premium</span><br><b>$${premium.toFixed(2)}</b></div>
          <div><span style="color:var(--text-muted);">Total Cost (1 contract)</span><br><b>$${(premium * 100).toFixed(2)}</b></div>
        </div>
        <div class="trade-params-grid">
          <div class="trade-param">
            <label>Entry Price</label>
            <input type="number" step="0.01" id="trade-entry" value="${Number(entryPrice).toFixed(2)}">
          </div>
          <div class="trade-param">
            <label>Stop Loss</label>
            <input type="number" step="0.01" id="trade-sl" value="${Number(slPrice).toFixed(2)}">
            <div class="param-hint" style="color:var(--red);">-${((1 - Number(slPrice) / Number(entryPrice)) * 100).toFixed(0)}%</div>
          </div>
          <div class="trade-param">
            <label>Take Profit</label>
            <input type="number" step="0.01" id="trade-tp" value="${Number(tpPrice).toFixed(2)}">
            <div class="param-hint" style="color:var(--green);">+${((Number(tpPrice) / Number(entryPrice) - 1) * 100).toFixed(0)}%</div>
          </div>
        </div>
        <div class="trade-edit-hint">✎ Edit any field above before confirming</div>
        <div class="trade-modal-actions">
          <button class="btn-cancel" id="trade-cancel">Cancel</button>
          <button class="${btnClass}" id="trade-confirm">${btnText}</button>
        </div>
      </div>`;

    overlay.style.display = 'flex';

    // Handlers
    document.getElementById('trade-cancel')?.addEventListener('click', () => {
      overlay.style.display = 'none';
    });
    overlay.addEventListener('click', (e) => {
      if (e.target === overlay) overlay.style.display = 'none';
    });
    document.getElementById('trade-confirm')?.addEventListener('click', () => this.submitTrade(opp));
  },

  // ============================================================
  // SUBMIT TRADE
  // ============================================================
  async submitTrade(opp) {
    const entryPrice = parseFloat(document.getElementById('trade-entry')?.value || opp.premium);
    const slPrice = parseFloat(document.getElementById('trade-sl')?.value || 0);
    const tpPrice = parseFloat(document.getElementById('trade-tp')?.value || 0);

    const confirmBtn = document.getElementById('trade-confirm');
    if (confirmBtn) {
      confirmBtn.disabled = true;
      confirmBtn.textContent = '⏳ Placing...';
    }

    try {
      const tradeData = {
        ticker: opp.ticker,
        option_symbol: opp.option_symbol || `${opp.ticker}_${opp.expiration_date}_${opp.strike_price}_${opp.option_type}`,
        option_type: opp.option_type,
        direction: opp.option_type === 'Call' ? 'LONG' : 'LONG',
        strike: opp.strike_price,
        expiry: opp.expiration_date,
        entry_price: entryPrice,
        qty: 1,
        sl_price: slPrice,
        tp_price: tpPrice,
        strategy: this.scanMode === '0dte' ? '0DTE' : this.scanMode.startsWith('weekly') ? 'WEEKLY' : 'LEAP',
        card_score: opp.opportunity_score || 0
      };

      const result = await api.placeTrade(tradeData);

      // Close trade modal
      document.getElementById('trade-modal-overlay').style.display = 'none';

      if (result.success) {
        this.showTradeResult('success', result.trade, result.broker_msg);
      } else {
        this.showTradeResult('failure', opp, null, result.error || 'Unknown error');
      }
    } catch (e) {
      document.getElementById('trade-modal-overlay').style.display = 'none';
      this.showTradeResult('failure', opp, null, e.message || 'Network error');
    }
  },

  // ============================================================
  // TRADE RESULT (SUCCESS / FAILURE)
  // ============================================================
  showTradeResult(type, data, brokerMsg, errorMsg) {
    const overlay = document.getElementById('trade-result-overlay');
    const modal = document.getElementById('trade-result-modal');
    if (!overlay || !modal) return;

    if (type === 'success') {
      const trade = data;
      modal.innerHTML = `
        <div class="trade-result-header success">
          <div style="font-size:1.5rem;">✓</div>
          <div style="font-size:1.1rem; font-weight:800;">Trade Placed Successfully</div>
        </div>
        <div class="trade-result-body">
          <div class="result-detail-grid">
            <span class="result-detail-label">Trade ID</span>
            <span class="result-detail-value">#${trade.id || '—'}</span>
            <span class="result-detail-label">Status</span>
            <span class="result-detail-value" style="color:var(--green);">${trade.status || 'OPEN'}</span>
            <span class="result-detail-label">Ticker</span>
            <span class="result-detail-value">${trade.ticker || '—'}</span>
            <span class="result-detail-label">Strike / Expiry</span>
            <span class="result-detail-value">$${trade.strike || '—'} · ${trade.expiry || '—'}</span>
            <span class="result-detail-label">Entry Price</span>
            <span class="result-detail-value">$${trade.entry_price ? Number(trade.entry_price).toFixed(2) : '—'}</span>
            <span class="result-detail-label">Quantity / Cost</span>
            <span class="result-detail-value">${trade.qty || 1} × $${trade.entry_price ? (Number(trade.entry_price) * 100).toFixed(2) : '—'}</span>
            <span class="result-detail-label">Stop Loss</span>
            <span class="result-detail-value" style="color:var(--red);">$${trade.sl_price ? Number(trade.sl_price).toFixed(2) : '—'}</span>
            <span class="result-detail-label">Take Profit</span>
            <span class="result-detail-value" style="color:var(--green);">$${trade.tp_price ? Number(trade.tp_price).toFixed(2) : '—'}</span>
          </div>
          ${brokerMsg ? `
            <div class="ctrl-box" style="margin-bottom:14px;">
              <div class="ctrl-box-title">🏦 Broker Confirmation</div>
              <div class="result-detail-grid">
                <span class="result-detail-label">Mode</span>
                <span class="result-detail-value">${trade.broker_mode || 'Paper'}</span>
                <span class="result-detail-label">Order ID</span>
                <span class="result-detail-value">${trade.tradier_order_id || '—'}</span>
                <span class="result-detail-label">OCO</span>
                <span class="result-detail-value" style="font-size:0.72rem;">${brokerMsg}</span>
              </div>
            </div>` : ''}
          <div class="result-actions">
            <button class="btn-back" id="result-back">← Back to Scanner</button>
            <button class="btn-view" id="result-portfolio">📊 View in Portfolio</button>
          </div>
        </div>`;
    } else {
      // Failure
      const opp = data;
      modal.innerHTML = `
        <div class="trade-result-header failure">
          <div style="font-size:1.5rem;">✗</div>
          <div style="font-size:1.1rem; font-weight:800;">Trade Failed</div>
        </div>
        <div class="trade-result-body">
          <div style="padding:12px; background:var(--red-bg); border:1px solid var(--red-border); border-radius:var(--radius-sm); margin-bottom:14px;">
            <div style="font-weight:700; color:var(--red); font-size:0.82rem; margin-bottom:6px;">⚠ Error Details</div>
            <div style="font-size:0.78rem; color:var(--text); line-height:1.6;">${errorMsg}</div>
          </div>
          <div style="padding:10px; background:var(--bg); border-radius:var(--radius-sm); margin-bottom:14px; font-size:0.7rem; color:var(--text-muted);">
            <div style="font-weight:600; margin-bottom:4px;">Other possible reasons:</div>
            <ul style="margin:0; padding-left:16px; line-height:1.8;">
              <li>Max open positions reached. Close a position first.</li>
              <li>Daily loss limit breached. Trading paused until tomorrow.</li>
              <li>Broker rejected order. Check buying power.</li>
              <li>Missing required fields in trade request.</li>
            </ul>
          </div>
          <div style="padding:10px; background:var(--bg); border-radius:var(--radius-sm); margin-bottom:14px; font-size:0.72rem; color:var(--text-light);">
            <div style="font-weight:600; margin-bottom:4px; color:var(--text-muted);">Failed Order</div>
            <div>${opp.ticker || '—'} · $${opp.strike_price ? opp.strike_price.toFixed(2) : '—'} ${opp.option_type || '—'}</div>
          </div>
          <div class="result-actions">
            <button class="btn-back" id="result-back">← Back to Scanner</button>
            <button class="btn-retry" id="result-retry">🔄 Retry Trade</button>
          </div>
        </div>`;
    }

    overlay.style.display = 'flex';

    // Handlers
    document.getElementById('result-back')?.addEventListener('click', () => {
      overlay.style.display = 'none';
      // Also close any open views
      document.getElementById('analyze-view').style.display = 'none';
      document.getElementById('ai-result-view').style.display = 'none';
    });
    document.getElementById('result-portfolio')?.addEventListener('click', () => {
      overlay.style.display = 'none';
      // Switch to portfolio tab
      document.querySelectorAll('.app-tab').forEach(t => t.classList.remove('active'));
      document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
      document.querySelector('[data-tab="portfolio"]')?.classList.add('active');
      document.getElementById('tab-portfolio')?.classList.add('active');
    });
    document.getElementById('result-retry')?.addEventListener('click', () => {
      overlay.style.display = 'none';
      if (this.currentOpp) this.showTradeModal(this.currentOpp);
    });
    overlay.addEventListener('click', (e) => {
      if (e.target === overlay) overlay.style.display = 'none';
    });
  }
};

// ============================================================
// AUTH CHECK
// ============================================================
async function checkAuth() {
  try {
    const result = await api.healthCheck();
    // If we get a 401 the api.request will redirect to /login
    return result && !result.error;
  } catch (e) {
    return true; // Don't block on health check failure
  }
}

// ============================================================
// BOOTSTRAP
// ============================================================
document.addEventListener('DOMContentLoaded', async () => {
  toast.init();
  // Auth check — redirect to /login on 401
  await checkAuth();
  // Init scanner
  await scanner.init();
});
