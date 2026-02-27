// Watchlist component
const watchlist = {
    maxItems: 30,
    tickers: [], // For autocomplete

    async init() {
        console.log("Watchlist Initialized");
        this.cacheElements();
        this.bindEvents();

        // Initial load
        await this.load();

        // Load tickers for autocomplete (Reuse scanner logic or fetch)
        await this.loadTickers();
    },

    cacheElements() {
        this.input = document.getElementById('watchlist-input');
        this.resultsList = document.getElementById('watchlist-autocomplete-list');
        this.container = document.getElementById('watchlist-container');
        this.countDisplay = document.getElementById('watchlist-count-display');
        this.headerCount = document.getElementById('watchlist-count');
    },

    bindEvents() {
        if (!this.input) return;

        // Autocomplete
        this.input.addEventListener('input', (e) => {
            const query = e.target.value;
            if (query.length > 0) {
                const matches = this.searchTickers(query);
                this.showResults(matches);
            } else {
                this.hideResults();
            }
        });

        // Close autocomplete when clicking outside
        document.addEventListener('click', (e) => {
            if (e.target !== this.input && e.target !== this.resultsList) {
                this.hideResults();
            }
        });

        // Add button
        const addBtn = document.getElementById('btn-add-watchlist');
        if (addBtn) {
            addBtn.addEventListener('click', (e) => {
                e.preventDefault();
                this.add(this.input.value);
            });
        }
    },

    async load() {
        try {
            const result = await api.getWatchlist();

            if (result.success) {
                this.render(result.watchlist);
            } else {
                if (typeof toast !== 'undefined') toast.error('Failed to load watchlist');
            }
        } catch (error) {
            console.error('Error loading watchlist:', error);
            if (typeof toast !== 'undefined') toast.error('Error loading watchlist');
        }
    },

    render(watchlistData) {
        if (!this.container) return;

        const count = watchlistData ? watchlistData.length : 0;
        if (this.countDisplay) this.countDisplay.textContent = count;
        if (this.headerCount) this.headerCount.textContent = count;

        if (!watchlistData || watchlistData.length === 0) {
            this.container.innerHTML = `
                <div class="empty-state-small">Watchlist is empty</div>
            `;
            return;
        }

        this.container.innerHTML = watchlistData.map(item => `
            <div class="watchlist-tag" onclick="watchlist.scanTicker('${item.ticker}')">
                <span class="watchlist-tag-symbol">${item.ticker}</span>
                <button class="watchlist-tag-remove" onclick="event.stopPropagation(); watchlist.remove('${item.ticker}')">&times;</button>
            </div>
        `).join('');
    },

    async add(ticker) {
        if (!ticker || ticker.trim() === '') {
            if (typeof toast !== 'undefined') toast.error('Please enter a ticker symbol');
            return;
        }
        ticker = ticker.trim().toUpperCase();

        // BUG-2 FIX: Validate ticker format (1-5 uppercase letters)
        if (!/^[A-Z]{1,5}$/.test(ticker)) {
            if (typeof toast !== 'undefined') toast.error(`Invalid ticker "${ticker}". Use 1-5 letters (e.g. AAPL, MSFT).`);
            return;
        }

        try {
            const result = await api.addToWatchlist(ticker);

            if (result.success) {
                if (typeof toast !== 'undefined') toast.success(result.message);
                this.input.value = ''; // Clear input
                this.load(); // Reload to update UI and count
            } else {
                // BUG-5 FIX: Show the actual error/message from backend (e.g. "already in watchlist")
                if (typeof toast !== 'undefined') toast.error(result.message || result.error || 'Failed to add ticker');
            }
        } catch (error) {
            console.error('Error adding ticker:', error);
            if (typeof toast !== 'undefined') toast.error('Error adding ticker');
        }
    },

    async remove(ticker) {
        try {
            const result = await api.removeFromWatchlist(ticker);

            if (result.success) {
                if (typeof toast !== 'undefined') toast.success(result.message);
                this.load();
            } else {
                if (typeof toast !== 'undefined') toast.error(result.message || 'Failed to remove ticker');
            }
        } catch (error) {
            console.error('Error removing ticker:', error);
            if (typeof toast !== 'undefined') toast.error('Error removing ticker');
        }
    },

    scanTicker(ticker) {
        if (typeof scanner !== 'undefined') {
            scanner.scanTicker(ticker);
        } else {
            console.error("Scanner not initialized");
        }
    },

    // --- Autocomplete Helpers ---

    async loadTickers() {
        try {
            if (window.scanner && window.scanner.tickers && window.scanner.tickers.length > 0) {
                this.tickers = window.scanner.tickers;
            } else {
                const response = await fetch('/api/data/tickers.json');
                const data = await response.json();
                this.tickers = data.tickers || [];
            }
            console.log(`✅ Watchlist: Loaded ${this.tickers.length} tickers for autocomplete`);
        } catch (e) {
            console.error("Failed to load tickers:", e);
        }
    },

    searchTickers(query) {
        if (!query || query.length < 1) return [];
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

    showResults(matches) {
        if (!this.resultsList) return;

        if (matches.length === 0) {
            this.hideResults();
            return;
        }

        this.resultsList.innerHTML = matches.map(t => {
            return `
                <div class="autocomplete-item" onclick="watchlist.selectTicker('${t.symbol}')">
                    <span class="item-symbol">${t.symbol}</span>
                    <span class="item-name">${t.name}</span>
                </div>
            `;
        }).join('');

        this.resultsList.style.display = 'block';
    },

    hideResults() {
        if (this.resultsList) this.resultsList.style.display = 'none';
    },

    selectTicker(symbol) {
        this.input.value = symbol;
        this.hideResults();
        // Option to verify exist check or auto-add
    }
};
