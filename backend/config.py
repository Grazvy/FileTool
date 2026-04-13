import os

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key'
    DEBUG = os.environ.get('DEBUG', 'True').lower() == 'true'
    HOST = '127.0.0.1'
    PORT = int(os.environ.get('PORT', 5000))
    STATIC_FOLDER = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'frontend')
    TEMP_FOLDER = os.path.join(os.path.dirname(__file__), 'temp')