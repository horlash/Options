# User Guide
**Last Updated:** 2026-02-16
**Version:** NewScanner v3.0 (Strict ORATS Mode)

Welcome to the NewScanner! This guide will help you get the most out of the application.

## Feature Overview

### 1. Weekly Scanner (Momentum)
-   **Goal:** Find "Sniper Entries" for short-term gains (0-45 Days).
-   **Includes:** 0DTE logic (if days=1), Gamma Walls, and Smart Money Flow.

### 2. LEAP Scanner (Investment)
-   **Goal:** Find long-term "Deep Value" calls (>150 Days).
-   **Includes:** ROE/Margin checks, Multi-Timeframe Trend alignment.

### 3. Sector Scanner (Rotation) [NEW]
-   **Goal:** Find the "Best House in the Best Neighborhood".
-   **Output:** Top 3 tickers in a sector (e.g., Energy, Tech) with AI Analysis.
-   **Fallback:** If FMP is down, uses a local cached list.

---

## Getting Started

### 1. Launch the Application

Start the backend server:
```bash
python backend/app.py
```

Open the frontend in your browser:
```bash
cd frontend
python -m http.server 8000
```
Navigate to `http://localhost:8000`

### 2. Build Your Watchlist (Weekly/LEAP Mode)

**To add a ticker:**
1. Type the stock symbol (e.g., AAPL).
2. Click "+" Add.
3. The scanner will automatically skip "Junk" tickers that fail fundamental checks (unless it's an Index/ETF).

### 3. Running a Sector Scan

1. Click the **"Sector Scan"** tab.
2. Select a Sector from the dropdown (e.g., "Technology").
3. Click "Scan".
4. Wait ~30 seconds. FMP will filter thousands of stocks, rank them, and the **AI** will analyze the Top 3.
5. Review the **"AI Thesis"** card to see *why* a stock was chosen.

---

## Interpreting Results

### Opportunity Cards
-   **Score (0-100):** The Algo's raw mathematical rating.
-   **Badges:**
    -   `EPS Growth ↗`: Strong fundamentals.
    -   `Smart Money 🏦`: Unusual options volume or positive skew.
    -   `Gamma Boss 🧱`: Approaching a Gamma Wall.

### AI Thesis (Reasoning Engine)
For Top Picks, you will see a text block explaining the trade:
-   **"The Setup":** Why the technicals look good.
-   **"The Risk":** What could go wrong (e.g., Earnings coming up).
-   **"The Verdict":** A Conviction Score (e.g., "High Confidence: 85%").

---

## Understanding the Scoring System

The system uses a **Hybrid Scoring Model**:

1.  **Base Score (Hard Data):** We calculate a raw score (0-100) based on:
    -   **Technicals (40%)**: RSI, MACD, Bollinger Bands.
    -   **Sentiment (30%)**: News sentiment + Analyst Ratings.
    -   **Volume (10%)**: "Surging" volume adds points.
    -   **Trend (20%)**: Moving Average alignment.

2.  **AI Adjustment (Soft Data):**
    -   The AI receives the Base Score (e.g., 75).
    -   It reads the specific news headlines and earnings transcripts.
    -   It adjusts the score by **±20 points** (e.g., +5 for a new contract announcement = Final 80).
    
**Why this matters:** The score is grounded in math but flexible enough to capture human-like nuance.

---

## Troubleshooting

### "Using Free Tier" Message
This is normal. It means Finnhub didn't have specific sentiment data, so we fell back to analyzing headlines manually.

### "No Opportunities Found"
-   **Watchlist:** Try adding more tickers or diverse sectors.
-   **Filters:** Your `MIN_PROFIT_POTENTIAL` in `.env` might be too high (Default: 15).

---

## FAQ

**Q: Why did VIX return results now?**
A: We added a specific exemption for Index pricing models.

**Q: Can I change the $2000 limit?**
A: Yes, modify `MAX_INVESTMENT_PER_POSITION` in `.env`.

**Q: Is 0DTE scanning safe?**
A: It is "High Risk". The AI switches to "Sniper Persona" to warn you about Gamma lines.

## Next Steps
1. Build a diverse watchlist
2. Run a Sector Scan to find new ideas
3. Use the LEAP scanner for your core portfolio
