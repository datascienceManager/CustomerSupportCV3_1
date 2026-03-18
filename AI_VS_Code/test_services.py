"""
tests/test_services.py
Unit tests for database, AI agent classification, and email service.
Run with: pytest tests/ -v
"""

import pytest
import os
import sys

# Ensure project root is on the path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# ── Set test env vars before any imports ──────────────────────────────────────
os.environ.setdefault("DB_TYPE", "sqlite")
os.environ.setdefault("SQLITE_DB_PATH", "/tmp/test_voice_agent.db")
os.environ.setdefault("ANTHROPIC_API_KEY", "test_key")
os.environ.setdefault("APP_ENV", "test")


# ── Database tests ─────────────────────────────────────────────────────────────

class TestDatabase:
    def setup_method(self):
        """Fresh DB engine for each test."""
        from services.database import Base, get_engine
        Base.metadata.create_all(get_engine())

    def test_save_and_retrieve_query(self):
        from services.database import save_query, get_all_queries
        record = save_query(
            session_id="test-session-001",
            raw_query="What is the return policy?",
            ai_response="You can return items within 30 days.",
            category="product",
            channel="chat",
            sentiment="neutral",
        )
        assert record.id is not None
        assert record.category.value == "product"
        assert record.session_id == "test-session-001"

        rows = get_all_queries(limit=10)
        assert any(r["session_id"] == "test-session-001" for r in rows)

    def test_unsummarised_queries_filter(self):
        from services.database import save_query, get_unsummarised_queries, QueryStatus
        save_query(
            session_id="filter-test",
            raw_query="I need a refund",
            ai_response="We can process that.",
            category="payment",
            channel="chat",
            sentiment="negative",
        )
        queries = get_unsummarised_queries("payment")
        assert len(queries) >= 1
        assert all(q.status == QueryStatus.NEW for q in queries)

    def test_mark_queries_emailed(self):
        from services.database import save_query, get_unsummarised_queries, mark_queries_emailed, QueryStatus
        record = save_query(
            session_id="email-test",
            raw_query="Billing question",
            ai_response="Here is billing info.",
            category="payment",
            channel="chat",
        )
        mark_queries_emailed([record.id])

        # Should no longer appear in unsummarised list
        remaining = get_unsummarised_queries("payment")
        assert not any(q.id == record.id for q in remaining)

    def test_to_dict(self):
        from services.database import save_query
        record = save_query(
            session_id="dict-test",
            raw_query="Product info",
            ai_response="Here are product details.",
            category="product",
            channel="voice",
            customer_name="Alice",
        )
        d = record.to_dict()
        assert d["customer_name"] == "Alice"
        assert d["channel"] == "voice"
        assert d["category"] == "product"
        assert "created_at" in d

    def test_unknown_category_fallback(self):
        from services.database import save_query
        record = save_query(
            session_id="unknown-cat",
            raw_query="Random question",
            ai_response="Let me help.",
            category="something_invalid",
            channel="chat",
        )
        assert record.category.value == "unknown"


# ── Voice utils tests ──────────────────────────────────────────────────────────

class TestVoiceUtils:
    def test_audio_bytes_to_base64(self):
        from utils.voice_utils import audio_bytes_to_base64
        dummy_bytes = b"RIFF\x00\x00\x00\x00WAVEfmt "
        result = audio_bytes_to_base64(dummy_bytes)
        assert result.startswith("data:audio/mp3;base64,")

    def test_transcribe_no_key(self):
        """Without OPENAI_API_KEY, transcription returns None gracefully."""
        import os
        original = os.environ.pop("OPENAI_API_KEY", None)
        try:
            # Force reload settings
            import importlib
            import config.settings as cfg_mod
            cfg_mod.settings.openai_api_key = ""

            from utils.voice_utils import transcribe_audio
            result = transcribe_audio(b"fake audio bytes")
            assert result is None
        finally:
            if original:
                os.environ["OPENAI_API_KEY"] = original
                cfg_mod.settings.openai_api_key = original

    def test_tts_synthesis(self):
        """gTTS synthesis should return MP3 bytes for valid text."""
        from utils.voice_utils import synthesize_speech
        try:
            result = synthesize_speech("Hello, this is a test.")
            # May fail in CI without network — just check it doesn't crash unexpectedly
            if result is not None:
                assert isinstance(result, bytes)
                assert len(result) > 0
        except Exception:
            pytest.skip("gTTS unavailable in this environment")


# ── Google Sheets tests ────────────────────────────────────────────────────────

class TestGoogleSheets:
    def test_get_sheet_url_no_id(self):
        from services import google_sheets as gs
        original = gs.settings.google.sheet_id
        gs.settings.google.sheet_id = ""
        url = gs.get_sheet_url()
        assert url == ""
        gs.settings.google.sheet_id = original

    def test_get_sheet_url_with_id(self):
        from services import google_sheets as gs
        gs.settings.google.sheet_id = "abc123"
        url = gs.get_sheet_url()
        assert "abc123" in url
        gs.settings.google.sheet_id = ""

    def test_append_no_credentials(self):
        """Should return None gracefully when no credentials file exists."""
        from services.google_sheets import append_query
        result = append_query(
            record_id=999,
            session_id="test-gs",
            customer_name="Bob",
            customer_email="bob@example.com",
            channel="chat",
            category="product",
            sentiment="neutral",
            raw_query="Test query",
            ai_response="Test response",
        )
        assert result is None


# ── Settings tests ─────────────────────────────────────────────────────────────

class TestSettings:
    def test_sqlite_connection_url(self):
        from config.settings import DatabaseConfig
        cfg = DatabaseConfig(db_type="sqlite", sqlite_path="/tmp/test.db")
        assert "sqlite" in cfg.connection_url
        assert "test.db" in cfg.connection_url

    def test_mysql_connection_url(self):
        from config.settings import DatabaseConfig
        cfg = DatabaseConfig(
            db_type="mysql",
            mysql_host="localhost",
            mysql_port=3306,
            mysql_database="testdb",
            mysql_user="user",
            mysql_password="pass",
        )
        url = cfg.connection_url
        assert "mysql+pymysql" in url
        assert "localhost" in url
        assert "testdb" in url

    def test_is_production(self):
        from config.settings import AppConfig
        cfg = AppConfig(app_env="production")
        assert cfg.is_production is True

        cfg2 = AppConfig(app_env="development")
        assert cfg2.is_production is False


# ── Email service tests ────────────────────────────────────────────────────────

class TestEmailService:
    def test_html_template_renders(self):
        from services.email_service import _html_template
        html = _html_template(
            department_name="Product Team",
            summary_text="## Summary\n\nTop issues:\n- Feature requests\n- Bug reports",
            query_count=10,
            date_str="January 01, 2025",
        )
        assert "Product Team" in html
        assert "10 queries" in html
        assert "January 01, 2025" in html
        assert "<html>" in html

    def test_send_no_key_console_fallback(self, capsys):
        from services.email_service import _send_via_sendgrid
        import services.email_service as em
        original = em.settings.email.sendgrid_api_key
        em.settings.email.sendgrid_api_key = ""

        result = _send_via_sendgrid("test@example.com", "Test Subject", "<p>Hello</p>")
        assert result is True  # console fallback returns True

        captured = capsys.readouterr()
        assert "EMAIL" in captured.out or "test@example.com" in captured.out

        em.settings.email.sendgrid_api_key = original


# ── Scheduler tests ────────────────────────────────────────────────────────────

class TestScheduler:
    def test_start_stop(self):
        from utils.scheduler import start_scheduler, stop_scheduler
        start_scheduler()
        start_scheduler()  # Idempotent — should not raise
        stop_scheduler()

    def test_start_idempotent(self):
        from utils.scheduler import start_scheduler, stop_scheduler
        for _ in range(3):
            start_scheduler()
        stop_scheduler()
