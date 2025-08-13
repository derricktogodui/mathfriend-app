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

# --- Page and Session Configuration ---
st.set_page_config(
    layout="wide",
    page_title="MathFriend",
    page_icon="🧮",
    initial_sidebar_state="expanded"
)

# --- Database Setup and Connection Logic ---
DB_FILE = 'users.db'

def create_tables_if_not_exist():
    conn = None
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS users
                     (username TEXT PRIMARY KEY, password TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS quiz_results
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT, topic TEXT,
                      score INTEGER, timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        c.execute('''CREATE TABLE IF NOT EXISTS chat_messages
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT, message TEXT,
                      media TEXT, timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        c.execute('''CREATE TABLE IF NOT EXISTS user_profiles
                     (username TEXT PRIMARY KEY, full_name TEXT, school TEXT,
                      age INTEGER, bio TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS user_status
                     (username TEXT PRIMARY KEY, is_online BOOLEAN,
                      last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        c.execute("PRAGMA table_info(chat_messages)")
        columns = [column[1] for column in c.fetchall()]
        if 'media' not in columns:
            c.execute("ALTER TABLE chat_messages ADD COLUMN media TEXT")
        conn.commit()
    except sqlite3.Error as e:
        st.error(f"Database setup error: {e}")
    finally:
        if conn:
            conn.close()

create_tables_if_not_exist()

# --- User Authentication Functions ---
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
    except sqlite3.Error as e:
        st.error(f"Login database error: {e}")
        return False
    finally:
        if conn:
            conn.close()

def signup_user(username, password):
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, hash_password(password)))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    except sqlite3.Error as e:
        st.error(f"Signup database error: {e}")
        return False
    finally:
        if conn:
            conn.close()

# --- Profile Management Functions ---
def get_user_profile(username):
    try:
        conn = sqlite3.connect(DB_FILE)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT * FROM user_profiles WHERE username=?", (username,))
        profile = c.fetchone()
        return dict(profile) if profile else {}
    except sqlite3.Error as e:
        st.error(f"Get profile error: {e}")
        return {}
    finally:
        if conn:
            conn.close()

def update_user_profile(username, full_name, school, age, bio):
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute('''INSERT OR REPLACE INTO user_profiles (username, full_name, school, age, bio) 
                     VALUES (?, ?, ?, ?, ?)''', (username, full_name, school, age, bio))
        conn.commit()
        return True
    except sqlite3.Error as e:
        st.error(f"Profile update error: {e}")
        return False
    finally:
        if conn:
            conn.close()

def change_password(username, current_password, new_password):
    if not login_user(username, current_password):
        return False
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("UPDATE users SET password=? WHERE username=?", (hash_password(new_password), username))
        conn.commit()
        return True
    except sqlite3.Error as e:
        st.error(f"Password change error: {e}")
        return False
    finally:
        if conn:
            conn.close()

# --- Online Status Functions ---
def update_user_status(username, is_online):
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute('''INSERT OR REPLACE INTO user_status (username, is_online, last_seen) 
                     VALUES (?, ?, CURRENT_TIMESTAMP)''', (username, is_online))
        conn.commit()
    except sqlite3.Error:
        pass
    finally:
        if conn:
            conn.close()

def get_online_users():
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT username FROM user_status WHERE is_online = 1 AND last_seen > datetime('now', '-2 minutes')")
        return [row[0] for row in c.fetchall()]
    except sqlite3.Error:
        return []
    finally:
        if conn:
            conn.close()

# --- Quiz and Result Functions ---
def generate_question(topic, difficulty):
    question, answer = "An error occurred generating a question.", None
    if topic in ["Addition", "Subtraction", "Multiplication", "Division", "Exponents"]:
        a, b = 0, 0
        if difficulty == "Easy": a, b = random.randint(1, 10), random.randint(1, 10)
        elif difficulty == "Medium": a, b = random.randint(10, 50), random.randint(1, 20)
        elif difficulty == "Hard": a, b = random.randint(50, 150), random.randint(10, 50)
        if topic == "Addition": question, answer = f"What is ${a} + {b}$?", a + b
        elif topic == "Subtraction": a, b = max(a, b), min(a, b); question, answer = f"What is ${a} - {b}$?", a - b
        elif topic == "Multiplication":
            if difficulty == "Hard": a, b = random.randint(10, 30), random.randint(10, 30)
            question, answer = f"What is ${a} \\times {b}$?", a * b
        elif topic == "Division":
            b = random.randint(2, 12); a = b * random.randint(2, 12)
            if difficulty == "Hard": b = random.randint(5, 20); a = b * random.randint(5, 20)
            question, answer = f"What is ${a} \\div {b}$?", a // b
        elif topic == "Exponents":
            base, power = (random.randint(2, 5), random.randint(2, 3))
            if difficulty == "Medium": base, power = (random.randint(2, 10), random.randint(2, 3))
            if difficulty == "Hard": base, power = (random.randint(2, 7), random.randint(3, 4))
            question, answer = f"What is ${base}^{{{power}}}$?", base ** power
    elif topic == "sets and operations on sets":
        set_a = set(random.sample(range(1, 15), random.randint(3, 5)))
        set_b = set(random.sample(range(1, 15), random.randint(3, 5)))
        op_choice = random.choice(["union", "intersection", "difference"])
        if difficulty == "Easy": op_choice = random.choice(["union", "intersection"])
        if op_choice == "union": question, answer = f"If A = ${set_a}$ and B = ${set_b}$, what is the cardinality of $A \\cup B$?", len(set_a.union(set_b))
        elif op_choice == "intersection": question, answer = f"If A = ${set_a}$ and B = ${set_b}$, what is the cardinality of $A \\cap B$?", len(set_a.intersection(set_b))
        elif op_choice == "difference": question, answer = f"If A = ${set_a}$ and B = ${set_b}$, what is the cardinality of $A - B$?", len(set_a.difference(set_b))
    elif topic == "surds":
        if difficulty == "Easy": p_sq, other = random.choice([4, 9, 16, 25]), random.choice([2, 3, 5]); val = p_sq * other; question, answer = f"Simplify $\\sqrt{{{val}}}$ to $a\\sqrt{{b}}$. What is 'a'?", int(math.sqrt(p_sq))
        elif difficulty == "Medium": c1, c2, base = random.randint(2, 8), random.randint(2, 8), random.choice([2, 3, 5, 7]); question, answer = f"Calculate ${c1}\\sqrt{{{base}}} + {c2}\\sqrt{{{base}}}$. If the result is $a\\sqrt{{b}}$, what is 'a'?", c1 + c2
        elif difficulty == "Hard": num, den_sqrt = random.randint(2, 9), random.choice([2, 3, 5, 7]); question, answer = f"Rationalize $\\frac{{{num}}}{{\\sqrt{{{den_sqrt}}}}}$. If the result is $\\frac{{a\\sqrt{{b}}}}{{c}}$, what is $a+b+c$?", num + den_sqrt + den_sqrt
    elif topic == "coordinate geometry":
        x1, y1, x2, y2 = random.randint(-5, 5), random.randint(-5, 5), random.randint(-5, 5), random.randint(-5, 5)
        while x1 == x2 and y1 == y2: x2, y2 = random.randint(-5, 5), random.randint(-5, 5)
        if difficulty == "Easy": question, answer = f"What is the sum of the coordinates (x+y) of the midpoint between $({x1}, {y1})$ and $({x2}, {y2})$?", (x1 + x2) / 2 + (y1 + y2) / 2
        elif difficulty == "Medium":
            if x2 - x1 == 0: question, answer = f"A line passes through $({x1}, {y1})$ and $({x2}, {y2})$. What is its slope? (Enter 999 for undefined)", 999
            else: num, den = y2 - y1, x2 - x1; common = math.gcd(num, den); a, b = num // common, den // common; question, answer = f"What is the slope of the line between $({x1}, {y1})$ and $({x2}, {y2})$? If it is $\\frac{{a}}{{b}}$, enter $a+b$.", a + (-b if b < 0 else b)
        elif difficulty == "Hard":
            slope = random.randint(-4, 4) or 1; y_int = random.randint(-5, 5)
            a, b = 1, abs(slope); common = math.gcd(a, b); a, b = a // common, b // common; question, answer = f"A line is defined by $y = {slope}x + {y_int}$. What is the slope of a perpendicular line? If it is $-\\frac{{a}}{{b}}$, enter $a+b$.", a + b
    elif topic == "probabilty":
        if difficulty == "Easy": red, blue = random.randint(3, 8), random.randint(3, 8); total = red + blue; common = math.gcd(red, total); question, answer = f"A bag has {red} red and {blue} blue balls. What is $a+b$ if the probability of drawing a red ball is $\\frac{{a}}{{b}}$?", (red // common) + (total // common)
        elif difficulty == "Medium": sides = random.choice([6, 8, 12]); evens, total = sides // 2, sides; common = math.gcd(evens, total); question, answer = f"On a fair {sides}-sided die, what is $a+b$ if the probability of rolling an even number is $\\frac{{a}}{{b}}$?", (evens // common) + (total // common)
        elif difficulty == "Hard": total, success = 52, 4; common = math.gcd(success, total); question, answer = f"From a standard deck of {total} cards, what is $a+b$ if the probability of drawing an Ace is $\\frac{{a}}{{b}}$?", (success // common) + (total // common)
    elif topic == "sequence and series":
        start, diff = random.randint(1, 10), random.randint(2, 5)
        if difficulty == "Easy": series = [start + i*diff for i in range(4)]; question, answer = f"What is the next term in the arithmetic sequence: ${', '.join(map(str, series))}, \\dots$?", series[-1] + diff
        elif difficulty == "Medium": n = random.randint(8, 12); question, answer = f"What is the ${n}^{{th}}$ term of an arithmetic sequence with first term ${start}$ and common difference ${diff}$?", start + (n-1)*diff
        elif difficulty == "Hard": n = random.randint(5, 8); question, answer = f"What is the sum of the first ${n}$ terms of an arithmetic series with first term ${start}$ and common difference ${diff}$?", n/2 * (2*start + (n-1)*diff)
    if question == "An error occurred generating a question.": question, answer = f"Questions for '{topic}' are under development.", None
    return question, answer

def save_quiz_result(username, topic, score):
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("INSERT INTO quiz_results (username, topic, score) VALUES (?, ?, ?)", (username, topic, score))
        conn.commit()
    except sqlite3.Error: pass
    finally:
        if conn: conn.close()

def get_top_scores(topic):
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT username, score FROM quiz_results WHERE topic=? ORDER BY score DESC, timestamp ASC LIMIT 10", (topic,))
        return c.fetchall()
    except sqlite3.Error: return []
    finally:
        if conn: conn.close()

def get_user_quiz_history(username):
    try:
        conn = sqlite3.connect(DB_FILE)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT topic, score, timestamp FROM quiz_results WHERE username=? ORDER BY timestamp DESC", (username,))
        return c.fetchall()
    except sqlite3.Error: return []
    finally:
        if conn: conn.close()

def get_user_stats(username):
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM quiz_results WHERE username=?", (username,)); total_quizzes = c.fetchone()[0]
        c.execute("SELECT score FROM quiz_results WHERE username=? ORDER BY timestamp DESC LIMIT 1", (username,)); last_score = c.fetchone(); last_score = last_score[0] if last_score else "N/A"
        c.execute("SELECT MAX(score) FROM quiz_results WHERE username=?", (username,)); top_score = c.fetchone(); top_score = top_score[0] if top_score and top_score[0] is not None else "N/A"
        return total_quizzes, last_score, top_score
    except sqlite3.Error: return 0, "N/A", "N/A"
    finally:
        if conn: conn.close()

# --- UI Helper Functions ---
def confetti_animation():
    html("""<script src="https://cdn.jsdelivr.net/npm/canvas-confetti@1.5.1/dist/confetti.browser.min.js"></script><script>setTimeout(() => confetti({ particleCount: 150, spread: 90, origin: { y: 0.6 } }), 100);</script>""")

# --- Page Rendering Logic ---
def show_login_page():
    st.markdown("""<style>.login-container { background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%); border-radius: 16px; padding: 40px; text-align: center; } .login-title { background: linear-gradient(90deg, #667eea 0%, #764ba2 100%); -webkit-background-clip: text; background-clip: text; color: transparent; font-size: 2.2rem; }</style>""", unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        with st.container():
            st.markdown('<div class="login-container">', unsafe_allow_html=True)
            st.markdown('<h1 class="login-title">MathFriend</h1>', unsafe_allow_html=True)
            page_mode = st.radio("Select", ["Login", "Sign Up"], label_visibility="collapsed", horizontal=True)
            if page_mode == "Login":
                with st.form("login_form"):
                    username = st.text_input("Username")
                    password = st.text_input("Password", type="password")
                    if st.form_submit_button("Login", type="primary", use_container_width=True):
                        if login_user(username, password):
                            st.session_state.logged_in = True
                            st.session_state.username = username
                            update_user_status(username, True)
                            st.success(f"Welcome back, {username}!")
                            time.sleep(1); st.rerun()
                        else:
                            st.error("Invalid username or password.")
            elif page_mode == "Sign Up":
                with st.form("signup_form"):
                    new_username = st.text_input("Choose a Username")
                    new_password = st.text_input("Create a Password", type="password")
                    confirm_password = st.text_input("Confirm Password", type="password")
                    if st.form_submit_button("Sign Up", type="primary", use_container_width=True):
                        if not all([new_username, new_password, confirm_password]): st.error("All fields are required.")
                        elif new_password != confirm_password: st.error("Passwords do not match.")
                        elif signup_user(new_username, new_password): st.success("Account created! Please log in."); time.sleep(1)
                        else: st.error("Username already exists.")
            st.markdown('</div>', unsafe_allow_html=True)

def show_main_app():
    st.markdown("""<style>... a lot of CSS ...</style>""", unsafe_allow_html=True) # Placeholder for your CSS
    with st.sidebar:
        st.title("🧮 MathFriend")
        st.write(f"Welcome, {st.session_state.username}!")
        st.markdown("---")
        selected_page = st.radio("Menu", ["Dashboard", "Quiz", "Leaderboard", "Profile"], label_visibility="collapsed")
        if st.button("Logout", type="secondary"):
            update_user_status(st.session_state.username, False)
            st.session_state.logged_in = False
            for key in st.session_state.keys():
                del st.session_state[key]
            st.rerun()

    if selected_page == "Dashboard":
        st.header("📈 Your Dashboard")
        # Placeholder for Dashboard content
        st.write("Dashboard coming soon!")

    elif selected_page == "Quiz":
        st.header("🧠 Quiz Time!")
        st.markdown("<div class='content-card'>", unsafe_allow_html=True)

        if 'quiz_active' not in st.session_state: st.session_state.quiz_active = False
        
        if not st.session_state.quiz_active:
            st.write("Select a topic and difficulty, then start the quiz. Answer as many questions as you like!")
            all_topics = ["Addition", "Subtraction", "Multiplication", "Division", "Exponents", "sets and operations on sets", "surds", "coordinate geometry", "probabilty", "sequence and series"]
            c1, c2 = st.columns(2)
            st.session_state.topic = c1.selectbox("Choose a topic:", all_topics)
            st.session_state.difficulty = c2.radio("Choose difficulty:", ["Easy", "Medium", "Hard"], horizontal=True)
            if st.button("Start Endless Quiz", type="primary", use_container_width=True):
                st.session_state.quiz_active = True
                st.session_state.score = 0
                st.session_state.questions_attempted = 0
                st.session_state.current_quiz_question = generate_question(st.session_state.topic, st.session_state.difficulty)
                st.rerun()

        elif st.session_state.quiz_active is True:
            question_text, correct_answer = st.session_state.current_quiz_question
            st.subheader(f"Current Score: {st.session_state.score} / {st.session_state.questions_attempted}")
            st.markdown("---")
            if correct_answer is None:
                st.error(question_text)
                if st.button("End Session"): st.session_state.quiz_active = False; st.rerun()
                st.stop()
            st.latex(question_text)
            if 'last_answer_feedback' in st.session_state:
                if st.session_state.last_answer_feedback['correct']: st.success(st.session_state.last_answer_feedback['text'])
                else: st.error(st.session_state.last_answer_feedback['text'])
            with st.form(key="quiz_form"):
                user_answer_input = st.number_input("Your Answer:", step=1, value=None, placeholder="Type your answer here...", key="user_answer")
                submitted = st.form_submit_button("Submit Answer")
            if st.button("Stop Quiz & See Results", type="secondary"):
                if st.session_state.questions_attempted > 0: save_quiz_result(st.session_state.username, st.session_state.topic, st.session_state.score)
                st.session_state.quiz_active = "results"; st.rerun()
            if submitted:
                if user_answer_input is not None:
                    st.session_state.questions_attempted += 1
                    try: is_correct = math.isclose(float(user_answer_input), correct_answer, rel_tol=1e-5)
                    except (ValueError, TypeError): is_correct = False
                    if is_correct: st.session_state.score += 1; st.session_state.last_answer_feedback = {'correct': True, 'text': 'Correct! 🎉 Here is your next question.'}; confetti_animation()
                    else: st.session_state.last_answer_feedback = {'correct': False, 'text': f'Not quite. The correct answer was {correct_answer}. Try this one!'}
                    st.session_state.current_quiz_question = generate_question(st.session_state.topic, st.session_state.difficulty); st.rerun()
                else: st.warning("Please enter an answer.")

        elif st.session_state.quiz_active == "results":
            st.balloons(); st.header("Session Complete!")
            score, attempted = st.session_state.get('score', 0), st.session_state.get('questions_attempted', 0)
            accuracy = (score / attempted * 100) if attempted > 0 else 0
            st.markdown(f"### You answered **{score}** out of **{attempted}** questions correctly!")
            st.metric(label="Your Accuracy", value=f"{accuracy:.1f} %")
            if st.button("Start a New Quiz", type="primary", use_container_width=True):
                for key in ['quiz_active', 'score', 'questions_attempted', 'current_quiz_question', 'last_answer_feedback']:
                    if key in st.session_state: del st.session_state[key]
                st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)
        
    elif selected_page == "Profile":
        # Placeholder for Profile page content
        st.header("👤 Your Profile")
        st.write("Profile editing coming soon!")

# --- Main Execution Block ---
if __name__ == "__main__":
    if "logged_in" not in st.session_state: st.session_state.logged_in = False
    if st.session_state.logged_in:
        show_main_app()
    else:
        show_login_page()
