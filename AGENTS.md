# Agent entry

Keep initial context small.

1. If an Issue number is explicitly given, read only that Issue first.
2. Otherwise run `python tools/context/select_task.py` and start from the single returned Issue.
3. Run `python tools/context/task_packet.py <issue-number>` to create `.codex/tasks/<issue>/task.json`.
4. Search before reading full files. Prefer target source plus matching tests.
5. Do not read all Issues, docs, or the whole repository unless the task requires it.
6. Stop exploration when Goal / Required / Acceptance can be implemented safely.
7. Keep unrelated refactors out of the task.

Sources of truth:
- Requirements / priority: GitHub Issues
- Implementation: source code
- AI entry/routing: this file and `doc/`
- Code-derived structure: generated docs when available

Generated task packets are local working artifacts and remain outside Git via `.codex/tasks/`.
