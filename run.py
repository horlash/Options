import sys
import os
from dotenv import load_dotenv

# Load environment variables
import logging

# Configure logging to show everything
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)

load_dotenv()

# Add the parent directory to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Now import and run the app
from backend.app import app
from backend.config import Config

if __name__ == '__main__':
    print("="*50)
    print("Options Scanner - Backend Server")
    print("="*50)
    print(f"\nServer starting on http://localhost:{Config.PORT}")
    print("\nPress Ctrl+C to stop the server\n")
    
    app.run(
        host='0.0.0.0',
        port=Config.PORT,
        debug=Config.FLASK_DEBUG
    )
