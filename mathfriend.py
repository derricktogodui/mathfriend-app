import streamlit as st
import random
import datetime
import json
import os
import time

# --- APP CONFIG ---
st.set_page_config(page_title="MathFriend", page_icon="📚", layout="centered")

DATA_FILE = "users.json"

# --- SAMPLE QUESTIONS ---
QUESTIONS = {
    "Algebra": [
        {
            "question": "What is 2 + 3?",
            "options": ["4", "5", "6", "7"],
            "answer": "5",
            "tip": "Think about how many you get when you add two fingers and three fingers.",
            "explanation": "2 + 3 = 5 because adding two and three gives a total of five."
        },
        {
            "question": "Solve for x: 2x = 10",
            "options": ["4", "5", "6", "8"],
            "answer": "5",
            "tip": "Divide both sides by 2.",
            "explanation": "2x = 10 → x = 10/2 → x = 5."
        },
        {
            "question": "What is (x + 3)(x - 2)?",
            "options": ["x² + x - 6", "x² + x + 6", "x² - 5x + 6", "x² - x - 6"],
            "answer": "x² + x - 6",
            "tip": "Use FOIL method: First, Outer, Inner, Last.",
            "explanation": "(x + 3)(x - 2) = x² - 2x + 3x - 6 = x² + x - 6"
        },
    ],
    "Geometry": [
        {
            "question": "What is the sum of angles in a triangle?",
            "options": ["90°", "180°", "270°", "360°"],
            "answer": "180°",
            "tip": "Think about the angles in any flat triangle.",
            "explanation": "In Euclidean geometry, the sum of the angles in a triangle is always 180°."
        },
        {
            "question": "How many sides does a pentagon have?",
            "options": ["4", "5", "6", "7"],
            "answer": "5",
            "tip": "Pent means five.",
            "explanation": "A pentagon has 5 sides."
        },
    ],
    "Calculus": [
        {
            "question": "What is the derivative of x²?",
            "options": ["2x", "x", "x²", "1"],
            "answer": "2x",
            "tip": "Use power rule: d/dx of xⁿ is n*xⁿ⁻¹.",
            "explanation": "Derivative of x² is 2x."
        },
        {
            "question": "What is the integral of 2x dx?",
            "options": ["x² + C", "2x + C", "x + C", "x³ + C"],
            "answer": "x² + C",
            "tip": "Integral of 2x is x² plus constant.",
            "explanation": "∫2x dx = x² + C."
        },
    ],
}

# --- THEORY CONTENT ---
THEORY = {
    "Algebra": [
        "Algebra is the branch of mathematics dealing with symbols and the rules for manipulating those symbols.",
        "An equation is a statement that two expressions are equal.",
        "You can solve equations by isolating the variable on one side.",
    ],
    "Geometry": [
        "Geometry is concerned with properties and relations of points, lines, surfaces, and solids.",
        "The sum of interior angles of a triangle is always 180 degrees.",
        "Polygons are shapes with many sides, like pentagons, hexagons, etc.",
    ],
    "Calculus": [
        "Calculus studies change and motion through derivatives and integrals.",
        "The derivative represents the rate of change of a function.",
        "The integral is the area under the curve of a function.",
    ],
}

# --- SESSION STATE SETUP ---
if "step" not in st.session_state:
    st.session_state.step = "splash"
if "user_name" not in st.session_state:
    st.session_state.user_name = ""
if "school" not in st.session_state:
    st.session_state.school = "Kajaji SHS"
if "topic" not in st.session_state:
    st.session_state.topic = ""
if "mode" not in st.session_state:
    st.session_state.mode = ""
if "questions" not in st.session_state:
    st.session_state.questions = []
if "question_index" not in st.session_state:
    st.session_state.question_index = 0
if "score" not in st.session_state:
    st.session_state.score = 0
if "streak" not in st.session_state:
    st.session_state.streak = 0
if "last_practice_date" not in st.session_state:
    st.session_state.last_practice_date = None
if "theory_index" not in st.session_state:
    st.session_state.theory_index = 0
if "users_data" not in st.session_state:
    st.session_state.users_data = {}
if "hints_used" not in st.session_state:
    st.session_state.hints_used = 0
if "timer_start" not in st.session_state:
    st.session_state.timer_start = None
if "time_out" not in st.session_state:
    st.session_state.time_out = False
if "last_answered" not in st.session_state:
    st.session_state.last_answered = True
if "history" not in st.session_state:
    st.session_state.history = []

# --- DATA PERSISTENCE FUNCTIONS ---
def load_users_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    return {}

def save_users_data():
    with open(DATA_FILE, "w") as f:
        json.dump(st.session_state.users_data, f, indent=4)

def get_user_key(name, school):
    return f"{name.lower()}_{school.lower().replace(' ', '_')}"

def load_user_data():
    key = get_user_key(st.session_state.user_name, st.session_state.school)
    data = st.session_state.users_data.get(key)
    if data:
        st.session_state.streak = data.get("streak", 0)
        last_date_str = data.get("last_practice_date")
        if last_date_str:
            st.session_state.last_practice_date = datetime.datetime.strptime(last_date_str, "%Y-%m-%d").date()
        else:
            st.session_state.last_practice_date = None
        st.session_state.score = data.get("total_score", 0)
        st.session_state.history = data.get("history", [])
    else:
        st.session_state.streak = 0
        st.session_state.last_practice_date = None
        st.session_state.score = 0
        st.session_state.history = []

def save_user_data():
    key = get_user_key(st.session_state.user_name, st.session_state.school)
    st.session_state.users_data[key] = {
        "name": st.session_state.user_name,
        "school": st.session_state.school,
        "streak": st.session_state.streak,
        "last_practice_date": st.session_state.last_practice_date.strftime("%Y-%m-%d") if st.session_state.last_practice_date else None,
        "total_score": st.session_state.score,
        "history": st.session_state.history,
    }
    save_users_data()

# --- NAVIGATION FUNCTION ---
def go_to(step):
    st.session_state.step = step

def shuffle_options(options):
    shuffled = options[:]
    random.shuffle(shuffled)
    return shuffled

# --- STREAK & BADGE ---
def update_streak():
    today = datetime.date.today()
    last_date = st.session_state.last_practice_date
    if last_date is None:
        st.session_state.streak = 1
    else:
        delta = (today - last_date).days
        if delta == 1:
            st.session_state.streak += 1
        elif delta > 1:
            st.session_state.streak = 1
    st.session_state.last_practice_date = today

def get_streak_badge(streak):
    if streak >= 30:
        return "🥇 Gold Streak Master (30+ days!)"
    elif streak >= 7:
        return "🥈 Silver Streak Pro (7+ days!)"
    elif streak >= 3:
        return "🥉 Bronze Beginner (3+ days!)"
    else:
        return None

# --- TIMER ---
QUESTION_TIME_LIMIT = 30  # seconds

def start_timer():
    st.session_state.timer_start = time.time()
    st.session_state.time_out = False
    st.session_state.last_answered = False

def check_timer():
    if st.session_state.timer_start is None:
        return False
    elapsed = time.time() - st.session_state.timer_start
    remaining = int(QUESTION_TIME_LIMIT - elapsed)
    if remaining <= 0:
        st.session_state.time_out = True
        return True
    else:
        st.write(f"⏰ Time left: {remaining} seconds")
        return False

# --- ANIMATED HEADER ---
def show_animated_header():
    header_html = """
    <style>
    @keyframes fadeSlideUp {
      0% {
        opacity: 0;
        transform: translateY(20px);
      }
      100% {
        opacity: 1;
        transform: translateY(0);
      }
    }
    .centered-text {
      font-size: 50px;
      font-weight: bold;
      color: #2E86C1;
      animation: fadeSlideUp 1s ease forwards;
      opacity: 0;
      text-align: center;
      margin-top: 40px;
      font-family: Arial, sans-serif;
    }
    </style>

    <div class="centered-text">MathFriend</div>
    """
    st.markdown(header_html, unsafe_allow_html=True)

# --- LEADERBOARD ---
def show_leaderboard():
    show_animated_header()
    st.header("🏆 Leaderboard")
    if not st.session_state.users_data:
        st.info("No users yet.")
        return
    # Sort users by streak descending, then by total_score descending
    sorted_users = sorted(
        st.session_state.users_data.values(),
        key=lambda u: (u.get("streak",0), u.get("total_score",0)),
        reverse=True
    )
    # Show top 10
    top_users = sorted_users[:10]
    st.write("Top users by streak and total score:")
    for i, user in enumerate(top_users, start=1):
        badge = get_streak_badge(user.get("streak",0)) or ""
        st.write(f"{i}. {user['name']} ({user['school']}) — Streak: {user.get('streak',0)} days, Total Score: {user.get('total_score',0)} {badge}")

    if st.button("⬅️ Back to Menu"):
        go_to("menu")

# --- THEORY MODE ---
def show_theory():
    show_animated_header()
    topic = st.session_state.topic
    st.header(f"📖 Theory: {topic}")

    content = THEORY.get(topic, [])
    index = st.session_state.theory_index
    if not content:
        st.info("Theory content coming soon!")
    else:
        st.write(content[index])
        col1, col2 = st.columns(2)
        with col1:
            if st.button("⬅️ Previous") and index > 0:
                st.session_state.theory_index -= 1
        with col2:
            if st.button("Next ➡️") and index < len(content) - 1:
                st.session_state.theory_index += 1

    if st.button("⬅️ Back to Menu"):
        st.session_state.theory_index = 0
        go_to("menu")

# --- PROGRESS SCREEN ---
def show_progress():
    show_animated_header()
    st.header(f"📊 Progress for {st.session_state.user_name}")
    if not st.session_state.history:
        st.info("No practice history yet. Start practicing to see your progress here!")
    else:
        for record in st.session_state.history[-10:][::-1]:  # last 10 attempts, newest first
            date = record.get("date")
            topic = record.get("topic")
            mode = record.get("mode")
            score = record.get("score")
            total = record.get("total")
            st.write(f"🗓️ {date} — Topic: **{topic}**, Mode: {mode}, Score: {score}/{total}")

    if st.button("⬅️ Back to Menu"):
        go_to("menu")

# --- SCREENS ---
if st.session_state.step == "splash":
    show_animated_header()
    st.markdown("**Your everyday buddy for mastering math!**")
    if st.button("Start ➡️"):
        go_to("register")

elif st.session_state.step == "register":
    show_animated_header()
    st.header("👋 Welcome to MathFriend!")
    first_time = st.radio("Is this your first time here?", ("Yes, first time", "No, I'm returning"))

    if first_time == "Yes, first time":
        name = st.text_input("Full Name")
        school_choice = st.selectbox("School", ["Kajaji SHS", "Other"])
        if school_choice == "Other":
            school = st.text_input("Enter your school")
        else:
            school = "Kajaji SHS"

        if st.button("Continue"):
            if name.strip() == "":
                st.warning("Please enter your name.")
            else:
                st.session_state.user_name = name.strip()
                st.session_state.school = school.strip() if school_choice == "Other" else "Kajaji SHS"
                # Load users data & user data
                st.session_state.users_data = load_users_data()
                load_user_data()
                update_streak()
                save_user_data()
                go_to("menu")

    else:
        name = st.text_input("Enter your name")
        if st.button("Continue"):
            if name.strip() == "":
                st.warning("Please enter your name.")
            else:
                st.session_state.user_name = name.strip()
                st.session_state.users_data = load_users_data()
                load_user_data()
                update_streak()
                save_user_data()
                go_to("menu")

elif st.session_state.step == "menu":
    show_animated_header()
    st.header(f"Welcome, {st.session_state.user_name} from {st.session_state.school}!")
    st.info(f"🔥 Your current streak: {st.session_state.streak} day(s) in a row!")
    badge = get_streak_badge(st.session_state.streak)
    if badge:
        st.markdown(f"**🏅 {badge}**")

    st.markdown("**Choose an option:**")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("📝 Practice Questions"):
            go_to("topic")
    with col2:
        if st.button("📚 Theory Lessons"):
            go_to("topic_theory")

    if st.button("📈 View Progress"):
        go_to("progress")

    if st.button("🏆 Leaderboard"):
        go_to("leaderboard")
    if st.button("🚪 Logout"):
        # Clear user session data except for persistent data
        st.session_state.step = "splash"
        st.session_state.user_name = ""
        st.session_state.school = "Kajaji SHS"
        st.session_state.topic = ""
        st.session_state.mode = ""
        st.session_state.questions = []
        st.session_state.question_index = 0
        st.session_state.score = 0
        st.session_state.streak = 0
        st.session_state.last_practice_date = None
        st.session_state.theory_index = 0
        st.session_state.users_data = {}
        st.session_state.hints_used = 0
        st.session_state.timer_start = None
        st.session_state.time_out = False
        st.session_state.last_answered = True
        st.session_state.history = []

elif st.session_state.step == "topic":
    show_animated_header()
    st.header("📂 Choose Your Topic")
    topic = st.selectbox("Select a math topic", list(QUESTIONS.keys()))
    mode = st.radio("Choose Practice Mode", ["Multiple Choice"])

    if st.button("Start Practice"):
        st.session_state.topic = topic
        st.session_state.mode = mode
        questions = QUESTIONS.get(topic, [])
        if mode == "Multiple Choice" and questions:
            questions = random.sample(questions, len(questions))
            for q in questions:
                q["shuffled_options"] = shuffle_options(q["options"])
        else:
            for q in questions:
                q["shuffled_options"] = q["options"]
        st.session_state.questions = questions
        st.session_state.question_index = 0
        st.session_state.score = 0
        st.session_state.hints_used = 0
        st.session_state.time_out = False
        st.session_state.last_answered = True
        go_to("questions")

elif st.session_state.step == "topic_theory":
    show_animated_header()
    st.header("📂 Choose Your Topic for Theory")
    topic = st.selectbox("Select a math topic", list(THEORY.keys()))
    if st.button("Start Theory"):
        st.session_state.topic = topic
        st.session_state.theory_index = 0
        go_to("theory")

elif st.session_state.step == "questions":
    show_animated_header()
    questions = st.session_state.questions
    if not questions:
        st.warning("No questions available for this topic yet.")
        if st.button("⬅️ Back to Menu"):
            go_to("menu")
    else:
        q_index = st.session_state.question_index
        question = questions[q_index]

        st.subheader(f"Question {q_index + 1} of {len(questions)}")
        st.write(question["question"])

        # Timer start if first time on question
        if st.session_state.timer_start is None or st.session_state.last_answered:
            start_timer()

        # Show timer and check if time is up
        timed_out = check_timer()

        # Show Hint button if hints remain
        if st.session_state.hints_used < 2:
            if st.button("💡 Show Hint"):
                st.info(f"Hint: {question['tip']}")
                st.session_state.hints_used += 1

        if st.session_state.mode == "Multiple Choice":
            answer = st.radio("Choose your answer:", question["shuffled_options"])
        else:
            st.write("_Theory mode coming soon!_")
            answer = None

        submitted = st.button("Submit Answer")

        if submitted and not st.session_state.last_answered:
            if answer == question["answer"]:
                st.success("🎉 Correct! Great job!")
                st.session_state.score += 1
            else:
                st.error(f"❌ Incorrect. Explanation: {question['explanation']}")

            st.session_state.last_answered = True

        if timed_out and not st.session_state.last_answered:
            st.error(f"⏰ Time's up! The correct answer was: {question['answer']}")
            st.session_state.last_answered = True

        if st.session_state.last_answered:
            if st.button("➡️ Next Question"):
                st.session_state.question_index += 1
                st.session_state.timer_start = None
                st.session_state.last_answered = False
                st.experimental_rerun()

        if q_index + 1 > len(questions) - 1:
            st.write(f"Quiz finished! Your score: {st.session_state.score} / {len(questions)}")
            # Save result to history
            today_str = datetime.date.today().strftime("%Y-%m-%d")
            st.session_state.history.append({
                "date": today_str,
                "topic": st.session_state.topic,
                "mode": st.session_state.mode,
                "score": st.session_state.score,
                "total": len(questions)
            })
            # Update total score
            st.session_state.score += 0  # already counted during quiz
            save_user_data()
            if st.button("⬅️ Back to Menu"):
                go_to("menu")

elif st.session_state.step == "theory":
    show_theory()

elif st.session_state.step == "progress":
    show_progress()

elif st.session_state.step == "leaderboard":
    show_leaderboard()
