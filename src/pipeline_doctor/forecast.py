"""Forecast failures before they happen, from the same tables.

A log can only tell you what broke. Three tables tell you what is about to break, and when:

    credential register   one row per credential with an expiry date (never a value): a credential that
                          expires in N days is a `credential_expiry` failure on that date for every pipeline
                          that uses it. "unknown" expiry is itself a finding.
    dependency inventory  one row per model, package or endpoint with an end-of-support or deprecation date:
                          a `deprecation` failure on that date.
    run table trend       duration and cost over the trailing ok runs: a line through them says when a
                          pipeline will breach its SLA or its budget (`cost_anomaly` / `source_late`).

Severity follows the days-to-event ladder (SEV2 within 7 days, SEV3 within 30, SEV4 within 90; SEV1 when
the date has passed for a scheduled pipeline), so a forecast row is an alert with an owner and an action,
not a guess.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from ._tracing import traced

FORECAST_COLUMNS = ["subject_name", "subject_kind_code", "pipeline_name", "predicted_failure_class_code",
                    "predicted_date", "days_until_count", "severity_code", "recommended_action_code", "owner_name",
                    "evidence_text"]
LADDER_DAYS = ((7, "SEV2"), (30, "SEV3"), (90, "SEV4"))


def _date(x):
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return None
    if isinstance(x, str) and x.strip().lower() in ("never", "unknown", "", "none"):
        return None
    t = pd.to_datetime(x, errors="coerce")
    return None if pd.isna(t) else pd.Timestamp(t).tz_localize(None).normalize()


def _severity(days: float | None, is_scheduled: bool = True) -> str | None:
    if days is None:
        return None
    if days < 0:
        return "SEV1" if is_scheduled else "SEV2"
    for limit, sev in LADDER_DAYS:
        if days <= limit:
            return sev
    return None


@traced
def load_credential_register(path: str | Path) -> pd.DataFrame:
    """A secrets register as `ops/secrets_register.yaml` keeps it: `credentials:` with `name`, `expires`
    (date, never or unknown), `owner`, `used_by`, `if_it_expires`. Values are never present or read."""
    raw = yaml.safe_load(Path(path).read_text())["credentials"]
    rows = [{"credential_name": c["name"], "expires_text": str(c.get("expires", "unknown")),
             "owner_name": c.get("owner"), "used_by_text": str(c.get("used_by", "")),
             "if_it_expires_text": c.get("if_it_expires", "")} for c in raw]
    return pd.DataFrame(rows)


@traced
def load_dependency_inventory(path: str | Path) -> pd.DataFrame:
    """One row per model, package or endpoint: `dependency_name`, `dependency_kind_code`, `end_of_support_date`
    (date or empty), `used_by_text`, `owner_name`."""
    return pd.read_csv(path, dtype={"end_of_support_date": "string"})


@traced
def credential_forecast(register: pd.DataFrame, config: pd.DataFrame, today) -> pd.DataFrame:
    """One forecast row per (credential, pipeline that uses it): when it expires, how many days away, the
    severity from the ladder, and `fix_setting` as the action. Unknown expiry is a SEV4 finding."""
    today = _date(today)
    rows = []
    for _, c in register.iterrows():
        exp = _date(c["expires_text"])
        users = [p for p in config["pipeline_name"] if p in c["used_by_text"]] or [None]
        for p in users:
            if exp is None:
                unknown = c["expires_text"].strip().lower() == "unknown"
                if not unknown:
                    continue
                rows.append({"subject_name": c["credential_name"], "subject_kind_code": "credential",
                             "pipeline_name": p, "predicted_failure_class_code": "credential_expiry",
                             "predicted_date": None, "days_until_count": None, "severity_code": "SEV4",
                             "recommended_action_code": "fix_setting", "owner_name": c["owner_name"],
                             "evidence_text": "expiry unknown: look it up where the credential was made and record it"})
                continue
            days = (exp - today).days
            sev = _severity(days)
            if sev is None:
                continue
            rows.append({"subject_name": c["credential_name"], "subject_kind_code": "credential",
                         "pipeline_name": p, "predicted_failure_class_code": "credential_expiry",
                         "predicted_date": exp.date().isoformat(), "days_until_count": days, "severity_code": sev,
                         "recommended_action_code": "fix_setting", "owner_name": c["owner_name"],
                         "evidence_text": f"expires {exp.date().isoformat()}; {c['if_it_expires_text']}"})
    return pd.DataFrame(rows, columns=FORECAST_COLUMNS)


@traced
def deprecation_forecast(inventory: pd.DataFrame, config: pd.DataFrame, today) -> pd.DataFrame:
    """One row per (dependency with an end-of-support date, pipeline that uses it)."""
    today = _date(today)
    rows = []
    for _, d in inventory.iterrows():
        eos = _date(d.get("end_of_support_date"))
        if eos is None:
            continue
        users = [p for p in config["pipeline_name"] if p in str(d.get("used_by_text", ""))] or [None]
        days = (eos - today).days
        sev = _severity(days)
        if sev is None:
            continue
        for p in users:
            rows.append({"subject_name": d["dependency_name"], "subject_kind_code": d.get("dependency_kind_code", "dependency"),
                         "pipeline_name": p, "predicted_failure_class_code": "deprecation",
                         "predicted_date": eos.date().isoformat(), "days_until_count": days, "severity_code": sev,
                         "recommended_action_code": "hold_downstream", "owner_name": d.get("owner_name"),
                         "evidence_text": f"end of support {eos.date().isoformat()}"})
    return pd.DataFrame(rows, columns=FORECAST_COLUMNS)


def _slope(y: np.ndarray) -> float:
    if len(y) < 3 or np.allclose(y, y[0]):
        return 0.0
    x = np.arange(len(y), dtype=float)
    return float(np.polyfit(x, y, 1)[0])


@traced
def trend_forecast(history: pd.DataFrame, config: pd.DataFrame, today, n: int = 10) -> pd.DataFrame:
    """Per pipeline, a line through the last `n` ok runs' duration and cost. If the line crosses the
    pipeline's `max_duration_seconds` or `budget_usd` (optional config columns) within 90 days, that is a
    forecast row; the date assumes the pipeline's recent cadence (median gap between ok runs)."""
    today = _date(today)
    rows = []
    for _, c in config.iterrows():
        h = history[(history["pipeline_name"] == c["pipeline_name"]) & (history["run_status_code"] == "ok")]
        if len(h) < 3:
            continue
        h = h.assign(_t=pd.to_datetime(h["ended_ts"], utc=True)).sort_values("_t").tail(n)
        gaps = h["_t"].diff().dropna().dt.total_seconds() / 86400
        cadence_days = float(gaps.median()) if len(gaps) else 1.0
        for col, limit_col, cls, action in (("duration_seconds", "max_duration_seconds", "source_late", "hold_downstream"),
                                            ("cost_usd", "budget_usd", "cost_anomaly", "hold_downstream")):
            if col not in h or limit_col not in c or pd.isna(c[limit_col]):
                continue
            y = pd.to_numeric(h[col], errors="coerce").dropna().to_numpy(dtype=float)
            if len(y) < 3:
                continue
            slope, last, limit = _slope(y), float(y[-1]), float(c[limit_col])
            if last >= limit:
                runs_to_breach = 0.0
            elif slope <= 0:
                continue
            else:
                runs_to_breach = (limit - last) / slope
            days = runs_to_breach * max(cadence_days, 0.0)
            sev = _severity(days)
            if sev is None:
                continue
            when = (today + pd.Timedelta(days=days)).date().isoformat()
            rows.append({"subject_name": c["pipeline_name"], "subject_kind_code": "pipeline",
                         "pipeline_name": c["pipeline_name"], "predicted_failure_class_code": cls,
                         "predicted_date": when, "days_until_count": round(days), "severity_code": sev,
                         "recommended_action_code": action, "owner_name": c.get("owner_name"),
                         "evidence_text": f"{col} last {last:.3g}, limit {limit:.3g}, slope {slope:+.3g} per run over {len(y)} runs"})
    return pd.DataFrame(rows, columns=FORECAST_COLUMNS)


@traced
def forecast_all(config: pd.DataFrame, today, register: pd.DataFrame | None = None,
             inventory: pd.DataFrame | None = None, history: pd.DataFrame | None = None) -> pd.DataFrame:
    """All forecasts, soonest first. Each row is an alert: subject, predicted class and date, severity,
    owner, action, evidence."""
    parts = []
    if register is not None and len(register):
        parts.append(credential_forecast(register, config, today))
    if inventory is not None and len(inventory):
        parts.append(deprecation_forecast(inventory, config, today))
    if history is not None and len(history):
        parts.append(trend_forecast(history, config, today))
    if not parts:
        return pd.DataFrame(columns=FORECAST_COLUMNS)
    out = pd.concat(parts, ignore_index=True)
    order = out["days_until_count"].fillna(10**6)
    return out.assign(_o=order).sort_values(["_o", "severity_code"]).drop(columns="_o").reset_index(drop=True)
