# Coding Standards

[日本語](コーディング規約.md) | [English](coding-standards.md)

These standards define the general coding rules for comfyUI_support_tools.

The project uses ideas from `upd-commander-base-design` for responsibility boundaries and dependency direction, while also adopting conventional Python practices for readability, maintainability, testability, security, and compatibility.

References:
- https://github.com/tomiya7688/upd-commander-base-design
- `specification/recommended-practices.md`
- `specification/implementation-quality.md`

Names such as Commander and Processing are not mandatory everywhere.
The important requirements are clear responsibility boundaries, explicit dependency direction, readability, and verifiability.

---

## 1. Core principles

- Prefer readability over clever brevity.
- Prefer explicit behavior over hidden or magical behavior.
- Do not remove duplication merely for its own sake; extract shared code only when the shared responsibility is real.
- Keep changes scoped. Do not mix unrelated refactors into a task.
- Do not break public APIs, configuration formats, saved data, CLI arguments, or workflows without a reason and migration path.
- Do not scatter magic numbers or unexplained strings through implementation code.
- Avoid unnecessary global state.
- Avoid heavy work or external side effects during import.
- Design failure paths as well as success paths.
- Express enforceable constraints in code, not only in comments.

---

## 2. Responsibility separation

- One file should have one primary responsibility.
- One module should have one primary responsibility.
- One function should perform one primary action.
- If a file contains independent behavior that cannot be explained by its filename, consider splitting it.
- Do not force simple behavior into classes; a Python module plus functions is acceptable.
- Do not mix unrelated UI, I/O, image processing, ComfyUI communication, persistence, and configuration responsibilities in one giant module.

### Audit for files over 1000 lines

A project-owned file over 1000 lines is an **architecture audit trigger, not a ban**.

Do not split a file mechanically because of line count. At the same time, once a file exceeds 1000 lines, explicitly re-check whether its responsibility should remain a single file/module.

Audit at least the following:

- Are multiple independent responsibilities mixed together?
- Are UI, I/O, API communication, transformation, persistence, or state management mixed without a strong reason?
- Can independently testable units be moved into separate modules?
- Are unrelated classes or function groups colocated only for convenience?
- Does a change in one area frequently affect unrelated behavior?
- Would splitting simplify dependency direction?
- Would splitting only create cycles or excessive inter-module chatter?
- Is the size justified by generated code, large static definitions, or a one-to-one mapping to an external specification?

Keeping a file over 1000 lines is acceptable when it remains cohesive and splitting would make dependencies, readability, or maintenance worse.
Files under 1000 lines can still require splitting when responsibilities are mixed.

### Dependency and control flow

- Let upper-level orchestration determine process order.
- Avoid unnecessary horizontal calls between lower-level modules.
- Prefer pure helpers, validation, conversion, data structures, and explicitly shared utilities for genuinely common behavior.
- Prefer execution paths that can be followed from explicit callers.

---

## 3. Python style

Follow common PEP 8 conventions unless the repository formatter defines a more specific rule.

- Use four spaces for indentation.
- Do not mix tabs and spaces.
- Remove trailing whitespace.
- Use conventional spacing around operators and commas.
- Break excessively long lines.
- Treat the configured formatter as authoritative when one exists.
- Prefer f-strings for readable interpolation.
- Do not construct OS paths with manual string concatenation.

---

## 4. Naming

Use names that reveal intent.

- Variables, functions, methods: `snake_case`
- Classes: `PascalCase`
- Constants: `UPPER_SNAKE_CASE`
- Modules/files: normally `snake_case.py`
- Internal names: use a leading underscore when appropriate
- Booleans: prefer names such as `is_*`, `has_*`, `can_*`, `should_*`, or `enable_*`

Avoid vague names such as `data`, `info`, `obj`, `tmp`, or `value` outside very small scopes.
Use consistent terminology for the same concept.

---

## 5. Imports

- Put imports at the top of the file by default.
- Separate standard library, third-party, and project imports logically.
- Do not use wildcard imports.
- Do not use function-local imports as a casual workaround for circular dependencies.
- Local imports are acceptable for clear reasons such as optional dependencies or carefully isolated cycles.
- Remove unused imports.
- Avoid importing the same module in multiple inconsistent forms.

---

## 6. Functions

Do not overload one function with unrelated acquisition, validation, transformation, persistence, rendering, notification, and orchestration work.

Split independent actions into smaller functions called from an upper-level function.
Do not fragment inseparable small steps mechanically.

### Parameters and return values

- Too many parameters often indicate excessive responsibility or a missing data structure.
- Avoid APIs controlled by many boolean flags.
- Avoid giant tuples with unclear meaning; use dataclasses or other explicit structures when helpful.
- Never use mutable objects as default argument values.

---

## 7. Type hints

- Add type hints to new public functions, important internal APIs, and complex data structures where practical.
- Use types to improve readability, not to create type puzzles.
- Limit `Any` to boundaries where it is genuinely necessary.
- Consider `dataclass`, `TypedDict`, `Protocol`, and enums for meaningful structures.
- Do not let vague `dict[str, object]` structures spread through the whole codebase.
- Make optional/`None` behavior visible in types and logic.

---

## 8. Object-oriented design and module independence

Object-oriented design in this project does **not** mean maximizing classes, inheritance, or encapsulation.

The highest priority is that **each module owns an independent responsibility, does not depend on another module's internals, and can be replaced, removed, or unit-tested with limited impact**.

Encapsulation, abstraction, interfaces, Protocols, and classes are tools for that independence, not goals by themselves.

### Modules are the primary design unit

- Define module/package/Application responsibility boundaries before designing class hierarchies.
- A module should be explainable as one cohesive unit.
- Avoid designs that require one module to understand another module's private state or implementation.
- If replacing/removing a module forces unrelated edits across the repository, re-evaluate the boundary.
- Avoid modules that require unrelated subsystems to be started merely to unit-test them.
- Prefer module internals whose class layout is invisible to consumers.

### Dependencies must be minimal and one-way

- Do not create circular dependencies.
- Avoid bidirectional A↔B dependencies.
- Avoid peer modules calling each other back and forth.
- Lower-level modules must not depend on concrete upper-level implementations.
- Consumers should not need transitive implementation knowledge.
- Keep dependencies explicit through imports, constructor/function parameters, or contracts.
- Do not hide dependencies behind global registries, service locators, or giant singletons.

When Module A finishes and Module B must run next, prefer returning to an upper Orchestrator/Commander and letting it choose the next step.

### Depend on contracts, not internals

When modules must communicate, prefer the smallest useful public contract instead of concrete private implementation details.

Useful contract forms include:

- small public functions/APIs
- `Protocol`
- ABC/interface
- explicit dataclass/TypedDict input and output types
- command/result objects
- events/messages
- callbacks

Do not create abstraction layers without a concrete benefit.
Use them when they improve replaceability, test doubles, or module boundary stability.

### Data ownership

- A module should not directly mutate state owned by another module.
- Do not use shared mutable global state as an inter-module communication channel.
- Make ownership of mutable data clear.
- Use values, DTOs, dataclasses, or copies when appropriate across boundaries.
- Avoid consumers depending on private dictionary key layouts.
- Separate storage/API representations from internal models when useful.

### Cross-module workflows belong to orchestration

Do not bury multi-module sequencing inside one leaf module.
Each module should complete its own responsibility and return a result; the upper orchestration layer decides what happens next.

### Do not create a dependency junk drawer

- Do not put unrelated code into `common`, `utils`, or `helpers`.
- Shared code must have an explainable responsibility and scope.
- Do not move domain rules into generic utilities.
- Avoid one giant common module depended on by nearly everything.
- Separate shared contracts from shared implementations when helpful.

### Prefer independence over inheritance

- Do not use inheritance when it increases module coupling.
- Do not inherit merely to reuse code.
- Prefer composition, delegation, or small Protocols where they fit.
- Avoid deep base-class hierarchies where one base change affects many unrelated features.
- Framework-required inheritance should preferably remain at the framework boundary.

### Class usage

- Use classes when state, lifecycle, or polymorphism justifies them.
- Do not create classes only as namespaces.
- Do not create God Objects.
- Use dataclasses for simple data instead of excessive getter/setter classes.
- Do not expose internal mutable state across module boundaries.
- Do not let one class accumulate multiple module-level responsibilities.

---

## 9. Comments and docstrings

Comments should explain purpose, boundaries, or reasons—not merely restate code.
Keep comments synchronized with implementation.

### Permanent declaration-comment rule: JSON-like Comment Outs

This project permanently adopts https://github.com/tomiya7688/Json-like-comment-outs for declaration-level structured comments.

The Japanese specification in that repository is canonical.

For project-owned new or substantively modified code, apply JSON-like Comment Outs directly before:

- classes
- functions
- methods

Legacy code does not need a bulk comment-only migration. Update comments when the declaration itself is substantively changed.
Generated, vendored, and third-party code is excluded.

For tool stability, this repository standardizes the Semantic Keys to the Japanese forms:

- `責務`
- `処理`
- `フィールド`
- `引数`
- `戻り値`
- `副作用`
- `エラー`
- `補足`

Implementation-internal comments remain normal `#` comments.
Python docstrings may be used in addition when runtime or tooling expects them; avoid unnecessary duplicate prose.

---

## 10. Exception handling

- Do not silently swallow errors with broad `except:` or `except Exception:`.
- Catch specific exceptions where practical.
- Do not convert unrecoverable failures into success.
- Preserve causes when translating exceptions.
- Include enough context in error messages to identify the failed operation or target.
- Separate user-facing messages from developer diagnostics when useful.
- Do not treat “print the error and continue” as a default strategy.

---

## 11. Logging

- Use `logging` for application/library diagnostics.
- Do not commit temporary debug `print()` calls.
- Use log levels intentionally.
- Avoid duplicate logging of the same error across multiple layers.
- Never log passwords, API keys, cookies, tokens, or similar secrets.
- Do not dump huge image payloads, base64 blobs, or giant JSON objects into normal logs.

---

## 12. Files, paths, and encoding

- Prefer `pathlib.Path`.
- Do not manually join path separators.
- Do not hard-code Windows-specific paths in general-purpose logic.
- Specify text encodings explicitly.
- Use safe temporary-file mechanisms such as `tempfile`.
- Consider data-loss risks before overwriting files.
- Validate user-provided paths before destructive operations.

---

## 13. Configuration and constants

- Do not scatter magic values, model names, timeout values, or fixed paths.
- Use named constants or configuration.
- Distinguish user-configurable values from implementation constants.
- Do not define the same default independently in multiple places.
- Keep environment-specific values out of source code.

---

## 14. Data structures

- Avoid giant dictionaries whose behavior depends on undocumented string keys.
- Consider dataclasses, TypedDicts, or enums for stable structures.
- Validate and normalize external API data at boundaries.
- Separate internal representations from external formats when useful.
- Avoid passing one mutable dictionary through many layers where each layer silently changes it.

---

## 15. External APIs and ComfyUI communication

- Separate HTTP/API access from pure data transformations.
- Use network timeouts.
- Handle failures, timeouts, and invalid responses.
- Do not assume external responses always match the expected schema.
- Do not retry forever.
- Be careful retrying non-idempotent operations.
- Prefer a dedicated conversion/boundary layer for ComfyUI workflow/prompt structures instead of constructing them throughout UI code.

---

## 16. Subprocesses and external commands

- Avoid `shell=True` where possible.
- Never concatenate untrusted input into shell commands.
- Pass arguments as a list.
- Check return codes.
- Capture/use stdout and stderr when useful.
- Consider timeouts for operations that may hang.
- Validate executable/dependency availability when practical.

---

## 17. Security

Even for local tools, do not blindly trust external input.

- Never commit passwords, API keys, private keys, or tokens.
- Do not log credentials.
- Do not apply `eval()` or `exec()` to external input.
- Do not deserialize untrusted pickle-like formats that can execute code.
- Defend against archive path traversal.
- Do not concatenate user input into shell commands or SQL.
- Make trust boundaries explicit when downloading or executing models, scripts, or plugins.

---

## 18. Dependencies

- Do not add a large dependency when the standard library is sufficient.
- Document the purpose of new dependencies.
- Avoid duplicate libraries for the same responsibility.
- Do not make optional features inflate mandatory dependencies without a reason.
- Document confusing package/import-name differences where useful.
- Remove unused dependencies when practical.

---

## 19. Performance

- Do not sacrifice clarity to premature optimization.
- Avoid obvious unnecessary copies and repeated model loads in image/video/model-heavy paths.
- Do not load huge files fully into memory without a reason.
- Define cache lifetime and invalidation.
- Base meaningful optimization work on measurement where practical.
- Pay attention to GPU/VRAM lifecycle and duplicate loads.

---

## 20. Concurrency and asynchronous work

- Do not mix threads, processes, and asyncio without a clear reason.
- Avoid blocking the UI thread with long-running work.
- Minimize shared mutable state.
- Consider cancellation, timeouts, and shutdown.
- Do not swallow background-worker exceptions.
- Respect GUI framework thread rules.
- Consider race conditions when multiple workers can update the same files or settings.

---

## 21. UI code

- Separate UI construction, event wiring, and business logic where practical.
- Do not put long-running work directly in event handlers.
- Do not rely on UI-only validation for core invariants.
- Error messages should help users decide what to do next.
- Avoid UI widgets directly reaching deep into files, APIs, or ComfyUI internals.
- Keep non-UI logic testable without starting the GUI.

---

## 22. Backward compatibility

Consider compatibility with:

- existing CLI arguments
- configuration formats
- saved data formats
- ComfyUI workflow formats
- public functions/APIs
- file locations
- Windows launch scripts
- existing models and custom nodes

When a breaking change is necessary, provide a migration path or compatibility layer where appropriate.

---

## 23. Tests

- Do not break existing tests.
- Update tests together with specification changes.
- Add tests for important new behavior where practical.
- Add regression tests for bug fixes when possible.
- Keep pure logic unit-testable without GUI or external servers.
- Do not make tests depend on execution order.
- Do not let tests damage real user data.
- Use temporary files/directories for isolated filesystem tests.

---

## 24. Implementation quality

Before considering a change complete, run the checks available for the affected scope:

- Python syntax/import checks
- formatter or format checks
- linter
- unit tests
- required startup/build checks
- existing GitHub Actions

Do not treat a change as complete while normal tests or CI are broken.

If a formatter/linter/type checker is standardized, its repository configuration is authoritative.
Do not make a new quality tool mandatory informally; add its configuration, CI integration, and documentation together.

---

## 25. Development tools and script placement

Place development support tools under `tools/` by default.

```text
tools/
└─ <tool_name>/
   ├─ script/
   │  └─ ...
   ├─ README.md
   └─ ...
```

Do not keep adding support scripts at repository root unless compatibility requires it.

---

## 26. Review checklist

Review at least:

- Are names clear?
- Does each file have one cohesive responsibility?
- For files over 1000 lines, was responsibility splitting explicitly audited?
- Does each function have one primary action?
- Are UI/API/data/persistence layers unnecessarily coupled?
- Are peer modules becoming horizontally coupled?
- Is dependency direction easy to trace?
- Are import-time side effects increasing?
- Are exceptions being swallowed?
- Are secrets exposed in logs?
- Are paths and external input handled safely?
- Are unnecessary dependencies being added?
- Are public APIs or configuration formats broken without a reason?
- Do comments explain intent rather than restate code?
- Are formatter/lint/test/CI checks being bypassed?
- Does important new behavior have appropriate tests?

---

## 27. Adoption policy

New code must follow these standards by default.

Do not mass-refactor unrelated legacy code merely to satisfy the standards. Apply them progressively to code that is substantively touched.

Reasonable exceptions for performance, compatibility, framework constraints, or external APIs are allowed when documented.
Prefer safe continuous improvement over large rule-only rewrites.

---

## 28. UPD standard for new Applications

New major Applications follow `doc/architecture/upd_standard.md` and are organized under `src/comfyui_support_tools/applications/` by Application with UI / Process / Data separation.

- Commander coordinates calls only.
- Messenger handles layer communication only.
- Processing performs actual work.
- UI must not directly depend on Data.
- Do not directly depend on another Application's internal modules.
- Applications communicate through explicit APIs/contracts.
- Migrate legacy `scripts/` progressively as responsibilities are touched.

New Application code must pass `tools/architecture/upd_check.py` in strict mode where applicable.

---

## 29. Japanese / English README and documentation

README files and project-owned documentation are maintained in both Japanese and English.

- Create both languages for new documents.
- When an existing document is substantively modified, update its paired language version in the same PR.
- Keep requirements, warnings, and specification meaning equivalent across languages.
- When using separate files, add reciprocal language links at the top.
- Do not bulk-translate unrelated legacy documents merely to satisfy the rule; pair documents as they are substantively touched.
- Machine-generated output, third-party original text, and canonical license/legal text may be exempt when translation would harm source fidelity.
- Preserve uncertain specialist terminology instead of guessing; include the original term when necessary.
- A change is not complete if only one language has been updated.
