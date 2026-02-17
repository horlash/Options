# NewScanner v2.0 (AI-Powered Options Engine)

**The "Hedge Fund in a Box" Tool**

NewScanner is an advanced options analysis platform that combines **Technical Algorithms**, **Fundamental "Moat" Filtering**, and **AI Reasoning** to identify high-probability trades.

---

## 🚀 Key Features

### 1. Multi-Strategy Scanning
-   **Weekly "Sniper" Mode:** Finds high-momentum, short-term plays (0-45 DTE). Supports 0DTE logic with Gamma Risk analysis.
-   **LEAP "Investor" Mode:** Finds deep-value, long-term options (>150 DTE) on high-quality companies.
-   **Sector Rotation:** Scans entire sectors (e.g., Technology, Energy) to find the "Best of Breed" using relative strength.

### 2. The "Reasoning Engine" (AI)
-   Unlike varied script scanners, NewScanner uses an LLM-based reasoning engine.
-   **Personas:** Switches between "Sniper" (Aggressive), "Swing" (Balanced), and "Value" (Conservative) based on the trade.
-   **Thesis Generation:** Writes a 2-sentence rationale for every Top Pick.

### 3. Institutional Grade Logic
-   **Moat Check:** Automatically filters out "Junk" stocks (Low ROE, Low Margin) unless they are Indices/ETFs.
-   **Two-Tier Exemption:** Smartly handles VIX/SPX pricing anomalies (skipping profit math that fails on Futures-based products).
-   **Smart Money Skew:** Detects unusual institutional buying via Call/Put IV divergence.

---

## 🛠️ Prerequisites

-   **Python 3.10+** (Recommend 3.11)
-   **Docker Desktop** (Optional, but recommended for isolation)
-   **Schwab Developer Account** (For Real-Time Data)
-   **FMP / Finnhub Keys** (For Fundamentals & News)

---

## ⚡ Quick Start

### 1. Setup Environment
Copy the example config and add your API keys:
```bash
cp .env.example .env
# Edit .env and add SCHWAB, FMP, and FINNHUB keys.
```

### 2. Verify Data Feeds
Run the maintenance checks to ensure your Ticker Cache and Tokens are valid:
```bash
python backend/scripts/refresh_tickers_v2.py
```

### 3. Run the Backend
```bash
python backend/app.py
```
*Server runs at `http://localhost:5000`*

### 4. Launch Frontend
```bash
cd frontend
python -m http.server 8000
```
*UI accessible at `http://localhost:8000`*

---

## 📚 Documentation

We have comprehensive guides in the `docs/` folder:

-   **Start Here:** [User Guide](docs/USER_GUIDE.md)
-   **Setup:** [API Setup Guide](docs/API_SETUP.md)
-   **Maintenance:** [Maintenance Manual](docs/MAINTENANCE.md) (Token updates, Cache refreshes)
-   **Strategies:**
    -   [Weekly "Sniper" Logic](docs/WEEKLY_LOGIC_ENHANCED.md)
    -   [LEAP "Expert" Logic](docs/LEAP_STRATEGY_EXPERT.md)
    -   [Sector Scan Logic](docs/SECTOR_SCAN_LOGIC.md)
    -   [Index/ETF Handling](docs/INDEX_VS_PROFIT_LOGIC.md)
-   **AI:** [Reasoning Engine](docs/REASONING_ENGINE.md)
-   **Errors:** [Troubleshooting](docs/TROUBLESHOOTING.md)

---

## ⚠️ Important Notes

-   **Indices (VIX/SPX):** The scanner treats these differently. See `INDEX_VS_PROFIT_LOGIC.md`.
-   **API Limits:** FMP and Finnhub Free Tiers are supported but strictly rate-limited.
-   **Disclaimer:** This software is for **Research Purposes Only**. It is not financial advice.

---

**Version:** 2.0.0
**Last Updated:** February 2026
