"""
Database connection API routes
"""
from flask import Blueprint, request, jsonify, session
from utils import test_connection, init_session

connection_bp = Blueprint('connection', __name__)


@connection_bp.route('/api/connect', methods=['POST'])
def connect():
    """Connect to database with credentials"""
    try:
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['host', 'user', 'database']
        if not all(field in data for field in required_fields):
            return jsonify({
                'success': False,
                'message': 'Missing required fields (host, user, database)'
            }), 400
        
        # Prepare database config
        db_config = {
            'host': data['host'],
            'port': data.get('port', 3306),
            'user': data['user'],
            'password': data.get('password', ''),
            'database': data['database']
        }
        
        # Test connection
        success, message = test_connection(db_config)
        
        if not success:
            return jsonify({
                'success': False,
                'message': message
            }), 400
        
        # Store in session
        init_session()
        session['db_config'] = db_config
        session['db_connected'] = True
        session['schema_cache'] = None  # Clear schema cache
        
        # Handle optional directive
        directive = data.get('directive', '').strip()
        if directive:
            session['chatbot_directive'] = directive
        
        # Initialize with welcome message
        welcome_msg = f"✅ Successfully connected to **{data['database']}**!"
        if directive:
            welcome_msg += f"\n\n🎯 **Active Directive:** {directive[:100]}..."
        welcome_msg += "\n\nAsk me anything about your data!"
        
        session['messages'] = [{
            "role": "assistant",
            "content": welcome_msg
        }]
        
        return jsonify({
            'success': True,
            'message': message,
            'database': data['database'],
            'has_directive': bool(directive),
            'directive_preview': directive[:100] if directive else None
        }), 200
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Connection error: {str(e)}'
        }), 500


@connection_bp.route('/api/disconnect', methods=['POST'])
def disconnect():
    """Disconnect from database"""
    try:
        session['db_config'] = None
        session['db_connected'] = False
        session['chatbot_directive'] = None
        session['messages'] = []
        session['schema_cache'] = None
        
        return jsonify({
            'success': True,
            'message': 'Disconnected successfully'
        }), 200
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Disconnect error: {str(e)}'
        }), 500


@connection_bp.route('/api/status', methods=['GET'])
def status():
    """Get connection status"""
    try:
        init_session()
        
        db_connected = session.get('db_connected', False)
        db_config = session.get('db_config')
        directive = session.get('chatbot_directive')
        
        response_data = {
            'success': True,
            'connected': db_connected
        }
        
        if db_connected and db_config:
            response_data['database'] = db_config.get('database')
            response_data['host'] = db_config.get('host')
            response_data['user'] = db_config.get('user')
        
        if directive:
            response_data['has_directive'] = True
            response_data['directive'] = directive
        else:
            response_data['has_directive'] = False
        
        return jsonify(response_data), 200
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Status error: {str(e)}'
        }), 500
