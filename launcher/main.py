#!/usr/bin/env python3
"""
Launcher for File Tool
Starts the backend server and opens the browser
"""

import sys
import os
import webbrowser
import threading
import time

# Add the parent directory to the Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.app.main import create_app
from backend.config import Config

def open_browser():
    """Open browser after a short delay to allow server to start"""
    time.sleep(2)  # Wait for server to be ready
    url = f'http://{Config.HOST}:{Config.PORT}'
    webbrowser.open(url)
    print(f"Opened browser at {url}")

def main():
    print("Starting File Tool...")

    # Create and run the Flask app
    app = create_app()

    # Only open browser in the initial process (not in reloader child process)
    if os.environ.get('WERKZEUG_RUN_MAIN') != 'true':
        browser_thread = threading.Thread(target=open_browser, daemon=True)
        browser_thread.start()

    # Run the server without debug (prevents debugger/reloader conflicts)
    print(f"Server starting on http://{Config.HOST}:{Config.PORT}")
    app.run(host=Config.HOST, port=Config.PORT, debug=False)

if __name__ == '__main__':
    main()