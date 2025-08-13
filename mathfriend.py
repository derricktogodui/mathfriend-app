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
        c.execute('''CREATE TABLE IF NOT EXISTS typing_indicators
                     (username TEXT PRIMARY KEY, is_typing BOOLEAN,
                      timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
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
        pass # Fail silently
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
    """
    Generates a random math question with proper LaTeX symbols based on the topic and difficulty.
    """
    question, answer = "An error occurred generating a question.", None

    # --- Basic Arithmetic ---
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

    # --- Sets and Operations ---
    elif topic == "sets and operations on sets":
        set_a = set(random.sample(range(1, 15), random.randint(3, 5)))
        set_b = set(random.sample(range(1, 15), random.randint(3, 5)))
        op_choice = random.choice(["union", "intersection", "difference"])
        if difficulty == "Easy": op_choice = random.choice(["union", "intersection"])
        if op_choice == "union":
            question = f"If A = ${set_a}$ and B = ${set_b}$, what is the cardinality of $A \\cup B$ (the union)?"
            answer = len(set_a.union(set_b))
        elif op_choice == "intersection":
            question = f"If A = ${set_a}$ and B = ${set_b}$, what is the cardinality of $A \\cap B$ (the intersection)?"
            answer = len(set_a.intersection(set_b))
        elif op_choice == "difference":
            question = f"If A = ${set_a}$ and B = ${set_b}$, what is the cardinality of $A - B$?"
            answer = len(set_a.difference(set_b))

    # --- Surds ---
    elif topic == "surds":
        if difficulty == "Easy":
            p_sq = random.choice([4, 9, 16, 25]); other = random.choice([2, 3, 5])
            val = p_sq * other
            question = f"Simplify $\\sqrt{{{val}}}$ into the form $a\\sqrt{{b}}$. What is the integer value of 'a'?"
            answer = int(math.sqrt(p_sq))
        elif difficulty == "Medium":
            c1, c2 = random.randint(2, 8), random.randint(2, 8); base = random.choice([2, 3, 5, 7])
            question = f"Calculate ${c1}\\sqrt{{{base}}} + {c2}\\sqrt{{{base}}}$. If the result is $a\\sqrt{{b}}$, what is 'a'?"
            answer = c1 + c2
        elif difficulty == "Hard":
            num = random.randint(2, 9); den_sqrt = random.choice([2, 3, 5, 7])
            question = f"Rationalize the denominator of $\\frac{{{num}}}{{\\sqrt{{{den_sqrt}}}}}$. If the result is $\\frac{{a\\sqrt{{b}}}}{{c}}$, what is $a+b+c$?"
            answer = num + den_sqrt + den_sqrt

    # --- Coordinate Geometry ---
    elif topic == "coordinate geometry":
        x1, y1 = random.randint(-5, 5), random.randint(-5, 5)
        x2, y2 = random.randint(-5, 5), random.randint(-5, 5)
        while x1 == x2 and y1 == y2: x2, y2 = random.randint(-5, 5), random.randint(-5, 5)
        if difficulty == "Easy":
            question = f"What is the midpoint between $({x1}, {y1})$ and $({x2}, {y2})$? Enter the sum of the coordinates (x+y)."
            answer = (x1 + x2) / 2 + (y1 + y2) / 2
        elif difficulty == "Medium":
            question = f"What is the slope of the line between $({x1}, {y1})$ and $({x2}, {y2})$? If it is $\\frac{{a}}{{b}}$, enter $a+b$."
            if x2 - x1 == 0: question, answer = f"A line passes through $({x1}, {y1})$ and $({x2}, {y2})$. What is its slope? (Enter 999 for undefined)", 999
            else:
                num, den = y2 - y1, x2 - x1
                common = math.gcd(num, den)
                a, b = num // common, den // common
                if b < 0: a, b = -a, -b
                answer = a + b
        elif difficulty == "Hard":
            slope = random.randint(-4, 4); y_int = random.randint(-5, 5)
            if slope == 0: slope = 1
            question = f"A line is defined by $y = {slope}x + {y_int}$. What is the slope of a perpendicular line? If it is $-\\frac{{a}}{{b}}$, enter $a+b$."
            num, den = 1, abs(slope)
            common = math.gcd(num, den)
            a, b = num // common, den // common
            answer = a + b
            
    # --- Probability ---
    elif topic == "probabilty":
        if difficulty == "Easy":
            red, blue = random.randint(3, 8), random.randint(3, 8); total = red + blue
            question = f"A bag has {red} red and {blue} blue balls. What is the probability of drawing a red ball? If the answer is $\\frac{{a}}{{b}}$, enter $a+b$."
            common = math.gcd(red, total)
            answer = (red // common) + (total // common)
        elif difficulty == "Medium":
            sides = random.choice([6, 8, 12])
            question = f"On a fair {sides}-sided die, what is the probability of rolling an even number? If the answer is $\\frac{{a}}{{b}}$, enter $a+b$."
            evens = sides // 2; total = sides
            common = math.gcd(evens, total)
            answer = (evens // common) + (total // common)
        elif difficulty == "Hard":
            total, success = 52, 4
            question = f"From a standard deck of {total} cards, what is the probability of drawing an Ace? If the answer is $\\frac{{a}}{{b}}$, enter $a+b$."
            common = math.gcd(success, total)
            answer = (success // common) + (total // common)
            
    # --- Sequence and Series ---
    elif topic == "sequence and series":
        start, diff = random.randint(1, 10), random.randint(2, 5)
        if difficulty == "Easy":
            series = [start + i*diff for i in range(4)]
            question = f"What is the next term in the arithmetic sequence: ${', '.join(map(str, series))}, \\dots$?"
            answer = series[-1] + diff
        elif difficulty == "Medium":
            n = random.randint(8, 12)
            question = f"What is the ${n}^{{th}}$ term of an arithmetic sequence with first term ${start}$ and common difference ${diff}$?"
            answer = start + (n-1)*diff
        elif difficulty == "Hard":
            n = random.randint(5, 8)
            question = f"What is the sum of the first ${n}$ terms of an arithmetic series with first term ${start}$ and common difference ${diff}$?"
            answer = n/2 * (2*start + (n-1)*diff)

    if question == "An error occurred generating a question.":
        question, answer = f"Questions for the topic '{topic}' are under development.", None

    return question, answer

def save_quiz_result(username, topic, score):
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("INSERT INTO quiz_results (username, topic, score) VALUES (?, ?, ?)", (username, topic, score))
        conn.commit()
    except sqlite3.Error:
        pass # Fail silently
    finally:
        if conn:
            conn.close()

# Other data functions (get_top_scores, get_user_quiz_history, etc.) remain the same...

def show_main_app():
    # Inject CSS for styling - this remains the same
    st.markdown("""<style>...</style>""", unsafe_allow_html=True)
    
    # Sidebar remains the same
    with st.sidebar:
        st.title("🧮 MathFriend")
        # ... rest of sidebar ...

    # Page routing
    selected_page = st.sidebar.radio("Go to", ["Dashboard", "Quiz", "Leaderboard", "Chat", "Profile"])

    if selected_page == "Quiz":
        st.header("🧠 Quiz Time!")
        st.markdown("<div class='content-card'>", unsafe_allow_html=True)

        # Initialize session state for the new quiz mode if it doesn't exist
        if 'quiz_active' not in st.session_state:
            st.session_state.quiz_active = False
        
        # --- UI for setting up the quiz ---
        if not st.session_state.quiz_active:
            st.write("Select a topic and difficulty, then start the quiz. Answer as many questions as you like!")
            
            all_topics = ["Addition", "Subtraction", "Multiplication", "Division", "Exponents",
                          "sets and operations on sets", "surds", "coordinate geometry",
                          "probabilty", "sequence and series"]
            
            c1, c2 = st.columns(2)
            with c1:
                st.session_state.topic = st.selectbox("Choose a topic:", all_topics)
            with c2:
                st.session_state.difficulty = st.radio("Choose difficulty:", ["Easy", "Medium", "Hard"], horizontal=True)

            if st.button("Start Endless Quiz", type="primary", use_container_width=True):
                st.session_state.quiz_active = True
                st.session_state.score = 0
                st.session_state.questions_attempted = 0
                st.session_state.current_quiz_question = generate_question(st.session_state.topic, st.session_state.difficulty)
                st.rerun()

        # --- UI for the active "Endless Quiz" ---
        elif st.session_state.quiz_active is True:
            question_text, correct_answer = st.session_state.current_quiz_question
            
            # Display current session score
            st.subheader(f"Current Score: {st.session_state.score} / {st.session_state.questions_attempted}")
            st.markdown("---")

            # Handle case where a question could not be generated for a topic
            if correct_answer is None:
                st.error(question_text)
                if st.button("End Session"):
                    st.session_state.quiz_active = False
                    st.rerun()
                st.stop()

            # Display the question and the answer form
            st.latex(question_text)
            
            # Show feedback from the last answer
            if 'last_answer_feedback' in st.session_state:
                if st.session_state.last_answer_feedback['correct']:
                    st.success(st.session_state.last_answer_feedback['text'])
                else:
                    st.error(st.session_state.last_answer_feedback['text'])

            with st.form(key="quiz_form"):
                user_answer_input = st.number_input("Your Answer:", step=1, value=None, placeholder="Type your answer here...", key="user_answer")
                submitted = st.form_submit_button("Submit Answer")

            # Add a button to stop the quiz session
            if st.button("Stop Quiz & See Results", type="secondary"):
                if st.session_state.questions_attempted > 0:
                    save_quiz_result(st.session_state.username, st.session_state.topic, st.session_state.score)
                st.session_state.quiz_active = "results"
                st.rerun()

            if submitted:
                if user_answer_input is not None:
                    st.session_state.questions_attempted += 1
                    user_answer = float(user_answer_input)
                    is_correct = math.isclose(user_answer, correct_answer, rel_tol=1e-5)
                    
                    if is_correct:
                        st.session_state.score += 1
                        st.session_state.last_answer_feedback = {'correct': True, 'text': 'Correct! 🎉 Here is your next question.'}
                    else:
                        st.session_state.last_answer_feedback = {'correct': False, 'text': f'Not quite. The correct answer was {correct_answer}. Try this one!'}

                    # Generate the next question and rerun the page
                    st.session_state.current_quiz_question = generate_question(st.session_state.topic, st.session_state.difficulty)
                    st.rerun()
                else:
                    st.warning("Please enter an answer.")

        # --- UI for displaying the final results ---
        elif st.session_state.quiz_active == "results":
            st.balloons()
            st.header("Session Complete!")
            
            score = st.session_state.get('score', 0)
            attempted = st.session_state.get('questions_attempted', 0)
            accuracy = (score / attempted * 100) if attempted > 0 else 0
            
            st.markdown(f"### You answered **{score}** out of **{attempted}** questions correctly!")
            st.metric(label="Your Accuracy", value=f"{accuracy:.1f} %")

            if st.button("Start a New Quiz", type="primary", use_container_width=True):
                # Clean up session state to prepare for the next quiz
                for key in ['quiz_active', 'score', 'questions_attempted', 'current_quiz_question', 'last_answer_feedback']:
                    if key in st.session_state:
                        del st.session_state[key]
                st.rerun()

        st.markdown("</div>", unsafe_allow_html=True)

# Main execution block
if __name__ == "__main__":
    # The splash screen and login logic remains the same
    if "show_splash" not in st.session_state: st.session_state.show_splash = True
    if st.session_state.show_splash:
        st.markdown("""<style>.main {visibility: hidden;}</style><div class="splash-container"><div class="splash-text">MathFriend</div></div>""", unsafe_allow_html=True)
        time.sleep(1)
        st.session_state.show_splash = False
        st.rerun()
    else:
        st.markdown("<style>.main {visibility: visible;}</style>", unsafe_allow_html=True)
        if "logged_in" not in st.session_state: st.session_state.logged_in = False
        if "page" not in st.session_state: st.session_state.page = "login"
        if st.session_state.logged_in:
            # This function is a placeholder for the full app UI
            # You would integrate the quiz logic within your actual main app function
            show_main_app() 
        else:
            # This is a placeholder for your login page function
            show_login_page()
