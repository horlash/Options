# Point 7: Multi-User Data Isolation — Deep Dive (Triple Deep)

> **Status:** Draft (Backup Automation Added)  
> **Date:** Feb 19, 2026  
> **Depends On:** Point 1 (Database) & Point 6 (Data Model)

---

## 🔒 The Goal: "Zero Leakage"
We are moving from a "Single Player" local script to a "Multi-Tenant" SaaS architecture.
**User A (Alice)** must NEVER see **User B (Bob)'s** trades.

---

## 🏗️ The Infrastructure (Dev/Prod Parity)
**Decision:** We are dropping SQLite for development.
**Reason:** SQLite does not support RLS. We must use **Dockerized Postgres** locally.

---

## 🔒 Layer 4: The Enforcer (Postgres RLS)

### 1. The Policy (SQL)
We must run this SQL manually (via migration) to set the rules.

```sql
-- Enable RLS
ALTER TABLE paper_trades ENABLE ROW LEVEL SECURITY;

-- Create Policy: "Only show rows where username matches the session variable"
CREATE POLICY tenant_isolation_policy ON paper_trades
    USING (username = current_setting('app.current_user', true));
```

### 2. The Messenger (SQLAlchemy Hook)
We use a Python hook to set the session variable before every query.

```python
# backend/database/session.py
def set_app_user(conn, cursor, ...):
    # Retrieve current user from Flask Context
    user = getattr(g, 'user', None)
    if user:
        cursor.execute(f"SET LOCAL app.current_user = '{user.username}'")
    else:
        cursor.execute("SET LOCAL app.current_user = 'SYSTEM'")
```

---

## 💾 Automated Backup Strategy (The Fix)

You asked: *"Can this be automated?"*
**Answer: YES.** We do not rely on humans remembering to use `sudo`.

### Step 1: Create a Dedicated Backup User
We create a robot user in Postgres specifically for this task.

```sql
-- Run this once in Neon/Postgres
CREATE USER backup_service WITH PASSWORD 'complex_password';
GRANT CONNECT ON DATABASE tradeoptions TO backup_service;
GRANT pg_read_all_data TO backup_service;
-- THE MAGIC KEY:
GRANT BYPASSRLS TO backup_service;
```

### Step 2: The Backup Script (`scripts/backup_db.sh`)
This script uses the robot credentials. It sees *everything*.

```bash
#!/bin/bash
# Auto-Backup Script
export PGPASSWORD='complex_password'

# Dump the full DB (RLS is bypassed automatically)
pg_dump -h ep-xyz.neon.tech -U backup_service -d tradeoptions > backup_$(date +%F).sql

# Optional: Upload to S3/Google Drive
# aws s3 cp ...
```

### Step 3: Schedule It
Add to the system cron (or GitHub Actions):
`0 2 * * * /app/scripts/backup_db.sh` (Runs at 2:00 AM)

**Result:** You sleep. The robot backs up 100% of the data. No "partial backup" risks.

---

## ⚠️ Migration & Compatibility Checks

### Risk 1: Alembic is Blind
*   **The Problem:** Alembic monitors *Tables*, not *Policies*.
*   **The Fix:** We must manually add `op.execute("ENABLE BACKUP...")` in migration files.

### Risk 2: App Logic
*   **The Problem:** If `set_app_user` fails, the query fails.
*   **The Fix:** The hook handles the `None` case (defaults to `SYSTEM`) to ensure background jobs don't crash.

---

## Final Plan for Point 7

1.  **Infrastructure:** Docker Postgres (Local) matches Prod.
2.  **Schema:** `username` column + Index.
3.  **Security:** RLS Policy + SQLAlchemy Hook.
4.  **Backups:** Dedicated `backup_service` user + Cron Script.

This approach gives us "Banking Grade" security with "Set and Forget" operations.
