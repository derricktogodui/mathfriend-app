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

            # --- PASTE THE NEW CODE EXACTLY HERE ---
            conn.execute(text('''CREATE TABLE IF NOT EXISTS seen_questions (
                                id SERIAL PRIMARY KEY,
                                username TEXT NOT NULL,
                                question_id TEXT NOT NULL,
                                seen_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                                UNIQUE (username, question_id)
                            )'''))
            
            # ADD THIS BLOCK
            conn.execute(text('''CREATE TABLE IF NOT EXISTS user_achievements (
                                id SERIAL PRIMARY KEY,
                                username TEXT NOT NULL,
                                achievement_name TEXT NOT NULL,
                                badge_icon TEXT,
                                unlocked_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                            )'''))
            
            # --- Populate daily_challenges if it's empty ---
            result = conn.execute(text("SELECT COUNT(*) FROM daily_challenges")).scalar_one()
            if result == 0:
                print("Populating daily_challenges table for the first time.")
                # This list is now expanded to cover all 18 topics
                challenges = [
                    # General Challenges
                    ("Answer 5 questions correctly on any topic.", "Any", 5),
                    ("Complete any quiz with a score of 4 or more.", "Any", 4),
                    
                    # Original 12 Topic Challenges
                    ("Correctly answer 4 Set theory questions.", "Sets", 4),
                    ("Get 3 correct answers in a Percentages quiz.", "Percentages", 3),
                    ("Solve 4 problems involving Fractions.", "Fractions", 4),
                    ("Simplify 3 expressions using the laws of Indices.", "Indices", 3),
                    ("Get 3 correct answers in a Surds quiz.", "Surds", 3),
                    ("Evaluate 3 Binary Operations correctly.", "Binary Operations", 3),
                    ("Answer 4 questions on Relations and Functions.", "Relations and Functions", 4),
                    ("Solve 3 problems on Sequence and Series.", "Sequence and Series", 3),
                    ("Solve 2 math Word Problems.", "Word Problems", 2),
                    ("Answer 4 questions about Shapes (Geometry).", "Shapes (Geometry)", 4),
                    ("Get 5 correct answers in Algebra Basics.", "Algebra Basics", 5),
                    ("Solve 3 problems in Linear Algebra.", "Linear Algebra", 3),
                    
                    # New 6 Advanced Topic Challenges
                    ("Solve 3 logarithmic equations.", "Logarithms", 3),
                    ("Correctly answer 4 probability questions.", "Probability", 4),
                    ("Find the coefficient in 2 binomial expansions.", "Binomial Theorem", 2),
                    ("Use the Remainder Theorem twice.", "Polynomial Functions", 2),
                    ("Solve 3 trigonometric equations.", "Trigonometry", 3),
                    ("Calculate the magnitude of 4 vectors.", "Vectors", 4)
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
    # This now calls the umbrella function to update both challenges and achievements
    update_gamification_progress(username, topic, score)
    
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

# ADD THESE TWO NEW FUNCTIONS

def get_seen_questions(username):
    """Fetches the set of all question IDs a user has already seen."""
    with engine.connect() as conn:
        query = text("SELECT question_id FROM seen_questions WHERE username = :username")
        result = conn.execute(query, {"username": username}).fetchall()
        return {row[0] for row in result}

def save_seen_question(username, question_id):
    """Saves a question ID to a user's seen list."""
    with engine.connect() as conn:
        query = text("INSERT INTO seen_questions (username, question_id) VALUES (:username, :question_id) ON CONFLICT DO NOTHING")
        conn.execute(query, {"username": username, "question_id": question_id})
        conn.commit()

# ADD THESE THREE NEW FUNCTIONS

def check_and_award_achievements(username, topic):
    """Checks all achievement conditions for a user and awards them if met."""
    with engine.connect() as conn:
        existing_achievements_query = text("SELECT achievement_name FROM user_achievements WHERE username = :username")
        existing_set = {row[0] for row in conn.execute(existing_achievements_query, {"username": username}).fetchall()}
        
        # --- Achievement 1: "First Step" (Take 1 quiz) ---
        if "First Step" not in existing_set:
            insert_query = text("INSERT INTO user_achievements (username, achievement_name, badge_icon) VALUES (:username, 'First Step', '👟')")
            conn.execute(insert_query, {"username": username})
            st.session_state.achievement_unlocked_toast = "First Step"
            existing_set.add("First Step")

        # --- Achievement 2: "Century Scorer" (Get 100 total correct answers) ---
        if "Century Scorer" not in existing_set:
            total_score_query = text("SELECT SUM(score) FROM quiz_results WHERE username = :username")
            total_score = conn.execute(total_score_query, {"username": username}).scalar_one() or 0
            if total_score >= 100:
                insert_query = text("INSERT INTO user_achievements (username, achievement_name, badge_icon) VALUES (:username, 'Century Scorer', '💯')")
                conn.execute(insert_query, {"username": username})
                st.session_state.achievement_unlocked_toast = "Century Scorer"
                existing_set.add("Century Scorer")

        # --- Achievement 3: "Topic Master" (Get 25 correct answers in a specific topic) ---
        achievement_name = f"{topic} Master"
        if achievement_name not in existing_set:
            topic_score_query = text("SELECT SUM(score) FROM quiz_results WHERE username = :username AND topic = :topic")
            topic_score = conn.execute(topic_score_query, {"username": username, "topic": topic}).scalar_one() or 0
            if topic_score >= 25:
                insert_query = text("INSERT INTO user_achievements (username, achievement_name, badge_icon) VALUES (:username, :name, '🎓')")
                conn.execute(insert_query, {"username": username, "name": achievement_name})
                st.session_state.achievement_unlocked_toast = achievement_name

        conn.commit()

def get_user_achievements(username):
    """Fetches all achievements unlocked by a user."""
    with engine.connect() as conn:
        query = text("SELECT achievement_name, badge_icon, unlocked_at FROM user_achievements WHERE username = :username ORDER BY unlocked_at DESC")
        result = conn.execute(query, {"username": username}).mappings().fetchall()
        return [dict(row) for row in result]

def update_gamification_progress(username, topic, score):
    """Umbrella function to update all gamification systems."""
    update_daily_challenge_progress(username, topic, score)
    check_and_award_achievements(username, topic)

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

# ADD THIS NEW FUNCTION
def get_question_id(question_text):
    """Creates a unique and consistent ID for a question based on its text."""
    return hashlib.md5(question_text.encode()).hexdigest()

# --- FULLY IMPLEMENTED QUESTION GENERATION ENGINE (12 TOPICS) ---

def _generate_sets_question():
    """Generates a multi-subtopic question for Sets with enhanced variety and advanced topics."""
    # UPGRADED: Added new advanced sub-topics
    q_type = random.choice(['operation', 'venn_two', 'venn_three', 'subsets', 'complement', 'properties', 'demorgan'])
    question, answer, hint, explanation = "", "", "", ""
    options = set()
    
    # Define a Universal Set for relevant questions
    universal_set = set(range(1, 21))

    if q_type == 'operation':
        set_a = set(random.sample(range(1, 20), k=random.randint(3, 8)))
        set_b = set(random.sample(range(1, 20), k=random.randint(3, 8)))
        op, sym = random.choice([('union', '\\cup'), ('intersection', '\\cap'), ('difference', '-')])
        question = f"Given $A = {set_a}$ and $B = {set_b}$, find $A {sym} B$."
        if op == 'union': res = set_a.union(set_b)
        elif op == 'intersection': res = set_a.intersection(set_b)
        else: res = set_a.difference(set_b)
        answer = str(res); hint = "Review Union (all), Intersection (common), and Difference."; explanation = f"The **{op}** of $A$ and $B$ results in the set ${res}$."
        options = {answer, str(set_a.symmetric_difference(set_b)), str(set_b.difference(set_a))}

    elif q_type == 'venn_two':
        total = random.randint(50, 100); a_only, b_only, both = random.randint(10, 25), random.randint(10, 25), random.randint(5, 15)
        neither = total - (a_only + b_only + both); total_a, total_b = a_only + both, b_only + both
        item_pairs = [("Fufu", "Banku"), ("Physics", "Chemistry"), ("History", "Government"), ("Twi", "Ga")]; group_a_name, group_b_name = random.choice(item_pairs)
        location = random.choice(["Accra", "Kumasi", "Takoradi", "Tamale"])
        question = f"In a survey of {total} students in {location}, {total_a} liked {group_a_name} and {total_b} liked {group_b_name}. If {neither} liked neither, how many liked BOTH?"
        answer = str(both); hint = "Use the formula $|A \\cup B| = |A| + |B| - |A \\cap B|$."; explanation = f"1. Students liking at least one = Total - Neither = {total} - {neither} = {a_only+b_only+both}.\n2. Let Both be $x$. Then ${total_a} + {total_b} - x = {a_only+b_only+both}$, which gives $x = {both}$."
        options = {answer, str(a_only), str(b_only), str(neither)}

    elif q_type == 'venn_three':
        a,b,c,ab,bc,ac,abc = [random.randint(5, 15) for _ in range(7)]; total_a, total_b, total_c = a+ab+ac+abc, b+ab+bc+abc, c+ac+bc+abc; total = sum([a,b,c,ab,bc,ac,abc])
        item_sets = [("MTN", "Vodafone", "AirtelTigo"), ("Gari", "Rice", "Yam")]; item1, item2, item3 = random.choice(item_sets)
        question = f"A survey of {total} people showed that {total_a} liked {item1}, {total_b} liked {item2}, and {total_c} liked {item3}. {ab+abc} liked {item1} & {item2}, {ac+abc} liked {item1} & {item3}, {bc+abc} liked {item2} & {item3}, and {abc} liked all three. How many people liked exactly one item?"
        answer = str(a+b+c); hint = "Draw a Venn diagram, start from the center, and subtract outwards."; explanation = f"{item1} only = {a}, {item2} only = {b}, {item3} only = {c}. Total = {a+b+c}."
        options = {answer, str(ab+bc+ac), str(abc)}
    
    elif q_type == 'subsets':
        num_elements = random.randint(3, 6); s = set(random.sample(range(1, 100), k=num_elements))
        sub_q_type = random.choice(['count_all', 'count_proper'])
        if sub_q_type == 'count_all':
            question = f"How many subsets can be formed from the set $S = {s}$?"; answer = str(2**num_elements)
            hint = "The number of subsets of a set with 'n' elements is $2^n$."
            explanation = f"The set has {num_elements} elements. The number of subsets is $2^{{{num_elements}}} = {2**num_elements}$."
        else: # count_proper
            question = f"How many **proper** subsets does the set $S = {s}$ have?"; answer = str(2**num_elements - 1)
            hint = "The number of proper subsets is $2^n - 1$."; explanation = f"Total subsets = $2^{{{num_elements}}} = {2**num_elements}$. Proper subsets exclude the set itself, so we subtract 1."
        options = {answer, str(2*num_elements), str(num_elements**2)}

    # --- NEW SUB-TOPICS ---
    elif q_type == 'complement':
        set_a = set(random.sample(range(1, 20), k=random.randint(5, 8)))
        question = f"Given the Universal set $\mathcal{{U}} = \\{{1, 2, ..., 20\\}}$ and the set $A = {set_a}$, find the complement of A, denoted $A'$."
        complement_set = universal_set - set_a
        answer = str(complement_set)
        hint = "The complement of a set A contains all the elements in the universal set that are NOT in set A."
        explanation = f"We are looking for all numbers from 1 to 20 that are not present in set A.\n$A' = \mathcal{{U}} - A = {universal_set} - {set_a} = {complement_set}$."
        options = {answer, str(set_a), str(universal_set)}

    elif q_type == 'properties':
        law, is_true = random.choice([("Commutative Law for Union ($A \\cup B = B \\cup A$)", "True"), ("Associative Law for Intersection ($(A \\cap B) \\cap C = A \\cap (B \\cap C)$)", "True"), ("Distributive Law ($A \\cup (B \\cap C) = (A \\cup B) \\cap (A \cup C)$)", "True"), ("Commutative Law for Difference ($A - B = B - A$)", "False")])
        question = f"Which of the following statements about the properties of set operations is correct?"
        # For simplicity, we make the correct answer a fixed statement and distractors fixed variations.
        correct_statement = "The union of sets is commutative."
        distractors = {"The difference of sets is commutative.", "The intersection of sets is not associative.", "The power set operation is commutative."}
        answer = correct_statement
        hint = "Think about whether the order of sets matters for operations like Union ($\cup$) and Intersection ($\cap$)."
        explanation = f"The Commutative Law holds for Union and Intersection ($A \\cup B = B \\cup A$), but not for Difference ($A - B \\neq B - A$). The Associative and Distributive laws also hold for union and intersection as stated in standard set theory."
        options = {answer, *distractors}
        
    elif q_type == 'demorgan':
        set_a = set(random.sample(range(1, 20), k=random.randint(4, 6)))
        set_b = set(random.sample(range(1, 20), k=random.randint(4, 6)))
        question = f"Given $\mathcal{{U}} = \\{{1, ..., 20\\}}$, $A = {set_a}$, and $B = {set_b}$, which set is equal to $(A \cup B)'$ according to De Morgan's Laws?"
        
        # Calculate the correct answer based on De Morgan's Law
        a_comp = universal_set - set_a
        b_comp = universal_set - set_b
        correct_answer_set = a_comp.intersection(b_comp)
        answer = str(correct_answer_set)
        
        hint = "De Morgan's Laws state that $(A \cup B)' = A' \cap B'$ and $(A \cap B)' = A' \cup B'$."
        explanation = f"1. First, find $A \cup B = {set_a.union(set_b)}$.\n2. Then find its complement: $(A \cup B)' = {universal_set - set_a.union(set_b)}$.\n3. According to De Morgan's law, this must be equal to $A' \cap B'$.\n4. $A' = {a_comp}$.\n5. $B' = {b_comp}$.\n6. $A' \cap B' = {correct_answer_set}$. The law holds true."
        # Distractors based on common mistakes
        options = {answer, str(a_comp.union(b_comp)), str(universal_set - set_a.intersection(set_b)), str(set_a.symmetric_difference(set_b))}

    return {"question": question, "options": _finalize_options(options, default_type="set_str"), "answer": answer, "hint": hint, "explanation": explanation}
def _generate_percentages_question():
    """Generates a multi-subtopic question for Percentages with enhanced variety."""
    # UPGRADED: Expanded list of sub-topics based on your suggestions
    q_type = random.choice(['conversion', 'percent_of', 'express_as_percent', 'percent_change', 'profit_loss', 'reverse_percent', 'successive_change', 'percent_error'])
    question, answer, hint, explanation = "", "", "", ""
    options = set()

    if q_type == 'conversion':
        frac = Fraction(random.randint(1, 4), random.choice([5, 8, 10, 20]))
        percent = frac.numerator / frac.denominator * 100
        decimal = frac.numerator / frac.denominator
        
        start_form, end_form, ans_val = random.choice([
            (f"${_get_fraction_latex_code(frac)}$", "a percentage", f"{percent:.0f}%"),
            (f"{decimal}", "a percentage", f"{percent:.0f}%"),
            (f"{percent:.0f}%", "a decimal", f"{decimal}")
        ])
        question = f"Express {start_form} as {end_form}."
        answer = str(ans_val)
        hint = "To convert a fraction or decimal to a percentage, multiply by 100. To convert a percentage to a decimal, divide by 100."
        explanation = f"To convert {start_form} to {end_form}, you perform the required operation. The result is {answer}."
        options = {answer, f"{decimal*10}", f"{percent/10}%"}

    elif q_type == 'percent_of':
        percent, number = random.randint(1, 19)*5, random.randint(10, 50)*10
        question = f"Calculate {percent}% of GHS {number:.2f}."
        answer = f"GHS {(percent/100)*number:.2f}"
        hint = "Convert the percentage to a decimal and multiply."
        explanation = f"{percent}% of {number} is equivalent to {percent/100} * {number} = {float(answer.split(' ')[1]):.2f}."
        options = {answer, f"GHS {percent*number/10:.2f}", f"GHS {number/percent:.2f}"}

    elif q_type == 'express_as_percent':
        part, whole = random.randint(10, 40), random.randint(50, 100)
        question = f"In a class in Accra, {part} students out of {whole} are girls. What percentage of the class are girls?"
        answer = f"{(part/whole)*100:.1f}%"
        hint = "Use the formula: (Part / Whole) * 100%."
        explanation = f"The percentage is calculated as $(\\frac{{{part}}}{{{whole}}}) \\times 100\\% = {answer}$."
        options = {answer, f"{(whole/part)*100:.1f}%"}

    elif q_type == 'percent_change':
        old, new = random.randint(50, 200), random.randint(201, 400)
        question = f"The price of a textbook increased from GHS {old} to GHS {new}. Find the percentage increase."
        ans_val = ((new - old) / old) * 100; answer = f"{ans_val:.1f}%"
        hint = "Use the formula: (New Value - Old Value) / Old Value * 100%"; explanation = f"Change = {new} - {old} = {new-old}.\nPercent Change = (\\frac{{{new-old}}}{{{old}}}) \\times 100 = {answer}."
        options = {answer, f"{((new-old)/new)*100:.1f}%"}

    elif q_type == 'profit_loss':
        cost, selling = random.randint(100, 200), random.randint(201, 300)
        question = f"A trader in Kumasi bought an item for GHS {cost} and sold it for GHS {selling}. Calculate the profit percent."
        profit = selling - cost; ans_val = (profit / cost) * 100; answer = f"{ans_val:.1f}%"
        hint = "Profit Percent = (Profit / Cost Price) * 100%"; explanation = f"Profit = {selling} - {cost} = {profit}.\nProfit Percent = (\\frac{{{profit}}}{{{cost}}}) \\times 100 = {answer}."
        options = {answer, f"{(profit/selling)*100:.1f}%"}

    elif q_type == 'reverse_percent':
        original_price = random.randint(100, 400)
        discount = random.randint(1, 8) * 5 # 5, 10, 15... 40
        final_price = original_price * (1 - discount/100)
        question = f"After a {discount}% discount, a shirt costs GHS {final_price:.2f}. What was the original price?"
        answer = f"GHS {original_price:.2f}"
        hint = f"The final price represents {100-discount}% of the original price. Let the original price be P and solve for it."
        explanation = f"Let P be the original price.\n$P \\times (1 - \\frac{{{discount}}}{{100}}) = {final_price:.2f}$.\n$P = \\frac{{{final_price:.2f}}}{{1 - {discount/100}}} = {original_price:.2f}$."
        options = {answer, f"GHS {final_price * (1 + discount/100):.2f}"}

    elif q_type == 'successive_change':
        initial_val = 1000
        increase = random.randint(10, 20)
        decrease = random.randint(5, 9)
        val_after_increase = initial_val * (1 + increase/100)
        final_val = val_after_increase * (1 - decrease/100)
        net_change = ((final_val - initial_val) / initial_val) * 100
        question = f"A worker's salary of GHS {initial_val} was increased by {increase}%, and later decreased by {decrease}%. What is the net percentage change in their salary?"
        answer = f"{net_change:.2f}%"
        hint = "Calculate the new salary after the first change, then apply the second change to that new amount."
        explanation = f"1. After {increase}% increase: GHS {initial_val} * 1.{increase} = GHS {val_after_increase}.\n2. After {decrease}% decrease: GHS {val_after_increase} * (1 - 0.0{decrease}) = GHS {final_val}.\n3. Net Change = {final_val} - {initial_val} = {final_val-initial_val}.\n4. Net % Change = (\\frac{{{final_val-initial_val}}}{{{initial_val}}}) \\times 100 = {answer}."
        options = {answer, f"{increase-decrease}%"}

    elif q_type == 'percent_error':
        actual = random.randint(50, 100)
        error = random.randint(1, 5)
        measured = actual + error
        question = f"A length was measured as {measured} cm, but the actual length was {actual} cm. Calculate the percentage error."
        ans_val = (error / actual) * 100
        answer = f"{ans_val:.2f}%"
        hint = "Percentage Error = (Error / Actual Value) * 100%."
        explanation = f"1. Error = Measured - Actual = {measured} - {actual} = {error}.\n2. Percentage Error = (\\frac{{{error}}}{{{actual}}}) \\times 100\\% = {answer}."
        options = {answer, f"{(error/measured)*100:.2f}%"}

    return {"question": question, "options": _finalize_options(options), "answer": answer, "hint": hint, "explanation": explanation}

def _generate_fractions_question():
    """Generates a multi-subtopic question for Fractions with enhanced variety."""
    q_type = random.choice(['operation', 'bodmas', 'word_problem', 'convert_mixed', 'equivalent', 'compare', 'complex_fraction'])
    question, answer, hint, explanation = "", "", "", ""
    options = set()

    if q_type == 'operation':
        f1, f2 = Fraction(random.randint(1, 10), random.randint(2, 10)), Fraction(random.randint(1, 10), random.randint(2, 10))
        op, sym = random.choice([('add', '+'), ('subtract', '-'), ('multiply', '\\times'), ('divide', '\\div')])
        if op == 'divide' and f2.numerator == 0: f2 = Fraction(1, f2.denominator)
        
        f1_latex, f2_latex = _get_fraction_latex_code(f1), _get_fraction_latex_code(f2)
        question = f"Calculate: ${f1_latex} {sym} {f2_latex}$"
        
        if op == 'add': res = f1 + f2
        elif op == 'subtract': res = f1 - f2
        elif op == 'multiply': res = f1 * f2
        else: res = f1 / f2
        
        answer = _format_fraction_text(res)
        hint = "Remember the specific rules for adding, subtracting, multiplying, and dividing fractions."
        explanation = f"The result of the calculation is ${_get_fraction_latex_code(res)}$."
        options = {answer, _format_fraction_text(Fraction(f1.numerator+f2.numerator, f1.denominator+f2.denominator))}

    elif q_type == 'bodmas':
        a, b, c = [random.randint(2, 6) for _ in range(3)]
        question = f"Evaluate the expression: $ (\\frac{{1}}{{{a}}} + \\frac{{1}}{{{b}}}) \\times {c} $"
        res = (Fraction(1, a) + Fraction(1, b)) * c
        answer = _format_fraction_text(res)
        hint = "Follow BODMAS. Solve the operation inside the brackets first."
        explanation = f"1. Bracket: $\\frac{{1}}{{{a}}} + \\frac{{1}}{{{b}}} = \\frac{{{b}+{a}}}{{{a*b}}}$.\n\n2. Multiply: $\\frac{{{a+b}}}{{{a*b}}} \\times {c} = {_get_fraction_latex_code(res)}$."
        distractor = _format_fraction_text(Fraction(1,a) + Fraction(1,b)*c)
        options = {answer, distractor}

    elif q_type == 'word_problem':
        den = random.choice([3, 4, 5, 8]); num = random.randint(1, den-1); quantity = random.randint(10, 20) * den
        question = f"A student in Accra had {quantity} oranges and gave away $\\frac{{{num}}}{{{den}}}$ of them. How many oranges did the student have left?"
        answer = str(int(quantity * (1-Fraction(num,den))))
        hint = "First, find the fraction of oranges remaining. Then, multiply that fraction by the total number of oranges."
        explanation = f"1. Fraction remaining = $1 - \\frac{{{num}}}{{{den}}} = \\frac{{{den-num}}}{{{den}}}$.\n2. Oranges left = $\\frac{{{den-num}}}{{{den}}} \\times {quantity} = {answer}$."
        options = {answer, str(int(quantity*Fraction(num,den)))}

    elif q_type == 'convert_mixed':
        whole, num, den = random.randint(1, 5), random.randint(1, 5), random.randint(6, 10)
        improper_num = whole * den + num; improper_frac = Fraction(improper_num, den)
        mixed_num_latex = f"{whole}\\frac{{{num}}}{{{den}}}"
        
        if random.random() > 0.5:
            question = f"Convert the mixed number ${mixed_num_latex}$ to an improper fraction."
            answer = _format_fraction_text(improper_frac)
            hint = "Multiply the whole number by the denominator and add the numerator."
            explanation = f"Calculation: $({whole} \\times {den}) + {num} = {improper_num}$. The improper fraction is ${_get_fraction_latex_code(improper_frac)}$."
        else:
            question = f"Convert the improper fraction ${_get_fraction_latex_code(improper_frac)}$ to a mixed number."
            answer = f"${mixed_num_latex}$"
            hint = "Divide the numerator by the denominator."
            explanation = f"${improper_num} \\div {den} = {whole}$ with a remainder of ${num}$. The mixed number is ${mixed_num_latex}$."
        options = {answer, f"{whole*num+den}/{den}"}

    elif q_type == 'equivalent':
        num, den = random.randint(2, 5), random.randint(6, 11); multiplier = random.randint(2, 5)
        question = f"Find the missing value: $\\frac{{{num}}}{{{den}}} = \\frac{{?}}{{{den*multiplier}}}$"
        answer = str(num * multiplier)
        hint = "Multiply the numerator and the denominator by the same number."
        explanation = f"The denominator was multiplied by {multiplier}, so the numerator must also be multiplied by {multiplier}. Missing value = ${num} \\times {multiplier} = {answer}$."
        options = {answer, str(num+multiplier)}
        
    elif q_type == 'compare':
        f1 = Fraction(random.randint(1, 4), random.randint(5, 10)); f2 = Fraction(random.randint(1, 4), random.randint(5, 10));
        while f1 == f2: f2 = Fraction(random.randint(1, 4), random.randint(5, 10))
        question = f"Which of the following statements is true?"
        answer = f"${_get_fraction_latex_code(f1)} > {_get_fraction_latex_code(f2)}$" if f1 > f2 else f"${_get_fraction_latex_code(f1)} < {_get_fraction_latex_code(f2)}$"
        hint = "To compare fractions, find a common denominator or convert them to decimals."
        explanation = f"${_get_fraction_latex_code(f1)} \\approx {float(f1):.3f}$ and ${_get_fraction_latex_code(f2)} \\approx {float(f2):.3f}$. Therefore, {answer} is true."
        options = {answer, f"${_get_fraction_latex_code(f1)} = {_get_fraction_latex_code(f2)}$"}

    elif q_type == 'complex_fraction':
        f1, f2 = Fraction(random.randint(1, 5), random.randint(2, 6)), Fraction(random.randint(1, 5), random.randint(2, 6))
        question = f"Simplify the complex fraction: $\\frac{{{_get_fraction_latex_code(f1)}}}{{{_get_fraction_latex_code(f2)}}}$"
        answer = _format_fraction_text(f1 / f2)
        hint = "Rewrite the complex fraction as a division problem: (top) ÷ (bottom)."
        # --- THIS LINE IS CORRECTED ---
        inverted_f2_latex = _get_fraction_latex_code(Fraction(f2.denominator, f2.numerator))
        explanation = f"This is equivalent to ${_get_fraction_latex_code(f1)} \\div {_get_fraction_latex_code(f2)}$, which is ${_get_fraction_latex_code(f1)} \\times {inverted_f2_latex} = {_get_fraction_latex_code(f1/f2)}$."
        options = {answer, _format_fraction_text(f1*f2)}

    return {"question": question, "options": _finalize_options(options, "fraction"), "answer": answer, "hint": hint, "explanation": explanation}
def _generate_indices_question():
    """Generates a multi-subtopic question for Indices with enhanced variety."""
    # Subtopics: Laws, Fractional, Solving Equations (same/different base), Standard Form
    q_type = random.choice(['laws', 'fractional', 'solve_same_base', 'standard_form', 'solve_different_base'])
    question, answer, hint, explanation = "", "", "", ""
    options = set()

    if q_type == 'laws':
        base = random.randint(2, 7)
        p1, p2 = random.randint(5, 10), random.randint(2, 4)
        op, sym, res_p, rule = random.choice([
            ('multiply', '\\times', p1+p2, 'a^m \\times a^n = a^{m+n}'), 
            ('divide', '\\div', p1-p2, 'a^m \\div a^n = a^{m-n}'),
            ('power', ')', p1*p2, '(a^m)^n = a^{mn}')
        ])
        if op == 'power':
            question = f"Simplify the expression: $({base}^{{{p1}}})^{{{p2}}}$"
            explanation = f"Using the power of a power rule, $(x^a)^b = x^{{ab}}$, we get $({base}^{{{p1}}})^{{{p2}}} = {base}^{{{p1*p2}}}$."
        else:
            question = f"Simplify the expression: ${base}^{{{p1}}} {sym} {base}^{{{p2}}}$"
            explanation = f"Using the {op} rule, ${rule}$, we get ${base}^{{{p1}}} {sym} {base}^{{{p2}}} = {base}^{{{res_p}}}$."
        answer = f"${base}^{{{res_p}}}$"
        hint = f"Recall the laws of indices for '{op}' operations."
        options = {answer, f"${base}^{{{p1+p2}}}$", f"${base}^{{{p1*p2}}}$"}

    elif q_type == 'fractional':
        base_num = random.choice([4, 8, 9, 16, 27, 64])
        if base_num in [4, 9, 16]: root = 2
        else: root = 3
        power = random.randint(2, 3)
        question = f"Evaluate: ${base_num}^{{\\frac{{{power}}}{{{root}}}}}$"
        res = int(round((base_num**(1/root))**power))
        answer = str(res)
        hint = "First, find the root of the base number, then apply the power."
        explanation = f"The expression ${base_num}^{{\\frac{{{power}}}{{{root}}}}}$ means $(\\sqrt[{root}]{{{base_num}}})^{{{power}}}$.\n1. $\\sqrt[{root}]{{{base_num}}} = {int(base_num**(1/root))}$.\n2. $({int(base_num**(1/root))})^{{{power}}} = {res}$."
        options = {answer, str(base_num*power/root)}

    elif q_type == 'solve_same_base':
        base = random.randint(2, 5)
        power = random.randint(2, 4)
        a, b = 2, -1
        while (power - b) % a != 0:
            power = random.randint(2, 5)
        question = f"Solve for the variable $x$: ${base}^{{{a}x + ({b})}} = {base**power}$"
        answer = _format_fraction_text(Fraction(power - b, a))
        hint = "If the bases on both sides of an equation are the same, you can equate the exponents."
        explanation = f"1. The equation is ${base}^{{{a}x + ({b})}} = {base**power}$.\n2. Since the bases are equal, set the exponents equal: ${a}x + ({b}) = {power}$.\n3. ${a}x = {power-b}$.\n4. $x = \\frac{{{power-b}}}{{{a}}}$."
        options = {answer, str(power), str(power-b)}

    elif q_type == 'standard_form':
        # --- THIS ENTIRE BLOCK IS REWRITTEN FOR ROBUSTNESS ---
        num = round(random.uniform(1.0, 9.9), random.randint(2, 4))
        power = random.randint(3, 6)
        
        # Create the decimal form of the number
        decimal_form = f"{num / (10**power):.{power+len(str(int(num)))}f}"
        
        # Create the correctly formatted LaTeX answer
        answer = f"${num} \\times 10^{{-{power}}}$"
        
        # Create a set of unique, correctly formatted distractors
        distractors = {
            f"${num} \\times 10^{{{power}}}$",         # Wrong sign on exponent
            f"{decimal_form}",                       # Just the decimal form
            f"${round(num*10, 2)} \\times 10^{{-{power+1}}}$" # Wrong coefficient
        }
        
        question = f"A measurement taken by a scientist in Kajaji is {decimal_form} metres. Express this number in standard form."
        hint = "Standard form is written as $A \\times 10^n$, where $1 \\le A < 10$. Count how many places the decimal point must move."
        explanation = f"To get the number {num} (which is between 1 and 10), we must move the decimal point {power} places to the right. Moving to the right corresponds to a negative exponent.\nThus, the standard form is {answer}."
        
        options = {answer, *distractors}

    elif q_type == 'solve_different_base':
        problems = [(4, 2, 2, 1, 2), (8, 3, 4, 2, 2), (9, 2, 3, 1, 3), (27, 3, 9, 2, 3)]
        base1, p1, base2, p2, common_base = random.choice(problems)
        k = random.randint(1, 4)
        x_val_frac = Fraction(-p2 * k, p1 - p2)
        while (p1 - p2) == 0 or x_val_frac.denominator != 1:
            base1, p1, base2, p2, common_base = random.choice(problems)
            k = random.randint(1, 4)
            if (p1 - p2) != 0: x_val_frac = Fraction(-p2 * k, p1 - p2)
        x_val = x_val_frac.numerator
        
        question = f"Solve for x in the equation: ${base1}^x = {base2}^{{x-{k}}}$"
        answer = str(x_val)
        hint = "Express both sides of the equation as powers of the same common base."
        explanation = (f"1. Express with base {common_base}: $({common_base}^{{{p1}}})^x = ({common_base}^{{{p2}}})^{{x-{k}}}$.\n"
                       f"2. Simplify exponents: ${common_base}^{{{p1}x}} = {common_base}^{{{p2}(x-{k})}}$.\n"
                       f"3. Equate exponents: ${p1}x = {p2}x - {p2*k}$.\n"
                       f"4. Solve for x: $({p1-p2})x = {-p2*k} \implies x = {x_val}$.")
        options = {answer, str(k), str(x_val + 1)}

    return {"question": question, "options": _finalize_options(options), "answer": answer, "hint": hint, "explanation": explanation}

def _generate_surds_question():
    """Generates a multi-subtopic question for Surds with enhanced variety."""
    q_type = random.choice(['identify', 'simplify', 'operate', 'rationalize', 'equation', 'geometry'])
    question, answer, hint, explanation = "", "", "", ""
    options = set()

    if q_type == 'identify':
        surd = random.choice([2, 3, 5, 7, 11])
        perfect_square = random.choice([4, 9, 16, 25])
        
        question = f"Which of the following numbers is a surd?"
        answer = f"$\\sqrt{{{surd}}}$"
        hint = "A surd is an irrational number left in root form. A number is not a surd if its root is a whole number."
        explanation = f"$\\sqrt{{{perfect_square}}} = {int(math.sqrt(perfect_square))}$, which is a rational number.\n$\\sqrt{{{surd}}}$ cannot be simplified to a rational number, so it is a surd."
        options = {answer, f"$\\sqrt{{{perfect_square}}}$", str(random.randint(2,10))}

    elif q_type == 'simplify':
        p_sq, n = random.choice([4, 9, 16, 25, 36]), random.choice([2, 3, 5, 7, 10])
        num = p_sq * n
        question = f"Express $\\sqrt{{{num}}}$ in its simplest surd form."
        answer = f"${int(math.sqrt(p_sq))}\\sqrt{{{n}}}$"
        hint = f"Find the largest perfect square that is a factor of {num}."
        explanation = f"1. Find factors: ${num} = {p_sq} \\times {n}$.\n2. Split the surd: $\\sqrt{{{num}}} = \\sqrt{{{p_sq}}} \\times \\sqrt{{{n}}}$.\n3. Simplify: ${answer}$."
        options = {answer, f"${n}\\sqrt{{{p_sq}}}$"}

    elif q_type == 'operate':
        op_type = random.choice(['add_sub', 'multiply'])
        if op_type == 'add_sub':
            base_surd = random.choice([2, 3, 5]); c1, c2 = random.randint(2, 10), random.randint(2, 10)
            op, sym, res = random.choice([('add', '+', c1+c2), ('subtract', '-', c1-c2)])
            question = f"Simplify: ${c1}\\sqrt{{{base_surd}}} {sym} {c2}\\sqrt{{{base_surd}}}$"
            answer = f"${res}\\sqrt{{{base_surd}}}$"
            hint = "You can only add or subtract 'like' surds."
            explanation = f"Factor out the common surd: $({c1} {sym} {c2})\\sqrt{{{base_surd}}} = {res}\\sqrt{{{base_surd}}}$."
            options = {answer, f"${c1+c2}\\sqrt{{{base_surd*2}}}$"}
        else: # multiply
            a, b = random.randint(2, 5), random.randint(2, 5)
            c = random.randint(2, 5)
            question = f"Expand and simplify: $({a} + \\sqrt{{{b}}})({c} - \\sqrt{{{b}}})$"
            res_term1 = a*c - b
            res_term2 = c - a
            answer = f"${res_term1} + {res_term2}\\sqrt{{{b}}}$" if res_term2 >= 0 else f"${res_term1} - {abs(res_term2)}\\sqrt{{{b}}}$"
            hint = "Use the FOIL method to expand the brackets, then collect like terms."
            explanation = f"$({a} + \\sqrt{{{b}}})({c} - \\sqrt{{{b}}}) = {a*c} - {a}\\sqrt{{{b}}} + {c}\\sqrt{{{b}}} - {b} = {answer}$."
            options = {answer, f"{a*c+b} + {c+a}\\sqrt{{{b}}}$"}

    elif q_type == 'rationalize':
        a, b, c = random.randint(2, 9), random.randint(2, 9), random.choice([2, 3, 5, 7])
        while b*b == c: b = random.randint(2,9)
        question = f"Rationalize the denominator of $\\frac{{{a}}}{{{b} + \\sqrt{{{c}}}}}$"
        num_part1, num_part2 = a*b, -a; den = b**2 - c
        common_divisor = math.gcd(math.gcd(num_part1, num_part2), den)
        s_num_part1, s_num_part2, s_den = num_part1//common_divisor, num_part2//common_divisor, den//common_divisor
        num_latex = f"{s_num_part1} - {abs(s_num_part2)}\\sqrt{{{c}}}" if s_num_part2 < 0 else f"{s_num_part1} + {s_num_part2}\\sqrt{{{c}}}"
        if s_den == 1 or s_den == -1: answer = f"${-s_num_part1 if s_den == -1 else s_num_part1} {'+' if -s_num_part2 > 0 else '-'} {abs(s_num_part2)}\\sqrt{{{c}}}$"
        else: answer = f"$\\frac{{{num_latex}}}{{{s_den}}}$"
        hint = f"Multiply the numerator and denominator by the conjugate of the denominator, which is $({b} - \\sqrt{{{c}}})$."
        explanation = f"1. Multiply by conjugate: $\\frac{{{a}}}{{{b} + \\sqrt{{{c}}}}} \\times \\frac{{{b} - \\sqrt{{{c}}}}}{{{b} - \\sqrt{{{c}}}}}$.\n2. Numerator: ${a*b} - {a}\\sqrt{{{c}}}$.\n3. Denominator: ${b**2} - {c} = {den}$.\n4. Simplify $\\frac{{{a*b} - {a}\\sqrt{{{c}}}}}{{{den}}}$ to get {answer}."
        options = {answer, f"$\\frac{{{a*b} + {a}\\sqrt{{{c}}}}}{{{den}}}$"}

    elif q_type == 'equation':
        result = random.randint(2, 5); c = random.randint(1, 10); x_val = result**2 + c
        question = f"Solve for x: $\\sqrt{{x - {c}}} = {result}$"
        answer = str(x_val); hint = "To solve for x, square both sides of the equation."
        explanation = (f"1. Given: $\\sqrt{{x - {c}}} = {result}$.\n2. Square both sides: $x - {c} = {result**2}$.\n3. $x = {result**2} + {c} = {x_val}$.")
        options = {answer, str(result + c), str(result**2)}

    elif q_type == 'geometry':
        # --- THIS BLOCK IS REWRITTEN FOR BETTER DISTRACTORS ---
        a, b = random.randint(2, 5), random.randint(6, 9)
        c_sq = a**2 + b**2
        question = f"A right-angled triangle has shorter sides of length ${a}$ cm and ${b}$ cm. Find the exact length of the hypotenuse in surd form."
        answer = f"$\\sqrt{{{c_sq}}}$"
        hint = "Use Pythagoras' theorem: $a^2 + b^2 = c^2$. Leave the result in surd form."
        explanation = f"1. By Pythagoras' theorem, $c^2 = a^2 + b^2$.\n2. $c^2 = {a}^2 + {b}^2 = {a**2} + {b**2} = {c_sq}$.\n3. The exact length of the hypotenuse is $c = \\sqrt{{{c_sq}}}$ cm."
        
        # Create plausible distractors in the same surd format
        distractor1 = f"$\\sqrt{{{abs(b**2 - a**2)}}}$" # Common mistake: subtracting instead of adding
        distractor2 = f"$\\sqrt{{{a+b}}}$"            # Common mistake: adding before squaring
        distractor3 = f"${a+b}$"                       # Mistake: adding sides (not in surd form, but very common)
        options = {answer, distractor1, distractor2, distractor3}

    return {"question": question, "options": _finalize_options(options), "answer": answer, "hint": hint, "explanation": explanation}
def _generate_binary_ops_question():
    """Generates a multi-subtopic question for Binary Operations with enhanced variety."""
    # UPGRADED: Expanded list of sub-topics based on your suggestions
    q_type = random.choice(['evaluate', 'table_read', 'identity_inverse', 'properties'])
    question, answer, hint, explanation = "", "", "", ""
    options = set()

    if q_type == 'evaluate':
        a, b = random.randint(2, 9), random.randint(2, 9)
        c = random.randint(2, 5)
        op_def, op_func, op_sym = random.choice([
            (f"p \\ast q = p + q + {c}pq", lambda x, y: x + y + c*x*y, r"\ast"),
            (f"x \\oplus y = x^2 - {c}y", lambda x, y: x**2 - c*y, r"\oplus"),
            (f"m \\nabla n = m + n - {c}", lambda x, y: x + y - c, r"\nabla"),
        ])
        question = f"A binary operation is defined on the set of real numbers by ${op_def}$. Evaluate $({a} {op_sym} {b})$."
        answer = str(op_func(a, b))
        hint = "Substitute the first value for the first variable and the second value for the second variable in the definition."
        explanation = f"1. The definition is ${op_def}$.\n2. We substitute a={a} and b={b}.\n3. The calculation becomes: {op_func(a,b)}."
        options = {answer, str(op_func(b, a))}

    elif q_type == 'identity_inverse':
        # Using a standard definition for this type a*b = a+b-k
        k = random.randint(2, 5)
        identity_element = k
        element = random.randint(k+1, 12)
        # a * inv = e => a + inv - k = k => inv = 2k - a
        inverse_element = 2*k - element
        
        question = f"For the binary operation $a \\ast b = a+b-{k}$ on the set of real numbers, what is the inverse of the element ${element}$?"
        answer = str(inverse_element)
        hint = f"First, confirm the identity element 'e' by solving $a \\ast e = a$. Then, find the inverse 'inv' by solving ${element} \\ast inv = e$."
        explanation = f"1. Find identity (e): $a+e-{k}=a \implies e={k}$.\n2. Let the inverse of {element} be $inv$.\n3. The formula is ${element} \\ast inv = {identity_element}$.\n4. Using the definition: ${element} + inv - {k} = {identity_element}$.\n5. $inv = {identity_element} + {k} - {element} = {2*k - element}$."
        options = {answer, str(-element), str(element-k)}

    elif q_type == 'properties':
        op_def_c, sym_c = (r"a \Delta b = a + b + ab", r"\Delta") # Commutative
        op_def_nc, sym_nc = (r"a \circ b = 2a - b", r"\circ") # Not commutative
        chosen_op, chosen_sym, is_comm = random.choice([(op_def_c, sym_c, True), (op_def_nc, sym_nc, False)])
        
        question = f"Is the binary operation ${chosen_op}$ defined on the set of real numbers a commutative operation?"
        answer = "Yes" if is_comm else "No"
        hint = "A binary operation * is commutative if $a * b = b * a$ for all values."
        explanation = f"To check for commutativity, we test if $a {chosen_sym} b = b {chosen_sym} a$.\nFor ${chosen_op}$: $a {chosen_sym} b = {chosen_op.split('=')[1].strip()}$.\nAnd $b {chosen_sym} a = {chosen_op.split('=')[1].strip().replace('a','B').replace('b','A').upper().replace('A','a').replace('B','b')}$.\nSince these are {'' if is_comm else 'not '}equal, the operation is {'' if is_comm else 'not '}commutative."
        options = {"Yes", "No"}

    elif q_type == 'table_read':
        s = [1, 2, 3, 4]
        op_sym = random.choice(["$\\oplus$", "$\\otimes$"])
        table_md = f"| {op_sym} | 1 | 2 | 3 | 4 |\n|---|---|---|---|---|\n"
        results = {}
        # Operation: (row + col) mod 4, with 0 replaced by 4 for closure in {1,2,3,4}
        for row in s:
            table_md += f"| **{row}** |"
            for col in s:
                res = (row + col) % 4
                if res == 0: res = 4 
                table_md += f" {res} |"
                results[(row, col)] = res
            table_md += "\n"
        
        sub_q = random.choice(['evaluate', 'identity'])
        if sub_q == 'evaluate':
            a, b = random.choice(s), random.choice(s)
            question = f"The operation {op_sym} is defined on the set $\\{{1, 2, 3, 4\\}}$ by the Cayley table below. Find the value of $({a} {op_sym} {b})$.\n\n{table_md}"
            answer = str(results[(a,b)])
            hint = "To find a * b from the table, locate the row for 'a' and the column for 'b'. The cell where they intersect is the answer."
            explanation = f"1. Find the row labeled **{a}**.\n2. Find the column labeled **{b}**.\n3. The value in the cell where this row and column meet is **{answer}**."
            options = {answer, str(results.get((b,a))), str(random.choice(s))}
        else: # identity
            # The identity 'e' is the element whose row and column are identical to the header row/column
            identity_element = 4 # For (a+b)%4 on {1,2,3,4}
            question = f"The operation {op_sym} is defined on the set $\\{{1, 2, 3, 4\\}}$ by the Cayley table below. What is the identity element?\n\n{table_md}"
            answer = str(identity_element)
            hint = "The identity element 'e' is the element where the row for 'e' and the column for 'e' are identical to the header row and column."
            explanation = f"Look for the row in the table that reads '1 2 3 4'. The label for that row is the identity element, which is **{identity_element}**. Similarly, the column for **{identity_element}** also reads '1 2 3 4'."
            options = {answer, "1", "2", "3"}
        
    return {"question": question, "options": _finalize_options(options), "answer": answer, "hint": hint, "explanation": explanation}

def _generate_relations_functions_question():
    """Generates a multi-subtopic question for Relations and Functions with enhanced variety."""
    q_type = random.choice(['domain_range', 'evaluate', 'composite', 'inverse', 'types_of_relations', 'is_function'])
    question, answer, hint, explanation = "", "", "", ""
    options = set()
    
    if q_type == 'domain_range':
        # --- THIS ENTIRE BLOCK IS REWRITTEN FOR CORRECTNESS ---
        domain_list = sorted(list(set(random.sample(range(-15, 20), k=random.randint(4, 5)))))
        range_list = sorted(list(set(random.sample(range(-15, 20), k=random.randint(4, 5)))))
        
        # Ensure domain and range are not identical
        while set(domain_list) == set(range_list):
            range_list = sorted(list(set(random.sample(range(-15, 20), k=random.randint(4, 5)))))
            
        relation_pairs = list(zip(domain_list, range_list))
        random.shuffle(relation_pairs)
        relation_str = str(set(relation_pairs)).replace("'", "")
        
        d_or_r = random.choice(['domain', 'range'])
        
        question = f"What is the {d_or_r} of the relation $R = {relation_str}$?"
        
        domain_set_str = str(set(domain_list))
        range_set_str = str(set(range_list))

        if d_or_r == 'domain':
            answer = domain_set_str
            # Plausible distractors
            distractor1 = range_set_str
            distractor2 = str(set(domain_list).union(set(range_list)))
            distractor3 = str(set(domain_list) - {random.choice(domain_list)}) # Domain with one element missing
        else: # range
            answer = range_set_str
            # Plausible distractors
            distractor1 = domain_set_str
            distractor2 = str(set(domain_list).union(set(range_list)))
            distractor3 = str(set(range_list) - {random.choice(range_list)}) # Range with one element missing

        hint = "The domain is the set of all unique first elements (x-values). The range is the set of all unique second elements (y-values)."
        explanation = f"Given the relation $R = {relation_str}$:\n- The domain (set of all first numbers) is ${domain_set_str}$.\n- The range (set of all second numbers) is ${range_set_str}$."
        options = {answer, distractor1, distractor2, distractor3}

    elif q_type == 'evaluate':
        a, b, x = random.randint(2, 8), random.randint(-10, 10), random.randint(1, 7)
        question = f"If $f(x) = {a}x^2 + {b}$, find the value of $f({x})$."
        answer = str(a * (x**2) + b)
        hint = "Substitute the given value for x into the function's definition and evaluate."
        explanation = f"We replace every 'x' with '{x}':\n$f({x}) = {a}({x})^2 + {b} = {a*(x**2)} + {b} = {a*(x**2)+b}$."
        options = {answer, str(a * x + b), str((a * x)**2 + b)}

    elif q_type == 'composite':
        a, b, c, d, x_val = [random.randint(1, 5) for _ in range(5)]
        g_of_x = c*x_val + d
        question = f"Given $f(x) = {a}x + {b}$ and $g(x) = {c}x + {d}$, find the value of $(f \\circ g)({x_val})$."
        answer = str(a*g_of_x + b)
        hint = f"This means find $f(g({x_val}))$. Calculate the inner function first."
        explanation = f"1. First find $g({x_val}) = {c}({x_val}) + {d} = {g_of_x}$.\n2. Now use this result as the input for f: $f({g_of_x}) = {a}({g_of_x}) + {b} = {a*g_of_x+b}$."
        options = {answer, str(c*(a*x_val + b) + d)}

    elif q_type == 'inverse':
        a, b = random.randint(2,7), random.randint(1,10)
        question = f"Find the inverse function, $f^{{-1}}(x)$, of the function $f(x) = \\frac{{x + {b}}}{{{a}}}$."
        answer = f"$f^{{-1}}(x) = {a}x - {b}$"
        hint = "Let y = f(x), swap x and y, then make y the subject of the formula."
        explanation = f"1. Start with $y = \\frac{{x + {b}}}{{{a}}}$.\n2. Swap x and y: $x = \\frac{{y + {b}}}{{{a}}}$.\n3. Solve for y: ${a}x = y + {b} \\implies y = {a}x - {b}$."
        options = {answer, f"$f^{{-1}}(x) = \\frac{{x - {b}}}{{{a}}}$", f"$f^{{-1}}(x) = {a}x + {b}$"}
        
    elif q_type == 'types_of_relations':
        one_to_one = str({(1, 'a'), (2, 'b'), (3, 'c')})
        many_to_one = str({(1, 'a'), (2, 'a'), (3, 'b')})
        one_to_many = str({(1, 'a'), (1, 'b'), (2, 'c')})
        relation, correct_type = random.choice([(one_to_one, "One-to-one"), (many_to_one, "Many-to-one"), (one_to_many, "One-to-many")])
        question = f"The relation $R = {relation}$. What type of mapping is this?"
        answer = correct_type
        hint = "Check if any x-values or y-values are repeated in the ordered pairs."
        explanation = f"This relation is **{correct_type}** because of how the inputs (first elements) map to the outputs (second elements)."
        options = {"One-to-one", "Many-to-one", "One-to-many"}
        options.add(answer)

    elif q_type == 'is_function':
        func_relation = str({(1, 5), (2, 10), (3, 15)})
        not_func_relation = str({(1, 5), (1, 6), (2, 10)})
        question = f"Which of the following relations is also a function?"
        answer = func_relation
        hint = "A relation is a function if every input (x-value) maps to exactly one, unique output (y-value)."
        explanation = f"The relation {not_func_relation} is not a function because the input '1' maps to two different outputs (5 and 6). The relation {func_relation} is a function because every input has only one output."
        options = {answer, not_func_relation}

    return {"question": question, "options": _finalize_options(options, "set_str"), "answer": answer, "hint": hint, "explanation": explanation}

def _generate_sequence_series_question():
    """Generates a multi-subtopic question for Sequence and Series with enhanced variety."""
    # UPGRADED: Expanded list of sub-topics based on your suggestions
    q_type = random.choice(['ap_term', 'gp_term', 'ap_sum', 'gp_sum_inf', 'word_problem'])
    question, answer, hint, explanation = "", "", "", ""
    options = set()
    a = random.randint(2, 10)

    if q_type == 'ap_term':
        d, n = random.randint(3, 10), random.randint(10, 25)
        sequence = ", ".join([str(a + i*d) for i in range(4)])
        question = f"Find the {n}th term of the arithmetic progression: {sequence}, ..."
        answer = str(a + (n - 1) * d)
        hint = r"Use the AP nth term formula: $a_n = a + (n-1)d$."
        explanation = f"1. First term $a = {a}$.\n2. Common difference $d = {a+d} - {a} = {d}$.\n3. The {n}th term is $a_{{{n}}} = {a} + ({n}-1)({d}) = {answer}$."
        options = {answer, str(a + n*d)}
    
    elif q_type == 'gp_term':
        r, n = random.randint(2, 4), random.randint(5, 8)
        sequence = ", ".join([str(a * r**i) for i in range(3)])
        question = f"What is the {n}th term of the geometric progression: {sequence}, ...?"
        answer = str(a * r**(n-1))
        hint = r"Use the GP nth term formula: $a_n = ar^{n-1}$."
        explanation = f"1. First term $a = {a}$.\n2. Common ratio $r = \\frac{{{a*r}}}{{{a}}} = {r}$.\n3. The {n}th term is $a_{{{n}}} = {a} \\times {r}^{{{n}-1}} = {answer}$."
        options = {answer, str((a*r)**(n-1))}

    elif q_type == 'ap_sum':
        d, n = random.randint(2, 7), random.randint(12, 25)
        question = f"Find the sum of the first {n} terms of an Arithmetic Progression with first term {a} and common difference {d}."
        answer = str(int((n/2) * (2*a + (n-1)*d)))
        hint = r"Use the sum of an AP formula: $S_n = \frac{n}{2}(2a + (n-1)d)$."
        explanation = f"$S_{{{n}}} = \\frac{{{n}}}{{2}}(2({a}) + ({n}-1)({d})) = \\frac{{{n}}}{{2}}({2*a + (n-1)*d}) = {answer}$."
        options = {answer, str(n*(a + (n-1)*d))}

    elif q_type == 'gp_sum_inf':
        r = Fraction(random.randint(1,3), random.randint(4, 7))
        question = f"A geometric series has a first term of ${a}$ and a common ratio of ${_get_fraction_latex_code(r)}$. Calculate its sum to infinity."
        answer = _format_fraction_text(a / (1 - r))
        hint = r"Use the sum to infinity formula: $S_\infty = \frac{a}{1-r}$, which is valid for $|r| < 1$."
        explanation = f"$S_\\infty = \\frac{{{a}}}{{1 - {_get_fraction_latex_code(r)}}} = \\frac{{{a}}}{{{_get_fraction_latex_code(1-r)}}} = {_get_fraction_latex_code(a/(1-r))}$."
        options = {answer, _format_fraction_text(a/(1+r))}
        
    elif q_type == 'word_problem':
        initial_amount = random.randint(100, 200)
        depreciation_rate = random.randint(10, 20)
        years = 3
        # Value after n years = P * (1 - r)^n
        final_value = initial_amount * ((1 - depreciation_rate/100)**years)
        question = f"A farmer in the Ashanti Region buys a machine for GHS {initial_amount}. The machine depreciates in value by {depreciation_rate}% each year. What is its value after {years} years, to two decimal places?"
        answer = f"GHS {final_value:.2f}"
        hint = "This is a geometric progression problem where the common ratio 'r' is less than 1. Use the formula for depreciation: Final Value = $P(1 - r)^n$."
        explanation = f"1. The initial value P = {initial_amount}.\n2. The rate r = {depreciation_rate}% = {depreciation_rate/100}.\n3. The number of years n = {years}.\n4. Final Value = ${initial_amount}(1 - {depreciation_rate/100})^{{{years}}} = {initial_amount}({1-depreciation_rate/100})^{{{years}}} \\approx {final_value:.2f}$."
        options = {answer, f"GHS {initial_amount * (1 - (depreciation_rate*years)/100):.2f}"} # Simple interest depreciation
    
    return {"question": question, "options": _finalize_options(options), "answer": answer, "hint": hint, "explanation": explanation}


def _generate_word_problems_question():
    """Generates a multi-subtopic question for Word Problems with enhanced variety."""
    # UPGRADED: Expanded list of sub-topics based on your suggestions
    q_type = random.choice(['linear_number', 'age', 'consecutive_integers', 'ratio', 'work_rate'])
    question, answer, hint, explanation = "", "", "", ""
    options = set()

    if q_type == 'linear_number':
        x, k, m = random.randint(5, 20), random.randint(5, 20), random.randint(2, 5)
        result = m*x + k
        question = f"When {m} times a certain number is increased by {k}, the result is {result}. Find the number."
        answer = str(x)
        hint = "Let the number be 'n'. Translate the sentence into an equation and solve for n."
        explanation = f"1. Let the number be n. The equation is ${m}n + {k} = {result}$.\n2. Subtract {k}: ${m}n = {result-k}$.\n3. Divide by {m}: $n = \\frac{{{result-k}}}{{{m}}} = {x}$."
        options = {answer, str(result-k), str(result/m)}

    elif q_type == 'age':
        ama_age, kofi_age = random.randint(5, 15), random.randint(20, 40)
        while kofi_age - 2*ama_age <= 0: # Ensure a positive number of years
            ama_age, kofi_age = random.randint(5, 15), random.randint(20, 40)
        ans_val = kofi_age - 2*ama_age
        
        phrasing = random.choice([
            f"Ama is {ama_age} years old and her father Kofi is {kofi_age} years old. In how many years will Kofi be twice as old as Ama?",
            f"A mother in Accra is {kofi_age} and her son is {ama_age}. In how many years will the mother's age be double her son's age?"
        ])
        question = phrasing
        answer = str(ans_val)
        hint = "Let the number of years be 'x'. Set up an equation for their future ages: Father's Future Age = 2 * Child's Future Age."
        explanation = f"1. Let x be the number of years.\n2. In x years, their ages will be {ama_age}+x and {kofi_age}+x.\n3. Equation: ${kofi_age}+x = 2({ama_age}+x)$.\n4. Solve for x: ${kofi_age}+x = {2*ama_age}+2x \implies x = {kofi_age - 2*ama_age} = {ans_val}$."
        options = {answer, str(kofi_age - ama_age)}

    elif q_type == 'consecutive_integers':
        start, num = random.randint(10, 30), random.choice([2, 3])
        num_type = random.choice(['integers', 'even integers', 'odd integers'])
        if num_type == 'integers': integers = [start+i for i in range(num)]
        elif num_type == 'even integers': integers = [start*2, start*2+2, start*2+4][:num]
        else: integers = [start*2+1, start*2+3, start*2+5][:num]
        total = sum(integers)
        
        question = f"The sum of {num} consecutive {num_type} is {total}. What is the smallest of these integers?"
        answer = str(integers[0])
        hint = f"Represent the integers algebraically (e.g., n, n+2 for consecutive even integers). Set their sum equal to {total} and solve for n."
        explanation = f"1. Let the integers be n, n+2, ...\n2. Equation for the sum: {num}n + ... = {total}.\n3. Solving for n gives the first integer, which is {answer}."
        options = {answer, str(integers[-1]), str(int(total/num))}

    elif q_type == 'ratio':
        ratio1, ratio2 = random.randint(2, 5), random.randint(3, 7)
        total_amount = random.randint(10, 20) * (ratio1 + ratio2)
        share1 = int((ratio1 / (ratio1+ratio2)) * total_amount)
        share2 = total_amount - share1
        
        question = f"Two students, Yaw and Adwoa, share GHS {total_amount} in the ratio {ratio1}:{ratio2}. How much does Yaw, who gets the first share, receive?"
        answer = f"GHS {share1}"
        hint = "First, find the total number of parts in the ratio. Then, divide the total amount by the total parts to find the value of one part."
        explanation = f"1. Total parts in ratio = {ratio1} + {ratio2} = {ratio1+ratio2}.\n2. Value of one part = GHS {total_amount} / {ratio1+ratio2} = GHS {total_amount/(ratio1+ratio2)}.\n3. Yaw's share = {ratio1} parts = {ratio1} * {total_amount/(ratio1+ratio2)} = GHS {share1}."
        options = {answer, f"GHS {share2}"}
        
    elif q_type == 'work_rate':
        time_a = random.randint(3, 6) # Time for person A to do the job
        time_b = time_a * 2          # Time for person B is double
        # Rate of A = 1/time_a, Rate of B = 1/time_b. Combined rate = 1/a + 1/b = (a+b)/ab
        # Time together = 1 / combined_rate = ab / (a+b)
        time_together = (time_a * time_b) / (time_a + time_b)
        
        question = f"Worker A can complete a job in {time_a} hours. Worker B can complete the same job in {time_b} hours. How long would it take them to complete the job if they work together?"
        answer = f"{time_together:.2f} hours"
        hint = "First, find the rate of work for each person (jobs per hour). Then, add their rates together to find their combined rate."
        explanation = f"1. Rate of A = $\\frac{{1}}{{{time_a}}}$ jobs/hour.\n2. Rate of B = $\\frac{{1}}{{{time_b}}}$ jobs/hour.\n3. Combined Rate = $\\frac{{1}}{{{time_a}}} + \\frac{{1}}{{{time_b}}} = \\frac{{{time_b+time_a}}}{{{time_a*time_b}}}$ jobs/hour.\n4. Time Together = $\\frac{{1}}{{\\text{{Combined Rate}}}} = \\frac{{{time_a*time_b}}}{{{time_a+time_b}}} = {time_together:.2f}$ hours."
        options = {answer, f"{ (time_a+time_b)/2 :.2f} hours"}

    return {"question": question, "options": _finalize_options(options), "answer": answer, "hint": hint, "explanation": explanation}


def _generate_shapes_question():
    """Generates a multi-subtopic question for Shapes/Geometry with enhanced variety."""
    q_type = random.choice(['angles_lines', 'triangles_pythagoras', 'area_perimeter', 'volume_surface_area', 'circle_theorems'])
    question, answer, hint, explanation = "", "", "", ""
    options = set()

    if q_type == 'angles_lines':
        angle_type = random.choice(['point', 'straight_line', 'parallel'])
        if angle_type == 'point':
            a1, a2 = random.randint(100, 150), random.randint(80, 120)
            a3 = 360 - (a1 + a2)
            question = f"Three angles meet at a point. Two of the angles are {a1}° and {a2}°. What is the size of the third angle?"
            # CORRECTED: Added degree sign to answer and options
            answer = f"{a3}°"
            hint = "The sum of angles at a point is always 360°."
            explanation = f"Angles at a point add up to 360°. So, the third angle is $360 - ({a1} + {a2}) = 360 - {a1+a2} = {a3}°$."
            options = {answer, f"{180 - a1}°", f"{180 - a2}°"}
        else: # parallel lines
            angle1 = random.randint(50, 120)
            prop, angle2 = random.choice([("alternate", angle1), ("corresponding", angle1), ("co-interior", 180 - angle1)])
            question = f"In a diagram with two parallel lines cut by a transversal, one angle is {angle1}°. What is the size of its {prop} angle?"
            # CORRECTED: Added degree sign to answer and options
            answer = f"{angle2}°"
            hint = f"Recall the relationship between {prop} angles."
            explanation = f"For parallel lines:\n- Alternate angles are equal.\n- Corresponding angles are equal.\n- Co-interior angles sum to 180°.\nTherefore, the {prop} angle is {answer}."
            options = {answer, f"{180-angle1}°", f"{90-angle1}°"}

    elif q_type == 'triangles_pythagoras':
        a, b = random.choice([(3,4), (5,12), (8,15), (7,24), (9,40)])
        c = int(math.sqrt(a**2 + b**2))
        question = f"A right-angled triangle has shorter sides of length ${a}$ cm and ${b}$ cm. Find the length of its hypotenuse."
        answer = str(c)
        hint = "Use Pythagoras' theorem: $a^2 + b^2 = c^2$."
        explanation = f"1. By Pythagoras' theorem, $c^2 = a^2 + b^2$.\n2. $c^2 = {a}^2 + {b}^2 = {a**2} + {b**2} = {c**2}$.\n3. $c = \\sqrt{{{c**2}}} = {c}$ cm."
        options = {answer, str(a+b), str(abs(b-a))}

    elif q_type == 'area_perimeter':
        shape = random.choice(['rectangle', 'circle', 'trapezium'])
        if shape == 'rectangle':
            l, w = random.randint(10, 30), random.randint(5, 20)
            calc = random.choice(['area', 'perimeter'])
            question = f"A football field in Accra measures {l}m by {w}m. Calculate its {calc}."
            answer = str(l*w) if calc == 'area' else str(2*(l+w))
            hint = "Area of a rectangle is length × width. Perimeter is 2 × (length + width)."
            explanation = f"For a rectangle with length {l} and width {w}:\n- Area = ${l} \\times {w} = {l*w} m^2$.\n- Perimeter = $2({l} + {w}) = {2*(l+w)} m$."
            options = {str(l*w), str(2*(l+w))}
        elif shape == 'circle':
            r = random.randint(7, 21)
            question = f"Find the area of a circular garden with a radius of {r}m. (Use $\\pi \\approx 22/7$)"
            answer = str(int(Fraction(22,7) * r**2))
            hint = "Area of a circle = $\pi r^2$."
            explanation = f"Area = $\\pi r^2 = \\frac{{22}}{{7}} \\times {r}^2 = {answer} m^2$."
            options = {answer, str(int(2*Fraction(22,7)*r))}
        else: # trapezium
            a, b, h = random.randint(5, 10), random.randint(11, 20), random.randint(6, 12)
            question = f"A trapezium has parallel sides of length {a} cm and {b} cm, and a height of {h} cm. Find its area."
            answer = str(int(0.5 * (a+b) * h))
            hint = "Area of a trapezium = $\\frac{1}{2}(a+b)h$, where a and b are the parallel sides."
            explanation = f"Area = $\\frac{{1}}{{2}}({a} + {b}) \\times {h} = {answer} cm^2$."
            options = {answer, str((a+b)*h)}

    elif q_type == 'volume_surface_area':
        shape = random.choice(['cuboid', 'cylinder'])
        if shape == 'cuboid':
            l, w, h = random.randint(5,12), random.randint(5,12), random.randint(5,12)
            calc = random.choice(['volume', 'surface area'])
            question = f"A box has dimensions {l}cm by {w}cm by {h}cm. Find its total {calc}."
            answer = str(l*w*h) if calc == 'volume' else str(2*(l*w+w*h+l*h))
            hint = "Volume = l×w×h. Surface Area = 2(lw + wh + lh)."
            explanation = f"For the cuboid:\n- Volume = ${l} \\times {w} \\times {h} = {l*w*h} cm^3$.\n- Surface Area = $2({l*w} + {w*h} + {l*h}) = {2*(l*w+w*h+l*h)} cm^2$."
            options = {str(l*w*h), str(2*(l*w+w*h+l*h))}
        else: # cylinder
            r, h = 7, random.randint(10, 20) # Use r=7 for nice pi calculations
            question = f"A cylindrical tin of Milo has a radius of {r}cm and a height of {h}cm. Find its volume. (Use $\\pi \\approx 22/7$)"
            answer = str(int(Fraction(22,7) * r**2 * h))
            hint = "Volume of a cylinder = $\pi r^2 h$."
            explanation = f"Volume = $\\pi r^2 h = \\frac{{22}}{{7}} \\times {r}^2 \\times {h} = {answer} cm^3$."
            options = {answer, str(int(2*Fraction(22,7)*r*h))}

    elif q_type == 'circle_theorems':
        angle_at_center = random.randint(40, 120) * 2
        angle_at_circumference = angle_at_center // 2
        question = f"In a circle, an arc subtends an angle of {angle_at_center}° at the center. What angle does it subtend at any point on the remaining part of the circumference?"
        # CORRECTED: Added degree sign to answer and options
        answer = f"{angle_at_circumference}°"
        hint = "Recall the circle theorem: The angle at the center is twice the angle at the circumference."
        explanation = f"The angle at the circumference is half the angle at the center.\nAngle = $\\frac{{{angle_at_center}}}{{2}} = {angle_at_circumference}°$."
        options = {answer, f"{angle_at_center}°", f"{180-angle_at_center}°"}
        
    return {"question": question, "options": _finalize_options(options), "answer": answer, "hint": hint, "explanation": explanation}
def _generate_algebra_basics_question():
    """Generates a multi-subtopic question for Algebra Basics with enhanced variety."""
    # UPGRADED: Expanded list of sub-topics based on your suggestions
    q_type = random.choice(['simplify_expression', 'factorization', 'solve_linear', 'solve_simultaneous', 'solve_quadratic', 'solve_inequality', 'algebraic_fractions'])
    question, answer, hint, explanation = "", "", "", ""
    options = set()

    if q_type == 'simplify_expression':
        a, b, c, d = [random.randint(2, 8) for _ in range(4)]
        question = f"Expand and simplify the expression: ${a}(x + {b}) - {c}(x - {d})$"
        x_coeff = a - c
        const = a * b + c * d
        
        if x_coeff == 1: x_part = "x"
        elif x_coeff == -1: x_part = "-x"
        elif x_coeff == 0: x_part = ""
        else: x_part = f"{x_coeff}x"

        if const == 0 and x_part != "": answer = f"${x_part}$"
        elif const > 0: answer = f"${x_part} + {const}$" if x_part != "" else str(const)
        else: answer = f"${x_part} - {abs(const)}$" if x_part != "" else str(const)
            
        hint = "First, expand both brackets by multiplying. Then, be careful with the signs and collect like terms."
        explanation = f"1. Expand brackets: $({a}x + {a*b}) - ({c}x - {c*d})$.\n2. Simplify: ${a}x + {a*b} - {c}x + {c*d}$.\n3. Collect terms: $({a-c})x + ({a*b+c*d}) = {x_coeff}x + {const}$."
        options = {answer, f"${a+c}x + {a*b-c*d}$"}

    elif q_type == 'factorization':
        factor_type = random.choice(['diff_squares', 'trinomial'])
        if factor_type == 'diff_squares':
            a, b_val = random.randint(2, 10), random.randint(2, 5)
            b = f"{b_val}y"
            question = f"Factorize completely: ${a**2}x^2 - {b_val**2}y^2$"
            answer = f"$({a}x - {b})({a}x + {b})$"
            hint = "Recognize this as a difference of two squares: $A^2 - B^2 = (A-B)(A+B)$."
            explanation = f"Here, $A^2 = {a**2}x^2$ so $A={a}x$, and $B^2 = {b_val**2}y^2$ so $B={b}$.\nThe factorization is $(A-B)(A+B)$, which gives ${answer}$."
            options = {answer, f"$({a}x - {b})^2$"}
        else: # trinomial
            r1, r2 = random.randint(-7, 7), random.randint(-7, 7)
            while r1 == 0 or r2 == 0 or r1==r2: r1, r2 = random.randint(-7, 7), random.randint(-7, 7)
            b, c = r1 + r2, r1 * r2
            question = f"Factorize the trinomial: $x^2 + ({b})x + ({c})$"
            answer = f"$(x {'+' if r1 > 0 else '-'} {abs(r1)})(x {'+' if r2 > 0 else '-'} {abs(r2)})$"
            hint = f"Look for two numbers that multiply to {c} and add to {b}."
            explanation = f"The two numbers are ${r1}$ and ${r2}$, since ${r1} \\times {r2} = {c}$ and ${r1} + {r2} = {b}$.\nTherefore, the factors are $(x + ({r1}))(x + ({r2}))$, which is ${answer}$."
            options = {answer, f"$(x - {r1})(x - {r2})$"}

    elif q_type == 'solve_linear':
        a, b, x = random.randint(2, 8), random.randint(5, 20), random.randint(2, 10)
        c = a * x + b
        question = f"Solve for x in the equation: ${a}x + {b} = {c}$"
        answer = str(x)
        hint = "Isolate the term with 'x' on one side of the equation, then divide to find x."
        explanation = f"1. Equation: ${a}x + {b} = {c}$.\n2. Subtract {b} from both sides: ${a}x = {c-b}$.\n3. Divide by {a}: $x = \\frac{{{c-b}}}{{{a}}} = {x}$."
        options = {answer, str(c-b), str((c+b)/a)}
        
    elif q_type == 'solve_simultaneous':
        x, y = random.randint(1, 8), random.randint(1, 8)
        a1, b1, a2, b2 = [random.randint(1, 4) for _ in range(4)]
        while a1*b2 - a2*b1 == 0: a2, b2 = random.randint(1, 4), random.randint(1, 4)
        c1 = a1*x + b1*y
        c2 = a2*x + b2*y
        question = f"Solve the following system of linear equations:\n\n$ {a1}x + {b1}y = {c1} $\n\n$ {a2}x + {b2}y = {c2} $"
        answer = f"x = {x}, y = {y}"
        hint = "Use either the substitution or elimination method to solve for one variable first."
        explanation = f"Using the elimination method, one can solve to find that y = {y}. Substituting this value back into the first equation gives x = {x}."
        options = {answer, f"x = {y}, y = {x}", f"x = {c1-c2}, y = {c1+c2}"}
        
    elif q_type == 'solve_quadratic':
        r1, r2 = random.randint(-6, 6), random.randint(-6, 6)
        while r1 == 0 or r2 == 0 or r1 == r2: r1, r2 = random.randint(-6, 6), random.randint(-6, 6)
        b = -(r1 + r2)
        c = r1 * r2
        question = f"Find the roots of the quadratic equation: $x^2 + {b}x + {c} = 0$"
        answer = f"x = {r1} or x = {r2}"
        hint = "Solve by factorizing the quadratic expression or using the quadratic formula."
        explanation = f"This equation can be factorized by finding two numbers that multiply to {c} and add to {b}. These numbers are {-r1} and {-r2}.\nSo, $(x - {r1})(x - {r2}) = 0$.\nThe solutions are $x = {r1}$ and $x = {r2}$."
        options = {answer, f"x = {-r1} or x = {-r2}"}

    elif q_type == 'solve_inequality':
        a, b, x = random.randint(2, 5), random.randint(10, 20), random.randint(3, 8)
        c = a*x - b
        question = f"Find the solution to the inequality: ${a}x - {b} > {c}$"
        answer = f"$x > {x}$"
        hint = "Solve this just like a linear equation. Only flip the inequality sign if you multiply or divide by a negative number."
        explanation = f"1. Inequality: ${a}x - {b} > {c}$.\n2. Add {b} to both sides: ${a}x > {c+b}$.\n3. Divide by {a}: $x > \\frac{{{c+b}}}{{{a}}} = {x}$."
        options = {answer, f"$x < {x}$", f"$x > {c-b}"}
        
    elif q_type == 'algebraic_fractions':
        a, b = random.randint(2, 5), random.randint(3, 6)
        question = f"Simplify the algebraic fraction: $\\frac{{x}}{{{a}}} + \\frac{{x}}{{{b}}}$"
        num = a + b; den = a * b; common = math.gcd(num, den); num //= common; den //= common
        answer = f"$\\frac{{{num}x}}{{{den}}}$"
        hint = "To add algebraic fractions, find a common denominator, just like with regular fractions."
        explanation = f"1. The lowest common multiple of {a} and {b} is {a*b}.\n2. $\\frac{{x}}{{{a}}} + \\frac{{x}}{{{b}}} = \\frac{{{b}x}}{{{a*b}}} + \\frac{{{a}x}}{{{a*b}}}$.\n3. Combine and simplify: $\\frac{{({a+b})x}}{{{a*b}}} = {answer}$."
        options = {answer, f"$\\frac{{2x}}{{{a+b}}}$", f"$\\frac{{x^2}}{{{a*b}}}$"}

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
    # This dictionary of all 18 generators remains the same
    generators = {
        "Sets": _generate_sets_question, "Percentages": _generate_percentages_question,
        "Fractions": _generate_fractions_question, "Indices": _generate_indices_question,
        "Surds": _generate_surds_question, "Binary Operations": _generate_binary_ops_question,
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
    
    generator_func = generators.get(topic)
    if not generator_func:
        return {"question": f"Questions for **{topic}** are coming soon!", "options": ["OK"], "answer": "OK", "hint": "Under development."}

    # --- NEW LOGIC TO PREVENT REPEATS ---
    seen_ids = get_seen_questions(st.session_state.username)
    
    # Try up to 10 times to find a new question to avoid an infinite loop
    for _ in range(10):
        # 1. Generate a candidate question
        candidate_question = generator_func()
        
        # For multi-part, the stem is the unique identifier
        question_text = candidate_question.get("stem", candidate_question.get("question", ""))
        
        # 2. Create its unique ID
        q_id = get_question_id(question_text)
        
        # 3. Check if it has been seen
        if q_id not in seen_ids:
            # 4. If not seen, save it and return it
            save_seen_question(st.session_state.username, q_id)
            return candidate_question
    
    # If we fail to find a new question after 10 tries, return a fallback message
    return {"question": "Wow! You've seen a lot of questions. We're digging deep for a new one...", "options": ["OK"], "answer": "OK", "hint": "Generating a fresh challenge!"}
        

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
        /* --- FINAL, ROBUST SCROLLING FIX FOR ALL DEVICES --- */
        /* This targets the main view container, locks it to the screen size,
           and makes it the primary scrollable element. This is a more
           powerful approach that should override other conflicting styles. */
        div[data-testid="stAppViewContainer"] {
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            overflow-y: auto;
        }
        
        /* --- BASE STYLES & OTHER RULES --- */
        .stApp { background-color: #f0f2ff; }
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
                    
                    if is_multi:
                        part_index = st.session_state.current_part_index
                        is_last_part = (part_index + 1 == len(q_data["parts"]))
                        
                        if part_index == 0:
                            st.session_state.questions_attempted += 1
                            st.session_state.multi_part_correct = True 
                        
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
        if is_correct:
            st.success(f"**{user_choice}** (Correct!)")
            # --- THIS IS THE NEW LOGIC ---
            # Celebrate when the streak hits 3, 5, or any multiple of 5
            if st.session_state.current_streak in [3, 5] or (st.session_state.current_streak > 5 and st.session_state.current_streak % 5 == 0):
                st.balloons()
        else:
            st.error(f"**{user_choice}** (Incorrect)")
            st.info(f"The correct answer was: **{actual_answer}**")

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
    # ADD THIS BLOCK
    st.subheader("🏆 My Achievements")
    achievements = get_user_achievements(st.session_state.username)
    if not achievements:
        st.info("Your trophy case is empty for now. Keep playing to earn badges!")
    else:
        # Create a grid layout for the badges
        cols = st.columns(4)
        for i, achievement in enumerate(achievements):
            col = cols[i % 4]
            with col:
                with st.container(border=True):
                    st.markdown(f"<div style='font-size: 3rem; text-align: center;'>{achievement['badge_icon']}</div>", unsafe_allow_html=True)
                    st.markdown(f"<div style='font-size: 1rem; text-align: center; font-weight: bold;'>{achievement['achievement_name']}</div>", unsafe_allow_html=True)
                    st.markdown(f"<div style='font-size: 0.8rem; text-align: center; color: grey;'>Unlocked: {achievement['unlocked_at'].strftime('%b %d, %Y')}</div>", unsafe_allow_html=True)
    
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
    
    # --- ADDED: Notification Handler for Both Features ---
    # This checks for the daily challenge flag and shows a toast if it's set
    if st.session_state.get('challenge_completed_toast', False):
        st.toast("🎉 Daily Challenge Completed! Great job!", icon="🎉")
        del st.session_state.challenge_completed_toast # Reset the flag

    # This checks for the new achievement flag and shows a toast and balloons if it's set
    if st.session_state.get('achievement_unlocked_toast', False):
        achievement_name = st.session_state.achievement_unlocked_toast
        st.toast(f"🏆 Achievement Unlocked: {achievement_name}!", icon="🏆")
        st.balloons()
        del st.session_state.achievement_unlocked_toast # Reset the flag

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
            # ADDED: Ensure achievement flag is cleared on logout
            if 'challenge_completed_toast' in st.session_state: del st.session_state.challenge_completed_toast
            if 'achievement_unlocked_toast' in st.session_state: del st.session_state.achievement_unlocked_toast
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
                    
                    # --- THIS IS THE NEW LINE YOU REQUESTED ---
                    st.toast(f"Welcome back, {username}! Ready to solve some math today?", icon="🎉")
                    
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
































































