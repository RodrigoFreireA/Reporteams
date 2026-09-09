# Dokploy

Guia para subir a versao completa deste projeto no Dokploy, com login por sessao e persistencia em Postgres.

## Arquivo recomendado

Use:

- `docker-compose.dokploy-full.yml`

Esse compose sobe:

- `app` Flask/Gunicorn
- `postgres` para usuarios e dashboards salvos

## Antes de publicar

Suba a branch que contem essa versao:

```bash
git push -u origin feat/oracle-always-free
```

## Passo a passo no Dokploy

1. Crie um novo servico `Docker Compose`.
2. Conecte o provider do seu repositorio.
3. Use o repositorio:
   - `https://github.com/RodrigoFreireA/Reporteams.git`
4. Use a branch:
   - `main`
5. Em `Compose File Path`, informe:
   - `docker-compose.dokploy-full.yml`

## Variaveis de ambiente

No Dokploy, crie estas variaveis:

```env
APP_ENV=production
PORT=8000
APP_HOST_PORT=8000
APP_SECRET_KEY=troque-por-uma-chave-longa-e-aleatoria-com-32-ou-mais-caracteres
SESSION_COOKIE_SECURE=1
SESSION_COOKIE_DOMAIN=
LOGIN_RATE_LIMIT_MAX=5
LOGIN_RATE_LIMIT_WINDOW_SECONDS=900
LOGIN_RATE_LIMIT_LOCKOUT_SECONDS=900

POSTGRES_DB=reportchart
POSTGRES_USER=reportchart
POSTGRES_PASSWORD=troque-por-uma-senha-forte
DATABASE_URL=postgresql+psycopg://reportchart:troque-por-uma-senha-forte@postgres:5432/reportchart
AI_SUMMARY_PROVIDER=heuristic
AI_SUMMARY_MODEL=gemma3:1b
AI_SUMMARY_OLLAMA_URL=http://ollama:11434
AI_SUMMARY_TIMEOUT=60
```

Notas:

- `APP_SECRET_KEY` precisa ser estavel. Se mudar, todas as sessoes atuais deixam de valer.
- Use `SESSION_COOKIE_SECURE=1` quando houver HTTPS. Se for testar temporariamente por IP e sem HTTPS, use `SESSION_COOKIE_SECURE=0` apenas nesse periodo.
- Se quiser compartilhar a mesma sessao entre `reportx.site` e `www.reportx.site`, defina `SESSION_COOKIE_DOMAIN=reportx.site`.
- Cadastro publico esta desativado. O primeiro admin continua sendo criado pelo bootstrap; depois disso, crie usuarios pelo painel admin.
- O rate limit de login padrao bloqueia temporariamente apos 5 falhas no mesmo IP/e-mail dentro de 15 minutos.
- `AI_SUMMARY_PROVIDER=heuristic` usa resumo local sem depender de modelo externo.
- Para IA local na VPS, suba um `ollama` na mesma rede e troque `AI_SUMMARY_PROVIDER=ollama`.
- Para resumo executivo leve, `gemma3:1b` tende a ser a opcao mais enxuta que ainda entrega texto util. Se voce quiser insistir na linha Gemma 4, use a menor variante disponivel e valide RAM e latencia antes.
- Se essa variavel mudar, faca redeploy.

## Deploy

1. Clique em `Save`.
2. Clique em `Deploy`.
3. Aguarde os containers `app` e `postgres` ficarem saudaveis.

Se voce ainda nao configurar dominio, acesse por IP:

```text
http://IP_DO_SERVIDOR:8000
```

## Primeiro acesso

No primeiro acesso, o sistema entra em modo bootstrap:

1. Abra a aplicacao.
2. Crie o primeiro usuario administrador.
3. Esse usuario passa a ser o dono dos dashboards que ele salvar.

Depois disso:

- novos acessos passam pela tela de login
- cada usuario so enxerga os proprios dashboards
- cada upload gera um dashboard salvo no Postgres

## Fluxo funcional

1. Usuario entra com email e senha.
2. Faz upload do `.xlsx`.
3. O backend processa o arquivo.
4. O resultado do dashboard e salvo no Postgres.
5. A biblioteca lateral lista os dashboards do usuario.
6. O usuario pode reabrir ou excluir dashboards salvos.

## Quando voce decidir usar dominio

No Dokploy:

1. Abra o servico.
2. Va em `Domains`.
3. Adicione o dominio para o servico `app`.
4. Informe a porta interna `8000`.
5. Salve e redeploy.

Com HTTPS, mantenha:

```env
SESSION_COOKIE_SECURE=1
```

Sem HTTPS, use `SESSION_COOKIE_SECURE=0` apenas para teste temporario, senao o cookie de sessao nao sera enviado pelo navegador.

## Arquivos relevantes

- `docker-compose.dokploy-full.yml`
- `Dockerfile`
- `app.py`

As variáveis devem ser cadastradas diretamente como secrets/environment variables
no Dokploy. Não copie valores de produção para um arquivo versionado.

## Referencias oficiais

- Dokploy Docker Compose: https://docs.dokploy.com/docs/core/docker-compose
- Dokploy Domains: https://docs.dokploy.com/docs/core/docker-compose/domains
- Dokploy Providers: https://docs.dokploy.com/docs/core/providers
- Dokploy Databases: https://docs.dokploy.com/docs/core/databases
