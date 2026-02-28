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
  async getTickers() { return this.request('/data/tickers.json'); }
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
    const input = document.getElementById('watchlist-input');
    const dropdown = document.getElementById('watchlist-autocomplete');
    if (!input) return;

    // Load watchlist from API on start
    this.loadWatchlist();

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

    input.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        const ticker = input.value.trim().toUpperCase();
        if (ticker) {
          input.value = '';
          dropdown.style.display = 'none';
          this.addToWatchlist(ticker);
        }
      }
    });

    document.addEventListener('click', (e) => {
      if (!input.contains(e.target) && !dropdown.contains(e.target)) {
        dropdown.style.display = 'none';
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
    const container = document.getElementById('watchlist-chips');
    if (!container) return;
    if (!tickers || tickers.length === 0) {
      container.innerHTML = '<span style="font-size:0.72rem;color:var(--text-light);font-style:italic;">No tickers yet</span>';
      return;
    }
    container.innerHTML = tickers.map(t => `
      <span class="chip">
        ${t}
        <button class="chip-remove" data-ticker="${t}" title="Remove ${t}" aria-label="Remove ${t}">×</button>
      </span>
    `).join('');

    container.querySelectorAll('.chip-remove').forEach(btn => {
      btn.addEventListener('click', () => this.removeFromWatchlist(btn.dataset.ticker));
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
      <div class="${cardClass}">
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
            <span class="metric-label">Expiry</span>
            <span class="metric-val${urgentClass}">${expiryDate}</span>
          </div>
          <div class="metric">
            <span class="metric-label">Premium</span>
            <span class="metric-val">$${opp.premium ? opp.premium.toFixed(2) : '—'}</span>
          </div>
          <div class="metric">
            <span class="metric-label">Break Even</span>
            <span class="metric-val">$${breakEven ? breakEven.toFixed(2) : '—'}</span>
          </div>
          <div class="metric">
            <span class="metric-label">Days Left</span>
            <span class="metric-val${urgentClass}">${opp.days_to_expiry != null ? opp.days_to_expiry : '—'}</span>
          </div>
          <div class="metric">
            <span class="metric-label">Volume</span>
            <span class="metric-val">${(opp.volume || 0).toLocaleString()}</span>
          </div>
          <div class="metric">
            <span class="metric-label">Open Int</span>
            <span class="metric-val">${(opp.open_interest || 0).toLocaleString()}</span>
          </div>
        </div>
        ${tradingSystemsHtml}
        <div class="card-footer">
          <div class="card-badges">${badgesHtml}</div>
          <div class="card-source">${source}</div>
          ${tradeAreaHtml}
        </div>
      </div>`;
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
