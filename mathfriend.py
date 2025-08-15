import streamlit as st
import time
from datetime import datetime

# =================================================================
# PHASED INITIALIZATION SYSTEM (Optimized for Streamlit Community Cloud)
# =================================================================

# Stage 1: Minimal session state for login
if "logged_in" not in st.session_state:
    st.session_state.update({
        "logged_in": False,
        "page": "login",
        "username": "",
        "show_splash": True,
        "_full_init": False,  # Flag for deferred initialization
        "_imports_loaded": False  # Track heavy imports
    })

# =================================================================
# ULTRA-FAST SPLASH SCREEN (0.3s render)
# =================================================================
if st.session_state.show_splash:
    st.markdown("""
    <style>
        .splash {
            display: flex;
            justify-content: center;
            align-items: center;
            height: 100vh;
            font-size: 2.5rem;
            font-weight: 700;
            color: #4361ee;
            animation: fadein 0.3s;
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
        }
        @keyframes fadein { from { opacity: 0; transform: scale(0.95); } 
                          to { opacity: 1; transform: scale(1); } }
    </style>
    <div class="splash">
        <div style="text-align:center">
            <div>🧮</div>
            <div>MathFriend</div>
        </div>
    </div>
    """, unsafe_allow_html=True)
    time.sleep(0.3)  # Reduced from 1s
    st.session_state.show_splash = False
    st.rerun()

# =================================================================
# LAZY-LOADED CORE SYSTEMS (Only load when needed)
# =================================================================
def _load_heavy_imports():
    """Load heavy dependencies only after login"""
    if not st.session_state._imports_loaded:
        global pd, px, Fraction, math, base64, re, hashlib, html, st_autorefresh
        import pandas as pd
        import plotly.express as px
        from fractions import Fraction
        import math
        import base64
        import re
        import hashlib
        from streamlit.components.v1 import html
        from streamlit_autorefresh import st_autorefresh
        st.session_state._imports_loaded = True

def _init_full_database():
    """Complete database initialization after login"""
    conn = _get_db_connection()
    try:
        conn.executescript('''
            CREATE TABLE IF NOT EXISTS quiz_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT,
                topic TEXT,
                score INTEGER,
                questions_answered INTEGER,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS user_profiles (
                username TEXT PRIMARY KEY,
                full_name TEXT,
                school TEXT,
                age INTEGER,
                bio TEXT
            );
            CREATE TABLE IF NOT EXISTS chat_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT,
                message TEXT,
                media TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS user_status (
                username TEXT PRIMARY KEY, 
                is_online BOOLEAN,
                last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS typing_indicators (
                username TEXT PRIMARY KEY,
                is_typing BOOLEAN,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        ''')
        conn.commit()
    finally:
        conn.close()

# =================================================================
# OPTIMIZED DATABASE CORE (WAL mode + connection pooling)
# =================================================================
@st.cache_resource
def _get_db_connection():
    import sqlite3
    conn = sqlite3.connect('users.db', timeout=15)
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA cache_size = -10000")  # 10MB cache
    return conn

def _init_auth_tables():
    """Only create auth tables needed for login"""
    conn = _get_db_connection()
    try:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS users (
                username TEXT PRIMARY KEY, 
                password TEXT
            )''')
        conn.commit()
    finally:
        pass  # Don't close - using cached connection

# =================================================================
# AUTHENTICATION CORE (Optimized password hashing)
# =================================================================
def _hash_password(password):
    import bcrypt
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def _verify_password(username, password):
    import bcrypt
    conn = _get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT password FROM users WHERE username=?", (username,))
        result = cursor.fetchone()
        return bool(result) and bcrypt.checkpw(password.encode('utf-8'), result[0].encode('utf-8'))
    except Exception:
        return False
    finally:
        pass  # Connection managed by cache_resource

# =================================================================
# LOGIN/SIGNUP PAGES (Minimal design for speed)
# =================================================================
def _render_login_page():
    st.markdown("""
    <style>
        .auth-container {
            max-width: 400px;
            margin: 2rem auto;
            padding: 2rem;
            border-radius: 12px;
            box-shadow: 0 2px 16px rgba(0,0,0,0.1);
        }
        .auth-title {
            color: #4361ee;
            margin-bottom: 1.5rem;
        }
    </style>
    """, unsafe_allow_html=True)

    with st.container():
        st.markdown('<div class="auth-title"><h1>🔐 MathFriend Login</h1></div>', unsafe_allow_html=True)
        
        with st.form("login_form", clear_on_submit=False):
            username = st.text_input("Username", key="login_username")
            password = st.text_input("Password", type="password", key="login_password")
            
            if st.form_submit_button("Login", type="primary", use_container_width=True):
                if username and password:
                    _init_auth_tables()
                    if _verify_password(username, password):
                        st.session_state.update({
                            "logged_in": True,
                            "username": username,
                            "dark_mode": False,
                            "quiz_active": False,
                            "quiz_topic": "Sets",
                            "quiz_score": 0,
                            "questions_answered": 0
                        })
                        st.rerun()
                    else:
                        st.error("Invalid credentials")

        if st.button("Create Account", use_container_width=True):
            st.session_state.page = "signup"
            st.rerun()

def _render_signup_page():
    with st.container():
        st.markdown('<div class="auth-title"><h1>✨ Create Account</h1></div>', unsafe_allow_html=True)
        
        with st.form("signup_form", clear_on_submit=True):
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            confirm = st.text_input("Confirm Password", type="password")
            
            if st.form_submit_button("Sign Up", type="primary", use_container_width=True):
                if password != confirm:
                    st.error("Passwords don't match")
                elif not username or not password:
                    st.error("All fields required")
                else:
                    _init_auth_tables()
                    conn = _get_db_connection()
                    try:
                        conn.execute("INSERT INTO users VALUES (?,?)", 
                                    (username, _hash_password(password)))
                        conn.commit()
                        st.success("Account created! Please login")
                        st.session_state.page = "login"
                        time.sleep(1)
                        st.rerun()
                    except conn.IntegrityError:
                        st.error("Username already exists")
                    finally:
                        pass  # Connection managed by cache_resource

# =================================================================
# MAIN APP COMPONENTS (Loaded only after authentication)
# =================================================================
def _render_main_app():
    # Complete initialization
    if not st.session_state._full_init:
        _load_heavy_imports()
        _init_full_database()
        st.session_state._full_init = True
    
    # Your original show_main_app() implementation here
    # Including all features:
    # - Quiz system
    # - Chat interface
    # - Profile management
    # - Leaderboards
    # - Learning resources
    
    # Example structure (replace with your actual implementation):
    with st.sidebar:
        st.title(f"Welcome, {st.session_state.username}!")
        selected_page = st.radio("Menu", [
            "📊 Dashboard", 
            "📝 Quiz", 
            "🏆 Leaderboard", 
            "💬 Chat", 
            "👤 Profile", 
            "📚 Resources"
        ], label_visibility="hidden")
        
        if st.button("Logout", type="primary", use_container_width=True):
            update_user_status(st.session_state.username, False)
            st.session_state.clear()
            st.session_state.page = "login"
            st.rerun()
    
    if selected_page == "📊 Dashboard":
        _render_dashboard()
    elif selected_page == "📝 Quiz":
        _render_quiz_interface()
    # ... (all other sections)

# =================================================================
# APP ROUTER (Optimized control flow)
# =================================================================
if not st.session_state.logged_in:
    if st.session_state.page == "login":
        _render_login_page()
    else:
        _render_signup_page()
else:
    _render_main_app()
