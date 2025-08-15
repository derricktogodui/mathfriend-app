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
from streamlit.components.v1 import html, cache_resource
from streamlit_autorefresh import st_autorefresh
from fractions import Fraction

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

@cache_resource
def create_tables_if_not_exist():
    """
    Ensures all necessary tables and columns exist in the database.
    This function is cached and runs only once per server start.
    """
    conn = None
    try:
        # Increased timeout for robustness under load
        conn = sqlite3.connect(DB_FILE, timeout=15)
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
                      questions_answered INTEGER,
                      timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
                      
        # Create chat_messages table
        c.execute('''CREATE TABLE IF NOT EXISTS chat_messages
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      username TEXT,
                      message TEXT,
                      media TEXT,
                      timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')

        # Create user profiles table
        c.execute('''CREATE TABLE IF NOT EXISTS user_profiles
                     (username TEXT PRIMARY KEY,
                      full_name TEXT,
                      school TEXT,
                      age INTEGER,
                      bio TEXT)''')
        
        # Create online status table
        c.execute('''CREATE TABLE IF NOT EXISTS user_status
                     (username TEXT PRIMARY KEY, 
                      is_online BOOLEAN,
                      last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        
        # Create typing indicators table
        c.execute('''CREATE TABLE IF NOT EXISTS typing_indicators
                     (username TEXT PRIMARY KEY,
                      is_typing BOOLEAN,
                      timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')

        # Check for the 'media' column and add it if it's missing
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
        print("Database initialized successfully.")
    except sqlite3.Error as e:
        st.error(f"Database setup error: {e}")
    finally:
        if conn:
            conn.close()

def signup_user(username, password):
    conn = None
    try:
        conn = sqlite3.connect(DB_FILE, timeout=15)
        c = conn.cursor()
        c.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, hash_password(password)))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        if conn: conn.close()


# --- Profile Management Functions ---
def get_user_profile(username):
    conn = None
    try:
        conn = sqlite3.connect(DB_FILE, timeout=15)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT * FROM user_profiles WHERE username=?", (username,))
        profile = c.fetchone()
        return dict(profile) if profile else None
    finally:
        if conn: conn.close()

def update_user_profile(username, full_name, school, age, bio):
    conn = None
    try:
        conn = sqlite3.connect(DB_FILE, timeout=15)
        c = conn.cursor()
        c.execute('''INSERT OR REPLACE INTO user_profiles (username, full_name, school, age, bio) 
                     VALUES (?, ?, ?, ?, ?)''', (username, full_name, school, age, bio))
        conn.commit()
        return True
    finally:
        if conn: conn.close()

def change_password(username, current_password, new_password):
    if not login_user(username, current_password):
        return False
    conn = None
    try:
        conn = sqlite3.connect(DB_FILE, timeout=15)
        c = conn.cursor()
        c.execute("UPDATE users SET password=? WHERE username=?", (hash_password(new_password), username))
        conn.commit()
        return True
    finally:
        if conn: conn.close()


# --- Online Status Functions ---
def update_user_status(username, is_online):
    conn = None
    try:
        conn = sqlite3.connect(DB_FILE, timeout=15)
        c = conn.cursor()
        c.execute('''INSERT OR REPLACE INTO user_status (username, is_online, last_seen) 
                     VALUES (?, ?, CURRENT_TIMESTAMP)''', (username, is_online))
        conn.commit()
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
    elif operation == 'intersection':
        question_text += ", what is $A \cap B$?"
        correct_answer = str(set_a.intersection(set_b))
    else:
        question_text += ", what is $A - B$?"
        correct_answer = str(set_a.difference(set_b))
    options = {correct_answer, str(set_a), str(set_b), str(set_a.symmetric_difference(set_b))}
    while len(options) < 4:
        options.add(str(set(random.sample(range(1, 20), k=random.randint(2,4)))))
    shuffled_options = list(options)
    random.shuffle(shuffled_options)
    return {"question": question_text, "options": shuffled_options, "answer": correct_answer, "hint": "Review the definitions of set union, intersection, and difference."}

def _generate_percentages_question():
    q_type = random.choice(['percent_of', 'what_percent', 'original_price'])
    if q_type == 'percent_of':
        percent = random.randint(1, 40) * 5
        number = random.randint(1, 50) * 10
        question_text = f"What is {percent}% of {number}?"
        correct_answer = f"{(percent / 100) * number:.2f}"
        hint = "To find the percent of a number, convert the percent to a decimal (divide by 100) and multiply."
    elif q_type == 'what_percent':
        part = random.randint(1, 20)
        whole = random.randint(part + 1, 50)
        question_text = f"What percent of {whole} is {part}?"
        correct_answer = f"{(part / whole) * 100:.2f}%"
        hint = "To find what percent a part is of a whole, divide the part by the whole and multiply by 100."
    else:
        original_price = random.randint(20, 200)
        discount_percent = random.randint(1, 8) * 5
        final_price = original_price * (1 - discount_percent/100)
        question_text = f"An item is sold for ${final_price:.2f} after a {discount_percent}% discount. What was the original price?"
        correct_answer = f"${original_price:.2f}"
        hint = "Let the original price be 'P'. The final price is P * (1 - discount/100). Solve for P."
    options = [correct_answer]
    while len(options) < 4:
        noise = random.uniform(0.75, 1.25)
        wrong_answer_val = float(re.sub(r'[^\d.]', '', correct_answer)) * noise
        prefix = "$" if correct_answer.startswith("$") else ""
        suffix = "%" if correct_answer.endswith("%") else ""
        new_option = f"{prefix}{wrong_answer_val:.2f}{suffix}"
        if new_option not in options: options.append(new_option)
    random.shuffle(options)
    return {"question": question_text, "options": list(set(options)), "answer": correct_answer, "hint": hint}

def _get_fraction_latex_code(f: Fraction):
    if f.denominator == 1:
        return str(f.numerator)
    return f"\\frac{{{f.numerator}}}{{{f.denominator}}}"

def _format_fraction_text(f: Fraction):
    if f.denominator == 1:
        return str(f.numerator)
    return f"{f.numerator}/{f.denominator}"

def _generate_fractions_question():
    q_type = random.choice(['add_sub', 'mul_div', 'simplify'])
    f1 = Fraction(random.randint(1, 10), random.randint(2, 10))
    f2 = Fraction(random.randint(1, 10), random.randint(2, 10))
    if q_type == 'add_sub':
        op_symbol = random.choice(['+', '-'])
        expression_code = f"{_get_fraction_latex_code(f1)} {op_symbol} {_get_fraction_latex_code(f2)}"
        correct_answer_obj = f1 + f2 if op_symbol == '+' else f1 - f2
        hint = "To add or subtract fractions, you must first find a common denominator."
    elif q_type == 'mul_div':
        op_symbol = random.choice(['\\times', '\\div'])
        expression_code = f"{_get_fraction_latex_code(f1)} {op_symbol} {_get_fraction_latex_code(f2)}"
        if op_symbol == '\\div':
            if f2.numerator == 0: f2 = Fraction(1, f2.denominator)
            correct_answer_obj = f1 / f2
            hint = "To divide by a fraction, invert the second fraction and multiply."
        else:
            correct_answer_obj = f1 * f2
            hint = "To multiply fractions, multiply the numerators and the denominators together."
    else: # simplify
        common_factor = random.randint(2, 5)
        unsimplified_f = Fraction(f1.numerator * common_factor, f1.denominator * common_factor)
        expression_code = f"{_get_fraction_latex_code(unsimplified_f)}"
        correct_answer_obj = f1
        hint = "Find the greatest common divisor (GCD) of the numerator and denominator and divide both by it."
    if q_type == 'simplify':
        question_text = f"Simplify the fraction ${expression_code}$ to its lowest terms."
    else:
        question_text = f"Calculate: ${expression_code}$"
    correct_answer = _format_fraction_text(correct_answer_obj)
    options = {correct_answer}
    while len(options) < 4:
        distractor_f = random.choice([f1 + 1, f2, f1*f2, f1/f2 if f2 !=0 else f1])
        options.add(_format_fraction_text(distractor_f))
    shuffled_options = list(options)
    random.shuffle(shuffled_options)
    return {"question": question_text, "options": shuffled_options, "answer": correct_answer, "hint": hint}

def _generate_surds_question():
    q_type = random.choice(['simplify', 'operate'])
    if q_type == 'simplify':
        p = random.choice([4, 9, 16, 25])
        n = random.choice([2, 3, 5, 6, 7])
        num_inside = p * n
        coeff_out = int(math.sqrt(p))
        question_text = f"Simplify $\sqrt{{{num_inside}}}$"
        correct_answer = f"${coeff_out}\sqrt{{{n}}}$"
        hint = f"Look for the largest perfect square that divides {num_inside}."
        options = {correct_answer, f"${n}\sqrt{{{coeff_out}}}$", f"$\sqrt{{{num_inside}}}$"}
    else:
        base_surd = random.choice([2, 3, 5])
        c1, c2 = random.randint(1, 5), random.randint(1, 5)
        op = random.choice(['+', '-'])
        question_text = f"Calculate: ${c1}\sqrt{{{base_surd}}} {op} {c2}\sqrt{{{base_surd}}}$"
        result_coeff = c1 + c2 if op == '+' else c1 - c2
        correct_answer = f"${result_coeff}\sqrt{{{base_surd}}}$"
        hint = "You can only add or subtract 'like' surds (surds with the same number under the root)."
        options = {correct_answer, f"${c1+c2}\sqrt{{{base_surd*2}}}$", f"${c1*c2}\sqrt{{{base_surd}}}$"}
    while len(options) < 4:
        options.add(f"${random.randint(1,10)}\sqrt{{{random.randint(2,7)}}}$")
    shuffled_options = list(options)
    random.shuffle(shuffled_options)
    return {"question": question_text, "options": shuffled_options, "answer": correct_answer, "hint": hint}

def _generate_binary_ops_question():
    a, b = random.randint(1, 10), random.randint(1, 10)
    op_def, op_func = random.choice([
        ("a \\oplus b = 2a + b", lambda x, y: 2*x + y),
        ("a \\oplus b = a^2 - b", lambda x, y: x**2 - y),
        ("a \\oplus b = ab + a", lambda x, y: x*y + x),
        ("a \\oplus b = (a+b)^2", lambda x, y: (x+y)**2)
    ])
    question_text = f"Given the binary operation ${op_def}$, what is the value of ${a} \\oplus {b}$?"
    correct_answer = str(op_func(a, b))
    hint = "Substitute the values of 'a' and 'b' into the given definition for the operation."
    options = {correct_answer, str(op_func(b, a)), str(a+b), str(a*b)}
    while len(options) < 4:
        options.add(str(random.randint(1, 100)))
    shuffled_options = list(options)
    random.shuffle(shuffled_options)
    return {"question": question_text, "options": shuffled_options, "answer": correct_answer, "hint": hint}

def _generate_word_problems_question():
    x = random.randint(2, 10)
    k = random.randint(2, 5)
    op_word, op_func = random.choice([("tripled", lambda n: 3*n), ("doubled", lambda n: 2*n)])
    adjust_word, adjust_func = random.choice([("added to", lambda n, v: n + v), ("subtracted from", lambda n, v: n - v)])
    result = adjust_func(op_func(x), k)
    question_text = f"When a number is {op_word} and {k} is {adjust_word} the result, the answer is {result}. What is the number?"
    correct_answer = str(x)
    hint = "Let the unknown number be 'x'. Translate the sentence into a mathematical equation and solve for x."
    options = {correct_answer, str(result-k), str(x+k), str(result)}
    while len(options) < 4:
        options.add(str(random.randint(1, 20)))
    shuffled_options = list(options)
    random.shuffle(shuffled_options)
    return {"question": question_text, "options": shuffled_options, "answer": correct_answer, "hint": hint}

def generate_question(topic):
    generators = {
        "Sets": _generate_sets_question,
        "Percentages": _generate_percentages_question,
        "Fractions": _generate_fractions_question,
        "Surds": _generate_surds_question,
        "Binary Operations": _generate_binary_ops_question,
        "Word Problems": _generate_word_problems_question,
    }
    generator_func = generators.get(topic)
    if generator_func:
        return generator_func()
    else:
        return {"question": f"Questions for **{topic}** are coming soon!", "options": ["OK"], "answer": "OK", "hint": "This topic is under development."}

# --- Database Query Functions ---
def save_quiz_result(username, topic, score, questions_answered):
    conn = None
    try:
        conn = sqlite3.connect(DB_FILE, timeout=15)
        c = conn.cursor()
        c.execute("INSERT INTO quiz_results (username, topic, score, questions_answered) VALUES (?, ?, ?, ?)",
                  (username, topic, score, questions_answered))
        conn.commit()
    finally:
        if conn: conn.close()

def get_top_scores(topic):
    conn = None
    try:
        conn = sqlite3.connect(DB_FILE, timeout=15)
        c = conn.cursor()
        c.execute("""
            SELECT username, score, questions_answered FROM quiz_results WHERE topic=? AND questions_answered > 0
            ORDER BY (CAST(score AS REAL) / questions_answered) DESC, questions_answered DESC, timestamp ASC LIMIT 10
        """, (topic,))
        return c.fetchall()
    finally:
        if conn: conn.close()

def get_user_quiz_history(username):
    conn = None
    try:
        conn = sqlite3.connect(DB_FILE, timeout=15)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT topic, score, questions_answered, timestamp FROM quiz_results WHERE username=? ORDER BY timestamp DESC", (username,))
        return c.fetchall()
    finally:
        if conn: conn.close()

def get_user_stats(username):
    conn = None
    try:
        conn = sqlite3.connect(DB_FILE, timeout=15)
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM quiz_results WHERE username=?", (username,))
        total_quizzes = c.fetchone()[0]
        c.execute("SELECT score, questions_answered FROM quiz_results WHERE username=? ORDER BY timestamp DESC LIMIT 1", (username,))
        last_result = c.fetchone()
        last_score_str = f"{last_result[0]}/{last_result[1]}" if last_result and last_result[1] > 0 else "N/A"
        c.execute("SELECT score, questions_answered FROM quiz_results WHERE username=? AND questions_answered > 0 ORDER BY (CAST(score AS REAL) / questions_answered) DESC, score DESC LIMIT 1", (username,))
        top_result = c.fetchone()
        top_score_str = f"{top_result[0]}/{top_result[1]}" if top_result and top_result[1] > 0 else "N/A"
        return total_quizzes, last_score_str, top_score_str
    finally:
        if conn: conn.close()

def add_chat_message(username, message, media=None):
    conn = None
    try:
        conn = sqlite3.connect(DB_FILE, timeout=15)
        c = conn.cursor()
        c.execute("INSERT INTO chat_messages (username, message, media) VALUES (?, ?, ?)", (username, message, media))
        conn.commit()
    finally:
        if conn: conn.close()

def get_chat_messages(limit=25, offset=0):
    conn = None
    try:
        conn = sqlite3.connect(DB_FILE, timeout=15)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("""
            SELECT id, username, message, media, timestamp FROM chat_messages 
            ORDER BY timestamp DESC LIMIT ? OFFSET ?
        """, (limit, offset))
        results = c.fetchall()
        return results[::-1]
    finally:
        if conn: conn.close()

@st.cache_data(ttl=60)
def get_all_usernames():
    conn = None
    try:
        conn = sqlite3.connect(DB_FILE, timeout=15)
        c = conn.cursor()
        c.execute("SELECT username FROM users")
        return [row[0] for row in c.fetchall()]
    finally:
        if conn: conn.close()

# --- Helper & UI Functions ---
def get_avatar_url(username):
    hash_object = hashlib.md5(username.encode())
    return f"https://www.gravatar.com/avatar/{hash_object.hexdigest()}?d=identicon"

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
    if not message.startswith("@MathBot"): return None
    query = message.replace("@MathBot", "").strip().lower()
    if "4+2" in query: return "The result is 6." # Simple hardcoded example
    return "I can help with basic math. Try '@MathBot 4+2'."

def confetti_animation():
    html("""<script src="https://cdn.jsdelivr.net/npm/canvas-confetti@1.5.1/dist/confetti.browser.min.js"></script><script>confetti();</script>""")

def metric_card(title, value, icon, color):
    return f"""<div style="background: white; border-radius: 12px; padding: 15px; box-shadow: 0 4px 12px rgba(0,0,0,0.05); border-left: 4px solid {color};"><div style="display: flex; align-items: center; margin-bottom: 8px;"><div style="font-size: 24px; margin-right: 10px;">{icon}</div><div style="font-size: 14px; color: #666;">{title}</div></div><div style="font-size: 28px; font-weight: bold; color: {color};">{value}</div></div>"""

def show_login_page():
    st.markdown("<style>.main {display: flex; justify-content: center; align-items: center;}</style>", unsafe_allow_html=True)
    with st.container(border=True):
        st.title("🔐 MathFriend Login")
        with st.form("login_form"):
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            if st.form_submit_button("Login", type="primary", use_container_width=True):
                if login_user(username, password):
                    st.session_state.logged_in = True
                    st.session_state.username = username
                    st.success("Login successful!")
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error("Invalid username or password")
        if st.button("Don't have an account? Sign Up"):
            st.session_state.page = "signup"
            st.rerun()

def show_signup_page():
    st.markdown("<style>.main {display: flex; justify-content: center; align-items: center;}</style>", unsafe_allow_html=True)
    with st.container(border=True):
        st.title("Create a New Account")
        with st.form("signup_form"):
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            confirm_password = st.text_input("Confirm Password", type="password")
            if st.form_submit_button("Create Account", type="primary", use_container_width=True):
                if password != confirm_password:
                    st.error("Passwords do not match.")
                elif signup_user(username, password):
                    st.success("Account created! Please log in.")
                    st.session_state.page = "login"
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error("Username already exists.")
        if st.button("Back to Login"):
            st.session_state.page = "login"
            st.rerun()

def show_profile_page():
    st.header("👤 Your Profile")
    with st.container(border=True):
        profile = get_user_profile(st.session_state.username) or {}
        with st.form("profile_form"):
            st.subheader("Edit Profile")
            full_name = st.text_input("Full Name", value=profile.get('full_name', ''))
            school = st.text_input("School", value=profile.get('school', ''))
            age = st.number_input("Age", min_value=5, max_value=100, value=profile.get('age', 18))
            bio = st.text_area("Bio", value=profile.get('bio', ''))
            if st.form_submit_button("Save Profile", type="primary"):
                if update_user_profile(st.session_state.username, full_name, school, age, bio):
                    st.success("Profile updated!"); st.rerun()

        with st.form("password_form"):
            st.subheader("Change Password")
            current_password = st.text_input("Current Password", type="password")
            new_password = st.text_input("New Password", type="password")
            confirm_new_password = st.text_input("Confirm New Password", type="password")
            if st.form_submit_button("Change Password", type="primary"):
                if new_password != confirm_new_password: st.error("New passwords don't match!")
                elif change_password(st.session_state.username, current_password, new_password): st.success("Password changed successfully!")
                else: st.error("Incorrect current password")

def show_main_app():
    # --- PERFORMANCE FIX: Limit status updates to once per minute ---
    last_update = st.session_state.get("last_status_update", 0)
    if time.time() - last_update > 60:
        update_user_status(st.session_state.username, True)
        st.session_state.last_status_update = time.time()

    with st.sidebar:
        profile = get_user_profile(st.session_state.username)
        display_name = profile.get('full_name') if profile and profile.get('full_name') else st.session_state.username
        st.title(f"Welcome, {display_name}!")
        selected_page = st.radio("Menu", ["📊 Dashboard", "📝 Quiz", "🏆 Leaderboard", "💬 Chat", "👤 Profile", "📚 Learning Resources"], label_visibility="hidden")
        if st.button("Logout", type="primary", use_container_width=True):
            update_user_status(st.session_state.username, False)
            st.session_state.logged_in = False
            st.session_state.page = "login"
            st.rerun()

    topic_options = ["Sets", "Percentages", "Fractions", "Surds", "Binary Operations", "Word Problems"]
    
    if selected_page == "📊 Dashboard":
        st.header("📈 Progress Dashboard")
        with st.container(border=True):
            total_quizzes, last_score, top_score = get_user_stats(st.session_state.username)
            col1, col2, col3 = st.columns(3)
            col1.metric("Total Quizzes Taken", total_quizzes)
            col2.metric("Last Score", last_score)
            col3.metric("Best Score (by Accuracy)", top_score)

    elif selected_page == "📝 Quiz":
        st.header("🧠 Quiz Time!")
        with st.container(border=True):
            if not st.session_state.quiz_active:
                st.write("Select a topic and challenge yourself!")
                st.session_state.quiz_topic = st.selectbox("Choose a topic:", topic_options)
                if st.button("Start Quiz", type="primary", use_container_width=True):
                    st.session_state.quiz_active = True
                    st.session_state.quiz_score = 0
                    st.session_state.questions_answered = 0
                    if 'current_q_data' in st.session_state: del st.session_state['current_q_data']
                    st.rerun()
            else:
                st.write(f"**Topic:** {st.session_state.quiz_topic} | **Score:** {st.session_state.quiz_score}/{st.session_state.questions_answered}")
                if 'current_q_data' not in st.session_state:
                    st.session_state.current_q_data = generate_question(st.session_state.quiz_topic)
                q_data = st.session_state.current_q_data
                
                st.markdown(q_data["question"], unsafe_allow_html=True)
                with st.expander("🤔 Need a hint?"): st.info(q_data["hint"])
                
                with st.form(key=f"quiz_form_{st.session_state.questions_answered}"):
                    user_choice = st.radio("Select your answer:", q_data["options"], index=None)
                    if st.form_submit_button("Submit Answer", type="primary"):
                        if user_choice is not None:
                            st.session_state.questions_answered += 1
                            if str(user_choice) == str(q_data["answer"]):
                                st.session_state.quiz_score += 1
                                st.success("Correct! Well done! 🎉")
                                confetti_animation()
                            else:
                                st.error(f"Not quite. The correct answer was: **{q_data['answer']}**")
                            del st.session_state.current_q_data
                            time.sleep(1.5)
                            st.rerun()
                        else:
                            st.warning("Please select an answer before submitting.")
                
                if st.button("Stop Quiz & Save Score"):
                    if st.session_state.questions_answered > 0:
                        save_quiz_result(st.session_state.username, st.session_state.quiz_topic, st.session_state.quiz_score, st.session_state.questions_answered)
                        st.info(f"Quiz stopped. Score of {st.session_state.quiz_score}/{st.session_state.questions_answered} saved.")
                    st.session_state.quiz_active = False
                    st.rerun()

    elif selected_page == "🏆 Leaderboard":
        st.header("🏆 Global Leaderboard")
        with st.container(border=True):
            leaderboard_topic = st.selectbox("Select a topic to view:", topic_options)
            top_scores = get_top_scores(leaderboard_topic)
            if top_scores:
                leaderboard_data = [{"Rank": f"#{r}", "Username": u, "Score": f"{s}/{t}", "Accuracy": (s/t)*100} for r, (u,s,t) in enumerate(top_scores, 1)]
                df = pd.DataFrame(leaderboard_data)
                def highlight_user(row):
                    if row.Username == st.session_state.username:
                        return ['background-color: #e6f7ff; font-weight: bold; color: #000000;'] * len(row)
                    return [''] * len(row)
                st.dataframe(df.style.apply(highlight_user, axis=1).format({'Accuracy': "{:.1f}%"}).hide(axis="index"), use_container_width=True)
            else:
                st.info(f"No scores recorded for **{leaderboard_topic}** yet.")

    elif selected_page == "💬 Chat":
        st.header("💬 Community Chat")
        if 'chat_offset' not in st.session_state: st.session_state.chat_offset = 0
        
        live_refresh = st.toggle("Enable Live Refresh", value=True, help="Automatically refresh chat every 5s. Turn off to improve performance.")
        if live_refresh:
            st_autorefresh(interval=5000, key="chat_refresh")

        # ... (Your final, stable chat UI code with pagination would go here)
        st.info("Chat functionality is under construction in this version.")


    elif selected_page == "📚 Learning Resources":
        st.header("📚 Learning Resources")
        st.info("Coming soon!")

# --- Main App Logic ---
# Direct start without splash screen (removed splash for speed)
st.markdown("<h1 style='text-align:center;'>Welcome to MathFriend!</h1>", unsafe_allow_html=True)

if st.session_state.logged_in:
    show_main_app()
else:
    if st.session_state.page == "login":
        show_login_page()
    else:
        show_signup_page()
