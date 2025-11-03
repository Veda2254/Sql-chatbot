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
        context += "- If user says 'them/they/it/these/those', identify what entity they refer to from history\n"
        context += "- If user says 'each/all of them', determine which table/entities they mean\n"
        context += "- If user asks 'where can I find X', identify location-related columns in the schema and JOIN as needed\n"
        context += "- If previous query showed a LIST of items, follow-ups likely refer to that list\n"
        context += "- If previous query showed SPECIFIC items, follow-ups refer to those items\n"
        context += "="*50 + "\n"
    
    prompt = f"""You are an expert SQL query generator. Your task is to convert natural language questions into valid SQL queries based on the provided database schema.

{schema_info['description']}

RELATIONSHIPS:
{json.dumps(schema_info['relationships'], indent=2)}
{context}
USER QUESTION: "{user_query}"

TASK:
1. Analyze what the user is asking for
2. **CRITICAL - CONTEXT RESOLUTION**: 
   - If the user uses pronouns (it, they, them, their, these, those) or words like "each", "all of them", look at the conversation history
   - Identify WHAT SPECIFIC ENTITIES were discussed in the previous exchange
   - For questions with pronouns, resolve them to the specific items/entities from previous queries
   - If previous query returned a list, "them/these/those" refers to items in that list
   - If previous query was about specific entities, follow-up questions refer to those entities
3. Determine which tables and columns are needed based on the schema provided
4. Identify relevant entities by matching user's terms with table/column names and sample data
5. Generate a valid SQL query to answer the question
6. Include JOINs when data spans multiple related tables
7. Use aggregation functions (COUNT, SUM, AVG, MAX, MIN) when appropriate
8. Include WHERE, GROUP BY, ORDER BY, and LIMIT clauses as needed

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
- **Common patterns requiring subqueries:**
  - Average value per parent record (e.g., average transaction value, average project cost)
  - Total value across all parent records where each has multiple detail records
  - Maximum/minimum parent record value where value is sum of details
  - Count of parent records meeting criteria based on aggregated detail values

FOLLOW-UP QUERY PATTERNS:
- "Which [entities] have them?" after listing items → JOIN items + relationships + related_entities WHERE item_id IN (previous results)
- "How many does each have?" after listing entities → JOIN with related table, GROUP BY entity
- "Show me their details" after COUNT query → SELECT detailed info about those items
- "Where can I find it?" after showing a specific item → JOIN to get location/relationship info from related tables

IMPORTANT RULES:
- Return ONLY valid SQL (MySQL syntax)
- Use table and column names EXACTLY as shown in the schema above
- **CRITICAL**: If the question asks for data that DOES NOT EXIST in any table/column in the schema, return confidence = 0.0 and set sql_query = null
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
- For ANY question requiring data not present in the schema, return confidence = 0.0 with explanation in reasoning

QUERY OPTIMIZATION:
- Use appropriate JOIN types (INNER, LEFT, RIGHT) based on the question
- Leverage primary and foreign keys for efficient joins
- Prefer simpler queries when they achieve the same result
- Use subqueries when you need to aggregate aggregated data

ERROR HANDLING:
- If the question is ambiguous, generate the most reasonable interpretation
- **CRITICAL**: If the question asks for information that doesn't exist in the schema, return confidence = 0.0, sql_query = null, and explain what's missing
- If required columns/tables are not available, DO NOT attempt to generate SQL - return low confidence instead

RESPONSE FORMAT (JSON):
{{
    "sql_query": "SELECT ... FROM ... WHERE ...",
    "reasoning": "Brief explanation of what this query does and why these tables/columns were chosen",
    "confidence": 0.0-1.0,
    "tables_used": ["table1", "table2"]
}}

EXAMPLES OF QUERY PATTERNS:

Average Value from Master-Detail Relationship (CORRECT APPROACH):
User: "What is the average value per parent record?" or "What's the average total?"
{{
    "sql_query": "SELECT AVG(parent_total) as average_value FROM (SELECT parent_id, SUM(quantity_col * value_col) as parent_total FROM detail_table GROUP BY parent_id) as totals",
    "reasoning": "Calculating average by first computing the total value of each parent record (sum of quantity × value for all child records), then averaging those parent totals. This ensures we get the average per parent, not per child record.",
    "confidence": 0.95,
    "tables_used": ["detail_table"]
}}

Total Value Across All Records (CORRECT APPROACH):
User: "What's the total value?" or "How much in total?"
{{
    "sql_query": "SELECT SUM(quantity_col * value_col) as total_value FROM detail_table",
    "reasoning": "Calculating total value by multiplying quantity by value for each detail record and summing all results",
    "confidence": 0.95,
    "tables_used": ["detail_table"]
}}

Aggregated Value per Category (with JOIN):
User: "What's the average value per category?"
{{
    "sql_query": "SELECT c.category_id, c.category_name, AVG(parent_total) as avg_value FROM categories c JOIN parent_table p ON c.category_id = p.category_id JOIN (SELECT parent_id, SUM(quantity_col * value_col) as parent_total FROM detail_table GROUP BY parent_id) d ON p.parent_id = d.parent_id GROUP BY c.category_id, c.category_name",
    "reasoning": "First calculating total value per parent record, then joining with parent and category tables, finally grouping by category to get average value per category",
    "confidence": 0.9,
    "tables_used": ["categories", "parent_table", "detail_table"]
}}

Simple Count:
User: "How many records are in [table]?"
{{
    "sql_query": "SELECT COUNT(*) as total FROM table_name",
    "reasoning": "Counting all records in the specified table",
    "confidence": 0.95,
    "tables_used": ["table_name"]
}}

Search with Joins:
User: "Where can I find [entity]?"
{{
    "sql_query": "SELECT t1.col1, t2.col2, t2.location_col FROM table1 t1 JOIN table2 t2 ON t1.id = t2.fk_id WHERE t1.name_col LIKE '%entity%'",
    "reasoning": "Joining related tables to find location/relationship information for the specified entity",
    "confidence": 0.9,
    "tables_used": ["table1", "table2"]
}}

Aggregation with Sorting:
User: "What's the highest/lowest [attribute]?"
{{
    "sql_query": "SELECT col1, col2, target_col FROM table_name ORDER BY target_col DESC LIMIT 1",
    "reasoning": "Finding record with maximum value in target column",
    "confidence": 0.95,
    "tables_used": ["table_name"]
}}

Filtered Search:
User: "Show me [items] that meet [criteria]"
{{
    "sql_query": "SELECT col1, col2, col3 FROM table_name WHERE condition1 AND condition2 ORDER BY relevant_col",
    "reasoning": "Filtering records based on user criteria",
    "confidence": 0.9,
    "tables_used": ["table_name"]
}}

Text Pattern Search (Multiple Terms):
User: "Show me [items with specific attribute]" (when sample data shows abbreviations)
{{
    "sql_query": "SELECT col1, col2, col3 FROM table_name WHERE (text_col LIKE '%full_term%' OR text_col LIKE '%abbreviation%') ORDER BY relevant_col",
    "reasoning": "Searching using both full term and common abbreviation found in sample data. Using OR to catch all variations.",
    "confidence": 0.9,
    "tables_used": ["table_name"]
}}

Multi-Column Text Search:
User: "Find items with [keyword]"
{{
    "sql_query": "SELECT col1, col2, col3 FROM table_name WHERE (name_col LIKE '%keyword%' OR description_col LIKE '%keyword%' OR category_col LIKE '%keyword%')",
    "reasoning": "Searching across multiple text columns to find all matches for the keyword",
    "confidence": 0.85,
    "tables_used": ["table_name"]
}}

Follow-up with Pronoun Reference (Generic Pattern):
Previous Query: User asked for items matching certain criteria
Current Query: "Which [related_entities] have them?" or "Where can I find them?"
{{
    "sql_query": "SELECT t1.col, t2.related_col FROM table1 t1 JOIN table2 t2 ON t1.id = t2.fk_id WHERE t1.attribute [previous_filter_condition] ORDER BY relevant_col",
    "reasoning": "User is asking about related entities for the items from the previous query. Applying the same filter condition from conversation history and joining to the related table they're asking about.",
    "confidence": 0.85,
    "tables_used": ["table1", "table2"]
}}

Follow-up with Collective Reference (Generic Pattern):
Previous Query: User listed a set of entities
Current Query: "How many/What [attribute] does each have?" or "Show details for each"
{{
    "sql_query": "SELECT entity_table.name, COUNT(related_table.id) as count FROM entity_table LEFT JOIN related_table ON entity_table.id = related_table.fk_id GROUP BY entity_table.id ORDER BY count DESC",
    "reasoning": "User wants aggregated information for each entity that was listed in the previous response. Using GROUP BY to aggregate per entity.",
    "confidence": 0.9,
    "tables_used": ["entity_table", "related_table"]
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

def generate_natural_language_response(user_query: str, sql_result: str, llm) -> str:
    """
    Converts raw SQL results into natural, conversational language
    """
    
    prompt = f"""You are a helpful assistant. Convert the database query results into a natural, conversational response.

USER ASKED: "{user_query}"

DATABASE RESULTS:
{sql_result}

INSTRUCTIONS:
1. Write a natural, friendly response as if you're talking to someone who asked a question
2. Format any monetary values with appropriate currency symbols (e.g.,₹, $, €, £)
3. Present exact values from the results without modification or rounding unless specifically asked
4. Use bullet points or numbered lists for multiple items
5. Include all relevant details from the query results
6. If no results found, politely say so and suggest the user try rephrasing
7. If there are multiple options, present them clearly and organized
8. Be concise but thorough - provide complete information when multiple details are returned
9. For numerical data, provide context (e.g., "23 records found" not just "23")
10. For comparisons, highlight the differences clearly
11. Use appropriate formatting: bold for emphasis, tables for structured data when helpful

ACCURACY RULES:
- **NEVER add information not present in the database results**
- **NEVER make calculations or assumptions beyond what the data shows**
- **NEVER invent column values, dates, or details that aren't in the results**
- If a field is NULL or missing, say "Not specified" or "Not available"
- Quote exact numbers and values from the results
- If showing quantities or counts, be precise
- Reference the actual data returned, don't make assumptions
- If the results are empty or insufficient to answer fully, acknowledge this limitation
- DO NOT fabricate data to make the answer sound better

TONE:
- Professional but friendly
- Helpful and informative
- Objective - stick to the facts from the database
- Acknowledge when information is incomplete or unavailable

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
    1. Get schema automatically
    2. Generate SQL with LLM (no templates)
    3. Execute query
    4. Convert to natural language
    """
    
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
            user_query, 
            schema_info, 
            llm,
            conversation_history=st.session_state.messages
        )
        
        sql_query = query_info.get('sql_query')
        confidence = query_info.get('confidence', 0.0)
        reasoning = query_info.get('reasoning', '')
        
        print(f"\n{'='*50}")
        print(f"USER QUERY: {user_query}")
        print(f"REASONING: {reasoning}")
        print(f"CONFIDENCE: {confidence}")
        print(f"GENERATED SQL: {sql_query}")
        print(f"{'='*50}\n")
        
        # Step 2: Execute query if confidence is reasonable
        if sql_query and confidence > 0.4:
            try:
                sql_result = db.run(sql_query)
                
                # Step 3: Convert to natural language
                if sql_result and sql_result.strip() and sql_result != "[]":
                    natural_response = generate_natural_language_response(
                        user_query, 
                        sql_result, 
                        llm
                    )
                    return natural_response
                else:
                    return "I couldn't find any results matching your query. Could you try rephrasing or asking something else?"
                    
            except Exception as sql_error:
                print(f"SQL Execution Error: {sql_error}")
                return fallback_to_sql_agent(user_query, db, llm)
        
        else:
            # Low confidence or out-of-scope query
            if confidence == 0.0:
                return f"I apologize, but I cannot answer that question. {reasoning}\n\nThe available database contains information about: {', '.join(schema_info['tables'].keys())}. Please ask a question related to this data."
            else:
                return fallback_to_sql_agent(user_query, db, llm)
            
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
        
        result = agent.invoke({"input": user_query})
        return result.get("output", "I couldn't process that request. Please try rephrasing.")
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


# ==================================================
# DATABASE CONNECTION SIDEBAR
# ==================================================

def show_database_connection_sidebar():
    with st.sidebar:
        st.title("🔌 Database Connection")
        
        if st.session_state.db_connected:
            st.success(f"✅ Connected to: {st.session_state.db_config['database']}")
            st.info(f"**Host:** {st.session_state.db_config['host']}\n**User:** {st.session_state.db_config['user']}")
            
            if st.button("🔄 Change Database", use_container_width=True):
                st.session_state.db_connected = False
                st.session_state.db_config = None
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
                            st.session_state.messages = [{
                                "role": "assistant",
                                "content": f"✅ Successfully connected to **{database}**! Ask me anything about your data."
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
st.caption("Zero hardcoding - Works with any database!")

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