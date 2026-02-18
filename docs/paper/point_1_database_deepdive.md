# Point 1: Database Persistence Strategy — FINALIZED ✅

> **Status:** Approved  
> **Date:** Feb 18, 2026  
> **Decision:** Neon PostgreSQL (production) + SQLite (development)

---

## Final Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| **Dev database** | SQLite (keep as-is) | Zero setup, fast iteration, local file |
| **Production database** | Neon PostgreSQL (free tier) | Always free, 500MB, no pause/lock-in, auto-backup |
| **Toggle mechanism** | `DATABASE_URL` env variable | Same SQLAlchemy code, one-line connection string swap |
| **Data protection** | Auto-backup + 6-hour PITR + `is_locked` on completed trades | Prevents data loss and unauthorized modification |
| **MCP server** | Deferred to Phase 7 | Need 50+ completed trades before historical context adds value |
| **Migration effort** | Minimal | SQLAlchemy ORM handles engine switch, one-time type audit needed |
| **Cost** | $0 | 500MB ≈ 15 years of data at projected usage |

---

## Why SQLite Fails in Production

| Failure Mode | Impact |
|-------------|--------|
| Write locking | Only 1 writer — blocks multi-user trades |
| File corruption | Server crash mid-write can corrupt entire DB |
| No network access | Can't share between server instances |
| No replication | Single file = single point of failure |
| No auto-backup | Must manually copy `.db` file |

---

## Why Neon PostgreSQL Was Chosen

### Over Supabase
- **No inactivity pause** — Neon scales to zero but always stays available; Supabase pauses after 7 days
- **Less vendor lock-in** — Neon is pure PostgreSQL; Supabase has proprietary Auth/REST/real-time features that don't migrate
- **DB branching** — Neon supports dev/prod branches on free tier (like git for databases)
- **Cheaper growth** — $19/mo (Neon Launch) vs $25/mo (Supabase Pro) if we outgrow free tier

### Over AWS RDS / Azure SQL
- **Always free** — AWS RDS free tier expires after 12 months; Azure SQL is always free but complex setup
- **Zero config** — No VPC, security groups, IAM roles, or resource groups to manage
- **Same PostgreSQL** — Standard connection string, full SQLAlchemy compatibility

### Neon Free Tier Specs
- 500 MB storage
- 100 CU-hours/month compute (≈400 hours at 0.25 CU)
- 5 GB egress/month
- 100 projects
- 6-hour point-in-time recovery
- Scales to zero after 5 min inactivity (auto-wakes on demand)

---

## Implementation Strategy

### Connection String Toggle

```python
# config.py
import os

class Config:
    # Dev: SQLite (local file)
    # Prod: Neon PostgreSQL (cloud)
    DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///./leap_scanner.db')
```

```env
# .env.development (local)
DATABASE_URL=sqlite:///./leap_scanner.db

# .env.production (Neon)
DATABASE_URL=postgresql://user:pass@ep-xxx.us-east-2.aws.neon.tech/neondb?sslmode=require
```

### Migration Checklist (During Execution)
- [ ] Create Neon account + project
- [ ] Get connection string
- [ ] Add to `.env.production`
- [ ] Run `Base.metadata.create_all(engine)` against Neon to create tables
- [ ] One-time type audit: ensure DateTime/Float columns are strict
- [ ] Test SQLAlchemy connection from Flask

---

## Data Volume Projection

```
1 paper trade record ≈ 500 bytes
1 price snapshot ≈ 100 bytes

At 5 users × 10 trades/week × 50 weeks:
  Trades: 2,500/year × 500 bytes = 1.25 MB/year
  Snapshots: 2,500 × 60 × 100 bytes = 15 MB/year
  
  Total: ~17 MB/year
  500 MB capacity → ~15 years of data
```

---

## MCP Server (Phase 7 — Deferred)

When 50+ trades are recorded, an MCP server will expose trade history as tools for AI context:
- `get_trade_history(ticker)` → past trades for a ticker
- `get_win_rate_by_score(min, max)` → win rate for score ranges
- `get_best_entry_conditions(ticker)` → conditions that led to wins
- `get_strategy_performance(strategy)` → win rate by strategy type

This feeds historical performance data into Perplexity's prompt for context-aware analysis.
