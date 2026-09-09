# Oracle Always Free

Guia pratico para subir este projeto em uma VM `Always Free` da Oracle Cloud Infrastructure (OCI).

## O que muda em relacao ao Cloud Run

Nesta trilha, a infraestrutura fica assim:

- uma VM `OCI Ampere A1` Always Free
- `Podman Compose` na propria VM
- `Caddy` para proxy reverso e HTTPS
- `Flask` em container
- `Postgres` em container privado na mesma VM

Essa arquitetura e simples, barata e suficiente para a fase inicial do produto.

## Observacoes importantes

- A Oracle tambem mostra um periodo inicial de trial na criacao da conta.
- A diferenca e que os recursos `Always Free` nao expiram no fim desse periodo, desde que voce fique dentro dos limites.
- As instancias de computacao Always Free precisam ser criadas na `regiao home` da conta.
- Se a forma estiver sem capacidade, a propria Oracle recomenda tentar outro `Availability Domain` ou aguardar e tentar novamente.

## Limites relevantes do Always Free

Segundo a documentacao oficial consultada em 31/03/2026:

- `VM.Standard.A1.Flex`: total de `4 OCPUs` e `24 GB` de memoria gratis
- ate `200 GB` combinados de boot volume + block volume
- as instancias Always Free podem ser recuperadas pela Oracle se ficarem `7 dias` com uso muito baixo de CPU, rede e memoria

## Recomendacao para este projeto

Use:

- imagem `Ubuntu` elegivel para Always Free
- forma `VM.Standard.A1.Flex`
- `2 OCPUs`
- `12 GB RAM`
- boot volume de `50 GB`

Esse tamanho e suficiente para:

- `Flask + gunicorn`
- `pandas/openpyxl`
- `Postgres`
- `Caddy`

Se faltar capacidade para `2 OCPUs / 12 GB`, tente:

- `1 OCPU / 6 GB`
- outro `Availability Domain`

## Arquivos desta branch

- `Dockerfile`
- `docker-compose.oracle.yml`
- `deploy/oracle/Caddyfile`
- `deploy/oracle/setup-oracle-linux.sh`

O arquivo `.env` deve ser criado somente na VM e nunca versionado.

## Passo a passo

### 1. Criar a conta e escolher a regiao home

1. Crie a conta OCI.
2. Escolha a `regiao home` com cuidado.
3. Guarde essa regra: compute Always Free e banco Always Free sao provisionados na regiao home.

### 2. Criar um compartimento

No OCI Console:

1. `Identity & Security`
2. `Compartments`
3. Crie um compartimento como `reportchart-prod`

### 3. Criar a rede

Use o caminho recomendado pela propria Oracle:

1. `Networking`
2. `Virtual cloud networks`
3. `Start VCN Wizard`
4. Escolha `Create VCN with Internet Connectivity`

Sugestao de nomes:

- VCN: `reportchart-vcn`
- public subnet: `reportchart-public-subnet`

### 4. Criar a VM

No OCI Console:

1. `Compute`
2. `Instances`
3. `Create instance`

Configuracao recomendada:

- Name: `reportchart-vm`
- Compartment: `reportchart-prod`
- Image: `Ubuntu` com selo `Always Free eligible`
- Shape: `VM.Standard.A1.Flex`
- OCPU: `2`
- Memory: `12 GB`
- Boot volume: `50 GB`
- Network: public subnet da VCN criada
- Public IPv4: habilitado
- SSH key: gere ou envie sua chave publica

### 5. Abrir portas da aplicacao

Voce precisa liberar:

- `22/tcp` idealmente so para o seu IP
- `80/tcp` para acesso HTTP
- `443/tcp` para HTTPS

Se estiver usando a security list padrao da subnet publica, adicione regras de ingress para:

- source `0.0.0.0/0`, port `80`
- source `0.0.0.0/0`, port `443`

Para `22`, prefira:

- source `SEU_IP_PUBLICO/32`, port `22`

### 6. Conectar na VM

Depois que a instancia estiver `RUNNING`, conecte por SSH:

```bash
ssh -i /caminho/da/sua-chave opc@IP_PUBLICO_DA_VM
```

### 7. Preparar a VM

Copie o script desta branch para a VM ou clone o repositorio primeiro. Depois rode:

```bash
sudo bash deploy/oracle/setup-oracle-linux.sh
```

O script instala `Podman`, `podman-compose`, `firewalld`, libera `80/443` no firewall local
e prepara o diretorio `/opt/reportchart-web`.

### 8. Subir o projeto na VM

No servidor:

```bash
cd /opt
git clone SEU_REPOSITORIO reportchart-web
cd reportchart-web
touch .env
```

Edite o `.env`:

```bash
nano .env
```

Ajuste no minimo:

- `APP_SECRET_KEY`
- `POSTGRES_PASSWORD`
- `DATABASE_URL` usando a mesma senha definida em `POSTGRES_PASSWORD`
- `SESSION_COOKIE_SECURE=1` com HTTPS; use `0` apenas para teste temporario por IP sem HTTPS
- `DOMAIN` quando ja tiver dominio
- `ACME_EMAIL` quando ja tiver dominio

### 9. Fazer o primeiro deploy

```bash
sudo podman-compose -f docker-compose.oracle.yml up -d --build
```

Verifique:

```bash
sudo podman-compose -f docker-compose.oracle.yml ps
sudo podman-compose -f docker-compose.oracle.yml logs -f
```

### 10. Testar antes do dominio

Com a VM no ar e as portas abertas:

- teste `http://IP_PUBLICO_DA_VM/`
- teste `http://IP_PUBLICO_DA_VM/healthz`

O endpoint `/healthz` deve responder com JSON simples.

### 11. Apontar dominio e ativar HTTPS

Quando estiver pronto para usar HTTPS:

1. crie um registro `A` no seu DNS apontando para o `IP_PUBLICO_DA_VM`
2. coloque esse host em `DOMAIN=` no `.env`
3. reinicie o stack

```bash
sudo podman-compose -f docker-compose.oracle.yml up -d
```

O `Caddy` tenta emitir certificado automaticamente para o dominio configurado.

## Operacao basica

Atualizar o app:

```bash
git pull
sudo podman-compose -f docker-compose.oracle.yml up -d --build
```

Parar:

```bash
sudo podman-compose -f docker-compose.oracle.yml down
```

Reiniciar:

```bash
sudo podman-compose -f docker-compose.oracle.yml restart
```

## Banco e seguranca

Nesta fase inicial, o Postgres fica dentro da mesma VM e nao e publicado para a internet.

Isso e aceitavel para um MVP se voce:

- nao expor a porta `5432`
- usar senha forte
- fizer backup periodico
- manter a VM atualizada

Para a proxima fase do projeto, eu recomendo:

1. implementar login seguro
2. salvar dashboards por usuario no Postgres
3. adicionar backup automatico do banco
4. trocar renderizacao sensivel no frontend para evitar `XSS`

## Problemas comuns

### Sem capacidade para criar A1

Mensagem comum:

- falta de capacidade do host

Acoes praticas:

1. tente outro `Availability Domain`
2. tente uma forma menor, como `1 OCPU / 6 GB`
3. aguarde e tente novamente

### Porta aberta na OCI, mas sem acesso externo

Verifique os dois lados:

1. regra de ingress da subnet ou NSG
2. firewall do Ubuntu na propria VM

### HTTPS nao sobe

Cheque:

1. `DOMAIN` no `.env`
2. DNS `A` apontando para o IP certo
3. portas `80` e `443` abertas
4. logs do `caddy`

```bash
sudo podman-compose -f docker-compose.oracle.yml logs caddy
```
