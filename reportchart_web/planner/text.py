"""Small, dependency-free text and date rules used by Planner processing."""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime


def strip_value(value) -> str:
    if value is None:
        return ""
    return str(value).strip()


def lower_value(value) -> str:
    return strip_value(value).lower()


def normalize_text_key(value) -> str:
    text = strip_value(value)
    text = "".join(
        ch for ch in unicodedata.normalize("NFKD", text)
        if not unicodedata.combining(ch)
    )
    return re.sub(r"\s+", " ", text).strip().lower()


def parse_date(value):
    if not value or str(value).strip().lower() in ("", "nan", "none"):
        return None
    text = str(value).strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%m/%d/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None
