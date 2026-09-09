# Segurança

O ReportChart processa dados de planejamento que podem conter nomes de pessoas, projetos, prazos e informações internas. A segurança precisa ser considerada antes de publicar uma instalação ou um exemplo de dados.

## Não versionar

- `.env` e qualquer arquivo com credenciais;
- `instance/`, bancos SQLite, dumps e backups;
- exportações `.xlsx` do Planner;
- `secret.key`, tokens, cookies e logs de produção;
- screenshots ou fixtures que contenham dados reais sem anonimização.

O `.gitignore` cobre os artefatos locais mais comuns, mas cada contribuição deve revisar `git diff` antes de publicar.

## Controles existentes

- senhas armazenadas com `scrypt`;
- política mínima de senha e limitação de tentativas de login;
- sessões `HttpOnly`, `SameSite=Lax` e `Secure` em produção;
- tokens CSRF em operações mutáveis;
- autorização no backend para usuário, administrador, equipe e dashboard;
- limite de tamanho para uploads;
- `secure_filename` e diretório temporário para arquivos enviados;
- headers de segurança, CSP, `X-Frame-Options` e HSTS em HTTPS de produção;
- nenhuma credencial padrão é criada pelo código.

## Publicação segura

1. Defina `APP_ENV=production` e uma `APP_SECRET_KEY` aleatória, estável e fora do Git.
2. Configure PostgreSQL e uma senha forte via secret manager ou variáveis protegidas.
3. Ative HTTPS e `SESSION_COOKIE_SECURE=true`.
4. Não habilite bootstrap automático de administrador em servidor compartilhado; use o fluxo de primeiro acesso ou uma operação controlada.
5. Remova dados de `instance/`, logs locais, exports e artefatos de teste antes de criar o repositório público.
6. Execute os testes e uma varredura de segredos antes de cada release.

## Reportar vulnerabilidades

Não abra uma issue pública para uma vulnerabilidade ainda não corrigida. O canal preferencial para a publicação é o recurso privado **Report a vulnerability** das GitHub Security Advisories deste repositório, que deve ser habilitado pelos mantenedores antes da primeira publicação pública.

Se o recurso ainda não estiver habilitado, aguarde a configuração do canal privado pelos mantenedores em vez de enviar credenciais, exports ou dados reais em uma issue. O relatório deve incluir impacto, passos para reproduzir, versão/commit afetado e uma sugestão de mitigação.

Até existir um canal dedicado, registre o contato de segurança no repositório antes da primeira publicação pública.
