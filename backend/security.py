from functools import wraps
from flask import request, Response, session, redirect
import json
import os
import hashlib
import time
from datetime import datetime

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
            if (request.endpoint in public_endpoints or 
                request.path.startswith('/static') or 
                request.path.startswith('/api/paper') or
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

    def login_user(self, username, password):
        """Validates credentials and sets session."""
        users = self.load_users()
        if username in users:
            hashed_input = hashlib.sha256(password.encode()).hexdigest()
            if users[username] == hashed_input:
                session['user'] = username
                session['logged_in'] = True
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
        except:
            return {}

    def log_access(self, username, path):
        # logging every single asset request is noisy, skip static files unless important
        if path.startswith('/api/') or path == '/':
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            log_entry = f"[{timestamp}] User: {username} | Path: {path} | IP: {request.remote_addr}\n"
            try:
                with open(self.log_file, 'a') as f:
                    f.write(log_entry)
            except:
                pass
