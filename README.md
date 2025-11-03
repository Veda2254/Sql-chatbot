# 🤖 Universal SQL Database Chatbot

This is an intelligent, self-configuring chatbot built with Streamlit, LangChain, and the Groq API. It can connect to **any** MySQL database, automatically discover its schema, and answer natural language questions by generating and executing SQL queries on the fly.

This project is designed to be "zero-hardcoding," meaning it doesn't rely on pre-written templates and can adapt to your specific database structure.

---

## Key Features

-   **Automatic Schema Discovery**: Intelligently inspects the connected database to learn all tables, columns, data types, and relationships (foreign keys).
-   **Intelligent SQL Generation**: Uses a powerful LLM (via Groq) to convert natural language questions (e.g., "how many users signed up last week?") into complex SQL queries.
-   **Conversation Context**: Remembers the last few messages to understand follow-up questions and pronouns (e.g., "what are *their* names?").
-   **Natural Language Responses**: Converts the raw SQL query results back into a friendly, easy-to-understand answer.
-   **Dynamic Connection**: Connect to and switch between different MySQL databases directly from the Streamlit sidebar.
-   **Fallback Mechanism**: Includes a LangChain SQL Agent as a fallback for queries the primary LLM struggles with.

---

## How It Works

1.  **Connect**: You provide your MySQL database credentials (host, user, password, database name) in the sidebar.
2.  **Inspect**: The app connects and runs an automatic schema discovery to understand your database layout.
3.  **Ask**: You ask a question in plain English.
4.  **Generate**: The app builds a detailed prompt, including your schema and conversation history, and sends it to the Groq LLM to generate a precise SQL query.
5.  **Execute**: The generated SQL query is run against your database.
6.  **Answer**: The raw results are sent back to the LLM, which formats them into a natural language response.

---

## 🚀 Getting Started

Follow these steps to run the project locally.

### 1. Clone the Repository

```bash
git clone https://github.com/Veda2254/Sql-chatbot.git
cd sql-chatbot
```

### 2. Create and Activate a Virtual Environment

It's highly recommended to use a virtual environment to manage dependencies.

```bash
# For macOS/Linux
python3 -m venv venv
source venv/bin/activate

# For Windows
python -m venv venv
.\venv\Scripts\activate
```

### 3. Install Requirements

Install all the necessary Python libraries from the `requirements.txt` file.

```bash
pip install -r requirements.txt
```

### 4. Create Your Environment File

The app loads your Groq API key from a `.env` file.

1.  Create a file named `.env` in the root of the project directory.
2.  Add your Groq API key to this file:

    ```
    GROQ_API_KEY="your-groq-api-key-here"
    ```

### 5. Run the Application

Launch the Streamlit app from your terminal.

```bash
streamlit run main.py
```

Your web browser should automatically open to the application (usually at `http://localhost:8501`). You can then use the sidebar to connect to your MySQL database and start asking questions!