# Verificação de segurança local

Última verificação: 2026-09-09

## Verificações executadas

- busca textual por chaves, tokens, senhas, chaves privadas, URLs de banco e arquivos sensíveis;
- inspeção dos arquivos atualmente versionados para `.env`, bancos, exports `.xlsx` e logs;
- `pip check` para dependências instaladas.

## Resultado

- nenhuma credencial ou chave privada identificada no conteúdo atual;
- `.gitignore` cobre `.env`, bancos, exports, logs e arquivos temporários;
- `pip check`: nenhuma dependência quebrada.

## Limitações

- `pip check` não substitui uma auditoria de vulnerabilidades CVE; executar `pip-audit` ou ferramenta equivalente no pipeline de release;
- o histórico Git contém nomes de logs locais antigos e deve ser revisado antes da publicação pública;
- HTTPS, PostgreSQL de staging, secret manager e canal privado de vulnerabilidades ainda dependem da infraestrutura e dos mantenedores.
