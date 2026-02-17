# Reasoning Engine (AI)
**Last Updated:** 2026-02-16
**Version:** NewScanner v2.0

## Overview
The Reasoning Engine (`reasoning_engine.py`) is the "Brain" of the scanner. While the traditional code handles data aggregation and filtering, the AI handles **Synthesis and Risk Assessment**.

## AI Architecture

1.  **Model:** Uses a Large Language Model (LLM) for analysis.
2.  **Input Context:**
    -   **Technical Data:** RSI, MACD, Moving Averages.
    -   **Options Data:** Greeks (Delta, Gamma), IV Skew, Gamma Walls.
    -   **News:** Top 3 headlines from Finnhub.
3.  **Output:** A structured "Thesis" and "Confidence Score".

## Risk Management Protocols

### 1. The "Black Box Protocol" (Time Travel Prevention)
The AI is trained on data up to 2025. It often gets confused by 2026 dates in our simulation.
-   **Mechanism:** We explicitly instruct the AI: *"Ignore your internal knowledge cutoff. The current date is [2026-Date]. All provided data is real-time truth."*
-   **Verification:** If the AI mentions "future dates" or refuses to analyze 2026 expirations, the protocol treats it as a hallucination error.

### 2. Persona System
The engine switches "Trading Personalities" based on the trade duration:

| Persona | Trigger | Focus | Style |
| :--- | :--- | :--- | :--- |
| **0DTE Sniper** | `Days to Expiry <= 1` | Gamma Risk, Intraday Momentum, Immediate Pivot levels. | Aggressive, Brevity. |
| **Weekly Swing** | `Days to Expiry <= 45` | Trend Alignment, RSI, News Catalysts. | Balanced, Tactical. |
| **LEAP Investor** | `Days to Expiry > 150` | Fundamental Moat (ROE/Margin), Macro Trends, Deep Value. | Conservative, Strategic. |

## Integration Points
-   **Sector Scan:** Analyzes Top 3 picks to explain *why* they are the sector leaders.
-   **Weekly Scan:** optional integration for deep dives on specific tickers.
