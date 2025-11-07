"""
Flask Application - SQL Chatbot with API
Main entry point for the application
"""
import os
from flask import Flask, render_template
from flask_cors import CORS
from flask_session import Session
from flask_caching import Cache
from config import config

# Import API blueprints
from api import connection_bp, directive_bp, chat_bp, schema_bp


def create_app(config_name='development'):
    """Application factory pattern"""
    app = Flask(__name__)
    
    # Load configuration
    app.config.from_object(config[config_name])
    
    # Initialize extensions
    CORS(app, resources={r"/api/*": {"origins": app.config['CORS_ORIGINS']}})
    Session(app)
    cache = Cache(app)
    
    # Create session directory if it doesn't exist
    if not os.path.exists(app.config['SESSION_FILE_DIR']):
        os.makedirs(app.config['SESSION_FILE_DIR'])
    
    # Register blueprints
    app.register_blueprint(connection_bp)
    app.register_blueprint(directive_bp)
    app.register_blueprint(chat_bp)
    app.register_blueprint(schema_bp)
    
    # Main route - serve frontend
    @app.route('/')
    def index():
        return render_template('index.html')
    
    # Health check endpoint
    @app.route('/health')
    def health():
        return {'status': 'healthy', 'message': 'SQL Chatbot API is running'}, 200
    
    return app


if __name__ == '__main__':
    # Get environment
    env = os.getenv('FLASK_ENV', 'development')
    app = create_app(env)
    
    # Run application
    port = int(os.getenv('PORT', 5000))
    debug = env == 'development'
    
    print(f"""
    ╔════════════════════════════════════════════════════════════╗
    ║         🤖 SQL Chatbot API Server Starting...              ║
    ╠════════════════════════════════════════════════════════════╣
    ║  Environment: {env.upper():44}                             ║
    ║  Debug Mode:  {str(debug):44}                              ║
    ║  Port:        {str(port):44}                               ║
    ║                                                            ║
    ║  🌐 Open your browser and navigate to:                     ║
    ║     http://localhost:{port:44}                             ║
    ╚════════════════════════════════════════════════════════════╝
    """)
    
    app.run(host='0.0.0.0', port=port, debug=debug)
