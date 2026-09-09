# ReportChart Web

O ReportChart transforma uma exportação do Microsoft Planner em uma leitura operacional de fluxo: entrega, tempo, escopo, qualidade, pessoas e previsibilidade.

O projeto está sendo preparado para código aberto. A aplicação continua evoluindo, por isso a documentação distingue o que já existe do que está sendo refatorado.

## O que já funciona

- autenticação por sessão, bootstrap do primeiro administrador e controle de acesso;
- upload de exportações `.xlsx` do Planner;
- dashboards persistidos por usuário;
- equipes com duração de sprint e associação de dashboards;
- KPIs de sprint, métricas de fluxo, distribuição, escopo, calendário e roadmap;
- comparativos, relatórios configuráveis e regras de perfil;
- guia pós-login com as regras de preenchimento do Planner;
- SQLite para uso local e PostgreSQL para ambientes compartilhados;
- execução web com Flask/Gunicorn e empacotamento desktop opcional.

## Requisitos

- Python 3.12 ou superior;
- pip;
- Microsoft Planner exportado para Excel para testar o processamento.

## Executar localmente

```powershell
python -m venv .venv
\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
python app.py
```

Abra `http://127.0.0.1:5001`. No primeiro acesso, crie o administrador pela tela de bootstrap. O banco local fica em `instance/reportchart.db`, que não deve ser versionado.

Para executar os testes:

```powershell
python -m unittest discover -s tests -p "test_*.py"
```

## Configuração e dados sensíveis

Nunca coloque senhas, tokens, chaves, arquivos `.xlsx`, bancos ou dumps reais no Git. Use `.env.example` como referência e mantenha os valores reais fora do repositório.

Em produção, `APP_SECRET_KEY` é obrigatório e deve ter pelo menos 32 caracteres. Gere uma chave aleatória e configure `SESSION_COOKIE_SECURE=true` quando a aplicação estiver atrás de HTTPS. O bootstrap automático de administrador é opt-in e só deve ser usado no modo desktop com variáveis de ambiente explícitas.

Consulte [SECURITY.md](SECURITY.md) para o modelo de ameaça, práticas de reporte e checklist de publicação.

Este projeto é distribuído sob a licença [MIT](LICENSE).

## Estrutura atual

```text
reportchart_web/            # camadas backend extraídas gradualmente
  config.py                 # configuração e políticas de ambiente
  extensions.py             # extensões Flask compartilhadas
  security.py              # senha, CSRF, rate limit e guards
  models.py                # entidades persistidas e relacionamentos ORM
  repositories.py          # consultas persistentes por agregado
  bootstrap.py             # inicialização do banco e bootstrap administrativo
  summary_provider.py      # prompt e integração opcional com Ollama
  chart_configuration.py   # validação e serialização de gráficos customizados
  planner/text.py          # regras puras de texto e datas do Planner
  planner/identifiers.py   # identificação de HU e perfis das tarefas
  planner/classification.py # áreas, categorias e regras de bucket
  planner/metrics.py        # cálculos métricos puros
  planner/quality.py        # qualidade, impedimentos e scope creep
  planner/excel_loader.py   # leitura e normalização inicial dos exports Excel
  blueprints/public.py      # landing, shell e views HTML
  blueprints/auth.py        # bootstrap, login, sessão e logout
  blueprints/teams.py       # equipes, duração de sprint e membros
  blueprints/admin_users.py # administração de usuários
  blueprints/admin_configuration.py # gráficos e regras de perfil
  blueprints/layouts.py      # layouts salvos e versões
  blueprints/reports.py      # dashboards, equipes e resumos
  blueprints/planner.py      # roadmaps salvos e upload do Planner
app.py                    # entrada Flask atual; em decomposição gradual
generate_dashboard.py     # processamento e cálculo das métricas
index.html                # shell da aplicação autenticada
views/                    # views carregadas sob demanda
static/js/                # módulos de interface por domínio
static/css/               # design system e responsividade
tests/                    # testes de segurança, formatos e métricas
docs/                     # decisões, operação e arquitetura
desktop/                  # launcher e empacotamento Windows
deploy/                   # artefatos de execução/deploy
```

## Arquitetura alvo

A arquitetura será migrada por fatias, mantendo contratos HTTP estáveis:

```text
interface (rotas, views, API)
        ↓
application (casos de uso e políticas)
        ↓
domain (entidades, regras e contratos)
        ↓
infrastructure (SQLAlchemy, arquivos, Planner/Excel, IA)
```

O plano detalhado está em [docs/architecture.md](docs/architecture.md), os contratos do Planner em [docs/planner-contracts.md](docs/planner-contracts.md) e o acompanhamento vivo em [PROGRESS.md](PROGRESS.md). A regra é extrair uma fronteira por vez, adicionar testes de contrato e só depois remover o código legado.

## Princípios do projeto

- segurança por padrão e configuração explícita;
- autorização no servidor, nunca apenas na interface;
- funções de domínio determinísticas e testáveis;
- views finas, casos de uso claros e acesso a dados isolado;
- migrações compatíveis com instalações existentes;
- mudanças pequenas, documentadas e verificadas por testes.

## Licença

O projeto é distribuído sob a [licença MIT](LICENSE).

Consulte também o [relatório de verificação de segurança local](docs/security-scan.md) e a [matriz de autorização](docs/authorization-matrix.md) antes de publicar uma release.

Para contribuir, consulte [CONTRIBUTING.md](CONTRIBUTING.md). O procedimento de migração para o repositório público está em [docs/open-source-release.md](docs/open-source-release.md).
