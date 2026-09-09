import pandas as pd

from generate_dashboard import build_scope_quality_metrics


def test_scope_quality_counts_bug_adjustment_without_hu_and_impediments():
    df = pd.DataFrame(
        [
            {
                "labels": ".DEV; NAO PREVISTO; BUGs e Ajustes",
                "bucket": "Backlog Sprint",
                "bucket_norm": "Backlog Sprint",
                "hu": "",
                "done_kpi": False,
            },
            {
                "labels": ".DEV; HU067 - Cadastro [40SP]; BUGs e Ajustes",
                "bucket": "Em Andamento",
                "bucket_norm": "Em Andamento",
                "hu": "HU067",
                "done_kpi": False,
            },
            {
                "labels": ".ARQUITETURA; HU067 - Cadastro [40SP]; IMPEDIMENTO",
                "bucket": "Em Andamento",
                "bucket_norm": "Em Andamento",
                "hu": "HU067",
                "done_kpi": False,
            },
        ]
    )

    metrics = build_scope_quality_metrics(df, {}, {"storypoints": 0, "hu_count": 1})

    assert metrics["bug_task_count"] == 2
    assert metrics["bug_task_with_hu_count"] == 1
    assert metrics["bug_hu_count"] == 1
    assert metrics["bug_density_avg"] == 1.0
    assert ["Fora de HU", 1, "-"] in metrics["bug_rows"]

    assert metrics["impediment_task_count"] == 1
    assert metrics["impediment_task_with_hu_count"] == 1
    assert metrics["impediment_hu_count"] == 1
    assert metrics["impediment_rows"] == [["HU067", 1, 2]]
