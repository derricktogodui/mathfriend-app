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
from fractions import Fraction

# Streamlit-specific configuration
st.set_page_config(
    layout="wide",
    page_title="MathFriend",
    page_icon="🧮",
    initial_sidebar_state="expanded"
)

# --- Session State Initialization ---
# Centralize all session state variables here.

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

# MERGED: New quiz-related session state for the dynamic MCQ system
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
        
        # Create users table
        c.execute('''CREATE TABLE IF NOT EXISTS users
                     (username TEXT PRIMARY KEY, password TEXT)''')
                     
        # UPDATED: Added questions_answered column to quiz_results
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
        
        # UPDATED: Check for and add 'questions_answered' column in quiz_results if missing
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


# --- User Authentication Functions --- 
def hash_password(password):
    """Hashes a password using bcrypt."""
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def check_password(hashed_password, user_password):
    """Checks a password against its hash."""
    return bcrypt.checkpw(user_password.encode('utf-8'), hashed_password.encode('utf-8'))

def login_user(username, password):
    """Authenticates a user."""
    conn = None
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
    """Creates a new user account."""
    conn = None
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


# --- Profile Management Functions ---
def get_user_profile(username):
    """Gets a user's profile info"""
    conn = None
    try:
        conn = sqlite3.connect(DB_FILE)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT * FROM user_profiles WHERE username=?", (username,))
        profile = c.fetchone()
        return dict(profile) if profile else None
    except sqlite3.Error as e:
        st.error(f"Get profile error: {e}")
        return None
    finally:
        if conn:
            conn.close()

def update_user_profile(username, full_name, school, age, bio):
    """Updates a user's profile"""
    conn = None
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute('''INSERT OR REPLACE INTO user_profiles 
                     (username, full_name, school, age, bio) 
                     VALUES (?, ?, ?, ?, ?)''', 
                     (username, full_name, school, age, bio))
        conn.commit()
        return True
    except sqlite3.Error as e:
        st.error(f"Profile update error: {e}")
        return False
    finally:
        if conn:
            conn.close()

def change_password(username, current_password, new_password):
    """Changes a user's password"""
    if not login_user(username, current_password):
        return False
    conn = None
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        hashed_password = hash_password(new_password)
        c.execute("UPDATE users SET password=? WHERE username=?", 
                 (hashed_password, username))
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
    """Updates a user's online status"""
    conn = None
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute('''INSERT OR REPLACE INTO user_status (username, is_online) 
                     VALUES (?, ?)''', (username, is_online))
        conn.commit()
    except sqlite3.Error as e:
        st.error(f"Status update error: {e}")
    finally:
        if conn:
            conn.close()

def get_online_users():
    """Returns list of users currently online"""
    conn = None
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        # Consider users online if they've been active in the last 2 minutes
        c.execute("""SELECT username FROM user_status 
                     WHERE is_online = 1 AND 
                     last_seen > datetime('now', '-2 minutes')""")
        return [row[0] for row in c.fetchall()]
    except sqlite3.Error as e:
        st.error(f"Get online users error: {e}")
        return []
    finally:
        if conn:
            conn.close()

def update_typing_status(username, is_typing):
    """Updates a user's typing indicator status"""
    conn = None
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute('''INSERT OR REPLACE INTO typing_indicators 
                     (username, is_typing) VALUES (?, ?)''', 
                     (username, is_typing))
        conn.commit()
    except sqlite3.Error as e:
        st.error(f"Typing status update error: {e}")
    finally:
        if conn:
            conn.close()

def get_typing_users():
    """Returns list of users currently typing"""
    conn = None
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        # Consider typing indicators active for 5 seconds
        c.execute("""SELECT username FROM typing_indicators 
                     WHERE is_typing = 1 AND 
                     timestamp > datetime('now', '-5 seconds')""")
        return [row[0] for row in c.fetchall()]
    except sqlite3.Error as e:
        st.error(f"Get typing users error: {e}")
        return []
    finally:
        if conn:
            conn.close()


# --- MERGED: New Question Generation Logic ---

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

    if q_type == 'percent_of':
        percent = random.randint(1, 40) * 5 # e.g., 5, 10, 15... 200
        number = random.randint(1, 50) * 10 # e.g., 10, 20, 30... 500
        question_text = f"What is {percent}% of {number}?"
        correct_answer = f"{(percent / 100) * number:.2f}"
        hint = "To find the percent of a number, convert the percent to a decimal (divide by 100) and multiply."
    
    elif q_type == 'what_percent':
        part = random.randint(1, 20)
        whole = random.randint(part + 1, 50)
        question_text = f"What percent of {whole} is {part}?"
        correct_answer = f"{(part / whole) * 100:.2f}%"
        hint = "To find what percent a part is of a whole, divide the part by the whole and multiply by 100."

    else: # original_price
        original_price = random.randint(20, 200)
        discount_percent = random.randint(1, 8) * 5 # 5% to 40%
        final_price = original_price * (1 - discount_percent/100)
        question_text = f"An item is sold for ${final_price:.2f} after a {discount_percent}% discount. What was the original price?"
        correct_answer = f"${original_price:.2f}"
        hint = "Let the original price be 'P'. The final price is P * (1 - discount/100). Solve for P."
        
    # Generate distractors
    options = [correct_answer]
    while len(options) < 4:
        # Generate a plausible but incorrect number
        noise = random.uniform(0.75, 1.25)
        wrong_answer_val = float(re.sub(r'[^\d.]', '', correct_answer)) * noise
        prefix = "$" if correct_answer.startswith("$") else ""
        suffix = "%" if correct_answer.endswith("%") else ""
        new_option = f"{prefix}{wrong_answer_val:.2f}{suffix}"
        if new_option not in options:
            options.append(new_option)
    
    random.shuffle(options)
    
    return {"question": question_text, "options": list(set(options)), "answer": correct_answer, "hint": hint}

def _get_fraction_latex_code(f: Fraction):
    """Helper to get the inner LaTeX code for a fraction, WITHOUT dollar signs."""
    if f.denominator == 1:
        return str(f.numerator)
    return f"\\frac{{{f.numerator}}}{{{f.denominator}}}"

def _format_fraction_text(f: Fraction):
    """Helper to format Fraction objects into plain text (e.g., '1/2')."""
    if f.denominator == 1:
        return str(f.numerator)
    return f"{f.numerator}/{f.denominator}"
def _generate_fractions_question():
    q_type = random.choice(['add_sub', 'mul_div', 'simplify'])
    f1 = Fraction(random.randint(1, 10), random.randint(2, 10))
    f2 = Fraction(random.randint(1, 10), random.randint(2, 10))

    # --- THIS ENTIRE SECTION IS REWRITTEN FOR ROBUSTNESS ---
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
            hint = "To multiply fractions, multiply the numerators together and the denominators together."
    else: # simplify
        common_factor = random.randint(2, 5)
        unsimplified_f = Fraction(f1.numerator * common_factor, f1.denominator * common_factor)
        expression_code = f"{_get_fraction_latex_code(unsimplified_f)}"
        correct_answer_obj = f1
        hint = "Find the greatest common divisor (GCD) of the numerator and denominator and divide both by it."

    # Now, wrap the entire expression in ONE SINGLE LaTeX block
    if q_type == 'simplify':
        question_text = f"Simplify the fraction ${expression_code}$ to its lowest terms."
    else:
        question_text = f"Calculate: ${expression_code}$"
    # --- END OF REWRITTEN SECTION ---

    # The options/answer logic remains the same (plain text)
    correct_answer = _format_fraction_text(correct_answer_obj)
    options = {correct_answer}
    while len(options) < 4:
        distractor_f = random.choice([f1 + 1, f2, f1*f2, f1/f2 if f2 !=0 else f1, Fraction(f1.numerator, f2.denominator)])
        options.add(_format_fraction_text(distractor_f))
    
    shuffled_options = list(options)
    random.shuffle(shuffled_options)
    return {"question": question_text, "options": shuffled_options, "answer": correct_answer, "hint": hint}

def _generate_surds_question():
    q_type = random.choice(['simplify', 'operate'])
    
    if q_type == 'simplify':
        perfect_squares = [4, 9, 16, 25]
        non_squares = [2, 3, 5, 6, 7]
        p = random.choice(perfect_squares)
        n = random.choice(non_squares)
        num_inside = p * n
        coeff_out = int(math.sqrt(p))
        
        question_text = f"Simplify $\sqrt{{{num_inside}}}$"
        correct_answer = f"${coeff_out}\sqrt{{{n}}}$"
        hint = f"Look for the largest perfect square that divides {num_inside}. In this case, {p}."
        options = {correct_answer, f"${n}\sqrt{{{coeff_out}}}$", f"$\sqrt{{{num_inside}}}$"}
    
    else: # operate
        base_surd = random.choice([2, 3, 5])
        c1 = random.randint(1, 5)
        c2 = random.randint(1, 5)
        op = random.choice(['+', '-'])
        
        question_text = f"Calculate: ${c1}\sqrt{{{base_surd}}} {op} {c2}\sqrt{{{base_surd}}}$"
        result_coeff = c1 + c2 if op == '+' else c1 - c2
        correct_answer = f"${result_coeff}\sqrt{{{base_surd}}}$"
        hint = "You can only add or subtract 'like' surds, just like you would with variables (e.g., 2x + 3x = 5x)."
        options = {correct_answer, f"${c1+c2}\sqrt{{{base_surd*2}}}$", f"${c1*c2}\sqrt{{{base_surd}}}$"}
        
    while len(options) < 4:
        options.add(f"${random.randint(1,10)}\sqrt{{{random.randint(2,7)}}}$")
        
    shuffled_options = list(options)
    random.shuffle(shuffled_options)
    return {"question": question_text, "options": shuffled_options, "answer": correct_answer, "hint": hint}

def _generate_binary_ops_question():
    a = random.randint(1, 10)
    b = random.randint(1, 10)
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
    
    op_word, op_func = random.choice([
        ("tripled", lambda n: 3*n),
        ("doubled", lambda n: 2*n)
    ])
    adjust_word, adjust_func = random.choice([
        ("added to", lambda n, v: n + v),
        ("subtracted from", lambda n, v: n - v)
    ])
    
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
    """
    Master question generator. Routes to the correct sub-generator based on topic.
    """
    if topic == "Sets":
        return _generate_sets_question()
    elif topic == "Percentages":
        return _generate_percentages_question()
    elif topic == "Fractions":
        return _generate_fractions_question()
    elif topic == "Surds":
        return _generate_surds_question()
    elif topic == "Binary Operations":
        return _generate_binary_ops_question()
    elif topic == "Word Problems":
        return _generate_word_problems_question()
    else:
        # Fallback for topics not yet implemented
        return {
            "question": f"Questions for **{topic}** are coming soon!",
            "options": ["OK"], "answer": "OK",
            "hint": "This topic is under development."
        }


# --- MERGED: UPDATED Quiz and Result Functions ---

def save_quiz_result(username, topic, score, questions_answered):
    """Saves a user's quiz result, including total questions answered."""
    conn = None
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
    conn = None
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
    conn = None
    try:
        conn = sqlite3.connect(DB_FILE)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT topic, score, questions_answered, timestamp FROM quiz_results WHERE username=? ORDER BY timestamp DESC", (username,))
        return c.fetchall()
    except sqlite3.Error as e:
        st.error(f"Get quiz history database error: {e}")
        return []
    finally:
        if conn: conn.close()

def get_user_stats(username):
    """Fetches key statistics for a user's dashboard."""
    conn = None
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM quiz_results WHERE username=?", (username,))
        total_quizzes = c.fetchone()[0]
        
        # Get last score as a fraction
        c.execute("SELECT score, questions_answered FROM quiz_results WHERE username=? ORDER BY timestamp DESC LIMIT 1", (username,))
        last_result = c.fetchone()
        last_score_str = f"{last_result[0]}/{last_result[1]}" if last_result and last_result[1] > 0 else "N/A"
        
        # Get top score based on accuracy
        c.execute("SELECT score, questions_answered FROM quiz_results WHERE username=? AND questions_answered > 0 ORDER BY (CAST(score AS REAL) / questions_answered) DESC, score DESC LIMIT 1", (username,))
        top_result = c.fetchone()
        top_score_str = f"{top_result[0]}/{top_result[1]}" if top_result and top_result[1] > 0 else "N/A"

        return total_quizzes, last_score_str, top_score_str
    except sqlite3.Error as e:
        st.error(f"Get user stats database error: {e}")
        return 0, "N/A", "N/A"
    finally:
        if conn: conn.close()

# --- Chat Functions ---
def add_chat_message(username, message, media=None):
    """Adds a new chat message with optional media to the database."""
    conn = None
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
    conn = None
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
    conn = None
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
        ":smile:": "😊", ":laughing:": "😂", ":thumbsup:": "👍", ":thumbsdown:": "👎",
        ":heart:": "❤️", ":star:": "⭐", ":100:": "💯", ":fire:": "🔥",
        ":thinking:": "🤔", ":nerd:": "🤓"
    }
    for shortcut, emoji in emoji_map.items():
        message = message.replace(shortcut, emoji)

    for user in mentioned_usernames:
        if user == current_user:
            message = re.sub(r'(?i)(@' + re.escape(user) + r')', r'<span class="mention-highlight">\1</span>', message)
    
    return message


# --- MathBot Integration ---
def get_mathbot_response(message):
    """
    Solves a basic math expression or provides a definition from a chat message.
    """
    if not message.startswith("@MathBot"):
        return None

    query = message.replace("@MathBot", "").strip()
    query_lower = query.lower()

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


# --- Modern UI Components ---
def confetti_animation():
    """Displays a confetti animation for achievements"""
    html("""
    <script src="https://cdn.jsdelivr.net/npm/canvas-confetti@1.5.1/dist/confetti.browser.min.js"></script>
    <script>
    function fireConfetti() {
        confetti({
            particleCount: 150,
            spread: 70,
            origin: { y: 0.6 }
        });
    }
    setTimeout(fireConfetti, 100);
    </script>
    """)

def metric_card(title, value, icon, color):
    """Creates a modern metric card"""
    return f"""
    <div style="background: white; border-radius: 12px; padding: 15px; box-shadow: 0 4px 12px rgba(0,0,0,0.05); 
                border-left: 4px solid {color}; margin-bottom: 15px;">
        <div style="display: flex; align-items: center; margin-bottom: 8px;">
            <div style="font-size: 24px; margin-right: 10px;">{icon}</div>
            <div style="font-size: 14px; color: #666;">{title}</div>
        </div>
        <div style="font-size: 28px; font-weight: bold; color: {color};">{value}</div>
    </div>
    """


# --- Page Rendering Logic ---
def show_login_page():
    col1, col2, col3 = st.columns([1, 3, 1])
    with col2:
        st.markdown("""
        <style>
            .login-container {
                background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
                border-radius: 16px;
                padding: 40px;
                box-shadow: 0 8px 32px rgba(31, 38, 135, 0.15);
                backdrop-filter: blur(4px);
                -webkit-backdrop-filter: blur(4px);
                border: 1px solid rgba(255, 255, 255, 0.18);
                text-align: center;
            }
            .login-title {
                background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
                -webkit-background-clip: text;
                background-clip: text;
                color: transparent;
                font-size: 2.2rem;
                font-weight: 800;
                margin-bottom: 10px;
            }
            .login-subtitle {
                color: #475569;
                margin-bottom: 30px;
                font-size: 1rem;
            }
            .stTextInput>div>div>input {
                border-radius: 8px !important;
                padding: 10px 15px !important;
            }
            .login-btn {
                background: linear-gradient(90deg, #667eea 0%, #764ba2 100%) !important;
                border: none !important;
                color: white !important;
                font-weight: 600 !important;
                padding: 12px 24px !important;
                border-radius: 8px !important;
                transition: all 0.3s ease !important;
            }
            .login-btn:hover {
                transform: translateY(-2px);
                box-shadow: 0 5px 15px rgba(102, 126, 234, 0.4) !important;
            }
            .toggle-btn {
                background: transparent !important;
                border: none !important;
                color: #667eea !important;
                font-weight: 500 !important;
            }
            .toggle-btn:hover {
                text-decoration: underline !important;
            }
            .forgot-password {
                text-align: right;
                margin-top: -10px;
                margin-bottom: 15px;
            }
            .forgot-password a {
                color: #666;
                font-size: 0.85rem;
                text-decoration: none;
            }
            .forgot-password a:hover {
                text-decoration: underline;
            }
        </style>
        <div class="login-container">
            <div class="login-title">🔐 MathFriend</div>
            <div class="login-subtitle">Your personal math learning companion</div>
        """, unsafe_allow_html=True)

        # Login form
        if st.session_state.page == "login":
            with st.form("login_form"):
                username = st.text_input("Username", key="login_username")
                password = st.text_input("Password", type="password", key="login_password")
                
                st.markdown('<div class="forgot-password"><a href="#" onclick="window.alert(\'Password reset feature coming soon! For now, please create a new account.\')">Forgot password?</a></div>', unsafe_allow_html=True)
                
                submitted = st.form_submit_button("Login", type="primary")
                
                if submitted:
                    if login_user(username, password):
                        st.session_state.logged_in = True
                        st.session_state.username = username
                        update_user_status(username, True)
                        st.success(f"Welcome back, {username}!")
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.error("Invalid username or password.")
            
            if st.button("Don't have an account? Sign Up", key="signup_button"):
                st.session_state.page = "signup"
                st.rerun()
        
        # Signup form
        else:
            with st.form("signup_form"):
                new_username = st.text_input("New Username", key="signup_username")
                new_password = st.text_input("New Password", type="password", key="signup_password")
                confirm_password = st.text_input("Confirm Password", type="password", key="confirm_password")
                signup_submitted = st.form_submit_button("Create Account", type="primary")

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
        st.markdown("<div style='text-align: center; margin-top: 20px; color: #64748b; font-size: 0.9rem;'>Built with ❤️ by Derrick Kwaku Togodui</div>", unsafe_allow_html=True)

def show_profile_page():
    """Displays the user profile page with editing capabilities"""
    st.header("👤 Your Profile")
    st.markdown("<div class='content-card'>", unsafe_allow_html=True)
    
    update_user_status(st.session_state.username, True)
    
    profile = get_user_profile(st.session_state.username) or {}
    
    with st.form("profile_form"):
        col1, col2 = st.columns(2)
        full_name = col1.text_input("Full Name", value=profile.get('full_name', ''))
        school = col1.text_input("School", value=profile.get('school', ''))
        age = col2.number_input("Age", min_value=5, max_value=100, 
                                 value=profile.get('age', 18))
        bio = col2.text_area("Bio", value=profile.get('bio', ''),
                              help="Tell others about your math interests and goals")
        
        if st.form_submit_button("Save Profile", type="primary"):
            if update_user_profile(st.session_state.username, full_name, school, age, bio):
                st.success("Profile updated successfully!")
                st.rerun()
    
    st.markdown("---")
    st.subheader("Change Password")
    with st.form("password_form"):
        current_password = st.text_input("Current Password", type="password")
        new_password = st.text_input("New Password", type="password",
                                   help="Use at least 8 characters with a mix of letters and numbers")
        confirm_password = st.text_input("Confirm New Password", type="password")
        
        if st.form_submit_button("Change Password", type="primary"):
            if new_password != confirm_password:
                st.error("New passwords don't match!")
            elif change_password(st.session_state.username, current_password, new_password):
                st.success("Password changed successfully!")
            else:
                st.error("Incorrect current password")
    
    st.markdown("</div>", unsafe_allow_html=True)

def show_main_app():
    # Inject modern CSS styles
    st.markdown("""
    <style>
        :root {
            --primary: #4361ee;
            --secondary: #3a0ca3;
            --accent: #4895ef;
            --light: #f8f9fa;
            --dark: #212529;
            --success: #4cc9f0;
            --warning: #f8961e;
            --danger: #f72585;
        }
        
        [data-theme="dark"] {
            --primary: #3a86ff;
            --secondary: #8338ec;
            --accent: #ff006e;
            --light: #212529;
            --dark: #f8f9fa;
        }
        
        .main-content-container {
            background-color: var(--light);
            color: var(--dark);
            padding: 20px;
            border-radius: 12px;
            transition: all 0.3s ease;
        }
        
        .main-title {
            color: var(--primary);
            font-size: 2.5rem;
            margin-bottom: 0.5rem;
            background: linear-gradient(90deg, var(--primary), var(--secondary));
            -webkit-background-clip: text;
            background-clip: text;
            color: transparent;
        }
        
        .content-card {
            background-color: rgba(255, 255, 255, 0.9);
            padding: 20px;
            border-radius: 12px;
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.05);
            margin-bottom: 20px;
            border: 1px solid rgba(0, 0, 0, 0.05);
            transition: transform 0.3s ease, box-shadow 0.3s ease;
        }
        
        .content-card:hover {
            transform: translateY(-3px);
            box-shadow: 0 6px 16px rgba(0, 0, 0, 0.1);
        }
        
        .dashboard-metric-card {
            background-color: white;
            padding: 15px;
            border-radius: 12px;
            box-shadow: 0 2px 8px rgba(0, 0, 0, 0.05);
            text-align: center;
            border-left: 4px solid var(--primary);
        }
        
        .stMetric { font-size: 1.2rem; }
        .stMetric > div > div > div { font-weight: 700 !important; }
        
        .avatar {
            width: 40px; height: 40px; border-radius: 50%; object-fit: cover;
            margin: 0 10px; border: 2px solid white; box-shadow: 0 2px 5px rgba(0,0,0,0.1);
        }
        
        .online-indicator {
            position: absolute; bottom: -2px; right: -2px; width: 12px; height: 12px;
            border-radius: 50%; background-color: #4CAF50; border: 2px solid white;
        }
        
        .mention-highlight {
            font-weight: bold; color: white !important; background-color: var(--accent);
            padding: 2px 6px; border-radius: 6px;
        }
        
        .stButton > button {
            border-radius: 8px !important; padding: 8px 16px !important;
            font-weight: 500 !important; transition: all 0.3s ease !important;
        }
        
        .stButton > button:hover {
            transform: translateY(-2px); box-shadow: 0 4px 8px rgba(0,0,0,0.1) !important;
        }
        
        .sidebar .stRadio > div > label {
            padding: 10px 15px; border-radius: 8px; transition: all 0.3s ease;
        }
        
        .sidebar .stRadio > div > label:hover { background-color: rgba(67, 97, 238, 0.1); }
        
        .typing-indicator {
            display: flex; align-items: center; margin-bottom: 10px;
            color: #666; font-size: 0.9rem;
        }
        
        /* Responsive adjustments */
        @media screen and (max-width: 768px) {
            .main-title { font-size: 1.8rem; }
            .content-card { padding: 15px; }
        }
    </style>
    """, unsafe_allow_html=True)
    
    # Dark mode toggle in sidebar
    if st.session_state.dark_mode:
        st.markdown("""
        <style>
            .main-content-container { background-color: #121212 !important; color: #ffffff !important; }
            .content-card { background-color: #1e1e1e !important; border: 1px solid #333 !important; }
            .dashboard-metric-card { background-color: #1e1e1e !important; }
            .stTextInput>div>div>input, .stTextArea>div>div>textarea {
                background-color: #333 !important; color: white !important; border-color: #555 !important;
            }
        </style>
        """, unsafe_allow_html=True)
    
    with st.sidebar:
        st.session_state.dark_mode = st.toggle("🌙 Dark Mode", value=st.session_state.dark_mode)
    
    # Main content container
    st.markdown(f"<div class='main-content-container'>", unsafe_allow_html=True)
    
    # User greeting with avatar
    avatar_url = get_avatar_url(st.session_state.username)
    profile = get_user_profile(st.session_state.username)
    display_name = profile.get('full_name', st.session_state.username) if profile else st.session_state.username
    
    st.markdown(f"""
    <div style="display: flex; align-items: center; margin-bottom: 20px;">
        <div style="position: relative; display: inline-block;">
            <img src="{avatar_url}" style="width: 60px; height: 60px; border-radius: 50%; margin-right: 15px; border: 3px solid #4361ee;"/>
            <div class="online-indicator"></div>
        </div>
        <div>
            <h1 class="main-title">Welcome back, {display_name}!</h1>
            <p style="color: #666; margin-top: -10px;">Ready to master some math today?</p>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    st.sidebar.markdown("### **Menu**")
    st.sidebar.markdown("---")
    
    selected_page = st.sidebar.radio(
        "Go to", 
        ["📊 Dashboard", "📝 Quiz", "🏆 Leaderboard", "💬 Chat", "👤 Profile", "📚 Learning Resources"],
        label_visibility="collapsed"
    )
    
    st.sidebar.markdown("---")
    st.sidebar.markdown("### **Account**")
    if st.sidebar.button("Logout", type="primary"):
        update_user_status(st.session_state.username, False)  # Mark user as offline
        st.session_state.logged_in = False
        st.session_state.page = "login"
        st.rerun()
    
    update_user_status(st.session_state.username, True)
    
    # Define consistent topic list
    topic_options = ["Sets", "Percentages", "Surds", "Binary Operations", "Word Problems", "Fractions"]
    
    if selected_page == "📊 Dashboard":
        st.markdown("---")
        st.markdown("<div class='content-card'>", unsafe_allow_html=True)
        st.header("📈 Progress Dashboard")
        st.write("Track your math learning journey with these insights.")
        
        total_quizzes, last_score, top_score = get_user_stats(st.session_state.username)
        
        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown(metric_card("Total Quizzes", total_quizzes, "📚", "#4361ee"), unsafe_allow_html=True)
        with col2:
            st.markdown(metric_card("Last Score", last_score, "⭐", "#4cc9f0"), unsafe_allow_html=True)
        with col3:
            st.markdown(metric_card("Top Score", top_score, "🏆", "#f72585"), unsafe_allow_html=True)
        
        st.markdown("<div class='content-card' style='margin-top: 20px;'>", unsafe_allow_html=True)
        st.subheader("🌟 Motivational Quote")
        st.markdown("""
        <blockquote style="border-left: 4px solid #4361ee; padding-left: 15px; font-style: italic; color: #555;">
            "Mathematics is not about numbers, equations, computations, or algorithms: 
            it is about understanding." — William Paul Thurston
        </blockquote>
        """, unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)
        
        user_history = get_user_quiz_history(st.session_state.username)
        if user_history:
            df_data = []
            for row in user_history:
                row_dict = dict(row)
                accuracy = (row_dict['score'] / row_dict['questions_answered']) * 100 if row_dict['questions_answered'] > 0 else 0
                df_data.append({
                    'Topic': row_dict['topic'],
                    'Score': f"{row_dict['score']}/{row_dict['questions_answered']}",
                    'Accuracy': accuracy,
                    'Timestamp': row_dict['timestamp']
                })

            df = pd.DataFrame(df_data)
            df['Timestamp'] = pd.to_datetime(df['Timestamp'])
            df['Date'] = df['Timestamp'].dt.date
            
            st.markdown("<div class='content-card'>", unsafe_allow_html=True)
            st.subheader("📅 Your Accuracy Over Time")
            fig = px.line(df, x='Date', y='Accuracy', color='Topic', 
                          markers=True, template="plotly_white",
                          color_discrete_sequence=px.colors.qualitative.Plotly,
                          labels={'Accuracy': 'Accuracy (%)'})
            fig.update_layout(plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)')
            st.plotly_chart(fig, use_container_width=True)
            st.markdown("</div>", unsafe_allow_html=True)
            
            st.markdown("<div class='content-card'>", unsafe_allow_html=True)
            st.subheader("📊 Average Accuracy by Topic")
            avg_scores = df.groupby('Topic')['Accuracy'].mean().reset_index().sort_values('Accuracy', ascending=False)
            fig_bar = px.bar(avg_scores, x='Topic', y='Accuracy', color='Topic',
                             template="plotly_white", text='Accuracy',
                             color_discrete_sequence=px.colors.qualitative.Pastel)
            fig_bar.update_traces(texttemplate='%{text:.1f}%', textposition='outside')
            fig_bar.update_layout(showlegend=False, plot_bgcolor='rgba(0,0,0,0)', 
                                 paper_bgcolor='rgba(0,0,0,0)', xaxis_title=None)
            st.plotly_chart(fig_bar, use_container_width=True)
            st.markdown("</div>", unsafe_allow_html=True)
        else:
            st.info("Start taking quizzes to see your progress here!")
        
        st.markdown("</div>", unsafe_allow_html=True)

    # --- ###################################################### ---
    # --- ### MERGED: OVERHAULED QUIZ SECTION ### ---
    # --- ###################################################### ---
    # --- ###################################################### ---
    # --- ### DEFINITIVELY CORRECTED QUIZ SECTION ### ---
    # --- ###################################################### ---
    elif selected_page == "📝 Quiz":
        st.header("🧠 Quiz Time!")
        st.markdown("<div class='content-card'>", unsafe_allow_html=True)

        # --- Quiz Setup Screen ---
        if not st.session_state.quiz_active:
            st.write("Select a topic and challenge yourself with unlimited questions!")
            
            st.session_state.quiz_topic = st.selectbox("Choose a topic:", topic_options)
            
            if st.button("Start Quiz", type="primary", use_container_width=True):
                # Initialize quiz state
                st.session_state.quiz_active = True
                st.session_state.quiz_score = 0
                st.session_state.questions_answered = 0
                # Clear any leftover state from previous quizzes
                if 'current_q_data' in st.session_state:
                    del st.session_state['current_q_data']
                if 'user_answer_choice' in st.session_state:
                    del st.session_state['user_answer_choice']
                st.rerun()

        # --- Active Quiz Screen ---
        else:
            st.write(f"**Topic: {st.session_state.quiz_topic}** | **Score: {st.session_state.quiz_score} / {st.session_state.questions_answered}**")
            
            # 1. Check for a stored question in the session state. If not present, generate a new one.
            if 'current_q_data' not in st.session_state:
                st.session_state.current_q_data = generate_question(st.session_state.quiz_topic)
            
            # 2. Use the stored question for this entire script run.
            q_data = st.session_state.current_q_data
            
            # Check for "coming soon" messages
            if "coming soon" in q_data["question"]:
                st.info(q_data["question"])
                st.session_state.quiz_active = False # End quiz if topic is not ready
                del st.session_state.current_q_data # Clean up
                if st.button("Back to Topic Selection"):
                    st.rerun()
            else:
                st.markdown("---")
                st.markdown(q_data["question"], unsafe_allow_html=True)

                with st.expander("🤔 Need a hint?"):
                    st.info(q_data["hint"])

                # 3. The form will now work correctly because q_data is stable across the submit-rerun.
                with st.form(key=f"quiz_form_{st.session_state.questions_answered}"):
                    st.radio(
                        "Select your answer:", 
                        options=q_data["options"], 
                        index=None,
                        key="user_answer_choice" 
                    )
                    
                    submitted = st.form_submit_button("Submit Answer", type="primary")

                    if submitted:
                        user_choice = st.session_state.user_answer_choice
                        
                        if user_choice is not None:
                            st.session_state.questions_answered += 1
                            if str(user_choice) == str(q_data["answer"]):
                                st.session_state.quiz_score += 1
                                st.success("Correct! Well done! 🎉")
                                confetti_animation()
                            else:
                                encouragements = ["Don't give up!", "That was a tricky one. Try again!", "So close! You'll get the next one.", "Every mistake is a step towards learning."]
                                st.error(f"Not quite. The correct answer was: **{q_data['answer']}**")
                                st.warning(random.choice(encouragements))
                            
                            # 4. CRITICAL: After processing the answer, delete the stored question and the radio choice.
                            # This will trigger the generation of a new question on the next rerun.
                            del st.session_state.current_q_data
                            del st.session_state.user_answer_choice
                            
                            time.sleep(1.5) 
                            st.rerun()
                        else:
                            st.warning("Please select an answer before submitting.")

            if st.button("Stop Quiz & Save Score"):
                if st.session_state.questions_answered > 0:
                    save_quiz_result(st.session_state.username, st.session_state.quiz_topic, st.session_state.quiz_score, st.session_state.questions_answered)
                    st.info(f"Quiz stopped. Your final score of {st.session_state.quiz_score}/{st.session_state.questions_answered} has been recorded.")
                else:
                    st.info("Quiz stopped. No questions were answered, so no score was recorded.")
                
                # 5. Clean up all quiz-related state when stopping.
                st.session_state.quiz_active = False
                if 'current_q_data' in st.session_state:
                    del st.session_state.current_q_data
                if 'user_answer_choice' in st.session_state:
                    del st.session_state.user_answer_choice
                
                time.sleep(2)
                st.rerun()

        st.markdown("</div>", unsafe_allow_html=True)

    # --- ###################################################### ---
    # --- ### MERGED: OVERHAULED LEADERBOARD SECTION ### ---
    # --- ###################################################### ---
    elif selected_page == "🏆 Leaderboard":
        st.header("🏆 Global Leaderboard")
        st.markdown("<div class='content-card'>", unsafe_allow_html=True)
        st.write("See who has the highest accuracy for each topic!")
        
        leaderboard_topic = st.selectbox("Select a topic to view:", topic_options)
        
        top_scores = get_top_scores(leaderboard_topic)
        
        if top_scores:
            leaderboard_data = []
            for rank, (username, score, total) in enumerate(top_scores, 1):
                accuracy = (score / total) * 100
                leaderboard_data.append({
                    "Rank": f"#{rank}",
                    "Username": username,
                    "Score": f"{score}/{total}",
                    "Accuracy": accuracy
                })
            
            df = pd.DataFrame(leaderboard_data)
            
            def highlight_user(row):
                if row.Username == st.session_state.username:
                    return ['background-color: #e6f7ff; font-weight: bold;'] * len(row)
                return [''] * len(row)

            st.dataframe(
                df.style.apply(highlight_user, axis=1).format({'Accuracy': "{:.1f}%"}).hide(axis="index"),
                column_config={
                    "Username": st.column_config.TextColumn("User"),
                    "Accuracy": st.column_config.ProgressColumn(
                        "Accuracy",
                        format="%.1f%%",
                        min_value=0,
                        max_value=100,
                    )
                },
                use_container_width=True
            )
        else:
            st.info(f"No scores have been recorded for **{leaderboard_topic}** yet. Be the first!")
        
        st.markdown("</div>", unsafe_allow_html=True)

    elif selected_page == "💬 Chat":
        st.header("💬 Community Chat")

        # --- NEW DISCORD-INSPIRED CSS ---
        st.markdown("""
        <style>
            .chat-frame {
                background-color: #f0f2f5;
                border-radius: 12px;
                height: 75vh;
                display: flex;
                flex-direction: column;
                box-shadow: 0 4px 12px rgba(0,0,0,0.08);
            }

            .message-list {
                flex-grow: 1;
                overflow-y: auto;
                padding: 20px 10px;
                display: flex;
                flex-direction: column;
            }

            /* Custom Scrollbar */
            .message-list::-webkit-scrollbar {
                width: 8px;
            }
            .message-list::-webkit-scrollbar-track {
                background: #f0f2f5;
            }
            .message-list::-webkit-scrollbar-thumb {
                background-color: #c1c1c1;
                border-radius: 10px;
                border: 2px solid #f0f2f5;
            }

            .message-row {
                display: flex;
                align-items: flex-start;
                gap: 10px;
                padding: 8px 10px;
                border-radius: 8px;
                transition: background-color 0.2s;
            }
            
            .message-row:hover {
                background-color: #e9e9eb;
            }

            .avatar-large {
                width: 40px;
                height: 40px;
                border-radius: 50%;
                object-fit: cover;
            }

            .message-content {
                display: flex;
                flex-direction: column;
                gap: 4px;
                width: 100%;
            }

            .message-header {
                display: flex;
                align-items: center;
                gap: 8px;
            }

            .username {
                font-weight: bold;
                color: #1a1a1a;
            }
            
            .timestamp {
                font-size: 0.75rem;
                color: #65676b;
            }
            
            .message-text {
                font-size: 0.95rem;
                color: #050505;
                word-wrap: break-word;
            }
            
            /* Special style for MathBot */
            .mathbot-row .username {
                color: #007aff; /* Blue username for the bot */
            }
            .mathbot-row .message-text {
                background-color: #e7f3ff;
                padding: 8px;
                border-radius: 8px;
                border: 1px solid #cce1f8;
            }

            .chat-image {
                max-width: 300px;
                border-radius: 8px;
                margin-top: 5px;
            }

            /* Styling Streamlit's native form */
            .stForm {
                padding: 15px;
                border-top: 1px solid #ddd;
                background-color: #f0f2f5;
            }
        </style>
        """, unsafe_allow_html=True)

        # --- CHAT UI LAYOUT ---
        with st.container():
            # Build the HTML for all messages
            messages_html_parts = []
            all_messages = get_chat_messages()
            all_usernames = get_all_usernames()
            last_username = None

            for msg in all_messages:
                _, username, message_text, media, timestamp = msg
                time_obj = datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S")
                time_str = time_obj.strftime("%H:%M")
                
                # Show avatar and header only if the user is different from the last one
                is_new_user = (username != last_username)
                
                avatar_url = get_avatar_url(username)
                bot_class = " mathbot-row" if username == "MathBot" else ""
                
                message_html = ""
                # Render header for new user messages
                if is_new_user:
                    message_html += f"""
                        <div class="message-header">
                            <span class="username">{username}</span>
                            <span class="timestamp">{time_str}</span>
                        </div>
                    """
                
                # Render message content
                content_html = ""
                if message_text:
                    formatted_text = format_message(message_text, all_usernames, st.session_state.username)
                    content_html += f"<div class='message-text'>{formatted_text}</div>"
                if media:
                    content_html += f"<div class='message-text'><img src='data:image/png;base64,{media}' class='chat-image'/></div>"

                # If it's a new user, wrap with avatar. If not, just show content.
                if is_new_user:
                    row_html = f"""
                    <div class="message-row{bot_class}">
                        <img src="{avatar_url}" class="avatar-large"/>
                        <div class="message-content">{message_html}{content_html}</div>
                    </div>
                    """
                else:
                    # For consecutive messages, add some left padding to align with previous messages
                    row_html = f"""
                    <div class="message-row{bot_class}" style="padding-left: 50px;">
                        <div class="message-content">{content_html}</div>
                    </div>
                    """
                
                messages_html_parts.append(row_html)
                last_username = username
            
            all_messages_html = "".join(messages_html_parts)

            # Assemble the entire chat panel and render with a single command
            chat_panel_html = f"""
            <div class="chat-frame">
                <div class="message-list" id="message-list">
                    {all_messages_html}
                </div>
            </div>
            """
            st.markdown(chat_panel_html, unsafe_allow_html=True)
            
            # Chat Input Form
            with st.form("chat_form", clear_on_submit=True):
                col1, col2, col3 = st.columns([0.8, 0.1, 0.1])
                with col1:
                    user_message = st.text_input("Message", key="chat_input", placeholder=f"Message as {st.session_state.username}", label_visibility="collapsed")
                with col2:
                    uploaded_file = st.file_uploader("📎", type=["png", "jpg", "jpeg"], label_visibility="collapsed")
                with col3:
                    submitted = st.form_submit_button("➤", type="primary")

                if submitted:
                    if user_message.strip() or uploaded_file:
                        media_data = base64.b64encode(uploaded_file.getvalue()).decode('utf-8') if uploaded_file else None
                        add_chat_message(st.session_state.username, user_message, media_data)
                        if user_message.startswith("@MathBot"):
                            bot_response = get_mathbot_response(user_message)
                            if bot_response:
                                add_chat_message("MathBot", bot_response)
                        st.rerun()
            
            # JavaScript for auto-scrolling
            st.markdown("""
                <script>
                    const messageList = document.getElementById("message-list");
                    if (messageList) {
                        messageList.scrollTop = messageList.scrollHeight;
                    }
                </script>
            """, unsafe_allow_html=True)
            
            # Auto-refresh for real-time feel
            st_autorefresh(interval=3000, key="chat_refresh")

    elif selected_page == "👤 Profile":
        show_profile_page()

    elif selected_page == "📚 Learning Resources":
        st.header("📚 Learning Resources")
        st.markdown("<div class='content-card'>", unsafe_allow_html=True)
        st.write("Mini-tutorials and helpful examples to help you study.")
        
        resource_topic = st.selectbox("Select a topic to learn about:", topic_options)

        if resource_topic == "Sets":
            st.subheader("🧮 Sets and Operations on Sets")
            st.markdown("""
            <div style="background-color: #f8f9fa; padding: 20px; border-radius: 10px; border-left: 4px solid #4361ee;">
                <h4 style="margin-top: 0;">Key Concepts</h4>
                <p>A <strong>set</strong> is a collection of distinct objects. Key operations include:</p>
                <ul>
                    <li><strong>Union ($A \cup B$)**: All elements from both sets combined.</li>
                    <li><strong>Intersection ($A \cap B$)**: Only elements that appear in both sets.</li>
                    <li><strong>Difference ($A - B$)**: Elements in A but not in B.</li>
                </ul>
                <hr>
                <strong>Example:</strong> Let Set $A = \{1, 2, 3\}$ and Set $B = \{3, 4, 5\}$
                <ul>
                    <li>$A \cup B = \{1, 2, 3, 4, 5\}$</li>
                    <li>$A \cap B = \{3\}$</li>
                    <li>$A - B = \{1, 2\}$</li>
                </ul>
            </div>
            """, unsafe_allow_html=True)

        elif resource_topic == "Percentages":
            st.subheader("➗ Percentages")
            st.markdown("""
            <div style="background-color: #f8f9fa; padding: 20px; border-radius: 10px; border-left: 4px solid #4cc9f0;">
                <h4 style="margin-top: 0;">Key Concepts</h4>
                <p>A <strong>percentage</strong> is a number or ratio expressed as a fraction of 100.</p>
                <ul>
                    <li>To find <strong>X% of Y</strong>, calculate $(X/100) * Y$. <br><i>Example: 20% of 50 = (20/100) * 50 = 10</i></li>
                    <li>To find what percentage <strong>A is of B</strong>, calculate $(A/B) * 100$. <br><i>Example: What % is 5 of 20? = (5/20) * 100 = 25%</i></li>
                </ul>
            </div>
            """, unsafe_allow_html=True)

        else:
            st.info(f"Learning resources for **{resource_topic}** are under development.")
        
        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("</div>", unsafe_allow_html=True) # Close main content container


# --- Splash Screen and Main App Logic ---

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
    
    if st.session_state.logged_in:
        show_main_app()
    else:
        show_login_page()








