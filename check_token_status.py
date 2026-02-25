"""
Schwab Token Status Check (One-Shot)
=====================================
Checks if token.json exists and is still valid.
  - Exit code 0: token is valid (>15 min remaining)
  - Exit code 1: token is expired, missing, or about to expire

Called by run_and_share.bat before starting the backend.
If this exits with code 1, the bat file launches auto_schwab_auth.py.
"""

import sys
import os
import json
import time

TOKEN_PATH = 'token.json'

def check_token():
    if not os.path.exists(TOKEN_PATH):
        print("❌ Token file not found!")
        return 1

    try:
        with open(TOKEN_PATH, 'r') as f:
            data = json.load(f)

        # Token format: {"token": {"expires_at": <unix_timestamp>, ...}, ...}
        expires_at = data.get('token', {}).get('expires_at')
        if not expires_at:
            print("❌ Invalid token format: no expires_at field")
            return 1

        now = time.time()
        time_left = expires_at - now
        minutes_left = int(time_left / 60)

        if time_left < 900:  # Less than 15 minutes
            print(f"⚠️ Token expiring soon ({minutes_left} min remaining)")
            return 1

        print(f"✅ Token valid ({minutes_left} min remaining)")
        return 0

    except json.JSONDecodeError:
        print("❌ Token file is corrupt (invalid JSON)")
        return 1
    except Exception as e:
        print(f"❌ Token check failed: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(check_token())
