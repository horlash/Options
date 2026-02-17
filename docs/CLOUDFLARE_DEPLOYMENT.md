# Cloudflare Tunnel Deployment Guide
**Last Updated:** 2026-02-16
**Version:** NewScanner v3.0

---

## Why Cloudflare Tunnel?

| Feature | ngrok | Cloudflare Tunnel |
|---------|-------|-------------------|
| **Free** | 1 tunnel, random URL | ✅ Unlimited, custom subdomain |
| **Zscaler-safe** | ❌ Often blocked | ✅ Looks like normal HTTPS traffic |
| **Stable URL** | ❌ Random on free tier | ✅ your-name.cfargotunnel.com |
| **Custom domain** | ❌ Paid only | ✅ Free with your domain |
| **Auth** | Basic | ✅ Cloudflare Access (SSO, email OTP) |
| **Speed** | Good | ✅ Cloudflare edge network |
| **Reliability** | Fair | ✅ Enterprise-grade |

---

## Architecture

```
┌──────────────┐     HTTPS (443)     ┌─────────────────┐     HTTP     ┌──────────────┐
│   Browser    │ ◄──────────────────► │  Cloudflare     │ ◄──────────► │  cloudflared │
│  (anywhere)  │                      │  Edge Network   │  (encrypted) │  (your PC)   │
└──────────────┘                      └─────────────────┘              └──────┬───────┘
                                                                              │
                                                                     localhost:5000
                                                                              │
                                                                     ┌───────┴───────┐
                                                                     │   Flask App   │
                                                                     │  (backend +   │
                                                                     │   frontend)   │
                                                                     └───────────────┘
```

**Key:** `cloudflared` runs on your PC and establishes an outbound-only connection to Cloudflare. No inbound ports need to be opened.

---

## Prerequisites

1. **Cloudflare Account** — Free at [cloudflare.com](https://dash.cloudflare.com/sign-up)
2. **Domain** (optional but recommended) — Transfer or add a domain to Cloudflare DNS
3. **`cloudflared` CLI** — The tunnel agent binary

---

## Setup Plan

### Phase 1: Install `cloudflared`

**Windows (winget):**
```powershell
winget install cloudflare.cloudflared
```

**Windows (manual):**
```powershell
# Download from https://github.com/cloudflare/cloudflared/releases
# Place cloudflared.exe in PATH
```

**Verify:**
```powershell
cloudflared --version
```

### Phase 2: Authenticate & Create Tunnel

```powershell
# 1. Login to Cloudflare (opens browser)
cloudflared tunnel login

# 2. Create a named tunnel
cloudflared tunnel create options-scanner

# 3. Note the Tunnel ID (e.g., a1b2c3d4-e5f6-7890-abcd-ef1234567890)
```

### Phase 3: Configure Tunnel

Create `~/.cloudflared/config.yml`:
```yaml
tunnel: <TUNNEL_ID>
credentials-file: C:\Users\olasu\.cloudflared\<TUNNEL_ID>.json

ingress:
  - hostname: scanner.yourdomain.com   # Or use *.cfargotunnel.com
    service: http://localhost:5000
  - service: http_status:404
```

### Phase 4: DNS Setup

**Option A: Custom domain** (you own a domain on Cloudflare):
```powershell
cloudflared tunnel route dns options-scanner scanner.yourdomain.com
```

**Option B: Quick tunnel** (no domain needed):
```powershell
# Temporary URL (changes each restart)
cloudflared tunnel --url http://localhost:5000
```

### Phase 5: Run

```powershell
# Start the Flask app
Start-Process -NoNewWindow python -ArgumentList "backend/app.py"

# Start the tunnel
cloudflared tunnel run options-scanner
```

**Access from anywhere:**
`https://scanner.yourdomain.com`

---

## Flask Configuration Changes Needed

For HTTPS tunnel, Flask needs these cookie settings:

```python
# In backend/config.py or app.py:
app.config['SESSION_COOKIE_SECURE'] = True       # Only send cookies over HTTPS
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'    # Cross-site protection
app.config['SESSION_COOKIE_HTTPONLY'] = True       # XSS protection
```

> **Note:** These should only be enabled when running behind the tunnel (HTTPS). For local-only dev (HTTP), `SESSION_COOKIE_SECURE = False`.

---

## Security Considerations

| Layer | Protection | Status |
|-------|-----------|--------|
| Transport | HTTPS via Cloudflare (auto SSL) | ✅ Included |
| Authentication | Flask session login (username/password) | ✅ Existing |
| API Keys | `.env` file, never exposed to browser | ✅ Existing |
| Cloudflare Access | Optional — add email OTP or SSO gate | 🔜 Recommended |

### Optional: Cloudflare Access (Zero Trust)
Add an extra auth layer so only approved emails can access the tunnel:
1. Go to Cloudflare Dashboard → Zero Trust → Access → Applications
2. Create a Self-Hosted Application for `scanner.yourdomain.com`
3. Set policy: "Allow emails ending in @yourdomain.com"
4. Users get an email OTP before reaching the login page

---

## Quick Start Scripts

### `start_tunnel.bat` (for daily use)
```bat
@echo off
echo Starting Options Scanner + Cloudflare Tunnel...
start /B python backend/app.py
timeout /t 3 >nul
cloudflared tunnel run options-scanner
```

### `start_dev.bat` (local only, no tunnel)
```bat
@echo off
echo Starting Options Scanner (Local Dev)...
python backend/app.py
```

---

## Verification Checklist

After setup, verify:
- [ ] `cloudflared --version` returns version
- [ ] `cloudflared tunnel list` shows `options-scanner`
- [ ] Flask starts on `http://localhost:5000` 
- [ ] `cloudflared tunnel run` shows "Connection registered"
- [ ] Browser can reach `https://scanner.yourdomain.com`
- [ ] Login page loads correctly
- [ ] Scan ticker returns results
- [ ] Session persists after page refresh
