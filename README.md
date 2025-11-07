#  Universal SQL Database Chatbot

This is an intelligent, self-configuring chatbot built with **Flask API**, **HTML/CSS/JavaScript frontend**, **LangChain**, and the **Groq API**. It can connect to **any** MySQL database, automatically discover its schema, and answer natural language questions by generating and executing SQL queries on the fly.

This project is designed to be "zero-hardcoding," meaning it doesn't rely on pre-written templates and can adapt to your specific database structure.

---

## Key Features

-   **Flask REST API**: Clean API architecture with dedicated endpoints for database operations, chat, and directives
-   **Modern Web Interface**: Responsive HTML/CSS/JS frontend with Streamlit-inspired design
-   **Automatic Schema Discovery**: Intelligently inspects the connected database to learn all tables, columns, data types, and relationships (foreign keys)
-   **Intelligent SQL Generation**: Uses a powerful LLM (via Groq) to convert natural language questions into complex SQL queries
-   **Conversation Context**: Remembers conversation history to understand follow-up questions and pronouns
-   **Natural Language Responses**: Converts raw SQL query results back into friendly, easy-to-understand answers
-   **Custom Directives**: Define chatbot behavior, tone, and domain expertise through custom directives
-   **Dynamic Connection**: Connect to and switch between different MySQL databases through the web interface
-   **Read-Only Security**: Built-in SQL injection prevention and read-only query enforcement
-   **Fallback Mechanism**: Includes a LangChain SQL Agent as a fallback for complex queries

---

## Architecture

```
Frontend (HTML/CSS/JS) ↔ Flask API ↔ Core Logic (utils/) ↔ Database/LLM
```

### Project Structure
```
sql-chatbot/
├── app.py                      # Flask application entry point
├── config.py                   # Configuration settings
├── requirements.txt            # Python dependencies
├── .env                        # Environment variables
├── api/                        # REST API endpoints
│   ├── connection_routes.py   # Database connection API
│   ├── directive_routes.py    # Directive management API
│   ├── chat_routes.py         # Chat conversation API
│   └── schema_routes.py       # Schema information API
├── utils/                      # Core logic modules
│   ├── security.py            # SQL injection prevention
│   ├── db_manager.py          # Database connection
│   ├── schema_inspector.py    # Schema discovery
│   ├── query_generator.py     # SQL generation
│   ├── response_generator.py  # Natural language responses
│   └── llm_client.py          # LLM client management
├── templates/                  # HTML templates
│   └── index.html             # Main chat interface
└── static/                     # Static assets
    ├── css/style.css          # Styling
    └── js/main.js             # Frontend JavaScript
```

---

## API Endpoints

### Database Connection
- `POST /api/connect` - Connect to database
- `POST /api/disconnect` - Disconnect from database
- `GET /api/status` - Get connection status

### Directive Management
- `POST /api/directive` - Set/update chatbot directive
- `GET /api/directive` - Get current directive
- `DELETE /api/directive` - Clear directive

### Chat Operations
- `POST /api/chat` - Send chat message
- `GET /api/chat/history` - Get chat history
- `DELETE /api/chat/clear` - Clear chat history

### Database Info
- `GET /api/schema` - Get database schema

---

## Getting Started

Follow these steps to run the project locally.

### 1. Clone the Repository

```bash
git clone https://github.com/Veda2254/Sql-chatbot.git
cd sql-chatbot
```

### 2. Create and Activate a Virtual Environment

It's highly recommended to use a virtual environment to manage dependencies.

```bash
# For Windows (PowerShell)
python -m venv venv
.\venv\Scripts\activate

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

# For Windows
pip install -r requirements.txt

# For macOS/Linux
pip3 install -r requirements.txt
```

### 4. Set Up Environment Variables

Create a `.env` file in the root directory:

```bash
# Windows PowerShell
New-Item .env -ItemType File

# macOS/Linux
touch .env
```

Add your Groq API key to the `.env` file:

```
GROQ_API_KEY=your_groq_api_key_here
SECRET_KEY=your_secret_key_for_flask_sessions
```

Get your Groq API key from: https://console.groq.com/keys

### 5. Run the Application

```bash
# Windows PowerShell
python app.py

# macOS/Linux
python3 app.py
```

### 6. Access the Application

Open your web browser and navigate to:
```
http://localhost:5000
```

---

## 💬 Using the Chatbot

1. **Connect to Database**: Use the sidebar form to enter your MySQL database credentials
2. **Set Directive (Optional)**: Define custom behavior for the chatbot (e.g., "Behave as a medical assistant...")
3. **Ask Questions**: Type natural language questions about your data in the chat input
4. **View Results**: Get intelligent, conversational responses based on your database

### Example Questions:
- "How many users are in the database?"
- "Show me the top 5 products by revenue"
- "What are the names of customers who placed orders last month?"
- "Find all active subscriptions"

---

## 🔒 Security Features

- **Read-Only Mode**: Only SELECT queries are allowed - no INSERT, UPDATE, DELETE, or DROP operations
- **SQL Injection Prevention**: Input sanitization and query validation
- **Session Management**: Secure server-side session storage
- **Query Validation**: All generated queries are validated before execution

---

## 🛠️ Technologies Used

- **Backend**: Flask, Python 3.8+
- **Frontend**: HTML5, CSS3, Vanilla JavaScript
- **AI/ML**: LangChain, Groq API (Llama 3.3 70B)
- **Database**: MySQL, SQLAlchemy
- **Session Management**: Flask-Session
- **API**: RESTful architecture

---

## 📝 Development

### Running in Development Mode

```bash
# Set environment variable
export FLASK_ENV=development  # macOS/Linux
$env:FLASK_ENV="development"  # Windows PowerShell

# Run application
python app.py
```

### Project Components

- **Core Logic**: All original Streamlit logic preserved in `utils/` modules
- **API Layer**: RESTful endpoints in `api/` blueprints
- **Frontend**: Modern, responsive web interface
- **Security**: Built-in validation and read-only enforcement

---

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

---

## 📄 License

This project is open source and available under the MIT License.

---

## Acknowledgments

- Groq for providing fast LLM inference
- LangChain for the SQL agent framework
- The open-source community

---

## 📧 Contact

For questions or feedback, please open an issue on GitHub.

**Repository**: https://github.com/Veda2254/Sql-chatbot
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