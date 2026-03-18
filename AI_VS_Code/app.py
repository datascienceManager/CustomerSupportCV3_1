"""
app.py
AI Voice Agent — Main Streamlit Application Entry Point
"""

import uuid
import logging
import streamlit as st
from pathlib import Path

# ── Page config (must be FIRST Streamlit call) ────────────────────────────────
st.set_page_config(
    page_title="AI Voice Agent",
    page_icon="🎙️",
    layout="wide",
    initial_sidebar_state="expanded",
)

from config.settings import settings
from utils.scheduler import start_scheduler

logger = logging.getLogger(__name__)

# ── Start background scheduler once ──────────────────────────────────────────
if "scheduler_started" not in st.session_state:
    start_scheduler()
    st.session_state.scheduler_started = True

# ── Session initialisation ────────────────────────────────────────────────────
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())[:8]

if "conversation" not in st.session_state:
    st.session_state.conversation = []          # list of {role, content, meta}

if "customer_name" not in st.session_state:
    st.session_state.customer_name = ""

if "customer_email" not in st.session_state:
    st.session_state.customer_email = ""

if "page" not in st.session_state:
    st.session_state.page = "chat"


# ── Custom CSS ────────────────────────────────────────────────────────────────
def inject_css():
    st.markdown("""
    <style>
      /* ── Google Font ── */
      @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@300;400;500;600;700&family=Space+Grotesk:wght@500;700&display=swap');

      html, body, [class*="css"] {
        font-family: 'DM Sans', sans-serif;
      }

      /* ── Global background ── */
      .stApp {
        background: linear-gradient(135deg, #0f1117 0%, #131720 50%, #0a0d14 100%);
        color: #e8eaf0;
      }

      /* ── Sidebar ── */
      section[data-testid="stSidebar"] {
        background: linear-gradient(180deg, #111827 0%, #0d1321 100%);
        border-right: 1px solid #1e2b42;
      }

      /* ── Card component ── */
      .agent-card {
        background: linear-gradient(135deg, #141e2e 0%, #111827 100%);
        border: 1px solid #1e3a5f;
        border-radius: 16px;
        padding: 24px;
        margin-bottom: 16px;
        box-shadow: 0 4px 24px rgba(0,0,0,0.3);
      }

      /* ── Chat bubble ── */
      .chat-user {
        background: linear-gradient(135deg, #1a56db 0%, #1e40af 100%);
        color: white;
        border-radius: 18px 18px 4px 18px;
        padding: 12px 18px;
        margin: 8px 0 8px 15%;
        font-size: 15px;
        line-height: 1.5;
        box-shadow: 0 2px 8px rgba(26,86,219,0.3);
      }
      .chat-agent {
        background: linear-gradient(135deg, #1f2937 0%, #111827 100%);
        color: #e5e7eb;
        border: 1px solid #374151;
        border-radius: 18px 18px 18px 4px;
        padding: 12px 18px;
        margin: 8px 15% 8px 0;
        font-size: 15px;
        line-height: 1.5;
      }
      .chat-meta {
        font-size: 11px;
        color: #6b7280;
        margin-top: 4px;
        padding: 0 4px;
      }

      /* ── Category badge ── */
      .badge-product {
        background: linear-gradient(135deg,#065f46,#047857);
        color: #d1fae5; border-radius: 20px;
        padding: 3px 12px; font-size: 12px; font-weight: 600;
      }
      .badge-payment {
        background: linear-gradient(135deg,#1e3a8a,#1d4ed8);
        color: #bfdbfe; border-radius: 20px;
        padding: 3px 12px; font-size: 12px; font-weight: 600;
      }
      .badge-unknown {
        background: linear-gradient(135deg,#374151,#4b5563);
        color: #d1d5db; border-radius: 20px;
        padding: 3px 12px; font-size: 12px; font-weight: 600;
      }

      /* ── Input overrides ── */
      .stTextInput > div > div > input,
      .stTextArea textarea {
        background: #1a2235 !important;
        color: #e5e7eb !important;
        border: 1px solid #2d3f5e !important;
        border-radius: 10px !important;
      }

      /* ── Buttons ── */
      .stButton > button {
        background: linear-gradient(135deg, #1a56db 0%, #1e40af 100%) !important;
        color: white !important;
        border: none !important;
        border-radius: 10px !important;
        font-family: 'DM Sans', sans-serif !important;
        font-weight: 600 !important;
        padding: 8px 20px !important;
        transition: transform 0.15s ease, box-shadow 0.15s ease !important;
      }
      .stButton > button:hover {
        transform: translateY(-1px) !important;
        box-shadow: 0 4px 12px rgba(26,86,219,0.4) !important;
      }

      /* ── Metric cards ── */
      [data-testid="metric-container"] {
        background: #141e2e !important;
        border: 1px solid #1e3a5f !important;
        border-radius: 12px !important;
        padding: 16px !important;
      }

      /* ── Scrollable chat area ── */
      .chat-scroll {
        max-height: 520px;
        overflow-y: auto;
        padding: 8px;
        scrollbar-width: thin;
        scrollbar-color: #374151 transparent;
      }

      /* ── Title ── */
      .hero-title {
        font-family: 'Space Grotesk', sans-serif;
        font-size: 2.2rem;
        font-weight: 700;
        background: linear-gradient(135deg, #60a5fa 0%, #a78bfa 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin: 0;
      }
      .hero-sub {
        color: #6b7280;
        font-size: 14px;
        margin-top: 4px;
      }

      /* ── Status dot ── */
      .status-dot {
        width: 8px; height: 8px; border-radius: 50%;
        display: inline-block; margin-right: 6px;
        background: #10b981;
        box-shadow: 0 0 6px #10b981;
        animation: pulse 2s infinite;
      }
      @keyframes pulse {
        0%,100% { opacity:1; } 50% { opacity:.4; }
      }
    </style>
    """, unsafe_allow_html=True)


# ── Sidebar navigation ────────────────────────────────────────────────────────
def render_sidebar():
    with st.sidebar:
        st.markdown("""
        <div style='text-align:center; padding: 20px 0 28px'>
          <div style='font-size:48px'>🎙️</div>
          <div style='font-family:"Space Grotesk",sans-serif; font-size:18px;
                      font-weight:700; color:#60a5fa; margin-top:8px'>
            AI Voice Agent
          </div>
          <div style='color:#4b5563; font-size:12px; margin-top:4px'>
            Powered by Claude AI
          </div>
        </div>
        """, unsafe_allow_html=True)

        st.markdown("---")
        st.markdown("### 🧭 Navigation")

        pages = {
            "chat": ("💬", "Chat / Voice"),
            "dashboard": ("📊", "Dashboard"),
            "admin": ("⚙️", "Admin"),
        }

        for key, (icon, label) in pages.items():
            is_active = st.session_state.page == key
            style = "background:#1a2b4a; border-left:3px solid #1a56db;" if is_active else ""
            if st.button(
                f"{icon}  {label}",
                key=f"nav_{key}",
                use_container_width=True,
            ):
                st.session_state.page = key
                st.rerun()

        st.markdown("---")
        st.markdown("### 👤 Your Info")
        name = st.text_input("Name (optional)", value=st.session_state.customer_name, key="sidebar_name")
        email = st.text_input("Email (optional)", value=st.session_state.customer_email, key="sidebar_email")
        if name != st.session_state.customer_name:
            st.session_state.customer_name = name
        if email != st.session_state.customer_email:
            st.session_state.customer_email = email

        st.markdown("---")
        st.markdown(f"""
        <div style='font-size:12px; color:#4b5563; text-align:center'>
          <span class='status-dot'></span>Session: <code style='color:#6b7280'>{st.session_state.session_id}</code>
          <br><br>🌍 {settings.company_name}
        </div>
        """, unsafe_allow_html=True)


# ── Page router ───────────────────────────────────────────────────────────────
def main():
    inject_css()
    render_sidebar()

    page = st.session_state.page

    if page == "chat":
        from pages.chat_page import render_chat_page
        render_chat_page()
    elif page == "dashboard":
        from pages.dashboard_page import render_dashboard_page
        render_dashboard_page()
    elif page == "admin":
        from pages.admin_page import render_admin_page
        render_admin_page()


if __name__ == "__main__":
    main()
