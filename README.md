# pipeline-doctor

DataOps for data pipelines: four metadata tables, a rules-first remediation ladder, graduation to
automatic, and a switch-off test that measures what each table contributes.

> Personal learning project. Not affiliated with or endorsed by any employer, institution or vendor. The
> example incidents are from a public synthetic-data project; nothing here is any organization's platform,
> incident or plan.

## The claim, in one table

Most of what breaks in production is a configuration problem, not a code problem, and it shows up in
tables before it shows up in logs. So an agent that reads the tables first fixes most incidents by rules.
That is a claim about a share, so it is measured: hide each ingredient and record what the rules can still do.

| Ingredient | In one line | Hide it and… |
|---|---|---|
| Metadata-driven | pipelines, runs, lineage, runbook are tables | no failure's impact can be named |
| Conventions | typed names; every change traced to an issue | classification drops from 100% to 67% |
| Configuration management | one place per setting; credentials and dependencies with expiry dates | expiry and drift become invisible |
| Telemetry | every call records timing and cost | cost anomalies vanish |
| Forecasting | the four above predict failures, with a date | you only hear about it after it breaks |

<details>
<summary>What this replaces</summary>

Dumping the whole log into the prompt. Context engineering is choosing which rows; with the tables above
the LLM is reserved for what the rules cannot name.

</details>

## The four tables (the agent's entire context)

| Table | One row per | Their word for it |
|---|---|---|
| `dim_pipeline` | pipeline: owner, SLA, expectations, retry policy, outputs, runbook pointer | reusable patterns, standards |
| `fact_pipeline_run` | run or step: timings, counts, schema hash, checks passed and failed, error type, duration, cost | observability |
| `dim_lineage_edge` | edge: what feeds what, who consumes it | impact assessment |
| `dim_runbook_entry` | failure class: ordered allowed actions, reversible, severity, escalation | operational decisioning |

Plus `fact_remediation_decision`: one row per recommendation with the human's decision and whether it
matched. Column names are typed (`_name`, `_code`, `_ts`, `_count`, `_ratio`, `_seconds`, `_usd`, `is_`),
and the ablation below is the evidence that the typing is load-bearing.

## The six signals

Per run, against the pipeline's trailing ok runs: **freshness** (against the SLA), **volume**, **schema**,
**quality** (share of checks passed), **duration** and **cost**. Duration and cost are OpenTelemetry metrics
(`pipeline.run.duration_seconds`, `pipeline.run.cost_usd`) carrying the span header (service, data product,
environment), so the full cost of a run across the stack is one group-by. Tracked per table, alerted on
deviation, visible to consumers, not just engineers.

## The ladder (one failure class at a time)

The ladder handles failures that have happened; the forecaster (below) handles the ones that have not yet.

1. **Deterministic**: retry with backoff, rerun an idempotent step, hold downstream. No AI.
2. **Classify** by rules, in order. Configuration-management classes first: `credential_expiry`,
   `vulnerability`, `deprecation`, `config_drift`, `config`. Then `platform`, `schema_drift`,
   `volume_anomaly`, `quality_fail`, `cost_anomaly`, `source_late`, `unknown`.
3. **Root cause** by LLM, `unknown` only: the run row, the last N runs, lineage one hop, the runbook entry.
4. **Recommend**: the first allowed action, the impact one hop down the lineage, severity, owner, a
   templated notification. Never an action off the runbook's list. A person approves in one step.
5. **Automate**: a reversible class runs unattended after N matches with the human; two misses send it
   back to recommend-only. The rule is code, not a prompt.

**Agents recommend; code acts.** Anything that changes data goes through an approval step with a fallback
to the old manual path; the loop is drawn tighter where the action is irreversible.

## Forecasting: the failure before it happens

A log can only say what broke. The same tables say what is about to break, and when. `forecast` reads a
credential register (expiry dates, never values), a dependency inventory (end-of-support dates for models,
packages, endpoints) and the run table's duration and cost trend, and returns alert rows: subject, predicted
failure class, predicted date, days until, severity from the days ladder (SEV2 within 7 days, SEV3 within
30, SEV4 within 90, SEV1 once past), owner, action, evidence. An unknown expiry is itself a SEV4 finding.
A cost line that crosses the budget in three runs is a `cost_anomaly` three days out, not a surprise on the
invoice; a feed shrinking toward half its baseline is a `volume_anomaly` with a date; a schema hash that
changed twice in the last ten runs is a `schema_drift` advisory to set the schema mode deliberately; a
dependency marked deprecated with no date is a SEV3 to plan the replacement. Performance and cost are OpenTelemetry metrics on every run, so the trend is always there to read.

```python
from pipeline_doctor import forecast
reg = forecast.load_credential_register("ops/secrets_register.yaml")
print(forecast.forecast_all(cfg, "2026-10-29", register=reg, history=runs))
```

## Alerting: route now, batch the rest

Every row from the doctor or the forecaster is an alert with a severity, an owner and an action. `digest`
routes them by the ladder: SEV1 and SEV2 go out now, one message each; SEV3 into a daily digest; SEV4 into
a weekly one. A digest is one message per owner per period, grouped by severity then subject, each problem
once with a count and the pipelines it touches, carried until closed; a SEV2 still open at the next digest
is flagged "fix the cause or lower the level". `render` writes the plain-text message; sending it (email,
chat) is the adopting project's job.

## Is it actually working?

- **Offline:** past incidents with the on-call's final decision are free labels, fifty to a few hundred to start. `evaluate` reports
  classification accuracy (Wilson 95% intervals), action agreement with the human, share resolved without the
  LLM, share with a known impact, and the fields the LLM would have been handed.
- **Online (planned):** mean time to classify, mean time to restore, share of incidents resolved without a
  human, false-page rate. DORA's four, applied to data pipelines.
- **Judge the judge (planned):** the root-cause rung is scored by an LLM judge aligned to human labels, with
  a deterministic no-PHI scorer on every trace, and a candidate ships only if it beats the current one on the
  incident set (champion/challenger).

## The switch-off test: what each table contributes

`ablation` (the ML term for this) re-runs the eval with one piece hidden from the doctor: the config table,
the typed naming conventions, lineage, the OpenTelemetry metrics, the run history. Whatever drops is what
that piece was doing. On the example project's nine incidents (a small set; the intervals say so):

| Condition | Class accuracy (95% CI) | Action agreement | Without the LLM | Impact known | Fields handed to the LLM |
|---|---|---|---|---|---|
| full | 1.00 (0.70–1.00) | 0.78 | 1.00 | 1.00 | 0 |
| no_config | 1.00 (0.70–1.00) | 0.56 | 1.00 | 0.00 | 0 |
| no_conventions | 0.67 (0.35–0.88) | 0.78 | 1.00 | 1.00 | 0 |
| no_lineage | 1.00 (0.70–1.00) | 0.78 | 1.00 | 0.00 | 0 |
| no_metrics | 0.89 (0.56–0.98) | 0.78 | 1.00 | 1.00 | 0 |
| no_history | 0.67 (0.35–0.88) | 0.56 | 0.67 | 1.00 | 372 |

Read: hide the config table and no failure's impact can be named; hide the typed naming conventions and
classification drops from 100% to 67%; hide the run history and a third of the incidents go to the LLM, each
with hundreds of fields of context. The example set has no rows yet for the four configuration-management
classes: adding a project's real credential, deprecation and drift incidents is the next step, and the
share they make up is the number the paper reports.

## Use it

```bash
pip install git+https://github.com/healthtransformationlab/pipeline-doctor
```

```python
from pipeline_doctor import doctor
cfg, rb = doctor.load_config("ops/pipeline_config.yaml"), doctor.load_runbook("ops/runbook.yaml")
inc, lin = doctor.load_incidents("data/ops/incident.csv"), doctor.load_lineage("data/ops/lineage_edge.csv")
print(doctor.evaluate(inc, cfg, rb, lin))     # per class and overall
print(doctor.ablation(inc, cfg, rb, lin))     # the switch-off test
```

An adopting project supplies the four files (examples in `examples/`), points `doctor.traced` at its own
OpenTelemetry decorator if it has one, and adds a row to its incident set whenever something breaks. The
first adopter is [health-transformation-lab-nlp](https://github.com/healthtransformationlab/health-transformation-lab-nlp)
(spec 027); the second is the coding-agent task set in
[gemma-developer-agent](https://github.com/healthtransformationlab/gemma-developer-agent).

## Vocabulary bridge

logging → observability · process → operational decisioning · metadata-driven → reusable patterns, the
context layer · a runbook → next best action · a human approving → human review and fallback paths.

MIT. Owner John Bowyer.
