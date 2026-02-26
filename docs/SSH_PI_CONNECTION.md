# SSH Connection to Raspberry Pi

## Overview

The Options application runs on a Raspberry Pi (production). This document covers
how to connect via SSH for maintenance, deployments, and database operations.

## Connection Details

| Field         | Value                              |
|---------------|------------------------------------|
| Host          | `192.168.1.244`                    |
| User          | `root`                             |
| Auth          | SSH key pair (Ed25519)             |
| Key (local)   | `C:\Users\olasu\.ssh\pikeypair`    |
| Key (public)  | `C:\Users\olasu\.ssh\pikeypair.pub`|
| SSH Port      | 22 (default)                       |

## Quick Connect

```bash
ssh -i C:\Users\olasu\.ssh\pikeypair root@192.168.1.244
```

## Docker Containers on Pi

| Container          | Port  | Purpose                     |
|--------------------|-------|-----------------------------|
| `leap_scanner_prod`| 5000  | Flask app (Options Scanner) |
| `paper_trading_db` | 5432  | PostgreSQL (paper trading)  |

## Common Operations

### Run SQL against the database

Pipe SQL via stdin to avoid PowerShell quote-escaping issues:

```powershell
echo "SELECT * FROM user_settings LIMIT 5;" | ssh -i C:\Users\olasu\.ssh\pikeypair -o BatchMode=yes root@192.168.1.244 "docker exec -i paper_trading_db psql -U paper_user -d paper_trading"
```

### Check container status

```powershell
ssh -i C:\Users\olasu\.ssh\pikeypair root@192.168.1.244 "docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'"
```

### View app logs

```powershell
ssh -i C:\Users\olasu\.ssh\pikeypair root@192.168.1.244 "docker logs --tail 50 leap_scanner_prod"
```

### Restart the app

```powershell
ssh -i C:\Users\olasu\.ssh\pikeypair root@192.168.1.244 "docker restart leap_scanner_prod"
```

## Key Pair Setup

The Ed25519 key pair was generated locally. To set up on a fresh Pi:

```bash
# On the Pi (as root):
mkdir -p ~/.ssh
chmod 700 ~/.ssh
echo "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIIpKiB4PBIGMvtOP/UxzPtsWBD4aTil8M18xbQSh0/su olasu@Olash" >> ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys
```

### sshd_config Requirements

Ensure these are set in `/etc/ssh/sshd_config`:

```
PubkeyAuthentication yes
AuthorizedKeysFile .ssh/authorized_keys
```

After changes: `sudo systemctl restart ssh`

### Windows Key Permissions

The private key file must have restricted permissions on Windows:

```powershell
icacls "C:\Users\olasu\.ssh\pikeypair" /inheritance:r /grant:r "olasu:(R)"
```

## Ngrok Access

The app is also exposed via ngrok at:
- **Production**: `https://tradeoptions.ngrok.app`
- Requires login (username/password auth)

## Database Credentials

| Role       | User/Pass                    | Purpose                    |
|------------|------------------------------|----------------------------|
| Superuser  | `paper_user` / `paper_pass`  | Migrations, admin queries  |
| App user   | `app_user` / `app_pass`      | Application (RLS enforced) |
