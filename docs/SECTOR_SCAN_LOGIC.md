# Sector Scan Logic
**Last Updated:** 2026-02-16
**Version:** NewScanner v2.0

## Overview
The Sector Scan is a specialized tool designed to find the "Best in Breed" stocks within a specific industry. unlike the Weekly or LEAP scanners which look for *any* good chart, the Sector Scan looks for *relative strength* within a sector.

## Architecture

1.  **Data Source:** 
    -   **FMP API (Financial Modeling Prep):** Used for the initial "Stock Screener" to filter by Sector, Industry, Market Cap, and Volume.
    -   **Local Cache (`tickers.json`):** Limits the FMP search to our known universe of 10,000+ liquid tickers.
    
2.  **Logic Flow:**
    -   **Step 1: Filtering.** We request all stocks in "Technology" (for example) with Market Cap > $2B and Volume > 500k.
    -   **Step 2: Scoring.** We apply our proprietary scoring model (Technical + Sentiment) to rank them.
    -   **Step 3: Categorization.** We tag each result as:
        -   **Tactical:** High Momentum, Breakout setup.
        -   **Value:** Good Fundamentals, but maybe slower moving.
        -   **Momentum:** Pure trend play.
    -   **Step 4: AI Analysis.** The **Top 3** results are sent to the Reasoning Engine for a "Thesis" generation.

## AI Integration (Top 3)
To keep the scan fast, we only perform deep AI analysis on the Top 3 candidates.
-   **Input:** Technical Data, News Headlines, Greeks.
-   **Output:** A 2-sentence "Thesis" explaining *why* this stock is the winner of the sector.

## Filtering Criteria
-   **Market Cap:** > $2 Billion (Mid/Large Cap focus).
-   **Volume:** > 500,000 avg volume (Liquidity focus).
-   **Price:** > $5 (No penny stocks).

## Usage
Select a Sector from the dropdown (e.g., "Energy", "Finance") and click "Scan".
