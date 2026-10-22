# One-cycle development workflow

[日本語](ワークフロー.md) | [Documentation index](../README.md)

One work cycle covers one Issue or an existing related PR. Design, implementation, and review are distinct responsibilities even when one person performs multiple roles. The sources of truth are the Issue requirements, source code, [coding standards](../coding-standards.md), and this workflow; scratch notes and AI summaries are not authoritative.

## Shared start (every cycle)

1. Check `git remote -v` and `git status --short --branch`. Identify the repository and preserve user changes, including untracked data.
2. **Run `git fetch origin` before deciding the next action, every time.** If it fails, record remote freshness as unverified and do not make a selection or merge decision that relies on fresh remote state. Fetching and integrating are separate operations.
3. After fetching, inspect `git log --oneline --left-right HEAD...origin/main` and only relevant diffs. Do not blindly `git pull origin main` on a task branch. Update the base deliberately, on the appropriate branch, after inspecting changes and conflicts.
4. Inspect open PRs first. If one relates to the task, check its latest head, diff, CI, review comments, and conflicts. Prefer updating or reviewing that PR over creating a duplicate. Do not read every unrelated PR in full.
5. Otherwise, select one Issue. Respect a supplied number, or use `python tools/context/select_task.py`. Read its body, relevant comments, priority, dependencies, and acceptance criteria. Use `python tools/context/task_packet.py <issue-number>` when useful.

Repeat these steps on a new work cycle, resumption, PR review, and merge decision. A fetch from a previous cycle is not a substitute. If fetching is unavailable, distinguish locally verified work from remote-dependent decisions in the handoff.

## Shared and individual responsibilities

Every contributor must confirm the Issue scope and primary sources, protect user data, avoid unrelated changes, distinguish verified from unverified results, keep Japanese and English docs in sync, and leave a handoff. These duties remain even when working alone.

| Role | Role-specific result and decision | Handoff |
| --- | --- | --- |
| Coordinator | Check PRs first, arrange Issue priority/dependencies and assignments, prevent duplicate work. Do not impersonate authority to message or merge. | Issue/PR, owner, base/head, next owner |
| Designer | Define goal, exclusions, boundaries, alternatives, acceptance criteria, and verification. Do not claim implementation or review approval. | Design choices, sources, open questions, smallest implementable unit |
| Implementer | Change code, tests, and docs on a task branch; self-review and prepare the PR. Do not call self-review independent review. | Scope, validation results, unverified items, risks, PR URL |
| Reviewer | Independently assess the latest-head diff with evidence and locations; recheck the new head after fixes. | Findings and resolution state, remaining verification, reviewed head |
| Merger | Confirm required CI, reviews, conflicts, base/head, and `pr_safety` at the end. Do not merge on failure or unknown status. | Merge result, Issue state, follow-up work |

People may hold multiple roles, but record who held each and whether independent review occurred in the Issue/PR. If no independent reviewer is available, say "self-review only." Hand off any action outside the assignee's authority as a request; do not claim it was done.

Each handoff includes Issue/PR, current and next role/owner, branch/base/head, scope, evidence links, executed checks and results, unverified items, unresolved findings, and next action. Persist decisions in the Issue/PR or canonical docs, not only local notes.

## Design

Extract Goal / Required / Acceptance and exclusions from the Issue. Search for relevant design, source, and matching tests, then read only needed portions. Decide responsibility, API/dependency boundaries, third-party licensing, and the need for real GUI/API/GPU checks. Split large work into small dependency-ordered units, not one mixed PR. Stop exploring once the evidence needed to implement and verify safely is available.

## Implementation

Use an Issue-specific branch, never edit `main`/`master` directly. Read the [coding standards](../coding-standards.md) before code changes. Edit target code and tests and update Japanese/English docs in the same PR. Never stage unrelated untracked user data. Run focused tests, static checks, and `git diff --check`; report actual GUI, external API, GPU, real-backend, and CI evidence separately.

Before PR, self-review acceptance coverage, diff scope, JSON-like declaration comments, error handling, dependencies/licenses, meaningful tests, bilingual docs, secrets, and user-data inclusion. Do not commit or open a PR if `python tools/completion/completion_gate.py` fails. Stage explicit target files only. Write the PR body in Japanese with its Issue, changes, validation results, and unverified/deferred items.

## Review and completion

The reviewer first fetches current remote and latest PR head, then compares the Issue acceptance criteria to the diff. Check omissions, unexpected files, standard violations, regressions, security/secrets, third-party licenses, bilingual docs, and insufficient tests. Findings cite file/location, impact, and evidence or reproduction. After fixes, review the same PR at its new head; do not reuse CI success from an older head.

Before merge, confirm required CI and unresolved reviews on the latest head and run `python tools/completion/pr_safety.py <pr-number>`. Stop for conflict, unknown mergeability, failed required checks, unexpected diff, or repo/base/head mismatch. Merge only a safe completed PR, then update Issue and follow-ups. Begin the next cycle with another fetch.

## Context reduction

Follow [AI Context Reducer](https://github.com/tomiya7688/ai-context-reducer): manifest → task packet → relevant source only → stop condition. Entry docs map locations/responsibilities instead of duplicating specifications. Narrow with `rg --files` and `rg -n`, then consult primary Issue, code, tests, and diffs. A task packet is a temporary compact goal/scope/constraints/acceptance/source-link note, not a replacement for source of truth. Expand research only when new dependencies, contradictions, or test failures require it.
