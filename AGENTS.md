# AGENTS.md

Rules for every coding agent (Claude Code, Codex, Cursor, Copilot and others) in this repo. The rules every
healthtransformationlab repository shares are in [`conventions/AGENTS-common.md`](conventions/AGENTS-common.md),
vendored from here; this file adds only what is specific to pipeline-doctor. `CLAUDE.md` imports both.

## The claim these conventions make

**Conventions do the thinking a small model is too small to do.** A large model can read a raw log dump and
a column called `value` and work out what happened. A small model running on a laptop or a free GPU mostly
cannot: it is weak at *inferring* from messy, incomplete context and fine at *looking up* in tidy context.
So every shared convention is justified by one thing: what it turns from an inference into a lookup for a
small local coding agent fixing a data-pipeline bug. A convention that buys nothing on that test is dropped.

That is a claim about a share, so it is measured, not asserted. The switch-off test (`doctor.ablation`;
"ablation" is the research word for it) hides one convention at a time and records what the agent can still
do without it. PipelineDoctorBench (`pipeline_doctor.kbench`, a Kaggle Benchmarks task) runs the same test
on real models of every size: every incident, under every condition, class and action scored against the
owner's recorded decision, root cause scored by a judge model. The rules are a model on that leaderboard
too (`RulesReader`), so the deterministic rung has its own row.

| Convention (AGENTS-common.md) | What it turns into a lookup | Switch-off condition |
|---|---|---|
| Data names: typed suffixes (`_ts`, `_ratio`, `_usd`, `is_`), singular tables | a column's meaning and unit, from its name, without reading data | `no_conventions` |
| Every run is a row, with the span header; a failure says how it ended; no row data in logs | which run failed, how, and what it cost, from a handful of rows instead of a log dump | `no_metrics`, `no_history` |
| One declaration per setting; a secrets register and dependency inventory with expiry dates | whether a failure is a setting, a credential or a deprecation, before any code is read | `no_config` |
| Lineage as a table | who is affected one hop down, so "hold downstream" is a row, not a guess | `no_lineage` |
| Runbook as a table: one entry per failure class, actions in order | the action is chosen from a list; the agent never invents a verb | always on: it is the answer format |
| Issues, branches and PRs (`000 BUG3`, `fix/<issue>-slug`, `Closes #n`) | where the branch, test, spec and review go, given one issue | measured by the agent's PR passing CI, not by the doctor |
| CI guard tests (`pr_conventions.py`, naming, `@traced`) | a mistake is caught by a test, not by the agent noticing | same |
| Sources-of-truth map in each repo's `AGENTS.md` | which file owns a concern, instead of grepping | same |

Measured today: the first five rows (`doctor.ablation`, `tests/test_doctor.py`, and `RulesReader` on
PipelineDoctorBench). The last three are claims until the same incidents are run through a small local agent
that must also open the PR: that is the measurement planned in `gemma-developer-agent`.

## Project context

DataOps for data pipelines: four metadata tables, a rules-first remediation ladder, graduation to automatic,
a switch-off test of what each table contributes, a forecaster for the failures that are visible in tables
before they happen, and a digest that routes alerts. Python 3.11+, pandas, pytest.

## Mental model

**A failed run's rows from four tables go in; a classified failure and the first allowed runbook action come
out; the rules decide, and the LLM is reserved for `unknown`.**

## Sources of truth (the map)

| Concern | Lives in |
|---|---|
| The four tables and their typed columns | `README.md` ("The four tables"), `doctor.py` (`RUN_COLUMNS`) |
| The six signals and the ladder's classes, in order | `doctor.py` (`SIGNAL_NAMES`, `CLASSES`, `classify`) |
| Recommend and graduation | `doctor.recommend`, `doctor.graduation` |
| The switch-off test and its conditions | `doctor.ABLATIONS`, `doctor.ablation`, `tests/test_doctor.py` |
| Forecasting (secrets register, dependency inventory) | `forecast.py`, `tests/test_forecast.py` |
| Alert routing and digests | `digest.py`, `tests/test_digest.py` |
| PipelineDoctorBench (the switch-off test on real models) | `kbench.py`, `kaggle/pipeline_doctor_task.py`, `tests/test_kbench.py` |
| Tracing (`@traced` shim; adopters swap in theirs) | `_tracing.py` |
| The incident set, config, runbook, lineage | `examples/health-transformation-lab-nlp/` |
| Shared conventions, their version, the PR check, the ADR template | `conventions/` |

## Critical implementation rules

- Every public function gets `@traced` (the shim in `_tracing.py`; adopters replace it).
- `kbench.py` must not use `from __future__ import annotations`: the Kaggle SDK reads each task's real return
  annotation to pick how the leaderboard scores it.
- SDK run files (`*.run.json`, `*.task.json`) are written where a task runs and are gitignored.
- A change to `conventions/` bumps `conventions/VERSION`; the vendoring repos pull by that version.

## Operational commands

```bash
pip install -e ".[dev,kbench]"
pytest -q tests                                 # rules, recommender, switch-off test, forecast, digest, PipelineDoctorBench on scripted models
python kaggle/pipeline_doctor_task.py           # dry run: the rules' real row, then a SIMULATED model row
kaggle b init -y && kaggle b t push pipeline-doctor-triage -f kaggle/pipeline_doctor_task.py --wait   # push to Kaggle Benchmarks
```
