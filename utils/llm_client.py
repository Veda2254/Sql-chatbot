"""
LLM client initialization and management
"""
import os
from langchain_groq import ChatGroq
from langchain_community.agent_toolkits.sql.base import create_sql_agent
from langchain_community.agent_toolkits.sql.toolkit import SQLDatabaseToolkit
import langchain
from langchain_community.cache import InMemoryCache

# Initialize cache
langchain.llm_cache = InMemoryCache()


def get_llm_client(temperature: float = 0.3):
    """Get configured Groq LLM client"""
    groq_api_key = os.getenv("GROQ_API_KEY")
    if not groq_api_key:
        raise ValueError("GROQ_API_KEY not found in environment variables")
    
    return ChatGroq(
        model_name="llama-3.3-70b-versatile",
        groq_api_key=groq_api_key,
        temperature=temperature
    )


def create_sql_agent_fallback(db, llm):
    """Create LangChain SQL Agent as fallback"""
    toolkit = SQLDatabaseToolkit(db=db, llm=llm)
    return create_sql_agent(
        llm=llm,
        toolkit=toolkit,
        verbose=True,
        handle_parsing_errors=True,
        max_iterations=10
    )
