"""
Natural-language -> structured task parsing.

Example:
    "Add task: Complete ML playlist on September 18 at 8 PM, high priority"
    ->  title="Complete ML playlist", due_date=2026-09-18 20:00, priority=HIGH

Strategy: `dateparser.search.search_dates` tends to fragment a combined
date+time phrase like "September 18 at 8 PM" into two separate hits
("September 18" and "8 PM" parsed independently against 'now', which is
wrong). Instead we:
  1. Strip priority/recurring keywords first (they can confuse date search).
  2. Find the earliest date "trigger" word/pattern (a month name, weekday,
     "today"/"tomorrow", "in N days", explicit numeric date, etc.).
  3. Take everything from that trigger to the end of the string as one
     candidate phrase, then hand the WHOLE phrase to `dateparser.parse`
     (not `search_dates`), which correctly combines date + time together.
  4. If parsing the full tail fails (e.g. trailing unrelated words confuse
     it), progressively shorten the candidate at natural boundaries
     (commas, "and", conjunctions) and retry.

This is deterministic and fast — no LLM call — matching spec section 4's
intent (structured extraction with confirmation only when genuinely
ambiguous). The LLM layer (app/ai) is reserved for open-ended Q&A.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import dateparser

from app.database.models import TaskPriority

_PRIORITY_KEYWORDS = {
    TaskPriority.CRITICAL: ["critical", "urgent", "asap", "immediately"],
    TaskPriority.HIGH: ["high priority", "important", "high-priority"],
    TaskPriority.MEDIUM: ["medium priority", "normal priority"],
    TaskPriority.LOW: ["low priority", "whenever", "no rush"],
}

_RECURRING_PATTERNS = {
    r"\bevery day\b|\bdaily\b": "DAILY",
    r"\bevery week\b|\bweekly\b": "WEEKLY",
    r"\bevery month\b|\bmonthly\b": "MONTHLY",
    r"\bevery monday\b": "WEEKLY:MON",
    r"\bevery weekday\b": "WEEKDAYS",
}

_LEAD_IN_PATTERNS = [
    r"^add (a )?task[:\-]?\s*",
    r"^create (a )?task[:\-]?\s*",
    r"^remind me (to )?",
    r"^new task[:\-]?\s*",
]

_MONTHS = (
    "january|february|march|april|may|june|july|august|september|october|november|december|"
    "jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec"
)
_WEEKDAYS = "monday|tuesday|wednesday|thursday|friday|saturday|sunday"

# We scan for the EARLIEST matching position across all of these, not
# pattern priority order.
_DATE_TRIGGER_PATTERNS = [
    rf"\b({_MONTHS})\b",
    rf"\b({_WEEKDAYS})\b",
    r"\btoday\b|\btonight\b|\btomorrow\b",
    r"\bnext week\b|\bnext month\b",
    r"\bin \d+ (day|days|week|weeks|hour|hours|month|months)\b",
    r"\b\d{1,2}/\d{1,2}(/\d{2,4})?\b",
    r"\bat \d{1,2}(:\d{2})?\s*(am|pm)?\b",
]

_DATE_SETTINGS = {
    "PREFER_DATES_FROM": "future",
    "RETURN_AS_TIMEZONE_AWARE": False,
}

# Boundaries at which we're willing to trim a trailing clause that confused
# the parser (e.g. ", high priority" or " and then submit it").
_TRIM_BOUNDARIES = [r",", r"\band\b", r"\bthen\b", r"\bto\b"]


@dataclass
class ParsedTask:
    title: str
    due_date: Optional[datetime] = None
    priority: TaskPriority = TaskPriority.MEDIUM
    recurring_rule: Optional[str] = None
    date_detected: bool = False
    priority_detected: bool = False
    raw_text: str = ""
    ambiguous: bool = False
    ambiguity_reason: str = ""


def _strip_lead_in(text: str) -> str:
    cleaned = text.strip()
    for pattern in _LEAD_IN_PATTERNS:
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)
    return cleaned.strip()


def _detect_priority(text: str) -> tuple[TaskPriority, bool]:
    lowered = text.lower()
    for priority, keywords in _PRIORITY_KEYWORDS.items():
        if any(kw in lowered for kw in keywords):
            return priority, True
    return TaskPriority.MEDIUM, False


def _strip_priority_and_recurring(text: str) -> str:
    cleaned = text
    for keywords in _PRIORITY_KEYWORDS.values():
        for kw in keywords:
            cleaned = re.sub(re.escape(kw), "", cleaned, flags=re.IGNORECASE)
    for pattern in _RECURRING_PATTERNS:
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)
    return cleaned


def _detect_recurring(text: str) -> Optional[str]:
    lowered = text.lower()
    for pattern, rule in _RECURRING_PATTERNS.items():
        if re.search(pattern, lowered):
            return rule
    return None


def _find_earliest_trigger(text: str) -> Optional[int]:
    earliest = None
    for pattern in _DATE_TRIGGER_PATTERNS:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match and (earliest is None or match.start() < earliest):
            earliest = match.start()
    return earliest


def _try_parse_candidate(candidate: str, now: datetime) -> Optional[datetime]:
    candidate = candidate.strip(" ,.-")
    if not candidate:
        return None
    return dateparser.parse(candidate, settings={**_DATE_SETTINGS, "RELATIVE_BASE": now})


def _extract_date(text: str, now: datetime) -> tuple[Optional[datetime], Optional[str]]:
    """Returns (due_date, matched_phrase) or (None, None) if nothing found."""
    start = _find_earliest_trigger(text)
    if start is None:
        return None, None

    tail = text[start:]

    # Try the full tail first, then progressively trim at boundaries so
    # trailing unrelated clauses ("high priority", "and submit it") don't
    # break the parse.
    candidates = [tail]
    for boundary in _TRIM_BOUNDARIES:
        pieces = re.split(boundary, tail, flags=re.IGNORECASE)
        if len(pieces) > 1 and pieces[0].strip():
            candidates.append(pieces[0])

    for candidate in candidates:
        parsed = _try_parse_candidate(candidate, now)
        if parsed:
            return parsed, candidate

    return None, None


def parse_task_text(text: str, now: Optional[datetime] = None) -> ParsedTask:
    now = now or datetime.now()
    working_text = text.strip()

    priority, priority_detected = _detect_priority(working_text)
    recurring_rule = _detect_recurring(working_text)

    date_search_text = _strip_priority_and_recurring(working_text)
    due_date, matched_phrase = _extract_date(date_search_text, now)

    title = working_text
    if matched_phrase:
        title = title.replace(matched_phrase, " ")
    title = _strip_priority_and_recurring(title)
    title = _strip_lead_in(title)

    title = re.sub(r"\bon\b\s*$", "", title, flags=re.IGNORECASE)
    title = re.sub(r"[,\-]\s*$", "", title)
    title = re.sub(r"\s{2,}", " ", title).strip(" ,-")

    if not title:
        title = "Untitled task"

    ambiguous = False
    ambiguity_reason = ""
    if due_date is None:
        ambiguous = True
        ambiguity_reason = "No date/time detected — confirm when this task is due."
    if len(title) < 3:
        ambiguous = True
        ambiguity_reason = (ambiguity_reason + " Task title looks too short to be useful.").strip()

    return ParsedTask(
        title=title,
        due_date=due_date,
        priority=priority,
        recurring_rule=recurring_rule,
        date_detected=due_date is not None,
        priority_detected=priority_detected,
        raw_text=text,
        ambiguous=ambiguous,
        ambiguity_reason=ambiguity_reason,
    )
