from functools import wraps
from flask import request, Response, session, redirect
import json
import os
import hashlib
import hmac
import time
import logging
from datetime import datetime

log = logging.getLogger(__name__)

# Try to import bcrypt; fall back to SHA-256 if unavailable
try:
    import bcrypt
    HAS_BCRYPT = True
except ImportError:
    HAS_BCRYPT = False
    log.warning("bcrypt not installed — falling back to SHA-256 password hashing. "
                "Install bcrypt for production: pip install bcrypt")

class Security:
    def __init__(self, app=None):
        self.app = app
        if app:
            self.init_app(app)

    def init_app(self, app):
        self.users_file = os.path.join(os.path.dirname(__file__), 'users.json')
        self.log_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'access.log')
        
        @app.before_request
        def require_login():
            # Allow OPTIONS requests for CORS
            if request.method == 'OPTIONS':
                return
                
            # Public endpoints validation
            public_endpoints = [
                'login_page', 'login_api', 'static', 'health_check'
            ]
            
            # Allow static resources and specific public routes
            # P0-NEW-2 FIX: Blueprint endpoints are prefixed (e.g., 'paper.health_check').
            # Use suffix match so health_check works regardless of blueprint prefix.
            endpoint = request.endpoint or ''
            if (endpoint in public_endpoints or
                endpoint.endswith('.health_check') or
                request.path.startswith('/static') or 
                request.path.endswith('.css') or 
                request.path.endswith('.js') or 
                request.path.endswith('.png') or 
                request.path.endswith('.ico')):
                return

            # Check session
            if not session.get('logged_in'):
                # Redirect to login page for browser requests
                return redirect('/login')
            
            # Log access occasionally if needed (optional)
            # self.log_access(session.get('user'), request.path)

    def _verify_password(self, stored_hash, password):
        """Verify password against stored hash. Supports both bcrypt and legacy SHA-256."""
        if HAS_BCRYPT and stored_hash.startswith('$2'):
            # bcrypt hash detected
            return bcrypt.checkpw(password.encode('utf-8'), stored_hash.encode('utf-8'))
        else:
            # Legacy SHA-256 comparison (timing-safe)
            hashed_input = hashlib.sha256(password.encode()).hexdigest()
            return hmac.compare_digest(stored_hash, hashed_input)

    def _hash_password(self, password):
        """Hash a password using bcrypt (preferred) or SHA-256 (fallback)."""
        if HAS_BCRYPT:
            return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        else:
            return hashlib.sha256(password.encode()).hexdigest()

    def login_user(self, username, password):
        """Validates credentials and sets session."""
        users = self.load_users()
        if username in users:
            if self._verify_password(users[username], password):
                session['user'] = username
                session['logged_in'] = True
                
                # Auto-upgrade legacy SHA-256 hashes to bcrypt on successful login
                if HAS_BCRYPT and not users[username].startswith('$2'):
                    users[username] = self._hash_password(password)
                    self._save_users(users)
                    log.info(f"Upgraded password hash for user '{username}' to bcrypt")
                
                self.log_access(username, '/login (SUCCESS)')
                return True
        self.log_access(username, '/login (FAILED)')
        return False

    def logout_user(self):
        """Clears the session."""
        session.clear()
        
    def is_authenticated(self):
        """Checks if user is logged in."""
        return session.get('logged_in', False)

    def load_users(self):
        if not os.path.exists(self.users_file):
            return {}
        try:
            with open(self.users_file, 'r') as f:
                return json.load(f)
        except Exception as e:
            log.error(f"Failed to load users file: {e}")
            return {}

    def _save_users(self, users):
        """Save users dict back to file (for hash upgrades)."""
        try:
            with open(self.users_file, 'w') as f:
                json.dump(users, f, indent=2)
        except Exception as e:
            log.error(f"Failed to save users file: {e}")

    def log_access(self, username, path):
        """Log access events with sanitized username."""
        if path.startswith('/api/') or path == '/' or 'login' in path.lower():
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            # Sanitize username to prevent log injection
            safe_user = str(username or 'unknown').replace('\n', '\\n').replace('\r', '\\r')[:50]
            log_entry = f"[{timestamp}] User: {safe_user} | Path: {path} | IP: {request.remote_addr}\n"
            try:
                with open(self.log_file, 'a') as f:
                    f.write(log_entry)
            except Exception:
                pass
