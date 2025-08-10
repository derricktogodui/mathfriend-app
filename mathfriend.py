import streamlit as st
import sqlite3
import bcrypt
import time
import random
import pandas as pd
import plotly.express as px

# Streamlit-specific configuration must be at the very top of the script
st.set_page_config(layout="wide")

# --- Database Initialization ---
conn = sqlite3.connect('users.db')
c = conn.cursor()
c.execute('''CREATE TABLE IF NOT EXISTS users
             (username TEXT PRIMARY KEY, password TEXT)''')
# Create a new table for quiz results if it doesn't exist
c.execute('''CREATE TABLE IF NOT EXISTS quiz_results
             (id INTEGER PRIMARY KEY AUTOINCREMENT,
              username TEXT,
              topic TEXT,
              score INTEGER,
              timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
# Create a new table for chat messages
c.execute('''CREATE TABLE IF NOT EXISTS chat_messages
             (id INTEGER PRIMARY KEY AUTOINCREMENT,
              username TEXT,
              message TEXT,
              timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
conn.commit()

# --- Functions for user authentication ---
def hash_password(password):
    """Hashes a password using bcrypt."""
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def check_password(hashed_password, user_password):
    """Checks a password against its hash."""
    return bcrypt.checkpw(user_password.encode('utf-8'), hashed_password.encode('utf-8'))

def login_user(username, password):
    """Authenticates a user."""
    c.execute("SELECT password FROM users WHERE username=?", (username,))
    result = c.fetchone()
    if result:
        hashed_password = result[0]
        if check_password(hashed_password, password):
            return True
    return False

def signup_user(username, password):
    """Creates a new user account."""
    try:
        hashed_password = hash_password(password)
        c.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, hashed_password))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False

# --- Quiz and Result Functions ---
def generate_question(topic):
    """Generates a random math question based on the topic."""
    if topic == "Addition":
        a = random.randint(1, 20)
        b = random.randint(1, 20)
        question = f"What is {a} + {b}?"
        answer = a + b
    elif topic == "Subtraction":
        a = random.randint(10, 30)
        b = random.randint(1, a)
        question = f"What is {a} - {b}?"
        answer = a - b
    elif topic == "Multiplication":
        a = random.randint(1, 12)
        b = random.randint(1, 12)
        question = f"What is {a} x {b}?"
        answer = a * b
    else:
        question = "Please select a topic to start."
        answer = None
    return question, answer

def save_quiz_result(username, topic, score):
    """Saves a user's quiz result to the database."""
    c.execute("INSERT INTO quiz_results (username, topic, score) VALUES (?, ?, ?)",
              (username, topic, score))
    conn.commit()

def get_top_scores(topic):
    """Fetches the top 10 scores for a given topic."""
    c.execute("SELECT username, score FROM quiz_results WHERE topic=? ORDER BY score DESC, timestamp ASC LIMIT 10", (topic,))
    return c.fetchall()

def get_user_quiz_history(username):
    """Fetches a user's quiz history."""
    c.execute("SELECT topic, score, timestamp FROM quiz_results WHERE username=? ORDER BY timestamp DESC", (username,))
    return c.fetchall()

# --- Chat Functions ---
def add_chat_message(username, message):
    """Adds a new chat message to the database."""
    c.execute("INSERT INTO chat_messages (username, message) VALUES (?, ?)", (username, message))
    conn.commit()

def get_chat_messages():
    """Fetches all chat messages from the database."""
    c.execute("SELECT username, message, timestamp FROM chat_messages ORDER BY timestamp ASC")
    return c.fetchall()

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

# --- The new homepage function with placeholders ---
def show_main_app():
    st.title(f"Welcome to MathFriend, {st.session_state.username}! 🧑‍🏫")
    st.write("Your personal hub for mastering math.")
    
    st.sidebar.markdown("### **Menu**")
    st.sidebar.markdown("---")
    
    selected_page = st.sidebar.radio(
        "Go to", 
        ["📊 Dashboard", "📝 Quiz", "🏆 Leaderboard", "💬 Chat", "📚 Learning Resources"],
        label_visibility="collapsed"
    )
    
    st.sidebar.markdown("---")

    if selected_page == "📊 Dashboard":
        st.header("Progress Dashboard 📈")
        user_history = get_user_quiz_history(st.session_state.username)
        if user_history:
            df = pd.DataFrame(user_history, columns=['Topic', 'Score', 'Timestamp'])
            df['Timestamp'] = pd.to_datetime(df['Timestamp'])
            df['Date'] = df['Timestamp'].dt.date
            
            # Group by topic and date to show trends
            topic_scores = df.groupby(['Date', 'Topic'])['Score'].mean().reset_index()

            # Display a line chart of scores over time
            st.subheader("Quiz Scores Over Time")
            fig = px.line(topic_scores, x='Date', y='Score', color='Topic', markers=True, title="Your Quiz Performance")
            st.plotly_chart(fig, use_container_width=True)
            
            # Display a bar chart of average scores by topic
            st.subheader("Average Score by Topic")
            avg_scores = df.groupby('Topic')['Score'].mean().reset_index()
            fig_bar = px.bar(avg_scores, x='Topic', y='Score', color='Topic', title="Your Average Score per Topic")
            st.plotly_chart(fig_bar, use_container_width=True)
            
            st.subheader("Your Recent Quiz Results")
            st.table(df[['Topic', 'Score', 'Timestamp']].head())
        else:
            st.info("Start taking quizzes to see your progress here!")

    elif selected_page == "📝 Quiz":
        st.header("Quiz Time! 🧠")
        if 'quiz_active' not in st.session_state:
            st.session_state.quiz_active = False
            st.session_state.current_question = 0
            st.session_state.score = 0
            st.session_state.topic = "Addition"
            st.session_state.questions = []
            st.session_state.quiz_started_time = None

        if not st.session_state.quiz_active:
            st.write("Select a topic and challenge yourself!")
            topic_options = ["Addition", "Subtraction", "Multiplication"]
            st.session_state.topic = st.selectbox("Choose a topic:", topic_options)
            
            if st.button("Start Quiz"):
                st.session_state.quiz_active = True
                st.session_state.current_question = 0
                st.session_state.score = 0
                st.session_state.questions = [generate_question(st.session_state.topic) for _ in range(5)]
                st.session_state.quiz_started_time = time.time()
                st.rerun()
        else:
            quiz_duration = time.time() - st.session_state.quiz_started_time
            st.write(f"Time elapsed: **{int(quiz_duration)} seconds**")

            if st.session_state.current_question < len(st.session_state.questions):
                question_text, correct_answer = st.session_state.questions[st.session_state.current_question]
                st.subheader(f"Question {st.session_state.current_question + 1}:")
                st.write(question_text)
                
                with st.form(key=f"quiz_form_{st.session_state.current_question}"):
                    user_answer = st.number_input("Your answer:", step=1)
                    submit_button = st.form_submit_button("Submit Answer")
                    
                    if submit_button:
                        if user_answer == correct_answer:
                            st.success("Correct! 🎉")
                            st.session_state.score += 1
                        else:
                            st.error(f"Incorrect. The correct answer was {correct_answer}.")
                        
                        st.session_state.current_question += 1
                        time.sleep(1)
                        st.rerun()
            else:
                st.success(f"Quiz complete! You scored {st.session_state.score} out of {len(st.session_state.questions)}.")
                save_quiz_result(st.session_state.username, st.session_state.topic, st.session_state.score)
                st.session_state.quiz_active = False
                st.button("Start a new quiz", on_click=st.rerun)

    elif selected_page == "🏆 Leaderboard":
        st.header("Global Leaderboard 🏆")
        st.write("See who has the highest scores for each topic!")
        topic_options = ["Addition", "Subtraction", "Multiplication"]
        leaderboard_topic = st.selectbox("Select a topic to view the leaderboard:", topic_options)
        
        top_scores = get_top_scores(leaderboard_topic)
        
        if top_scores:
            df = pd.DataFrame(top_scores, columns=['Username', 'Score'])
            df.index += 1
            st.table(df)
        else:
            st.info("No scores have been recorded for this topic yet.")

    elif selected_page == "💬 Chat":
        st.header("Community Chat 💬")
        st.write("Help each other out with math homework!")

        messages_container = st.container()

        with messages_container:
            all_messages = get_chat_messages()
            for username, message, timestamp in all_messages:
                st.markdown(f"**{username}** (`{timestamp}`): {message}")
        
        st.markdown("---")

        with st.form("chat_form", clear_on_submit=True):
            user_message = st.text_input("Say something...", key="chat_input")
            col1, col2 = st.columns([1, 4])
            with col1:
                submitted = st.form_submit_button("Send")
            
            if submitted and user_message:
                add_chat_message(st.session_state.username, user_message)
                st.rerun()

    elif selected_page == "📚 Learning Resources":
        st.header("Learning Resources 📚")
        st.write("Mini-tutorials and helpful examples to help you study.")

        topic_options = ["Addition", "Subtraction", "Multiplication"]
        resource_topic = st.selectbox("Select a topic to learn about:", topic_options)

        if resource_topic == "Addition":
            st.subheader("What is Addition?")
            st.info("Addition is the process of combining two or more numbers to get a total sum. It's the most basic operation in math!")
            st.markdown("For example: `3 + 5 = 8`. Here, we are combining the numbers 3 and 5 to get the total sum of 8.")
        elif resource_topic == "Subtraction":
            st.subheader("What is Subtraction?")
            st.info("Subtraction is taking one number away from another. It's the opposite of addition.")
            st.markdown("For example: `10 - 4 = 6`. We start with 10 and take away 4, leaving us with 6.")
        elif resource_topic == "Multiplication":
            st.subheader("What is Multiplication?")
            st.info("Multiplication is a faster way of doing repeated addition. It's like adding the same number to itself a certain number of times.")
            st.markdown("For example: `4 x 3 = 12`. This is the same as saying `4 + 4 + 4 = 12`.")

    st.sidebar.markdown("---")
    if st.sidebar.button("Logout"):
        st.session_state.logged_in = False
        st.session_state.page = "login"
        st.rerun()
    st.sidebar.markdown("---")

# --- Main App Logic with a robust splash screen ---
if "show_splash" not in st.session_state:
    st.session_state.show_splash = True

if st.session_state.show_splash:
    st.markdown("<style>.main {visibility: hidden;}</style>", unsafe_allow_html=True)
    st.markdown("""
    <style>
        @keyframes fade-in-slide-up {
            0% { opacity: 0; transform: translateY(20px); }
            100% { opacity: 1; transform: translateY(0); }
        }
        .splash-container {
            position: fixed; top: 0; left: 0; width: 100vw; height: 100vh;
            background-color: #ffffff; display: flex; justify-content: center;
            align-items: center; z-index: 9999;
        }
        .splash-text {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            font-size: 50px; font-weight: bold; color: #2E86C1;
            animation: fade-in-slide-up 1s ease-out forwards;
        }
    </style>
    <div class="splash-container">
        <div class="splash-text">MathFriend</div>
    </div>
    """, unsafe_allow_html=True)
    
    # Hide splash screen after a short delay
    time.sleep(1)
    st.session_state.show_splash = False
    st.rerun()
else:
    st.markdown("<style>.main {visibility: visible;}</style>", unsafe_allow_html=True)
    st.markdown("""
    <style>
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
    /* Custom CSS to make the sidebar radio buttons bold and beautiful */
    div[data-testid="stSidebarNav"] li > a > div:first-child {
        font-weight: bold;
    }
    div[data-testid="stSidebarNav"] li {
        margin-bottom: 5px; /* Adds space between menu items */
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
