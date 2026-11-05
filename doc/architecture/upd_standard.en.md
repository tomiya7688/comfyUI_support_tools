# UPD + Part Swap Standard Architecture

[日本語](upd_standard.md)

New major Applications in this project use **UPD + Part Swap Design** as the standard architecture.

- UPD defines the UI / Process / Data responsibility boundaries and dependency direction.
- Part Swap Design defines closed replaceable parts whose internals are hidden from consumers.
- UPD Commander Base Design is an optional pattern for cases where orchestration or communication is itself a meaningful responsibility. It is not mandatory for every Application.

Canonical sources:
- https://github.com/tomiya7688/upd-design
- https://github.com/tomiya7688/part-swap-design
- https://github.com/tomiya7688/upd-commander-base-design

## Scope

New code normally lives under `src/comfyui_support_tools/applications/<application>/`.
Do not bulk-migrate `scripts/` or `nuno/`; migrate responsibilities incrementally when they are touched.

Default shape:

~~~text
Application
├─ UI
├─ Process
└─ Data
~~~

Add Commander / Messenger / Processing roles inside a layer only when they have a real responsibility.

## Application boundary

An Application is a functional boundary whose UI / Process / Data responsibilities belong together.
Do not directly import another Application's internal modules.

Application-to-Application communication uses:
- explicit APIs such as HTTP / WebSocket
- DTOs / Contracts in `shared/contracts`
- explicit external adapters / transports

Do not move implementation into `shared` merely to bypass an Application boundary.

## UPD layer boundary

The responsibility flow is:

~~~text
Request: UI -> Process -> Data
Result:  Data -> Process -> UI
~~~

- UI owns external input/output and presentation.
- Process owns application decisions, validation, transformations, and domain flow.
- Data owns persistence, retrieval, and external data access.
- UI must not bypass Process to depend directly on Data.
- Data does not know UI-specific representations.
- Process does not know widget internals or storage implementation internals.

For a simple in-process flow, adjacent layers may communicate through a small public function / Contract.
Do not create Commander / Messenger classes or empty directories merely to claim UPD compliance.

## Part Swap Design

Replaceable implementations form closed parts.

Typical parts:
- generation backend / workflow adapter
- model-family detector
- evaluator / ranker / repair strategy
- image / video filter
- OCR / text detector
- trainer / personalization adapter
- video decode / analysis backend
- storage / cache / artifact / export adapter
- Post Process processor

### Part boundary

- Consumers do not import internal modules of a part.
- Consumers depend on stable input/output Contracts, semantic IDs, capabilities, and result types.
- Swapping implementation A for B should normally change only the composition root / registry / config binding.
- Do not scatter concrete branching such as `if backend == ...` or `if model == ...` through consumers.
- Do not turn internal helpers into an open call relationship shared by unrelated Applications.
- Promote genuinely common responsibilities into an independent part or shared Contract.
- Do not create interfaces for one-owner internals when independent replacement has no real value.

### Tests

For deliberate extension points, prefer:
- public-boundary contract tests
- swap tests using fake / minimal implementations
- implementation-specific tests kept inside the part

When the Contract allows implementations to produce different results, test required invariants, failure semantics, and Acceptance rather than byte-identical behavior.

## When to use Message Orientated Design

Message Orientated Design is **selectively applied between independent state-owning subjects**.
Do not turn every module/class interaction into a Message.

A "subject" here means an Application, service, worker, job runtime, training session, plugin host, or similar unit with independent state/lifecycle.
Inside one subject/part, normal function calls remain the default.

### Use a Message boundary

Use it when:
- async / event / queue coordination is useful
- communication crosses a process, service, Application, plugin, or worker boundary
- progress / cancel / completion / failure / state changes are first-class events
- sender and receiver have independent lifecycles
- the receiver interprets a request according to its own state
- the receiver or transport should be replaceable

### Do not use a Message boundary

Keep direct calls for:
- pure helpers
- internals of one Part Swap part
- local algorithms with one owner/lifecycle
- small synchronous validation/conversion
- cases where Message infrastructure does not reduce coupling

### Message Contract

When the Message Orientated boundary is selected:

~~~text
Subject A
  -> Sender
  -> immutable Message
  -> Message Manager / transport
  -> Receptor
  -> Subject B internal processing
~~~

- Do not directly call another subject's private/internal functions.
- Do not directly read/write another subject's owned state.
- Messages are immutable; create a new Message when meaning, destination, or content changes.
- Responses across the selected Message boundary are new Messages.
- Prefer typed/frozen contracts over a repository-wide untyped dictionary protocol.
- Receptor identifies the message type and dispatches only; domain decisions stay in subject processing.
- Sender is the subject's outbound Message boundary.
- Message Manager performs delivery only. It does not own domain decisions, retry policy, model selection, persistence, or workflow orchestration.
- A global Message Manager is not required; route through the smallest useful manager/domain scope.
- A global Message ID is not required. Add request/run/job correlation IDs only when a protocol needs them.

### Relationship to the other architecture rules

- UPD decides which layer owns state and meaning.
- Part Swap Design keeps subject internals replaceable.
- Message Orientated Design defines communication between independent subjects.
- Commander coordinates complex workflow sequencing.
- Message Manager only delivers Messages.

Do not automatically equate UPD Messenger with Message Orientated Design's Sender/Receptor/Message Manager.
They may share one transport/boundary implementation only when their responsibilities genuinely coincide.

### Representative flow

~~~text
Character Registry
  -> TrainCharacterRequested
  -> Training Application

Training Application
  -> TrainingProgress
  -> Character Registry / Job UI

Training Application
  -> TrainingCompleted
  -> Character Registry
~~~

Character Registry does not call trainer internals or mutate training-session state directly.

## When to use Commander

Commander / Orchestrator is **optional**, not a default requirement.
Use it when sequencing itself becomes a meaningful responsibility, for example:

- multiple independent parts must run in sequence
- routing / branching selects the next part
- retry / fallback / Top-K / repair / re-evaluation changes the flow
- long-job cancel / pause / resume / checkpoint state changes sequencing
- the workflow itself needs focused tests independent of its parts

When used:
- Commander coordinates order and flow decisions only.
- Algorithms, I/O, HTTP, subprocesses, inference, and persistence stay in the appropriate Processing/part.
- Commander uses public part Contracts and does not reach into part internals.

Do not add a formal Commander to a simple input -> transform -> save flow merely for structure.

## When to use Messenger

Messenger is also optional.
Use it when communication / transport itself deserves an isolated responsibility, such as:

- async / event / queue delivery
- IPC / subprocess services
- HTTP / WebSocket
- cross-process communication
- cross-Application communication
- protocol translation or delivery reliability

When used:
- Messenger transports payloads / Contracts.
- It does not perform domain decisions, algorithms, or persistence.

Do not require pass-through Messenger objects for simple adjacent UPD layers inside one process.

## Shared

Allowed under `src/comfyui_support_tools/shared/`:
- Contracts / DTOs
- value objects
- small Application-independent pure utilities
- the public boundary of a genuinely shared replaceable part

Not allowed:
- Processing belonging to one Application
- persistence belonging to one Application
- GUI processing
- proxies for another Application's internals
- helpers moved only to bypass a part boundary

## Legacy coexistence

- New Applications start with UPD + Part Swap Design.
- Do not bulk-rewrite working legacy code without a task.
- Shrink old implementations as responsibilities move to the new structure.
- Do not deepen legacy Tabs by adding new subprocess / HTTP / file mutation / inference / scoring logic; move touched responsibilities toward an Application/part boundary.

## Checker policy

Architecture checkers help enforce the design; they are not the design source of truth.

They should:
- detect UI -> Data bypasses
- detect direct dependencies on another Application's internals
- when Commander exists, detect actual work inside Commander
- when Messenger exists, detect domain work inside Messenger
- where practical, detect/test consumer coupling to concrete extension implementations

They must not:
- require empty Commander / Messenger scaffolding for a simple UPD flow
- force responsibility-free classes/files merely to satisfy checker structure

If the current `tools/architecture/upd_check.py` is stricter than this policy, this document is canonical and the checker must be updated instead of forcing unnecessary structure into production code.
