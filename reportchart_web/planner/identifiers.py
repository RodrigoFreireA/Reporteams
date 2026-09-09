"""Deterministic rules for HU and profile metadata in Planner tasks."""

from __future__ import annotations

import re
from functools import lru_cache

from .text import lower_value as _lower
from .text import normalize_text_key as _norm_text_key
from .text import strip_value as _strip


HU_ID_RE = re.compile(r"(HU\s*\d+)", re.IGNORECASE)
HU_LABEL_RE = re.compile(r"HU\s*\d+", re.IGNORECASE)
TITLE_PROFILE_MARKER_RE = re.compile(r"\[\s*([^\]]+?)\s*\]")

TITLE_PROFILE_MARKER_ALIASES = {
    "dev": ".DEV", "desenvolvimento": ".DEV",
    "arquitetura": ".ARQUITETURA", "arquit": ".ARQUITETURA",
    "requisitos": ".REQUISITOS", "requisito": ".REQUISITOS", "req": ".REQUISITOS",
    "ux": ".UX", "ui": ".UX",
    "gp": ".GP", "gestao": ".GP", "gestao de projeto": ".GP",
    "testes": ".TESTES", "teste": ".TESTES", "qa": ".TESTES",
    "db": ".DB", "banco": ".DB", "banco de dados": ".DB",
    "publicacao": ".PUBLICACAO", "deploy": ".PUBLICACAO",
    "revisao": ".REVISAO", "review": ".REVISAO",
    "construcao": ".CONSTRUCAO", "prototipo": ".PROTOTIPO", "pesquisa": ".PESQUISA",
}


def compact_hu_id(value):
    return re.sub(r"\s+", "", str(value or "")).upper()


@lru_cache(maxsize=4096)
def extract_hu_from_labels(labels):
    if not labels or _lower(labels) in ("", "nan"):
        return ""
    for part in (p.strip() for p in str(labels).split(";") if p.strip()):
        if part.upper().startswith("HU"):
            match = HU_ID_RE.match(part)
            return match.group(1).replace(" ", "").upper() if match else part.strip()
    return ""


@lru_cache(maxsize=4096)
def extract_hu_from_title(title):
    if not title or _lower(title) in ("", "nan"):
        return ""
    match = HU_ID_RE.search(str(title))
    return compact_hu_id(match.group(1)) if match else ""


@lru_cache(maxsize=4096)
def extract_hu_for_task(title, labels):
    return extract_hu_from_title(title) or extract_hu_from_labels(labels)


def bracketed_hu_segment(text, hu_start):
    bracket_start = None
    for index in range(hu_start, -1, -1):
        if text[index] == "]":
            break
        if text[index] == "[":
            bracket_start = index
            break
    if bracket_start is None or text[bracket_start + 1:hu_start].strip():
        return ""

    depth = 0
    for index in range(bracket_start, len(text)):
        if text[index] == "[":
            depth += 1
        elif text[index] == "]":
            depth -= 1
            if depth == 0:
                return re.sub(r"\s+", " ", text[bracket_start + 1:index]).strip()
    return ""


@lru_cache(maxsize=4096)
def extract_hu_full_from_title(title):
    if not title or _lower(title) in ("", "nan"):
        return ""
    text = str(title).strip()
    match = HU_ID_RE.search(text)
    if not match:
        return ""
    bracketed = bracketed_hu_segment(text, match.start())
    return bracketed or re.sub(r"\s+", " ", text[match.start():]).strip()


def hu_full_has_metadata(full_name, hu_id):
    compact = compact_hu_id(full_name)
    return bool(compact and compact != compact_hu_id(hu_id))


@lru_cache(maxsize=4096)
def extract_hu_full_label(labels):
    if not labels or _lower(labels) in ("", "nan"):
        return ""
    for part in (p.strip() for p in str(labels).split(";") if p.strip()):
        if HU_LABEL_RE.match(part):
            return part
    return ""


@lru_cache(maxsize=4096)
def extract_hu_full_for_task(title, labels):
    title_hu = extract_hu_from_title(title)
    label_hu = extract_hu_from_labels(labels)
    if title_hu:
        title_full = extract_hu_full_from_title(title)
        if hu_full_has_metadata(title_full, title_hu):
            return title_full
        label_full = extract_hu_full_label(labels)
        if label_hu == title_hu and hu_full_has_metadata(label_full, title_hu):
            return label_full
        return title_hu
    return extract_hu_full_label(labels) or label_hu


def profile_label_from_title_marker(marker):
    marker_text = re.sub(r"\s+", " ", _strip(marker)).strip()
    if not marker_text:
        return ""
    explicit_label = marker_text.startswith(".")
    lookup_text = marker_text.lstrip(". ").strip()
    key = _norm_text_key(lookup_text)
    alias = TITLE_PROFILE_MARKER_ALIASES.get(key)
    if alias:
        return alias
    if explicit_label and key and not key.startswith("hu") and not re.fullmatch(r"\d+\s*sp", key):
        return f".{lookup_text}".upper()
    return ""


@lru_cache(maxsize=4096)
def profile_labels_from_title(title):
    if not title or _lower(title) in ("", "nan"):
        return ""
    labels = []
    seen = set()
    for marker in TITLE_PROFILE_MARKER_RE.findall(str(title)):
        label = profile_label_from_title_marker(marker)
        key = _norm_text_key(label)
        if label and key not in seen:
            labels.append(label)
            seen.add(key)
    return ";".join(labels)


@lru_cache(maxsize=4096)
def effective_profile_labels(title, labels):
    return profile_labels_from_title(title) or _strip(labels)
