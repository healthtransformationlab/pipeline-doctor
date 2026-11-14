"""pipeline-doctor: DataOps for data pipelines. Four metadata tables, a rules-first remediation ladder,
graduation to automatic, a switch-off test of what each table contributes, and a forecaster for the
failures that have not happened yet (credential expiry, deprecation, duration and cost trends), and cost per run
and per project from Databricks billing."""

from . import billing, digest, doctor, forecast
from .billing import billing_costs, job_projects, project_costs
from .doctor import (
    ABLATIONS,
    CLASSES,
    RUN_COLUMNS,
    SIGNAL_NAMES,
    ablation,
    baseline_history,
    classify,
    evaluate,
    graduation,
    load_config,
    load_incidents,
    load_lineage,
    load_runbook,
    recommend,
    signals,
)
from .forecast import (
    FORECAST_COLUMNS,
    credential_forecast,
    deprecation_forecast,
    forecast_all,
    load_credential_register,
    load_dependency_inventory,
    schema_change_forecast,
    trend_forecast,
    volume_forecast,
)

__all__ = [
    "ABLATIONS",
    "CLASSES",
    "FORECAST_COLUMNS",
    "RUN_COLUMNS",
    "SIGNAL_NAMES",
    "ablation",
    "baseline_history",
    "billing",
    "billing_costs",
    "classify",
    "credential_forecast",
    "deprecation_forecast",
    "digest",
    "doctor",
    "evaluate",
    "forecast",
    "forecast_all",
    "graduation",
    "job_projects",
    "load_config",
    "load_credential_register",
    "load_dependency_inventory",
    "load_incidents",
    "load_lineage",
    "load_runbook",
    "project_costs",
    "recommend",
    "schema_change_forecast",
    "signals",
    "trend_forecast",
    "volume_forecast",
]
__version__ = "0.5.0"
