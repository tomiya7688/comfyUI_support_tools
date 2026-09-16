# Agent entry

Keep initial context small.

1. If an Issue number is explicitly given, read only that Issue first.
2. Otherwise run `python tools/context/select_task.py` and start from the single returned Issue.
3. Run `python tools/context/task_packet.py <issue-number>` to create a compact local task packet.
4. Search before reading full files. Prefer target source plus matching tests.
5. If structure is unclear, run `python tools/context/repo_map.py` and inspect `.codex/repo_map.json` instead of scanning the repository.
6. Do not read all Issues, docs, or the whole repository unless the task requires it.
7. Read `doc/コーディング規約.md` before implementing or refactoring code.
8. Stop exploration when Goal / Required / Acceptance can be implemented safely.
9. Keep unrelated refactors out of the task.
10. Apply coding rules to new/modified code only; do not mass-refactor unrelated legacy code.
11. Before commit/PR, run `python tools/completion/completion_gate.py`; do not proceed if it fails.
12. Before automated PR handling/merge, run `python tools/completion/pr_safety.py <pr-number>` and stop on conflict, unknown mergeability, failed checks, default-branch work, or unexpected diff.

Sources of truth:
- Requirements / priority: GitHub Issues
- Implementation: source code
- Coding rules: `doc/コーディング規約.md`
- AI entry/routing: this file and `doc/`
- Code-derived structure: generated docs when available

Generated task packets and repository maps are local working artifacts under `.codex/` and stay outside Git.
