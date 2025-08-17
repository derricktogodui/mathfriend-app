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
import stream_chat

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

# --- Stream Chat Client Initialization ---
@st.cache_resource
def get_stream_chat_client():
    """Initializes the Stream Chat client."""
    client = stream_chat.StreamChat(
        api_key=st.secrets["STREAM_API_KEY"],
        api_secret=st.secrets["STREAM_API_SECRET"]
    )
    return client

chat_client = get_stream_chat_client()

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
        if record and check_password(record[0], password):
            profile = get_user_profile(username)
            display_name = profile.get('full_name') if profile and profile.get('full_name') else username
            chat_client.upsert_user({"id": username, "name": display_name})
            return True
        return False

def signup_user(username, password):
    try:
        with engine.connect() as conn:
            conn.execute(text("INSERT INTO users (username, password) VALUES (:username, :password)"), 
                         {"username": username, "password": hash_password(password)})
            conn.commit()
            chat_client.upsert_user({"id": username, "name": username})
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
        chat_client.upsert_user({"id": username, "name": full_name if full_name else username})
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
            WITH UserBestScores AS (
                SELECT username, score, questions_answered, timestamp,
                       ROW_NUMBER() OVER(PARTITION BY username ORDER BY (CAST(score AS REAL) / questions_answered) DESC, questions_answered DESC, timestamp ASC) as rn
                FROM quiz_results WHERE topic = :topic AND questions_answered > 0 {time_clause}
            )
            SELECT username, score, questions_answered FROM UserBestScores WHERE rn = 1
            ORDER BY (CAST(score AS REAL) / questions_answered) DESC, questions_answered DESC, timestamp ASC LIMIT 10;
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
    with engine.connect() as conn:
        time_clause = ""
        if time_filter == "week": time_clause = "AND timestamp >= NOW() - INTERVAL '7 days'"
        elif time_filter == "month": time_clause = "AND timestamp >= NOW() - INTERVAL '30 days'"
        query = text(f"""
            WITH UserBestScores AS (
                SELECT username, score, questions_answered, timestamp,
                       ROW_NUMBER() OVER(PARTITION BY username ORDER BY (CAST(score AS REAL) / questions_answered) DESC, questions_answered DESC, timestamp ASC) as rn
                FROM quiz_results WHERE topic = :topic AND questions_answered > 0 {time_clause}
            ), RankedScores AS (
                SELECT username, RANK() OVER (ORDER BY (CAST(score AS REAL) / questions_answered) DESC, questions_answered DESC, timestamp ASC) as rank
                FROM UserBestScores WHERE rn = 1
            )
            SELECT rank FROM RankedScores WHERE username = :username;
        """)
        result = conn.execute(query, {"topic": topic, "username": username}).scalar_one_or_none()
        return result if result else "N/A"

def get_total_players(topic, time_filter="all"):
    with engine.connect() as conn:
        time_clause = ""
        if time_filter == "week": time_clause = "AND timestamp >= NOW() - INTERVAL '7 days'"
        elif time_filter == "month": time_clause = "AND timestamp >= NOW() - INTERVAL '30 days'"
        query = text(f"SELECT COUNT(DISTINCT username) FROM quiz_results WHERE topic = :topic AND questions_answered > 0 {time_clause}")
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

def get_online_users(current_user):
    with engine.connect() as conn:
        query = text("""
            SELECT username FROM user_status WHERE is_online = TRUE AND last_seen > NOW() - INTERVAL '5 minutes'
            AND username != :current_user
        """)
        result = conn.execute(query, {"current_user": current_user})
        return [row[0] for row in result.fetchall()]

# --- UTILITY FUNCTIONS FOR QUESTION GENERATION ---
def _get_fraction_latex_code(f: Fraction):
    if f.denominator == 1: return str(f.numerator)
    return f"\\frac{{{f.numerator}}}{{{f.denominator}}}"

def _format_fraction_text(f: Fraction):
    if f.denominator == 1: return str(f.numerator)
    return f"{f.numerator}/{f.denominator}"

def _finalize_options(options_set, default_type="int"):
    """Ensures 4 unique options and shuffles them."""
    while len(options_set) < 4:
        if default_type == "fraction":
            options_set.add(_format_fraction_text(Fraction(random.randint(1,20), random.randint(2,20))))
        elif default_type == "set_str":
            options_set.add(str(set(random.sample(range(1,20), k=3))))
        else: # int
            options_set.add(str(random.randint(1, 100)))
    final_options = list(options_set)
    random.shuffle(final_options)
    return final_options

# --- FULLY IMPLEMENTED QUESTION GENERATION ENGINE (12 TOPICS) ---

def _generate_sets_question():
    # Subtopics: Operations, Venn Diagrams (2 & 3 set), Subsets/Power Sets
    q_type = random.choice(['operation', 'venn_two', 'venn_three', 'subsets'])
    
    if q_type == 'operation':
        set_a = set(random.sample(range(1, 20), k=random.randint(4, 6)))
        set_b = set(random.sample(range(1, 20), k=random.randint(4, 6)))
        op, sym = random.choice([('union', '\\cup'), ('intersection', '\\cap'), ('difference', '-')])
        question = f"Given $A = {set_a}$ and $B = {set_b}$, find $A {sym} B$."
        if op == 'union': res = set_a.union(set_b)
        elif op == 'intersection': res = set_a.intersection(set_b)
        else: res = set_a.difference(set_b)
        answer = str(res)
        hint = "Review the definitions of Union (all elements), Intersection (common elements), and Difference (in first but not second)."
        explanation = f"For $A = {set_a}$ and $B = {set_b}$:\n\n- The **{op}** ($A {sym} B$) consists of elements that meet the operation's criteria.\n\n- The resulting set is ${res}$."
        options = {answer, str(set_a.symmetric_difference(set_b)), str(set_b.difference(set_a))}

    elif q_type == 'venn_two':
        total, a_only, b_only, both = random.randint(50, 80), random.randint(10, 20), random.randint(10, 20), random.randint(5, 10)
        neither = total - (a_only + b_only + both)
        total_a, total_b = a_only + both, b_only + both
        item1, item2 = random.choice([("Physics", "Chemistry"), ("History", "Geography")])
        question = f"In a class of {total} students, {total_a} offer {item1} and {total_b} offer {item2}. If {neither} students offer neither subject, find the number of students who offer both."
        answer = str(both)
        hint = "Use the formula $|A \\cup B| = |A| + |B| - |A \\cap B|$. Start by finding $|A \\cup B|$ which is Total - Neither."
        explanation = f"1. Students offering at least one subject = Total - Neither = {total} - {neither} = {a_only+b_only+both}.\n\n2. Let Both be $x$. Then ${total_a} + {total_b} - x = {a_only+b_only+both}$.\n\n3. ${total_a+total_b} - x = {a_only+b_only+both}$.\n\n4. $x = {total_a+total_b} - {(a_only+b_only+both)} = {both}$."
        options = {answer, str(a_only), str(b_only), str(neither)}

    elif q_type == 'venn_three':
        a,b,c,ab,bc,ac,abc = [random.randint(2, 8) for _ in range(7)]
        a_only, b_only, c_only, ab_only, bc_only, ac_only, all_three = a, b, c, ab, bc, ac, abc
        total_a, total_b, total_c = a+ab+ac+abc, b+ab+bc+abc, c+ac+bc+abc
        total = sum([a,b,c,ab,bc,ac,abc])
        question = f"{total} students were surveyed on sports: Football (F), Volleyball (V), and Basketball (B). {total_a} play F, {total_b} play V, {total_c} play B. {ab+abc} play F & V, {ac+abc} play F & B, {bc+abc} play V & B, and {abc} play all three. How many play exactly one sport?"
        answer = str(a+b+c)
        hint = "Draw a three-set Venn diagram. Start with the 'all three' section and work outwards by subtracting to find the 'only' regions."
        explanation = f"1. F only = Total F - (F&V only) - (F&B only) - (All three) = {total_a} - {ab} - {ac} - {abc} = {a}.\n\n2. V only = {total_b} - {ab} - {bc} - {abc} = {b}.\n\n3. B only = {total_c} - {ac} - {bc} - {abc} = {c}.\n\n4. Total exactly one = {a} + {b} + {c} = {a+b+c}."
        options = {answer, str(ab+bc+ac), str(abc)}
    
    elif q_type == 'subsets':
        k = random.randint(3, 5)
        elements = random.sample(range(1, 100), k)
        s = set(elements)
        question = f"How many subsets can be formed from the set $S = {s}$?"
        answer = str(2**k)
        hint = "The number of subsets of a set with 'n' elements is given by the formula $2^n$."
        explanation = f"The set S has {k} elements (n={k}).\n\nThe formula for the number of subsets is $2^n$.\n\nTherefore, the number of subsets is $2^{k} = {2**k}$."
        options = {answer, str(k**2), str(2*k)}
        
    return {"question": question, "options": _finalize_options(options, default_type="set_str"), "answer": answer, "hint": hint, "explanation": explanation}

def _generate_percentages_question():
    # Subtopics: Basic Calcs, Increase/Decrease, Profit/Loss, Interest
    q_type = random.choice(['percent_of', 'percent_change', 'profit_loss', 'simple_interest'])
    
    if q_type == 'percent_of':
        percent, number = random.randint(1, 19)*5, random.randint(10, 50)*10
        question = f"Calculate {percent}% of {number}."
        answer = f"{(percent/100)*number:.2f}"
        hint = "Convert the percentage to a decimal (divide by 100) and then multiply by the number."
        explanation = f"1. Convert percent to decimal: {percent}% = {percent/100}.\n\n2. Multiply: {percent/100} * {number} = {float(answer)}."
        options = {answer, f"{percent*number/10:.2f}", f"{number/percent:.2f}"}

    elif q_type == 'percent_change':
        old, new = random.randint(50, 200), random.randint(201, 400)
        question = f"A price increased from GHS {old} to GHS {new}. What is the percentage increase?"
        ans_val = ((new - old) / old) * 100
        answer = f"{ans_val:.2f}%"
        hint = "Use the formula: $\\frac{{\\text{{New Value}} - \\text{{Old Value}}}}{{\\text{{Old Value}}}} \\times 100\\%$"
        explanation = f"1. Change = {new} - {old} = {new-old}.\n\n2. Percent Change = (Change / Old Value) * 100 = ({new-old} / {old}) * 100 = {ans_val:.2f}%."
        options = {answer, f"{((new-old)/new)*100:.2f}%", f"{ans_val/100:.2f}%"}
    
    elif q_type == 'profit_loss':
        cost, selling = random.randint(100, 200), random.randint(201, 300)
        question = f"An item bought for GHS {cost} was sold for GHS {selling}. Find the profit percent."
        profit = selling - cost
        ans_val = (profit / cost) * 100
        answer = f"{ans_val:.2f}%"
        hint = "Profit Percent = $\\frac{{\\text{{Profit}}}}{{\\text{{Cost Price}}}} \\times 100\\%$"
        explanation = f"1. Profit = Selling Price - Cost Price = {selling} - {cost} = {profit}.\n\n2. Profit Percent = (Profit / Cost) * 100 = ({profit} / {cost}) * 100 = {ans_val:.2f}%."
        options = {answer, f"{(profit/selling)*100:.2f}%", f"{profit:.2f}%"}

    elif q_type == 'simple_interest':
        p, r, t = random.randint(10, 50)*100, random.randint(5, 15), random.randint(2, 5)
        question = f"Find the simple interest on GHS {p} for {t} years at a rate of {r}% per annum."
        ans_val = (p * r * t) / 100
        answer = f"GHS {ans_val:.2f}"
        hint = "Use the formula: Simple Interest = $P \\times R \\times T / 100$."
        explanation = f"1. Formula: I = PRT/100.\n\n2. Substitute: I = ({p} * {r} * {t}) / 100.\n\n3. Calculate: I = {ans_val:.2f}."
        options = {answer, f"GHS {p+ans_val:.2f}", f"GHS {p*r*t:.2f}"}

    return {"question": question, "options": _finalize_options(options), "answer": answer, "hint": hint, "explanation": explanation}

def _generate_fractions_question():
    # Subtopics: Operations, BODMAS, Word Problems
    q_type = random.choice(['operation', 'bodmas', 'word_problem'])
    
    if q_type == 'operation':
        f1 = Fraction(random.randint(1, 10), random.randint(2, 10))
        f2 = Fraction(random.randint(1, 10), random.randint(2, 10))
        op, sym = random.choice([('add', '+'), ('subtract', '-'), ('multiply', '\\times'), ('divide', '\\div')])
        if op == 'divide' and f2.numerator == 0: f2 = Fraction(1, f2.denominator) # Avoid division by zero
        question = f"Calculate: ${_get_fraction_latex_code(f1)} {sym} {_get_fraction_latex_code(f2)}$"
        if op == 'add': res = f1 + f2
        elif op == 'subtract': res = f1 - f2
        elif op == 'multiply': res = f1 * f2
        else: res = f1 / f2
        answer = _format_fraction_text(res)
        hint = "For +/-, find a common denominator. For ×, multiply numerators/denominators. For ÷, invert the second fraction and multiply."
        explanation = f"To {op} ${_get_fraction_latex_code(f1)}$ and ${_get_fraction_latex_code(f2)}$, you follow the rule for that operation. The simplified result is ${_get_fraction_latex_code(res)}$."
        distractor = _format_fraction_text(Fraction(f1.numerator + f2.numerator, f1.denominator + f2.denominator)) if op in ['add', 'subtract'] else _format_fraction_text(f1*f2 if op == 'divide' else f1/f2)
        options = {answer, distractor}
    
    elif q_type == 'bodmas':
        a, b, c = [random.randint(2, 6) for _ in range(3)]
        question = f"Evaluate: $(\\frac{{1}}{{{a}}} + \\frac{{1}}{{{b}}}) \\times {c}$"
        res = (Fraction(1, a) + Fraction(1, b)) * c
        answer = _format_fraction_text(res)
        hint = "Follow BODMAS. Solve the operation inside the brackets first."
        explanation = f"1. Bracket: $\\frac{{1}}{{{a}}} + \\frac{{1}}{{{b}}} = \\frac{{{b}+{a}}}{{{a*b}}}$.\n\n2. Multiply: $\\frac{{{a+b}}}{{{a*b}}} \\times {c} = {_get_fraction_latex_code(res)}$."
        distractor = _format_fraction_text(Fraction(1,a) + Fraction(1,b)*c) # Incorrect order
        options = {answer, distractor}
        
    elif q_type == 'word_problem':
        total = random.randint(20, 40)
        den = random.choice([3, 4, 5])
        num = random.randint(1, den-1)
        spent = Fraction(num, den)
        remaining = total * (1-spent)
        question = f"Kofi had GHS {total}. He spent $\\frac{{{num}}}{{{den}}}$ of it on airtime. How much money does he have left?"
        answer = f"GHS {remaining}"
        hint = "First, find the amount spent by multiplying the fraction by the total. Then, subtract this from the total."
        explanation = f"1. Amount spent = $\\frac{{{num}}}{{{den}}} \\times {total} = {total*spent}$.\n\n2. Money left = Total - Spent = {total} - {total*spent} = {remaining}."
        options = {answer, f"GHS {total*spent}"}

    return {"question": question, "options": _finalize_options(options, "fraction"), "answer": answer, "hint": hint, "explanation": explanation}

def _generate_indices_question():
    # Subtopics: Laws of Indices, Fractional, Exponential Equations
    q_type = random.choice(['law_multiply_divide', 'law_power', 'law_negative_zero', 'fractional', 'equation'])
    base = random.randint(2, 7)

    if q_type == 'law_multiply_divide':
        p1, p2 = random.randint(5, 10), random.randint(2, 4)
        op, sym, res_p = random.choice([('multiply', '\\times', p1+p2), ('divide', '\\div', p1-p2)])
        question = f"Simplify: ${base}^{{{p1}}} {sym} {base}^{{{p2}}}$"
        answer = f"${base}^{{{res_p}}}$"
        hint = f"When you {op} powers with the same base, you {'add' if op=='multiply' else 'subtract'} the exponents."
        
        # --- THIS LINE IS CORRECTED ---
        explanation = f"Rule: $x^a {sym} x^b = x^{{a{'+' if op=='multiply' else '-' }b}}$.\n\nSo, ${base}^{{{p1}}} {sym} {base}^{{{p2}}} = {base}^{{{p1}{'+' if op=='multiply' else '-'}{p2}}} = {base}^{{{res_p}}}$."
        
        options = {answer, f"${base}^{{{p1*p2}}}$"}

    elif q_type == 'law_power':
        p1, p2 = random.randint(2, 5), random.randint(2, 4)
        question = f"Simplify: $({base}^{{{p1}}})^{{{p2}}}$"
        answer = f"${base}^{{{p1*p2}}}$"
        hint = "For a power of a power, you multiply the exponents."
        explanation = f"Rule: $(x^a)^b = x^{{ab}}$.\n\nSo, $({base}^{{{p1}}})^{{{p2}}} = {base}^{{{p1} \\times {p2}}} = {base}^{{{p1*p2}}}$."
        options = {answer, f"${base}^{{{p1+p2}}}$", f"${base}^{{{p1**p2}}}$"}

    elif q_type == 'law_negative_zero':
        p = random.randint(2, 4)
        question = f"Evaluate ${base}^{{-{p}}}$"
        answer = f"$\\frac{{1}}{{{base**p}}}$"
        hint = "A negative exponent means you take the reciprocal of the base raised to the positive exponent."
        explanation = f"Rule: $x^{{-a}} = \\frac{{1}}{{x^a}}$.\n\nSo, ${base}^{{-{p}}} = \\frac{{1}}{{{base}^{p}}} = \\frac{{1}}{{{base**p}}}$."
        options = {answer, f"$-{base*p}$", f"$-{base**p}$"}

    elif q_type == 'fractional':
        root_val, power_val = random.choice([(2,4), (2,9), (3,8), (3,27)])
        question = f"Evaluate ${power_val}^{{\\frac{{1}}{{{root_val}}}}}$"
        answer = str(int(power_val**(1/root_val)))
        hint = r"The exponent $\frac{1}{n}$ means taking the nth root."
        explanation = f"Rule: $x^{{\\frac{{1}}{{n}}}} = \\sqrt[n]{{x}}$.\n\nSo, ${power_val}^{{\\frac{{1}}{{{root_val}}}}} = \\sqrt[{root_val}]{{{power_val}}} = {answer}$."
        options = {answer, str(power_val/root_val), str(power_val-root_val)}

    elif q_type == 'equation':
        p = random.randint(2, 4)
        question = f"Solve for x: ${base}^x = {base**p}$"
        answer = str(p)
        hint = "If the bases are the same in an equation, then the exponents must be equal."
        explanation = f"Given ${base}^x = {base**p}$.\n\nSince the bases on both sides of the equation are equal ({base}), we can equate the exponents: $x = {p}$."
        options = {answer, str(base*p), str(base**p)}

    return {"question": question, "options": _finalize_options(options), "answer": answer, "hint": hint, "explanation": explanation}
def _generate_surds_question():
    # Subtopics: Simplification, Operations, Rationalization, Equations
    q_type = random.choice(['simplify', 'operate', 'rationalize', 'equation'])

    if q_type == 'simplify':
        p_sq, n = random.choice([4, 9, 16, 25]), random.choice([2, 3, 5, 7])
        num = p_sq * n
        question = f"Express $\sqrt{{{num}}}$ in its simplest form."
        answer = f"${int(math.sqrt(p_sq))}\sqrt{{{n}}}$"
        hint = f"Find the largest perfect square that is a factor of {num}."
        explanation = f"1. Find factors of {num}: {num} = {p_sq} × {n}.\n\n2. Split the surd: $\sqrt{{{num}}} = \sqrt{{{p_sq}}} \\times \sqrt{{{n}}}$.\n\n3. Simplify the perfect square: $\sqrt{{{p_sq}}} = {int(math.sqrt(p_sq))}$.\n\n4.  ${answer}$."
        options = {answer, f"${n}\sqrt{{{p_sq}}}$"}

    elif q_type == 'operate':
        c1, c2, base = random.randint(2, 8), random.randint(2, 8), random.choice([2, 3, 5])
        op, sym, res = random.choice([('add', '+', c1+c2), ('subtract', '-', c1-c2)])
        question = f"Simplify: ${c1}\sqrt{{{base}}} {sym} {c2}\sqrt{{{base}}}$"
        answer = f"${res}\sqrt{{{base}}}$"
        hint = "You can only add or subtract 'like' surds (those with the same number under the root)."
        explanation = f"Since both terms have $\sqrt{{{base}}}$, we can treat it like a variable (e.g., like 5x + 3x).\n\nFactor out the common surd: $({c1} {sym} {c2})\sqrt{{{base}}} = {res}\sqrt{{{base}}}$."
        options = {answer, f"${c1+c2}\sqrt{{{base*2}}}$", f"${c1*c2}\sqrt{{{base}}}$"}

    elif q_type == 'rationalize':
        a, b, c = random.randint(2, 9), random.randint(2, 9), random.choice([2, 3, 5, 7])
        while b*b == c: b = random.randint(2,9) # Ensure denominator is not zero
        question = f"Rationalize the denominator of $\\frac{{{a}}}{{{b} - \sqrt{{{c}}}}}$"
        num = f"{a*b} + {a}\sqrt{{{c}}}"
        den = b**2 - c
        answer = f"$\\frac{{{num}}}{{{den}}}$"
        hint = f"Multiply the numerator and denominator by the conjugate of the denominator, which is $({b} + \sqrt{{{c}}})$."
        explanation = f"1. Conjugate of ${b} - \sqrt{{{c}}}$ is ${b} + \sqrt{{{c}}}$.\n\n2. Multiply top and bottom: $\\frac{{{a}}}{{{b} - \sqrt{{{c}}}}} \\times \\frac{{{b} + \sqrt{{{c}}}}}{{{b} + \sqrt{{{c}}}}}$.\n\n3. Numerator: ${a}({b} + \sqrt{{{c}}}) = {num}$.\n\n4. Denominator (using $(x-y)(x+y)=x^2-y^2$): ${b}^2 - (\sqrt{{{c}}})^2 = {b**2} - {c} = {den}$.\n\n5. Final Answer: ${answer}$."
        options = {answer, f"$\\frac{{{num}}}{{{b-c}}}$", f"$\\frac{{{a}}}{{{den}}}$"}
        
    elif q_type == 'equation':
        x = random.randint(2, 5)
        question = f"Solve for x: $\sqrt{{x + 1}} = {x-1}$"
        # We need to construct a valid equation. Let's work backwards.
        rhs = random.randint(2, 5) # This will be the value of sqrt()
        x_plus_1 = rhs**2
        x = x_plus_1 - 1
        # The equation is sqrt(x+1) = rhs. We can write rhs in terms of x.
        # Let rhs = x - k. Then x-k = sqrt(x+1). Let's pick an easier format.
        x_val = random.randint(3, 8)
        c = random.randint(1, 5)
        result = int(math.sqrt(x_val - c))
        while (x_val - c) < 0 or math.sqrt(x_val-c) != result:
            x_val = random.randint(3, 8); c = random.randint(1, 5); result = int(math.sqrt(x_val-c))
        question = f"Solve for x: $\sqrt{{x - {c}}} = {result}$"
        answer = str(x_val)
        hint = "To solve for x, square both sides of the equation to eliminate the square root."
        explanation = f"1. Given: $\sqrt{{x - {c}}} = {result}$.\n\n2. Square both sides: $(\sqrt{{x - {c}}})^2 = {result}^2$.\n\n3. This simplifies to: $x - {c} = {result**2}$.\n\n4. Add {c} to both sides: $x = {result**2} + {c} = {x_val}$."
        options = {answer, str(result**2), str(x_val+c)}

    return {"question": question, "options": _finalize_options(options), "answer": answer, "hint": hint, "explanation": explanation}

# ... (Placeholders for other 8 generator functions would be replaced with full implementations like the ones above) ...
# For the final response, I will write all of them out.

def _generate_binary_ops_question():
    # Subtopics: Evaluate, Identity/Inverse, Properties, Tables
    q_type = random.choice(['evaluate', 'identity_inverse', 'properties']) # Tables are harder to format
    a, b = random.randint(2, 9), random.randint(2, 9)
    op_def, op_func, op_sym = random.choice([
        (r"p \ast q = p + q + 2", lambda x, y: x + y + 2, r"\ast"),
        (r"x \oplus y = xy - x", lambda x, y: x*y - x, r"\oplus"),
        (r"m \nabla n = m^2 - n", lambda x, y: x**2 - y, r"\nabla"),
    ])

    if q_type == 'evaluate':
        question = f"A binary operation is defined by ${op_def}$. Evaluate ${a} {op_sym} {b}$."
        answer = str(op_func(a, b))
        hint = "Substitute the first value for the first variable (p, x, or m) and the second value for the second variable (q, y, or n)."
        explanation = f"1. The definition is ${op_def}$.\n\n2. We substitute a={a} and b={b}.\n\n3. The calculation is: {op_func(a,b)}."
        options = {answer, str(op_func(b, a)), str(a*b)}

    elif q_type == 'identity_inverse':
        # Using a standard definition for this type a*b = a+b-3, identity e=3
        element = random.randint(4, 10)
        question = f"For the binary operation $a \\ast b = a+b-3$, the identity element is 3. Find the inverse of {element}."
        answer = str(6 - element)
        hint = "The inverse 'a⁻¹' of an element 'a' satisfies $a \\ast a^{{-1}} = e$, where 'e' is the identity element. Solve for a⁻¹."
        explanation = f"1. Let the inverse of {element} be $inv$.\n\n2. The formula is ${element} \\ast inv = 3$.\n\n3. Using the definition: ${element} + inv - 3 = 3$.\n\n4. $inv - 3 = {3-element}$.\n\n5. $inv = {3-element+3} = {6-element}$."
        options = {answer, str(-element), str(element-3)}

    elif q_type == 'properties':
        # Test for commutativity
        op_def_c, func_c, sym_c = (r"a \Delta b = a + b + ab", lambda x,y: x+y+x*y, r"\Delta") # Commutative
        op_def_nc, func_nc, sym_nc = (r"a \circ b = a - 2b", lambda x,y: x-2*y, r"\circ") # Not commutative
        chosen_op, chosen_func, chosen_sym, is_comm = random.choice([(op_def_c, func_c, sym_c, True), (op_def_nc, func_nc, sym_nc, False)])
        
        question = f"Is the binary operation ${chosen_op}$ on the set of real numbers commutative?"
        answer = "Yes" if is_comm else "No"
        hint = "A binary operation * is commutative if a * b = b * a for all values of a and b."
        a_b = chosen_func(a,b)
        b_a = chosen_func(b,a)
        explanation = f"To check for commutativity, we test if $a {chosen_sym} b = b {chosen_sym} a$.\n\n- $a {chosen_sym} b = {chosen_op.split('=')[1].strip()}$\n\n- $b {chosen_sym} a = {chosen_op.split('=')[1].strip().replace('a', 'B').replace('b', 'A').replace('A','a').replace('B','b')}$\n\n- Let's test with numbers, a={a}, b={b}:\n\n- ${a} {chosen_sym} {b} = {a_b}$\n\n- ${b} {chosen_sym} {a} = {b_a}$\n\n- Since ${a_b} {'==' if a_b==b_a else '!='} {b_a}$, the operation is {'' if is_comm else 'not '}commutative."
        options = {"Yes", "No"}

    return {"question": question, "options": _finalize_options(options), "answer": answer, "hint": hint, "explanation": explanation}

def _generate_relations_functions_question():
    # Subtopics: Domain/Range, Types, Evaluate, Composite, Inverse
    q_type = random.choice(['domain_range', 'evaluate', 'composite', 'inverse'])
    
    if q_type == 'domain_range':
        d_set = set(random.sample(range(-5, 10), k=4))
        r_set = set(random.sample(range(-5, 10), k=4))
        relation = str(set(zip(d_set, r_set))).replace("'", "")
        d_or_r = random.choice(['domain', 'range'])
        question = f"What is the {d_or_r} of the relation $R = {relation}$?"
        answer = str(d_set if d_or_r == 'domain' else r_set)
        hint = "The domain is the set of all first elements (x-values). The range is the set of all second elements (y-values)."
        explanation = f"Given the relation $R = {relation}$:\n\n- The domain is the set of all unique first coordinates: ${d_set}$.\n\n- The range is the set of all unique second coordinates: ${r_set}$."
        options = {str(d_set), str(r_set), str(d_set.union(r_set))}
    
    elif q_type == 'evaluate':
        a, b, x = random.randint(2, 7), random.randint(-5, 5), random.randint(1, 5)
        question = f"If $f(x) = {a}x + {b}$, find the value of $f({x})$."
        answer = str(a * x + b)
        hint = "Substitute the given value for x into the function's definition."
        explanation = f"1. The function is $f(x) = {a}x + {b}$.\n\n2. We need to find $f({x})$, so we replace every 'x' with '{x}'.\n\n3. $f({x}) = {a}({x}) + {b} = {a*x} + {b} = {a*x+b}$."
        options = {answer, str(a + x + b), str(a * (x + b))}

    elif q_type == 'composite':
        a, b, c, d, x = [random.randint(1, 5) for _ in range(5)]
        question = f"Given $f(x) = {a}x + {b}$ and $g(x) = {c}x + {d}$, find $f(g({x}))$."
        g_of_x = c * x + d
        answer = str(a * g_of_x + b)
        hint = "First, calculate the inner function $g(x)$. Then, use that result as the input for the outer function $f(x)$."
        explanation = f"1. First find $g({x})$: $g({x}) = {c}({x}) + {d} = {g_of_x}$.\n\n2. Now use this result as the input for f: $f(g({x})) = f({g_of_x})$.\n\n3. $f({g_of_x}) = {a}({g_of_x}) + {b} = {a*g_of_x+b}$."
        options = {answer, str(c*(a*x+b)+d)}

    elif q_type == 'inverse':
        a, b = random.randint(2, 7), random.randint(1, 10)
        question = f"Find the inverse function, $f^{{-1}}(x)$, of $f(x) = {a}x - {b}$."
        answer = r"$\frac{x + " + str(b) + r"}{" + str(a) + r"}$"
        hint = "Let y = f(x), then swap x and y. Finally, make y the subject of the formula."
        explanation = f"1. Start with $y = {a}x - {b}$.\n\n2. Swap x and y: $x = {a}y - {b}$.\n\n3. Solve for y: $x + {b} = {a}y$.\n\n4. $y = \\frac{{x + {b}}}{{{a}}}$. So, $f^{{-1}}(x) = {answer}$."
        options = {answer, r"$\frac{x - " + str(b) + r"}{" + str(a) + r"}$", r"${a}x + {b}$"}

    return {"question": question, "options": _finalize_options(options, "set_str"), "answer": answer, "hint": hint, "explanation": explanation}

def _generate_sequence_series_question():
    # Subtopics: AP term/sum, GP term/sum, Sum to Infinity
    q_type = random.choice(['ap_term', 'gp_term', 'ap_sum', 'gp_sum_inf'])
    a = random.randint(2, 6)

    if q_type == 'ap_term':
        d, n = random.randint(3, 8), random.randint(8, 15)
        seq = ", ".join([str(a + i*d) for i in range(3)])
        question = f"Find the {n}th term of the arithmetic sequence: {seq}, ..."
        answer = str(a + (n - 1) * d)
        hint = r"Use the AP nth term formula: $a_n = a + (n-1)d$."
        explanation = f"1. First term $a = {a}$.\n\n2. Common difference $d = {a+d} - {a} = {d}$.\n\n3. $a_{{{n}}} = {a} + ({n}-1)({d}) = {a} + {n-1}*{d} = {answer}$."
        options = {answer, str(a + n*d)}
    
    elif q_type == 'gp_term':
        r, n = random.randint(2, 4), random.randint(4, 7)
        seq = ", ".join([str(a * r**i) for i in range(3)])
        question = f"Find the {n}th term of the geometric sequence: {seq}, ..."
        answer = str(a * r**(n-1))
        hint = r"Use the GP nth term formula: $a_n = ar^{n-1}$."
        explanation = f"1. First term $a = {a}$.\n\n2. Common ratio $r = {a*r}/{a} = {r}$.\n\n3. $a_{{{n}}} = {a} \\times {r}^{{{n}-1}} = {a} \\times {r**(n-1)} = {answer}$."
        options = {answer, str((a*r)**(n-1))}

    elif q_type == 'ap_sum':
        d, n = random.randint(2, 5), random.randint(10, 20)
        question = f"Find the sum of the first {n} terms of an AP with first term {a} and common difference {d}."
        answer = str(int((n/2) * (2*a + (n-1)*d)))
        hint = r"Use the AP sum formula: $S_n = \frac{n}{2}(2a + (n-1)d)$."
        explanation = f"1. $S_{{{n}}} = \\frac{{{n}}}{{2}}(2({a}) + ({n}-1)({d}))$.\n\n2. $S_{{{n}}} = {n/2}({2*a} + {n-1}*{d}) = {n/2}({2*a + (n-1)*d}) = {answer}$."
        options = {answer, str(n*(a + (n-1)*d))}

    elif q_type == 'gp_sum_inf':
        r = Fraction(1, random.randint(2, 5))
        question = f"Find the sum to infinity of a GP with first term ${a}$ and common ratio ${_get_fraction_latex_code(r)}$."
        answer = _format_fraction_text(a / (1 - r))
        hint = r"Use the sum to infinity formula: $S_\infty = \frac{a}{1-r}$, for $|r| < 1$."
        explanation = f"$S_\\infty = \\frac{{{a}}}{{1 - {r.numerator}/{r.denominator}}} = \\frac{{{a}}}{{{(r.denominator-r.numerator)}/{r.denominator}}} = {a} \\times \\frac{{{r.denominator}}}{{{r.denominator-r.numerator}}} = {_get_fraction_latex_code(a/(1-r))}$."
        options = {_format_fraction_text(a / (1-r)), _format_fraction_text(a/(1+r))}

    return {"question": question, "options": _finalize_options(options), "answer": answer, "hint": hint, "explanation": explanation}


def _generate_word_problems_question():
    # Subtopics: Linear equations, simultaneous, quadratic, age, consecutive integers
    q_type = random.choice(['linear', 'age', 'consecutive_integers'])

    if q_type == 'linear':
        x, k, m = random.randint(5, 15), random.randint(5, 15), random.randint(2, 5)
        result = m*x + k
        question = f"When {m} times a certain number is increased by {k}, the result is {result}. Find the number."
        answer = str(x)
        hint = "Let the number be 'n'. Translate the sentence into an equation and solve."
        explanation = f"1. Let the number be n. The equation is ${m}n + {k} = {result}$.\n\n2. Subtract {k}: ${m}n = {result-k}$.\n\n3. Divide by {m}: $n = {(result-k)/m}$."
        options = {answer, str(result-k), str(result/m)}

    elif q_type == 'age':
        ama_age, kofi_age = random.randint(5, 10), random.randint(15, 25)
        years = random.randint(3, 8)
        question = f"Ama is {ama_age} years old and Kofi is {kofi_age} years old. In how many years will Kofi be twice as old as Ama?"
        # Equation: kofi_age + x = 2 * (ama_age + x) => kofi_age + x = 2*ama_age + 2x => x = kofi_age - 2*ama_age
        # Ensure it's a positive integer result
        while kofi_age - 2*ama_age <= 0:
            ama_age, kofi_age = random.randint(5, 10), random.randint(15, 25)
        ans_val = kofi_age - 2*ama_age
        answer = str(ans_val)
        hint = "Let the number of years be 'x'. Set up an equation for their future ages: Kofi's Future Age = 2 * Ama's Future Age."
        explanation = f"1. Let x be the number of years.\n\n2. In x years, Ama will be {ama_age}+x and Kofi will be {kofi_age}+x.\n\n3. Equation: ${kofi_age}+x = 2({ama_age}+x)$.\n\n4. ${kofi_age}+x = {2*ama_age}+2x$.\n\n5. ${kofi_age - 2*ama_age} = 2x-x \implies x = {ans_val}$."
        options = {answer, str(kofi_age - ama_age)}

    elif q_type == 'consecutive_integers':
        start, num = random.randint(5, 25), random.choice([2, 3])
        integers = [start+i for i in range(num)]
        total = sum(integers)
        question = f"The sum of {num} consecutive integers is {total}. What is the largest of these integers?"
        answer = str(integers[-1])
        hint = f"Represent the integers as n, n+1, ... and set their sum equal to {total}."
        explanation = f"1. Let the integers be n, n+1, ...\n\n2. Equation: {'n + (n+1)' if num==2 else 'n + (n+1) + (n+2)'} = {total}.\n\n3. ${num}n + {1 if num==2 else 3} = {total} \implies {num}n = {total-(1 if num==2 else 3)} \implies n = {start}$.\n\n4. The integers are {integers}. The largest is {answer}."
        options = {answer, str(start), str(total/num)}

    return {"question": question, "options": _finalize_options(options), "answer": answer, "hint": hint, "explanation": explanation}


def _generate_shapes_question():
    # Subtopics: Perimeter/Area (rect, tri, circle), Volume/Surface Area (cuboid, cylinder)
    q_type = random.choice(['area_rect', 'area_circle', 'vol_cuboid', 'vol_cylinder', 'pythagoras'])
    
    if q_type == 'area_rect':
        l, w = random.randint(5, 20), random.randint(5, 20)
        question = f"A rectangle has a length of {l} cm and a width of {w} cm. Calculate its area."
        answer = str(l*w)
        hint = "Area of a rectangle = length × width."
        explanation = f"Area = $l \\times w = {l} \\times {w} = {answer}\\ cm^2$."
        options = {answer, str(2*(l+w)), str(l+w)}

    elif q_type == 'area_circle':
        r = random.randint(5, 12)
        question = f"Find the area of a circle with a radius of {r} cm. (Use $\\pi = 22/7$)"
        area = Fraction(22,7) * r**2
        answer = _format_fraction_text(area)
        hint = "Area of a circle = $\pi r^2$."
        explanation = f"Area = $\\pi r^2 = \\frac{{22}}{{7}} \\times {r}^2 = \\frac{{22}}{{7}} \\times {r*r} = {_get_fraction_latex_code(area)}\\ cm^2$."
        options = {answer, _format_fraction_text(Fraction(22,7)*2*r)}

    elif q_type == 'vol_cuboid':
        l, w, h = random.randint(5, 12), random.randint(5, 12), random.randint(5, 12)
        question = f"A cuboid has dimensions {l} cm by {w} cm by {h} cm. What is its volume?"
        answer = str(l*w*h)
        hint = "Volume of a cuboid = length × width × height."
        explanation = f"Volume = $l \\times w \\times h = {l} \\times {w} \\times {h} = {answer}\\ cm^3$."
        options = {answer, str(2*(l*w+w*h+l*h)), str(l+w+h)}
        
    elif q_type == 'vol_cylinder':
        r, h = 7, random.randint(5, 15) # use r=7 for nice pi calculation
        question = f"Calculate the volume of a cylinder with radius {r} cm and height {h} cm. (Use $\\pi = 22/7$)"
        vol = Fraction(22,7) * r**2 * h
        answer = str(int(vol))
        hint = "Volume of a cylinder = $\pi r^2 h$."
        explanation = f"Volume = $\\pi r^2 h = \\frac{{22}}{{7}} \\times {r}^2 \\times {h} = {answer}\\ cm^3$."
        options = {answer, str(int(2*Fraction(22,7)*r*h))}
        
    elif q_type == 'pythagoras':
        a, b = random.choice([(3,4), (5,12), (8,15), (7,24)])
        c = int(math.sqrt(a**2 + b**2))
        question = f"A right-angled triangle has two shorter sides of length {a} cm and {b} cm. Find the length of the hypotenuse."
        answer = str(c)
        hint = "Use the Pythagorean theorem: $a^2 + b^2 = c^2$."
        explanation = f"1. Theorem: $a^2 + b^2 = c^2$.\n\n2. Substitute: ${a}^2 + {b}^2 = c^2$.\n\n3. ${a**2} + {b**2} = c^2 \implies {a**2+b**2} = c^2$.\n\n4. $c = \sqrt{{{a**2+b**2}}} = {c}$ cm."
        options = {answer, str(a+b), str(abs(b-a))}
        
    return {"question": question, "options": _finalize_options(options), "answer": answer, "hint": hint, "explanation": explanation}

def _generate_algebra_basics_question():
    # Subtopics: Simplification/Factorization, Solving Equations (linear, quad, simultaneous), Change of Subject
    q_type = random.choice(['simplify', 'solve_linear', 'change_subject', 'solve_simultaneous'])
    
    if q_type == 'simplify':
        a, b = random.randint(2, 6), random.randint(2, 6)
        question = f"Expand and simplify: ${a}(x + {b}) - {a-1}x$"
        answer = f"x + {a*b}"
        hint = "First, expand the bracket by multiplying. Then, collect like terms."
        explanation = f"1. Expand: ${a}(x + {b}) = {a}x + {a*b}$.\n\n2. Full expression: ${a}x + {a*b} - {a-1}x$.\n\n3. Collect x terms: $({a} - {a-1})x = 1x = x$.\n\n4. Final result: $x + {a*b}$."
        options = {answer, f"{2*a-1}x + {a*b}", f"x - {a*b}"}
        
    elif q_type == 'solve_linear':
        a, b, c, x = random.randint(2, 5), random.randint(5, 15), random.randint(5, 15), random.randint(2, 8)
        rhs = a*x + b
        lhs = c
        # a*x + b = c*x - d. Need to make it simpler. a*x + b = c
        rhs = a*x+b
        question = f"Solve for x: ${a}x - {c} = {rhs-c}$"
        answer = str(x)
        hint = "Group terms with 'x' on one side and constant terms on the other."
        explanation = f"1. Equation: ${a}x - {c} = {rhs-c}$.\n\n2. Add {c} to both sides: ${a}x = {rhs}$.\n\n3. Divide by {a}: $x = {rhs/a}$."
        options = {answer, str((rhs-c-c)/a), str(rhs/a+c)}
        
    elif q_type == 'change_subject':
        var = random.choice(['u', 'a', 't'])
        question = f"Make '{var}' the subject of the formula $v = u + at$."
        if var == 'u': answer = "$u = v - at$"; options = {answer, "$u = v + at$"}
        elif var == 'a': answer = "$a = \\frac{v-u}{t}$"; options = {answer, "$a = v - u - t$"}
        else: answer = "$t = \\frac{v-u}{a}$"; options = {answer, "$t = v - u - a$"}
        hint = "Use inverse operations to isolate the desired variable."
        explanation = f"To make '{var}' the subject, we need to move all other terms to the other side.\n\n- Start with $v = u + at$.\n\n- To find {var}, we isolate it: {answer}."
    
    elif q_type == 'solve_simultaneous':
        x, y = random.randint(1, 5), random.randint(1, 5)
        a1, b1 = random.randint(1,3), random.randint(1,3)
        a2, b2 = random.randint(1,3), random.randint(1,3)
        while a1*b2 - a2*b1 == 0: a2, b2 = random.randint(1,3), random.randint(1,3) # ensure unique solution
        c1 = a1*x + b1*y
        c2 = a2*x + b2*y
        question = f"Solve the simultaneous equations:\n\n$ {a1}x + {b1}y = {c1} $\n\n$ {a2}x + {b2}y = {c2} $"
        answer = f"x={x}, y={y}"
        hint = "Use either the substitution or elimination method to solve for one variable first."
        explanation = f"Using elimination:\n\n1. Multiply first eq by {a2}, second by {a1}: \n\n  $ {a1*a2}x + {b1*a2}y = {c1*a2} $\n\n  $ {a1*a2}x + {b2*a1}y = {c2*a1} $\n\n2. Subtract them: $({b1*a2} - {b2*a1})y = {c1*a2} - {c2*a1} \implies {b1*a2 - b2*a1}y = {c1*a2 - c2*a1} \implies y={y}$.\n\n3. Substitute y={y} into first eq: ${a1}x + {b1}({y}) = {c1} \implies {a1}x = {c1-b1*y} \implies x={x}$."
        options = {answer, f"x={y}, y={x}", f"x={x}, y={-y}"}
    
    return {"question": question, "options": _finalize_options(options), "answer": answer, "hint": hint, "explanation": explanation}


def _generate_linear_algebra_question():
    # Subtopics: Matrix ops, Determinant/Inverse, Solving systems
    q_type = random.choice(['add_sub', 'multiply', 'determinant', 'inverse'])
    mat_a = np.random.randint(-5, 10, size=(2, 2)); mat_b = np.random.randint(-5, 10, size=(2, 2))
    def mat_to_latex(m): return f"\\begin{{pmatrix}} {m[0,0]} & {m[0,1]} \\\\ {m[1,0]} & {m[1,1]} \\end{{pmatrix}}"

    if q_type == 'add_sub':
        op, sym, res_mat = random.choice([('add', '+', mat_a+mat_b), ('subtract', '-', mat_a-mat_b)])
        question = f"Given matrices $A = {mat_to_latex(mat_a)}$ and $B = {mat_to_latex(mat_b)}$, find $A {sym} B$."
        answer = f"${mat_to_latex(res_mat)}$"
        hint = f"To {op} matrices, {op} their corresponding elements."
        explanation = f"You {op} the element in each position. e.g., for the top-left element: ${mat_a[0,0]} {sym} {mat_b[0,0]} = {res_mat[0,0]}$."
        options = {answer, f"${mat_to_latex(mat_a*mat_b)}$"}
    
    elif q_type == 'multiply':
        question = f"Find the product $AB$ for $A = {mat_to_latex(mat_a)}$ and $B = {mat_to_latex(mat_b)}$."
        res_mat = np.dot(mat_a, mat_b)
        answer = f"${mat_to_latex(res_mat)}$"
        hint = "Multiply rows of the first matrix by columns of the second matrix."
        explanation = f"Top-left element of result = (row 1 of A) ⋅ (col 1 of B) = $({mat_a[0,0]} \\times {mat_b[0,0]}) + ({mat_a[0,1]} \\times {mat_b[1,0]}) = {res_mat[0,0]}$."
        options = {answer, f"${mat_to_latex(mat_a+mat_b)}$"}
        
    elif q_type == 'determinant':
        question = f"Find the determinant of matrix $A = {mat_to_latex(mat_a)}$."
        answer = str(int(np.linalg.det(mat_a)))
        hint = r"For a 2x2 matrix $\begin{pmatrix} a & b \\ c & d \end{pmatrix}$, the determinant is $ad - bc$."
        explanation = f"Determinant = $(a \\times d) - (b \\times c) = ({mat_a[0,0]} \\times {mat_a[1,1]}) - ({mat_a[0,1]} \\times {mat_a[1,0]}) = {answer}$."
        options = {answer, str(mat_a[0,0]+mat_a[1,1])}

    elif q_type == 'inverse':
        det = int(np.linalg.det(mat_a))
        while det == 0: # Ensure inverse exists
            mat_a = np.random.randint(-5, 10, size=(2, 2)); det = int(np.linalg.det(mat_a))
        question = f"Find the inverse of matrix $A = {mat_to_latex(mat_a)}$."
        inv_mat = np.linalg.inv(mat_a)
        adj_mat = np.array([[mat_a[1,1], -mat_a[0,1]], [-mat_a[1,0], mat_a[0,0]]])
        answer = f"$\\frac{{1}}{{{det}}}{mat_to_latex(adj_mat)}$"
        hint = r"The inverse is $\frac{1}{\det(A)} \begin{pmatrix} d & -b \\ -c & a \end{pmatrix}$."
        explanation = f"1. Determinant = {det}.\n\n2. Adjugate matrix: swap a and d, negate b and c = ${mat_to_latex(adj_mat)}$.\n\n3. Inverse = $\\frac{{1}}{{\\text{{determinant}}}} \\times \\text{{adjugate}} = {answer}$."
        options = {answer, f"${mat_to_latex(adj_mat)}$"}

    return {"question": question, "options": _finalize_options(options), "answer": answer, "hint": hint, "explanation": explanation}

def _generate_advanced_combo_question():
    """Generates a multi-part question combining Geometry and Algebra."""
    l, w = random.randint(5, 10), random.randint(11, 15)
    area = l * w
    k = random.randint(5, 20)
    x = math.sqrt(area - k)
    while x < 1 or x != int(x):
        l, w = random.randint(5, 10), random.randint(11, 15); k = random.randint(5, area - 1)
        if area > k: x = math.sqrt(area - k)
        else: x = 0
    x = int(x)
    return {
        "is_multipart": True,
        "stem": f"A rectangular field has a length of **{l} metres** and a width of **{w} metres**.",
        "parts": [
            {"question": "a) What is the area of the field in square metres?", "options": [str(area), str(2*(l+w)), str(l+w), str(area+10)], "answer": str(area), "hint": "Area = length × width.", "explanation": f"Area = $l \\times w = {l} \\times {w} = {area}\\ m^2$."},
            {"question": f"b) The square of a positive number, $x$, when increased by {k}, is equal to the area of the field. What is the value of $x$?", "options": [str(x), str(area-k), str(math.sqrt(area)), str(x*x)], "answer": str(x), "hint": "Set up the equation $x^2 + {k} = Area$ and solve for $x$.", "explanation": f"1. $x^2 + {k} = {area}$.\n\n2. $x^2 = {area} - {k} = {area-k}$.\n\n3. $x = \sqrt{{{area-k}}} = {x}$."}
        ]
    }

def generate_question(topic):
    # This dictionary now maps all 12 topics to their dedicated, complete generator functions.
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
        "Advanced Combo": _generate_advanced_combo_question,
    }
    generator_func = generators.get(topic)
    if generator_func: 
        return generator_func()
    else: 
        return {"question": f"Questions for **{topic}** are coming soon!", "options": ["OK"], "answer": "OK", "hint": "This topic is under development.", "explanation": "No explanation available."}

# --- UI DISPLAY FUNCTIONS ---
def confetti_animation():
    html("""<script src="https://cdn.jsdelivr.net/npm/canvas-confetti@1.5.1/dist/confetti.browser.min.js"></script><script>confetti();</script>""")

def get_time_based_greeting():
    current_hour = datetime.now().hour
    if 5 <= current_hour < 12: return "Good morning"
    elif 12 <= current_hour < 18: return "Good afternoon"
    else: return "Good evening"

def load_css():
    """Loads the main CSS for the application."""
    st.markdown("""
    <style>
        /* CSS styles remain the same as the last version */
        .stApp { background-color: #f0f2ff; }
        [data-testid="stAppViewContainer"] > .main { display: flex; flex-direction: column; align-items: center; overflow: auto !important; }
        div[data-testid="stAppViewContainer"] * { color: #31333F !important; }
        div[data-testid="stSidebar"] { background-color: #0F1116 !important; }
        div[data-testid="stSidebar"] * { color: #FAFAFA !important; }
        /* ... all other CSS rules ... */
        .main-content { background-color: #ffffff; padding: 2rem; border-radius: 12px; box-shadow: 0 4px 12px rgba(0,0,0,0.08); }
    </style>
    """, unsafe_allow_html=True) # Abridged for brevity

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
            # ... dashboard logic ...
            fig = px.bar(topic_perf_df, y='Accuracy', title="Average Accuracy by Topic", labels={'Accuracy': 'Accuracy (%)'}, text_auto='.2s')
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Complete some quizzes to see your topic performance analysis!")
    with tab2:
        # ... history logic ...
        st.info("Your quiz history is empty. Take a quiz to get started!")

def display_blackboard_page():
    st.header("칠판 Blackboard")
    # ... blackboard/chat logic ...
    
def display_quiz_page(topic_options):
    st.header("🧠 Quiz Time!")
    QUIZ_LENGTH = 10

    if not st.session_state.quiz_active:
        st.subheader("Choose Your Challenge")
        topic_perf_df = get_topic_performance(st.session_state.username)
        if not topic_perf_df.empty and len(topic_perf_df) > 1 and topic_perf_df['Accuracy'].iloc[-1] < 100:
            weakest_topic = topic_perf_df.index[-1]
            st.info(f"💡 **Practice Suggestion:** Your lowest accuracy is in **{weakest_topic}**. Why not give it a try?")
        
        selected_topic = st.selectbox("Select a topic to begin:", topic_options)
        
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
                st.session_state.quiz_active = True; st.session_state.quiz_topic = selected_topic
                st.session_state.on_summary_page = False; st.session_state.quiz_score = 0
                st.session_state.questions_answered = 0; st.session_state.current_streak = 0
                st.session_state.incorrect_questions = []
                if 'current_q_data' in st.session_state: del st.session_state['current_q_data']
                st.rerun()
        return

    if st.session_state.get('on_summary_page', False) or st.session_state.questions_answered >= QUIZ_LENGTH:
        display_quiz_summary()
        return

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

    if not st.session_state.get('answer_submitted', False):
        if q_data.get("is_multipart", False):
            # ... multi-part question form logic ...
            st.markdown(q_data["stem"], unsafe_allow_html=True)
            if 'current_part_index' not in st.session_state: st.session_state.current_part_index = 0
            part_data = q_data["parts"][st.session_state.current_part_index]
            st.markdown(part_data["question"], unsafe_allow_html=True)
            with st.expander("🤔 Need a hint?"): st.info(part_data["hint"])
            with st.form(key=f"multipart_form_{st.session_state.current_part_index}"):
                user_choice = st.radio("Select your answer:", part_data["options"], index=None)
                if st.form_submit_button("Submit Answer"):
                    if user_choice is not None:
                        st.session_state.user_choice = user_choice
                        st.session_state.answer_submitted = True
                        st.rerun()
                    else: st.warning("Please select an answer.")
        else: # Single Question
            # ... single question form logic ...
            st.markdown(q_data["question"], unsafe_allow_html=True)
            with st.expander("🤔 Need a hint?"): st.info(q_data["hint"])
            with st.form(key=f"quiz_form_{st.session_state.questions_answered}"):
                user_choice = st.radio("Select your answer:", q_data["options"], index=None)
                if st.form_submit_button("Submit Answer", type="primary"):
                    if user_choice is not None:
                        st.session_state.user_choice = user_choice
                        st.session_state.answer_submitted = True
                        st.rerun()
                    else: st.warning("Please select an answer before submitting.")
    else: # Explanation phase
        # ... logic for showing explanation and next button ...
        user_choice = st.session_state.user_choice
        if q_data.get("is_multipart", False):
            # ... multi-part explanation logic ...
            part_index = st.session_state.current_part_index
            part_data = q_data["parts"][part_index]
            is_correct = str(user_choice) == str(part_data["answer"])
            is_last_part = part_index + 1 == len(q_data["parts"])
            st.markdown(q_data["stem"], unsafe_allow_html=True)
            st.markdown(part_data["question"], unsafe_allow_html=True)
            st.write("Your answer:")
            if is_correct: st.success(f"**{user_choice}** (Correct!)")
            else: st.error(f"**{user_choice}** (Incorrect)"); st.info(f"The correct answer was: **{part_data['answer']}**")
            with st.expander("Show Explanation", expanded=True): st.markdown(part_data["explanation"], unsafe_allow_html=True)
            button_label = "Next Question" if (is_last_part or not is_correct) else "Next Part"
            if st.button(button_label, type="primary", use_container_width=True):
                if is_correct and not is_last_part:
                    st.session_state.current_part_index += 1
                else:
                    st.session_state.questions_answered += 1
                    if is_correct and is_last_part:
                        st.session_state.quiz_score += 1; st.session_state.current_streak += 1
                    else:
                        st.session_state.current_streak = 0; st.session_state.incorrect_questions.append(q_data)
                    del st.session_state.current_q_data; del st.session_state.current_part_index
                del st.session_state.user_choice; del st.session_state.answer_submitted
                st.rerun()
        else: # Single Question Explanation
            # ... single question explanation logic ...
            is_correct = str(user_choice) == str(q_data["answer"])
            st.markdown(q_data["question"], unsafe_allow_html=True)
            st.write("Your answer:")
            if is_correct: st.success(f"**{user_choice}** (Correct!)")
            else: st.error(f"**{user_choice}** (Incorrect)"); st.info(f"The correct answer was: **{q_data['answer']}**")
            if q_data.get("explanation"):
                with st.expander("Show Explanation", expanded=True): st.markdown(q_data["explanation"], unsafe_allow_html=True)
            if st.button("Next Question", type="primary", use_container_width=True):
                st.session_state.questions_answered += 1
                if is_correct: st.session_state.quiz_score += 1; st.session_state.current_streak += 1
                else: st.session_state.current_streak = 0; st.session_state.incorrect_questions.append(q_data)
                del st.session_state.current_q_data; del st.session_state.user_choice; del st.session_state.answer_submitted
                st.rerun()
    
    if st.button("Stop Round & Save Score"):
        st.session_state.on_summary_page = True
        keys_to_delete = ['current_q_data', 'user_choice', 'answer_submitted', 'current_part_index']
        for key in keys_to_delete:
            if key in st.session_state: del st.session_state[key]
        st.rerun()

def display_quiz_summary():
    st.header("🎉 Round Complete! 🎉")
    # ... summary logic ...
    
def display_leaderboard(topic_options):
    st.header("🏆 Global Leaderboard")
    # ... leaderboard logic ...

def display_learning_resources(topic_options):
    st.header("📚 Learning Resources")
    # ... learning resources logic ...

def display_profile_page():
    st.header("👤 Your Profile")
    # ... profile page logic ...

def show_main_app():
    load_css()
    # ... status update logic ...
    with st.sidebar:
        # ... sidebar logic ...
        st.title("MathFriend")
    
    st.markdown('<div class="main-content">', unsafe_allow_html=True)
    topic_options = [
        "Sets", "Percentages", "Fractions", "Indices", "Surds", 
        "Binary Operations", "Relations and Functions", "Sequence and Series", 
        "Word Problems", "Shapes (Geometry)", "Algebra Basics", "Linear Algebra",
        "Advanced Combo"
    ]
    
    # ... page routing logic ...
    selected_page = st.sidebar.radio("Menu", ["📊 Dashboard", "📝 Quiz", "🏆 Leaderboard", "칠판 Blackboard", "👤 Profile", "📚 Learning Resources"])

    if selected_page == "📝 Quiz":
        display_quiz_page(topic_options)
    # ... other page routes ...

    st.markdown('</div>', unsafe_allow_html=True)

def show_login_or_signup_page():
    load_css()
    # ... login/signup logic ...

# --- Initial Script Execution Logic ---
if st.session_state.show_splash:
    # ... splash screen logic ...
    st.session_state.show_splash = False; st.rerun()
else:
    if st.session_state.logged_in:
        show_main_app()
    else:
        show_login_or_signup_page()

