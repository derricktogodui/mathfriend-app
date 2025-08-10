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

# Streamlit-specific configuration must be at the very top of the script
st.set_page_config(layout="wide")

# --- Database Setup and Connection Logic ---
# The database file name
DB_FILE = 'users.db'

def create_tables_if_not_exist():
    """
    Ensures all necessary tables and columns exist in the database.
    This function now also handles adding the 'media' column if it's missing.
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

        # Check for the 'media' column and add it if it's missing
        # This is the key change to fix the "no such column" error
        c.execute("PRAGMA table_info(chat_messages)")
        columns = [column[1] for column in c.fetchall()]
        if 'media' not in columns:
            c.execute("ALTER TABLE chat_messages ADD COLUMN media TEXT")
            st.info("The 'media' column has been added to the chat_messages table.")
                      
        conn.commit()
    except sqlite3.Error as e:
        st.error(f"Database setup error: {e}")
    finally:
        if conn:
            conn.close()

# Call the setup function once when the script first runs
create_tables_if_not_exist()

# --- Functions for user authentication ---
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

# --- Quiz and Result Functions ---
def generate_question(topic, difficulty):
    """Generates a random math question based on the topic and difficulty."""
    # Placeholder for advanced topics
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
        ":smile:": "😊", ":laughing:": "😂", ":thumbsup:": "�", ":thumbsdown:": "👎",
        ":heart:": "❤️", ":star:": "⭐", ":100:": "💯", ":fire:": "🔥",
        ":thinking:": "🤔", ":nerd:": "🤓"
    }
    for shortcut, emoji in emoji_map.items():
        message = message.replace(shortcut, emoji)

    for user in mentioned_usernames:
        if user == current_user:
            message = re.sub(r'(?i)(@' + re.escape(user) + r')', r'<span class="mention-highlight">\1</span>', message)
    
    return message

# --- MathBot Integration (in-app calculator and definer) ---
def get_mathbot_response(message):
    """
    Solves a basic math expression or provides a definition from a chat message.
    """
    if not message.startswith("@MathBot"):
        return None

    query = message.replace("@MathBot", "").strip()
    query_lower = query.lower()

    # Updated definitions for the new topics
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
    # Wrap the entire main content in a container with a styled background
    st.markdown("<div class='main-content-container'>", unsafe_allow_html=True)
    st.markdown(f"<h1 class='main-title'>Welcome to MathFriend, {st.session_state.username}! 🧑‍🏫</h1>", unsafe_allow_html=True)
    st.markdown("Your personal hub for mastering math.")
    
    st.sidebar.markdown("### **Menu**")
    st.sidebar.markdown("---")
    
    selected_page = st.sidebar.radio(
        "Go to", 
        ["📊 Dashboard", "📝 Quiz", "🏆 Leaderboard", "💬 Chat", "📚 Learning Resources"],
        label_visibility="collapsed"
    )
    
    st.sidebar.markdown("---")

    if selected_page == "📊 Dashboard":
        st.markdown("---")
        st.markdown("<div class='content-card'>", unsafe_allow_html=True)
        st.header("Progress Dashboard 📈")
        st.write("A quick look at your math journey.")

        # Get user statistics
        total_quizzes, last_score, top_score = get_user_stats(st.session_state.username)
        
        # Display quick stats in a clean row of cards
        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown("<div class='dashboard-metric-card'>", unsafe_allow_html=True)
            st.metric(label="Total Quizzes Taken", value=total_quizzes)
            st.markdown("</div>", unsafe_allow_html=True)
        with col2:
            st.markdown("<div class='dashboard-metric-card'>", unsafe_allow_html=True)
            st.metric(label="Last Score (out of 5)", value=last_score)
            st.markdown("</div>", unsafe_allow_html=True)
        with col3:
            st.markdown("<div class='dashboard-metric-card'>", unsafe_allow_html=True)
            st.metric(label="Top Score (out of 5)", value=top_score)
            st.markdown("</div>", unsafe_allow_html=True)
        
        st.markdown("<div class='content-card'>", unsafe_allow_html=True)
        st.subheader("Motivational Quote of the Day 🌟")
        st.markdown(f"> *\"The only way to learn mathematics is to do mathematics.\"* — Paul Halmos")
        st.markdown("</div>", unsafe_allow_html=True)

        user_history = get_user_quiz_history(st.session_state.username)
        if user_history:
            df = pd.DataFrame(user_history, columns=['Topic', 'Score', 'Timestamp'])
            df['Timestamp'] = pd.to_datetime(df['Timestamp'])
            df['Date'] = df['Timestamp'].dt.date
            
            topic_scores = df.groupby(['Date', 'Topic'])['Score'].mean().reset_index()

            st.markdown("<div class='content-card'>", unsafe_allow_html=True)
            st.subheader("Quiz Scores Over Time")
            fig = px.line(topic_scores, x='Date', y='Score', color='Topic', markers=True, title="Your Quiz Performance")
            st.plotly_chart(fig, use_container_width=True)
            st.markdown("</div>", unsafe_allow_html=True)
            
            st.markdown("<div class='content-card'>", unsafe_allow_html=True)
            st.subheader("Average Score by Topic")
            avg_scores = df.groupby('Topic')['Score'].mean().reset_index()
            fig_bar = px.bar(avg_scores, x='Topic', y='Score', color='Topic', title="Your Average Score per Topic")
            st.plotly_chart(fig_bar, use_container_width=True)
            st.markdown("</div>", unsafe_allow_html=True)
            
            st.markdown("<div class='content-card'>", unsafe_allow_html=True)
            st.subheader("Your Recent Quiz Results")
            st.table(df[['Topic', 'Score', 'Timestamp']].head())
            st.markdown("</div>", unsafe_allow_html=True)
        else:
            st.info("Start taking quizzes to see your progress here!")
        st.markdown("</div>", unsafe_allow_html=True)

    elif selected_page == "📝 Quiz":
        st.header("Quiz Time! 🧠")
        if 'quiz_active' not in st.session_state:
            st.session_state.quiz_active = False
            st.session_state.current_question = 0
            st.session_state.score = 0
            st.session_state.topic = "sets and operations on sets"
            st.session_state.difficulty = "Easy"
            st.session_state.questions = []
            st.session_state.quiz_started_time = None

        if not st.session_state.quiz_active:
            st.write("Select a topic and challenge yourself!")
            
            # Updated topic list for quizzes
            topic_options = [
                "sets and operations on sets", "surds", "binary operations",
                "relations and functions", "polynomial functions",
                "rational functions", "binomial theorem", "coordinate geometry",
                "probabilty", "vectors", "sequence and series"
            ]
            st.session_state.topic = st.selectbox("Choose a topic:", topic_options)
            
            difficulty_options = ["Easy", "Medium", "Hard"]
            st.session_state.difficulty = st.selectbox("Choose a difficulty:", difficulty_options)

            if st.button("Start Quiz"):
                # Handle advanced topics with a message
                if st.session_state.topic in topic_options:
                    st.info("Quiz functionality for this advanced topic is still being developed. Please check back later!")
                else:
                    st.session_state.quiz_active = True
                    st.session_state.current_question = 0
                    st.session_state.score = 0
                    st.session_state.questions = [generate_question(st.session_state.topic, st.session_state.difficulty) for _ in range(5)]
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
        
        # Updated topic list for leaderboard
        topic_options = [
            "sets and operations on sets", "surds", "binary operations",
            "relations and functions", "polynomial functions",
            "rational functions", "binomial theorem", "coordinate geometry",
            "probabilty", "vectors", "sequence and series"
        ]
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
        st.write("Ask for help, share tips, or get an instant answer from the **@MathBot**!")
        st.markdown("---")

        all_usernames = get_all_usernames()
        all_messages = get_chat_messages()

        chat_container = st.container(height=400)

        with chat_container:
            for message_id, username, message, media, timestamp in all_messages:
                
                message_parts = []
                if media:
                    message_parts.append(f"<img src='data:image/png;base64,{media}' style='max-width:100%; height:auto; border-radius: 8px;'/>")
                
                if message:
                    formatted_message = format_message(message, all_usernames, st.session_state.username)
                    message_parts.append(f"<div>{formatted_message}</div>")

                if not message_parts:
                    continue

                avatar_url = get_avatar_url(username)
                is_mentioned = re.search(r'(?i)(@' + re.escape(st.session_state.username) + r')', message or "")
                mention_class = "mention-border" if is_mentioned else ""
                
                if username == st.session_state.username:
                    st.markdown(f"""
                        <div style="display:flex; justify-content: flex-end; align-items:flex-end;">
                            <div class="chat-bubble-user {mention_class}">
                                <small style="display:block; text-align:right; color:#ddd; font-size:10px;">{username} - {timestamp}</small>
                                {"".join(message_parts)}
                            </div>
                            <img class='avatar' src='{avatar_url}'/>
                        </div>
                    """, unsafe_allow_html=True)
                else:
                    col1, col2 = st.columns([0.9, 0.1])
                    with col1:
                        st.markdown(f"""
                            <div style="display:flex; justify-content: flex-start; align-items:flex-end;">
                                <img class='avatar' src='{avatar_url}'/>
                                <div class="chat-bubble-other {mention_class}">
                                    <small style="display:block; text-align:left; color:#888; font-size:10px;">{username} - {timestamp}</small>
                                    {"".join(message_parts)}
                                </div>
                            </div>
                        """, unsafe_allow_html=True)
                    with col2:
                        if st.button("🚩", key=f"report_{message_id}", help="Report this message"):
                            report_message(message_id, st.session_state.username)
                            
        st.markdown("---")

        with st.form("chat_form", clear_on_submit=True):
            user_message = st.text_area("Say something...", key="chat_input", height=50)
            
            # --- THE FIX IS HERE ---
            # Using st.columns for a clean layout
            col_upload, col_send = st.columns([0.7, 0.3])
            
            with col_upload:
                # Replaced the custom markdown button with a standard Streamlit file uploader.
                # This ensures the button works correctly across all platforms.
                uploaded_file = st.file_uploader("Upload Photo", type=["png", "jpg", "jpeg"], label_visibility="visible")
            
            with col_send:
                # st.form_submit_button now acts as the "Send" button
                submitted = st.form_submit_button("Send")
            # --- END OF FIX ---
            
            if submitted and (user_message or uploaded_file):
                media_data = None
                if uploaded_file is not None:
                    media_data = base64.b64encode(uploaded_file.getvalue()).decode('utf-8')
                
                add_chat_message(st.session_state.username, user_message, media_data)

                if user_message:
                    bot_response = get_mathbot_response(user_message)
                    if bot_response:
                        add_chat_message("MathBot", bot_response, None)

                st.rerun()

    elif selected_page == "📚 Learning Resources":
        st.header("Learning Resources 📚")
        st.write("Mini-tutorials and helpful examples to help you study.")
        
        # Updated topic list for learning resources
        topic_options = [
            "sets and operations on sets", "surds", "binary operations",
            "relations and functions", "polynomial functions",
            "rational functions", "binomial theorem", "coordinate geometry",
            "probabilty", "vectors", "sequence and series"
        ]
        resource_topic = st.selectbox("Select a topic to learn about:", topic_options)

        if resource_topic == "sets and operations on sets":
            st.subheader("Sets and Operations on Sets")
            st.info("A set is a collection of distinct objects. Operations on sets include **union** (combining all elements), **intersection** (finding common elements), and **difference** (elements in one set but not another).")
            st.markdown("For example: if Set A = {1, 2, 3} and Set B = {3, 4, 5}, the union is {1, 2, 3, 4, 5} and the intersection is {3}.")
        elif resource_topic == "surds":
            st.subheader("Surds")
            st.info("A **surd** is an irrational number that can be expressed with a root symbol, like $\sqrt{2}$. They are numbers that cannot be simplified to a whole number or a fraction.")
            st.markdown("For example, $\sqrt{2}$, $\sqrt{3}$, and $\sqrt{5}$ are surds. $\sqrt{4}$ is not a surd because it simplifies to 2.")
        elif resource_topic == "binary operations":
            st.subheader("Binary Operations")
            st.info("A **binary operation** is a calculation that combines two elements to produce a new element. Basic math operations like addition and multiplication are binary operations.")
            st.markdown("For example, in the expression $5 + 3 = 8$, the '+' symbol is a binary operation that takes two numbers, 5 and 3, and produces a new number, 8.")
        elif resource_topic == "relations and functions":
            st.subheader("Relations and Functions")
            st.info("A **relation** is a set of ordered pairs showing a relationship between two sets of numbers. A **function** is a special type of relation where every input has exactly one output.")
            st.markdown("For example, the relation {(1, 2), (2, 4), (3, 6)} is also a function. The relation {(1, 2), (1, 3)} is not a function because the input '1' has two different outputs.")
        elif resource_topic == "polynomial functions":
            st.subheader("Polynomial Functions")
            st.info("A **polynomial function** is a function made up of variables and coefficients, using only addition, subtraction, multiplication, and non-negative integer exponents.")
            st.markdown("For example, $f(x) = 3x^2 + 2x - 1$ is a polynomial function.")
        elif resource_topic == "rational functions":
            st.subheader("Rational Functions")
            st.info("A **rational function** is any function that can be expressed as a ratio of two polynomials, such as $f(x) = \frac{P(x)}{Q(x)}$. The denominator cannot be zero.")
            st.markdown("For example, $f(x) = \frac{2x+1}{x-3}$ is a rational function. You must be careful where the denominator, $x-3$, equals zero.")
        elif resource_topic == "binomial theorem":
            st.subheader("Binomial Theorem")
            st.info("The **binomial theorem** is a powerful formula for expanding the expression $(x+y)^n$ into a sum of terms. It's especially useful for large values of $n$.")
            st.markdown("For example, $(x+y)^2 = x^2 + 2xy + y^2$. The binomial theorem gives you a direct way to find the coefficients for any power.")
        elif resource_topic == "coordinate geometry":
            st.subheader("Coordinate Geometry")
            st.info("Coordinate geometry is the study of geometry using a coordinate system, like the Cartesian plane. It helps us describe and analyze geometric shapes using numbers and algebra.")
            st.markdown("Key concepts include finding the **distance** between two points, the **slope** of a line, and the **equation of a line** or circle.")
        elif resource_topic == "probabilty":
            st.subheader("Probability")
            st.info("Probability is a measure of the likelihood that a particular event will occur. It is expressed as a number between 0 and 1, where 0 means the event is impossible and 1 means it's certain.")
            st.markdown("For example, the probability of rolling a 4 on a standard six-sided die is $\frac{1}{6}$ because there is one '4' and six possible outcomes.")
        elif resource_topic == "vectors":
            st.subheader("Vectors")
            st.info("A **vector** is a quantity that has both **magnitude** (size or length) and **direction**. It's often used in physics and engineering to represent forces, velocity, and displacement.")
            st.markdown("For example, a car traveling at 60 mph *north* is a vector. A car traveling at just 60 mph is a scalar quantity (it only has magnitude).")
        elif resource_topic == "sequence and series":
            st.subheader("Sequence and Series")
            st.info("A **sequence** is an ordered list of numbers. A **series** is the sum of the terms in a sequence.")
            st.markdown("For example, the sequence of even numbers is 2, 4, 6, 8... while the series is $2 + 4 + 6 + 8 + ...$.")

    st.sidebar.markdown("---")
    if st.sidebar.button("Logout"):
        st.session_state.logged_in = False
        st.session_state.page = "login"
        st.rerun()
    st.sidebar.markdown("---")
    st.markdown("</div>", unsafe_allow_html=True) # Close the main content container

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
    .chat-bubble-user {
        background-color: #007BFF;
        color: white;
        padding: 10px 15px;
        border-radius: 15px 15px 0 15px;
        margin-bottom: 10px;
        max-width: 60%;
    }
    .chat-bubble-other {
        background-color: #e0e0e0;
        color: black;
        padding: 10px 15px;
        border-radius: 15px 15px 15px 0;
        margin-bottom: 10px;
        max-width: 60%;
    }
    .avatar {
        width: 40px;
        height: 40px;
        border-radius: 50%;
        object-fit: cover;
        margin: 0 10px;
    }
    .chat-bubble-user + .avatar {
        order: 2; /* Puts avatar after the bubble */
    }
    .chat-bubble-user {
        order: 1; /* Puts bubble before the avatar */
    }
    .mention-highlight {
        font-weight: bold;
        color: yellow !important;
        background-color: #2E86C1;
        padding: 2px 4px;
        border-radius: 5px;
    }
    .mention-border {
        border: 2px solid #ffcc00 !important;
    }
    /* NEW CSS for main content area */
    .main-content-container {
        background-color: #f0f2f6; /* A soft, light gray background */
        padding: 20px;
        border-radius: 12px;
    }
    .main-title {
        color: #1a2a52; /* A darker blue for better contrast */
        font-size: 2.5rem;
        margin-bottom: 0.5rem;
    }
    .content-card {
        background-color: #ffffff;
        padding: 20px;
        border-radius: 10px;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.05);
        margin-bottom: 20px;
    }
    .dashboard-metric-card {
        background-color: #e3f2fd; /* A light blue for metric cards */
        padding: 15px;
        border-radius: 8px;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.05);
        text-align: center;
    }
    .stMetric {
        font-size: 1.2rem;
    }
    .stFileUploader > button {
        background: linear-gradient(90deg, #00C6FF, #0072FF);
        color: white;
        font-weight: bold;
        border: none;
        border-radius: 8px;
        padding: 8px 12px;
        box-shadow: 0 2px 5px rgba(0,0,0,0.1);
        width: 100%;
        transition: all 0.3s ease;
    }
    .stFileUploader > button:hover {
        box-shadow: 0 4px 10px rgba(0,0,0,0.2);
        transform: translateY(-1px);
    }
    .stFileUploader > button:active {
        transform: translateY(1px);
    }
    .stFileUploader label {
        font-weight: bold;
        color: #475569;
    }
    /* === NEW: Responsive design for mobile screens === */
    @media screen and (max-width: 600px) {
        .main-title {
            font-size: 1.8rem;
        }
        .content-card {
            padding: 15px;
        }
        .dashboard-metric-card {
            padding: 10px;
        }
        .stMetric > div:first-child > div:nth-child(2) > div:first-child {
            font-size: 1.5rem !important; /* Make metric values larger for mobile */
        }
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