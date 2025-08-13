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

# --- UPDATED: Function to manage query parameters for session persistence ---
def manage_session_state():
    """Uses URL query parameters to maintain login state across refreshes."""
    # REPLACED: st.experimental_get_query_params() with st.query_params
    if "user" in st.query_params:
        if not st.session_state.get("logged_in"):
            st.session_state.logged_in = True
            # REPLACED: No longer need to access by index [0]
            st.session_state.username = st.query_params["user"]
    
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
    """
    conn = None
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        
        c.execute('''CREATE TABLE IF NOT EXISTS users
                     (username TEXT PRIMARY KEY, password TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS quiz_results
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      username TEXT, topic TEXT, score INTEGER,
                      timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        c.execute('''CREATE TABLE IF NOT EXISTS chat_messages
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      username TEXT, message TEXT, media TEXT,
                      timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        c.execute('''CREATE TABLE IF NOT EXISTS user_profiles
                     (username TEXT PRIMARY KEY, full_name TEXT,
                      school TEXT, age INTEGER, bio TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS user_status
                     (username TEXT PRIMARY KEY, is_online BOOLEAN,
                      last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        c.execute('''CREATE TABLE IF NOT EXISTS typing_indicators
                     (username TEXT PRIMARY KEY, is_typing BOOLEAN,
                      timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')

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

create_tables_if_not_exist()


# --- User Authentication Functions --- 
def hash_password(password):
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def check_password(hashed_password, user_password):
    return bcrypt.checkpw(user_password.encode('utf-8'), hashed_password.encode('utf-8'))

def login_user(username, password):
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
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        hashed_password = hash_password(password)
        c.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, hashed_password))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    except sqlite3.Error as e:
        st.error(f"Signup database error: {e}")
        return False
    finally:
        if conn:
            conn.close()


# --- Profile Management Functions ---
def get_user_profile(username):
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
            a, b = random.randint(10, 20), random.randint(10, 20)
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
        question, answer = "Please select a topic to start.", None
    
    return question, answer

def save_quiz_result(username, topic, score, duration):
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
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("""
            SELECT username, MAX(score) as top_score
            FROM quiz_results WHERE topic=? GROUP BY username
            ORDER BY top_score DESC, timestamp ASC LIMIT 10
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
    try:
        conn = sqlite3.connect(DB_FILE)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT topic, score, timestamp FROM quiz_results WHERE username=? ORDER BY timestamp DESC", (username,))
        return c.fetchall()
    except sqlite3.Error as e:
        st.error(f"Get quiz history database error: {e}")
        return []
    finally:
        if conn:
            conn.close()

def get_user_stats(username):
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM quiz_results WHERE username=?", (username,))
        total_quizzes = c.fetchone()[0]
        c.execute("SELECT score FROM quiz_results WHERE username=? ORDER BY timestamp DESC LIMIT 1", (username,))
        last_score = c.fetchone()
        last_score = last_score[0] if last_score else "N/A"
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
    try:
        conn = sqlite3.connect(DB_FILE)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT id, username, message, media, timestamp FROM chat_messages ORDER BY timestamp ASC")
        return c.fetchall()
    except sqlite3.Error as e:
        st.error(f"Get chat messages database error: {e}")
        return []
    finally:
        if conn:
            conn.close()

def get_all_usernames():
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT username FROM users")
        return [row[0] for row in c.fetchall()]
    except sqlite3.Error as e:
        st.error(f"Get all usernames database error: {e}")
        return []
    finally:
        if conn:
            conn.close()

def format_message(message, mentioned_usernames, current_user):
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
    if not message.startswith("@MathBot"):
        return None
    query = message.replace("@MathBot", "").strip().lower()
    definitions = {
        "sets": "A set is a collection of distinct objects, considered as an object in its own right.",
        "surds": "A surd is an irrational number that can be expressed with a root symbol, like $\sqrt{2}$.",
    }
    if query.startswith("define"):
        term = query.split("define", 1)[1].strip()
        return f"**Definition:** {definitions.get(term, 'I don\\'t have a definition for that yet.')}",
    try:
        expression = query.replace('x', '*').replace('^', '**')
        if not re.fullmatch(r'[\d\s\.\+\-\*\/\(\)]+', expression):
            return "I can only solve simple arithmetic expressions."
        return f"The result is {eval(expression)}."
    except Exception:
        return "Sorry, I couldn't solve that expression."

def get_avatar_url(username):
    hash_object = hashlib.md5(username.encode())
    hash_hex = hash_object.hexdigest()
    first_letter = username[0].upper()
    color_code = hash_hex[0:6]
    return f"https://placehold.co/60x60/{color_code}/ffffff?text={first_letter}"


# --- Modern UI Components ---
def confetti_animation():
    html("""
    <script src="https://cdn.jsdelivr.net/npm/canvas-confetti@1.5.1/dist/confetti.browser.min.js"></script>
    <script>setTimeout(() => confetti({ particleCount: 150, spread: 90, origin: { y: 0.6 } }), 100);</script>
    """)

def metric_card(title, value, icon, color):
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
            .login-container { background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%); border-radius: 16px; padding: 40px; box-shadow: 0 8px 32px rgba(31, 38, 135, 0.15); text-align: center; }
            .login-title { background: linear-gradient(90deg, #667eea 0%, #764ba2 100%); -webkit-background-clip: text; background-clip: text; color: transparent; font-size: 2.2rem; font-weight: 800; margin-bottom: 10px; }
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
                        # REPLACED: st.experimental_set_query_params with st.query_params
                        st.query_params["user"] = username
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
                if st.form_submit_button("Create Account", type="primary", use_container_width=True):
                    if not all([new_username, new_password, confirm_password]):
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
        :root {
            --primary: #4361ee; --secondary: #3a0ca3; --accent: #4895ef;
            --light-bg: #f8f9fa; --dark-text: #212529; --light-text: #f8f9fa;
            --card-bg-light: #ffffff; --card-border-light: rgba(0, 0, 0, 0.05);
            --success: #4cc9f0; --warning: #f8961e; --danger: #f72585;
            --green-light: #dcf8c6; --green-dark: #2a3922; --white-ish: #f1f1f1;
            --dark-bg: #121212; --card-bg-dark: #1e1e1e; --card-border-dark: #333;
            --text-dark-primary: #e0e0e0; --text-dark-secondary: #aaaaaa;
        }
        .main-content-container { padding: 20px; border-radius: 12px; transition: all 0.3s ease; }
        .content-card { background-color: var(--card-bg-light); color: var(--dark-text); padding: 25px; border-radius: 12px; box-shadow: 0 4px 12px rgba(0, 0, 0, 0.05); margin-bottom: 20px; border: 1px solid var(--card-border-light); transition: transform 0.3s ease, box-shadow 0.3s ease; }
        .content-card:hover { transform: translateY(-3px); box-shadow: 0 6px 16px rgba(0, 0, 0, 0.1); }
        .main-title { background: linear-gradient(90deg, var(--primary), var(--secondary)); -webkit-background-clip: text; background-clip: text; color: transparent; font-size: clamp(1.8rem, 4vw, 2.5rem); margin-bottom: 0.5rem; word-break: break-word; }
        .header-container { display: flex; align-items: center; margin-bottom: 20px; gap: 15px; }
        .avatar-container { flex-shrink: 0; position: relative; }
        .header-text { min-width: 0; }
        .metric-card-instance { background: var(--card-bg-light); border-radius: 12px; padding: 15px; box-shadow: 0 4px 12px rgba(0,0,0,0.05); margin-bottom: 15px; }
        .metric-card-content { display: flex; align-items: center; margin-bottom: 8px; }
        .metric-icon { font-size: 24px; margin-right: 10px; }
        .metric-title { font-size: 14px; color: #666; }
        .metric-value { font-size: 28px; font-weight: bold; }
        .chat-app-container { display: flex; flex-direction: column; height: 75vh; background: var(--card-bg-light); border-radius: 12px; box-shadow: 0 4px 12px rgba(0,0,0,0.08); overflow: hidden; }
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
        .quiz-setup-card { text-align: center; }
        .quiz-results-summary { text-align: center; padding: 30px; }
        .quiz-final-score { font-size: 3rem; font-weight: bold; color: var(--primary); }
        .mention-highlight { font-weight: bold; color: white !important; background-color: var(--accent); padding: 2px 6px; border-radius: 6px; }
    </style>
    """, unsafe_allow_html=True)
    
    if st.session_state.dark_mode:
        st.markdown("""
        <style>
            [data-testid="stApp"], .main-content-container, body { background-color: var(--dark-bg) !important; color: var(--text-dark-primary) !important; }
            h1, h2, h3, h4, p, label, .stMarkdown, .stRadio { color: var(--text-dark-primary); }
            .content-card, .metric-card-instance, .rank-other, .quiz-setup-card { background-color: var(--card-bg-dark) !important; border-color: var(--card-border-dark) !important; color: var(--text-dark-primary); }
            .stTextInput>div>div>input, .stTextArea>div>textarea, .stNumberInput>div>div>input { background-color: #2c2c2c !important; color: var(--text-dark-primary) !important; border-color: #444 !important; }
            .chat-app-container { background: #181818 !important; }
            .chat-header { border-bottom-color: var(--card-border-dark); }
            .msg-own .msg-bubble { background-color: var(--green-dark); color: var(--text-dark-primary); }
            .msg-other .msg-bubble { background-color: #333; color: var(--text-dark-primary); }
            .chat-input-area { background: #222; border-top-color: var(--card-border-dark); }
            .date-separator { background: #2c2c2c; color: #888; }
            .metric-title, .msg-meta { color: var(--text-dark-secondary) !important; }
            .rank-1, .rank-2, .rank-3 { color: #111 !important; }
        </style>
        """, unsafe_allow_html=True)

    with st.sidebar:
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
            # REPLACED: st.experimental_set_query_params() with st.query_params.clear()
            st.query_params.clear()
            st.session_state.logged_in = False
            st.session_state.page = "login"
            for key in list(st.session_state.keys()):
                if key not in ['page']:
                    del st.session_state[key]
            st.rerun()

    st.markdown(f"<div class='main-content-container'>", unsafe_allow_html=True)
    
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
        cols[0].markdown(metric_card("Total Quizzes", total_quizzes, "📚", "#4361ee"), unsafe_allow_html=True)
        cols[1].markdown(metric_card("Last Score", f"{last_score}/5" if last_score != "N/A" else "N/A", "⭐", "#4cc9f0"), unsafe_allow_html=True)
        cols[2].markdown(metric_card("Top Score", f"{top_score}/5" if top_score != "N/A" else "N/A", "🏆", "#f72585"), unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

        user_history = get_user_quiz_history(st.session_state.username)
        if user_history:
            df = pd.DataFrame(user_history, columns=['Topic', 'Score', 'Timestamp'])
            df['Timestamp'] = pd.to_datetime(df['Timestamp'])
            df['Date'] = df['Timestamp'].dt.date
            plot_template = "plotly_dark" if st.session_state.dark_mode else "plotly_white"

            st.markdown("<div class='content-card'>", unsafe_allow_html=True)
            st.subheader("📅 Your Progress Over Time")
            fig = px.line(df, x='Date', y='Score', color='Topic', markers=True, template=plot_template)
            fig.update_layout(plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)')
            st.plotly_chart(fig, use_container_width=True)
            st.markdown("</div>", unsafe_allow_html=True)
        else:
            st.info("Start taking quizzes to see your progress here!")

    elif selected_page == "📝 Quiz":
        st.header("🧠 Quiz Time!")
        if 'quiz_active' not in st.session_state:
            st.session_state.quiz_active = False

        if not st.session_state.quiz_active:
            st.markdown("<div class='content-card quiz-setup-card'>", unsafe_allow_html=True)
            st.subheader("🚀 Set Up Your Challenge")
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
                duration = time.time() - st.session_state.quiz_started_time
                st.balloons()
                st.markdown("<div class='quiz-results-summary'>", unsafe_allow_html=True)
                st.header("✨ Quiz Complete! ✨")
                st.markdown(f"<span class='quiz-final-score'>{st.session_state.score}/{len(st.session_state.questions)}</span>", unsafe_allow_html=True)
                
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
        topic_options = ["Addition", "Subtraction", "Multiplication", "Division", "Exponents"]
        leaderboard_topic = st.selectbox("Select a topic:", topic_options)
        top_scores = get_top_scores(leaderboard_topic)
        st.markdown("</div>", unsafe_allow_html=True)

        if top_scores:
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

        st.markdown('<div class="chat-app-container">', unsafe_allow_html=True)
        st.markdown(f'<div class="chat-header"><b>Online:</b> {", ".join(f"🟢 {u}" for u in online_users) if online_users else "None"}</div>', unsafe_allow_html=True)
        st.markdown('<div id="chat-messages" class="chat-messages">', unsafe_allow_html=True)

        if len(all_messages) > st.session_state.messages_to_show:
            if st.button("Load Older Messages", key="load_more"):
                st.session_state.messages_to_show += 30
                st.rerun()
        
        messages_to_display = all_messages[-st.session_state.messages_to_show:]
        last_date = None
        for msg in messages_to_display:
            date_obj = datetime.strptime(msg['timestamp'], "%Y-%m-%d %H:%M:%S")
            if date_obj.strftime("%b %d, %Y") != last_date:
                last_date = date_obj.strftime("%b %d, %Y")
                st.markdown(f'<div class="date-separator">{last_date}</div>', unsafe_allow_html=True)
            
            own = msg['username'] == st.session_state.username
            st.markdown(f"""
            <div class="msg-row {'msg-own' if own else 'msg-other'}">
                {'' if own else f"<img src='{get_avatar_url(msg['username'])}' class='avatar-small'/>"}
                <div class="msg-content">
                    <div class="msg-meta" style="text-align: {'right' if own else 'left'};">
                        {'' if own else f"<b>{msg['username']}</b> at "}{date_obj.strftime('%H:%M')}
                    </div>
                    <div class="msg-bubble">
                        {format_message(msg['message'], [], st.session_state.username) if msg['message'] else ''}
                        {f"<img src='data:image/png;base64,{msg['media']}' class='chat-image'/>" if msg['media'] else ''}
                    </div>
                </div>
            </div>""", unsafe_allow_html=True)

        st.markdown('</div>', unsafe_allow_html=True)
        
        st.markdown('<div class="chat-input-area">', unsafe_allow_html=True)
        with st.form("chat_form", clear_on_submit=True):
            user_message = st.text_area("", key="chat_input", height=40, placeholder="Type a message...", label_visibility="collapsed")
            c1, c2 = st.columns([4, 1])
            uploaded_file = c1.file_uploader("📷", type=["png","jpg","jpeg"], label_visibility="collapsed")
            if c2.form_submit_button("Send", type="primary", use_container_width=True):
                if user_message.strip() or uploaded_file:
                    media_data = base64.b64encode(uploaded_file.getvalue()).decode('utf-8') if uploaded_file else None
                    add_chat_message(st.session_state.username, user_message, media_data)
                    if user_message.startswith("@MathBot"):
                        bot_response = get_mathbot_response(user_message)
                        if bot_response: add_chat_message("MathBot", bot_response)
                    st.rerun()
        st.markdown('</div></div>', unsafe_allow_html=True)

        html('<script>setTimeout(() => { const chatBox = document.getElementById("chat-messages"); if (chatBox) chatBox.scrollTop = chatBox.scrollHeight; }, 200);</script>', height=0)

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
            st.markdown("- **Union (A ∪ B):** All elements from both sets.\n- **Intersection (A ∩ B):** Elements common to both sets.")
            st.markdown("**Example:** If A = {1, 2} and B = {2, 3}, then A ∩ B = {2}.")
        elif resource_topic == "surds":
            st.subheader("√ Surds")
            st.markdown("A **surd** is an irrational number expressed with a root symbol, like $ \sqrt{2} $. We can simplify them: $ \sqrt{12} = \sqrt{4 \cdot 3} = \sqrt{4} \cdot \sqrt{3} = 2\sqrt{3} $.")
        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("</div>", unsafe_allow_html=True)

# --- Main App Logic ---
if __name__ == "__main__":
    if "show_splash" not in st.session_state:
        st.session_state.show_splash = True

    if st.session_state.show_splash:
        st.markdown("""
        <style>.main {visibility: hidden;} .splash-container { position: fixed; top: 0; left: 0; width: 100vw; height: 100vh; background-color: #fff; display: flex; justify-content: center; align-items: center; z-index: 9999; } .splash-text { font-size: 50px; font-weight: bold; color: #2E86C1; }</style>
        <div class="splash-container"><div class="splash-text">MathFriend</div></div>
        """, unsafe_allow_html=True)
        time.sleep(1)
        st.session_state.show_splash = False
        st.rerun()
    else:
        st.markdown("<style>.main {visibility: visible;}</style>", unsafe_allow_html=True)
        manage_session_state()
        
        if st.session_state.logged_in:
            show_main_app()
        else:
            show_login_page()

