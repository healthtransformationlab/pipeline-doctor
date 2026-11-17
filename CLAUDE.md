# CLAUDE.md

@conventions/AGENTS-common.md
@AGENTS.md

The shared rules (`conventions/AGENTS-common.md`) and this repo's own (`AGENTS.md`) apply to every agent.
This file adds only Claude Code's own workflow.

## Workflow

| Stage | Tool | Output |
|-------|------|--------|
| What and why | `/speckit-specify` (then `/speckit-clarify` if needed) | `specs/NNN-name/spec.md` |
| One issue per user story, then its branch | GitHub issue; branch `<type>/<issue>-<slug>` | issue `#n`, branch `feat/<n>-NNN-slug` |
| How | `/speckit-plan`, `/speckit-tasks` | `plan.md`, `tasks.md` in the same folder |
| Each task | Superpowers `test-driven-development` | failing test → code → passing test |
| Before saying done | Superpowers `verification-before-completion` | commands run, output checked |
| Open a PR | `conventions/pull_request_template.md`, `Closes #<issue>` | PR + `pull_requests/pr-<n>-review.md` |


## Times

When you tell the owner a time, in chat, in a status cell or in a message, write it in 12-hour form with AM or PM, in
UTC with Central time beside it: "12:02 AM UTC (6:02 PM Central)". The owner asked for this on November 17, 2026
("give all utc times in am pm all chats"). Files, logs, tables, commit messages and code keep ISO 8601 UTC.
