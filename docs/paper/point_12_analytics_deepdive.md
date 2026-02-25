# Point 12: Analytics & Performance Reporting — Deep Dive (Double Deep)

> **Status:** IMPLEMENTED ✅ (Phase 5 complete — 32/32 tests pass)  
> **Date:** Feb 20, 2026  
> **Depends On:** Point 1 (Database), Point 6 (Backtesting Data), Point 11 (Lifecycle)  
> **Findings:** [implementation_findings.md](file:///c:/Users/olasu/.gemini/antigravity/Options-feature/docs/paper/implementation_findings.md#phase-5-analytics--performance-reporting)

---

## 🎯 The Goal: "Know If You're Actually Good"
Pretty charts are useless without the right metrics.
This point defines exactly what we measure, how we calculate it, and how we display it.

---

## 📊 Core Metrics: The Numbers That Matter

### Metric Definitions

| # | Metric | Formula | What It Tells You |
|---|--------|---------|-------------------|
| 1 | **Win Rate** | `wins / total_trades * 100` | % of trades that made money |
| 2 | **Profit Factor** | `gross_profit / gross_loss` | $ won per $ lost (>1.5 = good) |
| 3 | **Expectancy** | `(win_rate * avg_win) - (loss_rate * avg_loss)` | Expected $ per trade |
| 4 | **Avg Win** | `sum(pnl where pnl > 0) / count(wins)` | Mean profit on winners |
| 5 | **Avg Loss** | `sum(pnl where pnl < 0) / count(losses)` | Mean loss on losers |
| 6 | **Largest Win** | `max(pnl)` | Best single trade |
| 7 | **Largest Loss** | `min(pnl)` | Worst single trade |
| 8 | **Avg Hold Time** | `avg(closed_at - created_at)` | How long positions stay open |
| 9 | **Max Drawdown** | `max peak-to-trough decline` | Worst losing streak impact |
| 10 | **Total P&L** | `sum(realized_pnl)` | Net result |

---

## 🗄️ SQL Queries: The Engine Behind Each Metric

### 1. Summary Stats (Single Query)

```sql
-- backend/queries/analytics.py
SUMMARY_STATS_QUERY = """
SELECT
    COUNT(*) AS total_trades,
    COUNT(*) FILTER (WHERE realized_pnl > 0) AS wins,
    COUNT(*) FILTER (WHERE realized_pnl < 0) AS losses,
    COUNT(*) FILTER (WHERE realized_pnl = 0) AS breakeven,
    
    ROUND(
        COUNT(*) FILTER (WHERE realized_pnl > 0)::numeric 
        / NULLIF(COUNT(*), 0) * 100, 1
    ) AS win_rate,
    
    ROUND(
        SUM(realized_pnl) FILTER (WHERE realized_pnl > 0)::numeric
        / NULLIF(ABS(SUM(realized_pnl) FILTER (WHERE realized_pnl < 0))::numeric, 0), 2
    ) AS profit_factor,
    
    ROUND(AVG(realized_pnl) FILTER (WHERE realized_pnl > 0)::numeric, 2) AS avg_win,
    ROUND(AVG(realized_pnl) FILTER (WHERE realized_pnl < 0)::numeric, 2) AS avg_loss,
    
    MAX(realized_pnl) AS largest_win,
    MIN(realized_pnl) AS largest_loss,
    
    ROUND(SUM(realized_pnl)::numeric, 2) AS total_pnl,
    
    ROUND(
        AVG(EXTRACT(EPOCH FROM (closed_at - created_at)) / 3600)::numeric, 1
    ) AS avg_hold_hours
FROM paper_trades
WHERE status IN ('CLOSED', 'EXPIRED')
  AND username = current_setting('app.current_user', true)
"""
```

> [!IMPORTANT]
> **Bug found during implementation:** `ABS()` returns `double precision`, but `ROUND(double, int)` has no overload in Postgres. Must cast `ABS(...)::numeric` before passing to `NULLIF()`. See [implementation_findings.md → Bug #1](file:///c:/Users/olasu/.gemini/antigravity/Options-feature/docs/paper/implementation_findings.md).

### 2. Equity Curve (Cumulative P&L Over Time)

```sql
EQUITY_CURVE_QUERY = """
SELECT
    TO_CHAR(DATE(closed_at), 'YYYY-MM-DD') AS trade_date,
    ROUND(SUM(realized_pnl)::numeric, 2) AS daily_pnl,
    ROUND(
        SUM(SUM(realized_pnl)) OVER (ORDER BY DATE(closed_at))::numeric, 2
    ) AS cumulative_pnl
FROM paper_trades
WHERE status IN ('CLOSED', 'EXPIRED')
  AND username = current_setting('app.current_user', true)
GROUP BY DATE(closed_at)
ORDER BY DATE(closed_at)
"""
```

> [!IMPORTANT]
> **Bug found during implementation:** Original had `TO_CHAR(closed_at, 'YYYY-MM-DD')` in SELECT but `DATE(closed_at)` in GROUP BY. Postgres strict mode rejects this mismatch. Fix: `TO_CHAR(DATE(closed_at), 'YYYY-MM-DD')` so SELECT and GROUP BY both use `DATE(closed_at)`.

### 3. Max Drawdown Calculation

```sql
MAX_DRAWDOWN_QUERY = """
WITH equity AS (
    SELECT
        DATE(closed_at) AS trade_date,
        SUM(SUM(realized_pnl)) OVER (ORDER BY DATE(closed_at)) AS cumulative_pnl
    FROM paper_trades
    WHERE status IN ('CLOSED', 'EXPIRED')
      AND username = current_setting('app.current_user', true)
    GROUP BY DATE(closed_at)
),
peaks AS (
    SELECT
        trade_date,
        cumulative_pnl,
        MAX(cumulative_pnl) OVER (ORDER BY trade_date) AS running_peak
    FROM equity
)
SELECT
    ROUND(MIN(cumulative_pnl - running_peak)::numeric, 2) AS max_drawdown,
    (ARRAY_AGG(trade_date ORDER BY (cumulative_pnl - running_peak) ASC))[1] AS drawdown_date
FROM peaks
WHERE cumulative_pnl - running_peak < 0
"""
```

### 4. Per-Ticker Breakdown

```sql
TICKER_BREAKDOWN_QUERY = """
SELECT
    ticker,
    COUNT(*) AS trades,
    COUNT(*) FILTER (WHERE realized_pnl > 0) AS wins,
    ROUND(
        COUNT(*) FILTER (WHERE realized_pnl > 0)::numeric 
        / NULLIF(COUNT(*), 0) * 100, 1
    ) AS win_rate,
    ROUND(SUM(realized_pnl)::numeric, 2) AS total_pnl,
    ROUND(AVG(realized_pnl)::numeric, 2) AS avg_pnl
FROM paper_trades
WHERE status IN ('CLOSED', 'EXPIRED')
  AND username = current_setting('app.current_user')
GROUP BY ticker
ORDER BY total_pnl DESC
"""
```

### 5. Per-Strategy Breakdown (Using JSONB context from Point 6)

```sql
STRATEGY_BREAKDOWN_QUERY = """
SELECT
    COALESCE(strategy, 'Unknown') AS strategy,
    COUNT(*) AS trades,
    ROUND(
        COUNT(*) FILTER (WHERE realized_pnl > 0)::numeric 
        / NULLIF(COUNT(*), 0) * 100, 1
    ) AS win_rate,
    ROUND(SUM(realized_pnl)::numeric, 2) AS total_pnl,
    ROUND(
        SUM(realized_pnl) FILTER (WHERE realized_pnl > 0)::numeric
        / NULLIF(ABS(SUM(realized_pnl) FILTER (WHERE realized_pnl < 0))::numeric, 0), 2
    ) AS profit_factor
FROM paper_trades
WHERE status IN ('CLOSED', 'EXPIRED')
  AND username = current_setting('app.current_user', true)
GROUP BY strategy
ORDER BY total_pnl DESC
"""
```

> [!NOTE]
> The implemented version uses `COALESCE(strategy, 'Unknown')` instead of filtering by `trade_context->>'strategy_type' IS NOT NULL`. This ensures trades without a strategy still appear in breakdowns.

### 6. Monthly P&L Heatmap

```sql
MONTHLY_PNL_QUERY = """
SELECT
    TO_CHAR(closed_at, 'YYYY') AS year,
    TO_CHAR(closed_at, 'Mon') AS month,
    EXTRACT(MONTH FROM closed_at) AS month_num,
    ROUND(SUM(realized_pnl)::numeric, 2) AS monthly_pnl,
    COUNT(*) AS trade_count
FROM paper_trades
WHERE status IN ('CLOSED', 'EXPIRED')
  AND username = current_setting('app.current_user')
GROUP BY year, month, month_num
ORDER BY year, month_num
"""
```

### 7. MFE/MAE Analysis (Point 6 Integration)

```sql
MFE_MAE_QUERY = """
SELECT
    ticker,
    realized_pnl,
    trade_context->>'mfe' AS max_favorable_excursion,
    trade_context->>'mae' AS max_adverse_excursion,
    CASE
        WHEN realized_pnl > 0 AND (trade_context->>'mfe')::numeric > realized_pnl * 1.5
        THEN 'LEFT_MONEY'
        WHEN realized_pnl < 0 AND ABS((trade_context->>'mae')::numeric) > ABS(realized_pnl) * 1.5
        THEN 'HELD_TOO_LONG'
        ELSE 'OPTIMAL'
    END AS exit_quality
FROM paper_trades
WHERE status IN ('CLOSED', 'EXPIRED')
  AND username = current_setting('app.current_user')
  AND trade_context->>'mfe' IS NOT NULL
ORDER BY closed_at DESC
"""
```

---

## 💻 Backend Service

```python
# backend/services/analytics_service.py

class AnalyticsService:
    def __init__(self, db_session):
        self.db = db_session
    
    def get_summary(self, username: str) -> dict:
        """Get all summary stats for a user."""
        result = self.db.execute(
            text(SUMMARY_STATS_QUERY)
        ).mappings().first()
        
        if not result or result['total_trades'] == 0:
            return self._empty_summary()
        
        # Calculate Expectancy
        win_rate = float(result['win_rate'] or 0) / 100
        avg_win = float(result['avg_win'] or 0)
        avg_loss = abs(float(result['avg_loss'] or 0))
        expectancy = (win_rate * avg_win) - ((1 - win_rate) * avg_loss)
        
        return {
            **dict(result),
            'expectancy': round(expectancy, 2),
        }
    
    def get_equity_curve(self, username: str) -> list:
        """Get cumulative P&L data for charting."""
        rows = self.db.execute(
            text(EQUITY_CURVE_QUERY)
        ).mappings().all()
        return [dict(r) for r in rows]
    
    def get_max_drawdown(self, username: str) -> dict:
        """Get worst peak-to-trough decline."""
        result = self.db.execute(
            text(MAX_DRAWDOWN_QUERY)
        ).mappings().first()
        return dict(result) if result else {'max_drawdown': 0}
    
    def get_ticker_breakdown(self, username: str) -> list:
        """Get per-ticker performance."""
        rows = self.db.execute(
            text(TICKER_BREAKDOWN_QUERY)
        ).mappings().all()
        return [dict(r) for r in rows]
    
    def get_strategy_breakdown(self, username: str) -> list:
        """Get per-strategy performance."""
        rows = self.db.execute(
            text(STRATEGY_BREAKDOWN_QUERY)
        ).mappings().all()
        return [dict(r) for r in rows]
    
    def get_monthly_pnl(self, username: str) -> list:
        """Get monthly P&L for heatmap."""
        rows = self.db.execute(
            text(MONTHLY_PNL_QUERY)
        ).mappings().all()
        return [dict(r) for r in rows]
    
    def get_mfe_mae_analysis(self, username: str) -> list:
        """Get exit quality analysis."""
        rows = self.db.execute(
            text(MFE_MAE_QUERY)
        ).mappings().all()
        return [dict(r) for r in rows]
    
    def _empty_summary(self):
        return {
            'total_trades': 0, 'wins': 0, 'losses': 0,
            'win_rate': 0, 'profit_factor': 0, 'expectancy': 0,
            'avg_win': 0, 'avg_loss': 0, 'largest_win': 0,
            'largest_loss': 0, 'total_pnl': 0, 'avg_hold_hours': 0,
        }
```

---

## 🌐 API Endpoints

```python
# backend/routes/analytics.py

@app.route('/api/analytics/summary')
def analytics_summary():
    service = AnalyticsService(db.session)
    return jsonify(service.get_summary(current_user.username))

@app.route('/api/analytics/equity-curve')
def analytics_equity_curve():
    service = AnalyticsService(db.session)
    return jsonify(service.get_equity_curve(current_user.username))

@app.route('/api/analytics/drawdown')
def analytics_drawdown():
    service = AnalyticsService(db.session)
    return jsonify(service.get_max_drawdown(current_user.username))

@app.route('/api/analytics/by-ticker')
def analytics_by_ticker():
    service = AnalyticsService(db.session)
    return jsonify(service.get_ticker_breakdown(current_user.username))

@app.route('/api/analytics/by-strategy')
def analytics_by_strategy():
    service = AnalyticsService(db.session)
    return jsonify(service.get_strategy_breakdown(current_user.username))

@app.route('/api/analytics/monthly')
def analytics_monthly():
    service = AnalyticsService(db.session)
    return jsonify(service.get_monthly_pnl(current_user.username))

@app.route('/api/analytics/mfe-mae')
def analytics_mfe_mae():
    service = AnalyticsService(db.session)
    return jsonify(service.get_mfe_mae_analysis(current_user.username))
```

---

## 🎨 Performance Tab UI Layout

### Section 1: Summary Cards (Top Row)

```
┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐
│ Total P&L│ │ Win Rate │ │ Profit   │ │Expectancy│ │   Max    │
│  +$2,450 │ │  62.5%   │ │ Factor   │ │  +$38.20 │ │ Drawdown │
│  🟢 ▲    │ │  25/40   │ │   1.85   │ │ per trade│ │  -$890   │
└──────────┘ └──────────┘ └──────────┘ └──────────┘ └──────────┘
```

Each card shows:
- The metric value (large, bold)
- A subtitle (context)
- Color indicator (green if healthy, red if bad)

### Section 2: Charts (Middle)

#### Chart A: Equity Curve (Line Chart)
- X-axis: Date
- Y-axis: Cumulative P&L ($)
- Line color: Green when above $0, Red when below
- Shaded area under the line

#### Chart B: Monthly P&L Heatmap (Bar Chart)
- X-axis: Month
- Y-axis: P&L ($)
- Green bars for profit months, Red bars for loss months

#### Chart C: Win/Loss Distribution (Histogram)
- X-axis: P&L buckets (-$500 to +$500 in $50 increments)
- Y-axis: Number of trades
- Shows the shape of your returns

### Section 3: Breakdown Tables (Bottom)

#### Table A: By Ticker
| Ticker | Trades | Win Rate | Total P&L | Avg P&L |
|--------|--------|----------|-----------|---------|
| NVDA | 12 | 75% | +$1,200 | +$100 |
| AAPL | 8 | 50% | +$320 | +$40 |
| TSLA | 6 | 33% | -$480 | -$80 |

#### Table B: By Strategy
| Strategy | Trades | Win Rate | Profit Factor | Total P&L |
|----------|--------|----------|---------------|-----------|
| Momentum | 15 | 67% | 2.10 | +$1,800 |
| Mean Reversion | 10 | 60% | 1.50 | +$650 |
| Breakout | 5 | 40% | 0.80 | -$200 |

#### Table C: MFE/MAE Exit Quality
| Ticker | P&L | MFE | MAE | Exit Quality |
|--------|-----|-----|-----|-------------|
| NVDA | +$200 | +$450 | -$80 | LEFT_MONEY 🟡 |
| AAPL | -$150 | +$50 | -$300 | HELD_TOO_LONG 🔴 |
| META | +$180 | +$200 | -$30 | OPTIMAL 🟢 |

---

## 📈 Chart Library: Chart.js

We use [Chart.js](https://www.chartjs.org/) — lightweight, no build step, CDN-loadable.

```html
<!-- frontend/index.html -->
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
```

### Equity Curve Implementation

```javascript
// frontend/js/components/performance.js

async function renderEquityCurve() {
    const data = await fetch('/api/analytics/equity-curve').then(r => r.json());
    
    const ctx = document.getElementById('equity-chart').getContext('2d');
    new Chart(ctx, {
        type: 'line',
        data: {
            labels: data.map(d => d.trade_date),
            datasets: [{
                label: 'Cumulative P&L',
                data: data.map(d => d.cumulative_pnl),
                borderColor: data.map(d => d.cumulative_pnl >= 0 ? '#22c55e' : '#ef4444'),
                backgroundColor: 'rgba(34, 197, 94, 0.1)',
                fill: true,
                tension: 0.3,
                pointRadius: 3,
            }]
        },
        options: {
            responsive: true,
            plugins: {
                legend: { display: false },
                tooltip: {
                    callbacks: {
                        label: (ctx) => `P&L: $${ctx.parsed.y.toFixed(2)}`
                    }
                }
            },
            scales: {
                y: {
                    ticks: {
                        callback: (val) => `$${val}`
                    }
                }
            }
        }
    });
}
```

### Monthly P&L Bar Chart

```javascript
async function renderMonthlyPnl() {
    const data = await fetch('/api/analytics/monthly').then(r => r.json());
    
    const ctx = document.getElementById('monthly-chart').getContext('2d');
    new Chart(ctx, {
        type: 'bar',
        data: {
            labels: data.map(d => `${d.month} ${d.year}`),
            datasets: [{
                label: 'Monthly P&L',
                data: data.map(d => d.monthly_pnl),
                backgroundColor: data.map(d => 
                    d.monthly_pnl >= 0 ? '#22c55e' : '#ef4444'
                ),
                borderRadius: 4,
            }]
        },
        options: {
            responsive: true,
            plugins: {
                legend: { display: false },
            },
            scales: {
                y: {
                    ticks: { callback: (val) => `$${val}` }
                }
            }
        }
    });
}
```

---

## 🔄 Auto-Refresh: When to Update Analytics

Analytics refresh on these triggers:

| Trigger | What Refreshes |
|---------|---------------|
| Trade transitions to CLOSED | Full summary + equity curve |
| Trade transitions to EXPIRED | Full summary + equity curve |
| User opens Performance tab | All data (lazy load) |
| Manual refresh button click | All data |

**No polling needed.** Analytics only change when a trade closes.

```javascript
// frontend/js/components/portfolio.js
// After a trade closes successfully:
if (newStatus === 'CLOSED' || newStatus === 'EXPIRED') {
    // Invalidate analytics cache
    analyticsCache = null;
    
    // If user is on Performance tab, refresh it
    if (currentTab === 'performance') {
        await renderPerformanceDashboard();
    }
}
```

---

## 📤 Export (CSV + JSON)

Users can export their trade history in either format.

### CSV Export

```python
# backend/routes/analytics.py
import csv
import io

@app.route('/api/analytics/export/csv')
def export_trades_csv():
    trades = _get_closed_trades()
    
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        'Ticker', 'Direction', 'Entry', 'Exit', 'Qty',
        'P&L', 'Hold Time (hrs)', 'Strategy', 'Opened', 'Closed'
    ])
    
    for t in trades:
        writer.writerow([
            t.ticker, t.direction, t.entry_price, t.exit_price,
            t.quantity, t.realized_pnl,
            round((t.closed_at - t.created_at).total_seconds() / 3600, 1),
            t.trade_context.get('strategy_type', 'N/A'),
            t.created_at.isoformat(), t.closed_at.isoformat()
        ])
    
    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': 'attachment;filename=paper_trades.csv'}
    )
```

### JSON Export

```python
@app.route('/api/analytics/export/json')
def export_trades_json():
    trades = _get_closed_trades()
    
    data = [{
        'ticker': t.ticker,
        'direction': t.direction,
        'entry_price': float(t.entry_price),
        'exit_price': float(t.exit_price),
        'quantity': t.quantity,
        'realized_pnl': float(t.realized_pnl),
        'hold_time_hours': round(
            (t.closed_at - t.created_at).total_seconds() / 3600, 1
        ),
        'strategy': t.trade_context.get('strategy_type', 'N/A'),
        'status': t.status,
        'opened_at': t.created_at.isoformat(),
        'closed_at': t.closed_at.isoformat(),
        'trade_context': t.trade_context,  # Full JSONB context (MFE/MAE, etc.)
    } for t in trades]
    
    response = jsonify(data)
    response.headers['Content-Disposition'] = 'attachment;filename=paper_trades.json'
    return response


def _get_closed_trades():
    """Shared query for both export formats."""
    return db.session.query(PaperTrade).filter(
        PaperTrade.status.in_(['CLOSED', 'EXPIRED']),
        PaperTrade.username == current_setting('app.current_user')
    ).order_by(PaperTrade.closed_at.desc()).all()
```

### Frontend Export Buttons

```javascript
// frontend/js/components/performance.js
function exportTradesCSV() {
    window.location.href = '/api/analytics/export/csv';
}

function exportTradesJSON() {
    window.location.href = '/api/analytics/export/json';
}
```

---

## 📋 Summary

| Component | Decision |
|-----------|----------|
| **Core Metrics** | 10 metrics: Win Rate, Profit Factor, Expectancy, Avg Win/Loss, Drawdown, etc. |
| **SQL Engine** | Raw Postgres queries with `FILTER` clauses (no ORM overhead) |
| **Charts** | Chart.js (CDN, no build step) — Equity Curve + Monthly P&L + Distribution |
| **Breakdown** | By Ticker, By Strategy, By Exit Quality (MFE/MAE) |
| **Refresh** | Event-driven (on trade close), not polled |
| **Export** | CSV + JSON download of full trade history |
| **RLS Integration** | All queries use `current_setting('app.current_user')` (Point 7) |
| **Performance** | Raw SQL + lazy loading = fast even with 1000+ trades |

---

## 🗂️ Files Affected

```
backend/
├── queries/
│   └── analytics.py          # All SQL query constants
├── services/
│   └── analytics_service.py  # AnalyticsService class
├── routes/
│   └── analytics.py          # API endpoints + CSV export
frontend/
├── js/
│   └── components/
│       └── performance.js    # Chart.js rendering + summary cards
└── css/
    └── performance.css       # Performance tab styles
```
