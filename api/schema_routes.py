"""
Database schema API routes
"""
from flask import Blueprint, jsonify, session
from utils import init_session, get_database_schema_info

schema_bp = Blueprint('schema', __name__)


@schema_bp.route('/api/schema', methods=['GET'])
def get_schema():
    """Get database schema information"""
    try:
        init_session()
        
        # Check if database is connected
        if not session.get('db_connected', False):
            return jsonify({
                'success': False,
                'message': 'Please connect to a database first'
            }), 400
        
        # Get or create schema cache
        schema_info = session.get('schema_cache')
        db_config = session.get('db_config')
        
        if not schema_info:
            schema_info = get_database_schema_info(db_config)
            session['schema_cache'] = schema_info
        
        return jsonify({
            'success': True,
            'schema': schema_info
        }), 200
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error getting schema: {str(e)}'
        }), 500
