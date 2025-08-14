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

# Streamlit-specific configuration
st.set_page_config(
    layout="wide",
    page_title="MathFriend",
    page_icon="🧮",
    initial_sidebar_state="expanded"
)

# --- Session State Initialization ---
# Centralize all session state variables here
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

# --- Quiz-related session state for the dynamic MCQ system ---
if 'quiz_active' not in st.session_state:
    st.session_state.quiz_active = False
if 'quiz_topic' not in st.session_state:
    st.session_state.quiz_topic = "Sets" # Default topic
if 'quiz_score' not in st.session_state:
    st.session_state.quiz_score = 0
if 'questions_answered' not in st.session_state:
    st.session_state.questions_answered = 0


# --- Database Setup and Connection Logic ---
DB_FILE = 'users.db'

def create_tables_if_not_exist():
    """
    Ensures all necessary tables and columns exist in the database.
    UPDATED: quiz_results now includes a 'questions_answered' column for accuracy tracking.
    """
    conn = None
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        
        c.execute('''CREATE TABLE IF NOT EXISTS users
                     (username TEXT PRIMARY KEY, password TEXT)''')
                     
        # UPDATED: Added questions_answered column
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

# Call the setup function once when the script first runs
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
        if result:
            return check_password(result[0], password)
        return False
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

# --- Online Status Functions ---
def update_user_status(username, is_online):
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("INSERT OR REPLACE INTO user_status (username, is_online) VALUES (?, ?)", (username, is_online))
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
        c.execute("INSERT OR REPLACE INTO typing_indicators (username, is_typing) VALUES (?, ?)", (username, is_typing))
        conn.commit()
    finally:
        if conn: conn.close()

def get_typing_users():
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT username FROM typing_indicators WHERE is_typing = 1 AND timestamp > datetime('now', '-5 seconds')")
        return [row[0] for row in c.fetchall()]
    finally:
        if conn: conn.close()
        
# --- NEW: Question Generation Logic ---

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
        
    else: # Difference
        question_text += ", what is $A - B$?"
        correct_answer = str(set_a.difference(set_b))
        distractors = [str(set_b.difference(set_a)), str(set_a.union(set_b)), str(set_a.intersection(set_b))]
        hint = "The difference (A - B) finds elements that are in A but NOT in B."

    options = list(set([correct_answer] + distractors))
    while len(options) < 4:
        options.append(str(set(random.sample(range(1, 20), k=random.randint(2,4)))))
    random.shuffle(options)
    
    return {"question": question_text, "options": options, "answer": correct_answer, "hint": hint}

def _generate_percentages_question():
    q_type = random.choice(['percent_of', 'what_percent', 'original_price'])
    correct_answer = ""

    if q_type == 'percent_of':
        percent = random.randint(1, 40) * 5
        number = random.randint(1, 50) * 10
        question_text = f"What is {percent}% of {number}?"
        correct_answer_val = (percent / 100) * number
        correct_answer = f"{correct_answer_val:.2f}".rstrip('0').rstrip('.')
        hint = "To find the percent of a number, convert the percent to a decimal (divide by 100) and multiply."
    
    elif q_type == 'what_percent':
        part = random.randint(1, 20)
        whole = random.randint(part + 1, 50)
        question_text = f"What percent of {whole} is {part}?"
        correct_answer_val = (part / whole) * 100
        correct_answer = f"{correct_answer_val:.2f}".rstrip('0').rstrip('.') + "%"
        hint = "To find what percent a part is of a whole, divide the part by the whole and multiply by 100."

    else: # original_price
        original_price = random.randint(20, 200)
        discount_percent = random.randint(1, 8) * 5
        final_price = original_price * (1 - discount_percent/100)
        question_text = f"An item is sold for ${final_price:.2f} after a {discount_percent}% discount. What was the original price?"
        correct_answer = f"${original_price:.2f}"
        hint = "Let the original price be 'P'. The final price is P * (1 - discount/100). Solve for P."
        
    # Generate distractors
    options = [correct_answer]
    while len(options) < 4:
        try:
            noise = random.uniform(0.75, 1.25)
            # Extract numeric value from correct answer for manipulation
            numeric_part_str = re.sub(r'[^\d.]', '', correct_answer)
            if numeric_part_str:
                wrong_answer_val = float(numeric_part_str) * noise
                prefix = "$" if correct_answer.startswith("$") else ""
                suffix = "%" if correct_answer.endswith("%") else ""
                options.append(f"{prefix}{wrong_answer_val:.2f}{suffix}".rstrip('0').rstrip('.'))
            else: # Fallback if no numeric part
                options.append(f"{random.randint(1,100)}")
        except (ValueError, IndexError): # Catch potential errors if regex fails
             options.append(f"{random.randint(1,100)}")

    random.shuffle(options)
    
    return {"question": question_text, "options": list(set(options)), "answer": correct_answer, "hint": hint}

def generate_question(topic):
    """
    Master question generator. Routes to the correct sub-generator based on topic.
    """
    if topic == "Sets":
        return _generate_sets_question()
    elif topic == "Percentages":
        return _generate_percentages_question()
    # Add other topics here with `elif topic == "New Topic": return _generate_new_topic_question()`
    else:
        # Fallback for topics not yet implemented
        return {
            "question": f"Questions for **{topic}** are coming soon!",
            "options": ["OK"],
            "answer": "OK",
            "hint": "Please select another topic from the list to start a quiz."
        }

# --- UPDATED: Quiz and Result Functions ---

def save_quiz_result(username, topic, score, questions_answered):
    """Saves a user's quiz result, including total questions answered."""
    # Avoid saving empty quizzes
    if questions_answered == 0:
        return
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
    """Fetches the top 10 scores for a given topic, ranked by accuracy."""
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        # Rank by accuracy (score/questions_answered), then by most questions answered for tie-breaking
        c.execute("""
            SELECT username, score, questions_answered 
            FROM quiz_results 
            WHERE topic=? AND questions_answered > 0
            ORDER BY (CAST(score AS REAL) / questions_answered) DESC, questions_answered DESC, timestamp ASC
            LIMIT 10
        """, (topic,))
        results = c.fetchall()
        return results
    except sqlite3.Error as e:
        st.error(f"Get top scores database error: {e}")
        return []
    finally:
        if conn: conn.close()

def get_user_quiz_history(username):
    """Fetches a user's quiz history, now including questions answered."""
    try:
        conn = sqlite3.connect(DB_FILE)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT topic, score, questions_answered, timestamp FROM quiz_results WHERE username=? ORDER BY timestamp DESC", (username,))
        return c.fetchall()
    finally:
        if conn: conn.close()

def get_user_stats(username):
    """Fetches key statistics for a user's dashboard."""
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
    emoji_map = {":smile:": "😊", ":laughing:": "😂", ":thumbsup:": "👍", ":heart:": "❤️"}
    for shortcut, emoji in emoji_map.items():
        message = message.replace(shortcut, emoji)
    for user in mentioned_usernames:
        if user == current_user:
            message = re.sub(r'(?i)(@' + re.escape(user) + r')', r'<span class="mention-highlight">\1</span>', message)
    return message

def get_mathbot_response(message):
    if not message.startswith("@MathBot"):
        return None
    query = message.replace("@MathBot", "").strip().lower()
    definitions = {
        "sets": "A set is a collection of distinct objects, considered as an object in its own right.",
        "surds": "A surd is an irrational number that can be expressed with a root symbol, like $\sqrt{2}$.",
        "binary operation": "A binary operation is a calculation that combines two elements to produce a new one.",
        "percentages": "A percentage is a number or ratio expressed as a fraction of 100."
    }
    if query.startswith("define"):
        term = query.split("define", 1)[1].strip()
        return f"**Definition:** {definitions.get(term, "I don't have a definition for that yet.")}"
    return "I can help with definitions. Try '@MathBot define sets'."

def get_avatar_url(username):
    hash_object = hashlib.md5(username.encode())
    hash_hex = hash_object.hexdigest()
    first_letter = username[0].upper()
    color_code = hash_hex[0:6]
    return f"https://placehold.co/40x40/{color_code}/ffffff?text={first_letter}"

def confetti_animation():
    html("""<script src="https://cdn.jsdelivr.net/npm/canvas-confetti@1.5.1/dist/confetti.browser.min.js"></script><script>setTimeout(() => confetti({particleCount: 150, spread: 70, origin: { y: 0.6 }}), 100);</script>""")

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
        else: # Signup
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
    # A large block of CSS styles is here, collapsed for brevity in this view
    st.markdown("""<style> ... </style>""", unsafe_allow_html=True)
    
    with st.sidebar:
        st.session_state.dark_mode = st.toggle("🌙 Dark Mode", value=st.session_state.dark_mode)
        st.markdown("### **Menu**")
        selected_page = st.sidebar.radio("Go to", ["📊 Dashboard", "📝 Quiz", "🏆 Leaderboard", "💬 Chat", "👤 Profile", "📚 Learning Resources"], label_visibility="collapsed")
        st.markdown("---")
        st.sidebar.markdown("### **Account**")
        if st.sidebar.button("Logout", type="primary"):
            update_user_status(st.session_state.username, False)
            st.session_state.logged_in = False
            st.session_state.quiz_active = False # End quiz on logout
            st.rerun()

    update_user_status(st.session_state.username, True)

    if selected_page == "📊 Dashboard":
        st.markdown("<div class='content-card'>", unsafe_allow_html=True)
        st.header("📈 Progress Dashboard")
        st.write("Track your math learning journey with these insights.")
        
        total_quizzes, last_score_str, top_score_str = get_user_stats(st.session_state.username)
        
        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown(metric_card("Total Quizzes", total_quizzes, "📚", "#4361ee"), unsafe_allow_html=True)
        with col2:
            st.markdown(metric_card("Last Score", last_score_str, "⭐", "#4cc9f0"), unsafe_allow_html=True)
        with col3:
            st.markdown(metric_card("Top Score (by Accuracy)", top_score_str, "🏆", "#f72585"), unsafe_allow_html=True)
        
        st.markdown("<div class='content-card' style='margin-top: 20px;'>", unsafe_allow_html=True)
        st.subheader("🌟 Motivational Quote")
        st.markdown("""<blockquote style="border-left: 4px solid #4361ee; padding-left: 15px; font-style: italic; color: #555;">"Mathematics is not about numbers, equations, computations, or algorithms: it is about understanding." — William Paul Thurston</blockquote>""", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)
        
        user_history = get_user_quiz_history(st.session_state.username)
        if user_history:
            df = pd.DataFrame(user_history)
            df['Timestamp'] = pd.to_datetime(df['timestamp'])
            df['Date'] = df['Timestamp'].dt.date
            df['Accuracy'] = df.apply(lambda row: (row['score'] / row['questions_answered']) * 100 if row['questions_answered'] > 0 else 0, axis=1)
            
            st.markdown("<div class='content-card' style='margin-top: 20px;'>", unsafe_allow_html=True)
            st.subheader("📅 Your Accuracy Over Time")
            fig = px.line(df, x='Date', y='Accuracy', color='topic', markers=True, template="plotly_white")
            fig.update_layout(plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)', yaxis_title="Accuracy (%)")
            st.plotly_chart(fig, use_container_width=True)
            st.markdown("</div>", unsafe_allow_html=True)
            
            st.markdown("<div class='content-card' style='margin-top: 20px;'>", unsafe_allow_html=True)
            st.subheader("📝 Recent Quiz Results")
            df_display = df[['topic', 'score', 'questions_answered', 'Accuracy', 'Timestamp']].copy()
            df_display['Result'] = df_display['score'].astype(str) + "/" + df_display['questions_answered'].astype(str)
            st.dataframe(df_display[['topic', 'Result', 'Accuracy', 'Timestamp']].rename(columns={'topic': 'Topic'}).head(10).style.format({'Accuracy': '{:.1f}%', 'Timestamp': lambda x: x.strftime('%Y-%m-%d %H:%M')}), use_container_width=True)
            st.markdown("</div>", unsafe_allow_html=True)
        else:
            st.info("Start taking quizzes to see your progress here!")
        
        st.markdown("</div>", unsafe_allow_html=True)

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
                if st.button("Back to Topic Selection"):
                    st.rerun()
            else:
                st.markdown("---")
                st.markdown(q_data["question"])
                with st.expander("🤔 Need a hint?"):
                    st.info(q_data["hint"])
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
                        else:
                            st.warning("Please select an answer before submitting.")
            if st.button("Stop Quiz & Save Score"):
                save_quiz_result(st.session_state.username, st.session_state.quiz_topic, st.session_state.quiz_score, st.session_state.questions_answered)
                st.info(f"Quiz stopped. Your final score of {st.session_state.quiz_score}/{st.session_state.questions_answered} has been recorded.")
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
            leaderboard_data = [{"Rank": f"#{r}", "Username": u, "Score": f"{s}/{t}", "Accuracy": f"{(s/t)*100:.1f}%"} for r, (u, s, t) in enumerate(top_scores, 1)]
            df = pd.DataFrame(leaderboard_data)
            def highlight_user(row): return ['background-color: #e6f7ff; font-weight: bold;'] * len(row) if row.Username == st.session_state.username else [''] * len(row)
            st.dataframe(df.style.apply(highlight_user, axis=1).hide(axis="index"), use_container_width=True)
        else:
            st.info(f"No scores have been recorded for **{leaderboard_topic}** yet. Be the first!")
        st.markdown("</div>", unsafe_allow_html=True)

    elif selected_page == "💬 Chat":
        st.header("💬 Community Chat")
        st.markdown("""<style>.chat-container{height:70vh;overflow-y:auto;display:flex;flex-direction:column;gap:6px}.msg-row{display:flex;align-items:flex-end}.msg-own{justify-content:flex-end}.msg-bubble{max-width:min(80%,500px);padding:8px 12px;border-radius:18px}.msg-own .msg-bubble{background-color:#dcf8c6;border-bottom-right-radius:4px}.msg-other .msg-bubble{background-color:#fff;border-bottom-left-radius:4px}</style>""", unsafe_allow_html=True)
        st_autorefresh(interval=3000, key="chat_refresh")
        all_messages = get_chat_messages()
        st.markdown('<div id="chat-container">', unsafe_allow_html=True)
        for msg in all_messages:
            own = msg['username'] == st.session_state.username
            st.markdown(f"<div class='msg-row {'msg-own' if own else 'msg-other'}'><div class='msg-bubble'>{msg['message']}</div></div>", unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)
        st.markdown("""<script>var chatBox=document.getElementById('chat-container'); if(chatBox){chatBox.scrollTop=chatBox.scrollHeight;}</script>""", unsafe_allow_html=True)
        with st.form("chat_form", clear_on_submit=True):
            user_message = st.text_area("", key="chat_input", height=40, placeholder="Type a message", label_visibility="collapsed")
            if st.form_submit_button("Send", type="primary"):
                if user_message.strip():
                    add_chat_message(st.session_state.username, user_message)
                    if user_message.startswith("@MathBot"):
                        bot_response = get_mathbot_response(user_message)
                        if bot_response: add_chat_message("MathBot", bot_response)
                    st.rerun()
    
    elif selected_page == "👤 Profile":
        show_profile_page()

    elif selected_page == "📚 Learning Resources":
        st.header("📚 Learning Resources")
        st.markdown("<div class='content-card'>", unsafe_allow_html=True)
        topic_options = ["Sets", "Percentages", "Surds", "Binary Operations", "Word Problems
