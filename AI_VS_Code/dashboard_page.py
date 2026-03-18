"""
pages/dashboard_page.py
Analytics dashboard — query statistics, category breakdown, recent queries table.
"""

import streamlit as st
import pandas as pd
import logging
from collections import Counter

from services.database import get_all_queries, get_session
from services.database import CustomerQuery, EmailLog

logger = logging.getLogger(__name__)


def _load_data():
    """Return (queries_df, email_logs_df)."""
    rows = get_all_queries(limit=1000)
    df = pd.DataFrame(rows) if rows else pd.DataFrame(
        columns=["id","session_id","customer_name","channel","category",
                 "sentiment","raw_query","ai_response","status","created_at"]
    )
    if not df.empty and "created_at" in df.columns:
        df["created_at"] = pd.to_datetime(df["created_at"], errors="coerce")

    db = get_session()
    try:
        logs = db.query(EmailLog).order_by(EmailLog.sent_at.desc()).limit(50).all()
        email_df = pd.DataFrame([{
            "department": l.department,
            "recipient": l.recipient_email,
            "queries": l.query_count,
            "sent_at": l.sent_at,
            "success": "✅" if l.success else "❌",
        } for l in logs])
    finally:
        db.close()

    return df, email_df


def render_dashboard_page():
    st.markdown("""
    <p class='hero-title'>📊 Analytics Dashboard</p>
    <p class='hero-sub'>Real-time overview of all customer interactions</p>
    <br>
    """, unsafe_allow_html=True)

    df, email_df = _load_data()

    # ── Top metrics ─────────────────────────────────────────────────────────
    total = len(df)
    product_n = len(df[df["category"] == "product"]) if not df.empty else 0
    payment_n = len(df[df["category"] == "payment"]) if not df.empty else 0
    voice_n = len(df[df["channel"] == "voice"]) if not df.empty else 0
    neg_n = len(df[df["sentiment"] == "negative"]) if not df.empty else 0

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Total Queries", total)
    c2.metric("📦 Product", product_n)
    c3.metric("💳 Payment", payment_n)
    c4.metric("🎤 Voice", voice_n)
    c5.metric("😟 Negative", neg_n)

    st.markdown("<br>", unsafe_allow_html=True)

    if df.empty:
        st.info("No queries yet. Start chatting to see analytics here!")
        return

    # ── Charts row ──────────────────────────────────────────────────────────
    chart_col1, chart_col2 = st.columns(2, gap="large")

    with chart_col1:
        st.markdown("<div class='agent-card'>", unsafe_allow_html=True)
        st.markdown("##### 📊 Queries by Category")
        cat_counts = df["category"].value_counts().reset_index()
        cat_counts.columns = ["Category", "Count"]
        st.bar_chart(cat_counts.set_index("Category"), height=220)
        st.markdown("</div>", unsafe_allow_html=True)

    with chart_col2:
        st.markdown("<div class='agent-card'>", unsafe_allow_html=True)
        st.markdown("##### 😊 Sentiment Breakdown")
        sent_counts = df["sentiment"].value_counts().reset_index()
        sent_counts.columns = ["Sentiment", "Count"]
        st.bar_chart(sent_counts.set_index("Sentiment"), height=220)
        st.markdown("</div>", unsafe_allow_html=True)

    # ── Channel + Status breakdown ──────────────────────────────────────────
    chart_col3, chart_col4 = st.columns(2, gap="large")

    with chart_col3:
        st.markdown("<div class='agent-card'>", unsafe_allow_html=True)
        st.markdown("##### 📡 Channel Distribution")
        ch_counts = df["channel"].value_counts().reset_index()
        ch_counts.columns = ["Channel", "Count"]
        st.bar_chart(ch_counts.set_index("Channel"), height=200)
        st.markdown("</div>", unsafe_allow_html=True)

    with chart_col4:
        st.markdown("<div class='agent-card'>", unsafe_allow_html=True)
        st.markdown("##### 📋 Query Status")
        st_counts = df["status"].value_counts().reset_index()
        st_counts.columns = ["Status", "Count"]
        st.bar_chart(st_counts.set_index("Status"), height=200)
        st.markdown("</div>", unsafe_allow_html=True)

    # ── Daily trend ─────────────────────────────────────────────────────────
    if "created_at" in df.columns and df["created_at"].notna().any():
        st.markdown("<div class='agent-card'>", unsafe_allow_html=True)
        st.markdown("##### 📈 Daily Query Trend")
        trend = (
            df.set_index("created_at")
            .resample("D")["id"]
            .count()
            .reset_index()
            .rename(columns={"id": "Queries", "created_at": "Date"})
        )
        st.area_chart(trend.set_index("Date"), height=220)
        st.markdown("</div>", unsafe_allow_html=True)

    # ── Recent queries table ─────────────────────────────────────────────────
    st.markdown("<div class='agent-card'>", unsafe_allow_html=True)
    st.markdown("##### 📝 Recent Queries (last 50)")

    display_df = df.head(50)[[
        "id","customer_name","channel","category","sentiment","status","raw_query","created_at"
    ]].copy()
    display_df.columns = ["ID","Customer","Channel","Category","Sentiment","Status","Query","Time"]
    display_df["Query"] = display_df["Query"].str[:80] + "…"
    st.dataframe(display_df, use_container_width=True, hide_index=True)
    st.markdown("</div>", unsafe_allow_html=True)

    # ── Email log ────────────────────────────────────────────────────────────
    if not email_df.empty:
        st.markdown("<div class='agent-card'>", unsafe_allow_html=True)
        st.markdown("##### 📧 Email Summary Log")
        st.dataframe(email_df, use_container_width=True, hide_index=True)
        st.markdown("</div>", unsafe_allow_html=True)
