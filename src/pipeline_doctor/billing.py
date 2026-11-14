"""Cost from Databricks billing (spec 001): per job run, and per project per day.

Reads views over `system.billing.usage` and `system.billing.list_prices` (a workspace owner makes them once; their
reader needs no grant on `system.billing` itself). A line is priced at the list price in effect when it was used,
for the same SKU and unit. Anything with an unpriced line gets no cost at all, never a partial one, and the SKUs are
returned to be named. Projects come from each job's `project` tag (conventions/AGENTS-common.md).

`billing_costs` moved here from health-transformation-lab-nlp's doctor job, unchanged in behaviour.
"""

from __future__ import annotations

import pandas as pd

from ._tracing import traced

UNTAGGED = "untagged"
PROJECT_TAG = "project"

USAGE_SQL = """
select usage_metadata.job_id as job_id, usage_metadata.job_run_id as job_run_id,
       sku_name, usage_unit, usage_quantity, usage_start_time, usage_date
from {schema}.usage
where usage_date >= current_date() - interval {days} days
"""
PRICES_SQL = """
select sku_name, usage_unit, cast(pricing.default as double) as price_usd, price_start_time, price_end_time
from {schema}.list_prices
where currency_code = 'USD'
"""


def _priced(usage: pd.DataFrame, prices: pd.DataFrame) -> pd.DataFrame:
    """Usage lines with `line_usd` (null when unpriced) and `line_dbu` (DBU lines, priced or not)."""
    u = usage.assign(_row=range(len(usage)))
    u["usage_start_time"] = pd.to_datetime(u["usage_start_time"], utc=True)
    p = prices.assign(price_start_time=pd.to_datetime(prices["price_start_time"], utc=True),
                      price_end_time=pd.to_datetime(prices["price_end_time"], utc=True))
    m = u.merge(p, on=["sku_name", "usage_unit"], how="left")
    inside = (m["price_start_time"] <= m["usage_start_time"]) & (
        m["price_end_time"].isna() | (m["usage_start_time"] < m["price_end_time"]))
    priced = m[inside].drop_duplicates("_row")
    u = u.merge(priced[["_row", "price_usd"]], on="_row", how="left")
    u["line_usd"] = u["usage_quantity"].astype(float) * u["price_usd"]
    u["line_dbu"] = u["usage_quantity"].astype(float).where(u["usage_unit"].astype(str).str.upper() == "DBU", 0.0)
    return u


def _sum_or_nan(s: pd.Series) -> float:
    return s.sum() if s.notna().all() else float("nan")


def _missing(u: pd.DataFrame) -> list[str]:
    return sorted(u.loc[u["price_usd"].isna(), "sku_name"].astype(str).unique())


@traced
def billing_costs(usage: pd.DataFrame, prices: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """Each job run's cost and DBUs, and the SKUs no price covers. Lines without a run are left out."""
    if usage is None or not len(usage):
        return pd.DataFrame(columns=["run_id", "cost_usd", "billed_dbu"]), []
    u = _priced(usage[usage["job_run_id"].notna()], prices)
    if not len(u):
        return pd.DataFrame(columns=["run_id", "cost_usd", "billed_dbu"]), []
    u["run_id"] = u["job_run_id"].astype(str)
    g = u.groupby("run_id")
    costs = g["line_usd"].agg(_sum_or_nan).rename("cost_usd").to_frame()
    costs["billed_dbu"] = g["line_dbu"].sum()
    return costs.reset_index(), _missing(u)


@traced
def job_projects(jobs: list[dict]) -> dict[str, str]:
    """Jobs API `jobs.list` items -> {job_id: project}, from each job's `project` tag. Untagged jobs are left out."""
    out = {}
    for job in jobs or []:
        tags = (job.get("settings") or {}).get("tags") or {}
        if tags.get(PROJECT_TAG):
            out[str(job["job_id"])] = str(tags[PROJECT_TAG])
    return out


@traced
def project_costs(usage: pd.DataFrame, prices: pd.DataFrame,
                  projects: dict[str, str]) -> tuple[pd.DataFrame, list[str]]:
    """One row per (usage_date, project_name, job_id): cost_usd, billed_dbu, usage_line_count; and unpriced SKUs.

    A job without a project tag, and usage with no job (SQL warehouse, notebooks), count as `untagged`; the latter
    keeps job_id null so it isn't mistaken for a job.
    """
    cols = ["usage_date", "project_name", "job_id", "cost_usd", "billed_dbu", "usage_line_count"]
    if usage is None or not len(usage):
        return pd.DataFrame(columns=cols), []
    u = _priced(usage, prices)
    u["job_id"] = u["job_id"].where(u["job_id"].notna(), None)
    u["job_id"] = u["job_id"].map(lambda j: None if j is None or pd.isna(j) else str(j))
    u["project_name"] = u["job_id"].map(lambda j: projects.get(j, UNTAGGED) if j else UNTAGGED)
    u["usage_date"] = pd.to_datetime(u["usage_date"]).dt.date
    u["_job"] = u["job_id"].fillna("")   # groupby drops nulls; the empty key stands for "no job"
    g = u.groupby(["usage_date", "project_name", "_job"])
    out = pd.DataFrame({
        "cost_usd": g["line_usd"].agg(_sum_or_nan),
        "billed_dbu": g["line_dbu"].sum(),
        "usage_line_count": g.size(),
    }).reset_index()
    out["job_id"] = out["_job"].replace("", None)
    return out[cols], _missing(u)
