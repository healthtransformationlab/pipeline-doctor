# 001: Cost and run health across projects

**One place to see what every project costs on Databricks and whether its pipelines are healthy.**

The organisation's projects (health-transformation-lab-nlp, Open Navigator, DE_Assessment) share one Databricks Free
Edition account and its daily limit, but each tracks cost its own way or not at all. The NLP lab prices its runs from
`system.billing`; the others don't. This spec moves that into pipeline-doctor, so every project gets it by adopting
the package and one tag.

## User stories

### US1 - Cost per project per day, from billing (P1) #7

As the owner of several projects on one account, I want each day's cost per project and per job, priced from
Databricks' own billing tables, so I can see which project uses the shared limit and the budget.

- **Done when:** given billing usage lines, list prices and a job-to-project map, `pipeline_doctor.billing` returns one
  row per (usage date, project, job) with `cost_usd` and `billed_dbu`; a line with no list price leaves that row's
  `cost_usd` empty (never zero) and its SKU is named; usage from a job with no project tag counts under
  `project_name = "untagged"`; usage with no job (SQL warehouse, notebooks) counts under `job_id = null`.
- The per-run pricing the NLP lab's doctor job does (`billing_costs`) moves here unchanged in behaviour.

### US2 - One tag per project (P1) #8

As an adopting project, I want one convention for marking my jobs, so billing can be split without a lookup table.

- **Done when:** `conventions/AGENTS-common.md` says every Databricks job carries the tag `project` (the repository
  name), and `pipeline_doctor.billing.job_projects` reads it from Jobs API job settings.

### US3 - The ops console (P2) #9

As the owner, I want one dashboard: cost by project and day against a budget, each pipeline's run health (freshness,
volume, failed checks, duration), and the forecasts (credentials, cost crossing the budget).

- **Done when:** a Databricks bundle in this repo deploys the billing views, a daily job that writes
  `fact_project_cost_daily` and `fact_pipeline_run` for every job in the workspace, and an AI/BI dashboard over them.

### US4 - Adopt it in each project (P2) #10

As each project, I want to drop my own cost code and use this, so there is one implementation.

- **Done when:** health-transformation-lab-nlp imports `billing_costs` from pipeline-doctor; Open Navigator and
  DE_Assessment tag their jobs with `project`. One issue per repository.

## Out of scope

Billing across separate Databricks accounts (each account needs its own views); paid-account features Free Edition
lacks (`system.lakeflow` run history, account console).
