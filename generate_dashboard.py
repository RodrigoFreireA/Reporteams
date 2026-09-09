#!/usr/bin/env python3
"""
OnePageReport Dashboard Generator v3 - Template Filling Approach
Copy the spreadsheet template and populate data tabs using a raw export
from Microsoft Planner / Teams board.

Usage:
    python generate_dashboard.py <input_file.xlsx> [output_file.xlsx] \
        [--template template.xlsx] [--author "Nome - Cargo"]
"""

import sys
import os
import io
import re
import shutil
import argparse
import calendar
import unicodedata
import zipfile
from bisect import bisect_right
from datetime import datetime, timedelta, date
from collections import defaultdict
from functools import lru_cache

# ─── UTF-8 stdout wrapper (Windows cp1252 fix) ────────────────────────────────
if hasattr(sys.stdout, "buffer") and sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import pandas as pd
from openpyxl import load_workbook

from reportchart_web.planner.text import (
    lower_value as _lower,
    normalize_text_key as _norm_text_key,
    parse_date as _parse_date,
    strip_value as _strip,
)
from reportchart_web.planner.identifiers import (
    compact_hu_id as _compact_hu_id,
    effective_profile_labels as _effective_profile_labels_for_task_cached,
    extract_hu_for_task as _extract_hu_for_task_cached,
    extract_hu_from_labels as _extract_hu_cached,
    extract_hu_from_title as _extract_hu_from_title_cached,
    extract_hu_full_for_task as _extract_hu_full_for_task_cached,
    extract_hu_full_from_title as _extract_hu_full_from_title_cached,
    extract_hu_full_label as _extract_hu_full_label,
    hu_full_has_metadata as _hu_full_has_metadata,
    profile_label_from_title_marker as _profile_label_from_title_marker,
    profile_labels_from_title as _profile_labels_from_title_cached,
)
from reportchart_web.planner.classification import (
    AREA_DISPLAY,
    AREA_KEYWORDS,
    TEMPLATE_AREAS,
    area_for_assignee as _area_for_assignee,
    area_for_bucket_labels_assignee as _area_for_bucket_labels_assignee,
    area_for_labels_or_assignee as _area_for_labels_or_assignee_cached,
    categories_from_labels as _categories_from_labels,
    count_rows_with_label as _count_rows_with_label,
    normalize_label_key as _norm_label_key,
    row_has_label_key as _row_has_label_key,
)
from reportchart_web.planner.metrics import (
    average as _avg,
    flow_efficiency as _flow_efficiency,
    percentage as _pct,
    population_stddev as _stddev_population,
)
from reportchart_web.planner.quality import (
    row_has_bug_or_adjustment as _row_has_bug_or_adjustment,
    row_has_impediment as _row_has_impediment,
    row_is_scope_creep as _row_is_scope_creep,
    row_quality_text as _row_quality_text,
)
from reportchart_web.planner.excel_loader import load_base as _load_planner_excel

# Compatibilidade para consumidores que ainda importam o loader deste módulo.
load_base = _load_planner_excel

# ─────────────────────────────── KEYWORDS ────────────────────────────────────
NAO_PREVISTO_KW = ["nao previsto","não previsto","nao mapeado","não mapeado","nao_previsto"]
BACKLOG_KW      = ["backlog","incremento"]
EXCLUDE_CAT     = {"cancelado","residual","bugs e ajustes","cms","banco de dados",
                   "nao previsto","não previsto","backlog","incremento"}


# ─────────────────────────────── HELPERS ─────────────────────────────────────
HU_ID_RE        = re.compile(r"(HU\s*\d+)", re.IGNORECASE)
HU_LABEL_RE     = re.compile(r"HU\s*\d+", re.IGNORECASE)
SP_BRACKET_RE   = re.compile(r"\[(\d+)\s*SP\]", re.IGNORECASE)
HU_SCOPE_ADD_RE = re.compile(r"\[\s*\+E\s*(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\s*\]", re.IGNORECASE)
SPRINT_GOAL_RE  = re.compile(r"(?i)^sprint\s+goal\s*[:\-]\s*")
TITLE_PROFILE_MARKER_RE = re.compile(r"\[\s*([^\]]+?)\s*\]")
NAO_PREV_RE     = re.compile("|".join(re.escape(k) for k in NAO_PREVISTO_KW), re.IGNORECASE)
BACKLOG_RE      = re.compile("|".join(re.escape(k) for k in BACKLOG_KW), re.IGNORECASE)

TITLE_PROFILE_MARKER_ALIASES = {
    "dev": ".DEV",
    "desenvolvimento": ".DEV",
    "arquitetura": ".ARQUITETURA",
    "arquit": ".ARQUITETURA",
    "requisitos": ".REQUISITOS",
    "requisito": ".REQUISITOS",
    "req": ".REQUISITOS",
    "ux": ".UX",
    "ui": ".UX",
    "gp": ".GP",
    "gestao": ".GP",
    "gestao de projeto": ".GP",
    "testes": ".TESTES",
    "teste": ".TESTES",
    "qa": ".TESTES",
    "db": ".DB",
    "banco": ".DB",
    "banco de dados": ".DB",
    "publicacao": ".PUBLICACAO",
    "deploy": ".PUBLICACAO",
    "revisao": ".REVISAO",
    "review": ".REVISAO",
    "construcao": ".CONSTRUCAO",
    "prototipo": ".PROTOTIPO",
    "pesquisa": ".PESQUISA",
}


def _parse_effort(checklist_items_cell, completed_cell):
    if completed_cell and "/" in str(completed_cell):
        try:
            return int(str(completed_cell).split("/")[1])
        except Exception:
            pass
    if checklist_items_cell and str(checklist_items_cell).strip():
        s = str(checklist_items_cell).strip()
        return s.count(";") + 1
    return 0

def _is_nao_previsto(text):
    b = _lower(text)
    for kw in NAO_PREVISTO_KW:
        if kw in b:
            return True
    return False

def _is_backlog(bucket):
    b = _lower(bucket)
    for kw in BACKLOG_KW:
        if kw in b:
            return True
    return False

def _parse_date_series(series):
    """
    Vectorised date parsing with the exact same precedence as _parse_date:
    %d/%m/%Y, %Y-%m-%d, %m/%d/%Y, %d-%m-%Y.
    """
    s = series.fillna("").astype(str).str.strip()
    s = s.mask(s.str.lower().isin({"", "nan", "none"}))

    parsed = pd.Series(pd.NaT, index=s.index, dtype="datetime64[ns]")
    formats = ("%d/%m/%Y", "%Y-%m-%d", "%m/%d/%Y", "%d-%m-%Y")
    for fmt in formats:
        missing = parsed.isna() & s.notna()
        if not missing.any():
            break
        parsed.loc[missing] = pd.to_datetime(s[missing], format=fmt, errors="coerce")

    out = parsed.dt.date
    return out.where(parsed.notna(), None)
def _extract_gp_storypoints_by_hu(wb):
    """
    Extrai storypoints por HU a partir da aba gp_Plann_Sprint.
    Soma todas as células numéricas por coluna de HU (ignorando N/A).
    Retorna dict {HUxxx: sp_total}.
    """
    sheet_name = None
    for cand in ("gp_Plann_Sprint", "Gp_Plann_Sprint"):
        if cand in wb.sheetnames:
            sheet_name = cand
            break
    if sheet_name is None:
        return {}

    ws = wb[sheet_name]
    hu_cols = []  # list[(col_idx, hu_short)]
    for c in range(2, ws.max_column + 1):
        v = ws.cell(1, c).value
        if v is None or str(v).strip() == "":
            continue
        m = re.search(r"\b(HU\d+)\b", str(v), flags=re.IGNORECASE)
        if m:
            hu_cols.append((c, m.group(1).upper()))

    if not hu_cols:
        return {}

    out = {hu: 0.0 for _, hu in hu_cols}
    for c, hu in hu_cols:
        s = 0.0
        for r in range(2, ws.max_row + 1):
            first = ws.cell(r, 1).value
            if first is None and r > 20:
                break
            raw = ws.cell(r, c).value
            try:
                if isinstance(raw, str) and raw.strip().upper() == "N/A":
                    continue
                if raw is None or str(raw).strip() == "":
                    continue
                s += float(str(raw).replace(",", "."))
            except Exception:
                continue
        out[hu] = round(s, 2)

    return out


def _enrich_kpis_with_hu_storypoints(kpis, df, hu_storypoints):
    """
    Atualiza storypoints e métricas HU/SP dos KPIs com base em HU + storypoints.
    """
    total_sp = round(sum(v for v in hu_storypoints.values() if v), 2)
    kpis["storypoints"] = total_sp

    hu_ct_means = []
    hu_lt_means = []
    weighted_ct_num = 0.0
    weighted_ct_den = 0.0
    weighted_lt_num = 0.0
    weighted_lt_den = 0.0

    for hu, grp in df[df["hu"] != ""].groupby("hu"):
        g_done = grp[grp["done_kpi"] & grp["date_done"].notna()]
        if g_done.empty:
            continue

        # Cycle = conclusão - início
        ct_vals = []
        for _, row in g_done[g_done["date_start"].notna()].iterrows():
            delta = (row["date_done"] - row["date_start"]).days
            if delta >= 0:
                ct_vals.append(delta)
        if ct_vals:
            ct_mean = sum(ct_vals) / len(ct_vals)
            hu_ct_means.append(ct_mean)
            sp = hu_storypoints.get(str(hu).upper(), 0) or 0
            if sp > 0:
                weighted_ct_num += ct_mean * sp
                weighted_ct_den += sp

        # Lead = conclusão - criação (com proteção início<criação)
        lt_vals = []
        for _, row in g_done[g_done["date_criacao"].notna()].iterrows():
            d_done = row["date_done"]
            d_cr = row["date_criacao"]
            d_start = row.get("date_start")
            base = max(d_cr, d_start) if (d_start is not None and not pd.isna(d_start)) else d_cr
            delta = (d_done - base).days
            if delta >= 0:
                lt_vals.append(delta)
        if lt_vals:
            lt_mean = sum(lt_vals) / len(lt_vals)
            hu_lt_means.append(lt_mean)
            sp = hu_storypoints.get(str(hu).upper(), 0) or 0
            if sp > 0:
                weighted_lt_num += lt_mean * sp
                weighted_lt_den += sp

    if hu_ct_means:
        kpis["ct_hu"] = round(sum(hu_ct_means) / len(hu_ct_means), 2)
    if hu_lt_means:
        kpis["lt_hu"] = round(sum(hu_lt_means) / len(hu_lt_means), 2)
    kpis["ct_sp"] = round(weighted_ct_num / weighted_ct_den, 2) if weighted_ct_den > 0 else kpis.get("ct_hu", 0)
    kpis["lt_sp"] = round(weighted_lt_num / weighted_lt_den, 2) if weighted_lt_den > 0 else kpis.get("lt_hu", 0)


# ────────────────────────────── COMPUTE ──────────────────────────────────────
def compute_all(df_raw, plan_name, export_date_str=""):
    """Normalise column names, parse dates and return enriched DataFrame."""
    COL_MAP = {
        "nome da tarefa":                           "tarefa",
        "task name":                                "tarefa",
        "nome do bucket":                           "bucket",
        "bucket name":                              "bucket",
        "categoria":                                "bucket",
        "atribuído a":                              "assignee",
        "assigned to":                              "assignee",
        "concluído em":                             "data_conclusao",
        "date completed":                           "data_conclusao",
        "data de conclusão":                        "data_due",
        "data de vencimento":                       "data_due",
        "due date":                                 "data_due",
        "data de início":                           "data_inicio",
        "start date":                               "data_inicio",
        "data de criação":                          "data_criacao",
        "created date":                             "data_criacao",
        "data de criacao":                          "data_criacao",
        "criado em":                                "data_criacao",
        "progresso":                                "pct_done_raw",
        "status":                                   "pct_done_raw",
        "percentual concluído":                     "pct_done",
        "% concluída":                              "pct_done",
        "percent complete":                         "pct_done",
        "rótulos":                                  "labels",
        "labels":                                   "labels",
        "notas":                                    "notas",
        "descrição":                                "notas",
        "notes":                                    "notas",
        "itens da lista de verificação":            "checklist_items",
        "checklist items":                          "checklist_items",
        "itens concluídos da lista de verificação": "checklist_done",
        "completed checklist items":                "checklist_done",
    }
    cols_lower = {c.lower(): c for c in df_raw.columns}
    rename = {}
    for alias, canon in COL_MAP.items():
        if alias in cols_lower:
            rename[cols_lower[alias]] = canon
    df = df_raw.rename(columns=rename).copy()

    for c in ["tarefa","bucket","assignee","data_conclusao","data_inicio",
              "data_due","pct_done","pct_done_raw","labels","notas",
              "checklist_items","checklist_done","data_criacao"]:
        if c not in df.columns:
            df[c] = ""

    pct_raw = df["pct_done_raw"].fillna("").astype(str).str.strip()
    pct_num = pd.to_numeric(
        df["pct_done"].fillna("").astype(str).str.replace("%", "", regex=False),
        errors="coerce"
    ).fillna(0)

    date_done = _parse_date_series(df["data_conclusao"])
    date_start = _parse_date_series(df["data_inicio"])
    date_due = _parse_date_series(df["data_due"])
    date_criacao = _parse_date_series(df.get("data_criacao", pd.Series([""] * len(df))))

    pct_raw_norm = pct_raw.apply(
        lambda s: "".join(
            ch for ch in unicodedata.normalize("NFKD", s)
            if not unicodedata.combining(ch)
        ).lower().strip()
    )
    done_by_text = pct_raw_norm == "concluida"
    done_by_pct = pct_num >= 100
    done_by_date = date_done.notna()

    # Regra de neg?cio: "Conclu?da" ? definida por status de progresso.
    # Datas de conclus?o s?o usadas para timeline, mas n?o para reclassificar status.
    df["done"] = done_by_text | done_by_pct
    df["done_kpi"] = df["done"]
    df["done_by_date"] = done_by_date
    df["date_done"] = date_done
    df["date_start"] = date_start
    df["date_due"] = date_due
    df["date_criacao"] = date_criacao

    checklist_done = df["checklist_done"].fillna("").astype(str).str.strip()
    effort_from_completed = pd.to_numeric(
        checklist_done.str.extract(r"/\s*(\d+)")[0],
        errors="coerce",
    )
    checklist_items = df["checklist_items"].fillna("").astype(str).str.strip()
    effort_from_items = checklist_items.str.count(";") + checklist_items.ne("").astype(int)
    df["effort"] = effort_from_completed.fillna(effort_from_items).fillna(0).astype(int)

    bucket_norm = df["bucket"].fillna("").astype(str).str.strip()
    bucket_lower = bucket_norm.str.lower()
    title_text = df["tarefa"].fillna("").astype(str)
    labels_text = df["labels"].fillna("").astype(str)
    labels_lower = labels_text.str.lower()

    df["bucket_norm"] = bucket_norm
    df["is_nao_prev"] = (
        bucket_lower.str.contains(NAO_PREV_RE, na=False)
        | labels_lower.str.contains(NAO_PREV_RE, na=False)
    )
    df["is_backlog"] = bucket_lower.str.contains(BACKLOG_RE, na=False)
    df["hu"] = [
        _extract_hu_for_task_cached(title, labels)
        for title, labels in zip(title_text.tolist(), labels_text.tolist())
    ]

    title_values = title_text.tolist()
    label_values = labels_text.tolist()
    profile_labels = [
        _effective_profile_labels_for_task_cached(title, labels)
        for title, labels in zip(title_values, label_values)
    ]
    df["profile_labels"] = profile_labels

    assignees = df["assignee"].fillna("").astype(str).tolist()
    bucket_list = bucket_norm.tolist()
    df["area"] = [
        _area_for_bucket_labels_assignee(bkt, lbl, assignee)
        for bkt, lbl, assignee in zip(bucket_list, profile_labels, assignees)
    ]

    all_dates = []
    for col in ["date_done","date_start","date_due"]:
        all_dates += df[col].dropna().tolist()

    sprint_start = min(all_dates) if all_dates else date.today()
    sprint_end   = max(all_dates) if all_dates else date.today()
    # Use export date from Nome do plano sheet if available, else today
    export_date  = _parse_date(export_date_str) or date.today()
    sprint_name  = plan_name or "Sprint"

    # Extract Sprint Goal text without removing the row from the dataset
    sprint_goal = ""
    mask = df["tarefa"].fillna("").astype(str).str.strip().str.lower() == "sprint goal"
    if mask.any():
        raw_goal = _strip(df.loc[mask, "notas"].iloc[0])
        # Strip common prefixes like "Sprint goal: " or "Sprint Goal: "
        sprint_goal = SPRINT_GOAL_RE.sub("", raw_goal).strip()

    return df, sprint_name, sprint_start, sprint_end, export_date, sprint_goal


def _parse_ignore_labels(ignore_labels):
    """
    Parse the ignore labels configuration.
    Accepts separators ';' or ',' and returns normalized label keys.
    """
    if ignore_labels is None:
        return set()

    if isinstance(ignore_labels, (list, tuple, set)):
        parts = []
        for item in ignore_labels:
            parts.extend(re.split(r"[;,]", str(item)))
    else:
        parts = re.split(r"[;,]", str(ignore_labels))

    return {_norm_label_key(p) for p in parts if str(p).strip()}


def _labels_has_ignored_token(labels_text, ignored_tokens):
    if not ignored_tokens:
        return False
    if labels_text is None:
        return False

    parts = [p.strip() for p in str(labels_text).split(";") if p.strip()]
    for p in parts:
        if _norm_label_key(p) in ignored_tokens:
            return True
    return False


def _apply_ignore_labels(df, ignore_labels=None):
    """
    Remove rows whose labels contain any ignored token.
    Returns (filtered_df, removed_count).
    """
    ignored_tokens = _parse_ignore_labels(ignore_labels)
    if not ignored_tokens:
        return df, 0

    mask_ignored = df["labels"].fillna("").astype(str).apply(
        lambda s: _labels_has_ignored_token(s, ignored_tokens)
    )
    removed = int(mask_ignored.sum())
    if removed <= 0:
        return df, 0

    return df.loc[~mask_ignored].copy(), removed


def _recompute_sprint_bounds(df, fallback_start, fallback_end):
    all_dates = []
    for col in ("date_done", "date_start", "date_due"):
        if col in df.columns:
            all_dates += df[col].dropna().tolist()

    if all_dates:
        return min(all_dates), max(all_dates)
    return fallback_start, fallback_end


# ─────────────────────────────── KPIs ────────────────────────────────────────
def build_kpis(df):
    # KPIs usam TODAS as tarefas (conforme Prompt Mestre: "Total = total de registros")
    total         = len(df)
    done          = int(df["done_kpi"].sum())
    pending       = total - done
    nao_prev      = int(df["is_nao_prev"].sum())
    backlog_total = int(df["is_backlog"].sum())
    sem_hu        = int((df["hu"] == "").sum())

    # Tarefas concluídas com datas válidas (para métricas de tempo)
    df_done = df[df["done_kpi"] & df["date_done"].notna()].copy()

    # CYCLE TIME TASK = média de (conclusão − início) para tarefas concluídas
    # Usa date_start (Data de Início)
    ct_task = None
    df_ct = df_done[df_done["date_start"].notna()].copy()
    if len(df_ct) > 0:
        delta_ct = [(d - s).days for d, s in zip(df_ct["date_done"].tolist(), df_ct["date_start"].tolist()) if d and s and (d - s).days >= 0]
        ct_task = round(sum(delta_ct) / len(delta_ct), 2) if delta_ct else None

    # LEAD TIME TASK = média de (conclusão − criação) para tarefas concluídas
    lt_task = None
    df_lt = df_done[df_done["date_criacao"].notna()].copy()
    if len(df_lt) > 0:
        delta_lt = []
        for d, c, s in zip(df_lt["date_done"].tolist(), df_lt["date_criacao"].tolist(), df_lt["date_start"].fillna(pd.NaT).tolist()):
            if d and c:
                # Se data início < criação, usa criação como base
                base = max(c, s) if (s and not pd.isna(s)) else c
                delta = (d - base).days
                if delta >= 0:
                    delta_lt.append(delta)
        lt_task = round(sum(delta_lt) / len(delta_lt), 2) if delta_lt else None

    # CYCLE TIME HU = média dos cycle times por HU, depois média das médias
    ct_hu = None
    lt_hu = None
    hu_groups = [(hu, grp) for hu, grp in df[df["hu"] != ""].groupby("hu")]
    if hu_groups:
        hu_ct_means = []
        hu_lt_means = []
        for _, grp in hu_groups:
            g_done = grp[grp["done_kpi"] & grp["date_done"].notna()]
            # CT por HU
            g_ct = g_done[g_done["date_start"].notna()]
            if len(g_ct) > 0:
                deltas = [(d - s).days for d, s in zip(g_ct["date_done"].tolist(), g_ct["date_start"].tolist()) if d and s and (d-s).days >= 0]
                if deltas:
                    hu_ct_means.append(sum(deltas) / len(deltas))
            # LT por HU
            g_lt = g_done[g_done["date_criacao"].notna()]
            if len(g_lt) > 0:
                deltas = []
                for d, c, s in zip(g_lt["date_done"].tolist(), g_lt["date_criacao"].tolist(), g_lt["date_start"].fillna(pd.NaT).tolist()):
                    if d and c:
                        base = max(c, s) if (s and not pd.isna(s)) else c
                        delta = (d - base).days
                        if delta >= 0:
                            deltas.append(delta)
                if deltas:
                    hu_lt_means.append(sum(deltas) / len(deltas))
        ct_hu = round(sum(hu_ct_means) / len(hu_ct_means), 2) if hu_ct_means else None
        lt_hu = round(sum(hu_lt_means) / len(hu_lt_means), 2) if hu_lt_means else None

    # Stakeholders = contagem de responsáveis distintos
    stakeholders = int(df["assignee"].fillna("").astype(str).str.strip().replace("", pd.NA).dropna().nunique())

    pct_entrega = round(done / total, 4) if total else 0

    return {
        "total":         int(total),
        "done":          done,
        "pending":       pending,
        "nao_prev":      nao_prev,
        "sem_hu":        sem_hu,
        "backlog_total": backlog_total,
        "ct_task":       ct_task,
        "lt_task":       lt_task,
        "ct_hu":         ct_hu,
        "lt_hu":         lt_hu,
        "pct_entrega":   pct_entrega,
        "stakeholders":  stakeholders,
    }


# ─────────────────────────────── HU LIST + NAMES ─────────────────────────────
def build_hu_list(df):
    """Returns [(hu_id, total, done)] sorted by hu_id."""
    dfw = df[df["hu"] != ""].copy()
    rows = []
    for hu, grp in dfw.groupby("hu"):
        rows.append((hu, len(grp), int(grp["done"].sum())))
    rows.sort(key=lambda x: x[0])
    return rows


def build_hu_full_names(df):
    """
    Map HU short IDs (e.g. 'HU044') to full strings from task title first,
    falling back to Planner labels.
    """
    hu_names = {}
    df_hu = df[df["hu"] != ""]

    for hu_id, title, labels in zip(
        df_hu["hu"].tolist(),
        df_hu["tarefa"].fillna("").astype(str).tolist(),
        df_hu["labels"].fillna("").astype(str).tolist(),
    ):
        if hu_id in hu_names:
            continue

        full_name = _extract_hu_full_for_task_cached(title, labels)
        hu_names[hu_id] = full_name or hu_id

    return hu_names

def build_hu_storypoints_from_labels(df):
    """
    Extrai story points (SP) dos nomes das HUs no titulo da tarefa ou rotulos.
    Formato esperado: 'HU054 - CMS Layout [37SP]' → {'HU054': 37}
    Retorna dict {hu_id: sp_int} e total_sp (int).
    """
    hu_full_names = build_hu_full_names(df)
    hu_sp = {}
    for hu_id, full_name in hu_full_names.items():
        m = SP_BRACKET_RE.search(full_name)
        if m:
            hu_sp[hu_id] = int(m.group(1))
    total_sp = sum(hu_sp.values())
    return hu_sp, total_sp


def _resolve_scope_marker_date(day_text, month_text, year_text=None, sprint_start=None, sprint_end=None, export_date=None):
    try:
        day = int(day_text)
        month = int(month_text)
    except Exception:
        return None

    if year_text:
        try:
            year = int(year_text)
            if year < 100:
                year += 2000
            return date(year, month, day)
        except Exception:
            return None

    refs = [v for v in (sprint_start, sprint_end, export_date) if _is_valid_date(v)]
    if not refs:
        refs = [date.today()]

    years = set()
    for ref in refs:
        years.update({ref.year - 1, ref.year, ref.year + 1})

    candidates = []
    for year in sorted(years):
        try:
            candidates.append(date(year, month, day))
        except Exception:
            continue
    if not candidates:
        return None

    start = sprint_start if _is_valid_date(sprint_start) else None
    end = sprint_end if _is_valid_date(sprint_end) else None
    if start and end and end < start:
        start, end = end, start

    def score(candidate):
        in_window = 0 if start and end and start <= candidate <= end else 1
        distance = min(abs((candidate - ref).days) for ref in refs)
        return (in_window, distance)

    return min(candidates, key=score)


def build_hu_scope_events_from_labels(df, sprint_start=None, sprint_end=None, export_date=None, hu_storypoints=None):
    hu_full_names = build_hu_full_names(df)
    events = {}
    for hu_id, full_name in hu_full_names.items():
        match = HU_SCOPE_ADD_RE.search(full_name or "")
        if not match:
            continue
        event_date = _resolve_scope_marker_date(
            match.group(1),
            match.group(2),
            match.group(3),
            sprint_start=sprint_start,
            sprint_end=sprint_end,
            export_date=export_date,
        )
        if not event_date:
            continue
        events[hu_id] = {
            "type": "add",
            "date": event_date,
            "marker": match.group(0),
            "label": full_name,
            "sp": float((hu_storypoints or {}).get(str(hu_id).upper(), 0) or 0),
        }
    return events


def _serialize_scope_events(events, hu_weights=None):
    rows = []
    hu_weights = hu_weights or {}
    for hu, event in sorted((events or {}).items(), key=lambda item: (item[1].get("date") or date.min, item[0])):
        event_date = event.get("date")
        rows.append({
            "hu": hu,
            "type": event.get("type") or "add",
            "date": event_date.strftime("%Y-%m-%d") if _is_valid_date(event_date) else None,
            "marker": event.get("marker") or "",
            "label": event.get("label") or hu,
            "sp": round(float(event.get("sp") or 0), 2),
            "weight": round(float(hu_weights.get(hu, 0) or 0), 2),
        })
    return rows


def _serialize_task_scope_events_from_burndown(rows):
    events = []
    for row in rows or []:
        if not row or not row[0]:
            continue
        added = int(row[6] or 0) if len(row) > 6 else 0
        if added <= 0:
            continue
        events.append({
            "type": "add",
            "date": row[0],
            "label": "Nao Previsto",
            "count": added,
        })
    return events


def _scope_event_index(event_date, bd_start, days):
    if not _is_valid_date(event_date):
        return 0
    return min(max((event_date - bd_start).days, 0), max(days - 1, 0))


def _linear_burn_from(total, current_index, start_index, end_index):
    total = float(total or 0)
    if total <= 0 or current_index < start_index:
        return 0.0
    span = max(end_index - start_index, 1)
    return max(total * (1 - (current_index - start_index) / span), 0.0)


def _step_plan_from(total, current_index, start_index, days, blocks=5):
    if float(total or 0) <= 0 or current_index < start_index:
        return 0.0
    return _build_step_plan(total, max(days - start_index, 1), blocks=blocks)[current_index - start_index]


def _row_scope_entry_date(row, default_date=None):
    for col in ("date_criacao", "date_start", "date_done", "date_due"):
        value = row.get(col)
        if _is_valid_date(value):
            return value
    return default_date


def _resolve_burndown_window(df, sprint_start=None, sprint_end=None, min_days=31):
    """
    Resolve a janela temporal do burndown com regra de negocio:
    - inicio = menor data entre criacao e inicio da tarefa
    - fim minimo = inicio + (min_days - 1)
    - se houver data maior no board, estende ate essa data
    """
    start_candidates = []
    for col in ("date_criacao", "date_start"):
        if col not in df.columns:
            continue
        for v in df[col].tolist():
            if _is_valid_date(v):
                start_candidates.append(v)

    if start_candidates:
        start = min(start_candidates)
    else:
        ref = sprint_end if _is_valid_date(sprint_end) else sprint_start
        if not _is_valid_date(ref):
            ref = date.today()
        start, end = _month_bounds(ref)
        return start, end, (end - start).days + 1

    min_end = start + timedelta(days=max(int(min_days), 1) - 1)
    board_candidates = []
    for col in ("date_criacao", "date_start", "date_done", "date_due"):
        if col not in df.columns:
            continue
        for v in df[col].tolist():
            if _is_valid_date(v):
                board_candidates.append(v)

    max_board = max(board_candidates) if board_candidates else min_end
    end = max(min_end, max_board)
    return start, end, (end - start).days + 1


def _precompute_burndown_sp(df, sprint_start, sprint_end, export_date, hu_storypoints):
    """
    Burndown por Story Points: cada tarefa pesa SP_da_HU / total_tarefas_da_HU.
    Colunas: [data, meta_linear, a_realizar]
    """
    from datetime import timedelta, datetime as _dt
    dfw = df[(~df["is_backlog"]) & (df["hu"] != "")].copy()
    bd_start, bd_end, days = _resolve_burndown_window(dfw, sprint_start, sprint_end)

    total_sp = float(sum(hu_storypoints.values())) if hu_storypoints else 0.0
    if total_sp == 0:
        return [[None, None, None]] * days

    # Peso SP por tarefa: distribui o SP da HU igualmente entre suas tarefas
    task_weight = {}
    for hu_id, grp in dfw.groupby("hu"):
        sp = float(hu_storypoints.get(str(hu_id).upper(), 0) or 0)
        count = len(grp)
        if count > 0:
            for idx in grp.index:
                task_weight[idx] = sp / count

    result = []
    for i in range(days):
        d = bd_start + timedelta(days=i)
        meta = round(total_sp * (1 - i / max(days - 1, 1)), 2)
        # SP ainda a realizar: tarefas não concluídas até o dia d
        sp_remaining = 0.0
        for idx, row in dfw.iterrows():
            w = task_weight.get(idx, 0.0)
            d_done = row.get("date_done")
            if not _is_valid_date(d_done) or d_done > d:
                sp_remaining += w
        # carry-forward após export_date
        if _is_valid_date(export_date) and d > export_date:
            ref = bd_start + timedelta(days=max(0, (export_date - bd_start).days))
            # recalcula sp_remaining para ref (não para d)
            pass  # já está correto: tarefas sem date_done ficam em "a realizar"
        result.append([d.strftime("%Y-%m-%d"), meta, round(sp_remaining, 2)])
    return result


def _precompute_burndown_sp(df, sprint_start, sprint_end, export_date, hu_storypoints, hu_scope_events=None):
    """
    Burndown por Story Points com suporte a HU nova marcada por [+Edd/mm].
    Colunas: [data, meta_revisada, a_realizar, escopo_acumulado, meta_original, sp_adicionado]
    """
    dfw = df[(~df["is_backlog"]) & (df["hu"] != "")].copy()
    bd_start, bd_end, days = _resolve_burndown_window(dfw, sprint_start, sprint_end)

    total_sp = float(sum(hu_storypoints.values())) if hu_storypoints else 0.0
    if total_sp == 0:
        return [[None, None, None]] * days

    hu_scope_events = hu_scope_events or {}

    task_weight = {}
    for hu_id, grp in dfw.groupby("hu"):
        sp = float(hu_storypoints.get(str(hu_id).upper(), 0) or 0)
        count = len(grp)
        if count > 0:
            for idx in grp.index:
                task_weight[idx] = sp / count

    event_sp_by_index = defaultdict(float)
    original_sp = 0.0
    hu_event_indexes = {}
    for hu_id, sp in hu_storypoints.items():
        hu = str(hu_id).upper()
        sp = float(sp or 0)
        event = hu_scope_events.get(hu)
        event_date = event.get("date") if event else None
        if event and _is_valid_date(event_date) and event_date > bd_start:
            event_index = _scope_event_index(event_date, bd_start, days)
            event_sp_by_index[event_index] += sp
            hu_event_indexes[hu] = event_index
        else:
            original_sp += sp

    result = []
    for i in range(days):
        d = bd_start + timedelta(days=i)
        meta_original = _linear_burn_from(original_sp, i, 0, days - 1)
        meta = meta_original
        for event_index, event_sp in event_sp_by_index.items():
            meta += _linear_burn_from(event_sp, i, event_index, days - 1)
        scope_total = original_sp + sum(event_sp for event_index, event_sp in event_sp_by_index.items() if event_index <= i)
        added_today = event_sp_by_index.get(i, 0.0)

        sp_remaining = 0.0
        for idx, row in dfw.iterrows():
            hu = str(row.get("hu") or "").upper()
            event_index = hu_event_indexes.get(hu)
            if event_index is not None and i < event_index:
                continue
            w = task_weight.get(idx, 0.0)
            d_done = row.get("date_done")
            if not _is_valid_date(d_done) or d_done > d:
                sp_remaining += w

        result.append([
            d.strftime("%Y-%m-%d"),
            round(meta, 2),
            round(sp_remaining, 2),
            round(scope_total, 2),
            round(meta_original, 2),
            round(added_today, 2),
        ])
    return result


# ─────────────────────────── POR COLABORADOR ─────────────────────────────────
def build_por_colaborador(df):
    rows = []
    for person, grp in df.groupby("assignee"):
        name = _strip(person) or "Sem atribuição"
        done = int(grp["done"].sum())
        pend = len(grp) - done
        rows.append((name, done, pend))
    rows.sort(key=lambda x: -(x[1]+x[2]))
    return rows


# ─────────────────────────────── AREAS ───────────────────────────────────────
def build_areas(df):
    """Área = rótulos que começam com '.' (ponto), conforme novo prompt."""
    from collections import defaultdict
    area_counts = defaultdict(int)
    for label_text in df["labels"].fillna("").astype(str).tolist():
        for lbl in label_text.split(";"):
            lbl = lbl.strip()
            if lbl.startswith("."):
                area_counts[lbl] += 1
    rows = [(area, count, 0) for area, count in area_counts.items()]
    rows.sort(key=lambda x: -x[1])
    return rows


# ─────────────────────────────── HU IN/OUT ───────────────────────────────────
def build_hu_in_out(df):
    dfw = df[~df["is_backlog"]].copy()
    in_hu  = int((dfw["hu"] != "").sum())
    out_hu = int((dfw["hu"] == "").sum())
    return [("Em HU", in_hu), ("Fora de HU", out_hu)]


# ─────────────────────────────── POR CATEGORIA ───────────────────────────────
def build_por_categoria(df):
    """Returns (cat_rows, bubble_rows)."""
    cat_counts = defaultdict(lambda: {"done": 0, "total": 0, "effort": 0, "label": ""})

    labels = df["labels"].fillna("").astype(str).tolist()
    done_vals = df["done"].astype(int).tolist()
    efforts = df["effort"].fillna(0).astype(int).tolist()

    for label_text, done, effort in zip(labels, done_vals, efforts):
        for cat in _categories_from_labels(label_text):
            key = _norm_label_key(cat)
            if not key:
                continue
            if not cat_counts[key]["label"]:
                cat_counts[key]["label"] = cat.strip()
            cat_counts[key]["total"] += 1
            cat_counts[key]["done"] += done
            cat_counts[key]["effort"] += effort

    PINNED_LAST = {"bugs e ajustes"}  # categorias sempre exibidas por último

    cat_rows = []
    bub_rows = []
    pinned_cat = []
    pinned_bub = []
    for _key, vals in sorted(cat_counts.items(), key=lambda x: -x[1]["total"]):
        cat = vals["label"]
        done = vals["done"]
        total = vals["total"]
        effort = vals["effort"]
        pend = total - done
        if _norm_label_key(cat) in PINNED_LAST:
            pinned_cat.append((cat, done, pend))
            pinned_bub.append((cat, done, total, effort))
        else:
            cat_rows.append((cat, done, pend))
            bub_rows.append((cat, done, total, effort))

    # Itens fixados sempre ao final (ex: BUGs e Ajustes)
    cat_rows.extend(pinned_cat)
    bub_rows.extend(pinned_bub)

    return cat_rows, bub_rows


# ─────────────────────────────── ESFORÇO HU ──────────────────────────────────
def build_esforco_hu_detailed(df):
    """
    Returns [(hu_id, max_effort_per_person, total_effort)] sorted by total desc.
    max_effort_per_person = max effort contributed by any single assignee for this HU.
    """
    rows = []
    for hu, grp in df[df["hu"] != ""].groupby("hu"):
        total_effort = int(grp["effort"].sum())
        per_person   = grp.groupby("assignee")["effort"].sum()
        max_ep       = int(per_person.max()) if not per_person.empty else 0
        rows.append((hu, max_ep, total_effort))
    rows.sort(key=lambda x: -x[2])
    return rows


# ─────────────────────────── BUILD RÓTULOS ───────────────────────────────────
def build_rotulos(df):
    """
    Returns list of (label_display, done, pending, lead_time, cycle_time) sorted by total desc.
    LeadTime = conclusão − início  (mean over done tasks with that label)
    CycleTime = conclusão − criação (mean over done tasks with that label)
    Label display = "Rótulo (done/total)"
    """
    from collections import defaultdict
    label_done   = defaultdict(int)
    label_total  = defaultdict(int)
    label_lt     = defaultdict(list)
    label_ct     = defaultdict(list)

    for _, row in df.iterrows():
        lbls = [l.strip() for l in str(row.get("labels", "")).split(";") if l.strip()]
        for lbl in lbls:
            key = lbl.strip()
            if not key:
                continue
            label_total[key] += 1
            if row.get("done_kpi"):
                label_done[key] += 1
                # Lead time: conclusão - início
                d_done  = row.get("date_done")
                d_start = row.get("date_start")
                d_criac = row.get("date_criacao")
                if d_done and pd.notna(d_done) and d_start and pd.notna(d_start):
                    lt = (d_done - d_start).days
                    if lt >= 0:
                        label_lt[key].append(lt)
                # Cycle time: conclusão - criação
                if d_done and pd.notna(d_done) and d_criac and pd.notna(d_criac):
                    ct = (d_done - d_criac).days
                    if ct >= 0:
                        label_ct[key].append(ct)

    rows = []
    for lbl in label_total:
        done  = label_done[lbl]
        total = label_total[lbl]
        pend  = total - done
        lt    = round(sum(label_lt[lbl]) / len(label_lt[lbl]), 2) if label_lt[lbl] else 0
        ct    = round(sum(label_ct[lbl]) / len(label_ct[lbl]), 2) if label_ct[lbl] else 0
        display = f"{lbl} ({done}/{total})"
        rows.append((display, done, pend, lt, ct))
    rows.sort(key=lambda x: -(x[1]+x[2]))
    return rows


# ─────────────────────── BUILD RESPONSÁVEIS ──────────────────────────────────
def build_responsaveis(df):
    """
    Returns list of (name_display, done_bucket, pending, lead_time, cycle_time) sorted by total desc.
    name_display = "Nome (done/total)"
    """
    rows = []
    for person, grp in df.groupby("assignee"):
        name = _strip(person) or "Sem atribuição"
        done_bucket = int(grp["done_kpi"].sum())
        pend        = len(grp) - done_bucket
        total       = len(grp)

        grp_done = grp[grp["done_kpi"] & grp["date_done"].notna()]
        # Lead time
        lt_vals = []
        for _, row in grp_done.iterrows():
            d_done  = row.get("date_done")
            d_start = row.get("date_start")
            if d_done and pd.notna(d_done) and d_start and pd.notna(d_start):
                lt = (d_done - d_start).days
                if lt >= 0:
                    lt_vals.append(lt)
        # Cycle time
        ct_vals = []
        for _, row in grp_done.iterrows():
            d_done  = row.get("date_done")
            d_criac = row.get("date_criacao")
            if d_done and pd.notna(d_done) and d_criac and pd.notna(d_criac):
                ct = (d_done - d_criac).days
                if ct >= 0:
                    ct_vals.append(ct)

        lt = round(sum(lt_vals) / len(lt_vals), 2) if lt_vals else 0
        ct = round(sum(ct_vals) / len(ct_vals), 2) if ct_vals else 0
        display = f"{name} ({done_bucket}/{total})"
        rows.append((display, done_bucket, pend, lt, ct))
    rows.sort(key=lambda x: -(x[1]+x[2]))
    return rows


# ──────────────────────────── BUILD CFD ──────────────────────────────────────
def build_cfd(df, sprint_start, export_date):
    """
    Cumulative Flow Diagram — daily counts for full month.
    Returns (dates, todo_list, doing_list, done_list)
    - To Do:   tasks where date_start is None or > day
    - Doing:   tasks where date_start <= day < date_done (or export if no date_done)
    - Done:    cumulative tasks with date_done <= day
    Carry-forward after export_date.
    """
    bd_start, bd_end = _month_bounds(sprint_start)
    days = (bd_end - bd_start).days + 1
    cutoff = export_date if isinstance(export_date, date) else export_date

    todo_list, doing_list, done_list = [], [], []
    last_todo = last_doing = last_done = None

    for i in range(days):
        d = bd_start + timedelta(days=i)
        if d <= cutoff:
            todo  = 0
            doing = 0
            done  = 0
            for _, row in df.iterrows():
                d_start = row.get("date_start")
                d_done  = row.get("date_done")
                # Done: cumulative
                if d_done and d_done <= d:
                    done += 1
                elif d_start and d_start <= d:
                    doing += 1
                else:
                    todo += 1
            last_todo, last_doing, last_done = todo, doing, done
        else:
            todo, doing, done = last_todo, last_doing, last_done
        todo_list.append(todo)
        doing_list.append(doing)
        done_list.append(done)

    dates = [datetime(bd_start.year, bd_start.month, (bd_start + timedelta(days=i)).day) for i in range(days)]
    return dates, todo_list, doing_list, done_list


# ──────────────────────────── BUILD WIP ──────────────────────────────────────
def build_wip(df, sprint_start, export_date):
    """
    WIP by bucket — daily counts for full month.
    Returns (dates, bucket_names, bucket_matrix)
    bucket_matrix[bucket_idx][day_idx] = count
    'Concluído' bucket is cumulative (growing). Others use interval [start, done).
    Carry-forward after export_date.
    """
    bd_start, bd_end = _month_bounds(sprint_start)
    days = (bd_end - bd_start).days + 1
    cutoff = export_date if isinstance(export_date, date) else export_date

    # Identifica buckets únicos (exceto backlog)
    all_buckets = df[~df["is_backlog"]]["bucket_norm"].fillna("").unique().tolist()
    # Ordena: Concluído primeiro, depois por frequência decrescente
    bucket_counts = df[~df["is_backlog"]]["bucket_norm"].value_counts().to_dict()
    all_buckets = sorted(all_buckets, key=lambda b: (
        0 if "conclu" in b.lower() else 1,
        -bucket_counts.get(b, 0)
    ))

    bucket_matrix = {b: [0]*days for b in all_buckets}
    last_state = {b: 0 for b in all_buckets}

    for i in range(days):
        d = bd_start + timedelta(days=i)
        if d <= cutoff:
            for bkt in all_buckets:
                count = 0
                is_concluido = "conclu" in bkt.lower()
                for _, row in df[~df["is_backlog"]].iterrows():
                    if row["bucket_norm"] != bkt:
                        continue
                    d_start = row.get("date_start")
                    d_done  = row.get("date_done")
                    if is_concluido:
                        # Cumulative: count if done on or before day
                        if d_done and d_done <= d:
                            count += 1
                    else:
                        # Interval: [start, done)
                        end = d_done if d_done else cutoff
                        if d_start and d_start <= d < end:
                            count += 1
                        elif not d_start and d <= (end or cutoff):
                            pass  # sem data início, não conta
                last_state[bkt] = count
                bucket_matrix[bkt][i] = count
        else:
            for bkt in all_buckets:
                bucket_matrix[bkt][i] = last_state[bkt]

    dates = [datetime(bd_start.year, bd_start.month, (bd_start + timedelta(days=i)).day) for i in range(days)]
    x_total = [sum(bucket_matrix[b][i] for b in all_buckets) for i in range(days)]
    return dates, all_buckets, bucket_matrix, x_total


def build_wip_prompt3(df, sprint_start, export_date):
    """
    WIP diario por rotulo (31 dias), com conservacao de inventario.

    Regras:
    - X_total = soma total de associacoes (rotulos) da base.
    - Colunas dinamicas: Backlog + todos os rotulos unicos + Concluido.
    - Backlog: soma X se Data_Inicio > Data_Ref (ou sem data_inicio).
    - WIP (rotulos): soma 1 por rotulo se
      Data_Inicio <= Data_Ref e (Data_Conclusao > Data_Ref ou nula).
    - Concluido: soma X se Data_Conclusao <= Data_Ref.
    - No dia da conclusao, sai do WIP e entra em Concluido.
    - Carry-forward apos data de exportacao.

    Retorna (dates, columns, matrix, x_total_rows)
      matrix[col_name][day_idx] = count
      x_total_rows[day_idx] = X_total (constante)
    """
    bd_start, bd_end = _month_bounds(sprint_start)
    days = (bd_end - bd_start).days + 1
    cutoff = export_date if isinstance(export_date, date) else bd_end
    if cutoff < bd_start:
        cutoff = bd_start
    if cutoff > bd_end:
        cutoff = bd_end

    # Mapeia todos os rotulos unicos (case-insensitive), preservando display.
    label_display = {}
    for labels_text in df["labels"].fillna("").astype(str).tolist():
        for token in _categories_from_labels(labels_text):
            key = _norm_label_key(token)
            if key and key not in label_display:
                label_display[key] = token.strip()

    label_keys = sorted(label_display.keys(), key=lambda k: label_display[k].lower())
    columns = ["Backlog"] + [label_display[k] for k in label_keys] + ["Concluido"]
    matrix = {c: [0] * days for c in columns}

    # Preprocessa tarefas com X = qtd de associacoes (rotulos unicos da tarefa).
    tasks = []
    for _, row in df.iterrows():
        seen = set()
        row_keys = []
        for token in _categories_from_labels(row.get("labels", "")):
            key = _norm_label_key(token)
            if key and key not in seen:
                seen.add(key)
                row_keys.append(key)

        x = len(row_keys)
        if x <= 0:
            continue

        d_start = row.get("date_start")
        d_done = row.get("date_done")
        if pd.isna(d_start):
            d_start = None
        if pd.isna(d_done):
            d_done = None
        tasks.append((row_keys, x, d_start, d_done))

    x_total_value = sum(x for _, x, _, _ in tasks)
    x_total_rows = [x_total_value] * days

    for i in range(days):
        d = bd_start + timedelta(days=i)

        # Repeticao apos exportacao (carry-forward).
        if i > 0 and d > cutoff:
            for c in columns:
                matrix[c][i] = matrix[c][i - 1]
            continue

        backlog = 0
        done = 0
        per_label = {k: 0 for k in label_keys}

        for row_keys, x, d_start, d_done in tasks:
            done_now = d_done is not None and d_done <= d
            started = d_start is not None and d_start <= d

            if done_now:
                done += x
                continue

            if started:
                # WIP: soma 1 por rotulo da tarefa.
                for k in row_keys:
                    per_label[k] += 1
            else:
                # Backlog: soma X da tarefa inteira.
                backlog += x

        matrix["Backlog"][i] = backlog
        for k in label_keys:
            matrix[label_display[k]][i] = per_label[k]
        matrix["Concluido"][i] = done

        # Conservacao de inventario: soma horizontal deve fechar em X_total.
        row_sum = backlog + done + sum(per_label.values())
        if row_sum != x_total_value:
            matrix["Backlog"][i] += (x_total_value - row_sum)

    dates = [
        datetime(bd_start.year, bd_start.month, (bd_start + timedelta(days=i)).day)
        for i in range(days)
    ]
    return dates, columns, matrix, x_total_rows


# ──────────────────────────── BUILD CTS ──────────────────────────────────────
def build_cts(df, sprint_start):
    """
    Completions per Time & Subject — matrix days × HU.
    Returns (dates, hu_labels, cts_matrix, fora_hu_daily)
    cts_matrix[hu_idx][day_idx] = count of tasks completed that day for that HU
    fora_hu_daily[day_idx] = count of tasks without HU completed that day
    """
    bd_start, bd_end = _month_bounds(sprint_start)
    days = (bd_end - bd_start).days + 1

    def _all_hus(labels_text):
        out = []
        seen = set()
        for token in [p.strip() for p in str(labels_text).split(";") if p.strip()]:
            m = re.search(r"\b(HU\s*0*\d+)\b", token, flags=re.IGNORECASE)
            if not m:
                continue
            num = re.sub(r"\D", "", m.group(1))
            hu = f"HU{num.zfill(3)}"
            if hu not in seen:
                seen.add(hu)
                out.append(hu)
        return out

    hu_set = set()
    hu_full = {}
    for _, row in df.iterrows():
        labels_text = str(row.get("labels", ""))
        full = _extract_hu_full_label(labels_text)
        for hu in _all_hus(labels_text):
            hu_set.add(hu)
            if hu not in hu_full:
                hu_full[hu] = full or hu
    hu_list = sorted(hu_set)

    cts_matrix   = [[0]*days for _ in hu_list]
    fora_hu_daily = [0]*days

    done_rows = df[df["done_kpi"] & df["date_done"].notna()]
    for _, row in done_rows.iterrows():
        d = row["date_done"]
        offset = (d - bd_start).days
        if 0 <= offset < days:
            hu = row["hu"]
            if hu and hu in hu_list:
                idx = hu_list.index(hu)
                cts_matrix[idx][offset] += 1
            else:
                fora_hu_daily[offset] += 1

    dates = [datetime(bd_start.year, bd_start.month, (bd_start + timedelta(days=i)).day) for i in range(days)]
    return dates, [hu_full.get(h, h) for h in hu_list], cts_matrix, fora_hu_daily


# ──────────────────────── BUILD HISTOGRAMA ───────────────────────────────────
def build_histograma(df):
    """
    Histograma de cycle time (conclusão − início) para tarefas concluídas.
    Returns (hist_31, indicativos)
    hist_31 = list of 31 values, index 0 = cycle time of 1 day
    indicativos = list of 31 values (0.5, 0.75, 0.9 at percentile positions, else None)
    """
    # Cycle time = conclusão − início (Lead Time)
    done_rows = df[df["done_kpi"] & df["date_done"].notna() & df["date_start"].notna()]
    ct_vals = []
    for _, row in done_rows.iterrows():
        delta = (row["date_done"] - row["date_start"]).days
        if delta >= 0:
            ct_vals.append(max(delta, 1))  # mínimo 1 dia

    hist_31 = [0] * 31
    for v in ct_vals:
        if 1 <= v <= 31:
            hist_31[v-1] += 1

    # Percentis (50%, 75%, 90%) baseados na distribuição cumulativa
    total = len(ct_vals)
    indicativos = [None] * 31
    if total > 0:
        cumsum = 0
        found = set()
        for i, count in enumerate(hist_31):
            cumsum += count
            pct = cumsum / total
            if 0.5 not in found and pct >= 0.5:
                indicativos[i] = 0.5
                found.add(0.5)
            elif 0.75 not in found and pct >= 0.75:
                indicativos[i] = 0.75
                found.add(0.75)
            elif 0.9 not in found and pct >= 0.9:
                indicativos[i] = 0.9
                found.add(0.9)

    return hist_31, indicativos


# ─────────────────────── BUILD HISTOGRAMA2 ───────────────────────────────────
def build_histograma2(df):
    """
    Estatísticas do histograma de tempos.
    Retorna lista de (descricao, valor) em ordem crescente de valor.
    Lead Time = conclusão − início
    Cycle Time = conclusão − criação
    """
    done_rows = df[df["done_kpi"] & df["date_done"].notna()]

    # Lead time values (conclusão − início)
    lt_vals = []
    for _, row in done_rows[done_rows["date_start"].notna()].iterrows():
        delta = (row["date_done"] - row["date_start"]).days
        if delta >= 0:
            lt_vals.append(max(delta, 1))

    # Cycle time values (conclusão − criação)
    ct_vals = []
    for _, row in done_rows[done_rows["date_criacao"].notna()].iterrows():
        d_criac = row["date_criacao"]
        d_start = row.get("date_start")
        d_done  = row["date_done"]
        # Se início < criação, usa criação
        base = max(d_criac, d_start) if d_start and not pd.isna(d_start) else d_criac
        delta = (d_done - base).days
        if delta >= 0:
            ct_vals.append(max(delta, 1))

    if not lt_vals:
        return []

    lt_sorted = sorted(lt_vals)
    n = len(lt_sorted)

    def median(vals):
        s = sorted(vals); m = len(s)
        return (s[m//2-1] + s[m//2]) / 2 if m % 2 == 0 else s[m//2]

    def percentil(vals, p):
        s = sorted(vals); idx = int(p * len(s))
        return s[min(idx, len(s)-1)]

    from statistics import mode as stat_mode
    try:
        moda = stat_mode(lt_vals)
    except Exception:
        moda = lt_vals[0] if lt_vals else 0

    med  = round(median(lt_sorted), 2)
    lt_m = round(sum(lt_sorted) / n, 2)
    ct_m = round(sum(ct_vals) / len(ct_vals), 2) if ct_vals else 0
    p75  = round(percentil(lt_sorted, 0.75), 2)
    p90  = round(percentil(lt_sorted, 0.90), 2)
    amp  = lt_sorted[-1] - lt_sorted[0] if lt_sorted else 0

    return [
        ("Moda: Tempo de ciclo mais frequente", moda),
        (f"Mediana (50% das entregas): concluídas neste prazo (ritmo padrão)", med),
        (f"Lead Time Médio: Tempo médio geral de ciclo", lt_m),
        (f"Cycle Time Médio: Tempo médio entre criação e fim da atividade", ct_m),
        (f"Percentil 75% (Corte de Maioria): 3/4 das demandas finalizadas neste prazo", p75),
        (f"SLE - Service Level Expectation (90%): Limite de confiança (90% de certeza neste prazo)", p90),
        (f"Amplitude de Desvio (Outlier): Diferença entre mais rápida [{lt_sorted[0]} dias] e a mais lenta [{lt_sorted[-1]} dias]", amp),
    ]


# ─────────────────────────── DISPERSÃO DIÁRIA ────────────────────────────────
def _month_bounds(ref_date):
    """Return (first_day, last_day) of the month of ref_date."""
    first = date(ref_date.year, ref_date.month, 1)
    last_day = calendar.monthrange(ref_date.year, ref_date.month)[1]
    last  = date(ref_date.year, ref_date.month, last_day)
    return first, last


def build_dispersao_daily(df, sprint_start, sprint_end):
    """
    Build daily task completion counts for Dispersao chart.
    X-axis always covers the full month of sprint_end (1st to last day).
    Returns (hu_list, days, hu_matrix, nao_hu_daily).
      hu_list      : sorted list of HU short IDs
      days         : number of days in the sprint month (28-31)
      hu_matrix    : list[hu_idx][day_offset] = simple task count that day
      nao_hu_daily : list[day_offset] = task count for tasks without HU
    """
    # Snap to full month of sprint_end
    bd_start, bd_end = _month_bounds(sprint_end)
    days = (bd_end - bd_start).days + 1  # always 28-31

    hu_list = sorted(df[df["hu"] != ""]["hu"].unique().tolist())
    hu_index = {hu: idx for idx, hu in enumerate(hu_list)}

    # Valores float: cada tarefa concluída contribui 1.0
    hu_matrix = [[0.0] * days for _ in hu_list]
    nao_hu_daily = [0.0] * days

    done_rows = df[df["done"] & df["date_done"].notna()][["hu", "date_done"]]
    for hu, d in zip(done_rows["hu"].tolist(), done_rows["date_done"].tolist()):
        offset = (d - bd_start).days
        if 0 <= offset < days:
            idx = hu_index.get(hu)
            if idx is None:
                nao_hu_daily[offset] += 1.0
            else:
                hu_matrix[idx][offset] += 1.0

    return hu_list, days, hu_matrix, nao_hu_daily


# ═══════════════════════════════════════════════════════════════════════════════
#                        TEMPLATE FILLING FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════════

def _is_valid_date(v):
    return v is not None and not (hasattr(v, "_typ") or str(v) == "NaT")


def _date_only(v):
    if not _is_valid_date(v):
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    if hasattr(v, "date"):
        try:
            return v.date()
        except Exception:
            return None
    return None


def _easter_date(year):
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return date(year, month, day)


@lru_cache(maxsize=None)
def _br_national_holidays(year):
    easter = _easter_date(year)
    return {
        date(year, 1, 1),
        easter - timedelta(days=2),
        date(year, 4, 21),
        date(year, 5, 1),
        date(year, 9, 7),
        date(year, 10, 12),
        date(year, 11, 2),
        date(year, 11, 15),
        date(year, 11, 20),
        date(year, 12, 25),
    }


def _sprint_day_metrics(sprint_start, sprint_end):
    start = _date_only(sprint_start)
    end = _date_only(sprint_end)
    if not start or not end:
        return {
            "sprint_days_calendar": 0,
            "sprint_days_business": 0,
            "sprint_weekend_days": 0,
            "sprint_holiday_days": 0,
        }
    if end < start:
        start, end = end, start

    total_days = max(0, (end - start).days)
    holiday_years = range(start.year, end.year + 1)
    holidays = set()
    for year in holiday_years:
        holidays.update(_br_national_holidays(year))

    weekend_days = 0
    holiday_days = 0
    business_days = 0
    current = start
    while current < end:
        if current.weekday() >= 5:
            weekend_days += 1
        elif current in holidays:
            holiday_days += 1
        else:
            business_days += 1
        current += timedelta(days=1)

    return {
        "sprint_days_calendar": total_days,
        "sprint_days_business": business_days,
        "sprint_weekend_days": weekend_days,
        "sprint_holiday_days": holiday_days,
    }


MIN_SPRINT_CALENDAR_DAYS = 20


def _is_business_day(day):
    return day.weekday() < 5 and day not in _br_national_holidays(day.year)


def _business_days_between(start, end_exclusive):
    if not start or not end_exclusive:
        return 0
    if end_exclusive < start:
        start, end_exclusive = end_exclusive, start
    count = 0
    current = start
    while current < end_exclusive:
        if _is_business_day(current):
            count += 1
        current += timedelta(days=1)
    return count


def _previous_business_day(day):
    current = day
    while not _is_business_day(current):
        current -= timedelta(days=1)
    return current


def _last_day_of_month(day):
    last_day = calendar.monthrange(day.year, day.month)[1]
    return date(day.year, day.month, last_day)


def _schedule_window_for_deadline(sprint_start, sprint_end, export_date):
    ref_for_deadline = _date_only(sprint_end) or _date_only(export_date) or date.today()
    official_deadline = _last_day_of_month(ref_for_deadline)
    operational_deadline = _previous_business_day(official_deadline)
    official_end_exclusive = official_deadline + timedelta(days=1)
    operational_end_exclusive = operational_deadline + timedelta(days=1)

    start = _date_only(sprint_start) or (official_end_exclusive - timedelta(days=MIN_SPRINT_CALENDAR_DAYS))
    if start > official_deadline:
        start = official_end_exclusive - timedelta(days=MIN_SPRINT_CALENDAR_DAYS)
    if (official_end_exclusive - start).days < MIN_SPRINT_CALENDAR_DAYS:
        start = official_end_exclusive - timedelta(days=MIN_SPRINT_CALENDAR_DAYS)

    return {
        "start": start,
        "official_deadline": official_deadline,
        "operational_deadline": operational_deadline,
        "official_end_exclusive": official_end_exclusive,
        "operational_end_exclusive": operational_end_exclusive,
    }


def _enrich_kpis_with_sprint_calendar(kpis, sprint_start, sprint_end, export_date=None):
    window = _schedule_window_for_deadline(sprint_start, sprint_end, export_date)
    metrics = _sprint_day_metrics(window["start"], window["official_end_exclusive"])
    kpis.update(metrics)
    kpis.update({
        "sprint_calendar_basis": "deadline_month",
        "sprint_effective_start": window["start"].isoformat(),
        "sprint_deadline_date": window["official_deadline"].isoformat(),
        "sprint_operational_deadline_date": window["operational_deadline"].isoformat(),
        "sprint_min_calendar_days": MIN_SPRINT_CALENDAR_DAYS,
    })


def _done_plan_value(row):
    d = row.get("date_due")
    if _is_valid_date(d):
        return d
    return row.get("date_done")


def _wip_phase_from_row(row):
    bucket = _lower(row.get("bucket_norm", ""))
    labels = _lower(row.get("profile_labels", row.get("labels", "")))
    tokens = [t.strip() for t in str(labels).split(";") if t.strip()]
    has_hu = bool(str(row.get("hu", "") or "").strip()) or any(t.startswith("hu") for t in tokens)
    has_gp = any(t in (".gp", "gp") for t in tokens)
    has_ux = any(t in (".ux", "ux") for t in tokens)
    has_po = any(t in (".po", "po") for t in tokens)
    has_req = any(t in (".requisitos", "requisitos") for t in tokens)

    if "gestao" in bucket or "gestão" in bucket:
        return "Gestão"
    # Item de gestão sem HU (ex.: GP/PO/servant) deve ir para Gestão.
    if has_gp and not has_hu:
        return "Gestão"
    # Itens de UX com PO/REQUISITOS são tratados como refinamento.
    if has_ux and (has_po or has_req):
        return "Em Refinamento"
    if any(t.startswith(".dev") or "dev." in t for t in tokens):
        return "Em Desenvolvimento"
    if any(
        t.startswith(".ux")
        or t.startswith(".desktop")
        or t.startswith(".mobile")
        or t.startswith(".figma")
        for t in tokens
    ):
        return "UX/UI"
    return "Em Refinamento"


def build_task_rows_for_custom_filters(df):
    rows = []
    for _, row in df.iterrows():
        base_profile = str(row.get("area", "") or "").strip()
        rows.append(
            {
                "title": str(row.get("tarefa", "") or "").strip(),
                "hu": str(row.get("hu", "") or "").strip(),
                "bucket": str(row.get("bucket_norm", "") or "").strip(),
                "labels": str(row.get("labels", "") or "").strip(),
                "profile_labels": str(row.get("profile_labels", row.get("labels", "")) or "").strip(),
                "assignee": str(row.get("assignee", "") or "").strip(),
                "is_backlog": bool(row.get("is_backlog", False)),
                "date_start": row.get("date_start").strftime("%Y-%m-%d") if _is_valid_date(row.get("date_start")) else None,
                "date_created": row.get("date_criacao").strftime("%Y-%m-%d") if _is_valid_date(row.get("date_criacao")) else None,
                "date_criacao": row.get("date_criacao").strftime("%Y-%m-%d") if _is_valid_date(row.get("date_criacao")) else None,
                "date_done": row.get("date_done").strftime("%Y-%m-%d") if _is_valid_date(row.get("date_done")) else None,
                "date_due": row.get("date_due").strftime("%Y-%m-%d") if _is_valid_date(row.get("date_due")) else None,
                "wip_done_date": _done_plan_value(row).strftime("%Y-%m-%d") if _is_valid_date(_done_plan_value(row)) else None,
                "wip_phase": _wip_phase_from_row(row),
                "profile_base": base_profile,
                "profile_base_display": AREA_DISPLAY.get(base_profile, base_profile or "Outros"),
            }
        )
    return rows


def _build_step_plan(total, days, blocks=5):
    import math

    if days <= 0:
        return []
    blocks = max(1, min(blocks, days))

    offsets = []
    for i in range(blocks):
        off = int(math.ceil((i + 1) * days / blocks) - 1)
        off = max(0, min(days - 1, off))
        if not offsets or off != offsets[-1]:
            offsets.append(off)
    if offsets[-1] != days - 1:
        offsets[-1] = days - 1

    targets = []
    for i in range(len(offsets)):
        t = round(total * (1 - (i + 1) / len(offsets)))
        targets.append(max(t, 0))
    targets[-1] = 0

    plan = []
    cur = total
    k = 0
    for i in range(days):
        while k < len(offsets) and i >= offsets[k]:
            cur = targets[k]
            k += 1
        plan.append(cur)
    return plan


def build_kpis(df):
    total = len(df)
    done = int(df["done_kpi"].sum())
    pending = total - done
    nao_prev = int(df["is_nao_prev"].sum())
    backlog_total = int(df["is_backlog"].sum())
    sem_hu = int((df["hu"].fillna("").astype(str).str.strip() == "").sum())
    fluxo_continuo = _count_rows_with_label(df, "FLUXO.CONTINUO")
    hu_count = int(df["hu"].fillna("").astype(str).str.strip().replace("", pd.NA).dropna().nunique())

    df_done = df[df["done_kpi"] & df["date_done"].notna()].copy()

    ct_task = None
    df_ct = df_done[df_done["date_start"].notna()].copy()
    if len(df_ct) > 0:
        deltas = [
            (d - s).days
            for d, s in zip(df_ct["date_done"].tolist(), df_ct["date_start"].tolist())
            if _is_valid_date(d) and _is_valid_date(s) and (d - s).days >= 0
        ]
        ct_task = round(sum(deltas) / len(deltas), 2) if deltas else None

    lt_task = None
    df_lt = df_done[df_done["date_criacao"].notna()].copy()
    if len(df_lt) > 0:
        deltas = []
        for d, c in zip(df_lt["date_done"].tolist(), df_lt["date_criacao"].tolist()):
            if _is_valid_date(d) and _is_valid_date(c):
                delta = (d - c).days
                if delta >= 0:
                    deltas.append(delta)
        lt_task = round(sum(deltas) / len(deltas), 2) if deltas else None

    ct_hu = None
    lt_hu = None
    hu_groups = [(hu, grp) for hu, grp in df[df["hu"] != ""].groupby("hu")]
    if hu_groups:
        hu_ct_means = []
        hu_lt_means = []
        for _, grp in hu_groups:
            g_done = grp[grp["done_kpi"] & grp["date_done"].notna()]

            g_ct = g_done[g_done["date_start"].notna()]
            if len(g_ct) > 0:
                deltas = [
                    (d - s).days
                    for d, s in zip(g_ct["date_done"].tolist(), g_ct["date_start"].tolist())
                    if _is_valid_date(d) and _is_valid_date(s) and (d - s).days >= 0
                ]
                if deltas:
                    hu_ct_means.append(sum(deltas) / len(deltas))

            g_lt = g_done[g_done["date_criacao"].notna()]
            if len(g_lt) > 0:
                deltas = []
                for d, c in zip(g_lt["date_done"].tolist(), g_lt["date_criacao"].tolist()):
                    if _is_valid_date(d) and _is_valid_date(c):
                        delta = (d - c).days
                        if delta >= 0:
                            deltas.append(delta)
                if deltas:
                    hu_lt_means.append(sum(deltas) / len(deltas))

        ct_hu = round(sum(hu_ct_means) / len(hu_ct_means), 2) if hu_ct_means else None
        lt_hu = round(sum(hu_lt_means) / len(hu_lt_means), 2) if hu_lt_means else None

    stakeholders = int(
        df["assignee"].fillna("").astype(str).str.strip().replace("", pd.NA).dropna().nunique()
    )
    pct_entrega = round(done / total, 4) if total else 0

    return {
        "total": int(total),
        "done": done,
        "pending": pending,
        "nao_prev": nao_prev,
        "sem_hu": sem_hu,
        "backlog_total": backlog_total,
        "ct_task": ct_task,
        "lt_task": lt_task,
        "ct_hu": ct_hu,
        "lt_hu": lt_hu,
        "ct_sp": ct_hu,
        "lt_sp": lt_hu,
        "storypoints": 0,
        "fluxo_continuo": fluxo_continuo,
        "pct_entrega": pct_entrega,
        "stakeholders": stakeholders,
        "hu_count": hu_count,
    }


def _enrich_kpis_with_hu_storypoints(kpis, df, hu_storypoints):
    total_sp = round(sum(v for v in hu_storypoints.values() if v), 2)
    kpis["storypoints"] = total_sp

    hu_ct_means = []
    hu_lt_means = []
    weighted_ct_num = 0.0
    weighted_ct_den = 0.0
    weighted_lt_num = 0.0
    weighted_lt_den = 0.0

    for hu, grp in df[df["hu"] != ""].groupby("hu"):
        g_done = grp[grp["done_kpi"]].copy()
        if g_done.empty:
            continue

        ct_vals = []
        for _, row in g_done.iterrows():
            d_done = _done_plan_value(row)
            d_start = row.get("date_start")
            if _is_valid_date(d_done) and _is_valid_date(d_start):
                delta = (d_done - d_start).days
                if delta >= 0:
                    ct_vals.append(delta)
        if ct_vals:
            ct_mean = sum(ct_vals) / len(ct_vals)
            hu_ct_means.append(ct_mean)
            sp = hu_storypoints.get(str(hu).upper(), 0) or 0
            if sp > 0:
                weighted_ct_num += ct_mean * sp
                weighted_ct_den += sp

        lt_vals = []
        for _, row in g_done.iterrows():
            d_done = _done_plan_value(row)
            d_cr = row.get("date_criacao")
            if _is_valid_date(d_done) and _is_valid_date(d_cr):
                delta = (d_done - d_cr).days
                if delta >= 0:
                    lt_vals.append(delta)
        if lt_vals:
            lt_mean = sum(lt_vals) / len(lt_vals)
            hu_lt_means.append(lt_mean)
            sp = hu_storypoints.get(str(hu).upper(), 0) or 0
            if sp > 0:
                weighted_lt_num += lt_mean * sp
                weighted_lt_den += sp

    if hu_ct_means:
        kpis["ct_hu"] = round(sum(hu_ct_means) / len(hu_ct_means), 2)
    if hu_lt_means:
        kpis["lt_hu"] = round(sum(hu_lt_means) / len(hu_lt_means), 2)
    kpis["ct_sp"] = round(weighted_ct_num / weighted_ct_den, 2) if weighted_ct_den > 0 else kpis.get("ct_hu", 0)
    kpis["lt_sp"] = round(weighted_lt_num / weighted_lt_den, 2) if weighted_lt_den > 0 else kpis.get("lt_hu", 0)


def _metric_days(sprint_start, sprint_end):
    start = _date_only(sprint_start)
    end = _date_only(sprint_end)
    if not start or not end:
        today = date.today()
        return [today], today, today + timedelta(days=1)
    if end < start:
        start, end = end, start
    days_count = max(1, (end - start).days)
    return [start + timedelta(days=i) for i in range(days_count)], start, start + timedelta(days=days_count)


def _task_storypoint_weights(df, hu_storypoints):
    if not hu_storypoints:
        return {}
    weights = {}
    df_hu = df[df["hu"].fillna("").astype(str).str.strip() != ""]
    if df_hu.empty:
        return weights
    counts = df_hu.groupby("hu").size().to_dict()
    for idx, row in df_hu.iterrows():
        hu = str(row.get("hu") or "").upper()
        sp = float(hu_storypoints.get(hu, 0) or 0)
        count = int(counts.get(row.get("hu"), 0) or 0)
        weights[idx] = sp / count if sp > 0 and count > 0 else 0.0
    return weights


def _quality_rows_by_hu(df, tagged_df):
    tagged_df_hu = tagged_df[tagged_df["hu"].fillna("").astype(str).str.strip() != ""]
    rows = []
    if not tagged_df_hu.empty:
        for hu, grp in tagged_df_hu.groupby("hu"):
            total_hu_tasks = int(len(df[df["hu"] == hu]))
            rows.append([str(hu), int(len(grp)), total_hu_tasks])

    without_hu = int(len(tagged_df) - len(tagged_df_hu))
    if without_hu:
        rows.append(["Fora de HU", without_hu, "-"])

    rows.sort(key=lambda row: (row[0] == "Fora de HU", -int(row[1] or 0), row[0]))
    return rows, tagged_df_hu


def build_flow_metrics(df, sprint_start, sprint_end, kpis):
    days, start, end_exclusive = _metric_days(sprint_start, sprint_end)

    daily_wip = []
    for day in days:
        count = 0
        for _, row in df.iterrows():
            d_start = row.get("date_start")
            d_done = row.get("date_done")
            if _is_valid_date(d_start) and d_start <= day and (not _is_valid_date(d_done) or d_done > day):
                count += 1
        daily_wip.append(count)

    throughput_rows = []
    week_counts = []
    week_start = start
    week_idx = 1
    while week_start < end_exclusive:
        week_end = min(week_start + timedelta(days=7), end_exclusive)
        count = 0
        for _, row in df[df["done_kpi"]].iterrows():
            d_done = row.get("date_done")
            if _is_valid_date(d_done) and week_start <= d_done < week_end:
                count += 1
        label = f"S{week_idx} ({week_start.strftime('%d/%m')}-{(week_end - timedelta(days=1)).strftime('%d/%m')})"
        throughput_rows.append([label, count])
        week_counts.append(count)
        week_start = week_end
        week_idx += 1

    ct_vals = []
    for _, row in df[df["done_kpi"]].iterrows():
        d_done = row.get("date_done")
        d_start = row.get("date_start")
        if _is_valid_date(d_done) and _is_valid_date(d_start):
            delta = (d_done - d_start).days
            if delta >= 0:
                ct_vals.append(delta)

    return {
        "wip_avg": _avg(daily_wip),
        "wip_days": len(daily_wip),
        "throughput_weekly_avg": _avg(week_counts),
        "throughput_total": int(sum(week_counts)),
        "throughput_weeks": len(week_counts),
        "throughput_rows": throughput_rows,
        "flow_eff_task": _flow_efficiency(kpis.get("ct_task"), kpis.get("lt_task")),
        "flow_eff_hu": _flow_efficiency(kpis.get("ct_hu"), kpis.get("lt_hu")),
        "flow_eff_sp": _flow_efficiency(kpis.get("ct_sp"), kpis.get("lt_sp")),
        "cycle_time_stddev": _stddev_population(ct_vals),
        "cycle_time_stddev_count": len(ct_vals),
    }


def build_scope_quality_metrics(df, hu_storypoints, kpis):
    committed_sp = float(kpis.get("storypoints") or (sum(hu_storypoints.values()) if hu_storypoints else 0) or 0)
    weights = _task_storypoint_weights(df, hu_storypoints)

    delivered_sp = 0.0
    if hu_storypoints:
        for hu, sp in hu_storypoints.items():
            grp = df[df["hu"].fillna("").astype(str).str.upper() == str(hu).upper()]
            if not grp.empty and bool(grp["done_kpi"].all()):
                delivered_sp += float(sp or 0)

    hu_sp_values = [float(v) for v in hu_storypoints.values() if v]
    bug_df = df[df.apply(_row_has_bug_or_adjustment, axis=1)].copy()
    bug_rows, bug_df_hu = _quality_rows_by_hu(df, bug_df)
    impediment_df = df[df.apply(_row_has_impediment, axis=1)].copy()
    impediment_rows, impediment_df_hu = _quality_rows_by_hu(df, impediment_df)
    hu_count = int(kpis.get("hu_count") or df[df["hu"] != ""]["hu"].nunique() or 0)

    creep_mask = df.apply(_row_is_scope_creep, axis=1)
    creep_df = df[creep_mask]
    creep_sp = round(sum(weights.get(idx, 0.0) for idx in creep_df.index), 2) if weights else 0.0

    return {
        "committed_sp": round(committed_sp, 2),
        "delivered_sp": round(delivered_sp, 2),
        "say_do_ratio": _pct(delivered_sp, committed_sp),
        "avg_hu_size_sp": _avg(hu_sp_values),
        "bug_task_count": int(len(bug_df)),
        "bug_task_with_hu_count": int(len(bug_df_hu)),
        "bug_hu_count": int(bug_df_hu["hu"].nunique()) if not bug_df_hu.empty else 0,
        "bug_density_avg": round(len(bug_df_hu) / hu_count, 2) if hu_count else None,
        "bug_rows": bug_rows[:8],
        "impediment_task_count": int(len(impediment_df)),
        "impediment_task_with_hu_count": int(len(impediment_df_hu)),
        "impediment_hu_count": int(impediment_df_hu["hu"].nunique()) if not impediment_df_hu.empty else 0,
        "impediment_rows": impediment_rows[:8],
        "scope_creep_tasks": int(len(creep_df)),
        "scope_creep_sp": creep_sp,
        "scope_creep_task_pct": _pct(len(creep_df), len(df)),
        "scope_creep_sp_pct": _pct(creep_sp, committed_sp),
    }


def build_time_metrics(df, sprint_start, sprint_end, export_date, hu_storypoints, scope_metrics):
    window = _schedule_window_for_deadline(sprint_start, sprint_end, export_date)
    start = window["start"]
    official_deadline = window["official_deadline"]
    operational_deadline = window["operational_deadline"]
    official_end_exclusive = window["official_end_exclusive"]
    operational_end_exclusive = window["operational_end_exclusive"]

    total_days = _business_days_between(start, operational_end_exclusive)
    calendar_total_days = max(1, (official_end_exclusive - start).days)
    ref = _date_only(export_date) or date.today()

    if ref < start:
        remaining_days = total_days
        calendar_remaining_days = calendar_total_days
    elif ref > operational_deadline:
        remaining_days = 0
        calendar_remaining_days = 0 if ref > official_deadline else max(0, (official_deadline - ref).days + 1)
    else:
        remaining_days = _business_days_between(ref, operational_end_exclusive)
        calendar_remaining_days = max(0, (official_deadline - ref).days + 1)
    elapsed = max(total_days - remaining_days, 0)
    calendar_elapsed = max(calendar_total_days - calendar_remaining_days, 0)

    weights = _task_storypoint_weights(df, hu_storypoints)
    if weights:
        total_work = float(scope_metrics.get("committed_sp") or sum(hu_storypoints.values()) or 0)
        done_work = sum(weights.get(idx, 0.0) for idx, row in df.iterrows() if bool(row.get("done_kpi", False)))
        unit = "SP"
    else:
        total_work = float(len(df))
        done_work = float(int(df["done_kpi"].sum())) if "done_kpi" in df.columns else 0.0
        unit = "tarefas"

    remaining_work = max(total_work - done_work, 0.0)
    days_remaining_pct = _pct(remaining_days, total_days) or 0
    work_remaining_pct = _pct(remaining_work, total_work) or 0
    delta = round(work_remaining_pct - days_remaining_pct, 2)
    status = "saudavel"
    if delta > 20:
        status = "alerta"
    elif delta > 10:
        status = "atencao"

    first_response_vals = []
    for _, row in df.iterrows():
        d_created = row.get("date_criacao")
        d_start = row.get("date_start")
        if _is_valid_date(d_created) and _is_valid_date(d_start):
            delta_days = (d_start - d_created).days
            if delta_days >= 0:
                first_response_vals.append(delta_days)

    return {
        "days_elapsed": int(elapsed),
        "days_remaining": int(remaining_days),
        "days_total": int(total_days),
        "days_remaining_pct": round(days_remaining_pct, 2),
        "calendar_days_elapsed": int(calendar_elapsed),
        "calendar_days_remaining": int(calendar_remaining_days),
        "calendar_days_total": int(calendar_total_days),
        "calendar_days_remaining_pct": round(_pct(calendar_remaining_days, calendar_total_days) or 0, 2),
        "deadline_date": official_deadline.isoformat(),
        "operational_deadline_date": operational_deadline.isoformat(),
        "deadline_shifted": official_deadline != operational_deadline,
        "sprint_effective_start": start.isoformat(),
        "min_calendar_days": MIN_SPRINT_CALENDAR_DAYS,
        "schedule_basis": "business_days",
        "work_remaining": round(remaining_work, 2),
        "work_total": round(total_work, 2),
        "work_unit": unit,
        "work_remaining_pct": round(work_remaining_pct, 2),
        "schedule_delta_pct": delta,
        "schedule_status": status,
        "first_response_avg": _avg(first_response_vals),
        "first_response_count": len(first_response_vals),
    }


def build_areas(df):
    """
    Areas para o gráfico de proporção:
    - considera rótulos com estrutura de área (contendo ponto), exclui HU* e FLUXO.CONTINUO
    - normaliza para prefixo com "." no output (ex.: SERVANT.LEADER -> .SERVANT.LEADER)
    """
    from collections import defaultdict

    counts = defaultdict(lambda: {"done": 0, "total": 0})
    done_series = (
        df["done_kpi"] if "done_kpi" in df.columns
        else df["done"] if "done" in df.columns
        else pd.Series([False] * len(df))
    )

    profile_label_col = "profile_labels" if "profile_labels" in df.columns else "labels"
    for label_text, is_done in zip(df[profile_label_col].fillna("").astype(str).tolist(), done_series.tolist()):
        done_flag = bool(is_done)
        for raw in [p.strip() for p in str(label_text).split(";") if p.strip()]:
            key = _norm_label_key(raw)
            if not key:
                continue
            if key.startswith("hu"):
                continue
            if key == "fluxo.continuo":
                continue
            if "." not in key:
                continue

            display = raw.strip()
            if not display.startswith("."):
                display = f".{display}"
            area_key = display.upper()
            counts[area_key]["total"] += 1
            if done_flag:
                counts[area_key]["done"] += 1

    rows = []
    for area, vals in counts.items():
        total = int(vals["total"])
        done = int(vals["done"])
        pending = max(0, total - done)
        if total > 0:
            rows.append((area, done, pending))
    rows.sort(key=lambda x: -(x[1] + x[2]))
    return rows


def build_rotulos(df):
    from collections import defaultdict

    label_done = defaultdict(int)
    label_total = defaultdict(int)
    label_lt = defaultdict(list)
    label_ct = defaultdict(list)
    label_display = {}

    for _, row in df.iterrows():
        lbls = [l.strip() for l in str(row.get("labels", "")).split(";") if l.strip()]
        for lbl in lbls:
            key = _norm_label_key(lbl)
            if not key:
                continue
            if key not in label_display:
                label_display[key] = lbl.strip()
            label_total[key] += 1
            if row.get("done_kpi"):
                label_done[key] += 1
                d_done = row.get("date_done")
                d_start = row.get("date_start")
                d_criac = row.get("date_criacao")
                if _is_valid_date(d_done) and _is_valid_date(d_criac):
                    lt = (d_done - d_criac).days
                    if lt >= 0:
                        label_lt[key].append(lt)
                if _is_valid_date(d_done) and _is_valid_date(d_start):
                    ct = (d_done - d_start).days
                    if ct >= 0:
                        label_ct[key].append(ct)

    rows = []
    for key in label_total:
        done = label_done[key]
        total = label_total[key]
        pend = total - done
        lt = round(sum(label_lt[key]) / len(label_lt[key]), 2) if label_lt[key] else 0
        ct = round(sum(label_ct[key]) / len(label_ct[key]), 2) if label_ct[key] else 0
        display = f"{label_display[key]} ({done}/{total})"
        rows.append((display, done, pend, lt, ct))
    rows.sort(key=lambda x: -(x[1] + x[2]))
    return rows


def build_responsaveis(df):
    rows = []
    for person, grp in df.groupby("assignee"):
        name = _strip(person) or "Sem atribuição"
        done_bucket = int(grp["done_kpi"].sum())
        pend = len(grp) - done_bucket
        total = len(grp)

        grp_done = grp[grp["done_kpi"] & grp["date_done"].notna()]
        lt_vals = []
        ct_vals = []
        for _, row in grp_done.iterrows():
            d_done = row.get("date_done")
            d_start = row.get("date_start")
            d_criac = row.get("date_criacao")
            if _is_valid_date(d_done) and _is_valid_date(d_criac):
                lt = (d_done - d_criac).days
                if lt >= 0:
                    lt_vals.append(lt)
            if _is_valid_date(d_done) and _is_valid_date(d_start):
                ct = (d_done - d_start).days
                if ct >= 0:
                    ct_vals.append(ct)

        lt = round(sum(lt_vals) / len(lt_vals), 2) if lt_vals else 0
        ct = round(sum(ct_vals) / len(ct_vals), 2) if ct_vals else 0
        display = f"{name} ({done_bucket}/{total})"
        rows.append((display, done_bucket, pend, lt, ct))

    rows.sort(key=lambda x: -(x[1] + x[2]))
    return rows


def build_cfd(df, sprint_start, export_date, sprint_end=None):
    bd_start, bd_end, days = _resolve_burndown_window(df, sprint_start, sprint_end)
    cutoff = export_date if _is_valid_date(export_date) else bd_end
    if cutoff < bd_start:
        cutoff = bd_start
    if cutoff > bd_end:
        cutoff = bd_end

    todo_list, doing_list, done_list = [], [], []
    last_todo = last_doing = last_done = 0

    for i in range(days):
        d = bd_start + timedelta(days=i)
        if d <= cutoff:
            todo = 0
            doing = 0
            done = 0
            for _, row in df.iterrows():
                d_start = row.get("date_start")
                d_done = _done_plan_value(row)
                if _is_valid_date(d_done) and d_done <= d:
                    done += 1
                elif _is_valid_date(d_start) and d_start <= d:
                    doing += 1
                else:
                    todo += 1
            last_todo, last_doing, last_done = todo, doing, done
        else:
            todo, doing, done = last_todo, last_doing, last_done
        todo_list.append(todo)
        doing_list.append(doing)
        done_list.append(done)

    dates = [
        datetime(
            (bd_start + timedelta(days=i)).year,
            (bd_start + timedelta(days=i)).month,
            (bd_start + timedelta(days=i)).day,
        )
        for i in range(days)
    ]
    return dates, todo_list, doing_list, done_list


def build_wip(df, sprint_start, export_date, sprint_end=None):
    bd_start, bd_end, days = _resolve_burndown_window(df, sprint_start, sprint_end)
    cutoff = export_date if _is_valid_date(export_date) else bd_end
    if cutoff < bd_start:
        cutoff = bd_start
    if cutoff > bd_end:
        cutoff = bd_end

    bucket_names = ["Concluído", "Em Desenvolvimento", "Em Refinamento", "Gestão", "UX/UI"]
    bucket_matrix = {b: [0] * days for b in bucket_names}
    last_state = {b: 0 for b in bucket_names}

    for i in range(days):
        d = bd_start + timedelta(days=i)
        if d <= cutoff:
            done_count = 0
            active_counts = {
                "Em Desenvolvimento": 0,
                "Em Refinamento": 0,
                "Gestão": 0,
                "UX/UI": 0,
            }
            for _, row in df.iterrows():
                d_start = row.get("date_start")
                d_done = _done_plan_value(row)
                if _is_valid_date(d_done) and d_done <= d:
                    done_count += 1
                    continue
                if _is_valid_date(d_start):
                    end = d_done if _is_valid_date(d_done) else cutoff
                    if d_start <= d < end:
                        phase = _wip_phase_from_row(row)
                        if phase in active_counts:
                            active_counts[phase] += 1

            bucket_matrix["Concluído"][i] = done_count
            bucket_matrix["Em Desenvolvimento"][i] = active_counts["Em Desenvolvimento"]
            bucket_matrix["Em Refinamento"][i] = active_counts["Em Refinamento"]
            bucket_matrix["Gestão"][i] = active_counts["Gestão"]
            bucket_matrix["UX/UI"][i] = active_counts["UX/UI"]
            for b in bucket_names:
                last_state[b] = bucket_matrix[b][i]
        else:
            for b in bucket_names:
                bucket_matrix[b][i] = last_state[b]

    dates = [
        datetime(
            (bd_start + timedelta(days=i)).year,
            (bd_start + timedelta(days=i)).month,
            (bd_start + timedelta(days=i)).day,
        )
        for i in range(days)
    ]
    return dates, bucket_names, bucket_matrix, None


def build_cts(df, sprint_start, sprint_end=None):
    bd_start, bd_end, days = _resolve_burndown_window(df, sprint_start, sprint_end)

    def _all_hus(labels_text):
        out = []
        seen = set()
        for token in [p.strip() for p in str(labels_text).split(";") if p.strip()]:
            m = re.search(r"\b(HU\s*0*\d+)\b", token, flags=re.IGNORECASE)
            if not m:
                continue
            num = re.sub(r"\D", "", m.group(1))
            hu = f"HU{num.zfill(3)}"
            if hu not in seen:
                seen.add(hu)
                out.append(hu)
        return out

    hu_set = set()
    hu_full = {}
    for _, row in df.iterrows():
        labels_text = str(row.get("labels", ""))
        full = _extract_hu_full_label(labels_text)
        for hu in _all_hus(labels_text):
            hu_set.add(hu)
            if hu not in hu_full:
                hu_full[hu] = full or hu
    hu_list = sorted(hu_set)

    hu_index = {h: i for i, h in enumerate(hu_list)}
    cts_matrix = [[0] * days for _ in hu_list]
    fora_hu_daily = [0] * days

    done_rows = df.copy()
    for _, row in done_rows.iterrows():
        d = _done_plan_value(row)
        if not _is_valid_date(d):
            continue
        offset = (d - bd_start).days
        if 0 <= offset < days:
            hu_keys = _all_hus(row.get("labels", ""))
            if not hu_keys:
                fora_hu_daily[offset] += 1
            else:
                for hu in hu_keys:
                    idx = hu_index.get(hu)
                    if idx is not None:
                        cts_matrix[idx][offset] += 1

    dates = [
        datetime(
            (bd_start + timedelta(days=i)).year,
            (bd_start + timedelta(days=i)).month,
            (bd_start + timedelta(days=i)).day,
        )
        for i in range(days)
    ]
    return dates, [hu_full.get(h, h) for h in hu_list], cts_matrix, fora_hu_daily


def build_dispersao_daily(df, sprint_start, sprint_end):
    bd_start, bd_end, days_count = _resolve_burndown_window(df, sprint_start, sprint_end)

    def _all_hus(labels_text):
        out = []
        seen = set()
        for token in [p.strip() for p in str(labels_text).split(";") if p.strip()]:
            m = re.search(r"\b(HU\s*0*\d+)\b", token, flags=re.IGNORECASE)
            if not m:
                continue
            num = re.sub(r"\D", "", m.group(1))
            hu = f"HU{num.zfill(3)}"
            if hu not in seen:
                seen.add(hu)
                out.append(hu)
        return out

    hu_set = set()
    for labels_text in df["labels"].fillna("").astype(str).tolist():
        for hu in _all_hus(labels_text):
            hu_set.add(hu)
    hu_list = sorted(hu_set)
    hu_index = {hu: idx for idx, hu in enumerate(hu_list)}

    hu_matrix = [[0.0] * days_count for _ in hu_list]
    nao_hu_daily = [0.0] * days_count

    done_rows = df.copy()
    for _, row in done_rows.iterrows():
        d = _done_plan_value(row)
        if not _is_valid_date(d):
            continue
        offset = (d - bd_start).days
        if 0 <= offset < days_count:
            hu_keys = _all_hus(row.get("labels", ""))
            if not hu_keys:
                nao_hu_daily[offset] += 1.0
            else:
                for hu in hu_keys:
                    idx = hu_index.get(hu)
                    if idx is not None:
                        hu_matrix[idx][offset] += 1.0

    day_values = [
        datetime(
            (bd_start + timedelta(days=i)).year,
            (bd_start + timedelta(days=i)).month,
            (bd_start + timedelta(days=i)).day,
        )
        for i in range(days_count)
    ]
    return hu_list, day_values, hu_matrix, nao_hu_daily


def _w(ws, row, col, value):
    """Write a value to a specific cell."""
    ws.cell(row=row, column=col).value = value


def _fill_kpi_sheet(wb, kpis, sprint_name, sprint_goal,
                    projeto="", gerente="", linkedin="", export_date=None,
                    nome_arquivo="", product_goal="",
                    write_cabecalhos=True):
    """
    Preenche os KPIs no template.

    Novo template (xKPI + gp_Cabecalhos):
      xKPI: métricas numéricas (15 linhas)
      gp_Cabecalhos: metadados do projeto (PROJETO, GERENTE, etc.)

    Template legado (Cabecalhos e KPI):
      Estrutura combinada com metadados + KPIs em 13 linhas.
    """
    if export_date and hasattr(export_date, "strftime"):
        export_date_display = export_date.strftime("%d/%m/%Y")
    else:
        export_date_display = str(export_date) if export_date else ""
    pct = round(kpis["done"] / kpis["total"], 4) if kpis["total"] else 0

    if "xKPI" in wb.sheetnames:
        # ── Novo template: xKPI contém apenas métricas ──
        ws = wb["xKPI"]
        xkpi_rows = [
            ("STORYPOINTS",                kpis.get("storypoints", 0)),
            ("TAREFAS",                    kpis["total"]),
            ("TAREFAS CONCLUÍDAS",         kpis["done"]),
            ("PENDENTES",                  kpis["pending"]),
            ("EM BACKLOG",                 kpis.get("backlog_total", 0)),
            ("AUSENTES EM HU",             kpis["sem_hu"]),
            ("NÃO PREVISTAS",              kpis["nao_prev"]),
            ("CYCLE TIME TASK",            round(kpis.get("ct_task") or 0, 2)),
            ("LEAD TIME TASK",             round(kpis.get("lt_task") or 0, 2)),
            ("CYCLE TIME HU",              round(kpis.get("ct_hu") or 0, 2)),
            ("LEAD TIME HU",               round(kpis.get("lt_hu") or 0, 2)),
            ("CYCLE TIME SP.",             round(kpis.get("ct_sp") or 0, 2)),
            ("LEAD TIME SP.",              round(kpis.get("lt_sp") or 0, 2)),
            ("QTD HUS",                    kpis.get("hu_count", 0)),
            ("RESPONSAVEIS NOMEADOS",      kpis.get("stakeholders", 0)),
            ("DIAS CORRIDOS SPRINT",       kpis.get("sprint_days_calendar", 0)),
            ("DIAS UTEIS SPRINT",          kpis.get("sprint_days_business", 0)),
            ("Fluxo Contínuo",             kpis.get("fluxo_continuo", 0)),
            ("% de Entrega:",              pct),
            ("Stakeholders com tarefas",   kpis.get("stakeholders", 0)),
        ]
        for i, (lbl, val) in enumerate(xkpi_rows, start=1):
            _w(ws, i, 1, lbl)
            _w(ws, i, 2, val)

        # ── gp_Cabecalhos: metadados do projeto (só preenche se write_cabecalhos=True) ──
        if write_cabecalhos and "gp_Cabecalhos" in wb.sheetnames:
            wsc = wb["gp_Cabecalhos"]
            cab_rows = [
                ("PROJETO",                                projeto or sprint_name),
                ("NOME DO GERENTE DO PROJETO",             gerente),
                ("link para LINKEDIN DO GERENTE DO PROJETO", linkedin),
                ("PRODUCT GOAL (OBJETIVO DO PROJETO)",     product_goal or sprint_goal or ""),
                ("SPRINT GOAL (OBJETIVO DA SPRINT)",       sprint_goal or ""),
                ("LINK ARQUIVO BASE / PLANO",              nome_arquivo),
                ("DATA DA EXTRACAO DOS DADOS",             export_date_display),
            ]
            for i, (lbl, val) in enumerate(cab_rows, start=1):
                _w(wsc, i, 1, lbl)
                _w(wsc, i, 2, val)

    else:
        # ── Template legado (Cabecalhos e KPI) ──
        ws = wb["Cabecalhos e KPI"] if "Cabecalhos e KPI" in wb.sheetnames else None
        if ws is None:
            return
        labels_col_a = [
            "PROJETO",
            "NOME DO GERENTE DO PROJETO",
            "link para LINKEDIN DO GERENTE DO PROJETO",
            "DATA DA EXTRACAO DOS DADOS",
            "NOME DO ARQUIVO BASE / PLANO",
            "SPRINT GOAL (OBJETIVO)",
            "TAREFAS TOTAL",
            "TAREFAS CONCLUÍDAS",
            "PENDENTES",
            "NÃO PREVISTAS",
            "% ENTREGA",
            "EM BACKLOG",
            "AUSENTES EM HU",
        ]
        for i, lbl in enumerate(labels_col_a, start=1):
            _w(ws, i, 1, lbl)
        values_col_b = [
            projeto or sprint_name,
            gerente,
            linkedin,
            export_date_display,
            nome_arquivo,
            sprint_goal or "",
            kpis["total"],
            kpis["done"],
            kpis["pending"],
            kpis["nao_prev"],
            pct,
            kpis.get("backlog_total", 0),
            kpis["sem_hu"],
        ]
        for i, val in enumerate(values_col_b, start=1):
            _w(ws, i, 2, val)


def _fill_hu_sheet(wb, hu_list, hu_full_names, extras_count=0):
    """
    HUs sheet:  A = full HU label,  B = total task count
    Template has 5 data rows (rows 2-6) + row 7 = EXTRAS (AUSENTE EM HU).
    O gráfico TAREFAS POR HU referencia HUs!B2:B7 (6 linhas).
    """
    sheet_name = "xHUs" if "xHUs" in wb.sheetnames else "HUs"
    ws = wb[sheet_name]
    TEMPLATE_ROWS = 5
    top = sorted(hu_list, key=lambda x: -x[1])[:TEMPLATE_ROWS]

    for i in range(TEMPLATE_ROWS):
        r = i + 2
        if i < len(top):
            hu_id, total, done = top[i]
            full_name = hu_full_names.get(hu_id, hu_id)
            _w(ws, r, 1, full_name)
            _w(ws, r, 2, total)
        else:
            _w(ws, r, 1, None)
            _w(ws, r, 2, None)

    # Linha 7: EXTRAS (tarefas sem HU) – referenciado pelo gráfico TAREFAS POR HU
    _w(ws, 7, 1, "EXTRAS (AUSENTE EM HU)")
    _w(ws, 7, 2, extras_count)


def _fill_burndown_sheet(wb, df, sprint_start, sprint_end, export_date):
    """
    BurndownTarefas:  A = datetime,  B = Meta,  C = Planejado,  D = A Realizar
    Template has 31 data rows (rows 2-32).
    X-axis always covers the full month of sprint_end (1st to last day).
    """
    sheet_name = "xBurndownTarefas" if "xBurndownTarefas" in wb.sheetnames else "BurndownTarefas"
    ws = wb[sheet_name]
    ROWS = 31
    dfw = df[~df["is_backlog"]].copy()
    total = len(dfw)

    # Snap to full month of sprint_end
    bd_start, bd_end = _month_bounds(sprint_end)
    days = (bd_end - bd_start).days + 1  # 28-31

    # Planejado: remove tasks only when due date is within month and <= current day.
    due_offsets = [
        (d - bd_start).days
        for d in dfw["date_due"].tolist()
        if d is not None and not (hasattr(d, '_typ') or str(d) == 'NaT')
        and bd_start <= d <= bd_end
    ]
    due_hist = [0] * days
    for off in due_offsets:
        due_hist[off] += 1
    due_prefix = []
    running = 0
    for count in due_hist:
        running += count
        due_prefix.append(running)

    # A Realizar: total - tasks done up to day (includes tasks done before sprint month).
    done_dates = sorted(
        d for d in dfw.loc[dfw["done"] & dfw["date_done"].notna(), "date_done"].tolist()
    )

    for i in range(ROWS):
        r = i + 2
        if i < days:
            d = bd_start + timedelta(days=i)
            dt = datetime(d.year, d.month, d.day)
            meta = round(total * (1 - i / max(days - 1, 1)))
            plan = total - due_prefix[i]

            concluded_until_day = bisect_right(done_dates, d)
            rlz = total - concluded_until_day

            _w(ws, r, 1, dt)
            _w(ws, r, 2, meta)
            _w(ws, r, 3, plan)
            _w(ws, r, 4, rlz)
        else:
            _w(ws, r, 1, None)
            _w(ws, r, 2, None)
            _w(ws, r, 3, None)
            _w(ws, r, 4, None)


def _fill_burndown_hu_sheet(wb, df, sprint_start, sprint_end, export_date):
    """
    BurndownHU:  A = datetime,  B = Meta,  C = Planejado,  D = A Realizar
    Template has 31 data rows (rows 2-32).
    X-axis always covers the full month of sprint_end (1st to last day).

    Meta   : decresce de forma LINEAR a partir da soma total de tarefas nas HUs.
    Planejado: degraus proporcionais ao tamanho de cada HU.
    A Realizar: soma das tarefas totais das HUs que ainda NÃO estão 100% concluídas.
                (se HU054 tem 36 tarefas e 1 resta, conta 36)
    """
    sheet_name = "xBurndownHU" if "xBurndownHU" in wb.sheetnames else "BurndownHU"
    ws = wb[sheet_name]
    ROWS = 31
    dfw = df[df["hu"] != ""].copy()

    # Snap to full month of sprint_end
    bd_start, bd_end = _month_bounds(sprint_end)
    days = (bd_end - bd_start).days + 1  # 28-31

    hu_groups = list(dfw.groupby("hu"))

    # Info por HU: (task_count, completion_date_or_None)
    hu_info = []
    for hu_id, grp in hu_groups:
        hu_total = len(grp)
        done_mask = grp["done"].astype(bool)
        if bool(done_mask.all()):
            done_dates = [
                d for d in grp.loc[done_mask & grp["date_done"].notna(), "date_done"].tolist()
                if d is not None
            ]
            completion_date = max(done_dates) if done_dates else (
                export_date if bd_start <= export_date <= bd_end else bd_end
            )
        else:
            completion_date = None  # não concluída na sprint
        hu_info.append((hu_total, completion_date))

    # Meta inicial = soma de tarefas de todas as HUs
    total_hu_tasks = sum(t for t, _ in hu_info)

    # Planejado: quedas proporcionais ao tamanho de cada HU, em degraus 7/5 dias
    # Ordenar HUs por data de conclusão (concluídas primeiro, pendentes por último)
    hu_info_sorted = sorted(
        hu_info,
        key=lambda x: (x[1] is None, x[1] or date.max)
    )
    drop_offsets = []
    if hu_info_sorted:
        anchor = export_date
        if anchor < bd_start:
            anchor = bd_start
        if anchor > bd_end:
            anchor = bd_end
        first_off = (anchor - bd_start).days
        drop_offsets = [first_off]
        next_off = first_off + 7
        for _ in range(len(hu_info_sorted) - 2):
            if next_off < days - 1:
                drop_offsets.append(next_off)
                next_off += 5
        drop_offsets.append(days - 1)
        # Preenche se necessário
        used = set(drop_offsets)
        cand = days - 2
        while len(drop_offsets) < len(hu_info_sorted) and cand >= 0:
            if cand not in used:
                drop_offsets.insert(-1, cand)
                used.add(cand)
            cand -= 1
        drop_offsets = sorted(drop_offsets[:len(hu_info_sorted)])

    # Planejado: soma acumulada das quedas de cada HU no offset correspondente
    # Cria lista de (offset, task_count) para cada "queda" planejada
    plan_drops = []  # (day_offset, task_count_to_drop)
    for idx, (drop_off) in enumerate(drop_offsets):
        if idx < len(hu_info_sorted):
            task_cnt, _ = hu_info_sorted[idx]
            plan_drops.append((drop_off, task_cnt))

    # Monta array de Planejado por dia
    plan_remaining = total_hu_tasks
    plan_by_day = []
    drops_by_day = defaultdict(int)
    for off, cnt in plan_drops:
        drops_by_day[off] += cnt
    running_plan = total_hu_tasks
    for i in range(days):
        running_plan = max(running_plan - drops_by_day.get(i, 0), 0)
        plan_by_day.append(running_plan)
    # Garantir que último dia = 0
    if plan_by_day:
        plan_by_day[-1] = 0

    for i in range(ROWS):
        r = i + 2
        if i < days:
            d = bd_start + timedelta(days=i)
            dt = datetime(d.year, d.month, d.day)
            meta = round(total_hu_tasks * (1 - i / max(days - 1, 1)))

            plan = plan_by_day[i]

            # A Realizar: soma de tarefas de HUs NÃO 100% concluídas até o dia d
            a_realiz = 0
            for hu_total, comp_date in hu_info:
                if comp_date is None or comp_date > d:
                    a_realiz += hu_total
            # Primeiro dia = Meta inicial (conforme especificação)
            if i == 0:
                a_realiz = total_hu_tasks

            _w(ws, r, 1, dt)
            _w(ws, r, 2, meta)
            _w(ws, r, 3, plan)
            _w(ws, r, 4, a_realiz)
        else:
            _w(ws, r, 1, None)
            _w(ws, r, 2, None)
            _w(ws, r, 3, None)
            _w(ws, r, 4, None)


def _fill_dispersao_sheet(wb, hu_list, days, hu_matrix, nao_hu_daily,
                           bd_start, hu_full_names):
    """
    Dispersao — interleaved per-series X/Y layout:

      Row  1: X values for series 0  (day + offset_0, col B:AF)
      Row  2: name (col A) + Y values for series 0  (band 1 or None)
      Row  3: X values for series 1  (day + offset_1)
      Row  4: name + Y values for series 1  (band 2 or None)
      Row  5: X values for series 2
      Row  6: name + Y values for series 2
      Row  7: X values for series 3
      Row  8: name + Y values for series 3
      Row  9: X values for series 4
      Row 10: name + Y values for series 4
      Row 11: X values for series 5 (Nao em HU)
      Row 12: name + Y values for series 5  (band 6 or None)

    Per-series horizontal jitter offsets spread points around the integer day
    so same-day events from different HUs are not stacked vertically.
    Offsets: -0.30, -0.18, -0.06, +0.06, +0.18, +0.30

    Y values use row-band positioning: series i → Y = i+1 when tasks were
    completed that day, else None (dot hidden).

    Template has 31 date columns (B:AF) and 12 data rows (rows 1-12).
    bd_start: first day of the sprint month.
    """
    sheet_name = "xDispersaoTarefas" if "xDispersaoTarefas" in wb.sheetnames else "Dispersao"
    ws        = wb[sheet_name]
    DATE_COLS = 31   # columns B:AF
    HU_ROWS   = 5    # series 0-4 (top 5 HUs)

    # Per-series X jitter offsets — spread +-0.30 around integer day
    OFFSETS = [-0.30, -0.18, -0.06, +0.06, +0.18, +0.30]

    # Clear any old data in rows 1-12
    for r in range(1, 13):
        for c in range(1, DATE_COLS + 2):
            ws.cell(r, c).value = None

    def _write_series_rows(x_row, y_row, band_y, day_values, name):
        """Write X row (jittered day) and Y row (band or None) for one series."""
        offset = OFFSETS[band_y - 1]
        ws.cell(x_row, 1).value = None          # col A of X row blank
        ws.cell(y_row, 1).value = name           # series name in col A of Y row
        for j in range(DATE_COLS):
            col = j + 2
            if j < days:
                day_num  = (bd_start + timedelta(days=j)).day
                x_val    = round(day_num + offset, 4)
                has_data = day_values[j] > 1e-9
            else:
                x_val    = None
                has_data = False

            ws.cell(x_row, col).value = x_val
            ws.cell(x_row, col).number_format = "0.00"

            ws.cell(y_row, col).value = band_y if has_data else None
            ws.cell(y_row, col).number_format = "0"

    # Series 0-4: individual HU rows
    top_hu = hu_list[:HU_ROWS]
    for i in range(HU_ROWS):
        x_row  = 2 * i + 1   # 1, 3, 5, 7, 9
        y_row  = 2 * i + 2   # 2, 4, 6, 8, 10
        band_y = i + 1        # 1, 2, 3, 4, 5
        if i < len(top_hu):
            hu_id     = top_hu[i]
            full_name = hu_full_names.get(hu_id, hu_id)
            day_vals  = hu_matrix[i]
        else:
            full_name = None
            day_vals  = [0.0] * days
        _write_series_rows(x_row, y_row, band_y, day_vals, full_name)

    # Series 5: Nao em HU -> rows 11 (X) and 12 (Y), band 6
    _write_series_rows(11, 12, 6, nao_hu_daily, "Nao Presente em HU")


def _fill_colaborador_sheet(wb, collab_rows):
    """
    PorColaborador:
      A = 'Nome (done/total)',  B = done count,  C = pending count
    Template has 11 data rows (rows 2-12).
    """
    sheet_name = "xResponsaveis" if "xResponsaveis" in wb.sheetnames else "PorColaborador"
    ws   = wb[sheet_name]
    ROWS = 11
    top  = collab_rows[:ROWS]

    for i in range(ROWS):
        r = i + 2
        if i < len(top):
            name, done, pend = top[i]
            total = done + pend
            label = f"{name} ({done}/{total})"
            _w(ws, r, 1, label)
            _w(ws, r, 2, done)
            _w(ws, r, 3, pend)
        else:
            _w(ws, r, 1, None)
            _w(ws, r, 2, None)
            _w(ws, r, 3, None)


def _fill_areas_sheet(wb, area_rows):
    """
    xAreas (novo template): linhas dinâmicas, A = área (label com "."), B = total.
    Areas (template antigo): 12 linhas fixas com TEMPLATE_AREAS.
    """
    if "xAreas" in wb.sheetnames:
        ws = wb["xAreas"]
        # New template: dynamic rows from build_areas (labels starting with ".")
        # Clear existing data rows
        for r in range(2, ws.max_row + 2):
            _w(ws, r, 1, None)
            _w(ws, r, 2, None)
        for i, (area, done, pend) in enumerate(area_rows):
            _w(ws, i + 2, 1, area)
            _w(ws, i + 2, 2, done + pend)
    elif "Areas" in wb.sheetnames:
        ws = wb["Areas"]
        area_totals = {}
        for area, done, pend in area_rows:
            display = AREA_DISPLAY.get(area, area)
            area_totals[display] = done + pend
        for i, area_name in enumerate(TEMPLATE_AREAS):
            r = i + 2
            _w(ws, r, 1, area_name)
            _w(ws, r, 2, area_totals.get(area_name, 0))


def _fill_hu_in_out_sheet(wb, in_out_rows):
    """
    HU_inOut: 2 rows, A = group name, B = total count
    """
    sheet_name = "xHU_inOut" if "xHU_inOut" in wb.sheetnames else "HU_inOut"
    ws = wb[sheet_name]
    for i, (label, total) in enumerate(in_out_rows):
        r = i + 2
        _w(ws, r, 1, label)
        _w(ws, r, 2, total)


def _fill_categoria_sheet(wb, cat_rows):
    """
    PorCategoria:
      A = 'LABEL (done/total)',  B = done,  C = pending
    Template has 16 data rows (rows 2-17).
    """
    sheet_name = "xRotulos" if "xRotulos" in wb.sheetnames else "PorCategoria"
    ws   = wb[sheet_name]
    ROWS = 16
    top  = cat_rows[:ROWS]

    for i in range(ROWS):
        r = i + 2
        if i < len(top):
            cat, done, pend = top[i]
            total = done + pend
            label = f"{cat} ({done}/{total})"
            _w(ws, r, 1, label)
            _w(ws, r, 2, done)
            _w(ws, r, 3, pend)
        else:
            _w(ws, r, 1, None)
            _w(ws, r, 2, None)
            _w(ws, r, 3, None)


def _fill_categoria_bubbles_sheet(wb, bub_rows, template_effort=None):
    """
    PorCategoriaBubbles:
      A = 'LABEL (done/total)',  B = done,  C = total,  D = esforço
    Template has 17 data rows (rows 2-18).
    A última linha (row 18) é reservada para "BUGs e Ajustes" (sempre pinado ao final).

    Se template_effort for fornecido (dict {label_norm: effort}), usa os
    valores de esforço planejado do template em vez do esforço de checklist.
    """
    sheet_name = "PorCategoriaBubbles" if "PorCategoriaBubbles" in wb.sheetnames else None
    if sheet_name is None:
        return  # Sheet not in new template — skip silently
    ws   = wb[sheet_name]
    ROWS = 17
    top  = bub_rows[:ROWS]

    for i in range(ROWS):
        r = i + 2
        if i < len(top):
            cat, done, total, effort_checklist = top[i]
            # Usa esforço do template (planejamento) quando disponível
            if template_effort:
                effort = template_effort.get(_norm_label_key(cat), effort_checklist)
            else:
                effort = effort_checklist
            label = f"{cat} ({done}/{total})"
            _w(ws, r, 1, label)
            _w(ws, r, 2, done)
            _w(ws, r, 3, total)
            _w(ws, r, 4, effort)
        else:
            _w(ws, r, 1, None)
            _w(ws, r, 2, None)
            _w(ws, r, 3, None)
            _w(ws, r, 4, None)


def _fill_rotulos_sheet(wb, rotulos_rows):
    """
    xRotulos: A = Rótulo (done/total), B = done, C = pending, D = LeadTime, E = CycleTime
    """
    sheet_name = "xRotulos" if "xRotulos" in wb.sheetnames else ("PorCategoria" if "PorCategoria" in wb.sheetnames else None)
    if not sheet_name:
        return
    ws = wb[sheet_name]
    # Clear existing data (keep row 1 header)
    for r in range(2, ws.max_row + 1):
        for c in range(1, 6):
            ws.cell(r, c).value = None
    # Write header row 1
    headers = ["Rótulo (qtd concluído / qtd total)", "Qtd. Concluído", "Qtd Total", "Leadtime (em dias)", "Cycletime (em dias)"]
    for c, h in enumerate(headers, 1):
        ws.cell(1, c).value = h
    for i, (display, done, pend, lt, ct) in enumerate(rotulos_rows):
        r = i + 2
        _w(ws, r, 1, display)
        _w(ws, r, 2, done)
        _w(ws, r, 3, pend)
        _w(ws, r, 4, lt)
        _w(ws, r, 5, ct)


def _fill_responsaveis_sheet(wb, resp_rows):
    """
    xResponsaveis: A = Nome (done/total), B = done_bucket, C = pending, D = LeadTime, E = CycleTime
    """
    sheet_name = "xResponsaveis" if "xResponsaveis" in wb.sheetnames else ("PorColaborador" if "PorColaborador" in wb.sheetnames else None)
    if not sheet_name:
        return
    ws = wb[sheet_name]
    for r in range(2, ws.max_row + 1):
        for c in range(1, 6):
            ws.cell(r, c).value = None
    headers = ["Nome (qtd concluído / qtd total)", "Qtd. no Bucket Concluído", "Qtd. Fora do Bucket Concluído", "LeadTime (Dias)", "CycleTime (Dias)"]
    for c, h in enumerate(headers, 1):
        ws.cell(1, c).value = h
    for i, (display, done_bkt, pend, lt, ct) in enumerate(resp_rows):
        r = i + 2
        _w(ws, r, 1, display)
        _w(ws, r, 2, done_bkt)
        _w(ws, r, 3, pend)
        _w(ws, r, 4, lt)
        _w(ws, r, 5, ct)


def _fill_cfd_sheet(wb, dates, todo_list, doing_list, done_list):
    """
    xCFD: A = Data, B = To Do, C = Doing, D = Done
    """
    sheet_name = "xCFD" if "xCFD" in wb.sheetnames else None
    if not sheet_name:
        return
    ws = wb[sheet_name]
    _w(ws, 1, 1, "Data"); _w(ws, 1, 2, "To Do"); _w(ws, 1, 3, "Doing"); _w(ws, 1, 4, "Done")
    for i, (dt, td, do, dn) in enumerate(zip(dates, todo_list, doing_list, done_list)):
        r = i + 2
        _w(ws, r, 1, dt); _w(ws, r, 2, td); _w(ws, r, 3, do); _w(ws, r, 4, dn)


def _fill_wip_sheet(wb, dates, bucket_names, bucket_matrix, x_total=None):
    """
    xWIP: A = Data, B..N = one dynamic column per state/label, last col = Total.
    """
    sheet_name = "xWIP" if "xWIP" in wb.sheetnames else None
    if not sheet_name:
        return
    ws = wb[sheet_name]

    # Limpa valores antigos (preserva estilo/formatação).
    for r in range(1, ws.max_row + 1):
        for c in range(1, ws.max_column + 1):
            ws.cell(r, c).value = None

    _w(ws, 1, 1, "Data")
    for j, bkt in enumerate(bucket_names):
        _w(ws, 1, j + 2, bkt)
    total_col = len(bucket_names) + 2
    if x_total is not None:
        _w(ws, 1, total_col, "Total")
    for i, dt in enumerate(dates):
        r = i + 2
        _w(ws, r, 1, dt)
        for j, bkt in enumerate(bucket_names):
            _w(ws, r, j + 2, bucket_matrix[bkt][i])
        if x_total is not None:
            _w(ws, r, total_col, x_total[i])


def _fill_cts_sheet(wb, dates, hu_labels, cts_matrix, fora_hu_daily):
    """
    xCTS: A = Data, then pairs (HU_nome, qtd) for each HU, last pair = Fora de HU
    Row 1: header with HU names and 'qtd' alternating
    """
    sheet_name = "xCTS" if "xCTS" in wb.sheetnames else None
    if not sheet_name:
        return
    ws = wb[sheet_name]
    # Header row
    def _short_hu_label(lbl):
        s = str(lbl)
        s = s.replace("Construção UI/UX Desktop", "Desktop")
        s = s.replace("Construção UI/UX Mobile", "Mobile")
        s = s.replace("Construção DEV", "Construção")
        s = s.replace("Testes DEV", "Testes")
        s = s.replace("Registro e Publicação", "Registro")
        return s

    _w(ws, 1, 1, "Data")
    all_labels = list(hu_labels) + ["Fora de HU"]
    for j, lbl in enumerate(all_labels):
        _w(ws, 1, j * 2 + 2, _short_hu_label(lbl))
        _w(ws, 1, j * 2 + 3, "qtd")
    # Data rows
    for i, dt in enumerate(dates):
        r = i + 2
        _w(ws, r, 1, dt)
        for j, (lbl, vals) in enumerate(zip(hu_labels, cts_matrix)):
            v = vals[i]
            # index col (HU name repeated when there's data)
            _w(ws, r, j * 2 + 2, lbl if v > 0 else None)
            _w(ws, r, j * 2 + 3, v)
        # Fora de HU
        j = len(hu_labels)
        v = fora_hu_daily[i]
        _w(ws, r, j * 2 + 2, "Fora de HU" if v > 0 else None)
        _w(ws, r, j * 2 + 3, v)


def _fill_histograma_sheet(wb, hist_31, indicativos):
    """
    xHistograma: A = DIAS (1-31), B = QTD, C = INDICATIVO
    """
    sheet_name = "xHistograma" if "xHistograma" in wb.sheetnames else None
    if not sheet_name:
        return
    ws = wb[sheet_name]
    _w(ws, 1, 1, "DIAS"); _w(ws, 1, 2, "QTD"); _w(ws, 1, 3, "INDICATIVO")
    for i in range(31):
        r = i + 2
        _w(ws, r, 1, i + 1)
        _w(ws, r, 2, hist_31[i] if i < len(hist_31) else 0)
        _w(ws, r, 3, indicativos[i] if i < len(indicativos) else None)


def _fill_histograma2_sheet(wb, stats_rows):
    """
    xHistograma2: A = descricao, B = valor
    """
    sheet_name = "xHistograma2" if "xHistograma2" in wb.sheetnames else None
    if not sheet_name:
        return
    ws = wb[sheet_name]
    _w(ws, 1, 1, "Descritivo da Métrica (Legenda)"); _w(ws, 1, 2, "Dado numérico de referência (dias)")
    for i, (desc, val) in enumerate(stats_rows):
        r = i + 2
        _w(ws, r, 1, desc)
        _w(ws, r, 2, val)


def _fill_esforco_hu_sheet(wb, hu_full_names, esforco_detailed):
    """
    EsforcoHU:
      A = HU full name,  B = max effort per profile,  C = total effort
    Template has 5 data rows (rows 2-6).
    """
    ws   = wb["EsforcoHU"]
    ROWS = 5
    top  = esforco_detailed[:ROWS]

    for i in range(ROWS):
        r = i + 2
        if i < len(top):
            hu_id, max_ep, total_effort = top[i]
            full_name = hu_full_names.get(hu_id, hu_id)
            _w(ws, r, 1, full_name)
            _w(ws, r, 2, max_ep)
            _w(ws, r, 3, total_effort)
        else:
            _w(ws, r, 1, None)
            _w(ws, r, 2, None)
            _w(ws, r, 3, None)


def _clear_report_planning_tables(wb):
    """
    Limpa APENAS as células de dados das tabelas Planejamento e Histórico,
    preservando integralmente a estrutura de cabeçalhos do template:
      - Linha 6: "PRIORIDADE" + números 1-9 (Planejamento) / "SPRINT 0..07" (Histórico)
      - Linha 7: nomes das HUs (Planejamento) / datas das sprints (Histórico)
      - Col G (7): labels de perfil do Planejamento
      - Col R (18): fórmulas AVERAGE do Histórico
      - Col U (21): labels de perfil do Histórico
      - Linhas 19-20: fórmulas LARGE/SUM do Planejamento

    O que é limpo (somente valores manuais):
      Planejamento — linhas 8-18, colunas H-L (8-12): storypoints por HU por perfil
      Histórico    — linhas 8-21, colunas V-AC (22-29): valores históricos por sprint
    """
    if "Report" not in wb.sheetnames:
        return
    ws = wb["Report"]

    # Planejamento: limpa textos antigos atrás do gráfico de roadmap (col G)
    # para evitar "sobreposição visual" quando o gráfico é transparente.
    for r in range(8, 21):
        try:
            ws.cell(r, 7).value = None
        except AttributeError:
            pass  # MergedCell — skip

    # Planejamento: só as células de storypoints manuais (rows 8-18, cols H-L = 8-12)
    for r in range(8, 19):
        for c in range(8, 13):
            cell = ws.cell(r, c)
            try:
                cell.value = None
            except AttributeError:
                pass  # MergedCell — skip

    # Histórico: só os valores históricos (rows 8-21, cols V-AC = 22-29)
    for r in range(8, 22):
        for c in range(22, 30):
            cell = ws.cell(r, c)
            try:
                cell.value = None
            except AttributeError:
                pass  # MergedCell — skip


def _clear_report_roadmap_overlay_cells(wb):
    """
    Limpa cÃ©lulas que ficam por trÃ¡s do grÃ¡fico de Roadmap no Report.

    O chart de roadmap (chart9) cobre aproximadamente C11:AC32. Como esse
    grÃ¡fico pode ser transparente, qualquer texto/fÃ³rmula nessa Ã¡rea aparece
    sobreposto (incluindo #DIV/0! de fÃ³rmulas antigas).
    """
    if "Report" not in wb.sheetnames:
        return
    ws = wb["Report"]

    # Bloco visual coberto pelo roadmap.
    for r in range(11, 33):       # 11..32
        for c in range(3, 30):    # C..AC
            try:
                ws.cell(r, c).value = None
            except AttributeError:
                pass  # MergedCell â€” skip

    # Defesa extra para labels/formulas que podem reaparecer no eixo central.
    for r in range(7, 23):        # 7..22
        for c in (7, 18, 21):     # G, R, U
            try:
                ws.cell(r, c).value = None
            except AttributeError:
                pass


def _ensure_report_manual_structure(wb):
    """
    Garante estrutura mínima do bloco manual do Report (Planejamento/Histórico).
    Restaura labels de perfil APENAS se estiverem ausentes (não sobrescreve).

    Colunas corretas conforme template:
      Planejamento: labels na col G (7), dados HU em H-L (8-12)
      Histórico:    AVERAGE em col R (18), labels na col U (21), dados em V-AC (22-29)
    """
    if "Report" not in wb.sheetnames:
        return

    ws = wb["Report"]

    profile_labels_plan = [
        "PO (DOCS, LINKS, LEIS, ETC.)",
        "REQUISITOS",
        "UX/UI  (DESKTOP)",
        "UX/UI  (MOBILE)",
        "DEV FRONT (DESKTOP)",
        "DEV FRONT (MOBILE)",
        "DEV BACK",
        "DEV BANCO DE DADOS",
        "DEV BI",
        "TESTE (possíveis no prazo da sprint)",
        "ARQUITETURA",
        "Mensuração (maior esforço individual)",
        "Mensuracao soma total esforço por HU",
    ]

    profile_labels_hist = profile_labels_plan + [
        "Quantidade de Histórias de Usuário (HU)",
    ]

    def _safe_cell_write(ws, row, col, value):
        """Write value to cell only if it's writable (not a MergedCell slave)."""
        try:
            cell = ws.cell(row, col)
            existing = cell.value
            if not _strip(str(existing) if existing is not None else ""):
                cell.value = value
        except AttributeError:
            pass  # MergedCell slave — skip

    # ── Planejamento (área superior): NÃO repor labels na col G (linhas 8-20) ──
    # Esses textos aparecem "por trás" do gráfico de roadmap (fundo transparente).
    # O bloco de planejamento da sprint que alimenta fórmulas fica em linhas inferiores.

    # ── Histórico: labels na col U (21), linhas 7-21 ──
    _safe_cell_write(ws, 7, 21, "ID ou DESCRIÇÃO DO ITEM")
    for i, label in enumerate(profile_labels_hist, start=8):  # U8:U21
        _safe_cell_write(ws, i, 21, label)

    # ── Fórmulas AVERAGE do Histórico: col R (18), linhas 8-21 ──
    # (=AVERAGE(V{r}:AC{r}) — referencia cols V-AC = dados históricos)
    for r in range(8, 22):
        _safe_cell_write(ws, r, 18, f"=AVERAGE(V{r}:AC{r})")

    # Nota: NÃO preencher zeros nas células vazias do Histórico.
    # As células vazias devem ficar em branco para o usuário preencher manualmente.


def _update_report_metadata(wb, export_date, author):
    """
    Update Report sheet header cells:
      V2 = data da extração,  Y2 = author name
    """
    if "Report" not in wb.sheetnames:
        return
    ws = wb["Report"]
    # Write as formatted string to avoid ####### when column is narrow
    for row, col, val in [
        (2, 22, export_date.strftime("%d/%m/%Y")),  # V2
        (2, 25, author),                             # Y2
    ]:
        try:
            ws.cell(row, col).value = val
        except AttributeError:
            pass  # MergedCell slave — skip


def _clear_sheet_non_formula(ws, r1=1, c1=1, r2=None, c2=None):
    if r2 is None:
        r2 = ws.max_row
    if c2 is None:
        c2 = ws.max_column
    for r in range(r1, r2 + 1):
        for c in range(c1, c2 + 1):
            cell = ws.cell(r, c)
            val = cell.value
            if isinstance(val, str) and val.startswith("="):
                continue
            try:
                cell.value = None
            except Exception:
                pass


def create_clean_template(source_template_path, output_template_path):
    """
    Build a reusable clean template from an existing workbook:
      - clear data tabs (x* and legacy data tabs)
      - clear manual gp_* input values
      - keep formulas/charts/layout
    """
    wb = load_workbook(source_template_path)

    legacy_data_tabs = {
        "KPI", "Roadmap", "HUs", "BurndownTarefas", "BurndownHU",
        "Dispersao", "Colaboradores", "Areas", "HUInOut",
        "Categorias", "PorCategoria", "xHU", "xHU_inOut",
    }

    # 1) Data tabs used by processing pipeline
    for name in wb.sheetnames:
        ws = wb[name]
        if name.startswith("x") or name in legacy_data_tabs:
            _clear_sheet_non_formula(ws)

    # 2) Manual gp_* tabs
    if "gp_Cabecalhos" in wb.sheetnames:
        _clear_sheet_non_formula(wb["gp_Cabecalhos"], r1=1, c1=2, r2=200, c2=2)
    if "gp_Plann_Sprint" in wb.sheetnames:
        ws = wb["gp_Plann_Sprint"]
        _clear_sheet_non_formula(ws, r1=1, c1=2, r2=ws.max_row, c2=ws.max_column)
    if "gp_Plann_Projeto" in wb.sheetnames:
        _clear_sheet_non_formula(wb["gp_Plann_Projeto"])
    if "gp_Disponibilidade" in wb.sheetnames:
        ws = wb["gp_Disponibilidade"]
        _clear_sheet_non_formula(ws, r1=7, c1=1, r2=ws.max_row, c2=max(4, ws.max_column))
    if "gp_Transversalidade" in wb.sheetnames:
        ws = wb["gp_Transversalidade"]
        _clear_sheet_non_formula(ws, r1=2, c1=1, r2=ws.max_row, c2=max(5, ws.max_column))
    if "gp_Roadmap" in wb.sheetnames:
        ws = wb["gp_Roadmap"]
        _clear_sheet_non_formula(ws, r1=2, c1=1, r2=ws.max_row, c2=max(2, ws.max_column))

    # 3) Legacy manual tabs (when present)
    for legacy_name in ("Planejamento", "Historico"):
        if legacy_name in wb.sheetnames:
            _clear_sheet_non_formula(wb[legacy_name])
    if "Roadmap" in wb.sheetnames:
        ws = wb["Roadmap"]
        _clear_sheet_non_formula(ws, r1=2, c1=1, r2=ws.max_row, c2=ws.max_column)

    # 4) Manual table area in Report and metadata
    if "Report" in wb.sheetnames:
        _clear_report_planning_tables(wb)
        _clear_report_roadmap_overlay_cells(wb)
        ws = wb["Report"]
        for row, col in ((2, 22), (2, 25)):  # V2, Y2
            try:
                ws.cell(row, col).value = None
            except Exception:
                pass

    try:
        wb.calculation.fullCalcOnLoad = True
        wb.calculation.forceFullCalc = True
    except Exception:
        pass
    wb.save(output_template_path)

    # Restore original chart visuals from source template to avoid white backgrounds.
    _postprocess_xlsx(output_template_path, template_path=source_template_path)


# ═══════════════════════════════════════════════════════════════════════════════
#             AUTO-EXTRAÇÃO DA TAREFA GESTÃO E ROADMAP DO PLANNER
# ═══════════════════════════════════════════════════════════════════════════════

_DATE_LINE_RE = re.compile(
    r"^(?:(\d{2})[/-](\d{2})[/-](\d{4})|(\d{4})-(\d{2})-(\d{2}))(.*)$"
)
_DATE_TOKEN_RE = re.compile(
    r"(?<!\d)(?:(\d{2})[/-](\d{2})[/-](\d{4})|(\d{4})-(\d{2})-(\d{2}))(?!\d)"
)


def _roadmap_date_match(match):
    if not match:
        return None, ""
    if match.group(1):
        day, month, year = match.group(1), match.group(2), match.group(3)
    else:
        year, month, day = match.group(4), match.group(5), match.group(6)
    return f"{day}/{month}/{year}", match.group(7)


def _normalize_roadmap_block(text):
    lines = [line.strip() for line in str(text or "").splitlines() if line.strip()]
    if not lines:
        return ""

    date_match = _DATE_LINE_RE.match(lines[0])
    date, trailing = _roadmap_date_match(date_match)
    date = date or lines[0]
    content_lines = []
    if date_match:
        trailing = trailing.strip()
        if trailing:
            content_lines.extend(
                part.strip()
                for part in re.split(r"\t+|;|\s{2,}", trailing)
                if part.strip()
            )
        content_lines.extend(lines[1:])
    else:
        content_lines.extend(lines[1:])

    goal = ""
    marco_parts = []
    unlabeled = []
    has_goal_label = False
    has_marco_label = False
    for line in content_lines:
        goal_match = re.match(r"^goal\s*:\s*(.*)$", line, flags=re.IGNORECASE)
        marco_match = re.match(r"^marco\s*:\s*(.*)$", line, flags=re.IGNORECASE)
        if goal_match:
            has_goal_label = True
            goal = goal_match.group(1).strip()
        elif marco_match:
            has_marco_label = True
            value = marco_match.group(1).strip()
            if value:
                marco_parts.append(value)
        else:
            unlabeled.append(line)

    if not has_goal_label and unlabeled and (has_marco_label or len(unlabeled) >= 2):
        goal = unlabeled.pop(0)
    marco_parts.extend(unlabeled)

    normalized = [date]
    if goal:
        normalized.append(f"Goal: {goal}")
    if marco_parts:
        normalized.append(f"Marco: {' '.join(marco_parts)}")
    return "\n".join(normalized)

def build_gestao_meta(df):
    """
    Extrai PROJETO, GERENTE e LINKEDIN da tarefa 'Gestão' no export do Planner.
    Retorna dict com chaves: projeto, gerente, linkedin.
    """
    mask = df["tarefa"].fillna("").astype(str).str.strip().str.lower() == "gestão"
    if not mask.any():
        mask = df["tarefa"].fillna("").astype(str).str.strip().str.lower() == "gestao"
    task_norm = df["tarefa"].fillna("").astype(str).map(_norm_text_key)
    alt_mask = task_norm.isin({"gestao", "governanca"})
    if alt_mask.any():
        mask = alt_mask
    if not mask.any():
        return {"projeto": "", "gerente": "", "linkedin": ""}

    desc = _strip(df.loc[mask, "notas"].iloc[0])
    result = {"projeto": "", "gerente": "", "linkedin": ""}
    for line in desc.split("\n"):
        line = line.strip()
        if ":" not in line:
            continue
        key_raw, _, val = line.partition(":")
        key_norm = key_raw.strip().upper()
        val = val.strip()
        if key_norm == "PROJETO":
            result["projeto"] = val
        elif "GERENTE" in key_norm and "LINKEDIN" not in key_norm:
            result["gerente"] = val
        elif "LINKEDIN" in key_norm:
            result["linkedin"] = val
    return result


def build_roadmap_from_df(df):
    """
    Extrai os itens do roadmap da tarefa 'Roadmap' no export do Planner.
    Cada item = uma linha que começa com data DD/MM/YYYY + linha(s) de descrição.
    Retorna lista de (marco_text, posição).
    """
    POSITION_SEQ = [10, -10, 40, 25, 10, -40, -25, -10, 40, 25, 10, -40, -10,
                    40, 25, 10, -40, -25, -10, 40]

    task_names = df["tarefa"].fillna("").astype(str).map(_norm_text_key)
    exact_mask = task_names == "roadmap"
    named_mask = task_names.str.startswith("roadmap ")
    named_mask = task_names.str.contains(r"\broadmap\b", regex=True)
    mask = exact_mask | named_mask
    if not mask.any():
        return []

    desc = _strip(df.loc[mask, "notas"].iloc[0])
    lines = desc.split("\n")

    # Agrupa linhas em blocos: cada bloco começa com uma data
    blocks = []
    date_matches = list(_DATE_TOKEN_RE.finditer(desc))
    for index, match in enumerate(date_matches):
        end = date_matches[index + 1].start() if index + 1 < len(date_matches) else len(desc)
        block = desc[match.start():end].strip()
        if block:
            blocks.append(block)

    result = []
    for i, text in enumerate(blocks):
        pos = POSITION_SEQ[i % len(POSITION_SEQ)]
        result.append((_normalize_roadmap_block(text), pos))
    return result


def _fill_roadmap_sheet(wb, roadmap_items):
    """
    Preenche a aba Roadmap com os itens extraídos do Planner.
    Estrutura esperada: A = Marco (texto completo), B = Posição (int).
    """
    if "Roadmap" not in wb.sheetnames:
        return
    ws = wb["Roadmap"]
    # Limpa dados (mantém header linha 1)
    for r in range(2, ws.max_row + 1):
        ws.cell(r, 1).value = None
        ws.cell(r, 2).value = None
    for i, (marco, pos) in enumerate(roadmap_items):
        r = i + 2
        _w(ws, r, 1, marco)
        _w(ws, r, 2, pos)


def read_template_effort(wb):
    """
    Lê a tabela de planejamento do Report (perfis × HUs) e a EsforcoHU,
    e retorna um dict {label_normalizado: esforco_total} para uso em
    PorCategoriaBubbles.

    Estrutura do Report (nova template v2):
      Linhas 8-18, col 7 = nome do perfil
      Cols 8+ = esforço por HU (valor inteiro ou 'N/A')

    Mapeamento perfil → rótulos (do Prompt Mestre):
      DEV FRONT.*DESKTOP  → DEV, FRONTEND, DESKTOP
      DEV FRONT.*MOBILE   → DEV, FRONTEND, MOBILE
      DEV BACK            → DEV, BACKEND
      DEV BANCO           → DEV, BACKEND
      DEV BI              → DEV
      UX.*DESKTOP         → UX, FRONTEND, DESKTOP
      UX.*MOBILE          → UX, FRONTEND, MOBILE
      TESTE               → Q/A TESTES
    """
    PROFILE_LABEL_MAP = [
        (re.compile(r"dev front.*desktop", re.I), ["DEV", "FRONTEND", "DESKTOP"]),
        (re.compile(r"dev front.*mobile",  re.I), ["DEV", "FRONTEND", "MOBILE"]),
        (re.compile(r"dev back\b",         re.I), ["DEV", "BACKEND"]),
        (re.compile(r"dev banco",          re.I), ["DEV", "BACKEND"]),
        (re.compile(r"dev bi\b",           re.I), ["DEV"]),
        (re.compile(r"ux.*desktop",        re.I), ["UX", "FRONTEND", "DESKTOP"]),
        (re.compile(r"ux.*mobile",         re.I), ["UX", "FRONTEND", "MOBILE"]),
        (re.compile(r"\bux\b",             re.I), ["UX"]),
        (re.compile(r"teste",              re.I), ["Q/A TESTES", "TESTES"]),
    ]

    label_effort = defaultdict(int)

    ws_rep = wb.get("Report") if hasattr(wb, "get") else (
        wb["Report"] if "Report" in wb.sheetnames else None
    )
    if ws_rep:
        for r in range(8, 19):
            profile = ws_rep.cell(r, 7).value
            if not profile:
                continue
            profile_str = str(profile).strip()
            # Soma esforço deste perfil por todos os HUs (cols 8 em diante)
            total = 0
            for c in range(8, 18):
                val = ws_rep.cell(r, c).value
                if val and str(val).strip() not in ("", "N/A", "nan", "None"):
                    try:
                        total += int(float(str(val)))
                    except (ValueError, TypeError):
                        pass
            if total == 0:
                continue
            for pattern, labels in PROFILE_LABEL_MAP:
                if pattern.search(profile_str):
                    for lbl in labels:
                        label_effort[_norm_label_key(lbl)] += total
                    break

    # EsforcoHU → HU labels
    ws_hu = None
    try:
        ws_hu = wb["EsforcoHU"]
    except (KeyError, TypeError):
        pass
    if ws_hu:
        for r in range(2, ws_hu.max_row + 1):
            hu_name = ws_hu.cell(r, 1).value
            total_val = ws_hu.cell(r, 3).value
            if not hu_name or not total_val:
                continue
            try:
                effort = int(float(str(total_val)))
            except (ValueError, TypeError):
                continue
            label_effort[_norm_label_key(str(hu_name).strip())] = effort
            # Also index by short HU ID (e.g. "HU052")
            m = re.match(r"(HU\s*\d+)", str(hu_name), re.I)
            if m:
                label_effort[_norm_label_key(m.group(1))] = effort

    return dict(label_effort)


# ═══════════════════════════════════════════════════════════════════════════════
#                     DADOS MANUAIS  (Opção B – legado, mantido para compat.)
# ═══════════════════════════════════════════════════════════════════════════════

# Mapeamento fixo das linhas de perfil no Report (col 5 = nome do perfil)
# Report rows 8-18 = 11 perfis; rows 19-20 = fórmulas (não sobrescrever)
REPORT_PROFILE_ROWS   = list(range(8, 19))   # rows 8..18 (11 perfis)
REPORT_PLAN_COL_START = 5   # col E: nome do perfil
REPORT_PLAN_COL_END   = 14  # col N: último HU (9 colunas de HU = F..N)
REPORT_HIST_PROFILE_COL  = 19   # col S: nome do perfil (historico)
REPORT_HIST_SPRINT_START = 20   # col T: primeira sprint
REPORT_HIST_SPRINT_END   = 27   # col AA: última sprint (8 sprints)
REPORT_HIST_ROWS         = list(range(8, 22))   # rows 8..21 (14 linhas)

GP_PLANN_PROJ_DEFAULT_LABELS = [
    "ID ou DESCRIÇÃO DO ITEM",
    "PO (DOCS, LINKS, LEIS, ETC.)",
    "REQUISITOS",
    "UX/UI  (DESKTOP)",
    "UX/UI  (MOBILE)",
    "BENCHMARK COMPONENTES - DEV",
    "CONSTRUCAO COMPONENTES - DEV",
    "TESTES- DEV",
    "REGISTRO e PUBLICAÇÃO (Storybook) - DEV",
    "",
    "",
    "",
    "Mensuração (maior esforço individual)",
    "Throughput - Qtd Storypoints",
    "Throughput - Qtd de Tarefas/Cards",
    "Qtd de Histórias de Usuário (HU)",
]

GP_PLANN_SPRINT_DEFAULT_LABELS = [
    "ID ou DESCRIÇÃO DO ITEM",
    "PO (DOCS, LINKS, LEIS, ETC.)",
    "REQUISITOS",
    "UX/UI  (DESKTOP)",
    "UX/UI  (MOBILE)",
    "BENCHMARK COMPONENTES - DEV",
    "CONSTRUCAO COMPONENTES - DEV",
    "TESTES- DEV",
    "REGISTRO e PUBLICAÇÃO (Storybook) - DEV",
    "",
    "",
    "",
    "Mensuração (maior esforço individual)",
    "Mensuracao soma total esforço por HU",
]


def _normalize_gp_plann_projeto_matrix(matrix):
    """
    Normaliza matriz de gp_Plann_Projeto para evitar deslocamentos de coluna.

    Casos tratados:
    1) Coluna extra de "Média..." no início -> remove coluna 1.
    2) Coluna de rótulos ausente (A1 já começa em "Escopo ...") -> recoloca
       a coluna de rótulos padrão na frente.
    """
    if not isinstance(matrix, list) or not matrix:
        return matrix

    safe_rows = [r for r in matrix if isinstance(r, list)]
    if not safe_rows:
        return matrix

    def _norm_txt(s):
        s = str(s or "").strip().lower()
        s = unicodedata.normalize("NFKD", s)
        return "".join(ch for ch in s if not unicodedata.combining(ch))

    def _looks_scope_header(s):
        return bool(re.search(
            r"escopo|sprint|continuo|jan|fev|mar|abr|mai|jun|jul|ago|set|out|nov|dez",
            _norm_txt(s),
        ))

    def _is_profile_label(s):
        return bool(re.search(
            r"po|requis|ux|dev|benchmark|construcao|teste|registro|mensur|throughput|historia",
            _norm_txt(s),
        ))

    first_header = _norm_txt(safe_rows[0][0] if len(safe_rows[0]) > 0 else "")
    second_header = _norm_txt(safe_rows[0][1] if len(safe_rows[0]) > 1 else "")
    looks_media_header = ("media" in first_header)
    looks_scope_header = _looks_scope_header(second_header)

    non_empty = 0
    numeric_first = 0
    label_second = 0
    profile_first = 0
    na_like_first = 0
    max_check = min(len(safe_rows), 24)
    for i in range(1, max_check):
        row = safe_rows[i]
        a = str(row[0]).strip() if len(row) > 0 and row[0] is not None else ""
        b = str(row[1]).strip() if len(row) > 1 and row[1] is not None else ""
        if a or b:
            non_empty += 1
        if re.fullmatch(r"-?\d+([.,]\d+)?", a):
            numeric_first += 1
        if _is_profile_label(b):
            label_second += 1
        if _is_profile_label(a):
            profile_first += 1
        if _norm_txt(a) in {"n/a", "na", ""}:
            na_like_first += 1

    # Caso clássico: usuário colou bloco com coluna "Média..." à esquerda.
    # Segurança: só remove coluna quando a coluna "Média..." é explícita.
    looks_shifted_by_media = looks_media_header
    if looks_shifted_by_media:
        return [row[1:] if isinstance(row, list) and len(row) > 1 else ([] if isinstance(row, list) else row)
                for row in matrix]

    # Caso legado: coluna de rótulos já foi perdida (A1 começa em Escopo...).
    has_id_header = bool(re.search(r"\bid\b", first_header) and re.search(r"descr", first_header))
    looks_scope_first = _looks_scope_header(first_header)
    looks_scope_second = _looks_scope_header(second_header)
    looks_missing_label_col = (
        (not has_id_header)
        and looks_scope_first
        and looks_scope_second
        and non_empty >= 4
        and profile_first <= 1
        and (na_like_first + numeric_first) >= int((non_empty * 0.6) + 0.9999)
    )

    if looks_missing_label_col:
        rebuilt = []
        for i, row in enumerate(matrix):
            if not isinstance(row, list):
                rebuilt.append(row)
                continue
            label = GP_PLANN_PROJ_DEFAULT_LABELS[i] if i < len(GP_PLANN_PROJ_DEFAULT_LABELS) else ""
            rebuilt.append([label] + row)
        return rebuilt

    return matrix


def _normalize_gp_plann_projeto_sheet(ws):
    """
    Normaliza a aba gp_Plann_Projeto diretamente na planilha.
    """
    max_rows = 240
    max_cols = 40

    matrix = []
    for r in range(1, max_rows + 1):
        row = [ws.cell(r, c).value for c in range(1, max_cols + 1)]
        while row and (row[-1] is None or str(row[-1]).strip() == ""):
            row.pop()
        matrix.append(row)

    while matrix and not matrix[-1]:
        matrix.pop()

    normalized = _normalize_gp_plann_projeto_matrix(matrix)
    if normalized == matrix:
        return

    for r in range(1, max_rows + 1):
        for c in range(1, max_cols + 1):
            ws.cell(r, c).value = None

    for r_idx, row in enumerate(normalized, start=1):
        if not isinstance(row, list):
            continue
        for c_idx, val in enumerate(row, start=1):
            ws.cell(r_idx, c_idx).value = val


def _normalize_gp_plann_sprint_matrix(matrix):
    """
    Corrige gp_Plann_Sprint quando a coluna A foi "engolida".
    """
    if not isinstance(matrix, list) or not matrix:
        return matrix

    safe_rows = [r for r in matrix if isinstance(r, list)]
    if not safe_rows:
        return matrix

    def _norm_txt(s):
        s = str(s or "").strip().lower()
        s = unicodedata.normalize("NFKD", s)
        return "".join(ch for ch in s if not unicodedata.combining(ch))

    def _is_profile_label(s):
        return bool(re.search(
            r"po|requis|ux|dev|benchmark|construcao|teste|registro|mensur|throughput|historia",
            _norm_txt(s),
        ))

    first_header = _norm_txt(safe_rows[0][0] if len(safe_rows[0]) > 0 else "")
    second_header = _norm_txt(safe_rows[0][1] if len(safe_rows[0]) > 1 else "")
    has_id_header = bool(re.search(r"\bid\b", first_header) and re.search(r"descr", first_header))

    non_empty = 0
    profile_first = 0
    na_like_first = 0
    hu_header_like = 0
    max_check = min(len(safe_rows), 24)
    for i in range(1, max_check):
        row = safe_rows[i]
        a = str(row[0]).strip() if len(row) > 0 and row[0] is not None else ""
        b = str(row[1]).strip() if len(row) > 1 and row[1] is not None else ""
        if a or b:
            non_empty += 1
        if _is_profile_label(a):
            profile_first += 1
        if _norm_txt(a) in {"n/a", "na", ""} or re.fullmatch(r"-?\d+([.,]\d+)?", a):
            na_like_first += 1
        if re.match(r"hu\s*\d+", _norm_txt(first_header)) or re.match(r"hu\s*\d+", _norm_txt(second_header)):
            hu_header_like = 1

    looks_missing_label_col = (
        (not has_id_header)
        and hu_header_like == 1
        and non_empty >= 4
        and profile_first <= 1
        and na_like_first >= int((non_empty * 0.6) + 0.9999)
    )
    if not looks_missing_label_col:
        return matrix

    rebuilt = []
    for i, row in enumerate(matrix):
        if not isinstance(row, list):
            rebuilt.append(row)
            continue
        label = GP_PLANN_SPRINT_DEFAULT_LABELS[i] if i < len(GP_PLANN_SPRINT_DEFAULT_LABELS) else ""
        rebuilt.append([label] + row)
    return rebuilt


def _normalize_gp_plann_sprint_sheet(ws):
    max_rows = 240
    max_cols = 40

    matrix = []
    for r in range(1, max_rows + 1):
        row = [ws.cell(r, c).value for c in range(1, max_cols + 1)]
        while row and (row[-1] is None or str(row[-1]).strip() == ""):
            row.pop()
        matrix.append(row)

    while matrix and not matrix[-1]:
        matrix.pop()

    normalized = _normalize_gp_plann_sprint_matrix(matrix)
    if normalized == matrix:
        return

    for r in range(1, max_rows + 1):
        for c in range(1, max_cols + 1):
            ws.cell(r, c).value = None

    for r_idx, row in enumerate(normalized, start=1):
        if not isinstance(row, list):
            continue
        for c_idx, val in enumerate(row, start=1):
            ws.cell(r_idx, c_idx).value = val


def extract_dados_manuais_starter(template_path, keep_formulas=False):
    """
    Extrai as 3 seções manuais do template e retorna um novo Workbook
    com sheets Roadmap, Planejamento e Historico prontos para o usuário editar.
    """
    from openpyxl import Workbook as _WB
    tpl = load_workbook(template_path, data_only=not keep_formulas)
    out = _WB()
    out.remove(out.active)

    # ── 1. Roadmap ────────────────────────────────────────────────────────────
    if "Roadmap" in tpl.sheetnames:
        ws_src = tpl["Roadmap"]
        ws_dst = out.create_sheet("Roadmap")
        for row in ws_src.iter_rows(values_only=True):
            ws_dst.append(list(row))

    # ── 2. Planejamento (Report cols E-N, rows 6-18) ──────────────────────────
    ws_dst = out.create_sheet("Planejamento")
    if "Report" in tpl.sheetnames:
        ws_rep = tpl["Report"]
        # rows 6-7 = cabeçalhos (PRIORIDADE + HU names)
        # rows 8-18 = perfis com storypoints
        for src_row in range(6, 19):
            row_data = []
            for col in range(REPORT_PLAN_COL_START, REPORT_PLAN_COL_END + 1):
                v = ws_rep.cell(src_row, col).value
                # No starter removemos fórmulas para facilitar edição manual.
                # Na opção A (report anterior), mantemos fórmulas quando solicitado.
                if keep_formulas:
                    row_data.append(v)
                else:
                    row_data.append(None if isinstance(v, str) and v.startswith("=") else v)
            ws_dst.append(row_data)

    # ── 3. Historico (Report cols S-AA, rows 6-21) ───────────────────────────
    ws_dst = out.create_sheet("Historico")
    if "Report" in tpl.sheetnames:
        ws_rep = tpl["Report"]
        # rows 6-7 = cabeçalhos (Sprint labels + períodos)
        # rows 8-21 = perfis com pontuação histórica
        for src_row in range(6, 22):
            row_data = []
            # col S (19) = nome do perfil
            for col in range(REPORT_HIST_PROFILE_COL, REPORT_HIST_SPRINT_END + 1):
                v = ws_rep.cell(src_row, col).value
                if keep_formulas:
                    row_data.append(v)
                else:
                    row_data.append(None if isinstance(v, str) and v.startswith("=") else v)
            ws_dst.append(row_data)

    return out


def inject_dados_manuais(wb, dados_manuais_path):
    """
    Injeta as 3 abas do arquivo de dados manuais no workbook de saída.
    Sheets esperadas: Roadmap, Planejamento, Historico.
    """
    dm = load_workbook(dados_manuais_path)

    def _clear_rect(ws, r1, r2, c1, c2):
        for r in range(r1, r2 + 1):
            for c in range(c1, c2 + 1):
                ws.cell(r, c).value = None

    # ── 1. Roadmap ────────────────────────────────────────────────────────────
    if "Roadmap" in dm.sheetnames and "Roadmap" in wb.sheetnames:
        ws_src = dm["Roadmap"]
        ws_dst = wb["Roadmap"]
        # limpa linhas de dados (mantém linha 1 = cabeçalho do template)
        _clear_rect(ws_dst, 1, ws_dst.max_row, 1, ws_dst.max_column)
        # copia tudo da fonte
        for r_idx, row in enumerate(ws_src.iter_rows(values_only=True), 1):
            for c_idx, val in enumerate(row, 1):
                ws_dst.cell(r_idx, c_idx).value = val

    # ── 2. Planejamento → Report cols E-N, rows 6-18 ─────────────────────────
    if "Planejamento" in dm.sheetnames and "Report" in wb.sheetnames:
        ws_src = dm["Planejamento"]
        ws_dst = wb["Report"]
        _clear_rect(ws_dst, 6, 18, REPORT_PLAN_COL_START, REPORT_PLAN_COL_END)
        # Planejamento row 1 → Report row 6 (PRIORIDADE / HU names header)
        # Planejamento row 2 → Report row 7 (HU descriptions)
        # Planejamento rows 3-13 → Report rows 8-18 (11 perfis)
        for local_r, report_r in enumerate(range(6, 19), 1):
            if local_r > ws_src.max_row:
                break
            for local_c, report_c in enumerate(
                    range(REPORT_PLAN_COL_START, REPORT_PLAN_COL_END + 1), 1):
                val = ws_src.cell(local_r, local_c).value
                ws_dst.cell(report_r, report_c).value = val

    # ── 3. Historico → Report cols S-AA, rows 6-21 ───────────────────────────
    if "Historico" in dm.sheetnames and "Report" in wb.sheetnames:
        ws_src = dm["Historico"]
        ws_dst = wb["Report"]
        _clear_rect(ws_dst, 6, 21, REPORT_HIST_PROFILE_COL, REPORT_HIST_SPRINT_END)
        # Historico row 1 → Report row 6 (Sprint labels)
        # Historico row 2 → Report row 7 (períodos)
        # Historico rows 3-16 → Report rows 8-21 (perfis + totais)
        for local_r, report_r in enumerate(range(6, 22), 1):
            if local_r > ws_src.max_row:
                break
            for local_c, report_c in enumerate(
                    range(REPORT_HIST_PROFILE_COL, REPORT_HIST_SPRINT_END + 1), 1):
                val = ws_src.cell(local_r, local_c).value
                ws_dst.cell(report_r, report_c).value = val


# ═══════════════════════════════════════════════════════════════════════════════
#                    ZIP-LEVEL POST-PROCESSING  (chartEx injection)
# ═══════════════════════════════════════════════════════════════════════════════

def inject_dados_manuais_ext(wb, dados_manuais_path):
    """
    Injeta dados manuais no workbook de saida.

    Suporta:
    - Legado: Roadmap, Planejamento, Historico
    - gp_*: gp_Roadmap, gp_Plann_Sprint, gp_Plann_Projeto,
      gp_Disponibilidade, gp_Transversalidade, gp_Cabecalhos

    Retorno:
      {"roadmap": bool, "report_plan_hist": bool, "gp_tabs": [..]}
    """
    dm = load_workbook(dados_manuais_path)
    applied_gp_tabs = set()
    applied_roadmap = False
    applied_report_plan_hist = False

    def _clear_rect(ws, r1, r2, c1, c2):
        for r in range(r1, r2 + 1):
            for c in range(c1, c2 + 1):
                ws.cell(r, c).value = None

    def _copy_sheet_all(ws_src, ws_dst):
        for r in range(1, ws_dst.max_row + 1):
            for c in range(1, ws_dst.max_column + 1):
                try:
                    ws_dst.cell(r, c).value = None
                except Exception:
                    pass
        for r_idx, row in enumerate(ws_src.iter_rows(values_only=True), 1):
            for c_idx, val in enumerate(row, 1):
                try:
                    ws_dst.cell(r_idx, c_idx).value = val
                except Exception:
                    pass

    for sheet_name in (
        "gp_Plann_Projeto",
        "gp_Plann_Sprint",
        "gp_Cabecalhos",
        "gp_Disponibilidade",
        "gp_Transversalidade",
        "gp_Roadmap",
    ):
        if sheet_name in dm.sheetnames and sheet_name in wb.sheetnames:
            _copy_sheet_all(dm[sheet_name], wb[sheet_name])
            if sheet_name == "gp_Plann_Projeto":
                _normalize_gp_plann_projeto_sheet(wb[sheet_name])
            if sheet_name == "gp_Plann_Sprint":
                _normalize_gp_plann_sprint_sheet(wb[sheet_name])
            applied_gp_tabs.add(sheet_name)
            if sheet_name == "gp_Roadmap":
                applied_roadmap = True

    if "Roadmap" in dm.sheetnames and "Roadmap" in wb.sheetnames:
        _copy_sheet_all(dm["Roadmap"], wb["Roadmap"])
        applied_roadmap = True

    if "Roadmap" in dm.sheetnames and "gp_Roadmap" in wb.sheetnames and "gp_Roadmap" not in applied_gp_tabs:
        _copy_sheet_all(dm["Roadmap"], wb["gp_Roadmap"])
        applied_gp_tabs.add("gp_Roadmap")
        applied_roadmap = True

    if "Planejamento" in dm.sheetnames and "Report" in wb.sheetnames:
        ws_src = dm["Planejamento"]
        ws_dst = wb["Report"]
        _clear_rect(ws_dst, 6, 18, REPORT_PLAN_COL_START, REPORT_PLAN_COL_END)
        for local_r, report_r in enumerate(range(6, 19), 1):
            if local_r > ws_src.max_row:
                break
            for local_c, report_c in enumerate(range(REPORT_PLAN_COL_START, REPORT_PLAN_COL_END + 1), 1):
                ws_dst.cell(report_r, report_c).value = ws_src.cell(local_r, local_c).value
        applied_report_plan_hist = True

    if "Historico" in dm.sheetnames and "Report" in wb.sheetnames:
        ws_src = dm["Historico"]
        ws_dst = wb["Report"]
        _clear_rect(ws_dst, 6, 21, REPORT_HIST_PROFILE_COL, REPORT_HIST_SPRINT_END)
        for local_r, report_r in enumerate(range(6, 22), 1):
            if local_r > ws_src.max_row:
                break
            for local_c, report_c in enumerate(range(REPORT_HIST_PROFILE_COL, REPORT_HIST_SPRINT_END + 1), 1):
                ws_dst.cell(report_r, report_c).value = ws_src.cell(local_r, local_c).value
        applied_report_plan_hist = True

    # IMPORTANTE:
    # Nao copiar a aba Report inteira do arquivo manual.
    # Isso reintroduz dados/graficos antigos e gera sobreposicoes no dashboard final.
    # O fluxo correto e copiar apenas:
    #   - abas gp_* (entrada manual)
    #   - legado Planejamento/Historico (quando usados explicitamente)
    # Portanto, mesmo que o arquivo manual tenha "Report", ela e ignorada aqui.

    return {
        "roadmap": applied_roadmap,
        "report_plan_hist": applied_report_plan_hist,
        "gp_tabs": sorted(applied_gp_tabs),
    }



def inject_dados_formulario(wb, form_data):
    """
    Injeta dados do formulario web nas abas gp_* do workbook.

    form_data: dict com chaves opcionais:
      cabecalhos      -> gp_Cabecalhos (PROJETO, GERENTE, LINKEDIN, PRODUCT_GOAL, SPRINT_GOAL)
      plann_projeto   -> gp_Plann_Projeto (matrix: list[list[str]])
      plann_sprint    -> gp_Plann_Sprint (hus: list[str], values: list[list[str]])
      disponibilidade -> gp_Disponibilidade (list de {situacao, empregador, nome, pct})
      transversalidade-> gp_Transversalidade (list de {nome, funcao, squad, intervalo})
      roadmap         -> gp_Roadmap (list de {marco, posicao})

    Retorna lista de nomes de abas que foram preenchidas.
    """
    filled = []

    def _clear_non_formula(ws):
        for r in range(1, ws.max_row + 1):
            for c in range(1, ws.max_column + 1):
                cell = ws.cell(r, c)
                val = cell.value
                if isinstance(val, str) and val.startswith("="):
                    continue
                try:
                    cell.value = None
                except Exception:
                    pass

    def _coerce_cell(v):
        if v is None:
            return None
        if isinstance(v, (int, float)):
            return v
        s = str(v).strip()
        if s == "":
            return None
        num = s.replace(".", "").replace(",", ".") if "," in s else s
        if re.fullmatch(r"-?\d+(\.\d+)?", num):
            try:
                f = float(num)
                return int(f) if abs(f - int(f)) < 1e-9 else f
            except Exception:
                return s
        return s

    def _normalize_plann_projeto_matrix(matrix):
        """
        Corrige matriz colada com coluna extra de "Média..." no início.
        Esperado em gp_Plann_Projeto:
          col A = perfil/label
          col B.. = sprints/valores
        """
        if not isinstance(matrix, list) or not matrix:
            return matrix

        safe_rows = [r for r in matrix if isinstance(r, list) and len(r) > 0]
        if not safe_rows:
            return matrix

        def _norm_txt(s):
            s = str(s or "").strip().lower()
            s = unicodedata.normalize("NFKD", s)
            return "".join(ch for ch in s if not unicodedata.combining(ch))

        first_header = _norm_txt(safe_rows[0][0] if len(safe_rows[0]) > 0 else "")
        second_header = _norm_txt(safe_rows[0][1] if len(safe_rows[0]) > 1 else "")
        looks_media_header = ("media" in first_header)
        looks_scope_header = bool(re.search(r"escopo|sprint|continuo|jan|fev|mar|abr|mai|jun|jul|ago|set|out|nov|dez", second_header))

        non_empty = 0
        numeric_first = 0
        label_second = 0
        max_check = min(len(safe_rows), 16)
        for i in range(1, max_check):
            row = safe_rows[i]
            a = str(row[0]).strip() if len(row) > 0 and row[0] is not None else ""
            b = str(row[1]).strip() if len(row) > 1 and row[1] is not None else ""
            if a or b:
                non_empty += 1
            if re.fullmatch(r"-?\d+([.,]\d+)?", a):
                numeric_first += 1
            if re.search(r"po|requis|ux|dev|teste|arquitet|mensur|throughput|historia", _norm_txt(b)):
                label_second += 1

        looks_shifted = looks_media_header or (
            looks_scope_header and non_empty >= 4 and
            numeric_first >= int((non_empty * 0.6) + 0.9999) and
            label_second >= 2
        )
        if not looks_shifted:
            return matrix

        return [row[1:] if isinstance(row, list) else row for row in matrix]

    # ── gp_Cabecalhos ─────────────────────────────────────────────────────────
    if "cabecalhos" in form_data and "gp_Cabecalhos" in wb.sheetnames:
        c = form_data["cabecalhos"]
        ws = wb["gp_Cabecalhos"]
        cab_rows = [
            ("PROJETO",                                        c.get("projeto", "")),
            ("NOME DO GERENTE DO PROJETO",                     c.get("gerente", "")),
            ("link para LINKEDIN DO GERENTE DO PROJETO",       c.get("linkedin", "")),
            ("PRODUCT GOAL (OBJETIVO DO PROJETO)",             c.get("product_goal", "")),
            ("SPRINT GOAL (OBJETIVO DA SPRINT)",               c.get("sprint_goal", "")),
        ]
        for i, (lbl, val) in enumerate(cab_rows, start=1):
            _w(ws, i, 1, lbl)
            if val:  # Nao sobrescreve com vazio
                _w(ws, i, 2, val)
        filled.append("gp_Cabecalhos")

    # ── gp_Plann_Projeto ──────────────────────────────────────────────────────
    if "plann_projeto" in form_data and "gp_Plann_Projeto" in wb.sheetnames:
        pp = form_data["plann_projeto"] or {}
        matrix = pp.get("matrix", [])
        if isinstance(matrix, list) and matrix:
            matrix = _normalize_gp_plann_projeto_matrix(matrix)
            ws = wb["gp_Plann_Projeto"]
            _clear_non_formula(ws)
            for r_idx, row in enumerate(matrix, start=1):
                if not isinstance(row, list):
                    continue
                for c_idx, raw in enumerate(row, start=1):
                    _w(ws, r_idx, c_idx, _coerce_cell(raw))
            filled.append("gp_Plann_Projeto")

    # ── gp_Plann_Sprint ───────────────────────────────────────────────────────
    if "plann_sprint" in form_data and "gp_Plann_Sprint" in wb.sheetnames:
        ps = form_data["plann_sprint"]
        ws = wb["gp_Plann_Sprint"]
        _ROLES = [
            "PO (DOCS, LINKS, LEIS, ETC.)",
            "REQUISITOS",
            "UX/UI  (DESKTOP)",
            "UX/UI  (MOBILE)",
            "DEV FRONT (DESKTOP)",
            "DEV FRONT (MOBILE)",
            "DEV BACK",
            "DEV BANCO DE DADOS",
            "DEV BI",
            "TESTE (possíveis no prazo da sprint)",
            "ARQUITETURA",
        ]
        hus = ps.get("hus", [])
        values = ps.get("values")
        if values is None:
            values = []
            rows_payload = ps.get("rows", [])
            if isinstance(rows_payload, list):
                for row in rows_payload:
                    if isinstance(row, dict):
                        vals = row.get("valores")
                        if vals is None:
                            vals = row.get("values", [])
                        values.append(vals if isinstance(vals, list) else [])
                    else:
                        values.append([])
        _w(ws, 1, 1, "ID ou DESCRIÇÃO DO ITEM")
        for j, hu in enumerate(hus, start=2):
            _w(ws, 1, j, hu)
        for i, role in enumerate(_ROLES):
            row_vals = values[i] if i < len(values) else []
            _w(ws, i + 2, 1, role)
            for j, val in enumerate(row_vals):
                _w(ws, i + 2, j + 2, val if str(val).strip() else "N/A")
        filled.append("gp_Plann_Sprint")

    # ── gp_Disponibilidade ────────────────────────────────────────────────────
    if "disponibilidade" in form_data and "gp_Disponibilidade" in wb.sheetnames:
        rows = form_data["disponibilidade"]
        ws = wb["gp_Disponibilidade"]
        _w(ws, 6, 1, "SITUACAO")
        _w(ws, 6, 2, "EMPREGADOR")
        _w(ws, 6, 3, "NOME")
        _w(ws, 6, 4, "Percentual Disponivel")
        # Limpa area de dados mantendo formulas do template fora de A:D.
        for r in range(8, 501):
            _w(ws, r, 1, None)
            _w(ws, r, 2, None)
            _w(ws, r, 3, None)
            _w(ws, r, 4, None)

        # Dados iniciam na linha 8 (linha 7 e reservada no template).
        for i, row in enumerate(rows, start=8):
            _w(ws, i, 1, row.get("situacao", "titular"))
            _w(ws, i, 2, row.get("empregador", ""))
            _w(ws, i, 3, row.get("nome", ""))
            try:
                pct_raw = row.get("pct", row.get("percentual", row.get("percent", None)))
                _w(ws, i, 4, _parse_percent_fraction(pct_raw, default_value=1.0))
            except (ValueError, TypeError):
                _w(ws, i, 4, 1.0)
        filled.append("gp_Disponibilidade")

    # ── gp_Transversalidade ───────────────────────────────────────────────────
    if "transversalidade" in form_data and "gp_Transversalidade" in wb.sheetnames:
        rows = form_data["transversalidade"]
        ws = wb["gp_Transversalidade"]
        _w(ws, 1, 1, "NOME")
        _w(ws, 1, 2, "FUNÇÃO")
        _w(ws, 1, 3, "SQUAD")
        _w(ws, 1, 4, "INTERVALO")
        _w(ws, 1, 5, "coluna")
        for i, row in enumerate(rows, start=2):
            _w(ws, i, 1, row.get("nome", ""))
            _w(ws, i, 2, row.get("funcao", ""))
            _w(ws, i, 3, row.get("squad", ""))
            _w(ws, i, 4, row.get("intervalo", ""))
            _w(ws, i, 5, 1)
        filled.append("gp_Transversalidade")

    # ── gp_Roadmap ────────────────────────────────────────────────────────────
    if "roadmap" in form_data and "gp_Roadmap" in wb.sheetnames:
        items = form_data["roadmap"]
        ws = wb["gp_Roadmap"]
        _w(ws, 1, 1, "Marco")
        _w(ws, 1, 2, "Posição")
        for i, item in enumerate(items, start=2):
            _w(ws, i, 1, item.get("marco", ""))
            try:
                _w(ws, i, 2, float(str(item.get("posicao", "0")).replace(",", ".")))
            except (ValueError, TypeError):
                _w(ws, i, 2, 0)
        filled.append("gp_Roadmap")

    return filled


def _parse_percent_fraction(raw, default_value=1.0):
    """
    Converte diferentes formatos de percentual para fração:
      100   -> 1.0
      100%  -> 1.0
      0.8   -> 0.8
      80,5% -> 0.805
    """
    if raw is None:
        return default_value
    txt = str(raw).strip()
    if txt == "":
        return default_value
    has_pct = "%" in txt
    txt = txt.replace("%", "").replace(" ", "").replace(",", ".")
    val = float(txt)
    if has_pct or abs(val) > 1.0:
        val = val / 100.0
    return val


def _normalize_gp_disponibilidade_sheet(ws):
    """
    Normaliza percentuais em gp_Disponibilidade!D8:D* para fração (0..1),
    preservando linhas totalmente vazias.
    """
    for r in range(8, 501):
        a = ws.cell(r, 1).value
        b = ws.cell(r, 2).value
        c = ws.cell(r, 3).value
        d = ws.cell(r, 4).value
        has_row = any(
            v is not None and str(v).strip() != ""
            for v in (a, b, c, d)
        )
        if not has_row:
            continue
        try:
            ws.cell(r, 4).value = _parse_percent_fraction(d, default_value=1.0)
        except Exception:
            ws.cell(r, 4).value = 1.0


def _postprocess_xlsx(output_path: str, template_path: str = None) -> None:
    """
    Pós-processamento MINIMAL do xlsx via manipulação direta do ZIP.

    Estratégia (cirúrgica — só toca o que é necessário):
      - NÃO substitui drawing1.xml (openpyxl gera um válido para charts normais).
      - NÃO injeta chart .rels ou style/colors de charts NORMAIS (openpyxl funciona sem eles).
      - SOMENTE injeta arquivos necessários para chartEx (sunburst / tree-map):
        * chartEx1.xml, chartEx2.xml (os gráficos em si)
        * chartEx1.xml.rels, chartEx2.xml.rels (referências de style/colors dos chartEx)
        * style/colors referenciados PELOS chartEx (style6, colors6, style11, colors11)
      - Adiciona anchors chartEx ao drawing1.xml do openpyxl (append, não replace).
      - Adiciona refs no drawing1.xml.rels e Content_Types.
      - Limpa cache do gráfico Roadmap (chart10).
    """
    import re as _re

    # Fast-path: preserve chart visuals exactly as in template (including transparency).
    if template_path and os.path.exists(template_path):
        tmp_visual = output_path + ".tmp_postproc_visual"
        try:
            replace_map = {}
            with zipfile.ZipFile(template_path, "r") as ztpl:
                tpl_names = set(ztpl.namelist())

                # Drawing + normal chart parts
                for name in tpl_names:
                    is_drawing = name in {
                        "xl/drawings/drawing1.xml",
                        "xl/drawings/_rels/drawing1.xml.rels",
                    }
                    is_chart = (
                        name.startswith("xl/charts/chart")
                        and name.endswith(".xml")
                        and "chartEx" not in name
                    )
                    is_chart_rel = (
                        name.startswith("xl/charts/_rels/chart")
                        and name.endswith(".rels")
                        and "chartEx" not in name
                    )
                    if is_drawing or is_chart or is_chart_rel:
                        replace_map[name] = ztpl.read(name)

                # chartEx + dependencies
                chart_ex_rels = []
                for name in tpl_names:
                    if name.startswith("xl/charts/chartEx") and name.endswith(".xml"):
                        replace_map[name] = ztpl.read(name)
                    elif name.startswith("xl/charts/_rels/chartEx") and name.endswith(".rels"):
                        rel_bytes = ztpl.read(name)
                        replace_map[name] = rel_bytes
                        chart_ex_rels.append(rel_bytes.decode("utf-8", errors="ignore"))

                for rel_xml in chart_ex_rels:
                    for dep in _re.findall(r'Target="([^"]+)"', rel_xml):
                        dep_path = f"xl/charts/{dep}"
                        if dep_path in tpl_names:
                            replace_map[dep_path] = ztpl.read(dep_path)

                # Normal chart style/color dependencies used by chart rels.
                for name in tpl_names:
                    if name.startswith("xl/charts/style") and name.endswith(".xml"):
                        replace_map[name] = ztpl.read(name)
                    elif name.startswith("xl/charts/colors") and name.endswith(".xml"):
                        replace_map[name] = ztpl.read(name)

            if replace_map:
                with zipfile.ZipFile(output_path, "r") as zin, \
                     zipfile.ZipFile(tmp_visual, "w", zipfile.ZIP_DEFLATED) as zout:

                    existing_names = set(zin.namelist())
                    for item in zin.infolist():
                        name = item.filename
                        data = replace_map.get(name, zin.read(name))

                        if name == "[Content_Types].xml":
                            xml = data.decode("utf-8", errors="ignore")
                            additions = ""
                            for part_name in replace_map.keys():
                                if not part_name.startswith("xl/charts/") or "/_rels/" in part_name:
                                    continue
                                base = part_name.split("/")[-1]
                                if base.startswith("chartEx") and base.endswith(".xml"):
                                    ctype = "application/vnd.ms-office.chartex+xml"
                                elif base.startswith("style") and base.endswith(".xml"):
                                    ctype = "application/vnd.ms-office.chartstyle+xml"
                                elif base.startswith("colors") and base.endswith(".xml"):
                                    ctype = "application/vnd.ms-office.chartcolorstyle+xml"
                                elif base.startswith("chart") and base.endswith(".xml"):
                                    ctype = "application/vnd.openxmlformats-officedocument.drawingml.chart+xml"
                                else:
                                    continue
                                override = f'/xl/charts/{base}'
                                if override not in xml:
                                    additions += (
                                        f'<Override PartName="{override}" '
                                        f'ContentType="{ctype}"/>'
                                    )
                            if additions:
                                xml = xml.replace("</Types>", additions + "</Types>")
                            data = xml.encode("utf-8")

                        if (
                            name.startswith("xl/charts/chart")
                            and name.endswith(".xml")
                            and "chartEx" not in name
                        ):
                            xml = data.decode("utf-8", errors="ignore")
                            xml = _re.sub(
                                r'<c:strCache>.*?</c:strCache>',
                                '<c:strCache><c:ptCount val="0"/></c:strCache>',
                                xml,
                                flags=_re.DOTALL,
                            )
                            xml = _re.sub(
                                r'<c:numCache>.*?</c:numCache>',
                                '<c:numCache><c:formatCode>General</c:formatCode>'
                                '<c:ptCount val="0"/></c:numCache>',
                                xml,
                                flags=_re.DOTALL,
                            )
                            data = xml.encode("utf-8")

                        zout.writestr(item, data)

                    for part_name, part_data in replace_map.items():
                        if part_name not in existing_names:
                            zout.writestr(part_name, part_data)

                os.replace(tmp_visual, output_path)
                print("      [OK] visual dos gráficos preservado do template + caches de séries limpos.")
                return
        except Exception as _preserve_err:
            if os.path.exists(tmp_visual):
                os.remove(tmp_visual)
            print(f"      [aviso] preservação visual falhou, usando fallback: {_preserve_err}")

    # ── 1. Extrai SOMENTE assets de chartEx do template ──────────────────────
    chartex_assets = {}    # zip_path -> bytes  (SOMENTE chartEx e seus deps)
    chartex_rids = []      # lista de (rId_original, target_relativo) do template
    chartex_deps = set()   # style/colors que os chartEx referenciam

    if template_path and os.path.exists(template_path):
        try:
            with zipfile.ZipFile(template_path, "r") as ztpl:
                tpl_names = set(ztpl.namelist())

                # Descobre rIds dos chartEx no drawing1.xml.rels do template
                if "xl/drawings/_rels/drawing1.xml.rels" in tpl_names:
                    _rels_xml = ztpl.read("xl/drawings/_rels/drawing1.xml.rels").decode("utf-8")
                    for m in _re.finditer(
                        r'Id="(rId\d+)"\s+Type="[^"]*chartEx[^"]*"\s+Target="([^"]*)"', _rels_xml
                    ):
                        chartex_rids.append((m.group(1), m.group(2)))

                # Extrai os chartEx XML
                for _zn in tpl_names:
                    if _zn.startswith("xl/charts/chartEx") and _zn.endswith(".xml"):
                        chartex_assets[_zn] = ztpl.read(_zn)

                # Extrai os .rels dos chartEx e descobre quais style/colors eles usam
                for _zn in tpl_names:
                    if _zn.startswith("xl/charts/_rels/chartEx") and _zn.endswith(".rels"):
                        rels_data = ztpl.read(_zn)
                        chartex_assets[_zn] = rels_data
                        # Parse para descobrir dependências
                        for dep_m in _re.finditer(r'Target="([^"]+)"', rels_data.decode("utf-8")):
                            dep_target = dep_m.group(1)  # ex: "style6.xml", "colors6.xml"
                            dep_path = f"xl/charts/{dep_target}"
                            chartex_deps.add(dep_path)

                # Extrai SOMENTE os style/colors referenciados pelos chartEx
                for dep_path in chartex_deps:
                    if dep_path in tpl_names:
                        chartex_assets[dep_path] = ztpl.read(dep_path)

                # Extrai as anchors de chartEx do template drawing1.xml (posição original)
                if "xl/drawings/drawing1.xml" in tpl_names:
                    _tpl_drawing = ztpl.read("xl/drawings/drawing1.xml").decode("utf-8")
                    chartex_assets["__tpl_drawing__"] = _tpl_drawing.encode("utf-8")

            if chartex_assets:
                print(f"      [OK] {len(chartex_assets)} asset(s) chartEx extraído(s) do template.")
                if chartex_rids:
                    print(f"      [OK] chartEx encontrados: {[r[0] for r in chartex_rids]}")
                if chartex_deps:
                    print(f"      [OK] Dependências chartEx: {sorted(chartex_deps)}")
        except Exception as _e:
            print(f"      [aviso] Não foi possível ler assets do template: {_e}")
            chartex_assets = {}

    has_any_chartex = bool(chartex_rids)

    if not has_any_chartex:
        print("      [aviso] chartEx não encontrado no template – gráficos chartEx não injetados.")

    # ── 2. Processa o ZIP ─────────────────────────────────────────────────────
    tmp_path = output_path + ".tmp_postproc"
    chartex_rid_map = {}  # target -> novo rId (definido no escopo externo para drawing1.xml.rels)

    try:
        with zipfile.ZipFile(output_path, "r") as zin, \
             zipfile.ZipFile(tmp_path, "w", zipfile.ZIP_DEFLATED) as zout:

            existing_names = set(zin.namelist())

            # Monta mapa de injeção: SOMENTE chartEx e suas deps
            inject_map = {}
            for _tn, _td in chartex_assets.items():
                if _tn.startswith("__"):  # skip metadados internos
                    continue
                if _tn not in existing_names:
                    inject_map[_tn] = _td

            for item in zin.infolist():
                name = item.filename
                data = zin.read(name)

                # ── drawing1.xml: APPEND anchors dos chartEx ──────────────────
                if name == "xl/drawings/drawing1.xml" and has_any_chartex:
                    xml = data.decode("utf-8")
                    uses_prefix = "xdr:wsDr" in xml
                    xdr = "xdr:" if uses_prefix else ""
                    close_tag = f"</{xdr}wsDr>"

                    # Descobre o maior rId no .rels do openpyxl para não colidir
                    _rels_data = zin.read("xl/drawings/_rels/drawing1.xml.rels").decode("utf-8") \
                        if "xl/drawings/_rels/drawing1.xml.rels" in existing_names else ""
                    _existing_rids = [int(x) for x in _re.findall(r'rId(\d+)', _rels_data)]
                    _next_rid = max(_existing_rids) + 1 if _existing_rids else 30

                    # Descobre o maior shape id no drawing
                    _existing_ids = [int(x) for x in _re.findall(r'<(?:\w+:)?cNvPr id="(\d+)"', xml)]
                    _next_id = max(_existing_ids) + 1 if _existing_ids else 100

                    # Mapeia chartEx targets para novos rIds
                    for _orig_rid, tgt in chartex_rids:
                        chartex_rid_map[tgt] = f"rId{_next_rid}"
                        _next_rid += 1

                    # Tenta extrair as anchors originais do template para preservar posição
                    tpl_drawing = chartex_assets.get("__tpl_drawing__", b"").decode("utf-8")
                    tpl_anchors = {}  # orig_rId -> anchor_xml
                    if tpl_drawing:
                        for am in _re.finditer(
                            r'<xdr:twoCellAnchor>(.*?)</xdr:twoCellAnchor>',
                            tpl_drawing, _re.DOTALL
                        ):
                            block = am.group(0)
                            rid_match = _re.search(r'r:id="(rId\d+)"', block)
                            if rid_match and rid_match.group(1) in {r[0] for r in chartex_rids}:
                                tpl_anchors[rid_match.group(1)] = block

                    for _orig_rid, tgt in chartex_rids:
                        new_rid = chartex_rid_map[tgt]
                        label = tgt.split("/")[-1].replace(".xml", "")

                        if _orig_rid in tpl_anchors:
                            # Usa anchor do template com posição original, troca rId e id
                            anchor_xml = tpl_anchors[_orig_rid]
                            # Troca o rId interno para o novo
                            anchor_xml = anchor_xml.replace(
                                f'r:id="{_orig_rid}"', f'r:id="{new_rid}"')
                            # Troca xdr: prefix se necessário (template usa xdr:, openpyxl não)
                            if not uses_prefix:
                                anchor_xml = _re.sub(r'xdr:', '', anchor_xml)
                                anchor_xml = anchor_xml.replace('<twoCellAnchor>', '<twoCellAnchor>')
                            # Atualiza shape ids para não colidir
                            for old_id in _re.findall(r'<(?:\w+:)?cNvPr id="(\d+)"', anchor_xml):
                                old_id_int = int(old_id)
                                if old_id_int > 0:  # Preserva id="0" no Fallback
                                    anchor_xml = anchor_xml.replace(
                                        f'id="{old_id}"', f'id="{_next_id}"', 1)
                                    _next_id += 1
                            anchor = anchor_xml
                        else:
                            # Fallback: gera anchor minimal
                            anchor = (
                                f'<{xdr}twoCellAnchor>'
                                f'<{xdr}from><{xdr}col>0</{xdr}col><{xdr}colOff>0</{xdr}colOff>'
                                f'<{xdr}row>0</{xdr}row><{xdr}rowOff>0</{xdr}rowOff></{xdr}from>'
                                f'<{xdr}to><{xdr}col>5</{xdr}col><{xdr}colOff>0</{xdr}colOff>'
                                f'<{xdr}row>5</{xdr}row><{xdr}rowOff>0</{xdr}rowOff></{xdr}to>'
                                '<mc:AlternateContent xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006">'
                                '<mc:Choice xmlns:cx1="http://schemas.microsoft.com/office/drawing/2015/9/8/chartex" Requires="cx1">'
                                f'<{xdr}graphicFrame macro="">'
                                f'<{xdr}nvGraphicFramePr>'
                                f'<{xdr}cNvPr id="{_next_id}" name="{label}"/>'
                                f'<{xdr}cNvGraphicFramePr/>'
                                f'</{xdr}nvGraphicFramePr>'
                                f'<{xdr}xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/></{xdr}xfrm>'
                                '<a:graphic>'
                                '<a:graphicData uri="http://schemas.microsoft.com/office/drawing/2014/chartex">'
                                '<cx:chart xmlns:cx="http://schemas.microsoft.com/office/drawing/2014/chartex" '
                                'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
                                f'r:id="{new_rid}"/>'
                                '</a:graphicData>'
                                '</a:graphic>'
                                f'</{xdr}graphicFrame>'
                                '</mc:Choice>'
                                '</mc:AlternateContent>'
                                f'<{xdr}clientData/>'
                                f'</{xdr}twoCellAnchor>'
                            )
                            _next_id += 1

                        xml = xml.replace(close_tag, anchor + close_tag)
                    data = xml.encode("utf-8")

                # ── drawing1.xml.rels: adiciona refs para chartEx ─────────────
                elif name == "xl/drawings/_rels/drawing1.xml.rels" and has_any_chartex:
                    xml = data.decode("utf-8")
                    for tgt, new_rid in chartex_rid_map.items():
                        if new_rid not in xml:
                            xml = xml.replace("</Relationships>",
                                f'<Relationship Id="{new_rid}" '
                                'Type="http://schemas.microsoft.com/office/2014/relationships/chartEx" '
                                f'Target="{tgt}"/>'
                                '</Relationships>')
                    data = xml.encode("utf-8")

                # ── [Content_Types].xml: registra SOMENTE chartEx + deps ──────
                elif name == "[Content_Types].xml" and has_any_chartex:
                    xml = data.decode("utf-8")
                    additions = ""
                    # chartEx content types
                    for _tn in inject_map:
                        bn = _tn.split("/")[-1]
                        if bn.startswith("chartEx") and bn.endswith(".xml") and bn not in xml:
                            additions += (
                                f'<Override PartName="/xl/charts/{bn}" '
                                'ContentType="application/vnd.ms-office.chartex+xml"/>')
                        elif bn.startswith("style") and bn.endswith(".xml") and bn not in xml:
                            additions += (
                                f'<Override PartName="/xl/charts/{bn}" '
                                'ContentType="application/vnd.ms-office.chartstyle+xml"/>')
                        elif bn.startswith("colors") and bn.endswith(".xml") and bn not in xml:
                            additions += (
                                f'<Override PartName="/xl/charts/{bn}" '
                                'ContentType="application/vnd.ms-office.chartcolorstyle+xml"/>')
                    if additions:
                        xml = xml.replace("</Types>", additions + "</Types>")
                    data = xml.encode("utf-8")

                # ── Limpa caches das séries dos charts normais ───────────────
                elif (
                    name.startswith("xl/charts/chart")
                    and name.endswith(".xml")
                    and "chartEx" not in name
                ):
                    xml = data.decode("utf-8")
                    xml = _re.sub(
                        r'<c:strCache>.*?</c:strCache>',
                        '<c:strCache><c:ptCount val="0"/></c:strCache>',
                        xml, flags=_re.DOTALL)
                    xml = _re.sub(
                        r'<c:numCache>.*?</c:numCache>',
                        '<c:numCache><c:formatCode>General</c:formatCode>'
                        '<c:ptCount val="0"/></c:numCache>',
                        xml, flags=_re.DOTALL)
                    data = xml.encode("utf-8")

                zout.writestr(item, data)

            # ── Escreve arquivos novos (SOMENTE chartEx + deps) ───────────────
            for zip_path, file_data in inject_map.items():
                if zip_path not in existing_names:
                    zout.writestr(zip_path, file_data)

        os.replace(tmp_path, output_path)
        if has_any_chartex:
            print("      [OK] chartEx injetado (minimal) + caches de séries limpos.")
        else:
            print("      [OK] Caches de séries limpos.")

    except Exception as exc:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        print(f"      [aviso] pós-processamento zip falhou: {exc}")


# ═══════════════════════════════════════════════════════════════════════════════
#                           MAIN ENTRY POINTS
# ═══════════════════════════════════════════════════════════════════════════════

def _fill_wip_sheet(wb, dates, bucket_names, bucket_matrix, x_total=None):
    sheet_name = "xWIP" if "xWIP" in wb.sheetnames else None
    if not sheet_name:
        return
    ws = wb[sheet_name]

    for r in range(1, ws.max_row + 1):
        for c in range(1, ws.max_column + 1):
            ws.cell(r, c).value = None

    _w(ws, 1, 1, "Data")
    for j, bkt in enumerate(bucket_names):
        _w(ws, 1, j + 2, bkt)

    for i, dt in enumerate(dates):
        r = i + 2
        _w(ws, r, 1, dt)
        for j, bkt in enumerate(bucket_names):
            _w(ws, r, j + 2, bucket_matrix[bkt][i])


def _fill_cts_sheet(wb, dates, hu_labels, cts_matrix, fora_hu_daily):
    sheet_name = "xCTS" if "xCTS" in wb.sheetnames else None
    if not sheet_name:
        return
    ws = wb[sheet_name]

    for r in range(1, ws.max_row + 1):
        for c in range(1, ws.max_column + 1):
            ws.cell(r, c).value = None

    def _short_hu_label(lbl):
        s = str(lbl)
        s = s.replace("Construção UI/UX Desktop", "Desktop")
        s = s.replace("Construção UI/UX Mobile", "Mobile")
        s = s.replace("Construção DEV", "Construção")
        s = s.replace("Testes DEV", "Testes")
        s = s.replace("Registro e Publicação", "Registro")
        return s

    _w(ws, 1, 1, "Data")
    all_labels = list(hu_labels) + ["Fora de HU"]
    for j, lbl in enumerate(all_labels):
        _w(ws, 1, j * 2 + 2, _short_hu_label(lbl))
        _w(ws, 1, j * 2 + 3, "qtd")

    for i, dt in enumerate(dates):
        r = i + 2
        _w(ws, r, 1, dt)
        for j, vals in enumerate(cts_matrix):
            _w(ws, r, j * 2 + 2, j + 1)
            _w(ws, r, j * 2 + 3, vals[i])
        j = len(hu_labels)
        _w(ws, r, j * 2 + 2, j + 1)
        _w(ws, r, j * 2 + 3, fora_hu_daily[i])


def _fill_dispersao_sheet(wb, hu_list, days, hu_matrix, nao_hu_daily, bd_start, hu_full_names):
    sheet_name = "xDispersaoTarefas" if "xDispersaoTarefas" in wb.sheetnames else "Dispersao"
    ws = wb[sheet_name]

    for r in range(1, ws.max_row + 1):
        for c in range(1, ws.max_column + 1):
            ws.cell(r, c).value = None

    def _short_disp_name(name):
        s = str(name)
        s = s.replace("UI/UX Desktop", "Desktop")
        s = s.replace("UI/UX Mobile", "Mobile")
        return s

    category_names = [_short_disp_name(hu_full_names.get(h, h)) for h in hu_list] + ["Não Presente em HU"]
    category_points = [dict() for _ in category_names]
    slots = [(-0.2, -0.2), (-0.2, 0.2), (0.2, -0.2), (0.2, 0.2)]

    for j in range(days):
        # Usa indice ordinal para evitar colisao de dia-do-mes em janelas multi-mes.
        day_num = j + 1
        hits = []
        for idx in range(len(hu_list)):
            cnt = hu_matrix[idx][j]
            if cnt > 0:
                hits.append((idx, float(cnt)))
        if nao_hu_daily[j] > 0:
            hits.append((len(hu_list), float(nao_hu_daily[j])))

        by_count = defaultdict(list)
        for idx, cnt in hits:
            by_count[cnt].append(idx)

        for cnt, idxs in by_count.items():
            idxs = sorted(idxs)
            if len(idxs) == 1:
                idx = idxs[0]
                category_points[idx][float(day_num)] = float(cnt)
            else:
                for k, idx in enumerate(idxs):
                    ox, oy = slots[k % len(slots)]
                    x = round(float(day_num) + ox, 1)
                    y = round(float(cnt) + oy, 1)
                    category_points[idx][x] = y

    x_values = sorted({x for pts in category_points for x in pts.keys()})

    _w(ws, 1, 1, "Nome da HU / Categoria")
    for c, x in enumerate(x_values, start=2):
        if abs(x - int(x)) < 1e-9:
            _w(ws, 1, c, int(x))
        else:
            _w(ws, 1, c, x)

    for i, name in enumerate(category_names):
        r = i + 2
        _w(ws, r, 1, name)
        pts = category_points[i]
        for c, x in enumerate(x_values, start=2):
            _w(ws, r, c, pts.get(x))


def _fill_burndown_sheet(wb, df, sprint_start, sprint_end, export_date):
    sheet_name = "xBurndownTarefas" if "xBurndownTarefas" in wb.sheetnames else "BurndownTarefas"
    ws = wb[sheet_name]
    ROWS = 31
    dfw = df[~df["is_backlog"]].copy()
    total = len(dfw)

    bd_start, bd_end = _month_bounds(sprint_end)
    days = (bd_end - bd_start).days + 1
    plan_by_day = _build_step_plan(total, days, blocks=5)

    done_dates = sorted(
        d for d in dfw.loc[dfw["done_kpi"] & dfw["date_done"].notna(), "date_done"].tolist()
    )

    for i in range(ROWS):
        r = i + 2
        if i < days:
            d = bd_start + timedelta(days=i)
            dt = datetime(d.year, d.month, d.day)
            meta = round(total * (1 - i / max(days - 1, 1)))
            plan = plan_by_day[i]
            rlz = total - bisect_right(done_dates, d)
            _w(ws, r, 1, dt)
            _w(ws, r, 2, meta)
            _w(ws, r, 3, plan)
            _w(ws, r, 4, rlz)
        else:
            _w(ws, r, 1, None)
            _w(ws, r, 2, None)
            _w(ws, r, 3, None)
            _w(ws, r, 4, None)


def _fill_burndown_hu_sheet(wb, df, sprint_start, sprint_end, export_date):
    sheet_name = "xBurndownHU" if "xBurndownHU" in wb.sheetnames else "BurndownHU"
    ws = wb[sheet_name]
    ROWS = 31
    dfw = df[df["hu"] != ""].copy()

    bd_start, bd_end = _month_bounds(sprint_end)
    days = (bd_end - bd_start).days + 1

    hu_info = []
    for _, grp in dfw.groupby("hu"):
        hu_total = len(grp)
        if bool(grp["done_kpi"].all()) and grp["date_done"].notna().all():
            completion_date = max(grp["date_done"].tolist())
        else:
            completion_date = None
        hu_info.append((hu_total, completion_date))

    total_hu_tasks = sum(t for t, _ in hu_info)
    plan_by_day = _build_step_plan(total_hu_tasks, days, blocks=5)

    for i in range(ROWS):
        r = i + 2
        if i < days:
            d = bd_start + timedelta(days=i)
            dt = datetime(d.year, d.month, d.day)
            meta = round(total_hu_tasks * (1 - i / max(days - 1, 1)))
            plan = plan_by_day[i]
            a_realiz = 0
            for hu_total, comp_date in hu_info:
                if comp_date is None or comp_date > d:
                    a_realiz += hu_total
            if i == 0:
                a_realiz = total_hu_tasks

            _w(ws, r, 1, dt)
            _w(ws, r, 2, meta)
            _w(ws, r, 3, plan)
            _w(ws, r, 4, a_realiz)
        else:
            _w(ws, r, 1, None)
            _w(ws, r, 2, None)
            _w(ws, r, 3, None)
            _w(ws, r, 4, None)


def _fill_burndown_storypoints_sheet(wb, df, sprint_end, hu_storypoints):
    sheet_name = "xBurndownStorypoints" if "xBurndownStorypoints" in wb.sheetnames else None
    if not sheet_name:
        return
    ws = wb[sheet_name]
    ROWS = 31

    dfw = df[(~df["is_backlog"]) & (df["hu"] != "")].copy()
    bd_start, bd_end = _month_bounds(sprint_end)
    days = (bd_end - bd_start).days + 1

    total_sp = float(sum(v for v in hu_storypoints.values() if v))
    plan_by_day = _build_step_plan(total_sp, days, blocks=5)
    task_counts_by_hu = dfw["hu"].value_counts().to_dict()
    task_weight = {}
    for hu, count in task_counts_by_hu.items():
        sp = float(hu_storypoints.get(str(hu).upper(), 0) or 0)
        if count > 0:
            task_weight[hu] = sp / count

    _w(ws, 1, 1, "Data")
    _w(ws, 1, 2, "Meta (Linear)")
    _w(ws, 1, 3, "Planejado")
    _w(ws, 1, 4, "A Realizar")

    for i in range(ROWS):
        r = i + 2
        if i < days:
            d = bd_start + timedelta(days=i)
            dt = datetime(d.year, d.month, d.day)
            meta = round(total_sp * (1 - i / max(days - 1, 1)))
            plan = plan_by_day[i]

            if i == 0:
                a_realizar = total_sp
            else:
                a_realizar = 0.0
                for _, row in dfw.iterrows():
                    hu = row.get("hu", "")
                    w = task_weight.get(hu, 0.0)
                    d_done = row.get("date_done")
                    if not _is_valid_date(d_done) or d_done > d:
                        a_realizar += w

            _w(ws, r, 1, dt)
            _w(ws, r, 2, meta)
            _w(ws, r, 3, plan)
            _w(ws, r, 4, a_realizar)
        else:
            _w(ws, r, 1, None)
            _w(ws, r, 2, None)
            _w(ws, r, 3, None)
            _w(ws, r, 4, None)


def _precompute_burndown(df, sprint_start, sprint_end, export_date):
    dfw = df[~df["is_backlog"]].copy()
    total = len(dfw)
    bd_start, bd_end, days = _resolve_burndown_window(dfw, sprint_start, sprint_end)
    plan_by_day = _build_step_plan(total, days, blocks=5)
    done_dates = sorted(
        d for d in dfw.loc[dfw["done_kpi"] & dfw["date_done"].notna(), "date_done"].tolist()
    )

    result = []
    for i in range(days):
        d = bd_start + timedelta(days=i)
        meta = round(total * (1 - i / max(days - 1, 1)))
        plan = plan_by_day[i]
        rlz = total - bisect_right(done_dates, d)
        result.append([d.strftime("%Y-%m-%d"), meta, plan, rlz])
    return result


def _precompute_burndown_hu(df, sprint_start, sprint_end, export_date):
    dfw = df[df["hu"] != ""].copy()
    bd_start, bd_end, days = _resolve_burndown_window(dfw, sprint_start, sprint_end)

    hu_info = []
    for _, grp in dfw.groupby("hu"):
        hu_total = len(grp)
        if bool(grp["done_kpi"].all()) and grp["date_done"].notna().all():
            completion_date = max(grp["date_done"].tolist())
        else:
            completion_date = None
        hu_info.append((hu_total, completion_date))

    total_hu_tasks = sum(t for t, _ in hu_info)
    plan_by_day = _build_step_plan(total_hu_tasks, days, blocks=5)

    result = []
    for i in range(days):
        d = bd_start + timedelta(days=i)
        meta = round(total_hu_tasks * (1 - i / max(days - 1, 1)))
        plan = plan_by_day[i]
        a_realiz = 0
        for hu_total, comp_date in hu_info:
            if comp_date is None or comp_date > d:
                a_realiz += hu_total
        if i == 0:
            a_realiz = total_hu_tasks
        result.append([d.strftime("%Y-%m-%d"), meta, plan, a_realiz])
    return result


def _fill_hu_sheet(wb, hu_list, hu_full_names, extras_count=0):
    sheet_name = "xHUs" if "xHUs" in wb.sheetnames else "HUs"
    ws = wb[sheet_name]

    for r in range(1, ws.max_row + 1):
        for c in range(1, ws.max_column + 1):
            ws.cell(r, c).value = None

    _w(ws, 1, 1, "Rótulo (História de Usuário)")
    _w(ws, 1, 2, "Quantidade de Registros")

    rows = sorted(hu_list, key=lambda x: x[0])
    r = 2
    for hu_id, total, _done in rows:
        _w(ws, r, 1, hu_full_names.get(hu_id, hu_id))
        _w(ws, r, 2, total)
        r += 1

    _w(ws, r, 1, "Ausente em HU")
    _w(ws, r, 2, extras_count)


def _fill_areas_sheet(wb, area_rows):
    sheet_name = "xAreas" if "xAreas" in wb.sheetnames else "Areas"
    if sheet_name not in wb.sheetnames:
        return
    ws = wb[sheet_name]

    for r in range(1, ws.max_row + 1):
        for c in range(1, ws.max_column + 1):
            ws.cell(r, c).value = None

    _w(ws, 1, 1, "“Área”")
    _w(ws, 1, 2, "“Qtd”")
    for i, (area, done, pend) in enumerate(area_rows, start=2):
        _w(ws, i, 1, area)
        _w(ws, i, 2, done + pend)


def _fill_hu_in_out_sheet(wb, in_out):
    sheet_name = "xHU_inOut" if "xHU_inOut" in wb.sheetnames else "HUInOut"
    if sheet_name not in wb.sheetnames:
        return
    ws = wb[sheet_name]

    for r in range(1, ws.max_row + 1):
        for c in range(1, ws.max_column + 1):
            ws.cell(r, c).value = None

    _w(ws, 1, 1, "Descrição")
    _w(ws, 1, 2, "Quantidade")
    for i, (label, cnt) in enumerate(in_out, start=2):
        if label.lower().startswith("em hu"):
            label_txt = '"Em HU"'
        elif label.lower().startswith("fora"):
            label_txt = '"Fora de HU"'
        else:
            label_txt = label
        _w(ws, i, 1, label_txt)
        _w(ws, i, 2, cnt)


def _extract_gp_effort_by_hu(wb):
    sheet_name = None
    for cand in ("gp_Plann_Sprint", "Gp_Plann_Sprint"):
        if cand in wb.sheetnames:
            sheet_name = cand
            break
    if sheet_name is None:
        return {}

    ws = wb[sheet_name]
    hu_cols = []
    for c in range(2, ws.max_column + 1):
        v = ws.cell(1, c).value
        if v is None or str(v).strip() == "":
            continue
        m = re.search(r"\b(HU\d+)\b", str(v), flags=re.IGNORECASE)
        if m:
            hu_cols.append((c, m.group(1).upper()))

    out = {hu: {"max": 0.0, "total": 0.0} for _, hu in hu_cols}

    max_row_idx = None
    total_row_idx = None
    for r in range(1, ws.max_row + 1):
        txt = _norm_label_key(ws.cell(r, 1).value)
        if "mensuracao (maior esforco individual)" in txt:
            max_row_idx = r
        if "mensuracao soma total esforco por hu" in txt:
            total_row_idx = r

    for c, hu in hu_cols:
        if max_row_idx and total_row_idx:
            v_max = ws.cell(max_row_idx, c).value
            v_tot = ws.cell(total_row_idx, c).value
            try:
                out[hu]["max"] = float(str(v_max).replace(",", ".")) if v_max not in (None, "") else 0.0
            except Exception:
                out[hu]["max"] = 0.0
            try:
                out[hu]["total"] = float(str(v_tot).replace(",", ".")) if v_tot not in (None, "") else 0.0
            except Exception:
                out[hu]["total"] = 0.0
            continue

        # Fallback: deriva da tabela de perfis (linhas numéricas da planilha)
        vals = []
        for r in range(2, ws.max_row + 1):
            first = ws.cell(r, 1).value
            if first is None and r > 20:
                break
            raw = ws.cell(r, c).value
            try:
                if isinstance(raw, str) and raw.strip().upper() == "N/A":
                    continue
                if raw in (None, ""):
                    continue
                vals.append(float(str(raw).replace(",", ".")))
            except Exception:
                continue
        if vals:
            out[hu]["max"] = max(vals)
            out[hu]["total"] = sum(vals)
    return out


def _fill_esforco_hu_sheet(wb, df_all, hu_full_names):
    sheet_name = "xEsforcoHU" if "xEsforcoHU" in wb.sheetnames else None
    if not sheet_name:
        return
    ws = wb[sheet_name]

    for r in range(1, ws.max_row + 1):
        for c in range(1, ws.max_column + 1):
            ws.cell(r, c).value = None

    effort = _extract_gp_effort_by_hu(wb)
    hu_ids = sorted(set(list(effort.keys()) + df_all[df_all["hu"] != ""]["hu"].unique().tolist()))

    _w(ws, 1, 1, "História de Usuário (HU)")
    _w(ws, 1, 2, "Esforço Max. por Perfil")
    _w(ws, 1, 3, "Esforço Total HU")
    _w(ws, 1, 4, "Total Tarefas")
    _w(ws, 1, 5, "Concluídas")

    r = 2
    for hu in hu_ids:
        grp = df_all[df_all["hu"] == hu]
        _w(ws, r, 1, hu_full_names.get(hu, hu))
        _w(ws, r, 2, effort.get(hu, {}).get("max", 0))
        _w(ws, r, 3, effort.get(hu, {}).get("total", 0))
        _w(ws, r, 4, int(len(grp)))
        _w(ws, r, 5, int(grp["done_kpi"].sum()))
        r += 1

    sem_hu_grp = df_all[df_all["hu"] == ""]
    _w(ws, r, 1, "Geral / Não Previstos / Bugs*")
    _w(ws, r, 2, 0)
    _w(ws, r, 3, 0)
    _w(ws, r, 4, int(len(sem_hu_grp)))
    _w(ws, r, 5, int(sem_hu_grp["done_kpi"].sum()))


def fill_template(template_path, input_path, output_path,
                  author="Gerado automaticamente",
                  dados_manuais_path=None,
                  report_type="equipe",
                  ignore_labels=None,
                  form_data=None):
    """
    Main pipeline:
    1. Load + compute from Planner export
    2. Copy template to output path
    3. Fill all data sheets in the template copy
    4. Save

    report_type:
      "equipe" (padrão) → One Page Report completo com KPIs, burndown, dispersão, etc.
      "gp"              → [Em desenvolvimento] Visão executiva para gerente de projeto.

    Dados automáticos: Roadmap, KPIs, HUs, Burndown, Dispersão, Áreas,
    Colaboradores, Categorias — extraídos do export do Planner.
    Dados manuais preservados no template: Planejamento, Histórico, EsforcoHU.
    """
    if report_type == "gp":
        raise NotImplementedError(
            "O Relatório para GP ainda está em desenvolvimento. "
            "Por enquanto, use o Relatório para Equipe."
        )
    print(f"[1/6] Lendo arquivo base: {input_path}")
    df_raw, plan_name, export_date_str = _load_planner_excel(input_path)

    print(f"[2/6] Processando dados ({len(df_raw)} tarefas)...")
    df_all, sprint_name, sprint_start, sprint_end, export_date, sprint_goal = \
        compute_all(df_raw, plan_name, export_date_str)

    removed_ignored = 0
    df_scope = df_all
    if ignore_labels:
        df_scope, removed_ignored = _apply_ignore_labels(df_all, ignore_labels=ignore_labels)
        if removed_ignored:
            print(f"      [filtro] {removed_ignored} tarefa(s) removida(s) por rótulos ignorados: {ignore_labels}")

    print(f"[3/6] Calculando métricas...")
    # Abas gerais (sem filtro)
    kpis = build_kpis(df_all)
    _enrich_kpis_with_sprint_calendar(kpis, sprint_start, sprint_end, export_date)
    hu_list = build_hu_list(df_all)
    hu_full_names = build_hu_full_names(df_all)
    collab_rows = build_por_colaborador(df_all)
    area_rows = build_areas(df_all)
    cat_rows, bub_rows = build_por_categoria(df_all)
    in_out = build_hu_in_out(df_all)

    # Abas de escopo (com filtro de rótulos ignorados)
    hu_disp, disp_days, hu_matrix, nao_hu_daily = \
        build_dispersao_daily(df_scope, sprint_start, sprint_end)
    rotulos_rows = build_rotulos(df_all)
    resp_rows = build_responsaveis(df_scope)
    hist_31, indicativos = build_histograma(df_scope)
    stats_rows = build_histograma2(df_scope)

    cfd_dates, cfd_todo, cfd_doing, cfd_done = build_cfd(
        df_scope, sprint_start, export_date, sprint_end=sprint_end
    )
    wip_dates, wip_buckets, wip_matrix, wip_total = build_wip(
        df_scope, sprint_start, export_date, sprint_end=sprint_end
    )
    cts_dates, cts_hu_labels, cts_matrix, fora_hu_daily_cts = build_cts(
        df_scope, sprint_start, sprint_end=sprint_end
    )

    # Extrai metadados da tarefa Gestão e Roadmap diretamente do Planner
    gestao_meta = build_gestao_meta(df_all)
    roadmap_items = build_roadmap_from_df(df_all)

    print(f"[4/6] Carregando template: {template_path}")
    wb = load_workbook(template_path)

    # Lê esforço planejado do template (Report + EsforcoHU – mantidos manualmente)
    template_effort = read_template_effort(wb)

    manual_injection = {"roadmap": False, "report_plan_hist": False, "gp_tabs": []}

    # Injeta dados manuais do arquivo adicional (legado + gp_*)
    if dados_manuais_path:
        print(f"      [manual] Injetando dados manuais: {os.path.basename(dados_manuais_path)}")
        manual_injection = inject_dados_manuais_ext(wb, dados_manuais_path)
        if manual_injection.get("gp_tabs"):
            print(f"      [manual] Abas gp_* aplicadas: {manual_injection.get('gp_tabs')}")

    # Injeta dados do formulário web (app.py) nas abas gp_* do template
    form_filled = []
    if form_data:
        form_filled = inject_dados_formulario(wb, form_data)
        if form_filled:
            print(f"      [form] Dados do formulário injetados: {form_filled}")

    # Normaliza percentuais da disponibilidade (form/manual) para fração 0..1.
    if "gp_Disponibilidade" in wb.sheetnames:
        _normalize_gp_disponibilidade_sheet(wb["gp_Disponibilidade"])

    # Storypoints e métricas ponderadas por HU devem refletir a aba gp_Plann_Sprint
    hu_storypoints = _extract_gp_storypoints_by_hu(wb)
    if hu_storypoints:
        _enrich_kpis_with_hu_storypoints(kpis, df_scope, hu_storypoints)

    print(f"[5/6] Preenchendo abas de dados...")
    _form_cab = form_data.get("cabecalhos", {}) if form_data else {}
    _has_form = bool(form_data)
    _fill_kpi_sheet(
        wb, kpis, sprint_name,
        _form_cab.get("sprint_goal") or sprint_goal,
        projeto=_form_cab.get("projeto") or gestao_meta.get("projeto", sprint_name),
        gerente=_form_cab.get("gerente") or gestao_meta.get("gerente", ""),
        linkedin=_form_cab.get("linkedin") or gestao_meta.get("linkedin", ""),
        product_goal=_form_cab.get("product_goal", ""),
        export_date=export_date,
        nome_arquivo=os.path.basename(input_path),
        write_cabecalhos=_has_form,
    )

    # Roadmap: preenchido automaticamente a partir da tarefa 'Roadmap' no Planner
    roadmap_already_manual = bool(
        manual_injection.get("roadmap")
        or ("gp_Roadmap" in manual_injection.get("gp_tabs", []))
        or ("gp_Roadmap" in form_filled)
        or ("roadmap" in (form_data or {}))
    )
    if roadmap_items and not roadmap_already_manual:
        _fill_roadmap_sheet(wb, roadmap_items)
    _fill_hu_sheet(wb, hu_list, hu_full_names, extras_count=kpis["sem_hu"])
    _fill_esforco_hu_sheet(wb, df_all, hu_full_names)
    _fill_burndown_sheet(wb, df_scope, sprint_start, sprint_end, export_date)
    _fill_burndown_hu_sheet(wb, df_scope, sprint_start, sprint_end, export_date)
    _fill_burndown_storypoints_sheet(wb, df_scope, sprint_end, hu_storypoints)
    disp_start = disp_days[0].date() if disp_days else date.today()
    _fill_dispersao_sheet(wb, hu_disp, len(disp_days), hu_matrix, nao_hu_daily,
                          disp_start, hu_full_names)
    _fill_colaborador_sheet(wb, collab_rows)
    _fill_areas_sheet(wb, area_rows)
    _fill_hu_in_out_sheet(wb, in_out)
    _fill_categoria_sheet(wb, cat_rows)
    # Bubbles: usa esforço do template (planejamento) em vez de esforço de checklist
    _fill_categoria_bubbles_sheet(wb, bub_rows, template_effort=template_effort)
    # Fill new sheets
    _fill_rotulos_sheet(wb, rotulos_rows)
    _fill_responsaveis_sheet(wb, resp_rows)
    _fill_histograma_sheet(wb, hist_31, indicativos)
    _fill_histograma2_sheet(wb, stats_rows)
    _fill_cfd_sheet(wb, cfd_dates, cfd_todo, cfd_doing, cfd_done)
    _fill_wip_sheet(wb, wip_dates, wip_buckets, wip_matrix, wip_total)
    _fill_cts_sheet(wb, cts_dates, cts_hu_labels, cts_matrix, fora_hu_daily_cts)
    # Mantém tabelas manuais quando vierem de planilha/formulário.
    if not dados_manuais_path and not form_data:
        _clear_report_planning_tables(wb)
    _clear_report_roadmap_overlay_cells(wb)
    if not dados_manuais_path:
        _update_report_metadata(wb, export_date, author)

    print(f"[6/6] Salvando: {output_path}")
    try:
        wb.calculation.fullCalcOnLoad = True
        wb.calculation.forceFullCalc = True
    except Exception:
        pass
    wb.save(output_path)

    # Pós-processamento ZIP: injeta chartEx e limpa caches de séries dos charts
    print("      Pós-processamento...")
    _postprocess_xlsx(output_path, template_path=template_path)

    print(f"[OK] Dashboard gerado com sucesso!")
    print(f"     Sprint : {sprint_name}")
    print(f"     Total  : {kpis['total']}  |  Concluídas: {kpis['done']}  "
          f"|  Pendentes: {kpis['pending']}")
    print(f"     HUs    : {len(hu_list)}")


def main():
    parser = argparse.ArgumentParser(description="OnePageReport Dashboard Generator v3")
    parser.add_argument("input", nargs="?", help="Arquivo base exportado do Planner (.xlsx)")
    parser.add_argument("output", nargs="?", help="Arquivo de saída (.xlsx)")
    parser.add_argument("--template", default=None,
                        help="Arquivo espelho/template (.xlsx). "
                             "Se não informado, usa template.xlsx na mesma pasta do script.")
    parser.add_argument("--author", default="Gerado automaticamente",
                        help="Nome do autor para o relatório")
    parser.add_argument(
        "--make-clean-template",
        nargs=2,
        metavar=("SOURCE_XLSX", "OUTPUT_XLSX"),
        help="Gera um template limpo a partir de um workbook de referência.",
    )
    args = parser.parse_args()

    if args.make_clean_template:
        src, dst = args.make_clean_template
        if not os.path.exists(src):
            print(f"[ERRO] Arquivo de origem não encontrado: {src}", file=sys.stderr)
            sys.exit(1)
        print(f"[clean-template] origem: {src}")
        print(f"[clean-template] saída : {dst}")
        create_clean_template(src, dst)
        print("[OK] Template limpo gerado com sucesso.")
        return

    if not args.input:
        parser.error("Informe <input.xlsx> ou use --make-clean-template SOURCE OUTPUT")

    input_path  = args.input
    output_path = args.output or os.path.splitext(input_path)[0] + "_Dashboard.xlsx"

    if not os.path.exists(input_path):
        print(f"[ERRO] Arquivo não encontrado: {input_path}", file=sys.stderr)
        sys.exit(1)

    # Resolve template path
    if args.template:
        template_path = args.template
    else:
        # Default: prefer template.next.xlsx (quando existir), fallback template.xlsx
        script_dir = os.path.dirname(os.path.abspath(__file__))
        candidate_next = os.path.join(script_dir, "template.next.xlsx")
        candidate_default = os.path.join(script_dir, "template.xlsx")
        template_path = candidate_next if os.path.exists(candidate_next) else candidate_default

    if not os.path.exists(template_path):
        print(f"[ERRO] Template não encontrado: {template_path}", file=sys.stderr)
        print("       Informe o caminho com --template ou coloque 'template.xlsx' "
              "na mesma pasta do script.", file=sys.stderr)
        sys.exit(1)

    fill_template(template_path, input_path, output_path, author=args.author)



# ═══════════════════════════════════════════════════════════════════════════════
#                    JSON INTERMEDIATE LAYER  (xlsx → JSON → Excel)
# ═══════════════════════════════════════════════════════════════════════════════

def _precompute_burndown(df, sprint_start, sprint_end, export_date):
    dfw = df[~df["is_backlog"]].copy()
    total = len(dfw)
    bd_start, bd_end, days = _resolve_burndown_window(dfw, sprint_start, sprint_end)
    plan_by_day = _build_step_plan(total, days, blocks=5)

    done_dates = sorted(
        d for d in dfw.loc[dfw["done_kpi"] & dfw["date_done"].notna(), "date_done"].tolist()
    )

    result = []
    for i in range(days):
        d = bd_start + timedelta(days=i)
        dt_str = d.strftime("%Y-%m-%d")
        meta = round(total * (1 - i / max(days - 1, 1)))
        plan = plan_by_day[i]
        concluded = bisect_right(done_dates, d)
        rlz = total - concluded
        result.append([dt_str, meta, plan, rlz])
    return result


def _precompute_burndown(df, sprint_start, sprint_end, export_date):
    dfw = df[~df["is_backlog"]].copy()
    bd_start, bd_end, days = _resolve_burndown_window(dfw, sprint_start, sprint_end)

    task_info = []
    event_count_by_index = defaultdict(int)
    original_total = 0

    for idx, row in dfw.iterrows():
        is_unplanned = bool(row.get("is_nao_prev", False))
        entry_index = None
        if is_unplanned:
            entry_date = _row_scope_entry_date(row, default_date=bd_start)
            entry_index = _scope_event_index(entry_date, bd_start, days)
            event_count_by_index[entry_index] += 1
        else:
            original_total += 1

        task_info.append({
            "entry_index": entry_index,
            "done": bool(row.get("done_kpi", False)),
            "date_done": row.get("date_done"),
        })

    result = []
    for i in range(days):
        d = bd_start + timedelta(days=i)
        dt_str = d.strftime("%Y-%m-%d")
        meta_original = _linear_burn_from(original_total, i, 0, days - 1)
        meta = meta_original
        plan = _step_plan_from(original_total, i, 0, days, blocks=5)
        for event_index, count in event_count_by_index.items():
            meta += _linear_burn_from(count, i, event_index, days - 1)
            plan += _step_plan_from(count, i, event_index, days, blocks=5)

        active_total = original_total + sum(count for event_index, count in event_count_by_index.items() if event_index <= i)
        added_today = event_count_by_index.get(i, 0)
        concluded = 0
        for task in task_info:
            entry_index = task["entry_index"]
            if entry_index is not None and i < entry_index:
                continue
            d_done = task["date_done"]
            if task["done"] and _is_valid_date(d_done) and d_done <= d:
                concluded += 1

        remaining = max(active_total - concluded, 0)
        result.append([
            dt_str,
            round(meta),
            round(plan),
            remaining,
            active_total,
            round(meta_original),
            added_today,
            concluded,
        ])
    return result


def _precompute_burndown_hu(df, sprint_start, sprint_end, export_date):
    dfw = df[df["hu"] != ""].copy()
    bd_start, bd_end, days = _resolve_burndown_window(dfw, sprint_start, sprint_end)

    hu_info = []
    for _, grp in dfw.groupby("hu"):
        hu_total = len(grp)
        if bool(grp["done_kpi"].all()) and grp["date_done"].notna().all():
            completion_date = max(grp["date_done"].tolist())
        else:
            completion_date = None
        hu_info.append((hu_total, completion_date))

    total_hu_tasks = sum(t for t, _ in hu_info)
    plan_by_day = _build_step_plan(total_hu_tasks, days, blocks=5)

    result = []
    for i in range(days):
        d = bd_start + timedelta(days=i)
        dt_str = d.strftime("%Y-%m-%d")
        meta = round(total_hu_tasks * (1 - i / max(days - 1, 1)))
        plan = plan_by_day[i]
        a_realiz = 0
        for hu_total, comp_date in hu_info:
            if comp_date is None or comp_date > d:
                a_realiz += hu_total
        if i == 0:
            a_realiz = total_hu_tasks
        result.append([dt_str, meta, plan, a_realiz])
    return result


def _precompute_burndown_hu(df, sprint_start, sprint_end, export_date, hu_scope_events=None):
    dfw = df[df["hu"] != ""].copy()
    bd_start, bd_end, days = _resolve_burndown_window(dfw, sprint_start, sprint_end)

    hu_scope_events = hu_scope_events or {}
    hu_info = []
    hu_weights = {}
    event_weight_by_index = defaultdict(float)
    original_weight = 0.0

    for hu, grp in dfw.groupby("hu"):
        hu = str(hu).upper()
        hu_total = len(grp)
        hu_weights[hu] = hu_total
        if bool(grp["done_kpi"].all()) and grp["date_done"].notna().all():
            completion_date = max(grp["date_done"].tolist())
        else:
            completion_date = None

        event = hu_scope_events.get(hu)
        event_date = event.get("date") if event else None
        if event and _is_valid_date(event_date) and event_date > bd_start:
            event_index = _scope_event_index(event_date, bd_start, days)
            event_weight_by_index[event_index] += hu_total
        else:
            event_index = None
            original_weight += hu_total
        hu_info.append((hu_total, completion_date, event_index))

    result = []
    for i in range(days):
        d = bd_start + timedelta(days=i)
        dt_str = d.strftime("%Y-%m-%d")
        meta_original = _linear_burn_from(original_weight, i, 0, days - 1)
        meta = meta_original
        plan = _step_plan_from(original_weight, i, 0, days, blocks=5)
        for event_index, event_weight in event_weight_by_index.items():
            meta += _linear_burn_from(event_weight, i, event_index, days - 1)
            plan += _step_plan_from(event_weight, i, event_index, days, blocks=5)
        scope_total = original_weight + sum(weight for event_index, weight in event_weight_by_index.items() if event_index <= i)
        added_today = event_weight_by_index.get(i, 0.0)

        a_realiz = 0
        for hu_total, comp_date, event_index in hu_info:
            if event_index is not None and i < event_index:
                continue
            if comp_date is None or comp_date > d:
                a_realiz += hu_total

        result.append([
            dt_str,
            round(meta),
            round(plan),
            a_realiz,
            round(scope_total),
            round(meta_original),
            round(added_today),
        ])
    return result


def _precompute_nao_prev_task_burn(df, sprint_start, sprint_end, export_date, require_hu=False):
    df_window = df[~df["is_backlog"]].copy()
    dfw = df_window[df_window["is_nao_prev"]].copy()
    if require_hu:
        dfw = dfw[dfw["hu"] != ""].copy()
    if dfw.empty:
        return [], []

    bd_start, bd_end, days = _resolve_burndown_window(df_window, sprint_start, sprint_end)

    task_info = []
    event_count_by_index = defaultdict(int)
    event_count_by_label_index = defaultdict(int)

    for _, row in dfw.iterrows():
        entry_date = _row_scope_entry_date(row, default_date=bd_start)
        entry_index = _scope_event_index(entry_date, bd_start, days)
        hu = str(row.get("hu") or "").upper()
        label = hu or "Fora de HU"
        event_count_by_index[entry_index] += 1
        event_count_by_label_index[(entry_index, label)] += 1
        task_info.append({
            "entry_index": entry_index,
            "done": bool(row.get("done_kpi", False)),
            "date_done": row.get("date_done"),
        })

    result = []
    for i in range(days):
        d = bd_start + timedelta(days=i)
        dt_str = d.strftime("%Y-%m-%d")
        meta = 0.0
        plan = 0.0
        for event_index, count in event_count_by_index.items():
            meta += _linear_burn_from(count, i, event_index, days - 1)
            plan += _step_plan_from(count, i, event_index, days, blocks=5)

        scope_total = sum(count for event_index, count in event_count_by_index.items() if event_index <= i)
        added_today = event_count_by_index.get(i, 0)
        concluded = 0
        for task in task_info:
            if i < task["entry_index"]:
                continue
            d_done = task["date_done"]
            if task["done"] and _is_valid_date(d_done) and d_done <= d:
                concluded += 1

        remaining = max(scope_total - concluded, 0)
        result.append([
            dt_str,
            round(meta),
            round(plan),
            remaining,
            scope_total,
            0,
            added_today,
            concluded,
        ])

    events = []
    for (event_index, label), count in sorted(event_count_by_label_index.items()):
        hu = "" if label == "Fora de HU" else label
        events.append({
            "type": "add",
            "date": (bd_start + timedelta(days=event_index)).strftime("%Y-%m-%d"),
            "hu": hu,
            "label": label,
            "count": int(count),
            "weight": int(count),
        })

    return result, events


def _precompute_nao_prev_hu_burn(df, sprint_start, sprint_end, export_date):
    return _precompute_nao_prev_task_burn(
        df, sprint_start, sprint_end, export_date, require_hu=True
    )


def _fill_burndown_from_rows(wb, rows, sheet_key="tarefas"):
    """
    Preenche uma aba de burndown a partir de linhas pré-computadas.
    sheet_key: "tarefas" ou "hu"
    rows: lista de [date_str, meta, plan, a_realizar] com tamanho variavel.
    """
    if sheet_key == "tarefas":
        sheet_name = "xBurndownTarefas" if "xBurndownTarefas" in wb.sheetnames else "BurndownTarefas"
    else:
        sheet_name = "xBurndownHU" if "xBurndownHU" in wb.sheetnames else "BurndownHU"

    if sheet_name not in wb.sheetnames:
        return
    ws = wb[sheet_name]

    for i, row in enumerate(rows):
        r = i + 2
        dt_str, meta, plan, rlz = row[:4]
        if dt_str:
            dt = datetime.strptime(dt_str, "%Y-%m-%d")
            _w(ws, r, 1, dt)
            _w(ws, r, 2, meta)
            _w(ws, r, 3, plan)
            _w(ws, r, 4, rlz)
        else:
            _w(ws, r, 1, None)
            _w(ws, r, 2, None)
            _w(ws, r, 3, None)
            _w(ws, r, 4, None)


def _collect_warnings(df, kpis, hu_list, sprint_start, sprint_end, export_date,
                       roadmap_items):
    """
    Analisa a qualidade dos dados e retorna lista de avisos para o usuario.
    Cada item: {"nivel": "erro"|"aviso"|"info", "msg": "..."}.
    Niveis:
      "erro"  - dados criticos ausentes, o relatorio pode estar incompleto.
      "aviso" - situacao preocupante, verificar antes de usar o relatorio.
      "info"  - observacao informativa, nao critica.
    """
    from datetime import date as _date_cls
    warns = []

    total = kpis.get("total", 0)

    # --- Sem tarefas ---
    if total == 0:
        warns.append({"nivel": "erro",
                      "msg": "Nenhuma tarefa encontrada no arquivo. "
                             "Verifique se e um export valido do Planner."})
        return warns  # sem dados uteis para analise adicional

    # --- Sprint sem datas ---
    if sprint_start is None:
        warns.append({"nivel": "aviso",
                      "msg": "Data de inicio do sprint nao encontrada. "
                             "O burndown de tarefas pode ficar vazio."})
    if sprint_end is None:
        warns.append({"nivel": "aviso",
                      "msg": "Data de fim do sprint nao encontrada. "
                             "Burndown e KPIs de prazo podem ficar vazios."})

    # --- Export muito antigo ---
    if export_date:
        today = _date_cls.today()
        days_old = (today - export_date).days
        if days_old > 14:
            warns.append({"nivel": "info",
                          "msg": f"Export com {days_old} dias de antecedencia. "
                                  "Considere usar um export mais recente para "
                                  "resultados precisos."})

    # --- Sprint encerrada ha muito tempo ---
    if sprint_end and export_date:
        delta = (export_date - sprint_end).days
        if delta > 30:
            warns.append({"nivel": "info",
                          "msg": f"Sprint encerrada ha {delta} dias. "
                                  "Os dados podem estar desatualizados."})

    # --- Poucas tarefas ---
    if 0 < total < 5:
        warns.append({"nivel": "aviso",
                      "msg": f"Apenas {total} tarefa(s) encontrada(s). "
                             "O relatorio pode estar incompleto."})

    # --- Nenhuma HU cadastrada ---
    if not hu_list:
        warns.append({"nivel": "aviso",
                      "msg": "Nenhuma Historia de Usuario (HU) identificada. "
                             "Verifique se as tarefas estao vinculadas a HUs."})
    else:
        # --- Alta proporcao de tarefas sem HU ---
        sem_hu = kpis.get("sem_hu", 0)
        if total > 0 and sem_hu / total > 0.5:
            pct = int(sem_hu / total * 100)
            warns.append({"nivel": "aviso",
                          "msg": f"{pct}% das tarefas ({sem_hu}/{total}) "
                                  "nao estao vinculadas a nenhuma HU."})

    # --- Muitas tarefas sem responsavel ---
    try:
        import pandas as _pd
        sem_resp = int((df["assignee"].fillna("").astype(str).str.strip() == "").sum())
        if total > 0 and sem_resp / total > 0.3:
            pct = int(sem_resp / total * 100)
            warns.append({"nivel": "info",
                          "msg": f"{pct}% das tarefas ({sem_resp}/{total}) "
                                  "nao possuem responsavel atribuido."})
    except Exception:
        pass

    # --- Roadmap vazio ---
    if not roadmap_items:
        warns.append({"nivel": "info",
                      "msg": "Nenhum item de Roadmap encontrado no arquivo. "
                             "O grafico de Roadmap ficara vazio."})

    # --- Sprint encerrada com baixa conclusao ---
    done = kpis.get("done", 0)
    if sprint_end and export_date and sprint_end <= export_date:
        if total > 0 and done / total < 0.5:
            pct = int(done / total * 100)
            warns.append({"nivel": "aviso",
                          "msg": f"Sprint encerrada com apenas {pct}% de conclusao "
                                  f"({done}/{total} tarefas)."})

    return warns


def compute_json(input_path, ignore_labels=None, planner_format="legacy"):
    """
    Pipeline parcial: le o export do Planner e retorna um dict JSON-serializavel
    com todos os dados computados (KPIs, burndown, CFD, WIP, CTS, etc.).

    Uso tipico:
        data = compute_json("planner_export.xlsx")
        import json
        with open("dados.json", "w") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    """
    def _d(v):
        if v is None:
            return None
        if hasattr(v, "strftime"):
            return v.strftime("%Y-%m-%d")
        return str(v)

    df_raw, plan_name, export_date_str = _load_planner_excel(input_path, planner_format=planner_format)
    detected_planner_format = df_raw.attrs.get("planner_format", planner_format)
    df_all, sprint_name, sprint_start, sprint_end, export_date, sprint_goal = \
        compute_all(df_raw, plan_name, export_date_str)

    df_scope = df_all
    if ignore_labels:
        df_scope, _ = _apply_ignore_labels(df_all, ignore_labels=ignore_labels)

    kpis = build_kpis(df_all)
    _enrich_kpis_with_sprint_calendar(kpis, sprint_start, sprint_end, export_date)
    hu_list = build_hu_list(df_all)
    hu_full_names = build_hu_full_names(df_all)
    hu_storypoints_labels, total_sp_labels = build_hu_storypoints_from_labels(df_all)
    hu_scope_events = build_hu_scope_events_from_labels(
        df_all,
        sprint_start=sprint_start,
        sprint_end=sprint_end,
        export_date=export_date,
        hu_storypoints=hu_storypoints_labels,
    )
    if hu_storypoints_labels:
        _enrich_kpis_with_hu_storypoints(kpis, df_scope, hu_storypoints_labels)
    flow_metrics = build_flow_metrics(df_scope, sprint_start, sprint_end, kpis)
    scope_quality_metrics = build_scope_quality_metrics(df_scope, hu_storypoints_labels, kpis)
    time_metrics = build_time_metrics(
        df_scope, sprint_start, sprint_end, export_date, hu_storypoints_labels, scope_quality_metrics
    )
    collab_rows = build_por_colaborador(df_all)
    area_rows = build_areas(df_all)
    cat_rows, bub_rows = build_por_categoria(df_all)
    in_out = build_hu_in_out(df_all)
    hu_disp, disp_days, hu_matrix, nao_hu_daily = build_dispersao_daily(df_scope, sprint_start, sprint_end)
    rotulos_rows = build_rotulos(df_all)
    resp_rows = build_responsaveis(df_scope)
    hist_31, indicativos = build_histograma(df_scope)
    stats_rows = build_histograma2(df_scope)
    gestao_meta = build_gestao_meta(df_all)
    roadmap_items = build_roadmap_from_df(df_all)

    # Coleta warnings de qualidade dos dados
    warnings = _collect_warnings(
        df_all, kpis, hu_list, sprint_start, sprint_end, export_date, roadmap_items
    )

    cfd_dates, cfd_todo, cfd_doing, cfd_done = build_cfd(
        df_scope, sprint_start, export_date, sprint_end=sprint_end
    )
    wip_dates, wip_buckets, wip_matrix, _wip_total = build_wip(
        df_scope, sprint_start, export_date, sprint_end=sprint_end
    )
    cts_dates, cts_hu_labels, cts_matrix, fora_hu_daily_cts = build_cts(
        df_scope, sprint_start, sprint_end=sprint_end
    )

    burndown_rows = _precompute_burndown(df_scope, sprint_start, sprint_end, export_date)
    burndown_hu_rows = _precompute_burndown_hu(df_scope, sprint_start, sprint_end, export_date, hu_scope_events)
    burndown_sp_rows = _precompute_burndown_sp(
        df_scope, sprint_start, sprint_end, export_date, hu_storypoints_labels, hu_scope_events
    )
    nao_prev_burn_rows, nao_prev_scope_events = _precompute_nao_prev_task_burn(
        df_scope, sprint_start, sprint_end, export_date
    )
    nao_prev_hu_burn_rows, nao_prev_hu_scope_events = _precompute_nao_prev_hu_burn(
        df_scope, sprint_start, sprint_end, export_date
    )
    task_scope_events = _serialize_task_scope_events_from_burndown(burndown_rows)
    hu_scope_weights = {
        str(hu).upper(): int(len(grp))
        for hu, grp in df_scope[df_scope["hu"] != ""].groupby("hu")
    }
    serialized_scope_events = _serialize_scope_events(hu_scope_events, hu_scope_weights)
    bd_start = disp_days[0].date() if disp_days else date.today()

    # Garante tipos JSON-serializaveis em kpis
    kpis_json = {}
    for k, v in kpis.items():
        if v is None:
            kpis_json[k] = None
        elif isinstance(v, float):
            kpis_json[k] = round(v, 6)
        elif hasattr(v, "__int__"):
            kpis_json[k] = int(v)
        else:
            kpis_json[k] = v

    return {
        "meta": {
            "sprint_name":  sprint_name,
            "sprint_goal":  sprint_goal,
            "sprint_start": _d(sprint_start),
            "sprint_end":   _d(sprint_end),
            "export_date":  _d(export_date),
            "nome_arquivo": os.path.basename(input_path),
            "planner_format": detected_planner_format,
            "projeto":      gestao_meta.get("projeto", sprint_name),
            "gerente":      gestao_meta.get("gerente", ""),
            "linkedin":     gestao_meta.get("linkedin", ""),
        },
        "kpis":        kpis_json,
        "flow_metrics": flow_metrics,
        "scope_quality_metrics": scope_quality_metrics,
        "time_metrics": time_metrics,
        "hu_list":     [[h, t, d] for h, t, d in hu_list],
        "hu_full_names": hu_full_names,
        "collab_rows": [[n, d, p] for n, d, p in collab_rows],
        "area_rows":   [[a, d, p] for a, d, p in area_rows],
        "cat_rows":    [[c, d, p] for c, d, p in cat_rows],
        "bub_rows":    [[c, d, t, e] for c, d, t, e in bub_rows],
        "in_out":      [[label, cnt] for label, cnt in in_out],
        "rotulos_rows": [[disp, dn, pn, lt, ct] for disp, dn, pn, lt, ct in rotulos_rows],
        "resp_rows":   [[disp, dn, pn, lt, ct] for disp, dn, pn, lt, ct in resp_rows],
        "hist_31":     hist_31,
        "indicativos": indicativos,
        "stats_rows":  [[desc, val] for desc, val in stats_rows],
        "cfd": {
            "dates": [_d(dt) for dt in cfd_dates],
            "todo":  cfd_todo,
            "doing": cfd_doing,
            "done":  cfd_done,
        },
        "wip": {
            "dates":   [_d(dt) for dt in wip_dates],
            "buckets": wip_buckets,
            "matrix":  {bkt: wip_matrix[bkt] for bkt in wip_buckets},
            "x_total": _wip_total,
        },
        "cts": {
            "dates":     [_d(dt) for dt in cts_dates],
            "hu_labels": list(cts_hu_labels),
            "matrix":    cts_matrix,
            "fora_hu":   fora_hu_daily_cts,
        },
        "burndown": {
            "rows": burndown_rows,
            "scope_events": task_scope_events,
        },
        "burndown_hu": {
            "rows": burndown_hu_rows,
            "scope_events": serialized_scope_events,
        },
        "burndown_sp": {
            "rows":     burndown_sp_rows,
            "total_sp": total_sp_labels,
            "hu_sp":    hu_storypoints_labels,
            "scope_events": serialized_scope_events,
        },
        "burndown_nao_prev": {
            "rows": nao_prev_burn_rows,
            "scope_events": nao_prev_scope_events,
        },
        "burndown_nao_prev_hu": {
            "rows": nao_prev_hu_burn_rows,
            "scope_events": nao_prev_hu_scope_events,
        },
        "dispersao": {
            "hu_list":      hu_disp,
            "days":         [_d(dt) for dt in disp_days],
            "days_count":   len(disp_days),
            "hu_matrix":    {hu: row for hu, row in zip(hu_disp, hu_matrix)},
            "nao_hu_daily": nao_hu_daily,
            "bd_start":     _d(bd_start),
        },
        "roadmap_items": [[t, p] for t, p in roadmap_items],
        "task_rows": build_task_rows_for_custom_filters(df_scope),
        "warnings":      warnings,
    }


def fill_template_from_json(template_path, data, output_path,
                             author="Gerado automaticamente"):
    """
    Preenche o template Excel a partir de um dict JSON (produzido por compute_json).
    Esta e a etapa 2 do pipeline xlsx->JSON->Excel.

    Util quando o JSON ja foi pre-computado (ex: enviado via browser) e
    so e necessario gerar o arquivo final.
    """
    meta = data.get("meta", {})

    def _parse_date(s):
        if not s:
            return date.today()
        try:
            return datetime.strptime(s, "%Y-%m-%d").date()
        except Exception:
            return date.today()

    export_date = _parse_date(meta.get("export_date"))
    sprint_name = meta.get("sprint_name", "Sprint")
    sprint_goal = meta.get("sprint_goal", "")

    wb = load_workbook(template_path)
    template_effort = read_template_effort(wb)
    hu_full_names = data.get("hu_full_names", {})

    # KPIs
    _fill_kpi_sheet(
        wb, data["kpis"], sprint_name, sprint_goal,
        projeto=meta.get("projeto", sprint_name),
        gerente=meta.get("gerente", ""),
        linkedin=meta.get("linkedin", ""),
        export_date=export_date,
        nome_arquivo=meta.get("nome_arquivo", ""),
    )

    # Roadmap
    roadmap_items = [(t, p) for t, p in data.get("roadmap_items", [])]
    if roadmap_items:
        _fill_roadmap_sheet(wb, roadmap_items)

    # HUs
    hu_list = [(h, t, d) for h, t, d in data.get("hu_list", [])]
    _fill_hu_sheet(wb, hu_list, hu_full_names,
                   extras_count=data["kpis"].get("sem_hu", 0))

    # Burndown
    _fill_burndown_from_rows(wb, data["burndown"]["rows"], sheet_key="tarefas")
    _fill_burndown_from_rows(wb, data["burndown_hu"]["rows"], sheet_key="hu")

    # Dispersao
    disp = data.get("dispersao", {})
    bd_start_str = disp.get("bd_start")
    if bd_start_str:
        bd_start = _parse_date(bd_start_str)
        raw_days = disp.get("days", 31)
        if isinstance(raw_days, list):
            days_count = len(raw_days)
        else:
            try:
                days_count = int(raw_days)
            except Exception:
                try:
                    days_count = int(disp.get("days_count", 31))
                except Exception:
                    days_count = 31

        hu_matrix_payload = disp.get("hu_matrix", [])
        if isinstance(hu_matrix_payload, dict):
            hu_keys = disp.get("hu_list", [])
            hu_matrix_rows = [hu_matrix_payload.get(h, [0.0] * days_count) for h in hu_keys]
        else:
            hu_matrix_rows = hu_matrix_payload

        _fill_dispersao_sheet(
            wb,
            disp.get("hu_list", []),
            days_count,
            hu_matrix_rows,
            disp.get("nao_hu_daily", []),
            bd_start,
            hu_full_names,
        )

    # Colaboradores, Areas, Categorias
    _fill_colaborador_sheet(wb, [(n, d, p) for n, d, p in data.get("collab_rows", [])])
    _fill_areas_sheet(wb,   [(a, d, p) for a, d, p in data.get("area_rows", [])])
    _fill_hu_in_out_sheet(wb, [(lbl, cnt) for lbl, cnt in data.get("in_out", [])])
    _fill_categoria_sheet(wb, [(c, d, p) for c, d, p in data.get("cat_rows", [])])
    _fill_categoria_bubbles_sheet(
        wb,
        [(c, d, t, e) for c, d, t, e in data.get("bub_rows", [])],
        template_effort=template_effort,
    )

    # Rotulos e Responsaveis
    _fill_rotulos_sheet(
        wb, [(d, dn, pn, lt, ct) for d, dn, pn, lt, ct in data.get("rotulos_rows", [])]
    )
    _fill_responsaveis_sheet(
        wb, [(d, dn, pn, lt, ct) for d, dn, pn, lt, ct in data.get("resp_rows", [])]
    )

    # Histograma
    _fill_histograma_sheet(wb, data.get("hist_31", [0]*31), data.get("indicativos", [None]*31))
    _fill_histograma2_sheet(wb, [(d, v) for d, v in data.get("stats_rows", [])])

    # CFD / WIP / CTS
    cfd = data.get("cfd", {})
    if cfd.get("dates"):
        cfd_dates = [datetime.strptime(s, "%Y-%m-%d") for s in cfd["dates"]]
        _fill_cfd_sheet(wb, cfd_dates, cfd["todo"], cfd["doing"], cfd["done"])

    wip = data.get("wip", {})
    if wip.get("dates"):
        wip_dates = [datetime.strptime(s, "%Y-%m-%d") for s in wip["dates"]]
        _fill_wip_sheet(
            wb, wip_dates, wip["buckets"], wip["matrix"], wip.get("x_total")
        )

    cts = data.get("cts", {})
    if cts.get("dates"):
        cts_dates = [datetime.strptime(s, "%Y-%m-%d") for s in cts["dates"]]
        _fill_cts_sheet(wb, cts_dates, cts["hu_labels"], cts["matrix"], cts["fora_hu"])

    # Report manual structure
    _clear_report_planning_tables(wb)
    _clear_report_roadmap_overlay_cells(wb)
    _update_report_metadata(wb, export_date, author)

    try:
        wb.calculation.fullCalcOnLoad = True
        wb.calculation.forceFullCalc = True
    except Exception:
        pass
    wb.save(output_path)

    print("      Pos-processamento...")
    _postprocess_xlsx(output_path, template_path=template_path)
    print("[OK] Dashboard gerado a partir de JSON!")



if __name__ == "__main__":
    main()
