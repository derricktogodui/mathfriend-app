import streamlit as st
import sqlite3
import bcrypt
import time

# --- Database Initialization ---
conn = sqlite3.connect('users.db')
c = conn.cursor()
c.execute('''CREATE TABLE IF NOT EXISTS users
             (username TEXT PRIMARY KEY, password TEXT)''')
conn.commit()

# --- Functions for user authentication ---
def hash_password(password):
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def check_password(hashed_password, user_password):
    return bcrypt.checkpw(user_password.encode('utf-8'), hashed_password.encode('utf-8'))

def login_user(username, password):
    c.execute("SELECT password FROM users WHERE username=?", (username,))
    result = c.fetchone()
    if result:
        hashed_password = result[0]
        if check_password(hashed_password, password):
            return True
    return False

def signup_user(username, password):
    try:
        hashed_password = hash_password(password)
        c.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, hashed_password))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False

# --- Page Rendering Logic ---
def show_login_page():
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("<div class='login-card'>", unsafe_allow_html=True)
        st.markdown("<div class='login-title'>🔐 Login to MathFriend</div>", unsafe_allow_html=True)
        st.markdown("<div class='login-subtitle'>Please enter your username and password</div>", unsafe_allow_html=True)
        
        with st.form("login_form"):
            username = st.text_input("Username", key="login_username")
            password = st.text_input("Password", type="password", key="login_password")
            submitted = st.form_submit_button("Login")
            
            if submitted:
                if login_user(username, password):
                    st.session_state.logged_in = True
                    st.session_state.username = username
                    st.success(f"Welcome back, {username}!")
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error("Invalid username or password.")
        
        if st.button("Don't have an account? Sign Up", key="signup_button"):
            st.session_state.page = "signup"
            st.rerun()
        
        st.markdown("</div>", unsafe_allow_html=True)
        st.markdown("<div class='footer-note'>Built with care by Derrick Kwaku Togodui</div>", unsafe_allow_html=True)

def show_signup_page():
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("<div class='login-card'>", unsafe_allow_html=True)
        st.markdown("<div class='login-title'>📝 Create a New Account</div>", unsafe_allow_html=True)
        st.markdown("<div class='login-subtitle'>Join the MathFriend community!</div>", unsafe_allow_html=True)

        with st.form("signup_form"):
            new_username = st.text_input("New Username", key="signup_username")
            new_password = st.text_input("New Password", type="password", key="signup_password")
            confirm_password = st.text_input("Confirm Password", type="password", key="confirm_password")
            signup_submitted = st.form_submit_button("Create Account")

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
        
        if st.button("Already have an account? Log In", key="login_button"):
            st.session_state.page = "login"
            st.rerun()
        
        st.markdown("</div>", unsafe_allow_html=True)
        st.markdown("<div class='footer-note'>Built with care by Derrick Kwaku Togodui</div>", unsafe_allow_html=True)

def show_main_app():
    st.title(f"Welcome to MathFriend, {st.session_state.username}! 🧑‍🏫")
    st.write("This is where the magic happens. Your math exercises will be here.")
    st.write("### Your Daily Challenge")
    st.write("Today's topic: Addition and Subtraction.")
    st.info("Here you can create your custom math content for students. For example, interactive quizzes or problem-solving exercises.")
    if st.button("Logout"):
        st.session_state.logged_in = False
        st.session_state.page = "login"
        st.rerun()

# --- Main App Logic with a robust splash screen ---
if "splash_displayed" not in st.session_state:
    st.session_state.splash_displayed = False

if not st.session_state.splash_displayed:
    st.markdown("<style>.main {visibility: hidden;}</style>", unsafe_allow_html=True)
    st.markdown("""
    <style>
        @keyframes smoothFadeZoom {
            0% {opacity: 0; transform: scale(0.85);}
            30% {opacity: 1; transform: scale(1);}
            70% {opacity: 1; transform: scale(1.02);}
            100% {opacity: 0; transform: scale(1);}
        }
        .splash-container {
            position: fixed; top: 0; left: 0;
            width: 100vw; height: 100vh;
            background-color: white;
            display: flex; justify-content: center; align-items: center;
            z-index: 9999;
            animation: smoothFadeZoom 2.8s ease-in-out forwards;
            user-select: none;
        }
        .splash-text {
            font-size: clamp(2rem, 5vw, 3.5rem); font-weight: bold;
            color: #007BFF; font-family: 'Segoe UI', Tahoma, sans-serif;
            text-align: center; letter-spacing: 1px;
        }
    </style>
    <div class="splash-container">
        <div class="splash-text">MathFriend</div>
    </div>
    """, unsafe_allow_html=True)
    
    time.sleep(2.8) 
    
    st.session_state.splash_displayed = True
    st.rerun() # The correct, non-experimental way to rerun
else:
    st.markdown("""
    <style>
    body, html, #root, .main {
        height: 100%; margin: 0; padding: 0;
        background-color: white; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
        -webkit-font-smoothing: antialiased; -moz-osx-font-smoothing: grayscale;
    }
    .login-card {
        width: 100%; max-width: 380px; background: white; border: 1px solid #ddd;
        border-radius: 12px; box-shadow: 0 6px 20px rgb(0 0 0 / 0.1);
        padding: 28px 24px; box-sizing: border-box; text-align: center;
    }
    .login-title {
        font-weight: 700; font-size: 1.9rem; margin-bottom: 8px; color: #007BFF;
    }
    .login-subtitle {
        color: #475569; margin-bottom: 22px; font-size: 1rem;
    }
    .footer-note {
        margin-top: 12px; font-size: 0.85rem; color: #64748b; text-align: center;
    }
    .stTextInput > div > input, .stTextInput > div > textarea {
        font-size: 1rem !important; padding: 8px 12px !important; border-radius: 6px !important;
        border: 1px solid #bbb !important;
    }
    .stButton > button {
        width: 100% !important; padding: 11px 0 !important; font-weight: 700 !important;
        background: linear-gradient(90deg, #007BFF, #0062D6) !important;
        border: none !important; border-radius: 8px !important; color: white !important;
        cursor: pointer; font-size: 1rem !important; transition: background-color 0.3s ease;
    }
    .stButton > button:hover {
        background: linear-gradient(90deg, #0056b3, #004080) !important;
    }
    </style>
    """, unsafe_allow_html=True)
    
    if "logged_in" not in st.session_state:
        st.session_state.logged_in = False
    if "page" not in st.session_state:
        st.session_state.page = "login"

    if st.session_state.logged_in:
        show_main_app()
    elif st.session_state.page == "signup":
        show_signup_page()
    else:
        show_login_page()