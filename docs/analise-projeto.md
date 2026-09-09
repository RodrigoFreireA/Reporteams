# Memoria Tecnica e Regras de Negocio - ReportChart Web

Ultima atualizacao: 2026-05-25
Origem: leitura de codigo local + historico git
Objetivo: servir como memoria tecnica do projeto, com foco em regra de negocio e comportamento real em runtime.

## 0) Escopo e privacidade deste documento

- Este arquivo fica em `docs/`.
- O deploy em container nao inclui `docs/` porque `.dockerignore` contem `docs/`.
- O app Flask nao expoe rota para arquivos de docs.

Resumo pratico: este MD fica no repositorio de desenvolvimento, mas nao entra na imagem Docker publicada.

## 1) Stack e arquitetura atual

- Backend: Flask + Flask-SQLAlchemy (arquivo monolitico `app.py`)
- Processamento de dados Planner: pandas + openpyxl (`generate_dashboard.py`)
- Frontend: HTML/CSS/JS puro em `index.html` (SPA sem bundler)
- Banco:
  - default local: SQLite (`instance/reportchart.db`)
  - producao: PostgreSQL via `DATABASE_URL`
- Servidor: gunicorn
- Persistencia principal: snapshots JSON completos do dashboard em `reports.payload_json`

Arquivos centrais:

- `app.py`
- `generate_dashboard.py`
- `index.html`
- `tests/test_security_flows.py`

## 2) Configuracao e defaults (regras de ambiente)

### 2.1 Backend

- `MAX_CONTENT_LENGTH = 50MB` (limite de upload)
- `SECRET_KEY`:
  - usa `APP_SECRET_KEY` quando definido
  - fallback: chave aleatoria por boot (`secrets.token_urlsafe(48)`)
  - em `APP_ENV=production`, `APP_SECRET_KEY` e obrigatoria e precisa ter ao menos 32 caracteres
- `DATABASE_URL`:
  - se vazio, usa SQLite local
  - normaliza prefixos `postgres://` e `postgresql://` para `postgresql+psycopg://`
- Sessao:
  - `SESSION_COOKIE_NAME=reportchart_session`
  - `SESSION_COOKIE_HTTPONLY=True`
  - `SESSION_COOKIE_SAMESITE=Lax`
  - `SESSION_COOKIE_SECURE` via env booleana; default true em `APP_ENV=production`
  - `SESSION_COOKIE_DOMAIN` opcional
  - `PERMANENT_SESSION_LIFETIME=7 dias`
- Cadastro publico:
  - desativado em codigo; novas contas comuns sao criadas por admin
  - `POST /api/register` sempre retorna 403
- Resumo IA:
  - `AI_SUMMARY_PROVIDER` default `heuristic`
  - `AI_SUMMARY_MODEL` default `gemma3:1b`
  - `AI_SUMMARY_OLLAMA_URL` default `http://127.0.0.1:11434`
  - `AI_SUMMARY_TIMEOUT` default `60s`
- Login:
  - `LOGIN_RATE_LIMIT_MAX` default `5`
  - `LOGIN_RATE_LIMIT_WINDOW_SECONDS` default `900`
  - `LOGIN_RATE_LIMIT_LOCKOUT_SECONDS` default `900`

### 2.2 Proxy

- Usa `ProxyFix` com `x_for/x_proto/x_host/x_port = 1`.
- Implicacao: headers de proxy reverso sao considerados para URL/esquema/host.

## 3) Modelo de dados (regras de dominio persistido)

### 3.1 `users`

- Campos: `email` unico, `display_name`, `password_hash`, `role`, `created_at`, `last_login_at`, `session_revoked_at`.
- Roles validas no sistema: `admin`, `user`, `disabled`.
- Roles gerenciaveis na criacao/edicao admin: `admin`, `user`, `disabled`.

### 3.2 `reports`

- Snapshot por usuario com ownership estrito (`user_id`).
- Conteudo principal em `payload_json` (JSON serializado do dashboard inteiro).
- Metadados: `title`, `source_filename`, `project_name`, `sprint_name`, `export_date`.

### 3.3 `custom_charts`

- Define visualizacao customizavel de datasets internos pre-computados.
- Campos de regra: `source_key`, `metric_key`, `chart_type`, `sort_mode`, `limit`, `enabled`, `sort_order`, `group_name`.

### 3.4 `custom_chart_type_options`

- Tipos permitidos por grafico customizado.
- Constraint unica: (`chart_id`, `chart_type`).

### 3.5 `profile_rules`

- Regras de override de perfil para classificacao de tarefas.
- Campos de criterio: `labels_contains`, `assignee_contains`, `bucket_contains`, `base_profiles`.
- `priority` define ordem de aplicacao (menor primeiro).

## 4) Seguranca (regras ativas)

### 4.1 Senhas

- Hash: `generate_password_hash(..., method="scrypt")`.
- Regra de senha forte:
  - minimo 12 caracteres
  - ao menos 1 letra
  - ao menos 1 digito
  - bloqueia senhas comuns e padroes obvios

### 4.2 Sessao e CSRF

- Ao logar:
  - limpa sessao anterior
  - define `session.permanent=True`
  - define `user_id`
  - define `login_at`
  - gera `csrf_token` aleatorio
- Rotas mutaveis usam `@csrf_required` e exigem header `X-CSRF-Token` (ou campo form).
- Comparacao CSRF com `secrets.compare_digest`.

### 4.3 Sessao de usuario desabilitado

- Em todo request (`before_request`):
  - se usuario carregado tiver role `disabled`, sessao e limpa imediatamente.
  - se `session.login_at <= users.session_revoked_at`, sessao e limpa imediatamente.
  - resposta marca expiracao de cookie.

### 4.4 Headers de seguranca em toda resposta

- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY`
- `Referrer-Policy: strict-origin-when-cross-origin`
- `Permissions-Policy: camera=(), microphone=(), geolocation=()`
- CSP:
  - `default-src 'self'`
  - `script-src 'self' 'unsafe-inline' https://cdn.plot.ly`
  - `style-src 'self' 'unsafe-inline'`
  - `img-src 'self' data: blob:`
  - `connect-src 'self'`
  - `frame-ancestors 'none'`
  - `base-uri 'self'`
  - `form-action 'self'`

### 4.5 Ownership

- Report so pode ser lido/resumido/excluido pelo dono (`report.user_id == g.user.id`).
- Acesso de outro usuario retorna 404 (nao 403), evitando leak de existencia.

## 5) Regras de autenticacao e ciclo de conta

### 5.1 Bootstrap

- `POST /api/bootstrap` so funciona quando nao existe nenhum usuario.
- Primeiro usuario sempre nasce como `admin`.
- Se bootstrap ja foi feito: 409.

### 5.2 Login

- `POST /api/login` bloqueia se bootstrap ainda nao concluido (409).
- Credenciais invalidas: 401.
- Falhas repetidas por IP/e-mail geram bloqueio temporario com 429.
- Usuario `disabled`: 403.
- Login bem-sucedido atualiza `users.last_login_at`.

### 5.3 Registro self-service

- Cadastro publico esta desativado.
- `POST /api/register` nao cria conta e retorna 403.
- Depois do bootstrap, novas contas devem ser criadas por admin em `POST /api/admin/users`.

### 5.4 Admin de usuarios

Regras de protecao:

- nao pode remover o proprio acesso admin
- nao pode excluir propria conta
- nao pode rebaixar/excluir o ultimo admin
- email sempre unico
- senha em update e opcional, mas se enviada precisa ser forte
- admin pode encerrar sessoes de outro usuario, marcando `session_revoked_at`.
- admin nao pode encerrar a propria sessao por essa rota; deve usar logout.

## 6) Matriz de autorizacao de rotas

### 6.1 Publicas

- `GET /`
- `GET /healthz`
- `GET /api/me` (retorna estado anonimo/autenticado)
- `POST /api/bootstrap`
- `POST /api/login`

### 6.2 Autenticadas

- `POST /api/logout` + CSRF
- `GET /api/reports`
- `GET /api/reports/{id}`
- `DELETE /api/reports/{id}` + CSRF
- `POST /api/reports/{id}/summary` + CSRF
- `POST /upload` + CSRF
- `GET /api/charts/custom`
- `GET /api/profile-rules`

### 6.3 Admin

- `GET /api/admin/users`
- `POST /api/admin/users` + CSRF
- `PATCH /api/admin/users/{id}` + CSRF
- `POST /api/admin/users/{id}/sessions/revoke` + CSRF
- `DELETE /api/admin/users/{id}` + CSRF
- `GET /api/admin/custom-charts`
- `POST /api/admin/custom-charts` + CSRF
- `PATCH /api/admin/custom-charts/{id}` + CSRF
- `DELETE /api/admin/custom-charts/{id}` + CSRF
- `GET /api/admin/profile-rules`
- `POST /api/admin/profile-rules` + CSRF
- `PATCH /api/admin/profile-rules/{id}` + CSRF
- `DELETE /api/admin/profile-rules/{id}` + CSRF

## 7) Regras de upload e persistencia de report

### 7.1 Upload (`POST /upload`)

Validacoes:

- precisa existir field `arquivo` em `request.files`
- nome de arquivo nao pode ser vazio
- nome seguro com `secure_filename`
- extensao obrigatoria `.xlsx` (case-insensitive)
- arquivo precisa ser zip valido (`zipfile.is_zipfile`)
- formato do export e escolhido no frontend antes do envio:
  - `legacy`: formato antigo, com tarefas na primeira planilha e metadados em `Nome do plano`
  - `teams_new`: formato novo do Teams, com metadados em `Plano` e tarefas em `Dados Consolidados`/`Tarefas`

Processamento:

- cria pasta temporaria
- salva `input.xlsx`
- executa `compute_json(input_path, ignore_labels, planner_format)`
- persiste report com dados serializados
- remove pasta temporaria em `finally`

Erros:

- validacao: 400
- falha de processamento: 500

### 7.2 Bibliotecas de report

- listagem ordenada por `updated_at DESC`.
- titulo do report no upload:
  - usa `meta.sprint_name` se existir
  - fallback: nome do arquivo sem extensao
- truncamentos:
  - title 160
  - source_filename 255
  - project_name 160
  - sprint_name 160
  - export_date 32

## 8) Regras de custom charts (CMS seguro v1)

### 8.1 Fontes permitidas (`source_key`)

- `hu_tasks`
- `areas`
- `categoria`
- `colaborador`
- `hu_inout`
- `rotulos`
- `responsaveis`
- `histograma`
- `wip_profile`

### 8.2 Tipos e metricas por fonte

- `hu_tasks`: tipos `bar_v,bar_h,pie,donut`; metricas `done,pending,total`
- `areas`: tipos `bar_v,bar_h,pie,donut`; metricas `done,pending,total`
- `categoria`: tipos `bar_v,bar_h,pie,donut`; metricas `done,pending,total`
- `colaborador`: tipos `bar_v,bar_h,pie,donut`; metricas `done,pending,total`
- `hu_inout`: tipos `bar_v,pie,donut`; metrica `count`
- `rotulos`: tipos `bar_v,bar_h`; metricas `done,pending,lead_time,cycle_time`
- `responsaveis`: tipos `bar_v,bar_h`; metricas `done,pending,lead_time,cycle_time`
- `histograma`: tipos `bar_v,line`; metrica `count`
- `wip_profile`: tipos `bar_v,line,area`; metrica `state_mix`

### 8.3 Validacoes de payload

- `name`: obrigatorio, max 160
- `group`: obrigatorio (ou default), deve estar em:
  - `Resumo`, `Andamento`, `Distribuicao`, `Tempo`
- `subtitle`: opcional, max 255
- `metric_key`: obrigatoria e restrita por `source_key`
- `chart_types`:
  - quando enviado, precisa conter pelo menos 1 tipo valido
  - ordenacao final respeita `CHART_TYPE_ORDER`
- `chart_type` inicial:
  - deve ser valido para a fonte
  - deve estar dentro de `chart_types` habilitados
- `sort_mode` permitido:
  - `metric_desc`, `metric_asc`, `label_asc`, `label_desc`
- `limit`:
  - opcional
  - se informado: 1..50
- `sort_order`:
  - inteiro 0..9999
- `enabled`:
  - parser boolean aceita: `1,true,yes,on`

### 8.4 Visibilidade

- endpoint publico `/api/charts/custom` retorna apenas `enabled=true`.
- endpoint admin lista todos.

## 9) Regras de profile rules

### 9.1 Validacao de criacao/edicao

- `name` obrigatorio (max 80)
- pelo menos um criterio precisa existir:
  - `labels_contains`
  - `assignee_contains`
  - `bucket_contains`
  - `base_profiles`
- `priority`: inteiro 0..9999
- `enabled`: bool parseado

### 9.2 Ordem de aplicacao

- somente regras `enabled=true`
- sort por:
  - `priority` asc
  - `name` normalizado asc

### 9.3 Matching por tarefa

- criterio de cada campo e `contains` texto normalizado (lower + sem acento)
- se mais de um criterio estiver preenchido, todos devem casar (AND)
- `base_profiles` compara contra perfil base da tarefa (`profile_base` / `profile_base_display`)
- primeira regra que casa define o perfil final da tarefa
- se nenhuma casar, usa perfil base

## 10) Regras de resumo executivo (`/api/reports/{id}/summary`)

### 10.1 Escopo

- sem `chart_id` ou `chart_id=kpis`: resumo geral
- `chart_id=custom_<id>`:
  - tenta carregar `CustomChart` no banco
  - se existir, usa `source_key/metric_key/sort/limit` do chart
- `chart_id=wip`:
  - se nao houver `task_rows`: cai para escopo `wip_bucket`
  - caso contrario: `wip_profile`
- demais `chart_id` usam mapeamento direto de fonte

### 10.2 Providers

- `heuristic`:
  - gera texto local a partir de fatos estruturados
- `ollama`:
  - chama `POST {AI_SUMMARY_OLLAMA_URL}/api/generate`
  - prompt restrito a dados fornecidos
  - `temperature=0.2`, `num_predict=260`
- fallback:
  - em erro de rede/http/timeout/resposta vazia -> `heuristic_fallback`

### 10.3 Filtros

- aceita `filters` como dict (ex: perfil no WIP)
- filtros entram em `facts.scope.filters`

## 11) Regras de negocio do parser Planner (`generate_dashboard.py`)

## 11.1 Entrada e mapeamento de colunas

- Le primeira planilha como base de tarefas.
- Se existir planilha `Nome do plano`, tenta extrair:
  - nome do plano
  - data de exportacao
- No formato novo do Teams:
  - le a aba `Dados Consolidados` como fonte preferencial das tarefas
  - usa a aba `Plano` para nome do plano e data de exportacao
  - se precisar cair para `Tarefas`, resolve IDs usando `Buckets` e `Usuarios`
- Mapeia aliases PT/EN para colunas canonicas (`tarefa`, `bucket`, `assignee`, datas, labels, notas, checklist etc).
- Colunas faltantes sao criadas vazias.

## 11.2 Regra de concluido

- `done = (progresso_texto == concluida) OR (pct_done >= 100)`
- `date_done` nao reclassifica status por si so.
- `done_kpi` usa essa mesma definicao.

## 11.3 Esforco

- prioridade de calculo:
  - denominador de `checklist_done` no formato `x/y`
  - fallback: contagem de itens em `checklist_items` (`;` + 1)

## 11.4 Flags de negocio

- `is_nao_prev`:
  - verdadeiro se bucket ou labels contiver termos de nao previsto
- `is_backlog`:
  - verdadeiro se bucket contiver backlog/incremento
- `hu`:
  - extraida do primeiro rotulo com padrao `HU<numero>`

## 11.5 Classificacao de area base (`df.area`)

Ordem de prioridade (mutuamente exclusiva):

1. bucket com "gestao" -> `Gestao`
2. label `GP` -> `Gestao`
3. bucket `Em Teste` -> `Revisao`
4. fallback por label/assignee usando dicionario de keywords

## 11.6 Datas de sprint no processamento

- `sprint_start = menor data entre date_done/date_start/date_due`
- `sprint_end = maior data entre date_done/date_start/date_due`
- se nao houver datas: usa data atual
- importante: burndown (tarefas/HU/SP) nao usa mais obrigatoriamente o mes de `sprint_end`; usa janela dinamica propria (item 13.3).
- `export_date`:
  - tenta parse da aba `Nome do plano`
  - fallback: data atual

## 11.7 Sprint goal

- se existir tarefa com nome exato `sprint goal`, extrai de `notas`
- remove prefixo regex `Sprint goal:`, `Sprint Goal -`, etc.

## 12) Regras de filtro por rotulos ignorados

- Aceita separadores `;` ou `,`.
- Normaliza tokens (case/acento).
- Remove linha quando algum label da tarefa bate exatamente com token normalizado.
- Em `compute_json`, o filtro afeta somente `df_scope`.

Campos baseados em `df_all` (nao filtrado por ignore_labels):

- `kpis`
- `hu_list`
- `hu_full_names`
- `hu_storypoints`
- `collab_rows`
- `area_rows`
- `cat_rows`, `bub_rows`
- `in_out`
- `rotulos_rows`
- `warnings`

Campos baseados em `df_scope` (filtrado quando ignore_labels existe):

- `resp_rows`
- `hist_31`, `indicativos`, `stats_rows`
- `dispersao`
- `cfd`
- `wip`
- `cts`
- `burndown`
- `burndown_hu`
- `burndown_sp`
- `task_rows`

## 13) Regras de calculo de indicadores

## 13.1 KPIs

- `total = numero de tarefas`
- `done = soma done_kpi`
- `pending = total - done`
- `nao_prev = soma is_nao_prev`
- `backlog_total = soma is_backlog`
- `sem_hu = tarefas sem HU em labels`
- `hu_count = numero de HUs distintas`
- `pct_entrega = done / total`
- `stakeholders = numero de assignees distintos nao vazios`
- `sprint_days_calendar = sprint_end - sprint_start`
- `sprint_days_business = dias corridos menos fins de semana e feriados nacionais BR`
- tempos:
  - `ct_task`: media de `date_done - date_start` (>=0)
  - `lt_task`: media de `date_done - date_criacao` (>=0)
  - `ct_hu/lt_hu`: media das medias por HU
- campos adicionais no payload KPI atual:
  - `ct_sp` e `lt_sp` (inicialmente alinhados com HU nessa versao)
  - `storypoints` (pode ficar 0 no KPI, embora burndown_sp use HU SP)
  - `fluxo_continuo` (contagem por label `FLUXO.CONTINUO`)

## 13.1.1 Escopo e qualidade

- `bug_task_count`: conta todas as tarefas com rotulos contendo `bug` ou `ajuste`, mesmo sem HU.
- `bug_task_with_hu_count`: subconjunto de bugs/ajustes vinculado a HU.
- `bug_hu_count`: HUs distintas afetadas por bugs/ajustes.
- `bug_density_avg`: `bug_task_count / hu_count`.
- `impediment_task_count`: conta tarefas com rotulos/bucket contendo `impedimento`, `impedido`, `impeditivo`, `bloqueio`, `bloqueado`, `blocked` ou `blocker`.
- `impediment_hu_count`: HUs distintas afetadas por impedimentos.
- `bug_rows` e `impediment_rows`: detalhamento por HU; tarefas sem HU aparecem como `Fora de HU`.

## 13.2 Story points por HU

- Extrai `[<n>SP]` do nome completo da HU.
- Burndown SP distribui SP igualmente entre tarefas da HU (`sp_hu / total_tarefas_hu`).
- Burndown SP usa a mesma janela temporal dinamica dos demais burndowns (ver 13.3).

## 13.3 Burndown de tarefas

- Janela temporal dinamica:
  - `start = min(date_criacao, date_start)` considerando linhas no `df_scope` (nao backlog).
  - `end_min = start + 30 dias` (periodo minimo de 31 dias).
  - `end = max(end_min, max(date_criacao, date_start, date_done, date_due))`.
  - fallback: se nao houver datas de inicio/criacao validas, usa limites do mes de referencia (`_month_bounds`).
- `meta`: linear ate zero no fim da janela dinamica.
- `plan`: plano em degraus via `_build_step_plan(..., blocks=5)`.
- `a_realizar`: total - concluidas ate o dia (bisect por datas de done).

## 13.4 Burndown HU

- Unidade e soma de tarefas de HU.
- HU conta como concluida so quando todas tarefas da HU estao concluida com data.
- `a_realizar`: soma total das HUs ainda nao totalmente concluidas.
- Janela temporal: mesma regra dinamica do item 13.3, aplicada sobre `df_scope` filtrado por `hu != ""`.

## 13.5 CFD

- Para cada dia do mes:
  - `done`: concluidas acumuladas
  - `doing`: `date_start <= dia < data_fim`
  - `todo`: restante
- data_fim usa preferencia de planejamento (`date_due` antes de `date_done`) em trechos atuais.
- apos `export_date`: carry-forward do ultimo estado.

## 13.6 WIP por fase

Fases fixas no payload atual:

- `Concluido`
- `Em Desenvolvimento`
- `Em Refinamento`
- `Gestao`
- `UX/UI`

Classificacao por `_wip_phase_from_row`:

1. bucket gestao -> `Gestao`
2. label GP sem HU -> `Gestao`
3. UX + (PO ou REQUISITOS) -> `Em Refinamento`
4. labels dev -> `Em Desenvolvimento`
5. labels ux/desktop/mobile/figma -> `UX/UI`
6. fallback -> `Em Refinamento`

Regra temporal:

- `Concluido`: cumulativo por data de fim
- fases ativas: contam no intervalo `start <= dia < fim`
- apos export_date: carry-forward

## 13.7 CTS e dispersao

- CTS (tabela): contagem de conclusoes por dia e por HU, mais serie `fora_hu`.
  - cada HU vira um par de colunas (`indice_fixo`, `qtd`) no template xlsx.
  - eixo temporal e diario dentro do periodo de referencia usado na geracao do payload.
- Dispersao (visual no web): substituida para o modelo `Cycle Time Scatterplot (data + volume da entrega)` do template.
  - fonte primaria: `cts` (`dates`, `hu_labels`, `matrix`, `fora_hu`).
  - fallback: `dispersao` legada (`hu_list`, `days`, `hu_matrix`, `nao_hu_daily`, `bd_start`).
  - eixo X: dia do mes extraido da data.
  - eixo Y: indice numerico da HU (oculto no front para evitar poluicao visual).
  - tamanho da bolha: volume de entregas (`qtd`) na combinacao `dia x HU`.
  - `Fora de HU` permanece como serie dedicada.
  - objetivo funcional: substituir o jitter 2x2 do scatter antigo por bolhas que evidenciam volumetria de entrega.

## 13.8 Rotulos e responsaveis

- Saida inclui `done`, `pending`, `lead_time`, `cycle_time` por grupo.
- Ordenacao por volume total desc.

## 13.9 Histograma

- Base: tarefas concluidas com datas validas.
- Bucket de 1 a 31 dias.
- `indicativos`: marca pontos de percentil 50/75/90 na distribuicao cumulativa.

## 13.10 Warnings de qualidade de dados

Regras e thresholds:

- `erro`: zero tarefas
- `aviso`: sprint_start ausente
- `aviso`: sprint_end ausente
- `info`: export mais antigo que 14 dias
- `info`: sprint encerrada ha mais de 30 dias em relacao ao export
- `aviso`: total de tarefas entre 1 e 4
- `aviso`: nenhuma HU identificada
- `aviso`: mais de 50% sem HU
- `info`: mais de 30% sem responsavel
- `info`: roadmap vazio
- `aviso`: sprint encerrada com entrega < 50%

## 14) Contrato de resposta da API (padrao)

- Sucesso: sempre `{"ok": true, ...}`
- Erro de regra de negocio/validacao: `{"ok": false, "erro": "..."}` com status adequado
- Codigos mais comuns:
  - 400 validacao
  - 401 nao autenticado
  - 403 proibido / CSRF invalido
  - 404 recurso nao encontrado (inclui ownership)
  - 409 conflito de estado
  - 500 falha interna

## 15) Regras de frontend relevantes para negocio

- Catalogo base de visualizacoes e fixo no cliente, com extensao por custom charts vindos da API.
- card builtin `dispersao` agora representa o `Cycle Time Scatterplot` (bolhas por volume), mantendo o mesmo `id` para nao quebrar persistencia de layout/favoritos.
- no `dispersao`, a legenda fica horizontal e o eixo Y nao exibe labels (evita truncamento do nome das HUs e privilegia leitura de volume por dia).
- Para custom chart:
  - tipos disponiveis por chart (`available_types`)
  - fallback de tipo para default permitido
- WIP builtin usa `task_rows` + profile rules para filtro por perfil no cliente.
- Tema/paleta persistidos em `localStorage` (`rcw-theme`, `rcw-palette`).
- Requisicoes autenticadas enviam `credentials: same-origin` e CSRF quando exigido.

## 16) Testes automatizados existentes

Arquivo: `tests/test_security_flows.py`

Cobertura validada:

- headers de seguranca
- CSRF no logout
- expiracao de cookie no logout
- gate admin para rotas restritas
- revogacao de sessao para usuario disabled
- CRUD e validacoes de custom charts
- CRUD e filtro publico de profile rules
- resumo geral e por secao
- ownership no endpoint de resumo

Execucao local observada:

- `python -m unittest -v tests.test_security_flows`
- resultado: 11 testes OK

## 17) Linha do tempo de entregas (git)

1. 2026-03-31 `b34a085` first commit
2. 2026-03-31 `d61beb6` burndown SP + HU full names + ajuste histograma
3. 2026-03-31 `5b4b411` assets deploy Oracle Always Free
4. 2026-03-31 `141443d` ajuste deps setup Oracle Linux
5. 2026-03-31 `0538daf` auth + persistencia + Dokploy ready
6. 2026-04-01 `2151758` admin user management
7. 2026-04-01 `1e79618` auth para dominio customizado
8. 2026-04-01 `3212829` self-service signup
9. 2026-04-01 `68ba983` fix logout cookie + testes de seguranca
10. 2026-04-01 `3a99c89` tabela de usuarios no admin
11. 2026-04-01 `8e8fec4` ajuste largura tabela admin
12. 2026-04-01 `d5d2413` safe custom chart CMS v1
13. 2026-04-01 `ab7bb35` profile rules + WIP filtrado
14. 2026-04-01 `9aac707` responsividade admin custom charts
15. 2026-04-01 `7101b65` multiplos tipos por custom chart
16. 2026-04-03 `4d90325` geracao de resumo de dashboard
17. 2026-04-03 `8481f2f` troca WIP builtin para visao por perfil
18. 2026-04-03 `a95f2ca` resumo section-aware

## 18) Observacoes tecnicas importantes (para manutencao)

- `generate_dashboard.py` possui funcoes redefinidas em mais de um ponto.
- Regra Python: a ultima definicao carregada e a efetiva em runtime.
- Para evitar ambiguidade futura, vale consolidar funcoes duplicadas em uma unica implementacao por nome.
- `db.create_all()` e usado no startup; nao existe trilha formal de migracao (ex: Alembic).

## 19) Checklist rapido de regressao antes de release

1. bootstrap, login, logout e `api/me`
2. CRUD admin users com regras do ultimo admin
3. upload `.xlsx` valido e invalido
4. listagem/abertura/exclusao de reports por ownership
5. CRUD custom charts e visibilidade publica apenas `enabled`
6. CRUD profile rules e filtro no WIP profile
7. resumo geral + resumo de secao (heuristic e fallback)
8. headers de seguranca e CSRF nos mutating endpoints
