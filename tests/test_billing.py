"""Cost from Databricks billing, per run and per project per day (spec 001 US1, US2)."""

import math

import pandas as pd

from pipeline_doctor import billing

PRICES = pd.DataFrame([
    {"sku_name": "JOBS_SERVERLESS", "usage_unit": "DBU", "price_usd": 0.35,
     "price_start_time": "2026-01-01T00:00:00Z", "price_end_time": "2026-11-01T00:00:00Z"},
    {"sku_name": "JOBS_SERVERLESS", "usage_unit": "DBU", "price_usd": 0.40,
     "price_start_time": "2026-11-01T00:00:00Z", "price_end_time": None},
    {"sku_name": "SQL_SERVERLESS", "usage_unit": "DBU", "price_usd": 0.70,
     "price_start_time": "2026-01-01T00:00:00Z", "price_end_time": None},
])


def usage(rows):
    cols = ["job_id", "job_run_id", "sku_name", "usage_unit", "usage_quantity", "usage_start_time", "usage_date"]
    return pd.DataFrame(rows, columns=cols)


def test_a_run_is_priced_at_the_list_price_in_effect_when_it_ran():
    u = usage([
        ["1", "r1", "JOBS_SERVERLESS", "DBU", 2.0, "2026-10-31T23:00:00Z", "2026-10-31"],
        ["1", "r1", "JOBS_SERVERLESS", "DBU", 1.0, "2026-11-01T01:00:00Z", "2026-11-01"],
    ])
    costs, missing = billing.billing_costs(u, PRICES)
    row = costs.set_index("run_id").loc["r1"]
    assert math.isclose(row["cost_usd"], 2.0 * 0.35 + 1.0 * 0.40)
    assert math.isclose(row["billed_dbu"], 3.0)
    assert missing == []


def test_a_run_with_an_unpriced_line_has_no_cost_and_the_sku_is_named():
    u = usage([
        ["1", "r1", "JOBS_SERVERLESS", "DBU", 2.0, "2026-11-02T00:00:00Z", "2026-11-02"],
        ["1", "r1", "GPU_SERVERLESS", "DBU", 1.0, "2026-11-02T00:00:00Z", "2026-11-02"],
    ])
    costs, missing = billing.billing_costs(u, PRICES)
    row = costs.set_index("run_id").loc["r1"]
    assert math.isnan(row["cost_usd"])
    assert math.isclose(row["billed_dbu"], 3.0)
    assert missing == ["GPU_SERVERLESS"]


def test_no_usage_gives_no_costs():
    costs, missing = billing.billing_costs(usage([]), PRICES)
    assert costs.empty and list(costs.columns) == ["run_id", "cost_usd", "billed_dbu"]
    assert missing == []


def test_job_projects_reads_the_project_tag():
    jobs = [
        {"job_id": 11, "settings": {"name": "a", "tags": {"project": "open-navigator"}}},
        {"job_id": 12, "settings": {"name": "b", "tags": {"other": "x"}}},
        {"job_id": 13, "settings": {"name": "c"}},
    ]
    assert billing.job_projects(jobs) == {"11": "open-navigator"}


def test_project_costs_are_one_row_per_day_project_and_job():
    u = usage([
        ["11", "r1", "JOBS_SERVERLESS", "DBU", 2.0, "2026-11-02T00:00:00Z", "2026-11-02"],
        ["11", "r2", "JOBS_SERVERLESS", "DBU", 1.0, "2026-11-02T05:00:00Z", "2026-11-02"],
        ["12", "r3", "JOBS_SERVERLESS", "DBU", 4.0, "2026-11-02T00:00:00Z", "2026-11-02"],
        [None, None, "SQL_SERVERLESS", "DBU", 1.0, "2026-11-03T00:00:00Z", "2026-11-03"],
    ])
    costs, missing = billing.project_costs(u, PRICES, {"11": "open-navigator"})
    assert missing == []
    rows = {(str(r.usage_date), r.project_name, r.job_id): r for r in costs.itertuples()}
    on = rows[("2026-11-02", "open-navigator", "11")]
    assert math.isclose(on.cost_usd, 3.0 * 0.40) and on.usage_line_count == 2
    assert math.isclose(rows[("2026-11-02", "untagged", "12")].cost_usd, 4.0 * 0.40)
    no_job = [r for k, r in rows.items() if k[0] == "2026-11-03"]
    assert len(no_job) == 1 and no_job[0].project_name == "untagged" and pd.isna(no_job[0].job_id)
    assert math.isclose(no_job[0].cost_usd, 0.70)


def test_an_unpriced_line_leaves_that_days_project_cost_empty():
    u = usage([
        ["11", "r1", "JOBS_SERVERLESS", "DBU", 2.0, "2026-11-02T00:00:00Z", "2026-11-02"],
        ["11", "r1", "GPU_SERVERLESS", "DBU", 1.0, "2026-11-02T00:00:00Z", "2026-11-02"],
    ])
    costs, missing = billing.project_costs(u, PRICES, {"11": "open-navigator"})
    assert math.isnan(costs.iloc[0]["cost_usd"]) and math.isclose(costs.iloc[0]["billed_dbu"], 3.0)
    assert missing == ["GPU_SERVERLESS"]


def test_the_usage_query_reads_the_job_and_the_run():
    sql = billing.USAGE_SQL.format(schema="ops.billing", days=7)
    assert "usage_metadata.job_id" in sql and "usage_metadata.job_run_id" in sql and "ops.billing.usage" in sql
