"""
pages/chat_page.py
Main customer-facing chat + voice interface.
"""

import streamlit as st
import logging
from datetime import datetime

from services.ai_agent import process_query
from services.database import save_query
from services.google_sheets import append_query
from utils.voice_utils import transcribe_audio, synthesize_speech, audio_bytes_to_base64

logger = logging.getLogger(__name__)

CATEGORY_BADGE = {
    "product": "<span class='badge-product'>📦 Product</span>",
    "payment": "<span class='badge-payment'>💳 Payment</span>",
    "unknown": "<span class='badge-unknown'>❓ General</span>",
}

SENTIMENT_ICON = {
    "positive": "😊",
    "neutral": "😐",
    "negative": "😟",
}


def _persist_interaction(user_msg: str, answer: str, category: str, sentiment: str, escalate: bool, channel: str = "chat"):
    """Save to DB + Google Sheets and store result in session state."""
    try:
        record = save_query(
            session_id=st.session_state.session_id,
            raw_query=user_msg,
            ai_response=answer,
            category=category,
            channel=channel,
            customer_name=st.session_state.customer_name or None,
            customer_email=st.session_state.customer_email or None,
            sentiment=sentiment,
        )
        # Async-safe: GSheet sync
        append_query(
            record_id=record.id,
            session_id=st.session_state.session_id,
            customer_name=st.session_state.customer_name or None,
            customer_email=st.session_state.customer_email or None,
            channel=channel,
            category=category,
            sentiment=sentiment,
            raw_query=user_msg,
            ai_response=answer,
            escalated=escalate,
        )
        return record.id
    except Exception as exc:
        logger.error("Persist failed: %s", exc)
        return None


def render_chat_messages():
    """Render all messages in the conversation."""
    if not st.session_state.conversation:
        st.markdown("""
        <div style='text-align:center; padding: 48px 0; color:#4b5563'>
          <div style='font-size:48px; margin-bottom:12px'>🎙️</div>
          <div style='font-size:16px; color:#6b7280'>
            Hello! I'm your AI assistant.<br>
            Ask me anything about our <b style='color:#60a5fa'>products</b>
            or <b style='color:#a78bfa'>payments</b>.
          </div>
        </div>
        """, unsafe_allow_html=True)
        return

    chat_html = "<div class='chat-scroll'>"
    for msg in st.session_state.conversation:
        role = msg["role"]
        content = msg["content"]
        meta = msg.get("meta", {})
        ts = msg.get("ts", "")

        if role == "user":
            channel_icon = "🎤" if meta.get("channel") == "voice" else "💬"
            chat_html += f"""
            <div class='chat-user'>{content}</div>
            <div class='chat-meta' style='text-align:right'>{channel_icon} {ts}</div>
            """
        else:
            category = meta.get("category", "unknown")
            sentiment = meta.get("sentiment", "neutral")
            escalate = meta.get("escalate", False)
            badge = CATEGORY_BADGE.get(category, CATEGORY_BADGE["unknown"])
            s_icon = SENTIMENT_ICON.get(sentiment, "😐")
            escalate_tag = " 🚨 <span style='color:#f87171;font-size:11px'>Escalated</span>" if escalate else ""

            chat_html += f"""
            <div class='chat-agent'>{content}</div>
            <div class='chat-meta'>{badge} &nbsp; {s_icon} {sentiment}{escalate_tag} &nbsp; · &nbsp; {ts}</div>
            """

    chat_html += "</div>"
    st.markdown(chat_html, unsafe_allow_html=True)


def render_chat_page():
    # ── Header ──────────────────────────────────────────────────────────────
    col_title, col_clear = st.columns([4, 1])
    with col_title:
        st.markdown("""
        <p class='hero-title'>🎙️ AI Voice Agent</p>
        <p class='hero-sub'>Ask about products, payments, or any support query</p>
        """, unsafe_allow_html=True)
    with col_clear:
        st.markdown("<div style='margin-top:16px'>", unsafe_allow_html=True)
        if st.button("🗑️ Clear Chat", use_container_width=True):
            st.session_state.conversation = []
            st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Layout: Chat area (left) + Input panel (right) ──────────────────────
    chat_col, input_col = st.columns([3, 2], gap="large")

    with chat_col:
        st.markdown("<div class='agent-card'>", unsafe_allow_html=True)
        render_chat_messages()
        st.markdown("</div>", unsafe_allow_html=True)

    with input_col:
        # ── Text input ──────────────────────────────────────────────────────
        st.markdown("<div class='agent-card'>", unsafe_allow_html=True)
        st.markdown("#### 💬 Text Query")
        user_text = st.text_area(
            "Type your question",
            placeholder="e.g. How do I track my order? / I was charged twice...",
            height=100,
            label_visibility="collapsed",
            key="text_input",
        )
        send_btn = st.button("✈️  Send Message", use_container_width=True, key="send_text")

        if send_btn and user_text.strip():
            _handle_text_query(user_text.strip())

        st.markdown("</div>", unsafe_allow_html=True)

        # ── Voice input ──────────────────────────────────────────────────────
        st.markdown("<div class='agent-card'>", unsafe_allow_html=True)
        st.markdown("#### 🎤 Voice Query")
        st.markdown(
            "<div style='font-size:12px; color:#6b7280; margin-bottom:8px'>"
            "Upload a WAV/WebM audio file or use the recorder below.</div>",
            unsafe_allow_html=True,
        )
        audio_file = st.file_uploader(
            "Upload audio",
            type=["wav", "mp3", "webm", "ogg", "m4a"],
            label_visibility="collapsed",
            key="voice_upload",
        )
        process_voice_btn = st.button("🎙️  Transcribe & Send", use_container_width=True, key="send_voice")

        if process_voice_btn and audio_file:
            _handle_voice_query(audio_file)

        # Audio recorder hint
        st.markdown("""
        <div style='margin-top:12px; padding:12px; background:#0d1321;
                    border-radius:10px; border:1px dashed #1e3a5f; text-align:center;
                    font-size:12px; color:#4b5563'>
          🎙️ <b>Browser recording tip:</b><br>
          Use your OS voice recorder and upload the file above,<br>
          or integrate <code>streamlit-webrtc</code> for live mic capture.
        </div>
        """, unsafe_allow_html=True)

        st.markdown("</div>", unsafe_allow_html=True)

        # ── Quick prompts ──────────────────────────────────────────────────
        st.markdown("<div class='agent-card'>", unsafe_allow_html=True)
        st.markdown("#### ⚡ Quick Questions")
        quick_prompts = [
            ("📦 Product availability", "Is the premium plan still available?"),
            ("💳 Refund request", "I need a refund for my last payment."),
            ("📋 Pricing info", "What are your current pricing plans?"),
            ("🔧 Technical issue", "The product feature is not working correctly."),
        ]
        for label, prompt in quick_prompts:
            if st.button(label, use_container_width=True, key=f"quick_{label}"):
                _handle_text_query(prompt)

        st.markdown("</div>", unsafe_allow_html=True)


# ── Query handlers ─────────────────────────────────────────────────────────────

def _handle_text_query(user_msg: str):
    ts = datetime.now().strftime("%H:%M")
    history = [
        {"role": m["role"], "content": m["content"]}
        for m in st.session_state.conversation
    ]

    with st.spinner("🤔 Thinking..."):
        try:
            answer, category, sentiment, escalate = process_query(user_msg, history)
        except Exception as exc:
            st.error(f"AI error: {exc}")
            return

    # Append to conversation
    st.session_state.conversation.append({
        "role": "user",
        "content": user_msg,
        "ts": ts,
        "meta": {"channel": "chat"},
    })
    st.session_state.conversation.append({
        "role": "assistant",
        "content": answer,
        "ts": ts,
        "meta": {"category": category, "sentiment": sentiment, "escalate": escalate},
    })

    _persist_interaction(user_msg, answer, category, sentiment, escalate, channel="chat")

    # Auto-play TTS
    _maybe_play_tts(answer)
    st.rerun()


def _handle_voice_query(audio_file):
    audio_bytes = audio_file.read()
    ts = datetime.now().strftime("%H:%M")

    with st.spinner("🎙️ Transcribing audio..."):
        transcript = transcribe_audio(audio_bytes, mime_type=audio_file.type or "audio/wav")

    if not transcript:
        st.warning(
            "⚠️ Could not transcribe audio. "
            "Ensure OPENAI_API_KEY is set, or type your query in the text box."
        )
        return

    st.success(f"📝 Transcribed: *{transcript}*")

    history = [
        {"role": m["role"], "content": m["content"]}
        for m in st.session_state.conversation
    ]

    with st.spinner("🤔 Generating response..."):
        try:
            answer, category, sentiment, escalate = process_query(transcript, history)
        except Exception as exc:
            st.error(f"AI error: {exc}")
            return

    st.session_state.conversation.append({
        "role": "user",
        "content": transcript,
        "ts": ts,
        "meta": {"channel": "voice"},
    })
    st.session_state.conversation.append({
        "role": "assistant",
        "content": answer,
        "ts": ts,
        "meta": {"category": category, "sentiment": sentiment, "escalate": escalate},
    })

    _persist_interaction(transcript, answer, category, sentiment, escalate, channel="voice")
    _maybe_play_tts(answer)
    st.rerun()


def _maybe_play_tts(text: str):
    """Synthesise speech and embed an autoplay audio element."""
    try:
        audio_bytes = synthesize_speech(text)
        if audio_bytes:
            data_uri = audio_bytes_to_base64(audio_bytes)
            st.markdown(
                f'<audio autoplay style="display:none"><source src="{data_uri}" type="audio/mp3"></audio>',
                unsafe_allow_html=True,
            )
    except Exception as exc:
        logger.debug("TTS skipped: %s", exc)
