# Agent entry

Keep initial context small.

1. If an Issue number is explicitly given, read only that Issue first.
2. Otherwise run `python tools/context/select_task.py` and start from the single returned Issue.
3. Search before reading full files. Prefer target source plus matching tests.
4. Do not read all Issues, docs, or the whole repository unless the task requires it.
5. Stop exploration when Goal / Required / Acceptance can be implemented safely.
6. Keep unrelated refactors out of the task.

Sources of truth:
- Requirements / priority: GitHub Issues
- Implementation: source code
- AI entry/routing: this file and `doc/`
- Code-derived structure: generated docs when available
