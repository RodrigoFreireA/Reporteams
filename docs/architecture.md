# Arquitetura e plano de refatoração

## Diagnóstico atual

O sistema funciona, mas a maior parte do backend está concentrada em `app.py` e o cálculo está concentrado em `generate_dashboard.py`. Isso aumenta o custo de revisão, dificulta testes unitários e mistura HTTP, persistência, autenticação e regra de negócio.

A refatoração será incremental. Não devemos mover centenas de funções em uma única alteração nem alterar o formato do payload sem contrato de compatibilidade.

## Camadas alvo

```text
reportchart_web/
  presentation/       # Flask blueprints, serializers HTTP, views
  application/        # casos de uso: upload, login, equipes, relatórios
  domain/              # entidades, value objects e políticas de métricas
  infrastructure/     # SQLAlchemy, filesystem, Excel e integrações externas
  config.py            # configuração por ambiente e validação
  extensions.py        # db e extensões Flask
  models.py            # entidades persistidas e relacionamentos ORM
  repositories.py      # gateways de persistência por agregado
  bootstrap.py         # inicialização do banco e bootstrap administrativo
  summary_provider.py  # prompt e integração opcional com Ollama
  chart_configuration.py # validação e serialização de gráficos customizados
  planner/text.py      # normalização textual e datas sem dependências Flask
  planner/identifiers.py # regras de HU, metadados e perfis
  planner/classification.py # áreas, categorias e buckets
  planner/metrics.py      # cálculos métricos puros
  planner/quality.py      # qualidade, impedimentos e scope creep
  planner/excel_loader.py # leitura e normalização inicial dos exports Excel
  blueprints/public.py    # landing, shell e views HTML
  blueprints/auth.py      # bootstrap, login, sessão e logout
  blueprints/teams.py     # equipes, sprint e membros
  blueprints/admin_users.py # administração de usuários
  blueprints/admin_configuration.py # gráficos e regras de perfil
  blueprints/layouts.py      # layouts salvos e versões
  blueprints/reports.py      # dashboards, equipes e resumos
  blueprints/planner.py      # roadmaps salvos e upload do Planner
```

### Presentation

Recebe a requisição, valida o formato externo, chama um caso de uso e traduz o resultado para JSON/HTML. Não deve calcular métricas nem consultar tabelas diretamente.

### Application

Orquestra uma operação completa, como `UploadPlannerReport`, `CreateTeam` ou `RevokeUserSessions`. É o lugar para autorização de caso de uso e transação.

### Domain

Contém regras determinísticas: identificação de HU, leitura de Story Points, classificação de rótulos, estados e políticas de sprint. Deve ser testável sem Flask, banco ou filesystem.

### Infrastructure

Implementa portas do domínio: repositórios SQLAlchemy, armazenamento de snapshots, parser do Excel e cliente do Ollama. Dependências externas ficam atrás de interfaces pequenas.

## Padrões adotados

- **Application Service** para casos de uso transacionais;
- **Repository** para acesso a usuários, equipes e relatórios;
- **Strategy** para formatos novo/antigo do Planner e provedores de resumo;
- **Factory** para selecionar parser e configuração por ambiente;
- **DTO/Serializer** na fronteira HTTP, evitando retornar modelos ORM diretamente;
- **Policy/Guard** para autenticação, CSRF e autorização;
- **Adapter** para Excel, PostgreSQL/SQLite e integrações externas.

## Sequência segura de migração

1. congelar contratos existentes com testes de rota e payload;
2. [x] extrair configuração e extensão SQLAlchemy;
3. [x] extrair políticas de senha, CSRF, rate limit e guards;
4. [x] extrair entidades persistidas e relacionamentos ORM;
5. extrair ciclo de criação da aplicação e autenticação completa;
6. [x] extrair primeira fatia de repositórios de usuário, equipe e relatório;
7. extrair casos de uso de upload e biblioteca;
8. extrair regras puras de normalização do parser do Planner;
9. extrair regras de identificação de HU, metadados e perfis;
10. extrair regras de classificação de áreas, categorias e buckets;
11. extrair cálculos métricos puros;
12. extrair regras de qualidade e escopo;
13. [x] extrair primeiro blueprint de páginas públicas e shell;
14. [x] extrair blueprint de autenticação e sessão;
15. [x] extrair blueprint de equipes e membros;
16. [x] extrair blueprint administrativo de usuários;
17. [x] extrair blueprint de gráficos e regras de perfil;
18. [x] extrair blueprint de layouts salvos e versões;
19. [x] extrair blueprint de relatórios e associação com equipes;
20. migrar demais rotas para blueprints por domínio;
21. reduzir `app.py` a composição da aplicação;
19. remover duplicações e atualizar documentação.

Cada passo deve manter o servidor executável, passar os testes e ser reversível. A primeira versão pública só deve ser marcada depois de uma revisão de dependências, segredos, licença e dados de exemplo.
