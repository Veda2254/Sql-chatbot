"""
Security module for SQL injection prevention and query validation
"""
import re


def is_read_only_query(sql_query: str) -> tuple[bool, str]:
    """
    Validates that SQL query is read-only (SELECT only)
    Returns: (is_valid, error_message)
    """
    if not sql_query:
        return False, "Empty query"
    
    # Convert to uppercase for checking
    sql_upper = sql_query.upper().strip()
    
    # List of forbidden keywords that modify data
    forbidden_keywords = [
        'INSERT', 'UPDATE', 'DELETE', 'DROP', 'CREATE', 'ALTER',
        'TRUNCATE', 'REPLACE', 'MERGE', 'GRANT', 'REVOKE',
        'EXEC', 'EXECUTE', 'CALL', 'LOAD', 'RENAME'
    ]
    
    # Check for forbidden keywords
    for keyword in forbidden_keywords:
        # Use word boundaries to avoid false positives
        pattern = r'\b' + keyword + r'\b'
        if re.search(pattern, sql_upper):
            return False, f"⚠️ Security Alert: {keyword} operations are not allowed. This chatbot is read-only."
    
    # Ensure query starts with SELECT (after removing comments)
    # Remove SQL comments
    sql_no_comments = re.sub(r'--.*$', '', sql_upper, flags=re.MULTILINE)
    sql_no_comments = re.sub(r'/\*.*?\*/', '', sql_no_comments, flags=re.DOTALL)
    sql_no_comments = sql_no_comments.strip()
    
    if not sql_no_comments.startswith('SELECT'):
        return False, "⚠️ Only SELECT queries are allowed. This chatbot cannot modify data."
    
    return True, ""


def sanitize_user_input(user_input: str) -> str:
    """
    Sanitize user input to prevent injection attempts
    """
    # Remove potential SQL injection patterns
    dangerous_patterns = [
        r';\s*DROP',
        r';\s*DELETE',
        r';\s*UPDATE',
        r';\s*INSERT',
        r'UNION\s+SELECT',
        r'--\s*$',
        r'/\*.*?\*/',
    ]
    
    cleaned = user_input
    for pattern in dangerous_patterns:
        cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE)
    
    return cleaned
