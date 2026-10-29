"""Route and batch alerts: the digest rule as code.

Every alert names a severity, an owner and an action (a forecast row or a remediation recommendation).
Routing follows the severity ladder:

    SEV1, SEV2   go out now, one message each, to the owner
    SEV3         the daily digest
    SEV4         the weekly digest

A digest is one message per owner per period: grouped by severity then by subject kind, each problem
once (same subject and failure class) with a count and the soonest date, carried until it is closed. A SEV2
that fires every period for the same cause is flagged: fix the cause or lower the level.
"""

from __future__ import annotations

import pandas as pd

from ._tracing import traced

ROUTE = {"SEV1": "now", "SEV2": "now", "SEV3": "daily", "SEV4": "weekly"}
ALERT_COLUMNS = ["subject_name", "subject_kind_code", "pipeline_name", "predicted_failure_class_code", "predicted_date",
                 "days_until_count", "severity_code", "recommended_action_code", "owner_name", "evidence_text"]
KEY = ["owner_name", "subject_name", "predicted_failure_class_code"]


@traced
def route(alerts: pd.DataFrame) -> pd.DataFrame:
    """Add `route_code` (now / daily / weekly) from the severity; unknown severities go to weekly."""
    out = alerts.copy()
    out["route_code"] = out["severity_code"].map(ROUTE).fillna("weekly")
    return out


@traced
def dedupe(alerts: pd.DataFrame) -> pd.DataFrame:
    """One row per (owner, subject, class): the highest severity, the soonest date, how many pipelines or
    rows it covers, and the pipelines named."""
    if alerts.empty:
        return alerts.assign(alert_count=pd.Series(dtype=int), pipeline_names_text=pd.Series(dtype=str))
    sev_rank = {"SEV1": 1, "SEV2": 2, "SEV3": 3, "SEV4": 4}
    a = alerts.assign(_rank=alerts["severity_code"].map(sev_rank).fillna(9),
                      _days=alerts["days_until_count"].fillna(10**6))
    a = a.sort_values(["_rank", "_days"])
    g = a.groupby(KEY, dropna=False, sort=False)
    first = g.head(1).set_index(KEY)
    first["alert_count"] = g.size()
    first["pipeline_names_text"] = g["pipeline_name"].apply(
        lambda s: ", ".join(sorted({str(x) for x in s.dropna()})) or "")
    return first.reset_index().drop(columns=["_rank", "_days"])


@traced
def digest(alerts: pd.DataFrame, period_code: str, open_since: pd.DataFrame | None = None) -> pd.DataFrame:
    """The rows for one period's digest (`daily` or `weekly`), deduplicated, plus any still-open rows from
    `open_since` (an earlier digest's rows not yet closed), with `is_repeat` set on those. A SEV2 that
    repeats is flagged `is_level_review` (fix the cause or lower the level)."""
    r = route(alerts)
    now = r[r["route_code"] == period_code]
    d = dedupe(now)
    d["is_repeat"] = False
    if open_since is not None and len(open_since):
        o = dedupe(open_since)
        o["is_repeat"] = True
        d = pd.concat([d, o[~o.set_index(KEY).index.isin(d.set_index(KEY).index)]], ignore_index=True)
    d["is_level_review"] = d["is_repeat"] & (d["severity_code"] == "SEV2")
    order = {"SEV1": 1, "SEV2": 2, "SEV3": 3, "SEV4": 4}
    return d.assign(_o=d["severity_code"].map(order).fillna(9)) \
            .sort_values(["owner_name", "_o", "subject_kind_code", "subject_name"]).drop(columns="_o") \
            .reset_index(drop=True)


@traced
def immediate(alerts: pd.DataFrame) -> pd.DataFrame:
    """SEV1 and SEV2 rows, one per (owner, subject, class), to go out now."""
    r = route(alerts)
    return dedupe(r[r["route_code"] == "now"]).reset_index(drop=True)


@traced
def render(rows: pd.DataFrame, period_code: str) -> dict[str, str]:
    """One plain-text message per owner: grouped by severity then subject kind, each line with its action,
    date and evidence. Returns {owner_name: text}."""
    out = {}
    for owner, g in rows.groupby("owner_name", dropna=False, sort=True):
        lines = [f"{period_code} digest for {owner}: {len(g)} open item(s)"]
        for sev, gs in g.groupby("severity_code", sort=True):
            lines.append(f"\n{sev}")
            for kind, gk in gs.groupby("subject_kind_code", sort=True):
                lines.append(f"  {kind}")
                for _, row in gk.iterrows():
                    when = f" by {row['predicted_date']}" if pd.notna(row.get("predicted_date")) else ""
                    count = f" ×{int(row['alert_count'])}" if row.get("alert_count", 1) > 1 else ""
                    repeat = " (repeat; fix the cause or lower the level)" if row.get("is_level_review") else \
                             (" (repeat)" if row.get("is_repeat") else "")
                    pipes = f" [{row['pipeline_names_text']}]" if row.get("pipeline_names_text") else ""
                    lines.append(f"    - {row['subject_name']}{pipes}: {row['predicted_failure_class_code']}{when}{count}"
                                 f" → {row['recommended_action_code']}{repeat}. {row['evidence_text']}")
        out[str(owner)] = "\n".join(lines)
    return out
