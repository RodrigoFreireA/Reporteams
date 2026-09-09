# Staging

Esta stack executa a aplicação com PostgreSQL, Redis e HTTPS automático pelo
Caddy. O Redis é usado pelo rate limit compartilhado entre os workers.

Crie um arquivo `.env` somente no servidor, fora do Git, contendo pelo menos:

```env
APP_SECRET_KEY=gere-uma-chave-longa-e-aleatoria
SESSION_COOKIE_SECURE=1
POSTGRES_DB=reportchart
POSTGRES_USER=reportchart
POSTGRES_PASSWORD=uma-senha-forte
DATABASE_URL=postgresql+psycopg://reportchart:uma-senha-forte@postgres:5432/reportchart
REDIS_PASSWORD=outra-senha-forte
RATE_LIMIT_REDIS_URL=redis://:outra-senha-forte@redis:6379/0
DOMAIN=staging.seu-dominio.example
ACME_EMAIL=voce@seu-dominio.example
PLANNER_RETENTION_DAYS=365
```

Suba a stack com:

```bash
docker compose -f deploy/staging/docker-compose.yml up -d --build
```

Agende periodicamente a retenção dos dados:

```bash
docker compose -f deploy/staging/docker-compose.yml exec app \
  python scripts/purge_expired_data.py
```

Faça backup do PostgreSQL e dos volumes antes de alterar o período de retenção.
