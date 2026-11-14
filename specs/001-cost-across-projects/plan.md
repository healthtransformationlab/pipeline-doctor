# 001 plan

## US1 and US2 (this pull request)

- `src/pipeline_doctor/billing.py`:
  - `USAGE_SQL`, `PRICES_SQL`: the queries over the billing views (`<schema>.usage`, `<schema>.list_prices`), with
    `usage_metadata.job_id` and `usage_metadata.job_run_id`.
  - `billing_costs(usage, prices)`: moved from health-transformation-lab-nlp `doctor_job.py`, same behaviour: one row
    per job run, `cost_usd` empty when any line is unpriced, `billed_dbu` from DBU lines priced or not, and the
    unpriced SKUs.
  - `job_projects(jobs)`: Jobs API `jobs.list` items -> `{job_id: project_name}` from `settings.tags.project`.
  - `project_costs(usage, prices, projects)`: one row per (`usage_date`, `project_name`, `job_id`) with `cost_usd`,
    `billed_dbu`, `usage_line_count`, and the unpriced SKUs.
- `conventions/AGENTS-common.md`: the `project` tag rule; `conventions/VERSION` 0.2.0 -> 0.3.0.
- Tests first: `tests/test_billing.py`.

## US3 and US4 (later pull requests)

- `databricks/`: bundle with `setup/billing_views.sql` (moved from the NLP lab, catalog parameterised), the job, the
  dashboard. Needs the shared workspace to test.
- Adopter issues in the three repositories.
