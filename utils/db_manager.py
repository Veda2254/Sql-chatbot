"""
Database connection and management utilities
"""
import mysql.connector
from urllib.parse import quote_plus
from sqlalchemy import create_engine
from langchain_community.utilities import SQLDatabase


def create_db_connection(db_config: dict):
    """Create MySQL database connection"""
    try:
        return mysql.connector.connect(**db_config)
    except mysql.connector.Error as err:
        raise Exception(f"Database connection error: {err}")


def get_db_chain(db_config: dict) -> SQLDatabase:
    """Create SQLAlchemy database connection for LangChain"""
    try:
        db_uri = f"mysql+mysqlconnector://{db_config['user']}:{quote_plus(db_config['password'])}@{db_config['host']}/{db_config['database']}"
        engine = create_engine(db_uri)
        return SQLDatabase(engine=engine)
    except Exception as e:
        raise Exception(f"Failed to create database chain: {e}")


def test_connection(db_config: dict) -> tuple[bool, str]:
    """
    Test database connection
    Returns: (success, message)
    """
    try:
        conn = mysql.connector.connect(**db_config)
        conn.close()
        return True, f"Successfully connected to {db_config['database']}"
    except mysql.connector.Error as err:
        return False, f"Connection failed: {err}"
