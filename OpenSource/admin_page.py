"""
pages/admin_page.py
Admin panel — Ollama status, trigger email summaries, view config, data export.
"""

import streamlit as st
import logging
import json
from datetime import datetime
from pathlib import Path

from config.settings import settings
from services.database import get_all_queries, get_unsummarised_queries
from services.google_sheets import get_sheet_url
from services.ai_agent import check_ollama_health, list_available_models

logger = logging.getLogger(__name__)


def _status_pill(ok: bool, ok_text: str = "Configured", bad_text: str = "Not set") -> str:
    if ok:
        return (
            f"<span style='background:#064e3b;color:#6ee7b7;padding:3px 12px;"
            f"border-radius:20px;font-size:12px;font-weight:600'>✅ {ok_text}</span>"
        )
    return (
        f"<span style='background:#450a0a;color:#fca5a5;padding:3px 12px;"
        f"border-radius:20px;font-size:12px;font-weight:600'>⚠️ {bad_text}</span>"
    )


def render_admin_page():
    st.markdown("""
    <p class='hero-title'>⚙️ Admin Panel</p>
    <p class='hero-sub'>Ollama status, manual controls, and data export</p>
    <br>
    """, unsafe_allow_html=True)

    tab1, tab2, tab3 = st.tabs(["🤖 LLM & Config", "📧 Email Control", "📤 Data Export"])

    # ── Tab 1: Config & Ollama Status ────────────────────────────────────────
    with tab1:

        # ── Ollama health card ─────────────────────────────────────────────
        st.markdown("<div class='agent-card'>", unsafe_allow_html=True)
        st.markdown("#### 🤖 Ollama LLM Status")

        col_refresh, _ = st.columns([1, 3])
        with col_refresh:
            do_check = st.button("🔄 Check Status", use_container_width=True)

        if do_check or "ollama_health" not in st.session_state:
            with st.spinner("Checking Ollama..."):
                st.session_state.ollama_health = check_ollama_health()

        health = st.session_state.get("ollama_health", {})
        online = health.get("online", False)
        models = health.get("models", [])
        err = health.get("error")

        if online:
            st.markdown(
                f"<div style='background:#052e16;border:1px solid #166534;border-radius:10px;"
                f"padding:14px 18px;margin:10px 0'>"
                f"<span style='color:#4ade80;font-size:15px;font-weight:700'>● Ollama Online</span><br>"
                f"<span style='color:#86efac;font-size:13px'>URL: {settings.ollama.base_url}</span><br>"
                f"<span style='color:#86efac;font-size:13px'>Active model: "
                f"<b style='color:#a3e635'>{settings.ollama.model}</b></span>"
                f"</div>",
                unsafe_allow_html=True,
            )
            if models:
                st.markdown("**📦 Installed models:**")
                cols = st.columns(3)
                for i, m in enumerate(models):
                    is_active = (m == settings.ollama.model or
                                 m.split(":")[0] == settings.ollama.model.split(":")[0])
                    badge_color = "#a3e635" if is_active else "#6b7280"
                    cols[i % 3].markdown(
                        f"<div style='background:#0d1321;border:1px solid #1e3a5f;"
                        f"border-radius:8px;padding:8px 12px;font-size:12px;"
                        f"color:{badge_color};margin:4px 0'>"
                        f"{'★ ' if is_active else ''}{m}</div>",
                        unsafe_allow_html=True,
                    )
        else:
            st.markdown(
                f"<div style='background:#450a0a;border:1px solid #7f1d1d;border-radius:10px;"
                f"padding:14px 18px;margin:10px 0'>"
                f"<span style='color:#f87171;font-size:15px;font-weight:700'>● Ollama Offline</span><br>"
                f"<span style='color:#fca5a5;font-size:13px'>{err or 'Cannot reach Ollama server'}</span>"
                f"</div>",
                unsafe_allow_html=True,
            )
            st.markdown("""
            <div style='background:#1c1f26;border-left:3px solid #f59e0b;border-radius:0 8px 8px 0;
                        padding:12px 16px;font-size:13px;color:#fbbf24;margin-top:8px'>
            <b>How to start Ollama:</b><br><br>
            <code style='color:#e5e7eb'>
            # macOS / Linux<br>
            brew install ollama &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;# or: curl https://ollama.com/install.sh | sh<br>
            ollama serve<br>
            ollama pull llama3.2<br><br>
            # Windows<br>
            # Download from https://ollama.com/download
            </code>
            </div>
            """, unsafe_allow_html=True)

        # ── Model switcher ─────────────────────────────────────────────────
        if online and models:
            st.markdown("<br>**🔀 Switch Active Model**")
            current_model = settings.ollama.model
            selected = st.selectbox(
                "Select model",
                options=models,
                index=models.index(current_model) if current_model in models else 0,
                label_visibility="collapsed",
            )
            if st.button("Apply Model", use_container_width=False):
                settings.ollama.model = selected
                st.success(f"✅ Active model switched to **{selected}** for this session.")
                st.info("To make permanent, set `OLLAMA_MODEL={selected}` in your .env file.")

        st.markdown("</div>", unsafe_allow_html=True)

        # ── Other services ─────────────────────────────────────────────────
        st.markdown("<div class='agent-card'>", unsafe_allow_html=True)
        st.markdown("#### 🔑 Service Configuration")

        checks = {
            "Ollama Server": online,
            "OpenAI API Key (Voice STT — optional)": bool(settings.openai_api_key),
            "SendGrid API Key (Email)": bool(settings.email.sendgrid_api_key),
            "Google Sheet ID": bool(settings.google.sheet_id),
            "Google Service Account JSON": Path(settings.google.service_account_json).exists(),
        }
        for label, status in checks.items():
            st.markdown(
                f"<div style='display:flex;align-items:center;gap:12px;margin:8px 0'>"
                f"<span style='color:#9ca3af;width:280px'>{label}</span>"
                f"{_status_pill(status)}</div>",
                unsafe_allow_html=True,
            )

        st.markdown("<br>")
        st.markdown("#### 🗄️ Database")
        db_type = settings.db.db_type.upper()
        db_url = settings.db.connection_url
        masked = db_url.split("@")[-1] if "@" in db_url else db_url
        st.markdown(
            f"<div style='background:#0d1321;padding:12px 16px;border-radius:8px;"
            f"font-family:monospace;font-size:13px;color:#60a5fa'>"
            f"🗄️ Type: <b>{db_type}</b><br>📍 {masked}</div>",
            unsafe_allow_html=True,
        )

        sheet_url = get_sheet_url()
        if sheet_url:
            st.markdown(
                f"<br><a href='{sheet_url}' target='_blank' "
                f"style='color:#60a5fa;font-size:13px'>🔗 Open Google Sheet ↗</a>",
                unsafe_allow_html=True,
            )

        st.markdown("<br>**⏰ Email Schedule**")
        st.markdown(
            f"<div style='background:#0d1321;padding:12px 16px;border-radius:8px;"
            f"font-size:13px;color:#a78bfa'>"
            f"📅 Daily at <b>{settings.email.summary_hour:02d}:{settings.email.summary_minute:02d} UTC</b><br>"
            f"📦 Product → <code style='color:#60a5fa'>{settings.email.product_dept_email}</code><br>"
            f"💳 Payment → <code style='color:#60a5fa'>{settings.email.payment_dept_email}</code>"
            f"</div>",
            unsafe_allow_html=True,
        )
        st.markdown("</div>", unsafe_allow_html=True)

    # ── Tab 2: Email Control ─────────────────────────────────────────────────
    with tab2:
        st.markdown("<div class='agent-card'>", unsafe_allow_html=True)
        st.markdown("#### 📧 Manual Email Trigger")

        product_q = get_unsummarised_queries("product")
        payment_q = get_unsummarised_queries("payment")

        c1, c2 = st.columns(2)
        with c1:
            st.markdown(
                f"<div style='background:#0d1321;padding:12px;border-radius:8px;"
                f"text-align:center;margin-bottom:12px'>"
                f"📦 <b>{len(product_q)}</b> unsent product queries</div>",
                unsafe_allow_html=True,
            )
        with c2:
            st.markdown(
                f"<div style='background:#0d1321;padding:12px;border-radius:8px;"
                f"text-align:center;margin-bottom:12px'>"
                f"💳 <b>{len(payment_q)}</b> unsent payment queries</div>",
                unsafe_allow_html=True,
            )

        st.markdown("""
        <div style='padding:12px;background:#1c1f26;border-left:3px solid #f59e0b;
                    border-radius:0 8px 8px 0;font-size:13px;color:#fbbf24;margin-bottom:16px'>
          ⚠️ This sends summary emails to both departments and marks all queued queries as <b>emailed</b>.
        </div>
        """, unsafe_allow_html=True)

        if st.button("🚀 Send All Department Summaries NOW", use_container_width=True, type="primary"):
            with st.spinner("Generating Ollama summaries and sending emails..."):
                try:
                    from utils.scheduler import trigger_now
                    results = trigger_now()
                    for dept, res in results.items():
                        if res.get("sent"):
                            st.success(f"✅ {dept.title()} email sent ({res['count']} queries) → {res.get('recipient','')}")
                        elif res.get("reason") == "no_queries":
                            st.info(f"ℹ️ {dept.title()}: no new queries to summarise.")
                        else:
                            st.error(f"❌ {dept.title()} email failed: {res.get('reason', 'unknown')}")
                except Exception as exc:
                    st.error(f"Error: {exc}")
        st.markdown("</div>", unsafe_allow_html=True)

        st.markdown("<div class='agent-card'>", unsafe_allow_html=True)
        st.markdown("#### 🎯 Send to Specific Department")
        dept_choice = st.selectbox("Department", ["product", "payment"])
        custom_email = st.text_input("Override recipient email (optional)")

        if st.button(f"Send {dept_choice.title()} Summary", use_container_width=True):
            queries = get_unsummarised_queries(dept_choice)
            if not queries:
                st.info(f"No unsummarised {dept_choice} queries found.")
            else:
                with st.spinner(f"Ollama is generating summary for {len(queries)} queries..."):
                    try:
                        from services.ai_agent import generate_department_summary
                        from services.email_service import (
                            _send_via_sendgrid, _html_template,
                            log_email, mark_queries_emailed,
                        )
                        q_dicts = [q.to_dict() for q in queries]
                        summary = generate_department_summary(q_dicts, dept_choice)
                        date_str = datetime.utcnow().strftime("%B %d, %Y")
                        dept_name = f"{dept_choice.title()} Team"
                        html = _html_template(dept_name, summary, len(q_dicts), date_str)
                        recipient = custom_email.strip() or (
                            settings.email.product_dept_email if dept_choice == "product"
                            else settings.email.payment_dept_email
                        )
                        success = _send_via_sendgrid(recipient, f"Query Summary - {dept_name}", html)
                        if success:
                            mark_queries_emailed([q.id for q in queries])
                            st.success(f"✅ Email sent to {recipient}")
                            with st.expander("📋 Preview Summary"):
                                st.markdown(summary)
                        else:
                            st.error("Failed to send email.")
                    except Exception as exc:
                        st.error(f"Error: {exc}")
        st.markdown("</div>", unsafe_allow_html=True)

    # ── Tab 3: Data Export ────────────────────────────────────────────────────
    with tab3:
        st.markdown("<div class='agent-card'>", unsafe_allow_html=True)
        st.markdown("#### 📤 Export Query Data")

        all_queries = get_all_queries(limit=5000)
        if not all_queries:
            st.info("No data to export yet.")
        else:
            import pandas as pd
            df = pd.DataFrame(all_queries)
            csv = df.to_csv(index=False).encode("utf-8")

            st.download_button(
                label=f"⬇️ Download CSV ({len(all_queries)} rows)",
                data=csv,
                file_name=f"ai_voice_agent_queries_{datetime.utcnow().strftime('%Y%m%d_%H%M')}.csv",
                mime="text/csv",
                use_container_width=True,
            )
            json_data = json.dumps(all_queries, default=str, indent=2).encode("utf-8")
            st.download_button(
                label="⬇️ Download JSON",
                data=json_data,
                file_name=f"ai_voice_agent_queries_{datetime.utcnow().strftime('%Y%m%d_%H%M')}.json",
                mime="application/json",
                use_container_width=True,
            )
            st.markdown("<br>**Preview (last 10 rows)**")
            st.dataframe(df.head(10), use_container_width=True, hide_index=True)
        st.markdown("</div>", unsafe_allow_html=True)
