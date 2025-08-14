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
import html  # Python's standard HTML library for escaping
from streamlit.components.v1 import html as st_html  # Streamlit's HTML rendering function
from streamlit_autorefresh import st_autorefresh

# Streamlit-specific configuration
st.set_page_config(
    layout="wide",
    page_title="MathFriend",
    page_icon="🧮",
    initial_sidebar_state="expanded"
)

# --- Session State Initialization ---
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "page" not in st.session_state:
    st.session_state.page = "login"
if "username" not in st.session_state:
    st.session_state.username = ""
if "show_splash" not in st.session_state:
    st.session_state.show_splash = True
if "dark_mode" not in st.session_state:
    st.session_state.dark_mode = False
if 'quiz_active' not in st.session_state:
    st.session_state.quiz_active = False
if 'quiz_topic' not in st.session_state:
    st.session_state.quiz_topic = "Sets"
if 'quiz_score' not in st.session_state:
    st.session_state.quiz_score = 0
if 'questions_answered' not in st.session_state:
    st.session_state.questions_answered = 0


# --- Database Setup and Connection Logic ---
DB_FILE = 'users.db'

def create_tables_if_not_exist():
    """Ensures all necessary tables and columns exist in the database."""
    conn = None
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        
        c.execute('''CREATE TABLE IF NOT EXISTS users
                     (username TEXT PRIMARY KEY, password TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS quiz_results
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      username TEXT,
                      topic TEXT,
                      score INTEGER,
                      questions_answered INTEGER,
                      timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        c.execute('''CREATE TABLE IF NOT EXISTS chat_messages
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      username TEXT,
                      message TEXT,
                      media TEXT,
                      timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        c.execute('''CREATE TABLE IF NOT EXISTS user_profiles
                     (username TEXT PRIMARY KEY,
                      full_name TEXT,
                      school TEXT,
                      age INTEGER,
                      bio TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS user_status
                     (username TEXT PRIMARY KEY, 
                      is_online BOOLEAN,
                      last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        c.execute('''CREATE TABLE IF NOT EXISTS typing_indicators
                     (username TEXT PRIMARY KEY,
                      is_typing BOOLEAN,
                      timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')

        # Check for and add 'media' column in chat_messages if missing
        c.execute("PRAGMA table_info(chat_messages)")
        chat_columns = [column[1] for column in c.fetchall()]
        if 'media' not in chat_columns:
            c.execute("ALTER TABLE chat_messages ADD COLUMN media TEXT")

        # Check for and add 'questions_answered' column in quiz_results if missing
        c.execute("PRAGMA table_info(quiz_results)")
        quiz_columns = [column[1] for column in c.fetchall()]
        if 'questions_answered' not in quiz_columns:
            c.execute("ALTER TABLE quiz_results ADD COLUMN questions_answered INTEGER DEFAULT 0")

        conn.commit()
    except sqlite3.Error as e:
        st.error(f"Database setup error: {e}")
    finally:
        if conn:
            conn.close()

create_tables_if_not_exist()


# --- User Authentication & Profile Functions ---
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
        return check_password(result[0], password) if result else False
    finally:
        if conn: conn.close()

def signup_user(username, password):
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, hash_password(password)))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        if conn: conn.close()

def get_user_profile(username):
    try:
        conn = sqlite3.connect(DB_FILE)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT * FROM user_profiles WHERE username=?", (username,))
        profile = c.fetchone()
        return dict(profile) if profile else None
    finally:
        if conn: conn.close()

def update_user_profile(username, full_name, school, age, bio):
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute('''INSERT OR REPLACE INTO user_profiles (username, full_name, school, age, bio) VALUES (?, ?, ?, ?, ?)''', (username, full_name, school, age, bio))
        conn.commit()
        return True
    finally:
        if conn: conn.close()

def change_password(username, current_password, new_password):
    if not login_user(username, current_password):
        return False
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("UPDATE users SET password=? WHERE username=?", (hash_password(new_password), username))
        conn.commit()
        return True
    finally:
        if conn: conn.close()

# --- Online Status & Typing Functions ---
def update_user_status(username, is_online):
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("INSERT OR REPLACE INTO user_status (username, is_online, last_seen) VALUES (?, ?, CURRENT_TIMESTAMP)", (username, is_online))
        conn.commit()
    finally:
        if conn: conn.close()

def get_online_users():
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT username FROM user_status WHERE is_online = 1 AND last_seen > datetime('now', '-2 minutes')")
        return [row[0] for row in c.fetchall()]
    finally:
        if conn: conn.close()
        
def update_typing_status(username, is_typing):
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("INSERT OR REPLACE INTO typing_indicators (username, is_typing, timestamp) VALUES (?, ?, CURRENT_TIMESTAMP)", (username, is_typing))
        conn.commit()
    finally:
        if conn: conn.close()

def get_typing_users():
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT username FROM typing_indicators WHERE is_typing = 1 AND timestamp > datetime('now', '-5 seconds')")
        return [row[0] for row in c.fetchall() if row[0] != st.session_state.username]
    finally:
        if conn: conn.close()

# --- Question Generation Logic ---
def _generate_sets_question():
    set_a = set(random.sample(range(1, 15), k=random.randint(3, 5)))
    set_b = set(random.sample(range(1, 15), k=random.randint(3, 5)))
    operation = random.choice(['union', 'intersection', 'difference'])
    question_text = f"Given Set $A = {set_a}$ and Set $B = {set_b}$"
    
    if operation == 'union':
        question_text += ", what is $A \cup B$?"
        correct_answer = str(set_a.union(set_b))
        distractors = [str(set_a.intersection(set_b)), str(set_a.difference(set_b)), str(set_a)]
        hint = "The union (∪) combines all unique elements from both sets."
    elif operation == 'intersection':
        question_text += ", what is $A \cap B$?"
        correct_answer = str(set_a.intersection(set_b))
        distractors = [str(set_a.union(set_b)), str(set_b - set_a), str(set_b)]
        hint = "The intersection (∩) finds only the elements that are common to both sets."
    else:  # Difference
        question_text += ", what is $A - B$?"
        correct_answer = str(set_a.difference(set_b))
        distractors = [str(set_b.difference(set_a)), str(set_a.union(set_b)), str(set_a.intersection(set_b))]
        hint = "The difference (A - B) finds elements that are in A but NOT in B."

    options = list(set([correct_answer] + distractors))
    while len(options) < 4:
        options.append(str(set(random.sample(range(1, 20), k=random.randint(2, 4)))))
    random.shuffle(options)
    
    return {"question": question_text, "options": options, "answer": correct_answer, "hint": hint}

def _generate_percentages_question():
    q_type = random.choice(['percent_of', 'what_percent', 'original_price'])
    if q_type == 'percent_of':
        percent = random.randint(1, 40) * 5
        number = random.randint(1, 50) * 10
        question_text = f"What is {percent}% of {number}?"
        correct_answer_val = (percent / 100) * number
        correct_answer = f"{correct_answer_val}".rstrip('0').rstrip('.')
        hint = "To find the percent of a number, convert the percent to a decimal (divide by 100) and multiply."
    elif q_type == 'what_percent':
        part = random.randint(1, 20)
        whole = random.randint(part + 1, 50)
        question_text = f"What percent of {whole} is {part}?"
        correct_answer_val = (part / whole) * 100
        correct_answer = f"{correct_answer_val:.1f}".rstrip('0').rstrip('.') + "%"
        hint = "To find what percent a part is of a whole, divide the part by the whole and multiply by 100."
    else:  # original_price
        original_price = random.randint(20, 200)
        discount_percent = random.randint(1, 8) * 5
        final_price = original_price * (1 - discount_percent / 100)
        question_text = f"An item is sold for ${final_price:.2f} after a {discount_percent}% discount. What was the original price?"
        correct_answer = f"${original_price:.2f}"
        hint = "Let the original price be 'P'. The final price is P * (1 - discount/100). Solve for P."
        
    options = [correct_answer]
    while len(options) < 4:
        try:
            noise = random.uniform(0.75, 1.25)
            numeric_part_str = re.sub(r'[^\d.]', '', correct_answer)
            if numeric_part_str:
                wrong_answer_val = float(numeric_part_str) * noise
                prefix = "$" if correct_answer.startswith("$") else ""
                suffix = "%" if correct_answer.endswith("%") else ""
                if "." in correct_answer:
                    precision = len(correct_answer.split('.')[1].rstrip('%'))
                    options.append(f"{prefix}{wrong_answer_val:.{precision}f}{suffix}")
                else:
                    options.append(f"{prefix}{int(wrong_answer_val)}{suffix}")
            else:
                options.append(f"{random.randint(1, 100)}")
        except (ValueError, IndexError):
            options.append(f"{random.randint(1, 100)}")
    random.shuffle(options)
    
    return {"question": question_text, "options": list(set(options)), "answer": correct_answer, "hint": hint}

def generate_question(topic):
    if topic == "Sets":
        return _generate_sets_question()
    elif topic == "Percentages":
        return _generate_percentages_question()
    else:
        return {
            "question": f"Questions for **{topic}** are coming soon!",
            "options": ["OK"], "answer": "OK",
            "hint": "Please select another topic to start a quiz."
        }

# --- Quiz and Result Functions ---
def save_quiz_result(username, topic, score, questions_answered):
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("INSERT INTO quiz_results (username, topic, score, questions_answered) VALUES (?, ?, ?, ?)",
                  (username, topic, score, questions_answered))
        conn.commit()
    except sqlite3.Error as e:
        st.error(f"Save quiz result database error: {e}")
    finally:
        if conn: conn.close()

def get_top_scores(topic):
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("""
            SELECT username, score, questions_answered FROM quiz_results 
            WHERE topic=? AND questions_answered > 0
            ORDER BY (CAST(score AS REAL) / questions_answered) DESC, questions_answered DESC, timestamp ASC
            LIMIT 10
        """, (topic,))
        return c.fetchall()
    except sqlite3.Error as e:
        st.error(f"Get top scores database error: {e}")
        return []
    finally:
        if conn: conn.close()

def get_user_quiz_history(username):
    try:
        conn = sqlite3.connect(DB_FILE)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT topic, score, questions_answered, timestamp FROM quiz_results WHERE username=? ORDER BY timestamp DESC", (username,))
        return c.fetchall()
    finally:
        if conn: conn.close()

def get_user_stats(username):
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM quiz_results WHERE username=?", (username,))
        total_quizzes = c.fetchone()[0]
        c.execute("SELECT score, questions_answered FROM quiz_results WHERE username=? ORDER BY timestamp DESC LIMIT 1", (username,))
        last_result = c.fetchone()
        last_score_str = f"{last_result[0]}/{last_result[1]}" if last_result else "N/A"
        c.execute("SELECT score, questions_answered FROM quiz_results WHERE username=? AND questions_answered > 0 ORDER BY (CAST(score AS REAL) / questions_answered) DESC, score DESC LIMIT 1", (username,))
        top_result = c.fetchone()
        top_score_str = f"{top_result[0]}/{top_result[1]}" if top_result else "N/A"
        return total_quizzes, last_score_str, top_score_str
    except sqlite3.Error as e:
        st.error(f"Get user stats error: {e}")
        return 0, "N/A", "N/A"
    finally:
        if conn: conn.close()

# --- Chat, MathBot, and UI Component Functions ---
def add_chat_message(username, message, media=None):
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("INSERT INTO chat_messages (username, message, media) VALUES (?, ?, ?)", (username, message, media))
        conn.commit()
    finally:
        if conn: conn.close()
        
def get_chat_messages():
    try:
        conn = sqlite3.connect(DB_FILE)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT * FROM chat_messages ORDER BY timestamp ASC")
        return c.fetchall()
    finally:
        if conn: conn.close()

def get_all_usernames():
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT username FROM users")
        return [row[0] for row in c.fetchall()]
    finally:
        if conn: conn.close()

def format_message(message, mentioned_usernames, current_user):
    if not message: return ""
    formatted_message = message
    emoji_map = {":smile:": "😊", ":laughing:": "😂", ":thumbsup:": "👍", ":heart:": "❤️"}
    for shortcut, emoji in emoji_map.items():
        formatted_message = formatted_message.replace(shortcut, emoji)
    
    formatted_message = html.escape(formatted_message)
    
    for user in mentioned_usernames:
        if f"@{user}" in message and user == current_user:
            formatted_message = re.sub(r'(?i)@' + re.escape(user), r'<span class="mention-highlight">@\1</span>', formatted_message)
    
    formatted_message = re.sub(r'\*(.*?)\*', r'<em>\1</em>', formatted_message)
    formatted_message = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', formatted_message)
    return formatted_message

def get_mathbot_response(message):
    if not message.startswith("@MathBot"): return None
    query = message.replace("@MathBot", "").strip().lower()
    definitions = {
        "sets": "A set is a collection of distinct objects.",
        "surds": "A surd is an irrational number that can be expressed with a root symbol, like $\sqrt{2}$.",
        "binary operation": "A binary operation is a calculation that combines two elements to produce a new one.",
        "percentages": "A percentage is a number or ratio expressed as a fraction of 100."
    }
    if query.startswith("define"):
        term = query.split("define", 1)[1].strip()
        return f"**MathBot:** {definitions.get(term, 'I do not have a definition for that yet.')}"
    return "**MathBot:** I can help with definitions. Try '@MathBot define sets'."

def get_avatar_url(username):
    hash_object = hashlib.md5(username.encode())
    hash_hex = hash_object.hexdigest()
    first_letter = username[0].upper()
    color_code = hash_hex[0:6]
    return f"https://placehold.co/40x40/{color_code}/ffffff?text={first_letter}"

def confetti_animation():
    st_html("""<script src="https://cdn.jsdelivr.net/npm/canvas-confetti@1.5.1/dist/confetti.browser.min.js"></script><script>setTimeout(() => confetti({particleCount: 150, spread: 70, origin: { y: 0.6 }}), 100);</script>""")

def metric_card(title, value, icon, color):
    return f"""<div style="background: white; border-radius: 12px; padding: 15px; box-shadow: 0 4px 12px rgba(0,0,0,0.05); border-left: 4px solid {color}; margin-bottom: 15px;"><div style="display: flex; align-items: center; margin-bottom: 8px;"><div style="font-size: 24px; margin-right: 10px;">{icon}</div><div style="font-size: 14px; color: #666;">{title}</div></div><div style="font-size: 28px; font-weight: bold; color: {color};">{value}</div></div>"""

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
                if st.form_submit_button("Login", type="primary"):
                    if login_user(username, password):
                        st.session_state.logged_in = True
                        st.session_state.username = username
                        update_user_status(username, True)
                        st.success(f"Welcome back, {username}!")
                        time.sleep(1)
                        st.rerun()
                    else: st.error("Invalid username or password.")
            if st.button("Don't have an account? Sign Up"): st.session_state.page = "signup"; st.rerun()
        else:  # Signup
            with st.form("signup_form"):
                new_username = st.text_input("New Username")
                new_password = st.text_input("New Password", type="password")
                confirm_password = st.text_input("Confirm Password", type="password")
                if st.form_submit_button("Create Account", type="primary"):
                    if not all([new_username, new_password, confirm_password]): st.error("All fields are required.")
                    elif new_password != confirm_password: st.error("Passwords do not match.")
                    elif signup_user(new_username, new_password):
                        st.success("Account created! Please log in."); time.sleep(1)
                        st.session_state.page = "login"; st.rerun()
                    else: st.error("Username already exists.")
            if st.button("Already have an account? Log In"): st.session_state.page = "login"; st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)

def show_profile_page():
    st.header("👤 Your Profile")
    st.markdown("<div class='content-card'>", unsafe_allow_html=True)
    update_user_status(st.session_state.username, True)
    profile = get_user_profile(st.session_state.username) or {}
    with st.form("profile_form"):
        col1, col2 = st.columns(2)
        full_name = col1.text_input("Full Name", value=profile.get('full_name', ''))
        school = col2.text_input("School", value=profile.get('school', ''))
        age = col1.number_input("Age", min_value=5, max_value=100, value=profile.get('age', 18))
        bio = col2.text_area("Bio", value=profile.get('bio', ''))
        if st.form_submit_button("Save Profile", type="primary"):
            if update_user_profile(st.session_state.username, full_name, school, age, bio):
                st.success("Profile updated!"); st.rerun()
    st.markdown("---")
    st.subheader("Change Password")
    with st.form("password_form"):
        current_password = st.text_input("Current Password", type="password")
        new_password = st.text_input("New Password", type="password")
        confirm_password = st.text_input("Confirm New Password", type="password")
        if st.form_submit_button("Change Password", type="primary"):
            if new_password != confirm_password: st.error("New passwords don't match!")
            elif change_password(st.session_state.username, current_password, new_password): st.success("Password changed successfully!")
            else: st.error("Incorrect current password")
    st.markdown("</div>", unsafe_allow_html=True)

def show_main_app():
    st.markdown("""
    <style>
        .content-card { background: white; border-radius: 12px; padding: 25px; box-shadow: 0 4px 12px rgba(0,0,0,0.05); margin-bottom: 20px; }
        .mention-highlight { background-color: #e6f7ff; color: #1890ff; padding: 2px 5px; border-radius: 4px; font-weight: bold; }
        .chat-container { height: 65vh; overflow-y: auto; display: flex; flex-direction: column; gap: 12px; scroll-behavior: smooth; padding: 10px; border: 1px solid #e0e0e0; border-radius: 12px; background-color: #f9f9f9; }
        .message-row { display: flex; align-items: flex-end; gap: 8px; }
        .message-row.own { justify-content: flex-end; }
        .message-row.other { justify-content: flex-start; }
        .chat-avatar { width: 40px; height: 40px; border-radius: 50%; }
        .message-bubble { max-width: 60%; padding: 10px 15px; border-radius: 18px; word-wrap: break-word; }
        .message-row.own .message-bubble { background: linear-gradient(90deg, #667eea 0%, #764ba2 100%); color: white; border-bottom-right-radius: 4px; }
        .message-row.other .message-bubble { background-color: #ffffff; border: 1px solid #e5e5e5; border-bottom-left-radius: 4px; }
        .message-meta { font-size: 0.75rem; color: #888; padding: 0 5px; }
        .chat-image { max-width: 100%; border-radius: 10px; margin-top: 5px; }
        .typing-indicator { font-style: italic; color: #888; font-size: 0.85rem; height: 20px; }
    </style>
    """, unsafe_allow_html=True)
    
    with st.sidebar:
        st.session_state.dark_mode = st.toggle("🌙 Dark Mode", value=st.session_state.dark_mode)
        st.markdown("### **Menu**")
        selected_page = st.sidebar.radio("Go to", ["📊 Dashboard", "📝 Quiz", "🏆 Leaderboard", "💬 Chat", "👤 Profile", "📚 Learning Resources"], label_visibility="collapsed")
        st.markdown("---")
        st.markdown("### **Online Users**")
        online_users = get_online_users()
        if online_users:
            for user in online_users: st.markdown(f"🟢 {user}")
        else: st.write("No other users are online.")
        st.markdown("---")
        st.sidebar.markdown("### **Account**")
        if st.sidebar.button("Logout", type="primary"):
            update_user_status(st.session_state.username, False)
            st.session_state.logged_in = False
            st.session_state.quiz_active = False
            st.rerun()

    update_user_status(st.session_state.username, True)

    if selected_page == "📊 Dashboard":
        st.header("📈 Progress Dashboard")
        total_quizzes, last_score_str, top_score_str = get_user_stats(st.session_state.username)
        col1, col2, col3 = st.columns(3)
        col1.markdown(metric_card("Total Quizzes", total_quizzes, "📚", "#4361ee"), unsafe_allow_html=True)
        col2.markdown(metric_card("Last Score", last_score_str, "⭐", "#4cc9f0"), unsafe_allow_html=True)
        col3.markdown(metric_card("Top Score", top_score_str, "🏆", "#f72585"), unsafe_allow_html=True)
    elif selected_page == "📝 Quiz":
        st.header("🧠 Quiz Time!")
        st.markdown("<div class='content-card'>", unsafe_allow_html=True)
        if not st.session_state.quiz_active:
            st.write("Select a topic and challenge yourself with unlimited questions!")
            topic_options = ["Sets", "Percentages", "Surds", "Binary Operations", "Word Problems", "Fractions"]
            st.session_state.quiz_topic = st.selectbox("Choose a topic:", topic_options)
            if st.button("Start Quiz", type="primary", use_container_width=True):
                st.session_state.quiz_active = True
                st.session_state.quiz_score = 0
                st.session_state.questions_answered = 0
                st.rerun()
        else:
            st.write(f"**Topic: {st.session_state.quiz_topic}** | **Score: {st.session_state.quiz_score} / {st.session_state.questions_answered}**")
            q_data = generate_question(st.session_state.quiz_topic)
            if "coming soon" in q_data["question"]:
                st.info(q_data["question"])
                st.session_state.quiz_active = False
                if st.button("Back to Topic Selection"): st.rerun()
            else:
                st.markdown("---")
                st.markdown(q_data["question"])
                with st.expander("🤔 Need a hint?"): st.info(q_data["hint"])
                with st.form(key=f"quiz_form_{st.session_state.questions_answered}"):
                    st.radio("Select your answer:", options=q_data["options"], index=None, key="user_answer_choice")
                    if st.form_submit_button("Submit Answer", type="primary"):
                        user_choice = st.session_state.user_answer_choice
                        if user_choice:
                            st.session_state.questions_answered += 1
                            if user_choice == q_data["answer"]:
                                st.session_state.quiz_score += 1
                                st.success("Correct! Well done! 🎉")
                                confetti_animation()
                            else:
                                st.error(f"Not quite. The correct answer was: **{q_data['answer']}**")
                                st.warning(random.choice(["Don't give up!", "That was tricky. Try again!", "So close! You'll get the next one."]))
                            time.sleep(1.5)
                            st.rerun()
                        else: st.warning("Please select an answer before submitting.")
            if st.button("Stop Quiz & Save Score"):
                if st.session_state.questions_answered > 0:
                    save_quiz_result(st.session_state.username, st.session_state.quiz_topic, st.session_state.quiz_score, st.session_state.questions_answered)
                    st.info(f"Quiz stopped. Your final score of {st.session_state.quiz_score}/{st.session_state.questions_answered} has been recorded.")
                else: st.info("Quiz stopped. No questions were answered, so no score was recorded.")
                st.session_state.quiz_active = False
                time.sleep(2)
                st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)
    elif selected_page == "🏆 Leaderboard":
        st.header("🏆 Global Leaderboard")
        st.markdown("<div class='content-card'>", unsafe_allow_html=True)
        st.write("See who has the highest accuracy for each topic!")
        topic_options = ["Sets", "Percentages", "Surds", "Binary Operations", "Word Problems", "Fractions"]
        leaderboard_topic = st.selectbox("Select a topic to view:", topic_options)
        top_scores = get_top_scores(leaderboard_topic)
        if top_scores:
            leaderboard_data = [{"Rank": f"#{r}", "Username": u, "Score": f"{s}/{t}", "Accuracy": f"{(s / t) * 100:.1f}%"} for r, (u, s, t) in enumerate(top_scores, 1) if t > 0]
            df = pd.DataFrame(leaderboard_data)
            def highlight_user(row): return ['background-color: #e6f7ff; font-weight: bold;'] * len(row) if row.Username == st.session_state.username else [''] * len(row)
            st.dataframe(df.style.apply(highlight_user, axis=1).hide(axis="index"), use_container_width=True)
        else: st.info(f"No scores have been recorded for **{leaderboard_topic}** yet. Be the first!")
        st.markdown("</div>", unsafe_allow_html=True)
    elif selected_page == "💬 Chat":
        st.header("💬 Community Chat")
        st_autorefresh(interval=3000, key="chat_refresh")
        all_messages = get_chat_messages()
        all_users = get_all_usernames()
        chat_container = st.container()
        with chat_container:
            st.markdown('<div class="chat-container" id="chat-box">', unsafe_allow_html=True)
            for msg in all_messages:
                is_own = msg['username'] == st.session_state.username
                col1, col2 = st.columns([1, 8] if not is_own else [8, 1])
                with (col1 if not is_own else col2):
                    st.image(get_avatar_url(msg['username']), width=40)
                with (col2 if not is_own else col1):
                    row_class = "own" if is_own else "other"
                    st.markdown(f"""
                        <div class="message-row {row_class}">
                            <div class="message-bubble">
                                <strong>{msg['username']}</strong><br>
                                {format_message(msg['message'], all_users, st.session_state.username)}
                                {'<img src="' + msg['media'] + '" class="chat-image">' if msg['media'] else ''}
                            </div>
                        </div>
                        <div class="message-meta {row_class}">
                            {datetime.strptime(msg['timestamp'], '%Y-%m-%d %H:%M:%S').strftime('%I:%M %p')}
                        </div>""", unsafe_allow_html=True)
            st.markdown('</div>', unsafe_allow_html=True)
            st_html("""<script>
                var chatBox = document.getElementById('chat-box');
                if(chatBox){ chatBox.scrollTop = chatBox.scrollHeight; }
            </script>""")
        typing_users = get_typing_users()
        indicator_placeholder = st.empty()
        if typing_users:
            indicator_placeholder.markdown(f"<div class='typing-indicator'>*{', '.join(typing_users)} is typing...*</div>", unsafe_allow_html=True)
        with st.form("chat_form", clear_on_submit=True):
            col1, col2 = st.columns([4, 1])
            user_message = col1.text_area("Your message:", key="chat_input", height=75, placeholder="Type a message... Use @ to mention.", on_change=update_typing_status, args=(st.session_state.username, True))
            uploaded_file = col2.file_uploader("Upload", type=["png", "jpg", "jpeg", "gif"], label_visibility="collapsed")
            if st.form_submit_button("Send"):
                if user_message or uploaded_file:
                    media_b64 = None
                    if uploaded_file:
                        media_b64 = f"data:{uploaded_file.type};base64,{base64.b64encode(uploaded_file.read()).decode()}"
                    bot_response = get_mathbot_response(user_message)
                    add_chat_message(st.session_state.username, user_message, media_b64)
                    if bot_response:
                        time.sleep(0.5)
                        add_chat_message("MathBot", bot_response)
                    update_typing_status(st.session_state.username, False)
                    st.rerun()
    elif selected_page == "👤 Profile":
        show_profile_page()
    elif selected_page == "📚 Learning Resources":
        st.header("📚 Learning Resources")
        st.markdown("<div class='content-card'>", unsafe_allow_html=True)
        st.write("Mini-tutorials and helpful examples to help you study.")
        topic_options = ["Sets", "Percentages", "Surds", "Binary Operations", "Word Problems", "Fractions"]
        resource_topic = st.selectbox("Select a topic to learn about:", topic_options)
        if resource_topic == "Sets":
            st.subheader("🧮 Sets and Operations on Sets")
            st.markdown("""A **set** is a collection of distinct objects. Key operations include:
- **Union ($A \cup B$)**: All elements from both sets combined.
- **Intersection ($A \cap B$)**: Only elements that appear in both sets.
- **Difference ($A - B$)**: Elements in A but not in B.""")
        elif resource_topic == "Percentages":
            st.subheader("➗ Percentages")
            st.markdown("""A **percentage** is a number or ratio expressed as a fraction of 100.
- To find **X% of Y**, calculate $(X/100) * Y$.
- To find what percentage **A is of B**, calculate $(A/B) * 100.""")
        else: st.info(f"Learning resources for **{resource_topic}** are under development.")
        st.markdown("</div>", unsafe_allow_html=True)

# --- Splash Screen and Main App Logic ---
if st.session_state.show_splash:
    st.markdown("""
    <style>.main {visibility: hidden;}</style>
    <div style="position: fixed; top: 0; left: 0; width: 100vw; height: 100vh; background-color: #ffffff; display: flex; justify-content: center; align-items: center; z-index: 9999;">
        <div style="font-size: 50px; font-weight: bold; color: #2E86C1;">MathFriend</div>
    </div>
    """, unsafe_allow_html=True)
    time.sleep(1)
    st.session_state.show_splash = False
    st.rerun()
else:
    st.markdown("<style>.main {visibility: visible;}</style>", unsafe_allow_html=True)
    if st.session_state.logged_in:
        show_main_app()
    else:
        show_login_page()
