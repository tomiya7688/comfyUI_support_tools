# Agent entry

Keep initial context small.

Every work session starts with `git fetch origin`. Verify the repository and worktree, then inspect relevant open PRs before choosing an Issue or implementation step. If fetching fails, mark remote freshness unverified and do not make a stale-state decision. For the one-cycle procedure and shared/individual roles, follow [the development workflow](doc/ワークフロー/workflow.md) ([日本語](doc/ワークフロー/ワークフロー.md)). Codex can load the shared [development-workflow skill](.agents/skills/development-workflow/SKILL.md); Claude uses `CLAUDE.md` and its thin skill adapter.

1. After the shared remote/PR preflight, if an Issue number is explicitly given, read only that Issue first.
2. Otherwise inspect relevant open PRs first; if none needs this task, run `python tools/context/select_task.py` and start from the single returned Issue.
3. Run `python tools/context/task_packet.py <issue-number>` to create a compact local task packet.
4. Search before reading full files. Prefer target source plus matching tests.
5. If structure is unclear, run `python tools/context/repo_map.py` and inspect `.codex/repo_map.json` instead of scanning the repository.
6. Do not read all Issues, docs, or the whole repository unless the task requires it.
7. Read `doc/コーディング規約.md` before implementing or refactoring code.
8. For new or substantively modified project-owned classes/functions/methods, apply the permanent JSON-like Comment Outs declaration-comment rule from `doc/コーディング規約.md`; keep implementation-internal comments as normal comments.
9. Use UPD for responsibility placement/dependency flow and Part Swap Design for replaceability. Plain UPD is valid for simple flows; do not add pass-through Commander/Messenger scaffolding merely for structure. Introduce Commander/Orchestrator only when sequencing, routing, retry/fallback, long-job control, or workflow coordination is itself a responsibility, and introduce Messenger only when communication/transport itself needs isolation.
10. Callers depend on a part's stable public input/output contract; internal subordinate modules stay inside a closed call relationship. For deliberate extension points, prefer a contract/swap test that can substitute a fake or alternate implementation without changing consumers. Do not over-fragment one-owner internals merely to create interfaces or orchestration layers.
11. Treat project-owned files over 1000 lines as an architecture audit trigger, not an automatic failure: explicitly check whether responsibilities should be split, and keep the file intact when a split would worsen cohesion or dependencies.
12. Maintain README and project-owned documentation in both Japanese and English; new or substantively modified docs must update both language versions in the same PR, except generated/third-party/canonical legal text.
13. Stop exploration when Goal / Required / Acceptance can be implemented safely.
14. Keep unrelated refactors out of the task.
15. Apply coding rules to new/modified code only; do not mass-refactor unrelated legacy code.
16. Before commit/PR, run `python tools/completion/completion_gate.py`; do not proceed if it fails.
17. Before automated PR handling/merge, run `python tools/completion/pr_safety.py <pr-number>` and stop on conflict, unknown mergeability, failed checks, default-branch work, repository/base/head mismatch, or unexpected diff.
18. Never write implementation changes directly to `main`/`master`, including through GitHub API/connector file-write actions. Always create a task branch, commit there, open a PR, wait for required CI to pass, run PR safety, then merge the PR.
19. Before editing, verify the repository is `tomiya7688/comfyUI_support_tools` and that the change belongs to the selected Issue/task. Do not carry implementation from another project into this repository unless the task explicitly requests a port.
20. Keep every PR scoped to one task. If unrelated changes appear in the diff, remove them before merge.

Sources of truth:
- Requirements / priority: GitHub Issues
- Implementation: source code
- Coding rules: `doc/コーディング規約.md`
- New Application architecture: `doc/architecture/upd_standard.md`
- AI entry/routing: this file and `doc/`
- Code-derived structure: generated docs when available

Generated task packets and repository maps are local working artifacts under `.codex/` and stay outside Git.
