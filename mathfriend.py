# mathfriend.py
import streamlit as st
from streamlit_autorefresh import st_autorefresh
import time
import datetime
import json
import os
import random

# ----------------------
# Config / Constants
# ----------------------
QUESTION_TIME_LIMIT = 30  # seconds
MAX_HINTS_PER_QUIZ = 2
USERS_FILE = "users.json"
CHAT_FILE = "chats.json"  # will contain public and private teacher chats
PERSIST_USER_FILE = "current_user.txt"

# Example sample questions (expandable)
SAMPLE_QUESTIONS = {
    "Algebra": [
        {"question": "What is 2 + 2?", "options": ["3", "4", "5", "6"], "answer": "4",
         "tips": "Think simple addition.", "explanation": "2 + 2 = 4."},
        {"question": "Solve for x: 2x = 6", "options": ["2", "3", "4", "6"], "answer": "3",
         "tips": "Divide both sides by 2.", "explanation": "2x = 6 → x = 3."},
    ],
    "Geometry": [
        {"question": "How many sides does a triangle have?", "options": ["3", "4", "5", "6"], "answer": "3",
         "tips": "Count the edges.", "explanation": "A triangle has 3 sides."},
    ]
}

AVATAR_EMOJIS = ["😀", "😎", "🤓", "🧐", "👩‍🎓", "👨‍🎓", "🧙‍♂️", "🦸‍♀️", "🦸‍♂️", "🐱", "🐶", "🦄", "🐸"]

# ----------------------
# Utilities: load/save
# ----------------------
def load_users():
    if os.path.exists(USERS_FILE):
        try:
            with open(USERS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_users(users):
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(users, f, indent=2, ensure_ascii=False)

def load_chats():
    if os.path.exists(CHAT_FILE):
        try:
            with open(CHAT_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []

def save_chats(chats):
    with open(CHAT_FILE, "w", encoding="utf-8") as f:
        json.dump(chats, f, indent=2, ensure_ascii=False)

def save_persist_user(user_key):
    with open(PERSIST_USER_FILE, "w", encoding="utf-8") as f:
        f.write(user_key)

def load_persist_user():
    if os.path.exists(PERSIST_USER_FILE):
        with open(PERSIST_USER_FILE, "r", encoding="utf-8") as f:
            return f.read().strip()
    return None

# ----------------------
# Session initialization
# ----------------------
def init_session():
    if "users" not in st.session_state:
        st.session_state.users = load_users()
    if "chat_messages" not in st.session_state:
        st.session_state.chat_messages = load_chats()
    if "step" not in st.session_state:
        st.session_state.step = "login"  # login, register, login_form, menu, select_topic, quiz, theory, progress, leaderboard, profile, chat_public, chat_teacher
    if "logged_in" not in st.session_state:
        st.session_state.logged_in = False
    if "user" not in st.session_state:
        saved = load_persist_user()
        if saved and saved in st.session_state.users:
            st.session_state.user = saved
            st.session_state.logged_in = True
            st.session_state.step = "menu"
        else:
            st.session_state.user = None
    # Quiz state
    if "topic" not in st.session_state:
        st.session_state.topic = None
    if "mode" not in st.session_state:
        st.session_state.mode = None
    if "question_index" not in st.session_state:
        st.session_state.question_index = 0
    if "score" not in st.session_state:
        st.session_state.score = 0
    if "timer_start" not in st.session_state:
        st.session_state.timer_start = None
    if "last_answered" not in st.session_state:
        st.session_state.last_answered = False
    if "hints_used" not in st.session_state:
        st.session_state.hints_used = 0
    if "selected_answer" not in st.session_state:
        st.session_state.selected_answer = None
    # Show/hide online users toggle for chat
    if "show_online_users" not in st.session_state:
        st.session_state.show_online_users = False
    # Badges
    if "badges" not in st.session_state:
        st.session_state.badges = set()

init_session()

# ----------------------
# Helpers
# ----------------------
def go_to(step):
    st.session_state.step = step

def reset_quiz_state():
    st.session_state.question_index = 0
    st.session_state.score = 0
    st.session_state.timer_start = None
    st.session_state.last_answered = False
    st.session_state.hints_used = 0
    st.session_state.selected_answer = None

def back_button():
    if st.button("⬅ Back"):
        go_to("menu")
        return True
    return False

# ----------------------
# Animated header (smaller welcome emoji + text)
# ----------------------
def animated_header_clickable():
    html = """
    <style>
    .mf-header {
      font-size: 40px;
      font-weight: 900;
      color: #2E86C1;
      text-align: center;
      margin-bottom: 4px;
      font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
      user-select:none;
    }
    .mf-welcome {
      text-align:center;
      margin-bottom:10px;
      color:#555;
      font-size: 18px;
      user-select:none;
    }
    </style>
    <div style="text-align:center;">
      <div class="mf-header">MathFriend <span style="font-size:24px;">🧮</span></div>
      <div class="mf-welcome">Learn, practice and play — built for our students</div>
    </div>
    """
    st.markdown(html, unsafe_allow_html=True)

# ----------------------
# Confetti + sound helper
# ----------------------
def inject_confetti_and_sound_code():
    st.markdown("""
    <script>
    function createConfettiPiece(color, x) {
      const confetti = document.createElement('div');
      confetti.style.position = 'fixed';
      confetti.style.width = '8px';
      confetti.style.height = '12px';
      confetti.style.left = x + 'px';
      confetti.style.top = '-20px';
      confetti.style.background = color;
      confetti.style.opacity = '0.9';
      confetti.style.zIndex = 9999;
      confetti.style.transform = 'rotate(' + (Math.random()*360) + 'deg)';
      confetti.style.borderRadius = '2px';
      confetti.style.animation = 'drop ' + (Math.random()*1.5 + 1.5) + 's linear forwards';
      document.body.appendChild(confetti);
      confetti.addEventListener('animationend', function(){ confetti.remove(); });
    }
    function launchConfetti() {
      const colors = ['#f44336','#e91e63','#ffeb3b','#4caf50','#2196f3','#ff9800','#9c27b0'];
      for (let i=0;i<120;i++){
        const x = Math.random() * window.innerWidth;
        const color = colors[Math.floor(Math.random()*colors.length)];
        createConfettiPiece(color, x);
      }
    }
    function playSound(id){
      var s = document.getElementById(id);
      if(s) s.play();
    }
    </script>
    <style>
    @keyframes drop { to { transform: translateY(700px) rotate(360deg); opacity: 0.8; } }
    </style>
    <audio id="mf-correct-sound" src="https://actions.google.com/sounds/v1/cartoon/clang_and_wobble.ogg"></audio>
    """, unsafe_allow_html=True)

def celebrate():
    st.markdown("<script>launchConfetti(); playSound('mf-correct-sound');</script>", unsafe_allow_html=True)

inject_confetti_and_sound_code()

# ----------------------
# Quick Access Panel
# ----------------------
def quick_access_panel(user_data):
    st.markdown("### Quick Access")
    last = user_data.get("history", [])[-3:]
    if last:
        st.markdown("**Recent activity:**")
        for h in reversed(last):
            st.markdown(f"- {h.get('date','?')}: {h.get('topic','?')} — {h.get('score','?')}/{h.get('total','?')}")
    else:
        st.markdown("No recent activity — start a quiz!")

    cols = st.columns(3)
    with cols[0]:
        if st.button("Practice Quiz"):
            go_to("select_topic")
    with cols[1]:
        if st.button("Chat (Public)"):
            go_to("chat_public")
    with cols[2]:
        if st.button("Chat a Teacher"):
            go_to("chat_teacher_request")

# ----------------------
# Screens
# ----------------------
def screen_login():
    animated_header_clickable()
    st.write("")
    st.markdown("### Are you a new user or a returning user?")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("New user — Register"):
            go_to("register")
    with c2:
        if st.button("Returning user — Login"):
            go_to("login_form")
    st.markdown("---")
    st.markdown("Tip: If you already registered and the app keeps asking you to log in, check that your name exactly matches your registered full name (case-insensitive).")
    st.markdown("---")
    st.markdown("<div style='text-align:center; font-size:14px;'>Powered by Derek Winters</div>", unsafe_allow_html=True)

def screen_register():
    animated_header_clickable()
    if back_button():
        return
    st.header("Register new student")
    with st.form("register_form"):
        name = st.text_input("Full name")
        school_choice = st.selectbox("School", ["Kajaji SHS", "Others"])
        other_school = ""
        if school_choice == "Others":
            other_school = st.text_input("Specify your school")
        avatar = st.selectbox("Pick an avatar", AVATAR_EMOJIS, index=0)
        submit = st.form_submit_button("Create account")
        if submit:
            school = other_school.strip() if school_choice == "Others" else school_choice
            if not name.strip():
                st.warning("Please enter your full name.")
            elif not school:
                st.warning("Please enter your school.")
            else:
                key = name.strip().lower()
                if key in st.session_state.users:
                    st.warning("User already exists. Please login instead.")
                else:
                    st.session_state.users[key] = {
                        "name": name.strip(),
                        "school": school,
                        "avatar": avatar,
                        "history": [],
                        "score": 0,
                        "streak": 0,
                        "last_login": None,
                        "badges": []
                    }
                    save_users(st.session_state.users)
                    st.session_state.user = key
                    st.session_state.logged_in = True
                    save_persist_user(key)
                    reset_quiz_state()
                    st.success(f"Welcome {name.strip()} — you're registered and logged in!")
                    go_to("menu")

def screen_login_form():
    animated_header_clickable()
    if back_button():
        return
    st.header("Login")
    with st.form("login_form"):
        name = st.text_input("Enter your full name")
        submit = st.form_submit_button("Login")
        if submit:
            key = name.strip().lower()
            if key in st.session_state.users:
                st.session_state.user = key
                st.session_state.logged_in = True
                save_persist_user(key)
                reset_quiz_state()
                st.success(f"Welcome back, {st.session_state.users[key]['name']}!")
                go_to("menu")
            else:
                st.warning("User not found. Please register.")

def screen_menu():
    animated_header_clickable()
    user_key = st.session_state.user
    user_data = st.session_state.users.get(user_key, {})
    avatar = user_data.get("avatar", "😀")
    st.markdown(f"<div style='text-align:center; font-size:20px;'><span style='font-size:28px;'>{avatar}</span> Welcome <b>{user_data.get('name','')}</b> from <i>{user_data.get('school','')}</i></div>", unsafe_allow_html=True)

    # Streak handling
    today = datetime.date.today()
    last_login = user_data.get("last_login")
    streak = user_data.get("streak", 0)
    if last_login:
        try:
            ll = datetime.date.fromisoformat(last_login)
            delta = (today - ll).days
            if delta == 1:
                streak += 1
            elif delta > 1:
                streak = 1
        except Exception:
            streak = 1
    else:
        streak = 1
    st.session_state.users[user_key]["streak"] = streak
    st.session_state.users[user_key]["last_login"] = today.isoformat()
    save_users(st.session_state.users)

    st.markdown(f"**🔥 Streak:** {streak} day{'s' if streak!=1 else ''}")
    if streak >= 7 and "7-day" not in user_data.get("badges", []):
        st.session_state.users[user_key].setdefault("badges", []).append("7-day")
        save_users(st.session_state.users)
        st.balloons()
        st.success("🏅 Badge unlocked: 7-day streak!")

    quick_access_panel(user_data)

    st.markdown("---")
    c1, c2, c3 = st.columns(3)
    with c1:
        if st.button("📚 Theory"):
            go_to("select_topic_theory")
    with c2:
        if st.button("📈 Progress"):
            go_to("progress")
    with c3:
        if st.button("🏆 Leaderboard"):
            go_to("leaderboard")

    st.markdown("---")
    c4, c5 = st.columns(2)
    with c4:
        if st.button("⚙️ Profile"):
            go_to("profile")
    with c5:
        if st.button("🚪 Logout"):
            st.session_state.logged_in = False
            st.session_state.user = None
            try:
                if os.path.exists(PERSIST_USER_FILE):
                    os.remove(PERSIST_USER_FILE)
            except Exception:
                pass
            go_to("login")

def screen_select_topic():
    animated_header_clickable()
    if back_button():
        return
    st.header("Select topic for quiz")
    topics = list(SAMPLE_QUESTIONS.keys())
    topic = st.selectbox("Topic", topics)
    if st.button("Start Quiz"):
        st.session_state.topic = topic
        reset_quiz_state()
        go_to("quiz")

def screen_select_topic_theory():
    animated_header_clickable()
    if back_button():
        return
    st.header("Select topic for theory")
    topics = list(SAMPLE_QUESTIONS.keys())
    topic = st.selectbox("Topic", topics)
    if st.button("Read Theory"):
        st.session_state.topic = topic
        go_to("theory")

def screen_quiz():
    animated_header_clickable()
    if back_button():
        return
    topic = st.session_state.topic or "Algebra"
    questions = SAMPLE_QUESTIONS.get(topic, [])
    idx = st.session_state.question_index

    if idx >= len(questions):
        st.success(f"Quiz finished! Score: {st.session_state.score}/{len(questions)}")
        # save progress
        u = st.session_state.user
        st.session_state.users[u].setdefault("history", []).append({
            "date": datetime.date.today().isoformat(),
            "topic": topic,
            "score": st.session_state.score,
            "total": len(questions)
        })
        st.session_state.users[u]["score"] = max(st.session_state.users[u].get("score", 0), st.session_state.score)
        save_users(st.session_state.users)
        if st.button("Back to Menu"):
            go_to("menu")
        if st.button("Retry"):
            reset_quiz_state()
            go_to("quiz")
        return

    q = questions[idx]
    st.markdown(f"**Question {idx+1} of {len(questions)}**")
    st.markdown(f"**{q['question']}**")

    st_autorefresh(interval=1000, key=f"quiz_timer_{idx}")

    if st.session_state.timer_start is None or st.session_state.last_answered:
        st.session_state.timer_start = time.time()
        st.session_state.last_answered = False
        st.session_state.hints_used = 0
        st.session_state.selected_answer = None

    elapsed = int(time.time() - st.session_state.timer_start)
    remaining = max(0, QUESTION_TIME_LIMIT - elapsed)
    st.info(f"Time left: {remaining}s")

    if remaining == 0 and not st.session_state.last_answered:
        st.error(f"⏰ Time's up! Correct answer: {q['answer']}")
        st.session_state.last_answered = True

    if st.session_state.hints_used < MAX_HINTS_PER_QUIZ:
        if st.button("Show Tip"):
            st.session_state.hints_used += 1
            st.info(q.get("tips", "No tips available."))

    with st.form("answer_form"):
        selected = st.radio("Choose an answer:", q["options"], index=0)
        submit = st.form_submit_button("Submit")
        if submit and not st.session_state.last_answered:
            st.session_state.selected_answer = selected
            if selected == q["answer"]:
                st.success("✅ Correct! Great job!")
                celebrate()
                st.session_state.score += 1
            else:
                st.error(f"❌ Wrong. Correct: {q['answer']}")
                st.info(q.get("explanation", ""))
            st.session_state.last_answered = True

    if st.session_state.last_answered:
        if st.button("Next Question"):
            st.session_state.question_index += 1
            st.session_state.last_answered = False
            st.session_state.timer_start = None

def screen_theory():
    animated_header_clickable()
    if back_button():
        return
    st.header(f"Theory: {st.session_state.topic or 'Algebra'}")
    t = st.session_state.topic or "Algebra"
    if t == "Algebra":
        st.write("Algebra is about variables and equations...")
    elif t == "Geometry":
        st.write("Geometry deals with shapes and sizes...")
    else:
        st.write("Content coming soon.")
    if st.button("Back to Topics"):
        go_to("select_topic_theory")

def screen_progress():
    animated_header_clickable()
    if back_button():
        return
    st.header("Your progress")
    user = st.session_state.users.get(st.session_state.user, {})
    hist = user.get("history", [])
    if not hist:
        st.info("No history yet.")
    else:
        for r in reversed(hist[-10:]):
            st.markdown(f"- {r.get('date')}: {r.get('topic')} — {r.get('score')}/{r.get('total')}")
    st.markdown(f"Best score: {user.get('score',0)}")
    if st.button("Back to Menu"):
        go_to("menu")

def screen_leaderboard():
    animated_header_clickable()
    if back_button():
        return
    st.header("Leaderboard")
    users = st.session_state.users
    ranking = sorted([(u["name"], u.get("score", 0)) for u in users.values()], key=lambda x: x[1], reverse=True)
    if not ranking:
        st.info("No scores yet.")
    else:
        for i, (name, s) in enumerate(ranking[:20], start=1):
            highlight = (st.session_state.users.get(st.session_state.user, {}).get("name") == name)
            if highlight:
                st.markdown(f"**{i}. {name} — {s} points (you)**")
            else:
                st.markdown(f"{i}. {name} — {s} points")
    if st.button("Back to Menu"):
        go_to("menu")

def screen_profile():
    animated_header_clickable()
    if back_button():
        return
    st.header("Profile settings")
    user_key = st.session_state.user
    user_data = st.session_state.users[user_key]
    with st.form("profile_form"):
        name = st.text_input("Full name", value=user_data.get("name",""))
        school = st.text_input("School", value=user_data.get("school",""))
        avatar = st.selectbox("Avatar", AVATAR_EMOJIS, index=AVATAR_EMOJIS.index(user_data.get("avatar","😀")) if user_data.get("avatar","😀") in AVATAR_EMOJIS else 0)
        submit = st.form_submit_button("Save profile")
        if submit:
            if not name.strip():
                st.warning("Name cannot be empty.")
            else:
                user_data["name"] = name.strip()
                user_data["school"] = school.strip()
                user_data["avatar"] = avatar
                save_users(st.session_state.users)
                st.success("Profile updated.")
    if st.button("Back to Menu"):
        go_to("menu")

# ----------------------
# Chat helpers
# ----------------------
def chat_display_box(messages, show_usernames=True):
    for m in messages:
        ts = datetime.datetime.fromisoformat(m["timestamp"]).strftime("%H:%M")
        name = st.session_state.users.get(m["user_key"], {}).get("name", m["user_key"])
        avatar = st.session_state.users.get(m["user_key"], {}).get("avatar", "🙂")
        own = (m["user_key"] == st.session_state.user)
        if own:
            st.markdown(f"<div style='text-align:right; margin:6px 0;'><div style='display:inline-block; background:#A9DFBF; padding:8px 12px; border-radius:12px; max-width:80%'>{m['text']}<div style='font-size:10px;color:#333;margin-top:6px'>{ts}</div></div></div>", unsafe_allow_html=True)
        else:
            st.markdown(f"<div style='text-align:left; margin:6px 0;'><div style='display:inline-block; background:#D6EAF8; padding:8px 12px; border-radius:12px; max-width:80%'><b>{avatar} {name}</b><br>{m['text']}<div style='font-size:10px;color:#333;margin-top:6px'>{ts}</div></div></div>", unsafe_allow_html=True)

def screen_chat_public():
    animated_header_clickable()
    if back_button():
        return

    st.header("Public Chat — Study Lounge")
    st_autorefresh(interval=5000, key="chat_public_refresh")
    st.session_state.chat_messages = load_chats()

    # Online users logic
    online_users = [u for u, d in st.session_state.users.items() if d.get("last_login")]
    online_count = len(online_users)
    clicked = st.button(f"🟢 Online users: {online_count}")
    if clicked:
        st.session_state.show_online_users = not st.session_state.show_online_users

    if st.session_state.show_online_users:
        # Horizontal list with avatars and names
        cols = st.columns(online_count if online_count>0 else 1)
        for i, u in enumerate(online_users):
            d = st.session_state.users[u]
            with cols[i]:
                st.markdown(f"<div style='text-align:center; font-size:18px;'>{d.get('avatar','🙂')}<br><small>{d.get('name','?')}</small></div>", unsafe_allow_html=True)

    public_msgs = [m for m in st.session_state.chat_messages if m.get("room") == "public"][-100:]
    chat_display_box(public_msgs)

    with st.form("public_chat_form", clear_on_submit=True):
        text = st.text_input("Type message (max 300 chars):", max_chars=300)
        send = st.form_submit_button("Send")
        if send and text.strip():
            msg = {
                "room": "public",
                "user_key": st.session_state.user,
                "text": text.strip(),
                "timestamp": datetime.datetime.now().isoformat()
            }
            st.session_state.chat_messages.append(msg)
            save_chats(st.session_state.chat_messages)
            st.success("Message sent.")

    if st.button("Clear public chat (teacher only)"):
        u = st.session_state.user
        if st.session_state.users.get(u, {}).get("is_teacher", False):
            st.session_state.chat_messages = [m for m in st.session_state.chat_messages if m.get("room") != "public"]
            save_chats(st.session_state.chat_messages)
            st.success("Public chat cleared.")
        else:
            st.warning("Only teachers can clear the public chat.")

def screen_chat_teacher_request():
    animated_header_clickable()
    if back_button():
        return
    st.header("Chat a Teacher (private)")
    st.write("This opens a private conversation between you and teachers. Teachers with accounts that have `is_teacher: true` in users.json can reply.")

    room = f"teacher_{st.session_state.user}"
    st.session_state.chat_messages = load_chats()
    private_msgs = [m for m in st.session_state.chat_messages if m.get("room") == room][-200:]

    if private_msgs:
        chat_display_box(private_msgs)
    else:
        st.info("No messages in your private thread yet. Send a question to your teacher below.")

    with st.form("teacher_chat_form", clear_on_submit=True):
        text = st.text_area("Write your question to the teacher (be polite and clear):", max_chars=1000)
        send = st.form_submit_button("Send to teacher")
        if send and text.strip():
            msg = {
                "room": room,
                "user_key": st.session_state.user,
                "text": text.strip(),
                "timestamp": datetime.datetime.now().isoformat()
            }
            st.session_state.chat_messages.append(msg)
            save_chats(st.session_state.chat_messages)
            st.success("Your question was saved. Teachers can view and reply in their Teacher Dashboard.")

    st.markdown("---")
    st.markdown("**How teachers reply:** Teachers log in with an account that has `is_teacher: true` in `users.json`. Contact admin to get teacher access.")

def screen_teacher_dashboard():
    animated_header_clickable()
    if not st.session_state.users.get(st.session_state.user, {}).get("is_teacher", False):
        st.error("Teacher dashboard available only to teacher accounts.")
        if st.button("Back to Menu"):
            go_to("menu")
        return
    if back_button():
        return

    st.header("Teacher Dashboard — Private student threads")
    st.session_state.chat_messages = load_chats()

    private = [m for m in st.session_state.chat_messages if m.get("room", "").startswith("teacher_")]
    rooms = {}
    for m in private:
        rooms.setdefault(m["room"], []).append(m)

    for room, msgs in rooms.items():
        student_key = room.replace("teacher_", "")
        st.subheader(f"Thread: {st.session_state.users.get(student_key, {}).get('name',student_key)}")
        chat_display_box(msgs)
        with st.form(f"reply_{room}", clear_on_submit=True):
            reply = st.text_input("Reply to student:")
            submit = st.form_submit_button("Send reply")
            if submit and reply.strip():
                msg = {
                    "room": room,
                    "user_key": st.session_state.user,
                    "text": reply.strip(),
                    "timestamp": datetime.datetime.now().isoformat()
                }
                st.session_state.chat_messages.append(msg)
                save_chats(st.session_state.chat_messages)
                st.success("Reply sent.")

# ----------------------
# Main router
# ----------------------
def main():
    st.set_page_config(page_title="MathFriend", page_icon="🧮", layout="centered", initial_sidebar_state="collapsed")

    if not st.session_state.logged_in:
        if st.session_state.step == "login":
            screen_login()
        elif st.session_state.step == "register":
            screen_register()
        elif st.session_state.step == "login_form":
            screen_login_form()
        else:
            go_to("login")
    else:
        step = st.session_state.step
        if step == "menu":
            screen_menu()
        elif step == "select_topic":
            screen_select_topic()
        elif step == "select_topic_theory":
            screen_select_topic_theory()
        elif step == "quiz":
            screen_quiz()
        elif step == "theory":
            screen_theory()
        elif step == "progress":
            screen_progress()
        elif step == "leaderboard":
            screen_leaderboard()
        elif step == "profile":
            screen_profile()
        elif step == "chat_public":
            screen_chat_public()
        elif step == "chat_teacher_request":
            screen_chat_teacher_request()
        elif step == "teacher_dashboard":
            screen_teacher_dashboard()
        else:
            go_to("menu")
            screen_menu()

if __name__ == "__main__":
    main()

