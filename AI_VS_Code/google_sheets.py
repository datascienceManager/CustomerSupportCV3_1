"""
services/google_sheets.py
Append customer query rows to a Google Sheet via the gspread library.
Falls back gracefully if credentials are not configured (demo mode).
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from config.settings import settings

logger = logging.getLogger(__name__)

# Column headers for the Google Sheet
SHEET_HEADERS = [
    "ID", "Session ID", "Timestamp", "Customer Name", "Customer Email",
    "Channel", "Category", "Sentiment", "Query", "AI Response",
    "Status", "Escalated",
]


def _get_worksheet():
    """Authenticate and return the target worksheet. Returns None on failure."""
    try:
        import gspread
        from google.oauth2.service_account import Credentials

        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ]

        creds_path = Path(settings.google.service_account_json)
        if not creds_path.exists():
            logger.warning(
                "Google service account JSON not found at %s — sheet sync disabled.",
                creds_path,
            )
            return None

        creds = Credentials.from_service_account_file(str(creds_path), scopes=scopes)
        client = gspread.authorize(creds)

        if not settings.google.sheet_id:
            logger.warning("GOOGLE_SHEET_ID not set — sheet sync disabled.")
            return None

        sheet = client.open_by_key(settings.google.sheet_id)
        try:
            ws = sheet.worksheet(settings.google.sheet_name)
        except gspread.WorksheetNotFound:
            ws = sheet.add_worksheet(title=settings.google.sheet_name, rows="1000", cols="20")
            ws.append_row(SHEET_HEADERS, value_input_option="USER_ENTERED")
            logger.info("Created new worksheet '%s' with headers.", settings.google.sheet_name)

        return ws

    except Exception as exc:
        logger.error("Google Sheets init failed: %s", exc)
        return None


def _ensure_headers(ws) -> None:
    """Make sure the first row contains the expected headers."""
    try:
        existing = ws.row_values(1)
        if not existing or existing[0] != "ID":
            ws.insert_row(SHEET_HEADERS, index=1)
            logger.info("Inserted header row into Google Sheet.")
    except Exception as exc:
        logger.warning("Could not verify sheet headers: %s", exc)


def append_query(
    record_id: int,
    session_id: str,
    customer_name: Optional[str],
    customer_email: Optional[str],
    channel: str,
    category: str,
    sentiment: str,
    raw_query: str,
    ai_response: str,
    status: str = "new",
    escalated: bool = False,
) -> Optional[int]:
    """
    Append one row to the Google Sheet.
    Returns the 1-based row number written, or None if sync is disabled.
    """
    ws = _get_worksheet()
    if ws is None:
        logger.info("Google Sheets sync skipped (not configured).")
        return None

    _ensure_headers(ws)

    row = [
        record_id,
        session_id,
        datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        customer_name or "Anonymous",
        customer_email or "",
        channel,
        category,
        sentiment,
        raw_query,
        ai_response,
        status,
        "Yes" if escalated else "No",
    ]

    try:
        ws.append_row(row, value_input_option="USER_ENTERED")
        # gspread doesn't directly return the row number; calculate from row count
        row_count = len(ws.col_values(1))
        logger.info("Appended row %d to Google Sheet.", row_count)
        return row_count
    except Exception as exc:
        logger.error("Failed to append row to Google Sheet: %s", exc)
        return None


def get_sheet_url() -> str:
    """Return a direct link to the configured Google Sheet."""
    if settings.google.sheet_id:
        return f"https://docs.google.com/spreadsheets/d/{settings.google.sheet_id}"
    return ""
