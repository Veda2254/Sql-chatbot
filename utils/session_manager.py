"""
Session management utilities for Flask
"""
from flask import session


def get_session_data(key: str, default=None):
    """Retrieve session data"""
    return session.get(key, default)


def update_session(key: str, value):
    """Update session data"""
    session[key] = value


def clear_session():
    """Clear all session data"""
    session.clear()


def init_session():
    """Initialize session with default values"""
    if 'messages' not in session:
        session['messages'] = []
    if 'db_config' not in session:
        session['db_config'] = None
    if 'db_connected' not in session:
        session['db_connected'] = False
    if 'chatbot_directive' not in session:
        session['chatbot_directive'] = None
    if 'schema_cache' not in session:
        session['schema_cache'] = None
