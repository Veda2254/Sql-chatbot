"""
Directive management API routes
"""
from flask import Blueprint, request, jsonify, session
from utils import init_session

directive_bp = Blueprint('directive', __name__)


@directive_bp.route('/api/directive', methods=['POST'])
def set_directive():
    """Set or update chatbot directive"""
    try:
        init_session()
        data = request.get_json()
        
        directive = data.get('directive', '').strip()
        
        if not directive:
            return jsonify({
                'success': False,
                'message': 'Directive cannot be empty'
            }), 400
        
        session['chatbot_directive'] = directive
        
        return jsonify({
            'success': True,
            'message': 'Directive updated successfully',
            'directive': directive
        }), 200
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error setting directive: {str(e)}'
        }), 500


@directive_bp.route('/api/directive', methods=['GET'])
def get_directive():
    """Get current chatbot directive"""
    try:
        init_session()
        directive = session.get('chatbot_directive')
        
        if directive:
            return jsonify({
                'success': True,
                'directive': directive,
                'has_directive': True
            }), 200
        else:
            return jsonify({
                'success': True,
                'directive': None,
                'has_directive': False
            }), 200
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error getting directive: {str(e)}'
        }), 500


@directive_bp.route('/api/directive', methods=['DELETE'])
def clear_directive():
    """Clear chatbot directive"""
    try:
        init_session()
        session['chatbot_directive'] = None
        
        return jsonify({
            'success': True,
            'message': 'Directive cleared successfully'
        }), 200
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error clearing directive: {str(e)}'
        }), 500
