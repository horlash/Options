import time
import os
import json
import logging
from datetime import datetime
from backend.api.schwab import SchwabAPI
from schwab.auth import client_from_token_file
from backend.config import Config

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [WATCHDOG] - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("token_watchdog.log"),
        logging.StreamHandler()
    ]
)

def check_and_refresh():
    token_path = 'token.json'
    
    if not os.path.exists(token_path):
        logging.error("Token file not found!")
        return

    try:
        with open(token_path, 'r') as f:
            data = json.load(f)
            
        # Check expiry
        expires_at = data.get('token', {}).get('expires_at')
        if not expires_at:
            logging.error("Invalid token format: no expires_at")
            return

        now = time.time()
        time_left = expires_at - now
        
        logging.info(f"Token status: {int(time_left/60)} minutes remaining")

        # Refresh if < 15 minutes remaining
        if time_left < 900:  
            logging.info("Token expiring soon. Triggering refresh...")
            
            # Initialize client to trigger auto-refresh
            # We use the raw client_from_token_file to ensure we have the token updater callback
            client = client_from_token_file(
                token_path,
                Config.SCHWAB_API_KEY,
                Config.SCHWAB_API_SECRET
            )
            
            # Make a lightweight call to force token refresh
            # valid usage: client.get_account_numbers() or similar
            try:
                # get_user_preferences is usually lightweight
                client.get_user_preferences()
                logging.info("✅ Refresh Triggered successfully via API call.")
                
                # Check new expiry
                with open(token_path, 'r') as f:
                    new_data = json.load(f)
                    new_expires = new_data.get('token', {}).get('expires_at')
                    new_left = new_expires - time.time()
                    logging.info(f"New expiry: {int(new_left/60)} minutes")
                    
            except Exception as api_err:
                logging.error(f"Failed to refresh via API call: {api_err}")

    except Exception as e:
        logging.error(f"Watchdog error: {e}")

if __name__ == "__main__":
    logging.info("Starting Token Watchdog Service...")
    while True:
        check_and_refresh()
        # Sleep for 5 minutes
        time.sleep(300)
