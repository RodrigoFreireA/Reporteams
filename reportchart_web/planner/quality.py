"""Quality and scope classification rules for Planner task rows."""

from __future__ import annotations

from .text import normalize_text_key


QUALITY_BUG_ADJUSTMENT_TERMS = ("bug", "ajuste")
QUALITY_IMPEDIMENT_TERMS = (
    "impedimento", "impedido", "impeditivo", "bloqueio", "bloqueado", "blocked", "blocker",
)
SCOPE_CREEP_TERMS = ("imprevisto", "nao mapeado", "nao previsto")


def row_quality_text(row) -> str:
    return normalize_text_key(
        f"{row.get('labels', '')};{row.get('bucket_norm', '')};{row.get('bucket', '')}"
    )


def row_has_quality_term(row, terms) -> bool:
    text = row_quality_text(row)
    return any(term in text for term in terms)


def row_has_bug_or_adjustment(row) -> bool:
    return row_has_quality_term(row, QUALITY_BUG_ADJUSTMENT_TERMS)


def row_has_impediment(row) -> bool:
    return row_has_quality_term(row, QUALITY_IMPEDIMENT_TERMS)


def row_is_scope_creep(row) -> bool:
    if bool(row.get("is_nao_prev", False)):
        return True
    return any(term in row_quality_text(row) for term in SCOPE_CREEP_TERMS)
