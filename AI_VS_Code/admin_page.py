"""
pages/admin_page.py
Admin panel — trigger email summaries, view config status, data export.
"""

import streamlit as st
import logging
import json
from datetime import datetime

from config.settings import settings
from services.database import get_all_queries, get_unsummarised_queries
from services.google_sheets import get_sheet_url

logger = logging.getLogger(__name__)


def _status_pill(ok: bool, ok_text: str = "Configured", bad_text: str = "Not set") -> str:
    if ok:
        return f"<span style='background:#064e3b;color:#6ee7b7;padding:3px 12px;border-radius:20px;font-size:12px;font-weight:600'>✅ {ok_text}</span>"
    return f"<span style='background:#450a0a;color:#fca5a5;padding:3px 12px;border-radius:20px;font-size:12px;font-weight:600'>⚠️ {bad_text}</span>"


def render_admin_page():
    st.markdown("""
    <p class='hero-title'>⚙️ Admin Panel</p>
    <p class='hero-sub'>Configuration status, manual controls, and data export</p>
    <br>
    """, unsafe_allow_html=True)

    tab1, tab2, tab3 = st.tabs(["🔧 Config Status", "📧 Email Control", "📤 Data Export"])

    # ── Tab 1: Config Status ─────────────────────────────────────────────────
    with tab1:
        st.markdown("<div class='agent-card'>", unsafe_allow_html=True)
        st.markdown("#### 🔑 API & Service Status")

        checks = {
            "Anthropic API Key": bool(settings.anthropic_api_key),
            "OpenAI API Key (Voice STT)": bool(settings.openai_api_key),
            "SendGrid API Key (Email)": bool(settings.email.sendgrid_api_key),
            "Google Sheet ID": bool(settings.google.sheet_id),
            "Google Service Account JSON": __import__('pathlib').Path(settings.google.service_account_json).exists(),
        }

        for label, status in checks.items():
            st.markdown(
                f"<div style='display:flex;align-items:center;gap:12px;margin:8px 0'>"
                f"<span style='color:#9ca3af;width:240px'>{label}</span>"
                f"{_status_pill(status)}</div>",
                unsafe_allow_html=True,
            )

        st.markdown("<br>")
        st.markdown("#### 🗄️ Database Info")
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

        st.markdown("#### ⏰ Email Schedule")
        st.markdown(
            f"<div style='background:#0d1321;padding:12px 16px;border-radius:8px;"
            f"font-size:13px;color:#a78bfa'>"
            f"📅 Daily summaries fire at <b>{settings.email.summary_hour:02d}:{settings.email.summary_minute:02d} UTC</b><br>"
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
                f"<div style='background:#0d1321;padding:12px;border-radius:8px;text-align:center;margin-bottom:12px'>"
                f"📦 <b>{len(product_q)}</b> unsent product queries"
                f"</div>",
                unsafe_allow_html=True,
            )
        with c2:
            st.markdown(
                f"<div style='background:#0d1321;padding:12px;border-radius:8px;text-align:center;margin-bottom:12px'>"
                f"💳 <b>{len(payment_q)}</b> unsent payment queries"
                f"</div>",
                unsafe_allow_html=True,
            )

        st.markdown("""
        <div style='padding:12px;background:#1c1f26;border-left:3px solid #f59e0b;
                    border-radius:0 8px 8px 0;font-size:13px;color:#fbbf24;margin-bottom:16px'>
          ⚠️ This will immediately send summary emails to both departments
          and mark all queued queries as <b>emailed</b>. Use carefully.
        </div>
        """, unsafe_allow_html=True)

        if st.button("🚀 Send All Department Summaries NOW", use_container_width=True, type="primary"):
            with st.spinner("Generating summaries and sending emails..."):
                try:
                    from utils.scheduler import trigger_now
                    results = trigger_now()
                    for dept, res in results.items():
                        if res.get("sent"):
                            st.success(f"✅ {dept.title()} email sent ({res['count']} queries) → {res.get('recipient','')}")
                        elif res.get("reason") == "no_queries":
                            st.info(f"ℹ️ {dept.title()}: no new queries to summarise.")
                        else:
                            st.error(f"❌ {dept.title()} email failed: {res.get('reason', 'unknown error')}")
                except Exception as exc:
                    st.error(f"Error: {exc}")

        st.markdown("</div>", unsafe_allow_html=True)

        # Send to single department
        st.markdown("<div class='agent-card'>", unsafe_allow_html=True)
        st.markdown("#### 🎯 Send to Specific Department")
        dept_choice = st.selectbox("Department", ["product", "payment"])
        custom_email = st.text_input(
            "Override recipient email (optional)",
            placeholder="Leave blank to use configured address",
        )

        if st.button(f"Send {dept_choice.title()} Summary", use_container_width=True):
            queries = get_unsummarised_queries(dept_choice)
            if not queries:
                st.info(f"No unsummarised {dept_choice} queries found.")
            else:
                with st.spinner("Generating AI summary..."):
                    try:
                        from services.ai_agent import generate_department_summary
                        from services.email_service import _send_via_sendgrid, _html_template, log_email, mark_queries_emailed
                        from config.settings import settings as cfg

                        q_dicts = [q.to_dict() for q in queries]
                        summary = generate_department_summary(q_dicts, dept_choice)
                        date_str = datetime.utcnow().strftime("%B %d, %Y")
                        dept_name = f"{dept_choice.title()} Team"
                        html = _html_template(dept_name, summary, len(q_dicts), date_str)

                        recipient = custom_email.strip() or (
                            cfg.email.product_dept_email if dept_choice == "product"
                            else cfg.email.payment_dept_email
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
