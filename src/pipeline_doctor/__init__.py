"""pipeline-doctor: DataOps for data pipelines. Four metadata tables, a rules-first remediation ladder,
graduation to automatic, and an ablation that shows what each table buys."""

from .doctor import (ABLATIONS, CLASSES, RUN_COLUMNS, SIGNAL_NAMES, ablation, baseline_history, classify, evaluate,
                     graduation, load_config, load_incidents, load_lineage, load_runbook, recommend, signals)

__all__ = ["ABLATIONS", "CLASSES", "RUN_COLUMNS", "SIGNAL_NAMES", "ablation", "baseline_history", "classify",
           "evaluate", "graduation", "load_config", "load_incidents", "load_lineage", "load_runbook", "recommend",
           "signals"]
__version__ = "0.1.0"
