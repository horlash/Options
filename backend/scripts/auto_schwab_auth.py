import sys
import time
import os
import json
from schwab.auth import get_auth_context, client_from_received_url

# Configuration
API_KEY = 'BBO22mnuVoTdTEptFGAMnpbPZi7h9PAHOshio0xu8NXh4cka'
APP_SECRET = 'uwVjRhbkbAZlBeG5quTXhCs8igjIfg2hFiJXQzAfG91yzYQnkxuhTtNA9ElESrz7'
CALLBACK_URL = 'https://127.0.0.1'
TOKEN_PATH = 'token.json'
AUTH_URL_FILE = 'auth_url.txt'
REDIRECT_RESULT_FILE = 'redirect_result.txt'

def token_write_func(token):
    print(f"DEBUG: Writing token to {TOKEN_PATH}...")
    with open(TOKEN_PATH, 'w') as f:
        json.dump(token, f)

def main():
    print("Starting custom automated auth flow...", flush=True)

    # Clean up
    if os.path.exists(AUTH_URL_FILE): os.remove(AUTH_URL_FILE)
    if os.path.exists(REDIRECT_RESULT_FILE): os.remove(REDIRECT_RESULT_FILE)

    # 1. Generate Auth URL
    auth_context = get_auth_context(API_KEY, CALLBACK_URL)
    url = auth_context.authorization_url
    
    print(f"Generated Auth URL: {url}", flush=True)
    
    # Save for agent to read
    with open(AUTH_URL_FILE, 'w') as f:
        f.write(url)
        
    print(f"Waiting for {REDIRECT_RESULT_FILE}...", flush=True)
    
    # 2. Wait for Redirect URL
    while not os.path.exists(REDIRECT_RESULT_FILE):
        time.sleep(1)
        
    with open(REDIRECT_RESULT_FILE, 'r') as f:
        received_url = f.read().strip()
        
    print(f"Received Redirect URL: {received_url}", flush=True)
    
    # 3. Complete Auth
    try:
        client = client_from_received_url(
            API_KEY, 
            APP_SECRET, 
            auth_context, 
            received_url, 
            token_write_func
        )
        
        # 4. Verify Refresh Token
        # Client wraps session. verify the underlying token
        # client.session.token should be the token dict
        token_data = client.session.token
        print(f"\n[Token Analysis] Keys: {list(token_data.keys())}", flush=True)
        
        if 'refresh_token' in token_data:
            print("✅ SUCCESS: Refresh Token acquired! System is now robust.", flush=True)
        else:
            print("⚠️ WARNING: NO REFRESH TOKEN FOUND.", flush=True)
            # Try to force save what we have
            token_write_func(token_data)
            
    except Exception as e:
        print(f"❌ Auth Failed: {e}", flush=True)
        # Dump full error
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
