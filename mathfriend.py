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

# --- Streamlit Page Configuration ---
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
# Quiz State
if 'quiz_active' not in st.session_state:
    st.session_state.quiz_active = False
if 'quiz_topic' not in st.session_state:
    st.session_state.quiz_topic = "Sets"
if 'quiz_score' not in st.session_state:
    st.session_state.quiz_score = 0
if 'questions_answered' not in st.session_state:
    st.session_state.questions_answered = 0
# CHAT STATE - For reply functionality
if 'reply_to_message' not in st.session_state:
    st.session_state.reply_to_message = None


# --- Database Setup and Connection Logic ---
DB_FILE = 'users.db'

def create_tables_if_not_exist():
    """
    Ensures all necessary tables and columns exist.
    UPDATED: Added reply_to_message_id to chat_messages and a new message_reactions table.
    """
    conn = None
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        
        # Standard tables
        c.execute('''CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, password TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS quiz_results (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT, topic TEXT, score INTEGER, questions_answered INTEGER, timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        c.execute('''CREATE TABLE IF NOT EXISTS user_profiles (username TEXT PRIMARY KEY, full_name TEXT, school TEXT, age INTEGER, bio TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS user_status (username TEXT PRIMARY KEY, is_online BOOLEAN, last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        c.execute('''CREATE TABLE IF NOT EXISTS typing_indicators (username TEXT PRIMARY KEY, is_typing BOOLEAN, timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        
        # UPDATED CHAT TABLE
        c.execute('''CREATE TABLE IF NOT EXISTS chat_messages (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT, message TEXT, media TEXT, reply_to_message_id INTEGER, timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')

        # NEW REACTION TABLE
        c.execute('''CREATE TABLE IF NOT EXISTS message_reactions (id INTEGER PRIMARY KEY AUTOINCREMENT, message_id INTEGER, username TEXT, emoji TEXT, UNIQUE(message_id, username, emoji))''')

        # Schema migration checks
        c.execute("PRAGMA table_info(chat_messages)")
        chat_columns = [col[1] for col in c.fetchall()]
        if 'media' not in chat_columns: c.execute("ALTER TABLE chat_messages ADD COLUMN media TEXT")
        if 'reply_to_message_id' not in chat_columns: c.execute("ALTER TABLE chat_messages ADD COLUMN reply_to_message_id INTEGER")
        
        c.execute("PRAGMA table_info(quiz_results)")
        quiz_columns = [col[1] for col in c.fetchall()]
        if 'questions_answered' not in quiz_columns: c.execute("ALTER TABLE quiz_results ADD COLUMN questions_answered INTEGER DEFAULT 0")

        conn.commit()
    finally:
        if conn: conn.close()

create_tables_if_not_exist()


# --- All Backend Functions (User Auth, Profile, Quiz, etc.) ---
# User Auth and Profile functions (unchanged)
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
        c.execute("INSERT INTO users VALUES (?, ?)", (u, hash_password(p))); conn.commit(); return True
    except sqlite3.IntegrityError: return False
    finally:
        if conn: conn.close()

# Other functions (get_user_profile, update_user_profile, etc.) are unchanged and collapsed for brevity
def get_user_profile(username): return {} # Placeholder
def update_user_profile(username, full_name, school, age, bio): return True # Placeholder

# Question Generation and Quiz Logic (unchanged from previous version)
def _generate_sets_question():
    set_a = set(random.sample(range(1, 15), k=random.randint(3, 5)))
    set_b = set(random.sample(range(1, 15), k=random.randint(3, 5)))
    op = random.choice(['union', 'intersection', 'difference'])
    q = f"Given $A = {set_a}$ and $B = {set_b}$, what is $A { {'union': '\cup', 'intersection': '\cap', 'difference': '-'}[op] } B$?"
    ans = str(getattr(set_a, op)(set_b))
    dist = [str(set_a.intersection(set_b)), str(set_a.union(set_b)), str(set_a-set_b), str(set_b-set_a)]
    hint = f"The {op} finds elements that are {'in both sets' if op != 'difference' else 'in the first set but not the second'}."
    opts = list(set([ans] + dist)); random.shuffle(opts)
    return {"question": q, "options": opts, "answer": ans, "hint": hint}

def generate_question(topic):
    if topic == "Sets": return _generate_sets_question()
    return {"question": f"Questions for **{topic}** are coming soon!", "options": ["OK"], "answer": "OK", "hint": "Please select another topic."}

# UPDATED CHAT AND REACTION FUNCTIONS
def add_chat_message(username, message, media=None, reply_to_id=None):
    try:
        conn = sqlite3.connect(DB_FILE); c = conn.cursor()
        c.execute("INSERT INTO chat_messages (username, message, media, reply_to_message_id) VALUES (?, ?, ?, ?)", (username, message, media, reply_to_id))
        conn.commit()
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
        c.execute("INSERT OR IGNORE INTO message_reactions (message_id, username, emoji) VALUES (?, ?, ?)", (message_id, username, emoji)); conn.commit()
    finally:
        if conn: conn.close()

def get_reactions_for_messages(message_ids):
    if not message_ids: return {}
    try:
        conn = sqlite3.connect(DB_FILE); c = conn.cursor()
        query = f"SELECT message_id, emoji, COUNT(username) FROM message_reactions WHERE message_id IN ({','.join('?'*len(message_ids))}) GROUP BY message_id, emoji"
        c.execute(query, message_ids)
        reactions = {}
        for msg_id, emoji, count in c.fetchall():
            if msg_id not in reactions: reactions[msg_id] = []
            reactions[msg_id].append({'emoji': emoji, 'count': count})
        return reactions
    finally:
        if conn: conn.close()

# Other helper functions (get_avatar_url, etc.) are unchanged and collapsed for brevity
def get_avatar_url(username):
    hash_object = hashlib.md5(username.encode()); hash_hex = hash_object.hexdigest()
    return f"https://placehold.co/40x40/{hash_hex[0:6]}/ffffff?text={username[0].upper()}"
def get_online_users(): return ["Alice", "Bob"] # Placeholder
def update_typing_status(u, s): pass # Placeholder
def get_typing_users(): return ["Charlie"] # Placeholder
def format_message(m, u, c): return m # Placeholder
def get_mathbot_response(m): return None # Placeholder


# --- ### PAGE RENDERING LOGIC ### ---

# Login/Profile pages are unchanged and collapsed for brevity
def show_login_page(): st.header("Login Page Placeholder")
def show_profile_page(): st.header("Profile Page Placeholder")

def show_main_app():
    # Sidebar is unchanged
    with st.sidebar:
        st.title("MathFriend")
        selected_page = st.radio("Menu", ["Dashboard", "Quiz", "Leaderboard", "Chat", "Profile"])
        if st.button("Logout"): st.session_state.logged_in = False; st.rerun()

    # Page routing
    if selected_page == "Chat":
        show_advanced_chat_page()
    elif selected_page == "Quiz":
        show_quiz_page() # Placeholder for your quiz logic
    else:
        st.header(f"{selected_page} Page Placeholder")

def show_quiz_page():
    st.header("New Quiz System Placeholder")
    # All your new quiz logic would go here

def show_advanced_chat_page():
    # --- NEW ADVANCED CHAT UI ---
    st.markdown("""
    <style>
        .chat-header { padding: 10px; border-bottom: 1px solid #ddd; display: flex; justify-content: space-between; align-items: center; }
        .chat-container { height: 70vh; overflow-y: auto; padding: 10px; display: flex; flex-direction: column-reverse; }
        .msg-wrapper { display: flex; margin-bottom: 5px; }
        .msg-bubble { padding: 8px 12px; border-radius: 18px; max-width: 70%; word-wrap: break-word; box-shadow: 0 1px 1px rgba(0,0,0,0.1); }
        .msg-own { justify-content: flex-end; }
        .msg-own .msg-bubble { background-color: #dcf8c6; border-bottom-right-radius: 4px; color: #222; }
        .msg-other .msg-bubble { background-color: #fff; border-bottom-left-radius: 4px; color: #222; }
        .avatar { width: 40px; height: 40px; border-radius: 50%; margin: 0 8px; }
        .reply-box { background: #f0f0f0; padding: 5px 10px; margin-bottom: 5px; border-left: 2px solid #007bff; font-size: 0.9em; border-radius: 4px; }
        .reactions { padding-top: 4px; }
        .reaction-pill { background: #e0eaf7; border-radius: 10px; padding: 2px 8px; font-size: 0.8em; margin-right: 4px; display: inline-block; }
        .action-buttons { visibility: hidden; }
        .msg-wrapper:hover .action-buttons { visibility: visible; }
        .action-buttons button { background: none; border: none; cursor: pointer; font-size: 1.1em; color: #888; }
        .input-bar { display: flex; padding: 10px; border-top: 1px solid #ddd; align-items: center; }
        .reply-indicator { padding: 5px 10px; background: #e9e9e9; border-radius: 10px; margin-bottom: 5px; font-size: 0.9em; }
    </style>
    """, unsafe_allow_html=True)
    
    # --- DATA FETCHING ---
    all_messages = get_chat_messages()
    messages_by_id = {msg['id']: msg for msg in all_messages}
    message_ids = [msg['id'] for msg in all_messages]
    reactions = get_reactions_for_messages(message_ids)
    online_users = get_online_users()
    typing_users = [u for u in get_typing_users() if u != st.session_state.username]

    # --- HEADER ---
    with st.container():
        st.markdown(f'<div class="chat-header"><strong>💬 Community Chat</strong> <span><strong>Online:</strong> {len(online_users)} 🟢</span></div>', unsafe_allow_html=True)

    # --- MESSAGE DISPLAY ---
    with st.container():
        st.markdown('<div class="chat-container">', unsafe_allow_html=True)
        # We iterate in reverse to display from bottom-up due to `flex-direction: column-reverse`
        for msg in reversed(all_messages):
            is_own = msg['username'] == st.session_state.username
            
            # Reply box logic
            reply_html = ""
            if msg['reply_to_message_id'] and msg['reply_to_message_id'] in messages_by_id:
                original_msg = messages_by_id[msg['reply_to_message_id']]
                reply_html = f"<div class='reply-box'><b>Replying to {original_msg['username']}</b><br>{original_msg['message'][:50]}...</div>"

            # Reactions logic
            reactions_html = ""
            if msg['id'] in reactions:
                reactions_html += "<div class='reactions'>"
                for reaction in reactions[msg['id']]:
                    reactions_html += f"<span class='reaction-pill'>{reaction['emoji']} {reaction['count']}</span>"
                reactions_html += "</div>"

            # Action buttons
            reply_button, thumbs_up, heart = st.columns([1,1,1])
            if st.button("↪️", key=f"reply_{msg['id']}", help="Reply"):
                st.session_state.reply_to_message = msg; st.rerun()
            if st.button("👍", key=f"thumb_{msg['id']}", help="Thumbs Up"):
                add_reaction(msg['id'], st.session_state.username, "👍"); st.rerun()
            if st.button("❤️", key=f"heart_{msg['id']}", help="Heart"):
                add_reaction(msg['id'], st.session_state.username, "❤️"); st.rerun()
            
            actions_html = f"<div class='action-buttons'>...</div>" # Placeholder for now

            # Putting it all together
            avatar = f"<img class='avatar' src='{get_avatar_url(msg['username'])}'>"
            bubble = f"""
                <div class='msg-wrapper {'msg-own' if is_own else 'msg-other'}'>
                    {'' if is_own else avatar}
                    <div>
                        <div class='msg-bubble'>
                            {reply_html}
                            {msg['message']}
                        </div>
                        {reactions_html}
                    </div>
                    {avatar if is_own else ''}
                </div>
            """
            st.markdown(bubble, unsafe_allow_html=True)

        st.markdown('</div>', unsafe_allow_html=True)

    # --- REPLY INDICATOR AND INPUT BAR ---
    st.markdown("---")
    if st.session_state.reply_to_message:
        c1, c2 = st.columns([10, 1])
        with c1:
            st.markdown(f"<div class='reply-indicator'>↪️ Replying to <strong>{st.session_state.reply_to_message['username']}</strong></div>", unsafe_allow_html=True)
        with c2:
            if st.button("✖️", key="cancel_reply"):
                st.session_state.reply_to_message = None; st.rerun()

    if typing_users:
        st.caption(f"{', '.join(typing_users)} is typing...")

    with st.form("chat_form", clear_on_submit=True):
        user_message = st.text_area("", key="chat_input", height=70, placeholder="Type a message...")
        if st.form_submit_button("Send ➤"):
            reply_id = st.session_state.reply_to_message['id'] if st.session_state.reply_to_message else None
            add_chat_message(st.session_state.username, user_message, reply_to_id=reply_id)
            st.session_state.reply_to_message = None # Clear reply state after sending
            st.rerun()

# --- Main App Logic ---
if "show_splash" not in st.session_state or st.session_state.show_splash:
    # Splash screen logic
    st.markdown("Splash Screen")
    time.sleep(1); st.session_state.show_splash = False; st.rerun()
else:
    if "logged_in" not in st.session_state or not st.session_state.logged_in:
        show_login_page()
    else:
        show_main_app()
