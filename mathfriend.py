import streamlit as st
import sqlite3
import time
import random
import pandas as pd
import plotly.express as px
import re
import hashlib
import math
import base64
import os
from datetime import datetime
from streamlit.components.v1 import html
from fractions import Fraction

# --- App Configuration ---
st.set_page_config(
    layout="wide",
    page_title="MathFriend",
    page_icon="🧮",
    initial_sidebar_state="expanded")

# --- Session State Initialization ---
def initialize_session_state():
    """Initializes all necessary session state variables."""
    defaults = {
        "logged_in": False,
        "page": "login",
        "username": "",
        "show_splash": True,
        "quiz_active": False,
        "quiz_topic": "Sets",
        "quiz_score": 0,
        "questions_answered": 0,
        "onboarding_complete": False,
        "onboarding_step": 0,
        "xp": 0,
        "level": 1,
        "streak": 0,
        "last_login_date": None,
        "badges": []
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value

initialize_session_state()

# --- Database Setup ---
DB_FILE = 'users.db'

def create_and_verify_tables():
    """Creates and verifies all necessary database tables."""
    conn = None
    try:
        conn = sqlite3.connect(DB_FILE, timeout=15)
        c = conn.cursor()
        
        c.execute('''CREATE TABLE IF NOT EXISTS users 
                    (username TEXT PRIMARY KEY, password TEXT, xp INTEGER DEFAULT 0, 
                    level INTEGER DEFAULT 1, streak INTEGER DEFAULT 0, last_login_date TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS quiz_results
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT, topic TEXT, score INTEGER,
                      questions_answered INTEGER, timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        c.execute('''CREATE TABLE IF NOT EXISTS user_profiles
                     (username TEXT PRIMARY KEY, full_name TEXT, school TEXT, age INTEGER, bio TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS user_status
                     (username TEXT PRIMARY KEY, is_online BOOLEAN, last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        c.execute('''CREATE TABLE IF NOT EXISTS user_badges
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT, badge_name TEXT, 
                      badge_icon TEXT, earned_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        c.execute('''CREATE TABLE IF NOT EXISTS daily_challenges
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT, challenge_date TEXT,
                      completed BOOLEAN DEFAULT FALSE, xp_earned INTEGER DEFAULT 0)''')

        c.execute("PRAGMA table_info(quiz_results)")
        quiz_columns = [column[1] for column in c.fetchall()]
        if 'questions_answered' not in quiz_columns:
            c.execute("ALTER TABLE quiz_results ADD COLUMN questions_answered INTEGER DEFAULT 0")

        conn.commit()
        print("Database setup and verification complete.")
    except sqlite3.Error as e:
        st.error(f"Database setup error: {e}")
    finally:
        if conn:
            conn.close()

def bootstrap_database():
    """Checks for the DB file and creates it if it doesn't exist."""
    if not os.path.exists(DB_FILE):
        print("Database file not found, creating and initializing...")
        create_and_verify_tables()
    else:
        print("Database file already exists.")

bootstrap_database()

# --- Core Backend Functions ---
def hash_password(password):
    """Hashes a password using SHA-256 for better performance."""
    salt = "mathfriend_static_salt_for_performance"
    salted_password = password + salt
    return hashlib.sha256(salted_password.encode()).hexdigest()

def check_password(hashed_password, user_password):
    """Checks a password against its SHA-256 hash."""
    return hashed_password == hash_password(user_password)

def login_user(username, password):
    conn = None
    try:
        conn = sqlite3.connect(DB_FILE, timeout=15)
        c = conn.cursor()
        c.execute("SELECT password, xp, level, streak, last_login_date FROM users WHERE username=?", (username,))
        result = c.fetchone()
        if result:
            if check_password(result[0], password):
                today = datetime.now().strftime("%Y-%m-%d")
                last_login = result[4]
                new_streak = result[3]
                
                if last_login:
                    last_date = datetime.strptime(last_login, "%Y-%m-%d").date()
                    current_date = datetime.now().date()
                    if (current_date - last_date).days == 1:
                        new_streak = result[3] + 1
                    elif (current_date - last_date).days > 1:
                        new_streak = 1
                else:
                    new_streak = 1
                
                c.execute("UPDATE users SET last_login_date=?, streak=? WHERE username=?", 
                         (today, new_streak, username))
                conn.commit()
                
                st.session_state.xp = result[1]
                st.session_state.level = result[2]
                st.session_state.streak = new_streak
                
                check_streak_badges(username, new_streak)
                update_user_status(username, True)
                return True
        return False
    finally:
        if conn: conn.close()

def check_streak_badges(username, streak):
    conn = None
    try:
        conn = sqlite3.connect(DB_FILE, timeout=15)
        c = conn.cursor()
        
        streak_badges = {
            3: ("3-Day Streak", "🔥"),
            7: ("7-Day Streak", "🔥🔥"),
            14: ("2-Week Streak", "🔥🔥🔥"),
            30: ("1-Month Streak", "🏆")
        }
        
        for milestone, (badge_name, badge_icon) in streak_badges.items():
            if streak >= milestone:
                c.execute("SELECT 1 FROM user_badges WHERE username=? AND badge_name=?", (username, badge_name))
                if not c.fetchone():
                    c.execute("INSERT INTO user_badges (username, badge_name, badge_icon) VALUES (?, ?, ?)",
                              (username, badge_name, badge_icon))
                    conn.commit()
                    st.session_state.badges.append({"name": badge_name, "icon": badge_icon})
    finally:
        if conn: conn.close()

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
    conn = None
    try:
        conn_check = sqlite3.connect(DB_FILE, timeout=15)
        c_check = conn_check.cursor()
        c_check.execute("SELECT password FROM users WHERE username=?", (username,))
        result = c_check.fetchone()
        conn_check.close()

        if result and check_password(result[0], current_password):
            conn = sqlite3.connect(DB_FILE, timeout=15)
            c = conn.cursor()
            c.execute("UPDATE users SET password=? WHERE username=?", (hash_password(new_password), username))
            conn.commit()
            return True
        return False
    finally:
        if conn: conn.close()


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

def save_quiz_result(username, topic, score, questions_answered):
    conn = None
    try:
        conn = sqlite3.connect(DB_FILE, timeout=15)
        c = conn.cursor()
        c.execute("INSERT INTO quiz_results (username, topic, score, questions_answered) VALUES (?, ?, ?, ?)",
                  (username, topic, score, questions_answered))
        
        xp_earned = score * 10
        if questions_answered > 0 and score/questions_answered > 0.8:
            xp_earned += 20
            
        c.execute("UPDATE users SET xp = xp + ? WHERE username=?", (xp_earned, username))
        
        c.execute("SELECT xp, level FROM users WHERE username=?", (username,))
        xp, level = c.fetchone()
        new_level = xp // 1000 + 1
        if new_level > level:
            c.execute("UPDATE users SET level = ? WHERE username=?", (new_level, username))
            c.execute("INSERT INTO user_badges (username, badge_name, badge_icon) VALUES (?, ?, ?)",
                      (username, f"Level {new_level}", "⭐"))
        
        conn.commit()
        
        st.session_state.xp += xp_earned
        st.session_state.level = new_level
        
        check_quiz_badges(username, topic, score, questions_answered)
    finally:
        if conn: conn.close()

def check_quiz_badges(username, topic, score, questions_answered):
    conn = None
    try:
        conn = sqlite3.connect(DB_FILE, timeout=15)
        c = conn.cursor()
        
        if score == questions_answered and questions_answered >= 5:
            badge_name = f"Perfect Score: {topic}"
            c.execute("SELECT 1 FROM user_badges WHERE username=? AND badge_name=?", (username, badge_name))
            if not c.fetchone():
                c.execute("INSERT INTO user_badges (username, badge_name, badge_icon) VALUES (?, ?, ?)",
                          (username, badge_name, "💯"))
                conn.commit()
                st.session_state.badges.append({"name": badge_name, "icon": "💯"})
        
        c.execute("SELECT COUNT(*) FROM quiz_results WHERE username=? AND topic=? AND score=questions_answered AND questions_answered>=5", 
                 (username, topic))
        perfect_scores = c.fetchone()[0]
        if perfect_scores >= 3:
            badge_name = f"Topic Master: {topic}"
            c.execute("SELECT 1 FROM user_badges WHERE username=? AND badge_name=?", (username, badge_name))
            if not c.fetchone():
                c.execute("INSERT INTO user_badges (username, badge_name, badge_icon) VALUES (?, ?, ?)",
                          (username, badge_name, "🏅"))
                conn.commit()
                st.session_state.badges.append({"name": badge_name, "icon": "🏅"})
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

def get_user_quiz_history(username):
    conn = None
    try:
        conn = sqlite3.connect(DB_FILE, timeout=15)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT topic, score, questions_answered, timestamp FROM quiz_results WHERE username=? ORDER BY timestamp DESC", (username,))
        results = c.fetchall()
        return results
    except sqlite3.Error as e:
        st.error(f"Error fetching quiz history: {e}")
        return []
    finally:
        if conn: conn.close()

def get_user_badges(username):
    conn = None
    try:
        conn = sqlite3.connect(DB_FILE, timeout=15)
        c = conn.cursor()
        c.execute("SELECT badge_name, badge_icon FROM user_badges WHERE username=? ORDER BY earned_date DESC", (username,))
        return [{"name": row[0], "icon": row[1]} for row in c.fetchall()]
    finally:
        if conn: conn.close()

def get_recommended_topics(username):
    """Get recommended topics based on weak areas"""
    conn = None
    try:
        conn = sqlite3.connect(DB_FILE, timeout=15)
        c = conn.cursor()
        
        c.execute("""
            SELECT topic, AVG(CAST(score AS REAL)/questions_answered) as accuracy 
            FROM quiz_results 
            WHERE username=? AND questions_answered > 0 
            GROUP BY topic 
            ORDER BY accuracy ASC 
            LIMIT 3
        """, (username,))
        weak_topics = [row[0] for row in c.fetchall()]
        
        all_topics = ["Sets", "Percentages", "Fractions", "Indices", "Surds", 
                     "Binary Operations", "Relations and Functions", "Sequence and Series", "Word Problems"]
        
        if len(weak_topics) < 3:
            c.execute("SELECT DISTINCT topic FROM quiz_results WHERE username=?", (username,))
            attempted_topics = [row[0] for row in c.fetchall()]
            new_topics = [t for t in all_topics if t not in attempted_topics]
            weak_topics.extend(new_topics[:3-len(weak_topics)])
        
        if len(weak_topics) < 3:
            weak_topics.extend(random.sample(all_topics, 3-len(weak_topics)))
        
        return weak_topics[:3]
    finally:
        if conn: conn.close()

def get_daily_challenge(username):
    """Get today's daily challenge or create one if it doesn't exist"""
    conn = None
    try:
        conn = sqlite3.connect(DB_FILE, timeout=15)
        c = conn.cursor()
        
        today = datetime.now().strftime("%Y-%m-%d")
        c.execute("SELECT * FROM daily_challenges WHERE username=? AND challenge_date=?", (username, today))
        challenge = c.fetchone()
        
        if not challenge:
            topic = random.choice(["Sets", "Percentages", "Fractions", "Indices"])
            c.execute("INSERT INTO daily_challenges (username, challenge_date) VALUES (?, ?)", (username, today))
            conn.commit()
            return {"topic": topic, "completed": False, "xp_earned": 0}
        
        # This part is simplified; in a real app, you'd store the topic in the DB
        return {"topic": "Sets", "completed": challenge[3], "xp_earned": challenge[4]}
    finally:
        if conn: conn.close()

def complete_daily_challenge(username):
    """Mark today's daily challenge as completed"""
    conn = None
    try:
        conn = sqlite3.connect(DB_FILE, timeout=15)
        c = conn.cursor()
        
        today = datetime.now().strftime("%Y-%m-%d")
        c.execute("UPDATE daily_challenges SET completed=TRUE, xp_earned=50 WHERE username=? AND challenge_date=?", 
                 (username, today))
        c.execute("UPDATE users SET xp = xp + 50 WHERE username=?", (username,))
        conn.commit()
        
        st.session_state.xp += 50
    finally:
        if conn: conn.close()

# --- Question Generation Functions ---
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
    return {
        "question": question_text, 
        "options": shuffled_options, 
        "answer": correct_answer, 
        "hint": "Review set operations.",
        "explanation": f"The {operation} of two sets {'combines all elements' if operation == 'union' else 'contains only common elements' if operation == 'intersection' else 'contains elements in A not in B'}"
    }

def _generate_percentages_question():
    q_type = random.choice(['percent_of', 'what_percent', 'original_price'])
    if q_type == 'percent_of':
        percent = random.randint(1, 40) * 5
        number = random.randint(1, 50) * 10
        question_text = f"What is {percent}% of {number}?"
        correct_answer = f"{(percent / 100) * number:.2f}"
        hint = "To find the percent of a number, convert the percent to a decimal (divide by 100) and multiply."
        explanation = f"{percent}% of {number} = {percent/100} × {number} = {correct_answer}"
    elif q_type == 'what_percent':
        part = random.randint(1, 20)
        whole = random.randint(part + 1, 50)
        question_text = f"What percent of {whole} is {part}?"
        correct_answer = f"{(part / whole) * 100:.2f}%"
        hint = "To find what percent a part is of a whole, divide the part by the whole and multiply by 100."
        explanation = f"({part} ÷ {whole}) × 100 = {correct_answer}"
    else:
        original_price = random.randint(20, 200)
        discount_percent = random.randint(1, 8) * 5
        final_price = original_price * (1 - discount_percent/100)
        question_text = f"An item is sold for ${final_price:.2f} after a {discount_percent}% discount. What was the original price?"
        correct_answer = f"${original_price:.2f}"
        hint = "Let the original price be 'P'. The final price is P * (1 - discount/100). Solve for P."
        explanation = f"If {discount_percent}% discount means you pay {100-discount_percent}% of original price. So {100-discount_percent}% of P = {final_price:.2f} ⇒ P = {final_price:.2f} ÷ {1-discount_percent/100:.2f} = {correct_answer}"
    options = [correct_answer]
    while len(options) < 4:
        noise = random.uniform(0.75, 1.25)
        wrong_answer_val = float(re.sub(r'[^\d.]', '', correct_answer)) * noise
        prefix = "$" if correct_answer.startswith("$") else ""
        suffix = "%" if correct_answer.endswith("%") else ""
        new_option = f"{prefix}{wrong_answer_val:.2f}{suffix}"
        if new_option not in options: options.append(new_option)
    random.shuffle(options)
    return {
        "question": question_text, 
        "options": list(set(options)), 
        "answer": correct_answer, 
        "hint": hint,
        "explanation": explanation
    }

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
        hint = "To add or subtract fractions, find a common denominator."
        explanation = f"First find common denominator: LCD = {f1.denominator * f2.denominator // math.gcd(f1.denominator, f2.denominator)}. Then convert and {op_symbol} numerators."
    elif q_type == 'mul_div':
        op_symbol = random.choice(['\\times', '\\div'])
        expression_code = f"{_get_fraction_latex_code(f1)} {op_symbol} {_get_fraction_latex_code(f2)}"
        if op_symbol == '\\div':
            if f2.numerator == 0: f2 = Fraction(1, f2.denominator)
            correct_answer_obj = f1 / f2
            hint = "To divide by a fraction, invert the second fraction and multiply."
            explanation = f"Dividing by a fraction is same as multiplying by its reciprocal: {_get_fraction_latex_code(f1)} × {_get_fraction_latex_code(Fraction(f2.denominator, f2.numerator))}"
        else:
            correct_answer_obj = f1 * f2
            hint = "To multiply fractions, multiply the numerators and denominators."
            explanation = f"Multiply numerators: {f1.numerator} × {f2.numerator} = {f1.numerator*f2.numerator}. Multiply denominators: {f1.denominator} × {f2.denominator} = {f1.denominator*f2.denominator}"
    else: # simplify
        common_factor = random.randint(2, 5)
        unsimplified_f = Fraction(f1.numerator * common_factor, f1.denominator * common_factor)
        expression_code = f"{_get_fraction_latex_code(unsimplified_f)}"
        correct_answer_obj = f1
        hint = "Divide the numerator and denominator by their greatest common divisor."
        explanation = f"GCD of {unsimplified_f.numerator} and {unsimplified_f.denominator} is {common_factor}. Divide both by {common_factor} to simplify."
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
    return {
        "question": question_text, 
        "options": shuffled_options, 
        "answer": correct_answer, 
        "hint": hint,
        "explanation": explanation
    }

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
        explanation = f"$\sqrt{{{num_inside}}} = \sqrt{{{p}×{n}}} = \sqrt{{{p}}}×\sqrt{{{n}}} = {coeff_out}\sqrt{{{n}}}$"
        options = {correct_answer, f"${n}\sqrt{{{coeff_out}}}$", f"$\sqrt{{{num_inside}}}$"}
    else:
        base_surd = random.choice([2, 3, 5])
        c1, c2 = random.randint(1, 5), random.randint(1, 5)
        op = random.choice(['+', '-'])
        question_text = f"Calculate: ${c1}\sqrt{{{base_surd}}} {op} {c2}\sqrt{{{base_surd}}}$"
        result_coeff = c1 + c2 if op == '+' else c1 - c2
        correct_answer = f"${result_coeff}\sqrt{{{base_surd}}}$"
        hint = "You can only add or subtract 'like' surds (surds with the same number under the root)."
        explanation = f"Combine coefficients: {c1} {op} {c2} = {result_coeff}, keep $\sqrt{{{base_surd}}}$"
        options = {correct_answer, f"${c1+c2}\sqrt{{{base_surd*2}}}$", f"${c1*c2}\sqrt{{{base_surd}}}$"}
    while len(options) < 4:
        options.add(f"${random.randint(1,10)}\sqrt{{{random.randint(2,7)}}}$")
    shuffled_options = list(options)
    random.shuffle(shuffled_options)
    return {
        "question": question_text, 
        "options": shuffled_options, 
        "answer": correct_answer, 
        "hint": hint,
        "explanation": explanation
    }

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
    explanation = f"${a} \\oplus {b} = {op_def.split('=')[1].strip().replace('a', str(a)).replace('b', str(b))} = {correct_answer}$"
    options = {correct_answer, str(op_func(b, a)), str(a+b), str(a*b)}
    while len(options) < 4:
        options.add(str(random.randint(1, 100)))
    shuffled_options = list(options)
    random.shuffle(shuffled_options)
    return {
        "question": question_text, 
        "options": shuffled_options, 
        "answer": correct_answer, 
        "hint": hint,
        "explanation": explanation
    }

def _generate_word_problems_question():
    x = random.randint(2, 10)
    k = random.randint(2, 5)
    op_word, op_func_str = random.choice([("tripled", "3*x"), ("doubled", "2*x")])
    adjust_word, adjust_op = random.choice([("added to", "+"), ("subtracted from", "-")])
    
    # Safely evaluate the expression
    def op_func(n): return 3*n if op_word == "tripled" else 2*n
    def adjust_func(n, v): return n + v if adjust_op == "+" else n - v
    
    result = adjust_func(op_func(x), k)
    question_text = f"When a number is {op_word} and {k} is {adjust_word} the result, the answer is {result}. What is the number?"
    correct_answer = str(x)
    hint = "Let the unknown number be 'x'. Translate the sentence into a mathematical equation and solve for x."
    explanation = f"Let x be the number. The equation is `{op_func_str} {adjust_op} {k} = {result}`. Solving for x gives {correct_answer}."
    options = {correct_answer, str(result-k), str(x+k), str(result)}
    while len(options) < 4:
        options.add(str(random.randint(1, 20)))
    shuffled_options = list(options)
    random.shuffle(shuffled_options)
    return {
        "question": question_text, 
        "options": shuffled_options, 
        "answer": correct_answer, 
        "hint": hint,
        "explanation": explanation
    }

def _generate_indices_question():
    q_type = random.choice(['multiply', 'divide', 'power', 'negative', 'fractional'])
    base = random.randint(2, 6)
    if q_type == 'multiply':
        p1, p2 = random.randint(2, 5), random.randint(2, 5)
        question_text = f"Simplify: ${base}^{p1} \\times {base}^{p2}$"
        correct_answer = f"${base}^{p1+p2}$"
        hint = "When multiplying powers with the same base, add the exponents: $x^a \\times x^b = x^{{a+b}}$."
        explanation = f"${base}^{p1} × {base}^{p2} = {base}^{{{p1+p2}}}$ (add exponents)"
        options = {correct_answer, f"${base}^{p1*p2}$", f"${base*2}^{p1+p2}$"}
    elif q_type == 'divide':
        p1, p2 = random.randint(5, 9), random.randint(2, 4)
        question_text = f"Simplify: ${base}^{p1} \\div {base}^{p2}$"
        correct_answer = f"${base}^{p1-p2}$"
        hint = "When dividing powers with the same base, subtract the exponents: $x^a \\div x^b = x^{{a-b}}$."
        explanation = f"${base}^{p1} ÷ {base}^{p2} = {base}^{{{p1-p2}}}$ (subtract exponents)"
        options = {correct_answer, f"${base}^{p1//p2}$", f"$1^{p1-p2}$"}
    elif q_type == 'power':
        p1, p2 = random.randint(2, 4), random.randint(2, 3)
        question_text = f"Simplify: $({base}^{p1})^{p2}$"
        correct_answer = f"${base}^{p1*p2}$"
        hint = "When raising a power to another power, multiply the exponents: $(x^a)^b = x^{{ab}}$."
        explanation = f"$({base}^{p1})^{p2} = {base}^{{{p1*p2}}}$ (multiply exponents)"
        options = {correct_answer, f"${base}^{p1+p2}$", f"${base}^{p1**p2}$"}
    elif q_type == 'negative':
        p1 = random.randint(2, 4)
        question_text = f"Express ${base}^{{-{p1}}}$ as a fraction."
        correct_answer = f"$\\frac{{1}}{{{base**p1}}}$"
        hint = f"A negative exponent means take the reciprocal: $x^{{-a}} = \\frac{{1}}{{x^a}}$."
        explanation = f"${base}^{{-{p1}}} = \\frac{{1}}{{{base}^{p1}}} = \\frac{{1}}{{{base**p1}}}$"
        options = {correct_answer, f"$-{base*p1}$", f"$\\frac{{1}}{{{base*p1}}}$"}
    else: # fractional
        roots = {8: 3, 27: 3, 4: 2, 9: 2, 16: 2, 64: 3, 81: 4}
        num = random.choice(list(roots.keys()))
        root = roots[num]
        exponent_latex = f"\\frac{{1}}{{{root}}}"
        question_text = f"What is the value of ${num}^{{{exponent_latex}}}$?"
        correct_answer = str(int(round(num**(1/root))))
        hint = f"The fractional exponent $\\frac{{1}}{{n}}$ is the same as the n-th root ($\sqrt[n]{{x}}$)."
        explanation = f"${num}^{{\\frac{{1}}{{{root}}}}} = \\sqrt[{root}]{{{num}}} = {correct_answer}$"
        options = {correct_answer, str(num/root), str(num*root)}
    while len(options) < 4:
        options.add(str(random.randint(1, 100)))
    shuffled_options = list(options)
    random.shuffle(shuffled_options)
    return {
        "question": question_text, 
        "options": shuffled_options, 
        "answer": correct_answer, 
        "hint": hint,
        "explanation": explanation
    }

def _generate_relations_functions_question():
    q_type = random.choice(['domain', 'range', 'is_function', 'evaluate'])
    if q_type == 'domain' or q_type == 'range':
        domain_set = set(random.sample(range(1, 10), k=4))
        range_set = set(random.sample(['a', 'b', 'c', 'd', 'e'], k=4))
        relation = str(set(zip(domain_set, range_set))).replace("'", "")
        question_text = f"Given the relation $R = {relation}$, what is its {'domain' if q_type == 'domain' else 'range'}?"
        correct_answer = str(domain_set if q_type == 'domain' else range_set).replace("'", "")
        hint = "The domain is the set of all first elements (x-values). The range is the set of all second elements (y-values)."
        explanation = f"The {'domain' if q_type == 'domain' else 'range'} is all the {'first' if q_type == 'domain' else 'second'} elements: {correct_answer}"
        options = {correct_answer, str(domain_set.union(range_set)).replace("'", "")}
    elif q_type == 'is_function':
        func_relation = str({(1, 'a'), (2, 'b'), (3, 'c')}).replace("'", "")
        not_func_relation = str({(1, 'a'), (1, 'b'), (2, 'c')}).replace("'", "")
        question_text = "Which of the following relations represents a function?"
        correct_answer = str(func_relation)
        hint = "A relation is a function if every input (x-value) maps to exactly one output (y-value). No x-value can be repeated with a different y-value."
        explanation = f"{func_relation} is a function because each input has exactly one output. {not_func_relation} is not a function because input 1 has two different outputs."
        options = {correct_answer, not_func_relation}
    else: # evaluate
        a, b, x = random.randint(2, 5), random.randint(1, 10), random.randint(1, 5)
        question_text = f"If $f(x) = {a}x + {b}$, what is the value of $f({x})$?"
        correct_answer = str(a * x + b)
        hint = "Substitute the value of x into the function definition and calculate the result."
        explanation = f"$f({x}) = {a}×{x} + {b} = {a*x} + {b} = {correct_answer}$"
        options = {correct_answer, str(a + x + b), str(a * (x + b))}
    while len(options) < 4:
        options.add(str(set(random.sample(range(1,10), k=3))).replace("'", ""))
    shuffled_options = list(options)
    random.shuffle(shuffled_options)
    return {
        "question": question_text, 
        "options": shuffled_options, 
        "answer": correct_answer, 
        "hint": hint,
        "explanation": explanation
    }

def _generate_sequence_series_question():
    q_type = random.choice(['ap_term', 'gp_term', 'ap_sum'])
    a = random.randint(1, 5)
    if q_type == 'ap_term':
        d = random.randint(2, 5)
        n = random.randint(5, 10)
        sequence = ", ".join([str(a + i*d) for i in range(4)])
        question_text = f"What is the {n}th term of the arithmetic sequence: {sequence}, ...?"
        correct_answer = str(a + (n - 1) * d)
        hint = f"The formula for the n-th term of an arithmetic progression is $a_n = a_1 + (n-1)d$."
        explanation = f"$a_{n} = {a} + ({n}-1)×{d} = {a} + {(n-1)*d} = {correct_answer}$"
        options = {correct_answer, str(a + n*d), str(a*n + d)}
    elif q_type == 'gp_term':
        r = random.randint(2, 3)
        n = random.randint(4, 6)
        sequence = ", ".join([str(a * r**i) for i in range(3)])
        question_text = f"What is the {n}th term of the geometric sequence: {sequence}, ...?"
        correct_answer = str(a * r**(n-1))
        hint = f"The formula for the n-th term of a geometric progression is $a_n = a_1 \\times r^{{n-1}}$."
        explanation = f"$a_{n} = {a} × {r}^{{{n-1}}} = {correct_answer}$"
        options = {correct_answer, str((a*r)**(n-1)), str(a * r*n)}
    else: # ap_sum
        d = random.randint(2, 5)
        n = random.randint(5, 10)
        question_text = f"What is the sum of the first {n} terms of an arithmetic sequence with first term {a} and common difference {d}?"
        correct_answer = str(int((n/2) * (2*a + (n-1)*d)))
        hint = f"The formula for the sum of the first n terms of an AP is $S_n = \\frac{{n}}{{2}}(2a_1 + (n-1)d)$."
        explanation = f"$S_{n} = \\frac{{{n}}}{{2}}(2×{a} + ({n}-1)×{d}) = \\frac{{{n}}}{{2}}({2*a} + {(n-1)*d}) = {correct_answer}$"
        options = {correct_answer, str(n*(a + (n-1)*d)), str(int((n/2) * (a + (n-1)*d)))}
    while len(options) < 4:
        options.add(str(random.randint(50, 200)))
    shuffled_options = list(options)
    random.shuffle(shuffled_options)
    return {
        "question": question_text, 
        "options": shuffled_options, 
        "answer": correct_answer, 
        "hint": hint,
        "explanation": explanation
    }

def generate_question(topic):
    generators = {
        "Sets": _generate_sets_question,
        "Percentages": _generate_percentages_question,
        "Fractions": _generate_fractions_question,
        "Surds": _generate_surds_question,
        "Binary Operations": _generate_binary_ops_question,
        "Word Problems": _generate_word_problems_question,
        "Indices": _generate_indices_question,
        "Relations and Functions": _generate_relations_functions_question,
        "Sequence and Series": _generate_sequence_series_question,
    }
    generator_func = generators.get(topic)
    if generator_func:
        return generator_func()
    else:
        return {
            "question": f"Questions for **{topic}** are coming soon!", 
            "options": ["OK"], 
            "answer": "OK", 
            "hint": "This topic is under development.",
            "explanation": "We're working hard to add more topics soon!"
        }

# --- UI Components and Animations ---
def confetti_animation():
    html("""<script src="https://cdn.jsdelivr.net/npm/canvas-confetti@1.5.1/dist/confetti.browser.min.js"></script>
    <script>
        confetti({
            particleCount: 150,
            spread: 70,
            origin: { y: 0.6 }
        });
    </script>""")

def load_css():
    """Enhanced CSS with design system and animations"""
    st.markdown("""
    <style>
        :root {
            --primary: #4285F4;
            --secondary: #34A853;
            --accent: #EA4335;
            --warning: #FBBC05;
            --light: #F8F9FA;
            --dark: #202124;
            --gray: #5F6368;
            --border-radius: 12px;
            --shadow: 0 4px 12px rgba(0,0,0,0.08);
        }
        .stApp { background-color: #f0f2f5; font-family: 'Google Sans', Roboto, Arial, sans-serif; }
        h1, h2, h3, h4, h5, h6 { color: var(--dark); font-family: 'Google Sans', Roboto, Arial, sans-serif; }
        .stTextInput input, .stTextArea textarea, .stNumberInput input {
            border: 1px solid #dadce0 !important; border-radius: 8px !important;
            padding: 10px 12px !important; color: var(--dark) !important;
            background-color: white !important; transition: all 0.2s;
        }
        .stTextInput input:focus, .stTextArea textarea:focus, .stNumberInput input:focus {
            border-color: var(--primary) !important;
            box-shadow: 0 0 0 2px rgba(66,133,244,0.2) !important;
        }
        .stButton > button {
            border-radius: var(--border-radius) !important; padding: 0.5rem 1.5rem !important;
            font-weight: 500 !important; transition: all 0.2s !important; border: none !important;
        }
        .stButton > button:hover { transform: translateY(-2px); box-shadow: var(--shadow); }
        .card {
            background: white; border-radius: var(--border-radius); padding: 1.5rem;
            box-shadow: var(--shadow); margin-bottom: 1rem; transition: transform 0.3s, box-shadow 0.3s;
        }
        .card:hover { transform: translateY(-4px); box-shadow: 0 8px 16px rgba(0,0,0,0.12); }
        .progress-container { background: #e9ecef; border-radius: 8px; height: 8px; margin: 1rem 0; }
        .progress-bar { background: var(--primary); height: 100%; border-radius: 8px; transition: width 0.5s ease; }
        .metric-card {
            background: #f8f9fa; border-radius: 12px; padding: 15px;
            border-left: 5px solid var(--primary); margin-bottom: 1rem;
        }
        .login-container {
            background: #ffffff; border-radius: 16px; padding: 2rem 3rem; margin: auto;
            max-width: 450px; box-shadow: 0 8px 32px rgba(0,0,0,0.1);
        }
        .login-title { text-align: center; font-weight: 800; font-size: 2.2rem; color: #1a1a1a; }
        .login-subtitle { text-align: center; color: #6c757d; margin-bottom: 2rem; }
    </style>
    """, unsafe_allow_html=True)

# --- Page Components ---
def display_dashboard(username):
    st.header(f"📈 Dashboard for {username.capitalize()}")
    
    challenge = get_daily_challenge(username)
    if not challenge['completed']:
        with st.container():
            st.markdown(f"""
            <div class="card" style="border-left: 5px solid var(--warning);">
                <h4>🌟 Daily Challenge</h4>
                <p>Complete a quiz on <strong>{challenge['topic']}</strong> to earn 50 XP!</p>
            </div>
            """, unsafe_allow_html=True)
    
    total_quizzes, last_score, top_score = get_user_stats(username)
    
    xp_progress = (st.session_state.xp % 1000) / 10
    st.markdown(f"""
    <div class="card">
        <h4>Your Progress</h4>
        <div style="display: flex; justify-content: space-between; margin-bottom: 0.5rem;">
            <span>Level {st.session_state.level}</span>
            <span>{st.session_state.xp} XP</span>
        </div>
        <div class="progress-container"><div class="progress-bar" style="width: {xp_progress}%;"></div></div>
        <div style="display: flex; gap: 2rem; margin-top: 1rem;">
            <div style="text-align: center;">
                <div style="font-size: 1.5rem; font-weight: bold;">{st.session_state.streak}</div>
                <div style="font-size: 0.8rem; color: var(--gray);">Day Streak</div>
            </div>
            <div style="text-align: center;">
                <div style="font-size: 1.5rem; font-weight: bold;">{total_quizzes}</div>
                <div style="font-size: 0.8rem; color: var(--gray);">Quizzes Taken</div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    badges = get_user_badges(username)
    if badges:
        st.subheader("🎖️ Your Badges")
        cols = st.columns(4)
        for i, badge in enumerate(badges[:8]):
            with cols[i % 4]:
                st.markdown(f"""<div class="card" style="text-align: center;">
                                <div style="font-size: 2rem;">{badge['icon']}</div>
                                <div style="font-size: 0.8rem; font-weight: 500;">{badge['name']}</div>
                             </div>""", unsafe_allow_html=True)

    st.subheader("📚 Continue Learning")
    rec_topics = get_recommended_topics(username)
    cols = st.columns(3)
    for i, topic in enumerate(rec_topics):
        with cols[i]:
            if st.button(topic, key=f"rec_{topic}", use_container_width=True):
                st.session_state.quiz_topic = topic
                st.session_state.page = "Quiz" 
                st.rerun()

    history = get_user_quiz_history(username)
    if history:
        df_data = [{"Topic": row['topic'], "Accuracy": (row['score'] / row['questions_answered'] * 100) if row['questions_answered'] > 0 else 0, 
                   "Date": datetime.strptime(row['timestamp'], "%Y-%m-%d %H:%M:%S").date()} for row in history]
        df = pd.DataFrame(df_data)
        st.subheader("📊 Accuracy Over Time")
        fig = px.line(df, x='Date', y='Accuracy', color='Topic', markers=True, 
                     title="Quiz Performance Trend", template="plotly_white")
        st.plotly_chart(fig, use_container_width=True)

def display_quiz_page(topic_options):
    st.header("🧠 Quiz Time!")
    
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
        progress = st.session_state.questions_answered * 10 
        st.markdown(f"""
        <div style="display: flex; justify-content: space-between; margin-bottom: 0.5rem;">
            <span><strong>Topic:</strong> {st.session_state.quiz_topic}</span>
            <span><strong>Score:</strong> {st.session_state.quiz_score}/{st.session_state.questions_answered}</span>
        </div>
        <div class="progress-container"><div class="progress-bar" style="width: {progress}%;"></div></div>
        """, unsafe_allow_html=True)
        
        if 'current_q_data' not in st.session_state:
            st.session_state.current_q_data = generate_question(st.session_state.quiz_topic)
            st.session_state.show_feedback = False
        
        q_data = st.session_state.current_q_data
        
        st.markdown(f'<h3>{q_data["question"]}</h3>', unsafe_allow_html=True)
            
        with st.form(key=f"quiz_form_{st.session_state.questions_answered}"):
            user_choice = st.radio("Select your answer:", q_data["options"], index=None)
            submit_button = st.form_submit_button("Submit Answer", type="primary", use_container_width=True)

        if submit_button:
            if user_choice is not None:
                st.session_state.questions_answered += 1
                st.session_state.show_feedback = True
                st.session_state.last_answer_correct = str(user_choice) == str(q_data["answer"])
                
                if st.session_state.last_answer_correct:
                    st.session_state.quiz_score += 1
                
                st.rerun()
            else:
                st.warning("Please select an answer before submitting.")
        
        if st.session_state.get("show_feedback"):
            if st.session_state.last_answer_correct:
                st.success(f"🎉 **Correct!**\n\n**Explanation:** {q_data['explanation']}")
                confetti_animation()
            else:
                st.error(f"❌ **Not quite.**\n\n**Correct Answer:** {q_data['answer']}\n\n**Explanation:** {q_data['explanation']}")
            
            if st.button("Next Question", type="secondary", use_container_width=True):
                del st.session_state.current_q_data
                st.session_state.show_feedback = False
                st.rerun()
        
        if st.button("Stop Quiz & Save Score", use_container_width=True):
            if st.session_state.questions_answered > 0:
                save_quiz_result(st.session_state.username, st.session_state.quiz_topic, 
                               st.session_state.quiz_score, st.session_state.questions_answered)
                
                challenge = get_daily_challenge(st.session_state.username)
                if not challenge['completed'] and st.session_state.quiz_topic == challenge['topic']:
                    complete_daily_challenge(st.session_state.username)
                    st.balloons()
                    st.success("🎉 Daily Challenge Completed! +50 XP")
                
                st.info(f"Quiz stopped. Score of {st.session_state.quiz_score}/{st.session_state.questions_answered} saved.")
            
            st.session_state.quiz_active = False
            time.sleep(1)
            st.rerun()

def display_leaderboard(topic_options):
    st.header("🏆 Global Leaderboard")
    leaderboard_topic = st.selectbox("Select a topic to view:", topic_options)
    top_scores = get_top_scores(leaderboard_topic)
    if top_scores:
        leaderboard_data = []
        for rank, (username, score, total) in enumerate(top_scores, 1):
            accuracy = (score / total) * 100 if total > 0 else 0
            leaderboard_data.append({
                "Rank": f"#{rank}", "Username": username,
                "Score": f"{score}/{total}", "Accuracy": f"{accuracy:.1f}%"
            })
        
        df = pd.DataFrame(leaderboard_data)
        
        def highlight_user(row):
            if row['Username'] == st.session_state.username:
                return ['background-color: #e6f7ff; font-weight: bold;'] * len(row)
            return [''] * len(row)
        
        st.dataframe(df.style.apply(highlight_user, axis=1).hide(axis="index"), use_container_width=True)
    else:
        st.info(f"No scores recorded for **{leaderboard_topic}** yet. Be the first!")

def display_learning_resources():
    st.header("📚 Learning Resources")
    with st.expander("🧮 Sets and Operations on Sets", expanded=True):
        st.markdown("""...""") # Add content here
    with st.expander("➗ Percentages"):
        st.markdown("""...""") # Add content here
    with st.expander("½ Fractions"):
        st.markdown("""...""") # Add content here


def display_profile_page():
    st.header("👤 Your Profile")
    
    profile = get_user_profile(st.session_state.username) or {}
    with st.form("profile_form"):
        st.subheader("Edit Profile Information")
        full_name = st.text_input("Full Name", value=profile.get('full_name', ''))
        school = st.text_input("School", value=profile.get('school', ''))
        age = st.number_input("Age", min_value=5, max_value=100, value=profile.get('age', 18))
        bio = st.text_area("Bio", value=profile.get('bio', ''))
        if st.form_submit_button("Save Profile", type="primary"):
            if update_user_profile(st.session_state.username, full_name, school, age, bio):
                st.success("Profile updated successfully!")
                time.sleep(1)
                st.rerun()

    with st.form("password_form"):
        st.subheader("Change Password")
        current_password = st.text_input("Current Password", type="password")
        new_password = st.text_input("New Password", type="password")
        confirm_password = st.text_input("Confirm New Password", type="password")
        if st.form_submit_button("Change Password", type="primary"):
            if new_password != confirm_password:
                st.error("New passwords do not match.")
            elif not current_password or not new_password:
                st.warning("Please fill in all password fields.")
            elif change_password(st.session_state.username, current_password, new_password):
                st.success("Password changed successfully!")
            else:
                st.error("Incorrect current password.")

# --- Main Application Flow ---
def display_login_page():
    """Renders the login and signup forms."""
    st.markdown('<div class="login-container">', unsafe_allow_html=True)
    
    if st.session_state.page == "login":
        st.markdown('<p class="login-title">🔐 MathFriend</p>', unsafe_allow_html=True)
        st.markdown('<p class="login-subtitle">Welcome Back!</p>', unsafe_allow_html=True)
        with st.form("login_form"):
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            if st.form_submit_button("Login", type="primary", use_container_width=True):
                if login_user(username, password):
                    st.session_state.logged_in = True
                    st.session_state.username = username
                    st.rerun()
                else:
                    st.error("Invalid username or password")
        if st.button("Don't have an account? Sign Up", use_container_width=True):
            st.session_state.page = "signup"
            st.rerun()
    else:  # Signup page
        st.markdown('<p class="login-title">Create Account</p>', unsafe_allow_html=True)
        with st.form("signup_form"):
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            confirm_password = st.text_input("Confirm Password", type="password")
            if st.form_submit_button("Create Account", type="primary", use_container_width=True):
                if not username or not password:
                    st.error("All fields are required.")
                elif password != confirm_password:
                    st.error("Passwords do not match.")
                elif signup_user(username, password):
                    st.success("Account created! Please log in.")
                    st.session_state.page = "login"
                    time.sleep(2)
                    st.rerun()
                else:
                    st.error("Username already exists.")
        if st.button("Back to Login", use_container_width=True):
            st.session_state.page = "login"
            st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

def display_main_app():
    """Renders the main application interface for a logged-in user."""
    with st.sidebar:
        st.title(f"Welcome, {st.session_state.username.capitalize()}!")
        page_options = ["Dashboard", "Quiz", "Leaderboard", "Profile", "Learning Resources"]
        st.session_state.page = st.radio("Menu", page_options)
        st.write("---")
        if st.button("Logout", use_container_width=True):
            update_user_status(st.session_state.username, is_online=False)
            # Clear session state on logout
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.rerun()
    
    # Page routing
    topic_options = ["Sets", "Percentages", "Fractions", "Indices", "Surds", 
                     "Binary Operations", "Relations and Functions", "Sequence and Series", "Word Problems"]
    
    if st.session_state.page == "Dashboard":
        display_dashboard(st.session_state.username)
    elif st.session_state.page == "Quiz":
        display_quiz_page(topic_options)
    elif st.session_state.page == "Leaderboard":
        display_leaderboard(topic_options)
    elif st.session_state.page == "Profile":
        display_profile_page()
    elif st.session_state.page == "Learning Resources":
        display_learning_resources()

def main():
    """Main function to control the application flow."""
    load_css()
    if st.session_state.logged_in:
        display_main_app()
    else:
        display_login_page()

if __name__ == "__main__":
    main()
