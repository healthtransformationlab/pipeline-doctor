# Review: PR #11, 001 US1 + US2

**Verdict:** approve.

- `billing_costs` keeps the NLP lab's behaviour: list price in effect by SKU and unit, empty cost (not zero) when any
  line is unpriced, DBUs counted priced or not. Lines without a run are dropped in the function as well as the query.
- `project_costs` keeps no-job usage separate (job_id null) under `untagged`, so warehouse and notebook cost isn't
  hidden or pinned on a job.
- Conventions change bumps `conventions/VERSION` (AGENTS.md rule). Every new public function has `@traced`.
- Tests first: 7 new, 53 passed in all.

**Nit:** two stories in one PR (#7, #8); they share one module and one test file.
