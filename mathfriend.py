import streamlit as st

# --- Smooth Splash Screen CSS + HTML ---
splash_html = """
<style>
@keyframes smoothFadeZoom {
    0% {opacity: 0; transform: scale(0.85);}
    30% {opacity: 1; transform: scale(1);}
    70% {opacity: 1; transform: scale(1.02);}
    100% {opacity: 0; transform: scale(1);}
}
.splash-container {
    position: fixed;
    top: 0;
    left: 0;
    width: 100vw;
    height: 100vh;
    background-color: white;
    display: flex;
    justify-content: center;
    align-items: center;
    z-index: 9999;
    animation: smoothFadeZoom 2.8s ease-in-out forwards;
    user-select: none;
}
.splash-text {
    font-size: clamp(2rem, 5vw, 3.5rem);
    font-weight: bold;
    color: #007BFF;
    font-family: 'Segoe UI', Tahoma, sans-serif;
    text-align: center;
    letter-spacing: 1px;
}
</style>

<div class="splash-container" id="splash">
    <div class="splash-text">MathFriend</div>
</div>

<script>
setTimeout(function(){
    document.getElementById("splash").style.display = "none";
}, 2800);
</script>
"""

# Show splash HTML overlay
st.markdown(splash_html, unsafe_allow_html=True)

# --- Use Streamlit containers for proper layout and centering ---
st.markdown("""
<style>
.centered-container {
    display: flex;
    justify-content: center;
    align-items: center;
    height: 100vh;
}
.login-card {
    width: 100%;
    max-width: 380px;
    background: white;
    border: 1px solid #ddd;
    border-radius: 12px;
    box-shadow: 0 6px 20px rgb(0 0 0 / 0.1);
    padding: 28px 24px;
    box-sizing: border-box;
    text-align: center;
}
.login-title {
    font-weight: 700;
    font-size: 1.9rem;
    margin-bottom: 8px;
    color: #007BFF;
}
.login-subtitle {
    color: #475569;
    margin-bottom: 22px;
    font-size: 1rem;
}
.footer-note {
    margin-top: 12px;
    font-size: 0.85rem;
    color: #64748b;
    text-align: center;
}
</style>
""", unsafe_allow_html=True)

# The following is a common trick to center elements in Streamlit
col1, col2, col3 = st.columns([1, 2, 1])

with col2:
    st.markdown("<div class='login-card'>", unsafe_allow_html=True)
    st.markdown("<div class='login-title'>🔐 Login to MathFriend</div>", unsafe_allow_html=True)
    st.markdown("<div class='login-subtitle'>Please enter your username and password</div>", unsafe_allow_html=True)
    
    with st.form("login_form"):
        username = st.text_input("Username", key="login_username")
        password = st.text_input("Password", type="password", key="login_password")
        submitted = st.form_submit_button("Login")
        
        if submitted:
            if not username or not password:
                st.error("Both username and password are required.")
            else:
                st.success(f"Welcome, {username}!")
                # Add login logic here

    st.markdown("</div>", unsafe_allow_html=True)
    st.markdown("<div class='footer-note'>Built with care by Derrick Kwaku Togodui</div>", unsafe_allow_html=True)