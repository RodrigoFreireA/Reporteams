"""External and prompt concerns for dashboard summaries."""

from __future__ import annotations

import json
import urllib.request


def build_llm_summary_prompt(facts: dict) -> str:
    scope = facts.get("scope") or {}
    if scope.get("kind") == "section":
        return (
            "Voce e um analista executivo de projetos agil. "
            "Responda em portugues do Brasil, com no maximo 6 bullets curtos. "
            "Compare a secao atual com o panorama geral da sprint. "
            "Use apenas os dados fornecidos, sem inventar metricas. "
            "Se houver filtro ativo, respeite o recorte informado.\n\n"
            "FATOS DA SECAO:\n"
            f"{json.dumps(facts, ensure_ascii=False, indent=2)}"
        )
    return (
        "Você é um analista executivo de projetos ágil. "
        "Responda em português do Brasil, com no máximo 7 bullets curtos. "
        "Use apenas os dados fornecidos, sem inventar métricas. "
        "Foque em panorama, gargalos, riscos e próximos passos. "
        "Se algum dado estiver ausente, ignore esse ponto.\n\n"
        "FATOS DO DASHBOARD:\n"
        f"{json.dumps(facts, ensure_ascii=False, indent=2)}"
    )


def generate_ollama_summary(facts: dict, *, model: str, url: str, timeout: float) -> tuple[str, str]:
    payload = json.dumps(
        {
            "model": model,
            "prompt": build_llm_summary_prompt(facts),
            "stream": False,
            "options": {"temperature": 0.2, "num_predict": 260},
        },
        ensure_ascii=False,
    ).encode("utf-8")
    request_obj = urllib.request.Request(
        url=f"{url}/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request_obj, timeout=timeout) as response:  # nosec B310
        body = json.loads(response.read().decode("utf-8"))
    text = str(body.get("response") or "").strip()
    if not text:
        raise RuntimeError("O provedor de IA retornou um resumo vazio.")
    return text, model
