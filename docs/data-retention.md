# Retenção de dados do Planner

Os dashboards e roadmaps salvos podem conter nomes de pessoas, projetos,
datas, etiquetas e informações operacionais. O período padrão de retenção é
de 365 dias após a última atualização, configurável por
`PLANNER_RETENTION_DAYS`.

O job `scripts/purge_expired_data.py` remove registros antigos de:

- dashboards importados (`reports`);
- roadmaps salvos (`saved_roadmaps`).

Arquivos `.xlsx` enviados são processados em diretório temporário e removidos
ao final do upload. Backups do PostgreSQL devem obedecer ao mesmo período ou a
um período menor definido pela operação.

O job deve ser executado por cron, scheduler ou tarefa de infraestrutura. A
remoção é permanente no banco; faça backup antes de reduzir o período ou rodar
o job pela primeira vez.
