"""Readers for Microsoft Planner Excel exports."""

from __future__ import annotations

import pandas as pd

from reportchart_web.planner.text import normalize_text_key as _norm_text_key, strip_value as _strip


def _load_legacy(path):
    workbook = pd.ExcelFile(path)
    sheet = workbook.sheet_names[0]
    dataframe = workbook.parse(sheet, dtype=str)
    dataframe.columns = [column.strip() for column in dataframe.columns]
    plan_name = ""
    export_date = ""
    if "Nome do plano" in workbook.sheet_names:
        try:
            plan_sheet = workbook.parse("Nome do plano", dtype=str)
            if len(plan_sheet.columns) >= 2:
                plan_name = str(plan_sheet.columns[1]).strip()
            exported = plan_sheet.iloc[:, 0].astype(str).str.lower().str.contains("exporta", na=False)
            if exported.any():
                export_date = str(plan_sheet.loc[exported].iloc[0, 1]).strip()
        except Exception:
            pass
    workbook.close()
    return dataframe, plan_name, export_date


def _clean_columns(dataframe):
    dataframe.columns = [_strip(column) for column in dataframe.columns]
    return dataframe


def _sheet_by_name(workbook, *names):
    wanted = {_norm_text_key(name) for name in names}
    for sheet_name in workbook.sheet_names:
        if _norm_text_key(sheet_name) in wanted:
            return sheet_name
    return None


def _looks_like_legacy(dataframe):
    columns = {_norm_text_key(column) for column in dataframe.columns}
    has_task = bool({"nome da tarefa", "task name"} & columns)
    has_bucket = bool({"nome do bucket", "bucket name"} & columns)
    has_progress = bool({"progresso", "percent complete"} & columns)
    has_labels = bool({"rotulos", "labels"} & columns)
    return has_task and has_bucket and (has_progress or has_labels)


def _load_legacy_tagged(path):
    dataframe, plan_name, export_date = _load_legacy(path)
    dataframe.attrs["planner_format"] = "legacy"
    return dataframe, plan_name, export_date


def _teams_plan_meta(workbook):
    plan_name = ""
    export_date = ""
    sheet_name = _sheet_by_name(workbook, "Plano")
    if not sheet_name:
        return plan_name, export_date
    try:
        plan_sheet = _clean_columns(workbook.parse(sheet_name, dtype=str))
        if plan_sheet.empty:
            return plan_name, export_date
        columns = {_norm_text_key(column): column for column in plan_sheet.columns}
        plan_column = columns.get("nome do plano")
        export_column = columns.get("data da exportacao")
        if plan_column:
            plan_name = _strip(plan_sheet.loc[0, plan_column])
        if export_column:
            export_date = _strip(plan_sheet.loc[0, export_column])
    except Exception:
        pass
    return plan_name, export_date


def _resolve_references(dataframe, workbook):
    if "Categoria" in dataframe.columns:
        bucket_sheet = _sheet_by_name(workbook, "Buckets")
        if bucket_sheet:
            buckets = _clean_columns(workbook.parse(bucket_sheet, dtype=str))
            if {"ID de Bucket", "Nome do Bucket"}.issubset(set(buckets.columns)):
                bucket_map = dict(zip(
                    buckets["ID de Bucket"].fillna("").astype(str),
                    buckets["Nome do Bucket"].fillna("").astype(str),
                ))
                dataframe["Categoria"] = dataframe["Categoria"].map(
                    lambda value: bucket_map.get(_strip(value), value)
                )

    user_sheet = _sheet_by_name(workbook, "Usuarios", "Usuários")
    if user_sheet:
        users = _clean_columns(workbook.parse(user_sheet, dtype=str))
        if {"ID do Usuário", "Nome do usuário"}.issubset(set(users.columns)):
            user_map = dict(zip(
                users["ID do Usuário"].fillna("").astype(str),
                users["Nome do usuário"].fillna("").astype(str),
            ))
            for column in ("Atribuído a", "Criado por", "Concluída por"):
                if column in dataframe.columns:
                    dataframe[column] = dataframe[column].map(
                        lambda value: user_map.get(_strip(value), value)
                    )
    return dataframe


def load_base(path, planner_format="legacy"):
    """Load an export and return tasks, plan name and export date."""
    planner_format = (planner_format or "legacy").strip().lower()
    workbook = pd.ExcelFile(path)

    if planner_format in {"legacy", "old", "antigo"}:
        sheet = workbook.sheet_names[0]
        dataframe = _clean_columns(workbook.parse(sheet, dtype=str))
        columns = {_norm_text_key(column) for column in dataframe.columns}
        if {"id do plano", "nome do plano"}.issubset(columns):
            workbook.close()
            raise ValueError(
                "Este arquivo parece estar no formato novo do Teams. "
                "Selecione o formato novo antes de enviar."
            )
        workbook.close()
        return _load_legacy_tagged(path)

    if planner_format in {"teams_new", "new", "novo"}:
        sheet = _sheet_by_name(workbook, "Dados Consolidados")
        resolve_references = False
        if not sheet:
            sheet = _sheet_by_name(workbook, "Tarefas")
            resolve_references = True
        if not sheet:
            first_sheet = workbook.sheet_names[0] if workbook.sheet_names else None
            if first_sheet:
                first_dataframe = _clean_columns(workbook.parse(first_sheet, dtype=str))
                if _looks_like_legacy(first_dataframe):
                    workbook.close()
                    return _load_legacy_tagged(path)
            workbook.close()
            raise ValueError(
                "Formato novo do Teams invalido: nao encontrei a aba "
                "'Dados Consolidados' ou 'Tarefas'."
            )
        dataframe = _clean_columns(workbook.parse(sheet, dtype=str))
        if resolve_references and _looks_like_legacy(dataframe):
            workbook.close()
            return _load_legacy_tagged(path)
        if resolve_references:
            dataframe = _resolve_references(dataframe, workbook)
        plan_name, export_date = _teams_plan_meta(workbook)
        workbook.close()
        dataframe.attrs["planner_format"] = "teams_new"
        return dataframe, plan_name, export_date

    workbook.close()
    raise ValueError("Formato de Excel nao reconhecido.")
