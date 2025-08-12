import streamlit as st
import sqlite3
import bcrypt
import time
import random
import pandas as pd
import plotly.express as px
import re
import hashlib
import json
import math
import base64
from datetime import datetime
from streamlit.components.v1 import html
from streamlit_autorefresh import st_autorefresh
from streamlit.components.v1 import html

# Streamlit-specific configuration
st.set_page_config(
    layout="wide",
    page_title="MathFriend",
    page_icon="🧮",
    initial_sidebar_state="expanded"
)

# --- Database Setup and Connection Logic ---
DB_FILE = 'users.db'

def create_tables_if_not_exist():
    """
    Ensures all necessary tables and columns exist in the database.
    Now includes tables for profiles, online status, and typing indicators.
    """
    conn = None
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        
        # Create users table
        c.execute('''CREATE TABLE IF NOT EXISTS users
                     (username TEXT PRIMARY KEY, password TEXT)''')
                     
        # Create quiz_results table
        c.execute('''CREATE TABLE IF NOT EXISTS quiz_results
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      username TEXT,
                      topic TEXT,
                      score INTEGER,
                      timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
                      
        # Create chat_messages table
        c.execute('''CREATE TABLE IF NOT EXISTS chat_messages
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      username TEXT,
                      message TEXT,
                      media TEXT,
                      timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')

        # Create user profiles table
        c.execute('''CREATE TABLE IF NOT EXISTS user_profiles
                     (username TEXT PRIMARY KEY,
                      full_name TEXT,
                      school TEXT,
                      age INTEGER,
                      bio TEXT)''')
        
        # Create online status table
        c.execute('''CREATE TABLE IF NOT EXISTS user_status
                     (username TEXT PRIMARY KEY, 
                      is_online BOOLEAN,
                      last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        
        # Create typing indicators table
        c.execute('''CREATE TABLE IF NOT EXISTS typing_indicators
                     (username TEXT PRIMARY KEY,
                      is_typing BOOLEAN,
                      timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')

        # Check for the 'media' column and add it if it's missing
        c.execute("PRAGMA table_info(chat_messages)")
        columns = [column[1] for column in c.fetchall()]
        if 'media' not in columns:
            c.execute("ALTER TABLE chat_messages ADD COLUMN media TEXT")
        
        conn.commit()
    except sqlite3.Error as e:
        st.error(f"Database setup error: {e}")
    finally:
        if conn:
            conn.close()

# Call the setup function once when the script first runs
create_tables_if_not_exist()

# --- User Authentication Functions --- 
# (Keep all existing auth functions exactly the same)
def hash_password(password):
    """Hashes a password using bcrypt."""
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def check_password(hashed_password, user_password):
    """Checks a password against its hash."""
    return bcrypt.checkpw(user_password.encode('utf-8'), hashed_password.encode('utf-8'))

def login_user(username, password):
    """
    Authenticates a user. This function now creates and closes its
    own database connection, making it thread-safe.
    """
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT password FROM users WHERE username=?", (username,))
        result = c.fetchone()
        if result:
            hashed_password = result[0]
            return check_password(hashed_password, password)
        return False
    except sqlite3.Error as e:
        st.error(f"Login database error: {e}")
        return False
    finally:
        if conn:
            conn.close()

def signup_user(username, password):
    """
    Creates a new user account. This function is also now thread-safe.
    """
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        hashed_password = hash_password(password)
        c.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, hashed_password))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False # Username already exists
    except sqlite3.Error as e:
        st.error(f"Signup database error: {e}")
        return False
    finally:
        if conn:
            conn.close()

# --- Profile Management Functions ---
def get_user_profile(username):
    """Gets a user's profile info"""
    try:
        conn = sqlite3.connect(DB_FILE)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT * FROM user_profiles WHERE username=?", (username,))
        profile = c.fetchone()
        return dict(profile) if profile else None
    except sqlite3.Error as e:
        st.error(f"Get profile error: {e}")
        return None
    finally:
        if conn:
            conn.close()

def update_user_profile(username, full_name, school, age, bio):
    """Updates a user's profile"""
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute('''INSERT OR REPLACE INTO user_profiles 
                     (username, full_name, school, age, bio) 
                     VALUES (?, ?, ?, ?, ?)''', 
                     (username, full_name, school, age, bio))
        conn.commit()
        return True
    except sqlite3.Error as e:
        st.error(f"Profile update error: {e}")
        return False
    finally:
        if conn:
            conn.close()

def change_password(username, current_password, new_password):
    """Changes a user's password"""
    if not login_user(username, current_password):
        return False
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        hashed_password = hash_password(new_password)
        c.execute("UPDATE users SET password=? WHERE username=?", 
                 (hashed_password, username))
        conn.commit()
        return True
    except sqlite3.Error as e:
        st.error(f"Password change error: {e}")
        return False
    finally:
        if conn:
            conn.close()

# --- Online Status Functions ---
def update_user_status(username, is_online):
    """Updates a user's online status"""
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute('''INSERT OR REPLACE INTO user_status (username, is_online) 
                     VALUES (?, ?)''', (username, is_online))
        conn.commit()
    except sqlite3.Error as e:
        st.error(f"Status update error: {e}")
    finally:
        if conn:
            conn.close()

def get_online_users():
    """Returns list of users currently online"""
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        # Consider users online if they've been active in the last 2 minutes
        c.execute("""SELECT username FROM user_status 
                     WHERE is_online = 1 AND 
                     last_seen > datetime('now', '-2 minutes')""")
        return [row[0] for row in c.fetchall()]
    except sqlite3.Error as e:
        st.error(f"Get online users error: {e}")
        return []
    finally:
        if conn:
            conn.close()

def update_typing_status(username, is_typing):
    """Updates a user's typing indicator status"""
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute('''INSERT OR REPLACE INTO typing_indicators 
                     (username, is_typing) VALUES (?, ?)''', 
                     (username, is_typing))
        conn.commit()
    except sqlite3.Error as e:
        st.error(f"Typing status update error: {e}")
    finally:
        if conn:
            conn.close()

def get_typing_users():
    """Returns list of users currently typing"""
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        # Consider typing indicators active for 5 seconds
        c.execute("""SELECT username FROM typing_indicators 
                     WHERE is_typing = 1 AND 
                     timestamp > datetime('now', '-5 seconds')""")
        return [row[0] for row in c.fetchall()]
    except sqlite3.Error as e:
        st.error(f"Get typing users error: {e}")
        return []
    finally:
        if conn:
            conn.close()

# --- Quiz and Result Functions ---
# (Keep all existing quiz functions exactly the same)
def generate_question(topic, difficulty):
    """Generates a random math question based on the topic and difficulty."""
    if topic in ["sets and operations on sets", "surds", "binary operations", "relations and functions", "polynomial functions", "rational functions", "binomial theorem", "coordinate geometry", "probabilty", "vectors", "sequence and series"]:
        return "Quiz questions for this topic are coming soon!", None
    
    a, b = 0, 0
    if difficulty == "Easy":
        a = random.randint(1, 10)
        b = random.randint(1, 10)
    elif difficulty == "Medium":
        a = random.randint(10, 50)
        b = random.randint(1, 20)
    elif difficulty == "Hard":
        a = random.randint(50, 100)
        b = random.randint(10, 50)
    
    question, answer = None, None

    if topic == "Addition":
        question = f"What is {a} + {b}?"
        answer = a + b
    elif topic == "Subtraction":
        a, b = max(a, b), min(a, b)
        question = f"What is {a} - {b}?"
        answer = a - b
    elif topic == "Multiplication":
        if difficulty == "Hard":
            a = random.randint(10, 20)
            b = random.randint(10, 20)
        question = f"What is {a} x {b}?"
        answer = a * b
    elif topic == "Division":
        b = random.randint(2, 10)
        a = b * random.randint(1, 10)
        if difficulty == "Hard":
            b = random.randint(11, 20)
            a = b * random.randint(1, 20)
        question = f"What is {a} / {b}?"
        answer = a / b
    elif topic == "Exponents":
        base = random.randint(1, 5)
        power = random.randint(2, 4)
        if difficulty == "Hard":
            base = random.randint(5, 10)
            power = random.randint(2, 3)
        question = f"What is {base}^{power}?"
        answer = base ** power
    else:
        question = "Please select a topic to start."
        answer = None
    
    return question, answer

def save_quiz_result(username, topic, score):
    """Saves a user's quiz result to the database."""
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("INSERT INTO quiz_results (username, topic, score) VALUES (?, ?, ?)",
                  (username, topic, score))
        conn.commit()
    except sqlite3.Error as e:
        st.error(f"Save quiz result database error: {e}")
    finally:
        if conn:
            conn.close()

def get_top_scores(topic):
    """Fetches the top 10 scores for a given topic."""
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT username, score FROM quiz_results WHERE topic=? ORDER BY score DESC, timestamp ASC LIMIT 10", (topic,))
        results = c.fetchall()
        return results
    except sqlite3.Error as e:
        st.error(f"Get top scores database error: {e}")
        return []
    finally:
        if conn:
            conn.close()

def get_user_quiz_history(username):
    """Fetches a user's quiz history."""
    try:
        conn = sqlite3.connect(DB_FILE)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT topic, score, timestamp FROM quiz_results WHERE username=? ORDER BY timestamp DESC", (username,))
        results = c.fetchall()
        return results
    except sqlite3.Error as e:
        st.error(f"Get quiz history database error: {e}")
        return []
    finally:
        if conn:
            conn.close()

def get_user_stats(username):
    """Fetches key statistics for a user's dashboard."""
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        # Get total quizzes taken
        c.execute("SELECT COUNT(*) FROM quiz_results WHERE username=?", (username,))
        total_quizzes = c.fetchone()[0]

        # Get last score
        c.execute("SELECT score FROM quiz_results WHERE username=? ORDER BY timestamp DESC LIMIT 1", (username,))
        last_score = c.fetchone()
        last_score = last_score[0] if last_score else "N/A"

        # Get top score
        c.execute("SELECT MAX(score) FROM quiz_results WHERE username=?", (username,))
        top_score = c.fetchone()
        top_score = top_score[0] if top_score and top_score[0] is not None else "N/A"
        
        return total_quizzes, last_score, top_score
    except sqlite3.Error as e:
        st.error(f"Get user stats database error: {e}")
        return 0, "N/A", "N/A"
    finally:
        if conn:
            conn.close()

# --- Chat Functions ---
def add_chat_message(username, message, media=None):
    """Adds a new chat message with optional media to the database."""
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("INSERT INTO chat_messages (username, message, media) VALUES (?, ?, ?)", (username, message, media))
        conn.commit()
    except sqlite3.Error as e:
        st.error(f"Add chat message database error: {e}")
    finally:
        if conn:
            conn.close()

def get_chat_messages():
    """Fetches all chat messages from the database."""
    try:
        conn = sqlite3.connect(DB_FILE)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT id, username, message, media, timestamp FROM chat_messages ORDER BY timestamp ASC")
        results = c.fetchall()
        return results
    except sqlite3.Error as e:
        st.error(f"Get chat messages database error: {e}")
        return []
    finally:
        if conn:
            conn.close()

def get_all_usernames():
    """Fetches all registered usernames."""
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT username FROM users")
        results = [row[0] for row in c.fetchall()]
        return results
    except sqlite3.Error as e:
        st.error(f"Get all usernames database error: {e}")
        return []
    finally:
        if conn:
            conn.close()

def report_message(message_id, reporter_username):
    """Logs a message report (to console for this example)."""
    st.warning(f"Message ID {message_id} reported by {reporter_username}.")
    pass

def format_message(message, mentioned_usernames, current_user):
    """Replaces common emoji shortcuts with actual emojis and formats message."""
    if not message:
        return ""
    emoji_map = {
        ":smile:": "😊", ":laughing:": "😂", ":thumbsup:": "👍", ":thumbsdown:": "👎",
        ":heart:": "❤️", ":star:": "⭐", ":100:": "💯", ":fire:": "🔥",
        ":thinking:": "🤔", ":nerd:": "🤓"
    }
    for shortcut, emoji in emoji_map.items():
        message = message.replace(shortcut, emoji)

    for user in mentioned_usernames:
        if user == current_user:
            message = re.sub(r'(?i)(@' + re.escape(user) + r')', r'<span class="mention-highlight">\1</span>', message)
    
    return message

# --- MathBot Integration ---
# (Keep existing MathBot functions exactly the same)
def get_mathbot_response(message):
    """
    Solves a basic math expression or provides a definition from a chat message.
    """
    if not message.startswith("@MathBot"):
        return None

    query = message.replace("@MathBot", "").strip()
    query_lower = query.lower()

    definitions = {
        "sets": "A set is a collection of distinct objects, considered as an object in its own right.",
        "surds": "A surd is an irrational number that can be expressed with a root symbol, like $\sqrt{2}$.",
        "binary operation": "A binary operation is a calculation that combines two elements to produce a new one.",
        "relations and functions": "A relation is a set of ordered pairs, while a function is a special type of relation where each input has exactly one output.",
        "polynomial functions": "A polynomial is an expression consisting of variables and coefficients, involving only the operations of addition, subtraction, multiplication, and non-negative integer exponents.",
        "rational functions": "A rational function is any function that can be expressed as a ratio of two polynomials, such as $f(x) = \frac{P(x)}{Q(x)}$.",
        "binomial theorem": "The binomial theorem describes the algebraic expansion of powers of a binomial $(x+y)^n$.",
        "coordinate geometry": "Coordinate geometry is the study of geometry using a coordinate system, like plotting points on a graph.",
        "probability": "Probability is a measure of the likelihood that an event will occur.",
        "vectors": "A vector is a quantity having magnitude and direction, often represented by a directed line segment.",
        "sequence and series": "A sequence is an ordered list of numbers, and a series is the sum of the terms in a sequence."
    }
    if query_lower.startswith("define"):
        term = query_lower.split("define", 1)[1].strip()
        if term in definitions:
            return f"**Definition:** {definitions[term]}"
        else:
            return f"Sorry, I don't have a definition for '{term}' yet."

    if query_lower.startswith("plot"):
        return "Sorry, plotting functionality is still in development, but it's a great idea!"

    if query_lower.startswith("solve"):
        return "Sorry, solving algebraic equations is a feature we're working on, but it's not ready yet."
    
    expression = query.replace('x', '*')
    expression = expression.replace('^', '**')
    
    if "root" in expression.lower():
        match = re.search(r'root\s*(\d+)', expression.lower())
        if match:
            number = float(match.group(1))
            try:
                result = math.sqrt(number)
                return f"The square root of {int(number)} is {result}."
            except ValueError:
                return "I can't calculate the square root of a negative number."
        return "Sorry, I can only calculate the square root of a single number (e.g., 'root 16')."
    
    if not re.fullmatch(r'[\d\s\.\+\-\*\/\(\)]+', expression):
        return "I can only solve simple arithmetic expressions."
    
    try:
        result = eval(expression)
        return f"The result is {result}."
    except Exception as e:
        return f"Sorry, I couldn't solve that expression. Error: {e}"

def get_avatar_url(username):
    """Generates a unique, consistent avatar based on the username."""
    hash_object = hashlib.md5(username.encode())
    hash_hex = hash_object.hexdigest()
    first_letter = username[0].upper()
    color_code = hash_hex[0:6]
    return f"https://placehold.co/40x40/{color_code}/ffffff?text={first_letter}"

# --- Modern UI Components ---
def confetti_animation():
    """Displays a confetti animation for achievements"""
    html("""
    <script src="https://cdn.jsdelivr.net/npm/canvas-confetti@1.5.1/dist/confetti.browser.min.js"></script>
    <script>
    function fireConfetti() {
        confetti({
            particleCount: 150,
            spread: 70,
            origin: { y: 0.6 }
        });
    }
    setTimeout(fireConfetti, 100);
    </script>
    """)

def progress_bar(value, max_value, color):
    """Creates a modern progress bar"""
    progress_html = f"""
    <div style="margin: 5px 0; border-radius: 10px; background: #e0e0e0; height: 10px; width: 100%;">
        <div style="border-radius: 10px; background: {color}; height: 10px; width: {value/max_value*100}%; transition: width 0.5s ease;"></div>
    </div>
    """
    st.markdown(progress_html, unsafe_allow_html=True)

def metric_card(title, value, icon, color):
    """Creates a modern metric card"""
    return f"""
    <div style="background: white; border-radius: 12px; padding: 15px; box-shadow: 0 4px 12px rgba(0,0,0,0.05); border-left: 4px solid {color}; margin-bottom: 15px;">
        <div style="display: flex; align-items: center; margin-bottom: 8px;">
            <div style="font-size: 24px; margin-right: 10px;">{icon}</div>
            <div style="font-size: 14px; color: #666;">{title}</div>
        </div>
        <div style="font-size: 28px; font-weight: bold; color: {color};">{value}</div>
    </div>
    """

# --- Page Rendering Logic ---

# Add CSS to style a scrollable container for the chat messages.
# This CSS targets a generic Streamlit container element and applies the
# necessary overflow property.
st.markdown("""
<style>
.chat-container {
    height: 600px;
    overflow-y: auto;
    border: 1px solid #e0e0e0;
    border-radius: 8px;
    padding: 10px;
    margin-bottom: 10px;
}
.chat-message-image {
    max-width: 150px;
    border-radius: 8px;
    cursor: pointer;
}
</style>
""", unsafe_allow_html=True)

def show_login_page():
    col1, col2, col3 = st.columns([1, 3, 1])
    with col2:
        st.markdown("""
        <style>
        .login-container {
            background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
            border-radius: 16px;
            padding: 40px;
            box-shadow: 0 8px 32px rgba(31, 38, 135, 0.15);
            backdrop-filter: blur(4px);
            -webkit-backdrop-filter: blur(4px);
            border: 1px solid rgba(255, 255, 255, 0.18);
            text-align: center;
        }
        .login-title {
            background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
            -webkit-background-clip: text;
            background-clip: text;
            color: transparent;
            font-size: 2.2rem;
            font-weight: 800;
            margin-bottom: 10px;
        }
        .login-subtitle {
            color: #475569;
            margin-bottom: 30px;
            font-size: 1rem;
        }
        .stTextInput>div>div>input {
            border-radius: 8px !important;
            padding: 10px 15px !important;
        }
        .login-btn {
            background: linear-gradient(90deg, #667eea 0%, #764ba2 100%) !important;
            border: none !important;
            color: white !important;
            font-weight: 600 !important;
            padding: 12px 24px !important;
            border-radius: 8px !important;
            transition: all 0.3s ease !important;
        }
        .login-btn:hover {
            transform: translateY(-2px);
            box-shadow: 0 5px 15px rgba(102, 126, 234, 0.4) !important;
        }
        .toggle-btn {
            background: transparent !important;
            border: none !important;
            color: #667eea !important;
            font-weight: 500 !important;
        }
        .toggle-btn:hover {
            text-decoration: underline !important;
        }
        .forgot-password {
            text-align: right;
            margin-top: -10px;
            margin-bottom: 15px;
        }
        .forgot-password a {
            color: #666;
            font-size: 0.85rem;
            text-decoration: none;
        }
        .forgot-password a:hover {
            text-decoration: underline;
        }
        </style>
        <div class="login-container">
        <div class="login-title">🔐 MathFriend</div>
        <div class="login-subtitle">Your personal math learning companion</div>
        """, unsafe_allow_html=True)
        # Login form
        if st.session_state.page == "login":
            with st.form("login_form"):
                username = st.text_input("Username", key="login_username")
                password = st.text_input("Password", type="password", key="login_password")
                # Forgot password link
                st.markdown('<div class="forgot-password"><a href="#" onclick="window.alert(\'Password reset feature coming soon! For now, please create a new account.\')">Forgot password?</a></div>', unsafe_allow_html=True)
                submitted = st.form_submit_button("Login", type="primary")
                if submitted:
                    if login_user(username, password):
                        st.session_state.logged_in = True
                        st.session_state.username = username
                        update_user_status(username, True)
                        st.success("Logged in successfully!")
                        st.session_state.page = "home"
                        st.rerun()
                    else:
                        st.error("Invalid username or password.")
        # ... (rest of show_login_page and other functions)
        
# --- Modified Chat Display Section ---

def show_chat_page():
    # Placeholder for the scrollable chat container
    # The custom CSS above will apply scrolling to this div
    st.subheader("Community Chat")
    
    with st.container():
        # Apply the custom CSS class to this container
        st.markdown('<div class="chat-container">', unsafe_allow_html=True)
        
        messages = get_chat_messages()
        for message in messages:
            with st.chat_message(message['username'], avatar=get_avatar_url(message['username'])):
                # Display the sender's username
                st.write(f"**{message['username']}**")
                
                # Check for and display the message text
                if message['message']:
                    st.markdown(format_message(message['message'], get_all_usernames(), st.session_state.username), unsafe_allow_html=True)
                
                # Check for and display media (images)
                if message['media']:
                    try:
                        # Decode the Base64 image data
                        image_data = base64.b64decode(message['media'])
                        
                        # Use a popover for the click-to-enlarge functionality
                        with st.popover("🖼️ View Full Image"):
                            # Display the full-size image inside the popover
                            st.image(image_data, caption="Full size image", use_column_width=True)
                        
                        # Display the thumbnail in the chat message itself
                        st.image(image_data, width=150, caption="Click to enlarge", use_column_width=False)

                    except (base64.binascii.Error, ValueError) as e:
                        st.error(f"Error decoding image: {e}")

        # Close the custom container div
        st.markdown('</div>', unsafe_allow_html=True)

    # --- Chat Input Form ---
    with st.form("chat_form", clear_on_submit=True):
        col1, col2 = st.columns([4, 1])
        with col1:
            chat_message = st.text_input("Type a message...", key="chat_input", placeholder="Type a message...", label_visibility="collapsed")
            # This is where the file uploader for images is placed
            uploaded_file = st.file_uploader("Upload an image...", type=["png", "jpg", "jpeg"], label_visibility="collapsed")
        with col2:
            st.markdown("<br>", unsafe_allow_html=True) # Add a line break for alignment
            send_button = st.form_submit_button("Send", type="primary")

    if send_button:
        # Save the message and/or image to the database
        media_b64 = None
        if uploaded_file is not None:
            # Read the uploaded file and convert it to Base64
            media_b64 = base64.b64encode(uploaded_file.read()).decode('utf-8')
        
        if chat_message or media_b64:
            add_chat_message(st.session_state.username, chat_message, media_b64)
            st.rerun()

    # Automatically refresh the page to show new messages
    st_autorefresh(interval=3000, key="chat_refresh")

    # Update typing status
    # ... (code for typing status)

# Assuming this part of the code exists to handle page navigation
if "page" not in st.session_state:
    st.session_state.page = "login"
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "username" not in st.session_state:
    st.session_state.username = None

# Show the appropriate page based on session state
if st.session_state.logged_in:
    # This is a placeholder for your main app logic, assuming you have a way to show different pages
    # I've added a simple button to demonstrate showing the chat page.
    st.sidebar.title(f"Welcome, {st.session_state.username}!")
    if st.sidebar.button("Show Chat"):
        show_chat_page()
else:
    show_login_page()
