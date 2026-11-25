# Contratos do processamento do Planner

Este documento registra as fronteiras estáveis do pipeline de importação. Alterações nesses contratos devem atualizar os testes de formato e a documentação da API.

## Entrada

- `load_base(path, planner_format)` recebe um arquivo `.xlsx` local.
- `planner_format` aceita `legacy`, `old`, `antigo`, `teams_new`, `new` e `novo`.
- O loader retorna `(dataframe, plan_name, export_date)`.
- O `DataFrame` retornado possui `attrs["planner_format"]` com `legacy` ou `teams_new`.
- Arquivos incompatíveis devem gerar `ValueError` com mensagem segura para o usuário.

## Normalização e métricas

- `compute_all(dataframe, plan_name, export_date)` normaliza colunas e datas e prepara as linhas de tarefa.
- `compute_json(path, ignore_labels=None, planner_format="legacy", committed_hus=None)` retorna um dicionário JSON-serializável.
- `kpis.storypoints` soma os SP das HUs do board. `scope_quality_metrics.committed_sp` soma os SP das HUs selecionadas e fica nulo quando não há seleção.
- `meta.committed_hus` registra a seleção. Com a seleção, o burndown de SP dá baixa na HU na última data de conclusão das suas tarefas, desde que todas estejam concluídas.
- O payload contém `meta`, `kpis`, linhas agregadas para os gráficos, `warnings` e, quando informado, `roadmap_items`.
- Datas são serializadas como texto ISO ou formato de apresentação definido pelo payload existente.
- Métricas que não podem ser calculadas devem retornar valor vazio/zero conforme o contrato existente, sem interromper todo o upload.

## Persistência do upload

- O endpoint autenticado `POST /upload` aceita multipart com `arquivo` `.xlsx`.
- Com `preview_commitment=1`, o upload retorna `commitment_options` com `id`, `name` e `sp` das HUs pontuadas e não cria um relatório. O envio final pode incluir `committed_hus`, uma lista de códigos separados por vírgula. Códigos desconhecidos ou sem estimativa retornam HTTP 400.
- `team_id` e `roadmap_id` são sempre validados no escopo do usuário antes de serem associados.
- O relatório persistido guarda o payload completo em `reports.payload_json`.
- Falhas de validação retornam HTTP 400; recurso inexistente retorna HTTP 404; falha inesperada retorna HTTP 500 sem detalhes internos.

## Compatibilidade

- `generate_dashboard.load_base` permanece disponível como alias para consumidores existentes.
- O novo leitor vive em `reportchart_web/planner/excel_loader.py`.
- Testes de formatos devem cobrir Legacy, Teams, formato incompatível e resolução de referências auxiliares.
