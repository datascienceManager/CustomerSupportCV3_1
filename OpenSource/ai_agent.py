"""
services/ai_agent.py
Core AI logic — uses Ollama (local open-source LLM) for:
  • Answering customer queries
  • Classifying query category (product / payment / unknown)
  • Detecting sentiment
  • Generating department email summaries

Ollama docs: https://ollama.com
Supported models: llama3.2, llama3.1, mistral, gemma2, phi3, qwen2.5, etc.

Quick start:
  brew install ollama          # macOS
  ollama serve                 # start daemon
  ollama pull llama3.2         # download model
"""

import json
import logging
import re
import time
from typing import Tuple

import requests

from config.settings import settings

logger = logging.getLogger(__name__)


# ── Ollama HTTP client helpers ─────────────────────────────────────────────────

def _base_url() -> str:
    return settings.ollama.base_url.rstrip("/")


def _auth() -> tuple | None:
    u, p = settings.ollama.username, settings.ollama.password
    return (u, p) if u and p else None


def _headers() -> dict:
    return {"Content-Type": "application/json"}


def check_ollama_health() -> dict:
    """
    Ping the Ollama server and return status info.
    Returns {"online": bool, "models": list[str], "error": str|None}
    """
    try:
        r = requests.get(
            f"{_base_url()}/api/tags",
            timeout=5,
            auth=_auth(),
            headers=_headers(),
        )
        r.raise_for_status()
        models = [m["name"] for m in r.json().get("models", [])]
        return {"online": True, "models": models, "error": None}
    except requests.ConnectionError:
        return {
            "online": False,
            "models": [],
            "error": (
                "Cannot connect to Ollama. "
                "Run: ollama serve"
            ),
        }
    except Exception as exc:
        return {"online": False, "models": [], "error": str(exc)}


def _chat(messages: list[dict], system: str | None = None) -> str:
    """
    Call the Ollama /api/chat endpoint (OpenAI-compatible messages format).
    Returns the assistant content string.
    Raises on HTTP/connection error.
    """
    payload: dict = {
        "model": settings.ollama.model,
        "messages": messages,
        "stream": False,
        "options": {
            "temperature": 0.2,      # Low temp for consistent JSON output
            "num_predict": 600,
        },
    }
    if system:
        # Prepend system message (works for all llama-family models)
        payload["messages"] = [{"role": "system", "content": system}] + messages

    url = f"{_base_url()}/api/chat"
    try:
        resp = requests.post(
            url,
            json=payload,
            timeout=settings.ollama.timeout,
            auth=_auth(),
            headers=_headers(),
        )
        resp.raise_for_status()
        data = resp.json()
        content = data.get("message", {}).get("content", "")
        if not content:
            raise ValueError(f"Empty content in Ollama response: {data}")
        return content.strip()
    except requests.Timeout:
        raise TimeoutError(
            f"Ollama timed out after {settings.ollama.timeout}s. "
            "Try a smaller model or increase OLLAMA_TIMEOUT."
        )
    except requests.ConnectionError:
        raise ConnectionError(
            "Ollama server is not reachable. "
            "Ensure 'ollama serve' is running."
        )


def _parse_json_response(raw: str) -> dict:
    """
    Extract and parse the first JSON object from a raw LLM response.
    Handles markdown fences, leading prose, and trailing text.
    """
    # Strip markdown code fences
    cleaned = re.sub(r"```(?:json)?", "", raw, flags=re.IGNORECASE).strip()
    cleaned = cleaned.replace("```", "").strip()

    # Try direct parse first
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # Find first { ... } block
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    raise ValueError(f"No valid JSON object found in: {raw[:300]}")


# ── System prompts ─────────────────────────────────────────────────────────────

def _build_system_prompt() -> str:
    return f"""You are a helpful, friendly, and professional customer support AI agent for {settings.company_name}.

Your responsibilities:
1. Answer customer questions clearly and accurately.
2. Handle TWO categories of queries:
   - PRODUCT queries: questions about product features, usage, availability, specifications, complaints about products.
   - PAYMENT queries: questions about billing, invoices, refunds, payment methods, transaction issues, pricing.
3. Be concise (2-4 sentences for simple queries, up to 8 for complex ones).
4. Always be empathetic and solution-focused.
5. If you cannot resolve something, set escalate to true.

IMPORTANT: Respond ONLY with a valid JSON object — no explanation, no markdown, no preamble. Just the raw JSON:
{{
  "answer": "<your helpful response to the customer>",
  "category": "<product|payment|unknown>",
  "sentiment": "<positive|neutral|negative>",
  "escalate": <true|false>
}}

Rules:
- category must be exactly one of: product, payment, unknown
- sentiment reflects the CUSTOMER'S tone: positive=happy/satisfied, neutral=normal, negative=frustrated/angry
- escalate=true only if issue cannot be resolved by AI and needs a human agent
- Return ONLY the JSON object, nothing else"""


SUMMARY_SYSTEM_PROMPT = """You are an internal analyst preparing concise department email summaries.
Write in plain text using simple headings (##). Be direct, professional, and actionable.
Do NOT use JSON. Do NOT use markdown code blocks."""


# ── Public API ────────────────────────────────────────────────────────────────

def process_query(
    user_message: str,
    conversation_history: list | None = None,
) -> Tuple[str, str, str, bool]:
    """
    Send a customer query to Ollama and return structured results.

    Returns:
        (answer, category, sentiment, escalate)
    """
    messages: list[dict] = []

    # Include last 6 turns for conversational context
    if conversation_history:
        for turn in conversation_history[-6:]:
            role = turn.get("role", "user")
            content = turn.get("content", "")
            if role in ("user", "assistant") and content:
                messages.append({"role": role, "content": content})

    messages.append({"role": "user", "content": user_message})

    system = _build_system_prompt()
    raw = ""

    try:
        raw = _chat(messages, system=system)
        logger.debug("Ollama raw response: %s", raw[:300])

        parsed = _parse_json_response(raw)
        answer = str(parsed.get("answer", "I'm sorry, I couldn't process your query.")).strip()
        category = str(parsed.get("category", "unknown")).lower().strip()
        sentiment = str(parsed.get("sentiment", "neutral")).lower().strip()
        escalate = bool(parsed.get("escalate", False))

        # Normalise values
        if category not in ("product", "payment", "unknown"):
            category = "unknown"
        if sentiment not in ("positive", "neutral", "negative"):
            sentiment = "neutral"

        return answer, category, sentiment, escalate

    except (ConnectionError, TimeoutError):
        raise  # Let the UI handle these with a clear message

    except (ValueError, json.JSONDecodeError) as exc:
        logger.warning("JSON parse failed, attempting fallback extraction. Error: %s | raw=%s", exc, raw[:200])
        # Fallback: return raw text as answer with unknown classification
        answer = raw if raw else "I'm sorry, I encountered an issue. Please try again."
        # Strip any JSON-like noise from the fallback answer
        answer = re.sub(r'\{.*\}', '', answer, flags=re.DOTALL).strip() or answer
        return answer[:500], "unknown", "neutral", True

    except Exception as exc:
        logger.error("Unexpected error in process_query: %s", exc, exc_info=True)
        return (
            "I'm sorry, I encountered an unexpected error. Please try again.",
            "unknown",
            "neutral",
            True,
        )


def generate_department_summary(queries: list[dict], department: str) -> str:
    """
    Ask Ollama to produce a concise plain-text email summary for a department.
    """
    queries_text = "\n".join(
        f"[{i+1}] [{q.get('created_at', '')}] "
        f"Customer: {q.get('customer_name', 'Anonymous')} | "
        f"Sentiment: {q.get('sentiment', 'neutral')} | "
        f"Query: {q.get('raw_query', '')} | "
        f"Response: {q.get('ai_response', '')}"
        for i, q in enumerate(queries)
    )

    prompt = f"""Prepare an internal summary email for the {department.upper()} department.

Today's {len(queries)} customer queries:

{queries_text}

Write a concise summary (under 400 words) with these sections:
## Overview
- Total queries and sentiment breakdown (positive / neutral / negative counts)

## Top Issues
- List the 3 most common themes or problems

## Urgent / Escalated Cases
- List any cases marked as escalated with brief context

## Recommended Actions
- 2-3 specific action items for the team

## Team Note
- One motivating sentence for the team

Plain text only. No JSON. No markdown code blocks."""

    try:
        return _chat(
            [{"role": "user", "content": prompt}],
            system=SUMMARY_SYSTEM_PROMPT,
        )
    except Exception as exc:
        logger.error("Summary generation failed: %s", exc)
        # Return a basic fallback summary so email can still be sent
        pos = sum(1 for q in queries if q.get("sentiment") == "positive")
        neg = sum(1 for q in queries if q.get("sentiment") == "negative")
        neu = len(queries) - pos - neg
        return (
            f"## {department.title()} Department — Daily Summary\n\n"
            f"**Total queries:** {len(queries)}\n"
            f"**Sentiment:** {pos} positive · {neu} neutral · {neg} negative\n\n"
            f"*(AI summary generation failed — please review queries manually.)*"
        )


def list_available_models() -> list[str]:
    """Return model names available on the local Ollama instance."""
    health = check_ollama_health()
    return health.get("models", [])
