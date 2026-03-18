"""
tests/test_services.py
Unit tests for database, Ollama AI agent, voice utils, email service, and scheduler.
Run with: pytest tests/ -v
"""

import pytest
import os
import sys
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# Set test env vars before any imports
os.environ.setdefault("DB_TYPE", "sqlite")
os.environ.setdefault("SQLITE_DB_PATH", "/tmp/test_voice_agent.db")
os.environ.setdefault("OLLAMA_BASE_URL", "http://localhost:11434")
os.environ.setdefault("OLLAMA_MODEL", "llama3.2")
os.environ.setdefault("APP_ENV", "test")


# ── Database tests ─────────────────────────────────────────────────────────────

class TestDatabase:
    def setup_method(self):
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
        from services.database import save_query, mark_queries_emailed, QueryStatus
        record = save_query(
            session_id="email-test",
            raw_query="Billing question",
            ai_response="Here is billing info.",
            category="payment",
            channel="chat",
        )
        mark_queries_emailed([record.id])
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


# ── Ollama AI agent tests ──────────────────────────────────────────────────────

class TestOllamaAgent:

    MOCK_CHAT_RESPONSE = (
        '{"answer": "Our return policy allows returns within 30 days.", '
        '"category": "product", "sentiment": "neutral", "escalate": false}'
    )

    def _mock_post(self, *args, **kwargs):
        """Simulate a successful Ollama /api/chat response."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "message": {"role": "assistant", "content": self.MOCK_CHAT_RESPONSE}
        }
        mock_resp.raise_for_status = MagicMock()
        return mock_resp

    def test_process_query_success(self):
        from services.ai_agent import process_query
        with patch("services.ai_agent.requests.post", side_effect=self._mock_post):
            answer, category, sentiment, escalate = process_query("What is the return policy?")
        assert "return" in answer.lower()
        assert category == "product"
        assert sentiment == "neutral"
        assert escalate is False

    def test_process_query_payment_category(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "message": {"content": '{"answer":"Refund in 5-7 days.","category":"payment","sentiment":"negative","escalate":true}'}
        }
        mock_resp.raise_for_status = MagicMock()
        from services.ai_agent import process_query
        with patch("services.ai_agent.requests.post", return_value=mock_resp):
            _, category, sentiment, escalate = process_query("I want a refund")
        assert category == "payment"
        assert sentiment == "negative"
        assert escalate is True

    def test_process_query_json_with_markdown_fences(self):
        """Model wraps JSON in ```json ... ``` — should still parse correctly."""
        fenced = '```json\n{"answer":"Hello!","category":"product","sentiment":"positive","escalate":false}\n```'
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"message": {"content": fenced}}
        mock_resp.raise_for_status = MagicMock()
        from services.ai_agent import process_query
        with patch("services.ai_agent.requests.post", return_value=mock_resp):
            answer, category, sentiment, escalate = process_query("Hi!")
        assert answer == "Hello!"
        assert category == "product"

    def test_process_query_invalid_category_normalised(self):
        """Out-of-range category values are normalised to 'unknown'."""
        bad_json = '{"answer":"Not sure.","category":"shipping","sentiment":"neutral","escalate":false}'
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"message": {"content": bad_json}}
        mock_resp.raise_for_status = MagicMock()
        from services.ai_agent import process_query
        with patch("services.ai_agent.requests.post", return_value=mock_resp):
            _, category, _, _ = process_query("Where is my order?")
        assert category == "unknown"

    def test_process_query_connection_error_raises(self):
        import requests as req
        from services.ai_agent import process_query
        with patch("services.ai_agent.requests.post", side_effect=req.ConnectionError("refused")):
            with pytest.raises(ConnectionError):
                process_query("test")

    def test_process_query_fallback_on_malformed_json(self):
        """Non-JSON response: returns raw text as answer, does not raise."""
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"message": {"content": "Sorry, I cannot help with that."}}
        mock_resp.raise_for_status = MagicMock()
        from services.ai_agent import process_query
        with patch("services.ai_agent.requests.post", return_value=mock_resp):
            answer, category, _, escalate = process_query("some query")
        assert isinstance(answer, str)
        assert category == "unknown"
        assert escalate is True

    def test_check_ollama_health_online(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "models": [{"name": "llama3.2"}, {"name": "mistral"}]
        }
        mock_resp.raise_for_status = MagicMock()
        from services.ai_agent import check_ollama_health
        with patch("services.ai_agent.requests.get", return_value=mock_resp):
            result = check_ollama_health()
        assert result["online"] is True
        assert "llama3.2" in result["models"]

    def test_check_ollama_health_offline(self):
        import requests as req
        from services.ai_agent import check_ollama_health
        with patch("services.ai_agent.requests.get", side_effect=req.ConnectionError):
            result = check_ollama_health()
        assert result["online"] is False
        assert result["error"] is not None

    def test_generate_summary_success(self):
        summary_text = "## Overview\n5 queries today.\n## Top Issues\n- Billing"
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"message": {"content": summary_text}}
        mock_resp.raise_for_status = MagicMock()
        from services.ai_agent import generate_department_summary
        queries = [
            {"created_at": "2025-01-01", "customer_name": "Alice",
             "sentiment": "neutral", "raw_query": "Billing?", "ai_response": "Here you go."}
        ]
        with patch("services.ai_agent.requests.post", return_value=mock_resp):
            result = generate_department_summary(queries, "payment")
        assert "Overview" in result or "queries" in result.lower()

    def test_generate_summary_fallback_on_error(self):
        """On error, returns a basic fallback summary (does not raise)."""
        import requests as req
        from services.ai_agent import generate_department_summary
        queries = [
            {"created_at": "", "customer_name": "Bob", "sentiment": "negative",
             "raw_query": "Refund!", "ai_response": "Processing."}
        ]
        with patch("services.ai_agent.requests.post", side_effect=req.ConnectionError("down")):
            result = generate_department_summary(queries, "payment")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_parse_json_response_direct(self):
        from services.ai_agent import _parse_json_response
        raw = '{"answer":"Hi","category":"product","sentiment":"positive","escalate":false}'
        parsed = _parse_json_response(raw)
        assert parsed["category"] == "product"

    def test_parse_json_response_embedded(self):
        from services.ai_agent import _parse_json_response
        raw = 'Sure! Here is the response: {"answer":"Ok","category":"payment","sentiment":"neutral","escalate":false} done.'
        parsed = _parse_json_response(raw)
        assert parsed["category"] == "payment"

    def test_parse_json_response_no_json_raises(self):
        from services.ai_agent import _parse_json_response
        with pytest.raises(ValueError):
            _parse_json_response("This is just plain text with no JSON.")


# ── Voice utils tests ──────────────────────────────────────────────────────────

class TestVoiceUtils:
    def test_audio_bytes_to_base64(self):
        from utils.voice_utils import audio_bytes_to_base64
        dummy = b"RIFF\x00\x00\x00\x00WAVEfmt "
        result = audio_bytes_to_base64(dummy)
        assert result.startswith("data:audio/mp3;base64,")

    def test_transcribe_no_key(self):
        from config import settings as cfg_mod
        original = cfg_mod.settings.openai_api_key
        cfg_mod.settings.openai_api_key = ""
        try:
            from utils.voice_utils import transcribe_audio
            result = transcribe_audio(b"fake audio")
            assert result is None
        finally:
            cfg_mod.settings.openai_api_key = original

    def test_tts_synthesis_mock(self):
        """Mock gTTS to avoid network calls in CI."""
        mock_tts = MagicMock()
        mock_tts.write_to_fp = lambda buf: buf.write(b"fake-mp3-bytes")
        with patch("utils.voice_utils.gTTS", return_value=mock_tts):
            from utils.voice_utils import synthesize_speech
            result = synthesize_speech("Hello world")
        assert result is not None
        assert isinstance(result, bytes)


# ── Google Sheets tests ────────────────────────────────────────────────────────

class TestGoogleSheets:
    def test_get_sheet_url_no_id(self):
        from services import google_sheets as gs
        original = gs.settings.google.sheet_id
        gs.settings.google.sheet_id = ""
        assert gs.get_sheet_url() == ""
        gs.settings.google.sheet_id = original

    def test_get_sheet_url_with_id(self):
        from services import google_sheets as gs
        gs.settings.google.sheet_id = "abc123"
        assert "abc123" in gs.get_sheet_url()
        gs.settings.google.sheet_id = ""

    def test_append_no_credentials(self):
        from services.google_sheets import append_query
        result = append_query(
            record_id=999, session_id="test-gs",
            customer_name="Bob", customer_email="bob@example.com",
            channel="chat", category="product", sentiment="neutral",
            raw_query="Test", ai_response="Response",
        )
        assert result is None


# ── Settings tests ─────────────────────────────────────────────────────────────

class TestSettings:
    def test_sqlite_connection_url(self):
        from config.settings import DatabaseConfig
        cfg = DatabaseConfig(db_type="sqlite", sqlite_path="/tmp/test.db")
        assert "sqlite" in cfg.connection_url

    def test_mysql_connection_url(self):
        from config.settings import DatabaseConfig
        cfg = DatabaseConfig(
            db_type="mysql", mysql_host="localhost", mysql_port=3306,
            mysql_database="testdb", mysql_user="user", mysql_password="pass",
        )
        assert "mysql+pymysql" in cfg.connection_url
        assert "testdb" in cfg.connection_url

    def test_ollama_defaults(self):
        from config.settings import OllamaConfig
        cfg = OllamaConfig()
        assert "11434" in cfg.base_url
        assert cfg.model != ""
        assert cfg.timeout > 0

    def test_is_production(self):
        from config.settings import AppConfig
        assert AppConfig(app_env="production").is_production is True
        assert AppConfig(app_env="development").is_production is False


# ── Email service tests ────────────────────────────────────────────────────────

class TestEmailService:
    def test_html_template_renders(self):
        from services.email_service import _html_template
        html = _html_template("Product Team", "## Summary\nAll good.", 10, "Jan 01, 2025")
        assert "Product Team" in html
        assert "10 queries" in html
        assert "<html>" in html

    def test_send_no_key_console_fallback(self, capsys):
        from services import email_service as em
        original = em.settings.email.sendgrid_api_key
        em.settings.email.sendgrid_api_key = ""
        result = em._send_via_sendgrid("test@example.com", "Subject", "<p>Hi</p>")
        assert result is True
        captured = capsys.readouterr()
        assert "test@example.com" in captured.out or "EMAIL" in captured.out
        em.settings.email.sendgrid_api_key = original


# ── Scheduler tests ────────────────────────────────────────────────────────────

class TestScheduler:
    def test_start_stop(self):
        from utils.scheduler import start_scheduler, stop_scheduler
        start_scheduler()
        start_scheduler()   # Idempotent
        stop_scheduler()

    def test_start_idempotent_multiple(self):
        from utils.scheduler import start_scheduler, stop_scheduler
        for _ in range(3):
            start_scheduler()
        stop_scheduler()
