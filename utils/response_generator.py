"""
Natural language response generation from SQL results
"""
import re
import ast
from decimal import Decimal


def clean_sql_results(sql_result: str) -> str:
    """
    Preprocesses raw SQL results to remove Python formatting artifacts
    Converts Decimal objects, tuples, and other Python structures to clean text
    Filters out binary data (images, blobs)
    """
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
                        # Skip binary data (bytes objects)
                        if isinstance(value, bytes):
                            cleaned_items.append("[Binary Data - Image/BLOB]")
                            continue
                        # Check for encoded binary strings
                        if isinstance(value, str) and (value.startswith('b\\x') or '\\x' in value[:20]):
                            cleaned_items.append("[Binary Data - Image/BLOB]")
                            continue
                            
                        if isinstance(value, (int, float)) or (hasattr(value, '__class__') and 'Decimal' in str(type(value))):
                            # Convert to float for cleaner display
                            cleaned_items.append(str(float(value)))
                        elif isinstance(value, str):
                            # Clean up formatting but preserve emails and URLs
                            cleaned_value = value.strip()
                            # Don't apply title case to emails, URLs, or already mixed-case strings
                            if '@' not in cleaned_value and 'http' not in cleaned_value.lower() and cleaned_value.isupper():
                                cleaned_value = cleaned_value.title()
                            cleaned_items.append(cleaned_value)
                        elif value is None:
                            cleaned_items.append("NULL")
                        else:
                            cleaned_items.append(str(value))
                    cleaned_rows.append(" | ".join(cleaned_items))
        
        # Return cleaned result as pipe-separated values with clear formatting
        cleaned_output = "\n".join(cleaned_rows)
        
        # Additional safety: remove any remaining Python artifacts
        cleaned_output = re.sub(r"Decimal\(['\"]([^'\"]+)['\"]\)", r'\1', cleaned_output)
        cleaned_output = cleaned_output.replace("[(", "").replace(")]", "")
        
        return cleaned_output
    
    except Exception as e:
        # If parsing fails, do aggressive regex-based cleaning
        print(f"Clean SQL Results Exception: {e}")
        
        # Check if this contains binary data
        if 'b\\x' in sql_result or '\\x89PNG' in sql_result:
            # Extract non-binary parts only
            parts = sql_result.split("b'")[0] if "b'" in sql_result else sql_result
            parts = parts.split("b\\x")[0] if "b\\x" in parts else parts
            sql_result = parts + " | [Binary Data - Image/BLOB removed]"
        
        # Remove Decimal() wrappers
        cleaned = re.sub(r"Decimal\(['\"]([^'\"]+)['\"]\)", r'\1', sql_result)
        
        # First, try to identify individual tuples (rows)
        # Pattern: (...), (...), (...)
        tuple_pattern = r'\(([^)]+)\)'
        tuples = re.findall(tuple_pattern, cleaned)
        
        if tuples and len(tuples) > 1:
            # Multiple rows found - process each tuple as a separate row
            cleaned_rows = []
            for tuple_content in tuples:
                # Remove quotes and clean up each field
                row_cleaned = re.sub(r"'([^']+)'", r'\1', tuple_content)
                # Convert to title case for uppercase words (but not emails/URLs)
                def title_case_match(match):
                    word = match.group(0)
                    if '@' in word or 'http' in word.lower():
                        return word
                    return word.title()
                row_cleaned = re.sub(r'\b[A-Z]{2,}\b', title_case_match, row_cleaned)
                # Replace commas with pipes for field separation
                row_cleaned = re.sub(r',\s*', ' | ', row_cleaned)
                cleaned_rows.append(row_cleaned)
            
            # Join rows with newlines
            cleaned = "\n".join(cleaned_rows)
        else:
            # Single row or unstructured data - use old approach
            # Remove list/tuple brackets and parentheses
            cleaned = cleaned.replace("[(", "").replace(")]", "")
            cleaned = re.sub(r"[\[\]\(\)]", "", cleaned)
            
            # Remove extra quotes around strings
            cleaned = re.sub(r"'([^']+)'", r'\1', cleaned)
            
            # Convert to title case for uppercase words
            def title_case_match(match):
                return match.group(0).title()
            
            cleaned = re.sub(r'\b[A-Z]{2,}\b', title_case_match, cleaned)
            
            # Clean up commas and spacing
            cleaned = re.sub(r',\s*', ' | ', cleaned)
        
        # Remove any remaining hex escape sequences
        cleaned = re.sub(r'\\x[0-9a-fA-F]{2}', '', cleaned)
        
        return cleaned


def generate_natural_language_response(user_query: str, sql_result: str, llm, custom_directive: str = None) -> str:
    """
    Converts raw SQL results into natural, conversational language
    """
    
    # Build custom directive section if provided
    directive_section = ""
    if custom_directive:
        directive_section = f"""
CUSTOM CHATBOT DIRECTIVE:
{custom_directive}

CRITICAL: Your response MUST align with the directive above. Adopt the specified role, tone, and domain expertise when crafting your answer.
{'='*50}

"""
    
    # Additional aggressive cleaning to ensure no raw format gets through
    sql_result_display = sql_result
    
    # Remove any remaining Python artifacts that might have survived
    sql_result_display = re.sub(r"Decimal\(['\"]([^'\"]+)['\"]\)", r'\1', sql_result_display)
    sql_result_display = sql_result_display.replace("[(", "").replace(")]", "")
    sql_result_display = re.sub(r"[\[\]]", "", sql_result_display)
    
    # Try to pre-parse the pipe-separated data to help the LLM
    parsed_data = []
    for line in sql_result_display.strip().split('\n'):
        if '|' in line:
            # Multiple fields separated by pipes
            fields = [f.strip() for f in line.split('|')]
            parsed_data.append(fields)
        elif line.strip():
            # Single field result (no pipes)
            parsed_data.append([line.strip()])
    
    # Build a simpler prompt
    data_context = ""
    show_all = any(word in user_query.lower() for word in ['list', 'all', 'show all', 'give all', 'what are', 'list all', 'give list'])
    
    # Debug: print if show_all is detected
    if show_all:
        print(f"DEBUG: LIST REQUEST DETECTED - Will show all {len(parsed_data)} items")
    
    if parsed_data:
        data_context = "The database returned this data:\n"
        
        # Determine how many rows to show
        max_rows_to_show = len(parsed_data) if show_all or len(parsed_data) <= 20 else 5
        
        for i, row in enumerate(parsed_data[:max_rows_to_show]):
            if len(row) == 1:
                # Single value
                data_context += f"  {i+1}. {row[0]}\n"
            else:
                # Multiple fields
                data_context += f"  Row {i+1}: {row}\n"
        
        if len(parsed_data) > max_rows_to_show:
            data_context += f"  (... and {len(parsed_data) - max_rows_to_show} more rows - summarize these)\n"
    
    # Determine response instruction based on query type
    list_instruction = ""
    if show_all and len(parsed_data) <= 50:
        list_instruction = f"\n\n🚨 CRITICAL INSTRUCTION 🚨\nThe user asked for a COMPLETE LIST of ALL items.\nYou MUST include EVERY SINGLE item from the {len(parsed_data)} items shown above.\nDO NOT say 'and others' or 'totaling X items' - LIST THEM ALL.\n\nFormat: 'She has worked in these genres: Documentary, Animation, New, Games, Sci-Fi, Classics, Horror, Sports, Family, Children, Foreign, Comedy, and Music.'"
    
    prompt = f"""{directive_section}You are a friendly database assistant. Your job is to explain query results in natural, conversational language.

🚨 ABSOLUTE REQUIREMENT 🚨
You MUST ALWAYS write in natural language sentences. NEVER show raw data formats.
Pipe symbols (|), brackets, or raw field values are STRICTLY FORBIDDEN in your response.

Question: "{user_query}"

{data_context}{list_instruction}

MANDATORY PARSING INSTRUCTIONS:
1. Read the data fields above
2. Understand what each field represents based on the question
3. Write a natural, conversational answer
4. Use proper sentences with context and meaning
5. NEVER copy the pipe-separated format

CORRECT RESPONSE PATTERNS:

For single row results:
Question: "Which store manager has better performance?"
Data: [['2', '2', '8121', '33726.77']]
✅ "Store #2, managed by staff member #2, has the better performance with 8,121 rentals generating total revenue of $33,726.77."

Question: "What's the customer's email?"
Data: [['mary.smith@example.com']]
✅ "The customer's email is mary.smith@example.com."

Question: "Who is the most valued customer?"
Data: [['Karl', 'Seal', '221.55']]
✅ "Karl Seal is our most valued customer, having spent a total of $221.55."

For multiple row results:
Question: "Which films have the best ratio?"
Data: [['Control Anthem', '4.99', '9.99', '0.50'], ['Daisy Menagerie', '4.99', '9.99', '0.50']]
✅ "Here are the films with the best rental-to-cost ratios:
• Control Anthem has a rental rate of $4.99 and replacement cost of $9.99 (ratio: 0.50)
• Daisy Menagerie has a rental rate of $4.99 and replacement cost of $9.99 (ratio: 0.50)"

FORBIDDEN RESPONSES (DO NOT DO THIS):
❌ "Here are the results: 2 | 2 | 8121 | 33726.77"
❌ "2 | 2 | 8121 | 33726.77"
❌ "Control Anthem | 4.99 | 9.99 | 0.50"
❌ Any response containing the pipe symbol (|)

Your response MUST be in natural language:"""
    
    try:
        response = llm.invoke(prompt)
        return response.content if hasattr(response, 'content') else str(response)
    except Exception as e:
        return f"Here are the results:\n\n{sql_result}"
