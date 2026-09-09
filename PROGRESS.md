# ReportChart — progresso do produto

Última revisão: 2026-09-09

Este arquivo acompanha a evolução do projeto e funciona como checklist de publicação open source. Cada etapa deve preservar o funcionamento local, atualizar os testes e registrar riscos conhecidos.

## Estado atual

- [x] Landing page pública e apresentação do produto
- [x] Autenticação por sessão, bootstrap do primeiro usuário e proteção de rotas
- [x] Biblioteca de dashboards e upload do Planner
- [x] Equipes, duração de sprint e associação de dashboards
- [x] Guia pós-login das regras do Planner
- [x] Limites de upload, CSRF, rate limit e headers de segurança
- [x] Remoção do administrador padrão com credenciais fixas
- [x] README, SECURITY e configuração de ambiente documentados
- [x] Licença, contribuição, código de conduta e templates de colaboração preparados

## Em andamento

- [x] Criar inventário de contratos do processamento do Planner (`docs/planner-contracts.md`)
- [x] Extrair configuração de ambiente de `app.py` para `reportchart_web/config.py`
- [x] Extrair a extensão SQLAlchemy para `reportchart_web/extensions.py`
- [x] Extrair políticas de senha, CSRF, rate limit e guards para `reportchart_web/security.py`
- [x] Extrair modelos SQLAlchemy para `reportchart_web/models.py`
- [x] Criar repositórios para usuários, equipes, relatórios, roadmaps e configuração de dashboards
- [x] Extrair regras puras de normalização textual/data do Planner
- [x] Extrair identificação de HU, metadados de título e perfis do Planner
- [x] Extrair classificação de áreas, categorias e buckets do Planner
- [x] Extrair cálculos métricos puros de média, percentual, desvio e eficiência
- [x] Extrair regras de qualidade, impedimento e scope creep
- [x] Extrair primeiro blueprint Flask para páginas públicas e shell da aplicação
- [x] Extrair blueprint Flask de autenticação e sessão
- [x] Extrair blueprint Flask de equipes e membros
- [x] Extrair blueprint Flask administrativo de usuários
- [x] Extrair blueprint Flask de gráficos customizados e regras de perfil
- [x] Extrair blueprint Flask de layouts salvos e versões
- [x] Extrair blueprint Flask de relatórios e associação com equipes
- [x] Extrair blueprint Flask de roadmaps e upload do Planner
- [x] Extrair regras de configuração de gráficos customizados do `app.py`
- [x] Extrair inicialização de banco e bootstrap administrativo
- [x] Isolar provedor de resumo externo e prompt de IA
- [x] Extrair leitor de exportações Excel Legacy e Teams e remover duplicação do gerador
- [ ] Extrair ciclo de criação da aplicação e blueprints
- [ ] Expandir repositórios para cobrir os demais fluxos de persistência
- [x] Separar o parser do Excel em módulo puro
- [ ] Separar todo o cálculo de métricas em módulos puros
- [x] Migrar rotas HTTP para blueprints por domínio
- [ ] Reduzir `app.py` a composição da aplicação

## Segurança antes da publicação

- [x] Escolher e adicionar a licença MIT
- [ ] Remover dados reais, exports, bancos e logs do histórico Git
- [ ] Habilitar canal privado de vulnerabilidades no GitHub Security Advisories
- [x] Executar verificação local de segredos e integridade de dependências (`docs/security-scan.md`)
- [x] Documentar a matriz de autorização (`docs/authorization-matrix.md`)
- [ ] Validar HTTPS, HSTS, cookies Secure e PostgreSQL em staging
- [x] Revisar permissões por usuário, administrador, equipe e dashboard (`docs/authorization-matrix.md`)
- [ ] Criar política de retenção e remoção de dados do Planner

## Critério para cada refatoração

1. Definir a fronteira e o contrato antes de mover código.
2. Adicionar ou atualizar testes de comportamento.
3. Fazer uma alteração pequena e reversível.
4. Executar a suíte completa e `git diff --check`.
5. Atualizar este arquivo e a documentação correspondente.

## Documentos relacionados

- `README.md`: instalação, operação e visão geral
- `SECURITY.md`: dados sensíveis, controles e publicação segura
- `docs/architecture.md`: camadas, padrões e sequência de migração
- `docs/open-source-release.md`: procedimento para criar o novo repositório sem histórico
