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
        "questions_attempted": 0, # NEW VARIABLE
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
    """Creates, verifies, and populates necessary database tables."""
    try:
        with engine.connect() as conn:
            # --- Standard Tables ---
            conn.execute(text('''CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, password TEXT)'''))
            conn.execute(text('''CREATE TABLE IF NOT EXISTS quiz_results
                         (id SERIAL PRIMARY KEY, username TEXT, topic TEXT, score INTEGER,
                          questions_answered INTEGER, timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP)'''))
            conn.execute(text('''CREATE TABLE IF NOT EXISTS user_profiles
                         (username TEXT PRIMARY KEY, full_name TEXT, school TEXT, age INTEGER, bio TEXT)'''))
            conn.execute(text('''CREATE TABLE IF NOT EXISTS user_status
                         (username TEXT PRIMARY KEY, is_online BOOLEAN, last_seen TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP)'''))
            
            # --- Daily Challenge Tables ONLY ---
            conn.execute(text('''CREATE TABLE IF NOT EXISTS daily_challenges (
                                id SERIAL PRIMARY KEY,
                                description TEXT NOT NULL,
                                topic TEXT NOT NULL, 
                                target_count INTEGER NOT NULL
                            )'''))
            conn.execute(text('''CREATE TABLE IF NOT EXISTS user_daily_progress (
                                username TEXT NOT NULL,
                                challenge_date DATE NOT NULL,
                                challenge_id INTEGER REFERENCES daily_challenges(id),
                                progress_count INTEGER DEFAULT 0,
                                is_completed BOOLEAN DEFAULT FALSE,
                                PRIMARY KEY (username, challenge_date)
                            )'''))

            # --- Populate daily_challenges if it's empty ---
            result = conn.execute(text("SELECT COUNT(*) FROM daily_challenges")).scalar_one()
            if result == 0:
                print("Populating daily_challenges table for the first time.")
                challenges = [
                    ("Answer 5 questions correctly on any topic.", "Any", 5),
                    ("Get 3 correct answers in a Fractions quiz.", "Fractions", 3),
                    ("Get 3 correct answers in a Surds quiz.", "Surds", 3),
                    ("Score at least 4 in an Algebra Basics quiz.", "Algebra Basics", 4),
                    ("Complete any quiz with a score of 5 or more.", "Any", 5)
                ]
                conn.execute(text("INSERT INTO daily_challenges (description, topic, target_count) VALUES (:description, :topic, :target_count)"), 
                             [{"description": d, "topic": t, "target_count": c} for d, t, c in challenges])
            
            conn.commit()
        print("Database tables created or verified successfully, including Daily Challenge tables.")
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
    
    # Call the daily challenge updater
    update_daily_challenge_progress(username, topic, score)
@st.cache_data(ttl=300) # Cache for 300 seconds (5 minutes)
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

@st.cache_data(ttl=60) # Cache for 60 seconds
def get_user_stats(username):
    with engine.connect() as conn:
        total_quizzes = conn.execute(text("SELECT COUNT(*) FROM quiz_results WHERE username = :username"), {"username": username}).scalar_one()
        last_result = conn.execute(text("SELECT score, questions_answered FROM quiz_results WHERE username = :username ORDER BY timestamp DESC LIMIT 1"), {"username": username}).first()
        last_score_str = f"{last_result[0]}/{last_result[1]}" if last_result and last_result[1] > 0 else "N/A"
        top_result = conn.execute(text("SELECT score, questions_answered FROM quiz_results WHERE username = :username AND questions_answered > 0 ORDER BY (CAST(score AS REAL) / questions_answered) DESC, score DESC LIMIT 1"), {"username": username}).first()
        top_score_str = f"{top_result[0]}/{top_result[1]}" if top_result and top_result[1] > 0 else "N/A"
        return total_quizzes, last_score_str, top_score_str

@st.cache_data(ttl=60)
def get_user_quiz_history(username):
    try:
        with engine.connect() as conn:
            result = conn.execute(text("SELECT topic, score, questions_answered, timestamp FROM quiz_results WHERE username = :username ORDER BY timestamp DESC"), {"username": username})
            return result.mappings().fetchall()
    except Exception as e:
        st.error(f"Error fetching quiz history: {e}")
        return []

def get_or_create_daily_challenge(username):
    """Fetches or assigns a daily challenge for a user."""
    today = datetime.now().date()
    with engine.connect() as conn:
        progress_query = text("""
            SELECT p.progress_count, p.is_completed, c.description, c.topic, c.target_count 
            FROM user_daily_progress p JOIN daily_challenges c ON p.challenge_id = c.id
            WHERE p.username = :username AND p.challenge_date = :today
        """)
        result = conn.execute(progress_query, {"username": username, "today": today}).mappings().first()
        
        if result:
            return dict(result)
        else:
            challenge_ids_query = text("SELECT id FROM daily_challenges")
            challenge_ids = [row[0] for row in conn.execute(challenge_ids_query).fetchall()]
            if not challenge_ids: return None
            
            new_challenge_id = random.choice(challenge_ids)
            
            insert_query = text("""
                INSERT INTO user_daily_progress (username, challenge_date, challenge_id)
                VALUES (:username, :today, :challenge_id)
            """)
            conn.execute(insert_query, {"username": username, "today": today, "challenge_id": new_challenge_id})
            conn.commit()
            
            return get_or_create_daily_challenge(username)

def update_daily_challenge_progress(username, topic, score):
    """Updates daily challenge progress after a quiz."""
    today = datetime.now().date()
    challenge = get_or_create_daily_challenge(username)
    
    if not challenge or challenge['is_completed']:
        return

    with engine.connect() as conn:
        if challenge['topic'] == 'Any' or challenge['topic'] == topic:
            new_progress = challenge['progress_count'] + score
            
            update_progress_query = text("""
                UPDATE user_daily_progress 
                SET progress_count = :new_progress 
                WHERE username = :username AND challenge_date = :today
            """)
            conn.execute(update_progress_query, {"new_progress": new_progress, "username": username, "today": today})

            if new_progress >= challenge['target_count']:
                complete_challenge_query = text("""
                    UPDATE user_daily_progress SET is_completed = TRUE 
                    WHERE username = :username AND challenge_date = :today
                """)
                conn.execute(complete_challenge_query, {"username": username, "today": today})
                st.session_state.challenge_completed_toast = True # Flag for UI notification
            
            conn.commit()

def get_topic_performance(username):
    history = get_user_quiz_history(username)
    if not history: return pd.DataFrame()
    df = pd.DataFrame([{"Topic": r['topic'], "Score": r['score'], "Total": r['questions_answered']} for r in history])
    performance = df.groupby('Topic').sum()
    performance['Accuracy'] = (performance['Score'] / performance['Total'] * 100).fillna(0)
    return performance.sort_values(by="Accuracy", ascending=False)

@st.cache_data(ttl=300)
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

@st.cache_data(ttl=300)
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
    # The 'r' before the string ensures backslashes are treated literally for LaTeX
    return rf"\frac{{{f.numerator}}}{{{f.denominator}}}"
def _format_fraction_text(f: Fraction):
    if f.denominator == 1: return str(f.numerator)
    return f"{f.numerator}/{f.denominator}"

def _finalize_options(options_set, default_type="int"):
    """Ensures 4 unique options and shuffles them."""
    # Ensure options are strings before adding
    options_set = {str(o) for o in options_set}
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
        if op == 'divide' and f2.numerator == 0: f2 = Fraction(1, f2.denominator)

        # THIS IS THE ONLY FIX APPLIED TO THE FUNCTION
        # 1. Generate the LaTeX parts first and store them in simple variables.
        f1_latex = _get_fraction_latex_code(f1)
        f2_latex = _get_fraction_latex_code(f2)
        # 2. Assemble the final string from the simple variables.
        question = f"Calculate: ${f1_latex} {sym} {f2_latex}$"
        
        if op == 'add': 
            res = f1 + f2
        elif op == 'subtract': 
            res = f1 - f2
        elif op == 'multiply': 
            res = f1 * f2
        else: 
            res = f1 / f2
        
        answer = _format_fraction_text(res)
        hint = "For +/-, find a common denominator. For ×, multiply numerators/denominators. For ÷, invert the second fraction and multiply."
        explanation = f"To {op} ${_get_fraction_latex_code(f1)}$ and ${_get_fraction_latex_code(f2)}$, you follow the rule for that operation. The simplified result is ${_get_fraction_latex_code(res)}$."
        distractor = _format_fraction_text(Fraction(f1.numerator + f2.numerator, f1.denominator + f2.denominator)) if op in ['add', 'subtract'] else _format_fraction_text(f1*f2 if op == 'divide' else f1/f2)
        options = {answer, distractor}
    
    elif q_type == 'bodmas':
        a, b, c = [random.randint(2, 6) for _ in range(3)]
        # This includes the fix from our previous discussion to add the '$' delimiters
        question = f"Evaluate the expression: $ (\\frac{{1}}{{{a}}} + \\frac{{1}}{{{b}}}) \\times {c} $"
        res = (Fraction(1, a) + Fraction(1, b)) * c
        answer = _format_fraction_text(res)
        hint = "Follow BODMAS. Solve the operation inside the brackets first."
        explanation = f"1. Bracket: $\\frac{{1}}{{{a}}} + \\frac{{1}}{{{b}}} = \\frac{{{b}+{a}}}{{{a*b}}}$.\n\n2. Multiply: $\\frac{{{a+b}}}{{{a*b}}} \\times {c} = {_get_fraction_latex_code(res)}$."
        distractor = _format_fraction_text(Fraction(1,a) + Fraction(1,b)*c)
        options = {answer, distractor}
        
    elif q_type == 'word_problem':
        total = random.randint(20, 40)
        den = random.choice([3, 4, 5])
        num = random.randint(1, den-1)
        spent = Fraction(num, den)
        remaining = total * (1-spent)
        # This wording is reverted to your original version
        question = f"Kofi had GHS {total}. He spent $\\frac{{{num}}}{{{den}}}$ of it on airtime. How much money does he have left?"
        answer = f"GHS {remaining}"
        hint = "First, find the amount spent by multiplying the fraction by the total. Then, subtract this from the total."
        explanation = f"1. Amount spent = $\\frac{{{num}}}{{{den}}} \\times {total} = {total*spent}$.\n\n2. Money left = Total - Spent = {total} - {total*spent} = {remaining}."
        # The options are reverted to your original version's formatting
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
        while b*b == c: b = random.randint(2,9)
        question = f"Rationalize the denominator of $\\frac{{{a}}}{{{b} - \sqrt{{{c}}}}}$"
        num = f"{a*b} + {a}\sqrt{{{c}}}"
        den = b**2 - c
        answer = f"$\\frac{{{num}}}{{{den}}}$"
        hint = f"Multiply the numerator and denominator by the conjugate of the denominator, which is $({b} + \sqrt{{{c}}})$."
        explanation = f"1. Conjugate of ${b} - \sqrt{{{c}}}$ is ${b} + \sqrt{{{c}}}$.\n\n2. Multiply top and bottom: $\\frac{{{a}}}{{{b} - \sqrt{{{c}}}}} \\times \\frac{{{b} + \sqrt{{{c}}}}}{{{b} + \sqrt{{{c}}}}}$.\n\n3. Numerator: ${a}({b} + \sqrt{{{c}}}) = {num}$.\n\n4. Denominator (using $(x-y)(x+y)=x^2-y^2$): ${b}^2 - (\sqrt{{{c}}})^2 = {b**2} - {c} = {den}$.\n\n5. Final Answer: ${answer}$."
        options = {answer, f"$\\frac{{{num}}}{{{b-c}}}$", f"$\\frac{{{a}}}{{{den}}}$"}
        
    elif q_type == 'equation':
        x_val = random.randint(3, 20)
        c = random.randint(1, 5)
        result = int(math.sqrt(x_val - c))
        while (x_val - c) < 0 or math.sqrt(x_val-c) != result:
            x_val = random.randint(3, 20); c = random.randint(1, 5);
            if (x_val-c) >=0: result = int(math.sqrt(x_val-c))
        question = f"Solve for x: $\sqrt{{x - {c}}} = {result}$"
        answer = str(x_val)
        hint = "To solve for x, square both sides of the equation to eliminate the square root."
        explanation = f"1. Given: $\sqrt{{x - {c}}} = {result}$.\n\n2. Square both sides: $(\sqrt{{x - {c}}})^2 = {result}^2$.\n\n3. This simplifies to: $x - {c} = {result**2}$.\n\n4. Add {c} to both sides: $x = {result**2} + {c} = {x_val}$."
        options = {answer, str(result**2), str(x_val+c)}

    return {"question": question, "options": _finalize_options(options), "answer": answer, "hint": hint, "explanation": explanation}

def _generate_binary_ops_question():
    # Subtopics: Evaluate, Identity/Inverse, Properties
    q_type = random.choice(['evaluate', 'identity_inverse', 'properties'])
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
        explanation = f"1. The definition is ${op_def}$.\n\n2. We substitute a={a} and b={b}.\n\n3. The calculation becomes: {op_func(a,b)}."
        options = {answer, str(op_func(b, a)), str(a*b)}

    elif q_type == 'identity_inverse':
        element = random.randint(4, 10)
        question = f"For the binary operation $a \\ast b = a+b-3$, the identity element is 3. Find the inverse of {element}."
        answer = str(6 - element)
        hint = "The inverse 'a⁻¹' of an element 'a' satisfies $a \\ast a^{{-1}} = e$, where 'e' is the identity element. Solve for a⁻¹."
        explanation = f"1. Let the inverse of {element} be $inv$.\n\n2. The formula is ${element} \\ast inv = 3$.\n\n3. Using the definition: ${element} + inv - 3 = 3$.\n\n4. $inv - 3 = {3-element}$.\n\n5. $inv = {3-element+3} = {6-element}$."
        options = {answer, str(-element), str(element-3)}

    elif q_type == 'properties':
        op_def_c, func_c, sym_c = (r"a \Delta b = a + b + ab", lambda x,y: x+y+x*y, r"\Delta") # Commutative
        op_def_nc, func_nc, sym_nc = (r"a \circ b = a - 2b", lambda x,y: x-2*y, r"\circ") # Not commutative
        chosen_op, chosen_func, chosen_sym, is_comm = random.choice([(op_def_c, func_c, sym_c, True), (op_def_nc, func_nc, sym_nc, False)])
        
        question = f"Is the binary operation ${chosen_op}$ on the set of real numbers commutative?"
        answer = "Yes" if is_comm else "No"
        hint = "A binary operation * is commutative if a * b = b * a for all values of a and b."
        a_b, b_a = chosen_func(a,b), chosen_func(b,a)
        explanation = f"To check for commutativity, we test if $a {chosen_sym} b = b {chosen_sym} a$.\n\n- Let's test with a={a}, b={b}:\n\n- ${a} {chosen_sym} {b} = {a_b}$\n\n- ${b} {chosen_sym} {a} = {b_a}$\n\n- Since ${a_b} {'==' if a_b==b_a else '!='} {b_a}$, the operation is {'' if is_comm else 'not '}commutative."
        options = {"Yes", "No"}

    return {"question": question, "options": _finalize_options(options), "answer": answer, "hint": hint, "explanation": explanation}

def _generate_relations_functions_question():
    # Subtopics: Domain/Range, Evaluate, Composite, Inverse
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
    # Subtopics: Linear equations, simultaneous, age, consecutive integers
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
        while kofi_age - 2*ama_age <= 0:
            ama_age, kofi_age = random.randint(5, 10), random.randint(15, 25)
        ans_val = kofi_age - 2*ama_age
        question = f"Ama is {ama_age} years old and Kofi is {kofi_age} years old. In how many years will Kofi be twice as old as Ama?"
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
    # Subtopics: Perimeter/Area (rect, tri, circle), Volume/Surface Area (cuboid, cylinder), Pythagoras
    q_type = random.choice(['area_rect', 'area_circle', 'vol_cuboid', 'vol_cylinder', 'pythagoras'])
    
    if q_type == 'area_rect':
        l, w = random.randint(5, 20), random.randint(5, 20)
        question = f"A rectangle has a length of {l} cm and a width of {w} cm. Calculate its area."
        answer = str(l*w)
        hint = "Area of a rectangle = length × width."
        explanation = f"Area = $l \\times w = {l} \\times {w} = {answer}\\ cm^2$."
        options = {answer, str(2*(l+w)), str(l+w)}

    elif q_type == 'area_circle':
        r = 7 # Use 7 or 14 for nice pi calculation
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
        r, h = 7, random.randint(5, 15)
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
    # Subtopics: Simplification, Solving Equations (linear, quad, simultaneous), Change of Subject
    q_type = random.choice(['simplify', 'solve_linear', 'change_subject', 'solve_simultaneous', 'solve_quadratic'])
    
    if q_type == 'simplify':
        a, b = random.randint(2, 6), random.randint(2, 6)
        question = f"Expand and simplify: ${a}(x + {b}) - {a-1}x$"
        answer = f"x + {a*b}"
        hint = "First, expand the bracket by multiplying. Then, collect like terms."
        explanation = f"1. Expand: ${a}(x + {b}) = {a}x + {a*b}$.\n\n2. Full expression: ${a}x + {a*b} - {a-1}x$.\n\n3. Collect x terms: $({a} - {a-1})x = 1x = x$.\n\n4. Final result: $x + {a*b}$."
        options = {answer, f"{2*a-1}x + {a*b}", f"x - {a*b}"}
        
    elif q_type == 'solve_linear':
        a, b, x = random.randint(2, 5), random.randint(5, 15), random.randint(2, 8)
        c = a * x + b
        question = f"Solve for x: ${a}x + {b} = {c}$"
        answer = str(x)
        hint = "Isolate the x term on one side of the equation, then divide."
        explanation = f"1. Equation: ${a}x + {b} = {c}$.\n\n2. Subtract {b} from both sides: ${a}x = {c-b}$.\n\n3. Divide by {a}: $x = {(c-b)/a}$."
        options = {answer, str(c-b), str((c+b)/a)}
        
    elif q_type == 'change_subject':
        var = random.choice(['u', 'a', 't'])
        question = f"Make '{var}' the subject of the formula $v = u + at$."
        if var == 'u': answer = "$u = v - at$"; options = {answer, "$u = v + at$"}
        elif var == 'a': answer = "$a = \\frac{v-u}{t}$"; options = {answer, "$a = v - u - t$"}
        else: answer = "$t = \\frac{v-u}{a}$"; options = {answer, "$t = v - u - a$"}
        hint = "Use inverse operations to isolate the desired variable."
        explanation = f"To make '{var}' the subject, we need to move all other terms to the other side.\n\n- Start with $v = u + at$.\n\n- To isolate {var}, we rearrange the formula to get: {answer}."
    
    elif q_type == 'solve_simultaneous':
        x, y = random.randint(1, 5), random.randint(1, 5)
        a1, b1 = random.randint(1,3), random.randint(1,3)
        a2, b2 = random.randint(1,3), random.randint(1,3)
        while a1*b2 - a2*b1 == 0: a2, b2 = random.randint(1,3), random.randint(1,3)
        c1 = a1*x + b1*y; c2 = a2*x + b2*y
        question = f"Solve the simultaneous equations:\n\n$ {a1}x + {b1}y = {c1} $\n\n$ {a2}x + {b2}y = {c2} $"
        answer = f"x={x}, y={y}"
        hint = "Use either the substitution or elimination method."
        explanation = f"Using elimination:\n\n1. Multiply first eq by {a2}, second by {a1}: \n\n  $ {a1*a2}x + {b1*a2}y = {c1*a2} $\n\n  $ {a1*a2}x + {b2*a1}y = {c2*a1} $\n\n2. Subtract them: $({b1*a2} - {b2*a1})y = {c1*a2} - {c2*a1} \implies {b1*a2 - b2*a1}y = {c1*a2 - c2*a1} \implies y={y}$.\n\n3. Substitute y={y} into first eq: ${a1}x + {b1}({y}) = {c1} \implies {a1}x = {c1-b1*y} \implies x={x}$."
        options = {answer, f"x={y}, y={x}", f"x={x}, y={-y}"}

    elif q_type == 'solve_quadratic':
        r1, r2 = random.randint(-5, 5), random.randint(-5, 5)
        while r1 == r2: r2 = random.randint(-5, 5)
        b = -(r1 + r2); c = r1 * r2; a = 1
        # To make it look more standard, ensure b and c are written with correct signs
        b_sign = "+" if b > 0 else "-"
        c_sign = "+" if c > 0 else "-"
        b_abs, c_abs = abs(b), abs(c)
        if b == 0:
            question = f"Solve the quadratic equation: $x^2 {c_sign} {c_abs} = 0$"
        else:
            question = f"Solve the quadratic equation: $x^2 {b_sign} {b_abs}x {c_sign} {c_abs} = 0$"
        answer = f"x={r1} or x={r2}"
        hint = "Factorize the quadratic expression or use the quadratic formula."
        explanation = f"This equation can be factorized by finding two numbers that multiply to {c} and add to {b}. These numbers are {-r1} and {-r2}.\n\nSo, $(x - ({r1}))(x - ({r2})) = 0$.\n\nThe solutions are $x = {r1}$ and $x = {r2}$."
        options = {answer, f"x={-r1} or x={-r2}", f"x={b} or x={c}"}
    
    return {"question": question, "options": _finalize_options(options), "answer": answer, "hint": hint, "explanation": explanation}


def _generate_linear_algebra_question():
    # Subtopics: Matrix ops, Determinant/Inverse
    q_type = random.choice(['add_sub', 'multiply', 'determinant', 'inverse'])
    mat_a = np.random.randint(-5, 10, size=(2, 2)); mat_b = np.random.randint(-5, 10, size=(2, 2))
    def mat_to_latex(m): return f"\\begin{{pmatrix}} {m[0,0]} & {m[0,1]} \\\\ {m[1,0]} & {m[1,1]} \\end{{pmatrix}}"

    if q_type == 'add_sub':
        op, sym, res_mat = random.choice([('add', '+', mat_a+mat_b), ('subtract', '-', mat_a-mat_b)])
        question = f"Given matrices $A = {mat_to_latex(mat_a)}$ and $B = {mat_to_latex(mat_b)}$, find $A {sym} B$."
        answer = f"${mat_to_latex(res_mat)}$"
        hint = f"To {op} matrices, {op} their corresponding elements."
        explanation = f"You {op} the element in each position. e.g., for the top-left element: ${mat_a[0,0]} {sym} {mat_b[0,0]} = {res_mat[0,0]}$."
        options = {answer, f"${mat_to_latex(np.dot(mat_a, mat_b))}$"}
    
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
        while det == 0:
            mat_a = np.random.randint(-5, 10, size=(2, 2)); det = int(np.linalg.det(mat_a))
        question = f"Find the inverse of matrix $A = {mat_to_latex(mat_a)}$."
        adj_mat = np.array([[mat_a[1,1], -mat_a[0,1]], [-mat_a[1,0], mat_a[0,0]]])
        answer = f"$\\frac{{1}}{{{det}}}{mat_to_latex(adj_mat)}$"
        hint = r"The inverse is $\frac{1}{\det(A)} \begin{pmatrix} d & -b \\ -c & a \end{pmatrix}$."
        explanation = f"1. Determinant = {det}.\n\n2. Adjugate matrix: swap a and d, negate b and c = ${mat_to_latex(adj_mat)}$.\n\n3. Inverse = $\\frac{{1}}{{\\text{{determinant}}}} \\times \\text{{adjugate}} = {answer}$."
        options = {answer, f"${mat_to_latex(adj_mat)}$"}

    return {"question": question, "options": _finalize_options(options), "answer": answer, "hint": hint, "explanation": explanation}

def _generate_logarithms_question():
    """Generates a multi-subtopic question for Logarithms."""
    # Subtopics: Conversion, Laws, Solving Equations, Change of Base
    q_type = random.choice(['conversion', 'laws', 'solve_simple', 'solve_combine'])
    question, answer, hint, explanation = "", "", "", ""
    options = set()

    if q_type == 'conversion':
        base = random.randint(2, 5)
        exponent = random.randint(2, 4)
        result = base ** exponent
        
        form_a, form_b = f"${base}^{{{exponent}}} = {result}$", f"$\\log_{{{base}}}({result}) = {exponent}$"
        
        if random.choice([True, False]):
            question = f"Express the equation {form_a} in logarithmic form."
            answer = form_b
            options = {answer, f"$\\log_{{{exponent}}}({result}) = {base}$", f"$\\log_{{{base}}}({exponent}) = {result}$"}
        else:
            question = f"Express the equation {form_b} in exponential form."
            answer = form_a
            options = {answer, f"${exponent}^{{{base}}} = {result}$", f"${result}^{{{exponent}}} = {base}$"}

        hint = "Remember the relationship: $\log_b(N) = x$ is the same as $b^x = N$."
        explanation = f"The base of the logarithm (${base}$) becomes the base of the power. The result of the logarithm (${exponent}$) becomes the exponent. So, {form_b} is equivalent to {form_a}."

    elif q_type == 'laws':
        val1, val2 = random.randint(2, 10), random.randint(2, 10)
        op, sym, res, rule_name = random.choice([
            ('add', '+', f"\\log({val1*val2})", "Product Rule"),
            ('subtract', '-', f"\\log(\\frac{{{val1}}}{{{val2}}})", "Quotient Rule")
        ])
        question = f"Simplify the expression: $\\log({val1}) {sym} \\log({val2})$"
        answer = f"${res}$"
        hint = f"Recall the {rule_name} for logarithms: $\log(A) + \log(B) = \log(AB)$ and $\log(A) - \log(B) = \log(A/B)$."
        explanation = f"Using the {rule_name}, $\\log({val1}) {sym} \\log({val2})$ simplifies to ${res}$."
        options = {answer, f"$\\log({val1+val2})$", f"$\\frac{{\\log({val1})}}{{\\log({val2})}}$"}

    elif q_type == 'solve_simple':
        base = random.randint(2, 4)
        result = random.randint(2, 4)
        x_val = base ** result
        question = f"Solve for x: $\\log_{{{base}}}(x) = {result}$"
        answer = str(x_val)
        hint = "Convert the logarithmic equation to its equivalent exponential form."
        explanation = f"1. The equation is $\\log_{{{base}}}(x) = {result}$.\n\n2. In exponential form, this is $x = {base}^{{{result}}}$.\n\n3. Therefore, $x = {x_val}$."
        options = {answer, str(base*result), str(result**base)}

    elif q_type == 'solve_combine':
        x_val = random.randint(3, 6)
        # We need log(x) + log(x-2) = log(x*(x-2)) = log(15) => x^2 - 2x - 15 = 0 => (x-5)(x+3)=0. x=5
        a, b = x_val, random.randint(1, x_val-1) # x, x-b
        result = a * (a-b)
        question = f"Solve for x: $\\log(x) + \\log(x - {b}) = \\log({result})$"
        answer = str(x_val)
        hint = "First, use the product rule to combine the logarithms on the left side."
        explanation = (f"1. Combine the logs on the left: $\\log(x(x-{b})) = \\log({result})$.\n\n"
                       f"2. Since the logs are equal, their arguments are equal: $x^2 - {b}x = {result}$.\n\n"
                       f"3. Rearrange into a quadratic equation: $x^2 - {b}x - {result} = 0$.\n\n"
                       f"4. Factor the quadratic: $(x - {x_val})(x + {x_val-b}) = 0$.\n\n"
                       f"5. The possible solutions are $x={x_val}$ and $x={-(x_val-b)}$. Since the logarithm of a negative number is undefined, the only valid solution is $x={x_val}$.")
        options = {answer, str(-(x_val-b)), str(result+b)}
        
    return {"question": question, "options": _finalize_options(options), "answer": answer, "hint": hint, "explanation": explanation}

def _generate_probability_question():
    """Generates a multi-subtopic question for Probability."""
    q_type = random.choice(['simple', 'combined', 'conditional'])
    
    if q_type == 'simple':
        red = random.randint(3, 8)
        blue = random.randint(3, 8)
        total = red + blue
        chosen_color = "red" if random.random() > 0.5 else "blue"
        num_chosen = red if chosen_color == "red" else blue
        
        question = f"A bag contains {red} red balls and {blue} blue balls. If one ball is picked at random, what is the probability that it is {chosen_color}?"
        answer_frac = Fraction(num_chosen, total)
        answer = _format_fraction_text(answer_frac)
        hint = "Probability = (Number of favorable outcomes) / (Total number of possible outcomes)."
        explanation = f"There are {num_chosen} {chosen_color} balls and a total of {total} balls. So, P({chosen_color}) = ${_get_fraction_latex_code(answer_frac)}$."
        options = {answer, _format_fraction_text(Fraction(red if chosen_color=='blue' else blue, total))}

    elif q_type == 'combined':
        # Probability of A or B (mutually exclusive)
        die_faces = {1, 2, 3, 4, 5, 6}
        evens = {2, 4, 6}
        greater_than_4 = {5, 6}
        union = evens.union(greater_than_4)
        
        question = "A fair six-sided die is rolled. What is the probability of rolling an even number or a number greater than 4?"
        answer_frac = Fraction(len(union), 6)
        answer = _format_fraction_text(answer_frac)
        hint = "Find the set of outcomes for each event and take their union. Be careful not to double-count."
        explanation = f"Event A (even) = {evens}. Event B (>4) = {greater_than_4}.\nThe combined event A or B is {union}, which has {len(union)} outcomes.\nTotal outcomes = 6.\nProbability = ${_get_fraction_latex_code(answer_frac)}$."
        options = {answer, _format_fraction_text(Fraction(len(evens)+len(greater_than_4), 6))}

    elif q_type == 'conditional':
        black = random.randint(3, 6)
        white = random.randint(3, 6)
        total = black + white
        question = f"A box in a shop in Kumasi contains {black} black pens and {white} white pens. Two pens are drawn one after the other **without replacement**. What is the probability that both are white?"
        prob_frac = Fraction(white, total) * Fraction(white - 1, total - 1)
        answer = _format_fraction_text(prob_frac)
        hint = "Calculate the probability of the first event, then the probability of the second event given the first has occurred, and multiply them."
        explanation = f"P(1st is white) = $\\frac{{{white}}}{{{total}}}$.\nAfter drawing one white pen, there are {white-1} white pens and {total-1} total pens left.\nP(2nd is white) = $\\frac{{{white-1}}}{{{total-1}}}$.\nTotal Probability = $\\frac{{{white}}}{{{total}}} \\times \\frac{{{white-1}}}{{{total-1}}} = {_get_fraction_latex_code(prob_frac)}$."
        options = {answer, _format_fraction_text(Fraction(white,total) * Fraction(white, total))}

    return {"question": question, "options": _finalize_options(options, "fraction"), "answer": answer, "hint": hint, "explanation": explanation}

def _generate_binomial_theorem_question():
    """Generates a question for the Binomial Theorem."""
    q_type = random.choice(['find_coefficient', 'find_term'])
    n = random.randint(4, 7)
    a, b = random.randint(1, 3), random.randint(1, 3)
    
    if q_type == 'find_coefficient':
        k = random.randint(2, n-1)
        question = f"Find the coefficient of the $x^{{{k}}}$ term in the expansion of $({a}x + {b})^{{{n}}}$."
        # Term is C(n,k) * (ax)^k * b^(n-k). Coefficient is C(n,k) * a^k * b^(n-k)
        coefficient = math.comb(n, k) * (a**k) * (b**(n-k))
        answer = str(coefficient)
        hint = f"Use the binomial theorem term formula: $\\binom{{n}}{{k}} a^{{n-k}} b^k$. Here, your 'a' is {a}x and 'b' is {b}, and you need the term where the power of x is {k}."
        explanation = f"The term with $x^{k}$ is given by $\\binom{{{n}}}{{{k}}}({a}x)^{{{k}}}({b})^{{{n-k}}}$.\nThe coefficient is $\\binom{{{n}}}{{{k}}} \\times {a}^{k} \\times {b}^{{{n-k}}} = {math.comb(n,k)} \\times {a**k} \\times {b**(n-k)} = {answer}$."
        options = {answer, str(math.comb(n,k) * (a**k)), str(math.comb(n,k))}

    elif q_type == 'find_term':
        r = random.randint(2, n-1) # find the r-th term
        # r-th term uses k = r-1
        k = r - 1
        term_coeff = math.comb(n, k) * (a**k) * (b**(n-k))
        term_power = k
        question = f"Find the {r}th term in the expansion of $({a}x + {b})^{{{n}}}$."
        answer = f"${term_coeff}x^{{{term_power}}}$"
        hint = f"The r-th term is given by the formula $\\binom{{n}}{{r-1}} a^{{n-(r-1)}} b^{{r-1}}$. Be careful with the variables."
        explanation = f"For the {r}th term, we use $k = {r}-1 = {k}$.\nThe term is $\\binom{{{n}}}{{{k}}}({a}x)^{{{k}}}({b})^{{{n-k}}} = {math.comb(n,k)} \\times {a**k}x^{k} \\times {b**(n-k)} = {answer}$."
        options = {answer, f"${math.comb(n,r)}x^{{{r}}}$"}

    return {"question": question, "options": _finalize_options(options), "answer": answer, "hint": hint, "explanation": explanation}

def _generate_polynomial_functions_question():
    """Generates a question for Polynomial Functions."""
    q_type = random.choice(['remainder_theorem', 'factor_theorem'])
    
    if q_type == 'remainder_theorem':
        a, b, c, d = [random.randint(-5, 5) for _ in range(4)]
        divisor_root = random.randint(-3, 3)
        question = f"Find the remainder when the polynomial $P(x) = {a}x^3 + {b}x^2 + {c}x + {d}$ is divided by $(x - {divisor_root})$."
        # Remainder is P(divisor_root)
        remainder = a*(divisor_root**3) + b*(divisor_root**2) + c*divisor_root + d
        answer = str(remainder)
        hint = f"According to the Remainder Theorem, the remainder when $P(x)$ is divided by $(x-a)$ is $P(a)$. Here, a = {divisor_root}."
        explanation = f"We need to evaluate $P({divisor_root})$:\n$P({divisor_root}) = {a}({divisor_root})^3 + {b}({divisor_root})^2 + {c}({divisor_root}) + {d} = {remainder}$."
        options = {answer, str(d), str(a+b+c+d)}

    elif q_type == 'factor_theorem':
        root = random.randint(1, 3)
        a, c, d = random.randint(1, 3), random.randint(1, 5), random.randint(1, 10)
        # P(root) = a*root^3 + k*root^2 + c*root + d = 0
        # k*root^2 = -(a*root^3 + c*root + d)
        k = - (a*(root**3) + c*root + d) // (root**2)
        while k == 0: k = random.randint(-3, 3)
        
        # Verify P(root) is 0
        p_val = a*(root**3) + k*(root**2) + c*root + d
        if p_val != 0: return _generate_polynomial_functions_question() # Regenerate if numbers don't work out
        
        question = f"Given that $(x - {root})$ is a factor of the polynomial $P(x) = {a}x^3 + kx^2 + {c}x + {d}$, find the value of the constant $k$."
        answer = str(k)
        hint = f"By the Factor Theorem, if $(x-a)$ is a factor of $P(x)$, then $P(a) = 0$. Solve for $k$."
        explanation = f"Since $(x - {root})$ is a factor, we know that $P({root}) = 0$.\n$P({root}) = {a}({root})^3 + k({root})^2 + {c}({root}) + {d} = 0$.\n${a*root**3} + {k*root**2}k + {c*root+d} = 0$.\n${k*root**2}k = -({a*root**3 + c*root+d})$.\n$k = {- (a*root**3 + c*root+d)} / {root**2} = {k}$."
        options = {answer, str(-k), str(root)}

    return {"question": question, "options": _finalize_options(options), "answer": answer, "hint": hint, "explanation": explanation}

def _generate_trigonometry_question():
    """Generates a question for Trigonometry."""
    q_type = random.choice(['solve_equation', 'identity', 'cosine_rule'])

    if q_type == 'solve_equation':
        val, func, func_name = random.choice([(0.5, math.sin, "sin"), (0.5, math.cos, "cos")])
        if func_name == "sin": solutions = "30, 150"; principal_val = 30
        else: solutions = "60, 300"; principal_val = 60
            
        question = f"Solve the equation $2{func_name}(\\theta) = 1$ for $0^\\circ \leq \\theta \leq 360^\\circ$."
        answer = f"{solutions[0]}°, {solutions[1]}°"
        hint = f"First, isolate ${func_name}(\\theta)$. Then find the principal value and use the CAST rule or function graph to find all solutions in the range."
        explanation = (f"1. ${func_name}(\\theta) = 1/2 = {val}$.\n"
                       f"2. The principal value (acute angle) is $\\theta = {principal_val}^\\circ$.\n"
                       f"3. Since ${func_name}$ is positive in the first and second (for sin) or fourth (for cos) quadrants, the solutions are:\n"
                       f"   - Q1: $\\theta = {principal_val}^\\circ$\n"
                       f"   - Q2/Q4: $\\theta = {180-principal_val if func_name=='sin' else 360-principal_val}^\\circ$\n"
                       f"So the solutions are {answer}.")
        options = {answer, f"{principal_val}°", f"{180-principal_val}°, {180+principal_val}°"}

    elif q_type == 'identity':
        question = r"Simplify the expression $\frac{{\sin^2\theta}}{{1 - \cos\theta}}$."
        answer = r"$1 + \cos\theta$"
        hint = "Use the fundamental identity $\sin^2\theta + \cos^2\theta = 1$ and the difference of two squares."
        explanation = r"1. Rewrite the numerator: $\sin^2\theta = 1 - \cos^2\theta$.\n2. Factor the numerator as a difference of two squares: $(1 - \cos\theta)(1 + \cos\theta)$.\n3. The expression becomes $\frac{{(1 - \cos\theta)(1 + \cos\theta)}}{{1 - \cos\theta}}$.\n4. Cancel the $(1 - \cos\theta)$ term, leaving $1 + \cos\theta$."
        options = {answer, r"$1 - \cos\theta$", r"$\cos\theta$"}

    elif q_type == 'cosine_rule':
        a, b, C_deg = random.randint(5, 10), random.randint(5, 10), 60
        c_sq = a**2 + b**2 - 2*a*b*math.cos(math.radians(C_deg))
        c = round(math.sqrt(c_sq), 2)
        question = f"In triangle ABC, side $a = {a}$ cm, side $b = {b}$ cm, and the included angle $C = {C_deg}^\\circ$. Find the length of side $c$."
        answer = f"{c} cm"
        hint = "Use the Cosine Rule: $c^2 = a^2 + b^2 - 2ab\cos(C)$."
        explanation = f"1. $c^2 = {a}^2 + {b}^2 - 2({a})({b})\cos({C_deg}^\\circ)$.\n2. $c^2 = {a**2} + {b**2} - {2*a*b}(0.5) = {c_sq}$.\n3. $c = \sqrt{{{c_sq}}} \\approx {c}$ cm."
        options = {answer, f"{round(math.sqrt(a**2 + b**2), 2)} cm"}

    return {"question": question, "options": _finalize_options(options), "answer": answer, "hint": hint, "explanation": explanation}

def _generate_vectors_question():
    """Generates a question for Vectors."""
    q_type = random.choice(['algebra', 'magnitude', 'dot_product'])
    
    if q_type == 'algebra':
        a = np.array([random.randint(-5, 5), random.randint(-5, 5)])
        b = np.array([random.randint(-5, 5), random.randint(-5, 5)])
        s1, s2 = random.randint(2, 4), random.randint(2, 4)
        
        question = f"Given vectors $\\mathbf{{a}} = \\binom{{{a[0]}}}{{{a[1]}}}$ and $\\mathbf{{b}} = \\binom{{{b[0]}}}{{{b[1]}}}$, find the vector ${s1}\\mathbf{{a}} - {s2}\\mathbf{{b}}$."
        result_vec = s1*a - s2*b
        answer = f"$\\binom{{{result_vec[0]}}}{{{result_vec[1]}}}$"
        hint = "Multiply each vector by its scalar first, then subtract the corresponding components."
        explanation = f"1. ${s1}\\mathbf{{a}} = {s1}\\binom{{{a[0]}}}{{{a[1]}}} = \\binom{{{s1*a[0]}}}{{{s1*a[1]}}}$.\n2. ${s2}\\mathbf{{b}} = {s2}\\binom{{{b[0]}}}{{{b[1]}}} = \\binom{{{s2*b[0]}}}{{{s2*b[1]}}}$.\n3. Subtract: $\\binom{{{s1*a[0]}}}{{{s1*a[1]}}} - \\binom{{{s2*b[0]}}}{{{s2*b[1]}}} = \\binom{{{s1*a[0] - s2*b[0]}}}{{{s1*a[1] - s2*b[1]}}} = {answer}$."
        options = {answer, f"$\\binom{{{a[0]-b[0]}}}{{{a[1]-b[1]}}}$"}

    elif q_type == 'magnitude':
        v = np.array([random.randint(2, 12), random.randint(2, 12)])
        question = f"Find the magnitude of the vector $\\mathbf{{v}} = {v[0]}\\mathbf{{i}} + {v[1]}\\mathbf{{j}}$."
        magnitude = round(np.linalg.norm(v), 2)
        answer = str(magnitude)
        hint = "The magnitude of a vector $x\mathbf{i} + y\mathbf{j}$ is $\sqrt{x^2 + y^2}$."
        explanation = f"Magnitude $|\mathbf{{v}}| = \sqrt{{({v[0]})^2 + ({v[1]})^2}} = \sqrt{{{v[0]**2} + {v[1]**2}}} = \sqrt{{{v[0]**2+v[1]**2}}} \\approx {answer}$."
        options = {answer, str(v[0]+v[1])}

    elif q_type == 'dot_product':
        a = np.array([random.randint(-5, 5), random.randint(-5, 5)])
        b = np.array([random.randint(-5, 5), random.randint(-5, 5)])
        while np.linalg.norm(a) == 0 or np.linalg.norm(b) == 0: # Avoid zero vectors
             a = np.array([random.randint(-5, 5), random.randint(-5, 5)]); b = np.array([random.randint(-5, 5), random.randint(-5, 5)])
        
        question = f"Find the angle between the vectors $\\mathbf{{a}} = \\binom{{{a[0]}}}{{{a[1]}}}$ and $\\mathbf{{b}} = \\binom{{{b[0]}}}{{{b[1]}}}$ to the nearest degree."
        dot_product = np.dot(a, b)
        mag_a, mag_b = np.linalg.norm(a), np.linalg.norm(b)
        cos_theta = dot_product / (mag_a * mag_b)
        angle_rad = np.arccos(np.clip(cos_theta, -1.0, 1.0)) # Clip for float precision errors
        angle_deg = round(np.degrees(angle_rad))
        answer = f"{angle_deg}°"
        hint = "Use the dot product formula: $\mathbf{a} \cdot \mathbf{b} = |\mathbf{a}| |\mathbf{b}| \cos\theta$."
        explanation = f"1. Dot Product: $\mathbf{{a}} \cdot \mathbf{{b}} = ({a[0]})({b[0]}) + ({a[1]})({b[1]}) = {dot_product}$.\n2. Magnitudes: $|\mathbf{{a}}| \\approx {round(mag_a, 2)}$, $|\mathbf{{b}}| \\approx {round(mag_b, 2)}$.\n3. $\cos\\theta = \\frac{{{dot_product}}}{{{round(mag_a,2)} \\times {round(mag_b,2)}}} \\approx {round(cos_theta, 2)}$.\n4. $\\theta = \cos^{{-1}}({round(cos_theta, 2)}) \\approx {answer}$."
        options = {answer, f"{round(dot_product)}°"}

    return {"question": question, "options": _finalize_options(options), "answer": answer, "hint": hint, "explanation": explanation}

# --- ADVANCED COMBO HELPER FUNCTIONS ---

def _combo_geometry_algebra():
    """ The original combo: Geometry -> Area -> Quadratic Equation """
    l, w = random.randint(5, 10), random.randint(11, 15)
    area = l * w
    k = random.randint(5, 20)
    x = math.sqrt(area - k)
    while x < 1 or x != int(x):
        l, w = random.randint(5, 10), random.randint(11, 15); area = l * w
        if area <= 5: continue
        k = random.randint(5, area - 2)
        x = math.sqrt(area - k)
    x = int(x)
    return {
        "is_multipart": True,
        "stem": f"A rectangular field in the Ashanti Region has a length of **{l} metres** and a width of **{w} metres**.",
        "parts": [
            {"question": "a) What is the area of the field in square metres?", "options": _finalize_options({str(area), str(2*(l+w))}), "answer": str(area), "hint": "Area = length × width.", "explanation": f"Area = $l \\times w = {l} \\times {w} = {area}\\ m^2$."},
            {"question": f"b) The square of a positive number, $x$, when increased by {k}, is equal to the area. Find $x$.", "options": _finalize_options({str(x), str(area-k)}), "answer": str(x), "hint": "Set up the equation $x^2 + {k} = Area$ and solve for $x$.", "explanation": f"1. $x^2 + {k} = {area}$.\n\n2. $x^2 = {area} - {k} = {area-k}$.\n\n3. $x = \sqrt{{{area-k}}} = {x}$."}
        ]
    }

def _combo_surds_geometry():
    """ Combo: Surds -> Pythagoras """
    a_val, b_val = random.choice([(5,11), (7,18), (3,13), (6,10)])
    question = f"A right-angled triangle has shorter sides of length $\sqrt{{{a_val}}}$ cm and $\sqrt{{{b_val}}}$ cm. Find the **square** of the length of the hypotenuse."
    answer = str(a_val + b_val)
    hint = "Use Pythagoras' theorem: $a^2 + b^2 = c^2$. Remember that $(\sqrt{x})^2 = x$."
    explanation = f"Let the sides be $a = \sqrt{{{a_val}}}$ and $b = \sqrt{{{b_val}}}$.\n\n1. By Pythagoras' theorem, the square of the hypotenuse, $c^2$, is $a^2 + b^2$.\n\n2. $c^2 = (\sqrt{{{a_val}}})^2 + (\sqrt{{{b_val}}})^2$.\n\n3. $c^2 = {a_val} + {b_val} = {answer}$.\nThe square of the hypotenuse is {answer} $cm^2$."
    return {
        "is_multipart": False, # This is a single question
        "question": question, "options": _finalize_options({answer, str(a_val*b_val), str(int(math.sqrt(a_val+b_val)))}),
        "answer": answer, "hint": hint, "explanation": explanation
    }

def _combo_trig_vectors():
    """ Combo: Vectors -> Dot Product -> Trigonometry """
    a = np.array([random.randint(-5, 5), random.randint(-5, 5)])
    b = np.array([random.randint(-5, 5), random.randint(-5, 5)])
    while np.linalg.norm(a) == 0 or np.linalg.norm(b) == 0:
         a, b = np.array([random.randint(-5, 5), random.randint(-5, 5)]), np.array([random.randint(-5, 5), random.randint(-5, 5)])
    question = f"Find the angle between the vectors $\\mathbf{{a}} = \\binom{{{a[0]}}}{{{a[1]}}}$ and $\\mathbf{{b}} = \\binom{{{b[0]}}}{{{b[1]}}}$ to the nearest degree."
    dot_product = np.dot(a, b)
    mag_a, mag_b = np.linalg.norm(a), np.linalg.norm(b)
    cos_theta = dot_product / (mag_a * mag_b)
    angle_rad = np.arccos(np.clip(cos_theta, -1.0, 1.0))
    angle_deg = round(np.degrees(angle_rad))
    answer = f"{angle_deg}°"
    hint = "Use the dot product formula: $\mathbf{a} \cdot \mathbf{b} = |\mathbf{a}| |\mathbf{b}| \cos\theta$."
    explanation = f"1. Dot Product: $\mathbf{{a}} \cdot \mathbf{{b}} = ({a[0]})({b[0]}) + ({a[1]})({b[1]}) = {dot_product}$.\n2. Magnitudes: $|\mathbf{{a}}| \\approx {round(mag_a, 2)}$, $|\mathbf{{b}}| \\approx {round(mag_b, 2)}$.\n3. $\cos\\theta = \\frac{{{dot_product}}}{{{round(mag_a,2)} \\times {round(mag_b,2)}}} \\approx {round(cos_theta, 2)}$.\n4. $\\theta = \cos^{{-1}}({round(cos_theta, 2)}) \\approx {answer}$."
    return {
        "is_multipart": False,
        "question": question, "options": _finalize_options({answer, f"{round(dot_product)}°"}),
        "answer": answer, "hint": hint, "explanation": explanation
    }

def _combo_prob_binomial():
    """ Combo: Binomial Theorem (Combinations) -> Probability """
    men = random.randint(5, 7)
    women = random.randint(4, 6)
    total_people = men + women
    committee_size = 5
    men_in_committee = 3
    women_in_committee = committee_size - men_in_committee
    
    question = f"A committee of {committee_size} people is to be chosen from a group of {men} men and {women} women. What is the probability that the committee consists of exactly {men_in_committee} men?"
    
    favorable_outcomes = math.comb(men, men_in_committee) * math.comb(women, women_in_committee)
    total_outcomes = math.comb(total_people, committee_size)
    prob = Fraction(favorable_outcomes, total_outcomes)
    answer = _format_fraction_text(prob)
    
    hint = "Prob = (Favorable Outcomes) / (Total Outcomes). Use combinations $\binom{n}{k}$ to find the number of ways to choose."
    explanation = (f"1. Favorable Outcomes: Ways to choose {men_in_committee} men from {men} AND {women_in_committee} women from {women}.\n   - $\\binom{{{men}}}{{{men_in_committee}}} \\times \\binom{{{women}}}{{{women_in_committee}}} = {math.comb(men, men_in_committee)} \\times {math.comb(women, women_in_committee)} = {favorable_outcomes}$.\n"
                   f"2. Total Outcomes: Ways to choose any {committee_size} people from {total_people}.\n   - $\\binom{{{total_people}}}{{{committee_size}}} = {total_outcomes}$.\n"
                   f"3. Probability = $\\frac{{{favorable_outcomes}}}{{{total_outcomes}}} = {_get_fraction_latex_code(prob)}$")

    return {
        "is_multipart": False,
        "question": question, "options": _finalize_options({answer}, "fraction"),
        "answer": answer, "hint": hint, "explanation": explanation
    }

def _combo_polynomial_functions():
    """ Combo: Polynomials (Remainder Theorem) -> Functions (Evaluate) """
    a, b, c, d = [random.randint(-5, 5) for _ in range(4)]
    divisor_root = random.randint(-3, 3)
    remainder = a*(divisor_root**3) + b*(divisor_root**2) + c*divisor_root + d
    
    f_a, f_b = random.randint(2, 5), random.randint(1, 10)
    f_of_r = f_a * remainder + f_b

    stem = f"The polynomial $P(x) = {a}x^3 + {b}x^2 + {c}x + {d}$ is divided by $(x - {divisor_root})$ to give a remainder, $R$."
    part_a = f"a) Find the value of the remainder, $R$."
    part_b = f"b) Given that $f(y) = {f_a}y + {f_b}$, find the value of $f(R)$."

    return {
        "is_multipart": True,
        "stem": stem,
        "parts": [
            {
                "question": part_a,
                "options": _finalize_options({str(remainder), str(d), str(a+b+c+d)}),
                "answer": str(remainder),
                "hint": f"By the Remainder Theorem, the remainder is $P({divisor_root})$." ,
                "explanation": f"To find the remainder, evaluate the polynomial at $x={divisor_root}$.\n$P({divisor_root}) = {a}({divisor_root})^3 + {b}({divisor_root})^2 + {c}({divisor_root}) + {d} = {remainder}$."
            },
            {
                "question": part_b,
                "options": _finalize_options({str(f_of_r), str(f_a*remainder), str(remainder+f_b)}),
                "answer": str(f_of_r),
                "hint": "Substitute the value of R you found in Part (a) into the function f(y).",
                "explanation": f"From Part (a), we know $R={remainder}$.\nWe need to find $f(R) = f({remainder})$.\n$f({remainder}) = {f_a}({remainder}) + {f_b} = {f_of_r}$."
            }
        ]
    }

def _generate_advanced_combo_question():
    """Randomly selects and runs one of the curated advanced combo generators."""
    
    # List of all the special combo generator functions we just created
    possible_combos = [
        _combo_geometry_algebra,
        _combo_surds_geometry,
        _combo_trig_vectors,
        _combo_prob_binomial,
        _combo_polynomial_functions,
    ]
    
    # Pick one of the functions from the list and execute it
    selected_combo_func = random.choice(possible_combos)
    return selected_combo_func()
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
        "Logarithms": _generate_logarithms_question,
        "Probability": _generate_probability_question,
        "Binomial Theorem": _generate_binomial_theorem_question,
        "Polynomial Functions": _generate_polynomial_functions_question,
        "Trigonometry": _generate_trigonometry_question,
        "Vectors": _generate_vectors_question,
        "Advanced Combo": _generate_advanced_combo_question,
    }
    # This block is now correctly indented
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
    st.markdown("""
    <style>
        /* --- BASE STYLES --- */
        .stApp { background-color: #f0f2ff; }
        
        /* --- GENERAL SCROLLING FIX (WORKS FOR MOST PAGES) --- */
        [data-testid="stAppViewContainer"] > .main {
            overflow: auto !important;
        }

        /* --- NEW, MORE SPECIFIC FIX FOR BLACKBOARD PAGE SCROLLING --- */
        /* This targets the main container specifically when a chat input is present */
        .stApp:has([data-testid="stChatInput"]) > div:first-child > div:first-child > div:first-child > section.main {
            display: flex;
            flex-direction: column;
            height: 100vh; /* Ensure it takes full viewport height */
        }

        /* This targets the block of chat messages and makes it scrollable */
        .stApp:has([data-testid="stChatInput"]) [data-testid="stVerticalBlock"] {
            flex-grow: 1;
            overflow-y: auto;
        }

        /* --- ALL OTHER STYLES --- */
        div[data-testid="stAppViewContainer"] * { color: #31333F !important; }
        div[data-testid="stSidebar"] { background-color: #0F1116 !important; }
        div[data-testid="stSidebar"] * { color: #FAFAFA !important; }
        div[data-testid="stSidebar"] h1 { color: #FFFFFF !important; }
        div[data-testid="stSidebar"] [data-testid="stRadio"] label { color: #E0E0E0 !important; }
        [data-baseweb="theme-dark"] div[data-testid="stAppViewContainer"] * { color: #31333F !important; }
        [data-baseweb="theme-dark"] div[data-testid="stSidebar"] * { color: #FAFAFA !important; }
        [data-testid="stChatMessage"] { background-color: transparent; }
        [data-testid="stChatMessageContent"] { border-radius: 20px; padding: 12px 16px; box-shadow: 0 1px 2px rgba(0,0,0,0.1); }
        [data-testid="stChatMessage"]:has(div[data-testid="stChatMessageAssistantAvatar"]) [data-testid="stChatMessageContent"] { background-color: #E5E5EA; color: #31333F !important; }
        [data-testid="stChatMessage"]:has(div[data-testid="stChatMessageUserAvatar"]) [data-testid="stChatMessageContent"] { background-color: #007AFF; }
        [data-testid="stChatMessage"]:has(div[data-testid="stChatMessageUserAvatar"]) * { color: white !important; }
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
        .login-title { text-align: center; font-weight: 800; font-size: 2.2rem; }
        .login-subtitle { text-align: center; color: #6c757d; margin-bottom: 2rem; }
        .main-content { background-color: #ffffff; padding: 2rem; border-radius: 12px; box-shadow: 0 4px 12px rgba(0,0,0,0.08); }
        @media (max-width: 640px) { .main-content, .login-container { padding: 1rem; } .login-title { font-size: 1.8rem; } }
    </style>
    """, unsafe_allow_html=True)
def display_dashboard(username):
    # --- Gamification Section ---
    challenge = get_or_create_daily_challenge(username)
    if challenge:
        st.subheader("Today's Challenge")
        if challenge['is_completed']:
            st.success(f"🎉 Well done! You've completed today's challenge: {challenge['description']}")
        else:
            with st.container(border=True):
                st.info(challenge['description'])
                # Ensure target_count is not zero to avoid division error
                if challenge['target_count'] > 0:
                    progress_percent = min(challenge['progress_count'] / challenge['target_count'], 1.0)
                    st.progress(progress_percent, text=f"Progress: {challenge['progress_count']} / {challenge['target_count']}")
                else:
                    st.progress(1.0, text="Challenge Complete!")
                st.caption("Visit the '📝 Quiz' page to make progress on your challenge!")
    
    st.markdown("<hr class='styled-hr'>", unsafe_allow_html=True)
    
    # --- Existing Dashboard Code with RESTORED line graph ---
    st.header(f"📈 Performance for {username}")
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
            # RESTORED: Data processing logic for the graph
            df_data = [
                {
                    "Topic": r['topic'], 
                    "Score": f"{r['score']}/{r['questions_answered']}", 
                    "Accuracy (%)": (r['score'] / r['questions_answered'] * 100) if r['questions_answered'] not in [None, 0] and r['score'] is not None else 0, 
                    "Date": r['timestamp'].strftime("%Y-%m-%d %H:%M")
                } for r in history
            ]
            df = pd.DataFrame(df_data)
            
            # RESTORED: The line graph itself
            line_fig = px.line(df, x='Date', y='Accuracy (%)', color='Topic', markers=True, title="Quiz Performance Trend")
            st.plotly_chart(line_fig, use_container_width=True)
            
            # The dataframe display
            st.dataframe(df, use_container_width=True)
        else:
            st.info("Your quiz history is empty. Take a quiz to get started!")

def display_blackboard_page():
    st.header("칠판 Blackboard")
    # --- ADD THIS LINE ---
    st.components.v1.html("<meta http-equiv='refresh' content='15'>", height=0)
    st.info("This is a community space. Ask clear questions, be respectful, and help your fellow students!", icon="👋")
    online_users = get_online_users(st.session_state.username)
    if online_users:
        st.markdown(f"**🟢 Online now:** {', '.join(online_users)}")
    else:
        st.markdown("_No other users are currently active._")
    st.markdown("<hr class='styled-hr'>", unsafe_allow_html=True)
    channel = chat_client.channel("messaging", channel_id="mathfriend-blackboard", data={"name": "MathFriend Blackboard"})
    channel.create(st.session_state.username)
    state = channel.query(watch=False, state=True, messages={"limit": 50})
    messages = state['messages']
    for msg in messages:
        user_id = msg["user"].get("id", "Unknown")
        user_name = msg["user"].get("name", user_id)
        is_current_user = (user_id == st.session_state.username)
        with st.chat_message(name="user" if is_current_user else "assistant"):
            if not is_current_user:
                st.markdown(f"**{user_name}**")
            st.markdown(msg["text"])
    if prompt := st.chat_input("Post your question or comment..."):
        channel.send_message({"text": prompt}, user_id=st.session_state.username)
        st.rerun()

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
                st.session_state.questions_answered = 0; st.session_state.questions_attempted = 0
                st.session_state.current_streak = 0; st.session_state.incorrect_questions = []
                if 'current_q_data' in st.session_state: del st.session_state['current_q_data']
                st.rerun()
        return

    if st.session_state.get('on_summary_page', False) or st.session_state.questions_answered >= QUIZ_LENGTH:
        display_quiz_summary(); return

    col1, col2, col3 = st.columns(3)
    with col1: st.metric("Score", f"{st.session_state.quiz_score}/{st.session_state.questions_attempted}")
    with col2: st.metric("Question", f"{st.session_state.questions_answered + 1}/{QUIZ_LENGTH}")
    with col3: st.metric("🔥 Streak", st.session_state.current_streak)
    st.progress(st.session_state.questions_answered / QUIZ_LENGTH, text="Round Progress")
    st.markdown("<hr class='styled-hr'>", unsafe_allow_html=True)
    
    if 'current_q_data' not in st.session_state:
        st.session_state.current_q_data = generate_question(st.session_state.quiz_topic)
    
    q_data = st.session_state.current_q_data
    st.subheader(f"Topic: {st.session_state.quiz_topic}")

    if not st.session_state.get('answer_submitted', False):
        is_multi = q_data.get("is_multipart", False)
        options = []
        if is_multi:
            st.markdown(q_data["stem"], unsafe_allow_html=True)
            if 'current_part_index' not in st.session_state: st.session_state.current_part_index = 0
            part_data = q_data["parts"][st.session_state.current_part_index]
            st.markdown(part_data["question"], unsafe_allow_html=True)
            with st.expander("🤔 Need a hint?"): st.info(part_data["hint"])
            options = part_data["options"]
        else:
            st.markdown(q_data["question"], unsafe_allow_html=True)
            with st.expander("🤔 Need a hint?"): st.info(q_data["hint"])
            options = q_data["options"]

        with st.form(key=f"quiz_form_{st.session_state.questions_answered}"):
            user_choice = st.radio("Select your answer:", options, index=None)
            if st.form_submit_button("Submit Answer", type="primary"):
                if user_choice is not None:
                    st.session_state.user_choice = user_choice
                    st.session_state.answer_submitted = True
                    
                    actual_answer = q_data["parts"][st.session_state.current_part_index]["answer"] if is_multi else q_data["answer"]
                    is_correct = str(user_choice) == str(actual_answer)
                    
                    # --- REVISED SCORING LOGIC ON SUBMIT ---
                    if is_multi:
                        part_index = st.session_state.current_part_index
                        is_last_part = (part_index + 1 == len(q_data["parts"]))
                        
                        if part_index == 0:
                            st.session_state.questions_attempted += 1
                            st.session_state.multi_part_correct = True # Assume correct until a part is wrong
                        
                        if not is_correct:
                            st.session_state.multi_part_correct = False

                        if is_correct and is_last_part and st.session_state.multi_part_correct:
                            st.session_state.quiz_score += 1
                            st.session_state.current_streak += 1
                        
                        if not is_correct:
                             st.session_state.current_streak = 0
                             if not any(q.get('stem', q.get('question')) == q_data.get('stem', q_data.get('question')) for q in st.session_state.incorrect_questions):
                                st.session_state.incorrect_questions.append(q_data)

                    else: # Single question logic
                        st.session_state.questions_attempted += 1
                        if is_correct:
                            st.session_state.quiz_score += 1
                            st.session_state.current_streak += 1
                        else:
                            st.session_state.current_streak = 0
                            st.session_state.incorrect_questions.append(q_data)
                    st.rerun()
                else:
                    st.warning("Please select an answer before submitting.")
    else: # Explanation Phase
        user_choice = st.session_state.user_choice; is_multi = q_data.get("is_multipart", False)
        part_data, actual_answer, explanation, question_text = {}, "", "", ""

        if is_multi:
            part_index = st.session_state.current_part_index; part_data = q_data["parts"][part_index]
            actual_answer, explanation = part_data["answer"], part_data["explanation"]
            question_text = q_data["stem"] + "\n\n" + part_data["question"]
        else:
            actual_answer, explanation = q_data["answer"], q_data.get("explanation", "")
            question_text = q_data["question"]

        is_correct = str(user_choice) == str(actual_answer)
        st.markdown(question_text, unsafe_allow_html=True)
        st.write("Your answer:");
        if is_correct: st.success(f"**{user_choice}** (Correct!)")
        else: st.error(f"**{user_choice}** (Incorrect)"); st.info(f"The correct answer was: **{actual_answer}**")

        with st.expander("Show Explanation", expanded=True): st.markdown(explanation, unsafe_allow_html=True)

        is_last_part = is_multi and (st.session_state.current_part_index + 1 == len(q_data["parts"]))
        button_label = "Next Question" if not is_multi or is_last_part or not is_correct else "Next Part"
        
        if st.button(button_label, type="primary", use_container_width=True):
            if not is_multi or is_last_part or not is_correct:
                st.session_state.questions_answered += 1

            if is_multi and is_correct and not is_last_part:
                st.session_state.current_part_index += 1
            else:
                del st.session_state.current_q_data
                if 'current_part_index' in st.session_state: del st.session_state['current_part_index']
                if 'multi_part_correct' in st.session_state: del st.session_state.multi_part_correct
            
            del st.session_state.user_choice; del st.session_state.answer_submitted
            st.rerun()

    if st.button("Stop Round & Save Score"):
        st.session_state.on_summary_page = True
        keys_to_delete = ['current_q_data', 'user_choice', 'answer_submitted', 'current_part_index', 'multi_part_correct']
        for key in keys_to_delete:
            if key in st.session_state: del st.session_state[key]
        st.rerun()
def display_quiz_summary():
    st.header("🎉 Round Complete! 🎉")
    final_score = st.session_state.quiz_score
    
    # --- FIX 1: Use the correct total ---
    # Use questions_attempted to reflect the questions the user actually saw.
    total_questions = st.session_state.questions_attempted
    
    accuracy = (final_score / total_questions * 100) if total_questions > 0 else 0
    
    if total_questions > 0 and 'result_saved' not in st.session_state:
        # Save the correct total to the database
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
                if q.get("is_multipart"):
                    st.markdown(f"**Question Stem:** {q['stem']}")
                    for i, part in enumerate(q['parts']):
                        st.markdown(f"**Part {chr(97+i)}):** {part['question']}")
                        st.error(f"**Correct Answer:** {part['answer']}")
                        st.info(f"**Explanation:** {part['explanation']}")
                else:
                    st.markdown(f"**Question:** {q['question']}")
                    st.error(f"**Correct Answer:** {q['answer']}")
                    if q.get("explanation"):
                        st.info(f"**Explanation:** {q['explanation']}")
                st.write("---")

    st.markdown("<hr class='styled-hr'>", unsafe_allow_html=True)
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Play Again (Same Topic)", use_container_width=True, type="primary"):
            st.session_state.on_summary_page = False
            st.session_state.quiz_active = True
            st.session_state.quiz_score = 0
            st.session_state.questions_answered = 0
            
            # --- FIX 2: Reset the new counter as well ---
            st.session_state.questions_attempted = 0
            
            st.session_state.current_streak = 0
            st.session_state.incorrect_questions = []
            
            keys_to_clear = ['current_q_data', 'result_saved', 'current_part_index', 'user_choice', 'answer_submitted']
            for key in keys_to_clear:
                if key in st.session_state: del st.session_state[key]
            st.rerun()
            
    with col2:
        if st.button("Choose New Topic", use_container_width=True):
            st.session_state.on_summary_page = False
            st.session_state.quiz_active = False
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

def display_learning_resources(topic_options):
    st.header("📚 Learning Resources")
    st.write("A summary of key concepts and formulas for each topic. Click a topic to expand it.")

    topics_content = {
        "Sets": """
        A **set** is a well-defined collection of distinct objects.
        - **Union ($A \\cup B$):** All elements that are in set A, or in set B, or in both.
        - **Intersection ($A \\cap B$):** All elements that are in *both* set A and set B.
        - **Complement ($A'$ or $A^c$):** All elements in the universal set ($\\mathcal{U}$) that are *not* in set A.
        - **Number of Subsets:** A set with $n$ elements has $2^n$ subsets.
        - **Venn Diagrams:** For two sets A and B, the key formula is:
          $$ |A \\cup B| = |A| + |B| - |A \\cap B| $$
        """,
        "Percentages": """
        A **percentage** is a number or ratio expressed as a fraction of 100.
        - **Percentage of a number:** To find $p\\%$ of $N$, calculate $\\frac{p}{100} \\times N$.
        - **Percentage Change:** Used to find the increase or decrease in a value.
          $$ \\text{Percent Change} = \\frac{{\\text{New Value} - \\text{Old Value}}}{{\\text{Old Value}}} \\times 100\\% $$
        - **Profit and Loss:**
            - Profit \\% = $(\\frac{{\\text{Profit}}}{{\\text{Cost Price}}}) \\times 100\\%$
            - Loss \\% = $(\\frac{{\\text{Loss}}}{{\\text{Cost Price}}}) \\times 100\\%$
        - **Simple Interest:** $I = P \\times R \\times T$, where P=Principal, R=Rate (as decimal), T=Time.
        """,
        "Fractions": """
        A **fraction** represents a part of a whole, written as $\\frac{{\\text{numerator}}}{{\\text{denominator}}}$.
        - **Adding/Subtracting:** Find a common denominator, then add or subtract the numerators.
        - **Multiplying:** Multiply the numerators and the denominators. $$\\frac{a}{b} \\times \\frac{c}{d} = \\frac{ac}{bd}$$
        - **Dividing:** Invert the second fraction and multiply. $$\\frac{a}{b} \\div \\frac{c}{d} = \\frac{a}{b} \\times \\frac{d}{c} = \\frac{ad}{bc}$$
        - **Order of Operations (BODMAS):** Brackets, Orders (powers/roots), Division, Multiplication, Addition, Subtraction.
        """,
        "Indices": """
        Indices (or exponents) show how many times a number is multiplied by itself.
        - **Multiplication Rule:** $x^a \\times x^b = x^{a+b}$
        - **Division Rule:** $x^a \\div x^b = x^{a-b}$
        - **Power of a Power Rule:** $(x^a)^b = x^{ab}$
        - **Negative Exponent:** $x^{-a} = \\frac{1}{x^a}$
        - **Fractional Exponent:** $x^{\\frac{1}{n}} = \\sqrt[n]{x}$
        - **Zero Exponent:** $x^0 = 1$ (for any non-zero x)
        """,
        "Surds": """
        A **surd** is an irrational root of a number (e.g., $\\sqrt{2}$).
        - **Simplifying:** Find the largest perfect square factor. Example: $\\sqrt{50} = \\sqrt{25 \\times 2} = \\sqrt{25} \\times \\sqrt{2} = 5\\sqrt{2}$.
        - **Operations:** You can only add or subtract 'like' surds. Example: $4\\sqrt{3} + 2\\sqrt{3} = 6\\sqrt{3}$.
        - **Rationalizing the Denominator:** To remove a surd from the denominator, multiply the numerator and denominator by the conjugate. The conjugate of $(a + \\sqrt{b})$ is $(a - \\sqrt{b})$.
        """,
        "Binary Operations": """
        A **binary operation** ($\\ast$) on a set is a rule for combining any two elements of the set to produce another element.
        - **Commutative Property:** The operation is commutative if $a \\ast b = b \\ast a$.
        - **Associative Property:** The operation is associative if $(a \\ast b) \\ast c = a \\ast (b \\ast c)$.
        - **Identity Element (e):** An element such that $a \\ast e = e \\ast a = a$.
        - **Inverse Element ($a^{-1}$):** An element such that $a \\ast a^{-1} = a^{-1} \\ast a = e$.
        """,
        "Relations and Functions": """
        - **Relation:** A set of ordered pairs $(x, y)$.
        - **Function:** A special relation where each input ($x$) has exactly one output ($y$).
        - **Domain:** The set of all possible input values ($x$).
        - **Range:** The set of all actual output values ($y$).
        - **Composite Function $f(g(x))$:** The output of $g(x)$ becomes the input for $f(x)$. First evaluate $g(x)$, then apply $f$ to the result.
        - **Inverse Function $f^{-1}(x)$:** The function that reverses $f(x)$. To find it: let $y=f(x)$, swap $x$ and $y$, then solve for $y$.
        """,
        "Sequence and Series": """
        - **Arithmetic Progression (AP):** A sequence with a *common difference* ($d$).
            - Nth term: $a_n = a_1 + (n-1)d$
            - Sum of n terms: $S_n = \\frac{n}{2}(2a_1 + (n-1)d)$
        - **Geometric Progression (GP):** A sequence with a *common ratio* ($r$).
            - Nth term: $a_n = a_1 r^{n-1}$
            - Sum of n terms: $S_n = \\frac{{a_1(r^n - 1)}}{{r-1}}$
        - **Sum to Infinity (GP):** For $|r| < 1$, $S_\\infty = \\frac{a_1}{1-r}$.
        """,
        "Word Problems": """
        A systematic approach is key for any student in Kumasi and beyond:
        1.  **Read and Understand:** Identify what is given and what is being asked.
        2.  **Define Variables:** Assign letters (e.g., $x, y$) to the unknown quantities.
        3.  **Formulate Equations:** Translate the words into mathematical equations or inequalities.
        4.  **Solve** the system of equations.
        5.  **Check** your answer to ensure it makes sense in the context of the problem.
        """,
        "Shapes (Geometry)": """
        - **Rectangle:** Area = $l \\times w$; Perimeter = $2(l+w)$.
        - **Circle:** Area = $\\pi r^2$; Circumference = $2\\pi r$.
        - **Cylinder:** Volume = $\\pi r^2 h$; Surface Area = $2\\pi r h + 2\\pi r^2$.
        - **Pythagoras' Theorem:** For a right-angled triangle, $a^2 + b^2 = c^2$, where $c$ is the hypotenuse.
        """,
        "Algebra Basics": """
        - **Change of Subject:** Rearranging a formula to isolate a different variable.
        - **Factorization:** Expressing an algebraic expression as a product of its factors.
        - **Solving Equations:**
            - **Linear:** Isolate the variable.
            - **Quadratic ($ax^2+bx+c=0$):** Solve by factorization, completing the square, or the quadratic formula: $$x = \\frac{{-b \\pm \\sqrt{{b^2-4ac}}}}{{2a}}$$
        """,
        "Linear Algebra": """
        Focuses on vectors and matrices. For a 2x2 matrix $A = \\begin{pmatrix} a & b \\\\ c & d \\end{pmatrix}$:
        - **Determinant:** $\det(A) = ad - bc$.
        - **Matrix Multiplication:** Is done by row-by-column dot product. Not commutative ($AB \\neq BA$).
        - **Inverse Matrix:** $A^{-1} = \\frac{1}{{\det(A)}} \\begin{pmatrix} d & -b \\\\ -c & a \\end{pmatrix}$. The inverse only exists if $\det(A) \\neq 0$.
        """,
        "Logarithms": """
        A logarithm is the inverse operation to exponentiation. $\log_b(N) = x$ is the same as $b^x = N$.
        - **Product Rule:** $\log_b(M) + \log_b(N) = \log_b(MN)$
        - **Quotient Rule:** $\log_b(M) - \log_b(N) = \log_b(\\frac{M}{N})$
        - **Power Rule:** $\log_b(M^p) = p \log_b(M)$
        - **Change of Base:** $\log_b(a) = \\frac{{\log_c(a)}}{{\log_c(b)}}$
        """,
        "Probability": """
        Probability measures the likelihood of an event. $$P(\\text{Event}) = \\frac{{\\text{Number of Favorable Outcomes}}}{{\\text{Total Number of Outcomes}}}$$
        - **Range:** $0 \le P(E) \le 1$. $P(E)=0$ means impossible, $P(E)=1$ means certain.
        - **Mutually Exclusive Events (OR):** $P(A \\text{ or } B) = P(A) + P(B)$.
        - **Independent Events (AND):** $P(A \\text{ and } B) = P(A) \\times P(B)$.
        """,
        "Binomial Theorem": """
        Used to expand powers of binomials, like $(a+b)^n$.
        - **The Formula:** $(a+b)^n = \\sum_{k=0}^{n} \\binom{n}{k} a^{n-k} b^k$
        - **Combinations:** The coefficient $\\binom{n}{k}$ is calculated as $\\frac{{n!}}{{k!(n-k)!}}$.
        - **Finding the $(r+1)^{th}$ term:** The term is given by $T_{r+1} = \\binom{n}{r} a^{n-r} b^r$.
        """,
        "Polynomial Functions": """
        Expressions involving variables with non-negative integer exponents.
        - **Remainder Theorem:** The remainder when a polynomial $P(x)$ is divided by $(x-a)$ is equal to $P(a)$.
        - **Factor Theorem:** If $P(a)=0$, then $(x-a)$ is a factor of $P(x)$. This is key to finding the roots of polynomials.
        """,
        "Trigonometry": """
        The study of relationships between the angles and sides of triangles.
        - **SOH CAH TOA:** For right-angled triangles.
        - **Identities:** $\sin^2\\theta + \cos^2\\theta = 1$ and $\tan\\theta = \\frac{{\sin\\theta}}{{\cos\\theta}}$.
        - **Sine Rule:** $\\frac{a}{{\sin A}} = \\frac{b}{{\sin B}} = \\frac{c}{{\sin C}}$.
        - **Cosine Rule:** $c^2 = a^2 + b^2 - 2ab\cos(C)$.
        """,
        "Vectors": """
        A quantity having both magnitude (length) and direction.
        - **Component Form:** A vector $\mathbf{v}$ can be written as $x\mathbf{i} + y\mathbf{j}$ or as a column vector $\\binom{x}{y}$.
        - **Magnitude:** The length of $\mathbf{v} = x\mathbf{i} + y\mathbf{j}$ is $|\mathbf{v}| = \\sqrt{x^2 + y^2}$.
        - **Scalar (Dot) Product:** $\mathbf{a} \cdot \mathbf{b} = a_1b_1 + a_2b_2$.
        - **Angle Between Vectors:** $\cos\\theta = \\frac{{\mathbf{a} \cdot \mathbf{b}}}{{|\mathbf{a}| |\mathbf{b}|}}$.
        """
    }

    for topic in topic_options:
        if topic in topics_content:
            with st.expander(f"**{topic}**", expanded=(topic == topic_options[0])):
                st.markdown(topics_content[topic], unsafe_allow_html=True)
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
            "📊 Dashboard", "📝 Quiz", "🏆 Leaderboard", "칠판 Blackboard", 
            "👤 Profile", "📚 Learning Resources"
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
        "Word Problems", "Shapes (Geometry)", "Algebra Basics", "Linear Algebra",
        "Logarithms",
        "Probability",
        "Binomial Theorem",
        "Polynomial Functions",
        "Trigonometry",
        "Vectors",
        "Advanced Combo"
    ]
    
    if selected_page == "📊 Dashboard":
        display_dashboard(st.session_state.username)
    elif selected_page == "📝 Quiz":
        display_quiz_page(topic_options)
    elif selected_page == "🏆 Leaderboard":
        display_leaderboard(topic_options)
    elif selected_page == "칠판 Blackboard":
        display_blackboard_page()
    elif selected_page == "👤 Profile":
        display_profile_page()
    elif selected_page == "📚 Learning Resources":
        display_learning_resources(topic_options)
        
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
if st.session_state.get("show_splash", True):
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
    if st.session_state.get("logged_in", False):
        show_main_app()
    else:
        show_login_or_signup_page()
























