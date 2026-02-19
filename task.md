# Task Checklist — Paper Trade Monitoring

> **Status:** Active (Planning Phase)  
> **Branch:** `feature/paper-trading`

---

## High-Level Roadmap

- [x] Create feature branch for paper trade monitoring (`feature/paper-trading` off `feature/automated-trading`)

## Detailed Point Review
- [x] Point 1: Database Persistence Strategy → **Neon PostgreSQL** (prod) + Docker Postgres (dev)
- [x] Point 2: Polling Frequency & Shared Price Cache → **Tradier-first, 60s cron, 40s snapshots, 15s frontend**
- [x] Point 3: UI Location — Portfolio Tab Upgrade → **Open/History/Performance tabs, Inline expansion, Visual Verification mandatory**
- [x] Point 4: SL/TP Bracket Enforcement → **Tradier OCO, Confirm modal + Sounds, Adjust TP supported**
- [x] Point 5: Market Hours Logic → **Strict 9:30-4:00 ET window, Pre/Post Bookends, Holiday Logic Ignored**
- [x] Point 6: Backtesting Data Model & Schema → **Context-Rich JSONB, MFE/MAE Targets, Multi-Timeframe**
- [x] Point 7: Multi-User Data Isolation → **Postgres RLS (Layer 4), Service Isolation (Layer 2), Docker Dev DB**
- [x] Point 8: Multi-Device Session Synchronization → **Optimistic Locking (Version col), 409 Conflict Handling**
- [x] Point 9: Tradier Integration Architecture → **Provider Pattern, Factory Switch, Fernet Encryption, Rate Limiter**
- [x] Point 10: Concurrency & Race Conditions → **Idempotency Keys, Advisory Locks, Pool Config, REPEATABLE READ**
- [x] Point 11: Position Lifecycle Management → **7-State Machine, Strict Transitions, Audit Trail, UI Mapping**
- [ ] Point 12: Analytics & Performance Reporting

## Implementation Phases
- [ ] **Phase 1: Foundation** (DB Models, RLS, Tradier Client)
- [ ] **Phase 2: UI Construction** (Portfolio Tab, Mockups)
- [ ] **Phase 3: The Engine** (Cron Jobs, Price Cache, Context Collector)
- [ ] **Phase 4: Order Logic** (Brackets, OCO, Lifecycle)
- [ ] **Phase 5: Intelligence** (Target Variables, Analytics)
- [ ] **Phase 6: Integration** (Live Toggle, MCP Knowledge)
