from flask import Flask, send_from_directory, request
import os
from .routes.handlers import api_bp
from ..config import Config

def create_app():
    app = Flask(__name__, static_folder=Config.STATIC_FOLDER, static_url_path='/static')
    app.config.from_object(Config)

    # Register API blueprint first (takes priority)
    app.register_blueprint(api_bp, url_prefix='/api')

    # Serve frontend files - API routes are handled above, this is fallback
    @app.route('/')
    def index():
        return send_from_directory(app.static_folder, 'index.html')

    @app.errorhandler(404)
    def not_found(e):
        # Try to serve from frontend folder, fallback to index.html for SPA routing
        path = os.path.join(app.static_folder, request.path.lstrip('/'))
        if os.path.isfile(path):
            return send_from_directory(app.static_folder, request.path.lstrip('/'))
        return send_from_directory(app.static_folder, 'index.html')

    return app

if __name__ == '__main__':
    app = create_app()
    app.run(host=Config.HOST, port=Config.PORT, debug=Config.DEBUG)