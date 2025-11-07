"""
SQL query generation using LLM - Core logic preserved from original
"""
import re
import json


def generate_sql_query_with_llm(user_query: str, schema_info: dict, llm, conversation_history: list = None, custom_directive: str = None) -> dict:
    """
    Uses LLM to:
    1. Understand user intent
    2. Generate appropriate SQL query
    3. Explain the reasoning
    
    NO hardcoded patterns or templates!
    """
    
    # Build custom directive section if provided
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
            role = "User" if msg.get("role") == "user" else "Assistant"
            # Include more content for assistant responses to capture what was retrieved
            max_length = 500 if msg.get("role") == "assistant" else 200
            content = msg.get('content', '')[:max_length]
            if len(msg.get('content', '')) > max_length:
                content += "..."
            context += f"{role}: {content}\n\n"
        
        context += """
🎯 ENHANCED FOLLOW-UP QUESTION DETECTION RULES:

**STEP 1: Determine if this is a FOLLOW-UP or NEW question**

IS A FOLLOW-UP if:
✅ Uses pronouns referring to previous results: "them", "they", "it", "those", "these", "their"
✅ Uses relative references: "each", "all of them", "any of them", "the same", "others"
✅ Asks for MORE details about previous results: "show their details", "what about their...", "how many do they..."
✅ Comparative questions building on previous: "which one is better", "compared to those"
✅ Short contextual questions: "how many?", "which ones?", "where?" (when previous context exists)
✅ Clarifying or drilling down: "for each", "break it down", "by category"

IS A NEW QUESTION if:
❌ Mentions completely different entities not in previous conversation
❌ Asks about different tables/concepts entirely (e.g., switching from "films" to "customers")
❌ Uses specific names/IDs not from previous results
❌ Complete sentences with full context that don't need history
❌ Starts with "Show me...", "Find...", "List...", "Get..." with NEW entities
❌ Question makes complete sense without any conversation history

**STEP 2: Handle based on type**

FOR FOLLOW-UP QUESTIONS:
1. Extract the entities/IDs from the MOST RECENT assistant response
2. If assistant listed items (films, actors, customers, etc.), extract those specific items
3. Build your query to filter/join using those specific entities
4. Confidence should be NORMAL (0.6-0.9) if you can identify the entities
5. Confidence should be LOW (0.2-0.4) ONLY if pronouns exist BUT no clear entities in history

FOR NEW QUESTIONS:
1. Treat as completely independent query
2. Don't try to reference conversation history
3. Use only the schema and current question
4. Confidence based purely on question clarity and schema availability

**STEP 3: Special Cases**

AMBIGUOUS CASES (could be either):
- If unsure, favor treating it as NEW question (safer)
- Only treat as follow-up if there are CLEAR pronouns or relative references
- Don't force follow-up context on independent questions

SINGLE-WORD RESPONSES ("yes", "no", "sure"):
- Check if assistant asked a YES/NO question previously
- If yes, return confidence = 0.2 and ask for clarification
- If no question was asked, treat as unclear input

EXAMPLES:

Previous: "Here are the top 5 films..."
Current: "show me their actors" → FOLLOW-UP (pronoun "their" refers to those 5 films)
Current: "which actors are in comedy films?" → NEW QUESTION (different context, no pronouns)

Previous: "Found 10 customers..."
Current: "how many orders does each have?" → FOLLOW-UP ("each" refers to those 10 customers)
Current: "how many orders are there?" → NEW QUESTION (asking about all orders, not specific to those customers)

Previous: "The film rental rate is $4.99"
Current: "what about replacement cost?" → FOLLOW-UP (continuing the same film)
Current: "show me all rental rates" → NEW QUESTION (asking for all films, not just that one)

Previous: "Action films: 50"
Current: "others?" → FOLLOW-UP (asking about other categories)
Current: "how many comedy films?" → NEW QUESTION (specific category, doesn't need context)

⚠️ CRITICAL: Don't over-interpret! If a question has full context and doesn't use pronouns, it's likely NEW.
""" + "="*50 + "\n"
    
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

🔍 CONTEXT AWARENESS & FOLLOW-UP ANALYSIS:

**STEP-BY-STEP APPROACH:**

1. **Read the conversation history above carefully**
2. **Identify if current question is FOLLOW-UP or NEW:**
   - Does it use pronouns (them/they/it/those/these/their)?
   - Does it reference previous results implicitly ("each", "others", "more")?
   - Would this question make sense WITHOUT the conversation history?
3. **If FOLLOW-UP:**
   - Extract entities/items from the most recent assistant response
   - Use those specific entities to build filtered queries
   - Maintain NORMAL confidence (0.6-0.9) if entities are clear
4. **If NEW QUESTION:**
   - Ignore conversation history for query building
   - Treat as standalone question
   - Base confidence only on question clarity + schema match
5. **If AMBIGUOUS:**
   - Default to treating as NEW question (safer approach)
   - Only use history if there are explicit pronouns/references

**Decision Rule:** When in doubt, assume it's a NEW question unless there are clear linguistic markers (pronouns, "each", "those", etc.)

TASK:
1. Analyze what the user is asking for
2. **CRITICAL - SECURITY CHECK**: If the question asks to modify/delete/update/insert data, IMMEDIATELY return confidence = 0.0
3. **CRITICAL - FOLLOW-UP vs NEW QUESTION DETECTION**:
   
   A) **Check for Follow-Up Indicators:**
      - Pronouns: "them", "they", "it", "those", "these", "their", "its"
      - Relative words: "each", "every", "all of them", "any of them", "others", "same", "rest"
      - Continuation phrases: "what about", "how about", "also show", "and their"
      - Context-dependent: "more", "less", "different", "similar", "compared to"
   
   B) **If Follow-Up Detected:**
      - Parse the MOST RECENT assistant response to extract entities
      - Look for: film names, actor names, customer IDs, category names, etc.
      - Build query that FILTERS by those specific entities
      - Example: If assistant said "Here are 5 films: A, B, C, D, E" and user asks "show their actors"
        → Generate query: SELECT actors WHERE film_name IN ('A','B','C','D','E')
      - Maintain good confidence (0.7-0.9) if you successfully extracted entities
      - Use low confidence (0.3-0.4) ONLY if pronouns exist but NO entities found in history
   
   C) **If New Question (No Follow-Up Indicators):**
      - Treat as completely independent query
      - Don't reference or filter by conversation history
      - Build query based solely on current question + schema
      - This is the DEFAULT - when in doubt, assume NEW question
   
   D) **Special Ambiguous Cases:**
      - Short questions like "how many?" → Check if previous response had countable items
        * If yes and context clear → Follow-up with high confidence
        * If unclear → Ask for clarification
      - Questions with entity names → If same entities as before, could be follow-up, but if different, it's NEW
      - "Show me X" → Usually NEW unless X uses pronouns ("show me their X")

4. Determine which tables and columns are needed based on the schema provided
5. Identify relevant entities by matching user's terms with table/column names and sample data
6. Generate a valid SELECT-ONLY SQL query to answer the question
7. **IMPORTANT - AVOID SELECT ***: Always specify column names explicitly. Avoid SELECT * as it may return binary data (images, BLOBs) that cannot be displayed properly. Select only the specific columns needed to answer the question.
8. Include JOINs when data spans multiple related tables
9. Use aggregation functions (COUNT, SUM, AVG, MAX, MIN) when appropriate
10. Include WHERE, GROUP BY, ORDER BY, and LIMIT clauses as needed

**CONFIDENCE GUIDELINES:**
- High (0.8-0.95): Clear question, schema matches, follow-up context resolved
- Medium (0.5-0.75): Understandable but slightly ambiguous  
- Low (0.3-0.45): Vague follow-up with unclear referents OR unclear question
- Very Low (0.0-0.2): Cannot determine intent, missing data, or modification request

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

📋 SMART FOLLOW-UP QUERY PATTERNS:

**Pattern 1: Asking about related entities**
Previous: "Here are 5 action films: A, B, C, D, E"
Follow-up: "show me their actors" / "who stars in them?"
→ Extract film names → SELECT actors JOIN films WHERE film.name IN ('A','B','C','D','E')

**Pattern 2: Aggregation on previous results**
Previous: "Found 10 customers from New York"  
Follow-up: "how many orders does each have?"
→ Extract customer IDs/names → SELECT customer, COUNT(orders) WHERE customer IN (...) GROUP BY customer

**Pattern 3: Additional details**
Previous: "Film X has rental rate $4.99"
Follow-up: "what about replacement cost?" / "show other details"
→ Continue with same film → SELECT replacement_cost WHERE film = X

**Pattern 4: Comparative follow-ups**
Previous: "Action films: 50"
Follow-up: "what about comedy?" / "others?"
→ New query on different category (NOT filtered by previous) → SELECT COUNT WHERE category = 'Comedy'

**Pattern 5: Drilling down**
Previous: "Total sales: $10,000"
Follow-up: "break it down by category" / "for each month"
→ Add GROUP BY to similar query → SELECT category, SUM(sales) GROUP BY category

⚠️ **Key Distinction:**
- "Show THEIR details" = Follow-up (filter by previous entities)
- "Show ALL details" = New question (don't filter)
- "How many action films?" = New (specific category mentioned)
- "How many of them?" = Follow-up (refers to previous results)

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
