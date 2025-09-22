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
import json
from streamlit_autorefresh import st_autorefresh
from dateutil import parser
from datetime import date, timedelta

# --- START: ADD THIS NEW BLOCK ---
# --- Global Game Constants ---
QUIZ_LENGTH = 10
WASSCE_QUIZ_LENGTH = 40
# --- END: ADD THIS NEW BLOCK ---

# --- App Configuration ---
st.set_page_config(
    layout="wide",
    page_title="MathFriend",
    page_icon="🧮",
    initial_sidebar_state="expanded"
)

# --- CORRECT LOCATION FOR THE DICTIONARY ---
# It is now outside and above any function
# Replace your current dictionary with this one
COSMETIC_ITEMS = {
    'Quiz Perks': {
        'hint_token': {'name': '💡 Hint Token', 'cost': 50, 'db_column': 'hint_tokens'},
        'fifty_fifty_lifeline': {'name': '🔀 50/50 Lifeline', 'cost': 100, 'db_column': 'fifty_fifty_tokens'},
        'skip_question_token': {'name': '↪️ Skip Question Token', 'cost': 150, 'db_column': 'skip_question_tokens'},
    },
    'Boosters': {
        'double_coins_booster': {'name': '🚀 Double Coins (1 Hr)', 'cost': 300, 'db_column': 'double_coins_expires_at'},
        'mystery_box': {'name': '🎁 Mystery Box', 'cost': 400, 'db_column': 'mystery_boxes'},
    },
    'Borders': {
        'bronze_border': {'name': '🥉 Bronze Border', 'cost': 500},
        'silver_border': {'name': '🥈 Silver Border', 'cost': 1200},
        'gold_border': {'name': '🥇 Golden Border', 'cost': 2500},
        'rainbow_border': {'name': '🌈 Rainbow Border', 'cost': 6000},
    },
    'Name Effects': {
        'bold_effect': {'name': 'Bold Name', 'cost': 400},
        'italic_effect': {'name': 'Italic Name', 'cost': 400},
    }
}

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
        "on_summary_page": False,
        # --- START: ADD THESE TWO NEW LINES ---
        "is_wassce_mode": False
        # --- END: ADD THESE TWO NEW LINES ---
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

@st.cache_resource
def get_supabase_client():
    """Initializes the Supabase client for file storage using the admin key."""
    from supabase import create_client
    url = st.secrets["SUPABASE_URL"]
    # --- THIS IS THE FIX ---
    # We now use the powerful service_role key to bypass RLS for storage operations.
    key = st.secrets["SUPABASE_SERVICE_KEY"]
    return create_client(url, key)

supabase_client = get_supabase_client()

def create_and_verify_tables():
    """Creates, verifies, and populates necessary database tables."""
    try:
        with engine.connect() as conn:

            # --- Standard Tables ---
            conn.execute(text('''CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, password TEXT)'''))
            conn.execute(text('''ALTER TABLE users ADD COLUMN IF NOT EXISTS role TEXT DEFAULT 'student' '''))
            conn.execute(text('''ALTER TABLE users ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE '''))
            conn.execute(text('''CREATE TABLE IF NOT EXISTS user_skill_levels (
                                username TEXT NOT NULL,
                                topic TEXT NOT NULL,
                                skill_score INTEGER DEFAULT 50,
                                PRIMARY KEY (username, topic)
                            )'''))
            conn.execute(text('''CREATE TABLE IF NOT EXISTS quiz_results
                         (id SERIAL PRIMARY KEY, username TEXT, topic TEXT, score INTEGER,
                          questions_answered INTEGER, timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP)'''))
            conn.execute(text('''CREATE TABLE IF NOT EXISTS user_profiles
                         (username TEXT PRIMARY KEY, full_name TEXT, school TEXT, age INTEGER, bio TEXT)'''))
            conn.execute(text('''ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS coins INTEGER DEFAULT 100'''))
            conn.execute(text('''CREATE TABLE IF NOT EXISTS coin_transactions (
                                id SERIAL PRIMARY KEY,
                                username TEXT NOT NULL,
                                amount INTEGER NOT NULL,
                                description TEXT,
                                timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                            )'''))
            conn.execute(text('''CREATE TABLE IF NOT EXISTS user_status
                         (username TEXT PRIMARY KEY, is_online BOOLEAN, last_seen TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP)'''))
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
            conn.execute(text('''CREATE TABLE IF NOT EXISTS seen_questions (
                                id SERIAL PRIMARY KEY,
                                username TEXT NOT NULL,
                                question_id TEXT NOT NULL,
                                seen_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                                UNIQUE (username, question_id)
                            )'''))
            conn.execute(text('''CREATE TABLE IF NOT EXISTS user_achievements (
                                id SERIAL PRIMARY KEY,
                                username TEXT NOT NULL,
                                achievement_name TEXT NOT NULL,
                                badge_icon TEXT,
                                unlocked_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                            )'''))
            conn.execute(text('''CREATE TABLE IF NOT EXISTS app_config (
                                config_key TEXT PRIMARY KEY,
                                config_value TEXT
                            )'''))
            conn.execute(text('''CREATE TABLE IF NOT EXISTS learning_resources (
                                topic TEXT PRIMARY KEY,
                                content TEXT
                            )'''))
            # --- Head-to-Head Duel Tables ---
            # ... (the rest of the function is the same, no need to copy it here)
            conn.execute(text('''
                CREATE TABLE IF NOT EXISTS duels (
                    id SERIAL PRIMARY KEY,
                    player1_username TEXT NOT NULL,
                    player2_username TEXT NOT NULL,
                    topic TEXT NOT NULL,
                    status TEXT NOT NULL,
                    player1_score INTEGER DEFAULT 0,
                    player2_score INTEGER DEFAULT 0,
                    current_question_index INTEGER DEFAULT 0,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    last_action_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    finished_at TIMESTAMP WITH TIME ZONE
                )
            '''))
            conn.execute(text('''
                CREATE TABLE IF NOT EXISTS duel_questions (
                    id SERIAL PRIMARY KEY,
                    duel_id INTEGER REFERENCES duels(id) ON DELETE CASCADE,
                    question_index INTEGER NOT NULL,
                    question_data_json TEXT NOT NULL,
                    answered_by TEXT,
                    is_correct BOOLEAN,
                    UNIQUE(duel_id, question_index)
                )
            '''))
            result = conn.execute(text("SELECT COUNT(*) FROM daily_challenges")).scalar_one()
            if result == 0:
                print("Populating daily_challenges table for the first time.")
                challenges = [
                    ("Answer 5 questions correctly on any topic.", "Any", 5), ("Complete any quiz with a score of 4 or more.", "Any", 4),
                    ("Correctly answer 4 Set theory questions.", "Sets", 4), ("Get 3 correct answers in a Percentages quiz.", "Percentages", 3),
                    ("Solve 4 problems involving Fractions.", "Fractions", 4), ("Simplify 3 expressions using the laws of Indices.", "Indices", 3),
                    ("Get 3 correct answers in a Surds quiz.", "Surds", 3), ("Evaluate 3 Binary Operations correctly.", "Binary Operations", 3),
                    ("Answer 4 questions on Relations and Functions.", "Relations and Functions", 4), ("Solve 3 problems on Sequence and Series.", "Sequence and Series", 3),
                    ("Solve 2 math Word Problems.", "Word Problems", 2), ("Answer 4 questions about Shapes (Geometry).", "Shapes (Geometry)", 4),
                    ("Get 5 correct answers in Algebra Basics.", "Algebra Basics", 5), ("Solve 3 problems in Linear Algebra.", "Linear Algebra", 3),
                    ("Solve 3 logarithmic equations.", "Logarithms", 3), ("Correctly answer 4 probability questions.", "Probability", 4),
                    ("Find the coefficient in 2 binomial expansions.", "Binomial Theorem", 2), ("Use the Remainder Theorem twice.", "Polynomial Functions", 2),
                    ("Solve 3 trigonometric equations.", "Trigonometry", 3), ("Calculate the magnitude of 4 vectors.", "Vectors", 4),
                    ("Solve 4 problems correctly in Statistics.", "Statistics", 4), ("Find the distance between two points 3 times.", "Coordinate Geometry", 3),
                    ("Find the derivative of 3 functions.", "Introduction to Calculus", 3), ("Convert 4 numbers to a different base.", "Number Bases", 4),
                    ("Solve 3 modulo arithmetic problems.", "Modulo Arithmetic", 3),
                ]
                conn.execute(text("INSERT INTO daily_challenges (description, topic, target_count) VALUES (:description, :topic, :target_count)"), 
                             [{"description": d, "topic": t, "target_count": c} for d, t, c in challenges])
            conn.commit()
        print("Database tables created or verified successfully, including corrected Duel tables.")
    except Exception as e:
        st.error(f"Database setup error: {e}")
#create_and_verify_tables()


# --- Core Backend Functions (PostgreSQL) ---
def hash_password(password):
    salt = "mathfriend_static_salt_for_performance"
    salted_password = password + salt
    return hashlib.sha256(salted_password.encode()).hexdigest()

def check_password(hashed_password, user_password):
    return hashed_password == hash_password(user_password)

# --- START: ADD THIS NEW FUNCTION ---
def load_quiz_state(username):
    """Loads an active quiz session from the database if it's less than 8 hours old."""
    with engine.connect() as conn:
        # This query fetches the session data only if it was updated in the last 8 hours.
        query = text("""
            SELECT session_data FROM public.quiz_sessions
            WHERE username = :username AND last_updated > NOW() - INTERVAL '8 hours'
        """)
        result = conn.execute(query, {"username": username}).scalar_one_or_none()

        if result:
            try:
                # The data from the database is loaded into the session state.
                # The .update() method adds all key-value pairs from the loaded data.
                loaded_data = json.loads(result) if isinstance(result, str) else result
                st.session_state.update(loaded_data)
                return True  # Indicates a session was successfully loaded.
            except (json.JSONDecodeError, TypeError):
                # If data is corrupted for any reason, we should not load it.
                return False
    return False # No recent session was found.
# --- END: ADD THIS NEW FUNCTION ---

# Replace your previous save_quiz_state function with this corrected version
def save_quiz_state(username):
    """Gathers the current quiz state and saves it to the database as a JSON object."""
    state_to_save = {
        "quiz_active": st.session_state.get("quiz_active", False),
        "quiz_topic": st.session_state.get("quiz_topic"),
        "quiz_score": st.session_state.get("quiz_score", 0),
        "questions_answered": st.session_state.get("questions_answered", 0),
        "questions_attempted": st.session_state.get("questions_attempted", 0),
        "current_streak": st.session_state.get("current_streak", 0),
        "incorrect_questions": st.session_state.get("incorrect_questions", []),
        "is_wassce_mode": st.session_state.get("is_wassce_mode", False),
        "current_q_data": st.session_state.get("current_q_data"),
        "all_wassce_questions": st.session_state.get("all_wassce_questions", []),
        "hint_revealed": st.session_state.get("hint_revealed", False),
        "fifty_fifty_used": st.session_state.get("fifty_fifty_used", False),
        "answer_submitted": st.session_state.get("answer_submitted", False),
        "user_choice": st.session_state.get("user_choice")
    }

    # This makes the JSON conversion more robust by turning any non-standard objects into strings.
    session_data_json = json.dumps(state_to_save, default=str)

    with engine.connect() as conn:
        # --- THIS QUERY HAS BEEN CORRECTED ---
        # The '::jsonb' cast has been removed to let SQLAlchemy handle the type conversion,
        # which is more reliable across different database drivers.
        query = text("""
            INSERT INTO public.quiz_sessions (username, session_data, last_updated)
            VALUES (:username, :session_data, NOW())
            ON CONFLICT (username) DO UPDATE SET
                session_data = EXCLUDED.session_data,
                last_updated = NOW();
        """)
        conn.execute(query, {"username": username, "session_data": session_data_json})
        conn.commit()
# --- START: ADD THIS NEW FUNCTION ---
def clear_quiz_state(username):
    """Deletes a user's saved quiz session from the database upon completion."""
    try:
        with engine.connect() as conn:
            query = text("DELETE FROM public.quiz_sessions WHERE username = :username")
            conn.execute(query, {"username": username})
            conn.commit()
    except Exception as e:
        # Log the error but don't crash the app if the clear fails.
        print(f"Error clearing quiz state for {username}: {e}")
# --- END: ADD THIS NEW FUNCTION ---

# --- END: ADD THIS NEW FUNCTION ---

# Replace your existing login_user function with this one
def login_user(username, password):
    with engine.connect() as conn:
        # --- MODIFIED: Now checks if the user is active ---
        query = text("SELECT password, is_active FROM public.users WHERE username = :username")
        record = conn.execute(query, {"username": username}).first()
        
        if record and record[1] is False: # record[1] is the is_active column
            st.error("This account has been suspended.")
            return False

        if record and check_password(record[0], password):
            # --- START: THIS IS THE NEW CODE BLOCK TO ADD INSIDE THE FUNCTION ---
            # After a successful login, we attempt to load a previous quiz session.
            if load_quiz_state(username):
                st.toast("🚀 Your previous quiz session has been restored!", icon="✅")
            # --- END: NEW CODE BLOCK TO ADD INSIDE THE FUNCTION ---
            profile = get_user_profile(username)
            display_name = profile.get('full_name') if profile and profile.get('full_name') else username
            chat_client.upsert_user({"id": username, "name": display_name})
            return True
            
        return False

def signup_user(username, password):
    try:
        with engine.connect() as conn:
            # This starts a transaction to ensure both actions succeed or fail together
            with conn.begin():
                # Action 1: Create the user's login credentials
                conn.execute(text("INSERT INTO users (username, password) VALUES (:username, :password)"), 
                             {"username": username, "password": hash_password(password)})
                
                # Action 2 (THE FIX): Create the user's profile at the same time
                conn.execute(text("INSERT INTO user_profiles (username, coins) VALUES (:username, 100)"),
                             {"username": username})

            # The transaction is committed here
            chat_client.upsert_user({"id": username, "name": username})
        return True
    except sqlalchemy.exc.IntegrityError:
        # This will catch if the username already exists
        return False

def get_user_profile(username):
    with engine.connect() as conn:
        result = conn.execute(text("SELECT * FROM user_profiles WHERE username = :username"), {"username": username})
        profile = result.mappings().first()
        return dict(profile) if profile else None

def get_coin_balance(username):
    """Fetches a user's current coin balance from their profile."""
    with engine.connect() as conn:
        query = text("SELECT coins FROM user_profiles WHERE username = :username")
        result = conn.execute(query, {"username": username}).scalar_one_or_none()
        return result if result is not None else 0

def get_user_transactions(username):
    """Fetches all coin transactions for a given user, ordered by most recent."""
    with engine.connect() as conn:
        query = text("""
            SELECT timestamp, amount, description 
            FROM coin_transactions 
            WHERE username = :username 
            ORDER BY timestamp DESC
        """)
        result = conn.execute(query, {"username": username}).mappings().fetchall()
        return [dict(row) for row in result]

def get_user_role(username):
    """Fetches the role of a user from the database."""
    with engine.connect() as conn:
        query = text("SELECT role FROM public.users WHERE username = :username")
        result = conn.execute(query, {"username": username}).scalar_one_or_none()
        return result

# --- NEW ADMIN BACKEND FUNCTIONS ---
# --- START: NEW FUNCTIONS for Content Management ---
# Reason for change: To add backend logic for reading and updating the learning resources from the database.

def get_learning_content(topic):
    """Fetches the learning content for a specific topic from the database."""
    with engine.connect() as conn:
        query = text("SELECT content FROM learning_resources WHERE topic = :topic")
        result = conn.execute(query, {"topic": topic}).scalar_one_or_none()
        return result if result else "No content available for this topic yet. The admin can add it in the Content Management panel."

def update_learning_content(topic, new_content):
    """Updates or inserts learning content for a topic in the database."""
    with engine.connect() as conn:
        query = text("""
            INSERT INTO learning_resources (topic, content)
            VALUES (:topic, :content)
            ON CONFLICT (topic) DO UPDATE SET
                content = EXCLUDED.content;
        """)
        conn.execute(query, {"topic": topic, "content": new_content})
        conn.commit()
    st.cache_data.clear() # Clear the cache to ensure users see the new content

# --- END: NEW FUNCTIONS for Content Management ---
# --- START: REVISED FUNCTION get_all_users_summary ---
# Reason for change: To gather more comprehensive data for the new admin overview table,
# including each user's coin balance and their overall average quiz accuracy.

def get_all_users_summary():
    """Fetches a comprehensive summary of all users for the admin panel."""
    with engine.connect() as conn:
        # This query is now enhanced to join with user_profiles to get coins,
        # and to calculate average accuracy from the quiz_results table.
        query = text("""
            SELECT 
                u.username,
                u.is_active,
                p.full_name,
                p.school,
                COALESCE(p.coins, 0) as coins,
                (SELECT COUNT(*) FROM quiz_results qr WHERE qr.username = u.username) as quizzes_taken,
                (SELECT AVG(CASE WHEN qr.questions_answered > 0 THEN (qr.score * 100.0 / qr.questions_answered) ELSE 0 END) FROM quiz_results qr WHERE qr.username = u.username) as average_accuracy,
                (SELECT last_seen FROM user_status us WHERE us.username = u.username) as last_seen
            FROM users u
            LEFT JOIN user_profiles p ON u.username = p.username
            ORDER BY u.username ASC;
        """)
        result = conn.execute(query).mappings().fetchall()
        return [dict(row) for row in result]

# --- END: REVISED FUNCTION get_all_users_summary ---

def get_all_achievements():
    """Returns a list of all possible achievement names."""
    # In a more advanced system, this could come from a database table.
    # For now, we can hard-code them based on the check_and_award_achievements function.
    
    # --- NOTE: This list must be manually kept in sync with your achievement logic ---
    base_achievements = ["First Step", "Century Scorer"]
    topic_masters = [f"{topic} Master" for topic in [
        "Sets", "Percentages", "Fractions", "Indices", "Surds", "Binary Operations",
        "Relations and Functions", "Sequence and Series", "Word Problems", "Shapes (Geometry)",
        "Algebra Basics", "Linear Algebra", "Logarithms", "Probability", "Binomial Theorem",
        "Polynomial Functions", "Trigonometry", "Vectors", "Statistics", "Coordinate Geometry",
        "Introduction to Calculus", "Number Bases", "Modulo Arithmetic"
    ]]
    return sorted(base_achievements + topic_masters)

def award_achievement_to_user(username, achievement_name, badge_icon):
    """Manually inserts an achievement for a user, avoiding duplicates."""
    with engine.connect() as conn:
        # First, check if the user already has this achievement
        check_query = text("""
            SELECT 1 FROM user_achievements 
            WHERE username = :username AND achievement_name = :achievement_name
        """)
        exists = conn.execute(check_query, {"username": username, "achievement_name": achievement_name}).first()
        
        if not exists:
            insert_query = text("""
                INSERT INTO user_achievements (username, achievement_name, badge_icon)
                VALUES (:username, :achievement_name, :badge_icon)
            """)
            conn.execute(insert_query, {
                "username": username,
                "achievement_name": achievement_name,
                "badge_icon": badge_icon
            })
            conn.commit()
            return True # Indicates success
        return False # Indicates user already had it

# --- NEW ADMIN BACKEND FUNCTIONS FOR GAME MANAGEMENT ---

def get_all_active_duels_admin():
    """Fetches all duels with 'active' status for the admin panel."""
    with engine.connect() as conn:
        query = text("""
            SELECT id, player1_username, player2_username, topic, player1_score, player2_score, last_action_at
            FROM duels
            WHERE status = 'active'
            ORDER BY last_action_at ASC
        """)
        result = conn.execute(query).mappings().fetchall()
        return [dict(row) for row in result]

def force_end_duel_admin(duel_id):
    """Allows an admin to forcefully end a duel by setting its status to 'expired'."""
    with engine.connect() as conn:
        query = text("""
            UPDATE duels
            SET status = 'expired', finished_at = CURRENT_TIMESTAMP
            WHERE id = :id AND status = 'active'
        """)
        conn.execute(query, {"id": duel_id})
        conn.commit()

# --- END OF GAME MANAGEMENT FUNCTIONS ---

# --- NEW ADMIN BACKEND FUNCTIONS FOR CHALLENGES ---

def get_all_challenges_admin():
    """Fetches all daily challenges from the database for the admin panel."""
    with engine.connect() as conn:
        query = text("SELECT id, description, topic, target_count FROM daily_challenges ORDER BY id ASC")
        result = conn.execute(query).mappings().fetchall()
        return [dict(row) for row in result]

def add_new_challenge(description, topic, target_count):
    """Adds a new daily challenge to the database."""
    with engine.connect() as conn:
        query = text("""
            INSERT INTO daily_challenges (description, topic, target_count)
            VALUES (:desc, :topic, :target)
        """)
        conn.execute(query, {"desc": description, "topic": topic, "target": target_count})
        conn.commit()

def update_challenge(challenge_id, description, topic, target_count):
    """Updates an existing daily challenge."""
    with engine.connect() as conn:
        query = text("""
            UPDATE daily_challenges
            SET description = :desc, topic = :topic, target_count = :target
            WHERE id = :id
        """)
        conn.execute(query, {
            "id": challenge_id,
            "desc": description,
            "topic": topic,
            "target": target_count
        })
        conn.commit()

def delete_challenge(challenge_id):
    """Deletes a daily challenge from the database."""
    with engine.connect() as conn:
        query = text("DELETE FROM daily_challenges WHERE id = :id")
        conn.execute(query, {"id": challenge_id})
        conn.commit()

# --- NEW ADMIN BACKEND FUNCTIONS FOR ANALYTICS ---

def get_admin_kpis():
    """Fetches key performance indicators for the admin dashboard."""
    with engine.connect() as conn:
        total_users = conn.execute(text("SELECT COUNT(*) FROM public.users")).scalar_one()
        total_quizzes = conn.execute(text("SELECT COUNT(*) FROM quiz_results")).scalar_one()
        total_duels = conn.execute(text("SELECT COUNT(*) FROM duels WHERE status != 'pending'")).scalar_one()
        return {
            "total_users": total_users,
            "total_quizzes": total_quizzes,
            "total_duels": total_duels
        }

def get_topic_popularity():
    """Fetches the count of quizzes taken per topic."""
    with engine.connect() as conn:
        query = text("""
            SELECT topic, COUNT(*) as quizzes_taken
            FROM quiz_results
            GROUP BY topic
            ORDER BY quizzes_taken DESC;
        """)
        result = conn.execute(query).mappings().fetchall()
        return [dict(row) for row in result]

def get_performance_over_time():
    """Fetches the average quiz accuracy per day."""
    with engine.connect() as conn:
        query = text("""
            SELECT 
                DATE_TRUNC('day', timestamp) as date,
                AVG(CASE WHEN questions_answered > 0 THEN (score * 100.0 / questions_answered) ELSE 0 END) as average_accuracy
            FROM quiz_results
            GROUP BY DATE_TRUNC('day', timestamp)
            ORDER BY date ASC;
        """)
        result = conn.execute(query).mappings().fetchall()
        return [dict(row) for row in result]

# --- NEW BACKEND FUNCTIONS FOR APP CONFIG ---

def get_config_value(key, default=None):
    """Fetches a specific configuration value from the app_config table."""
    with engine.connect() as conn:
        query = text("SELECT config_value FROM app_config WHERE config_key = :key")
        result = conn.execute(query, {"key": key}).scalar_one_or_none()
        return result if result else default

def set_config_value(key, value):
    """Inserts or updates a configuration value in the app_config table."""
    with engine.connect() as conn:
        query = text("""
            INSERT INTO app_config (config_key, config_value)
            VALUES (:key, :value)
            ON CONFLICT (config_key) DO UPDATE SET
                config_value = EXCLUDED.config_value;
        """)
        conn.execute(query, {"key": key, "value": value})
        conn.commit()

# --- END OF NEW BACKEND FUNCTIONS ---

# --- NEW ADMIN BACKEND FUNCTION FOR DELETING USERS ---

def delete_user_and_all_data(username):
    """Deletes a user and all of their associated data across all tables."""
    with engine.connect() as conn:
        with conn.begin():  # Start a transaction
            # Anonymize duel records instead of deleting them to preserve game history
            conn.execute(text("UPDATE duels SET player1_username = 'deleted_user' WHERE player1_username = :u"), {"u": username})
            conn.execute(text("UPDATE duels SET player2_username = 'deleted_user' WHERE player2_username = :u"), {"u": username})
            conn.execute(text("UPDATE duel_questions SET answered_by = 'deleted_user' WHERE answered_by = :u"), {"u": username})

            # Delete from all other tables
            tables_to_delete_from = [
                "user_achievements", "seen_questions", "user_daily_progress",
                "user_status", "user_profiles", "quiz_results", "public.users"
            ]
            for table in tables_to_delete_from:
                # Note: We use public.users to be specific
                conn.execute(text(f"DELETE FROM {table} WHERE username = :username"), {"username": username})
        # The transaction is automatically committed here if no errors occurred
    return True

# --- END OF USER DELETION FUNCTION ---

# --- NEW ADVANCED ANALYTICS BACKEND FUNCTIONS ---

def get_topic_performance_summary():
    """Calculates the overall average accuracy for each topic across all students."""
    with engine.connect() as conn:
        query = text("""
            SELECT 
                topic, 
                AVG(CASE WHEN questions_answered > 0 THEN (score * 100.0 / questions_answered) ELSE 0 END) as avg_accuracy,
                COUNT(*) as times_taken
            FROM quiz_results
            GROUP BY topic
            HAVING COUNT(*) > 2 -- Only include topics taken at least 3 times for statistical significance
            ORDER BY avg_accuracy DESC;
        """)
        result = conn.execute(query).mappings().fetchall()
        return [dict(row) for row in result]

def get_most_active_students():
    """Fetches a leaderboard of students who have taken the most quizzes."""
    with engine.connect() as conn:
        query = text("""
            SELECT username, COUNT(*) as quiz_count
            FROM quiz_results
            GROUP BY username
            ORDER BY quiz_count DESC
            LIMIT 10;
        """)
        result = conn.execute(query).mappings().fetchall()
        return [dict(row) for row in result]

def get_daily_activity():
    """Fetches the number of quizzes taken each day."""
    with engine.connect() as conn:
        query = text("""
            SELECT 
                DATE_TRUNC('day', timestamp)::date as date, 
                COUNT(*) as quiz_count
            FROM quiz_results
            GROUP BY DATE_TRUNC('day', timestamp)
            ORDER BY date ASC;
        """)
        result = conn.execute(query).mappings().fetchall()
        return [dict(row) for row in result]

def get_duel_topic_popularity():
    """Fetches the count of duels played per topic."""
    with engine.connect() as conn:
        query = text("""
            SELECT topic, COUNT(*) as duel_count
            FROM duels
            WHERE status != 'pending'
            GROUP BY topic
            ORDER BY duel_count DESC;
        """)
        result = conn.execute(query).mappings().fetchall()
        return [dict(row) for row in result]

# --- NEW ADMIN BACKEND FUNCTIONS FOR PRACTICE QUESTIONS ---

def get_active_practice_questions():
    """Fetches all practice questions marked as active, including new assignment fields."""
    with engine.connect() as conn:
        # --- THIS IS THE FIX ---
        # The query now selects the new 'uploads_enabled' column.
        query = text("""
            SELECT id, topic, question_text, answer_text, explanation_text, 
                   assignment_pool_name, unhide_answer_at, created_at,
                   uploads_enabled -- <<< ADD THIS LINE
            FROM daily_practice_questions 
            WHERE is_active = TRUE 
            ORDER BY created_at DESC
        """)
        result = conn.execute(query).mappings().fetchall()
        return [dict(row) for row in result]

def get_all_practice_questions():
    """Fetches all practice questions for the admin view."""
    with engine.connect() as conn:
        query = text("SELECT * FROM daily_practice_questions ORDER BY created_at DESC")
        result = conn.execute(query).mappings().fetchall()
        return [dict(row) for row in result]

def add_practice_question(topic, question, answer, explanation, pool_name=None, unhide_at=None):
    """Adds a new practice question to the database."""
    with engine.connect() as conn:
        query = text("""
            INSERT INTO daily_practice_questions (topic, question_text, answer_text, explanation_text, assignment_pool_name, unhide_answer_at)
            VALUES (:topic, :question, :answer, :explanation, :pool_name, :unhide_at)
        """)
        conn.execute(query, {
            "topic": topic, 
            "question": question, 
            "answer": answer, 
            "explanation": explanation,
            "pool_name": pool_name if pool_name else None, # Ensure NULL if empty
            "unhide_at": unhide_at
        })
        conn.commit()

def toggle_practice_question_status(question_id):
    """Flips the is_active status of a question."""
    with engine.connect() as conn:
        query = text("UPDATE daily_practice_questions SET is_active = NOT is_active WHERE id = :id")
        conn.execute(query, {"id": question_id})
        conn.commit()

def delete_practice_question(question_id):
    """Deletes a practice question from the database."""
    with engine.connect() as conn:
        query = text("DELETE FROM daily_practice_questions WHERE id = :id")
        conn.execute(query, {"id": question_id})
        conn.commit()

def bulk_toggle_question_status(pool_name, is_active):
    """Activates or deactivates all questions associated with a given pool name."""
    with engine.connect() as conn:
        query = text("""
            UPDATE daily_practice_questions 
            SET is_active = :is_active 
            WHERE assignment_pool_name = :pool_name
        """)
        conn.execute(query, {"is_active": is_active, "pool_name": pool_name})
        conn.commit()

def bulk_delete_questions(pool_name):
    """Deletes all practice questions associated with a given pool name."""
    with engine.connect() as conn:
        query = text("""
            DELETE FROM daily_practice_questions 
            WHERE assignment_pool_name = :pool_name
        """)
        conn.execute(query, {"pool_name": pool_name})
        conn.commit()

def bulk_toggle_uploads_for_pool(pool_name, uploads_enabled):
    """Activates or deactivates uploads for all questions in a pool."""
    with engine.connect() as conn:
        query = text("""
            UPDATE daily_practice_questions 
            SET uploads_enabled = :uploads_enabled 
            WHERE assignment_pool_name = :pool_name
        """)
        conn.execute(query, {"uploads_enabled": uploads_enabled, "pool_name": pool_name})
        conn.commit()

def bulk_import_questions(uploaded_file):
    """Reads a CSV file, validates it, and adds the questions to the database."""
    try:
        # Read the uploaded file into a pandas DataFrame
        df = pd.read_csv(uploaded_file)

        # 1. --- Validation Step ---
        required_headers = ['topic', 'question_text', 'answer_text']
        for header in required_headers:
            if header not in df.columns:
                st.error(f"Import failed. The CSV file is missing the required header: '{header}'")
                return
        
        # 2. --- Import Step ---
        questions_added = 0
        for index, row in df.iterrows():
            # Get the optional values safely, providing None if they don't exist or are empty
            explanation = row.get('explanation_text', '') or "No explanation provided."
            pool_name = row.get('assignment_pool_name') if pd.notna(row.get('assignment_pool_name')) else None
            unhide_at_str = row.get('unhide_answer_at') if pd.notna(row.get('unhide_answer_at')) else None
            
            unhide_at = None
            if unhide_at_str:
                try:
                    # Attempt to parse the date string from the CSV
                    unhide_at = parser.parse(unhide_at_str)
                except (ValueError, TypeError):
                    st.warning(f"Could not understand the date '{unhide_at_str}' for question '{row['topic']}'. It will be ignored.")
            
            # Use our existing function to add the question to the database
            add_practice_question(
                topic=row['topic'],
                question=row['question_text'],
                answer=row['answer_text'],
                explanation=explanation,
                pool_name=pool_name,
                unhide_at=unhide_at
            )
            questions_added += 1
        
        st.success(f"✅ Import successful! Added {questions_added} new questions to the database.")
        st.balloons()
        st.rerun()

    except Exception as e:
        st.error(f"An error occurred during the import process: {e}")

# --- START: NEW FUNCTION update_practice_question ---
# Reason for change: To add a backend function that can update an existing practice question in the database.

def update_practice_question(question_id, topic, question, answer, explanation, pool_name=None, unhide_at=None):
    """Updates an existing practice question in the database."""
    with engine.connect() as conn:
        query = text("""
            UPDATE daily_practice_questions 
            SET topic = :topic, 
                question_text = :question, 
                answer_text = :answer, 
                explanation_text = :explanation,
                assignment_pool_name = :pool_name,
                unhide_answer_at = :unhide_at
            WHERE id = :id
        """)
        conn.execute(query, {
            "id": question_id,
            "topic": topic,
            "question": question,
            "answer": answer,
            "explanation": explanation,
            "pool_name": pool_name if pool_name else None, # Ensure NULL if empty
            "unhide_at": unhide_at
        })
        conn.commit()


# --- START: NEW FUNCTION get_or_assign_student_question ---
# Reason for change: To add the core backend logic for the "Dynamic Single Assignment" feature.
# This function assigns a unique question from a pool to a student.

def get_or_assign_student_question(username, pool_name):
    """
    Checks if a student has an assigned question from a pool.
    If yes, returns the question ID.
    If no, assigns a new unique question, saves it, and returns the new ID.
    """
    with engine.connect() as conn:
        with conn.begin(): # Use a transaction for safety
            # 1. Check if a question is already assigned to this user for this pool
            find_query = text("""
                SELECT question_id FROM student_assignments 
                WHERE username = :username AND assignment_pool_name = :pool_name
            """)
            existing_assignment = conn.execute(find_query, {"username": username, "pool_name": pool_name}).scalar_one_or_none()
            
            if existing_assignment:
                return existing_assignment

            # 2. If no assignment exists, we need to assign a new one.
            # Get all available question IDs in the pool.
            pool_questions_query = text("""
                SELECT id FROM daily_practice_questions 
                WHERE assignment_pool_name = :pool_name AND is_active = TRUE
            """)
            all_pool_q_ids = {row[0] for row in conn.execute(pool_questions_query, {"pool_name": pool_name}).fetchall()}

            if not all_pool_q_ids:
                return None # No questions in this pool

            # Get all question IDs that are already assigned to OTHER students from this pool.
            assigned_q_ids_query = text("""
                SELECT question_id FROM student_assignments
                WHERE assignment_pool_name = :pool_name
            """)
            assigned_q_ids = {row[0] for row in conn.execute(assigned_q_ids_query, {"pool_name": pool_name}).fetchall()}
            
            # Find the questions that have not yet been assigned
            unassigned_q_ids = list(all_pool_q_ids - assigned_q_ids)

            if unassigned_q_ids:
                # If there are unassigned questions, pick one randomly
                chosen_q_id = random.choice(unassigned_q_ids)
            else:
                # If all questions have been assigned, start reusing them randomly from the full pool
                chosen_q_id = random.choice(list(all_pool_q_ids))
            
            # 3. Save the new assignment to the database
            insert_query = text("""
                INSERT INTO student_assignments (username, assignment_pool_name, question_id)
                VALUES (:username, :pool_name, :question_id)
            """)
            conn.execute(insert_query, {"username": username, "pool_name": pool_name, "question_id": chosen_q_id})
            
            return chosen_q_id

# --- END: NEW FUNCTION get_or_assign_student_question ---
# --- END: NEW FUNCTION update_practice_question ---

# --- NEW ADMIN BACKEND FUNCTIONS FOR USER ACTIONS ---

def toggle_user_suspension(username):
    """Flips the is_active status for a given user."""
    with engine.connect() as conn:
        query = text("UPDATE public.users SET is_active = NOT is_active WHERE username = :username")
        conn.execute(query, {"username": username})
        conn.commit()

def reset_user_password_admin(username, new_password):
    """Allows an admin to set a new password for a user."""
    with engine.connect() as conn:
        hashed_password = hash_password(new_password)
        query = text("UPDATE public.users SET password = :password WHERE username = :username")
        conn.execute(query, {"username": username, "password": hashed_password})
        conn.commit()

# --- END OF NEW USER ACTION FUNCTIONS ---

# --- END OF PRACTICE QUESTION FUNCTIONS ---

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

# --- START: NEW FUNCTION check_and_grant_daily_reward ---
# Reason for change: To add the backend logic for the daily login reward and streak system.

def check_and_grant_daily_reward(username):
    """Checks the user's login streak and grants a reward if applicable."""
    from datetime import date, timedelta

    today = date.today()
    reward_message = None
    
    with engine.connect() as conn:
        with conn.begin(): # Use a transaction
            query = text("SELECT last_login_date, streak_count FROM login_streaks WHERE username = :username")
            streak_data = conn.execute(query, {"username": username}).mappings().first()

            if not streak_data:
                # First time ever getting a daily reward
                insert_query = text("INSERT INTO login_streaks (username, last_login_date, streak_count) VALUES (:u, :d, 1)")
                conn.execute(insert_query, {"u": username, "d": today})
                update_coin_balance(username, 15, "Daily Login Reward: Day 1")
                reward_message = "🎉 Welcome! For your first daily login, you get 15 coins!"
            else:
                last_login = streak_data['last_login_date']
                streak = streak_data['streak_count']

                if last_login == today:
                    # Already logged in today, no new reward
                    return None
                
                yesterday = today - timedelta(days=1)
                new_streak = streak + 1 if last_login == yesterday else 1

                if new_streak >= 7:
                    # 7-day streak prize!
                    update_coin_balance(username, 0, "Daily Login Reward: 7-Day Streak Prize") # Log the transaction
                    update_sql = text("UPDATE user_profiles SET mystery_boxes = COALESCE(mystery_boxes, 0) + 1 WHERE username = :username")
                    conn.execute(update_sql, {"username": username})
                    reward_message = "🎊 7-Day Streak! You've earned a 🎁 Mystery Box!"
                    new_streak = 0 # Reset streak after big prize
                else:
                    # Standard daily reward
                    rewards = {1: 15, 2: 20, 3: 25, 4: 30, 5: 35, 6: 40}
                    reward_amount = rewards.get(new_streak, 15)
                    update_coin_balance(username, reward_amount, f"Daily Login Reward: Day {new_streak}")
                    reward_message = f"🎉 Daily Login Streak: Day {new_streak}! You get {reward_amount} coins!"

                # Update the streak table
                update_query = text("UPDATE login_streaks SET last_login_date = :d, streak_count = :s WHERE username = :u")
                conn.execute(update_query, {"d": today, "s": new_streak, "u": username})

    return reward_message

# --- END: NEW FUNCTION check_and_grant_daily_reward ---

def upload_assignment_file(username, pool_name, uploaded_file):
    """Uploads a file to Supabase Storage and records the submission."""
    try:
        file_path = f"{username}/{pool_name}/{uploaded_file.name}"
        
        # --- THIS IS THE FIX ---
        # The function now correctly uses 'supabase_client'.
        supabase_client.storage.from_('assignment_submissions').upload(file=uploaded_file.getvalue(), path=file_path)

        with engine.connect() as conn:
            query = text("""
                INSERT INTO assignment_submissions (username, assignment_pool_name, file_path)
                VALUES (:username, :pool_name, :file_path)
                ON CONFLICT (username, assignment_pool_name) DO UPDATE SET
                    file_path = EXCLUDED.file_path,
                    submitted_at = NOW();
            """)
            conn.execute(query, {"username": username, "pool_name": pool_name, "file_path": file_path})
            conn.commit()
        return True, "File uploaded successfully!"
    except Exception as e:
        if "duplicate" in str(e).lower():
            try:
                supabase_client.storage.from_('assignment_submissions').remove([file_path])
                supabase_client.storage.from_('assignment_submissions').upload(file=uploaded_file.getvalue(), path=file_path)
                return True, "You have updated your submission successfully!"
            except Exception as update_e:
                print(f"Error updating file: {update_e}")
                return False, f"An error occurred while updating your file: {update_e}"
        
        print(f"Error uploading file: {e}")
        return False, f"An error occurred: {e}"

def get_student_submission(username, pool_name):
    """Checks if a student has already submitted for an assignment pool."""
    with engine.connect() as conn:
        query = text("""
            SELECT file_path FROM assignment_submissions
            WHERE username = :username AND assignment_pool_name = :pool_name
        """)
        result = conn.execute(query, {"username": username, "pool_name": pool_name}).scalar_one_or_none()
        return result

def get_all_submissions_for_pool(pool_name):
    """Fetches all submissions for a pool and creates signed URLs for viewing."""
    with engine.connect() as conn:
        query = text("""
            SELECT username, file_path, submitted_at
            FROM assignment_submissions
            WHERE assignment_pool_name = :pool_name
            ORDER BY username ASC
        """)
        submissions = conn.execute(query, {"pool_name": pool_name}).mappings().fetchall()

    processed_submissions = []
    for sub in submissions:
        sub_dict = dict(sub)
        try:
            # --- THIS IS THE FIX ---
            # This now also uses the correct 'supabase_client'.
            response = supabase_client.storage.from_('assignment_submissions').create_signed_url(sub_dict['file_path'], 3600)
            sub_dict['view_url'] = response.get('signedURL')
            processed_submissions.append(sub_dict)
        except Exception as e:
            print(f"Error creating signed URL for {sub_dict['file_path']}: {e}")
            sub_dict['view_url'] = None
            processed_submissions.append(sub_dict)
            
    return processed_submissions

def save_grade(username, pool_name, grade, feedback):
    """Saves or updates a grade and feedback for a student's submission."""
    with engine.connect() as conn:
        query = text("""
            INSERT INTO assignment_grades (username, assignment_pool_name, grade, feedback)
            VALUES (:user, :pool, :grade, :feedback)
            ON CONFLICT (username, assignment_pool_name) DO UPDATE SET
                grade = EXCLUDED.grade,
                feedback = EXCLUDED.feedback,
                graded_at = NOW();
        """)
        conn.execute(query, {
            "user": username,
            "pool": pool_name,
            "grade": grade,
            "feedback": feedback
        })
        conn.commit()
    return True

def get_student_grade(username, pool_name):
    """Fetches the grade and feedback for a single student on a specific assignment."""
    with engine.connect() as conn:
        query = text("""
            SELECT grade, feedback, graded_at
            FROM assignment_grades
            WHERE username = :username AND assignment_pool_name = :pool_name
        """)
        result = conn.execute(query, {"username": username, "pool_name": pool_name}).mappings().first()
        return dict(result) if result else None

def get_grades_for_pool(pool_name):
    """Fetches all existing grades for an assignment pool."""
    with engine.connect() as conn:
        query = text("""
            SELECT username, grade, feedback 
            FROM assignment_grades
            WHERE assignment_pool_name = :pool_name
        """)
        result = conn.execute(query, {"pool_name": pool_name}).mappings().fetchall()
        # Return as a dictionary keyed by username for easy lookup
        return {row['username']: {'grade': row['grade'], 'feedback': row['feedback']} for row in result}

def toggle_upload_status_for_question(question_id):
    """Flips the uploads_enabled status of a question."""
    with engine.connect() as conn:
        query = text("UPDATE daily_practice_questions SET uploads_enabled = NOT uploads_enabled WHERE id = :id")
        conn.execute(query, {"id": question_id})
        conn.commit()

def format_time(seconds):
    """Formats seconds into a MM:SS string."""
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{minutes:02d}:{secs:02d}"
    
def set_user_flair(username, flair_text):
    """Updates the user_flair for a given user."""
    # Add a length limit to keep the flair short and clean
    if len(flair_text) > 25:
        st.toast("Flair text cannot be longer than 25 characters.", icon="⚠️")
        return
        
    with engine.connect() as conn:
        query = text("UPDATE user_profiles SET user_flair = :flair WHERE username = :username")
        conn.execute(query, {"flair": flair_text, "username": username})
        conn.commit()
    st.toast("Your new flair has been set!", icon="✨")

def get_user_flairs(usernames):
    """
    Efficiently fetches the user_flair for a given list of usernames.
    Returns a dictionary mapping username -> flair_text.
    """
    if not usernames:
        return {}
    
    with engine.connect() as conn:
        query = text("""
            SELECT username, user_flair 
            FROM user_profiles 
            WHERE username = ANY(:usernames) AND user_flair IS NOT NULL
        """)
        # We need to pass the list of usernames as a list/tuple for the ANY clause
        result = conn.execute(query, {"usernames": list(usernames)}).mappings().fetchall()
        return {row['username']: row['user_flair'] for row in result}

def _generate_avatar_html(username):
    """Generates a stylish avatar circle with a user's initial."""
    initial = username[0].upper()
    hash_val = int(hashlib.md5(username.encode()).hexdigest(), 16)
    hue = hash_val % 360
    
    avatar_style = f"""
        background-color: hsl({hue}, 60%, 50%);
    """
    
    return f'<div class="chat-avatar" style="{avatar_style}">{initial}</div>'

def get_user_display_info(usernames):
    """
    Efficiently fetches display info (flair, border, name effect) for a list of usernames.
    """
    if not usernames:
        return {}
    
    with engine.connect() as conn:
        # --- FIX: Also select 'active_name_effect' ---
        query = text("""
            SELECT username, user_flair, active_border, active_name_effect 
            FROM user_profiles 
            WHERE username = ANY(:usernames)
        """)
        result = conn.execute(query, {"usernames": list(usernames)}).mappings().fetchall()
        
        # --- FIX: Return the name effect in the dictionary ---
        return {
            row['username']: {
                "flair": row['user_flair'], 
                "border": row['active_border'],
                "effect": row['active_name_effect'] # Add this new key
            } for row in result
        }
def set_active_cosmetic(username, cosmetic_id, cosmetic_type):
    """Sets the active cosmetic for a user after verifying they own it."""
    with engine.connect() as conn:
        with conn.begin():
            # First, verify the user owns the cosmetic
            ownership_query = text("SELECT 1 FROM user_profiles WHERE username = :username AND :cosmetic_id = ANY(unlocked_cosmetics)")
            is_owned = conn.execute(ownership_query, {"username": username, "cosmetic_id": cosmetic_id}).first()

            if is_owned or cosmetic_id == 'default':
                if cosmetic_type == 'border':
                    update_query = text("UPDATE user_profiles SET active_border = :cosmetic_id WHERE username = :username")
                elif cosmetic_type == 'name_effect':
                    update_query = text("UPDATE user_profiles SET active_name_effect = :cosmetic_id WHERE username = :username")
                else:
                    return False # Invalid type

                conn.execute(update_query, {"username": username, "cosmetic_id": cosmetic_id})
                st.toast(f"Set active {cosmetic_type} to {cosmetic_id.replace('_', ' ').title()}!")
                return True
            else:
                st.error("You do not own this item.")
                return False

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

# Replace your function with this NEW version
def save_quiz_result(username, topic, score, questions_answered, coins_earned, description):
    # This function now acts as a coordinator for all post-quiz updates.
    with engine.connect() as conn:
        conn.execute(text("INSERT INTO quiz_results (username, topic, score, questions_answered) VALUES (:u, :t, :s, :qa)"),
                     {"u": username, "t": topic, "s": score, "qa": questions_answered})
        conn.commit()
    
    # --- START: THIS IS THE MODIFIED LOGIC ---
    # We only update the specific topic skill score if the quiz was NOT a WASSCE Prep session.
    # This keeps the adaptive learning pure to each topic.
    if topic != "WASSCE Prep":
        update_skill_score(username, topic, score, questions_answered)
    # --- END: MODIFIED LOGIC ---
    
    # Update the student's coin balance
    if coins_earned > 0:
        update_coin_balance(username, coins_earned, description)

    # Update other gamification systems (challenges and achievements)
    update_gamification_progress(username, topic, score)
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

@st.cache_data(ttl=300) # Cache for 5 minutes
def get_top_duel_players():
    """Fetches the top 5 players based on their total duel wins."""
    with engine.connect() as conn:
        query = text("""
            WITH wins AS (
                SELECT player1_username AS username, 1 AS win FROM duels WHERE status = 'player1_win'
                UNION ALL
                SELECT player2_username AS username, 1 AS win FROM duels WHERE status = 'player2_win'
            )
            SELECT username, SUM(win) as total_wins
            FROM wins
            GROUP BY username
            ORDER BY total_wins DESC
            LIMIT 5;
        """)
        result = conn.execute(query).mappings().fetchall()
        return [dict(row) for row in result]
@st.cache_data(ttl=300) # Cache for 5 minutes
def get_overall_top_scores(time_filter="all"):
    """Fetches the top 10 users based on the sum of all their correct answers."""
    with engine.connect() as conn:
        time_clause = ""
        if time_filter == "week": time_clause = "WHERE timestamp >= NOW() - INTERVAL '7 days'"
        elif time_filter == "month": time_clause = "WHERE timestamp >= NOW() - INTERVAL '30 days'"
        
        query = text(f"""
            SELECT username, SUM(score) as total_score
            FROM quiz_results
            {time_clause}
            GROUP BY username
            ORDER BY total_score DESC
            LIMIT 10;
        """)
        result = conn.execute(query)
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
            
            conn.execute(text("""
                UPDATE user_daily_progress SET progress_count = :new_progress 
                WHERE username = :username AND challenge_date = :today
            """), {"new_progress": new_progress, "username": username, "today": today})

            if new_progress >= challenge['target_count']:
                conn.execute(text("""
                    UPDATE user_daily_progress SET is_completed = TRUE 
                    WHERE username = :username AND challenge_date = :today
                """), {"username": username, "today": today})
                
                # --- NEW COIN REWARD LOGIC ---
                update_coin_balance(username, 50, "Daily Challenge Completed!")
                # --- END OF NEW LOGIC ---

                st.session_state.challenge_completed_toast = True
            
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

# --- NEW FUNCTIONS FOR RIVAL SNAPSHOT FEATURE ---

def get_rival_snapshot(username, topic, time_filter="all"):
    """
    Fetches the user's rank, total players, and their immediate rivals (above and below) for a specific topic.
    """
    with engine.connect() as conn:
        time_clause = ""
        if time_filter == "week":
            time_clause = "AND timestamp >= NOW() - INTERVAL '7 days'"
        elif time_filter == "month":
            time_clause = "AND timestamp >= NOW() - INTERVAL '30 days'"

        # THIS SQL QUERY HAS BEEN CORRECTED FOR RELIABILITY
        query = text(f"""
            WITH UserBestScores AS (
                SELECT
                    username, score, questions_answered, timestamp,
                    ROW_NUMBER() OVER(PARTITION BY username ORDER BY (CAST(score AS REAL) / questions_answered) DESC, questions_answered DESC, timestamp ASC) as rn
                FROM quiz_results
                WHERE topic = :topic AND questions_answered > 0 {time_clause}
            ),
            RankedScores AS (
                SELECT
                    username,
                    RANK() OVER (ORDER BY (CAST(score AS REAL) / questions_answered) DESC, questions_answered DESC, timestamp ASC) as rank
                FROM UserBestScores
                WHERE rn = 1
            ),
            CurrentUser AS (
                SELECT rank FROM RankedScores WHERE username = :username
            )
            SELECT username, rank
            FROM RankedScores
            WHERE rank IN ((SELECT rank FROM CurrentUser) - 1, (SELECT rank FROM CurrentUser), (SELECT rank FROM CurrentUser) + 1)
            ORDER BY rank;
        """)

        result = conn.execute(query, {"topic": topic, "username": username}).mappings().fetchall()
        
        snapshot = {"user_rank": None, "rival_above": None, "rival_below": None}
        if not result:
            return None

        user_row = next((r for r in result if r['username'] == username), None)
        if not user_row:
            return None
        snapshot['user_rank'] = user_row['rank']

        for row in result:
            if row['rank'] < snapshot['user_rank']:
                snapshot['rival_above'] = {'username': row['username'], 'rank': row['rank']}
            elif row['rank'] > snapshot['user_rank']:
                snapshot['rival_below'] = {'username': row['username'], 'rank': row['rank']}
        
        return snapshot
def get_total_overall_players(time_filter="all"):
    """Gets the total number of unique players on the overall leaderboard."""
    with engine.connect() as conn:
        time_clause = ""
        if time_filter == "week": time_clause = "WHERE timestamp >= NOW() - INTERVAL '7 days'"
        elif time_filter == "month": time_clause = "WHERE timestamp >= NOW() - INTERVAL '30 days'"
        query = text(f"SELECT COUNT(DISTINCT username) FROM quiz_results {time_clause}")
        return conn.execute(query).scalar_one() or 0

def get_overall_rival_snapshot(username, time_filter="all"):
    """Fetches the user's overall rank and their immediate rivals."""
    with engine.connect() as conn:
        time_clause = ""
        if time_filter == "week": time_clause = "WHERE timestamp >= NOW() - INTERVAL '7 days'"
        elif time_filter == "month": time_clause = "WHERE timestamp >= NOW() - INTERVAL '30 days'"
        
        # THIS SQL QUERY HAS BEEN CORRECTED TO USE THE RELIABLE SUBQUERY SYNTAX
        query = text(f"""
            WITH PlayerTotals AS (
                SELECT username, SUM(score) as total_score
                FROM quiz_results {time_clause}
                GROUP BY username
            ),
            RankedScores AS (
                SELECT username, RANK() OVER (ORDER BY total_score DESC, username ASC) as rank
                FROM PlayerTotals
            ),
            CurrentUser AS (
                SELECT rank FROM RankedScores WHERE username = :username
            )
            SELECT username, rank
            FROM RankedScores
            WHERE rank IN ((SELECT rank FROM CurrentUser) - 1, (SELECT rank FROM CurrentUser), (SELECT rank FROM CurrentUser) + 1)
            ORDER BY rank;
        """)
        result = conn.execute(query, {"username": username}).mappings().fetchall()
        
        snapshot = {"user_rank": None, "rival_above": None, "rival_below": None}
        if not result: return None

        user_row = next((r for r in result if r['username'] == username), None)
        if not user_row: return None
        snapshot['user_rank'] = user_row['rank']

        for row in result:
            if row['rank'] < snapshot['user_rank']:
                snapshot['rival_above'] = {'username': row['username'], 'rank': row['rank']}
            elif row['rank'] > snapshot['user_rank']:
                snapshot['rival_below'] = {'username': row['username'], 'rank': row['rank']}
        
        return snapshot
# --- END OF NEW FUNCTIONS ---

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
    """
    Gets online users who are NOT in a genuinely active duel.
    (FINAL, ROBUST LOGIC WITH TIMEOUT)
    """
    with engine.connect() as conn:
        # This final version checks status, question index, AND a 5-minute timeout,
        # ensuring abandoned duels automatically expire from the online list.
        query = text("""
            SELECT s.username
            FROM user_status s
            WHERE s.is_online = TRUE 
              AND s.last_seen > NOW() - INTERVAL '5 minutes'
              AND s.username != :current_user
              AND NOT EXISTS (
                  SELECT 1 
                  FROM duels d
                  WHERE 
                    (d.player1_username = s.username OR d.player2_username = s.username)
                    -- A duel is only TRULY active if all these are met:
                    AND d.status = 'active'                 -- It must be marked active.
                    AND d.current_question_index < 10       -- It must not be finished.
                    AND d.last_action_at > NOW() - INTERVAL '5 minutes' -- It must be recent.
              );
        """)
        result = conn.execute(query, {"current_user": current_user})
        return [row[0] for row in result.fetchall()]
# Add this block of 5 new functions to your Core Backend Functions section

# Replace your existing create_duel function with this one.
def create_duel(challenger_username, opponent_username, topic):
    """Creates a new duel challenge in the database."""
    with engine.connect() as conn:
        # --- THIS IS THE FIX ---
        # It now explicitly sets the last_action_at timestamp the moment a challenge is created.
        query = text("""
            INSERT INTO duels (player1_username, player2_username, topic, status, last_action_at)
            VALUES (:p1, :p2, :topic, 'pending', CURRENT_TIMESTAMP)
            RETURNING id;
        """)
        result = conn.execute(query, {"p1": challenger_username, "p2": opponent_username, "topic": topic})
        conn.commit()
        duel_id = result.scalar_one_or_none()
        return duel_id
def get_pending_challenge(username):
    """Checks if there is an active, recent challenge for a user."""
    with engine.connect() as conn:
        # Look for a pending challenge from the last 60 seconds
        query = text("""
            SELECT id, player1_username, topic 
            FROM duels 
            WHERE player2_username = :username 
            AND status = 'pending' 
            AND created_at > NOW() - INTERVAL '60 seconds'
            ORDER BY created_at DESC
            LIMIT 1;
        """)
        result = conn.execute(query, {"username": username}).mappings().first()
        return dict(result) if result else None

# Replace your existing get_active_duel_for_player function with this one.

def get_active_duel_for_player(username):
    """
    Return the most-recent active duel for this user.
    Robust against NULL current_question_index on fresh activations.
    """
    with engine.connect() as conn:
        query = text("""
            SELECT id
            FROM duels
            WHERE (player1_username = :username OR player2_username = :username)
              AND status = 'active'
              AND COALESCE(current_question_index, 0) < 10
              AND last_action_at > NOW() - INTERVAL '5 minutes'
            ORDER BY last_action_at DESC
            LIMIT 1;
        """)
        row = conn.execute(query, {"username": username}).mappings().first()
        return dict(row) if row else None

def get_duel_summary(duel_id):
    """Fetches all data needed for the duel summary page."""
    with engine.connect() as conn:
        # First, get the main duel information
        duel_details_query = text("SELECT * FROM duels WHERE id = :d")
        duel = conn.execute(duel_details_query, {"d": duel_id}).mappings().first()
        if not duel:
            return None
        
        summary = dict(duel)

        # Next, get all the questions and answers for that duel
        duel_questions_query = text("""
            SELECT question_index, question_data_json, answered_by, is_correct 
            FROM duel_questions 
            WHERE duel_id = :d 
            ORDER BY question_index ASC
        """)
        questions = conn.execute(duel_questions_query, {"d": duel_id}).mappings().fetchall()
        
        # Parse the JSON data for each question
        summary['questions'] = [
            {
                'index': q['question_index'],
                'data': json.loads(q['question_data_json']),
                'answered_by': q['answered_by'],
                'is_correct': q['is_correct']
            } for q in questions
        ]
        return summary

# Replace your existing accept_duel function with this one.
def accept_duel(duel_id, topic):
    """Correctly marks a duel as active, then generates and saves questions for BOTH players."""
    
    # Step 1: Perform a very fast transaction to ONLY update the status.
    with engine.connect() as conn:
        with conn.begin():
            update_query = text("""
                UPDATE duels 
                SET status = 'active', last_action_at = CURRENT_TIMESTAMP 
                WHERE id = :duel_id AND status = 'pending';
            """)
            conn.execute(update_query, {"duel_id": duel_id})
    
    # Step 2: Generate and store questions (this is based on the opponent's history)
    generate_and_store_duel_questions(duel_id, topic)

    # --- NEW: Save the generated questions for the challenger as well ---
    try:
        with engine.connect() as conn:
            # First, get the challenger's username from the duel info
            challenger_username = conn.execute(
                text("SELECT player1_username FROM duels WHERE id = :duel_id"),
                {"duel_id": duel_id}
            ).scalar_one_or_none()

            if challenger_username:
                # Next, get the questions that were just created for this duel
                questions = conn.execute(
                    text("SELECT question_data_json FROM duel_questions WHERE duel_id = :duel_id"),
                    {"duel_id": duel_id}
                ).mappings().fetchall()

                # Loop through the questions and save them to the challenger's seen list
                for q_row in questions:
                    q_data = json.loads(q_row["question_data_json"])
                    question_text = q_data.get("stem", q_data.get("question", ""))
                    q_id = get_question_id(question_text)
                    save_seen_question(challenger_username, q_id)
    except Exception as e:
        # If this fails for any reason, we don't want to crash the app.
        # We can log this error for debugging if needed.
        print(f"Error saving seen questions for challenger: {e}")
    # --- END OF NEW CODE ---
    
    return True

# Add this new helper function right after your accept_duel function
def generate_and_store_duel_questions(duel_id, topic):
    """Generates and stores questions for a duel if they don't already exist."""
    with engine.connect() as conn, conn.begin():
        count = conn.execute(
            text("SELECT COUNT(*) FROM duel_questions WHERE duel_id = :d"), {"d": duel_id}
        ).scalar_one()
        if count >= 10:
            return

        rows = []
        for i in range(10):
            q_data = generate_question(topic)
            rows.append({"duel_id": duel_id, "question_index": i, "question_data_json": json.dumps(q_data)})

        conn.execute(text("""
            INSERT INTO duel_questions (duel_id, question_index, question_data_json)
            VALUES (:duel_id, :question_index, :question_data_json)
            ON CONFLICT (duel_id, question_index) DO NOTHING
        """), rows)

def get_duel_state(duel_id):
    """Fetches the complete current state of a duel from the database."""
    with engine.connect() as conn:
        duel = conn.execute(text("SELECT * FROM duels WHERE id = :d"), {"d": duel_id}).mappings().first()
        if not duel:
            return None
        duel = dict(duel)

        # If the duel is finished or logically complete, don't try to fetch a question
        if duel.get("status") != "active" or (duel.get("current_question_index") or 0) >= 10:
            return duel

        qrow = conn.execute(
            text("""SELECT question_data_json, answered_by, is_correct
                    FROM duel_questions
                    WHERE duel_id = :d AND question_index = :i"""),
            {"d": duel_id, "i": duel.get("current_question_index", 0)}
        ).mappings().first()

        if qrow:
            duel["question"] = json.loads(qrow["question_data_json"])
            duel["question_answered_by"] = qrow["answered_by"]
            duel["question_is_correct"] = qrow["is_correct"]

        return duel
# Replace your existing submit_duel_answer function with this one.

def submit_duel_answer(duel_id, username, is_correct):
    """Records a player's answer and updates the duel state using more robust, atomic updates."""
    with engine.connect() as conn, conn.begin():
        # This logic fetches player usernames, which we need for awarding coins
        duel_info = conn.execute(
            text("SELECT player1_username, player2_username, current_question_index FROM duels WHERE id = :d"),
            {"d": duel_id}
        ).mappings().first()

        if not duel_info:
            return False

        q_index = duel_info["current_question_index"]
        player1, player2 = duel_info["player1_username"], duel_info["player2_username"]

        result = conn.execute(text("""
            UPDATE duel_questions
            SET answered_by = :u, is_correct = :ok
            WHERE duel_id = :d AND question_index = :i AND answered_by IS NULL
        """), {"u": username, "ok": is_correct, "d": duel_id, "i": q_index})

        if result.rowcount == 0:
            return False

        if is_correct:
            if username == player1:
                conn.execute(text("UPDATE duels SET player1_score = player1_score + 1 WHERE id = :d"), {"d": duel_id})
            else:
                conn.execute(text("UPDATE duels SET player2_score = player2_score + 1 WHERE id = :d"), {"d": duel_id})

        if q_index == 9:
            final_scores = conn.execute(
                text("SELECT player1_score, player2_score FROM duels WHERE id = :d"),
                {"d": duel_id}
            ).mappings().first()

            final_status = "draw"
            if final_scores["player1_score"] > final_scores["player2_score"]:
                final_status = "player1_win"
            elif final_scores["player2_score"] > final_scores["player1_score"]:
                final_status = "player2_win"

            # --- NEW COIN REWARD LOGIC ---
            if final_status == "player1_win":
                update_coin_balance(player1, 40, f"Won Duel vs. {player2}")
            elif final_status == "player2_win":
                update_coin_balance(player2, 40, f"Won Duel vs. {player1}")
            elif final_status == "draw":
                update_coin_balance(player1, 15, f"Duel Draw vs. {player2}")
                update_coin_balance(player2, 15, f"Duel Draw vs. {player1}")
            # --- END OF NEW LOGIC ---

            conn.execute(text("""
                UPDATE duels
                SET status = :final, current_question_index = 10,
                    last_action_at = CURRENT_TIMESTAMP, finished_at = CURRENT_TIMESTAMP
                WHERE id = :d
            """), {"final": final_status, "d": duel_id})
        else:
            conn.execute(text("""
                UPDATE duels
                SET current_question_index = current_question_index + 1,
                    last_action_at = CURRENT_TIMESTAMP
                WHERE id = :d
            """), {"d": duel_id})

        return True

def display_duel_summary_page(duel_summary):
    """Renders the detailed post-duel summary screen."""
    player1 = duel_summary["player1_username"]
    player2 = duel_summary["player2_username"]
    p1_score = duel_summary["player1_score"]
    p2_score = duel_summary["player2_score"]
    current_user = st.session_state.username

    st.header(f"📜 Duel Summary: {player1} vs. {player2}")

    # Determine the winner
    winner = ""
    if p1_score > p2_score: winner = player1
    elif p2_score > p1_score: winner = player2

    if winner:
        if winner == current_user:
            st.success(f"🎉 Congratulations, you won!")
            st.balloons()
        else:
            st.error(f"😞 You lost against {winner}.")
    else:
        st.info("🤝 The duel ended in a draw!")

    # Display final scores
    cols = st.columns(2)
    cols[0].metric(f"{player1}'s Final Score", p1_score)
    cols[1].metric(f"{player2}'s Final Score", p2_score)

    st.markdown("<hr class='styled-hr'>", unsafe_allow_html=True)
    st.subheader("Question Breakdown")

    # Loop through and display each question
    for q in duel_summary.get('questions', []):
        q_data = q['data']
        with st.expander(f"**Question {q['index'] + 1}**"):
            st.markdown(q_data.get("question", ""), unsafe_allow_html=True)
            st.write(f"**Correct Answer:** {q_data.get('answer')}")

            if q['answered_by']:
                if q['is_correct']:
                    st.success(f"✅ Answered correctly by {q['answered_by']}.")
                else:
                    st.error(f"❌ Answered incorrectly by {q['answered_by']}.")
            else:
                st.info("⚪ This question was not answered by either player.")
            st.write("---")
            
    st.markdown("<hr class='styled-hr'>", unsafe_allow_html=True)

    # --- THIS IS THE BACK TO LOBBY CODE ---
    # The Rematch button and columns have been removed.
    if st.button("🚪 Back to Lobby", use_container_width=True):
        st.session_state.pop("current_duel_id", None)
        st.session_state.page = "math_game_page" 
        st.rerun()
# --- FIX: THIS IS THE NEW, OPTIMIZED VERSION OF THE DUEL PAGE ---
def display_duel_page():
    """Renders the real-time head-to-head duel screen with improved loading logic."""
    duel_id = st.session_state.get("current_duel_id")
    if not duel_id:
        st.error("No active duel found.")
        st.session_state.page = "login"
        time.sleep(1)
        st.rerun()
        return

    duel_state = get_duel_state(duel_id)
    if not duel_state:
        st.error("Could not retrieve duel state.")
        st.session_state.pop("current_duel_id", None)
        st.session_state.page = "login"
        time.sleep(1)
        st.rerun()
        return

    status = duel_state["status"]
    current_q_index = duel_state.get("current_question_index", 0)

    # Check if the duel is finished FIRST, before rendering anything else.
    if status in ['player1_win', 'player2_win', 'draw', 'expired'] or current_q_index >= 10:
        duel_summary = get_duel_summary(duel_id)
        if duel_summary:
            display_duel_summary_page(duel_summary)
        else:
            st.error("Could not load duel summary.")
            if st.button("Back to Lobby", use_container_width=True):
                st.session_state.pop("current_duel_id", None)
                st.session_state.page = "math_game_page"
                st.rerun()
        return  # Exit the function immediately after showing the summary.

    # Header and Score Display (only runs for pending or active duels)
    player1 = duel_state["player1_username"]
    player2 = duel_state["player2_username"]
    p1_score = duel_state["player1_score"]
    p2_score = duel_state["player2_score"]

    st.header(f"⚔️ Duel: {player1} vs. {player2}")
    st.subheader(f"Topic: {duel_state['topic']}")

    # --- NEW: Live Scoreboard ---
    cols = st.columns(2)
    cols[0].metric(f"{player1}'s Score", p1_score)
    cols[1].metric(f"{player2}'s Score", p2_score)

    display_q_number = min(current_q_index + 1, 10)
    st.progress(current_q_index / 10, text=f"Question {display_q_number}/10")
    st.markdown("<hr class='styled-hr'>", unsafe_allow_html=True)

    # --- THIS IS THE OPTIMIZATION FOR THE "PREPARING DUEL" BUG ---
    # If questions aren't immediately available, this block runs silently
    # to ensure they are loaded without a disruptive spinner and extra rerun.
    if status == "active" and "question" not in duel_state:
        # Silently ensure questions are generated (acts as a safety net).
        generate_and_store_duel_questions(duel_id, duel_state["topic"])
        # Re-fetch the state within the same script run to get the questions.
        duel_state = get_duel_state(duel_id)
        # If still no question, show a brief loading message and rerun ONCE.
        if "question" not in duel_state:
            st.info("Preparing the duel...")
            st_autorefresh(interval=1500, limit=1, key="duel_start_refresh")
            return
    # --- END OF OPTIMIZATION ---

    # State-Specific Logic for pending or active duels
    if status == "pending":
        st.info(f"⏳ Waiting for {duel_state['player2_username']} to accept your challenge...")
        # FIX: Increased refresh interval for better responsiveness
        st_autorefresh(interval=2000, key="duel_pending_refresh")
        return

    # Normal active flow: Question is displayed
    q = duel_state.get("question")
    answered_by = duel_state.get("question_answered_by")

    # This handles the rare case where the question is still not loaded.
    if not q:
        st.info("Loading next question...")
        st_autorefresh(interval=1000, limit=1, key="duel_q_load_refresh")
        return

    st.markdown(q.get("question", ""), unsafe_allow_html=True)
    
    if answered_by:
        is_correct = duel_state.get('question_is_correct')
        if is_correct:
            st.success(f"✅ {answered_by} answered correctly!")
        else:
            st.error(f"❌ {answered_by} answered incorrectly. The answer was {q.get('answer')}.")
        st.info("Waiting for the next question...")
        # FIX: Increased refresh interval for better responsiveness
        st_autorefresh(interval=2000, key="duel_answered_refresh")
    else:
        with st.form(key=f"duel_form_{current_q_index}"):
            user_choice = st.radio("Select your answer:", q.get("options", []), index=None)
            if st.form_submit_button("Submit Answer", type="primary"):
                if user_choice is not None:
                    is_correct = (str(user_choice) == str(q.get("answer")))
                    # The backend function handles the "fastest finger" logic
                    submit_duel_answer(duel_id, st.session_state.username, is_correct)
                    st.rerun()
                else:
                    st.warning("Please select an answer.")
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

# --- NEW BACKEND FUNCTIONS FOR ADAPTIVE LEARNING ---

def get_skill_score(username, topic):
    """Fetches a user's skill score for a specific topic, creating it if it doesn't exist."""
    with engine.connect() as conn:
        query = text("SELECT skill_score FROM user_skill_levels WHERE username = :username AND topic = :topic")
        result = conn.execute(query, {"username": username, "topic": topic}).scalar_one_or_none()
        
        if result is None:
            # If the user has never played this topic, create a default entry
            insert_query = text("""
                INSERT INTO user_skill_levels (username, topic, skill_score)
                VALUES (:username, :topic, 50)
                ON CONFLICT (username, topic) DO NOTHING;
            """)
            conn.execute(insert_query, {"username": username, "topic": topic})
            conn.commit()
            return 50 # Return the default starting score
        return result

def update_skill_score(username, topic, score, questions_answered):
    """Updates a user's skill score based on their latest quiz performance."""
    if questions_answered == 0:
        return # Cannot update score with no questions answered

    accuracy = (score / questions_answered) * 100
    current_skill = get_skill_score(username, topic)

    # --- The Learning Algorithm ---
    # A simple algorithm: high accuracy pushes the score towards 100, low accuracy pushes it towards 0.
    # The 'learning_rate' determines how quickly the score changes.
    learning_rate = 0.25 
    
    # The new score is a weighted average of the current skill and the recent performance
    new_skill = current_skill * (1 - learning_rate) + accuracy * learning_rate
    
    # Clamp the score between 1 and 100 to prevent it from going out of bounds
    new_skill = max(1, min(100, int(new_skill)))

    with engine.connect() as conn:
        query = text("""
            UPDATE user_skill_levels 
            SET skill_score = :new_score 
            WHERE username = :username AND topic = :topic
        """)
        conn.execute(query, {"new_score": new_skill, "username": username, "topic": topic})
        conn.commit()

# --- NEW BACKEND FUNCTION FOR COIN ECONOMY ---

def update_coin_balance(username, amount, description):
    """
    Updates a user's coin balance and logs the transaction.
    This is the central function for all coin-related changes.
    """
    with engine.connect() as conn:
        with conn.begin(): # Start a database transaction
            try:
                # --- THIS IS THE FINAL, ROBUST FIX ---
                # This command will CREATE a profile if it doesn't exist,
                # or UPDATE the existing one. It solves the NULL issue permanently.
                update_query = text("""
                    INSERT INTO user_profiles (username, coins)
                    VALUES (:username, :initial_coins)
                    ON CONFLICT (username) DO UPDATE
                    SET coins = COALESCE(user_profiles.coins, 0) + :amount;
                """)
                conn.execute(update_query, {
                    "username": username, 
                    "initial_coins": 100 + amount, # For new profiles, start at 100 + this amount
                    "amount": amount               # For existing profiles, just add the amount
                })

                # Log the transaction
                log_query = text("""
                    INSERT INTO coin_transactions (username, amount, description)
                    VALUES (:username, :amount, :description)
                """)
                conn.execute(log_query, {"username": username, "amount": amount, "description": description})
                
                return True
            except Exception as e:
                print(f"Coin transaction failed for {username}: {e}")
                return False
def purchase_item(username, item_id, cost, update_statement):
    """
    Handles the logic for purchasing an item from the shop.
    Returns True on success, False on failure.
    """
    current_balance = get_coin_balance(username)
    
    if current_balance < cost:
        st.toast("Not enough coins!", icon="😞")
        return False

    with engine.connect() as conn:
        with conn.begin(): # Start a transaction
            try:
                # 1. Subtract the coins and log the transaction
                update_coin_balance(username, -cost, f"Purchased: {item_id}")
                
                # 2. Grant the item to the user
                conn.execute(update_statement, {"username": username})
                
                st.toast(f"Purchase successful! You bought {item_id}.", icon="🎉")
                return True
            except Exception as e:
                st.error(f"An error occurred during purchase: {e}")
                # The transaction will be automatically rolled back
                return False

def open_mystery_box(username):
    """
    Handles the logic for opening a mystery box.
    Returns (True, "Success Message") or (False, "Error Message").
    """
    with engine.connect() as conn:
        with conn.begin():  # Start a single, safe transaction
            try:
                # 1. Check if the user has a box and lock the row to prevent errors
                profile = conn.execute(
                    text("SELECT mystery_boxes, unlocked_cosmetics FROM user_profiles WHERE username = :username FOR UPDATE"),
                    {"username": username}
                ).mappings().first()

                if not profile or profile.get('mystery_boxes', 0) <= 0:
                    return (False, "You don't have any Mystery Boxes to open!")

                # 2. Consume one mystery box immediately
                conn.execute(
                    text("UPDATE user_profiles SET mystery_boxes = mystery_boxes - 1 WHERE username = :username"),
                    {"username": username}
                )

                # 3. Define the weighted prize pool
                prizes = ['common_coins', 'tokens', 'cosmetic', 'jackpot']
                weights = [60, 25, 14, 1]  # 60% coins, 25% tokens, 14% cosmetic, 1% jackpot
                
                chosen_prize_type = random.choices(prizes, weights=weights, k=1)[0]
                
                # 4. Award the prize based on the chosen type
                if chosen_prize_type == 'jackpot':
                    amount = 2000
                    description = "Mystery Box Jackpot!"
                    # --- FIX: Manually update coins and log transaction inside this single transaction ---
                    conn.execute(
                        text("UPDATE user_profiles SET coins = COALESCE(coins, 0) + :amount WHERE username = :username"),
                        {"amount": amount, "username": username}
                    )
                    conn.execute(
                        text("INSERT INTO coin_transactions (username, amount, description) VALUES (:u, :a, :d)"),
                        {"u": username, "a": amount, "d": description}
                    )
                    return (True, f"🎉 JACKPOT! You won 🪙 {amount} coins!")

                elif chosen_prize_type == 'common_coins':
                    amount = random.randint(50, 250)
                    description = "Mystery Box Reward"
                    # --- FIX: Manually update coins and log transaction inside this single transaction ---
                    conn.execute(
                        text("UPDATE user_profiles SET coins = COALESCE(coins, 0) + :amount WHERE username = :username"),
                        {"amount": amount, "username": username}
                    )
                    conn.execute(
                        text("INSERT INTO coin_transactions (username, amount, description) VALUES (:u, :a, :d)"),
                        {"u": username, "a": amount, "d": description}
                    )
                    return (True, f"You opened the box and found 🪙 {amount} coins!")

                elif chosen_prize_type == 'tokens':
                    token_type = random.choice(['hint_tokens', 'fifty_fifty_tokens', 'skip_question_tokens'])
                    amount = random.randint(2, 3)
                    token_name = token_type.replace('_', ' ').replace('tokens', ' Token(s)').title()
                    
                    conn.execute(
                        text(f"UPDATE user_profiles SET {token_type} = COALESCE({token_type}, 0) + :amount WHERE username = :username"),
                        {"amount": amount, "username": username}
                    )
                    return (True, f"Nice! You received {amount} x {token_name}!")
                
                elif chosen_prize_type == 'cosmetic':
                    all_cosmetics = list(COSMETIC_ITEMS['Borders'].keys()) + list(COSMETIC_ITEMS['Name Effects'].keys())
                    owned_cosmetics = profile.get('unlocked_cosmetics') or []
                    
                    unowned_cosmetics = [item for item in all_cosmetics if item not in owned_cosmetics]
                    
                    if not unowned_cosmetics:
                        # Consolation prize if they own everything
                        amount = 500
                        description = "Mystery Box (Consolation Prize)"
                        # --- FIX: Manually update coins and log transaction inside this single transaction ---
                        conn.execute(
                            text("UPDATE user_profiles SET coins = COALESCE(coins, 0) + :amount WHERE username = :username"),
                            {"amount": amount, "username": username}
                        )
                        conn.execute(
                            text("INSERT INTO coin_transactions (username, amount, description) VALUES (:u, :a, :d)"),
                            {"u": username, "a": amount, "d": description}
                        )
                        return (True, f"You own all the cosmetics! As a thank you, here are 🪙 {amount} coins!")
                    else:
                        won_item_id = random.choice(unowned_cosmetics)
                        all_items = {**COSMETIC_ITEMS['Borders'], **COSMETIC_ITEMS['Name Effects']}
                        won_item_name = all_items[won_item_id]['name']

                        conn.execute(
                            text("UPDATE user_profiles SET unlocked_cosmetics = array_append(unlocked_cosmetics, :item) WHERE username = :username"),
                            {"item": won_item_id, "username": username}
                        )
                        return (True, f"🎁 RARE ITEM! You unlocked the permanent cosmetic: {won_item_name}!")

            except Exception as e:
                # The transaction will automatically roll back on any error
                print(f"Mystery box failed for {username}: {e}")
                return (False, "An unexpected error occurred. Please try again.")

def purchase_gift_for_user(sender, recipient, item_id, item_details):
    """
    Securely handles the purchase of an item as a gift for another user.
    Returns (True, "Success Message") or (False, "Error Message").
    """
    cost = item_details['cost']
    item_name = item_details['name']

    if sender == recipient:
        return (False, "You cannot send a gift to yourself.")

    with engine.connect() as conn:
        with conn.begin():  # Start a single, safe transaction
            try:
                # 1. Verify recipient exists
                recipient_profile = conn.execute(
                    text("SELECT unlocked_cosmetics FROM user_profiles WHERE username = :username"),
                    {"username": recipient}
                ).mappings().first()
                if not recipient_profile:
                    return (False, f"User '{recipient}' does not exist.")

                # 2. Check if recipient already owns a permanent item
                if 'border' in item_id or 'effect' in item_id:
                    owned = recipient_profile.get('unlocked_cosmetics') or []
                    if item_id in owned:
                        return (False, f"{recipient} already owns the {item_name}.")

                # 3. Check sender's balance and lock their row
                sender_balance = conn.execute(
                    text("SELECT coins FROM user_profiles WHERE username = :username FOR UPDATE"),
                    {"username": sender}
                ).scalar_one_or_none() or 0

                if sender_balance < cost:
                    return (False, "You do not have enough coins to send this gift.")

                # 4. Process the transaction
                # A. Deduct coins from sender
                conn.execute(
                    text("UPDATE user_profiles SET coins = coins - :cost WHERE username = :username"),
                    {"cost": cost, "username": sender}
                )
                conn.execute(
                    text("INSERT INTO coin_transactions (username, amount, description) VALUES (:u, :a, :d)"),
                    {"u": sender, "a": -cost, "d": f"Gifted '{item_name}' to {recipient}"}
                )

                # B. Grant the item to the recipient
                if 'token' in item_id or 'lifeline' in item_id or 'booster' in item_id or 'box' in item_id:
                    # Handle consumable items
                    col_name = item_details['db_column']
                    conn.execute(
                        text(f"UPDATE user_profiles SET {col_name} = COALESCE({col_name}, 0) + 1 WHERE username = :username"),
                        {"username": recipient}
                    )
                else: # Handle permanent cosmetics
                    conn.execute(
                        text("UPDATE user_profiles SET unlocked_cosmetics = array_append(unlocked_cosmetics, :item) WHERE username = :username"),
                        {"item": item_id, "username": recipient}
                    )
                
                conn.execute(
                    text("INSERT INTO coin_transactions (username, amount, description) VALUES (:u, :a, :d)"),
                    {"u": recipient, "a": 0, "d": f"Received '{item_name}' as a gift from {sender}"}
                )

                return (True, f"Success! You sent {item_name} to {recipient}.")

            except Exception as e:
                print(f"Gifting failed: {e}")
                return (False, "An unexpected error occurred during the transaction.")

def transfer_coins(sender_username, recipient_username, amount):
    """
    Securely transfers coins from one user to another.
    Returns (True, "Success Message") or (False, "Error Message").
    """
    if sender_username == recipient_username:
        return (False, "You cannot gift coins to yourself.")
    if amount <= 0:
        return (False, "Gift amount must be positive.")

    with engine.connect() as conn:
        with conn.begin(): # Start a single transaction for the whole transfer
            try:
                # Check if recipient exists
                recipient_exists = conn.execute(
                    text("SELECT 1 FROM users WHERE username = :username"),
                    {"username": recipient_username}
                ).first()
                if not recipient_exists:
                    return (False, f"User '{recipient_username}' does not exist.")

                # Check sender's balance and lock the row to prevent race conditions
                sender_balance = conn.execute(
                    text("SELECT coins FROM user_profiles WHERE username = :username FOR UPDATE"),
                    {"username": sender_username}
                ).scalar_one_or_none() or 0

                if sender_balance < amount:
                    return (False, "You do not have enough coins to send this gift.")

                # Perform the transfer
                # 1. Subtract from sender
                update_sender_query = text("UPDATE user_profiles SET coins = coins - :amount WHERE username = :username")
                conn.execute(update_sender_query, {"amount": amount, "username": sender_username})
                
                # 2. Add to recipient (using the robust COALESCE method)
                update_recipient_query = text("UPDATE user_profiles SET coins = COALESCE(coins, 0) + :amount WHERE username = :username")
                conn.execute(update_recipient_query, {"amount": amount, "username": recipient_username})
                
                # 3. Log both sides of the transaction
                log_sender_query = text("INSERT INTO coin_transactions (username, amount, description) VALUES (:u, :a, :d)")
                conn.execute(log_sender_query, {"u": sender_username, "a": -amount, "d": f"Gift sent to {recipient_username}"})
                
                log_recipient_query = text("INSERT INTO coin_transactions (username, amount, description) VALUES (:u, :a, :d)")
                conn.execute(log_recipient_query, {"u": recipient_username, "a": amount, "d": f"Gift received from {sender_username}"})

                return (True, f"You successfully sent {amount} coins to {recipient_username}!")

            except Exception as e:
                # The transaction will automatically roll back on any error
                print(f"Coin transfer failed: {e}")
                return (False, "An unexpected error occurred.")

def use_hint_token(username):
    """Subtracts one hint token from a user's profile."""
    with engine.connect() as conn:
        with conn.begin(): # Start a transaction
            # First, check if the user has a token to spend
            current_tokens = conn.execute(
                text("SELECT hint_tokens FROM user_profiles WHERE username = :username"),
                {"username": username}
            ).scalar_one_or_none() or 0

            if current_tokens > 0:
                # Subtract one token
                conn.execute(
                    text("UPDATE user_profiles SET hint_tokens = hint_tokens - 1 WHERE username = :username"),
                    {"username": username}
                )
                # We log the usage here, within the same transaction, with 0 coins
                conn.execute(
                    text("INSERT INTO coin_transactions (username, amount, description) VALUES (:u, 0, 'Used Hint Token')"),
                    {"u": username}
                )
                return True
            else:
                return False

def use_fifty_fifty_token(username):
    """Subtracts one 50/50 token from a user's profile."""
    with engine.connect() as conn:
        with conn.begin(): # Start a transaction
            current_tokens = conn.execute(
                text("SELECT fifty_fifty_tokens FROM user_profiles WHERE username = :username"),
                {"username": username}
            ).scalar_one_or_none() or 0

            if current_tokens > 0:
                conn.execute(
                    text("UPDATE user_profiles SET fifty_fifty_tokens = fifty_fifty_tokens - 1 WHERE username = :username"),
                    {"username": username}
                )
                conn.execute(
                    text("INSERT INTO coin_transactions (username, amount, description) VALUES (:u, 0, 'Used 50/50 Lifeline')"),
                    {"u": username}
                )
                return True
            else:
                return False

def use_skip_question_token(username):
    """Subtracts one skip question token from a user's profile."""
    with engine.connect() as conn:
        with conn.begin(): # Start a transaction
            current_tokens = conn.execute(
                text("SELECT skip_question_tokens FROM user_profiles WHERE username = :username"),
                {"username": username}
            ).scalar_one_or_none() or 0

            if current_tokens > 0:
                conn.execute(
                    text("UPDATE user_profiles SET skip_question_tokens = skip_question_tokens - 1 WHERE username = :username"),
                    {"username": username}
                )
                return True
            else:
                return False

def is_double_coins_active(username):
    """Checks if a user's double coins booster is currently active."""
    with engine.connect() as conn:
        expires_at = conn.execute(
            text("SELECT double_coins_expires_at FROM user_profiles WHERE username = :username"),
            {"username": username}
        ).scalar_one_or_none()

        if expires_at and expires_at > datetime.now(expires_at.tzinfo):
            return True
        return False

# --- END OF NEW FUNCTION ---

# --- END OF ADAPTIVE LEARNING FUNCTIONS ---


# ADD THESE THREE NEW FUNCTIONS

def check_and_award_achievements(username, topic):
    """Checks all achievement conditions for a user and awards them if met."""
    with engine.connect() as conn:
        existing_achievements_query = text("SELECT achievement_name FROM user_achievements WHERE username = :username")
        existing_set = {row[0] for row in conn.execute(existing_achievements_query, {"username": username}).fetchall()}
        
        # --- Achievement 1: "First Step" (Take 1 quiz) ---
        if "First Step" not in existing_set:
            conn.execute(text("INSERT INTO user_achievements (username, achievement_name, badge_icon) VALUES (:u, 'First Step', '👟')"), {"u": username})
            st.session_state.achievement_unlocked_toast = "First Step"
            existing_set.add("First Step")
            # --- NEW COIN REWARD LOGIC ---
            update_coin_balance(username, 100, "Achievement Unlocked: First Step")

        # --- Achievement 2: "Century Scorer" (Get 100 total correct answers) ---
        if "Century Scorer" not in existing_set:
            total_score = conn.execute(text("SELECT SUM(score) FROM quiz_results WHERE username = :u"), {"u": username}).scalar_one() or 0
            if total_score >= 100:
                conn.execute(text("INSERT INTO user_achievements (username, achievement_name, badge_icon) VALUES (:u, 'Century Scorer', '💯')"), {"u": username})
                st.session_state.achievement_unlocked_toast = "Century Scorer"
                existing_set.add("Century Scorer")
                # --- NEW COIN REWARD LOGIC ---
                update_coin_balance(username, 100, "Achievement Unlocked: Century Scorer")

        # --- Achievement 3: "Topic Master" (Get 25 correct answers in a specific topic) ---
        achievement_name = f"{topic} Master"
        if achievement_name not in existing_set:
            topic_score = conn.execute(text("SELECT SUM(score) FROM quiz_results WHERE username = :u AND topic = :t"), {"u": username, "t": topic}).scalar_one() or 0
            if topic_score >= 25:
                conn.execute(text("INSERT INTO user_achievements (username, achievement_name, badge_icon) VALUES (:u, :n, '🎓')"), {"u": username, "n": achievement_name})
                st.session_state.achievement_unlocked_toast = achievement_name
                # --- NEW COIN REWARD LOGIC ---
                update_coin_balance(username, 100, f"Achievement Unlocked: {achievement_name}")

        conn.commit()
def get_user_achievements(username):
    """Fetches all achievements unlocked by a user."""
    with engine.connect() as conn:
        query = text("SELECT achievement_name, badge_icon, unlocked_at FROM user_achievements WHERE username = :username ORDER BY unlocked_at DESC")
        result = conn.execute(query, {"username": username}).mappings().fetchall()
        return [dict(row) for row in result]

def _check_and_award_perfect_score_bonus(username, topic):
    """
    Checks if a user has the 'Perfect Score' achievement for a topic.
    If not, it awards the achievement and returns True (eligible for bonus).
    If they do, it returns False (not eligible for bonus).
    """
    achievement_name = f"Perfect Score: {topic}"
    badge_icon = "🎯"

    # First, check if the user already has this specific achievement
    with engine.connect() as conn:
        check_query = text("""
            SELECT 1 FROM user_achievements 
            WHERE username = :username AND achievement_name = :achievement_name
        """)
        exists = conn.execute(check_query, {"username": username, "achievement_name": achievement_name}).first()

    if not exists:
        # If the achievement does not exist, award it.
        award_achievement_to_user(username, achievement_name, badge_icon)
        # Return True because this is the first time, and they should get the bonus.
        return True
    else:
        # If they already have the achievement, they are not eligible for the bonus.
        return False

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

def _generate_pascal_data(n):
    """
    Generates Pascal's triangle up to row n.
    Returns a formatted string for display and the last row as a list for calculations.
    """
    if n > 10: n = 10  # Cap at row 10 to keep the display clean
    
    triangle = []
    row = [1]
    for _ in range(n + 1):
        triangle.append(row)
        row = [x + y for x, y in zip([0] + row, row + [0])]
    
    last_row = triangle[-1]
    
    # Format the triangle into a centered, monospaced string
    max_len = len(" ".join(map(str, last_row)))
    triangle_str = "```\n"  # Start of a Markdown code block for monospacing
    for r in triangle:
        row_str = " ".join(map(str, r))
        triangle_str += row_str.center(max_len) + "\n"
    triangle_str += "```"  # End of the code block
    
    return triangle_str, last_row


def _generate_user_pill_html(username):
    """Generates a stylish 'pill' containing a user's avatar and name."""
    initial = username[0].upper()
    hash_val = int(hashlib.md5(username.encode()).hexdigest(), 16)
    hue = hash_val % 360
    
    # Styles for the container pill
    pill_style = f"""
        display: inline-flex;
        align-items: center;
        background-color: #e9ecef;
        border-radius: 16px;
        padding: 4px 8px 4px 4px;
        margin-right: 8px;
        font-size: 14px;
        color: #495057;
        font-weight: 500;
    """
    
    # Styles for the avatar circle inside the pill
    avatar_style = f"""
        display: flex;
        align-items: center;
        justify-content: center;
        width: 24px;
        height: 24px;
        border-radius: 50%;
        background-color: hsl({hue}, 70%, 80%);
        color: hsl({hue}, 70%, 25%);
        font-weight: bold;
        margin-right: 6px;
    """
    
    return f'<div style="{pill_style}"><div style="{avatar_style}">{initial}</div>{username}</div>'


# Paste this new function after _generate_user_pill_html

def _poly_to_str(coeffs):
    """Converts a list of polynomial coefficients into a LaTeX string."""
    poly_parts = []
    for i, c in enumerate(coeffs):
        if c == 0: continue
        power = len(coeffs) - 1 - i
        
        # Handle coefficient part
        if power > 0 and abs(c) == 1:
            coeff_str = "-" if c == -1 else ""
        else:
            coeff_str = str(c) if i == 0 else f"+ {c}" if c > 0 else f"- {abs(c)}"
        
        # Handle variable part
        if power == 0:
            var_part = ""
        elif power == 1:
            var_part = "x"
        else:
            var_part = f"x^{{{power}}}"
            
        poly_parts.append(f"{coeff_str}{var_part}")
        
    return " ".join(poly_parts).lstrip('+ ').replace("+ -", "- ")
# --- FULLY IMPLEMENTED QUESTION GENERATION ENGINE (12 TOPICS) ---

def _generate_sets_question(difficulty="Medium"):
    """Generates a Sets question based on the detailed, multi-level syllabus."""

    if difficulty == "Easy":
        q_type = random.choice(['notation_cardinality', 'basic_ops', 'total_subsets'])
    elif difficulty == "Medium":
        q_type = random.choice(['complement_difference', 'proper_subsets', 'venn_two', 'symmetric_difference'])
    else: # Hard
        q_type = random.choice(['set_laws', 'venn_three', 'power_sets', 'sets_probability'])

    question, answer, hint, explanation = "", "", "", ""
    options = set()
    universal_set = set(range(1, 21))

    # (The code for Easy questions and other question types remains unchanged)
    if q_type == 'notation_cardinality':
        set_a = set(random.sample(range(1, 30), k=random.randint(4, 7)))
        phrasing = random.choice([
            f"What is the cardinality of the set $A = {set_a}$?",
            f"For the set $A = {set_a}$, find $n(A)$.",
            f"How many distinct elements are in the set $A = {set_a}$?"
        ])
        question = phrasing
        answer = str(len(set_a))
        hint = "The cardinality of a set, denoted n(A) or |A|, is the number of elements in the set."
        explanation = f"To find the cardinality, we count the number of distinct elements in the set A. The set has **{answer}** elements."
        options = {answer, str(len(set_a) + 1), str(len(set_a) - 1), str(sum(set_a))}

    elif q_type == 'basic_ops':
        set_a = set(random.sample(range(1, 15), k=random.randint(3, 5)))
        set_b = set(random.sample(range(1, 15), k=random.randint(3, 5)))
        op, sym = random.choice([('union', '\\cup'), ('intersection', '\\cap')])
        question = f"Given $A = {set_a}$ and $B = {set_b}$, find $A {sym} B$."
        res = set_a.union(set_b) if op == 'union' else set_a.intersection(set_b)
        answer = str(res) if res else "$\\emptyset$"
        hint = "Union (∪) means 'all elements combined'. Intersection (∩) means 'only elements in common'."
        explanation = f"The {op} of sets A and B results in the set **{answer}**."
        options = {answer, str(set_a.difference(set_b)), str(set_b.difference(set_a))}

    elif q_type == 'total_subsets':
        num_elements = random.randint(3, 6)
        s = set(random.sample(range(1, 100), k=num_elements))
        question = f"How many subsets can be formed from the set $S = {s}$?"
        answer = str(2**num_elements)
        hint = "The formula for the total number of subsets of a set with 'n' elements is $2^n$."
        explanation = f"The set has {num_elements} elements. The total number of subsets is $2^{{{num_elements}}} = {answer}$."
        distractor1 = str(2**num_elements - 1)
        distractor2 = str(num_elements**2)
        options = {answer, distractor1, distractor2}

    elif q_type == 'complement_difference':
        set_a = set(random.sample(range(1, 20), k=random.randint(5, 8)))
        set_b = set(random.sample(range(1, 20), k=random.randint(5, 8)))
        op = random.choice(['complement', 'difference'])
        if op == 'complement':
            question = f"Given the universal set $\mathcal{{U}} = \\{{1, 2, ..., 20\\}}$ and $A = {set_a}$, find the complement, $A'$."
            res = universal_set - set_a
            answer = str(res) if res else "$\\emptyset$"
            hint = "The complement contains all elements in the universal set that are NOT in set A."
            explanation = f"$A' = \mathcal{{U}} - A = {answer}$."
            options = {answer, str(set_a), str(universal_set)}
        else: # Difference
            question = f"Given $A = {set_a}$ and $B = {set_b}$, find the set difference $A - B$."
            res = set_a.difference(set_b)
            answer = str(res) if res else "$\\emptyset$"
            hint = "The difference A - B contains all elements that are in A but NOT in B."
            explanation = f"We take all the elements of set A and remove any that also appear in set B. The result is {answer}."
            options = {answer, str(set_b.difference(set_a)), str(set_a.intersection(set_b))}

    elif q_type == 'proper_subsets':
        num_elements = random.randint(3, 6)
        s = set(random.sample(range(1, 100), k=num_elements))
        question = f"How many **proper** subsets does the set $S = {s}$ have?"
        answer = str(2**num_elements - 1)
        hint = "The number of proper subsets is one less than the total number of subsets ($2^n - 1$)."
        explanation = f"The total number of subsets is $2^{{{num_elements}}} = {2**num_elements}$. A proper subset is any subset except the set itself, so we subtract 1, giving **{answer}**."
        options = {answer, str(2**num_elements), str(num_elements - 1)}

    # --- 2.3: 2-Set Venn Diagram Problems (Medium) ---
    elif q_type == 'venn_two':
        total, a_val, b_val, both = random.randint(80, 120), random.randint(30, 50), random.randint(30, 50), random.randint(10, 25)
        union = a_val + b_val - both
        neither = total - union
        if neither < 0: return _generate_sets_question(difficulty=difficulty)
        
        # --- THIS IS THE NEW, MASSIVELY EXPANDED PHRASING BANK ---
        student_names = ["Joana","Happy","Doris","Gladys","Grace","Wassado","Jemima","Clementina","Bertha","Delight","Ampofo", "Julia", "Albert", "Confidence", "David", "Edmond", "Nuzrat", "Rawlings", "Georgina", "Isaac", "Korbey", "Wisdom", "Stephen", "Nnyibi", "Martin", "Yussif", "Awake", "Ferguson", "Grace", "Bernice", "Lazarus", "Agbey", "Emic", "Melody", "Christable", "Benedicta", "Irene"]
        local_schools = ["Ho Mawuli","Mawuko Girls","Prang SHS","Sunyani SHS","Keta SHTS","Jinijini SHS","Krachi SHS","Ola Girls","Kajaji SHS", "Bassa Community SHS", "Kwame Danso SHS", "Atebubu SHS"]
        student_1, student_2 = random.sample(student_names, 2)
        school_1, school_2 = random.sample(local_schools, 2)

        contexts = [
            (f"like {student_1}'s favourite food, Waakye", f"like {student_2}'s favourite, Jollof rice", "customers", "at a chop bar in Kojokrom"),
            ("play football", "play volleyball", "students", f"at {school_1}"),
            ("speak Twi", "speak Bono", "traders", "at the Kajaji Market"),
            ("passed Elective Maths", "passed Core Maths", "WASSCE candidates", "at a learning center in the Bono East Region"),
            ("study Chemistry", "study Physics", "SHS students", f"in {school_2}"),
            ("use Instagram", "use TikTok", "teenagers", "in a focus group in Atebubu"),
            ("eat Banku", "eat Kenkey", "patrons", "at a restaurant in Kwame Danso"),
            ("listen to Afrobeats", "listen to Highlife music", "music fans", "at a local festival"),
            ("use MTN", "use Vodafone", "mobile phone users", "in a small town near Kajaji"),
            ("take a Trotro", "take an Uber", "commuters", "in Kumasi"),
            ("own a cat", "own a dog", "pet owners", "in a neighborhood in Accra"),
            ("watch Ghanaian movies", "watch Nigerian movies", "viewers", "surveyed last month"),
            ("shop at Melcom", "shop at Shoprite", "customers", "at the mall"),
            (f"support {student_1}'s team, Asante Kotoko", f"support {student_2}'s team, Hearts of Oak", "football fans", "in a survey")
        ]
        item_a, item_b, group, context = random.choice(contexts)
        
        phrasing, unknown = random.choice([
            (f"Of {total} {group} {context}, {a_val} {item_a} and {b_val} {item_b}. If {both} do both, how many do neither?", "neither"),
            (f"Of {total} {group} {context}, {a_val} {item_a} and {b_val} {item_b}. If {neither} do neither, how many do both?", "both")
        ])
        # --- END OF THE PHRASING BANK ---
        
        question = phrasing
        answer = str(neither) if unknown == "neither" else str(both)
        hint = "Use the formula $n(Total) = n(A) + n(B) - n(A \\cap B) + n(Neither)$ or draw a Venn diagram."
        explanation = f"We have $n(A) = {a_val}$, $n(B) = {b_val}$, and $n(A \\cap B) = {both}$.\nThe number who are in at least one set is $n(A \\cup B) = n(A) + n(B) - n(A \\cap B) = {a_val} + {b_val} - {both} = {union}$.\nThe number in neither set is $n(Total) - n(A \\cup B) = {total} - {union} = {neither}$."
        
        a_only = a_val - both
        b_only = b_val - both
        options = {str(neither), str(both), str(a_only), str(b_only)}
        
        return {"question": question, "options": list(options), "answer": answer, "hint": hint, "explanation": explanation, "difficulty": difficulty}

    # --- 3.1: Symmetric Difference (Hard) ---
    elif q_type == 'symmetric_difference':
        set_a = set(random.sample(range(1, 20), k=random.randint(4, 6)))
        set_b = set(random.sample(range(1, 20), k=random.randint(4, 6)))
        question = f"Given $A = {set_a}$ and $B = {set_b}$, find the symmetric difference $A \\Delta B$."
        res = set_a.symmetric_difference(set_b)
        answer = str(res) if res else "$\\emptyset$"
        hint = "Symmetric difference contains elements in A or in B, but NOT in both. It can be calculated as $(A \\cup B) - (A \\cap B)$."
        explanation = f"The union is $A \\cup B = {set_a.union(set_b)}$.\nThe intersection is $A \\cap B = {set_a.intersection(set_b)}$.\nThe difference between these two sets is **{answer}**."
        options = {answer, str(set_a.union(set_b)), str(set_a.intersection(set_b)), str(set_a.difference(set_b))}

    # --- 3.2: Laws of Algebra of Sets (Hard) ---
    elif q_type == 'set_laws':
        law, answer = random.choice([
            ("De Morgan's Law states that $(A \\cup B)'$ is equivalent to:", "$A' \\cap B'$"),
            ("The Distributive Law states that $A \\cap (B \\cup C)$ is equivalent to:", "$(A \\cap B) \\cup (A \\cap C)$"),
            ("The Complement Law states that $A \\cup A'$ is equal to:", "$\\mathcal{U}$ (the universal set)"),
            ("The Associative Law states that $(A \\cup B) \\cup C$ is equivalent to:", "$A \\cup (B \\cup C)$")
        ])
        question = law
        hint = "Recall the fundamental laws governing set operations."
        explanation = f"This is a direct application of the standard laws of the algebra of sets. The correct identity is **{answer}**."
        if "De Morgan" in law: options = {"$A' \\cap B'$", "$A' \\cup B'$", "$A \\cap B'"}
        elif "Distributive" in law: options = {"$(A \\cap B) \\cup (A \\cap C)$", "$(A \\cup B) \\cap (A \\cup C)$", "$A \\cup (B \\cap C)$"}
        else: options = {"$\\mathcal{U}$ (the universal set)", "$\\emptyset$", "A"}

    # --- 3.3: 3-Set Venn Diagram Problems (Hard) ---
    elif q_type == 'venn_three':
        regions = [random.randint(5, 15) for _ in range(7)]
        r1, r2, r3, r12, r23, r13, r123 = regions
        
        # --- THIS IS THE NEW, MASSIVELY EXPANDED PHRASING BANK ---
        student_names = ["Joana","Happy","Doris","Gladys","Grace","Wassado","Jemima","Clementina","Bertha","Delight","Ampofo", "Julia", "Albert", "Confidence", "David", "Edmond", "Nuzrat", "Rawlings", "Georgina", "Isaac", "Korbey", "Wisdom", "Stephen", "Nnyibi", "Martin", "Yussif", "Awake", "Ferguson", "Grace", "Bernice", "Lazarus", "Agbey", "Emic", "Melody", "Christable", "Benedicta", "Irene"]
        local_schools = ["Ho Mawuli","Mawuko Girls","Prang SHS","Sunyani SHS","Keta SHTS","Jinijini SHS","Krachi SHS","Ola Girls","Kajaji SHS", "Bassa Community SHS", "Kwame Danso SHS", "Atebubu SHS"]
        student_1, student_2, student_3 = random.sample(student_names, 3)
        school_1 = random.choice(local_schools)
        
        contexts = [
            ("students", "Maths", "Science", "English", f"at {school_1}"),
            ("tourists", "Kakum National Park", "Cape Coast Castle", "Elmina Castle", "surveyed at a hotel"),
            ("farmers", "growing maize", "growing cassava", "growing yam", "in the Bono East Region"),
            ("shoppers", "buying Milo", "buying Nido", "buying Peak Milk", "at the Kajaji Market"),
            (f"friends of {student_1}", f"watching {student_2}'s favourite show", f"listening to {student_3}'s favourite music", "playing video games", "in a survey"),
            ("commuters", "taking a Trotro", "riding an Okada", "taking a taxi", "in a busy city"),
            ("patients", "having a headache", "having a cough", "having a fever", "at a clinic in Kojokrom")
        ]
        group, item_a, item_b, item_c, context = random.choice(contexts)
        # --- END OF THE PHRASING BANK ---
        
        total_A = r1 + r12 + r13 + r123
        total_B = r2 + r12 + r23 + r123
        total_C = r3 + r13 + r23 + r123
        
        asked_for, answer_val = random.choice([
            (f"liked **only** {item_a}", r1),
            (f"liked **only** {item_b}", r2),
            (f"liked **only** {item_c}", r3)
        ])

        question = (f"A survey of {group} {context} found the following:\n"
                    f"- {total_A} liked {item_a}\n"
                    f"- {total_B} liked {item_b}\n"
                    f"- {total_C} liked {item_c}\n"
                    f"- {r12+r123} liked {item_a} and {item_b}\n"
                    f"- {r13+r123} liked {item_a} and {item_c}\n"
                    f"- {r23+r123} liked {item_b} and {item_c}\n"
                    f"- {r123} liked all three.\n\n"
                    f"How many {group} {asked_for}?")
        answer = str(answer_val)
        hint = "Draw a three-circle Venn diagram. Start by filling in the center region (all three items) and work your way outwards by subtracting."
        explanation = (f"1. Start with the intersection of all three: ${r123}$.\n"
                       f"2. Find the 'two-item only' regions by subtracting the center: e.g., '{item_a} and {item_b} only' is ${r12+r123} - {r123} = {r12}$.\n"
                       f"3. Finally, find the 'only' regions by subtracting all other overlaps from the total for that item. For example, 'only {item_a}' is ${total_A} - ({r12} + {r13} + {r123}) = {r1}$.")
        
        options = {str(r1), str(r2), str(r3), str(r12), str(r13), str(r23), str(r123)}
        options.add(answer) 
        
        return {"question": question, "options": _finalize_options(options), "answer": answer, "hint": hint, "explanation": explanation, "difficulty": difficulty}

    # --- 3.4: Power Sets (Hard) ---
    elif q_type == 'power_sets':
        s_elements = sorted(random.sample(range(1, 10), 3))
        s = set(s_elements)
        answer = f"$\\{{\\emptyset, \\{{{s_elements[0]}\\}}, \\{{{s_elements[1]}\\}}, \\{{{s_elements[2]}\\}}, \\{{{s_elements[0]}, {s_elements[1]}\\}}, \\{{{s_elements[0]}, {s_elements[2]}\\}}, \\{{{s_elements[1]}, {s_elements[2]}\\}}, \\{{{s_elements[0]}, {s_elements[1]}, {s_elements[2]}\\}}\\}}"
        question = f"What is the Power Set, $\mathcal{{P}}(S)$, of the set $S = {s}$?"
        hint = "The Power Set is the set of all possible subsets of S, including the empty set and the set S itself."
        explanation = f"A set with 3 elements has $2^3 = 8$ subsets. We must list all of them, from the empty set to the full set, to form the Power Set. The correct listing is **{answer}**."
        options = {answer, f"${2**len(s)}$", f"$\\{{\\{{{s_elements[0]}\\}}, \\{{{s_elements[1]}\\}}, \\{{{s_elements[2]}\\}}\\}}"}

    # --- 3.5: Sets and Probability (Hard) ---
    elif q_type == 'sets_probability':
        total = 100
        a, b, intersection = random.randint(30, 50), random.randint(20, 40), random.randint(10, 20)
        prob_a = Fraction(a, total); prob_b = Fraction(b, total); prob_intersect = Fraction(intersection, total)
        prob_union = prob_a + prob_b - prob_intersect
        question = f"In a group of students, the probability that a student speaks Twi is ${prob_a.numerator}/{prob_a.denominator}$ and the probability that a student speaks Ga is ${prob_b.numerator}/{prob_b.denominator}$. If the probability that a student speaks both is ${prob_intersect.numerator}/{prob_intersect.denominator}$, what is the probability that a student speaks either Twi or Ga?"
        answer = f"${_get_fraction_latex_code(prob_union)}$"
        hint = "Use the formula for the probability of the union of two events: $P(A \\cup B) = P(A) + P(B) - P(A \\cap B)$."
        explanation = f"Let T be the event of speaking Twi and G be the event of speaking Ga.\n$P(T \\cup G) = P(T) + P(G) - P(T \\cap G)$\n$P(T \\cup G) = {_get_fraction_latex_code(prob_a)} + {_get_fraction_latex_code(prob_b)} - {_get_fraction_latex_code(prob_intersect)} = {_get_fraction_latex_code(prob_union)}$."
        options = {answer, f"${_get_fraction_latex_code(prob_a+prob_b)}$", f"${_get_fraction_latex_code(prob_intersect)}$"}

    final_options = _finalize_options(options, default_type="set_str")
    return {"question": question, "options": final_options, "answer": answer, "hint": hint, "explanation": explanation, "difficulty": difficulty}

# --- END: REVISED AND FINAL FUNCTION _generate_sets_question ---
def _generate_percentages_question(difficulty="Medium"):
    """Generates a Percentages question based on difficulty, preserving all original sub-types."""
    
    if difficulty == "Easy":
        q_type = random.choice(['conversion', 'percent_of'])
    elif difficulty == "Medium":
        q_type = random.choice(['express_as_percent', 'percent_change', 'profit_loss'])
    else: # Hard
        q_type = random.choice(['reverse_percent', 'successive_change', 'percent_error'])

    question, answer, hint, explanation = "", "", "", ""
    options = set()

    # --- Easy Questions ---
    if q_type == 'conversion':
        frac = Fraction(random.randint(1, 4), random.choice([5, 8, 10, 20, 25]))
        percent = frac.numerator / frac.denominator * 100
        decimal = frac.numerator / frac.denominator
        start_form, end_form, ans_val = random.choice([
            (f"${_get_fraction_latex_code(frac)}$", "a percentage", f"{percent:.0f}%"),
            (f"{decimal}", "a percentage", f"{percent:.0f}%"),
            (f"{percent:.0f}%", "a decimal", f"{decimal}")
        ])
        question = f"Express {start_form} as {end_form}."
        answer = str(ans_val)
        hint = "To convert from a fraction/decimal to a percentage, multiply by 100. To convert from a percentage to a decimal, divide by 100."
        explanation = f"The conversion from {start_form} to {end_form} results in {answer}$."
        options = {answer, f"{decimal*10}%", f"{percent/10}"}

    elif q_type == 'percent_of':
        percent, number = random.randint(1, 19)*5, random.randint(10, 50)*10
        question = f"Calculate {percent}% of GHS {number:.2f}."
        answer = f"GHS {(percent/100)*number:.2f}"
        hint = "Convert the percentage to a decimal (divide by 100) and then multiply."
        explanation = f"{percent}% of {number} is equivalent to ${percent/100} \\times {number} = {float(answer.split(' ')[1]):.2f}$."
        options = {answer, f"GHS {percent*number/10:.2f}", f"GHS {number/percent:.2f}"}

    # --- Medium Questions ---
    elif q_type == 'express_as_percent':
        part, whole = random.randint(10, 40), random.randint(50, 100)
        question = f"In a school in Accra, {part} students out of {whole} are boys. What percentage of the students are boys?"
        answer = f"{(part/whole)*100:.1f}%"
        hint = "Use the formula: (Part / Whole) * 100%."
        explanation = f"The percentage is calculated as $(\\frac{{{part}}}{{{whole}}}) \\times 100\\% = {answer}$."
        options = {answer, f"{(whole/part)*100:.1f}%", f"{part*100/whole:.0f}%"}

    elif q_type == 'percent_change':
        old, new = random.randint(50, 200), random.randint(201, 400)
        question = f"The price of a textbook increased from GHS {old} to GHS {new}. Find the percentage increase."
        ans_val = ((new - old) / old) * 100
        answer = f"{ans_val:.1f}%"
        hint = "Use the formula: (New Value - Old Value) / Old Value * 100%."
        explanation = f"Change = ${new} - {old} = {new-old}$.\n\nPercent Change = $(\\frac{{{new-old}}}{{{old}}}) \\times 100 = {answer}$."
        options = {answer, f"{((new-old)/new)*100:.1f}%", f"{ans_val:.0f}%"}

    elif q_type == 'profit_loss':
        cost, selling = random.randint(100, 200), random.randint(201, 300)
        question = f"A trader in Kumasi bought an item for GHS {cost} and sold it for GHS {selling}. Calculate the profit percent."
        profit = selling - cost
        ans_val = (profit / cost) * 100
        answer = f"{ans_val:.1f}%"
        hint = "Profit Percent = (Profit / Cost Price) * 100%."
        explanation = f"Profit = ${selling} - {cost} = {profit}$.\n\nProfit Percent = $(\\frac{{{profit}}}{{{cost}}}) \\times 100 = {answer}$."
        options = {answer, f"{(profit/selling)*100:.1f}%", f"{ans_val:.0f}%"}

    # --- Hard Questions ---
    elif q_type == 'reverse_percent':
        original_price = random.randint(100, 400)
        discount = random.randint(1, 8) * 5 # 5, 10, 15... 40
        final_price = original_price * (1 - discount/100)
        question = f"After a {discount}% discount, a shirt costs GHS {final_price:.2f}. What was the original price?"
        answer = f"GHS {original_price:.2f}"
        hint = f"The final price represents {100-discount}% of the original price. Let the original price be P and solve for it."
        explanation = f"Let P be the original price.\n$P \\times (1 - \\frac{{{discount}}}{{100}}) = {final_price:.2f}$.\n$P = \\frac{{{final_price:.2f}}}{{1 - {discount/100}}} = {original_price:.2f}$."
        options = {answer, f"GHS {final_price * (1 + discount/100):.2f}", f"GHS {final_price / (1 + discount/100):.2f}"}

    elif q_type == 'successive_change':
        initial_val = 1000
        increase = random.randint(10, 20)
        decrease = random.randint(5, 9)
        val_after_increase = initial_val * (1 + increase/100)
        final_val = val_after_increase * (1 - decrease/100)
        net_change = ((final_val - initial_val) / initial_val) * 100
        question = f"A worker's salary of GHS {initial_val} was increased by {increase}%, and later decreased by {decrease}%. What is the net percentage change in their salary?"
        answer = f"{net_change:.2f}%"
        hint = "Calculate the new salary after the first change, then apply the second change to that new amount. Do not just add or subtract the percentages."
        explanation = f"1. After {increase}% increase: GHS {initial_val} * 1.{increase:02d} = GHS {val_after_increase}.\n2. After {decrease}% decrease: GHS {val_after_increase} * (1 - 0.0{decrease}) = GHS {final_val:.2f}.\n3. Net Change = {final_val - initial_val:.2f}.\n4. Net % Change = (\\frac{{{final_val-initial_val:.2f}}}{{{initial_val}}}) \\times 100 = {answer}$."
        options = {answer, f"{increase-decrease}%", f"{increase-decrease:.2f}%"}

    elif q_type == 'percent_error':
        actual = random.randint(50, 100)
        error = random.randint(1, 5)
        measured = actual + error
        question = f"A length was measured as {measured} cm, but the actual length was {actual} cm. Calculate the percentage error."
        ans_val = (error / actual) * 100
        answer = f"{ans_val:.2f}%"
        hint = "Percentage Error = (Error / Actual Value) * 100%."
        explanation = f"1. Error = Measured - Actual = {measured} - {actual} = {error}.\n2. Percentage Error = (\\frac{{{error}}}{{{actual}}}) \\times 100\\% = {answer}$."
        options = {answer, f"{(error/measured)*100:.2f}%", f"{ans_val:.1f}%"}

    return {"question": question, "options": _finalize_options(options), "answer": answer, "hint": hint, "explanation": explanation, "difficulty": difficulty}

def _generate_fractions_question(difficulty="Medium"):
    """Generates a Fractions question based on difficulty, preserving all original sub-types."""

    if difficulty == "Easy":
        # Simple operations and direct equivalency
        q_type = random.choice(['operation_simple', 'equivalent'])
    elif difficulty == "Medium":
        # Multi-step problems and more complex operations
        q_type = random.choice(['operation_complex', 'bodmas', 'word_problem'])
    else: # Hard
        # Higher-level concepts like conversion, comparison, and complex structures
        q_type = random.choice(['convert_mixed', 'compare', 'complex_fraction'])

    question, answer, hint, explanation = "", "", "", ""
    options = set()

    # --- Easy Questions ---
    if q_type == 'operation_simple':
        f1, f2 = Fraction(random.randint(1, 5), random.randint(2, 6)), Fraction(random.randint(1, 5), random.randint(2, 6))
        op, sym = random.choice([('add', '+'), ('subtract', '-')])
        question = f"Calculate: ${_get_fraction_latex_code(f1)} {sym} ${_get_fraction_latex_code(f2)}$"
        res = f1 + f2 if op == 'add' else f1 - f2
        answer = _format_fraction_text(res)
        hint = "To add or subtract fractions, you must first find a common denominator."
        explanation = f"After finding a common denominator and performing the operation, the result is ${_get_fraction_latex_code(res)}$."
        options = {answer, _format_fraction_text(f1*f2)}

    elif q_type == 'equivalent':
        num, den, multiplier = random.randint(2, 5), random.randint(6, 11), random.randint(2, 5)
        question = f"Find the missing value: $\\frac{{{num}}}{{{den}}} = \\frac{{?}}{{{den*multiplier}}}$"
        answer = str(num * multiplier)
        hint = "To find an equivalent fraction, whatever you multiply the denominator by, you must also multiply the numerator by."
        explanation = f"The denominator was multiplied by {multiplier} (since ${den} \\times {multiplier} = {den*multiplier}$). Therefore, the numerator must also be multiplied by {multiplier}. The missing value is ${num} \\times {multiplier} = {answer}$."
        options = {answer, str(num+multiplier), str(den*multiplier)}

    # --- Medium Questions ---
    elif q_type == 'operation_complex':
        f1, f2 = Fraction(random.randint(1, 10), random.randint(2, 10)), Fraction(random.randint(1, 10), random.randint(2, 10))
        op, sym = random.choice([('multiply', '\\times'), ('divide', '\\div')])
        if op == 'divide' and f2.numerator == 0: f2 = Fraction(1, f2.denominator) # Avoid division by zero
        question = f"Calculate: ${_get_fraction_latex_code(f1)} {sym} {_get_fraction_latex_code(f2)}$"
        res = f1 * f2 if op == 'multiply' else f1 / f2
        answer = _format_fraction_text(res)
        hint = "To multiply, multiply straight across. To divide, invert the second fraction and multiply."
        explanation = f"The result of the calculation is ${_get_fraction_latex_code(res)}$."
        options = {answer, _format_fraction_text(f1+f2)}

    elif q_type == 'bodmas':
        a, b, c = [random.randint(2, 6) for _ in range(3)]
        question = f"Evaluate the expression: $ (\\frac{{1}}{{{a}}} + \\frac{{1}}{{{b}}}) \\times {c} $"
        res = (Fraction(1, a) + Fraction(1, b)) * c
        answer = _format_fraction_text(res)
        hint = "Follow BODMAS/PEMDAS. Solve the operation inside the brackets first."
        explanation = f"1. Solve the bracket: $\\frac{{1}}{{{a}}} + \\frac{{1}}{{{b}}} = \\frac{{{b}+{a}}}{{{a*b}}}$.\n\n2. Multiply by the constant: $\\frac{{{a+b}}}{{{a*b}}} \\times {c} = {_get_fraction_latex_code(res)}$."
        distractor = _format_fraction_text(Fraction(1,a) + Fraction(1,b)*c)
        options = {answer, distractor}

    elif q_type == 'word_problem':
        den = random.choice([3, 4, 5, 8]); num = random.randint(1, den-1); quantity = random.randint(10, 20) * den
        question = f"A student in Accra had {quantity} oranges and gave away $\\frac{{{num}}}{{{den}}}$ of them. How many oranges did the student have left?"
        answer = str(int(quantity * (1-Fraction(num,den))))
        hint = "First, find the fraction of oranges remaining. Then, multiply that fraction by the total number of oranges."
        explanation = f"1. Fraction remaining = $1 - \\frac{{{num}}}{{{den}}} = \\frac{{{den-num}}}{{{den}}}$.\n2. Oranges left = $\\frac{{{den-num}}}{{{den}}} \\times {quantity} = {answer}$."
        options = {answer, str(int(quantity*Fraction(num,den)))}

    # --- Hard Questions ---
    elif q_type == 'convert_mixed':
        whole, num, den = random.randint(1, 5), random.randint(1, 5), random.randint(6, 10)
        improper_num = whole * den + num; improper_frac = Fraction(improper_num, den)
        mixed_num_latex = f"{whole}\\frac{{{num}}}{{{den}}}"
        if random.random() > 0.5:
            question = f"Convert the mixed number ${mixed_num_latex}$ to an improper fraction."
            answer = _format_fraction_text(improper_frac)
            hint = "Multiply the whole number by the denominator, then add the numerator. Keep the same denominator."
            explanation = f"Calculation: $({whole} \\times {den}) + {num} = {improper_num}$. The improper fraction is ${_get_fraction_latex_code(improper_frac)}$."
        else:
            question = f"Convert the improper fraction ${_get_fraction_latex_code(improper_frac)}$ to a mixed number."
            answer = f"${mixed_num_latex}$"
            hint = "Divide the numerator by the denominator. The quotient is the whole number, and the remainder is the new numerator."
            explanation = f"${improper_num} \\div {den} = {whole}$ with a remainder of ${num}$. The mixed number is ${mixed_num_latex}$."
        options = {answer, f"{whole*num+den}/{den}", f"{improper_num}/{num}"}

    elif q_type == 'compare':
        f1 = Fraction(random.randint(1, 4), random.randint(5, 10)); f2 = Fraction(random.randint(1, 4), random.randint(5, 10));
        while f1 == f2: f2 = Fraction(random.randint(1, 4), random.randint(5, 10))
        question = f"Which of the following statements is true?"
        answer = f"${_get_fraction_latex_code(f1)} > {_get_fraction_latex_code(f2)}$" if f1 > f2 else f"${_get_fraction_latex_code(f1)} < {_get_fraction_latex_code(f2)}$"
        hint = "To compare fractions, you can find a common denominator or convert them to decimals."
        explanation = f"${_get_fraction_latex_code(f1)} \\approx {float(f1):.3f}$ and ${_get_fraction_latex_code(f2)} \\approx {float(f2):.3f}$. Therefore, the statement '{answer}' is true."
        options = {answer, f"${_get_fraction_latex_code(f1)} = {_get_fraction_latex_code(f2)}$", f"${_get_fraction_latex_code(f1)} < {_get_fraction_latex_code(f2)}$" if f1 > f2 else f"${_get_fraction_latex_code(f1)} > {_get_fraction_latex_code(f2)}$"}

    elif q_type == 'complex_fraction':
        f1, f2 = Fraction(random.randint(1, 5), random.randint(2, 6)), Fraction(random.randint(1, 5), random.randint(2, 6))
        question = f"Simplify the complex fraction: $\\frac{{{_get_fraction_latex_code(f1)}}}{{{_get_fraction_latex_code(f2)}}}$"
        answer = _format_fraction_text(f1 / f2)
        hint = "This is simply a division problem. Rewrite the complex fraction as (top fraction) ÷ (bottom fraction)."
        inverted_f2_latex = _get_fraction_latex_code(Fraction(f2.denominator, f2.numerator))
        explanation = f"This is equivalent to ${_get_fraction_latex_code(f1)} \\div {_get_fraction_latex_code(f2)}$, which becomes ${_get_fraction_latex_code(f1)} \\times {inverted_f2_latex} = {_get_fraction_latex_code(f1/f2)}$."
        options = {answer, _format_fraction_text(f1*f2), _format_fraction_text(f1+f2)}

    return {"question": question, "options": _finalize_options(options, "fraction"), "answer": answer, "hint": hint, "explanation": explanation, "difficulty": difficulty}
def _generate_indices_question(difficulty="Medium"):
    """Generates an Indices question based on difficulty, preserving all original sub-types."""
    
    if difficulty == "Easy":
        # Basic laws and standard form conversion
        q_type = random.choice(['laws', 'standard_form'])
    elif difficulty == "Medium":
        # Multi-step evaluation and solving with a common base
        q_type = random.choice(['fractional', 'solve_same_base'])
    else: # Hard
        # Requires finding a common base before solving
        q_type = 'solve_different_base'

    question, answer, hint, explanation = "", "", "", ""
    options = set()

    # --- Easy Questions ---
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
        options = {answer, f"${base}^{{{p1+p2}}}$", f"${base}^{{{p1-p2 if p1 > p2 else p2-p1}}}$"}

    elif q_type == 'standard_form':
        num = round(random.uniform(1.0, 9.9), random.randint(2, 4))
        power = random.randint(3, 6)
        decimal_form = f"{num / (10**power):.{power+len(str(int(num)))}f}"
        answer = f"${num} \\times 10^{{-{power}}}$"
        distractors = {f"${num} \\times 10^{{{power}}}$", f"${round(num*10, 2)} \\times 10^{{-{power+1}}}$"}
        question = f"A measurement is recorded as {decimal_form} metres. Express this number in standard form."
        hint = "Standard form is written as $A \\times 10^n$, where $1 \\le A < 10$. Count how many places the decimal point must move."
        explanation = f"To get the number {num} (which is between 1 and 10), we must move the decimal point {power} places to the right. Moving to the right corresponds to a negative exponent. Thus, the standard form is {answer}."
        options = {answer, *distractors}

    # --- Medium Questions ---
    elif q_type == 'fractional':
        base_num = random.choice([4, 8, 9, 16, 27, 64])
        root = 2 if base_num in [4, 9, 16] else 3
        power = random.randint(2, 3)
        question = f"Evaluate: ${base_num}^{{\\frac{{{power}}}{{{root}}}}}$"
        res = int(round((base_num**(1/root))**power))
        answer = str(res)
        hint = "First, find the root of the base number (denominator of the fraction), then apply the power (numerator of the fraction)."
        explanation = f"The expression ${base_num}^{{\\frac{{{power}}}{{{root}}}}}$ means $(\\sqrt[{root}]{{{base_num}}})^{{{power}}}$.\n1. $\\sqrt[{root}]{{{base_num}}} = {int(base_num**(1/root))}$.\n2. $({int(base_num**(1/root))})^{{{power}}} = {res}$."
        options = {answer, str(int(base_num*power/root)), str(int(base_num+power/root))}

    elif q_type == 'solve_same_base':
        base = random.randint(2, 5)
        power = random.randint(2, 4)
        a, b = 2, -1
        while (power - b) % a != 0: power = random.randint(2, 5) # Ensure integer answer
        question = f"Solve for the variable $x$: ${base}^{{{a}x + ({b})}} = {base**power}$"
        answer = _format_fraction_text(Fraction(power - b, a))
        hint = "If the bases on both sides of an equation are the same, you can set the exponents equal to each other."
        explanation = f"1. The equation is ${base}^{{{a}x + ({b})}} = {base**power}$.\n2. Since the bases are equal, equate the exponents: ${a}x + ({b}) = {power}$.\n3. ${a}x = {power-b}$.\n4. $x = \\frac{{{power-b}}}{{{a}}}$."
        options = {answer, str(power), str(power-b)}

    # --- Hard Question ---
    elif q_type == 'solve_different_base':
        problems = [(4, 2, 8, 3, 2), (9, 2, 27, 3, 3), (8, 3, 4, 2, 2)]
        base1, p1, base2, p2, common_base = random.choice(problems)
        k = random.randint(1, 4)
        # Equation: (cb^p1)^x = (cb^p2)^(x-k) => p1*x = p2*x - p2*k => (p1-p2)x = -p2*k
        x_val_frac = Fraction(-p2 * k, p1 - p2)
        # Ensure the problem gives a clean integer answer
        if x_val_frac.denominator != 1:
            return _generate_indices_question(difficulty=difficulty) # Regenerate if not an integer
        x_val = x_val_frac.numerator
        
        question = f"Solve for x in the equation: ${base1}^x = {base2}^{{x-{k}}}$"
        answer = str(x_val)
        hint = "Express both sides of the equation as powers of the same common base."
        explanation = (f"1. The common base for {base1} and {base2} is {common_base}.\n"
                       f"2. Rewrite the equation: $({common_base}^{{{p1}}})^x = ({common_base}^{{{p2}}})^{{x-{k}}}$.\n"
                       f"3. Simplify exponents: ${common_base}^{{{p1}x}} = {common_base}^{{{p2}(x-{k})}}$.\n"
                       f"4. Equate exponents: ${p1}x = {p2}x - {p2*k}$.\n"
                       f"5. Solve for x: $({p1-p2})x = {-p2*k} \\implies x = {x_val}$.")
        options = {answer, str(k), str(x_val + 1), str(x_val -1)}

    return {"question": question, "options": _finalize_options(options), "answer": answer, "hint": hint, "explanation": explanation, "difficulty": difficulty}

# --- START: REVISED FUNCTION _generate_surds_question (Corrected Indentation) ---
# Reason for change: To fix an IndentationError caused by a copy-paste issue. This version has the correct spacing.

def _generate_surds_question(difficulty="Medium"):
    if difficulty == "Easy":
        q_type = random.choice(['identify', 'simplify_single', 'ops_like_surds'])
    elif difficulty == "Medium":
        q_type = random.choice(['ops_unlike_surds', 'expand_single_bracket', 'rationalize_monomial', 'geometry_context'])
    else: # Hard
        q_type = random.choice(['rationalize_complex', 'nested_square_root', 'equality_of_surds', 'quadratic_roots', 'geometry_hard'])

    question, answer, hint, explanation = "", "", "", ""
    options = set()

    # --- 1.1: Identifying Surds (Easy) ---
    if q_type == 'identify':
        perfect_square = random.randint(3, 12)**2
        non_square_base = random.choice([2, 3, 5, 6, 7, 10, 11, 13, 14, 15])
        phrasing = random.choice([
            "Which of the following numbers is a surd?",
            "Identify the irrational number in the form of a surd from the options below.",
            "Which of the following roots cannot be simplified to a rational number?"
        ])
        question = phrasing
        answer = f"$\\sqrt{{{non_square_base}}}$"
        hint = "A surd is an irrational number. If a square root simplifies to a whole number, it is rational, not a surd."
        explanation = f"$\\sqrt{{{perfect_square}}}$ simplifies to {int(math.sqrt(perfect_square))}, which is a rational number. However, $\\sqrt{{{non_square_base}}}$ is a surd."
        options = {answer, f"$\\sqrt{{{perfect_square}}}$", str(random.randint(2,10)), f"$\\frac{{1}}{{2}}$"}

    # --- 1.2: Simplifying Single Surds (Easy) ---
    elif q_type == 'simplify_single':
        p_sq, n = random.choice([(4, 3), (4, 5), (9, 2), (9, 3), (16, 2), (25, 3), (36, 2)])
        num = p_sq * n
        phrasing = random.choice([
            f"Express $\\sqrt{{{num}}}$ in its simplest surd form.",
            f"What is the simplified form of $\\sqrt{{{num}}}$?",
            f"Simplify the expression $\\sqrt{{{num}}}$ completely."
        ])
        question = phrasing
        answer = f"${int(math.sqrt(p_sq))}\\sqrt{{{n}}}$"
        hint = f"Find the largest perfect square that is a factor of {num}."
        explanation = f"To simplify, we find the largest perfect square factor of {num}, which is {p_sq}.\n$\\sqrt{{{num}}} = \\sqrt{{{p_sq} \\times {n}}} = \\sqrt{{{p_sq}}} \\times \\sqrt{{{n}}} = {answer}$."
        distractor1 = f"${n}\\sqrt{{{p_sq}}}$"
        distractor2 = f"${p_sq}\\sqrt{{{n}}}$"
        options = {answer, distractor1, distractor2}

    # --- 1.3: Basic Operations on Like Surds (Easy) ---
    elif q_type == 'ops_like_surds':
        base_surd = random.choice([2, 3, 5, 7])
        c1, c2 = random.randint(2, 10), random.randint(2, 10)
        op, sym, res = random.choice([('add', '+', c1+c2), ('subtract', '-', c1-c2)])
        question = f"Simplify: ${c1}\\sqrt{{{base_surd}}} {sym} {c2}\\sqrt{{{base_surd}}}$"
        answer = f"${res}\\sqrt{{{base_surd}}}$"
        hint = "You can add or subtract 'like surds' by adding or subtracting their coefficients."
        explanation = f"Since both terms are 'like surds' (they both have $\\sqrt{{{base_surd}}}$), we can simply operate on their coefficients:\n$({c1} {sym} {c2})\\sqrt{{{base_surd}}} = {res}\\sqrt{{{base_surd}}}$."
        distractor1 = f"${c1*c2}\\sqrt{{{base_surd}}}$"
        distractor2 = f"${res}\\sqrt{{{base_surd*2}}}$"
        options = {answer, distractor1, distractor2}

    # --- 2.1: Operations on Unlike Surds (Medium) ---
    elif q_type == 'ops_unlike_surds':
        n = random.choice([2, 3, 5])
        p1, p2 = random.choice([(4,9), (4,16), (9,25)])
        s1, s2 = int(math.sqrt(p1)), int(math.sqrt(p2))
        c1, c2 = random.randint(2, 5), random.randint(2, 5)
        term1, term2 = c1 * s1, c2 * s2
        question = f"Simplify completely: ${c1}\\sqrt{{{p1*n}}} + {c2}\\sqrt{{{p2*n}}}$"
        answer = f"${term1 + term2}\\sqrt{{{n}}}$"
        hint = "First, simplify each surd term into its simplest form. Then, check if you have like surds to combine."
        explanation = f"1. Simplify the first term: ${c1}\\sqrt{{{p1*n}}} = {c1} \\times {s1}\\sqrt{{{n}}} = {term1}\\sqrt{{{n}}}$.\n2. Simplify the second term: ${c2}\\sqrt{{{p2*n}}} = {c2} \\times {s2}\\sqrt{{{n}}} = {term2}\\sqrt{{{n}}}$.\n3. Now add the like surds: ${term1}\\sqrt{{{n}}} + {term2}\\sqrt{{{n}}} = {answer}$."
        distractor1 = f"${c1+c2}\\sqrt{{{p1*n + p2*n}}}$"
        distractor2 = f"${term1 + c2}\\sqrt{{{n}}}$"
        options = {answer, distractor1, distractor2}

    # --- 2.2: Expansion of Single Brackets (Medium) ---
    elif q_type == 'expand_single_bracket':
        a, b, c = random.choice([2,3,5]), random.choice([2,3,5]), random.randint(2,6)
        question = f"Expand and simplify the expression: $\\sqrt{{{a}}}({c} + \\sqrt{{{b}}})$"
        if a == b: answer = f"${c}\\sqrt{{{a}}} + {a}$"
        else: answer = f"${c}\\sqrt{{{a}}} + \\sqrt{{{a*b}}}$"
        hint = "Use the distributive property to multiply the term outside the bracket with each term inside."
        explanation = f"$\\sqrt{{{a}}} \\times {c} + \\sqrt{{{a}}} \\times \\sqrt{{{b}}} = {answer}$"
        distractor1 = f"${c+a}\\sqrt{{{b}}}$"
        distractor2 = f"${c}\\sqrt{{{a+b}}}$"
        options = {answer, distractor1, distractor2}

    # --- 2.3: Rationalizing Monomial Denominators (Medium) ---
    elif q_type == 'rationalize_monomial':
        n = random.choice([2,3,5,6,7])
        a = random.randint(2,10) * n
        question = f"Express $\\frac{{{a}}}{{\\sqrt{{{n}}}}}$ with a rational denominator."
        answer = f"${a//n}\\sqrt{{{n}}}$"
        hint = "Multiply the numerator and the denominator by the surd in the denominator (in this case, by $\\sqrt{n}$)."
        explanation = f"To rationalize, we multiply the top and bottom by $\\sqrt{{{n}}}$:\n$\\frac{{{a}}}{{\\sqrt{{{n}}}}} \\times \\frac{{\\sqrt{{{n}}}}}{{\\sqrt{{{n}}}}} = \\frac{{{a}\\sqrt{{{n}}}}}{{{n}}}$.\nThis simplifies to ${answer}$ because {a} divided by {n} is {a//n}."
        distractor1 = f"${a}\\sqrt{{{n}}}$"
        distractor2 = str(a)
        options = {answer, distractor1, distractor2}

    # --- 2.4 & 2.5: Geometry (Medium & Hard) ---
    elif q_type in ['geometry_context', 'geometry_hard']:
        if difficulty == "Medium":
            problem_type = random.choice(['pythagoras', 'rectangle_area', 'rectangle_perimeter'])
        else: # Hard
            problem_type = random.choice(['cuboid_volume', 'trigonometry_sohcahtoa'])

        if problem_type == 'pythagoras':
            a_val, b_val = random.choice([(2,3), (5,7), (6,3), (11,5)])
            c_sq = a_val + b_val
            question = f"A right-angled triangle has shorter sides of length $\\sqrt{{{a_val}}}$ cm and $\\sqrt{{{b_val}}}$ cm. Find the exact length of the hypotenuse."
            answer = f"$\\sqrt{{{c_sq}}}$ cm"
            hint = "Use Pythagoras' theorem: $a^2 + b^2 = c^2$. Remember that $(\\sqrt{x})^2 = x$."
            explanation = f"1. Let the sides be $a = \\sqrt{{{a_val}}}$ and $b = \\sqrt{{{b_val}}}$.\n2. By Pythagoras' theorem, $c^2 = a^2 + b^2 = (\\sqrt{{{a_val}}})^2 + (\\sqrt{{{b_val}}})^2 = {a_val} + {b_val} = {c_sq}$.\n3. The exact length of the hypotenuse is $c = \\sqrt{{{c_sq}}}$ cm."
            distractor1 = f"${c_sq}$ cm"
            distractor2 = f"$\\sqrt{{{a_val+b_val-2*math.sqrt(a_val*b_val)}}}$ cm"
            options = {answer, distractor1, distractor2}

        elif problem_type in ['rectangle_area', 'rectangle_perimeter']:
            n = random.choice([2, 3, 5])
            p1, p2 = random.choice([(4,9), (4,16), (9,25)])
            l_simp, w_simp = int(math.sqrt(p1)), int(math.sqrt(p2))
            l_unsimp, w_unsimp = p1*n, p2*n
            
            if problem_type == 'rectangle_area':
                question = f"A rectangle has a length of $\\sqrt{{{l_unsimp}}}$ metres and a width of $\\sqrt{{{w_unsimp}}}$ metres. Find its exact area."
                answer = f"${l_simp * w_simp * n}$ m²"
                hint = "Area = length × width. First, simplify both surds, then multiply."
                explanation = f"1. Simplify Length: $\\sqrt{{{l_unsimp}}} = {l_simp}\\sqrt{{{n}}}$.\n2. Simplify Width: $\\sqrt{{{w_unsimp}}} = {w_simp}\\sqrt{{{n}}}$.\n3. Area = $({l_simp}\\sqrt{{{n}}}) \\times ({w_simp}\\sqrt{{{n}}}) = {l_simp*w_simp} \\times (\\sqrt{{{n}}})^2 = {l_simp*w_simp} \\times {n} = {answer}$."
                perimeter = f"${2*l_simp + 2*w_simp}\\sqrt{{{n}}}$ m"
                distractor1 = f"${l_simp * w_simp}\\sqrt{{{n}}}$ m²"
                options = {answer, perimeter, distractor1}
            else: # Perimeter
                question = f"A rectangle has a length of $\\sqrt{{{l_unsimp}}}$ metres and a width of $\\sqrt{{{w_unsimp}}}$ metres. Find its perimeter."
                answer = f"${2*l_simp + 2*w_simp}\\sqrt{{{n}}}$ m"
                hint = "Perimeter = 2(length + width). First, simplify both surds, then add and multiply by 2."
                explanation = f"1. Simplify Length: $\\sqrt{{{l_unsimp}}} = {l_simp}\\sqrt{{{n}}}$.\n2. Simplify Width: $\\sqrt{{{w_unsimp}}} = {w_simp}\\sqrt{{{n}}}$.\n3. Perimeter = $2({l_simp}\\sqrt{{{n}}} + {w_simp}\\sqrt{{{n}}}) = 2(({l_simp+w_simp})\\sqrt{{{n}}}) = {answer}$."
                area = f"${l_simp * w_simp * n}$ m²"
                distractor1 = f"${l_simp + w_simp}\\sqrt{{{n}}}$ m"
                options = {answer, area, distractor1}

        elif problem_type == 'cuboid_volume':
            l, w, h = 2, 3, 5
            c1, c2, c3 = random.randint(2,4), random.randint(2,4), random.randint(2,4)
            question = f"A cuboid has dimensions of ${c1}\\sqrt{{{l}}}$ cm, ${c2}\\sqrt{{{w}}}$ cm, and ${c3}\\sqrt{{{h}}}$ cm. Find its exact volume."
            answer = f"${c1*c2*c3}\\sqrt{{{l*w*h}}}$ cm³"
            hint = "Volume of a cuboid = length × width × height. Multiply the rational coefficients and the surds separately."
            explanation = f"Volume = $({c1}\\sqrt{{{l}}}) \\times ({c2}\\sqrt{{{w}}}) \\times ({c3}\\sqrt{{{h}}})$.\n= $({c1} \\times {c2} \\times {c3}) \\times (\\sqrt{{{l}}} \\times \\sqrt{{{w}}} \\times \\sqrt{{{h}}})$.\n= ${c1*c2*c3}\\sqrt{{{l*w*h}}}$ cm³."
            surface_area_approx = 2*(c1*c2*math.sqrt(l*w) + c2*c3*math.sqrt(w*h) + c1*c3*math.sqrt(l*h))
            distractor1 = f"${c1+c2+c3}\\sqrt{{{l+w+h}}}$ cm³"
            options = {answer, distractor1, f"{surface_area_approx:.0f} cm²"}
        
        elif problem_type == 'trigonometry_sohcahtoa':
            opp, hyp = random.choice([(1,2), (math.sqrt(3), 2), (1, math.sqrt(2))])
            adj_sq = hyp**2 - opp**2
            adj = math.sqrt(adj_sq)
            question = f"In a right-angled triangle, the side opposite angle $\\theta$ is $\\sqrt{{{int(opp**2)}}}$ cm and the hypotenuse is ${int(hyp)}$ cm. What is the exact length of the adjacent side?"
            answer = f"$\\sqrt{{{int(adj_sq)}}}$ cm" if adj != int(adj) else f"{int(adj)} cm"
            hint = "Use Pythagoras' theorem, $a^2 + b^2 = c^2$, to find the missing side."
            explanation = f"1. Let the adjacent side be 'a'. Then $a^2 + (opposite)^2 = (hypotenuse)^2$.\n2. $a^2 + (\\sqrt{{{int(opp**2)}}})^2 = ({int(hyp)})^2$.\n3. $a^2 + {int(opp**2)} = {int(hyp**2)}$.\n4. $a^2 = {int(hyp**2)} - {int(opp**2)} = {int(adj_sq)}$.\n5. $a = \\sqrt{{{int(adj_sq)}}}$. The final answer is **{answer}**."
            distractor1 = f"$\\sqrt{{{int(hyp**2 + opp**2)}}}$ cm"
            distractor2 = f"{int(hyp**2 - opp**2)} cm"
            options = {answer, distractor1, distractor2}

    # --- 3.1: Expansion of Double Brackets (Hard) ---
    elif q_type == 'expand_double_bracket':
        a, b, c = random.randint(2, 5), random.choice([2, 3, 5]), random.randint(2, 5)
        question = f"Expand and simplify: $({a} + \\sqrt{{{b}}})({c} - \\sqrt{{{b}}})$"
        res_term1, res_term2 = a*c - b, c - a
        answer = f"${res_term1} + {res_term2}\\sqrt{{{b}}}$" if res_term2 >= 0 else f"${res_term1} - {abs(res_term2)}\\sqrt{{{b}}}$"
        hint = "Use the FOIL (First, Outer, Inner, Last) method to expand the brackets, then collect like terms."
        explanation = f"FOIL gives: $({a*c}) - {a}\\sqrt{{{b}}} + {c}\\sqrt{{{b}}} - {b}$.\nCollect like terms: $({a*c} - {b}) + ({c} - {a})\\sqrt{{{b}}} = {answer}$."
        options = {answer, f"{a*c+b} + {c+a}\\sqrt{{{b}}}$"}

    # --- 3.2: Advanced Rationalization (Hard) ---
    elif q_type == 'rationalize_binomial':
        n = random.choice([2,3,5]); a,b,c,d = [random.randint(1,5) for _ in range(4)]
        while c*c == d*d*n: c,d = random.randint(1,5), random.randint(1,5)
        question = f"Express $\\frac{{{a} + {b}\\sqrt{{{n}}}}}{{{c} - {d}\\sqrt{{{n}}}}}$ in the form $p + q\\sqrt{{{n}}}$."
        den = c*c - d*d*n
        num_rat = a*c + b*d*n
        num_irr = a*d + b*c
        p = Fraction(num_rat, den)
        q = Fraction(num_irr, den)
        answer = f"${_get_fraction_latex_code(p)} + {_get_fraction_latex_code(q)}\\sqrt{{{n}}}$"
        hint = f"Multiply the numerator and denominator by the conjugate of the denominator, which is $({c} + {d}\\sqrt{{{n}}})$."
        explanation = f"1. Numerator: $({a} + {b}\\sqrt{{{n}}})({c} + {d}\\sqrt{{{n}}}) = ({a*c} + {b*d*n}) + ({a*d} + {b*c})\\sqrt{{{n}}}$.\n2. Denominator: $({c} - {d}\\sqrt{{{n}}})({c} + {d}\\sqrt{{{n}}}) = {c*c} - {d*d*n} = {den}$.\n3. Result: $\\frac{{{num_rat} + {num_irr}\\sqrt{{{n}}}}}{{{den}}}$, which simplifies to {answer}."
        distractor1 = f"${_get_fraction_latex_code(p)} - {_get_fraction_latex_code(q)}\\sqrt{{{n}}}$"
        p2 = Fraction(num_rat, c*c + d*d*n); q2 = Fraction(num_irr, c*c + d*d*n)
        distractor2 = f"${_get_fraction_latex_code(p2)} + {_get_fraction_latex_code(q2)}\\sqrt{{{n}}}$"
        options = {answer, distractor1, distractor2}

    # --- 3.3: Equality of Surds (Hard) ---
    elif q_type == 'equality_of_surds':
        x, y = 6, -8; base = 5
        question = f"Find the values of the rational numbers $x$ and $y$ that satisfy the equation: $$x(3 - \\sqrt{{{base}}}) = 8 + \\frac{{y\\sqrt{{{base}}}}}{{3 + \\sqrt{{{base}}}}}$$"
        answer = f"x = {x}, y = {y}"
        hint = "Simplify both sides to the form $A+B\\sqrt{5}$, then equate the rational and irrational parts to form simultaneous equations."
        explanation = f"1. LHS is $3x - x\\sqrt{{5}}$.\n2. RHS simplifies to $(8 - \\frac{{5y}}{{4}}) + (\\frac{{3y}}{{4}})\\sqrt{{5}}$.\n3. Equating parts gives: $3x = 8 - \\frac{{5y}}{{4}}$ and $-x = \\frac{{3y}}{{4}}$.\n4. Solving these simultaneously gives the answer."
        options = {answer, f"x = {-x}, y = {-y}", f"x = {y}, y = {x}"}

    # --- 3.4: Nested Square Roots (Hard) ---
    elif q_type == 'nested_square_root':
        a, b = random.choice([(6,5), (7,3), (11,5), (8,3)])
        A, C = a + b, 4 * a * b
        question = f"Simplify the expression completely: $\\sqrt{{{A} - \\sqrt{{{C}}}}}$"
        answer = f"$\\sqrt{{{a}}} - \\sqrt{{{b}}}$"
        hint = "The expression is not in the form $\\sqrt{A - 2\\sqrt{B}}$. You must first manipulate the inner surd, $\\sqrt{C}$, to pull out a '2'."
        explanation = f"1. Simplify inner surd: $\\sqrt{{{C}}} = \\sqrt{{4 \\times {a*b}}} = 2\\sqrt{{{a*b}}}$.\n2. The expression becomes $\\sqrt{{{A} - 2\\sqrt{{{a*b}}}}}$.\n3. We need two numbers that add to {A} and multiply to {a*b}. These are {a} and {b}.\n4. The simplified form is $\\sqrt{a} - \\sqrt{b}$ (placing the larger number first), which is {answer}."
        distractor1 = f"$\\sqrt{{{a}}} + \\sqrt{{{b}}}$"
        distractor2 = f"{A - math.sqrt(C)}"
        options = {answer, distractor1, distractor2}

    # --- 3.5: Crossover - Surds and Quadratic Equations (Hard) ---
    elif q_type == 'quadratic_roots':
        r1_a, r1_b, n = random.randint(2,5), random.randint(1,3), random.choice([2,3,5])
        sum_of_roots = 2*r1_a
        product_of_roots = r1_a*r1_a - r1_b*r1_b*n
        question = f"Find the quadratic equation in the form $x^2 + px + q = 0$ whose roots are $({r1_a} + {r1_b}\\sqrt{{{n}}})$ and $({r1_a} - {r1_b}\\sqrt{{{n}}})$."
        answer = f"$x^2 - {sum_of_roots}x + {product_of_roots} = 0$"
        hint = "A quadratic equation can be formed from its roots using $x^2 - (\\text{sum of roots})x + (\\text{product of roots}) = 0$."
        explanation = f"1. Sum of roots = $({r1_a} + {r1_b}\\sqrt{{{n}}}) + ({r1_a} - {r1_b}\\sqrt{{{n}}}) = {sum_of_roots}$.\n2. Product of roots = $({r1_a} + {r1_b}\\sqrt{{{n}}})({r1_a} - {r1_b}\\sqrt{{{n}}}) = {r1_a**2} - ({r1_b**2} \\times {n}) = {product_of_roots}$.\n3. The equation is $x^2 - ({sum_of_roots})x + ({product_of_roots}) = 0$."
        options = {answer, f"$x^2 + {sum_of_roots}x + {product_of_roots} = 0$", f"$x^2 - {sum_of_roots}x - {product_of_roots} = 0$"}

    return {"question": question, "options": _finalize_options(options), "answer": answer, "hint": hint, "explanation": explanation, "difficulty": difficulty}

# --- END: REVISED FUNCTION _generate_surds_question ---
def _generate_binary_ops_question(difficulty="Medium"):
    """Generates a Binary Operations question based on the detailed, multi-level curriculum."""

    if difficulty == "Easy":
        # Level 1: Foundations & Direct Computation
        q_type = random.choice(['evaluate', 'table_read'])
    elif difficulty == "Medium":
        # Level 2: Core Properties & Simple Equations
        q_type = random.choice(['identity', 'inverse', 'commutative', 'solve_simple'])
    else: # Hard
        # Level 3: Advanced & Abstract Properties
        q_type = random.choice(['associative', 'closure', 'modular_wassce', 'distributive'])

    question, answer, hint, explanation = "", "", "", ""
    options = set()

    # --- 1.1: Direct Evaluation (Easy) ---
    if q_type == 'evaluate':
        a, b = random.randint(-5, 8), random.randint(-5, 8)
        while a==0 or b==0: a, b = random.randint(-5, 8), random.randint(-5, 8)
        
        op_templates = [
            (f"p \\ast q = pq - p + 2q", lambda p,q: p*q - p + 2*q),
            (f"x \\oplus y = x^2 - 2y", lambda p,q: p**2 - 2*q),
            (f"m \\nabla n = m + n - 5", lambda p,q: p + q - 5),
            (f"a \\Delta b = 3a - b^2", lambda p,q: 3*p - q**2)
        ]
        op_def, op_func = random.choice(op_templates)
        op_sym = op_def.split(" ")[1]
        
        phrasing = random.choice([
            f"A binary operation {op_sym} is defined by ${op_def}$. Evaluate $({a} {op_sym} {b})$.",
            f"Given the operation {op_sym} on the set of real numbers by ${op_def}$, find the value of $({a} {op_sym} {b})$.",
            f"If $p {op_sym} q = {op_def.split('=')[1].strip()}$, what is the value of $({a} {op_sym} {b})$?"
        ])
        question = phrasing
        answer = str(op_func(a, b))
        hint = "Carefully substitute the first value for the first variable (e.g., 'p') and the second value for the second variable (e.g., 'q')."
        explanation = f"1. The rule is ${op_def}$.\n2. Substitute the first value ({a}) and the second value ({b}).\n3. Calculation: ${op_func(a,b)}$."
        # Smart Distractors
        distractor1 = str(op_func(b, a)) # Swapped order
        distractor2 = str(op_func(a, b) + random.choice([-1, 1])) # Off by one
        options = {answer, distractor1, distractor2}

    # --- 1.2: Reading Cayley Tables (Easy) ---
    elif q_type == 'table_read':
        s = ['a', 'b', 'c', 'd']
        op_sym = random.choice(["$\\ast$", "$\\otimes$", "$\\circ$"])
        results = {}
        for row in s:
            for col in s:
                results[(row, col)] = random.choice(s)
        table_md = f"| {op_sym} | a | b | c | d |\n|---|---|---|---|---|\n"
        for row in s:
            table_md += f"| **{row}** |";
            for col in s: table_md += f" {results.get((row, col))} |"
            table_md += "\n"
        a, b = random.sample(s, 2)
        question = f"The operation {op_sym} on the set $\\{{a, b, c, d\\}}$ is defined by the Cayley table below. Find the value of $({a} {op_sym} {b})$.\n\n{table_md}"
        answer = str(results.get((a,b)))
        hint = "Find the row for the first element and the column for the second element. The answer is where they intersect."
        explanation = f"To find $({a} {op_sym} {b})$, we locate the row labeled **{a}** and move across to the column labeled **{b}**. The value in that cell is **{answer}**."
        options = set(s)

    # --- 2.1 & 2.2: Identity & Inverse (Medium) ---
    elif q_type in ['identity', 'inverse']:
        # Create a large pool of varied operation templates
        op_templates = [
            (f"a \\ast b = a+b-{random.randint(2, 9)}", lambda k: k, lambda e, elem: 2*e - elem),
            (f"a \\ast b = a+b+\\frac{{ab}}{{2}}", lambda k: 0, lambda e, elem: Fraction(-2 * elem, 2 + elem)),
            (f"p \\circ q = pq", lambda k: 1, lambda e, elem: Fraction(1, elem)),
            (f"m \\nabla n = m+n-mn", lambda k: 0, lambda e, elem: Fraction(-elem, 1 - elem))
        ]
        op_def, identity_func, inverse_func = random.choice(op_templates)
        op_sym = op_def.split(" ")[1]
        
        # We need a dummy 'k' for the functions, though it's not always used
        dummy_k = int(re.search(r'\d+', op_def).group()) if re.search(r'\d+', op_def) else 1
        identity_element = identity_func(dummy_k)

        if q_type == 'identity':
            question = f"Find the identity element, $e$, for the binary operation ${op_def}$ on the set of real numbers."
            answer = str(identity_element)
            hint = "The identity element 'e' is the number that satisfies the equation $a \\ast e = a$ for any 'a'."
            explanation = f"We solve the equation $a \\ast e = a$. For the rule ${op_def}$, this becomes an equation we solve for $e$. The result is $e = {answer}$."
            options = {answer, "0", "1", "a"}
        else: # Inverse
            element_to_invert = random.randint(identity_element + 2, identity_element + 10)
            inverse_val = inverse_func(identity_element, element_to_invert)
            
            question = f"For the binary operation ${op_def}$, find the inverse of the element ${element_to_invert}$."
            answer = _format_fraction_text(inverse_val) if isinstance(inverse_val, Fraction) else str(inverse_val)
            hint = f"First, find the identity element 'e'. Then, find the inverse '$a^{{-1}}$' by solving ${element_to_invert} \\ast a^{{-1}} = e$."
            explanation = f"1. Find the identity element, $e$, which is {identity_element}.\n2. Let the inverse of {element_to_invert} be $inv$.\n3. Solve the equation ${element_to_invert} \\ast inv = {identity_element}$.\n4. The result of this calculation is **{answer}**."
            options = {answer, str(-element_to_invert), str(identity_element)}

    # --- 2.3: Commutativity (Medium) ---
    elif q_type == 'commutative':
        op_sym = random.choice([r"\Delta", r"\circ", r"\star"])
        templates = [
            (f"a {op_sym} b = a+b-ab", "Yes"),
            (f"a {op_sym} b = 2a+2b", "Yes"),
            (f"a {op_sym} b = a-b", "No"),
            (f"a {op_sym} b = a^2 - 2b", "No")
        ]
        op_def, answer = random.choice(templates)
        question = f"The operation {op_sym} is defined by ${op_def}$ on the set of real numbers. Is this operation commutative?"
        hint = "An operation is commutative if $a \\ast b = b \\ast a$ for all values. Check if the formula is symmetric when you swap 'a' and 'b'."
        explanation = f"We must check if $a {op_sym} b = b {op_sym} a$.\n$a {op_sym} b = {op_def.split('=')[1].strip()}$.\n$b {op_sym} a$ would be `{op_def.split('=')[1].strip().replace('a', 'TEMP').replace('b', 'a').replace('TEMP', 'b')}`.\nComparing these two expressions, we see they are {'equal' if answer == 'Yes' else 'not equal'}. Therefore, the operation is **{answer.lower()}**."
        options = {"Yes", "No"}

    # --- 2.4: Simple Equations (Medium) ---
    elif q_type == 'solve_simple':
        unknown_var = random.choice(['k', 'x', 'n', 'p'])
        var_val = random.randint(2, 8)
        b = random.randint(2, 8)
        
        op_templates = [
            (f"a \\ast b = 2a + 3b", lambda var, const: 2*var + 3*const),
            (f"a \\ast b = ab - a", lambda var, const: var*const - var),
            (f"a \\ast b = a^2 + b", lambda var, const: var**2 + const)
        ]
        op_def, op_func = random.choice(op_templates)
        op_sym = op_def.split(" ")[1]
        
        result = op_func(var_val, b)
        
        question = f"A binary operation is defined by ${op_def}$. Find the value of ${unknown_var}$ such that ${unknown_var} \\ast {b} = {result}$."
        answer = str(var_val)
        hint = f"Substitute the values into the given formula to form an equation, then solve for {unknown_var}."
        explanation = f"1. We are given the equation ${unknown_var} \\ast {b} = {result}$.\n2. Using the definition, this becomes `{op_def.replace('a', unknown_var).replace('b', str(b)).split('=')[1].strip()} = {result}`.\n3. Solving this equation for ${unknown_var}$ gives the answer **{answer}**."
        options = {answer, str(b), str(result)}

    # --- 3.1 & 3.2: Associativity & Closure (Hard) ---
    elif q_type in ['associative', 'closure']:
        op_sym = random.choice([r"\ast", r"\otimes"])
        if q_type == 'associative':
            templates = [
                (f"a {op_sym} b = a + b + 2", "Yes"), (f"a {op_sym} b = ab", "Yes"),
                (f"a {op_sym} b = 2a + b", "No"), (f"a {op_sym} b = a - b", "No")
            ]
            op_def, answer = random.choice(templates)
            question = f"Is the binary operation ${op_def}$ associative on the set of real numbers?"
            hint = "An operation is associative if $(a \\ast b) \\ast c = a \\ast (b \\ast c)$. You must expand both sides algebraically and compare them."
            explanation = f"To test for associativity, we check if $(a {op_sym} b) {op_sym} c = a {op_sym} (b {op_sym} c)$. For the operation ${op_def}$, this property is found to be **{answer.lower()}**."
            options = {"Yes", "No", "Commutative"} # Smart distractor: Commutative
        else: # Closure
            set_name, set_desc, op_def, answer = random.choice([
                ("the set of Odd Integers", "\\{..., -3, -1, 1, 3, ...\\}", "a \\ast b = ab", "Yes"),
                ("the set of Even Integers", "\\{..., -2, 0, 2, 4, ...\\}", "a \\ast b = a + b", "Yes"),
                ("the set of Odd Integers", "\\{..., -3, -1, 1, 3, ...\\}", "a \\ast b = a + b", "No"),
                ("the set $\\{ -1, 0, 1 \\}$", "", "a \\ast b = ab", "Yes")
            ])
            question = f"Consider the operation ${op_def}$ on {set_name}{'' if not set_desc else f', $S = {set_desc}$'}. Is the set S closed under this operation?"
            hint = "A set is closed under an operation if performing the operation on any two elements from the set always results in an answer that is also in the set."
            explanation = f"We must check if taking any two elements from {set_name} and applying the operation always produces a result that is also a member of that set. For this combination, the property is **{answer.lower()}**."
            options = {"Yes", "No"}

    # --- 3.3: WASSCE-Style Modular Arithmetic (Hard) ---
    elif q_type == 'modular_wassce':
        n = 5; a_coeff = 2
        set_str = "\\{0, 1, 2, 3, 4\\}"
        op_def = f"p \\ast q = (p + {a_coeff}q) \\pmod{{{n}}}"
        identity = 0 # p + 2*0 = p
        inverse_of_3 = 1 # 3 + 2*1 = 5 = 0 mod 5
        phrasing = random.choice([
            f"An operation $\\ast$ is defined on the set $S = {set_str}$ by the rule ${op_def}$. Find the inverse of the element 3.",
            f"On the set of integers modulo {n}, an operation is defined by ${op_def}$. What is the inverse of 3 under this operation?"
        ])
        question = phrasing
        answer = str(inverse_of_3)
        hint = "First find the identity element 'e' by solving $p \\ast e = p$. Then, find the inverse of 3, let's call it 'inv', by solving $3 \\ast inv = e$."
        explanation = f"1. Find identity (e): $p \\ast e = p \\implies p + {a_coeff}e \\equiv p \\pmod{{{n}}} \\implies {a_coeff}e \\equiv 0 \\pmod{{{n}}}$. The identity element is $e={identity}$.\n2. Find inverse of 3: $3 \\ast inv = {identity} \\implies 3 + {a_coeff}(inv) \\equiv {identity} \\pmod{{{n}}}$.\n3. $2(inv) \\equiv -3 \\equiv 2 \\pmod{{{n}}}$. By testing values in S, we find $2(1) = 2$. So the inverse is **{inverse_of_3}**."
        options = {answer, str(identity), "2", "4"}

    # --- 3.4: Distributivity (Hard) ---
    elif q_type == 'distributive':
        op1_def = "a \\ast b = ab"
        op2_def = "p \\circ q = p+q"
        question = f"Two binary operations are defined on the set of real numbers as ${op1_def}$ and ${op2_def}$. Is the operation $\\ast$ (multiplication) distributive over $\\circ$ (addition)?"
        answer = "Yes"
        hint = "To check if $\\ast$ is distributive over $\\circ$, you must test if $a \\ast (p \\circ q) = (a \\ast p) \\circ (a \\ast q)$ holds true."
        explanation = f"We must check if $a \\times (p+q) = (a \\times p) + (a \\times q)$.\n- LHS: $a(p+q) = ap + aq$.\n- RHS: $ap + aq$.\nSince the Left Hand Side equals the Right Hand Side, the operation **is distributive**."
        options = {"Yes", "No", "Only for positive numbers"}

    return {"question": question, "options": _finalize_options(options), "answer": answer, "hint": hint, "explanation": explanation, "difficulty": difficulty}
def _generate_relations_functions_question(difficulty="Medium"):
    """Generates a Relations and Functions question based on the detailed, multi-level syllabus."""

    if difficulty == "Easy":
        # Level 1: Foundations & Definitions
        q_type = random.choice(['is_function', 'domain_range_pairs', 'evaluate_simple', 'properties_of_relations'])
    elif difficulty == "Medium":
        # Level 2: Core Properties & Algebra
        q_type = random.choice(['types_of_mappings', 'domain_from_equation', 'composite_evaluation', 'algebra_of_functions'])
    else: # Hard
        # Level 3: Advanced Functions & Their Properties
        q_type = random.choice(['composite_algebraic', 'inverse_function', 'properties_of_inverse', 'even_odd_functions', 'graph_transformations'])

    question, answer, hint, explanation = "", "", "", ""
    options = set()

    # --- 1.1: Identifying Functions (Easy) ---
    if q_type == 'is_function':
        d = sorted(random.sample(range(1, 20), 4))
        r = random.sample(range(5, 30), 4)
        func_relation = str({(d[0], r[0]), (d[1], r[1]), (d[2], r[2])})
        not_func_relation = str({(d[0], r[0]), (d[0], r[1]), (d[1], r[2])})
        question = "Which of the following relations is also a function?"
        answer = func_relation
        hint = "A relation is a function if every input (first element) maps to exactly one output (second element)."
        explanation = f"The relation {not_func_relation} is not a function because the input '{d[0]}' maps to two different outputs. The relation {answer} is a function because every input has only one output."
        options = {answer, not_func_relation}

    # --- 1.2: Domain and Range from Ordered Pairs (Easy) ---
    elif q_type == 'domain_range_pairs':
        domain_list = sorted(list(set(random.sample(range(-10, 10), k=random.randint(4, 5)))))
        range_list = sorted(list(set(random.sample(range(-10, 10), k=random.randint(4, 5)))))
        relation_pairs = list(zip(domain_list, random.sample(range_list, len(domain_list))))
        relation_str = str(set(relation_pairs)).replace("'", "")
        actual_domain, actual_range = set(p[0] for p in relation_pairs), set(p[1] for p in relation_pairs)
        d_or_r = random.choice(['domain', 'range'])
        question = f"What is the {d_or_r} of the relation $R = {relation_str}$?"
        domain_set_str, range_set_str = str(actual_domain), str(actual_range)
        if d_or_r == 'domain':
            answer, distractor = domain_set_str, range_set_str
        else:
            answer, distractor = range_set_str, domain_set_str
        hint = "The domain is the set of all unique first elements (x-values). The range (or image) is the set of all unique second elements (y-values)."
        explanation = f"For the relation $R$, we collect all the first numbers to get the domain and all the second numbers to get the range.\n- Domain = ${domain_set_str}$.\n- Range = ${range_set_str}$."
        options = {answer, distractor, str(actual_domain.union(actual_range))}
        return {"question": question, "options": _finalize_options(options, "set_str"), "answer": answer, "hint": hint, "explanation": explanation, "difficulty": difficulty}

    # --- 1.3: Basic Function Evaluation (Easy) ---
    elif q_type == 'evaluate_simple':
        a, b, x = random.randint(2, 8), random.randint(-10, 10), random.randint(1, 7)
        question = f"If $f(x) = {a}x^2 + {b}$, find the value of $f({x})$."
        answer = str(a * (x**2) + b)
        hint = "Substitute the given value for 'x' into the function's definition and evaluate."
        explanation = f"We replace every 'x' with '{x}':\n$f({x}) = {a}({x})^2 + {b} = {a*(x**2)} + {b} = {a*(x**2)+b}$."
        options = {answer, str(a * x + b), str((a * x)**2 + b)}

    # --- 1.4: Properties of Relations (Easy) ---
    elif q_type == 'properties_of_relations':
        s = {1, 2, 3}
        prop, relation, ans = random.choice([
            ("Reflexive", "$\\{(1,1), (2,2), (3,3)\\}$", "Yes"),
            ("Symmetric", "$\\{(1,2), (2,1), (2,3), (3,2)\\}$", "Yes"),
            ("Transitive", "$\\{(1,2), (2,3), (1,3)\\}$", "Yes"),
            ("Symmetric", "$\\{(1,2), (2,3), (3,1)\\}$", "No")
        ])
        question = f"Is the relation $R = {relation}$ on the set $S = \\{{1,2,3\\}}$ **{prop}**?"
        answer = ans
        hint = f"A relation is {prop} if for its elements, a specific condition is met (e.g., for Symmetric, if (a,b) is in R, then (b,a) must also be in R)."
        explanation = f"The property of being **{prop}** requires a specific rule to be followed. The given relation **{answer.lower()}**, it does satisfy this rule."
        options = {"Yes", "No"}

    # --- 2.1: Types of Mappings (Medium) ---
    elif q_type == 'types_of_mappings':
        domain = [1, 2, 3, 4]
        codomain = ['a', 'b', 'c', 'd', 'e']
        
        # Create clear examples for each type
        one_to_one = str({(domain[0], codomain[0]), (domain[1], codomain[1]), (domain[2], codomain[2])})
        many_to_one = str({(domain[0], codomain[0]), (domain[1], codomain[0]), (domain[2], codomain[1])})
        one_to_many = str({(domain[0], codomain[0]), (domain[0], codomain[1]), (domain[1], codomain[2])})
        
        relation, correct_type = random.choice([
            (one_to_one, "One-to-one (injective)"), 
            (many_to_one, "Many-to-one"), 
            (one_to_many, "One-to-many (not a function)")
        ])
        
        question = f"The relation $R = {relation}$. What type of mapping is this?"
        answer = correct_type
        hint = "Check if inputs (first elements) or outputs (second elements) are repeated in the ordered pairs."
        explanation = f"In a **one-to-one** mapping, each input has a unique output. In a **many-to-one**, multiple inputs can go to the same output. In a **one-to-many**, one input goes to multiple outputs (this is not a function). The relation shown is a classic example of a **{correct_type}** mapping."
        
        # --- THIS IS THE FIX ---
        # We explicitly define the options and do not use the generic option filler.
        # This ensures no random numbers will ever be added.
        final_options = ["One-to-one (injective)", "Many-to-one", "One-to-many (not a function)"]
        random.shuffle(final_options)
        
        return {"question": question, "options": final_options, "answer": answer, "hint": hint, "explanation": explanation, "difficulty": difficulty}

    # --- 2.2: Finding the Domain from an Equation (Medium) ---
    elif q_type == 'domain_from_equation':
        a = random.randint(2, 9)
        b = random.randint(1, 9)
        func_type = random.choice(['rational', 'radical'])

        if func_type == 'rational':
            question = f"Find the domain of the function $f(x) = \\frac{{x+{b}}}{{x-{a}}}$."
            answer = f"All real numbers except $x={a}$"
            hint = "The domain of a rational function includes all real numbers except for values of x that make the denominator equal to zero."
            explanation = f"The function is undefined when its denominator is zero. We solve the equation $x-{a} = 0$, which gives $x={a}$. Therefore, the domain is all real numbers except for **{a}**."
            # Smart Distractors based on common errors:
            distractor1 = f"All real numbers except $x={-b}$" # Error: Student uses the root of the numerator.
            distractor2 = f"x = {a}" # Error: Student thinks the domain IS the excluded value.
            distractor3 = f"x \ge {a}" # Error: Student confuses the rule with radical functions.
            options = {answer, distractor1, distractor2, distractor3}
        else: # radical
            question = f"Find the domain of the function $f(x) = \\sqrt{{x-{a}}}$."
            answer = f"$x \ge {a}$"
            hint = "The expression inside a square root cannot be negative. Set the expression to be greater than or equal to zero and solve."
            explanation = f"For the function to be defined for real numbers, the term inside the square root must be non-negative. We solve the inequality $x-{a} \ge 0$, which gives $x \ge {a}$."
            # Smart Distractors based on common errors:
            distractor1 = f"x > {a}" # Error: Forgetting the "or equal to" part.
            distractor2 = f"x \le {a}" # Error: Flipping the inequality sign.
            distractor3 = f"All real numbers" # Error: Ignoring the radical entirely.
            options = {answer, distractor1, distractor2, distractor3}

    # --- 2.3: Composition of Functions (Evaluation) (Medium) ---
    elif q_type == 'composite_evaluation':
        a, b, c, d, x_val = [random.randint(1, 5) for _ in range(5)]
        g_of_x = c*x_val + d
        question = f"Given $f(x) = {a}x + {b}$ and $g(x) = {c}x + {d}$, find the value of $(f \\circ g)({x_val})$."
        answer = str(a*g_of_x + b)
        hint = f"This means find $f(g({x_val}))$. You must calculate the inner function, $g({x_val})$, first, then use that result as the input for $f(x)$."
        explanation = f"1. First, find $g({x_val}) = {c}({x_val}) + {d} = {g_of_x}$.\n2. Now, use this result as the input for f: $f({g_of_x}) = {a}({g_of_x}) + {b} = {a*g_of_x+b}$."
        distractor1 = str(c*(a*x_val + b) + d)
        distractor2 = str(a*c*x_val + b + d)
        options = {answer, distractor1, distractor2}

    # --- 2.4: Algebra of Functions (Medium) ---
    elif q_type == 'algebra_of_functions':
        f_coeffs = [random.randint(1, 5), random.randint(-5, 5)] # e.g., [2, 3] -> 2x+3
        g_coeffs = [random.randint(1, 5), random.randint(-5, 5)] # e.g., [1, 4] -> x+4
        f_str = _poly_to_str(f_coeffs)
        g_str = _poly_to_str(g_coeffs)
        
        op, sym = random.choice([('sum', '+'), ('product', '*')])
        question = f"Given $f(x) = {f_str}$ and $g(x) = {g_str}$, find $({f_str}) {sym} ({g_str})$."

        # --- Generate ALL possible results from different operations ---
        # Correct Sum: (f+g)(x)
        sum_coeffs = [f_coeffs[0] + g_coeffs[0], f_coeffs[1] + g_coeffs[1]]
        sum_ans = f"${_poly_to_str(sum_coeffs)}$"

        # Correct Product: (f*g)(x) = acx^2 + (ad+bc)x + bd
        prod_coeffs = [f_coeffs[0]*g_coeffs[0], f_coeffs[0]*g_coeffs[1] + f_coeffs[1]*g_coeffs[0], f_coeffs[1]*g_coeffs[1]]
        prod_ans = f"${_poly_to_str(prod_coeffs)}$"

        # Common Error 1: Subtraction (f-g)(x)
        sub_coeffs = [f_coeffs[0] - g_coeffs[0], f_coeffs[1] - g_coeffs[1]]
        sub_ans_distractor = f"${_poly_to_str(sub_coeffs)}$"

        # Common Error 2: Composition f(g(x)) = a(cx+d) + b = acx + ad + b
        fg_coeffs = [f_coeffs[0]*g_coeffs[0], f_coeffs[0]*g_coeffs[1] + f_coeffs[1]]
        fg_ans_distractor = f"${_poly_to_str(fg_coeffs)}$"
        
        if op == 'sum':
            answer = sum_ans
            # The distractors are the results of doing the WRONG operations
            options = {answer, prod_ans, sub_ans_distractor, fg_ans_distractor}
            hint = "To find the sum of two functions, add their corresponding like terms (the x-terms and the constant terms)."
            explanation = f"We add the expressions: $({f_str}) + ({g_str})$.\nCombine the x-terms: ${f_coeffs[0]}x + {g_coeffs[0]}x = {sum_coeffs[0]}x$.\nCombine the constants: ${f_coeffs[1]} + {g_coeffs[1]} = {sum_coeffs[1]}$.\nThe result is **{answer}**."
        else: # Product
            answer = prod_ans
            # The distractors are the results of doing the WRONG operations
            options = {answer, sum_ans, sub_ans_distractor, fg_ans_distractor}
            hint = "To find the product of two functions, use the FOIL method to expand the brackets and collect like terms."
            explanation = f"We multiply the expressions using FOIL: $({f_str})({g_str})$.\nThis gives ${f_coeffs[0]*g_coeffs[0]}x^2 + {f_coeffs[0]*g_coeffs[1]}x + {f_coeffs[1]*g_coeffs[0]}x + {f_coeffs[1]*g_coeffs[1]}$.\nCombining like terms gives **{answer}**."


    # --- 3.1 & 3.2: Algebraic Composition & Inverse Functions (Hard) ---
    elif q_type in ['composite_algebraic', 'inverse_function']:
        a, b = random.randint(2,7), random.randint(1,10)
        if q_type == 'composite_algebraic':
            c, d = random.randint(2,5), random.randint(1,5)
            question = f"Given $f(x) = {a}x + {b}$ and $g(x) = {c}x - {d}$, find the function $(f \\circ g)(x)$."
            answer = f"${a*c}x + {b-a*d}$"
            hint = "To find $f(g(x))$, substitute the entire expression for $g(x)$ into every 'x' in the function $f(x)$."
            explanation = f"$f(g(x)) = {a}(g(x)) + {b} = {a}({c}x - {d}) + {b} = {a*c}x - {a*d} + {b}$, which simplifies to **{answer}**."
            distractor1 = f"${a*c}x - {d}+{b}$"
            options = {answer, distractor1}
        else: # inverse_function
            question = f"Find the inverse function, $f^{{-1}}(x)$, of the function $f(x) = {a}x - {b}$."
            answer = f"$f^{{-1}}(x) = \\frac{{x + {b}}}{{{a}}}$"
            hint = "Let y = f(x), then swap the positions of x and y, and finally make y the subject of the formula."
            explanation = f"1. Start with $y = {a}x - {b}$.\n2. Swap x and y: $x = {a}y - {b}$.\n3. Solve for y: $x + {b} = {a}y \\implies y = \\frac{{x + {b}}}{{{a}}}$."
            distractor1 = f"$f^{{-1}}(x) = \\frac{{x - {b}}}{{{a}}}$"
            distractor2 = f"$f^{{-1}}(x) = {a}x + {b}$"
            options = {answer, distractor1, distractor2}

    # --- 3.3: Properties of Inverse Functions (Hard) ---
    elif q_type == 'properties_of_inverse':
        a, b = random.randint(2,7), random.randint(1,10)
        k = random.randint(5, 20)
        question = f"If $f(x) = {a}x + {b}$, what is the value of $f(f^{{-1}}({k}))$?"
        answer = str(k)
        hint = "The composition of a function and its inverse, $f(f^{-1}(x))$, always returns the original input, $x$."
        explanation = f"By definition, a function and its inverse 'undo' each other. Therefore, for any function $f$ and any input $k$, $f(f^{{-1}}({k}))$ will always be equal to **{k}**."
        options = {answer, str(a*k+b), str((k-b)/a)}

    # --- 3.4: Even and Odd Functions (Hard) ---
    elif q_type == 'even_odd_functions':
        func_str, ans = random.choice([
            ("x^4 + 2x^2", "Even"),
            ("x^3 - 5x", "Odd"),
            ("x^2 + 2x", "Neither")
        ])
        question = f"Determine if the function $f(x) = {func_str}$ is even, odd, or neither."
        answer = ans
        hint = "To test, find the expression for $f(-x)$. If $f(-x) = f(x)$, the function is even. If $f(-x) = -f(x)$, the function is odd."
        explanation = f"1. First, find $f(-x) = (-x)^4 + 2(-x)^2 = x^4 + 2x^2$. Since $f(-x) = f(x)$, the function is **Even**." if ans == "Even" else \
                    f"1. First, find $f(-x) = (-x)^3 - 5(-x) = -x^3 + 5x = -(x^3 - 5x) = -f(x)$. Since $f(-x) = -f(x)$, the function is **Odd**." if ans == "Odd" else \
                    f"1. First, find $f(-x) = (-x)^2 + 2(-x) = x^2 - 2x$. This is not equal to $f(x)$ or $-f(x)$. Therefore, the function is **Neither** even nor odd."
        options = {"Even", "Odd", "Neither"}
        
    return {"question": question, "options": _finalize_options(options), "answer": answer, "hint": hint, "explanation": explanation, "difficulty": difficulty}

# --- END: REVISED AND FINAL FUNCTION _generate_relations_functions_question ---

def _generate_sequence_series_question(difficulty="Medium"):
    """Generates a Sequence and Series question based on difficulty, preserving all original sub-types."""
    
    if difficulty == "Easy":
        # Fundamental calculations for AP and GP terms.
        q_type = random.choice(['ap_term', 'gp_term'])
    elif difficulty == "Medium":
        # Multi-step calculations and application problems.
        q_type = random.choice(['ap_sum', 'word_problem'])
    else: # Hard
        # More advanced concepts like sum to infinity.
        q_type = 'gp_sum_inf'

    question, answer, hint, explanation = "", "", "", ""
    options = set()
    a = random.randint(-15, 25)
    while a == 0: a = random.randint(-15, 25)

    # --- Easy Questions ---
    if q_type == 'ap_term':
        d = random.randint(-8, 12)
        n = random.randint(15, 40)
        while d == 0: d = random.randint(-8, 12)
        sequence = ", ".join([str(a + i*d) for i in range(4)])
        question = f"Find the {n}th term of the arithmetic progression: {sequence}, ..."
        answer = str(a + (n - 1) * d)
        hint = r"Use the AP nth term formula: $a_n = a + (n-1)d$."
        explanation = f"1. First term $a = {a}$.\n2. Common difference $d = {a+d} - {a} = {d}$.\n3. The {n}th term is $a_{{{n}}} = {a} + ({n}-1)({d}) = {answer}$."
        options = {answer, str(a + n*d), str(a*d + n)}
    
    elif q_type == 'gp_term':
        r, n = random.choice([-3, -2, 2, 3]), random.randint(5, 9)
        sequence = ", ".join([str(a * r**i) for i in range(3)])
        question = f"What is the {n}th term of the geometric progression: {sequence}, ...?"
        answer = str(a * r**(n-1))
        hint = r"Use the GP nth term formula: $a_n = ar^{n-1}$."
        explanation = f"1. First term $a = {a}$.\n2. Common ratio $r = \\frac{{{a*r}}}{{{a}}} = {r}$.\n3. The {n}th term is $a_{{{n}}} = {a} \\times {r}^{{{n}-1}} = {answer}$."
        options = {answer, str((a*r)**(n-1)), str(a * r * (n-1))}

    # --- Medium Questions ---
    elif q_type == 'ap_sum':
        d, n = random.randint(-5, 8), random.randint(15, 30)
        while d == 0: d = random.randint(-5, 8)
        question = f"Find the sum of the first {n} terms of an Arithmetic Progression with first term {a} and common difference {d}."
        answer = str(int((n/2) * (2*a + (n-1)*d)))
        hint = r"Use the sum of an AP formula: $S_n = \frac{n}{2}(2a + (n-1)d)$."
        explanation = f"$S_{{{n}}} = \\frac{{{n}}}{{2}}(2({a}) + ({n}-1)({d})) = \\frac{{{n}}}{{2}}({2*a} + {(n-1)*d}) = {answer}$."
        options = {answer, str(n*(a + (n-1)*d)), str(int((n/2)*(a + (a + n*d))))}

    elif q_type == 'word_problem':
        initial_amount = random.randint(200, 500) * 100 # GHS 20,000 to 50,000
        depreciation_rate = random.randint(8, 22)
        years = 4
        final_value = initial_amount * ((1 - depreciation_rate/100)**years)
        question = f"A new trotro purchased in Kumasi for GHS {initial_amount:,.2f} depreciates in value by {depreciation_rate}% each year. What is its approximate value after {years} years?"
        answer = f"GHS {final_value:,.2f}"
        hint = "This is a geometric progression problem. Use the formula: Final Value = $P(1 - r)^n$."
        explanation = f"1. P = {initial_amount}, r = {depreciation_rate/100}, n = {years}.\n2. Final Value = ${initial_amount:,.0f}(1 - {depreciation_rate/100})^{{{years}}} \\approx {final_value:,.2f}$."
        options = {answer, f"GHS {initial_amount * (1 - (depreciation_rate*years)/100):,.2f}", f"GHS {initial_amount - (initial_amount * depreciation_rate/100 * years):,.2f}"}
    
    # --- Hard Question ---
    elif q_type == 'gp_sum_inf':
        r = Fraction(random.randint(-2,2), random.randint(3, 7))
        while r == 0: r = Fraction(random.randint(-2,2), random.randint(3, 7))
        question = f"A geometric series has a first term of ${a}$ and a common ratio of ${_get_fraction_latex_code(r)}$. Calculate its sum to infinity."
        answer = _format_fraction_text(a / (1 - r))
        hint = r"Use the sum to infinity formula: $S_\infty = \frac{a}{1-r}$, which is valid only when $|r| < 1$."
        explanation = f"$S_\\infty = \\frac{{{a}}}{{1 - ({_get_fraction_latex_code(r)})}} = \\frac{{{a}}}{{{_get_fraction_latex_code(1-r)}}} = {_get_fraction_latex_code(a/(1-r))}$."
        options = {answer, _format_fraction_text(a/(1+r)), _format_fraction_text((a*r)/(1-r))}
    
    return {"question": question, "options": _finalize_options(options), "answer": answer, "hint": hint, "explanation": explanation, "difficulty": difficulty}

def _generate_word_problems_question(difficulty="Medium"):
    """Generates a Word Problems question based on difficulty, preserving all original sub-types."""

    gh_names = ["Yaw", "Adwoa", "Kofi", "Ama", "Kwame", "Abena"]
    gh_locations = ["Kejetia Market in Kumasi", "a shop in Osu, Accra", "a farm near Kajaji", "the Cape Coast Castle gift shop"]
    
    if difficulty == "Easy":
        # Direct translation from words to a simple equation.
        q_type = random.choice(['linear_number', 'ratio'])
    elif difficulty == "Medium":
        # Requires setting up a more complex equation with the variable on both sides.
        q_type = random.choice(['age', 'consecutive_integers'])
    else: # Hard
        # Involves reciprocal rates, a classic challenging problem type.
        q_type = 'work_rate'

    question, answer, hint, explanation = "", "", "", ""
    options = set()

    # --- Easy Questions ---
    if q_type == 'linear_number':
        x, k, m = random.randint(10, 50), random.randint(10, 50), random.randint(2, 7)
        result = m*x + k
        question = f"When {m} times a certain number is increased by {k}, the result is {result}. Find the number."
        answer = str(x)
        hint = "Let the number be 'n'. Translate the sentence into an equation like 'mn + k = result' and solve for n."
        explanation = f"1. Let the number be n. The equation is ${m}n + {k} = {result}$.\n2. Subtract {k}: ${m}n = {result-k}$.\n3. Divide by {m}: $n = \\frac{{{result-k}}}{{{m}}} = {x}$."
        options = {answer, str(result-k), str(int(result/m))}

    elif q_type == 'ratio':
        ratio1, ratio2 = random.randint(2, 9), random.randint(3, 10)
        while ratio1 == ratio2: ratio2 = random.randint(3, 10)
        total_amount = random.randint(20, 50) * (ratio1 + ratio2)
        share1 = int((ratio1 / (ratio1+ratio2)) * total_amount)
        share2 = total_amount - share1
        name1, name2 = random.sample(gh_names, 2)
        location = random.choice(gh_locations)
        question = f"At {location}, {name1} and {name2} share a profit of GHS {total_amount} in the ratio {ratio1}:{ratio2}. How much does {name1} receive?"
        answer = f"GHS {share1}"
        hint = "First, find the total number of parts in the ratio. Then, find the value of one part by dividing the total amount by the total parts."
        explanation = f"1. Total parts = {ratio1} + {ratio2} = {ratio1+ratio2}.\n2. Value of one part = GHS {total_amount} / {ratio1+ratio2} = GHS {total_amount//(ratio1+ratio2)}.\n3. {name1}'s share ({ratio1} parts) = {ratio1} * {total_amount//(ratio1+ratio2)} = GHS {share1}."
        options = {answer, f"GHS {share2}", f"GHS {total_amount//(ratio1+ratio2)}"}

    # --- Medium Questions ---
    elif q_type == 'age':
        child_age, parent_age = random.randint(8, 20), random.randint(40, 65)
        while parent_age - child_age < 20: parent_age = random.randint(40, 65)
        # Equation: parent + x = 2 * (child + x) => x = parent - 2*child
        ans_val = parent_age - 2*child_age
        if ans_val <= 0: return _generate_word_problems_question(difficulty=difficulty) # Regenerate if unsolvable
        child_name, parent_name = random.sample(gh_names, 2)
        question = f"{parent_name} is {parent_age} years old and their child {child_name} is {child_age} years old. In how many years will {parent_name} be exactly twice as old as {child_name}?"
        answer = str(ans_val)
        hint = "Let 'x' be the number of years. Set up the equation: Parent's Future Age = 2 * Child's Future Age."
        explanation = f"1. Let x be the number of years.\n2. In x years, their ages will be ({parent_age}+x) and ({child_age}+x).\n3. Equation: ${parent_age}+x = 2({child_age}+x)$.\n4. Solve: ${parent_age}+x = {2*child_age}+2x \\implies x = {parent_age - 2*child_age} = {ans_val}$."
        options = {answer, str(parent_age - child_age), str(ans_val + 2)}

    elif q_type == 'consecutive_integers':
        start, num = random.randint(20, 100), random.choice([3, 5])
        num_type = random.choice(['integers', 'even integers', 'odd integers'])
        if num_type == 'integers': integers = [start+i for i in range(num)]
        elif num_type == 'even integers': integers = [start*2 + 2*i for i in range(num)]
        else: integers = [start*2+1 + 2*i for i in range(num)]
        total = sum(integers)
        asked_for = random.choice(['smallest', 'largest', 'middle'])
        if asked_for == 'smallest': answer = str(integers[0])
        elif asked_for == 'largest': answer = str(integers[-1])
        else: answer = str(integers[num//2])
        question = f"The sum of {num} consecutive {num_type} is {total}. What is the **{asked_for}** of these integers?"
        hint = f"Represent the integers algebraically (e.g., n, n+1, n+2... or n, n+2, n+4...). Set their sum equal to {total} and solve for the first integer, n."
        explanation = f"Let the first integer be n. The sum can be written as an equation. Solving for n gives {integers[0]}. The full list of integers is {integers}. The {asked_for} integer is {answer}."
        options = {str(integers[0]), str(integers[-1]), str(int(total/num)), answer}

    # --- Hard Question ---
    elif q_type == 'work_rate':
        time_a = random.randint(4, 10); time_b = random.randint(4, 10)
        while time_a == time_b: time_b = random.randint(4, 10)
        time_together = (time_a * time_b) / (time_a + time_b)
        name1, name2 = random.sample(gh_names, 2)
        question = f"If {name1} can weed a farm in {time_a} hours and {name2} can weed the same farm in {time_b} hours, how long would it take them to finish the job if they work together?"
        answer = f"{time_together:.2f} hours"
        hint = "Add their individual rates of work. The rate is (1 / time). So, (1/A) + (1/B) = 1/Total_Time."
        explanation = f"1. {name1}'s Rate = $\\frac{{1}}{{{time_a}}}$ farms/hr.\n2. {name2}'s Rate = $\\frac{{1}}{{{time_b}}}$ farms/hr.\n3. Combined Rate = $\\frac{{1}}{{{time_a}}} + \\frac{{1}}{{{time_b}}} = \\frac{{{time_b+time_a}}}{{{time_a*time_b}}}$ farms/hr.\n4. Time Together = $\\frac{{1}}{{\\text{{Combined Rate}}}} = \\frac{{{time_a*time_b}}}{{{time_a+time_b}}} \\approx {time_together:.2f}$ hours."
        options = {answer, f"{ (time_a+time_b)/2 :.2f} hours", f"{ abs(time_a-time_b) :.2f} hours"}

    return {"question": question, "options": _finalize_options(options), "answer": answer, "hint": hint, "explanation": explanation, "difficulty": difficulty}


def _generate_shapes_question(difficulty="Medium"):
    """Generates a Shapes/Geometry question based on difficulty, preserving all original sub-types."""
    
    if difficulty == "Easy":
        # Foundational rules for angles and triangles.
        q_type = random.choice(['angles_lines', 'triangles_pythagoras'])
    elif difficulty == "Medium":
        # Standard calculations for 2D shapes.
        q_type = 'area_perimeter'
    else: # Hard
        # More complex 3D calculations and abstract theorems.
        q_type = random.choice(['volume_surface_area', 'circle_theorems'])

    question, answer, hint, explanation = "", "", "", ""
    options = set()

    # --- Easy Questions ---
    if q_type == 'angles_lines':
        angle_type = random.choice(['point', 'straight_line', 'parallel'])
        if angle_type == 'point':
            a1, a2 = random.randint(100, 150), random.randint(80, 120)
            a3 = 360 - (a1 + a2)
            question = f"Three angles meet at a point. Two of the angles are {a1}° and {a2}°. What is the size of the third angle?"
            answer = f"{a3}°"
            hint = "The sum of angles at a point is always 360°."
            explanation = f"Angles at a point add up to 360°. So, the third angle is $360° - ({a1}° + {a2}°) = 360° - {a1+a2}° = {a3}°$."
            options = {answer, f"{180 - a1}°", f"{180 - a2}°"}
        else: # parallel lines (original logic kept)
            angle1 = random.randint(50, 120)
            prop, angle2 = random.choice([("alternate", angle1), ("corresponding", angle1), ("co-interior", 180 - angle1)])
            question = f"In a diagram with two parallel lines cut by a transversal, one angle is {angle1}°. What is the size of its {prop} angle?"
            answer = f"{angle2}°"
            hint = f"Recall the relationship between {prop} angles."
            explanation = f"For parallel lines:\n- Alternate angles are equal.\n- Corresponding angles are equal.\n- Co-interior angles sum to 180°.\nTherefore, the {prop} angle is {answer}."
            options = {answer, f"{180-angle1}°", f"{90}°"}

    elif q_type == 'triangles_pythagoras':
        a, b = random.choice([(3,4), (5,12), (8,15), (7,24), (9,40)])
        c = int(math.sqrt(a**2 + b**2))
        question = f"A right-angled triangle has shorter sides of length ${a}$ cm and ${b}$ cm. Find the length of its hypotenuse."
        answer = f"{c}"
        hint = "Use Pythagoras' theorem: $a^2 + b^2 = c^2$."
        explanation = f"1. By Pythagoras' theorem, $c^2 = a^2 + b^2$.\n2. $c^2 = {a}^2 + {b}^2 = {a**2} + {b**2} = {c**2}$.\n3. $c = \\sqrt{{{c**2}}} = {c}$ cm."
        options = {answer, str(a+b), str(abs(b-a))}

    # --- Medium Question ---
    elif q_type == 'area_perimeter':
        shape = random.choice(['rectangle', 'circle', 'trapezium']) # Original internal randomness preserved
        if shape == 'rectangle':
            l, w = random.randint(10, 30), random.randint(5, 20)
            calc = random.choice(['area', 'perimeter'])
            question = f"A football field in Accra measures {l}m by {w}m. Calculate its {calc}."
            answer = str(l*w) if calc == 'area' else str(2*(l+w))
            hint = "Area of a rectangle is length × width. Perimeter is 2 × (length + width)."
            explanation = f"For a rectangle with length {l} and width {w}:\n- Area = ${l} \\times {w} = {l*w} m^2$.\n- Perimeter = $2({l} + {w}) = {2*(l+w)} m$."
            options = {str(l*w), str(2*(l+w)), str(l+w)}
        elif shape == 'circle':
            r = 7 # Use r=7 for nice pi calculations
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
            options = {answer, str((a+b)*h), str(a*b*h)}

    # --- Hard Questions ---
    elif q_type == 'volume_surface_area':
        shape = random.choice(['cuboid', 'cylinder']) # Original internal randomness preserved
        if shape == 'cuboid':
            l, w, h = random.randint(5,12), random.randint(5,12), random.randint(5,12)
            calc = random.choice(['volume', 'surface area'])
            question = f"A box has dimensions {l}cm by {w}cm by {h}cm. Find its total {calc}."
            answer = str(l*w*h) if calc == 'volume' else str(2*(l*w+w*h+l*h))
            hint = "Volume = l×w×h. Surface Area = 2(lw + wh + lh)."
            explanation = f"For the cuboid:\n- Volume = ${l} \\times {w} \\times {h} = {l*w*h} cm^3$.\n- Surface Area = $2({l*w} + {w*h} + {l*h}) = {2*(l*w+w*h+l*h)} cm^2$."
            options = {str(l*w*h), str(2*(l*w+w*h+l*h))}
        else: # cylinder
            r, h = 7, random.randint(10, 20)
            question = f"A cylindrical tin of Milo has a radius of {r}cm and a height of {h}cm. Find its volume. (Use $\\pi \\approx 22/7$)"
            answer = str(int(Fraction(22,7) * r**2 * h))
            hint = "Volume of a cylinder = $\pi r^2 h$."
            explanation = f"Volume = $\\pi r^2 h = \\frac{{22}}{{7}} \\times {r}^2 \\times {h} = {answer} cm^3$."
            options = {answer, str(int(2*Fraction(22,7)*r*h)), str(int(Fraction(22,7) * r**2))}

    elif q_type == 'circle_theorems':
        angle_at_center = random.randint(40, 120) * 2
        angle_at_circumference = angle_at_center // 2
        question = f"In a circle, an arc subtends an angle of {angle_at_center}° at the center. What angle does it subtend at any point on the remaining part of the circumference?"
        answer = f"{angle_at_circumference}°"
        hint = "Recall the circle theorem: The angle at the center is twice the angle at the circumference."
        explanation = f"The angle at the circumference is half the angle at the center.\nAngle = $\\frac{{{angle_at_center}°}}{{2}} = {angle_at_circumference}°$."
        options = {answer, f"{angle_at_center}°", f"{180-angle_at_center}°"}
        
    return {"question": question, "options": _finalize_options(options), "answer": answer, "hint": hint, "explanation": explanation, "difficulty": difficulty}
def _generate_algebra_basics_question(difficulty="Medium"):
    """Generates an Algebra Basics question based on difficulty, preserving all original sub-types."""
    
    if difficulty == "Easy":
        # Foundational skills: simplifying and solving basic linear equations.
        q_type = random.choice(['simplify_expression', 'solve_linear'])
    elif difficulty == "Medium":
        # Core algebraic techniques: factoring, inequalities, and fractions.
        q_type = random.choice(['factorization', 'solve_inequality', 'algebraic_fractions'])
    else: # Hard
        # Multi-step, complex problems: simultaneous and quadratic equations.
        q_type = random.choice(['solve_simultaneous', 'solve_quadratic'])

    question, answer, hint, explanation = "", "", "", ""
    options = set()

    # --- Easy Questions ---
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
        explanation = f"1. Expand brackets: $({a}x + {a*b}) - ({c}x - {c*d})$.\n2. Simplify: ${a}x + {a*b} - {c}x + {c*d}$.\n3. Collect like terms: $({a-c})x + ({a*b+c*d}) = {x_coeff}x + {const}$."
        options = {answer, f"${a+c}x + {a*b-c*d}$"}

    elif q_type == 'solve_linear':
        a, b, x = random.randint(2, 8), random.randint(5, 20), random.randint(2, 10)
        c = a * x + b
        question = f"Solve for x in the equation: ${a}x + {b} = {c}$"
        answer = str(x)
        hint = "Isolate the term with 'x' on one side of the equation, then divide to find x."
        explanation = f"1. Equation: ${a}x + {b} = {c}$.\n2. Subtract {b} from both sides: ${a}x = {c-b}$.\n3. Divide by {a}: $x = \\frac{{{c-b}}}{{{a}}} = {x}$."
        options = {answer, str(c-b), str((c+b)/a)}
        
    # --- Medium Questions ---
    elif q_type == 'factorization':
        factor_type = random.choice(['diff_squares', 'trinomial']) # Original internal randomness preserved
        if factor_type == 'diff_squares':
            a, b_val = random.randint(2, 10), random.randint(2, 5)
            b = f"{b_val}y"
            question = f"Factorize completely: ${a**2}x^2 - {b_val**2}y^2$"
            answer = f"$({a}x - {b})({a}x + {b})$"
            hint = "Recognize this as a difference of two squares: $A^2 - B^2 = (A-B)(A+B)$."
            explanation = f"Here, $A^2 = {a**2}x^2$ so $A={a}x$, and $B^2 = {b_val**2}y^2$ so $B={b}$.\nThe factorization is $(A-B)(A+B)$, which gives ${answer}$."
            options = {answer, f"$({a}x - {b})^2$", f"({a}x - {b_val})({a}x + {b_val})"}
        else: # trinomial
            r1, r2 = random.randint(-7, 7), random.randint(-7, 7)
            while r1 == 0 or r2 == 0 or r1==r2: r1, r2 = random.randint(-7, 7), random.randint(-7, 7)
            b, c = r1 + r2, r1 * r2
            question = f"Factorize the trinomial: $x^2 + ({b})x + ({c})$"
            answer = f"$(x {'+' if r1 > 0 else '-'} {abs(r1)})(x {'+' if r2 > 0 else '-'} {abs(r2)})$"
            hint = f"Look for two numbers that multiply to give the constant term ({c}) and add to give the x-coefficient ({b})."
            explanation = f"The two numbers are ${r1}$ and ${r2}$, since ${r1} \\times {r2} = {c}$ and ${r1} + {r2} = {b}$.\nTherefore, the factors are $(x + ({r1}))(x + ({r2}))$, which is ${answer}$."
            options = {answer, f"$(x - {r1})(x - {r2})$", f"$(x + {b})(x + {c})$"}

    elif q_type == 'solve_inequality':
        a, b, x = random.randint(2, 5), random.randint(10, 20), random.randint(3, 8)
        c = a*x - b
        question = f"Find the solution to the inequality: ${a}x - {b} > {c}$"
        answer = f"$x > {x}$"
        hint = "Solve this just like a linear equation. Only flip the inequality sign if you multiply or divide by a negative number."
        explanation = f"1. Inequality: ${a}x - {b} > {c}$.\n2. Add {b} to both sides: ${a}x > {c+b}$.\n3. Divide by {a} (a positive number, so the sign stays): $x > \\frac{{{c+b}}}{{{a}}} = {x}$."
        options = {answer, f"$x < {x}$", f"$x > {c-b}"}
        
    elif q_type == 'algebraic_fractions':
        a, b = random.randint(2, 5), random.randint(3, 6)
        while a==b: b = random.randint(3,6)
        question = f"Simplify the algebraic fraction: $\\frac{{x}}{{{a}}} + \\frac{{x}}{{{b}}}$"
        num = a + b; den = a * b; common = math.gcd(num, den); num //= common; den //= common
        answer = f"$\\frac{{{num}x}}{{{den}}}$"
        hint = "To add algebraic fractions, find a common denominator, just like with regular fractions."
        explanation = f"1. The lowest common multiple of {a} and {b} is {a*b}.\n2. $\\frac{{x}}{{{a}}} + \\frac{{x}}{{{b}}} = \\frac{{{b}x}}{{{a*b}}} + \\frac{{{a}x}}{{{a*b}}}$.\n3. Combine and simplify: $\\frac{{({a+b})x}}{{{a*b}}} = {answer}$"
        options = {answer, f"$\\frac{{2x}}{{{a+b}}}$", f"$\\frac{{x^2}}{{{a*b}}}$"}

    # --- Hard Questions ---
    elif q_type == 'solve_simultaneous':
        x, y = random.randint(1, 8), random.randint(1, 8)
        a1, b1, a2, b2 = [random.randint(1, 4) for _ in range(4)]
        while a1*b2 - a2*b1 == 0: a2, b2 = random.randint(1, 4), random.randint(1, 4) # Ensure unique solution
        c1 = a1*x + b1*y
        c2 = a2*x + b2*y
        question = f"Solve the following system of linear equations:\n\n$ {a1}x + {b1}y = {c1} $\n\n$ {a2}x + {b2}y = {c2} $"
        answer = f"x = {x}, y = {y}"
        hint = "Use either the substitution or elimination method to solve for one variable first."
        explanation = f"Using the elimination method, one can solve to find that y = {y}. Substituting this value back into the first equation, ${a1}x + {b1}({y}) = {c1}$, gives x = {x}."
        options = {answer, f"x = {y}, y = {x}", f"x = {c1-c2}, y = {c1+c2}"}
        
    elif q_type == 'solve_quadratic':
        r1, r2 = random.randint(-6, 6), random.randint(-6, 6)
        while r1 == 0 or r2 == 0 or r1 == r2: r1, r2 = random.randint(-6, 6), random.randint(-6, 6)
        b = -(r1 + r2)
        c = r1 * r2
        question = f"Find the roots of the quadratic equation: $x^2 + {b}x + {c} = 0$"
        answer = f"x = {r1} or x = {r2}"
        hint = "Solve by factorizing the quadratic expression or using the quadratic formula: $x = \\frac{{-b \\pm \\sqrt{{b^2-4ac}}}}{{2a}}$."
        explanation = f"This equation can be factorized by finding two numbers that multiply to {c} and add to {-b}. These numbers are {r1} and {r2}.\nSo, the equation becomes $(x - {r1})(x - {r2}) = 0$.\nThe solutions are therefore $x = {r1}$ and $x = {r2}$."
        options = {answer, f"x = {-r1} or x = {-r2}", f"x = {b} or x = {c}"}

    return {"question": question, "options": _finalize_options(options), "answer": answer, "hint": hint, "explanation": explanation, "difficulty": difficulty}


def _generate_linear_algebra_question(difficulty="Medium"):
    """Generates a Linear Algebra question based on difficulty, preserving all original sub-types."""

    if difficulty == "Easy":
        # Foundational 2x2 matrix operations.
        q_type = random.choice(['add_sub', 'determinant'])
    elif difficulty == "Medium":
        # More complex row-by-column multiplication.
        q_type = 'multiply'
    else: # Hard
        # Multi-step process of finding the inverse.
        q_type = 'inverse'

    # Helper function to format a numpy matrix into LaTeX
    def mat_to_latex(m):
        return f"\\begin{{pmatrix}} {m[0,0]} & {m[0,1]} \\\\ {m[1,0]} & {m[1,1]} \\end{{pmatrix}}"

    question, answer, hint, explanation = "", "", "", ""
    options = set()
    mat_a = np.random.randint(-5, 10, size=(2, 2))
    mat_b = np.random.randint(-5, 10, size=(2, 2))

    # --- Easy Questions ---
    if q_type == 'add_sub':
        op, sym, res_mat = random.choice([('add', '+', mat_a + mat_b), ('subtract', '-', mat_a - mat_b)])
        question = f"Given matrices $A = {mat_to_latex(mat_a)}$ and $B = {mat_to_latex(mat_b)}$, find $A {sym} B$."
        answer = f"${mat_to_latex(res_mat)}$"
        hint = f"To {op} matrices, simply {op} their corresponding elements in each position."
        explanation = f"You perform the operation on the element in each position. For example, the top-left element is calculated as: ${mat_a[0,0]} {sym} {mat_b[0,0]} = {res_mat[0,0]}$."
        options = {answer, f"${mat_to_latex(np.dot(mat_a, mat_b))}$", f"${mat_to_latex(mat_a * mat_b)}$"}
    
    elif q_type == 'determinant':
        question = f"Find the determinant of matrix $A = {mat_to_latex(mat_a)}$."
        answer = str(int(np.linalg.det(mat_a)))
        hint = r"For a 2x2 matrix $\begin{pmatrix} a & b \\ c & d \end{pmatrix}$, the determinant is calculated as $ad - bc$."
        explanation = f"Determinant = $(a \\times d) - (b \\times c) = ({mat_a[0,0]} \\times {mat_a[1,1]}) - ({mat_a[0,1]} \\times {mat_a[1,0]}) = {answer}$."
        options = {answer, str(mat_a[0,0]+mat_a[1,1]), str(mat_a[0,0]*mat_a[0,1] - mat_a[1,0]*mat_a[1,1])}

    # --- Medium Question ---
    elif q_type == 'multiply':
        question = f"Find the product $AB$ for the matrices $A = {mat_to_latex(mat_a)}$ and $B = {mat_to_latex(mat_b)}$."
        res_mat = np.dot(mat_a, mat_b)
        answer = f"${mat_to_latex(res_mat)}$"
        hint = "Matrix multiplication is 'row-by-column'. Multiply the elements of each row of the first matrix by the elements of each column of the second matrix and sum the results."
        explanation = f"The top-left element of the result is (row 1 of A) ⋅ (col 1 of B) = $({mat_a[0,0]} \\times {mat_b[0,0]}) + ({mat_a[0,1]} \\times {mat_b[1,0]}) = {res_mat[0,0]}$."
        options = {answer, f"${mat_to_latex(mat_a+mat_b)}$", f"${mat_to_latex(mat_b @ mat_a)}$"}
        
    # --- Hard Question ---
    elif q_type == 'inverse':
        det = int(np.linalg.det(mat_a))
        while det == 0: # Ensure the matrix is invertible
            mat_a = np.random.randint(-5, 10, size=(2, 2))
            det = int(np.linalg.det(mat_a))
        question = f"Find the inverse of the matrix $A = {mat_to_latex(mat_a)}$."
        adj_mat = np.array([[mat_a[1,1], -mat_a[0,1]], [-mat_a[1,0], mat_a[0,0]]])
        answer = f"$\\frac{{1}}{{{det}}}{mat_to_latex(adj_mat)}$"
        hint = r"The inverse is $\frac{1}{\det(A)} \times \text{adj}(A)$, where the adjugate matrix is found by swapping a and d, and negating b and c."
        explanation = f"1. First, find the determinant: $\det(A) = {det}$.\n\n2. Next, find the adjugate matrix: swap the main diagonal elements and negate the others to get ${mat_to_latex(adj_mat)}$.\n\n3. The inverse is $\\frac{{1}}{{\\text{{determinant}}}} \\times \\text{{adjugate}}$, which is ${answer}$."
        options = {answer, f"${mat_to_latex(adj_mat)}$", f"$\\frac{{1}}{{{-det}}}{mat_to_latex(adj_mat)}$"}

    return {"question": question, "options": _finalize_options(options), "answer": answer, "hint": hint, "explanation": explanation, "difficulty": difficulty}

def _generate_logarithms_question(difficulty="Medium"):
    """Generates a Logarithms question based on difficulty, preserving all original sub-types."""
    
    if difficulty == "Easy":
        # Foundational concepts: converting forms and solving simple logs.
        q_type = random.choice(['conversion', 'solve_simple'])
    elif difficulty == "Medium":
        # Applying the core laws of logarithms.
        q_type = 'laws'
    else: # Hard
        # Combining laws with algebraic solving.
        q_type = 'solve_combine'

    question, answer, hint, explanation = "", "", "", ""
    options = set()

    # --- Easy Questions ---
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
        explanation = f"The base of the logarithm (${base}$) becomes the base of the power. The result of the logarithm (${exponent}$) becomes the exponent. The two forms are equivalent."

    elif q_type == 'solve_simple':
        base = random.randint(2, 4)
        result = random.randint(2, 4)
        x_val = base ** result
        question = f"Solve for x: $\\log_{{{base}}}(x) = {result}$"
        answer = str(x_val)
        hint = "Convert the logarithmic equation to its equivalent exponential form to solve for x."
        explanation = f"1. The equation is $\\log_{{{base}}}(x) = {result}$.\n\n2. In exponential form, this is $x = {base}^{{{result}}}$.\n\n3. Therefore, $x = {x_val}$."
        options = {answer, str(base*result), str(result**base)}

    # --- Medium Question ---
    elif q_type == 'laws':
        val1, val2 = random.randint(2, 10), random.randint(2, 10)
        op, sym, res, rule_name = random.choice([
            ('add', '+', f"\\log({val1*val2})", "Product Rule"),
            ('subtract', '-', f"\\log(\\frac{{{val1}}}{{{val2}}})", "Quotient Rule")
        ])
        question = f"Use the laws of logarithms to simplify the expression: $\\log({val1}) {sym} \\log({val2})$"
        answer = f"${res}$"
        hint = f"Recall the {rule_name} for logarithms: $\log(A) + \log(B) = \log(AB)$ and $\log(A) - \log(B) = \log(A/B)$."
        explanation = f"Using the {rule_name}, $\\log({val1}) {sym} \\log({val2})$ simplifies directly to ${res}$."
        options = {answer, f"$\\log({val1+val2})$", f"$\\frac{{\\log({val1})}}{{\\log({val2})}}$"}

    # --- Hard Question ---
    elif q_type == 'solve_combine':
        x_val = random.randint(3, 8)
        b = random.randint(1, x_val - 1)
        result = x_val * (x_val - b)
        question = f"Solve for x: $\\log(x) + \\log(x - {b}) = \\log({result})$"
        answer = str(x_val)
        hint = "First, use the product rule to combine the logarithms on the left side into a single logarithm."
        explanation = (f"1. Combine the logs on the left: $\\log(x(x-{b})) = \\log({result})$.\n\n"
                       f"2. Since the logs (with the same base) are equal, their arguments must be equal: $x^2 - {b}x = {result}$.\n\n"
                       f"3. Rearrange into a quadratic equation: $x^2 - {b}x - {result} = 0$.\n\n"
                       f"4. Factor the quadratic: $(x - {x_val})(x + {x_val-b}) = 0$.\n\n"
                       f"5. The possible solutions are $x={x_val}$ and $x={-(x_val-b)}$. Since the logarithm of a negative number is undefined in this context, the only valid solution is $x={x_val}$.")
        options = {answer, str(-(x_val-b)), str(result+b)}
        
    return {"question": question, "options": _finalize_options(options), "answer": answer, "hint": hint, "explanation": explanation, "difficulty": difficulty}

def _generate_probability_question(difficulty="Medium"):
    """Generates a Probability question based on difficulty, preserving all original sub-types."""

    if difficulty == "Easy":
        # The most fundamental probability calculation.
        q_type = 'simple'
    elif difficulty == "Medium":
        # Involves the union of two events.
        q_type = 'combined'
    else: # Hard
        # Involves dependent, conditional events.
        q_type = 'conditional'

    question, answer, hint, explanation = "", "", "", ""
    options = set()
    
    # --- Easy Question ---
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
        explanation = f"There are {num_chosen} {chosen_color} balls and a total of {total} balls in the bag. So, the probability of picking a {chosen_color} ball is P({chosen_color}) = ${_get_fraction_latex_code(answer_frac)}$."
        options = {answer, _format_fraction_text(Fraction(red if chosen_color=='blue' else blue, total)), "1/2"}

    # --- Medium Question ---
    elif q_type == 'combined':
        die_faces = {1, 2, 3, 4, 5, 6}
        evens = {2, 4, 6}
        greater_than_4 = {5, 6}
        # The union of these two sets are the favorable outcomes
        union = evens.union(greater_than_4)
        
        question = "A fair six-sided die is rolled once. What is the probability of rolling an even number or a number greater than 4?"
        answer_frac = Fraction(len(union), 6)
        answer = _format_fraction_text(answer_frac)
        hint = "Find the set of outcomes for each event, then find their union. Be careful not to double-count outcomes that satisfy both conditions."
        explanation = f"Event A (even) = {evens}. Event B (>4) = {greater_than_4}.\nThe combined event 'A or B' is the union of these sets: {union}, which has {len(union)} favorable outcomes.\nSince there are 6 total outcomes on a die, the probability is ${_get_fraction_latex_code(answer_frac)}$."
        options = {answer, _format_fraction_text(Fraction(len(evens)+len(greater_than_4), 6)), _format_fraction_text(Fraction(len(evens), 6))}

    # --- Hard Question ---
    elif q_type == 'conditional':
        black = random.randint(3, 6)
        white = random.randint(3, 6)
        total = black + white
        question = f"A box in a shop in Kumasi contains {black} black pens and {white} white pens. Two pens are drawn one after the other **without replacement**. What is the probability that both are white?"
        prob_frac = Fraction(white, total) * Fraction(white - 1, total - 1)
        answer = _format_fraction_text(prob_frac)
        hint = "Calculate the probability of the first event, then the probability of the second event *given the first has occurred*, and multiply them."
        explanation = f"The probability that the first pen is white is P(1st is white) = $\\frac{{{white}}}{{{total}}}$.\nAfter drawing one white pen, there are now {white-1} white pens and {total-1} total pens left.\nThe probability that the second pen is also white is P(2nd is white) = $\\frac{{{white-1}}}{{{total-1}}}$.\nThe total probability is the product of these two: $\\frac{{{white}}}{{{total}}} \\times \\frac{{{white-1}}}{{{total-1}}} = {_get_fraction_latex_code(prob_frac)}$."
        # Distractor represents the case 'with replacement'
        options = {answer, _format_fraction_text(Fraction(white,total) * Fraction(white, total)), _format_fraction_text(Fraction(white-1, total-1))}

    return {"question": question, "options": _finalize_options(options, "fraction"), "answer": answer, "hint": hint, "explanation": explanation, "difficulty": difficulty}

def _generate_binomial_theorem_question(difficulty="Medium"):
    """Generates a Binomial Theorem question based on difficulty, preserving all original sub-types."""

    if difficulty == "Easy":
        # A new, foundational question type to test direct reading of Pascal's Triangle.
        q_type = 'pascal_read'
    elif difficulty == "Medium":
        # Your original 'find_coefficient' question.
        q_type = 'find_coefficient'
    else: # Hard
        # Your original 'find_term' question.
        q_type = 'find_term'

    question, answer, hint, explanation = "", "", "", ""
    options = set()
    
    # --- Easy Question ---
    if q_type == 'pascal_read':
        n = random.randint(3, 5)
        pascal_str, pascal_row = _generate_pascal_data(n)
        k = random.randint(1, n-1) # Ask for the 2nd, 3rd, or 4th coefficient etc.
        term_ord = {1: "2nd", 2: "3rd", 3: "4th", 4: "5th"}.get(k, f"{k+1}th")
        question = f"Using Pascal's Triangle, what is the **{term_ord}** coefficient in the expansion of $(a+b)^{n}$?"
        answer = str(pascal_row[k])
        hint = "The coefficients for the expansion of $(a+b)^n$ are found in the row of Pascal's Triangle that starts with 1, n, ..."
        explanation = f"Pascal's Triangle up to row {n} is:\n{pascal_str}\nThe row for n={n} is `{pascal_row}`. The {term_ord} number in that list is **{answer}**."
        options = set(str(c) for c in pascal_row)
        options.add(answer)

    # --- Medium Question ---
    elif q_type == 'find_coefficient':
        n = random.randint(4, 7)
        a, b = random.randint(1, 4), random.randint(1, 4)
        k = random.randint(2, n - 2)
        question = f"Find the coefficient of the $x^{{{k}}}$ term in the expansion of $({a}x + {b})^{{{n}}}$."
        coefficient = math.comb(n, k) * (a**k) * (b**(n-k))
        answer = str(coefficient)
        hint = f"Use the binomial formula for a specific term: $\\binom{{n}}{{k}} (ax)^k b^{{n-k}}$. Here, n={n} and k={k}."
        explanation = (f"The term containing $x^{k}$ is given by the formula $T_{k+1} = \\binom{{n}}{{k}} (ax)^k b^{{n-k}}$.\n"
                       f"The coefficient part is $\\binom{{{n}}}{{{k}}} a^k b^{{n-k}}$.\n"
                       f"$= {math.comb(n, k)} \\times {a}^{{{k}}} \\times {b}^{{{n-k}}} = {answer}$."
                      )
        distractor1 = str(math.comb(n, k) * (a**k))
        distractor2 = str(math.comb(n, k))
        options = {answer, distractor1, distractor2}

    # --- Hard Question ---
    elif q_type == 'find_term':
        n = random.randint(5, 8)
        a, b = random.randint(1, 4), random.randint(1, 4)
        r = random.randint(2, n - 1)
        k = r - 1
        question = f"Find the **{r}th term** in the expansion of $({a}x + {b})^{{{n}}}$."
        term_coeff = math.comb(n, k) * (a**k) * (b**(n-k))
        answer = f"${term_coeff}x^{{{k}}}$"
        hint = f"The r-th term is given by the formula $T_r = \\binom{{n}}{{r-1}} (ax)^{{r-1}} b^{{n-(r-1)}}$."
        explanation = (f"To find the {r}th term, we use an index of $k = r-1 = {k}$.\n"
                       f"The term is given by the formula $T_{r} = \\binom{{n}}{{k}}(ax)^{k}(b)^{{n-k}}$.\n"
                       f"$= \\binom{{{n}}}{{{k}}} ({a}x)^{{{k}}} ({b})^{{{n-k}}}$\n"
                       f"$= {math.comb(n, k)} \\times {a**k}x^{k} \\times {b**(n-k)}$\n"
                       f"$= {term_coeff}x^{{{k}}}$."
                       )
        distractor_coeff = math.comb(n, r) * (a**r) * (b**(n-r)) if r < n else math.comb(n, k) * (a**k)
        distractor = f"${distractor_coeff}x^{{{r}}}$"
        options = {answer, distractor, f"${term_coeff}x^{{{r}}}$"}

    return {"question": question, "options": _finalize_options(options), "answer": answer, "hint": hint, "explanation": explanation, "difficulty": difficulty}
def _generate_polynomial_functions_question(difficulty="Medium"):
    """Generates a Polynomial Functions question based on difficulty, preserving all original sub-types."""

    if difficulty == "Easy":
        # Direct application of the Remainder Theorem.
        q_type = 'remainder_theorem'
    elif difficulty == "Medium":
        # Using the Factor Theorem to find an unknown.
        q_type = 'factor_theorem'
    else: # Hard
        # A multi-step problem combining the Factor Theorem with solving a quadratic.
        q_type = 'find_all_roots'

    question, answer, hint, explanation = "", "", "", ""
    options = set()

    # --- Easy Question ---
    if q_type == 'remainder_theorem':
        a, b, c, d = [random.randint(-5, 5) for _ in range(4)]
        while a == 0: a = random.randint(-5, 5) # Ensure it's a cubic
        divisor_root = random.randint(-3, 3)
        question = f"Find the remainder when the polynomial $P(x) = {a}x^3 + {b}x^2 + {c}x + {d}$ is divided by $(x - {divisor_root})$."
        # Remainder is P(divisor_root)
        remainder = a*(divisor_root**3) + b*(divisor_root**2) + c*divisor_root + d
        answer = str(remainder)
        hint = f"According to the Remainder Theorem, the remainder when $P(x)$ is divided by $(x-a)$ is simply $P(a)$. In this case, a = {divisor_root}."
        explanation = f"We need to evaluate $P({divisor_root})$:\n$P({divisor_root}) = {a}({divisor_root})^3 + {b}({divisor_root})^2 + {c}({divisor_root}) + {d} = {remainder}$."
        options = {answer, str(d), str(a+b+c+d)}

    # --- Medium Question ---
    elif q_type == 'factor_theorem':
        root = random.randint(1, 3)
        a, c, d = random.randint(1, 3), random.randint(1, 5), random.randint(1, 10)
        # We set P(root) = 0 and solve for k: k = -(a*root^3 + c*root + d) / root^2
        # We need the numerator to be divisible by root^2 for a clean integer k
        while (a*(root**3) + c*root + d) % (root**2) != 0:
            a, c, d = random.randint(1, 3), random.randint(1, 5), random.randint(1, 10)
        k = - (a*(root**3) + c*root + d) // (root**2)
        if k == 0: return _generate_polynomial_functions_question(difficulty=difficulty) # Regenerate for non-trivial k
        
        question = f"Given that $(x - {root})$ is a factor of the polynomial $P(x) = {a}x^3 + kx^2 + {c}x + {d}$, find the value of the constant $k$."
        answer = str(k)
        hint = f"By the Factor Theorem, if $(x-a)$ is a factor of $P(x)$, then $P(a) = 0$. Set $P({root}) = 0$ and solve for $k$."
        explanation = f"Since $(x - {root})$ is a factor, we know that $P({root}) = 0$.\n$P({root}) = {a}({root})^3 + k({root})^2 + {c}({root}) + {d} = 0$.\n${a*root**3} + {k*root**2}k + {c*root+d} = 0$.\n${k*root**2}k = -({a*root**3 + c*root+d})$.\n$k = {- (a*root**3 + c*root+d)} / {root**2} = {k}$."
        options = {answer, str(-k), str(root), str(a+c+d)}
        
    # --- Hard Question ---
    elif q_type == 'find_all_roots':
        r1, r2, r3 = random.sample(range(-4, 5), 3)
        while 0 in [r1, r2, r3]: r1, r2, r3 = random.sample(range(-4, 5), 3) # Avoid zero roots for simplicity
        # P(x) = (x-r1)(x-r2)(x-r3) = x^3 - (r1+r2+r3)x^2 + (r1r2+r1r3+r2r3)x - r1r2r3
        b = -(r1 + r2 + r3)
        c = (r1*r2 + r1*r3 + r2*r3)
        d = -(r1*r2*r3)
        poly_str = f"x^3 {'+' if b >= 0 else ''} {b}x^2 {'+' if c >= 0 else ''} {c}x {'+' if d >= 0 else ''} {d}"
        given_factor_root = r1
        
        question = f"Given that $(x - {given_factor_root})$ is a factor of the polynomial $P(x) = {poly_str}$, find all the roots of the equation $P(x) = 0$."
        all_roots = sorted([r1, r2, r3])
        answer = f"x = {all_roots[0]}, {all_roots[1]}, {all_roots[2]}"
        hint = "Use the given factor to perform polynomial long division (or synthetic division) on P(x). Then, solve the resulting quadratic equation to find the other two roots."
        explanation = (f"1. We know $x={given_factor_root}$ is one root.\n"
                       f"2. Dividing $P(x)$ by $(x - {given_factor_root})$ gives the quadratic factor $x^2 - ({r2+r3})x + {r2*r3} = 0$.\n"
                       f"3. Factoring this quadratic gives $(x - {r2})(x - {r3}) = 0$, so the other roots are $x={r2}$ and $x={r3}$.\n"
                       f"4. The complete set of roots is ${answer}$.")
        options = {answer, f"x = {r1}, {-r2}, {-r3}", f"x = {b}, {c}, {d}"}

    return {"question": question, "options": _finalize_options(options), "answer": answer, "hint": hint, "explanation": explanation, "difficulty": difficulty}

def _generate_rational_functions_question(difficulty="Medium"):
    """Generates a Rational Functions question based on difficulty, preserving all original sub-types."""

    if difficulty == "Easy":
        # Foundational skills: simplifying and solving simple rational equations.
        q_type = random.choice(['simplify_expression', 'solve_equation'])
    elif difficulty == "Medium":
        # Core concepts of identifying key features from the equation.
        q_type = random.choice(['domain', 'vertical_asymptotes', 'horizontal_asymptotes'])
    else: # Hard
        # More complex analysis requiring multiple steps (factoring, division).
        q_type = random.choice(['find_holes', 'slant_asymptotes'])

    question, answer, hint, explanation = "", "", "", ""
    options = set()

    # --- Easy Questions ---
    if q_type == 'simplify_expression':
        hole_root, num_root, den_root = random.sample(range(-5, 6), 3)
        while hole_root == 0 or num_root == 0 or den_root == 0: hole_root, num_root, den_root = random.sample(range(-5, 6), 3)
        # Numerator: (x - hole_root)(x - num_root)
        num_poly = [1, -(hole_root + num_root), hole_root * num_root]
        # Denominator: (x - hole_root)(x - den_root)
        den_poly = [1, -(hole_root + den_root), hole_root * den_root]
        func_str = f"f(x) = \\frac{{{_poly_to_str(num_poly)}}}{{{_poly_to_str(den_poly)}}}"
        question = f"Simplify the rational expression completely: ${func_str}$"
        answer = f"$\\frac{{x {'-' if num_root > 0 else '+'} {abs(num_root)}}}{{x {'-' if den_root > 0 else '+'} {abs(den_root)}}}$"
        hint = "Factor both the numerator and the denominator, then cancel any common factors."
        explanation = f"1. Factored form: $f(x) = \\frac{{(x - {hole_root})(x - {num_root})}}{{(x - {hole_root})(x - {den_root})}}$.\n\n2. Cancel the common factor $(x - {hole_root})$.\n\n3. The simplified expression is **{answer}**."
        options = {answer, f"$\\frac{{x - {hole_root}}}{{x - {den_root}}}$"}

    elif q_type == 'solve_equation':
        b, c, x_sol = random.sample(range(-5, 6), 3)
        while x_sol == b: x_sol = random.randint(-5, 6) # Ensure solution is not extraneous
        a = c * (x_sol - b)
        if a==0 or c==0: return _generate_rational_functions_question(difficulty=difficulty)
        question = f"Solve for x: $\\frac{{{a}}}{{x - {b}}} = {c}$"
        answer = str(x_sol)
        hint = "Multiply both sides by the denominator to eliminate the fraction, then solve the resulting linear equation."
        explanation = f"1. Multiply both sides by $(x - {b})$: ${a} = {c}(x - {b})$.\n\n2. Distribute: ${a} = {c}x - {c*b}$.\n\n3. Solve for x: ${c}x = {a} + {c*b} \\implies x = \\frac{{{a+c*b}}}{{{c}}} = {x_sol}$.\n\n4. Check: The solution $x={x_sol}$ does not make the original denominator zero, so it is a valid solution."
        options = {answer, str(b), str(x_sol+1)}

    # --- Medium Questions ---
    elif q_type in ['domain', 'vertical_asymptotes']:
        r1, r2 = random.sample(range(-5, 6), 2)
        n_r = r1 + 1 if r1 != r2 -1 else r1 + 2
        num_poly = [1, -n_r]; den_poly = [1, -(r1+r2), r1*r2]
        func_str = f"f(x) = \\frac{{{_poly_to_str(num_poly)}}}{{{_poly_to_str(den_poly)}}}"
        if q_type == 'domain':
            question = f"Find the domain of the function: ${func_str}$"
            answer = f"All real numbers except $x={r1}$ and $x={r2}$"
            hint = "The domain includes all real numbers except for the values of x that make the denominator equal to zero."
            explanation = f"1. Set the denominator to zero: ${_poly_to_str(den_poly)} = 0$.\n\n2. Factor: $(x - {r1})(x - {r2}) = 0$.\n\n3. The function is undefined at $x={r1}$ and $x={r2}$."
            options = {answer, f"All real numbers except $x={n_r}$", f"All real numbers"}
        else: # vertical_asymptotes
            question = f"Find the equations of the vertical asymptotes for the function: ${func_str}$"
            answer = f"$x={r1}, x={r2}$"
            hint = "Vertical asymptotes occur at the x-values where the denominator is zero (and the factor does not cancel)."
            explanation = f"1. Since no factors cancel, we set the denominator to zero: $(x - {r1})(x - {r2}) = 0$.\n\n2. The vertical asymptotes are the lines $x={r1}$ and $x={r2}$."
            options = {answer, f"$y={r1}, y={r2}$", f"$x={n_r}$"}

    elif q_type == 'horizontal_asymptotes':
        case = random.choice(['top_less', 'equal', 'top_greater'])
        if case == 'top_less': # Degree of Numerator < Degree of Denominator
            num_poly, den_poly = [random.randint(1, 5)], [random.randint(1, 3), random.randint(1, 5), random.randint(1, 5)]
            answer, hint = "$y=0$", "If the denominator's degree is greater, the horizontal asymptote is y=0."
        elif case == 'equal': # Degrees are equal
            c1, c2 = random.randint(1, 6), random.randint(1, 6)
            num_poly, den_poly = [c1, random.randint(1, 5)], [c2, random.randint(1, 5)]
            ha = Fraction(c1, c2)
            answer, hint = f"$y = {_get_fraction_latex_code(ha)}$", "If degrees are equal, the asymptote is the ratio of the leading coefficients."
        else: # top_greater
            num_poly, den_poly = [random.randint(1, 3), random.randint(1, 5), random.randint(1, 5)], [random.randint(1, 5), random.randint(1, 5)]
            answer, hint = "None", "If the numerator's degree is greater, there is no horizontal asymptote (but there may be a slant one)."
        func_str = f"f(x) = \\frac{{{_poly_to_str(num_poly)}}}{{{_poly_to_str(den_poly)}}}"
        question = f"Find the equation of the horizontal asymptote for the function: ${func_str}$"
        explanation = f"We compare the degree of the numerator and the denominator. {hint} Therefore, the horizontal asymptote is **{answer}**."
        options = {"$y=0$", "$y=1$", "None", answer}

    # --- Hard Questions ---
    elif q_type == 'find_holes':
        hole_root, num_root, den_root = random.sample(range(-5, 6), 3)
        num_poly = [1, -(hole_root + num_root), hole_root * num_root]
        den_poly = [1, -(hole_root + den_root), hole_root * den_root]
        func_str = f"f(x) = \\frac{{{_poly_to_str(num_poly)}}}{{{_poly_to_str(den_poly)}}}"
        y_hole = Fraction(hole_root - num_root, hole_root - den_root)
        question = f"Find the coordinates of the hole (removable discontinuity) in the graph of: ${func_str}$"
        answer = f"$({hole_root}, {_get_fraction_latex_code(y_hole)})$"
        hint = "Factor the numerator and denominator. The cancelled factor gives the x-coordinate of the hole. Plug this x-value into the simplified function to find the y-coordinate."
        explanation = f"1. Factor: $f(x) = \\frac{{(x - {hole_root})(x - {num_root})}}{{(x - {hole_root})(x - {den_root})}}$.\n\n2. The common factor $(x-{hole_root})$ creates a hole at $x={hole_root}$.\n\n3. Use the simplified function $g(x) = \\frac{{x - {num_root}}}{{x - {den_root}}}$ to find the y-coordinate: $g({hole_root}) = \\frac{{{hole_root} - {num_root}}}{{{hole_root} - {den_root}}} = {_get_fraction_latex_code(y_hole)}$.\n\n4. The hole is at **{answer}**."
        options = {answer, f"$x = {hole_root}$", f"$x = {den_root}$"}

    elif q_type == 'slant_asymptotes':
        r1 = random.randint(-4, 4)
        a, b = random.randint(1, 3), random.randint(-3, 3)
        k = random.randint(1, 5) # Remainder
        den_poly = [1, -r1] # (x - r1)
        quotient_poly = [a, b] # ax + b
        num_poly = [a, b - a*r1, -b*r1 + k]
        func_str = f"f(x) = \\frac{{{_poly_to_str(num_poly)}}}{{{_poly_to_str(den_poly)}}}"
        question = f"Find the equation of the slant (oblique) asymptote for the function: ${func_str}$"
        answer = f"$y = {_poly_to_str(quotient_poly)}$"
        hint = "A slant asymptote exists when the degree of the numerator is exactly one greater than the denominator. Use polynomial long division to find it."
        explanation = f"To find the slant asymptote, we divide the numerator by the denominator.\n\n$({_poly_to_str(num_poly)}) \\div ({_poly_to_str(den_poly)})$ gives a quotient of $({_poly_to_str(quotient_poly)})$ and a remainder of ${k}$.\n\nThe slant asymptote is the quotient part: **{answer}**."
        options = {answer, f"$y = {_poly_to_str([a,b+1])}$", f"y = {a}x"}

    return {"question": question, "options": _finalize_options(options), "answer": answer, "hint": hint, "explanation": explanation, "difficulty": difficulty}

def _generate_trigonometry_question(difficulty="Medium"):
    """Generates a Trigonometry question based on difficulty, preserving all original sub-types."""
    
    if difficulty == "Easy":
        q_type = 'identity'
    elif difficulty == "Medium":
        q_type = 'solve_equation'
    else: # Hard
        q_type = 'cosine_rule'

    question, answer, hint, explanation = "", "", "", ""
    options = set()

    # --- Easy Question ---
    if q_type == 'identity':
        question = r"Simplify the expression $\frac{{\sin^2\theta}}{{1 - \cos\theta}}$."
        answer = r"$1 + \cos\theta$"
        hint = "Use the fundamental Pythagorean identity $\sin^2\theta + \cos^2\theta = 1$ and then factorize the numerator as a difference of two squares."
        # CORRECTED EXPLANATION: Uses newlines (\n) instead of <br> tags for robustness.
        explanation = (
            "1. Rewrite the numerator using the identity: $\sin^2\theta = 1 - \cos^2\theta$.\n"
            "2. Factor the numerator: $1 - \cos^2\theta = (1 - \cos\theta)(1 + \cos\theta)$.\n"
            "3. The expression becomes $\\frac{{(1 - \cos\theta)(1 + \cos\theta)}}{{1 - \cos\theta}}$.\n"
            "4. Cancel the common term $(1 - \cos\theta)$, leaving **$1 + \cos\theta$**."
        )
        options = {answer, r"$1 - \cos\theta$", r"$\cos\theta$", r"$\sin\theta$"}

    # --- Medium Question ---
    elif q_type == 'solve_equation':
        trig_values = {
            "sin": {"1/2": 30, "√3/2": 60, "1/√2": 45},
            "cos": {"1/2": 60, "√3/2": 30, "1/√2": 45},
            "tan": {"1": 45, "√3": 60, "1/√3": 30}
        }
        func_name = random.choice(["sin", "cos", "tan"])
        val_str, principal_val = random.choice(list(trig_values[func_name].items()))
        
        if func_name == "sin": quadrants, sol2 = [1, 2], 180 - principal_val
        elif func_name == "cos": quadrants, sol2 = [1, 4], 360 - principal_val
        else: quadrants, sol2 = [1, 3], 180 + principal_val
        
        question = f"Solve the equation ${func_name}(\\theta) = {val_str}$ for $0^\\circ \le \\theta \le 360^\\circ$."
        answer = f"{principal_val}°, {sol2}°"
        hint = f"Find the principal value (the acute angle). Then use the CAST rule to find the second solution in the range. {func_name} is positive in Quadrants {quadrants[0]} and {quadrants[1]}."
        explanation = (
            f"1. The principal (acute) angle for which ${func_name}(\\theta) = {val_str}$ is $\\theta = {principal_val}^\\circ$.\n"
            f"2. Since ${func_name}(\\theta)$ is positive, we look for solutions in Quadrant 1 and Quadrant {quadrants[1]}.\n"
            f"3. Quadrant 1 solution is {principal_val}°.\n"
            f"4. Quadrant {quadrants[1]} solution is ${'180° - ' if func_name=='sin' else '360° - ' if func_name=='cos' else '180° + '}{principal_val}° = {sol2}°$.\n"
            f"5. The two solutions are **{answer}**."
        )
        options = {answer, f"{principal_val}°", f"{principal_val}°, {180+principal_val}°"}

    # --- Hard Question ---
    elif q_type == 'cosine_rule':
        a, b, C_deg = random.randint(5, 25), random.randint(5, 25), random.choice([30, 45, 60, 120])
        c_sq = a**2 + b**2 - 2*a*b*math.cos(math.radians(C_deg))
        c = round(math.sqrt(c_sq), 2)
        question = f"In triangle ABC, side $a = {a}$ m, side $b = {b}$ m, and the included angle $C = {C_deg}^\\circ$. Find the length of the third side, $c$, to two decimal places."
        answer = f"{c} m"
        hint = "When you have two sides and the angle between them (SAS), use the Cosine Rule: $c^2 = a^2 + b^2 - 2ab\\cos(C)$."
        explanation = (
            f"1. $c^2 = {a}^2 + {b}^2 - 2({a})({b})\\cos({C_deg}^\\circ)$.\n"
            f"2. $c^2 = {a**2} + {b**2} - 2({a})({b})({round(math.cos(math.radians(C_deg)), 3)}) \\approx {round(c_sq, 2)}$.\n"
            f"3. $c = \\sqrt{{{round(c_sq, 2)}}} \\approx {c}$ m."
        )
        options = {answer, f"{round(math.sqrt(a**2 + b**2), 2)} m", f"{round(a+b - C_deg, 2)} m"}

    return {"question": question, "options": _finalize_options(options), "answer": answer, "hint": hint, "explanation": explanation, "difficulty": difficulty}
def _generate_vectors_question(difficulty="Medium"):
    """Generates a Vectors question based on difficulty, preserving all original sub-types."""

    if difficulty == "Easy":
        # Basic scalar multiplication and vector addition/subtraction.
        q_type = 'algebra'
    elif difficulty == "Medium":
        # Calculating the length/magnitude of a vector.
        q_type = 'magnitude'
    else: # Hard
        # Multi-step problem to find the angle between vectors using the dot product.
        q_type = 'dot_product'

    question, answer, hint, explanation = "", "", "", ""
    options = set()
    
    # --- Easy Question ---
    if q_type == 'algebra':
        a = np.array([random.randint(-5, 5), random.randint(-5, 5)])
        b = np.array([random.randint(-5, 5), random.randint(-5, 5)])
        s1, s2 = random.randint(2, 4), random.randint(2, 4)
        question = f"Given vectors $\\mathbf{{a}} = \\binom{{{a[0]}}}{{{a[1]}}}$ and $\\mathbf{{b}} = \\binom{{{b[0]}}}{{{b[1]}}}$, find the resulting vector from the operation ${s1}\\mathbf{{a}} - {s2}\\mathbf{{b}}$."
        result_vec = s1*a - s2*b
        answer = f"$\\binom{{{result_vec[0]}}}{{{result_vec[1]}}}$"
        hint = "First, multiply each vector by its scalar. Then, subtract the corresponding components of the resulting vectors."
        explanation = (f"1. ${s1}\\mathbf{{a}} = {s1}\\binom{{{a[0]}}}{{{a[1]}}} = \\binom{{{s1*a[0]}}}{{{s1*a[1]}}}$.\n"
                       f"2. ${s2}\\mathbf{{b}} = {s2}\\binom{{{b[0]}}}{{{b[1]}}} = \\binom{{{s2*b[0]}}}{{{s2*b[1]}}}$.\n"
                       f"3. Subtract the results: $\\binom{{{s1*a[0]}}}{{{s1*a[1]}}} - \\binom{{{s2*b[0]}}}{{{s2*b[1]}}} = \\binom{{{s1*a[0] - s2*b[0]}}}{{{s1*a[1] - s2*b[1]}}} = {answer}$."
                      )
        options = {answer, f"$\\binom{{{a[0]-b[0]}}}{{{a[1]-b[1]}}}$", f"$\\binom{{{s1*a[0] + s2*b[0]}}}{{{s1*a[1] + s2*b[1]}}}$"}

    # --- Medium Question ---
    elif q_type == 'magnitude':
        v = np.array([random.randint(2, 12), random.randint(2, 12)])
        question = f"Find the magnitude (or length) of the vector $\\mathbf{{v}} = {v[0]}\\mathbf{{i}} + {v[1]}\\mathbf{{j}}$."
        magnitude = round(np.linalg.norm(v), 2)
        answer = str(magnitude)
        hint = "The magnitude of a vector $x\\mathbf{i} + y\\mathbf{j}$ is found using the formula $|\\mathbf{{v}}| = \\sqrt{x^2 + y^2}$."
        explanation = f"Magnitude $|\mathbf{{v}}| = \sqrt{{({v[0]})^2 + ({v[1]})^2}} = \sqrt{{{v[0]**2} + {v[1]**2}}} = \sqrt{{{v[0]**2+v[1]**2}}} \\approx {answer}$."
        options = {answer, str(v[0]+v[1]), str(v[0]**2+v[1]**2)}

    # --- Hard Question ---
    elif q_type == 'dot_product':
        a = np.array([random.randint(-5, 5), random.randint(-5, 5)])
        b = np.array([random.randint(-5, 5), random.randint(-5, 5)])
        while np.linalg.norm(a) == 0 or np.linalg.norm(b) == 0: # Avoid zero vectors to prevent division by zero
             a = np.array([random.randint(-5, 5), random.randint(-5, 5)])
             b = np.array([random.randint(-5, 5), random.randint(-5, 5)])
        
        question = f"Find the angle between the vectors $\\mathbf{{a}} = \\binom{{{a[0]}}}{{{a[1]}}}$ and $\\mathbf{{b}} = \\binom{{{b[0]}}}{{{b[1]}}}$ to the nearest degree."
        dot_product = np.dot(a, b)
        mag_a, mag_b = np.linalg.norm(a), np.linalg.norm(b)
        cos_theta = dot_product / (mag_a * mag_b)
        angle_rad = np.arccos(np.clip(cos_theta, -1.0, 1.0))
        angle_deg = round(np.degrees(angle_rad))
        answer = f"{angle_deg}°"
        hint = "Use the dot product formula: $\\cos\\theta = \\frac{{\\mathbf{a} \\cdot \\mathbf{b}}}{{|\mathbf{a}| |\\mathbf{b}|}}$."
        explanation = (f"1. Dot Product: $\\mathbf{{a}} \\cdot \\mathbf{{b}} = ({a[0]})({b[0]}) + ({a[1]})({b[1]}) = {dot_product}$.\n"
                       f"2. Magnitudes: $|\mathbf{{a}}| \\approx {round(mag_a, 2)}$, $|\mathbf{{b}}| \\approx {round(mag_b, 2)}$.\n"
                       f"3. $\\cos\\theta = \\frac{{{dot_product}}}{{{round(mag_a,2)} \\times {round(mag_b,2)}}} \\approx {round(cos_theta, 3)}$.\n"
                       f"4. $\\theta = \\arccos({round(cos_theta, 3)}) \\approx {answer}$."
                      )
        options = {answer, f"{round(dot_product)}°", f"{90}°"}

    return {"question": question, "options": _finalize_options(options), "answer": answer, "hint": hint, "explanation": explanation, "difficulty": difficulty}

# --- PASTE THE 5 NEW TOPIC GENERATORS HERE ---

def _generate_statistics_question(difficulty="Medium"):
    """Generates a Statistics question based on difficulty, preserving all original sub-types."""
    
    if difficulty == "Easy":
        # The most basic measures of data.
        q_type = random.choice(['mode', 'range'])
    elif difficulty == "Medium":
        # Core measures of central tendency.
        q_type = random.choice(['mean', 'median'])
    else: # Hard
        # More complex calculations involving grouped data or measures of spread.
        q_type = random.choice(['frequency_tables', 'std_dev'])

    question, answer, hint, explanation = "", "", "", ""
    options = set()
    
    # --- Easy Questions ---
    if q_type == 'mode':
        k = random.randint(4, 5)
        base_data = random.sample(range(10, 50), k=k)
        mode_val = random.choice(base_data)
        data = base_data + [mode_val, mode_val] # Ensure a clear mode
        random.shuffle(data)
        question = f"What is the mode of the following set of numbers representing daily sales at a stall in Kejetia Market? `{data}`"
        answer = str(mode_val)
        hint = "The mode is the number that appears most frequently in a data set."
        explanation = f"By counting the occurrences of each number in the sorted list `{sorted(data)}`, we can see that **{answer}** appears most often (3 times)."
        options = {answer, str(int(np.mean(data))), str(np.median(data))}

    elif q_type == 'range':
        k = random.randint(5, 7)
        data = random.sample(range(10, 150), k=k)
        range_val = max(data) - min(data)
        question = f"Calculate the range of the following daily temperatures recorded in Kumasi: `{data}`"
        answer = str(range_val)
        hint = "The range is the difference between the highest and lowest values in the dataset."
        explanation = f"1. The highest value (Maximum) is `{max(data)}`.\n\n2. The lowest value (Minimum) is `{min(data)}`.\n\n3. Range = Maximum - Minimum = `{max(data)} - {min(data)} = {answer}`."
        options = {answer, str(max(data) + min(data)), str(max(data))}

    # --- Medium Questions ---
    elif q_type == 'mean':
        k = random.randint(5, 7)
        data = sorted(random.sample(range(5, 100), k=k))
        mean_val = sum(data) / len(data)
        question = f"A student in Accra recorded the following scores on their quizzes: `{data}`. What is the mean score, rounded to one decimal place?"
        answer = f"{mean_val:.1f}"
        hint = "The mean is the sum of all values divided by the number of values."
        explanation = f"1. Sum of values: `{'+'.join(map(str, data))} = {sum(data)}`\n\n2. Number of values: `{len(data)}`\n\n3. Mean = Sum / Count = `{sum(data)} / {len(data)} \\approx {answer}`."
        options = {answer, f"{np.median(data):.1f}", str(max(data)-min(data))}

    elif q_type == 'median':
        k = random.choice([5, 6, 7]) # Odd or even number of items
        data = sorted(random.sample(range(5, 100), k=k))
        median_val = np.median(data)
        question = f"Find the median of the following dataset: `{data}`"
        answer = str(median_val)
        hint = "First, sort the data. The median is the middle value. If there are two middle values, it's their average."
        explanation = f"1. The data must be sorted: `{data}`.\n\n2. Since there are {k} values, the median is the middle value. The calculated median is **{answer}**."
        options = {answer, f"{sum(data)/len(data):.1f}", str(data[0])}

    # --- Hard Questions ---
    elif q_type == 'frequency_tables':
        scores = [1, 2, 3, 4, 5]
        freqs = [random.randint(2, 10) for _ in range(5)]
        table_md = "| Score (x) | Frequency (f) |\n|---|---|\n"
        fx_calcs = []
        for s, f in zip(scores, freqs):
            table_md += f"| {s} | {f} |\n"
            fx_calcs.append(f"{s}x{f}={s*f}")

        total_items = sum(freqs)
        total_sum = sum(s * f for s, f in zip(scores, freqs))
        mean_val = total_sum / total_items

        question = f"The table below shows the results of a quiz. What is the mean score?\n\n{table_md}"
        answer = f"{mean_val:.2f}"
        hint = "To find the mean from a frequency table, calculate the sum of (score × frequency) for each row, then divide by the total frequency."
        explanation = f"1. Calculate `fx` for each row and sum them: `{', '.join(fx_calcs)}`. The sum is $\\sum fx = {total_sum}$.\n\n2. Sum the frequencies: $\\sum f = {total_items}$.\n\n3. Mean = $\\frac{{\\sum fx}}{{\\sum f}} = \\frac{{{total_sum}}}{{{total_items}}} \\approx {answer}$."
        options = {answer, f"{total_items/len(scores):.2f}", f"{total_sum / 5:.2f}"}

    elif q_type == 'std_dev':
        k = random.randint(4, 5)
        data = random.sample(range(10, 30), k=k)
        std_dev_val = np.std(data)
        question = f"Calculate the population standard deviation of the dataset: `{data}`. Round to two decimal places."
        answer = f"{std_dev_val:.2f}"
        hint = "1. Find the mean. 2. For each number, subtract the mean and square the result. 3. Find the average of those squared differences (the variance). 4. Take the square root of the variance."
        mean_val = np.mean(data)
        explanation = f"1. Mean (`μ`) = `{mean_val:.2f}`.\n\n2. Variance (`σ²`) = Average of squared differences from the mean ≈ `{np.var(data):.2f}`.\n\n3. Standard Deviation (`σ`) = `√Variance` ≈ `{answer}`."
        options = {answer, f"{np.var(data):.2f}", f"{max(data)-min(data):.2f}"}

    return {"question": question, "options": _finalize_options(options), "answer": answer, "hint": hint, "explanation": explanation, "difficulty": difficulty}


def _generate_coordinate_geometry_question(difficulty="Medium"):
    """Generates a Coordinate Geometry question based on difficulty, preserving all original sub-types."""

    if difficulty == "Easy":
        # Foundational formulas for midpoint and gradient.
        q_type = random.choice(['midpoint', 'gradient'])
    elif difficulty == "Medium":
        # More complex formulas and initial equation-finding.
        q_type = random.choice(['distance', 'equation_point_slope'])
    else: # Hard
        # Multi-step problems combining formulas or analyzing relationships.
        q_type = random.choice(['equation_two_points', 'parallel_perpendicular'])

    question, answer, hint, explanation = "", "", "", ""
    options = set()
    x1, y1, x2, y2 = [random.randint(-10, 10) for _ in range(4)]
    while x1 == x2 and y1 == y2: # Ensure points are distinct
        x2, y2 = random.randint(-10, 10), random.randint(-10, 10)

    # --- Easy Questions ---
    if q_type == 'midpoint':
        mid_x = (x1 + x2) / 2
        mid_y = (y1 + y2) / 2
        question = f"Find the midpoint of the line segment connecting A$({x1}, {y1})$ and B$({x2}, {y2})$."
        answer = f"({mid_x:.1f}, {mid_y:.1f})".replace(".0", "")
        hint = "The midpoint is the average of the x-coordinates and the average of the y-coordinates."
        explanation = f"Midpoint = $(\\frac{{x_1+x_2}}{{2}}, \\frac{{y_1+y_2}}{{2}}) = (\\frac{{{x1}+{x2}}}{{2}}, \\frac{{{y1}+{y2}}}{{2}}) = ({answer})$."
        options = {answer, f"({(x2-x1)/2}, {(y2-y1)/2})", f"({x1+x2}, {y1+y2})"}

    elif q_type == 'gradient':
        question = f"Find the gradient (slope) of the line passing through A$({x1}, {y1})$ and B$({x2}, {y2})$."
        if x1 == x2: # Vertical line
            answer = "Undefined"
            hint = "The gradient of a vertical line is undefined."
            explanation = "Since the x-coordinates are the same ($x_1 = x_2$), this is a vertical line. The gradient of a vertical line is undefined because the change in x is zero, leading to division by zero in the formula."
            options = {answer, "0", "1"}
        else:
            grad = Fraction(y2 - y1, x2 - x1)
            answer = _format_fraction_text(grad)
            hint = "Use the gradient formula: $m = \\frac{{y_2-y_1}}{{x_2-x_1}}$."
            explanation = f"Gradient $m = \\frac{{y_2-y_1}}{{x_2-x_1}} = \\frac{{{y2}-({y1})}}{{{x2}-({x1})}} = \\frac{{{y2-y1}}}{{{x2-x1}}} = {_get_fraction_latex_code(grad)}$."
            options = {answer, _format_fraction_text(Fraction(x2-x1, y2-y1)), str(y2-y1)}

    # --- Medium Questions ---
    elif q_type == 'distance':
        dist_sq = (x2 - x1)**2 + (y2 - y1)**2
        dist = math.sqrt(dist_sq)
        question = f"Find the distance between point A$({x1}, {y1})$ and point B$({x2}, {y2})$."
        if dist == int(dist): answer = str(int(dist))
        else: answer = f"$\\sqrt{{{dist_sq}}}$" # Leave as a simplified surd
        hint = "Use the distance formula: $d = \\sqrt{{(x_2 - x_1)^2 + (y_2 - y_1)^2}}$."
        explanation = f"Using the distance formula:\n$d = \\sqrt{{({x2} - ({x1}))^2 + ({y2} - ({y1}))^2}} = \\sqrt{{({x2-x1})^2 + ({y2-y1})^2}} = \\sqrt{{{dist_sq}}}$."
        if dist != int(dist): explanation += f" This is the exact distance in simplified surd form."
        else: explanation += f" = {int(dist)}"
        options = {answer, str(round(dist, 2)), str(dist_sq)}

    elif q_type == 'equation_point_slope':
        m_num, m_den = random.randint(-5, 5), random.randint(1, 3)
        while m_num == 0: m_num = random.randint(-5, 5)
        m = Fraction(m_num, m_den)
        c = y1 - m*x1
        question = f"Find the equation of the line that passes through the point $({x1}, {y1})$ and has a gradient of ${_get_fraction_latex_code(m)}$."
        answer = f"$y = {_get_fraction_latex_code(m)}x {'+' if c >= 0 else '-'} {_get_fraction_latex_code(abs(c))}$"
        hint = "Use the formula $y - y_1 = m(x - x_1)$ and rearrange it into the form $y = mx + c$."
        explanation = f"1. Start with $y - y_1 = m(x - x_1)$.\n\n2. Substitute values: $y - ({y1}) = {_get_fraction_latex_code(m)}(x - ({x1}))$.\n\n3. Simplify to find the y-intercept 'c': $c = y_1 - m \\times x_1 = {_get_fraction_latex_code(y1)} - {_get_fraction_latex_code(m)} \\times {_get_fraction_latex_code(Fraction(x1))} = {_get_fraction_latex_code(c)}$.\n\n4. The final equation is: {answer}."
        options = {answer, f"$y = {-1/m}x + {c}$", f"$y - {y1} = {_get_fraction_latex_code(m)}(x + {x1})$"}

    # --- Hard Questions ---
    elif q_type == 'equation_two_points':
        question = f"Find the equation of the line that passes through the points A$({x1}, {y1})$ and B$({x2}, {y2})$."
        if x1 == x2: # Vertical line
            answer = f"$x = {x1}$"
            hint = "First, find the gradient. If the x-coordinates are the same, it's a special case."
            explanation = "Since the x-coordinates are the same, this is a vertical line. All points on this line have an x-coordinate of {x1}, so the equation is $x = {x1}$."
            options = {answer, f"y = {y1}", f"y = x + {y1-x1}"}
        else:
            m = Fraction(y2 - y1, x2 - x1)
            c = y1 - m*x1
            answer = f"$y = {_get_fraction_latex_code(m)}x {'+' if c >= 0 else '-'} {_get_fraction_latex_code(abs(c))}$"
            hint = "First, calculate the gradient between the two points, then use the point-slope formula $y - y_1 = m(x - x_1)$ with one of the points."
            explanation = f"1. First, find the gradient: $m = \\frac{{{y2-y1}}}{{{x2-x1}}} = {_get_fraction_latex_code(m)}$.\n\n2. Use $y - y_1 = m(x - x_1)$: $y - ({y1}) = {_get_fraction_latex_code(m)}(x - ({x1}))$.\n\n3. Simplify to $y=mx+c$ form: {answer}."
            options = {answer, f"$y = {_get_fraction_latex_code(-1/m)}x {'+' if c >= 0 else '-'} {_get_fraction_latex_code(abs(c))}$"}

    elif q_type == 'parallel_perpendicular':
        m1 = Fraction(random.randint(-3, 3), random.randint(1, 2))
        while m1 == 0: m1 = Fraction(random.randint(-3, 3), random.randint(1, 2))
        c1 = random.randint(-5, 5)
        line1_eq = f"$y = {_get_fraction_latex_code(m1)}x {'+' if c1 >= 0 else '-'} {_get_fraction_latex_code(abs(c1))}$"
        relationship, m2 = random.choice([("Parallel", m1), ("Perpendicular", -1/m1), ("Neither", m1+1)])
        line2_eq = f"$y = {_get_fraction_latex_code(m2)}x + {c1+2}$"
        question = f"What is the relationship between the lines {line1_eq} and {line2_eq}?"
        answer = relationship
        hint = "Compare the gradients (m values) of the two lines. Parallel lines have equal gradients. For perpendicular lines, the product of their gradients is -1 (or one is the negative reciprocal of the other)."
        explanation = f"The gradient of the first line is $m_1 = {_get_fraction_latex_code(m1)}$. The gradient of the second line is $m_2 = {_get_fraction_latex_code(m2)}$. Since $m_1$ and $m_2$ meet the condition for being **{answer}**, that is the correct relationship."
        options = {"Parallel", "Perpendicular", "Neither"}

    return {"question": question, "options": _finalize_options(options), "answer": answer, "hint": hint, "explanation": explanation, "difficulty": difficulty}


def _generate_calculus_question(difficulty="Medium"):
    """Generates an Introduction to Calculus question based on difficulty, preserving all original sub-types."""
    
    if difficulty == "Easy":
        # Foundational concepts of limits and the power rule for differentiation.
        q_type = random.choice(['limits_substitution', 'diff_power_rule'])
    elif difficulty == "Medium":
        # Applying differentiation and introducing basic integration.
        q_type = random.choice(['gradient_of_curve', 'indefinite_integration'])
    else: # Hard
        # Multi-step integration problems.
        q_type = random.choice(['find_constant_c', 'definite_integration'])

    question, answer, hint, explanation = "", "", "", ""
    options = set()

    # --- Easy Questions ---
    if q_type == 'limits_substitution':
        coeffs = [random.randint(1, 5), random.randint(-5, 5), random.randint(-5, 5)]
        poly_str = _poly_to_str(coeffs)
        x_val = random.randint(-3, 3)
        limit_val = coeffs[0]*x_val**2 + coeffs[1]*x_val + coeffs[2]
        question = f"Evaluate the limit: $\\lim_{{x \\to {x_val}}} ({poly_str})$"
        answer = str(limit_val)
        hint = "Since this is a polynomial function, you can find the limit by direct substitution of the value x is approaching."
        explanation = f"Substitute $x = {x_val}$ directly into the expression:\n\n$({coeffs[0]})({x_val})^2 + ({coeffs[1]})({x_val}) + ({coeffs[2]}) = {limit_val}$."
        options = {answer, str(limit_val+1), str(limit_val-1)}

    elif q_type == 'diff_power_rule':
        coeffs = [random.randint(2, 6), random.randint(-5, 5), random.randint(2, 10)]
        poly_str = _poly_to_str(coeffs)
        deriv_coeffs = [coeffs[0]*2, coeffs[1]]
        deriv_str = _poly_to_str(deriv_coeffs)
        question = f"Find the derivative of $f(x) = {poly_str}$ with respect to x."
        answer = f"${deriv_str}$"
        hint = "Apply the power rule, $\\frac{{d}}{{dx}}(ax^n) = anx^{{n-1}}$, to each term of the polynomial. The derivative of a constant is zero."
        explanation = f"Differentiating term by term:\n\n$\\frac{{d}}{{dx}}({coeffs[0]}x^2) = {coeffs[0]*2}x$\n\n$\\frac{{d}}{{dx}}({coeffs[1]}x) = {coeffs[1]}$\n\n$\\frac{{d}}{{dx}}({coeffs[2]}) = 0$\n\nAdding these together, the derivative is ${answer}$."
        options = {answer, f"${poly_to_str(coeffs)}$", f"${poly_to_str([coeffs[0]*2, coeffs[1], coeffs[2]])}$"}

    # --- Medium Questions ---
    elif q_type == 'gradient_of_curve':
        coeffs = [random.randint(2, 5), random.randint(-5, 5)]
        poly_str = _poly_to_str(coeffs) + f" + {random.randint(1,10)}"
        x_val = random.randint(1, 4)
        gradient_val = coeffs[0]*2*x_val + coeffs[1]
        question = f"Find the gradient of the curve $y = {poly_str}$ at the point where $x={x_val}$."
        answer = str(gradient_val)
        hint = "First, find the derivative of the function (which represents the gradient at any point), then substitute the given x-value into the derivative."
        explanation = f"1. Find the derivative: $\\frac{{dy}}{{dx}} = {_poly_to_str([coeffs[0]*2, coeffs[1]])}$.\n\n2. Substitute $x={x_val}$ into the derivative: ${coeffs[0]*2}({x_val}) + ({coeffs[1]}) = {gradient_val}$."
        options = {answer, str(gradient_val + x_val), str(coeffs[0]*x_val**2 + coeffs[1]*x_val)}

    elif q_type == 'indefinite_integration':
        deriv_coeffs = [random.randint(1, 4) * 2, random.randint(2, 10)]
        deriv_str = _poly_to_str(deriv_coeffs)
        orig_coeffs = [deriv_coeffs[0]//2, deriv_coeffs[1]]
        orig_str = _poly_to_str(orig_coeffs)
        question = f"Find the indefinite integral: $\\int ({deriv_str}) \\,dx$."
        answer = f"${orig_str} + C$"
        hint = "Apply the reverse power rule, $\\int ax^n \\,dx = \\frac{{a}}{{n+1}}x^{{n+1}} + C$, to each term. Don't forget the constant of integration, C."
        explanation = f"Integrating term by term:\n\n$\\int {deriv_coeffs[0]}x \\,dx = \\frac{{{deriv_coeffs[0]}}}{{2}}x^2 = {orig_coeffs[0]}x^2$\n\n$\\int {deriv_coeffs[1]} \\,dx = {orig_coeffs[1]}x$\n\nAdding these and the constant of integration gives ${answer}$."
        options = {answer, f"${deriv_str} + C$", f"${_poly_to_str([orig_coeffs[0]*2, orig_coeffs[1]])} + C$"}

    # --- Hard Questions ---
    elif q_type == 'find_constant_c':
        deriv_coeffs = [random.randint(1, 4) * 2, random.randint(-5, 5)]
        deriv_str = _poly_to_str(deriv_coeffs)
        px, py = random.randint(1, 3), random.randint(5, 20)
        integral_val_at_px = (deriv_coeffs[0]//2)*px**2 + deriv_coeffs[1]*px
        const_c = py - integral_val_at_px
        orig_str = f"{_poly_to_str([deriv_coeffs[0]//2, deriv_coeffs[1]])} {'+' if const_c >= 0 else '-'} {abs(const_c)}"
        question = f"Given that $\\frac{{dy}}{{dx}} = {deriv_str}$ and the curve passes through the point $({px}, {py})$, find the specific equation of the curve."
        answer = f"$y = {orig_str}$"
        hint = "First, integrate the derivative to get the general form $y = ... + C$. Then, substitute the x and y coordinates of the given point to solve for C."
        explanation = f"1. Integrate: $y = \\int ({deriv_str}) \\,dx = {_poly_to_str([deriv_coeffs[0]//2, deriv_coeffs[1]])} + C$.\n\n2. Substitute the point $({px}, {py})$: ${py} = {deriv_coeffs[0]//2}({px})^2 + {deriv_coeffs[1]}({px}) + C$.\n\n3. Solve for C: ${py} = {integral_val_at_px} + C \\implies C = {py} - {integral_val_at_px} = {const_c}$.\n\n4. The final equation is {answer}."
        options = {answer, f"$y = {_poly_to_str([deriv_coeffs[0]//2, deriv_coeffs[1]])}$", f"$y = {deriv_str} + {const_c}$"}

    elif q_type == 'definite_integration':
        coeffs = [random.randint(1, 4) * 2, random.randint(2, 8)]
        poly_str = _poly_to_str(coeffs)
        a, b = random.randint(1, 3), random.randint(4, 5)
        integral_coeffs = [coeffs[0]//2, coeffs[1]]
        F_b = integral_coeffs[0]*b**2 + integral_coeffs[1]*b
        F_a = integral_coeffs[0]*a**2 + integral_coeffs[1]*a
        result = F_b - F_a
        question = f"Evaluate the definite integral: $\\int_{{{a}}}^{{{b}}} ({poly_str}) \\,dx$."
        answer = str(result)
        hint = "First find the indefinite integral, F(x). Then calculate F(b) - F(a), where 'b' is the upper limit and 'a' is the lower limit."
        explanation = f"1. The integral is $F(x) = {_poly_to_str(integral_coeffs)}$.\n\n2. Evaluate at the upper limit: $F({b}) = {integral_coeffs[0]}({b})^2 + {integral_coeffs[1]}({b}) = {F_b}$.\n\n3. Evaluate at the lower limit: $F({a}) = {integral_coeffs[0]}({a})^2 + {integral_coeffs[1]}({a}) = {F_a}$.\n\n4. The result is $F({b}) - F({a}) = {F_b} - {F_a} = {result}$."
        options = {answer, str(F_b+F_a), str(F_b)}

    return {"question": question, "options": _finalize_options(options), "answer": answer, "hint": hint, "explanation": explanation, "difficulty": difficulty}


def _generate_number_bases_question(difficulty="Medium"):
    """Generates a Number Bases question based on difficulty, preserving all original sub-types."""

    if difficulty == "Easy":
        # Foundational conversion skills.
        q_type = random.choice(['to_base_10', 'from_base_10'])
    elif difficulty == "Medium":
        # Basic arithmetic in other bases.
        q_type = random.choice(['addition', 'subtraction'])
    else: # Hard
        # More complex arithmetic.
        q_type = 'multiplication'

    question, answer, hint, explanation = "", "", "", ""
    options = set()
    base = random.choice([2, 3, 4, 5, 8])

    # --- Easy Questions ---
    if q_type == 'to_base_10':
        num_base10 = random.randint(10, 100)
        num_other_base = np.base_repr(num_base10, base)
        question = f"Convert the number ${num_other_base}_{{{base}}}$ to base 10."
        answer = str(num_base10)
        hint = f"Multiply each digit by the base raised to the power of its position (starting from 0 on the right)."
        exp_parts = [f"({digit} \\times {base}^{i})" for i, digit in enumerate(reversed(num_other_base))]
        explanation = f"To convert ${num_other_base}_{{{base}}}$ to base 10, expand it:\n\n`{' + '.join(exp_parts)} = {num_base10}`."
        options = {answer, str(int(num_other_base, base=16)) if base < 16 else str(num_base10+base), str(sum(int(d) for d in num_other_base)*base)}

    elif q_type == 'from_base_10':
        num_base10 = random.randint(20, 150)
        num_other_base = np.base_repr(num_base10, base)
        question = f"Convert the number ${num_base10}_{{10}}$ to base {base}."
        answer = str(num_other_base)
        hint = "Use repeated division by the target base. The remainders, read from bottom to top, form the new number."
        # Build a simple explanation of repeated division
        exp = f"We repeatedly divide {num_base10} by {base} and record the remainders:\n"
        n = num_base10
        rems = []
        while n > 0:
            rem = n % base
            rems.append(str(rem))
            exp += f"\n- ${n} \\div {base} = {n//base}$ remainder **{rem}**"
            n //= base
        exp += f"\n\nReading the remainders from bottom to top gives **{''.join(reversed(rems))}**."
        explanation = exp
        options = {answer, str(num_base10*base), str(num_base10//base)}

    # --- Medium Questions ---
    elif q_type == 'addition':
        n1 = random.randint(10, 50)
        n2 = random.randint(10, 50)
        n1_base = np.base_repr(n1, base)
        n2_base = np.base_repr(n2, base)
        result_10 = n1 + n2
        answer = np.base_repr(result_10, base)
        question = f"Calculate the sum in base {base}: ${n1_base}_{{{base}}} + {n2_base}_{{{base}}}$"
        hint = "The simplest method is to convert both numbers to base 10, add them normally, then convert the result back to the target base."
        explanation = f"1. Convert to base 10: ${n1_base}_{{{base}}} = {n1}_{{10}}$ and ${n2_base}_{{{base}}} = {n2}_{{10}}$.\n\n2. Add in base 10: ${n1} + {n2} = {result_10}$.\n\n3. Convert the result back to base {base}: ${result_10}_{{10}} = {answer}_{{{base}}}$."
        options = {answer, np.base_repr(result_10 + base, base), np.base_repr(n1,base)+np.base_repr(n2,base)}

    elif q_type == 'subtraction':
        n1 = random.randint(20, 60)
        n2 = random.randint(10, 50)
        if n1 < n2: n1, n2 = n2, n1 # Ensure result is positive
        n1_base, n2_base = np.base_repr(n1, base), np.base_repr(n2, base)
        result_10 = n1 - n2
        answer = np.base_repr(result_10, base)
        question = f"Calculate the difference in base {base}: ${n1_base}_{{{base}}} - {n2_base}_{{{base}}}$"
        hint = "Convert both numbers to base 10, subtract them, then convert the result back to the target base."
        explanation = f"1. Convert to base 10: ${n1_base}_{{{base}}} = {n1}_{{10}}$ and ${n2_base}_{{{base}}} = {n2}_{{10}}$.\n\n2. Subtract in base 10: ${n1} - {n2} = {result_10}$.\n\n3. Convert the result back to base {base}: ${result_10}_{{10}} = {answer}_{{{base}}}$."
        options = {answer, np.base_repr(result_10 + base, base)}

    # --- Hard Question ---
    elif q_type == 'multiplication':
        n1, n2 = random.randint(5, 12), random.randint(5, 12)
        n1_base, n2_base = np.base_repr(n1, base), np.base_repr(n2, base)
        result_10 = n1 * n2
        answer = np.base_repr(result_10, base)
        question = f"Calculate the product in base {base}: ${n1_base}_{{{base}}} \\times {n2_base}_{{{base}}}$"
        hint = "Convert both numbers to base 10, multiply them, then convert the final result back to the target base."
        explanation = f"1. Convert to base 10: ${n1_base}_{{{base}}} = {n1}_{{10}}$ and ${n2_base}_{{{base}}} = {n2}_{{10}}$.\n\n2. Multiply in base 10: ${n1} \\times {n2} = {result_10}$.\n\n3. Convert the result back to base {base}: ${result_10}_{{10}} = {answer}_{{{base}}}$."
        options = {answer, np.base_repr(n1+n2, base)}
        
    return {"question": question, "options": _finalize_options(options), "answer": answer, "hint": hint, "explanation": explanation, "difficulty": difficulty}


def _generate_modulo_arithmetic_question(difficulty="Medium"):
    """Generates a Modulo Arithmetic question based on difficulty, preserving all original sub-types."""

    if difficulty == "Easy":
        # Direct calculation and simple application.
        q_type = random.choice(['find_remainder', 'clock_arithmetic'])
    elif difficulty == "Medium":
        # Understanding the concept of congruence and another application.
        q_type = random.choice(['congruence', 'day_of_week'])
    else: # Hard
        # Solving a linear congruence, which requires algebraic thinking.
        q_type = 'solve_linear'

    question, answer, hint, explanation = "", "", "", ""
    options = set()

    # --- Easy Questions ---
    if q_type == 'find_remainder':
        n = random.randint(3, 12)
        a = random.randint(n + 1, n * 10)
        rem = a % n
        question = f"Find the remainder when ${a}$ is divided by ${n}$. (i.e., find ${a} \\pmod {n}$)"
        answer = str(rem)
        hint = "This is asking for the value of the 'modulo' operation, which is the remainder after division."
        explanation = f"To find the remainder, we see how many times ${n}$ fits into ${a}$ completely, and what is left over.\n\n${a} = {n} \\times {a//n} + {rem}$.\n\nThe remainder is **{rem}**."
        options = {answer, str(a//n), str(n-rem)}

    elif q_type == 'clock_arithmetic':
        current_time = random.randint(1, 12)
        hours_passed = random.randint(15, 100)
        final_time = (current_time + hours_passed - 1) % 12 + 1
        question = f"A student in Accra looks at a 12-hour clock. It is currently {current_time} o'clock. What time will it be in {hours_passed} hours?"
        answer = f"{final_time} o'clock"
        hint = "This problem can be solved using modulo 12. The cycle of a clock repeats every 12 hours."
        explanation = f"We can calculate this using modulo arithmetic:\n\n$({current_time} + {hours_passed}) \\pmod{{12}}$.\n\nA remainder of 0 corresponds to 12 o'clock. The calculation is `({current_time} + {hours_passed} - 1) % 12 + 1`, which results in **{final_time} o'clock**."
        options = {answer, f"{(current_time+hours_passed)%12} o'clock", f"{abs(current_time-hours_passed)%12} o'clock"}

    # --- Medium Questions ---
    elif q_type == 'congruence':
        n = random.randint(3, 9)
        is_true = random.choice([True, False])
        if is_true:
            rem = random.randint(0, n - 1)
            a = n * random.randint(2, 5) + rem
            b = n * random.randint(1, 4) + rem
            while a == b: b = n * random.randint(1, 4) + rem
            answer = "True"
        else:
            rem1, rem2 = random.sample(range(n), 2)
            a = n * random.randint(2, 5) + rem1
            b = n * random.randint(1, 4) + rem2
            answer = "False"
        question = f"Is the following congruence relation true or false? ${a} \\equiv {b} \\pmod {n}$"
        hint = f"The relation $a \\equiv b \\pmod n$ is true if and only if $a$ and $b$ have the same remainder when divided by $n$. Alternatively, if $(a - b)$ is a multiple of $n$."
        explanation = f"We check if $(a - b)$ is divisible by ${n}$.\n\n${a} - {b} = {a-b}$.\n\nIs {a-b} divisible by {n}? The answer is **{answer.lower()}**."
        options = {"True", "False"}
    
    elif q_type == 'day_of_week':
        days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        start_day_index = random.randint(0, 6)
        days_passed = random.randint(20, 200)
        final_day_index = (start_day_index + days_passed) % 7
        question = f"Today is {days[start_day_index]}. What day of the week will it be in {days_passed} days?"
        answer = days[final_day_index]
        hint = "Use modulo 7 to solve this problem. The cycle of a week repeats every 7 days."
        explanation = f"We can model the days of the week with numbers 0 through 6 (e.g., {days[start_day_index]} = {start_day_index}).\n\nWe calculate $({start_day_index} + {days_passed}) \\pmod 7$.\n\n$({start_day_index + days_passed}) \\pmod 7 = {final_day_index}$.\n\nThe number {final_day_index} corresponds to **{answer}**."
        options = set(days)

    # --- Hard Question ---
    elif q_type == 'solve_linear':
        n = random.choice([3, 5, 7, 11]) # Prime modulus for simplicity
        a = random.randint(2, n - 1)
        x = random.randint(1, n - 1)
        b = (a * x) % n
        question = f"Find the value of $x$ in the congruence: ${a}x \\equiv {b} \\pmod {n}$, where $x$ is an integer from 1 to {n-1}."
        answer = str(x)
        hint = f"You can test the integer values from 1 to {n-1} for $x$ to see which one satisfies the equation."
        explanation = f"We are looking for an integer $x$ such that ${a}x$ has the same remainder as ${b}$ when divided by ${n}$. By testing values, we find:\n\n- For $x={x}$, ${a}({x}) = {a*x}$.\n- ${a*x} \\div {n}$ is {a*x//n} with a remainder of {b}.\n\nSo, **$x={answer}$** is the solution."
        options = {answer, str((b-a)%n), str((b+a)%n)}

    return {"question": question, "options": _finalize_options(options), "answer": answer, "hint": hint, "explanation": explanation, "difficulty": difficulty}

def get_adaptive_question(topic, username):
    """
    The new "brain" of the quiz. It gets a question based on the user's skill level.
    """
    # --- THIS IS THE FIX: Handle 'Advanced Combo' as a special case first ---
    if topic == "Advanced Combo":
        # Advanced Combo questions don't have difficulty levels, so we call its generator directly.
        return _generate_advanced_combo_question()
    skill_score = get_skill_score(username, topic)

    if skill_score < 40:
        difficulty = "Easy"
    elif skill_score < 75:
        difficulty = "Medium"
    else:
        difficulty = "Hard"

    # This dictionary maps topic strings to their specific generator functions.
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
        "Rational Functions": _generate_rational_functions_question,
        "Trigonometry": _generate_trigonometry_question,
        "Vectors": _generate_vectors_question,
        "Statistics": _generate_statistics_question,
        "Coordinate Geometry": _generate_coordinate_geometry_question,
        "Introduction to Calculus": _generate_calculus_question,
        "Number Bases": _generate_number_bases_question,
        "Modulo Arithmetic": _generate_modulo_arithmetic_question,
    }
    
    generator_func = generators.get(topic)
    if not generator_func:
        return {"question": f"Questions for **{topic}** are coming soon!", "options": ["OK"], "answer": "OK", "hint": "Under development."}

    # --- Logic to prevent repeating questions ---
    seen_ids = get_seen_questions(username)
    
    # Try up to 10 times to find a new, unseen question
    for _ in range(10):
        # Pass the selected difficulty to the generator
        candidate_question = generator_func(difficulty=difficulty)
        
        question_text = candidate_question.get("stem", candidate_question.get("question", ""))
        q_id = get_question_id(question_text)
        
        if q_id not in seen_ids:
            save_seen_question(username, q_id)
            return candidate_question
    
    # Fallback if no new question is found after 10 tries
    return generator_func(difficulty=difficulty)

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

def _combo_stats_probability():
    """ Combo: Statistics (Mean) -> Probability """
    k = 5
    data = sorted(random.sample(range(10, 50), k=k))
    mean_val = sum(data) / len(data)
    
    # Count how many numbers are greater than the mean
    count_greater = sum(1 for x in data if x > mean_val)
    prob_frac = Fraction(count_greater, len(data))

    stem = f"A student in Kumasi has the following scores in a test: `{data}`."
    
    return {
        "is_multipart": True,
        "stem": stem,
        "parts": [
            {
                "question": "a) What is the mean of the scores?",
                "options": _finalize_options({f"{mean_val:.2f}", str(np.median(data))}),
                "answer": f"{mean_val:.2f}",
                "hint": "The mean is the sum of the values divided by the count of the values.",
                "explanation": f"Sum = `{sum(data)}`. Count = `{len(data)}`. Mean = `{sum(data)} / {len(data)} = {mean_val:.2f}`."
            },
            {
                "question": "b) If a score is picked at random, what is the probability that it is greater than the mean calculated in part (a)?",
                "options": _finalize_options({_format_fraction_text(prob_frac)}, "fraction"),
                "answer": _format_fraction_text(prob_frac),
                "hint": "Count how many scores in the original list are greater than the mean, then divide by the total number of scores.",
                "explanation": f"The scores greater than {mean_val:.2f} are `{[x for x in data if x > mean_val]}`. There are {count_greater} such scores out of a total of {len(data)}. Probability = {_get_fraction_latex_code(prob_frac)}."
            }
        ]
    }

def _combo_calculus_coord_geometry():
    """ Combo: Calculus (Differentiation) -> Coordinate Geometry (Equation of a line) """
    a, c = random.randint(2, 5), random.randint(1, 10)
    x_val = random.randint(1, 4)
    
    poly_str = f"{a}x^2 + {c}"
    deriv_str = f"{2*a}x"
    
    # Calculate point on curve
    y_val = a * x_val**2 + c
    gradient = 2 * a * x_val
    
    # Equation of the tangent line y - y1 = m(x - x1) => y = mx - mx1 + y1
    c_tangent = y_val - gradient * x_val
    
    stem = f"Consider the curve defined by the equation $y = {poly_str}$."

    return {
        "is_multipart": True,
        "stem": stem,
        "parts": [
            {
                "question": f"a) Find the gradient of the curve at the point where $x = {x_val}$.",
                "options": _finalize_options({str(gradient), str(y_val)}),
                "answer": str(gradient),
                "hint": "Find the derivative of the function, then substitute the x-value into the derivative.",
                "explanation": f"1. The derivative is $\\frac{{dy}}{{dx}} = {deriv_str}$.\n\n2. At $x={x_val}$, the gradient is ${2*a}({x_val}) = {gradient}$."
            },
            {
                "question": "b) Using your answer from part (a), find the equation of the tangent line to the curve at this point.",
                "options": _finalize_options({f"$y = {gradient}x {'+' if c_tangent >= 0 else '-'} {abs(c_tangent)}$"}),
                "answer": f"$y = {gradient}x {'+' if c_tangent >= 0 else '-'} {abs(c_tangent)}$",
                "hint": "First, find the y-coordinate of the point. Then use the formula $y - y_1 = m(x - x_1)$.",
                "explanation": f"1. The gradient $m = {gradient}$.\n\n2. The point is $({x_val}, {y_val})$.\n\n3. The equation is $y - {y_val} = {gradient}(x - {x_val})$, which simplifies to $y = {gradient}x - {gradient*x_val} + {y_val}$, or $y = {gradient}x {'+' if c_tangent >= 0 else '-'} {abs(c_tangent)}$."
            }
        ]
    }

def _combo_number_bases_modulo():
    """ Combo: Number Bases (Conversion) -> Modulo Arithmetic """
    base = random.choice([2, 3, 4, 5])
    num_base10 = random.randint(20, 100)
    num_other_base = np.base_repr(num_base10, base=base)
    mod_n = random.randint(3, 9)
    result_mod = num_base10 % mod_n

    stem = f"Consider the number ${num_other_base}_{{{base}}}$."
    
    return {
        "is_multipart": True,
        "stem": stem,
        "parts": [
            {
                "question": f"a) Convert the number from base {base} to base 10.",
                "options": _finalize_options({str(num_base10)}),
                "answer": str(num_base10),
                "hint": "Multiply each digit by the base raised to the power of its position, starting from 0 on the right.",
                "explanation": f"Converting ${num_other_base}_{{{base}}}$ to base 10 results in the number **{num_base10}**."
            },
            {
                "question": f"b) Using your base 10 answer from part (a), calculate its value modulo {mod_n}.",
                "options": _finalize_options({str(result_mod)}),
                "answer": str(result_mod),
                "hint": f"Find the remainder when {num_base10} is divided by {mod_n}.",
                "explanation": f"We need to calculate ${num_base10} \\pmod{{{mod_n}}}$.\n\n${num_base10} \\div {mod_n} = {num_base10 // mod_n}$ with a remainder of **{result_mod}**."
            }
        ]
    }

def _combo_coord_geometry_algebra():
    """ Combo: Coordinate Geometry (Distance) -> Algebra (Area) """
    x1, y1, x2, y2 = 1, 2, 4, 6 # Use a pythagorean triple base (3,4,5) for a clean integer distance
    dist = 5
    area = dist**2

    stem = f"Two points on a grid are A$({x1}, {y1})$ and B$({x2}, {y2})$."
    
    return {
        "is_multipart": True,
        "stem": stem,
        "parts": [
            {
                "question": "a) Find the distance between points A and B.",
                "options": _finalize_options({str(dist)}),
                "answer": str(dist),
                "hint": "Use the distance formula: $d = \\sqrt{{(x_2 - x_1)^2 + (y_2 - y_1)^2}}$." ,
                "explanation": f"$d = \\sqrt{{({x2} - {x1})^2 + ({y2} - {y1})^2}} = \\sqrt{{3^2 + 4^2}} = \\sqrt{{25}} = 5$."
            },
            {
                "question": "b) If the distance calculated in part (a) represents the side length of a square, what is the area of the square?",
                "options": _finalize_options({str(area)}),
                "answer": str(area),
                "hint": "The area of a square is the side length squared.",
                "explanation": f"The side length is {dist}. Area = $side^2 = {dist}^2 = {area}$."
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
        _combo_stats_probability,
        _combo_calculus_coord_geometry,
        _combo_number_bases_modulo,
        _combo_coord_geometry_algebra,
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
        "Rational Functions": _generate_rational_functions_question,
        "Trigonometry": _generate_trigonometry_question,
        "Vectors": _generate_vectors_question,
        "Advanced Combo": _generate_advanced_combo_question,
        # --- ADD THE NEW TOPICS HERE ---
        "Statistics": _generate_statistics_question,
        "Coordinate Geometry": _generate_coordinate_geometry_question,
        "Introduction to Calculus": _generate_calculus_question,
        "Number Bases": _generate_number_bases_question,
        "Modulo Arithmetic": _generate_modulo_arithmetic_question,
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
        
        /* --- BORDER STYLES (WITH NEW RAINBOW ANIMATION) --- */
        .bronze-border {
            border: 3px solid #cd7f32 !important;
            box-shadow: 0 0 10px #cd7f32;
        }
        .silver-border {
            border: 3px solid #c0c0c0 !important;
            box-shadow: 0 0 10px #c0c0c0;
        }
        .gold-border {
            border: 3px solid #FFD700 !important;
            box-shadow: 0 0 10px #FFD700;
        }
        
        /* --- THIS IS THE NEW, WORKING RAINBOW BORDER --- */
        .rainbow-border {
            border: 3px solid transparent !important;
            /* The animation property tells the border to use our 'rainbow-glow' animation */
            animation: rainbow-glow 2s linear infinite;
        }

        /* --- This animation rule defines the color changes --- */
        @keyframes rainbow-glow {
            0% { border-color: #b827fc; box-shadow: 0 0 10px #b827fc; }
            25% { border-color: #2c90fc; box-shadow: 0 0 10px #2c90fc; }
            50% { border-color: #b8fd33; box-shadow: 0 0 10px #b8fd33; }
            75% { border-color: #fec837; box-shadow: 0 0 10px #fec837; }
            100% { border-color: #fd1892; box-shadow: 0 0 10px #fd1892; }
        }
        /* --- END OF BORDER STYLES --- */

        /* --- NEW CHAT STYLES --- */
        .chat-container {
            display: flex;
            flex-direction: column-reverse; /* This makes the chat feel "anchored" to the bottom */
            width: 100%;
        }
        .chat-row {
            display: flex;
            align-items: flex-end;
            margin-top: 0.75rem;
        }
        .chat-row.user {
            justify-content: flex-end;
        }
        .chat-avatar {
            width: 40px;
            height: 40px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: bold;
            color: white;
            margin-right: 10px;
            margin-left: 10px;
            flex-shrink: 0;
        }
        .chat-bubble {
            padding: 10px 15px;
            border-radius: 18px;
            max-width: 70%;
            box-shadow: 0 1px 2px rgba(0,0,0,0.1);
        }
        .chat-bubble.user {
            background-color: #007AFF;
            color: white !important;
            border-bottom-right-radius: 4px;
        }
        .chat-bubble.assistant {
            background-color: #E5E5EA;
            color: #31333F !important;
            border-bottom-left-radius: 4px;
        }
        .chat-bubble * {
            color: inherit !important;
        }
        .chat-meta {
            font-size: 0.75rem;
            color: #6c757d !important;
            padding: 0 5px;
        }
        /* --- Add this with your other Chat Styles --- */
        .chat-date-divider {
            text-align: center;
            margin: 1rem 0;
        }
        .chat-date-chip {
            display: inline-block;
            background-color: #f0f2f5;
            color: #65676b !important;
            border-radius: 12px;
            padding: 4px 12px;
            font-size: 0.75rem;
            font-weight: 500;
        }
        /* --- END OF NEW CHAT STYLES --- */

        /* --- ADD THIS NEW CSS RULE --- */
        .quiz-prep-image {
            height: 190px;
            width: 100%;
            object-fit: cover;
            border-radius: 8px;
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
        .login-title { text-align: center; font-weight: 800; font-size: 2.2rem; }
        .login-subtitle { text-align: center; color: #6c757d; margin-bottom: 2rem; }
        .main-content { background-color: #ffffff; padding: 2rem; border-radius: 12px; box-shadow: 0 4px 12px rgba(0,0,0,0.08); }
        @media (max-width: 640px) { .main-content, .login-container { padding: 1rem; } .login-title { font-size: 1.8rem; } }
    </style>
    """, unsafe_allow_html=True)
def display_dashboard(username):
    
    announcement = get_config_value("announcement_text")
    if announcement:
        st.info(f"📣 **Announcement:** {announcement}")
        st.markdown("---")
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
        
        # --- START: THIS IS THE FIX ---
        # Create a new, filtered DataFrame for display that excludes 'WASSCE Prep'
        display_df = topic_perf_df[topic_perf_df.index != 'WASSCE Prep']
        
        if not display_df.empty:
            col1, col2 = st.columns(2)
            with col1:
                # Use the filtered display_df
                best_topic = display_df.index[0]; best_acc = display_df['Accuracy'].iloc[0]
                st.success(f"💪 **Strongest Topic:** {best_topic} ({best_acc:.1f}%)")
            with col2:
                # Use the filtered display_df
                if len(display_df) > 1:
                    worst_topic = display_df.index[-1]; worst_acc = display_df['Accuracy'].iloc[-1]
                    st.warning(f"🤔 **Area for Practice:** {worst_topic} ({worst_acc:.1f}%)")
            # Use the filtered display_df for the chart
            fig = px.bar(
                display_df, y='Accuracy', title="Average Accuracy by Topic",
                labels={'Accuracy': 'Accuracy (%)', 'Topic': 'Topic'}, text_auto='.2s'
            )
            # --- END: THIS IS THE FIX ---
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
def display_help_center_page():
    st.header("❓ Help Center & FAQ")
    st.info("Find answers to common questions about how to use MathFriend. Click on any question to see the answer.")

    st.subheader("🚀 Getting Started")
    with st.expander("How do I create an account?"):
        st.markdown("""
        1. On the login page, click the **"Don't have an account? Sign Up"** button.
        2. Choose a username. It can only contain letters, numbers, and the underscore symbol (`_`). No spaces are allowed.
        3. Create a secure password and confirm it.
        4. Click **"Create Account"**. You will be taken back to the login page to sign in.
        """)

    st.subheader("🏆 Gamification & Rewards")
    with st.expander("How do Daily Challenges work?"):
        st.markdown("""
        Every day, you are assigned a new challenge which you can see on your **📊 Dashboard**. These are small tasks, like "Answer 5 questions correctly on any topic." Completing your challenge gives you a **50 coin bonus!** Progress is tracked automatically as you use the app.
        """)
    with st.expander("What are Achievements?"):
        st.markdown("""
        Achievements are special badges you earn for reaching important milestones in the app, like taking your first quiz or mastering a topic by getting 25 correct answers. You can view all your earned badges in the **"🏆 My Achievements"** tab on your Profile page. Each achievement also comes with a one-time coin reward!
        """)
        
    st.subheader("📝 Quizzes & ⚔️ Duels")
    with st.expander("How does the quiz system work?"):
        st.markdown("""
        The quiz is the core of MathFriend! 
        - **Choose a Topic:** Select any topic from the dropdown list. The app may suggest a topic where you have the lowest accuracy.
        - **Answer Questions:** Each solo quiz round has 10 questions.
        - **Adaptive Difficulty:** The app tracks your "skill score" for each topic. If you score well, you'll start getting harder questions. If you struggle, the questions will get easier to help you build your foundation.
        - **Scoring:** You earn coins for correct answers and build up a "streak." Getting a high streak gives you a special balloon celebration!
        """)
    
    # --- START: NEW EXPANDER FOR WASSCE PREP ---
    with st.expander("What is WASSCE Prep Mode?"):
        st.markdown("""
        WASSCE Prep is a special mock exam mode designed to test your readiness for the real thing. Here’s how it's different from a solo quiz:
        - **Length:** It's a challenging **40-question** quiz.
        - **Topics:** Questions are pulled randomly from **all available topics** to simulate a real exam.
        - **Scoring:** Your final score **is saved** to your permanent history so you can track your improvement. You also earn coins for correct answers.
        - **Skill Score:** Importantly, your performance in this mode **does not** affect your individual skill scores for specific topics (like Algebra or Sets). This allows you to practice without worrying about lowering your hard-earned skill levels.
        """)
    # --- END: NEW EXPANDER ---

    with st.expander("What are the 'Lifelines' (Hint, 50/50, Skip)?"):
        st.markdown("""
        These are special items you can buy from the shop to help you during quizzes. You can see how many you own at the top of the quiz page.
        - **💡 Hint:** Reveals a helpful hint for the current question.
        - **🔀 50/50:** Removes two of the incorrect answer options, leaving you with a 50/50 chance.
        - **↪️ Skip:** Allows you to skip a question entirely without it affecting your score or streak.
        """)
    with st.expander("How do I challenge a friend to a duel?"):
        st.markdown("""
        1. Go to the **⚔️ Math Game** page from the sidebar.
        2. Make sure the **"Enable Live Lobby"** toggle at the top is ON. This makes you visible to others and allows you to receive challenges.
        3. You will see a list of other "Online Players" on the right.
        4. Click the **"Duel"** button next to the name of the person you want to challenge.
        5. Choose a topic and send the challenge! The first person to answer each question correctly gets the point.
        """)

    # --- START: NEW SECTION FOR LEADERBOARDS ---
    st.subheader("🏆 Leaderboards")
    with st.expander("How do the Leaderboards work?"):
        st.markdown("""
        The leaderboards are where you can see how you stack up against other MathFriend users!
        - **Overall Performance:** This board ranks players by their **total number of correct answers** across all topics and all time (or within the selected time filter). It's a measure of total effort and knowledge.
        - **Topic-Specific Boards:** When you select a topic like "Percentages," the ranking is based on **highest accuracy**. This allows specialists in a topic to shine, even if they haven't answered as many total questions.
        - **Rival Snapshot:** This special box on the leaderboard page shows you the player ranked directly above you and the player directly below you, giving you a target to chase and a rival to stay ahead of!
        """)
    # --- END: NEW SECTION ---

    st.subheader("👤 Profile, Shop & Gifting")
    with st.expander("How does the coin and shop system work?"):
        st.markdown("""
        You earn coins by playing and performing well in the app! You can then spend these coins in the **Shop**, which is located in the **👤 Profile** tab.
        - **Earning 🪙:** You get coins for correct quiz answers, winning duels, completing daily challenges, and unlocking achievements. Activating a "Double Coins Booster" from the shop will double all your earnings for one hour!
        - **Spending 🪙:** You can buy consumable items (like Hints and Mystery Boxes) or permanent cosmetic items (like Borders and Name Effects) to customize your profile.
        """)
    with st.expander("How do I equip a border or name effect I bought?"):
        st.markdown("""
        1. Go to the **👤 Profile** page.
        2. On the first tab, **"📝 My Profile"**, scroll down to the "🎨 Customize Your Look" section.
        3. You will see sections for "Active Border" and "Active Name Effect".
        4. Simply select the cosmetic item you want to use from the list of items you own, and it will be applied instantly.
        """)
    with st.expander("How do I send a gift to a friend?"):
        st.markdown("""
        There are two ways to gift:
        1.  **Gifting an Item:** In the Shop, every item has a "Gift" button next to the "Buy" button. Click it, enter your friend's username, and the item will be sent directly to them (and the coins deducted from your balance).
        2.  **Transferring Coins:** At the bottom of the Shop, there is a form to send coins directly to another user.
        """)
        
    st.subheader("📚 Learning & Community")
    with st.expander("What are Learning Resources?"):
        st.markdown("""
        The **📚 Learning Resources** page is your digital textbook. For each topic, you can find:
        - **Teacher's Corner:** Special practice questions and assignments posted by the administrator.
        - **Key Formulas & Notes:** A quick summary of the most important concepts.
        - **Video Tutorials:** Links to helpful videos to explain the topic further.
        - **Interactive Widgets:** Calculators and tools that let you experiment with concepts, like a Pythagoras calculator or a Venn diagram tool.
        """)
    with st.expander("What is the Blackboard for?"):
        st.markdown("""
        The **💬 Blackboard** is the community chat room. It's a place to ask for help on difficult problems, discuss topics with your classmates, or just say hello!
        """)
        
    st.subheader("🔐 Account & Support")
    with st.expander("How do I change my password?"):
        st.markdown("""
        You can change your password at any time from your Profile page.
        1. Go to the **👤 Profile** page.
        2. On the **"📝 My Profile"** tab, scroll to the bottom.
        3. Fill out the "Change Password" form by providing your current password and a new one.
        """)
    with st.expander("What if I forget my password?"):
        st.markdown("""
        Currently, there is no automated password reset feature. Please contact your teacher or the app administrator, and they can reset your password for you from the Admin Panel.
        """)
    with st.expander("Who do I contact to report a bug or suggest a feature?"):
        st.markdown("""
        We would love to hear your feedback! Please report any issues or suggestions directly to your teacher or the app administrator.
        """)
        
    # --- START: NEW SECTION FOR TROUBLESHOOTING ---
    st.subheader("🔧 Troubleshooting & Common Issues")
    with st.expander("Why can't I see my friend online to duel them?"):
        st.markdown("""
        To be visible in the Math Game Lobby and to challenge other players, both you and your friend must have the **"Enable Live Lobby"** toggle switch turned ON at the top of the **⚔️ Math Game** page. If the toggle is off, you are invisible to other players.
        """)
    with st.expander("Why did my quiz not resume after I logged back in?"):
        st.markdown("""
        The quiz resume feature is designed to save you from accidental disconnections or short breaks. However, to keep the system clean, an unfinished quiz session is automatically cleared if you do not return to it within **8 hours**. After 8 hours of inactivity, you will need to start a new quiz.
        """)
    # --- END: NEW SECTION ---
def display_blackboard_page():
    st.header("칠판 Blackboard")
    st.info("This is a community space. Ask clear questions, be respectful, and help your fellow students!", icon="👋")

    online_users = get_online_users(st.session_state.username)
    if online_users:
        pills_html_list = [_generate_user_pill_html(user) for user in online_users]
        pills_str = "".join(pills_html_list)
        container_style = """
            display: flex; align-items: center; width: 100%;
            overflow-x: auto; white-space: nowrap; padding-bottom: 10px;
        """
        st.markdown(f"""
            <div style="display: flex; align-items: center; margin-bottom: 10px;">
                <span style="margin-right: 10px; font-weight: bold;">🟢 Online:</span>
                <div style="{container_style}">{pills_str}</div>
            </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown("_No other users are currently active._")
    st.markdown("<hr class='styled-hr'>", unsafe_allow_html=True)

    st_autorefresh(interval=15000, key="chat_refresh")

    channel = chat_client.channel("messaging", channel_id="mathfriend-blackboard", data={"name": "MathFriend Blackboard"})
    state = channel.query(watch=False, state=True, messages={"limit": 50})
    messages = state['messages']

    user_ids_in_chat = {msg["user"].get("id") for msg in messages if msg["user"].get("id")}
    display_infos = get_user_display_info(user_ids_in_chat)
    
    st.markdown('<div class="chat-container">', unsafe_allow_html=True)

    last_message_date = None
    for msg in messages:
        # --- Date Chip Logic ---
        raw_datetime = msg['created_at']
        dt_object = parser.parse(raw_datetime) if isinstance(raw_datetime, str) else raw_datetime
        current_message_date = dt_object.astimezone().date()

        if last_message_date != current_message_date:
            display_date = "Today" if current_message_date == datetime.now().astimezone().date() else current_message_date.strftime("%B %d, %Y")
            st.markdown(f'<div class="chat-date-divider"><span class="chat-date-chip">{display_date}</span></div>', unsafe_allow_html=True)
            last_message_date = current_message_date
        # --- End Date Chip Logic ---
        user_id = msg["user"].get("id", "Unknown")
        user_name = msg["user"].get("name", user_id)
        is_current_user = (user_id == st.session_state.username)
        
        user_info = display_infos.get(user_id, {})
        user_flair = user_info.get("flair")
        
        raw_datetime = msg['created_at']
        dt_object = parser.parse(raw_datetime) if isinstance(raw_datetime, str) else raw_datetime
        timestamp = dt_object.astimezone().strftime("%I:%M %p")

        avatar_html = _generate_avatar_html(user_name)

        # --- THIS IS THE FIX ---
        # The multiline f-string for meta_html has been un-indented.
        # This prevents Streamlit's markdown renderer from misinterpreting
        # the HTML and misplacing the closing </div> tag.
        flair_html = f"<i>{user_flair}</i><br>" if user_flair else ""
        meta_html = f"""<div class="chat-meta">
<strong>{user_name}</strong>
{flair_html}
{timestamp}
</div>"""
        # --- END OF FIX ---
        
        bubble_html = f'<div class="chat-bubble {"user" if is_current_user else "assistant"}">{msg["text"]}</div>'
        
        if is_current_user:
            row_html = f'<div class="chat-row user">{meta_html}{bubble_html}{avatar_html}</div>'
        else:
            row_html = f'<div class="chat-row assistant">{avatar_html}{bubble_html}{meta_html}</div>'
            
        st.markdown(row_html, unsafe_allow_html=True)

    st.markdown('</div>', unsafe_allow_html=True)
            
    if prompt := st.chat_input("Post your question or comment..."):
        channel.send_message({"text": prompt}, user_id=st.session_state.username)
        st.rerun()
def display_math_game_page(topic_options):
    """Displays the duel lobby with a new, improved two-column layout and a duel leaderboard."""
    st.header("⚔️ Math Game Lobby")
    
    if 'live_lobby_active' not in st.session_state:
        st.session_state.live_lobby_active = False
    
    st.session_state.live_lobby_active = st.toggle(
        "Enable Live Lobby", 
        value=st.session_state.live_lobby_active, 
        help="Turn this on to receive challenges from other players in real-time."
    )

    left_col, right_col = st.columns([2, 1])

    with right_col:
        st.subheader("Online Players")
        online_users = get_online_users(st.session_state.username)
        
        if online_users:
            with st.container(height=400):
                for user in online_users:
                    with st.container(border=True):
                        c1, c2 = st.columns([3, 1]) 
                        with c1:
                            st.markdown(_generate_user_pill_html(user), unsafe_allow_html=True)
                        with c2:
                            if st.button("Duel", key=f"challenge_{user}", use_container_width=True):
                                st.session_state.challenging_user = user
                                st.rerun()
        else:
            st.markdown("_No other users are currently online._")

    with left_col:
        is_configuring_challenge = 'challenging_user' in st.session_state
        pending_challenge = get_pending_challenge(st.session_state.username) if st.session_state.live_lobby_active else None

        if st.session_state.live_lobby_active and not is_configuring_challenge and not pending_challenge:
            st_autorefresh(interval=3000, key="challenge_refresh")
        
        if is_configuring_challenge:
            opponent = st.session_state.challenging_user
            with st.container(border=True):
                st.subheader(f"Challenge {opponent}")
                duel_topic_options = [t for t in topic_options if t != "Advanced Combo"]
                topic = st.selectbox("Choose a topic for your duel:", duel_topic_options)
                c1, c2 = st.columns(2)
                if c1.button("✅ Send Challenge", use_container_width=True, type="primary"):
                    duel_id = create_duel(st.session_state.username, opponent, topic)
                    if duel_id:
                        st.toast(f"Challenge sent to {opponent}!", icon="⚔️")
                        st.session_state.page = "duel"
                        st.session_state.current_duel_id = duel_id
                        del st.session_state.challenging_user
                        st.rerun()
                if c2.button("❌ Cancel", use_container_width=True):
                    del st.session_state.challenging_user
                    st.rerun()

        elif pending_challenge:
            with st.container(border=True):
                challenger, topic, duel_id = pending_challenge['player1_username'], pending_challenge['topic'], pending_challenge['id']
                st.success(f"⚔️ **Incoming Challenge!**")
                st.write(f"**{challenger}** has challenged you to a duel on **{topic}**.")
                c1, c2 = st.columns(2)
                if c1.button("✅ Accept", use_container_width=True, type="primary", key=f"accept_{duel_id}"):
                    accept_duel(duel_id, topic)
                    st.session_state.page = "duel"
                    st.session_state.current_duel_id = duel_id
                    st.rerun()
                if c2.button("❌ Decline", use_container_width=True, key=f"decline_{duel_id}"):
                    st.toast("Challenge declined.")
                    st.rerun()
        
        else: 
            active_duel = get_active_duel_for_player(st.session_state.username)
            if active_duel:
                st.session_state.page = "duel"
                st.session_state.current_duel_id = active_duel['id']
                st.rerun()
            else:
                # --- START: UPGRADED DUEL LEADERBOARD ---
                st.subheader("🏆 Top 5 Duelists")
                top_duelists = get_top_duel_players()
                if top_duelists:
                    top_usernames = [player['username'] for player in top_duelists]
                    display_infos = get_user_display_info(top_usernames)

                    st.markdown("""
                        <div style="display: flex; justify-content: space-between; padding: 10px 0; border-bottom: 2px solid #dee2e6; font-weight: bold;">
                            <div style="flex: 0 0 70px;">Rank</div>
                            <div style="flex: 1;">Username</div>
                            <div style="flex: 0 0 120px; text-align: right;">Total Wins</div>
                        </div>
                    """, unsafe_allow_html=True)

                    for r, player_data in enumerate(top_duelists, 1):
                        username = player_data['username']
                        total_wins = player_data['total_wins']
                        user_info = display_infos.get(username, {})
                        is_current_user = (username == st.session_state.username)

                        active_border = user_info.get('border')
                        border_class_map = {
                            'bronze_border': 'bronze-border', 'silver_border': 'silver-border',
                            'gold_border': 'gold-border', 'rainbow_border': 'rainbow-border'
                        }
                        border_class = border_class_map.get(active_border, "")

                        if border_class:
                            style_attributes = "border-radius: 8px; padding: 10px; margin-bottom: 5px;"
                        else:
                            style_attributes = "border: 1px solid #e1e4e8; border-radius: 8px; padding: 10px; margin-bottom: 5px;"

                        if is_current_user:
                            style_attributes += " background-color: #e6f7ff;"

                        rank_display = "🥇" if r == 1 else "🥈" if r == 2 else "🥉" if r == 3 else f"{r}"
                        
                        username_display = username
                        active_effect = user_info.get('effect')
                        if active_effect == 'bold_effect':
                            username_display = f"<b>{username_display}</b>"
                        elif active_effect == 'italic_effect':
                            username_display = f"<i>{username_display}</i>"
                        
                        if is_current_user:
                            username_display = f"<strong>{username_display} (You)</strong>"
                        
                        st.markdown(f"""
                        <div class="{border_class}" style="{style_attributes}">
                            <div style="display: flex; justify-content: space-between; align-items: center;">
                                <div style="flex: 0 0 70px;">{rank_display}</div>
                                <div style="flex: 1;">{username_display}</div>
                                <div style="flex: 0 0 120px; text-align: right; font-weight: bold; color: #0d6efd;">{total_wins} Wins</div>
                            </div>
                        </div>
                        """, unsafe_allow_html=True)
                else:
                    st.info("No duel wins have been recorded yet. Be the first!")
                # --- END: UPGRADED DUEL LEADERBOARD ---
                
                st.markdown("<hr>", unsafe_allow_html=True)
                st.subheader("How to Play")
                st.markdown("""
                - **1. Send a Challenge:** Find an online player and click 'Duel'.
                - **2. Wait for Acceptance:** You will be taken to a waiting screen.
                - **3. Receive Challenges:** To get invitations, turn on the 'Enable Live Lobby' toggle.
                - **4. Win:** The first player to answer correctly wins the point!
                """)
def display_quiz_page(topic_options):
    st.header("🧠 Quiz Time!")

    # --- Section 1: This block runs when NO quiz is active ---
    if not st.session_state.quiz_active:
        st.subheader("Choose Your Challenge")
        st.markdown("---")
        col1, col2 = st.columns(2)

        with col1:
            with st.container(border=True):
                st.markdown("#### 🎯 Solo Practice")
                st.caption("Focus on a single topic to improve your skills.")
                topic_perf_df = get_topic_performance(st.session_state.username)
                
                # --- START: THIS IS THE FIX ---
                # Create a new DataFrame for suggestions that excludes 'WASSCE Prep'
                suggestion_df = topic_perf_df[topic_perf_df.index != 'WASSCE Prep']
                
                if not suggestion_df.empty and len(suggestion_df) > 1 and suggestion_df['Accuracy'].iloc[-1] < 100:
                    # Get the weakest topic from the filtered list
                    weakest_topic = suggestion_df.index[-1]
                    st.info(f"**Practice Suggestion:** Your lowest accuracy is in **{weakest_topic}**.")
                # --- END: THIS IS THE FIX ---
                selected_topic = st.selectbox("Select a topic to begin:", topic_options)
                if st.button("Start Solo Quiz", type="secondary", use_container_width=True, key="start_quiz_main"):
                    st.session_state.is_wassce_mode = False
                    st.session_state.quiz_active = True
                    st.session_state.quiz_topic = selected_topic
                    st.session_state.on_summary_page = False
                    st.session_state.quiz_score = 0
                    st.session_state.questions_answered = 0
                    st.session_state.questions_attempted = 0
                    st.session_state.current_streak = 0
                    st.session_state.incorrect_questions = []
                    keys_to_clear = ['current_q_data', 'result_saved', 'checked_personal_best', 'previous_best_accuracy', 'all_wassce_questions']
                    for key in keys_to_clear:
                        if key in st.session_state: del st.session_state[key]
                    st.rerun()

        with col2:
            with st.container(border=True):
                st.markdown("#### 🚀 WASSCE Prep")
                st.caption("A 40-question, mixed-topic challenge to test your exam readiness!")
                st.markdown(f'<img src="https://github.com/derricktogodui/mathfriend-app/releases/download/v1.0-assets/WASSCE.Study.Session.in.Action.png" class="quiz-prep-image">', unsafe_allow_html=True)
                if st.button("Start Exam Prep", key="start_wassce", type="primary", use_container_width=True):
                    st.session_state.is_wassce_mode = True
                    st.session_state.quiz_active = True
                    st.session_state.quiz_topic = "WASSCE Prep"
                    # The 'quiz_start_time' line has been removed
                    st.session_state.on_summary_page = False
                    st.session_state.quiz_score = 0
                    st.session_state.questions_answered = 0
                    st.session_state.questions_attempted = 0
                    st.session_state.current_streak = 0
                    st.session_state.incorrect_questions = []
                    st.session_state.all_wassce_questions = []
                    keys_to_clear = ['current_q_data', 'result_saved', 'checked_personal_best', 'previous_best_accuracy']
                    for key in keys_to_clear:
                        if key in st.session_state: del st.session_state[key]
                    st.rerun()
        return

    # --- Section 2: This block runs when a quiz IS active ---
    quiz_length = WASSCE_QUIZ_LENGTH if st.session_state.is_wassce_mode else QUIZ_LENGTH
    
    if st.session_state.get('on_summary_page', False) or st.session_state.questions_answered >= quiz_length:
        display_quiz_summary()
        return

    user_profile = get_user_profile(st.session_state.username) or {}
    hint_tokens = user_profile.get('hint_tokens', 0)
    fifty_fifty_tokens = user_profile.get('fifty_fifty_tokens', 0)
    skip_tokens = user_profile.get('skip_question_tokens', 0)

    if is_double_coins_active(st.session_state.username):
        st.info("🚀 **Double Coins Active!** All rewards from this quiz will be doubled.", icon="🎉")

    col1, col2, col3 = st.columns(3)
    with col1: st.metric("Score", f"{st.session_state.quiz_score}/{st.session_state.questions_attempted}")
    with col2: st.metric("Question", f"{st.session_state.questions_answered + 1}/{quiz_length}")
    with col3: st.metric("🔥 Streak", st.session_state.current_streak)
    st.caption(f"Your Items: 💡 Hints ({hint_tokens}) | 🔀 50/50s ({fifty_fifty_tokens}) | ↪️ Skips ({skip_tokens})")
    
    st.progress(st.session_state.questions_answered / quiz_length, text="Round Progress")
    st.markdown("<hr class='styled-hr'>", unsafe_allow_html=True)
    
    if 'current_q_data' not in st.session_state:
        if st.session_state.is_wassce_mode:
            available_topics = [t for t in topic_options if t != "Advanced Combo"]
            random_topic = random.choice(available_topics)
            question_data = get_adaptive_question(random_topic, st.session_state.username)
            question_data['topic'] = random_topic
            st.session_state.current_q_data = question_data
            if 'all_wassce_questions' not in st.session_state: st.session_state.all_wassce_questions = []
            st.session_state.all_wassce_questions.append(question_data)
        else:
            st.session_state.current_q_data = get_adaptive_question(st.session_state.quiz_topic, st.session_state.username)
        # --- ADD THIS NEW LINE ---
        save_quiz_state(st.session_state.username)
    
    q_data = st.session_state.current_q_data
    display_topic = q_data.get('topic', st.session_state.quiz_topic)
    st.subheader(f"Topic: {display_topic}")

    if not st.session_state.get('answer_submitted', False):
        part_data = q_data.get("parts", [{}])[st.session_state.get('current_part_index', 0)] if q_data.get("is_multipart") else q_data
        
        if q_data.get("is_multipart"):
            st.markdown(q_data["stem"], unsafe_allow_html=True)
        st.markdown(part_data["question"], unsafe_allow_html=True)
        
        with st.expander("🤔 Need Help? (Click to see lifelines)"):
            help_cols = st.columns(3)
            with help_cols[0]:
                if st.session_state.get('hint_revealed', False):
                    st.info(part_data["hint"])
                else:
                    if st.button(f"💡 Hint ({hint_tokens})", disabled=(hint_tokens <= 0), key="use_hint", use_container_width=True):
                        if use_hint_token(st.session_state.username):
                            st.session_state.hint_revealed = True
                            st.rerun()
            with help_cols[1]:
                if st.button(f"🔀 50/50 ({fifty_fifty_tokens})", disabled=(fifty_fifty_tokens <= 0 or st.session_state.get('fifty_fifty_used', False)), key="use_5050", use_container_width=True):
                    if use_fifty_fifty_token(st.session_state.username):
                        st.session_state.fifty_fifty_used = True
                        correct_answer = part_data["answer"]
                        incorrect_options = [opt for opt in part_data["options"] if str(opt) != str(correct_answer)]
                        option_to_keep = random.choice(incorrect_options)
                        new_options = [correct_answer, option_to_keep]
                        random.shuffle(new_options)
                        if q_data.get("is_multipart"):
                            st.session_state.current_q_data['parts'][st.session_state.get('current_part_index', 0)]['options'] = new_options
                        else:
                            st.session_state.current_q_data['options'] = new_options
                        st.rerun()
            with help_cols[2]:
                if st.button(f"↪️ Skip ({skip_tokens})", disabled=(skip_tokens <= 0), key="use_skip", use_container_width=True):
                    if use_skip_question_token(st.session_state.username):
                        st.toast("Question skipped!", icon="↪️")
                        st.session_state.questions_answered += 1
                        keys_to_reset = ['hint_revealed', 'fifty_fifty_used', 'current_q_data', 'user_choice', 'answer_submitted']
                        for key in keys_to_reset:
                            if key in st.session_state: del st.session_state[key]
                        st.rerun()

        with st.form(key=f"quiz_form_{st.session_state.questions_answered}"):
            user_choice = st.radio("Select your answer:", part_data["options"], index=None)
            if st.form_submit_button("Submit Answer", type="primary"):
                if user_choice is not None:
                    st.session_state.user_choice = user_choice
                    st.session_state.answer_submitted = True
                    st.session_state.questions_attempted += 1
                    is_correct = str(user_choice) == str(part_data["answer"])
                    if is_correct:
                        st.session_state.quiz_score += 1
                        st.session_state.current_streak += 1
                    else:
                        st.session_state.current_streak = 0
                        st.session_state.incorrect_questions.append(q_data)
                    st.rerun()
                else:
                    st.warning("Please select an answer before submitting.")
    else:
        user_choice = st.session_state.user_choice
        part_data = q_data.get("parts", [{}])[st.session_state.get('current_part_index', 0)] if q_data.get("is_multipart") else q_data
        actual_answer = part_data["answer"]
        explanation = part_data.get("explanation", "")
        question_text = (q_data.get("stem", "") + "\n\n" + part_data["question"]) if q_data.get("is_multipart") else part_data["question"]
        is_correct = str(user_choice) == str(actual_answer)
        st.markdown(question_text, unsafe_allow_html=True)
        st.write("Your answer:")
        if is_correct:
            st.success(f"**{user_choice}** (Correct!)")
            if st.session_state.current_streak in [3, 5] or (st.session_state.current_streak > 5 and st.session_state.current_streak % 5 == 0):
                st.balloons()
        else:
            st.error(f"**{user_choice}** (Incorrect)")
            st.info(f"The correct answer was: **{actual_answer}**")
        with st.expander("Show Explanation", expanded=True):
            st.markdown(explanation, unsafe_allow_html=True)
        if st.button("Next Question", type="primary", use_container_width=True):
            st.session_state.questions_answered += 1
            keys_to_reset = ['hint_revealed', 'fifty_fifty_used', 'current_q_data', 'user_choice', 'answer_submitted']
            for key in keys_to_reset:
                if key in st.session_state: del st.session_state[key]
            st.rerun()

    if st.button("Stop Round & Save Score"):
        st.session_state.on_summary_page = True
        keys_to_delete = ['current_q_data', 'user_choice', 'answer_submitted', 'current_part_index', 'multi_part_correct', 'hint_revealed', 'fifty_fifty_used']
        for key in keys_to_delete:
            if key in st.session_state: del st.session_state[key]
        st.rerun()

def display_quiz_summary():
    st.header("🎉 Round Complete! 🎉")
    # --- START: NEW CODE TO ADD ---
    # This is the first action we take on the summary page.
    # It clears the saved session from the database, marking the quiz as officially done.
    clear_quiz_state(st.session_state.username)
    # --- END: NEW CODE TO ADD ---

    final_score = st.session_state.quiz_score
    total_questions = st.session_state.questions_attempted
    accuracy = (final_score / total_questions * 100) if total_questions > 0 else 0

    # --- WASSCE MODE SUMMARY (NOW WITH SAVING AND COINS) ---
    if st.session_state.is_wassce_mode:
        # --- START: NEW LOGIC FOR WASSCE SAVING & REWARDS ---
        coins_earned = 0
        description = ""
        if total_questions > 0:
            coins_earned = final_score * 5  # 5 coins per correct answer
            description = "Completed WASSCE Prep Quiz"
            if final_score == WASSCE_QUIZ_LENGTH:
                coins_earned += 50  # Larger bonus for a perfect 40-question run
                description += " (Perfect Score Bonus!)"

        if is_double_coins_active(st.session_state.username):
            st.success(f"🚀 Double Coins booster was active! Your earnings are doubled: {coins_earned} -> {coins_earned * 2}", icon="🎉")
            coins_earned *= 2

        # Save the result once per session
        if total_questions > 0 and 'result_saved' not in st.session_state:
            save_quiz_result(st.session_state.username, "WASSCE Prep", final_score, total_questions, coins_earned, description)
            st.session_state.result_saved = True
        # --- END: NEW LOGIC FOR WASSCE SAVING & REWARDS ---
    # --- WASSCE MODE SUMMARY ---
    if st.session_state.is_wassce_mode:
        col1, col2 = st.columns(2)
        col1.metric("Final Score", f"{final_score}/{WASSCE_QUIZ_LENGTH}")
        col2.metric("Accuracy", f"{accuracy:.1f}%")
        
        st.markdown("<hr class='styled-hr'>", unsafe_allow_html=True)
        st.subheader("Performance Breakdown & Explanation")
        
        if total_questions > 0:
            if not st.session_state.incorrect_questions:
                st.success("🎉 Incredible! You had no incorrect answers in this session!")
            else:
                topic_performance = {}
                all_attempted_q_data = st.session_state.get('all_wassce_questions', [])
                for q in all_attempted_q_data:
                    topic = q.get('topic', 'Unknown')
                    if topic not in topic_performance:
                        topic_performance[topic] = {'correct': 0, 'total': 0}
                    topic_performance[topic]['total'] += 1
                    if q not in st.session_state.incorrect_questions:
                        topic_performance[topic]['correct'] += 1
                st.write("Here's how you performed in WASSCE prep during this session:")
        else:
            st.info("You did not attempt any questions in this session.")
        # --- THIS IS THE FIX: ADDING THE INCORRECT QUESTION REVIEW ---
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
        # --- END OF FIX ---
        
        if st.button("Back to Quiz Menu", use_container_width=True):
            st.session_state.is_wassce_mode = False
            st.session_state.quiz_active = False
            if 'result_saved' in st.session_state: del st.session_state['result_saved']
            if 'all_wassce_questions' in st.session_state: del st.session_state['all_wassce_questions']
            st.rerun()

    # --- REGULAR QUIZ SUMMARY ---
    else: # <-- THIS IS THE CORRECTED INDENTATION
        coins_earned = 0
        description = ""
        if total_questions > 0:
            coins_earned = final_score * 5
            description = f"Completed Quiz on {st.session_state.quiz_topic}"
            # --- START: NEW ONE-TIME BONUS LOGIC ---
            # Check for a perfect score
            if final_score == total_questions and total_questions > 0:
                # Check if the user is eligible for the one-time bonus for this topic
                is_bonus_eligible = _check_and_award_perfect_score_bonus(st.session_state.username, st.session_state.quiz_topic)
                if is_bonus_eligible:
                    coins_earned += 25
                    description += " (First-Time Perfect Score Bonus!)"
                    st.toast(f"🎯 New Achievement! You perfected '{st.session_state.quiz_topic}'!", icon="🎉")
            # --- END: NEW ONE-TIME BONUS LOGIC ---
        if is_double_coins_active(st.session_state.username):
            st.success(f"🚀 Double Coins booster was active! Your earnings are doubled: {coins_earned} -> {coins_earned * 2}", icon="🎉")
            coins_earned *= 2

        if total_questions > 0 and 'result_saved' not in st.session_state:
            save_quiz_result(st.session_state.username, st.session_state.quiz_topic, final_score, total_questions, coins_earned, description)
            st.session_state.result_saved = True
            
        col1, col2, col3 = st.columns(3)
        col1.metric(label="Your Final Score", value=f"{final_score}/{total_questions}")
        col2.metric(label="Accuracy", value=f"{accuracy:.1f}%")
        if coins_earned > 0:
            col3.metric(label="🪙 Coins Earned", value=f"+{coins_earned}")
        
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
                st.session_state.on_summary_page = False; st.session_state.quiz_active = True
                st.session_state.quiz_score = 0; st.session_state.questions_answered = 0
                st.session_state.questions_attempted = 0; st.session_state.current_streak = 0
                st.session_state.incorrect_questions = []
                keys_to_clear = ['current_q_data', 'result_saved', 'current_part_index', 'user_choice', 'answer_submitted', 'checked_personal_best', 'previous_best_accuracy']
                for key in keys_to_clear:
                    if key in st.session_state: del st.session_state[key]
                st.rerun()
                
        with col2:
            if st.button("Choose New Topic", use_container_width=True):
                st.session_state.on_summary_page = False; st.session_state.quiz_active = False
                if 'result_saved' in st.session_state: del st.session_state['result_saved']
                st.rerun()
def display_leaderboard(topic_options):
    st.header("🏆 Global Leaderboard")
    
    leaderboard_options = ["🏆 Overall Performance"] + topic_options
    col1, col2 = st.columns([2, 3])
    with col1:
        leaderboard_topic = st.selectbox("Select a category:", leaderboard_options, index=0)
    with col2:
        time_filter_option = st.radio("Filter by time:",["This Week", "This Month", "All Time"],index=2,horizontal=True,label_visibility="collapsed")
    
    time_filter_map = {"This Week": "week", "This Month": "month", "All Time": "all"}
    time_filter = time_filter_map[time_filter_option]

    st.markdown("<hr class='styled-hr'>", unsafe_allow_html=True)

    def display_rival_card(rival_data, total_players, label):
        col_rank, col_rivals = st.columns([1, 2])
        with col_rank:
            if rival_data and rival_data.get('user_rank') is not None:
                st.metric(label=label, value=f"#{rival_data['user_rank']} / {total_players} players")
            else:
                st.metric(label=label, value="N/A")
        
        with col_rivals:
            if rival_data and rival_data.get('user_rank') is not None:
                card_html = """<div style="border: 1px solid #e1e4e8; border-left: 5px solid #0d6efd; border-radius: 10px; padding: 1rem; background-color: #f8f9fa; height: 100%;">
                    <h5 style="margin-top: 0; margin-bottom: 0.75rem; font-weight: 500;">⚔️ Rival Snapshot</h5>"""
                if rival_data['rival_above']:
                    card_html += f"""<p style="margin-bottom: 0.5rem;"><span style="color:green; font-size: 1.2rem; font-weight: bold;">^</span> You're chasing: <strong>{rival_data['rival_above']['username']}</strong> (Rank #{rival_data['rival_above']['rank']})</p>"""
                else:
                    card_html += """<p style="margin-bottom: 0.5rem; color: green;">🎉 You're #1! There's no one above you!</p>"""
                if rival_data['rival_below']:
                    card_html += f"""<p style="margin-bottom: 0;"><span style="color:red; font-size: 1.2rem; font-weight: bold;">v</span> You're ahead of: <strong>{rival_data['rival_below']['username']}</strong> (Rank #{rival_data['rival_below']['rank']})</p>"""
                else:
                    card_html += """<p style="margin-bottom: 0;">Keep going to pull ahead of the pack!</p>"""
                card_html += "</div>"
                st.markdown(card_html, unsafe_allow_html=True)
            else:
                st.info(f"Take a quiz to get on the leaderboard!")
    
    if leaderboard_topic == "🏆 Overall Performance":
        total_players = get_total_overall_players(time_filter)
        rival_data = get_overall_rival_snapshot(st.session_state.username, time_filter)
        display_rival_card(rival_data, total_players, "Your Overall Rank")

        st.subheader(f"Top 10 Overall Performers ({time_filter_option})")
        st.caption("Ranked by total number of correct answers across all topics.")
        top_scores = get_overall_top_scores(time_filter)
        if top_scores:
            top_usernames = [score[0] for score in top_scores]
            display_infos = get_user_display_info(top_usernames)
            titles = [ "🥇 Math Legend", "🥈 Prime Mathematician", "🥉 Grand Prodigy", "The Destroyer", "Merlin", "The Genius", "Math Ninja", "The Professor", "The Oracle", "Last Baby" ]
            
            # This is your existing header, which we can keep.
            st.markdown("""
                <div style="display: flex; justify-content: space-between; padding: 10px 0; border-bottom: 2px solid #dee2e6; font-weight: bold;">
                    <div style="flex: 0 0 150px;">Rank</div>
                    <div style="flex: 1;">Username</div>
                    <div style="flex: 0 0 120px; text-align: right;">Total Score</div>
                </div>
            """, unsafe_allow_html=True)

            for r, (username, total_score) in enumerate(top_scores, 1):
                user_info = display_infos.get(username, {})
                is_current_user = (username == st.session_state.username)
                
                # --- THIS IS THE CORRECTED LOGIC ---
                active_border = user_info.get('border')
                border_class_map = {
                    'bronze_border': 'bronze-border', 'silver_border': 'silver-border',
                    'gold_border': 'gold-border', 'rainbow_border': 'rainbow-border'
                }
                border_class = border_class_map.get(active_border, "")

                # 1. Conditionally define the style string
                if border_class:
                    # If there's a special border, the class handles it. Don't add a default border here.
                    style_attributes = "border-radius: 8px; padding: 10px; margin-bottom: 5px;"
                else:
                    # If there's no special border, apply the default one.
                    style_attributes = "border: 1px solid #e1e4e8; border-radius: 8px; padding: 10px; margin-bottom: 5px;"
                
                # 2. Add the highlight for the current user
                if is_current_user:
                    style_attributes += " background-color: #e6f7ff;"

                # (The rest of the logic is the same)
                rank_title = titles[r-1] if r-1 < len(titles) else f"#{r}"
                username_display = username
                active_effect = user_info.get('effect')
                if active_effect == 'bold_effect':
                    username_display = f"<b>{username_display}</b>"
                elif active_effect == 'italic_effect':
                    username_display = f"<i>{username_display}</i>"
                if is_current_user:
                    username_display = f"<strong>{username_display} (You)</strong>"

                st.markdown(f"""
                <div class="{border_class}" style="{style_attributes}">
                    <div style="display: flex; justify-content: space-between; align-items: center;">
                        <div style="flex: 0 0 150px;">{rank_title}</div>
                        <div style="flex: 1;">{username_display}</div>
                        <div style="flex: 0 0 120px; text-align: right; font-weight: bold; color: #0d6efd;">{total_score} Correct</div>
                    </div>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.info(f"No scores recorded in this time period. Be the first!")

    else: # Topic-specific leaderboard
        # This section can be updated with the same flexbox logic if needed.
        # For now, focusing on the main "Overall" leaderboard as requested.
        total_players = get_total_players(leaderboard_topic, time_filter)
        rival_data = get_rival_snapshot(st.session_state.username, leaderboard_topic, time_filter)
        display_rival_card(rival_data, total_players, f"Your Rank in {leaderboard_topic}")

        st.subheader(f"Top 10 for {leaderboard_topic} ({time_filter_option})")
        st.caption("Ranked by highest accuracy score.")
        
        top_scores = get_top_scores(leaderboard_topic, time_filter)
        if top_scores:
            top_usernames = [score[0] for score in top_scores]
            display_infos = get_user_display_info(top_usernames)
            
            st.markdown("""
                <div style="display: flex; justify-content: space-between; padding: 10px 0; border-bottom: 2px solid #dee2e6; font-weight: bold;">
                    <div style="flex: 0 0 70px;">Rank</div>
                    <div style="flex: 1;">Username</div>
                    <div style="flex: 0 0 150px; text-align: right;">Score (Accuracy)</div>
                </div>
            """, unsafe_allow_html=True)

            for r, (u, s, t) in enumerate(top_scores, 1):
                user_info = display_infos.get(u, {})
                is_current_user = (u == st.session_state.username)

                # --- APPLY THE SAME CORRECTED LOGIC HERE ---
                active_border = user_info.get('border')
                border_class_map = {
                    'bronze_border': 'bronze-border', 'silver_border': 'silver-border',
                    'gold_border': 'gold-border', 'rainbow_border': 'rainbow-border'
                }
                border_class = border_class_map.get(active_border, "")

                if border_class:
                    style_attributes = "border-radius: 8px; padding: 10px; margin-bottom: 5px;"
                else:
                    style_attributes = "border: 1px solid #e1e4e8; border-radius: 8px; padding: 10px; margin-bottom: 5px;"

                if is_current_user:
                    style_attributes += " background-color: #e6f7ff;"

                # (The rest of the logic is the same)
                rank_display = "🥇" if r == 1 else "🥈" if r == 2 else "🥉" if r == 3 else f"{r}"
                username_display = u
                active_effect = user_info.get('effect')
                if active_effect == 'bold_effect':
                    username_display = f"<b>{username_display}</b>"
                elif active_effect == 'italic_effect':
                    username_display = f"<i>{username_display}</i>"
                if is_current_user:
                    username_display = f"<strong>{username_display} (You)</strong>"
                accuracy = (s/t)*100 if t > 0 else 0   
                st.markdown(f"""
                <div class="{border_class}" style="{style_attributes}">
                    <div style="display: flex; justify-content: space-between; align-items: center;">
                        <div style="flex: 0 0 70px;">{rank_display}</div>
                        <div style="flex: 1;">{username_display}</div>
                        <div style="flex: 0 0 150px; text-align: right; font-weight: bold; color: #0d6efd;">{s}/{t} ({accuracy:.1f}%)</div>
                    </div>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.info(f"No scores recorded for **{leaderboard_topic}** in this time period. Be the first!")
# --- NEW INTERACTIVE WIDGET FUNCTIONS (COMPLETE LIBRARY FOR ALL TOPICS) ---

def interactive_check_your_understanding(q, opts, ans, msg, key):
    """A generic widget for a quick, non-graded multiple-choice question."""
    st.subheader("Check Your Understanding")
    with st.container(border=True):
        # This line MUST have unsafe_allow_html=True
        st.markdown(q, unsafe_allow_html=True) 
        
        choice = st.radio("Select:", opts, index=None, key=key)
        if choice:
            if choice == ans: st.success(f"**Correct!** {msg}")
            else: st.error(f"**Not quite.** The correct answer is **{ans}**.")
def interactive_venn_diagram_calculator():
    st.subheader("Venn Diagram Calculator")
    with st.container(border=True):
        st.markdown("Enter the elements in each region to see the totals.")
        c1, c2, c3 = st.columns(3)
        a_only = c1.number_input("Only in Set A", 0, 1000, 10, key="v_a")
        b_only = c2.number_input("Only in Set B", 0, 1000, 15, key="v_b")
        both = c3.number_input("In Both A and B", 0, 1000, 5, key="v_both")
        total_a, total_b, union_ab = a_only + both, b_only + both, a_only + b_only + both
        st.success(f"**Results:** Total in A = **{total_a}**, Total in B = **{total_b}**, Total in A or B = **{union_ab}**")

def interactive_percentage_calculator():
    st.subheader("Percentage Calculator")
    with st.container(border=True):
        calc_type = st.radio("Choose a calculation:", ["% of Number", "% Change"], horizontal=True, key="p_calc")
        if calc_type == "% of Number":
            c1, c2 = st.columns(2)
            p = c1.number_input("What is...", value=25.0); n = c2.number_input("percent of...?", value=150.0)
            st.success(f"**Result:** {p}% of {n} is **{(p/100)*n:.2f}**")
        else:
            c1, c2 = st.columns(2)
            ov = c1.number_input("Original Value", value=200.0, min_value=0.1); nv = c2.number_input("New Value", value=250.0)
            if ov != 0: st.success(f"**Result:** The change is **{((nv-ov)/ov)*100:.2f}%**")

def interactive_fraction_widget():
    interactive_check_your_understanding(
        "What is $\\frac{1}{2} \\div \\frac{1}{4}$?", ["1/8", "2", "1/2"], "2", 
        "To divide by a fraction, you invert and multiply: $\\frac{1}{2} \\times \\frac{4}{1} = 2$.", "fractions_check"
    )

def interactive_indices_widget():
    st.subheader("Laws of Indices Explorer")
    with st.container(border=True):
        c1, c2, c3, c4 = st.columns(4)
        base = c1.number_input("Base (x)", 2, 10, 3)
        p1 = c2.number_input("Power 1 (a)", 1, 10, 4)
        p2 = c3.number_input("Power 2 (b)", 1, 10, 2)
        op = c4.selectbox("Operation", ["Multiply", "Divide", "Power"])
        if op == "Multiply":
            st.latex(f"{base}^{p1} \\times {base}^{p2} = {base}^{{{p1+p2}}} = {base**(p1+p2)}")
        elif op == "Divide":
            st.latex(f"{base}^{p1} \\div {base}^{p2} = {base}^{{{p1-p2}}} = {base**(p1-p2)}")
        else: # Power
            st.latex(f"({base}^{p1})^{p2} = {base}^{{{p1*p2}}} = {base**(p1*p2)}")

def interactive_surds_widget():
    interactive_check_your_understanding(
        "What is the conjugate of $5 + \\sqrt{3}$?", ["$5 - \\sqrt{3}$", "$-5 + \\sqrt{3}$", "22"],
        "$5 - \\sqrt{3}$", "The conjugate is found by flipping the middle sign.", "surds_check"
    )

def interactive_binary_ops_widget():
    interactive_check_your_understanding(
        "For a binary operation defined by the table below, what is $b \\ast c$? <br> | * | a | b | c | <br> |---|---|---|---| <br> | **b** | c | a | **d** |",
        ["a", "b", "c", "d"], "d", "Find the row for `b` and the column for `c`. They intersect at `d`.", "binary_check"
    )

def interactive_functions_widget():
    st.subheader("Function Evaluator")
    with st.container(border=True):
        func_str = st.text_input("Enter a function f(x)", "2*x**2 + 3*x - 5")
        x_val = st.number_input("Enter the value of x", value=3.0)
        try:
            x = x_val
            result = eval(func_str, {"x": x, "math": math})
            st.success(f"**Result:** $f({x_val}) = {result:.2f}$")
        except Exception as e:
            st.error(f"Invalid function or value. Please use Python syntax (e.g., 'x**2' for $x^2$).")

def interactive_sequence_series_widget():
    st.subheader("Sequence & Series Calculator")
    with st.container(border=True):
        seq_type = st.radio("Sequence Type", ["Arithmetic (AP)", "Geometric (GP)"], horizontal=True)
        a = st.number_input("First Term (a)", value=5.0)
        n = st.number_input("Term number (n)", min_value=1, value=10, step=1)
        if seq_type == "Arithmetic (AP)":
            d = st.number_input("Common Difference (d)", value=3.0)
            nth_term = a + (n-1)*d
            st.success(f"The **{n}th term** of this AP is **{nth_term:.2f}**")
        else:
            r = st.number_input("Common Ratio (r)", value=2.0)
            nth_term = a * (r**(n-1))
            st.success(f"The **{n}th term** of this GP is **{nth_term:.2f}**")

def interactive_word_problems_widget():
    interactive_check_your_understanding(
        "If Kofi is twice as old as Ama, and their ages sum to 24, how old is Kofi?",
        ["8", "12", "16", "20"], "16", "Let Ama's age be $x$. Kofi's age is $2x$. Then $x + 2x = 24 \implies 3x = 24 \implies x=8$. Kofi is $2 \times 8 = 16$.", "age_check"
    )

def interactive_pythagoras_calculator(): # You already have this one
    st.subheader("Pythagoras' Theorem Calculator")
    with st.container(border=True):
        st.markdown("Enter the lengths of the two shorter sides (`a` and `b`) to find the hypotenuse (`c`).")
        c1, c2 = st.columns(2)
        a = c1.number_input("Side a", min_value=0.1, value=3.0, step=0.1); b = c2.number_input("Side b", min_value=0.1, value=4.0, step=0.1)
        c = math.sqrt(a**2 + b**2)
        st.success(f"**Result:** The hypotenuse **c** is **{c:.2f}**")

def interactive_quadratic_calculator(): # You already have this one
    st.subheader("Quadratic Formula Calculator")
    with st.container(border=True):
        st.markdown("For $ax^2 + bx + c = 0$, enter the coefficients.")
        c1, c2, c3 = st.columns(3)
        a = c1.number_input("a", value=1.0); b = c2.number_input("b", value=-5.0); c = c3.number_input("c", value=6.0)
        if a != 0:
            d = b**2 - 4*a*c
            if d >= 0:
                x1 = (-b + math.sqrt(d))/(2*a); x2 = (-b - math.sqrt(d))/(2*a)
                st.success(f"**Roots:** $x_1 = {x1:.2f}$ and $x_2 = {x2:.2f}$")
            else: st.warning("No real roots.")
        else: st.error("'a' cannot be zero.")
            
def interactive_matrix_determinant_calculator():
    st.subheader("2x2 Matrix Determinant Calculator")
    with st.container(border=True):
        st.latex("\\begin{pmatrix} a & b \\\\ c & d \\end{pmatrix}")
        c1, c2 = st.columns(2)
        a = c1.number_input("a", value=4.0); b = c2.number_input("b", value=7.0)
        c = c1.number_input("c", value=2.0); d = c2.number_input("d", value=6.0)
        det = a*d - b*c
        st.success(f"**Determinant (ad - bc):** **{det:.2f}**")

def interactive_logarithm_converter():
    st.subheader("Logarithm & Exponential Form Converter")
    with st.container(border=True):
        c1, c2, c3 = st.columns(3)
        b = c1.number_input("Base (b)", min_value=2, value=3)
        x = c2.number_input("Exponent (x)", value=4)
        N = b**x
        st.success(f"**Result:** $log_{b}(N) = x \implies log_{{{b}}}({N}) = {x}$")
        st.success(f"**And:** $b^x = N \implies {b}^{{{x}}} = {N}$")

def interactive_probability_widget():
    interactive_check_your_understanding(
        "A bag has 3 red balls and 2 blue balls. What is the probability of picking a blue ball?",
        ["2/3", "3/5", "2/5", "1/2"], "2/5", "Prob = Favorable / Total = 2 blue / 5 total balls.", "prob_check"
    )

def interactive_binomial_widget():
    interactive_check_your_understanding(
        "What is the coefficient of the $x^2$ term in the expansion of $(x+2)^3$?",
        ["3", "4", "6", "12"], "6", "The term is $\\binom{3}{2}x^2(2)^1 = 3 \cdot x^2 \cdot 2 = 6x^2$.", "binom_check"
    )
    
def interactive_polynomial_widget():
    interactive_check_your_understanding(
        "What is the remainder when $P(x) = x^2 - 2x + 5$ is divided by $(x-3)$?",
        ["5", "8", "10", "20"], "8", "By the Remainder Theorem, the remainder is $P(3) = 3^2 - 2(3) + 5 = 9 - 6 + 5 = 8$.", "poly_check"
    )

def interactive_rational_functions_widget():
    interactive_check_your_understanding(
        "What is the vertical asymptote of the function $f(x) = \\frac{{x+1}}{{x-4}}$?",
        ["x = -1", "x = 4", "y = 1", "y = 4"], "x = 4", "The vertical asymptote occurs where the denominator is zero. $x-4=0 \implies x=4$.", "rational_check"
    )
    
def interactive_trigonometry_widget():
    st.subheader("SOH CAH TOA Calculator")
    with st.container(border=True):
        side1 = st.number_input("Opposite side", min_value=0.1, value=3.0)
        side2 = st.number_input("Adjacent side", min_value=0.1, value=4.0)
        hyp = math.sqrt(side1**2 + side2**2)
        angle_rad = math.asin(side1/hyp)
        angle_deg = math.degrees(angle_rad)
        st.success(f"**Results for Angle A:**")
        st.latex(f"\\sin(A) = \\frac{{Opp}}{{Hyp}} = \\frac{{{side1}}}{{{hyp:.2f}}} \\approx {math.sin(angle_rad):.2f}")
        st.latex(f"\\cos(A) = \\frac{{Adj}}{{Hyp}} = \\frac{{{side2}}}{{{hyp:.2f}}} \\approx {math.cos(angle_rad):.2f}")
        st.latex(f"\\tan(A) = \\frac{{Opp}}{{Adj}} = \\frac{{{side1}}}{{{side2}}} \\approx {math.tan(angle_rad):.2f}")

def interactive_vectors_widget():
    st.subheader("2D Vector Magnitude Calculator")
    with st.container(border=True):
        c1, c2 = st.columns(2)
        x = c1.number_input("x-component", value=3.0); y = c2.number_input("y-component", value=4.0)
        mag = math.sqrt(x**2 + y**2)
        st.success(f"**Magnitude:** The magnitude of $\\binom{{{x}}}{{{y}}}$ is **{mag:.2f}**.")
    
def interactive_statistics_widget():
    st.subheader("Mean, Median, Mode Calculator")
    with st.container(border=True):
        data_str = st.text_input("Enter numbers separated by commas", "5, 10, 15, 10, 25")
        try:
            data = [float(x.strip()) for x in data_str.split(',')]
            df = pd.Series(data)
            c1, c2, c3 = st.columns(3)
            c1.metric("Mean (Average)", f"{df.mean():.2f}")
            c2.metric("Median (Middle)", f"{df.median():.2f}")
            c3.metric("Mode (Most Frequent)", f"{df.mode().iloc[0] if not df.mode().empty else 'N/A'}")
        except:
            st.warning("Please enter a valid list of numbers.")

def interactive_coord_geometry_widget():
    st.subheader("Coordinate Geometry Calculator")
    with st.container(border=True):
        c1, c2 = st.columns(2)
        x1 = c1.number_input("x1", value=1.0); y1 = c2.number_input("y1", value=2.0)
        x2 = c1.number_input("x2", value=4.0); y2 = c2.number_input("y2", value=6.0)
        dist = math.sqrt((x2-x1)**2 + (y2-y1)**2)
        mid_x, mid_y = (x1+x2)/2, (y1+y2)/2
        st.success(f"**Distance:** {dist:.2f}")
        st.success(f"**Midpoint:** ({mid_x:.2f}, {mid_y:.2f})")

def interactive_calculus_widget():
    st.subheader("Simple Power Rule Differentiator")
    with st.container(border=True):
        c1, c2 = st.columns(2)
        a = c1.number_input("Coefficient (a)", value=4.0); n = c2.number_input("Power (n)", value=3.0)
        st.latex(f"\\frac{{d}}{{dx}}({a}x^{{{n}}}) = ({a*n})x^{{{n-1}}}")

def interactive_number_bases_widget():
    st.subheader("Number Base Converter (to Base 10)")
    with st.container(border=True):
        c1, c2 = st.columns(2)
        num_str = c1.text_input("Number", "1011")
        base = c2.number_input("From Base", min_value=2, max_value=16, value=2)
        try:
            result = int(num_str, base)
            st.success(f"**Result:** ${num_str}_{{{base}}}$ is **{result}** in Base 10.")
        except ValueError:
            st.error("Invalid digit for the specified base.")
            
def interactive_modulo_widget():
    st.subheader("Clock Arithmetic (Modulo) Calculator")
    with st.container(border=True):
        c1, c2 = st.columns(2)
        start = c1.number_input("Start Time", min_value=1, max_value=12, value=3)
        hours = c2.number_input("Hours Passed", min_value=0, value=15)
        end_time = (start + hours - 1) % 12 + 1
        st.success(f"**Result:** {hours} hours after {start} o'clock, it will be **{end_time} o'clock**.")

def display_learning_resources(topic_options):
    st.header("📚 Learning Resources & Interactive Lab")

    # --- START: New Teacher's Corner "Smart List" ---
    st.subheader("⭐ Teacher's Corner: Practice & Assignments")
    all_practice_qs = get_active_practice_questions()
    
    if not all_practice_qs:
        st.info("There are no active practice questions or assignments from your teacher at the moment.")
    else:
        displayed_pools = set()

        for q in all_practice_qs:
            pool_name = q.get('assignment_pool_name')

            if pool_name:
                if pool_name in displayed_pools:
                    continue 

                with st.container(border=True):
                    st.markdown(f"#### {pool_name}")
                    
                    with st.spinner("Fetching your unique question..."):
                        assigned_q_id = get_or_assign_student_question(st.session_state.username, pool_name)
                        assigned_q_data = next((item for item in all_practice_qs if item['id'] == assigned_q_id), None)
                    
                    if assigned_q_data:
                        st.markdown(assigned_q_data['question_text'], unsafe_allow_html=True)
                        # --- START: ADD THIS NEW CODE BLOCK ---
                        # Check for and display the student's grade
                        my_grade = get_student_grade(st.session_state.username, pool_name)
                        if my_grade:
                            with st.container(border=True):
                                st.subheader("📝 Your Grade & Feedback")
                                grade_display = my_grade.get('grade') or "Not yet graded"
                                feedback_display = my_grade.get('feedback') or "No feedback provided."
        
                                st.metric("Grade", grade_display)
        
                                st.markdown("**Teacher's Feedback:**")
                                st.info(feedback_display)
        
                                if my_grade.get('graded_at'):
                                    st.caption(f"Graded on: {my_grade['graded_at'].strftime('%b %d, %Y')}")
                        # --- END: ADD THIS NEW CODE BLOCK ---
                        deadline = assigned_q_data.get('unhide_answer_at')
                        created_time = assigned_q_data.get('created_at')
                        if not deadline and created_time:
                            deadline = created_time + timedelta(hours=48)
                        
                        # --- START: THIS IS THE CORRECTED AND REPLACED CODE BLOCK ---
                        # This logic now handles both the deadline and the new 'uploads_enabled' switch.
                        
                        # First, check if the deadline has passed. We only show the upload logic if it hasn't.
                        if not deadline or datetime.now(deadline.tzinfo) < deadline:
                            
                            st.markdown("---")
                            st.subheader("Submit Your Work")
                            
                            # Second, check the 'uploads_enabled' flag before showing the button.
                            # The .get() method safely defaults to True if the flag isn't set in the database yet.
                            if assigned_q_data.get('uploads_enabled', True): 
                                existing_submission = get_student_submission(st.session_state.username, pool_name)
                                
                                if existing_submission:
                                    st.success("✅ Your work has been submitted successfully.")
                                    st.info("You can upload a new file to replace your previous submission.")

                                uploaded_file = st.file_uploader(
                                    "Upload an image of your completed work (JPG, PNG)", 
                                    type=['png', 'jpg', 'jpeg'],
                                    key=f"upload_{pool_name}"
                                )
                                if uploaded_file is not None:
                                    success, message = upload_assignment_file(st.session_state.username, pool_name, uploaded_file)
                                    if success:
                                        st.success(message)
                                        st.rerun()
                                    else:
                                        st.error(message)
                            else:
                                # This message will now show if you have disabled uploads.
                                st.warning("Submissions are currently closed for this assignment by the teacher.")
                        
                        else: # This 'else' belongs to the deadline check
                            with st.expander("Show Answer and Explanation"):
                                st.success("**Answer:**")
                                st.markdown(assigned_q_data['answer_text'], unsafe_allow_html=True)
                                if assigned_q_data['explanation_text']:
                                    st.info("**Explanation:**")
                                    st.markdown(assigned_q_data['explanation_text'], unsafe_allow_html=True)

                        # --- END: REPLACEMENT CODE BLOCK ---
                                
                    else:
                        st.error("Could not load your assigned question.")
                displayed_pools.add(pool_name)

            else: # For general and time-released questions without a pool name
                with st.container(border=True):
                    st.markdown(f"**{q['topic']}**")
                    st.markdown(q['question_text'], unsafe_allow_html=True)
                    deadline = q.get('unhide_answer_at')
                    created_time = q.get('created_at')
                    if not deadline and created_time:
                        deadline = created_time + timedelta(hours=48)
                    if deadline and datetime.now(deadline.tzinfo) < deadline:
                        st.warning(f"The answer and explanation will be revealed after: **{deadline.strftime('%A, %b %d at %I:%M %p')}**")
                    else:
                        with st.expander("Show Answer and Explanation"):
                            st.success("**Answer:**")
                            st.markdown(q['answer_text'], unsafe_allow_html=True)
                            if q['explanation_text']:
                                st.info("**Explanation:**")
                                st.markdown(q['explanation_text'], unsafe_allow_html=True)

    # (The rest of your function for interactive widgets remains unchanged)
    st.markdown("<hr class='styled-hr'>", unsafe_allow_html=True)
    st.write("Select a topic to view notes, formulas, and interactive examples.")
    selectable_topics = [t for t in topic_options if t != "Advanced Combo"]
    selected_topic = st.selectbox("Choose a topic to explore:", selectable_topics)
    st.markdown("---")
    topic_widgets = {
        "Sets": interactive_venn_diagram_calculator,"Percentages": interactive_percentage_calculator,
        "Shapes (Geometry)": interactive_pythagoras_calculator, "Algebra Basics": interactive_quadratic_calculator,
        "Linear Algebra": interactive_matrix_determinant_calculator, "Logarithms": interactive_logarithm_converter,
        "Trigonometry": interactive_trigonometry_widget, "Vectors": interactive_vectors_widget,
        "Statistics": interactive_statistics_widget, "Coordinate Geometry": interactive_coord_geometry_widget,
        "Introduction to Calculus": interactive_calculus_widget, "Number Bases": interactive_number_bases_widget,
        "Modulo Arithmetic": interactive_modulo_widget, "Relations and Functions": interactive_functions_widget,
        "Sequence and Series": interactive_sequence_series_widget, "Indices": interactive_indices_widget,
        "Fractions": interactive_fraction_widget, "Surds": interactive_surds_widget,
        "Binary Operations": interactive_binary_ops_widget, "Word Problems": interactive_word_problems_widget,
        "Probability": interactive_probability_widget, "Binomial Theorem": interactive_binomial_widget,
        "Polynomial Functions": interactive_polynomial_widget, "Rational Functions": interactive_rational_functions_widget,
    }
    if selected_topic:
        st.subheader(selected_topic)
        content = get_learning_content(selected_topic)
        st.markdown(content, unsafe_allow_html=True)
        if selected_topic in topic_widgets:
            st.markdown("<hr>", unsafe_allow_html=True)
            topic_widgets[selected_topic]()
def display_profile_page():
    st.header("👤 Your Profile")

    # The tabs should be in this logical order: Shop then Inventory
    tab1, tab2, tab3, tab4 = st.tabs(["📝 My Profile", "🏆 My Achievements", "🛍️ Shop", "🎒 Inventory"])

    with tab1:
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

        if profile.get('unlocked_flair', False):
            st.markdown("<hr class='styled-hr'>", unsafe_allow_html=True)
            with st.form("flair_form"):
                st.subheader("✨ Set Your User Flair")
                current_flair = profile.get('user_flair', '')
                new_flair = st.text_input("Your Flair (max 25 characters)", value=current_flair, max_chars=25)
                if st.form_submit_button("Set Flair", type="primary"):
                    set_user_flair(st.session_state.username, new_flair)
                    st.rerun()

        st.markdown("<hr class='styled-hr'>", unsafe_allow_html=True)
        st.subheader("🎨 Customize Your Look")
        unlocked = profile.get('unlocked_cosmetics', []) or []
        
        with st.container(border=True):
            st.markdown("#### Active Border")
            unlocked_borders = ['default'] + [item for item in unlocked if 'border' in item]
            current_border = profile.get('active_border', 'default')
            
            if current_border not in unlocked_borders: unlocked_borders.append(current_border)

            border_options_map = {item_id: details['name'] for item_id, details in COSMETIC_ITEMS['Borders'].items()}
            border_options_map['default'] = 'Default'

            new_border = st.radio(
                "Select a border to display:", 
                options=unlocked_borders,
                format_func=lambda x: border_options_map.get(x, x.replace('_', ' ').title()),
                index=unlocked_borders.index(current_border),
                key="equip_border",
                horizontal=True
            )
            if new_border != current_border:
                if set_active_cosmetic(st.session_state.username, new_border, 'border'):
                    st.rerun()

        with st.container(border=True):
            st.markdown("#### Active Name Effect")
            unlocked_effects = ['default'] + [item for item in unlocked if 'effect' in item]
            current_effect = profile.get('active_name_effect', 'default')

            if current_effect not in unlocked_effects: unlocked_effects.append(current_effect)
            
            effect_options_map = {item_id: details['name'] for item_id, details in COSMETIC_ITEMS['Name Effects'].items()}
            effect_options_map['default'] = 'Default'

            new_effect = st.radio(
                "Select a name effect to display:",
                options=unlocked_effects,
                format_func=lambda x: effect_options_map.get(x, x.replace('_', ' ').title()),
                index=unlocked_effects.index(current_effect),
                key="equip_effect",
                horizontal=True
            )
            if new_effect != current_effect:
                if set_active_cosmetic(st.session_state.username, new_effect, 'name_effect'):
                    st.rerun()
        
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

    with tab2:
        st.subheader("🏆 My Achievements")
        achievements = get_user_achievements(st.session_state.username)
        if not achievements:
            st.info("Your trophy case is empty for now. Keep playing to earn badges!")
        else:
            cols = st.columns(4)
            for i, achievement in enumerate(achievements):
                col = cols[i % 4]
                with col:
                    with st.container(border=True):
                        st.markdown(f"<div style='font-size: 3rem; text-align: center;'>{achievement['badge_icon']}</div>", unsafe_allow_html=True)
                        st.markdown(f"<div style='font-size: 1rem; text-align: center; font-weight: bold;'>{achievement['achievement_name']}</div>", unsafe_allow_html=True)
                        st.markdown(f"<div style='font-size: 0.8rem; text-align: center; color: grey;'>Unlocked: {achievement['unlocked_at'].strftime('%b %d, %Y')}</div>", unsafe_allow_html=True)

    with tab3: # --- SHOP TAB ---
        st.subheader("🛍️ Item Shop")
        coin_balance = get_coin_balance(st.session_state.username)
        profile = get_user_profile(st.session_state.username) or {}
        unlocked_cosmetics = profile.get('unlocked_cosmetics', []) or []
        st.info(f"**Your Balance: 🪙 {coin_balance} Coins**")

        if 'gifting_item_id' in st.session_state:
            item_id = st.session_state.gifting_item_id
            item_details = st.session_state.gifting_item_details
            
            with st.form("gift_form"):
                st.markdown(f"### 🎁 Gifting: {item_details['name']}")
                st.write(f"This will cost you **{item_details['cost']} coins**.")
                recipient = st.text_input("Enter your friend's exact username:")
                
                if st.form_submit_button(f"Send Gift to {recipient or '...'} ", type="primary"):
                    if recipient:
                        success, message = purchase_gift_for_user(st.session_state.username, recipient, item_id, item_details)
                        if success:
                            st.success(message); st.balloons()
                        else:
                            st.error(message)
                        time.sleep(2)
                        del st.session_state.gifting_item_id
                        del st.session_state.gifting_item_details
                        st.rerun()
                    else:
                        st.warning("Please enter a recipient's username.")

            if st.button("Cancel Gift"):
                del st.session_state.gifting_item_id
                del st.session_state.gifting_item_details
                st.rerun()
        
        else: # Main Shop Display
            for category, items in COSMETIC_ITEMS.items():
                st.markdown(f"<hr><h4>{category}</h4>", unsafe_allow_html=True)
                num_columns = len(items) if len(items) <= 3 else 3
                cols = st.columns(num_columns)
                
                for i, (item_id, item_details) in enumerate(items.items()):
                    col = cols[i % num_columns]
                    with col:
                        with st.container(border=True):
                            st.markdown(f"**{item_details['name']}**")
                            st.caption(f"Cost: {item_details['cost']} Coins")
                            is_owned = item_id in unlocked_cosmetics

                            if is_owned:
                                st.success("✅ Purchased")
                            else:
                                c1, c2 = st.columns(2)
                                with c1:
                                    if st.button("Buy", key=f"buy_{item_id}", use_container_width=True, disabled=(coin_balance < item_details['cost'])):
                                        update_sql = None
                                        if 'db_column' in item_details:
                                            col_name = item_details['db_column']
                                            if 'expires_at' in col_name:
                                                update_sql = text(f"UPDATE user_profiles SET {col_name} = NOW() + INTERVAL '1 hour' WHERE username = :username")
                                            else:
                                                update_sql = text(f"UPDATE user_profiles SET {col_name} = COALESCE({col_name}, 0) + 1 WHERE username = :username")
                                        else:
                                            update_sql = text(f"UPDATE user_profiles SET unlocked_cosmetics = array_append(unlocked_cosmetics, '{item_id}') WHERE username = :username")
                                        
                                        if purchase_item(st.session_state.username, item_details['name'], item_details['cost'], update_sql):
                                            st.rerun()
                                with c2:
                                    if st.button("Gift", key=f"gift_{item_id}", use_container_width=True, disabled=(coin_balance < item_details['cost'])):
                                        st.session_state.gifting_item_id = item_id
                                        st.session_state.gifting_item_details = item_details
                                        st.rerun()

            st.markdown("<hr><h4>Special Unlocks</h4>", unsafe_allow_html=True)
            with st.container(border=True):
                st.markdown("**✨ User Flair Unlock**")
                st.caption("Cost: 750 Coins")
                if profile.get('unlocked_flair', False):
                    st.success("✅ Purchased")
                else:
                    c1, c2 = st.columns(2)
                    with c1:
                        if st.button("Buy", key="buy_user_flair_unlock", use_container_width=True, disabled=(coin_balance < 750)):
                            update_sql = text("UPDATE user_profiles SET unlocked_flair = TRUE WHERE username = :username")
                            if purchase_item(st.session_state.username, "User Flair Unlock", 750, update_sql):
                                st.rerun()
                    with c2:
                        # You can add a "Gift Flair Unlock" button here in the future if you wish
                        pass

            st.markdown("<hr class='styled-hr'>", unsafe_allow_html=True)
            st.subheader("💸 Transfer Coins to a Friend")
            with st.form("gift_coins_form", clear_on_submit=True):
                recipient = st.text_input("Recipient's Username")
                amount = st.number_input("Amount of Coins to Transfer", min_value=1, max_value=coin_balance, value=10, step=5)
                if st.form_submit_button("Send Coins", type="primary", use_container_width=True):
                    success, message = transfer_coins(st.session_state.username, recipient, amount)
                    if success:
                        st.success(message)
                    else:
                        st.error(message)

    with tab4: # --- INVENTORY TAB ---
        st.subheader("🎒 My Inventory")
        st.info("Here you can open any Mystery Boxes you have purchased.")
        profile = get_user_profile(st.session_state.username) or {}
        box_count = profile.get('mystery_boxes', 0)
        st.metric("Mystery Boxes Owned", f"🎁 {box_count}")

        if st.button("Open a Mystery Box", disabled=(box_count <= 0), type="primary", use_container_width=True):
            success, message = open_mystery_box(st.session_state.username)
            if success:
                st.balloons()
                st.success(message)
                time.sleep(2)
                st.rerun()
            else:
                st.error(message)
def display_admin_panel(topic_options):
    st.title("⚙️ Admin Panel: Mission Control")

    tab_names = [
        "📊 User Management", 
        "📝 Submissions",
        "🎯 Daily Challenges", 
        "🎮 Game Management", 
        "✍️ Practice Questions",
        "📣 Announcements",
        "📈 Analytics",
        "📝 Content Management"  # The new tab
    ]
    tabs = st.tabs(tab_names)

    # --- TAB 1: USER MANAGEMENT (WITH DETAILED STUDENT REPORTS) ---
    # --- START: REVISED CODE for Admin Panel Tab 0 ("User Management") ---
# Reason for change: To fix a TypeError when displaying the overview table and to incorporate the
# fixes for the user selection dropdowns, all within this single tab.

    with tabs[0]:
        st.subheader("User Management")
        
        st.markdown("#### Comprehensive Student Overview")
        st.info("This table provides a high-level summary of all registered users. Click on column headers to sort.")
        
        all_users_data = get_all_users_summary()
        if all_users_data:
            df = pd.DataFrame(all_users_data)
            
            # This corrected line fixes the TypeError
            df['average_accuracy'] = pd.to_numeric(df['average_accuracy'], errors='coerce').fillna(0).round(1)
            
            df['last_seen'] = pd.to_datetime(df['last_seen']).dt.strftime('%Y-%m-%d %H:%M').fillna('Never')
            
            st.dataframe(df.rename(columns={
                'username': 'Username',
                'is_active': 'Is Active',
                'full_name': 'Full Name',
                'school': 'School',
                'coins': 'Coins 🪙',
                'quizzes_taken': 'Quizzes Taken',
                'average_accuracy': 'Avg. Accuracy %',
                'last_seen': 'Last Seen'
            }), use_container_width=True)
        else:
            st.warning("No users found to display in the overview.")

        st.markdown("<hr class='styled-hr'>", unsafe_allow_html=True)

        user_list = [user['username'] for user in all_users_data]
        
        st.subheader("🔍 Detailed Student Report")
        if not user_list:
            st.warning("No users have registered yet to generate a report.")
        else:
            # Fix for report dropdown state
            if 'admin_report_user' not in st.session_state or st.session_state.admin_report_user not in user_list:
                st.session_state.admin_report_user = user_list[0] if user_list else None
            try:
                report_index = user_list.index(st.session_state.admin_report_user)
            except (ValueError, TypeError):
                report_index = 0
            selected_user_report = st.selectbox(
                "Select a student to view their detailed report",
                user_list,
                index=report_index
            )
            if selected_user_report != st.session_state.admin_report_user:
                st.session_state.admin_report_user = selected_user_report
                st.rerun()

            if selected_user_report:
                with st.container(border=True):
                    profile = get_user_profile(selected_user_report)
                    st.markdown(f"#### Report for: `{selected_user_report}`")
                    if profile:
                        st.write(f"**Name:** {profile.get('full_name', 'N/A')} | **School:** {profile.get('school', 'N/A')}")
                    
                    st.markdown("**Topic Performance**")
                    topic_perf_df = get_topic_performance(selected_user_report)
                    if not topic_perf_df.empty:
                        fig = px.bar(topic_perf_df, y='Accuracy', labels={'Accuracy': 'Accuracy (%)'})
                        st.plotly_chart(fig, use_container_width=True)
                    else:
                        st.info(f"{selected_user_report} has not completed any quizzes yet.")

                    with st.expander("View Full Quiz History"):
                        history = get_user_quiz_history(selected_user_report)
                        if history:
                            df_history = pd.DataFrame(history)
                            df_history['timestamp'] = pd.to_datetime(df_history['timestamp']).dt.strftime('%Y-%m-%d %H:%M')
                            st.dataframe(df_history.rename(columns={'topic':'Topic', 'score':'Score', 'questions_answered':'Total', 'timestamp':'Date'}), use_container_width=True)
                        else:
                            st.info("No quiz history found.")
                    # --- START: NEW COIN TRANSACTION VIEWER ---
                    with st.expander("View Coin Transaction History"):
                        transactions = get_user_transactions(selected_user_report)
                        if transactions:
                            df_trans = pd.DataFrame(transactions)
                            df_trans['timestamp'] = pd.to_datetime(df_trans['timestamp']).dt.strftime('%Y-%m-%d %H:%M')
                            st.dataframe(df_trans.rename(columns={'timestamp': 'Date', 'amount': 'Amount 🪙', 'description': 'Description'}), use_container_width=True)
                        else:
                            st.info("No coin transactions found for this user.")
                    # --- END: NEW COIN TRANSACTION VIEWER ---
        
        st.markdown("<hr class='styled-hr'>", unsafe_allow_html=True)
        st.subheader("🛠️ Administrative Actions")

        if not user_list:
            st.warning("No users to manage yet.")
        else:
            # Fix for action dropdown state
            if 'admin_selected_user' not in st.session_state or st.session_state.admin_selected_user not in user_list:
                st.session_state.admin_selected_user = user_list[0] if user_list else None
            try:
                default_index = user_list.index(st.session_state.admin_selected_user)
            except (ValueError, TypeError):
                default_index = 0
            selected_user_action = st.selectbox(
                "Select a user to perform an action on",
                user_list,
                index=default_index
            )
            st.session_state.admin_selected_user = selected_user_action

            if selected_user_action:
                st.markdown(f"#### Actions for: `{selected_user_action}`")
                with st.expander("✏️ Edit User Profile"):
                    profile = get_user_profile(selected_user_action) or {}
                    with st.form(key=f"edit_profile_{selected_user_action}"):
                        full_name = st.text_input("Full Name", value=profile.get('full_name', ''), key=f"name_{selected_user_action}")
                        school = st.text_input("School", value=profile.get('school', ''), key=f"school_{selected_user_action}")
                        if st.form_submit_button("Save Profile Changes"):
                            update_user_profile(selected_user_action, full_name, school, profile.get('age', 18), profile.get('bio', ''))
                            st.success(f"Profile for {selected_user_action} updated!")
                            st.rerun()
                with st.expander("🔑 Reset Password"):
                    with st.form(key=f"reset_pw_{selected_user_action}"):
                        st.warning(f"This will set a new temporary password for {selected_user_action}.")
                        new_pw = st.text_input("New Temporary Password", type="password")
                        if st.form_submit_button("Reset Password", type="primary"):
                            if new_pw:
                                reset_user_password_admin(selected_user_action, new_pw)
                                st.success(f"Password for {selected_user_action} has been reset.")
                            else:
                                st.error("Password cannot be blank.")
                with st.expander("⚖️ Suspend / Unsuspend Account"):
                    user_data_query = text("SELECT is_active FROM public.users WHERE username = :username")
                    with engine.connect() as conn:
                        is_active = conn.execute(user_data_query, {"username": selected_user_action}).scalar_one_or_none()
                    if is_active:
                        st.success(f"Account status for {selected_user_action} is currently **Active**.")
                        if st.button("Suspend Account", key=f"suspend_{selected_user_action}", type="primary"):
                            toggle_user_suspension(selected_user_action)
                            st.rerun()
                    else:
                        st.warning(f"Account status for {selected_user_action} is currently **Suspended**.")
                        if st.button("Unsuspend Account", key=f"unsuspend_{selected_user_action}"):
                            toggle_user_suspension(selected_user_action)
                            st.rerun()
                with st.expander("🏆 Award a Special Badge"):
                     with st.form("award_achievement_form_single", clear_on_submit=True):
                        st.markdown(f"Awarding badge to **{selected_user_action}**")
                        special_badge_name = st.text_input("Enter Special Badge Name", placeholder="e.g., Community Helper")
                        badge_icon = st.text_input("Badge Icon (e.g., 🌟, 💡, 🏅)", value="🏅")
                        if st.form_submit_button("Award Badge"):
                            if special_badge_name:
                                success = award_achievement_to_user(selected_user_action, special_badge_name, badge_icon)
                                if success: 
                                    st.success(f"Awarded '{special_badge_name}' to {selected_user_action}!")
                                else: 
                                    st.warning(f"{selected_user_action} already has that badge.")
                            else:
                                st.error("Please enter a name for the special badge.")
                with st.expander("🪙 Grant Coins"):
                    with st.form(key=f"grant_coins_{selected_user_action}"):
                        st.write(f"Granting coins to **{selected_user_action}**")
                        coins_to_grant = st.number_input("Amount of Coins to Grant", min_value=1, value=100)
                        reason = st.text_input("Reason for Grant (for transaction log)", "Admin grant")
                        if st.form_submit_button("Award Coins", type="primary"):
                            if update_coin_balance(selected_user_action, coins_to_grant, reason):
                                st.success(f"Successfully granted {coins_to_grant} coins to {selected_user_action}.")
                            else:
                                st.error("Failed to grant coins.")
                if selected_user_action != st.session_state.username:
                    with st.expander("❌ Delete User"):
                        st.error(f"This is permanent and cannot be undone.")
                        if st.button(f"Permanently Delete {selected_user_action}", type="primary"):
                            delete_user_and_all_data(selected_user_action)
                            st.success(f"User {selected_user_action} has been deleted.")
                            st.rerun()
# --- END: REVISED CODE for Admin Panel Tab 0 ("User Management") ---

 # This is the complete code for your "Submissions" tab with the grading UI

    with tabs[1]:
        st.subheader("View and Grade Assignment Submissions")
        st.info("Select an assignment to view submissions, enter grades, and provide feedback.")

        all_practice_q = get_all_practice_questions()
        pool_names = sorted(list(set(q['assignment_pool_name'] for q in all_practice_q if q['assignment_pool_name'])))
    
        if not pool_names:
            st.warning("No assignment pools have been created yet.")
        else:
            selected_pool = st.selectbox("Select an assignment pool to view and grade:", pool_names)
        
            if selected_pool:
                st.markdown(f"#### Grading for: **{selected_pool}**")
            
                # Fetch all submissions and all existing grades for the selected pool
                submissions = get_all_submissions_for_pool(selected_pool)
                grades = get_grades_for_pool(selected_pool)
            
                if not submissions:
                    st.info("No students have submitted work for this assignment yet.")
                else:
                    for sub in submissions:
                        username = sub['username']
                        # Get the existing grade for this user, or an empty dict if not yet graded
                        existing_grade_data = grades.get(username, {})

                        with st.container(border=True):
                            col1, col2 = st.columns([1, 1])
                        
                            with col1:
                                st.markdown(f"**Student:** `{username}`")
                                st.caption(f"Submitted: {sub['submitted_at'].strftime('%Y-%m-%d %I:%M %p')}")
                                if sub['view_url']:
                                    st.link_button("View Submission ↗️", sub['view_url'], use_container_width=True)
                                else:
                                    st.error("Could not load file.")
                        
                            with col2:
                                # Create a unique form for each student's grading
                                with st.form(key=f"grade_form_{username}_{selected_pool}"):
                                    st.markdown("**Enter Grade & Feedback**")
                                
                                    # Pre-fill the form with existing data if it exists
                                    grade = st.text_input(
                                        "Grade (e.g., 18/20)", 
                                        value=existing_grade_data.get('grade', ''), 
                                        key=f"grade_{username}"
                                    )
                                    feedback = st.text_area(
                                        "Feedback for Student", 
                                        value=existing_grade_data.get('feedback', ''), 
                                        key=f"feedback_{username}"
                                    )
                                
                                    if st.form_submit_button("Save Grade", type="primary", use_container_width=True):
                                        save_grade(username, selected_pool, grade, feedback)
                                        st.success(f"Grade for {username} saved!")
                                        st.rerun()
    # --- TAB 2: DAILY CHALLENGES ---
    # --- THIS IS THE NEW CODE FOR THE SECOND ADMIN TAB ---
    with tabs[2]:
        st.subheader("Manage Daily Challenges")
        st.info("Here you can control the pool of challenges that are randomly assigned to students each day.")

        # Create a definitive list of topics for the dropdown
        all_quiz_topics = sorted([
            "Sets", "Percentages", "Fractions", "Indices", "Surds", "Binary Operations",
            "Relations and Functions", "Sequence and Series", "Word Problems", "Shapes (Geometry)",
            "Algebra Basics", "Linear Algebra", "Logarithms", "Probability", "Binomial Theorem",
            "Polynomial Functions", "Rational Functions", "Trigonometry", "Vectors", "Statistics",
            "Coordinate Geometry", "Introduction to Calculus", "Number Bases", "Modulo Arithmetic",
            "Advanced Combo"
        ])
        challenge_topic_options = ["Any"] + all_quiz_topics

        st.markdown("---")
        st.subheader("Add New Challenge")
        with st.form("new_challenge_form", clear_on_submit=True):
            new_desc = st.text_input("Challenge Description", placeholder="e.g., Correctly answer 5 Algebra questions.")
            # Replaced st.text_input with st.selectbox
            new_topic = st.selectbox("Topic", options=challenge_topic_options)
            new_target = st.number_input("Target Count", min_value=1, value=3)
            if st.form_submit_button("Add Challenge", type="primary"):
                if new_desc and new_topic and new_target:
                    add_new_challenge(new_desc, new_topic, new_target)
                    st.success("New challenge added!")
                    st.rerun()
                else:
                    st.error("All fields are required.")
        
        st.markdown("<hr class='styled-hr'>", unsafe_allow_html=True)
        st.subheader("Existing Challenges")
        all_challenges = get_all_challenges_admin()
        if not all_challenges:
            st.warning("No challenges found in the database.")
        else:
            for challenge in all_challenges:
                with st.container(border=True):
                    st.markdown(f"**ID: {challenge['id']}** | **Topic:** `{challenge['topic']}`")
                    st.markdown(challenge['description'])
                    st.markdown(f"**Target:** {challenge['target_count']}")
                    with st.expander("Edit this challenge"):
                        with st.form(key=f"edit_form_{challenge['id']}"):
                            edit_desc = st.text_input("Description", value=challenge['description'], key=f"desc_{challenge['id']}")
                            
                            # Replaced st.text_input with st.selectbox for editing
                            try:
                                current_topic_index = challenge_topic_options.index(challenge['topic'])
                            except ValueError:
                                current_topic_index = 0 # Default to 'Any' if not found
                            edit_topic = st.selectbox("Topic", options=challenge_topic_options, index=current_topic_index, key=f"topic_{challenge['id']}")
                            
                            edit_target = st.number_input("Target", value=challenge['target_count'], min_value=1, key=f"target_{challenge['id']}")
                            c1, c2 = st.columns([3, 1])
                            if c1.form_submit_button("Save Changes"):
                                update_challenge(challenge['id'], edit_desc, edit_topic, edit_target)
                                st.success(f"Challenge {challenge['id']} updated!")
                                st.rerun()
                            if c2.form_submit_button("Delete", type="secondary"):
                                delete_challenge(challenge['id'])
                                st.success(f"Challenge {challenge['id']} deleted!")
                                st.rerun()
    # --- TAB 3: GAME MANAGEMENT ---
    with tabs[3]:
        st.subheader("Manage Active Duels")
        st.info("This panel shows all duels currently in progress. If a game appears to be stuck, you can use the 'Force End Duel' button to resolve it.")
        active_duels = get_all_active_duels_admin()
        if not active_duels:
            st.success("✅ No active duels at the moment.")
        else:
            st.warning(f"There are currently {len(active_duels)} duel(s) in progress.")
            for duel in active_duels:
                with st.container(border=True):
                    p1 = duel['player1_username']; p2 = duel['player2_username']
                    score1 = duel['player1_score']; score2 = duel['player2_score']
                    st.markdown(f"**Duel ID:** `{duel['id']}` | **Topic:** `{duel['topic']}`")
                    st.markdown(f"**Players:** `{p1}` (Score: {score1}) vs. `{p2}` (Score: {score2})")
                    st.caption(f"Last Action: {duel['last_action_at'].strftime('%Y-%m-%d %H:%M:%S')}")
                    if st.button("🔴 Force End Duel", key=f"end_duel_{duel['id']}", use_container_width=True):
                        force_end_duel_admin(duel['id'])
                        st.success(f"Duel ID {duel['id']} has been ended.")
                        st.rerun()
    with tabs[4]:
        st.subheader("Manage Practice Questions / Assignments")
        st.info("You can add questions one-by-one, or use the Bulk Import feature for large assignments.")
        st.markdown("---")

        with st.expander("🚀 Bulk Import Questions from File"):
            st.warning("Ensure your CSV file has the correct headers: `topic`, `question_text`, `answer_text`, and optionally `explanation_text`, `assignment_pool_name`, `unhide_answer_at`")
            uploaded_file = st.file_uploader("Choose a CSV file", type="csv")
        
            if uploaded_file is not None:
                if st.button("Import Questions from CSV", type="primary"):
                    bulk_import_questions(uploaded_file)
    
        st.subheader("Add a Single Question/Assignment")
        with st.expander("⚙️ Set Defaults for this Session"):
            st.caption("Set a default topic and pool name here to pre-fill the form below.")
            st.text_input("Default Topic/Title", key="pq_default_topic")
            st.text_input("Default Assignment Pool Name", key="pq_default_pool")

        st.checkbox("Set a specific answer reveal time (optional)", key="add_pq_set_deadline")
        with st.form("new_practice_q_form", clear_on_submit=True):
            pq_topic = st.text_input("Topic or Title", placeholder="e.g., Week 5 Assignment on Surds", value=st.session_state.get("pq_default_topic", ""))
            pq_question = st.text_area("Question Text (Supports Markdown & LaTeX)", height=200)
            pq_answer = st.text_area("Answer Text", height=100)
            pq_explanation = st.text_area("Detailed Explanation (Optional)", height=200)
            st.markdown("##### **Optional Assignment Settings**")
            pq_pool_name = st.text_input("Assignment Pool Name (Optional)", placeholder="e.g., Vacation Task 1", help="Group questions by giving them the same pool name.", value=st.session_state.get("pq_default_pool", ""))
        
            pq_unhide_at = None
            if st.session_state.add_pq_set_deadline:
                c1, c2 = st.columns(2)
                picked_date = c1.date_input("Reveal Date", key="add_reveal_date")
                picked_time = c2.time_input("Reveal Time", key="add_reveal_time")
                if picked_date and picked_time:
                    pq_unhide_at = datetime.combine(picked_date, picked_time)
        
            if st.form_submit_button("Add Practice Question", type="primary"):
                if pq_topic and pq_question and pq_answer:
                    add_practice_question(pq_topic, pq_question, pq_answer, pq_explanation, pq_pool_name, pq_unhide_at)
                    st.success(f"New question added!")
                    st.session_state.add_pq_set_deadline = False
                    st.rerun()
                else: 
                    st.error("Title, Question, and Answer are required.")
    
        st.markdown("<hr class='styled-hr'>", unsafe_allow_html=True)
        st.subheader("Existing Practice Questions")
    
        all_practice_q = get_all_practice_questions()
        st.markdown("#### Bulk Actions for Assignment Pools")
        pool_names = sorted(list(set(q['assignment_pool_name'] for q in all_practice_q if q['assignment_pool_name'])))
    
        if not pool_names:
            st.info("No assignment pools found. Add a question with a pool name to enable bulk actions.")
        else:
            selected_pool = st.selectbox("Select an assignment pool to manage:", pool_names)
            # --- START: New and improved button layout ---
        st.write("**Manage Question Status:**")
        col1, col2 = st.columns(2)
        if col1.button("✅ Activate All in Pool", key=f"activate_{selected_pool}", use_container_width=True):
            bulk_toggle_question_status(selected_pool, True)
            st.success(f"All questions in '{selected_pool}' have been activated.")
            st.rerun()
        if col2.button("❌ Deactivate All in Pool", key=f"deactivate_{selected_pool}", use_container_width=True):
            bulk_toggle_question_status(selected_pool, False)
            st.warning(f"All questions in '{selected_pool}' have been deactivated.")
            st.rerun()

        st.write("**Manage Submissions:**")
        col3, col4 = st.columns(2)
        if col3.button("📥 Enable Uploads for Pool", key=f"enable_uploads_{selected_pool}", use_container_width=True):
            bulk_toggle_uploads_for_pool(selected_pool, True)
            st.success(f"Uploads for '{selected_pool}' have been enabled.")
            st.rerun()
        if col4.button("🚫 Disable Uploads for Pool", key=f"disable_uploads_{selected_pool}", use_container_width=True):
            bulk_toggle_uploads_for_pool(selected_pool, False)
            st.warning(f"Uploads for '{selected_pool}' have been disabled.")
            st.rerun()
    
        st.write("**Destructive Actions:**")
        if st.button("🗑️ Delete All in Pool", key=f"delete_{selected_pool}", use_container_width=True, type="primary"):
            bulk_delete_questions(selected_pool)
            st.error(f"All questions in '{selected_pool}' have been permanently deleted.")
            st.rerun()
        # --- END: New and improved button layout ---
    
        st.markdown("---")

        if not all_practice_q:
            st.warning("No practice questions have been added yet.")
        else:
            for q in all_practice_q:
                with st.container(border=True):
                    upload_status = "Enabled ✅" if q.get('uploads_enabled', True) else "Disabled ❌"
                    st.markdown(f"**ID:** {q['id']} | **Status:** {'Active' if q['is_active'] else 'Inactive'} | **Uploads:** {upload_status}")
                
                    if q.get('assignment_pool_name'):
                        st.info(f"**Pool Name:** {q['assignment_pool_name']}")
                    st.markdown(f"**Question:**")
                    st.markdown(q['question_text'], unsafe_allow_html=True)
                
                    with st.expander("✏️ Edit this question"):
                        # This is where your code for the edit form goes
                        pass

                    with st.expander("View Answer & Explanation"):
                        st.success(f"**Answer:**")
                        st.markdown(q['answer_text'], unsafe_allow_html=True)
                        st.info(f"**Explanation:**")
                        st.markdown(q.get('explanation_text') or '_No explanation provided._', unsafe_allow_html=True)
                
                    # --- THIS IS THE CORRECT LAYOUT FOR THE BUTTONS ---
                    c1, c2, c3 = st.columns(3)
                
                    if c1.button("Activate/Deactivate", key=f"pq_toggle_{q['id']}", use_container_width=True):
                        toggle_practice_question_status(q['id'])
                        st.rerun()

                    if c3.button("Delete", key=f"pq_delete_{q['id']}", use_container_width=True, type="secondary"):
                        delete_practice_question(q['id'])
                        st.success(f"Question {q['id']} deleted.")
                        st.rerun()
    # --- TAB 5: ANNOUNCEMENTS ---
    with tabs[5]:
        st.subheader("📣 Site-Wide Announcements")
        st.info("Post a message that will appear at the top of every student's dashboard.")
        current_announcement = get_config_value("announcement_text", "")
        with st.form("announcement_form"):
            new_announcement = st.text_area("Announcement Message (Markdown is supported)", value=current_announcement, height=150)
            c1, c2 = st.columns(2)
            if c1.form_submit_button("Post / Update Announcement", type="primary", use_container_width=True):
                set_config_value("announcement_text", new_announcement)
                st.success("Announcement has been posted!")
                st.rerun()
            if c2.form_submit_button("Clear Announcement", use_container_width=True):
                set_config_value("announcement_text", "")
                st.warning("Announcement has been cleared.")
                st.rerun()
    
    # --- TAB 6: ANALYTICS ---
    with tabs[6]:
        st.subheader("📈 App Analytics & Insights")
        kpis = get_admin_kpis()
        c1, c2, c3 = st.columns(3)
        c1.metric("Total Users", kpis.get("total_users", 0))
        c2.metric("Total Quizzes Taken", kpis.get("total_quizzes", 0))
        c3.metric("Total Duels Played", kpis.get("total_duels", 0))
        
        st.markdown("<hr class='styled-hr'>", unsafe_allow_html=True)
        
        st.subheader("Topic Performance Analysis (All Students)")
        topic_perf_data = get_topic_performance_summary()
        if not topic_perf_data:
            st.info("Not enough quiz data yet to analyze topic performance.")
        else:
            df_perf = pd.DataFrame(topic_perf_data)
            df_perf['avg_accuracy'] = pd.to_numeric(df_perf['avg_accuracy'])
            df_perf['avg_accuracy'] = df_perf['avg_accuracy'].round(1)
            
            c1, c2 = st.columns(2)
            with c1:
                st.write("🧠 **Strongest Topics** (Highest Accuracy)")
                st.dataframe(df_perf.head(5).rename(columns={'topic': 'Topic', 'avg_accuracy': 'Accuracy %', 'times_taken': 'Times Taken'}), use_container_width=True)
            with c2:
                st.write("🤔 **Weakest Topics** (Lowest Accuracy)")
                st.dataframe(df_perf.tail(5).sort_values(by='avg_accuracy', ascending=True).rename(columns={'topic': 'Topic', 'avg_accuracy': 'Accuracy %', 'times_taken': 'Times Taken'}), use_container_width=True)

        st.markdown("<hr class='styled-hr'>", unsafe_allow_html=True)
        st.subheader("Activity & Engagement")
        c1, c2 = st.columns(2)
        with c1:
            st.write("📅 **Overall App Activity** (Quizzes per Day)")
            activity_data = get_daily_activity()
            if activity_data:
                df_activity = pd.DataFrame(activity_data)
                fig_activity = px.bar(df_activity, x="date", y="quiz_count", title="Quizzes Taken Per Day")
                st.plotly_chart(fig_activity, use_container_width=True)
            else:
                st.info("No daily activity to display yet.")
        
        with c2:
            st.write("⚔️ **Most Popular Duel Topics**")
            duel_pop_data = get_duel_topic_popularity()
            if duel_pop_data:
                df_duel_pop = pd.DataFrame(duel_pop_data)
                fig_duel_pop = px.pie(df_duel_pop, names="topic", values="duel_count", title="Duel Topic Distribution")
                st.plotly_chart(fig_duel_pop, use_container_width=True)
            else:
                st.info("No duels have been played yet.")

        st.markdown("<hr class='styled-hr'>", unsafe_allow_html=True)
        st.subheader("🏆 Top 10 Most Active Students")
        active_student_data = get_most_active_students()
        if active_student_data:
            df_active = pd.DataFrame(active_student_data)
            st.dataframe(df_active.rename(columns={'username': 'Username', 'quiz_count': 'Total Quizzes Taken'}), use_container_width=True)
        else:
            st.info("No student activity to rank yet.")

    # --- START: NEW CONTENT MANAGEMENT TAB ---
    with tabs[7]:
        st.subheader("📝 Content Management: Learning Resources")
        st.info("Select a topic to view and edit the notes, formulas, and video links that students see on the Learning Resources page.")

        # Get a list of all quiz topics to populate the editor
        all_topics = sorted([t for t in topic_options if t != "Advanced Combo"])
        
        selected_topic_to_edit = st.selectbox("Select a topic to edit:", all_topics, key="content_topic_select")

        if selected_topic_to_edit:
            # Fetch the current content from the database
            current_content = get_learning_content(selected_topic_to_edit)
            
            with st.form(key=f"edit_content_{selected_topic_to_edit}"):
                st.markdown(f"#### Editing Content for: **{selected_topic_to_edit}**")
                
                new_content = st.text_area(
                    "Content (Markdown and LaTeX are supported)",
                    value=current_content,
                    height=500
                )
                
                if st.form_submit_button("Save Changes", type="primary"):
                    update_learning_content(selected_topic_to_edit, new_content)
                    st.success(f"Content for '{selected_topic_to_edit}' has been updated successfully!")
                    # No rerun needed, as st.cache_data.clear() handles the update.

    # --- END: NEW CONTENT MANAGEMENT TAB ---

# Replace your existing show_main_app function with this one.

def show_main_app():
    load_css()
    # --- START: NEW DAILY REWARD LOGIC ---
    # This block runs once per session to check for a daily login reward.
    if 'daily_reward_checked' not in st.session_state:
        reward_message = check_and_grant_daily_reward(st.session_state.username)
        if reward_message:
            st.toast(reward_message, icon="🎁")
            st.balloons()
        st.session_state.daily_reward_checked = True
    # --- END: NEW DAILY REWARD LOGIC ---
    
    if st.session_state.get('challenge_completed_toast', False):
        st.toast("🎉 Daily Challenge Completed! Great job!", icon="🎉")
        del st.session_state.challenge_completed_toast
    if st.session_state.get('achievement_unlocked_toast', False):
        achievement_name = st.session_state.achievement_unlocked_toast
        st.toast(f"🏆 Achievement Unlocked: {achievement_name}!", icon="🏆")
        st.balloons()
        del st.session_state.achievement_unlocked_toast

    last_update = st.session_state.get("last_status_update", 0)
    if time.time() - last_update > 60:
        update_user_status(st.session_state.username, True)
        st.session_state.last_status_update = time.time()
        
    with st.sidebar:
        greeting = get_time_based_greeting()
        profile = get_user_profile(st.session_state.username)
        display_name = profile.get('full_name') if profile and profile.get('full_name') else st.session_state.username
        st.title(f"{greeting}, {display_name}!")
        # --- START: NEW DATE WIDGET ---
        # Get the current date and format it nicely
        today_date = datetime.now().strftime("%A, %B %d, %Y")
        st.caption(f"**{today_date}**")
        # --- END: NEW DATE WIDGET ---
        page_options = [
            "📊 Dashboard", "📝 Quiz", "🏆 Leaderboard", "⚔️ Math Game", "💬 Blackboard", 
            "👤 Profile", "📚 Learning Resources", "❓ Help Center"
        ]
        
        # Check the user's role from the database
        user_role = get_user_role(st.session_state.username)
        if user_role == 'admin':
            page_options.append("⚙️ Admin Panel")
        is_in_duel = st.session_state.get("page") == "duel"
        selected_page = st.radio("Menu", page_options, label_visibility="collapsed", disabled=is_in_duel)
        if is_in_duel:
            st.sidebar.warning("You are in a duel! Finish the game to navigate away.")

        st.write("---")
        if st.button("Logout", type="primary", use_container_width=True):
            st.session_state.logged_in = False
            if 'challenge_completed_toast' in st.session_state: del st.session_state.challenge_completed_toast
            if 'achievement_unlocked_toast' in st.session_state: del st.session_state.achievement_unlocked_toast
            st.rerun()
            
    st.markdown('<div class="main-content">', unsafe_allow_html=True)
    
    if st.session_state.get("page") == "duel":
        display_duel_page()
    else:
        topic_options = [
            "Sets", "Percentages", "Fractions", "Indices", "Surds", 
            "Binary Operations", "Relations and Functions", "Sequence and Series", 
            "Word Problems", "Shapes (Geometry)", "Algebra Basics", "Linear Algebra",
            "Logarithms", "Probability", "Binomial Theorem", "Polynomial Functions",
            "Rational Functions", "Trigonometry", "Vectors", "Statistics",
            "Coordinate Geometry", "Introduction to Calculus", "Number Bases",
            "Modulo Arithmetic", "Advanced Combo"
        ]
        
        if selected_page == "📊 Dashboard":
            display_dashboard(st.session_state.username)
        elif selected_page == "📝 Quiz":
            display_quiz_page(topic_options)
        elif selected_page == "🏆 Leaderboard":
            display_leaderboard(topic_options)
        elif selected_page == "⚔️ Math Game":
            # --- This change is necessary for the topic selector to work ---
            display_math_game_page(topic_options)
        elif selected_page == "💬 Blackboard":
            display_blackboard_page()
        elif selected_page == "👤 Profile":
            display_profile_page()
        elif selected_page == "📚 Learning Resources":
            display_learning_resources(topic_options)
        # 2. ADD THIS NEW ELIF BLOCK (a good place is right before the Admin Panel check)
        elif selected_page == "❓ Help Center":
            display_help_center_page()
        # --- AND ADD THIS FINAL BLOCK RIGHT AFTER IT ---
        elif selected_page == "⚙️ Admin Panel":
            display_admin_panel(topic_options)
        # --- END OF BLOCK ---
        
    st.markdown('</div>', unsafe_allow_html=True)
def show_login_or_signup_page():
    load_css()
    st.markdown('<div class="login-container">', unsafe_allow_html=True)

    if st.session_state.page == "login":
        st.markdown('<p class="login-title">MathFriend Login</p>', unsafe_allow_html=True)

        # --- START: NEW DESIGN ELEMENTS ---
        # Use the time-based greeting for a dynamic welcome message
        greeting = get_time_based_greeting()
        st.markdown(f'<p class="login-subtitle">{greeting}! Please sign in to continue.</p>', unsafe_allow_html=True)
        # --- END: NEW DESIGN ELEMENTS ---

        with st.form("login_form"):
            username = st.text_input("Username", key="login_user")
            password = st.text_input("Password", type="password", key="login_pass")
            if st.form_submit_button("Login", type="primary", use_container_width=True):
                if login_user(username, password):
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
            confirm_password = st.text_input("Confirm New Password", type="password", key="signup_confirm")
            if st.form_submit_button("Create Account", type="primary", use_container_width=True):
                if not username or not password:
                    st.error("All fields are required.")
                elif password != confirm_password:
                    st.error("Passwords do not match.")
                elif not re.match("^[a-zA-Z0-9_]+$", username):
                    st.error("Username is invalid. Please use only letters, numbers, and underscores (_). No spaces are allowed.")
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



































































































































































































































































































































































