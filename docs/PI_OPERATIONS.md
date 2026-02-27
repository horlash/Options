# Pi Operations Runbook

> Single source of truth for deploying, maintaining, and troubleshooting the Options Scanner on the Raspberry Pi.

---

## 1. System Overview

| Component | Details |
|-----------|---------|
| **Pi Model** | Raspberry Pi 4 (ARM64/aarch64) |
| **OS** | Debian (Raspberry Pi OS) |
| **RAM** | 3.7 GB |
| **Disk** | 59 GB (SD card) |
| **IP (Ethernet)** | `192.168.1.244` |
| **Public URL** | `https://tradeoptions.ngrok.app` |
| **Docker Image** | `horlamy/newscanner:latest` |
| **Source Repo** | `https://github.com/horlash/Options.git` |

### Docker Stack

| Container | Image | Port | Purpose |
|-----------|-------|------|---------|
| `leap_scanner_prod` | `horlamy/newscanner:latest` | 5000 | Flask app |
| `paper_trading_db` | `postgres:16-alpine` | 5432 | PostgreSQL (trades) |

### Key Files on Pi

| Path | Purpose |
|------|---------|
| `/root/docker-compose.yml` | Production stack definition + all env vars |
| `/root/start_leap.sh` | Startup script |
| `/root/start_ngrok.sh` | Ngrok tunnel launcher |
| `/root/Options-build/` | Git clone used for Docker builds |

---

## 2. SSH Access

```powershell
# Quick connect (from Windows)
ssh -i C:\Users\olasu\.ssh\pikeypair root@192.168.1.244

# With keep-alive (for long operations)
ssh -i C:\Users\olasu\.ssh\pikeypair -o ServerAliveInterval=30 root@192.168.1.244
```

| Field | Value |
|-------|-------|
| Host | `192.168.1.244` |
| User | `root` |
| Key | `C:\Users\olasu\.ssh\pikeypair` |
| Key type | Ed25519 |

---

## 3. Deployment Methods

### Method A: Hotfix (docker cp) — 30 seconds

Use for **quick file changes** without rebuilding the image. Changes are lost on container recreation.

```powershell
# 1. Copy files from local to Pi
scp -i C:\Users\olasu\.ssh\pikeypair -o BatchMode=yes `
    frontend/js/components/opportunities.js `
    backend/services/reasoning_engine.py `
    root@192.168.1.244:/tmp/

# 2. SSH in and copy into container
ssh -i C:\Users\olasu\.ssh\pikeypair root@192.168.1.244 `
    "docker cp /tmp/opportunities.js leap_scanner_prod:/app/frontend/js/components/opportunities.js; `
     docker cp /tmp/reasoning_engine.py leap_scanner_prod:/app/backend/services/reasoning_engine.py"

# 3. Restart only if Python files changed (frontend = just hard refresh)
ssh -i C:\Users\olasu\.ssh\pikeypair root@192.168.1.244 "docker restart leap_scanner_prod"
```

> **⚠️ Important:** Bump cache versions in `index.html` (e.g., `opportunities.js?v=20` → `?v=21`) so browsers load the new files.

---

### Method B: Full Docker Bake — 15 minutes

Use for **permanent changes** that survive container restarts. This bakes everything into the image.

```powershell
# 1. Commit and push locally
cd c:\Users\olasu\.gemini\antigravity\Options
git add -A
git commit -m "description of changes"
git push origin main

# 2. SSH to Pi — clone and build
ssh -i C:\Users\olasu\.ssh\pikeypair -o ServerAliveInterval=30 root@192.168.1.244

# On the Pi:
cd /root
rm -rf Options-build
git clone https://github.com/horlash/Options.git Options-build
cd Options-build
nohup docker build -t horlamy/newscanner:latest . > /root/build.log 2>&1 &
# Monitor: tail -f /root/build.log (takes ~10 min)

# 3. Push to DockerHub
docker push horlamy/newscanner:latest

# 4. Restart with new image
cd /root
docker compose up -d
```

> **Build time:** ~10 min on Pi (pip install ~500s, layer export ~490s). Image size: ~1.3 GB.

---

### Method C: Zip Transfer (legacy) — 12 minutes

Alternative if git isn't available on Pi:

```powershell
# On Windows:
cd c:\Users\olasu\.gemini\antigravity\Options
git archive --format=zip HEAD -o Options.zip
scp -i C:\Users\olasu\.ssh\pikeypair Options.zip root@192.168.1.244:/root/

# On Pi:
cd /root && rm -rf Options-build && mkdir Options-build
unzip Options.zip -d Options-build
cd Options-build
docker build -t horlamy/newscanner:latest .
docker push horlamy/newscanner:latest
cd /root && docker compose up -d
```

---

## 4. Docker Compose Reference

The production stack is defined in `/root/docker-compose.yml`:

```bash
# Start/restart the full stack
cd /root && docker compose up -d

# Stop everything
docker compose down

# View running containers
docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'

# View logs
docker logs --tail 50 leap_scanner_prod
docker logs -f leap_scanner_prod  # follow mode
```

### Environment Variables (in docker-compose.yml)

| Variable | Purpose |
|----------|---------|
| `SCHWAB_API_KEY` | Market data |
| `FINNHUB_API_KEY` | News/sentiment |
| `FMP_API_KEY` | Financial data |
| `ORATS_API_KEY` | Options chain data |
| `PERPLEXITY_API_KEY` | AI reasoning engine |
| `PAPER_TRADE_DB_URL` | PostgreSQL connection |
| `ENCRYPTION_KEY` | Tradier token encryption |
| `SECRET_KEY` | Flask session secret |

> **Keys are NOT in the Docker image** — they live only in docker-compose.yml on the Pi.

---

## 5. Database Operations

### Connect to PostgreSQL

```powershell
# From Windows (pipe SQL to avoid quote issues)
echo "SELECT * FROM paper_trades LIMIT 5;" | ssh -i C:\Users\olasu\.ssh\pikeypair -o BatchMode=yes root@192.168.1.244 "docker exec -i paper_trading_db psql -U paper_user -d paper_trading"
```

### Common Queries

```sql
-- Count open trades
SELECT COUNT(*) FROM paper_trades WHERE status='OPEN';

-- View admin trades
SELECT id, ticker, option_type, strike, status, entry_price, current_price FROM paper_trades WHERE username='admin';

-- Wipe all trades for a user
DELETE FROM price_snapshots WHERE trade_id IN (SELECT id FROM paper_trades WHERE username='admin');
DELETE FROM state_transitions WHERE trade_id IN (SELECT id FROM paper_trades WHERE username='admin');
DELETE FROM paper_trades WHERE username='admin';

-- View user settings
SELECT * FROM user_settings;
```

### Database Tables

| Table | Purpose |
|-------|---------|
| `paper_trades` | All trade records |
| `state_transitions` | Trade lifecycle audit log |
| `price_snapshots` | Historical price captures |
| `user_settings` | Per-user config (balance, SL/TP defaults) |

### Credentials

| Role | User / Pass | Purpose |
|------|-------------|---------|
| Superuser | `paper_user` / `paper_pass` | Admin, migrations |
| App user | `app_user` / `app_pass` | Application (RLS) |

### Backup

```bash
# On Pi — dump database
docker exec paper_trading_db pg_dump -U paper_user paper_trading > /root/paper_trading_backup_$(date +%Y%m%d).sql

# Restore
cat backup.sql | docker exec -i paper_trading_db psql -U paper_user -d paper_trading
```

---

## 6. Ngrok Setup

Ngrok exposes the Pi to the internet with a custom domain.

| Field | Value |
|-------|-------|
| Domain | `tradeoptions.ngrok.app` |
| Local port | `5000` |
| Config | `/root/start_ngrok.sh` |

```bash
# Start ngrok (on Pi)
ngrok http 5000 --url tradeoptions.ngrok.app

# Or use the startup script
/root/start_ngrok.sh
```

---

## 7. Rollback

### Quick Rollback (to previous image)

```bash
# On Pi:
# 1. Check available images
docker images horlamy/newscanner --format '{{.Tag}} {{.CreatedAt}}'

# 2. Edit docker-compose.yml to use old tag
sed -i 's|horlamy/newscanner:latest|horlamy/newscanner:1.1.0|' /root/docker-compose.yml

# 3. Restart
cd /root && docker compose up -d
```

### Full Rollback (to tagged release)

```bash
# The pre-merge state is tagged in git
git checkout v1.0.1-pre-merge
docker build -t horlamy/newscanner:rollback .
# Update docker-compose.yml to use :rollback, then docker compose up -d
```

---

## 8. Monitoring & Health

```bash
# Container status
docker ps

# App logs (last 50 lines)
docker logs --tail 50 leap_scanner_prod

# Search logs for errors
docker logs leap_scanner_prod 2>&1 | grep -i 'error\|traceback\|failed'

# Check disk space
df -h

# Check memory
free -h

# Check if Flask is responding
curl -s http://localhost:5000/ | head -5
```

---

## 9. Common Issues

| Problem | Cause | Fix |
|---------|-------|-----|
| `ORATS: No contract found` | Strike/expiry doesn't exist in live data | Normal for expired or invalid contracts |
| Container won't start | Missing env vars | Check `docker-compose.yml` for all required keys |
| `No module named X` | Package missing from requirements.txt | Add to requirements.txt, rebuild image |
| Stale frontend | Browser cache | Bump `?v=XX` in index.html, hard refresh |
| SSH connection refused | Pi IP changed | Check router DHCP leases, try `192.168.1.105` (WiFi) |
| Build hangs on Pi | Low memory | Close other containers during build: `docker stop leap_scanner_prod` |
| Push to DockerHub fails | Not logged in | `docker login -u horlamy` on Pi |
| `disk full` during build | Old images | `docker system prune -a` on Pi |

---

## 10. App Users

| User | Password | Role |
|------|----------|------|
| `admin` | *(private)* | Primary |
| `dev` | `password123` | Development |
| `tester1` | `tester1pass` | Testing |
| `tester2` | `tester2pass` | Testing |

Reset a password:
```python
python -c "import hashlib; print(hashlib.sha256('NEW_PASSWORD'.encode()).hexdigest())"
# Update the hash in backend/users.json
```
