# Migração para o repositório open source

O repositório de desenvolvimento possui histórico antigo e não deve ser publicado diretamente. A publicação deve começar em um repositório vazio, usando apenas a árvore de trabalho validada.

## Preparação

1. Confirme que `git status` está limpo.
2. Execute a suíte de testes e `pip check`.
3. Revise `SECURITY.md`, `.env.example`, dependências e licença.
4. Verifique que não existem arquivos reais em `instance/`, exports, logs ou `.env`.

## Criar a cópia sem histórico

Em uma pasta irmã do projeto, copie a árvore de trabalho sem `.git` e sem artefatos locais:

```powershell
robocopy . ..\reportchart-open-source /E /XD .git instance __pycache__ .venv build dist /XF .env *.db *.sqlite *.sqlite3 *.xlsx *.log
Set-Location ..\reportchart-open-source
git init -b main
git add .
git diff --cached --check
git commit -m "chore: initial open source release"
git remote add origin <URL_DO_NOVO_REPOSITORIO>
git push -u origin main
```

Depois crie `dev` a partir de `main`, habilite branch protection e o GitHub Security Advisories. Não copie o bundle de recuperação nem qualquer pasta `.git`.

## Antes de anunciar

- configure o canal privado de vulnerabilidades;
- configure o CI e confirme `pip-audit` sem vulnerabilidades não aceitas;
- valide o deploy de staging com HTTPS e PostgreSQL;
- publique uma versão `v0.1.0-alpha`, deixando o status experimental explícito.
