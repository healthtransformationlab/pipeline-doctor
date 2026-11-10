---
pr: 6
branch: fix/5-pin-hishel-below-2
title: "000 BUG1: pin hishel below 2 so the test suite imports"
author: Claude Code (agent session for jcbowyer)
reviewed_at: 2026-11-10
reviewer: the authoring session (failure reproduced and the fix shown passing in clean environments; no reviewer subagent run)
verdict: approve
---

# PR Review: 000 BUG1: pin hishel below 2 so the test suite imports

## Summary
CI's `pytest` job failed on every branch at the import of `kaggle_benchmarks`. One line in `pyproject.toml` pins
`hishel<2` in the `kbench` extra, as `health-transformation-lab-nlp` already does. Nothing blocking.

## Checks
| Check | Result |
|---|---|
| Failure reproduced on `main` in a clean Python 3.12 environment | yes: `hishel` 2.0.0, `kaggle-benchmarks` 0.6.2, 1 error during collection |
| With the pin, same environment otherwise | `hishel` 1.4.0, `pytest -q tests`: 62 passed |
| The existing tests are the regression test | `tests/test_kbench.py` could not be collected before and passes after |
| Branch name and issue link | `fix/5-pin-hishel-below-2`, `Closes #5` |

## Secrets, Real Data and Claims Scan
Secrets: none. Real data: none. Claims: none.

## Notes
- This is a dependency pin, not a new test: no test could be written that fails for this cause without the pin and
  passes with it, other than the suite importing at all, which is what CI now checks.
- `tests/test_kbench.py` uses `pytest.importorskip`, which skips on `ImportError` only. A broken install therefore
  fails the run rather than skipping, which is the safer behaviour and is left as it is.
- Revisit the pin when `kaggle-benchmarks` supports `hishel` 2.
