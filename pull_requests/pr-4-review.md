---
pr: 4
branch: chore/3-apache-licence
title: "000 CHORE1: license the repository under Apache 2.0"
author: Claude Code (agent session for jcbowyer)
reviewed_at: 2026-11-10
reviewer: the authoring session (diff, licence hash and test suite; no reviewer subagent run)
verdict: approve
---

# PR Review: 000 CHORE1: license the repository under Apache 2.0

## Summary
Replaces the MIT licence with Apache 2.0 at the owner's request, so every repository in the organisation carries
one licence. Four files. Nothing blocking.

## Checks
| Check | Result |
|---|---|
| `LICENSE` is the unmodified Apache 2.0 text | yes: SHA-256 `cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30` |
| `pyproject.toml` and `README.md` agree with `LICENSE` | yes |
| `python -m pytest -q tests` | 46 passed, 1 skipped (Kaggle Benchmarks SDK not installed) |
| Branch name and issue link | `chore/3-apache-licence`, `Closes #3` |

## Secrets, Real Data and Claims Scan
Secrets: none. Real data: none. Claims: none added.

## Notes
- Versions already published under MIT stay available under MIT. `health-transformation-lab-nlp` pins this
  package to commit `ff2feee`, which is MIT.
- `conventions/` is unchanged, so `conventions/VERSION` is not bumped.
