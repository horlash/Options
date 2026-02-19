# Point 1: Database Persistence Strategy — FINALIZED ✅

> **Status:** Approved | **Date:** Feb 18, 2026  
> **Decision:** Neon PostgreSQL (production) + SQLite (development)

---

## Final Decisions

| Decision | Choice |
|----------|--------|
| Dev database | SQLite (local, zero setup) |
| Production database | **Neon PostgreSQL** (always free, 500MB, no pause, no lock-in) |
| Toggle mechanism | `DATABASE_URL` env variable |
| Data protection | Auto-backup + 6-hour PITR + `is_locked` on closed trades |
| MCP server | Deferred to Phase 7 |
| Cost | $0 (500MB ≈ 15 years at projected usage) |

---

## Why Neon Over Alternatives

| Factor | Neon ✅ | Supabase | AWS RDS | Azure SQL |
|--------|---------|----------|---------|-----------|
| Always free | ✅ | ✅ (pauses after 7 days) | ❌ 12 months | ✅ (complex setup) |
| Lock-in | Minimal — pure PostgreSQL | Moderate — proprietary features | Minimal | Moderate |
| DB branching | ✅ Free | Paid only | ❌ | ❌ |
| Auto-wake | ✅ Scales to zero, wakes on demand | ❌ Must manually unpause | N/A | N/A |

---

## Complete Schema

### `paper_trades`
- Trade details: ticker, option_type, strike, expiry, entry_price, qty
- Brackets: sl_price, tp_price
- Scanner context: strategy, card_score, ai_score, ai_verdict, gate_verdict, technical_score, sentiment_score, delta_at_entry, iv_at_entry
- Live monitoring: current_price, unrealized_pnl
- Outcome: status, close_price, close_reason, realized_pnl, max_drawdown, max_gain
- Tradier: tradier_order_id, tradier_sl_order_id, tradier_tp_order_id, trigger_precision, broker_fill_price, broker_fill_time
- Concurrency: version, is_locked

### `price_snapshots`
- trade_id, timestamp, mark_price, bid, ask, delta, iv, underlying

### `user_settings`
- broker_mode, tradier_sandbox_token, tradier_live_token, tradier_account_id
- account_balance, max_positions, daily_loss_limit, heat_limit_pct, auto_refresh

Full SQL DDL available in artifact version.

---

## Migration Checklist

- [ ] Create Neon account + project
- [ ] Get connection string
- [ ] Add to `.env.production`
- [ ] Create SQLAlchemy models
- [ ] Run `Base.metadata.create_all(engine)` against Neon
- [ ] One-time type audit
- [ ] Test connection
