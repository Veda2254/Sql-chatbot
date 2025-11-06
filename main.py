import streamlit as st
import mysql.connector
import os
from dotenv import load_dotenv
from urllib.parse import quote_plus
from sqlalchemy import create_engine, inspect
import re
import json

# LangChain Imports
from langchain_community.utilities import SQLDatabase
from langchain_groq import ChatGroq
from langchain_community.agent_toolkits.sql.base import create_sql_agent
from langchain_community.agent_toolkits.sql.toolkit import SQLDatabaseToolkit
from langchain.agents import AgentExecutor
import langchain
from langchain_community.cache import InMemoryCache

langchain.llm_cache = InMemoryCache()

# --- PAGE CONFIGURATION ---
st.set_page_config(page_title="Universal DB Chatbot", page_icon="🤖", layout="centered")

# --- LOAD ENVIRONMENT VARIABLES ---
load_dotenv()
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

# ==================================================
# SECURITY: SQL INJECTION & MODIFICATION PREVENTION
# ==================================================

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


# --- DATABASE CONNECTION ---
def get_db_connection():
    try:
        db_config = st.session_state.get('db_config', None)
        if not db_config:
            return None
        return mysql.connector.connect(**db_config)
    except mysql.connector.Error as err:
        st.error(f"Database connection error: {err}")
        return None

@st.cache_resource
def get_db_chain(_db_config):
    """Create database connection with user-provided credentials"""
    db_uri = f"mysql+mysqlconnector://{_db_config['user']}:{quote_plus(_db_config['password'])}@{_db_config['host']}/{_db_config['database']}"
    engine = create_engine(db_uri)
    return SQLDatabase(engine=engine)


# ==================================================
# CORE: AUTOMATIC SCHEMA DISCOVERY
# ==================================================

@st.cache_resource
def get_database_schema_info(_db_config):
    """
    Automatically extracts complete database schema information
    NO hardcoding - works with ANY database structure
    """
    db = get_db_chain(_db_config)
    engine = db._engine
    inspector = inspect(engine)
    
    schema_info = {
        'tables': {},
        'relationships': [],
        'description': ""
    }
    
    # Extract all table information
    for table_name in inspector.get_table_names():
        columns = inspector.get_columns(table_name)
        pk = inspector.get_pk_constraint(table_name)
        fks = inspector.get_foreign_keys(table_name)
        
        # Get sample data to understand content
        try:
            sample_query = f"SELECT * FROM {table_name} LIMIT 3"
            sample_data = db.run(sample_query)
        except:
            sample_data = "No sample data available"
        
        schema_info['tables'][table_name] = {
            'columns': [
                {
                    'name': col['name'],
                    'type': str(col['type']),
                    'nullable': col['nullable']
                } for col in columns
            ],
            'primary_key': pk.get('constrained_columns', []),
            'foreign_keys': fks,
            'sample_data': sample_data
        }
        
        # Track relationships
        for fk in fks:
            schema_info['relationships'].append({
                'from_table': table_name,
                'from_column': fk['constrained_columns'][0] if fk['constrained_columns'] else None,
                'to_table': fk['referred_table'],
                'to_column': fk['referred_columns'][0] if fk['referred_columns'] else None
            })
    
    # Generate human-readable description
    description = "DATABASE SCHEMA:\n\n"
    for table_name, info in schema_info['tables'].items():
        description += f"📊 Table: {table_name}\n"
        description += f"   Columns: {', '.join([col['name'] + ' (' + col['type'] + ')' for col in info['columns']])}\n"
        if info['foreign_keys']:
            for fk in info['foreign_keys']:
                description += f"   🔗 Links to: {fk['referred_table']}\n"
        description += f"   Sample: {str(info['sample_data'])[:100]}...\n\n"
    
    schema_info['description'] = description
    return schema_info


# ==================================================
# PURE LLM QUERY GENERATOR (No Hardcoding)
# ==================================================

def generate_sql_query_with_llm(user_query: str, schema_info: dict, llm, conversation_history: list = None) -> dict:
    """
    Uses LLM to:
    1. Understand user intent
    2. Generate appropriate SQL query
    3. Explain the reasoning
    
    NO hardcoded patterns or templates!
    """
    
    # Get custom directive if available
    custom_directive = st.session_state.get('chatbot_directive', None)
    directive_section = ""
    if custom_directive:
        directive_section = f"""
{'='*50}
CUSTOM CHATBOT DIRECTIVE:
{'='*50}
{custom_directive}

IMPORTANT: Follow the directive above when interpreting user questions and generating responses.
This directive defines your role, domain expertise, and behavioral guidelines.
{'='*50}

"""
    
    # Build conversation context
    context = ""
    if conversation_history and len(conversation_history) > 1:
        # Get last 4 exchanges for better context
        recent_messages = conversation_history[-8:]  # Last 4 Q&A pairs
        context = "\n" + "="*50 + "\n"
        context += "CONVERSATION HISTORY (for context resolution):\n"
        context += "="*50 + "\n"
        for i, msg in enumerate(recent_messages):
            role = "User" if msg["role"] == "user" else "Assistant"
            # Include more content for assistant responses to capture what was retrieved
            max_length = 500 if msg["role"] == "assistant" else 200
            content = msg['content'][:max_length]
            if len(msg['content']) > max_length:
                content += "..."
            context += f"{role}: {content}\n\n"
        
        context += "CRITICAL INSTRUCTIONS FOR FOLLOW-UP QUESTIONS:\n"
        context += "- ALWAYS look at conversation history FIRST before determining confidence\n"
        context += "- If user says 'them/they/it/these/those', identify what entity they refer to from history\n"
        context += "- If user says 'each/all of them', determine which table/entities they mean\n"
        context += "- Single word responses like 'yes', 'no', 'sure' after a question = user agreeing/responding to assistant's previous question\n"
        context += "- For single-word or short responses, check if assistant asked a question - if yes, confidence should be LOW (user needs to clarify)\n"
        context += "- If previous query showed a LIST of items, follow-ups likely refer to that list\n"
        context += "- If previous query showed SPECIFIC items, follow-ups refer to those items\n"
        context += "- For vague follow-ups without clear intent, return confidence = 0.2 with reasoning asking for clarification\n"
        context += "="*50 + "\n"
    
    prompt = f"""You are an expert SQL query generator. Your task is to convert natural language questions into valid SQL queries based on the provided database schema.

🔒 CRITICAL SECURITY REQUIREMENT:
**YOU MUST ONLY GENERATE SELECT QUERIES - NO DATA MODIFICATION ALLOWED**
- NEVER use INSERT, UPDATE, DELETE, DROP, CREATE, ALTER, TRUNCATE, or any other data modification statements
- If user asks to modify/delete/update/insert data, return confidence = 0.0 and explain this is a read-only chatbot
- Your purpose is to RETRIEVE and ANALYZE data, not to modify it

{directive_section}
{schema_info['description']}

RELATIONSHIPS:
{json.dumps(schema_info['relationships'], indent=2)}
{context}
USER QUESTION: "{user_query}"

CONTEXT AWARENESS:
- Analyze the conversation history carefully before setting confidence
- If user's question is a short response (1-3 words) and assistant previously asked a question, this likely needs clarification
- Don't assume vague responses have clear intent - ask for clarification instead
- Check if the user is answering a previous question or asking a new question

TASK:
1. Analyze what the user is asking for
2. **CRITICAL - SECURITY CHECK**: If the question asks to modify/delete/update/insert data, IMMEDIATELY return confidence = 0.0
3. **CRITICAL - CONTEXT RESOLUTION**: 
   - If the user uses pronouns (it, they, them, their, these, those) or words like "each", "all of them", look at the conversation history
   - Identify WHAT SPECIFIC ENTITIES were discussed in the previous exchange
   - For questions with pronouns, resolve them to the specific items/entities from previous queries
   - If previous query returned a list, "them/these/those" refers to items in that list
   - If previous query was about specific entities, follow-up questions refer to those entities
4. Determine which tables and columns are needed based on the schema provided
5. Identify relevant entities by matching user's terms with table/column names and sample data
6. Generate a valid SELECT-ONLY SQL query to answer the question
7. Include JOINs when data spans multiple related tables
8. Use aggregation functions (COUNT, SUM, AVG, MAX, MIN) when appropriate
9. Include WHERE, GROUP BY, ORDER BY, and LIMIT clauses as needed

COMMUNICATION RULES FOR REASONING:
- NEVER mention "SQL query", "database query", "SELECT statement" or technical terms in reasoning
- Instead use: "search for", "find", "retrieve information", "look up data"
- If user provides insufficient context, reasoning should say: "I need more details to find what you're looking for. Could you please be more specific?"
- If it's a vague follow-up (like just 'yes'), reasoning should say: "Your response 'yes' doesn't give me enough context. What specific information would you like me to find?"
- Be conversational and user-friendly in all reasoning text
- Example GOOD reasoning: "I need more details to find the specific films you're interested in"
- Example BAD reasoning: "Cannot generate SQL query due to insufficient context"

CRITICAL MATHEMATICAL CALCULATION RULES:
**For questions about averages, totals, or aggregations involving master-detail relationships:**
- **ALWAYS calculate the complete value at the detail level FIRST, then aggregate**
- **When dealing with parent-child/master-detail table relationships:**
  - Step 1: Calculate totals at the child/detail level (e.g., multiply quantity × unit_value)
  - Step 2: Group by the parent/master record identifier
  - Step 3: Apply aggregate function (AVG, SUM, MAX, MIN) on the grouped results
- **Always use subqueries when aggregating aggregations** (e.g., average of sums, maximum of totals)
- **PATTERN FOR AGGREGATING ACROSS RELATED TABLES:**
  ```sql
  -- CORRECT: Calculate total per parent record first, then aggregate
  SELECT AGG_FUNCTION(parent_total) FROM (
      SELECT parent_id, SUM(quantity_col * value_col) as parent_total
      FROM detail_table
      GROUP BY parent_id
  ) as subquery
  
  -- WRONG: Don't aggregate the detail records directly
  -- AGG_FUNCTION(value_col) or AGG_FUNCTION(quantity_col * value_col) from detail_table
  ```

FOLLOW-UP QUERY PATTERNS:
- "Which [entities] have them?" after listing items → JOIN items + relationships + related_entities WHERE item_id IN (previous results)
- "How many does each have?" after listing entities → JOIN with related table, GROUP BY entity
- "Show me their details" after COUNT query → SELECT detailed info about those items
- "Where can I find it?" after showing a specific item → JOIN to get location/relationship info from related tables

IMPORTANT RULES:
- **ABSOLUTE RULE: Return ONLY SELECT queries - NEVER INSERT, UPDATE, DELETE, DROP, etc.**
- Return ONLY valid SQL (MySQL syntax)
- Use table and column names EXACTLY as shown in the schema above
- **CRITICAL**: If the question asks for data that DOES NOT EXIST in any table/column in the schema, return confidence = 0.0 and set sql_query = null
- **CRITICAL**: If the question asks to MODIFY data in any way, return confidence = 0.0 and explain read-only limitation
- For text searches, use LIKE with wildcards: WHERE column LIKE '%search_term%'
- Use CASE-INSENSITIVE matching: LOWER(column) LIKE LOWER('%search_term%')
- **CRITICAL TEXT SEARCH STRATEGY**: When searching for concepts in text fields:
  * First, look at the sample data to identify common abbreviations and patterns used
  * Search for both full terms AND common abbreviations/synonyms
  * Use multiple LIKE conditions with OR: `WHERE column LIKE '%term1%' OR column LIKE '%term2%' OR column LIKE '%term3%'`
  * Analyze sample data to understand domain-specific abbreviations and terminology
  * For any search term, consider: full name, abbreviations, common synonyms, plural/singular forms
- For partial name matches, search across ALL relevant text columns (not just one)
- When searching for items/entities, check ALL text columns including: name, title, description, type, category, model, brand, etc.
- For "where can I find X" questions, identify location-related columns (address, location, place, city, region, etc.) and include them
- For "most/least/highest/lowest" questions, use ORDER BY with LIMIT
- For "how many" questions, use COUNT(*)
- For comparisons, use appropriate operators (>, <, =, >=, <=, BETWEEN)
- Handle NULL values with IS NULL or IS NOT NULL
- Use DISTINCT when avoiding duplicates is necessary
- For complex filters, combine conditions with AND/OR
- Always include columns that provide meaningful context to the answer
- For numeric columns (amounts, quantities, counts, etc.), include them in SELECT when relevant
- For availability/status queries, check for positive values or active status in relevant columns
- Analyze the sample data to understand what information each column contains and what values are typical

OUT-OF-SCOPE DETECTION:
- If the question mentions concepts not present in any table/column → confidence = 0.0
- If the question asks about data types (dates, amounts, statuses) that aren't in the schema → confidence = 0.0
- If the question requires calculations on non-existent columns → confidence = 0.0
- **If the question asks to modify/update/delete/insert data → confidence = 0.0 with "read-only" explanation**
- For ANY question requiring data not present in the schema, return confidence = 0.0 with explanation in reasoning

QUERY OPTIMIZATION:
- Use appropriate JOIN types (INNER, LEFT, RIGHT) based on the question
- Leverage primary and foreign keys for efficient joins
- Prefer simpler queries when they achieve the same result
- Use subqueries when you need to aggregate aggregated data

ERROR HANDLING:
- If the question is ambiguous, generate the most reasonable interpretation
- **CRITICAL**: If the question asks for information that doesn't exist in the schema, return confidence = 0.0, sql_query = null, and explain what's missing
- **CRITICAL**: If the question asks to modify data, return confidence = 0.0, sql_query = null, and explain read-only limitation
- If required columns/tables are not available, DO NOT attempt to generate SQL - return low confidence instead

RESPONSE FORMAT (JSON):
{{
    "sql_query": "SELECT ... FROM ... WHERE ...",
    "reasoning": "Brief explanation of what this query does and why these tables/columns were chosen",
    "confidence": 0.0-1.0,
    "tables_used": ["table1", "table2"]
}}

Now generate the SQL query for: "{user_query}"

Return ONLY the JSON response, no other text.
"""
    
    try:
        response = llm.invoke(prompt)
        response_text = response.content if hasattr(response, 'content') else str(response)
        
        # Extract JSON from response
        json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
        if json_match:
            result = json.loads(json_match.group())
            return result
        else:
            return {
                "sql_query": None,
                "reasoning": "Could not generate SQL query",
                "confidence": 0.0,
                "tables_used": []
            }
    except Exception as e:
        print(f"LLM Query Generation Error: {e}")
        return {
            "sql_query": None,
            "reasoning": f"Error: {str(e)}",
            "confidence": 0.0,
            "tables_used": []
        }


# ==================================================
# NATURAL LANGUAGE RESPONSE GENERATOR
# ==================================================

def clean_sql_results(sql_result: str) -> str:
    """
    Preprocesses raw SQL results to remove Python formatting artifacts
    Converts Decimal objects, tuples, and other Python structures to clean text
    """
    import ast
    from decimal import Decimal
    
    try:
        # Try to parse the result as Python literal
        parsed = ast.literal_eval(sql_result)
        
        cleaned_rows = []
        
        # Handle list of tuples (most common case)
        if isinstance(parsed, list):
            for item in parsed:
                if isinstance(item, tuple):
                    cleaned_items = []
                    for value in item:
                        if isinstance(value, (int, float)) or (hasattr(value, '__class__') and 'Decimal' in str(type(value))):
                            # Convert to float for cleaner display
                            cleaned_items.append(str(float(value)))
                        elif isinstance(value, str):
                            # Title case for names
                            cleaned_items.append(value.title())
                        else:
                            cleaned_items.append(str(value))
                    cleaned_rows.append(" | ".join(cleaned_items))
        
        # Return cleaned result as pipe-separated values
        return "\n".join(cleaned_rows)
    
    except:
        # If parsing fails, do regex-based cleaning
        import re
        
        # Remove Decimal() wrappers
        cleaned = re.sub(r"Decimal\('([^']+)'\)", r'\1', sql_result)
        
        # Remove extra quotes around strings
        cleaned = re.sub(r"'([A-Z\s]+)'", r'\1', cleaned)
        
        # Convert to title case
        def title_case_match(match):
            return match.group(0).title()
        
        cleaned = re.sub(r'\b[A-Z]{2,}\b', title_case_match, cleaned)
        
        return cleaned

def generate_natural_language_response(user_query: str, sql_result: str, llm) -> str:
    """
    Converts raw SQL results into natural, conversational language
    """
    
    # Get custom directive if available
    custom_directive = st.session_state.get('chatbot_directive', None)
    directive_section = ""
    if custom_directive:
        directive_section = f"""
CUSTOM CHATBOT DIRECTIVE:
{custom_directive}

CRITICAL: Your response MUST align with the directive above. Adopt the specified role, tone, and domain expertise when crafting your answer.
{'='*50}

"""
    
    prompt = f"""{directive_section}You are a helpful assistant. Convert the database query results into a natural, conversational response.

USER ASKED: "{user_query}"

DATABASE RESULTS:
{sql_result}

CRITICAL FORMATTING REQUIREMENT 

The DATABASE RESULTS below contain raw Python data structures (tuples, Decimal objects, lists, etc.).
You MUST parse and format them into clean, human-readable text.

**NEVER show raw data like:**
- [('FILM_NAME', Decimal('4.99'), Decimal('9.99'))]
- ('ACTOR', 'NAME')
- Decimal('4.99')
- Raw tuple or list notation

**ALWAYS format as:**
- Film/actor names in Title Case with proper spacing
- Numbers as clean values: $4.99 (not Decimal('4.99'))
- Present data in organized lists, tables, or paragraphs
- Remove ALL Python syntax (parentheses, quotes, Decimal(), brackets, commas between values)

FORMATTING EXAMPLES:

RAW: [('CONTROL ANTHEM', Decimal('4.99'), Decimal('9.99'), Decimal('0.499499'))]
CORRECT: "Control Anthem has a rental rate of $4.99 and replacement cost of $9.99, with a ratio of 0.50"

RAW: [('HORROR',), ('ACTION',), ('COMEDY',)]
CORRECT: "The categories are Horror, Action, and Comedy"

RAW: [('TOM', 'HANKS'), ('MEG', 'RYAN')]
CORRECT: "Tom Hanks and Meg Ryan"

---

INSTRUCTIONS:

1. Parse ALL raw database output - Never display raw Python data structures
2. Write a natural, friendly response as if you're talking to someone who asked a question
3. CRITICAL DATA CONVERSION:
   - Convert Decimal('X.XX') to clean numbers: $X.XX for money, X.XX for ratios/decimals
   - Convert ('FIRST', 'LAST') to "First Last" (Title Case with space)
   - Convert ('SINGLE_VALUE',) to "Single Value"
   - Remove all parentheses, quotes, brackets, and technical notation
4. Format monetary values with appropriate currency symbols (e.g., ₹, $, €, £)
5. Present exact values from the results without modification or rounding unless specifically asked
6. Use bullet points, numbered lists, or tables for multiple items:
   - For 2-5 items: Use bullet points
   - For 6+ items: Use numbered list or markdown table
   - For items with multiple fields: Use formatted table
7. Include all relevant details from the query results
8. If no results found, politely say so and suggest the user try rephrasing
9. Be concise but thorough - provide complete information when multiple details are returned
10. For numerical data, provide context (e.g., "23 films found" not just "23")
11. For comparisons, highlight the differences clearly
12. Names and Text Formatting:
    - Format all names in Title Case (e.g., "John Smith" not "JOHN SMITH" or "('JOHN', 'SMITH')")
    - Remove database formatting artifacts (parentheses, quotes, commas between name parts)
    - For categories/genres, use proper capitalization (e.g., "Action" not "ACTION")
    - Join multi-part names with spaces (first name + last name)
13. NEVER use technical database terms like "SQL", "query", "SELECT", "JOIN", "tuple", "Decimal" in your response
14. Speak naturally as if explaining to a non-technical person
15. If you cannot provide an answer, politely ask for clarification without mentioning technical limitations
16. For complex data with multiple fields per record:
    - Create a formatted markdown table OR
    - Use numbered list with clear labels
    - Example: "1. Control Anthem - Rental: $4.99, Replacement: $9.99, Ratio: 0.50"

ACCURACY RULES:
- NEVER add information not present in the database results
- NEVER make calculations or assumptions beyond what the data shows
- NEVER invent column values, dates, or details that aren't in the results
- If a field is NULL or missing, say "Not specified" or "Not available"
- Quote exact numbers and values from the results (after converting from Decimal format)
- If showing quantities or counts, be precise
- Reference the actual data returned, don't make assumptions
- If the results are empty or insufficient to answer fully, acknowledge this limitation
- DO NOT fabricate data to make the answer sound better

DATA PRESENTATION RULES:
- PRIMARY RULE: Convert ALL database tuples and Decimal objects to natural language
- Example: [('TOM', 'HANKS'), ('MEG', 'RYAN')] → "Tom Hanks and Meg Ryan"
- Example: [('ACTION',), ('COMEDY',)] → "Action and Comedy"
- Example: Decimal('4.99') → $4.99 or 4.99 (depending on context)
- Example: [('FILM', Decimal('4.99'), Decimal('19.99'))] → "Film - Rental: $4.99, Cost: $19.99"
- Always format names and categories in readable Title Case format
- Remove all technical database formatting (quotes, parentheses, tuple notation, Decimal())
- For ratios or percentages, format as: 0.50 or 50% (whichever is more natural)

TONE:
- Professional but friendly
- Helpful and informative
- Objective - stick to the facts from the database
- Acknowledge when information is incomplete or unavailable
- Never sound robotic or technical

RESPONSE:"""
    
    try:
        response = llm.invoke(prompt)
        return response.content if hasattr(response, 'content') else str(response)
    except Exception as e:
        return f"Here are the results:\n\n{sql_result}"


# ==================================================
# MAIN INTELLIGENT QUERY PROCESSOR
# ==================================================

def process_user_query(user_query: str) -> str:
    """
    Complete pipeline:
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
    db_config = st.session_state.get('db_config')
    if not db_config:
        return "Please connect to a database first using the sidebar."
    
    db = get_db_chain(db_config)
    schema_info = get_database_schema_info(db_config)
    
    llm = ChatGroq(
        model_name="llama-3.3-70b-versatile",
        groq_api_key=GROQ_API_KEY,
        temperature=0.3
    )
    
    try:
        # Step 1: Generate SQL query using LLM with conversation history
        query_info = generate_sql_query_with_llm(
            sanitized_query, 
            schema_info, 
            llm,
            conversation_history=st.session_state.messages
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
                    cleaned_result = clean_sql_results(sql_result)
                    natural_response = generate_natural_language_response(
                        sanitized_query, 
                        cleaned_result, 
                        llm
                    )
                    return natural_response
                else:
                    return "I couldn't find any results matching your query. Could you try rephrasing or asking something else?"
                    
            except Exception as sql_error:
                print(f"SQL Execution Error: {sql_error}")
                return fallback_to_sql_agent(sanitized_query, db, llm)
        
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


def fallback_to_sql_agent(user_query: str, db: SQLDatabase, llm) -> str:
    """
    Fallback to LangChain SQL Agent for complex queries
    """
    try:
        toolkit = SQLDatabaseToolkit(db=db, llm=llm)
        agent = create_sql_agent(
            llm=llm,
            toolkit=toolkit,
            verbose=True,
            handle_parsing_errors=True,
            max_iterations=10
        )
        
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


# ==================================================
# SESSION STATE INITIALIZATION
# ==================================================

if 'messages' not in st.session_state:
    st.session_state.messages = []
if 'db_config' not in st.session_state:
    st.session_state.db_config = None
if 'db_connected' not in st.session_state:
    st.session_state.db_connected = False
if 'chatbot_directive' not in st.session_state:
    st.session_state.chatbot_directive = None


# ==================================================
# DATABASE CONNECTION SIDEBAR
# ==================================================

def show_database_connection_sidebar():
    with st.sidebar:
        st.title("🔌 Database Connection")
        
        if st.session_state.db_connected:
            st.success(f"✅ Connected to: {st.session_state.db_config['database']}")
            st.info(f"**Host:** {st.session_state.db_config['host']}\n**User:** {st.session_state.db_config['user']}")
            
            # Security notice
            st.warning("🔒 **Read-Only Mode**: This chatbot can only view data, not modify it.")
            
            # Show current directive
            if st.session_state.chatbot_directive:
                with st.expander("📋 Current Directive", expanded=False):
                    st.write(st.session_state.chatbot_directive)
            
            if st.button("🔄 Change Database", use_container_width=True):
                st.session_state.db_connected = False
                st.session_state.db_config = None
                st.session_state.chatbot_directive = None
                st.session_state.messages = []
                # Clear cache when switching databases
                get_db_chain.clear()
                get_database_schema_info.clear()
                st.rerun()
        else:
            st.warning("⚠️ No database connected")
            
            with st.form("db_connection_form"):
                st.subheader("Connect to MySQL Database")
                
                host = st.text_input("Host", value="localhost", help="Database server address")
                port = st.number_input("Port", value=3306, min_value=1, max_value=65535)
                user = st.text_input("Username", value="root", help="Database username")
                password = st.text_input("Password", type="password", help="Database password")
                database = st.text_input("Database Name", help="Name of the database to connect to")
                
                st.divider()
                st.subheader("🎯 Chatbot Directive")
                directive = st.text_area(
                    "Custom Behavior Directive (Optional)",
                    placeholder="Example: Behave as a medical hospital chatbot that helps extract patient information, appointment schedules, and medical records from the database. Always maintain HIPAA compliance and patient privacy in responses.",
                    help="Define how you want the chatbot to behave and respond. This will guide the chatbot's tone, focus, and domain expertise.",
                    height=120
                )
                
                submitted = st.form_submit_button("🔗 Connect", use_container_width=True)
                
                if submitted:
                    if not all([host, user, database]):
                        st.error("Please fill in all required fields (Host, Username, Database Name)")
                    else:
                        # Test connection
                        test_config = {
                            'host': host,
                            'port': port,
                            'user': user,
                            'password': password,
                            'database': database
                        }
                        
                        try:
                            # Test MySQL connection
                            test_conn = mysql.connector.connect(**test_config)
                            test_conn.close()
                            
                            # If successful, save to session state
                            st.session_state.db_config = test_config
                            st.session_state.db_connected = True
                            st.session_state.chatbot_directive = directive.strip() if directive.strip() else None
                            
                            welcome_msg = f"✅ Successfully connected to **{database}**!"
                            if st.session_state.chatbot_directive:
                                welcome_msg += f"\n\n🎯 **Active Directive:** {st.session_state.chatbot_directive[:100]}..."
                            welcome_msg += "\n\nAsk me anything about your data!"
                            
                            st.session_state.messages = [{
                                "role": "assistant",
                                "content": welcome_msg
                            }]
                            st.success(f"✅ Successfully connected to {database}!")
                            st.rerun()
                            
                        except mysql.connector.Error as err:
                            st.error(f"❌ Connection failed: {err}")


# ==================================================
# MAIN CHATBOT UI
# ==================================================

# Show database connection sidebar
show_database_connection_sidebar()

# Main chatbot interface
st.title("🤖 Universal Database Chatbot")
st.caption("🔒 Secure read-only access - Zero hardcoding - Works with any database!")

if st.session_state.db_connected:
    st.info(f"💬 Connected to: **{st.session_state.db_config['database']}** | Ask me anything!")
else:
    st.warning("⚠️ Please connect to a database using the sidebar before asking questions.")

# Display chat history
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# User input
if prompt := st.chat_input("Ask me anything about the data...", disabled=not st.session_state.db_connected):
    st.session_state.messages.append({"role": "user", "content": prompt})
    
    with st.chat_message("user"):
        st.markdown(prompt)
    
    with st.chat_message("assistant"):
        with st.spinner("🤔 Analyzing your question..."):
            # Main processing
            response_text = process_user_query(prompt)
            
            st.markdown(response_text)
            st.session_state.messages.append({
                "role": "assistant", 
                "content": response_text
            })

# Clear chat button
if st.session_state.messages:
    if st.button("🗑️ Clear Chat History"):
        st.session_state.messages = []
        st.rerun()