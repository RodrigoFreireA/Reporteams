# Contribuindo

Obrigado por contribuir com o ReportChart.

## Ambiente

1. Use Python 3.12 ou superior.
2. Crie um ambiente virtual e instale `requirements.txt`.
3. Copie `.env.example` para `.env`.
4. Execute os testes antes de abrir um PR:

```bash
python -m unittest discover -s tests -p "test_*.py"
```

## Regras

- Não envie `.env`, bancos, logs, exports do Planner, screenshots com dados reais ou credenciais.
- Mudanças de contrato do payload devem atualizar `docs/planner-contracts.md` e os testes.
- Rotas mutáveis precisam manter autenticação, autorização e CSRF.
- Prefira funções puras para regras de domínio e repositórios para persistência.
- Toda mudança deve passar pela suíte de testes e por `git diff --check`.

## Pull requests

Descreva o problema, a solução, os riscos e como validou a mudança. Para alterações visuais, inclua screenshots anonimizadas.

Vulnerabilidades não devem ser abertas como issue pública; siga `SECURITY.md`.
