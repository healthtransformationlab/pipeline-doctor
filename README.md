# pipeline-doctor

DataOps for data pipelines: four metadata tables, a rules-first remediation ladder, graduation to
automatic, and an ablation that shows what each table buys.

> Personal learning project. Not affiliated with or endorsed by any employer, institution or vendor. The
> example incidents are from a public synthetic-data project; nothing here is any organization's platform,
> incident or plan.

## The thesis

**Automated remediation is ninety percent a metadata problem.** If every pipeline, every run, every
dependency and every rule is already a row in a table, an agent has what it needs to find the cause and
act, and the LLM is the last ten percent, not the first. The agent does not read logs; it reads tables.
Context engineering is choosing which rows.

The anti-pattern this replaces: dumping the whole log into the prompt.

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

1. **Deterministic**: retry with backoff, rerun an idempotent step, hold downstream. No AI.
2. **Classify** by rules, in order: `config`, `platform`, `schema_drift`, `volume_anomaly`, `quality_fail`,
   `cost_anomaly`, `source_late`, `unknown`.
3. **Root cause** by LLM, `unknown` only: the run row, the last N runs, lineage one hop, the runbook entry.
4. **Recommend**: the first allowed action, the impact one hop down the lineage, severity, owner, a
   templated notification. Never an action off the runbook's list. A person approves in one step.
5. **Automate**: a reversible class runs unattended after N matches with the human; two misses send it
   back to recommend-only. The rule is code, not a prompt.

**Agents recommend; code acts.** Anything that changes data goes through an approval step with a fallback
to the old manual path; the loop is drawn tighter where the action is irreversible.

## Is it actually working?

- **Offline:** past incidents with the on-call's final decision are free labels. `evaluate` reports
  classification accuracy (Wilson 95% intervals), action agreement with the human, share resolved without the
  LLM, share with a known impact, and the fields the LLM would have been handed.
- **Online (planned):** mean time to classify, mean time to restore, share of incidents resolved without a
  human, false-page rate. DORA's four, applied to data pipelines.
- **Judge the judge (planned):** the root-cause rung is scored by an LLM judge aligned to human labels, with
  a deterministic no-PHI scorer on every trace, and a candidate ships only if it beats the current one on the
  incident set (champion/challenger).

## The ablation: what each piece of metadata buys

`ablation` re-runs the eval with one piece switched off: the config table, the typed conventions, lineage,
the metrics, the run history. On the example project's nine incidents (small; the intervals say so):

| Condition | Class accuracy (95% CI) | Action agreement | Without the LLM | Impact known | Fields handed to the LLM |
|---|---|---|---|---|---|
| full | 1.00 (0.70–1.00) | 0.78 | 1.00 | 1.00 | 0 |
| no_config | 1.00 (0.70–1.00) | 0.56 | 1.00 | 0.00 | 0 |
| no_conventions | 0.67 (0.35–0.88) | 0.78 | 1.00 | 1.00 | 0 |
| no_lineage | 1.00 (0.70–1.00) | 0.78 | 1.00 | 0.00 | 0 |
| no_metrics | 0.89 (0.56–0.98) | 0.78 | 1.00 | 1.00 | 0 |
| no_history | 0.67 (0.35–0.88) | 0.56 | 0.67 | 1.00 | 372 |

Read: the config table decides the action and the impact; typed conventions and the run history decide the
class; without history a third of the incidents fall to the LLM, each with hundreds of fields of context.

## Use it

```bash
pip install git+https://github.com/healthtransformationlab/pipeline-doctor
```

```python
from pipeline_doctor import doctor
cfg, rb = doctor.load_config("ops/pipeline_config.yaml"), doctor.load_runbook("ops/runbook.yaml")
inc, lin = doctor.load_incidents("data/ops/incident.csv"), doctor.load_lineage("data/ops/lineage_edge.csv")
print(doctor.evaluate(inc, cfg, rb, lin))     # per class and overall
print(doctor.ablation(inc, cfg, rb, lin))     # what each table buys
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
