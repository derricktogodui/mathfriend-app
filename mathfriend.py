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

# --- Page and Session Configuration ---

# Streamlit-specific configuration
st.set_page_config(
    layout="wide",
    page_title="MathFriend",
    page_icon="🧮",
    initial_sidebar_state="expanded"
)

# --- NEW: Function to manage query parameters for session persistence ---
def manage_session_state():
    """Uses URL query parameters to maintain login state across refreshes."""
    query_params = st.experimental_get_query_params()
    
    # Check if user is logged in via query param
    if query_params.get("user"):
        if not st.session_state.get("logged_in"):
            # This block runs only once when the page is reloaded with a user query param
            st.session_state.logged_in = True
            st.session_state.username = query_params["user"][0]
    
    # Initialize session state variables if they don't exist
    if "logged_in" not in st.session_state:
        st.session_state.logged_in = False
    if "page" not in st.session_state:
        st.session_state.page = "login"
    if "dark_mode" not in st.session_state:
        st.session_state.dark_mode = False
    if "messages_to_show" not in st.session_state:
        st.session_state.messages_to_show = 30 # For chat pagination


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
def hash_password(password):
    """Hashes a password using bcrypt."""
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def check_password(hashed_password, user_password):
    """Checks a password against its hash."""
    return bcrypt.checkpw(user_password.encode('utf-8'), hashed_password.encode('utf-8'))

def login_user(username, password):
    """Authenticates a user."""
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
    """Creates a new user account."""
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
        return dict(profile) if profile else {}
    except sqlite3.Error as e:
        st.error(f"Get profile error: {e}")
        return {}
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
        c.execute('''INSERT OR REPLACE INTO user_status (username, is_online, last_seen) 
                     VALUES (?, ?, CURRENT_TIMESTAMP)''', (username, is_online))
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
                     (username, is_typing, timestamp) VALUES (?, ?, CURRENT_TIMESTAMP)''', 
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
def generate_question(topic, difficulty):
    """Generates a random math question based on the topic and difficulty."""
    # This logic remains unchanged
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
        question = f"What is ${a} + {b}$?"
        answer = a + b
    elif topic == "Subtraction":
        a, b = max(a, b), min(a, b)
        question = f"What is ${a} - {b}$?"
        answer = a - b
    elif topic == "Multiplication":
        if difficulty == "Hard":
            a = random.randint(10, 20)
            b = random.randint(10, 20)
        question = f"What is ${a} \\times {b}$?"
        answer = a * b
    elif topic == "Division":
        b = random.randint(2, 10)
        a = b * random.randint(1, 10)
        if difficulty == "Hard":
            b = random.randint(11, 20)
            a = b * random.randint(1, 20)
        question = f"What is ${a} \\div {b}$?"
        answer = a / b
    elif topic == "Exponents":
        base = random.randint(1, 5)
        power = random.randint(2, 4)
        if difficulty == "Hard":
            base = random.randint(5, 10)
            power = random.randint(2, 3)
        question = f"What is ${base}^{power}$?"
        answer = base ** power
    else:
        question = "Please select a topic to start."
        answer = None
    
    return question, answer

def save_quiz_result(username, topic, score, duration):
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
        c.execute("""
            SELECT username, MAX(score) as top_score
            FROM quiz_results 
            WHERE topic=? 
            GROUP BY username
            ORDER BY top_score DESC, timestamp ASC 
            LIMIT 10
        """, (topic,))
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
def get_mathbot_response(message):
    """Solves a basic math expression or provides a definition from a chat message."""
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
        "rational functions": "A rational function is any function that can be expressed as a ratio of two polynomials, such as $f(x) = \\frac{P(x)}{Q(x)}$.",
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
    return f"https://placehold.co/60x60/{color_code}/ffffff?text={first_letter}"


# --- Modern UI Components ---
def confetti_animation():
    """Displays a confetti animation for achievements"""
    html("""
    <script src="https://cdn.jsdelivr.net/npm/canvas-confetti@1.5.1/dist/confetti.browser.min.js"></script>
    <script>
    function fireConfetti() {
        confetti({ particleCount: 150, spread: 90, origin: { y: 0.6 } });
    }
    setTimeout(fireConfetti, 100);
    </script>
    """)

def metric_card(title, value, icon, color):
    """Creates a modern metric card"""
    return f"""
    <div class="metric-card-instance" style="border-left: 4px solid {color};">
        <div class="metric-card-content">
            <div class="metric-icon">{icon}</div>
            <div class="metric-title">{title}</div>
        </div>
        <div class="metric-value" style="color: {color};">{value}</div>
    </div>
    """

# --- Page Rendering Logic ---
def show_login_page():
    col1, col2, col3 = st.columns([1, 3, 1])
    with col2:
        st.markdown("""
        <style>
            .login-container {
                background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
                border-radius: 16px; padding: 40px;
                box-shadow: 0 8px 32px rgba(31, 38, 135, 0.15);
                text-align: center;
            }
            .login-title {
                background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
                -webkit-background-clip: text; background-clip: text; color: transparent;
                font-size: 2.2rem; font-weight: 800; margin-bottom: 10px;
            }
            .login-subtitle { color: #475569; margin-bottom: 30px; font-size: 1rem; }
        </style>
        <div class="login-container">
            <div class="login-title">🔐 MathFriend</div>
            <div class="login-subtitle">Your personal math learning companion</div>
        """, unsafe_allow_html=True)

        if st.session_state.page == "login":
            with st.form("login_form"):
                username = st.text_input("Username", key="login_username")
                password = st.text_input("Password", type="password", key="login_password")
                st.markdown('<div style="text-align: right; margin-top: -10px; margin-bottom: 15px;"><a href="#" onclick="window.alert(\'Password reset feature coming soon!\')">Forgot password?</a></div>', unsafe_allow_html=True)
                submitted = st.form_submit_button("Login", type="primary", use_container_width=True)
                
                if submitted:
                    if login_user(username, password):
                        st.session_state.logged_in = True
                        st.session_state.username = username
                        update_user_status(username, True)
                        st.experimental_set_query_params(user=username) # Set query param for session
                        st.success(f"Welcome back, {username}!")
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.error("Invalid username or password.")
            
            if st.button("Don't have an account? Sign Up"):
                st.session_state.page = "signup"
                st.rerun()
        else: # Signup page
            with st.form("signup_form"):
                new_username = st.text_input("New Username", key="signup_username")
                new_password = st.text_input("New Password", type="password", key="signup_password")
                confirm_password = st.text_input("Confirm Password", type="password", key="confirm_password")
                signup_submitted = st.form_submit_button("Create Account", type="primary", use_container_width=True)

                if signup_submitted:
                    if not new_username or not new_password or not confirm_password:
                        st.error("All fields are required.")
                    elif new_password != confirm_password:
                        st.error("Passwords do not match.")
                    elif signup_user(new_username, new_password):
                        st.success("Account created successfully! Please log in.")
                        time.sleep(1)
                        st.session_state.page = "login"
                        st.rerun()
                    else:
                        st.error("Username already exists. Please choose a different one.")
            
            if st.button("Already have an account? Log In"):
                st.session_state.page = "login"
                st.rerun()
        
        st.markdown("</div>", unsafe_allow_html=True)
        st.markdown("<div style='text-align: center; margin-top: 20px; color: #64748b; font-size: 0.9rem;'>Built with ❤️ by Derrick Kwaku Togodui</div>", unsafe_allow_html=True)

def show_profile_page():
    st.header("👤 Your Profile")
    st.markdown("<div class='content-card'>", unsafe_allow_html=True)
    update_user_status(st.session_state.username, True)
    profile = get_user_profile(st.session_state.username)
    
    with st.form("profile_form"):
        col1, col2 = st.columns(2)
        with col1:
            full_name = st.text_input("Full Name", value=profile.get('full_name', ''))
            school = st.text_input("School", value=profile.get('school', ''))
        with col2:
            age = st.number_input("Age", min_value=5, max_value=100, value=profile.get('age', 18))
            bio = st.text_area("Bio", value=profile.get('bio', ''), help="Tell others about your math interests!")
        
        if st.form_submit_button("Save Profile", type="primary"):
            if update_user_profile(st.session_state.username, full_name, school, age, bio):
                st.success("Profile updated successfully!")
                st.rerun()
    
    st.markdown("---")
    st.subheader("Change Password")
    with st.form("password_form"):
        current_password = st.text_input("Current Password", type="password")
        new_password = st.text_input("New Password", type="password")
        confirm_password = st.text_input("Confirm New Password", type="password")
        
        if st.form_submit_button("Change Password", type="primary"):
            if new_password != confirm_password:
                st.error("New passwords don't match!")
            elif change_password(st.session_state.username, current_password, new_password):
                st.success("Password changed successfully!")
            else:
                st.error("Incorrect current password")
    
    st.markdown("</div>", unsafe_allow_html=True)

def show_main_app():
    # --- GLOBAL CSS STYLES ---
    st.markdown("""
    <style>
        /* Base Variables */
        :root {
            --primary: #4361ee; --secondary: #3a0ca3; --accent: #4895ef;
            --light-bg: #f8f9fa; --dark-text: #212529; --light-text: #f8f9fa;
            --card-bg-light: #ffffff; --card-border-light: rgba(0, 0, 0, 0.05);
            --success: #4cc9f0; --warning: #f8961e; --danger: #f72585;
            --green-light: #dcf8c6; --green-dark: #2a3922; --white-ish: #f1f1f1;
            --dark-bg: #121212; --card-bg-dark: #1e1e1e; --card-border-dark: #333;
            --text-dark-primary: #e0e0e0; --text-dark-secondary: #aaaaaa;
        }

        /* General layout and cards */
        .main-content-container { padding: 20px; border-radius: 12px; transition: all 0.3s ease; }
        .content-card {
            background-color: var(--card-bg-light); color: var(--dark-text);
            padding: 25px; border-radius: 12px;
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.05); margin-bottom: 20px;
            border: 1px solid var(--card-border-light);
            transition: transform 0.3s ease, box-shadow 0.3s ease;
        }
        .content-card:hover { transform: translateY(-3px); box-shadow: 0 6px 16px rgba(0, 0, 0, 0.1); }
        .main-title {
            background: linear-gradient(90deg, var(--primary), var(--secondary));
            -webkit-background-clip: text; background-clip: text; color: transparent;
            font-size: clamp(1.8rem, 4vw, 2.5rem); margin-bottom: 0.5rem; word-break: break-word;
        }

        /* Header Avatar Fix */
        .header-container { display: flex; align-items: center; margin-bottom: 20px; gap: 15px; }
        .avatar-container { flex-shrink: 0; position: relative; }
        .header-text { min-width: 0; }

        /* Dashboard Metrics */
        .metric-card-instance {
            background: var(--card-bg-light); border-radius: 12px; padding: 15px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.05); margin-bottom: 15px;
        }
        .metric-card-content { display: flex; align-items: center; margin-bottom: 8px; }
        .metric-icon { font-size: 24px; margin-right: 10px; }
        .metric-title { font-size: 14px; color: #666; }
        .metric-value { font-size: 28px; font-weight: bold; }

        /* Chat Redesign Styles */
        .chat-app-container {
            display: flex; flex-direction: column; height: 75vh;
            background: var(--card-bg-light); border-radius: 12px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.08); overflow: hidden;
        }
        .chat-header { padding: 10px 15px; border-bottom: 1px solid var(--card-border-light); font-size: 0.9rem; }
        .chat-messages { flex: 1; overflow-y: auto; padding: 10px; display: flex; flex-direction: column; }
        .msg-row { display: flex; align-items: flex-end; margin-bottom: 8px; }
        .msg-own { justify-content: flex-end; }
        .msg-bubble { max-width: 80%; padding: 8px 14px; border-radius: 18px; line-height: 1.4; word-wrap: break-word; box-shadow: 0 1px 2px rgba(0,0,0,0.1); }
        .msg-own .msg-bubble { background-color: var(--green-light); border-bottom-right-radius: 4px; color: #222; }
        .msg-other .msg-bubble { background-color: var(--white-ish); border-bottom-left-radius: 4px; color: #222; }
        .avatar-small { width: 30px; height: 30px; border-radius: 50%; margin-right: 8px; }
        .msg-meta { font-size: 0.75rem; color: #888; margin: 0 5px 3px 5px; }
        .msg-content { display: flex; flex-direction: column; }
        .date-separator { text-align: center; font-size: 0.75rem; color: #999; margin: 10px auto; padding: 2px 10px; background: var(--light-bg); border-radius: 10px; }
        .chat-image { max-height: 200px; border-radius: 8px; cursor: pointer; margin-top: 5px; }
        .chat-input-area { padding: 10px; border-top: 1px solid #ddd; background: #f0f0f0; }
        
        /* Leaderboard Redesign */
        .leaderboard-card { display: flex; align-items: center; padding: 15px; margin-bottom: 10px; border-radius: 10px; transition: all 0.2s ease; }
        .leaderboard-card:hover { transform: scale(1.02); }
        .leaderboard-rank { font-size: 1.5rem; font-weight: bold; color: #888; width: 40px; }
        .leaderboard-avatar { width: 50px; height: 50px; border-radius: 50%; margin: 0 15px; }
        .leaderboard-user { font-weight: 600; font-size: 1.1rem; flex-grow: 1; }
        .leaderboard-score { font-size: 1.2rem; font-weight: bold; }
        .rank-1 { background: linear-gradient(135deg, #FFD700, #FFA500); color: white; }
        .rank-2 { background: linear-gradient(135deg, #C0C0C0, #A9A9A9); color: white; }
        .rank-3 { background: linear-gradient(135deg, #CD7F32, #A0522D); color: white; }
        .rank-other { background: var(--card-bg-light); border: 1px solid var(--card-border-light); }

        /* Quiz Redesign */
        .quiz-setup-card { text-align: center; }
        .quiz-results-summary { text-align: center; padding: 30px; }
        .quiz-final-score { font-size: 3rem; font-weight: bold; color: var(--primary); }
        
        /* Generic helpers */
        .mention-highlight { font-weight: bold; color: white !important; background-color: var(--accent); padding: 2px 6px; border-radius: 6px; }
    </style>
    """, unsafe_allow_html=True)
    
    # --- COMPREHENSIVE DARK MODE STYLES ---
    if st.session_state.dark_mode:
        st.markdown("""
        <style>
            /* Apply to main background and text */
            [data-testid="stApp"], .main-content-container, body {
                background-color: var(--dark-bg) !important;
                color: var(--text-dark-primary) !important;
            }
            h1, h2, h3, h4, p, label, .stMarkdown, .stRadio { color: var(--text-dark-primary); }
            
            /* Cards and Containers */
            .content-card, .metric-card-instance, .rank-other, .quiz-setup-card {
                background-color: var(--card-bg-dark) !important;
                border-color: var(--card-border-dark) !important;
                color: var(--text-dark-primary);
            }
            .stTextInput>div>div>input, .stTextArea>div>textarea, .stNumberInput>div>div>input {
                background-color: #2c2c2c !important;
                color: var(--text-dark-primary) !important;
                border-color: #444 !important;
            }
            
            /* Chat Dark Mode */
            .chat-app-container { background: #181818 !important; }
            .chat-header { border-bottom-color: var(--card-border-dark); }
            .msg-own .msg-bubble { background-color: var(--green-dark); color: var(--text-dark-primary); }
            .msg-other .msg-bubble { background-color: #333; color: var(--text-dark-primary); }
            .chat-input-area { background: #222; border-top-color: var(--card-border-dark); }
            .date-separator { background: #2c2c2c; color: #888; }
            .metric-title, .msg-meta { color: var(--text-dark-secondary) !important; }

            /* Leaderboard winner cards */
            .rank-1, .rank-2, .rank-3 { color: #111 !important; } /* Make text dark on bright gradients */
        </style>
        """, unsafe_allow_html=True)

    with st.sidebar:
        # NEW: Global heading
        st.title("🧮 MathFriend")
        st.markdown("---")
        st.markdown("### **Menu**")
        selected_page = st.sidebar.radio(
            "Go to", 
            ["📊 Dashboard", "📝 Quiz", "🏆 Leaderboard", "💬 Chat", "👤 Profile", "📚 Learning Resources"],
            label_visibility="collapsed"
        )
        st.markdown("---")
        st.markdown("### **Appearance**")
        st.session_state.dark_mode = st.toggle("🌙 Dark Mode", value=st.session_state.dark_mode)
        st.markdown("---")
        st.markdown("### **Account**")
        if st.sidebar.button("Logout", type="secondary"):
            update_user_status(st.session_state.username, False)
            st.experimental_set_query_params() # Clear query params on logout
            st.session_state.logged_in = False
            st.session_state.page = "login"
            # Clear other states on logout
            for key in list(st.session_state.keys()):
                if key not in ['page']:
                    del st.session_state[key]
            st.rerun()

    # Main content area
    st.markdown(f"<div class='main-content-container'>", unsafe_allow_html=True)
    
    # --- MODIFIED: Header with responsive avatar ---
    avatar_url = get_avatar_url(st.session_state.username)
    profile = get_user_profile(st.session_state.username)
    display_name = profile.get('full_name', st.session_state.username)

    st.markdown(f"""
    <div class="header-container">
        <div class="avatar-container">
            <img src="{avatar_url}" style="width: 60px; height: 60px; border-radius: 50%; border: 3px solid var(--primary);"/>
            <div style="position: absolute; bottom: 2px; right: 2px; width: 14px; height: 14px; border-radius: 50%; background-color: #4CAF50; border: 2px solid white;"></div>
        </div>
        <div class="header-text">
            <h1 class="main-title">Welcome back, {display_name}!</h1>
            <p style="color: #666; margin-top: -10px;">Ready to master some math today?</p>
        </div>
    </div>
    """, unsafe_allow_html=True)

    update_user_status(st.session_state.username, True)

    if selected_page == "📊 Dashboard":
        st.markdown("<div class='content-card'>", unsafe_allow_html=True)
        st.header("📈 Progress Dashboard")
        st.write("Track your math learning journey with these insights.")
        total_quizzes, last_score, top_score = get_user_stats(st.session_state.username)
        
        cols = st.columns(3)
        with cols[0]:
            st.markdown(metric_card("Total Quizzes", total_quizzes, "📚", "#4361ee"), unsafe_allow_html=True)
        with cols[1]:
            st.markdown(metric_card("Last Score", f"{last_score}/5" if last_score != "N/A" else "N/A", "⭐", "#4cc9f0"), unsafe_allow_html=True)
        with cols[2]:
            st.markdown(metric_card("Top Score", f"{top_score}/5" if top_score != "N/A" else "N/A", "🏆", "#f72585"), unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

        user_history = get_user_quiz_history(st.session_state.username)
        if user_history:
            df = pd.DataFrame(user_history, columns=['Topic', 'Score', 'Timestamp'])
            df['Timestamp'] = pd.to_datetime(df['Timestamp'])
            df['Date'] = df['Timestamp'].dt.date
            
            plot_template = "plotly_dark" if st.session_state.dark_mode else "plotly_white"

            with st.container():
                st.markdown("<div class='content-card'>", unsafe_allow_html=True)
                st.subheader("📅 Your Progress Over Time")
                fig = px.line(df, x='Date', y='Score', color='Topic', markers=True, template=plot_template)
                fig.update_layout(plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)')
                st.plotly_chart(fig, use_container_width=True)
                st.markdown("</div>", unsafe_allow_html=True)
            
            with st.container():
                st.markdown("<div class='content-card'>", unsafe_allow_html=True)
                st.subheader("📊 Performance by Topic")
                avg_scores = df.groupby('Topic')['Score'].mean().reset_index()
                fig_bar = px.bar(avg_scores, x='Topic', y='Score', color='Topic', template=plot_template, text='Score')
                fig_bar.update_layout(showlegend=False, plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)')
                st.plotly_chart(fig_bar, use_container_width=True)
                st.markdown("</div>", unsafe_allow_html=True)
        else:
            st.info("Start taking quizzes to see your progress here!")

    elif selected_page == "📝 Quiz":
        st.header("🧠 Quiz Time!")
        if 'quiz_active' not in st.session_state:
            st.session_state.quiz_active = False

        if not st.session_state.quiz_active:
            # --- REDESIGNED: Quiz Setup Card ---
            st.markdown("<div class='content-card quiz-setup-card'>", unsafe_allow_html=True)
            st.subheader("🚀 Set Up Your Challenge")
            st.write("Select a topic and difficulty to test your skills!")
            
            topic_options = ["Addition", "Subtraction", "Multiplication", "Division", "Exponents"]
            st.session_state.topic = st.selectbox("Choose a topic:", topic_options, key="quiz_topic_select")
            
            difficulty_options = ["Easy", "Medium", "Hard"]
            st.session_state.difficulty = st.radio("Choose difficulty:", difficulty_options, horizontal=True, key="quiz_difficulty_radio")
            
            if st.button("Start Quiz", type="primary", use_container_width=True):
                st.session_state.quiz_active = True
                st.session_state.current_question = 0
                st.session_state.score = 0
                st.session_state.questions = [generate_question(st.session_state.topic, st.session_state.difficulty) for _ in range(5)]
                st.session_state.quiz_started_time = time.time()
                st.rerun()
            st.markdown("</div>", unsafe_allow_html=True)
        else:
            st.markdown("<div class='content-card'>", unsafe_allow_html=True)
            if st.session_state.current_question < len(st.session_state.questions):
                question_text, correct_answer = st.session_state.questions[st.session_state.current_question]
                st.subheader(f"Question {st.session_state.current_question + 1} of {len(st.session_state.questions)}")
                st.markdown(f"<h3>{question_text}</h3>", unsafe_allow_html=True)
                
                with st.form(key=f"quiz_form_{st.session_state.current_question}"):
                    user_answer = st.number_input("Your answer:", step=1, key=f"answer_{st.session_state.current_question}")
                    if st.form_submit_button("Submit Answer", type="primary"):
                        if user_answer == correct_answer:
                            st.success("Correct! 🎉")
                            st.session_state.score += 1
                            confetti_animation()
                        else:
                            st.error(f"Incorrect. The correct answer was {correct_answer}.")
                        st.session_state.current_question += 1
                        time.sleep(1)
                        st.rerun()
            else:
                # --- REDESIGNED: Quiz Results ---
                duration = time.time() - st.session_state.quiz_started_time
                st.balloons()
                st.markdown("<div class='quiz-results-summary'>", unsafe_allow_html=True)
                st.header("✨ Quiz Complete! ✨")
                st.markdown(f"You scored <span class='quiz-final-score'>{st.session_state.score}/{len(st.session_state.questions)}</span>", unsafe_allow_html=True)
                
                cols = st.columns(3)
                cols[0].metric("Final Score", st.session_state.score)
                cols[1].metric("Accuracy", f"{st.session_state.score/len(st.session_state.questions)*100:.0f}%")
                cols[2].metric("Time Taken", f"{duration:.0f}s")
                
                save_quiz_result(st.session_state.username, st.session_state.topic, st.session_state.score, duration)
                st.session_state.quiz_active = False

                if st.button("Start a New Quiz", type="primary", use_container_width=True):
                    st.rerun()
                st.markdown("</div>", unsafe_allow_html=True)
            st.markdown("</div>", unsafe_allow_html=True)

    elif selected_page == "🏆 Leaderboard":
        st.header("🏆 Global Leaderboard")
        st.markdown("<div class='content-card'>", unsafe_allow_html=True)
        st.write("See who has the highest scores for each topic!")
        
        topic_options = ["Addition", "Subtraction", "Multiplication", "Division", "Exponents"]
        leaderboard_topic = st.selectbox("Select a topic:", topic_options)
        top_scores = get_top_scores(leaderboard_topic)
        st.markdown("</div>", unsafe_allow_html=True)

        if top_scores:
            # --- REDESIGNED: Leaderboard Display ---
            for i, (username, score) in enumerate(top_scores):
                rank = i + 1
                avatar = get_avatar_url(username)
                
                if rank == 1: card_class, rank_display = "rank-1", "🥇"
                elif rank == 2: card_class, rank_display = "rank-2", "🥈"
                elif rank == 3: card_class, rank_display = "rank-3", "🥉"
                else: card_class, rank_display = "rank-other", f"#{rank}"
                
                score_color = "#111" if rank <= 3 else "var(--primary)"

                st.markdown(f"""
                <div class="leaderboard-card {card_class}">
                    <div class="leaderboard-rank">{rank_display}</div>
                    <img src="{avatar}" class="leaderboard-avatar">
                    <div class="leaderboard-user">{username}</div>
                    <div class="leaderboard-score" style="color: {score_color}">{score}/5</div>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.info("No scores have been recorded for this topic yet. Be the first!")

    elif selected_page == "💬 Chat":
        st.header("💬 Community Chat")
        st_autorefresh(interval=3000, key="chat_refresh")

        all_messages = get_chat_messages()
        online_users = get_online_users()

        # --- REDESIGNED: Chat App Container ---
        st.markdown('<div class="chat-app-container">', unsafe_allow_html=True)
        
        # Chat Header
        st.markdown(f"""
        <div class="chat-header">
            <b>Online:</b> {', '.join([f'🟢 {u}' for u in online_users]) if online_users else 'None'}
        </div>
        """, unsafe_allow_html=True)

        # Chat Messages Area
        st.markdown('<div id="chat-messages" class="chat-messages">', unsafe_allow_html=True)

        # Pagination Button
        if len(all_messages) > st.session_state.messages_to_show:
            if st.button("Load Older Messages", key="load_more"):
                st.session_state.messages_to_show += 30
                st.rerun()

        # Display sliced messages
        messages_to_display = all_messages[-st.session_state.messages_to_show:]
        last_date, last_user = None, None
        
        for msg in messages_to_display:
            username, message, media, timestamp = msg['username'], msg['message'], msg['media'], msg['timestamp']
            date_obj = datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S")
            date_str = date_obj.strftime("%b %d, %Y")
            time_str = date_obj.strftime("%H:%M")

            if date_str != last_date:
                st.markdown(f'<div class="date-separator">{date_str}</div>', unsafe_allow_html=True)
                last_date = date_str

            own = username == st.session_state.username
            row_class = "msg-own" if own else "msg-other"
            avatar_html = "" if own or last_user == username else f"<img src='{get_avatar_url(username)}' class='avatar-small'/>"
            
            parts = [f"<div>{format_message(message, [], st.session_state.username)}</div>"] if message else []
            if media:
                parts.append(f"<img src='data:image/png;base64,{media}' class='chat-image' onclick='alert(\"Image viewer coming soon!\")'/>")

            bubble_html = f"""
            <div class="msg-content">
                {'<div class="msg-meta" style="text-align: right;">' if own else '<div class="msg-meta">'}
                    {'' if own else f"<b>{username}</b> at "}{time_str}
                </div>
                <div class="msg-bubble">{''.join(parts)}</div>
            </div>
            """
            st.markdown(f"<div class='msg-row {row_class}'>{avatar_html if not own else ''}{bubble_html}{avatar_html if own else ''}</div>", unsafe_allow_html=True)
            last_user = username

        st.markdown('</div>', unsafe_allow_html=True) # End chat-messages
        
        # Chat Input Area
        st.markdown('<div class="chat-input-area">', unsafe_allow_html=True)
        with st.form("chat_form", clear_on_submit=True):
            user_message = st.text_area("", key="chat_input", height=40, placeholder="Type a message...", label_visibility="collapsed")
            c1, c2 = st.columns([4, 1])
            with c1:
                uploaded_file = st.file_uploader("📷", type=["png","jpg","jpeg"], label_visibility="collapsed")
            with c2:
                submitted = st.form_submit_button("Send", type="primary", use_container_width=True)
            
            if submitted and (user_message.strip() or uploaded_file):
                media_data = base64.b64encode(uploaded_file.getvalue()).decode('utf-8') if uploaded_file else None
                add_chat_message(st.session_state.username, user_message, media_data)
                if user_message.startswith("@MathBot"):
                    bot_response = get_mathbot_response(user_message)
                    if bot_response: add_chat_message("MathBot", bot_response)
                st.rerun()
        st.markdown('</div>', unsafe_allow_html=True) # End chat-input-area
        st.markdown('</div>', unsafe_allow_html=True) # End chat-app-container

        # Auto-scroll to bottom script
        html("""
        <script>
            setTimeout(function() {
                var chatBox = document.getElementById('chat-messages');
                if (chatBox) {
                    chatBox.scrollTop = chatBox.scrollHeight;
                }
            }, 200); // Delay to ensure DOM is updated
        </script>
        """, height=0)

    elif selected_page == "👤 Profile":
        show_profile_page()

    elif selected_page == "📚 Learning Resources":
        st.header("📚 Learning Resources")
        st.markdown("<div class='content-card'>", unsafe_allow_html=True)
        st.write("Mini-tutorials and helpful examples to help you study.")
        
        resource_topic = st.selectbox("Select a topic to learn about:", ["sets and operations on sets", "surds"])

        if resource_topic == "sets and operations on sets":
            st.subheader("🧮 Sets and Operations")
            st.markdown("A **set** is a collection of distinct objects. Operations include:")
            st.markdown("- **Union (A ∪ B):** All elements from both sets.")
            st.markdown("- **Intersection (A ∩ B):** Elements common to both sets.")
            st.markdown("**Example:** If A = {1, 2} and B = {2, 3}, then A ∩ B = {2}.")
        elif resource_topic == "surds":
            st.subheader("√ Surds")
            st.markdown("A **surd** is an irrational number expressed with a root symbol, like $ \sqrt{2} $. We can simplify them: $ \sqrt{12} = \sqrt{4 \cdot 3} = \sqrt{4} \cdot \sqrt{3} = 2\sqrt{3} $.")
        
        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("</div>", unsafe_allow_html=True) # Close main content container

# --- Main App Logic ---
if __name__ == "__main__":
    if "show_splash" not in st.session_state:
        st.session_state.show_splash = True

    if st.session_state.show_splash:
        st.markdown("""
        <style>
            .main {visibility: hidden;}
            .splash-container { position: fixed; top: 0; left: 0; width: 100vw; height: 100vh; background-color: #fff; display: flex; justify-content: center; align-items: center; z-index: 9999; }
            .splash-text { font-size: 50px; font-weight: bold; color: #2E86C1; }
        </style>
        <div class="splash-container"><div class="splash-text">MathFriend</div></div>
        """, unsafe_allow_html=True)
        time.sleep(1)
        st.session_state.show_splash = False
        st.rerun()
    else:
        st.markdown("<style>.main {visibility: visible;}</style>", unsafe_allow_html=True)
        manage_session_state() # Initialize or restore session state
        
        if st.session_state.logged_in:
            show_main_app()
        else:
            show_login_page()
