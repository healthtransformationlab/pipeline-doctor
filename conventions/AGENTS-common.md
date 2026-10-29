# AGENTS-common.md

Rules shared by every repository in this organisation, vendored from
[pipeline-doctor/conventions](https://github.com/healthtransformationlab/pipeline-doctor/tree/main/conventions)
(version in `VERSION`). A repository's own `AGENTS.md` adds to these; it never weakens them. `CLAUDE.md`
imports both. These rules are themselves the thesis of pipeline-doctor: a repository whose changes,
settings, credentials and decisions are all records is one an agent can operate.

## Ground rules

- **Personal learning projects, not affiliated.** Nothing here is any employer's or organisation's plan,
  study, finding or partnership. Mention companies only as their public sources describe them, with a citation.
- **No secrets, no real data.** Credentials never appear in code, files, logs, spans, issues, PRs or chat.
  Real personal data never enters a repo; synthetic or public, licensed data only, labelled as such.
- **Test first.** Write the failing test, then the code. A bug gets a regression test before the fix.
- **Label simulated output as simulated.** Never present a dry run as a result. Every number in a doc comes
  from a run in the repo or a cited source, with its interval where it has one.

## When a change needs a spec

Anything that changes a dataset, a metric, a rule or a workflow gets a spec first: `specs/NNN-name/spec.md`
(what and why), then `plan.md` and `tasks.md` (how). Small fixes don't. Every pull request gets a review
written to `pull_requests/pr-<n>-review.md`.

## Decisions and action items

A decision (what we chose, why, when to revisit) is a decision record in `docs/adr/NNNN-slug.md`
(`adr/README.md`, `adr/template.md`). An action item is a GitHub issue labelled `action-item`. Never a
decision only in an issue thread or a PR description.

## Branches and issues

Every user story is a GitHub issue, and every branch and pull request belongs to one.

1. **One issue per user story**, titled `<spec> <kind><n>: <story>`: kind `US` user story, `AI` action
   item, `BUG` fix, `CHORE` chore, `DOCS` docs; spec `000` for repo-wide work. Write the issue number next to
   the story in `spec.md`. A record created after the work merged carries the label `backfilled`, quotes the
   original text verbatim, and is closed on creation naming its source.
2. **Branch `<type>/<issue>-<slug>`**: type `feat fix docs data ci chore spec`; the issue number; a lowercase
   slug of at most 40 characters, starting with the spec number for spec work.
3. **Pull request: one issue's work, `Closes #<issue>` in the description** (`Refs #<n>` for one part of a
   larger story).
4. **Agent sessions never push to their assigned `claude/*` branch.** This rule is the standing permission:
   open or find the issue, create `<type>/<issue>-<slug>`, push there, open the PR from it.
5. Branches a tool names stay as they are: `dependabot/*`, `renovate/*`, `kaggle-results/*`.

CI checks 2-5 on every PR (`scripts/pr_conventions.py`, reusable workflow
`healthtransformationlab/pipeline-doctor/.github/workflows/pr-conventions.yml`).

## Configuration and secrets

Most production failures are configuration: a setting that differs between environments, a credential that
expired, a model or dependency that was deprecated.

- **One declaration per setting**, the same name in every environment; no per-environment defaults in code.
- **Check settings before doing work.** A required setting missing or malformed fails at once, naming it;
  an optional one warns and carries on; a credential is shape-checked then tried with one cheap call.
- **Settings change by pull request**, and the PR says which environments change.
- **Every credential is in `ops/secrets_register.yaml`** with where it lives, scope, owner, what breaks
  without it and its expiry date (never its value). Renew 14 days before expiry; rotate without a gap.
  `unknown` expiry is a finding. The register is what `pipeline_doctor.forecast` reads.
- **Every model, package and endpoint with an end-of-support date is in a dependency inventory**, which the
  forecaster reads the same way.

## Alerts and severity

Every alert names a severity, an owner and an action. Without an action it isn't an alert.

| Level | Means | Goes to |
|---|---|---|
| SEV1 | wrong or unsafe output published, data exposed, production down, or a credential already expired on a scheduled pipeline | the owner directly, now |
| SEV2 | a production pipeline failed and won't recover, or a credential or support window ends within 7 days | the owner, same day |
| SEV3 | failed then recovered, a quality check below threshold, rescued rows, within 30 days | the daily digest |
| SEV4 | warnings, deprecations, cost drift, unknown expiry, within 90 days | the weekly digest |

## Failures, retries and reruns

- **Every write is idempotent**: overwrite, `MERGE` on a key, or delete-then-append by batch key. Plain
  append only for event logs.
- **Every written row carries its batch key** (`run_id` and `run_ts`, or `file_sha256` and `loaded_ts`,
  and `git_commit_sha`).
- **Retries are set explicitly** per task, only for failures that can pass on their own; a bad setting or
  bad data fails at once.
- **A failure says how it ended** (exit code, signal, memory) and is logged where it survives the process.
- **Every run is a row**: pipeline, step, timings, counts, schema hash, checks, error type, duration, cost,
  with the OpenTelemetry span header (service, data product, environment). That row is what the doctor reads.

## Data names

Tables singular, one row per noun; `dim_<noun>`, `fact_<event>`, `<subject>_<noun>` for summaries;
columns `<what>_<kind>` with typed suffixes: `_id _key _code _name _text _date _ts _count _ratio _pct _rate
_seconds _usd _sha256 _sha _url`, `is_` for booleans. Never a bare `status`, `type`, `name` or `value`.

## Commits

Imperative subject; the body says why. Co-author trailer when an agent wrote it.
