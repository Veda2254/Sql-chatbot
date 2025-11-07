// Universal Database Chatbot - Frontend JavaScript
// Handles all API interactions and UI updates

// State management
let isConnected = false;

// DOM Elements
const connectionForm = document.getElementById('connectionForm');
const connectionStatus = document.getElementById('connectionStatus');
const connectedInfo = document.getElementById('connectedInfo');
const changeDbBtn = document.getElementById('changeDbBtn');
const infoBanner = document.getElementById('infoBanner');
const chatMessages = document.getElementById('chatMessages');
const chatInput = document.getElementById('chatInput');
const sendBtn = document.getElementById('sendBtn');
const clearChatBtn = document.getElementById('clearChatBtn');
const loadingOverlay = document.getElementById('loadingOverlay');

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
    checkConnectionStatus();
    setupEventListeners();
});

// Event Listeners
function setupEventListeners() {
    connectionForm.addEventListener('submit', handleConnect);
    changeDbBtn.addEventListener('click', handleDisconnect);
    sendBtn.addEventListener('click', handleSendMessage);
    chatInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            handleSendMessage();
        }
    });
    clearChatBtn.addEventListener('click', handleClearChat);
}

// API Functions
async function checkConnectionStatus() {
    try {
        const response = await fetch('/api/status');
        const data = await response.json();
        
        if (data.success && data.connected) {
            isConnected = true;
            updateUIForConnected(data);
            loadChatHistory();
        }
    } catch (error) {
        console.error('Error checking status:', error);
    }
}

async function handleConnect(e) {
    e.preventDefault();
    
    const formData = {
        host: document.getElementById('host').value,
        port: parseInt(document.getElementById('port').value),
        user: document.getElementById('user').value,
        password: document.getElementById('password').value,
        database: document.getElementById('database').value,
        directive: document.getElementById('directive').value.trim()
    };
    
    showLoading(true);
    
    try {
        const response = await fetch('/api/connect', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(formData)
        });
        
        const data = await response.json();
        
        if (data.success) {
            isConnected = true;
            updateUIForConnected(data);
            showToast('Connected successfully!', 'success');
            loadChatHistory();
        } else {
            showToast(data.message, 'error');
        }
    } catch (error) {
        showToast('Connection failed: ' + error.message, 'error');
    } finally {
        showLoading(false);
    }
}

async function handleDisconnect() {
    if (!confirm('Are you sure you want to disconnect? This will clear your chat history.')) {
        return;
    }
    
    showLoading(true);
    
    try {
        const response = await fetch('/api/disconnect', {
            method: 'POST'
        });
        
        const data = await response.json();
        
        if (data.success) {
            isConnected = false;
            updateUIForDisconnected();
            clearMessages();
            showToast('Disconnected successfully', 'info');
        }
    } catch (error) {
        showToast('Disconnect failed: ' + error.message, 'error');
    } finally {
        showLoading(false);
    }
}

async function handleSendMessage() {
    const message = chatInput.value.trim();
    
    if (!message || !isConnected) return;
    
    // Add user message immediately
    addMessage(message, 'user');
    chatInput.value = '';
    
    // Disable input while processing
    chatInput.disabled = true;
    sendBtn.disabled = true;
    
    try {
        const response = await fetch('/api/chat', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ message })
        });
        
        const data = await response.json();
        
        if (data.success) {
            addMessage(data.response, 'assistant');
        } else {
            showToast(data.message, 'error');
        }
    } catch (error) {
        showToast('Error sending message: ' + error.message, 'error');
        addMessage('Sorry, I encountered an error processing your message. Please try again.', 'assistant');
    } finally {
        chatInput.disabled = false;
        sendBtn.disabled = false;
        chatInput.focus();
        
        // Show clear chat button
        clearChatBtn.style.display = 'block';
    }
}

async function loadChatHistory() {
    try {
        const response = await fetch('/api/chat/history');
        const data = await response.json();
        
        if (data.success && data.messages.length > 0) {
            clearMessages();
            data.messages.forEach(msg => {
                addMessage(msg.content, msg.role);
            });
            clearChatBtn.style.display = 'block';
        }
    } catch (error) {
        console.error('Error loading chat history:', error);
    }
}

async function handleClearChat() {
    if (!confirm('Are you sure you want to clear the chat history?')) {
        return;
    }
    
    try {
        const response = await fetch('/api/chat/clear', {
            method: 'DELETE'
        });
        
        const data = await response.json();
        
        if (data.success) {
            clearMessages();
            clearChatBtn.style.display = 'none';
            showToast('Chat history cleared', 'info');
        }
    } catch (error) {
        showToast('Error clearing chat: ' + error.message, 'error');
    }
}

// UI Update Functions
function updateUIForConnected(data) {
    // Update status
    connectionStatus.className = 'status-box status-connected';
    connectionStatus.innerHTML = `
        <span class="status-icon">✅</span>
        <span class="status-text">Connected to: ${data.database}</span>
    `;
    
    // Show connected info
    document.getElementById('connectedDatabase').textContent = data.database || '-';
    document.getElementById('connectedHost').textContent = data.host || '-';
    document.getElementById('connectedUser').textContent = data.user || '-';
    
    // Show/hide directive
    if (data.has_directive && data.directive) {
        document.getElementById('currentDirectiveBox').style.display = 'block';
        document.getElementById('currentDirectiveText').textContent = data.directive;
    } else {
        document.getElementById('currentDirectiveBox').style.display = 'none';
    }
    
    connectedInfo.style.display = 'block';
    connectionForm.style.display = 'none';
    
    // Update main area
    infoBanner.classList.add('hidden');
    chatInput.disabled = false;
    sendBtn.disabled = false;
}

function updateUIForDisconnected() {
    // Update status
    connectionStatus.className = 'status-box status-disconnected';
    connectionStatus.innerHTML = `
        <span class="status-icon">⚠️</span>
        <span class="status-text">No database connected</span>
    `;
    
    // Hide connected info, show form
    connectedInfo.style.display = 'none';
    connectionForm.style.display = 'block';
    
    // Update main area
    infoBanner.classList.remove('hidden');
    chatInput.disabled = true;
    sendBtn.disabled = true;
    clearChatBtn.style.display = 'none';
}

function addMessage(content, role) {
    const messageDiv = document.createElement('div');
    messageDiv.className = `message message-${role}`;
    
    const avatar = document.createElement('div');
    avatar.className = 'message-avatar';
    avatar.textContent = role === 'user' ? '👤' : '🤖';
    
    const contentDiv = document.createElement('div');
    contentDiv.className = 'message-content';
    
    // Use marked.js to render markdown
    if (typeof marked !== 'undefined') {
        contentDiv.innerHTML = marked.parse(content);
    } else {
        contentDiv.textContent = content;
    }
    
    messageDiv.appendChild(avatar);
    messageDiv.appendChild(contentDiv);
    chatMessages.appendChild(messageDiv);
    
    // Auto scroll to bottom
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

function clearMessages() {
    chatMessages.innerHTML = '';
}

function showLoading(show) {
    loadingOverlay.style.display = show ? 'flex' : 'none';
}

function showToast(message, type = 'info') {
    const toastContainer = document.getElementById('toastContainer');
    
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.textContent = message;
    
    toastContainer.appendChild(toast);
    
    // Auto remove after 4 seconds
    setTimeout(() => {
        toast.style.animation = 'slideOut 0.3s ease-out';
        setTimeout(() => {
            toastContainer.removeChild(toast);
        }, 300);
    }, 4000);
}

// Add slideOut animation to CSS dynamically
const style = document.createElement('style');
style.textContent = `
    @keyframes slideOut {
        from {
            transform: translateX(0);
            opacity: 1;
        }
        to {
            transform: translateX(400px);
            opacity: 0;
        }
    }
`;
document.head.appendChild(style);
