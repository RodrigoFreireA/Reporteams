"""Classification rules for Planner areas, labels and categories."""

from __future__ import annotations

import re
from functools import lru_cache

from .text import lower_value, normalize_text_key, strip_value


AREA_KEYWORDS = {
    "Gestao": ["gp", "gestao", "gestão", "gerente", "gerencia", "coordena"],
    "Requisitos": ["requisito", "analista de negocio"],
    "Testes": ["teste", "q/a", "qa", "qualidade", "testador"],
    "Arquitetura": ["arquit"],
    "UX": ["ux", "ui", "design", "designer"],
    "Devs": ["dev", "frontend", "mobile", "desktop", "backend", "programad", "desenvolv"],
    "DB": ["db", "banco de dados", "dba"],
    "Publicacao": ["public", "deploy", "release"],
    "Revisao": ["revis", "review"],
    "Construcao": ["constr", "constru"],
    "Prototipo": ["proto"],
    "Pesquisa": ["bench", "pesquisa"],
}

AREA_DISPLAY = {
    "Gestao": "Gestão", "Requisitos": "Requisitos", "Testes": "Testes", "UX": "UX",
    "Devs": "Devs", "Arquitetura": "Arquitetura", "DB": "DB", "Publicacao": "Publicação",
    "Revisao": "Revisão", "Construcao": "Construção", "Prototipo": "Prototipo", "Pesquisa": "Pesquisa",
}

TEMPLATE_AREAS = [
    "Gestão", "Requisitos", "Testes", "UX", "Devs", "Revisão",
    "Arquitetura", "DB", "Publicação", "Construção", "Prototipo", "Pesquisa",
]


def area_for_assignee(assignee):
    value = lower_value(assignee)
    for area, keywords in AREA_KEYWORDS.items():
        if any(keyword in value for keyword in keywords):
            return area
    return "Outros"


@lru_cache(maxsize=4096)
def area_for_labels_or_assignee(labels, assignee):
    labels_text = strip_value(labels)
    if labels_text and lower_value(labels_text) not in ("", "nan"):
        for part in (p.strip() for p in labels_text.split(";") if p.strip()):
            if any(keyword in part.lower() for keywords in AREA_KEYWORDS.values() for keyword in keywords):
                for area, keywords in AREA_KEYWORDS.items():
                    if any(keyword in part.lower() for keyword in keywords):
                        return area
    return area_for_assignee(assignee)


@lru_cache(maxsize=4096)
def area_for_bucket_labels_assignee(bucket, labels, assignee):
    bucket_text = strip_value(bucket).lower()
    if "gestão" in bucket_text or "gestao" in bucket_text:
        return "Gestao"
    label_keys = {normalize_label_key(part) for part in labels.split(";") if part.strip()}
    if "gp" in label_keys or ".gp" in label_keys:
        return "Gestao"
    if "em teste" in bucket_text:
        return "Revisao"
    return area_for_labels_or_assignee(labels, assignee)


@lru_cache(maxsize=8192)
def categories_from_labels(labels):
    if not labels or lower_value(labels) in ("", "nan"):
        return ()
    return tuple(p.strip() for p in str(labels).split(";") if p.strip())


def normalize_label_key(value):
    return normalize_text_key(value)


def row_has_label_key(labels_text, target_key):
    if not labels_text or not target_key:
        return False
    return any(normalize_label_key(token) == target_key for token in categories_from_labels(labels_text))


def count_rows_with_label(df, label_text):
    key = normalize_label_key(label_text)
    if not key or "labels" not in df.columns:
        return 0
    return int(df["labels"].fillna("").astype(str).apply(lambda value: row_has_label_key(value, key)).sum())
