// Scanner component
const scanner = {
    isScanning: false,
    scanMode: 'weekly-0', // Default to This Week
    tickers: [], // Full list of cached tickers

    async init() {
        console.log('Scanner initialized');
        this.initSmartSearch(); // Initialize search first
        this.initTabs(); // Initialize tabs first so buttons exist
        this.setupSectorScan();

        // Fix: Explicitly set mode to update UI label from 'Leaps' to 'This Week...'
        this.setMode('weekly-0');
    },

    // --- SMART SEARCH FUNCTIONALITY ---
    async initSmartSearch() {
        this.searchInput = document.getElementById('quick-scan-input');
        this.resultsList = document.getElementById('autocomplete-list');

        // 1. Load Data
        try {
            const response = await fetch('/api/data/tickers.json');
            const data = await response.json();
            this.tickers = data.tickers || [];
            console.log(`✅ Smart Search: Loaded ${this.tickers.length} tickers`);
        } catch (e) {
            console.error("Failed to load tickers:", e);
        }

        if (!this.searchInput || !this.resultsList) return;

        // 2. Event Listeners
        this.searchInput.addEventListener('input', (e) => {
            const query = e.target.value;
            if (query.length > 0) {
                const matches = this.searchTickers(query);
                this.showResults(matches);
            } else {
                this.resultsList.style.display = 'none';
            }
        });

        // Close when clicking outside
        document.addEventListener('click', (e) => {
            if (e.target !== this.searchInput && e.target !== this.resultsList) {
                this.resultsList.style.display = 'none';
            }
        });
    },

    searchTickers(query) {
        if (!query || query.length < 1) return [];
        query = query.toUpperCase();

        // Priority 1: Starts with Symbol
        const symbolMatches = this.tickers.filter(t => t.symbol.toUpperCase().startsWith(query));

        // Priority 2: Starts with Name
        const nameStartMatches = this.tickers.filter(t =>
            !symbolMatches.includes(t) &&
            (t.name || '').toUpperCase().startsWith(query)
        );

        // Priority 3: Contains Name (Optional but helpful)
        const nameContainsMatches = this.tickers.filter(t =>
            !symbolMatches.includes(t) &&
            !nameStartMatches.includes(t) &&
            (t.name || '').toUpperCase().includes(query)
        );

        return [...symbolMatches, ...nameStartMatches, ...nameContainsMatches].slice(0, 8);
    },

    showResults(matches) {
        if (matches.length === 0) {
            this.resultsList.style.display = 'none';
            return;
        }

        this.resultsList.innerHTML = matches.map(t => {
            return `
                <div class="autocomplete-item" onclick="scanner.selectTicker('${t.symbol}')">
                    <span class="item-symbol">${t.symbol}</span>
                    <span class="item-name">${t.name}</span>
                </div>
            `;
        }).join('');

        this.resultsList.style.display = 'block';
    },

    selectTicker(symbol) {
        this.searchInput.value = symbol;
        this.resultsList.style.display = 'none';
        // Optional: Auto-scan on select?
        // For now just populate input as requested
    },

    /**
     * Validate a ticker symbol against format rules.
     * Only enforces regex (1-5 uppercase letters). The cached ticker list
     * is NOT used as a gate because it's incomplete — e.g. leveraged ETFs
     * like NVDL, TSLL are valid but missing from tickers.json.
     * @param {string} ticker - Uppercase ticker to validate
     * @returns {boolean} true if valid format
     */
    isValidTicker(ticker) {
        if (!ticker || typeof ticker !== 'string') return false;
        ticker = ticker.trim().toUpperCase();
        // Must be 1-5 uppercase letters only (blocks "MSTRAAPL", "XYZ999", etc.)
        return /^[A-Z]{1,5}$/.test(ticker);
    },

    initTabs() {
        console.log('Initializing tabs with dates...');
        // Helper to get next Friday date string
        const getFridayDate = (weeksOut) => {
            const today = new Date();
            const day = today.getDay();
            const daysUntilFriday = (5 - day + 7) % 7; // 5 is Friday
            const target = new Date(today);
            target.setDate(today.getDate() + daysUntilFriday + (weeksOut * 7));
            return target.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }); // Jan 24
        };

        // Update Button Labels
        const setLabel = (id, weeksOut) => {
            const btn = document.getElementById(id);
            if (btn) {
                const dateStr = getFridayDate(weeksOut);
                let label = "This Week";
                if (weeksOut === 1) label = "Next Week";
                if (weeksOut === 2) label = "Next 2 Weeks";
                // Added space before bracket as requested: "This Week (Jan 24)"
                btn.innerText = `${label} (${dateStr})`;
            }
        };

        setLabel('mode-weekly-0', 0);
        setLabel('mode-weekly-1', 1);
        setLabel('mode-weekly-2', 2);
        // 0DTE is static label
    },

    setMode(mode) {
        this.scanMode = mode;
        console.log(`Scanner mode set to: ${mode}`);

        // Update Opportunities Label
        const labelEl = document.getElementById('opportunities-mode-label');
        if (labelEl) {
            if (mode === 'leaps') {
                labelEl.textContent = 'Leaps';
            } else if (mode === '0dte') {
                labelEl.textContent = '⚡ 0DTE Intraday';
                labelEl.style.color = '#ff4d4d'; // Red alert color
            } else {
                // Parse mode to get date from the button for consistency
                // e.g. mode-weekly-0
                const btnId = `mode-${mode}`;
                const btn = document.getElementById(btnId);
                if (btn) {
                    // Extract text "This Week (Jan 24)"
                    // Ensure we don't double wrap or anything
                    labelEl.textContent = btn.textContent;
                }
            }
        }
    },

    // Industry Mapping
    INDUSTRIES: {
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
    },

    setupSectorScan() {
        const btn = document.getElementById('btn-sector-scan');
        const sectorSelect = document.getElementById('sector-select');
        const industrySelect = document.getElementById('industry-select');

        if (!btn || !sectorSelect) return;

        // Handle Sector Change -> Populate Subsectors
        sectorSelect.addEventListener('change', (e) => {
            const sector = e.target.value;
            industrySelect.innerHTML = '<option value="">Any Subsector</option>';

            if (sector && this.INDUSTRIES[sector]) {
                this.INDUSTRIES[sector].sort().forEach(ind => {
                    const opt = document.createElement('option');
                    opt.value = ind;
                    opt.textContent = ind;
                    industrySelect.appendChild(opt);
                });
                industrySelect.style.display = 'block';
            } else {
                industrySelect.style.display = 'none';
            }
        });

        btn.addEventListener('click', async (e) => {
            e.preventDefault();
            const sector = sectorSelect.value;
            const industry = industrySelect.value;
            const minCap = document.getElementById('cap-select').value;
            const minVol = document.getElementById('vol-select').value;

            if (!sector) {
                toast.error("Please select a sector");
                return;
            }

            // NEW: Strict 0DTE Constraint
            if (this.scanMode === '0dte') {
                toast.error("0DTE Sector Scan Not Supported");
                return;
            }

            this.runSectorScan(sector, minCap, minVol, industry);
        });
    },

    async runSectorScan(sector, minCap, minVol, industry) {
        if (this.isScanning) {
            toast.info('Scan already in progress');
            return;
        }

        // Determine weeksOut from current mode
        let weeksOut = null;
        if (this.scanMode !== 'leaps') {
            // mode is 'weekly-0', 'weekly-1', etc.
            weeksOut = parseInt(this.scanMode.split('-')[1]);
        }

        const modeLabel = weeksOut === null ? "LEAPS" : `Weekly (+${weeksOut})`;
        const indLabel = industry ? ` | ${industry}` : "";

        this.isScanning = true;
        this.showProgress();
        toast.info(`Scanning Top Picks in ${sector}${indLabel} (${modeLabel})...`);

        try {
            const result = await api.runSectorScan(sector, minCap, minVol, weeksOut, industry);

            if (result.success) {
                toast.success(`Found ${result.results.length} sector opportunities!`);
                opportunities.render(result.results);
            } else {
                toast.error(result.error || 'Sector scan failed');
            }
        } catch (error) {
            console.error('Error in sector scan:', error);
            toast.error('Sector scan error');
        } finally {
            this.isScanning = false;
            this.hideProgress();
        }
    },

    async run() {
        if (this.isScanning) {
            toast.info('Scan already in progress');
            return;
        }

        this.isScanning = true;
        this.showProgress();

        try {
            let result;
            if (this.scanMode === 'leaps') {
                toast.info('Starting LEAP scan...');
                result = await api.runScan();
            } else if (this.scanMode === '0dte') {
                toast.error('Bulk 0DTE Scan not yet supported. Please scan individual tickers.');
                this.isScanning = false;
                this.hideProgress();
                return;
            } else {
                // weekly-0, weekly-1, etc.
                const weeksOut = parseInt(this.scanMode.split('-')[1]);
                toast.info(`Starting Weekly Scan (+${weeksOut} weeks)...`);
                result = await api.runDailyScan(weeksOut);
            }

            if (result.success) {
                toast.success(`Scan complete! Found opportunities in ${result.results.length} tickers`);
                opportunities.render(result.results);
            } else {
                toast.error(result.error || 'Scan failed');
            }
        } catch (error) {
            console.error('Error running scan:', error);
            toast.error('Error running scan');
        } finally {
            this.isScanning = false;
            this.hideProgress();
        }
    },

    async scanTicker(ticker) {
        if (this.isScanning) {
            toast.info('Scan already in progress');
            return;
        }

        if (!ticker || typeof ticker !== 'string') {
            console.error('Invalid ticker provided to scanTicker');
            return;
        }

        ticker = ticker.trim().toUpperCase();

        if (!ticker) {
            toast.error('Please enter a ticker symbol');
            return;
        }

        // Validate ticker format and existence
        if (!this.isValidTicker(ticker)) {
            toast.error(`Unknown ticker "${ticker}". Use the autocomplete to find valid symbols.`);
            return;
        }

        toast.info(`Scanning ${ticker}...`);

        this.isScanning = true;
        this.showProgress();

        try {
            let result;
            if (this.scanMode === 'leaps') {
                toast.info(`Scanning ${ticker} (LEAPS)...`);
                result = await api.scanTicker(ticker);
            } else if (this.scanMode === '0dte') {
                toast.info(`⚡ Scanning ${ticker} (0DTE)...`);
                result = await api.scan0DTE(ticker);
            } else {
                const weeksOut = parseInt(this.scanMode.split('-')[1]);
                toast.info(`Scanning ${ticker} (Weekly +${weeksOut})...`);
                result = await api.scanTickerDaily(ticker, weeksOut);
            }

            if (result.success) {
                toast.success(`Scan complete for ${ticker}`);
                opportunities.render([result.result]);
            } else {
                toast.error(result.error || `Failed to scan ${ticker}`);
            }
        } catch (error) {
            console.error(`Error scanning ${ticker}:`, error);
            toast.error(`Error scanning ${ticker}`);
        } finally {
            this.isScanning = false;
            this.hideProgress();
        }
    },

    showProgress() {
        const progressEl = document.getElementById('scan-progress');
        if (progressEl) {
            progressEl.classList.remove('hidden');
        }

        // Disable all ticker scan buttons contextually if possible, 
        // but for now just safely handle missing btn
        const runScanBtn = document.getElementById('run-scan-btn');
        if (runScanBtn) {
            runScanBtn.disabled = true;
            runScanBtn.style.opacity = '0.5';
        }
    },

    hideProgress() {
        const progressEl = document.getElementById('scan-progress');
        if (progressEl) {
            progressEl.classList.add('hidden');
        }

        const runScanBtn = document.getElementById('run-scan-btn');
        if (runScanBtn) {
            runScanBtn.disabled = false;
            runScanBtn.style.opacity = '1';
        }
    }
};
