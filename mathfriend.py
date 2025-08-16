import streamlit as st
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
import numpy as np
import sqlalchemy
from sqlalchemy import create_engine, text

# --- App Configuration ---
st.set_page_config(
    layout="wide",
    page_title="MathFriend",
    page_icon="🧮",
    initial_sidebar_state="expanded"
)

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
        "current_streak": 0,
        "incorrect_questions": [],
        "on_summary_page": False
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value

initialize_session_state()


# --- Database Connection ---
@st.cache_resource
def get_db_engine():
    """Creates a SQLAlchemy engine with a connection pool."""
    db_url = st.secrets["DATABASE_URL"]
    return create_engine(db_url)

engine = get_db_engine()

def create_and_verify_tables():
    """Creates and verifies all necessary database tables in PostgreSQL."""
    try:
        with engine.connect() as conn:
            conn.execute(text('''CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, password TEXT)'''))
            conn.execute(text('''CREATE TABLE IF NOT EXISTS quiz_results
                         (id SERIAL PRIMARY KEY, username TEXT, topic TEXT, score INTEGER,
                          questions_answered INTEGER, timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP)'''))
            conn.execute(text('''CREATE TABLE IF NOT EXISTS user_profiles
                         (username TEXT PRIMARY KEY, full_name TEXT, school TEXT, age INTEGER, bio TEXT)'''))
            conn.execute(text('''CREATE TABLE IF NOT EXISTS user_status
                         (username TEXT PRIMARY KEY, is_online BOOLEAN, last_seen TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP)'''))
            conn.commit()
        print("Database tables created or verified successfully.")
    except Exception as e:
        st.error(f"Database setup error: {e}")

create_and_verify_tables()


# --- Core Backend Functions (PostgreSQL) ---
def hash_password(password):
    salt = "mathfriend_static_salt_for_performance"
    salted_password = password + salt
    return hashlib.sha256(salted_password.encode()).hexdigest()

def check_password(hashed_password, user_password):
    return hashed_password == hash_password(user_password)

def login_user(username, password):
    with engine.connect() as conn:
        result = conn.execute(text("SELECT password FROM users WHERE username = :username"), {"username": username})
        record = result.first()
        if record:
            return check_password(record[0], password)
        return False

def signup_user(username, password):
    try:
        with engine.connect() as conn:
            conn.execute(text("INSERT INTO users (username, password) VALUES (:username, :password)"), 
                         {"username": username, "password": hash_password(password)})
            conn.commit()
        return True
    except sqlalchemy.exc.IntegrityError:
        return False

def get_user_profile(username):
    with engine.connect() as conn:
        result = conn.execute(text("SELECT * FROM user_profiles WHERE username = :username"), {"username": username})
        profile = result.mappings().first()
        return dict(profile) if profile else None

def update_user_profile(username, full_name, school, age, bio):
    with engine.connect() as conn:
        query = text("""
            INSERT INTO user_profiles (username, full_name, school, age, bio) 
            VALUES (:username, :full_name, :school, :age, :bio)
            ON CONFLICT (username) DO UPDATE SET
                full_name = EXCLUDED.full_name, school = EXCLUDED.school,
                age = EXCLUDED.age, bio = EXCLUDED.bio;
        """)
        conn.execute(query, {"username": username, "full_name": full_name, "school": school, "age": age, "bio": bio})
        conn.commit()
    return True

def change_password(username, current_password, new_password):
    if not login_user(username, current_password):
        return False
    with engine.connect() as conn:
        conn.execute(text("UPDATE users SET password = :password WHERE username = :username"),
                     {"password": hash_password(new_password), "username": username})
        conn.commit()
    return True

def update_user_status(username, is_online):
    with engine.connect() as conn:
        query = text("""
            INSERT INTO user_status (username, is_online, last_seen) 
            VALUES (:username, :is_online, CURRENT_TIMESTAMP)
            ON CONFLICT (username) DO UPDATE SET
                is_online = EXCLUDED.is_online, last_seen = CURRENT_TIMESTAMP;
        """)
        conn.execute(query, {"username": username, "is_online": is_online})
        conn.commit()

def save_quiz_result(username, topic, score, questions_answered):
    with engine.connect() as conn:
        conn.execute(text("INSERT INTO quiz_results (username, topic, score, questions_answered) VALUES (:username, :topic, :score, :questions_answered)"),
                     {"username": username, "topic": topic, "score": score, "questions_answered": questions_answered})
        conn.commit()

def get_top_scores(topic, time_filter="all"):
    with engine.connect() as conn:
        time_clause = ""
        if time_filter == "week": time_clause = "AND timestamp >= NOW() - INTERVAL '7 days'"
        elif time_filter == "month": time_clause = "AND timestamp >= NOW() - INTERVAL '30 days'"
        query = text(f"""
            SELECT username, score, questions_answered FROM quiz_results 
            WHERE topic=:topic AND questions_answered > 0 {time_clause}
            ORDER BY (CAST(score AS REAL) / questions_answered) DESC, questions_answered DESC, timestamp ASC LIMIT 10
        """)
        result = conn.execute(query, {"topic": topic})
        return result.fetchall()

def get_user_stats(username):
    with engine.connect() as conn:
        total_quizzes = conn.execute(text("SELECT COUNT(*) FROM quiz_results WHERE username = :username"), {"username": username}).scalar_one()
        last_result = conn.execute(text("SELECT score, questions_answered FROM quiz_results WHERE username = :username ORDER BY timestamp DESC LIMIT 1"), {"username": username}).first()
        last_score_str = f"{last_result[0]}/{last_result[1]}" if last_result and last_result[1] > 0 else "N/A"
        top_result = conn.execute(text("SELECT score, questions_answered FROM quiz_results WHERE username = :username AND questions_answered > 0 ORDER BY (CAST(score AS REAL) / questions_answered) DESC, score DESC LIMIT 1"), {"username": username}).first()
        top_score_str = f"{top_result[0]}/{top_result[1]}" if top_result and top_result[1] > 0 else "N/A"
        return total_quizzes, last_score_str, top_score_str

def get_user_quiz_history(username):
    try:
        with engine.connect() as conn:
            result = conn.execute(text("SELECT topic, score, questions_answered, timestamp FROM quiz_results WHERE username = :username ORDER BY timestamp DESC"), {"username": username})
            return result.mappings().fetchall()
    except Exception as e:
        st.error(f"Error fetching quiz history: {e}")
        return []

def get_topic_performance(username):
    history = get_user_quiz_history(username)
    if not history: return pd.DataFrame()
    df = pd.DataFrame([{"Topic": r['topic'], "Score": r['score'], "Total": r['questions_answered']} for r in history])
    performance = df.groupby('Topic').sum()
    performance['Accuracy'] = (performance['Score'] / performance['Total'] * 100).fillna(0)
    return performance.sort_values(by="Accuracy", ascending=False)

def get_user_rank(username, topic, time_filter="all"):
    """Gets the rank of a specific user for a specific topic based on their best score."""
    with engine.connect() as conn:
        time_clause = ""
        if time_filter == "week": time_clause = "AND timestamp >= NOW() - INTERVAL '7 days'"
        elif time_filter == "month": time_clause = "AND timestamp >= NOW() - INTERVAL '30 days'"
        
        query = text(f"""
            WITH UserBestScores AS (
                SELECT
                    username,
                    score,
                    questions_answered,
                    timestamp,
                    ROW_NUMBER() OVER(
                        PARTITION BY username 
                        ORDER BY (CAST(score AS REAL) / questions_answered) DESC, questions_answered DESC, timestamp ASC
                    ) as rn
                FROM quiz_results
                WHERE topic = :topic AND questions_answered > 0 {time_clause}
            ),
            RankedScores AS (
                SELECT
                    username,
                    RANK() OVER (ORDER BY (CAST(score AS REAL) / questions_answered) DESC, questions_answered DESC, timestamp ASC) as rank
                FROM UserBestScores
                WHERE rn = 1
            )
            SELECT rank FROM RankedScores WHERE username = :username;
        """)
        result = conn.execute(query, {"topic": topic, "username": username}).scalar_one_or_none()
        return result if result else "N/A"

def get_total_players(topic, time_filter="all"):
    """Gets the total number of unique players who have a best score for a topic."""
    with engine.connect() as conn:
        time_clause = ""
        if time_filter == "week": time_clause = "AND timestamp >= NOW() - INTERVAL '7 days'"
        elif time_filter == "month": time_clause = "AND timestamp >= NOW() - INTERVAL '30 days'"
        
        query = text(f"""
            SELECT COUNT(DISTINCT username) 
            FROM quiz_results 
            WHERE topic = :topic AND questions_answered > 0 {time_clause}
        """)
        result = conn.execute(query, {"topic": topic}).scalar_one()
        return result if result else 0

def get_user_stats_for_topic(username, topic):
    with engine.connect() as conn:
        query_best = text("""
            SELECT MAX(CAST(score AS REAL) / questions_answered) * 100 FROM quiz_results 
            WHERE username = :username AND topic = :topic AND questions_answered > 0
        """)
        best_score = conn.execute(query_best, {"username": username, "topic": topic}).scalar_one_or_none() or 0
        query_attempts = text("SELECT COUNT(*) FROM quiz_results WHERE username = :username AND topic = :topic")
        attempts = conn.execute(query_attempts, {"username": username, "topic": topic}).scalar_one()
        return f"{best_score:.1f}%", attempts

def get_top_scores(topic, time_filter="all"):
    """Gets the top 10 scores for a topic, considering only each user's best attempt."""
    with engine.connect() as conn:
        time_clause = ""
        if time_filter == "week": time_clause = "AND timestamp >= NOW() - INTERVAL '7 days'"
        elif time_filter == "month": time_clause = "AND timestamp >= NOW() - INTERVAL '30 days'"
        
        query = text(f"""
            WITH UserBestScores AS (
                SELECT
                    username,
                    score,
                    questions_answered,
                    timestamp,
                    ROW_NUMBER() OVER(
                        PARTITION BY username 
                        ORDER BY (CAST(score AS REAL) / questions_answered) DESC, questions_answered DESC, timestamp ASC
                    ) as rn
                FROM quiz_results
                WHERE topic = :topic AND questions_answered > 0 {time_clause}
            )
            SELECT username, score, questions_answered 
            FROM UserBestScores
            WHERE rn = 1
            ORDER BY (CAST(score AS REAL) / questions_answered) DESC, questions_answered DESC, timestamp ASC 
            LIMIT 10;
        """)
        result = conn.execute(query, {"topic": topic})
        return result.fetchall()

# --- All Question Generation Functions ---

def _generate_sets_question():
    q_type = random.choice(['simple_operation', 'three_set_venn'])
    
    if q_type == 'simple_operation':
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
        hint = "Review the basic set operations: union ($\cup$), intersection ($\cap$), and difference ($-$)."

    elif q_type == 'three_set_venn':
        u = set(range(1, 25))
        set_a = set(random.sample(u, k=random.randint(5, 8)))
        set_b = set(random.sample(u, k=random.randint(5, 8)))
        set_c = set(random.sample(u, k=random.randint(5, 8)))
        
        question_text = f"Given $A = {set_a}$, $B = {set_b}$, and $C = {set_c}$, find the number of elements in $(A \cup B) \cap C$."
        correct_answer = str(len((set_a.union(set_b)).intersection(set_c)))
        
        options = {
            correct_answer,
            str(len(set_a.union(set_b.intersection(set_c)))),
            str(len(set_a.intersection(set_b.intersection(set_c)))),
            str(len(set_a.union(set_b).union(set_c)))
        }
        hint = "First, find the union of sets A and B. Then, find the intersection of that result with set C. Finally, count the elements."
    
    shuffled_options = list(options)
    random.shuffle(shuffled_options)
    return {"question": question_text, "options": shuffled_options, "answer": correct_answer, "hint": hint}

def _generate_percentages_question():
    q_type = random.choice(['percent_of', 'what_percent', 'original_price', 'percent_change'])
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
    elif q_type == 'original_price':
        original_price = random.randint(20, 200)
        discount_percent = random.randint(1, 8) * 5
        final_price = original_price * (1 - discount_percent/100)
        question_text = f"An item is sold for ${final_price:.2f} after a {discount_percent}% discount. What was the original price?"
        correct_answer = f"${original_price:.2f}"
        hint = "Let the original price be 'P'. The final price is P * (1 - discount/100). Solve for P."
    elif q_type == 'percent_change':
        old_value = random.randint(50, 200)
        change_factor = random.choice([random.uniform(0.5, 0.9), random.uniform(1.1, 1.5)])
        new_value = round(old_value * change_factor, 2)
        change_type = "increase" if new_value > old_value else "decrease"
        question_text = f"The price of an item changed from ${old_value} to ${new_value}. What was the percentage {change_type}?"
        percent_change = ((new_value - old_value) / old_value) * 100
        correct_answer = f"{abs(percent_change):.2f}%"
        hint = "The formula for percent change is ((New Value - Old Value) / Old Value) * 100."
    options = [correct_answer]
    while len(options) < 4:
        try:
            correct_val = float(re.sub(r'[^\d.-]', '', correct_answer))
            noise = random.uniform(0.5, 1.5)
            wrong_answer_val = correct_val * noise
            if wrong_answer_val == correct_val: continue
            prefix = "$" if correct_answer.startswith("$") else ""
            suffix = "%" if correct_answer.endswith("%") else ""
            new_option = f"{prefix}{abs(wrong_answer_val):.2f}{suffix}"
            if new_option not in options: options.append(new_option)
        except (ValueError, IndexError):
             options.append(f"{random.randint(1,100):.2f}%")
    random.shuffle(options)
    return {"question": question_text, "options": list(set(options)), "answer": correct_answer, "hint": hint}

def _get_fraction_latex_code(f: Fraction):
    if f.denominator == 1: return str(f.numerator)
    return f"\\frac{{{f.numerator}}}{{{f.denominator}}}"

def _format_fraction_text(f: Fraction):
    if f.denominator == 1: return str(f.numerator)
    return f"{f.numerator}/{f.denominator}"

def _generate_fractions_question():
    q_type = random.choice(['add_sub', 'mul_div', 'simplify', 'mixed_numbers'])
    f1 = Fraction(random.randint(1, 10), random.randint(2, 10))
    f2 = Fraction(random.randint(1, 10), random.randint(2, 10))
    if q_type == 'add_sub':
        op_symbol = random.choice(['+', '-'])
        expression_code = f"{_get_fraction_latex_code(f1)} {op_symbol} {_get_fraction_latex_code(f2)}"
        correct_answer_obj = f1 + f2 if op_symbol == '+' else f1 - f2
        question_text = f"Calculate: ${expression_code}$"
        hint = "To add or subtract fractions, find a common denominator."
    elif q_type == 'mul_div':
        op_symbol = random.choice(['\\times', '\\div'])
        expression_code = f"{_get_fraction_latex_code(f1)} {op_symbol} {_get_fraction_latex_code(f2)}"
        if op_symbol == '\\div':
            if f2.numerator == 0: f2 = Fraction(1, f2.denominator)
            correct_answer_obj = f1 / f2
            hint = "To divide by a fraction, invert the second fraction and multiply."
        else:
            correct_answer_obj = f1 * f2
            hint = "To multiply fractions, multiply the numerators and denominators."
        question_text = f"Calculate: ${expression_code}$"
    elif q_type == 'simplify':
        common_factor = random.randint(2, 5)
        unsimplified_f = Fraction(f1.numerator * common_factor, f1.denominator * common_factor)
        expression_code = f"{_get_fraction_latex_code(unsimplified_f)}"
        correct_answer_obj = f1
        question_text = f"Simplify the fraction ${expression_code}$ to its lowest terms."
        hint = "Divide the numerator and denominator by their greatest common divisor."
    elif q_type == 'mixed_numbers':
        w1, f1 = 1 + f1.numerator // f1.denominator, f1 % 1
        w2, f2 = 1 + f2.numerator // f2.denominator, f2 % 1
        if f1 == 0: f1 = Fraction(1, random.randint(2,5))
        if f2 == 0: f2 = Fraction(1, random.randint(2,5))
        mixed_f1 = w1 + f1
        mixed_f2 = w2 + f2
        correct_answer_obj = mixed_f1 + mixed_f2
        question_text = f"Calculate: ${w1}\\frac{{{f1.numerator}}}{{{f1.denominator}}} + {w2}\\frac{{{f2.numerator}}}{{{f2.denominator}}}$"
        hint = "First, convert the mixed numbers to improper fractions. Then, find a common denominator to add them."
    correct_answer = _format_fraction_text(correct_answer_obj)
    options = {correct_answer}
    while len(options) < 4:
        distractor_f = random.choice([f1 + 1, f2, f1*f2, f1/f2 if f2 !=0 else f1, correct_answer_obj + Fraction(1,2)])
        options.add(_format_fraction_text(distractor_f))
    shuffled_options = list(options)
    random.shuffle(shuffled_options)
    return {"question": question_text, "options": shuffled_options, "answer": correct_answer, "hint": hint}

def _generate_surds_question():
    q_type = random.choice(['simplify', 'operate', 'rationalize'])
    if q_type == 'simplify':
        p = random.choice([4, 9, 16, 25, 36])
        n = random.choice([2, 3, 5, 6, 7])
        num_inside = p * n
        coeff_out = int(math.sqrt(p))
        question_text = f"Simplify $\sqrt{{{num_inside}}}$"
        correct_answer = f"${coeff_out}\sqrt{{{n}}}$"
        hint = f"Look for the largest perfect square that divides {num_inside}."
        options = {correct_answer, f"${n}\sqrt{{{coeff_out}}}$", f"$\sqrt{{{num_inside}}}$"}
    elif q_type == 'operate':
        base_surd = random.choice([2, 3, 5])
        c1, c2 = random.randint(1, 5), random.randint(1, 5)
        op = random.choice(['+', '-'])
        question_text = f"Calculate: ${c1}\sqrt{{{base_surd}}} {op} {c2}\sqrt{{{base_surd}}}$"
        result_coeff = c1 + c2 if op == '+' else c1 - c2
        correct_answer = f"${result_coeff}\sqrt{{{base_surd}}}$"
        hint = "You can only add or subtract 'like' surds (surds with the same number under the root)."
        options = {correct_answer, f"${c1+c2}\sqrt{{{base_surd*2}}}$", f"${c1*c2}\sqrt{{{base_surd}}}$"}
    elif q_type == 'rationalize':
        a = random.randint(2, 9)
        b = random.randint(2, 9)
        c = random.choice([2,3,5,6,7])
        while b*b == c: b = random.randint(2,9) # Ensure b-sqrt(c) isn't an integer
        question_text = f"Rationalize the denominator of $\\frac{{{a}}}{{{b} - \sqrt{{{c}}}}}$"
        # Correct answer is a*(b+sqrt(c)) / (b^2 - c)
        numerator = f"{a*b} + {a}\sqrt{{{c}}}"
        denominator = b**2 - c
        correct_answer = f"$\\frac{{{numerator}}}{{{denominator}}}$"
        hint = "Multiply the numerator and the denominator by the conjugate of the denominator, which is $(b + \sqrt{c})$."
        options = {correct_answer, f"$\\frac{{{a}}}{{{b - c}}}$", f"$\\frac{{{a*b} - {a}\sqrt{{{c}}}}}{{{denominator}}}$"}
    while len(options) < 4:
        options.add(f"${random.randint(1,10)}\sqrt{{{random.randint(2,7)}}}$")
    shuffled_options = list(options)
    random.shuffle(shuffled_options)
    return {"question": question_text, "options": shuffled_options, "answer": correct_answer, "hint": hint}

def _generate_binary_ops_question():
    q_type = random.choice(['simple', 'multi_step'])
    a, b = random.randint(1, 10), random.randint(1, 10)
    op_def, op_func = random.choice([
        ("a \\oplus b = 2a + b", lambda x, y: 2*x + y),
        ("a \\oplus b = a^2 - b", lambda x, y: x**2 - y),
        ("a \\oplus b = ab + a", lambda x, y: x*y + x),
    ])
    if q_type == 'simple':
        question_text = f"Given the binary operation ${op_def}$, what is the value of ${a} \\oplus {b}$?"
        correct_answer = str(op_func(a, b))
        hint = "Substitute the values of 'a' and 'b' into the given definition for the operation."
        options = {correct_answer, str(op_func(b, a)), str(a+b)}
    elif q_type == 'multi_step':
        c = random.randint(1, 5)
        question_text = f"Given the binary operation ${op_def}$, what is the value of $({a} \\oplus {b}) \\oplus {c}$?"
        step1 = op_func(a,b)
        correct_answer = str(op_func(step1, c))
        hint = f"First, calculate the value inside the parentheses, $({a} \\oplus {b})$. Then, use that result as the first number in the second operation."
        options = {correct_answer, str(op_func(a, op_func(b,c))), str(step1 + c)}
    while len(options) < 4:
        options.add(str(random.randint(1, 100)))
    shuffled_options = list(options)
    random.shuffle(shuffled_options)
    return {"question": question_text, "options": shuffled_options, "answer": correct_answer, "hint": hint}

def _generate_word_problems_question():
    q_type = random.choice(['simple_equation', 'age_problem'])
    if q_type == 'simple_equation':
        x = random.randint(2, 10); k = random.randint(2, 5)
        op_word, op_func = random.choice([("tripled", lambda n: 3*n), ("doubled", lambda n: 2*n)])
        adjust_word, adjust_func = random.choice([("added to", lambda n, v: n + v), ("subtracted from", lambda n, v: n - v)])
        result = adjust_func(op_func(x), k)
        question_text = f"When a number is {op_word} and {k} is {adjust_word} the result, the answer is {result}. What is the number?"
        correct_answer = str(x)
        hint = "Let the unknown number be 'x'. Translate the sentence into a mathematical equation and solve for x."
        options = {correct_answer, str(result-k), str(x+k)}
    elif q_type == 'age_problem':
        person_b_age = random.randint(7, 15); multiplier = random.randint(2, 4)
        person_a_age = person_b_age * multiplier
        future_years = random.randint(3, 10)
        person_b_future = person_b_age + future_years
        person_a_future = person_a_age + future_years
        combined_future_age = person_a_future + person_b_future
        person_a_name, person_b_name = random.choice([("Kwame", "Ama"), ("John", "Mary"), ("Ali", "Aisha")])
        question_text = f"{person_a_name} is currently {multiplier} times as old as {person_b_name}. In {future_years} years, the sum of their ages will be {combined_future_age}. How old is {person_b_name} now?"
        correct_answer = str(person_b_age)
        hint = f"Let {person_b_name}'s current age be 'x'. Then {person_a_name}'s age is '{multiplier}x'. In {future_years} years, their ages will be (x + {future_years}) and ({multiplier}x + {future_years}). Set the sum of these equal to {combined_future_age} and solve for x."
        options = {correct_answer, str(person_a_age), str(person_b_future)}
    while len(options) < 4:
        options.add(str(random.randint(1, 50)))
    shuffled_options = list(options)
    random.shuffle(shuffled_options)
    return {"question": question_text, "options": list(set(shuffled_options)), "answer": correct_answer, "hint": hint}

def _generate_indices_question():
    q_type = random.choice(['multiply', 'divide', 'power', 'negative', 'fractional', 'combined'])
    base = random.randint(2, 6)
    if q_type in ['multiply', 'divide', 'power', 'negative', 'fractional']:
        if q_type == 'multiply':
            p1, p2 = random.randint(2, 5), random.randint(2, 5)
            question_text = f"Simplify: ${base}^{p1} \\times {base}^{p2}$"
            correct_answer = f"${base}^{p1+p2}$"
            hint = "When multiplying powers with the same base, add the exponents: $x^a \\times x^b = x^{{a+b}}$."
            options = {correct_answer, f"${base}^{p1*p2}$", f"${base*2}^{p1+p2}$"}
        elif q_type == 'divide':
            p1, p2 = random.randint(5, 9), random.randint(2, 4)
            question_text = f"Simplify: ${base}^{p1} \\div {base}^{p2}$"
            correct_answer = f"${base}^{p1-p2}$"
            hint = "When dividing powers with the same base, subtract the exponents: $x^a \\div x^b = x^{{a-b}}$."
            options = {correct_answer, f"${base}^{p1//p2}$", f"$1^{p1-p2}$"}
        elif q_type == 'power':
            p1, p2 = random.randint(2, 4), random.randint(2, 3)
            question_text = f"Simplify: $({base}^{p1})^{p2}$"
            correct_answer = f"${base}^{p1*p2}$"
            hint = "When raising a power to another power, multiply the exponents: $(x^a)^b = x^{{ab}}$."
            options = {correct_answer, f"${base}^{p1+p2}$", f"${base}^{p1**p2}$"}
        elif q_type == 'negative':
            p1 = random.randint(2, 4)
            question_text = f"Express ${base}^{{-{p1}}}$ as a fraction."
            correct_answer = f"$\\frac{{1}}{{{base**p1}}}$"
            hint = f"A negative exponent means take the reciprocal: $x^{{-a}} = \\frac{{1}}{{x^a}}$."
            options = {correct_answer, f"$-{base*p1}$", f"$\\frac{{1}}{{{base*p1}}}$"}
        else: # fractional
            roots = {8: 3, 27: 3, 4: 2, 9: 2, 16: 2, 64: 3, 81: 4}
            num = random.choice(list(roots.keys())); root = roots[num]
            exponent_latex = f"\\frac{{1}}{{{root}}}"
            question_text = f"What is the value of ${num}^{{{exponent_latex}}}$?"
            correct_answer = str(int(round(num**(1/root))))
            hint = f"The fractional exponent $\\frac{{1}}{{n}}$ is the same as the n-th root ($\sqrt[n]{{x}}$)."
            options = {correct_answer, str(num/root), str(num*root)}
    elif q_type == 'combined':
        p1, p2, p3 = random.randint(2, 5), random.randint(2, 5), random.randint(2, 5)
        question_text = f"Simplify: $\\frac{{{base}^{p1} \\times {base}^{p2}}}{{{base}^{p3}}}$"
        correct_answer = f"${base}^{p1+p2-p3}$"
        hint = "First, simplify the numerator by adding the exponents. Then, simplify the fraction by subtracting the exponents."
        options = {correct_answer, f"${base}^{p1*p2-p3}$", f"${base}^{p1+p2+p3}$"}
    while len(options) < 4:
        options.add(str(random.randint(1, 100)))
    shuffled_options = list(options)
    random.shuffle(shuffled_options)
    return {"question": question_text, "options": shuffled_options, "answer": correct_answer, "hint": hint}

def _generate_relations_functions_question():
    q_type = random.choice(['domain_range', 'is_function', 'evaluate', 'composite'])
    if q_type == 'domain_range':
        sub_type = random.choice(['domain', 'range'])
        domain_set = set(random.sample(range(1, 10), k=4))
        range_set = set(random.sample(['a', 'b', 'c', 'd', 'e'], k=4))
        relation = str(set(zip(domain_set, range_set))).replace("'", "")
        question_text = f"Given the relation $R = {relation}$, what is its {sub_type}?"
        correct_answer = str(domain_set if sub_type == 'domain' else range_set).replace("'", "")
        hint = "The domain is the set of all first elements (x-values). The range is the set of all second elements (y-values)."
        options = {correct_answer, str(domain_set.union(range_set)).replace("'", "")}
    elif q_type == 'is_function':
        func_relation = str({(1, 'a'), (2, 'b'), (3, 'c')}).replace("'", "")
        not_func_relation = str({(1, 'a'), (1, 'b'), (2, 'c')}).replace("'", "")
        question_text = "Which of the following relations represents a function?"
        correct_answer = str(func_relation)
        hint = "A relation is a function if every input (x-value) maps to exactly one output (y-value). No x-value can be repeated with a different y-value."
        options = {correct_answer, not_func_relation}
    elif q_type == 'evaluate':
        a, b, x = random.randint(2, 5), random.randint(1, 10), random.randint(1, 5)
        question_text = f"If $f(x) = {a}x + {b}$, what is the value of $f({x})$?"
        correct_answer = str(a * x + b)
        hint = "Substitute the value of x into the function definition and calculate the result."
        options = {correct_answer, str(a + x + b), str(a * (x + b))}
    elif q_type == 'composite':
        a, b = random.randint(2, 5), random.randint(0, 5)
        c, d = random.randint(2, 5), random.randint(0, 5)
        x_val = random.randint(1,5)
        question_text = f"Given $f(x) = {a}x + {b}$ and $g(x) = {c}x - {d}$, find the value of $f(g({x_val}))$."
        g_of_x = c*x_val - d
        correct_answer = str(a*g_of_x + b)
        hint = f"First, calculate the inner function, $g({x_val})$. Then, use that result as the input for the outer function, $f(x)$."
        options = {correct_answer, str(c*(a*x_val + b) - d), str(g_of_x)}

    while len(options) < 4:
        options.add(str(set(random.sample(range(1,10), k=3))).replace("'", ""))
    shuffled_options = list(options)
    random.shuffle(shuffled_options)
    return {"question": question_text, "options": shuffled_options, "answer": correct_answer, "hint": hint}

def _generate_sequence_series_question():
    q_type = random.choice(['ap_term', 'gp_term', 'ap_sum', 'gp_sum_infinity'])
    a = random.randint(1, 5)
    if q_type == 'ap_term':
        d = random.randint(2, 5); n = random.randint(5, 10)
        sequence = ", ".join([str(a + i*d) for i in range(4)])
        question_text = f"What is the {n}th term of the arithmetic sequence: {sequence}, ...?"
        correct_answer = str(a + (n - 1) * d)
        hint = f"The formula for the n-th term of an arithmetic progression is $a_n = a_1 + (n-1)d$."
        options = {correct_answer, str(a + n*d), str(a*n + d)}
    elif q_type == 'gp_term':
        r = random.randint(2, 3); n = random.randint(4, 6)
        sequence = ", ".join([str(a * r**i) for i in range(3)])
        question_text = f"What is the {n}th term of the geometric sequence: {sequence}, ...?"
        correct_answer = str(a * r**(n-1))
        hint = f"The formula for the n-th term of a geometric progression is $a_n = a_1 \\times r^{{n-1}}$."
        options = {correct_answer, str((a*r)**(n-1)), str(a * r*n)}
    elif q_type == 'ap_sum':
        d = random.randint(2, 5); n = random.randint(5, 10)
        question_text = f"What is the sum of the first {n} terms of an arithmetic sequence with first term {a} and common difference {d}?"
        correct_answer = str(int((n/2) * (2*a + (n-1)*d)))
        hint = f"The formula for the sum of the first n terms of an AP is $S_n = \\frac{{n}}{{2}}(2a_1 + (n-1)d)$."
        options = {correct_answer, str(n*(a + (n-1)*d)), str(int((n/2) * (a + (n-1)*d)))}
    elif q_type == 'gp_sum_infinity':
        r_num = random.randint(1, 4)
        r_den = random.randint(r_num + 1, 9)
        r = Fraction(r_num, r_den)
        question_text = f"Find the sum to infinity of a geometric progression with first term ${a}$ and common ratio $\\frac{{{r.numerator}}}{{{r.denominator}}}$."
        # S_inf = a / (1-r)
        correct_answer_obj = a / (1 - r)
        correct_answer = _format_fraction_text(correct_answer_obj)
        hint = "The sum to infinity of a GP is $S_\\infty = \\frac{{a}}{{1-r}}$, provided $|r| < 1$."
        options = {correct_answer, _format_fraction_text(a / (1+r)), _format_fraction_text(a*r)}

    while len(options) < 4:
        options.add(str(random.randint(50, 200)))
    shuffled_options = list(options)
    random.shuffle(shuffled_options)
    return {"question": question_text, "options": shuffled_options, "answer": correct_answer, "hint": hint}

def _generate_shapes_question():
    q_type = random.choice(['area_rectangle', 'perimeter_triangle', 'volume_cylinder', 'area_circle_reverse', 'complex_surface_area'])
    if q_type == 'area_rectangle':
        l, w = random.randint(5, 20), random.randint(5, 20)
        question_text = f"What is the area of a rectangle with length ${l}$ cm and width ${w}$ cm?"
        correct_answer = str(l * w)
        hint = "The area of a rectangle is length times width ($A = l \\times w$)."
        options = {correct_answer, str(2*l + 2*w), str(l+w)}
    elif q_type == 'perimeter_triangle':
        s1, s2, s3 = random.randint(5, 20), random.randint(5, 20), random.randint(5, 20)
        question_text = f"A triangle has sides of length ${s1}$ cm, ${s2}$ cm, and ${s3}$ cm. What is its perimeter?"
        correct_answer = str(s1 + s2 + s3)
        hint = "The perimeter of a shape is the sum of the lengths of all its sides."
        options = {correct_answer, str(s1*s2), str(max(s1,s2,s3))}
    elif q_type == 'volume_cylinder':
        r, h = random.randint(3, 10), random.randint(5, 15)
        volume = round(math.pi * (r**2) * h)
        question_text = f"What is the volume of a cylinder with a radius of ${r}$ cm and a height of ${h}$ cm? (Use $\pi \approx 3.14$ and round to the nearest whole number)."
        correct_answer = str(volume)
        hint = "The volume of a cylinder is $V = \pi r^2 h$."
        options = {correct_answer, str(round(2 * math.pi * r * h)), str(round(math.pi * r**2))}
    elif q_type == 'area_circle_reverse':
        r = random.randint(5,12)
        area = round((22/7) * r**2)
        question_text = f"The area of a circle is approximately ${area}$ cm$^2$. What is its radius? (Use $\pi \approx \\frac{{22}}{{7}}$)"
        correct_answer = str(r)
        hint = "The area of a circle is $A = \pi r^2$. Rearrange the formula to solve for the radius, $r$."
        options = {correct_answer, str(area/2), str(r*2)}
    elif q_type == 'complex_surface_area':
        l, w, h = random.randint(5,12), random.randint(5,12), random.randint(5,12)
        surface_area = 2*(l*w + l*h + w*h)
        question_text = f"A closed rectangular box has a length of ${l}$ cm, a width of ${w}$ cm, and a height of ${h}$ cm. What is its total surface area?"
        correct_answer = str(surface_area)
        hint = "The total surface area of a rectangular prism is $2(lw + lh + wh)$."
        options = {correct_answer, str(l*w*h), str(l+w+h)}
    while len(options) < 4:
        options.add(str(random.randint(50, 500)))
    shuffled_options = list(options)
    random.shuffle(shuffled_options)
    return {"question": question_text, "options": [str(o) for o in shuffled_options], "answer": correct_answer, "hint": hint}

def _generate_algebra_basics_question():
    q_type = random.choice(['substitution', 'change_subject', 'combined'])
    if q_type == 'substitution':
        x, y = random.randint(2, 6), random.randint(2, 6)
        a, b = random.randint(2, 5), random.randint(2, 5)
        question_text = f"If $x={x}$ and $y={y}$, what is the value of ${a}x + {b}y$?"
        correct_answer = str(a*x + b*y)
        hint = "Substitute the given values for x and y into the expression and evaluate."
        options = {correct_answer, str(a+x+b+y), str((a+b)*(x+y))}
    elif q_type == 'change_subject':
        var_to_make_subject = random.choice(['u', 'a', 't'])
        question_text = f"Make '{var_to_make_subject}' the subject of the formula $v = u + at$."
        if var_to_make_subject == 'u':
            correct_answer = r"$u = v - at$"
            options = {correct_answer, r"$u = v + at$", r"$u = \frac{v}{at}$"}
        elif var_to_make_subject == 'a':
            correct_answer = r"$a = \frac{v-u}{t}$"
            options = {correct_answer, r"$a = v - u - t$", r"$a = \frac{v+u}{t}$"}
        else: # t
            correct_answer = r"$t = \frac{v-u}{a}$"
            options = {correct_answer, r"$t = v - u - a$", r"$t = \frac{v-u}{-a}$"}
        hint = "Use inverse operations to isolate the desired variable on one side of the equation."
    elif q_type == 'combined':
        p, l, w = random.randint(30, 60), random.randint(10, 20), random.randint(5, 10)
        while p != 2*(l+w): p, l, w = random.randint(30, 60), random.randint(10, 20), random.randint(5, 10)
        var_to_make_subject = random.choice(['l', 'w'])
        question_text = f"Given the formula for the perimeter of a rectangle, $P = 2(l+w)$. First, make '${var_to_make_subject}' the subject of the formula. Then, find its value if $P={p}$ and ${'w' if var_to_make_subject == 'l' else 'l'}={w if var_to_make_subject == 'l' else l}$."
        correct_answer = str(l if var_to_make_subject == 'l' else w)
        hint = "First, rearrange the formula to solve for the requested variable. Then, substitute the given values to find the numerical answer."
        options = {correct_answer, str(p/2), str(p-w if var_to_make_subject == 'l' else p-l)}
    while len(options) < 4:
        options.add(str(random.randint(1, 100)))
    shuffled_options = list(options)
    random.shuffle(shuffled_options)
    return {"question": question_text, "options": [str(o) for o in shuffled_options], "answer": correct_answer, "hint": hint}
def _generate_linear_algebra_question():
    q_type = random.choice(['add', 'determinant', 'multiply'])
    mat_a = np.random.randint(-5, 10, size=(2, 2))
    mat_b = np.random.randint(-5, 10, size=(2, 2))
    def mat_to_latex(m):
        return f"\\begin{{pmatrix}} {m[0,0]} & {m[0,1]} \\\\ {m[1,0]} & {m[1,1]} \\end{{pmatrix}}"

    if q_type == 'add':
        question_text = f"Calculate the sum of the matrices $A = {mat_to_latex(mat_a)}$ and $B = {mat_to_latex(mat_b)}$."
        correct_mat = mat_a + mat_b
        correct_answer = f"${mat_to_latex(correct_mat)}$"
        hint = "To add two matrices, add their corresponding elements."
        options = {correct_answer, f"${mat_to_latex(mat_a - mat_b)}$", f"${mat_to_latex(mat_a * 2)}$"}
    elif q_type == 'determinant':
        question_text = f"Find the determinant of the matrix $A = {mat_to_latex(mat_a)}$."
        correct_answer = str(int(np.linalg.det(mat_a)))
        hint = "The determinant of a 2x2 matrix $\\begin{pmatrix} a & b \\\\ c & d \\end{pmatrix}$ is $ad - bc$."
        options = {correct_answer, str(mat_a[0,0]+mat_a[1,1]), str(mat_a[0,1]+mat_a[1,0])}
    elif q_type == 'multiply':
        question_text = f"Calculate the product of the matrices $A = {mat_to_latex(mat_a)}$ and $B = {mat_to_latex(mat_b)}$."
        correct_mat = np.dot(mat_a, mat_b)
        correct_answer = f"${mat_to_latex(correct_mat)}$"
        hint = "Matrix multiplication involves taking the dot product of rows from the first matrix and columns from the second matrix."
        options = {correct_answer, f"${mat_to_latex(mat_a + mat_b)}$", f"${mat_to_latex(np.transpose(correct_mat))}$"}

    while len(options) < 4:
        # Add a fallback for the determinant case, which doesn't produce LaTeX options
        if q_type == 'determinant':
            options.add(str(random.randint(-20, 20)))
        else:
            options.add(f"${mat_to_latex(np.random.randint(-5, 10, size=(2,2)))}$")
            
    shuffled_options = list(options)
    random.shuffle(shuffled_options)
    return {"question": question_text, "options": [str(o) for o in shuffled_options], "answer": str(correct_answer), "hint": hint}

def generate_question(topic):
    generators = {
        "Sets": _generate_sets_question,
        "Percentages": _generate_percentages_question,
        "Fractions": _generate_fractions_question,
        "Indices": _generate_indices_question,
        "Surds": _generate_surds_question,
        "Binary Operations": _generate_binary_ops_question,
        "Relations and Functions": _generate_relations_functions_question,
        "Sequence and Series": _generate_sequence_series_question,
        "Word Problems": _generate_word_problems_question,
        "Shapes (Geometry)": _generate_shapes_question,
        "Algebra Basics": _generate_algebra_basics_question,
        "Linear Algebra": _generate_linear_algebra_question,
    }
    generator_func = generators.get(topic)
    if generator_func:
        return generator_func()
    else:
        return {"question": f"Questions for **{topic}** are coming soon!", "options": ["OK"], "answer": "OK", "hint": "This topic is under development."}

def confetti_animation():
    html("""<script src="https://cdn.jsdelivr.net/npm/canvas-confetti@1.5.1/dist/confetti.browser.min.js"></script><script>confetti();</script>""")

def get_time_based_greeting():
    current_hour = datetime.now().hour
    if 5 <= current_hour < 12: return "Good morning"
    elif 12 <= current_hour < 18: return "Good afternoon"
    else: return "Good evening"

def load_css():
    """Loads the main CSS for the application for a consistent and responsive look."""
    st.markdown("""
    <style>
        .stApp { background-color: #f0f2f5; }
        [data-testid="stAppViewContainer"] > .main { display: flex; justify-content: center; align-items: center; }
        div[data-testid="stAppViewContainer"] * { color: #31333F !important; }
        div[data-testid="stSidebarUserContent"] * { color: #FAFAFA !important; }
        div[data-testid="stSidebarUserContent"] h1 { color: #FFFFFF !important; }
        div[data-testid="stSidebarUserContent"] [data-testid="stRadio"] label { color: #E0E0E0 !important; }
        div[data-testid="stSidebarUserContent"] hr { border-color: #444955 !important; }
        button[data-testid="stFormSubmitButton"] *, div[data-testid="stButton"] > button * { color: white !important; }
        a, a * { color: #0068c9 !important; }
        .main-content h1, .main-content h2, .main-content h3, .main-content h4, .main-content h5, .main-content h6 { color: #1a1a1a !important; }
        [data-testid="stMetricValue"] { color: #1a1a1a !important; }
        [data-testid="stSuccess"] * { color: #155724 !important; }
        [data-testid="stInfo"] * { color: #0c5460 !important; }
        [data-testid="stWarning"] * { color: #856404 !important; }
        [data-testid="stError"] * { color: #721c24 !important; }
        .main-content h1, .main-content h2, .main-content h3 { border-left: 5px solid #0d6efd; padding-left: 15px; border-radius: 3px; }
        [data-testid="stMetric"] { background-color: #FFFFFF; border: 1px solid #CCCCCC; padding: 20px; border-radius: 10px; box-shadow: 0 4px 8px rgba(0,0,0,0.1); border-left: 5px solid #CCCCCC; }
        [data-testid="stHorizontalBlock"] > div:nth-of-type(1) [data-testid="stMetric"] { border-left-color: #0d6efd; }
        [data-testid="stHorizontalBlock"] > div:nth-of-type(2) [data-testid="stMetric"] { border-left-color: #28a745; }
        [data-testid="stHorizontalBlock"] > div:nth-of-type(3) [data-testid="stMetric"] { border-left-color: #ffc107; }
        .stTextInput input, .stTextArea textarea, .stNumberInput input { color: #000 !important; background-color: #fff !important; }
        button[data-testid="stFormSubmitButton"] { background-color: #0d6efd; border: 1px solid #0d6efd; box-shadow: 0 4px 8px rgba(0,0,0,0.1); transition: all 0.2s ease-in-out; }
        button[data-testid="stFormSubmitButton"]:hover { background-color: #0b5ed7; border-color: #0a58ca; transform: translateY(-2px); box-shadow: 0 6px 12px rgba(0,0,0,0.15); }
        div[data-testid="stButton"] > button { background-color: #6c757d; border: 1px solid #6c757d; }
        div[data-testid="stButton"] > button:hover { background-color: #5a6268; border-color: #545b62; }
        [data-testid="stSelectbox"] div[data-baseweb="select"] > div { background-color: #fff !important; }
        .stDataFrame th { background-color: #e9ecef; font-weight: bold; }
        [data-testid="stForm"] { border: 1px solid #dee2e6; border-radius: 0.5rem; padding: 1.5rem; background-color: #fafafa; }
        .styled-hr { border: none; height: 2px; background: linear-gradient(to right, #0d6efd, #f0f2f5); margin: 2rem 0; }
        .login-container { background: #ffffff; border-radius: 16px; padding: 2rem 3rem; margin: auto; max-width: 450px; box-shadow: 0 8px 32px rgba(0,0,0,0.1); }
        .login-title { text-align: center; font-weight: 800; font-size: 2.2rem; color: #1a1a1a !important; }
        .login-subtitle { text-align: center; color: #6c757d !important; margin-bottom: 2rem; }
        .main-content { background-color: #ffffff; padding: 2rem; border-radius: 12px; box-shadow: 0 4px 12px rgba(0,0,0,0.08); }
        @media (max-width: 640px) { .main-content, .login-container { padding: 1rem; } .login-title { font-size: 1.8rem; } }
    </style>
    """, unsafe_allow_html=True)

def display_dashboard(username):
    st.header(f"📈 Dashboard for {username}")
    tab1, tab2 = st.tabs(["📊 Performance Overview", "📜 Full History"])
    with tab1:
        st.subheader("Key Metrics")
        total_quizzes, last_score, top_score = get_user_stats(username)
        col1, col2, col3 = st.columns(3)
        with col1: st.metric(label="📝 Total Quizzes Taken", value=total_quizzes)
        with col2: st.metric(label="🎯 Most Recent Score", value=last_score)
        with col3: st.metric(label="🏆 Best Ever Score", value=top_score)
        st.markdown("<hr class='styled-hr'>", unsafe_allow_html=True)
        st.subheader("Topic Performance")
        topic_perf_df = get_topic_performance(username)
        if not topic_perf_df.empty:
            col1, col2 = st.columns(2)
            with col1:
                best_topic = topic_perf_df.index[0]; best_acc = topic_perf_df['Accuracy'].iloc[0]
                st.success(f"💪 **Strongest Topic:** {best_topic} ({best_acc:.1f}%)")
            with col2:
                if len(topic_perf_df) > 1:
                    worst_topic = topic_perf_df.index[-1]; worst_acc = topic_perf_df['Accuracy'].iloc[-1]
                    st.warning(f"🤔 **Area for Practice:** {worst_topic} ({worst_acc:.1f}%)")
            fig = px.bar(
                topic_perf_df, y='Accuracy', title="Average Accuracy by Topic",
                labels={'Accuracy': 'Accuracy (%)', 'Topic': 'Topic'}, text_auto='.2s'
            )
            fig.update_traces(textposition='outside')
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Complete some quizzes to see your topic performance analysis!")
    with tab2:
        st.subheader("Accuracy Over Time")
        history = get_user_quiz_history(username)
        if history:
            df_data = [{"Topic": r['topic'], "Score": f"{r['score']}/{r['questions_answered']}", "Accuracy (%)": (r['score'] / r['questions_answered'] * 100) if r['questions_answered'] is not None and r['score'] is not None and r['questions_answered'] > 0 else 0, "Date": r['timestamp'].strftime("%Y-%m-%d %H:%M")} for r in history]
            df = pd.DataFrame(df_data)
            line_fig = px.line(df, x='Date', y='Accuracy (%)', color='Topic', markers=True, title="Quiz Performance Trend")
            st.plotly_chart(line_fig, use_container_width=True)
            st.dataframe(df, use_container_width=True)
        else:
            st.info("Your quiz history is empty. Take a quiz to get started!")

def display_quiz_page(topic_options):
    st.header("🧠 Quiz Time!")
    QUIZ_LENGTH = 10
    if not st.session_state.quiz_active:
        st.subheader("Choose Your Challenge")
        topic_perf_df = get_topic_performance(st.session_state.username)
        if not topic_perf_df.empty and topic_perf_df['Accuracy'].iloc[-1] < 100:
            weakest_topic = topic_perf_df.index[-1]
            st.info(f"💡 **Practice Suggestion:** Your lowest accuracy is in **{weakest_topic}**. Why not give it a try?")
        selected_topic = st.selectbox("Select a topic to begin:", topic_options)
        st.session_state.quiz_topic = selected_topic 
        st.markdown("<hr class='styled-hr'>", unsafe_allow_html=True)
        col1, col2 = st.columns(2)
        with col1:
            best_score, attempts = get_user_stats_for_topic(st.session_state.username, selected_topic)
            st.metric("Your Best Score on this Topic", best_score)
            st.metric("Quizzes Taken on this Topic", attempts)
        with col2:
            st.write("") 
            st.write("")
            if st.button("Start Quiz", type="primary", use_container_width=True, key="start_quiz_main"):
                st.session_state.quiz_active = True; st.session_state.on_summary_page = False
                st.session_state.quiz_score = 0; st.session_state.questions_answered = 0
                st.session_state.current_streak = 0; st.session_state.incorrect_questions = []
                if 'current_q_data' in st.session_state: del st.session_state['current_q_data']
                st.rerun()
    else:
        if st.session_state.get('on_summary_page', False):
            display_quiz_summary(); return
        if st.session_state.questions_answered >= QUIZ_LENGTH:
            st.session_state.on_summary_page = True; st.rerun()
        col1, col2, col3 = st.columns(3)
        with col1: st.metric("Score", f"{st.session_state.quiz_score}/{st.session_state.questions_answered}")
        with col2: st.metric("Question", f"{st.session_state.questions_answered + 1}/{QUIZ_LENGTH}")
        with col3: st.metric("🔥 Streak", st.session_state.current_streak)
        st.progress(st.session_state.questions_answered / QUIZ_LENGTH, text="Round Progress")
        st.markdown("<hr class='styled-hr'>", unsafe_allow_html=True)
        if 'current_q_data' not in st.session_state:
            st.session_state.current_q_data = generate_question(st.session_state.quiz_topic)
        q_data = st.session_state.current_q_data
        st.subheader(f"Topic: {st.session_state.quiz_topic}")
        st.markdown(q_data["question"], unsafe_allow_html=True)
        with st.expander("🤔 Need a hint?"): st.info(q_data["hint"])
        with st.form(key=f"quiz_form_{st.session_state.questions_answered}"):
            user_choice = st.radio("Select your answer:", q_data["options"], index=None, key="user_answer_choice")
            if st.form_submit_button("Submit Answer", type="primary"):
                if user_choice is not None:
                    st.session_state.questions_answered += 1
                    if str(user_choice) == str(q_data["answer"]):
                        st.session_state.quiz_score += 1; st.session_state.current_streak += 1
                        st.success("Correct! Well done! 🎉"); confetti_animation()
                    else:
                        st.session_state.current_streak = 0; st.session_state.incorrect_questions.append(q_data)
                        st.error(f"Not quite. The correct answer was: **{q_data['answer']}**")
                    del st.session_state.current_q_data; del st.session_state.user_answer_choice
                    time.sleep(1.5); st.rerun()
                else:
                    st.warning("Please select an answer before submitting.")
        if st.button("Stop Round & Save Score"):
            st.session_state.on_summary_page = True; st.rerun()

def display_quiz_summary():
    st.header("🎉 Round Complete! 🎉")
    final_score = st.session_state.quiz_score
    total_questions = st.session_state.questions_answered
    accuracy = (final_score / total_questions * 100) if total_questions > 0 else 0
    if total_questions > 0 and 'result_saved' not in st.session_state:
        save_quiz_result(st.session_state.username, st.session_state.quiz_topic, final_score, total_questions)
        st.session_state.result_saved = True
    st.metric(label="Your Final Score", value=f"{final_score}/{total_questions}", delta=f"{accuracy:.1f}% Accuracy")
    if accuracy >= 90:
        st.success("🏆 Excellent work! You're a true MathFriend master!"); confetti_animation()
    elif accuracy >= 70:
        st.info("👍 Great job! You've got a solid understanding of this topic.")
    else:
        st.warning("🙂 Good effort! A little more practice and you'll be an expert.")
    if st.session_state.incorrect_questions:
        with st.expander("🔍 Click here to review your incorrect answers"):
            for q in st.session_state.incorrect_questions:
                st.markdown(f"**Question:** {q['question']}")
                st.error(f"**Correct Answer:** {q['answer']}")
                st.info(f"**Hint:** {q['hint']}"); st.write("---")
    st.markdown("<hr class='styled-hr'>", unsafe_allow_html=True)
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Play Again (Same Topic)", use_container_width=True, type="primary"):
            st.session_state.on_summary_page = False; st.session_state.quiz_active = True
            st.session_state.quiz_score = 0; st.session_state.questions_answered = 0
            st.session_state.current_streak = 0; st.session_state.incorrect_questions = []
            if 'current_q_data' in st.session_state: del st.session_state['current_q_data']
            if 'result_saved' in st.session_state: del st.session_state['result_saved']
            st.rerun()
    with col2:
        if st.button("Choose New Topic", use_container_width=True):
            st.session_state.on_summary_page = False; st.session_state.quiz_active = False
            if 'result_saved' in st.session_state: del st.session_state['result_saved']
            st.rerun()

def display_leaderboard(topic_options):
    st.header("🏆 Global Leaderboard")
    col1, col2 = st.columns([2, 3])
    with col1:
        leaderboard_topic = st.selectbox("Select a topic:", topic_options, label_visibility="collapsed")
    with col2:
        time_filter_option = st.radio("Filter by time:",["This Week", "This Month", "All Time"],index=2,horizontal=True,label_visibility="collapsed")
    time_filter_map = {"This Week": "week", "This Month": "month", "All Time": "all"}
    time_filter = time_filter_map[time_filter_option]
    col1, col2 = st.columns(2)
    with col1:
        user_rank = get_user_rank(st.session_state.username, leaderboard_topic, time_filter)
        st.metric(label=f"Your Rank ({time_filter_option})", value=f"#{user_rank}")
    with col2:
        total_players = get_total_players(leaderboard_topic, time_filter)
        st.metric(label=f"Total Players ({time_filter_option})", value=total_players)
    st.markdown("<hr class='styled-hr'>", unsafe_allow_html=True)
    st.subheader(f"Top 10 for {leaderboard_topic} ({time_filter_option})")
    top_scores = get_top_scores(leaderboard_topic, time_filter)
    if top_scores:
        leaderboard_data = []
        for r, (u, s, t) in enumerate(top_scores, 1):
            rank_display = str(r)
            if r == 1: rank_display = "🥇"
            elif r == 2: rank_display = "🥈"
            elif r == 3: rank_display = "🥉"
            username_display = u
            if u == st.session_state.username:
                username_display = f"{u} (You)"
            leaderboard_data.append({
                "Rank": rank_display, "Username": username_display, "Score": f"{s}/{t}",
                "Accuracy": (s/t)*100 if t > 0 else 0
            })
        df = pd.DataFrame(leaderboard_data)
        def highlight_user(row):
            if "(You)" in row.Username:
                return ['background-color: #e6f7ff; font-weight: bold; color: #000000;'] * len(row)
            return [''] * len(row)
        st.dataframe(
            df.style.apply(highlight_user, axis=1).format({'Accuracy': "{:.1f}%"}).hide(axis="index"), 
            use_container_width=True
        )
    else:
        st.info(f"No scores recorded for **{leaderboard_topic}** in this time period. Be the first!")

def display_learning_resources():
    st.header("📚 Learning Resources")
    st.subheader("🧮 Sets and Operations on Sets")
    st.markdown("A **set** is a collection of distinct objects...")
    st.subheader("➗ Percentages")
    st.markdown("A **percentage** is a number or ratio expressed as a fraction of 100...")

def display_profile_page():
    st.header("👤 Your Profile")
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
    st.markdown("<hr class='styled-hr'>", unsafe_allow_html=True)
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
    load_css()
    last_update = st.session_state.get("last_status_update", 0)
    if time.time() - last_update > 60:
        update_user_status(st.session_state.username, True)
        st.session_state.last_status_update = time.time()
    with st.sidebar:
        greeting = get_time_based_greeting()
        profile = get_user_profile(st.session_state.username)
        display_name = profile.get('full_name') if profile and profile.get('full_name') else st.session_state.username
        st.title(f"{greeting}, {display_name}!")
        page_options = [
            "📊 Dashboard", "📝 Quiz", "🏆 Leaderboard", "👤 Profile", 
            "📚 Learning Resources", "💬 Chat (Paused)"
        ]
        selected_page = st.radio("Menu", page_options, label_visibility="collapsed")
        st.write("---")
        if st.button("Logout", type="primary", use_container_width=True):
            st.session_state.logged_in = False
            st.rerun()
            
    st.markdown('<div class="main-content">', unsafe_allow_html=True)
    topic_options = [
        "Sets", "Percentages", "Fractions", "Indices", "Surds", 
        "Binary Operations", "Relations and Functions", "Sequence and Series", 
        "Word Problems", "Shapes (Geometry)", "Algebra Basics", "Linear Algebra"
    ]
    if selected_page == "📊 Dashboard":
        display_dashboard(st.session_state.username)
    elif selected_page == "📝 Quiz":
        display_quiz_page(topic_options)
    elif selected_page == "🏆 Leaderboard":
        display_leaderboard(topic_options)
    elif selected_page == "👤 Profile":
        display_profile_page()
    elif selected_page == "📚 Learning Resources":
        display_learning_resources()
    elif selected_page == "💬 Chat (Paused)":
        st.header("💬 Community Chat")
        st.info("The chat feature is currently paused while we consider the next steps.")
    st.markdown('</div>', unsafe_allow_html=True)

def show_login_or_signup_page():
    load_css()
    st.markdown('<div class="login-container">', unsafe_allow_html=True)
    if st.session_state.page == "login":
        st.markdown('<p class="login-title">🔐 MathFriend Login</p>', unsafe_allow_html=True)
        st.markdown('<p class="login-subtitle">Welcome Back!</p>', unsafe_allow_html=True)
        with st.form("login_form"):
            username = st.text_input("Username", key="login_user")
            password = st.text_input("Password", type="password", key="login_pass")
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
    else: # Signup page
        st.markdown('<p class="login-title">Create Account</p>', unsafe_allow_html=True)
        with st.form("signup_form"):
            username = st.text_input("Username", key="signup_user")
            password = st.text_input("Password", type="password", key="signup_pass")
            confirm_password = st.text_input("Confirm Password", type="password", key="signup_confirm")
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

# --- Initial Script Execution Logic ---
if st.session_state.show_splash:
    load_css()
    st.markdown("""
        <style>
            @keyframes fadeIn { 0% { opacity: 0; } 100% { opacity: 1; } }
            .splash-screen {
                display: flex; justify-content: center; align-items: center;
                height: 100vh; font-size: 3rem; font-weight: 800; color: #0d6efd;
                animation: fadeIn 1.5s ease-in-out;
            }
        </style>
        <div class="splash-screen">🧮 MathFriend</div>
    """, unsafe_allow_html=True)
    time.sleep(2)
    st.session_state.show_splash = False
    st.rerun()
else:
    if st.session_state.logged_in:
        show_main_app()
    else:
        show_login_or_signup_page()



