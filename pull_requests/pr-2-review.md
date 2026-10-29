---
pr: 2
branch: feat/1-agents-md-pipeline-doctor-bench
title: "000 AI1: the conventions' claim, the repo's AGENTS.md and PipelineDoctorBench"
author: Claude Code (agent session for jcbowyer)
reviewed_at: 2026-10-29
reviewer: coordinator verification (full test suite, lint and a dry run; no reviewer subagent run)
verdict: approve
---

# PR Review: 000 AI1: the conventions' claim, the repo's AGENTS.md and PipelineDoctorBench

## Summary
States the claim the shared conventions make (conventions do the thinking a small model is too small to do)
as the repo's own AGENTS.md, mapping each convention to the switch-off condition that measures it, and adds
PipelineDoctorBench, which runs that switch-off test on real models through Kaggle Benchmarks. The rules
themselves are a model on the leaderboard (`RulesReader`), and a test holds their per-condition numbers to
`doctor.ablation`'s, so the benchmark cannot drift from the README's table. Approve.

## Scope of Change
- Files changed: 10 (+618 / -2), plus this review
- Areas touched: AGENTS.md, CLAUDE.md, conventions (one section, version 0.2.0), src, tests, kaggle, CI, pyproject
- Commits: b46f955 Add the conventions' claim, the repo's AGENTS.md and PipelineDoctorBench; this review
- Range reviewed: `origin/main..feat/1-agents-md-pipeline-doctor-bench`

## CI Status
| Check | Status |
|---|---|
| pytest, branch name and issue link | pending when written; see the PR |

## Secrets, PHI and Claims Scan
- Secrets: clean. SDK credentials come from `kaggle b init` into a gitignored `.env`.
- Real data: clean. The incident set is the repo's own, already committed; readers in tests are scripted.
- Organization claims: clean. The AGENTS.md says which rows of the thesis are measured and which are claims.

## Strengths
- `context_for` builds the agent's context through `doctor._ablate`, so the LLM and the rules see exactly
  the same switched-off rows; the parity test is what makes the "by condition" numbers comparable.
- The answer format is the runbook: an action off the list fails an assertion (`is_action_on_list`), so a
  model cannot score by inventing a verb.
- The answer key never reaches the prompt (`test_context_shows_the_four_tables_rows_for_the_incident`
  checks `recorded_in_text` and the class are absent).
- Simulated is labelled: `sim:` names, `is_simulated`, SIMULATED in the dry-run output; `RulesReader` is
  deliberately not simulated, since it is the rules.

## Findings
### 🔴 Blocking (Critical)
None.
### 🟡 Should fix (Important, non-blocking)
- Nine incidents is a small set; per-condition shares move in steps of 1/9. The backfilled issues from the
  repo's history (AGENTS-common.md, `backfilled` label) are what gives this benchmark weight. Tracked in #1.
### 🔵 Nits / suggestions (Minor)
- `_tracing.traced` is a shim, so nothing fails if a public function lacks it; the NLP repo's AST test
  (`test_every_public_function_in_the_package_is_traced`) could be vendored into `conventions/scripts`.

## Repo-Rule Compliance
| Rule | Pass? | Notes |
|---|---|---|
| No secrets, no real data | Yes | |
| Test first | Yes | 16 tests in `test_kbench.py`; the parity and gate tests fail without the module |
| Simulated is labelled simulated | Yes | |
| Spec for big changes | n/a | no dataset, rule or workflow change; `000 AI1` |
| Branches and issues | Yes | `feat/1-agents-md-pipeline-doctor-bench`, `Closes #1` |
| Configuration | Yes | no settings; CI installs the `kbench` extra, that is the only environment change |
| Data names | Yes | `truth_class_code`, `is_action_on_list`, `class_ok_ratio` |
| Commits | Yes | imperative subject, body says why, co-author trailer |
| conventions/ change bumps VERSION | Yes | 0.1.0 → 0.2.0 for the new section |

## Test Coverage
`pytest -q tests`: 62 passed. `ruff check --select E,F,B,I,UP,RUF --line-length 120` on the new files: clean.
`python kaggle/pipeline_doctor_task.py` from a clean folder: the rules' row matches the README's switch-off
table (full 1.00, no_conventions 0.67, no_metrics 0.89, no_history 0.67 class accuracy), then a SIMULATED
row. Not run: the push to Kaggle.

## Verdict
Approve. It can merge once CI is green.
