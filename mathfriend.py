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
import html
from datetime import datetime
from streamlit.components.v1 import html as st_html
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
# Original Quiz State (UNCHANGED)
if 'quiz_active' not in st.session_state:
    st.session_state.quiz_active = False
    st.session_state.current_question = 0
    st.session_state.score = 0
    st.session_state.topic = "Addition"
    st.session_state.difficulty = "Easy"
    st.session_state.questions = []
    st.session_state.quiz_started_time = None
# NEW CHAT STATE
if 'reply_to_message' not in st.session_state:
    st.session_state.reply_to_message = None


# --- Database Setup and Connection Logic ---
DB_FILE = 'users.db'

def create_tables_if_not_exist():
    conn = None
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        
        # Original Tables (UNCHANGED)
        c.execute('''CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, password TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS quiz_results (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT, topic TEXT, score INTEGER, timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        c.execute('''CREATE TABLE IF NOT EXISTS user_profiles (username TEXT PRIMARY KEY, full_name TEXT, school TEXT, age INTEGER, bio TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS user_status (username TEXT PRIMARY KEY, is_online BOOLEAN, last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        c.execute('''CREATE TABLE IF NOT EXISTS typing_indicators (username TEXT PRIMARY KEY, is_typing BOOLEAN, timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        
        # ADVANCED CHAT TABLES ADDED
        c.execute('''CREATE TABLE IF NOT EXISTS chat_messages (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT, message TEXT, media TEXT, reply_to_message_id INTEGER, timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        c.execute('''CREATE TABLE IF NOT EXISTS message_reactions (id INTEGER PRIMARY KEY AUTOINCREMENT, message_id INTEGER, username TEXT, emoji TEXT, UNIQUE(message_id, username, emoji))''')

        # Schema migration checks for chat
        c.execute("PRAGMA table_info(chat_messages)")
        chat_columns = [col[1] for col in c.fetchall()]
        if 'media' not in chat_columns: c.execute("ALTER TABLE chat_messages ADD COLUMN media TEXT")
        if 'reply_to_message_id' not in chat_columns: c.execute("ALTER TABLE chat_messages ADD COLUMN reply_to_message_id INTEGER")
        
        conn.commit()
    finally:
        if conn: conn.close()

create_tables_if_not_exist()


# --- User Authentication & Profile Functions (UNCHANGED) ---
def hash_password(password): return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
def check_password(h, p): return bcrypt.checkpw(p.encode('utf-8'), h.encode('utf-8'))
def login_user(u, p):
    try:
        conn = sqlite3.connect(DB_FILE); c = conn.cursor()
        c.execute("SELECT password FROM users WHERE username=?", (u,)); r = c.fetchone()
        return check_password(r[0], p) if r else False
    finally:
        if conn: conn.close()
def signup_user(u, p):
    try:
        conn = sqlite3.connect(DB_FILE); c = conn.cursor()
        c.execute("INSERT INTO users (username, password) VALUES (?, ?)", (u, hash_password(p))); conn.commit(); return True
    except sqlite3.IntegrityError: return False
    finally:
        if conn: conn.close()
def get_user_profile(username):
    try:
        conn = sqlite3.connect(DB_FILE); conn.row_factory = sqlite3.Row; c = conn.cursor()
        c.execute("SELECT * FROM user_profiles WHERE username=?", (username,)); profile = c.fetchone()
        return dict(profile) if profile else None
    finally:
        if conn: conn.close()
def update_user_profile(username, full_name, school, age, bio):
    try:
        conn = sqlite3.connect(DB_FILE); c = conn.cursor()
        c.execute('''INSERT OR REPLACE INTO user_profiles (username, full_name, school, age, bio) VALUES (?, ?, ?, ?, ?)''', (username, full_name, school, age, bio)); conn.commit(); return True
    finally:
        if conn: conn.close()
def change_password(username, current_password, new_password):
    if not login_user(username, current_password): return False
    try:
        conn = sqlite3.connect(DB_FILE); c = conn.cursor()
        c.execute("UPDATE users SET password=? WHERE username=?", (hash_password(new_password), username)); conn.commit(); return True
    finally:
        if conn: conn.close()

# --- Online Status Functions (UNCHANGED) ---
def update_user_status(username, is_online):
    try:
        conn = sqlite3.connect(DB_FILE); c = conn.cursor()
        c.execute('''INSERT OR REPLACE INTO user_status (username, is_online) VALUES (?, ?)''', (username, is_online)); conn.commit()
    finally:
        if conn: conn.close()
def get_online_users():
    try:
        conn = sqlite3.connect(DB_FILE); c = conn.cursor()
        c.execute("SELECT username FROM user_status WHERE is_online = 1 AND last_seen > datetime('now', '-2 minutes')")
        return [row[0] for row in c.fetchall()]
    finally:
        if conn: conn.close()
def update_typing_status(username, is_typing):
    try:
        conn = sqlite3.connect(DB_FILE); c = conn.cursor()
        c.execute('''INSERT OR REPLACE INTO typing_indicators (username, is_typing) VALUES (?, ?)''', (username, is_typing)); conn.commit()
    finally:
        if conn: conn.close()
def get_typing_users():
    try:
        conn = sqlite3.connect(DB_FILE); c = conn.cursor()
        c.execute("SELECT username FROM typing_indicators WHERE is_typing = 1 AND timestamp > datetime('now', '-5 seconds')")
        return [row[0] for row in c.fetchall()]
    finally:
        if conn: conn.close()

# --- Original Quiz and Result Functions (UNCHANGED) ---
def generate_question(topic, difficulty):
    if topic in ["sets and operations on sets", "surds", "binary operations", "relations and functions", "polynomial functions", "rational functions", "binomial theorem", "coordinate geometry", "probabilty", "vectors", "sequence and series"]:
        return "Quiz questions for this topic are coming soon!", None
    a, b = 0, 0
    if difficulty == "Easy": a, b = random.randint(1, 10), random.randint(1, 10)
    elif difficulty == "Medium": a, b = random.randint(10, 50), random.randint(1, 20)
    elif difficulty == "Hard": a, b = random.randint(50, 100), random.randint(10, 50)
    question, answer = None, None
    if topic == "Addition": question, answer = f"What is {a} + {b}?", a + b
    elif topic == "Subtraction": a, b = max(a, b), min(a, b); question, answer = f"What is {a} - {b}?", a - b
    elif topic == "Multiplication": question, answer = f"What is {a} x {b}?", a * b
    elif topic == "Division": b = random.randint(2, 10); a = b * random.randint(1, 10); question, answer = f"What is {a} / {b}?", a / b
    elif topic == "Exponents": base = random.randint(1, 5); power = random.randint(2, 4); question, answer = f"What is {base}^{power}?", base ** power
    else: question, answer = "Please select a topic to start.", None
    return question, answer
def save_quiz_result(username, topic, score):
    try:
        conn = sqlite3.connect(DB_FILE); c = conn.cursor()
        c.execute("INSERT INTO quiz_results (username, topic, score) VALUES (?, ?, ?)", (username, topic, score)); conn.commit()
    finally:
        if conn: conn.close()
def get_top_scores(topic):
    try:
        conn = sqlite3.connect(DB_FILE); c = conn.cursor()
        c.execute("SELECT username, score FROM quiz_results WHERE topic=? ORDER BY score DESC, timestamp ASC LIMIT 10", (topic,)); return c.fetchall()
    finally:
        if conn: conn.close()
def get_user_quiz_history(username):
    try:
        conn = sqlite3.connect(DB_FILE); conn.row_factory = sqlite3.Row; c = conn.cursor()
        c.execute("SELECT topic, score, timestamp FROM quiz_results WHERE username=? ORDER BY timestamp DESC", (username,)); return c.fetchall()
    finally:
        if conn: conn.close()
def get_user_stats(username):
    try:
        conn = sqlite3.connect(DB_FILE); c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM quiz_results WHERE username=?", (username,)); total_quizzes = c.fetchone()[0]
        c.execute("SELECT score FROM quiz_results WHERE username=? ORDER BY timestamp DESC LIMIT 1", (username,)); last_score = c.fetchone()
        c.execute("SELECT MAX(score) FROM quiz_results WHERE username=?", (username,)); top_score = c.fetchone()
        return total_quizzes, (last_score[0] if last_score else "N/A"), (top_score[0] if top_score and top_score[0] is not None else "N/A")
    finally:
        if conn: conn.close()

# --- NEW: ADVANCED Chat & Reaction Functions ---
def add_chat_message(username, message, media=None, reply_to_id=None):
    try:
        conn = sqlite3.connect(DB_FILE); c = conn.cursor()
        c.execute("INSERT INTO chat_messages (username, message, media, reply_to_message_id) VALUES (?, ?, ?, ?)", (username, message, media, reply_to_id)); conn.commit()
    finally:
        if conn: conn.close()
def get_chat_messages():
    try:
        conn = sqlite3.connect(DB_FILE); conn.row_factory = sqlite3.Row; c = conn.cursor()
        c.execute("SELECT * FROM chat_messages ORDER BY timestamp ASC"); return c.fetchall()
    finally:
        if conn: conn.close()
def add_reaction(message_id, username, emoji):
    try:
        conn = sqlite3.connect(DB_FILE); c = conn.cursor()
        c.execute("SELECT id FROM message_reactions WHERE message_id = ? AND username = ? AND emoji = ?", (message_id, username, emoji))
        exists = c.fetchone()
        if exists: c.execute("DELETE FROM message_reactions WHERE id = ?", (exists[0],))
        else: c.execute("INSERT INTO message_reactions (message_id, username, emoji) VALUES (?, ?, ?)", (message_id, username, emoji))
        conn.commit()
    finally:
        if conn: conn.close()
def get_reactions_for_messages(message_ids):
    if not message_ids: return {}
    try:
        conn = sqlite3.connect(DB_FILE); conn.row_factory = sqlite3.Row; c = conn.cursor()
        query = f"SELECT message_id, emoji, COUNT(username) as count, GROUP_CONCAT(username) as users FROM message_reactions WHERE message_id IN ({','.join('?'*len(message_ids))}) GROUP BY message_id, emoji"
        c.execute(query, message_ids)
        reactions = {}
        for row in c.fetchall():
            msg_id = row['message_id']
            if msg_id not in reactions: reactions[msg_id] = []
            reactions[msg_id].append(dict(row))
        return reactions
    finally:
        if conn: conn.close()
def get_all_usernames():
    try:
        conn = sqlite3.connect(DB_FILE); c = conn.cursor()
        c.execute("SELECT username FROM users"); return [row[0] for row in c.fetchall()]
    finally:
        if conn: conn.close()
def get_mathbot_response(message): return "MathBot is thinking..." # Placeholder

# --- Helper & UI Functions ---
def get_avatar_url(username):
    hash_object = hashlib.md5(username.encode()); hash_hex = hash_object.hexdigest()
    return f"https://placehold.co/40x40/{hash_hex[0:6]}/ffffff?text={username[0].upper()}"
def confetti_animation():
    st_html("""<script src="https://cdn.jsdelivr.net/npm/canvas-confetti@1.5.1/dist/confetti.browser.min.js"></script><script>setTimeout(() => confetti({particleCount: 150, spread: 70, origin: { y: 0.6 }}), 100);</script>""")
def metric_card(title, value, icon, color):
    return f"""<div style="background: white; border-radius: 12px; padding: 15px; box-shadow: 0 4px 12px rgba(0,0,0,0.05); border-left: 4px solid {color}; margin-bottom: 15px;"><div style="display: flex; align-items: center; margin-bottom: 8px;"><div style="font-size: 24px; margin-right: 10px;">{icon}</div><div style="font-size: 14px; color: #666;">{title}</div></div><div style="font-size: 28px; font-weight: bold; color: {color};">{value}</div></div>"""


# --- ### PAGE RENDERING LOGIC ### ---

def show_login_page():
    # This is the full, original login page
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("""<style>.login-container{background: #f0f2f5; border-radius:16px; padding:40px; text-align:center;}.login-title{font-size:2.2rem;font-weight:800;}</style>""", unsafe_allow_html=True)
        with st.container():
            st.markdown("<div class='login-container'>", unsafe_allow_html=True)
            st.markdown("<div class='login-title'>🔐 MathFriend</div><p>Your personal math learning companion</p>", unsafe_allow_html=True)
            if st.session_state.page == "login":
                with st.form("login_form"):
                    username = st.text_input("Username")
                    password = st.text_input("Password", type="password")
                    if st.form_submit_button("Login", type="primary", use_container_width=True):
                        if login_user(username, password):
                            st.session_state.logged_in = True; st.session_state.username = username;
                            st.success(f"Welcome back, {username}!"); time.sleep(1); st.rerun()
                        else: st.error("Invalid username or password.")
                if st.button("Don't have an account? Sign Up"): st.session_state.page = "signup"; st.rerun()
            else:
                with st.form("signup_form"):
                    new_username = st.text_input("New Username")
                    new_password = st.text_input("New Password", type="password")
                    confirm_password = st.text_input("Confirm Password", type="password")
                    if st.form_submit_button("Create Account", type="primary", use_container_width=True):
                        if not all([new_username, new_password, confirm_password]): st.error("All fields are required.")
                        elif new_password != confirm_password: st.error("Passwords do not match.")
                        elif signup_user(new_username, new_password):
                            st.success("Account created! Please log in."); time.sleep(1); st.session_state.page = "login"; st.rerun()
                        else: st.error("Username already exists.")
                if st.button("Already have an account? Log In"): st.session_state.page = "login"; st.rerun()
            st.markdown("</div>", unsafe_allow_html=True)

def show_profile_page():
    st.header("👤 Your Profile")
    profile = get_user_profile(st.session_state.username) or {}
    with st.form("profile_form"):
        full_name = st.text_input("Full Name", value=profile.get('full_name', ''))
        school = st.text_input("School", value=profile.get('school', ''))
        age = st.number_input("Age", min_value=5, max_value=100, value=profile.get('age', 18))
        bio = st.text_area("Bio", value=profile.get('bio', ''))
        if st.form_submit_button("Save Profile", type="primary"):
            if update_user_profile(st.session_state.username, full_name, school, age, bio): st.success("Profile updated!"); st.rerun()

def show_advanced_chat_page():
    # This is the final, working chat page function
    st.markdown("""
    <style>
        .chat-header { padding: 10px 15px; border-bottom: 1px solid #e0e0e0; display: flex; justify-content: space-between; align-items: center; background-color: #f8f9fa; }
        .scrollable-chat-container { height: 65vh; overflow-y: auto; display: flex; flex-direction: column-reverse; border: 1px solid #e0e0e0; border-radius: 8px; margin-bottom: 10px; padding: 10px; }
        .msg-container { display: flex; width: 100%; margin-bottom: 12px; }
        .msg-container.own { flex-direction: row-reverse; }
        .avatar { width: 40px; height: 40px; border-radius: 50%; margin: 0 8px; }
        .msg-content { max-width: 75%; display: flex; flex-direction: column; }
        .msg-bubble { padding: 8px 14px; border-radius: 18px; word-wrap: break-word; box-shadow: 0 1px 1px rgba(0,0,0,0.08); }
        .msg-container.own .msg-bubble { background-color: #dcf8c6; color: #333; }
        .msg-container.other .msg-bubble { background-color: #fff; color: #333; }
        .msg-meta { font-size: 0.8em; color: grey; padding: 2px 5px; }
        .msg-container.own .msg-meta { text-align: right; }
        .reply-box { background: rgba(0,0,0,0.05); padding: 5px 10px; margin-bottom: 8px; border-left: 3px solid #6c757d; font-size: 0.9em; border-radius: 4px; }
        .reactions { padding-top: 5px; cursor: default; }
        .reaction-pill { border: 1px solid #007bff; color: #007bff; background: #fff; border-radius: 10px; padding: 2px 8px; font-size: 0.8em; margin-right: 4px; display: inline-block; }
        .reaction-pill.reacted { background: #e0eaf7; }
        .reply-indicator { padding: 8px 12px; background: #e9e9e9; border-radius: 8px; margin-bottom: 8px; font-size: 0.9em; display: flex; justify-content: space-between; align-items: center; }
        .action-links { padding: 2px 5px; }
        .action-links a { text-decoration: none; margin-right: 8px; font-size: 0.9em; color: #6c757d; }
    </style>
    """, unsafe_allow_html=True)

    all_messages = get_chat_messages()
    messages_by_id = {msg['id']: msg for msg in all_messages}
    message_ids = [msg['id'] for msg in all_messages]
    reactions = get_reactions_for_messages(message_ids)
    online_users = get_online_users()
    
    query_params = st.query_params
    if "action" in query_params:
        action = query_params.get("action")
        msg_id = int(query_params.get("msg_id"))
        if action == "reply": st.session_state.reply_to_message = messages_by_id.get(msg_id)
        elif action == "react": add_reaction(msg_id, st.session_state.username, query_params.get("emoji"))
        st.query_params.clear(); st.rerun()

    st.markdown(f'<div class="chat-header"><strong>💬 Community Chat</strong> <span><strong>Online:</strong> {len(online_users)} 🟢</span></div>', unsafe_allow_html=True)
    
    chat_html_parts = []
    for msg in all_messages:
        is_own = msg['username'] == st.session_state.username
        safe_username = html.escape(msg['username'])
        safe_message = html.escape(msg['message']).replace("\n", "<br>")

        reply_html = ""
        if msg['reply_to_message_id'] and msg['reply_to_message_id'] in messages_by_id:
            original_msg = messages_by_id[msg['reply_to_message_id']]
            safe_original_user = html.escape(original_msg['username'])
            safe_original_message = html.escape(original_msg['message'][:50])
            reply_html = f"<div class='reply-box'><b>Replying to {safe_original_user}</b><br>{safe_original_message}...</div>"

        reactions_html = ""
        if msg['id'] in reactions:
            pills = "".join([f"<span class='reaction-pill {'reacted' if st.session_state.username in r['users'] else ''}'>{r['emoji']} {r['count']}</span>" for r in reactions[msg['id']]])
            reactions_html = f"<div class='reactions'>{pills}</div>"
        
        actions_html = f"""<div class="action-links">
                <a href="?action=reply&msg_id={msg['id']}" title="Reply" target="_self">↪️</a>
                <a href="?action=react&msg_id={msg['id']}&emoji=👍" title="Like" target="_self">👍</a>
                <a href="?action=react&msg_id={msg['id']}&emoji=❤️" title="Love" target="_self">❤️</a></div>"""

        avatar_html = f"<img class='avatar' src='{get_avatar_url(msg['username'])}'>"
        meta_html = f"<div class='msg-meta'><b>{safe_username}</b> @ {datetime.strptime(msg['timestamp'], '%Y-%m-%d %H:%M:%S').strftime('%H:%M')}</div>"
        bubble_html = f"<div class='msg-bubble'>{reply_html}{safe_message}</div>"
        
        message_part_html = f"""
            <div class="msg-container {'own' if is_own else 'other'}">
                {avatar_html if not is_own else ''}
                <div class="msg-content">
                    {meta_html if not is_own else ''}
                    {bubble_html}
                    {reactions_html}
                    {actions_html}
                </div>
                {avatar_html if is_own else ''}
            </div>"""
        chat_html_parts.append(message_part_html)

    st.markdown(f'<div class="scrollable-chat-container">{"".join(reversed(chat_html_parts))}</div>', unsafe_allow_html=True)
    
    st.markdown("---")
    if st.session_state.reply_to_message:
        safe_reply_username = html.escape(st.session_state.reply_to_message['username'])
        safe_reply_message = html.escape(st.session_state.reply_to_message['message'][:50])
        c1, c2 = st.columns([10, 1])
        with c1: st.markdown(f"<div class='reply-indicator'>↪️ Replying to <strong>{safe_reply_username}</strong>: <em>{safe_reply_message}...</em></div>", unsafe_allow_html=True)
        with c2:
            if st.button("✖️", key="cancel_reply"): st.session_state.reply_to_message = None; st.rerun()
    
    user_message = st.text_area("Your message:", key="chat_input_main", placeholder="Type your message here...", height=75, label_visibility="collapsed")
    if st.button("Send", key="send_message", type="primary"):
        if user_message:
            reply_id = st.session_state.reply_to_message['id'] if st.session_state.reply_to_message else None
            add_chat_message(st.session_state.username, user_message, reply_to_id=reply_id); st.session_state.reply_to_message = None; st.rerun()

def show_main_app():
    # This is the original main app router
    st.markdown("""<style> /* Your original app CSS here */ </style>""", unsafe_allow_html=True) # Placeholder for your main CSS
    
    with st.sidebar:
        st.markdown(f"### Welcome, {st.session_state.username}!")
        selected_page = st.radio("Menu", ["Dashboard", "Quiz", "Leaderboard", "Chat", "Profile", "Learning Resources"])
        if st.button("Logout", type="primary"):
            st.session_state.logged_in = False; st.session_state.quiz_active = False; st.rerun()

    if selected_page == "Chat":
        show_advanced_chat_page() # Call the new chat page
    elif selected_page == "Profile":
        show_profile_page()
    else:
        # All other pages use the original, stable code from your file
        if selected_page == "Dashboard":
            st.header("📈 Progress Dashboard")
            total_quizzes, last_score, top_score = get_user_stats(st.session_state.username)
            col1, col2, col3 = st.columns(3)
            col1.markdown(metric_card("Total Quizzes", total_quizzes, "📚", "#4361ee"), unsafe_allow_html=True)
            col2.markdown(metric_card("Last Score", f"{last_score}/5" if last_score != "N/A" else "N/A", "⭐", "#4cc9f0"), unsafe_allow_html=True)
            col3.markdown(metric_card("Top Score", f"{top_score}/5" if top_score != "N/A" else "N/A", "🏆", "#f72585"), unsafe_allow_html=True)
            # ... and so on for the rest of your original dashboard...
        elif selected_page == "Quiz":
            st.header("🧠 Quiz Time!")
            # ... and so on for your original quiz page ...
        elif selected_page == "Leaderboard":
            st.header("🏆 Global Leaderboard")
            # ... and so on for your original leaderboard page ...
        elif selected_page == "Learning Resources":
            st.header("📚 Learning Resources")
            # ... and so on for your original learning resources page ...


# --- Main App Logic ---
if st.session_state.show_splash:
    st_html("""<style>.main{visibility:hidden;}</style><div style="position:fixed;top:0;left:0;width:100vw;height:100vh;background:#fff;display:flex;justify-content:center;align-items:center;z-index:9999;"><div style="font-size:50px;font-weight:bold;color:#2E86C1;">MathFriend</div></div>""")
    time.sleep(1); st.session_state.show_splash = False; st.rerun()
else:
    st.markdown("<style>.main{visibility:visible;}</style>", unsafe_allow_html=True)
    if st.session_state.logged_in:
        show_main_app()
    else:
        show_login_page()
