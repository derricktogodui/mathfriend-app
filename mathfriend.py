import streamlit as st
from streamlit_autorefresh import st_autorefresh
import time
import datetime
import json
import os
import pyperclip  # for clipboard sharing

# --- Constants ---
QUESTION_TIME_LIMIT = 30  # seconds per question
MAX_HINTS_PER_QUIZ = 2
USER_PERSIST_FILE = "current_user.txt"
CHAT_FILE = "chat_messages.json"

# --- Helpers ---

def animated_header():
    st.markdown("""
    <style>
    @keyframes slideFadeIn {
        0% {opacity: 0; transform: translateY(20px);}
        100% {opacity: 1; transform: translateY(0);}
    }
    .animated-header {
        font-size: 48px;
        font-weight: 900;
        color: #2E86C1;
        text-align: center;
        animation: slideFadeIn 1s ease forwards;
        margin-bottom: 20px;
        font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
        user-select:none;
    }
    /* Confetti container */
    .confetti {
        position: fixed;
        width: 100%;
        height: 100%;
        pointer-events: none;
        top: 0; left: 0;
        z-index: 9999;
        overflow: visible;
    }
    .confetti-piece {
        position: absolute;
        width: 10px;
        height: 10px;
        background-color: #f44336;
        opacity: 0.8;
        animation-name: confetti-fall;
        animation-timing-function: linear;
        animation-iteration-count: 1;
    }
    @keyframes confetti-fall {
        0% {transform: translateY(0) rotate(0deg);}
        100% {transform: translateY(600px) rotate(360deg);}
    }
    /* Footer styling */
    footer {
        text-align: center;
        padding: 10px;
        font-size: 14px;
        color: #666;
        margin-top: 40px;
        font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
    }
    /* Dark mode styles */
    .dark-mode {
        background-color: #121212 !important;
        color: #e0e0e0 !important;
    }
    .dark-mode .stButton>button {
        background-color: #2196f3 !important;
        color: white !important;
    }
    /* Chat styling */
    .chat-container {
        max-height: 300px;
        overflow-y: auto;
        border: 1px solid #ddd;
        border-radius: 8px;
        padding: 10px;
        background: #f9f9f9;
        font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
    }
    .dark-mode .chat-container {
        background: #1e1e1e;
        border-color: #444;
    }
    .chat-message {
        margin-bottom: 8px;
        padding: 6px 10px;
        border-radius: 12px;
        max-width: 75%;
        word-wrap: break-word;
        font-size: 14px;
    }
    .chat-message.user {
        background-color: #D6EAF8;
        align-self: flex-start;
    }
    .dark-mode .chat-message.user {
        background-color: #2a62b8;
        color: white;
    }
    .chat-message.own {
        background-color: #A9DFBF;
        align-self: flex-end;
    }
    .dark-mode .chat-message.own {
        background-color: #196F3D;
        color: white;
    }
    .chat-timestamp {
        font-size: 10px;
        color: #888;
        margin-top: 2px;
    }
    .dark-mode .chat-timestamp {
        color: #bbb;
    }
    .chat-box {
        display: flex;
        gap: 8px;
        margin-top: 10px;
    }
    .chat-input {
        flex-grow: 1;
    }
    /* Responsive columns for buttons */
    @media (max-width: 600px) {
        .button-row {
            display: flex;
            flex-direction: column;
            gap: 10px;
        }
    }
    @media (min-width: 601px) {
        .button-row {
            display: flex;
            flex-direction: row;
            gap: 10px;
        }
    }
    </style>

    <div class="animated-header">MathFriend</div>

    <script>
    function createConfettiPiece(color, x) {
        const confetti = document.createElement('div');
        confetti.classList.add('confetti-piece');
        confetti.style.backgroundColor = color;
        confetti.style.left = x + 'px';
        confetti.style.top = '-10px';
        confetti.style.animationDuration = (Math.random() * 2 + 2) + 's';
        confetti.style.animationDelay = (Math.random() * 0.5) + 's';
        return confetti;
    }
    function launchConfetti() {
        const colors = ['#f44336','#e91e63','#ffeb3b','#4caf50','#2196f3','#ff9800','#9c27b0'];
        const container = document.createElement('div');
        container.className = 'confetti';
        document.body.appendChild(container);
        for(let i=0; i<100; i++) {
            const x = Math.random() * window.innerWidth;
            const color = colors[Math.floor(Math.random() * colors.length)];
            const confetti = createConfettiPiece(color, x);
            container.appendChild(confetti);
            confetti.addEventListener('animationend', () => {
                confetti.remove();
                if(container.childElementCount === 0) container.remove();
            });
        }
    }
    window.launchConfetti = launchConfetti;

    // Play sound by id
    function playSound(id) {
        var sound = document.getElementById(id);
        if(sound) {
            sound.play();
        }
    }
    window.playSound = playSound;
    </script>

    <audio id="correct-sound" src="https://actions.google.com/sounds/v1/cartoon/clang_and_wobble.ogg"></audio>
    """, unsafe_allow_html=True)

def show_confetti_and_sound():
    st.markdown("<script>launchConfetti(); playSound('correct-sound');</script>", unsafe_allow_html=True)

def footer():
    st.markdown("""
    <footer>
    MathFriend — created with ❤️ by <b>Derrick Togodui</b><br>
    Keep practicing and have fun learning math!
    </footer>
    """, unsafe_allow_html=True)

def load_user_data():
    if os.path.exists("users.json"):
        with open("users.json", "r") as f:
            return json.load(f)
    return {}

def save_user_data():
    with open("users.json", "w") as f:
        json.dump(st.session_state.users, f, indent=4)

def save_current_user(user_key):
    with open(USER_PERSIST_FILE, "w") as f:
        f.write(user_key)

def load_current_user():
    if os.path.exists(USER_PERSIST_FILE):
        with open(USER_PERSIST_FILE, "r") as f:
            return f.read().strip()
    return None

def load_chat_messages():
    if os.path.exists(CHAT_FILE):
        with open(CHAT_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

def save_chat_messages(messages):
    with open(CHAT_FILE, "w", encoding="utf-8") as f:
        json.dump(messages, f, indent=4)

def go_to(step):
    st.session_state.step = step

def reset_quiz_state():
    st.session_state.question_index = 0
    st.session_state.score = 0
    st.session_state.last_answered = False
    st.session_state.timer_start = None
    st.session_state.hints_used = 0
    st.session_state.selected_answer = None

# --- Initialize Session State ---

if "users" not in st.session_state:
    st.session_state.users = load_user_data()

if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "user" not in st.session_state:
    saved_user = load_current_user()
    if saved_user and saved_user in st.session_state.users:
        st.session_state.user = saved_user
        st.session_state.logged_in = True
        st.session_state.step = "menu"
    else:
        st.session_state.user = None
        st.session_state.step = "login"

if "step" not in st.session_state:
    st.session_state.step = "login"
if "topic" not in st.session_state:
    st.session_state.topic = None
if "mode" not in st.session_state:
    st.session_state.mode = None
if "question_index" not in st.session_state:
    st.session_state.question_index = 0
if "score" not in st.session_state:
    st.session_state.score = 0
if "last_answered" not in st.session_state:
    st.session_state.last_answered = False
if "timer_start" not in st.session_state:
    st.session_state.timer_start = None
if "history" not in st.session_state:
    st.session_state.history = []
if "leaderboard" not in st.session_state:
    st.session_state.leaderboard = []
if "show_notification" not in st.session_state:
    st.session_state.show_notification = True
if "dark_mode" not in st.session_state:
    st.session_state.dark_mode = False
if "hints_used" not in st.session_state:
    st.session_state.hints_used = 0
if "selected_answer" not in st.session_state:
    st.session_state.selected_answer = None
if "chat_messages" not in st.session_state:
    st.session_state.chat_messages = load_chat_messages()

# --- Sample minimal questions ---
sample_questions = {
    "Algebra": [
        {
            "question": "What is 2 + 2?",
            "options": ["3", "4", "5", "6"],
            "answer": "4",
            "tips": "Think simple addition.",
            "explanation": "2 plus 2 equals 4."
        },
        {
            "question": "Solve for x: 2x = 6",
            "options": ["2", "3", "4", "6"],
            "answer": "3",
            "tips": "Divide both sides by 2.",
            "explanation": "2x=6 means x=6/2=3."
        }
    ],
    "Geometry": [
        {
            "question": "How many sides in a triangle?",
            "options": ["3", "4", "5", "6"],
            "answer": "3",
            "tips": "Count the edges.",
            "explanation": "A triangle has 3 sides."
        }
    ]
}

# --- Avatar options ---
avatar_emojis = ["😀", "😎", "🤓", "🧐", "👩‍🎓", "👨‍🎓", "🧙‍♂️", "🦸‍♀️", "🦸‍♂️", "🐱", "🐶", "🦄", "🐸"]

# --- Screens ---

def login_screen():
    if st.session_state.dark_mode:
        st.markdown("<body class='dark-mode'>", unsafe_allow_html=True)
    animated_header()
    st.markdown("<h3 style='text-align:center; color:#2E86C1;'>Are you a new user or returning?</h3>", unsafe_allow_html=True)
    col1, col2 = st.columns(2)
    with col1:
        if st.button("New User"):
            go_to("register")
    with col2:
        if st.button("Returning User"):
            go_to("login_form")
    footer()

def register_screen():
    if st.session_state.dark_mode:
        st.markdown("<body class='dark-mode'>", unsafe_allow_html=True)
    animated_header()
    st.subheader("Register New User")
    with st.form("register_form"):
        name = st.text_input("Full Name")
        school = st.selectbox("School", ["Kajaji SHS", "Others"])
        other_school = ""
        if school == "Others":
            other_school = st.text_input("Please specify your school")
        avatar = st.selectbox("Pick an avatar emoji", avatar_emojis)
        submitted = st.form_submit_button("Register")
        if submitted:
            full_school = other_school.strip() if school == "Others" else school
            if not name.strip():
                st.warning("Please enter your full name.")
            elif not full_school.strip():
                st.warning("Please specify your school.")
            else:
                user_key = name.strip().lower()
                if user_key in st.session_state.users:
                    st.warning("User already exists! Please login instead.")
                else:
                    st.session_state.users[user_key] = {
                        "name": name.strip(),
                        "school": full_school,
                        "avatar": avatar,
                        "history": [],
                        "score": 0,
                        "streak": 0,
                        "last_login": None,
                        "daily_challenge_done": False
                    }
                    save_user_data()
                    # Auto login after registration:
                    st.session_state.user = user_key
                    st.session_state.logged_in = True
                    save_current_user(user_key)
                    reset_quiz_state()
                    st.success(f"Welcome, {name.strip()}! You are now logged in.")
                    go_to("menu")

    footer()

def login_form_screen():
    if st.session_state.dark_mode:
        st.markdown("<body class='dark-mode'>", unsafe_allow_html=True)
    animated_header()
    st.subheader("Returning User Login")
    with st.form("login_form"):
        name = st.text_input("Enter your full name")
        submitted = st.form_submit_button("Login")
        if submitted:
            user_key = name.strip().lower()
            if user_key in st.session_state.users:
                st.session_state.user = user_key
                st.session_state.logged_in = True
                save_current_user(user_key)
                reset_quiz_state()
                go_to("menu")
            else:
                st.warning("User not found. Please register first.")
    footer()

def profile_settings_screen():
    if st.session_state.dark_mode:
        st.markdown("<body class='dark-mode'>", unsafe_allow_html=True)
    animated_header()
    st.subheader("Profile Settings")

    user_data = st.session_state.users[st.session_state.user]
    with st.form("profile_form"):
        name = st.text_input("Full Name", value=user_data["name"])
        school = st.selectbox("School", ["Kajaji SHS", "Others"], index=0 if user_data["school"] == "Kajaji SHS" else 1)
        other_school = ""
        if school == "Others":
            other_school = st.text_input("Please specify your school", value=user_data["school"] if user_data["school"] != "Kajaji SHS" else "")
        avatar = st.selectbox("Pick an avatar emoji", avatar_emojis, index=avatar_emojis.index(user_data.get("avatar", "😀")))
        submitted = st.form_submit_button("Save Changes")
        if submitted:
            full_school = other_school.strip() if school == "Others" else school
            if not name.strip():
                st.warning("Please enter your full name.")
            elif not full_school.strip():
                st.warning("Please specify your school.")
            else:
                user_key_old = st.session_state.user
                user_key_new = name.strip().lower()
                if user_key_new != user_key_old and user_key_new in st.session_state.users:
                    st.warning("Name already taken by another user. Choose a different name.")
                else:
                    # Update user data
                    user_data["name"] = name.strip()
                    user_data["school"] = full_school
                    user_data["avatar"] = avatar

                    # If username changed, rename key in dict
                    if user_key_new != user_key_old:
                        st.session_state.users[user_key_new] = st.session_state.users.pop(user_key_old)
                        st.session_state.user = user_key_new
                        save_current_user(user_key_new)
                    save_user_data()
                    st.success("Profile updated successfully.")
    if st.button("Back to Menu"):
        go_to("menu")
    footer()

def menu_screen():
    if st.session_state.dark_mode:
        st.markdown("<body class='dark-mode'>", unsafe_allow_html=True)
    animated_header()
    user_data = st.session_state.users[st.session_state.user]

    # Dark mode toggle top-right
    dm = st.checkbox("🌙 Dark mode", value=st.session_state.dark_mode)
    if dm != st.session_state.dark_mode:
        st.session_state.dark_mode = dm
        go_to("menu")
        st.experimental_rerun()

    st.markdown(f"""
        <div style="background:#D6EAF8; padding:10px; border-radius:8px; font-size:18px; font-weight:bold; text-align:center; display:flex; align-items:center; justify-content:center; gap:10px;">
        <span style="font-size:32px;">{user_data.get('avatar','😀')}</span>
        Welcome, <span style="color:#1B4F72;">{user_data['name']}</span> from <span style="color:#117A65;">{user_data['school']}</span>!
        </div>
        """, unsafe_allow_html=True)

    # Daily challenge placeholder + streak info
    today = datetime.date.today()
    last_login = user_data.get("last_login")
    streak = user_data.get("streak", 0)
    daily_done = user_data.get("daily_challenge_done", False)

    if last_login is not None:
        last_login_date = datetime.datetime.strptime(last_login, "%Y-%m-%d").date()
        if (today - last_login_date).days == 1:
            streak += 1
        elif (today - last_login_date).days > 1:
            streak = 0
    else:
        streak = 1

    user_data["streak"] = streak
    user_data["last_login"] = str(today)
    save_user_data()

    st.markdown(f"**🔥 Current Streak:** {streak} days")

    st.markdown("### What would you like to do?")
    cols = st.columns(3, gap="small")
    with cols[0]:
        if st.button("Take a Quiz"):
            st.session_state.topic = None
            st.session_state.mode = "quiz"
            reset_quiz_state()
            go_to("select_topic")
    with cols[1]:
        if st.button("Study Theory"):
            st.session_state.topic = None
            st.session_state.mode = "theory"
            go_to("select_topic")
    with cols[2]:
        if st.button("View Progress"):
            go_to("progress")

    # Second row with chat and profile
    cols2 = st.columns(3, gap="small")
    with cols2[0]:
        if st.button("Chat Room"):
            go_to("chat")
    with cols2[1]:
        if st.button("Profile Settings"):
            go_to("profile")
    with cols2[2]:
        if st.button("Logout"):
            st.session_state.logged_in = False
            st.session_state.user = None
            if os.path.exists(USER_PERSIST_FILE):
                os.remove(USER_PERSIST_FILE)
            go_to("login")

    footer()

def select_topic_screen():
    if st.session_state.dark_mode:
        st.markdown("<body class='dark-mode'>", unsafe_allow_html=True)
    animated_header()
    st.subheader("Select a topic")
    topics = list(sample_questions.keys())
    topic = st.radio("Choose a topic:", topics)
    if st.button("Continue"):
        st.session_state.topic = topic
        if st.session_state.mode == "quiz":
            reset_quiz_state()
            go_to("quiz")
        else:
            go_to("theory")
    if st.button("Back to Menu"):
        go_to("menu")
    footer()

def theory_screen():
    if st.session_state.dark_mode:
        st.markdown("<body class='dark-mode'>", unsafe_allow_html=True)
    animated_header()
    st.subheader(f"Theory: {st.session_state.topic}")

    # Display theory for chosen topic
    if st.session_state.topic == "Algebra":
        st.markdown("""
        **Algebra** is the branch of mathematics dealing with symbols and the rules for manipulating those symbols.
        It includes solving equations, understanding functions, and working with variables.
        """)
    elif st.session_state.topic == "Geometry":
        st.markdown("""
        **Geometry** is the branch of mathematics concerned with shapes, sizes, relative positions of figures,
        and properties of space.
        """)
    else:
        st.write("Theory content coming soon...")

    if st.button("Back to Topics"):
        go_to("select_topic")
    if st.button("Back to Menu"):
        go_to("menu")
    footer()

def quiz_screen():
    if st.session_state.dark_mode:
        st.markdown("<body class='dark-mode'>", unsafe_allow_html=True)
    animated_header()

    questions = sample_questions.get(st.session_state.topic, [])
    if not questions:
        st.warning("No questions available for this topic yet.")
        if st.button("Back to Topics"):
            go_to("select_topic")
        return

    q_index = st.session_state.question_index
    score = st.session_state.score
    total = len(questions)

    if q_index >= total:
        # Quiz finished
        st.success(f"Quiz Complete! Your score: {score} / {total}")
        # Update user score & history
        user_data = st.session_state.users[st.session_state.user]
        user_data["score"] = max(user_data.get("score", 0), score)
        user_data["history"].append({
            "topic": st.session_state.topic,
            "score": score,
            "date": str(datetime.date.today())
        })
        save_user_data()

        # Show confetti + sound on good score
        if score >= total * 0.7:
            show_confetti_and_sound()

        if st.button("Back to Menu"):
            go_to("menu")
        if st.button("Retry Quiz"):
            reset_quiz_state()
            go_to("quiz")
        return

    question = questions[q_index]
    st.markdown(f"**Question {q_index+1} of {total}:** {question['question']}")

    # Timer countdown
    if st.session_state.timer_start is None:
        st.session_state.timer_start = time.time()
    elapsed = time.time() - st.session_state.timer_start
    time_left = max(0, QUESTION_TIME_LIMIT - int(elapsed))
    st.markdown(f"⏳ Time left: {time_left} seconds")

    # Show options with radio buttons
    options = question["options"]
    selected = st.radio("Select your answer:", options, key="answer_radio")

    col1, col2, col3 = st.columns([1, 1, 2])
    with col1:
        if st.button("Submit Answer"):
            if selected == question["answer"]:
                st.success("Correct! 🎉")
                st.session_state.score += 1
                show_confetti_and_sound()
            else:
                st.error(f"Incorrect! The correct answer was: {question['answer']}")
            st.session_state.last_answered = True
            st.session_state.timer_start = None
    with col2:
        if st.button("Hint"):
            if st.session_state.hints_used < MAX_HINTS_PER_QUIZ:
                st.info(f"Hint: {question['tips']}")
                st.session_state.hints_used += 1
            else:
                st.warning("Sorry, no more hints allowed for this quiz.")
    with col3:
        if st.session_state.last_answered:
            if st.button("Next Question"):
                st.session_state.question_index += 1
                st.session_state.last_answered = False
                st.session_state.selected_answer = None
                st.session_state.timer_start = None
                st.experimental_rerun()

    if st.session_state.last_answered:
        st.markdown(f"**Explanation:** {question['explanation']}")

    if st.button("Quit Quiz"):
        go_to("menu")

    footer()

def progress_screen():
    if st.session_state.dark_mode:
        st.markdown("<body class='dark-mode'>", unsafe_allow_html=True)
    animated_header()
    st.subheader("Your Progress")
    user_data = st.session_state.users[st.session_state.user]

    history = user_data.get("history", [])
    if not history:
        st.info("You haven't taken any quizzes yet.")
    else:
        for record in history[-10:]:
            st.markdown(f"**{record['date']}** - Topic: {record['topic']} — Score: {record['score']}")

    st.markdown(f"**Best Score:** {user_data.get('score', 0)}")
    st.markdown(f"**Current Streak:** {user_data.get('streak', 0)} days")

    if st.button("Back to Menu"):
        go_to("menu")

    footer()

def chat_screen():
    if st.session_state.dark_mode:
        st.markdown("<body class='dark-mode'>", unsafe_allow_html=True)

    animated_header()
    st.subheader("Public Chat Room")

    chat_container_style = """
    <style>
    #chat-container {
        display: flex;
        flex-direction: column;
    }
    </style>
    """
    st.markdown(chat_container_style, unsafe_allow_html=True)

    # Display messages in a scrollable container
    messages = st.session_state.chat_messages

    # Chat container box
    st.markdown('<div class="chat-container" id="chat-container">', unsafe_allow_html=True)
    for msg in messages[-50:]:  # show last 50 messages
        own_msg = (msg["user_key"] == st.session_state.user)
        cls = "own" if own_msg else "user"
        timestamp = datetime.datetime.fromisoformat(msg["timestamp"]).strftime("%H:%M")
        user_avatar = st.session_state.users.get(msg["user_key"], {}).get("avatar", "🙂")
        user_name = st.session_state.users.get(msg["user_key"], {}).get("name", "Unknown")

        st.markdown(
            f'<div class="chat-message {cls}">'
            f'<b>{user_avatar} {user_name}:</b> {msg["text"]}<br>'
            f'<span class="chat-timestamp">{timestamp}</span>'
            f'</div>', unsafe_allow_html=True
        )
    st.markdown('</div>', unsafe_allow_html=True)

    # Input to send new message
    with st.form("chat_form", clear_on_submit=True):
        msg = st.text_input("Type your message here", max_chars=200, key="chat_input")
        send = st.form_submit_button("Send")
        if send:
            if msg.strip():
                new_msg = {
                    "user_key": st.session_state.user,
                    "text": msg.strip(),
                    "timestamp": datetime.datetime.now().isoformat()
                }
                st.session_state.chat_messages.append(new_msg)
                save_chat_messages(st.session_state.chat_messages)
                st.experimental_rerun()

    if st.button("Back to Menu"):
        go_to("menu")

    footer()

# --- Routing ---
def main():
    if st.session_state.step == "login":
        login_screen()
    elif st.session_state.step == "register":
        register_screen()
    elif st.session_state.step == "login_form":
        login_form_screen()
    elif st.session_state.step == "menu":
        menu_screen()
    elif st.session_state.step == "profile":
        profile_settings_screen()
    elif st.session_state.step == "select_topic":
        select_topic_screen()
    elif st.session_state.step == "theory":
        theory_screen()
    elif st.session_state.step == "quiz":
        quiz_screen()
    elif st.session_state.step == "progress":
        progress_screen()
    elif st.session_state.step == "chat":
        chat_screen()
    else:
        st.error("Unknown page")

if __name__ == "__main__":
    main()

