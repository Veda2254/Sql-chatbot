"""
Chat conversation API routes
"""
from flask import Blueprint, request, jsonify, session
from utils import (
    init_session, sanitize_user_input, get_db_chain, 
    get_database_schema_info, get_llm_client, 
    generate_sql_query_with_llm, is_read_only_query,
    clean_sql_results, generate_natural_language_response,
    create_sql_agent_fallback
)

chat_bp = Blueprint('chat', __name__)


def process_user_query(user_query: str) -> str:
    """
    Complete pipeline - EXACT SAME LOGIC as original
    1. Sanitize input
    2. Get schema automatically
    3. Generate SQL with LLM (no templates)
    4. Validate SQL is read-only
    5. Execute query
    6. Convert to natural language
    """
    
    # Step 0: Sanitize user input
    sanitized_query = sanitize_user_input(user_query)
    
    # Initialize
    db_config = session.get('db_config')
    if not db_config:
        return "Please connect to a database first."
    
    try:
        db = get_db_chain(db_config)
        
        # Get or create schema cache
        schema_info = session.get('schema_cache')
        if not schema_info:
            schema_info = get_database_schema_info(db_config)
            session['schema_cache'] = schema_info
        
        llm = get_llm_client(temperature=0.3)
        
        # Get conversation history and directive
        conversation_history = session.get('messages', [])
        custom_directive = session.get('chatbot_directive')
        
        # Step 1: Generate SQL query using LLM with conversation history
        query_info = generate_sql_query_with_llm(
            sanitized_query, 
            schema_info, 
            llm,
            conversation_history=conversation_history,
            custom_directive=custom_directive
        )
        
        sql_query = query_info.get('sql_query')
        confidence = query_info.get('confidence', 0.0)
        reasoning = query_info.get('reasoning', '')
        
        print(f"\n{'='*50}")
        print(f"USER QUERY: {sanitized_query}")
        print(f"REASONING: {reasoning}")
        print(f"CONFIDENCE: {confidence}")
        print(f"GENERATED SQL: {sql_query}")
        print(f"{'='*50}\n")
        
        # Step 2: Security validation - Check if query is read-only
        if sql_query:
            is_valid, error_msg = is_read_only_query(sql_query)
            if not is_valid:
                return f"🔒 {error_msg}\n\nI can only help you **retrieve and analyze** data, not modify it. Please ask a question about viewing or analyzing your database information."
        
        # Step 3: Execute query if confidence is reasonable
        if sql_query and confidence > 0.4:
            try:
                sql_result = db.run(sql_query)
                
                # Step 4: Convert to natural language
                if sql_result and sql_result.strip() and sql_result != "[]":
                    # Debug logging
                    print(f"RAW SQL RESULT: {sql_result[:200]}...")
                    
                    cleaned_result = clean_sql_results(sql_result)
                    
                    print(f"CLEANED RESULT: {cleaned_result[:200]}...")
                    
                    natural_response = generate_natural_language_response(
                        sanitized_query, 
                        cleaned_result, 
                        llm,
                        custom_directive=custom_directive
                    )
                    
                    print(f"NATURAL RESPONSE: {natural_response[:200]}...")
                    
                    return natural_response
                else:
                    return "I couldn't find any results matching your query. Could you try rephrasing or asking something else?"
                    
            except Exception as sql_error:
                print(f"SQL Execution Error: {sql_error}")
                # Fallback to SQL agent
                return fallback_to_sql_agent(sanitized_query, db, llm, custom_directive)
        
        else:
            # Low confidence or out-of-scope query
            if confidence == 0.0:
                # Check if it's a modification request
                if any(keyword in reasoning.lower() for keyword in ['modify', 'update', 'delete', 'insert', 'change', 'remove']):
                    return f"🔒 **Security Notice:** This chatbot is read-only and cannot modify database contents.\n\n{reasoning}\n\nI can help you view and analyze data. What would you like to know about your database?"
                else:
                    clean_reasoning = reasoning.replace("SQL query", "search").replace("generate", "find").replace("database query", "information")
                    return f"I apologize, but I need more information. {clean_reasoning}\n\nWhat would you like to know?"
            elif confidence < 0.4:
                return "I'm not quite sure what you're asking for. Could you please provide more details or rephrase your question?"
            
    except Exception as e:
        print(f"Processing Error: {e}")
        return f"I encountered an error processing your question. Could you try rephrasing it?"


def fallback_to_sql_agent(user_query: str, db, llm, custom_directive: str = None) -> str:
    """
    Fallback to LangChain SQL Agent for complex queries - SAME LOGIC
    """
    try:
        agent = create_sql_agent_fallback(db, llm)
        
        # Add security instruction to agent
        secure_query = f"[READ-ONLY MODE] {user_query}. Only generate SELECT queries."
        result = agent.invoke({"input": secure_query})
        
        # Double-check the agent didn't generate modification queries
        output = result.get("output", "")
        # Clean any raw SQL results in agent output
        if "[(" in output or "Decimal(" in output:
            output = clean_sql_results(output)
        if any(keyword in output.upper() for keyword in ['INSERT', 'UPDATE', 'DELETE', 'DROP', 'ALTER']):
            return "🔒 Security Alert: Cannot execute data modification queries. This chatbot is read-only."
        
        return output if output else "I couldn't process that request. Please try rephrasing."
    except Exception as e:
        print(f"Agent Error: {e}")
        return "I'm having trouble understanding that question. Could you rephrase it?"


@chat_bp.route('/api/chat', methods=['POST'])
def chat():
    """Process chat message"""
    try:
        init_session()
        
        # Check if database is connected
        if not session.get('db_connected', False):
            return jsonify({
                'success': False,
                'message': 'Please connect to a database first'
            }), 400
        
        data = request.get_json()
        user_message = data.get('message', '').strip()
        
        if not user_message:
            return jsonify({
                'success': False,
                'message': 'Message cannot be empty'
            }), 400
        
        # Add user message to history
        messages = session.get('messages', [])
        messages.append({
            "role": "user",
            "content": user_message
        })
        session['messages'] = messages
        
        # Process query
        response_text = process_user_query(user_message)
        
        # Add assistant response to history
        messages.append({
            "role": "assistant",
            "content": response_text
        })
        session['messages'] = messages
        
        return jsonify({
            'success': True,
            'response': response_text
        }), 200
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Chat error: {str(e)}'
        }), 500


@chat_bp.route('/api/chat/history', methods=['GET'])
def get_history():
    """Get chat history"""
    try:
        init_session()
        messages = session.get('messages', [])
        
        return jsonify({
            'success': True,
            'messages': messages
        }), 200
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error getting history: {str(e)}'
        }), 500


@chat_bp.route('/api/chat/clear', methods=['DELETE'])
def clear_history():
    """Clear chat history"""
    try:
        init_session()
        session['messages'] = []
        
        return jsonify({
            'success': True,
            'message': 'Chat history cleared'
        }), 200
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error clearing history: {str(e)}'
        }), 500
