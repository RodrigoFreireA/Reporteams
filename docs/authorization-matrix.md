# Matriz de autorização

As permissões são aplicadas no backend. A interface apenas esconde ações que o usuário não pode executar.

| Área | Anônimo | Usuário autenticado | Administrador |
|---|---|---|---|
| Landing e login | leitura | leitura | leitura |
| Dashboard, biblioteca, upload e roadmaps | não | próprio usuário | próprio usuário |
| Associação dashboard/equipe | não | equipes visíveis ao usuário | todas as equipes visíveis |
| Equipes | não | equipes próprias ou em que participa | equipes administráveis |
| Membros de equipe | não | conforme papel `owner`/`admin` | conforme papel global |
| Usuários administrativos | não | não | sim |
| Gráficos customizados e regras de perfil | não | leitura | criar, editar e remover |
| Layouts e versões | não | próprios layouts e relatórios próprios | próprios recursos |

## Regras obrigatórias

- Toda rota mutável exige sessão e CSRF.
- Recursos persistidos são buscados pelo identificador junto ao proprietário ou escopo permitido.
- Usuários desabilitados não podem iniciar nem manter sessão válida.
- Ser administrador global não elimina a validação de existência, estado ativo ou formato do recurso.
- O frontend não é fonte de autorização; respostas `401` e `403` devem ser tratadas como comportamento esperado.

Os fluxos principais estão cobertos por `tests/test_security_flows.py`. Novos endpoints devem adicionar um caso de acesso permitido e um caso de acesso negado.
