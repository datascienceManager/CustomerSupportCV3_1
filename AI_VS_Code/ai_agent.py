"""
services/ai_agent.py
Core AI logic — uses Anthropic Claude for:
  • Answering customer queries
  • Classifying query category (product / payment / unknown)
  • Detecting sentiment
  • Generating department email summaries
"""

import json
import logging
import re
from typing import Tuple

import anthropic

from config.settings import settings

logger = logging.getLogger(__name__)

# Lazy client — created once
_client: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        if not settings.anthropic_api_key:
            raise ValueError("ANTHROPIC_API_KEY is not set. Please configure it in .env")
        _client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    return _client


# ── System prompt ─────────────────────────────────────────────────────────────

SYSTEM_PROMPT = f"""You are a helpful, friendly, and professional customer support AI agent for {settings.company_name}.

Your responsibilities:
1. Answer customer questions clearly and accurately.
2. Handle TWO categories of queries:
   - PRODUCT queries: questions about product features, usage, availability, specifications, complaints about products.
   - PAYMENT queries: questions about billing, invoices, refunds, payment methods, transaction issues, pricing.
3. Be concise (2-4 sentences for simple queries, up to 8 for complex ones).
4. Always be empathetic and solution-focused.
5. If you don't know something, say so honestly and offer to escalate.

Respond ONLY with a JSON object in this exact format (no markdown, no preamble):
{{
  "answer": "<your helpful response to the customer>",
  "category": "<product|payment|unknown>",
  "sentiment": "<positive|neutral|negative>",
  "escalate": <true|false>
}}

Rules:
- category must be exactly "product", "payment", or "unknown"
- sentiment reflects the customer's tone (positive=happy, neutral=normal, negative=frustrated/angry)
- escalate=true if the issue cannot be resolved by AI and needs a human agent
"""


# ── Public API ────────────────────────────────────────────────────────────────

def process_query(
    user_message: str,
    conversation_history: list | None = None,
) -> Tuple[str, str, str, bool]:
    """
    Send a query to Claude and parse the structured response.

    Returns:
        (answer, category, sentiment, escalate)
    """
    client = _get_client()

    messages = []
    if conversation_history:
        # Include prior turns for context (last 6 turns to stay within limits)
        messages.extend(conversation_history[-6:])
    messages.append({"role": "user", "content": user_message})

    try:
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=512,
            system=SYSTEM_PROMPT,
            messages=messages,
        )

        raw = response.content[0].text.strip()
        logger.debug("Raw AI response: %s", raw)

        # Strip accidental markdown fences
        raw = re.sub(r"^```json\s*|```$", "", raw, flags=re.MULTILINE).strip()

        parsed = json.loads(raw)
        answer = parsed.get("answer", "I'm sorry, I couldn't process your query.")
        category = parsed.get("category", "unknown")
        sentiment = parsed.get("sentiment", "neutral")
        escalate = parsed.get("escalate", False)

        return answer, category, sentiment, bool(escalate)

    except json.JSONDecodeError as exc:
        logger.error("Failed to parse Claude JSON: %s | raw=%s", exc, raw)
        return (
            "I'm sorry, I encountered an issue processing your request. Please try again.",
            "unknown",
            "neutral",
            True,
        )
    except anthropic.APIError as exc:
        logger.error("Anthropic API error: %s", exc)
        raise


def generate_department_summary(queries: list[dict], department: str) -> str:
    """
    Given a list of query dicts, ask Claude to produce a concise email summary
    for the relevant department.
    """
    client = _get_client()

    queries_text = "\n".join(
        f"[{i+1}] [{q.get('created_at', '')}] "
        f"Customer: {q.get('customer_name', 'Anonymous')} | "
        f"Sentiment: {q.get('sentiment', 'neutral')} | "
        f"Query: {q.get('raw_query', '')} | "
        f"AI Response: {q.get('ai_response', '')}"
        for i, q in enumerate(queries)
    )

    prompt = f"""You are preparing an internal summary email for the {department.upper()} department.

Here are today's {len(queries)} customer queries in that category:

{queries_text}

Write a concise, professional email summary that includes:
1. Total query count and overall sentiment breakdown
2. Top 3 most common issues / themes
3. Any urgent or escalated cases (mark clearly)
4. Recommended actions for the team
5. A brief positive note or encouragement for the team

Keep it under 400 words. Use clear headings. Be direct and actionable."""

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=600,
        messages=[{"role": "user", "content": prompt}],
    )

    return response.content[0].text.strip()
