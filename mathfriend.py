streamlit as st

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

    conn = None

    try:

        conn = sqlite3.connect(DB_FILE)

        c = conn.cursor()

        

        c.execute('''CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, password TEXT)''')

        c.execute('''CREATE TABLE IF NOT EXISTS quiz_results (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT, topic TEXT, score INTEGER, questions_answered INTEGER, timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')

        c.execute('''CREATE TABLE IF NOT EXISTS user_profiles (username TEXT PRIMARY KEY, full_name TEXT, school TEXT, age INTEGER, bio TEXT)''')

        c.execute('''CREATE TABLE IF NOT EXISTS user_status (username TEXT PRIMARY KEY, is_online BOOLEAN, last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')

        c.execute('''CREATE TABLE IF NOT EXISTS typing_indicators (username TEXT PRIMARY KEY, is_typing BOOLEAN, timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')

        c.execute('''CREATE TABLE IF NOT EXISTS chat_messages (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT, message TEXT, media TEXT, reply_to_message_id INTEGER, timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')

        c.execute('''CREATE TABLE IF NOT EXISTS message_reactions (id INTEGER PRIMARY KEY AUTOINCREMENT, message_id INTEGER, username TEXT, emoji TEXT, UNIQUE(message_id, username, emoji))''')



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





# --- User Authentication & Profile Functions ---

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

        c.execute('''INSERT OR REPLACE INTO user_profiles VALUES (?, ?, ?, ?, ?)''', (username, full_name, school, age, bio)); conn.commit(); return True

    finally:

        if conn: conn.close()

def change_password(username, current_password, new_password):

    if not login_user(username, current_password): return False

    try:

        conn = sqlite3.connect(DB_FILE); c = conn.cursor()

        c.execute("UPDATE users SET password=? WHERE username=?", (hash_password(new_password), username)); conn.commit(); return True

    finally:

        if conn: conn.close()



# --- Online Status Functions ---

def update_user_status(username, is_online):

    try:

        conn = sqlite3.connect(DB_FILE); c = conn.cursor()

        c.execute("INSERT OR REPLACE INTO user_status (username, is_online) VALUES (?, ?)", (username, is_online)); conn.commit()

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

        c.execute("INSERT OR REPLACE INTO typing_indicators (username, is_typing) VALUES (?, ?)", (username, is_typing)); conn.commit()

    finally:

        if conn: conn.close()

def get_typing_users():

    try:

        conn = sqlite3.connect(DB_FILE); c = conn.cursor()

        c.execute("SELECT username FROM typing_indicators WHERE is_typing = 1 AND timestamp > datetime('now', '-5 seconds')")

        return [row[0] for row in c.fetchall()]

    finally:

        if conn: conn.close()



# --- Question Generation & Quiz Logic ---

def _generate_sets_question():

    set_a = set(random.sample(range(1, 15), k=random.randint(3, 5)))

    set_b = set(random.sample(range(1, 15), k=random.randint(3, 5)))

    op = random.choice(['union', 'intersection', 'difference'])

    q = f"Given $A = {set_a}$ and $B = {set_b}$, what is $A { {'union': '\cup', 'intersection': '\cap', 'difference': '-'}[op] } B$?"

    ans = str(getattr(set_a, op)(set_b)) if len(getattr(set_a, op)(set_b)) > 0 else "set()"

    dist = [str(set_a.intersection(set_b)), str(set_a.union(set_b)), str(set_a-set_b), str(set_b-set_a)]

    hint = f"The {op} finds elements that are {'in both sets' if op != 'difference' else 'in the first set but not the second'}."

    opts = list(set([ans] + dist)); random.shuffle(opts)

    return {"question": q, "options": opts, "answer": ans, "hint": hint}

def generate_question(topic):

    if topic == "Sets": return _generate_sets_question()

    return {"question": f"Questions for **{topic}** are coming soon!", "options": ["OK"], "answer": "OK", "hint": "Please select another topic."}

def save_quiz_result(username, topic, score, questions_answered):

    if questions_answered == 0: return

    try:

        conn = sqlite3.connect(DB_FILE); c = conn.cursor()

        c.execute("INSERT INTO quiz_results (username, topic, score, questions_answered) VALUES (?, ?, ?, ?)", (username, topic, score, questions_answered)); conn.commit()

    finally:

        if conn: conn.close()



# --- Leaderboard & Stats Functions ---

def get_top_scores(topic):

    try:

        conn = sqlite3.connect(DB_FILE); c = conn.cursor()

        c.execute("""SELECT username, score, questions_answered FROM quiz_results WHERE topic=? AND questions_answered > 0 ORDER BY (CAST(score AS REAL) / questions_answered) DESC, questions_answered DESC, timestamp ASC LIMIT 10""", (topic,)); return c.fetchall()

    finally:

        if conn: conn.close()

def get_user_quiz_history(username):

    try:

        conn = sqlite3.connect(DB_FILE); conn.row_factory = sqlite3.Row; c = conn.cursor()

        c.execute("SELECT topic, score, questions_answered, timestamp FROM quiz_results WHERE username=? ORDER BY timestamp DESC", (username,)); return c.fetchall()

    finally:

        if conn: conn.close()

def get_user_stats(username):

    try:

        conn = sqlite3.connect(DB_FILE); c = conn.cursor()

        c.execute("SELECT COUNT(*) FROM quiz_results WHERE username=?", (username,)); total_quizzes = c.fetchone()[0]

        c.execute("SELECT score, questions_answered FROM quiz_results WHERE username=? ORDER BY timestamp DESC LIMIT 1", (username,)); last_result = c.fetchone()

        last_score_str = f"{last_result[0]}/{last_result[1]}" if last_result else "N/A"

        c.execute("SELECT score, questions_answered FROM quiz_results WHERE username=? AND questions_answered > 0 ORDER BY (CAST(score AS REAL) / questions_answered) DESC, score DESC LIMIT 1", (username,)); top_result = c.fetchone()

        top_score_str = f"{top_result[0]}/{top_result[1]}" if top_result else "N/A"

        return total_quizzes, last_score_str, top_score_str

    finally:

        if conn: conn.close()



# --- Chat & Reaction Functions ---

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

        # Remove existing reaction from user for this message

        c.execute("DELETE FROM message_reactions WHERE message_id = ? AND username = ? AND emoji = ?", (message_id, username, emoji))

        # Add new reaction

        c.execute("INSERT INTO message_reactions (message_id, username, emoji) VALUES (?, ?, ?)", (message_id, username, emoji)); conn.commit()

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



# --- Helper & UI Functions ---

def get_avatar_url(username):

    hash_object = hashlib.md5(username.encode()); hash_hex = hash_object.hexdigest()

    return f"https://placehold.co/40x40/{hash_hex[0:6]}/ffffff?text={username[0].upper()}"

def confetti_animation():

    html("""<script src="https://cdn.jsdelivr.net/npm/canvas-confetti@1.5.1/dist/confetti.browser.min.js"></script><script>setTimeout(() => confetti({particleCount: 150, spread: 70, origin: { y: 0.6 }}), 100);</script>""")

def get_mathbot_response(message):

    return "MathBot is thinking..."





# --- ### PAGE RENDERING LOGIC ### ---



def show_login_page():

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

                            st.session_state.logged_in = True; st.session_state.username = username

                            update_user_status(username, True); st.success(f"Welcome back, {username}!"); time.sleep(1); st.rerun()

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

    st.markdown("""

    <style>

        .chat-header { padding: 10px 15px; border-bottom: 1px solid #e0e0e0; display: flex; justify-content: space-between; align-items: center; background-color: #f8f9fa; }

        .chat-container { height: 65vh; overflow-y: auto; padding: 10px; display: flex; flex-direction: column-reverse; }

        .msg-wrapper { display: flex; margin-bottom: 12px; }

        .msg-bubble { padding: 8px 14px; border-radius: 18px; max-width: 75%; word-wrap: break-word; box-shadow: 0 1px 1px rgba(0,0,0,0.08); position: relative;}

        .msg-own { justify-content: flex-end; }

        .msg-own .msg-bubble { background-color: #dcf8c6; color: #333; }

        .msg-other { justify-content: flex-start; }

        .msg-other .msg-bubble { background-color: #fff; color: #333; }

        .avatar { width: 40px; height: 40px; border-radius: 50%; margin: 0 8px; }

        .reply-box { background: rgba(0,0,0,0.05); padding: 5px 10px; margin-bottom: 8px; border-left: 3px solid #007bff; font-size: 0.9em; border-radius: 4px; }

        .reactions { padding-top: 5px; cursor: default; }

        .reaction-pill { border: 1px solid #007bff; color: #007bff; background: #fff; border-radius: 10px; padding: 2px 8px; font-size: 0.8em; margin-right: 4px; display: inline-block; }

        .reaction-pill.reacted { background: #e0eaf7; }

        .reply-indicator { padding: 8px 12px; background: #e9e9e9; border-radius: 8px; margin-bottom: 8px; font-size: 0.9em; display: flex; justify-content: space-between; align-items: center; }

        .action-buttons { position: absolute; top: -15px; background: white; border-radius: 15px; box-shadow: 0 2px 5px rgba(0,0,0,0.2); visibility: hidden; opacity: 0; transition: opacity 0.2s; }

        .msg-wrapper:hover .action-buttons { visibility: visible; opacity: 1; }

        .msg-own .action-buttons { right: 10px; } .msg-other .action-buttons { left: 10px; }

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

    st.markdown(f'<div class="chat-header"><strong>💬 Community Chat</strong> <span><strong>Online:</strong> {len(online_users)} 🟢</span></div>', unsafe_allow_html=True)



    # --- MESSAGE DISPLAY ---

    message_container = st.container()

    with message_container:

        for msg in all_messages:

            is_own = msg['username'] == st.session_state.username

            col1, col2 = st.columns([1, 12] if not is_own else [12, 1])

            with col1 if not is_own else col2:

                st.image(get_avatar_url(msg['username']))

            with col2 if not is_own else col1:

                if msg['reply_to_message_id'] and msg['reply_to_message_id'] in messages_by_id:

                    original_msg = messages_by_id[msg['reply_to_message_id']]

                    st.markdown(f"<div class='reply-box'><b>Replying to {original_msg['username']}</b><br>{original_msg['message'][:50]}...</div>", unsafe_allow_html=True)

                

                st.markdown(f"<div class='msg-bubble'>{msg['message']}</div>", unsafe_allow_html=True)

                

                if msg['id'] in reactions:

                    pills = ""

                    for reaction in reactions[msg['id']]:

                        reacted_class = "reacted" if st.session_state.username in reaction['users'] else ""

                        pills += f"<span class='reaction-pill {reacted_class}'>{reaction['emoji']} {reaction['count']}</span>"

                    st.markdown(f"<div class='reactions'>{pills}</div>", unsafe_allow_html=True)



                b_col1, b_col2, b_col3, b_col4 = st.columns([1,1,1,10])

                if b_col1.button("↪️", key=f"reply_{msg['id']}", help="Reply"): st.session_state.reply_to_message = msg; st.rerun()

                if b_col2.button("👍", key=f"thumb_{msg['id']}", help="Thumbs Up"): add_reaction(msg['id'], st.session_state.username, "👍"); st.rerun()

                if b_col3.button("❤️", key=f"heart_{msg['id']}", help="Heart"): add_reaction(msg['id'], st.session_state.username, "❤️"); st.rerun()



    # --- INPUT BAR ---

    st.markdown("---")

    if st.session_state.reply_to_message:

        c1, c2 = st.columns([10, 1])

        with c1: st.markdown(f"<div class='reply-indicator'>↪️ Replying to <strong>{st.session_state.reply_to_message['username']}</strong></div>", unsafe_allow_html=True)

        with c2:

            if st.button("✖️", key="cancel_reply"): st.session_state.reply_to_message = None; st.rerun()



    if typing_users: st.caption(f"{', '.join(typing_users)} is typing...")



    user_message = st.text_area("Your message:", key="chat_input_main", placeholder="Type your message here...", height=75, label_visibility="collapsed")

    if st.button("Send", key="send_message", type="primary"):

        if user_message:

            update_typing_status(st.session_state.username, False)

            reply_id = st.session_state.reply_to_message['id'] if st.session_state.reply_to_message else None

            add_chat_message(st.session_state.username, user_message, reply_to_id=reply_id)

            st.session_state.reply_to_message = None

            st.rerun()



def show_main_app():

    with st.sidebar:

        st.markdown(f"### Welcome, {st.session_state.username}!")

        selected_page = st.radio("Menu", ["Dashboard", "Quiz", "Leaderboard", "Chat", "Profile", "Learning Resources"])

        if st.button("Logout", type="primary"):

            st.session_state.logged_in = False; st.session_state.quiz_active = False; st.rerun()



    if selected_page == "Dashboard": st.header("Dashboard")

    elif selected_page == "Quiz": st.header("Quiz")

    elif selected_page == "Leaderboard": st.header("Leaderboard")

    elif selected_page == "Chat": show_advanced_chat_page()

    elif selected_page == "Profile": show_profile_page()

    elif selected_page == "Learning Resources": st.header("Learning Resources")



# --- Main App Logic ---

if st.session_state.show_splash:

    st.markdown("""<style>.main{visibility:hidden;}</style><div style="position:fixed;top:0;left:0;width:100vw;height:100vh;background:#fff;display:flex;justify-content:center;align-items:center;z-index:9999;"><div style="font-size:50px;font-weight:bold;color:#2E86C1;">MathFriend</div></div>""", unsafe_allow_html=True)

    time.sleep(1); st.session_state.show_splash = False; st.rerun()

else:

    st.markdown("<style>.main{visibility:visible;}</style>", unsafe_allow_html=True)

    if st.session_state.logged_in:

        show_main_app()

    else:

        show_login_page()
