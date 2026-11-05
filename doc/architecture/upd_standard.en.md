# UPD + Part Swap Standard Architecture

[日本語](upd_standard.md)

New major Applications in this project use **UPD + Part Swap Design** as the standard architecture.

- UPD defines the UI / Process / Data responsibility boundaries and dependency direction.
- Part Swap Design defines closed replaceable parts whose internals are hidden from consumers.
- Message Orientated Design is selectively applied between independent state/lifecycle subjects when direct internal calls/state access would create coupling.
- Process Orchestrator / Workflow Processing is optional when dynamic loops, retry, candidate iteration, or workflow progression are themselves Process work.
- UPD Commander is optional when a thin request/result dispatch or continuation control point is useful.
- Messenger / Message Manager is optional when communication/delivery itself deserves an isolated responsibility.

None of these optional mechanisms is mandatory for every Application.

Canonical sources:
- https://github.com/tomiya7688/upd-design
- https://github.com/tomiya7688/part-swap-design
- https://github.com/tomiya7688/upd-commander-base-design

## Roles at a glance

Do not conflate similarly named concepts.

| Concept | Responsibility | May own | Must not own |
|---|---|---|---|
| UI | external input/output and presentation | widgets/input formatting | domain decisions / persistence |
| Process | application rules and decisions | validation / domain flow | UI widgets / storage details |
| Data | persistence and retrieval | file/DB/API data access and normalization | domain decisions / UI |
| Part | replaceable implementation boundary | private internals / implementation-specific algorithms | leaked internals required by consumers |
| Subject | independent state/lifecycle owner | owned mutable state | another subject's state ownership |
| Message | immutable communication between Subjects | from/to/type/content | mutable shared state / behavior |
| Process Orchestrator | workflow algorithm | loops / retry / candidate progression / state machine | UI or I/O implementation |
| Commander | dispatch/continuation control | next Processing/Messenger selection / minimal continuation ID | complex loops / domain algorithms / I/O |
| Messenger | layer/transport communication | delivery / protocol boundary | domain algorithms |
| Message Manager | Message delivery | target lookup / delivery | workflow / retry policy / persistence / model selection |
| Adapter | external/implementation-specific translation | protocol/config/result translation | domain-wide orchestration |

### Basic decision rule

- **Who owns state?** -> Subject / UPD owner.
- **Should the implementation be replaceable?** -> Part.
- **How do independent Subjects communicate?** -> Message.
- **How does a workflow iterate?** -> Process Orchestrator.
- **Which Processing should receive the next request/result?** -> Commander when needed.
- **Where should communication be delivered?** -> Messenger / Message Manager.
- **How are implementation-specific differences translated?** -> Adapter.

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

Following the canonical Message Orientated Design, the semantic minimum Message structure is:

~~~text
Message
├ from
├ to
├ type
└ content
~~~

- `from`: sending subject; prefer a stable semantic subject ID over a class name/path.
- `to`: receiving subject; prefer a stable semantic subject ID over a runtime object reference.
- `type`: semantic meaning; use a protocol-stable semantic type.
- `content`: typed payload; do not expose the receiver's owned internal state as message content.

Python may represent this with frozen dataclasses or another typed Message/envelope.
If a class type represents `type`, routing/serialization must still preserve the meaning of the four elements above.
A common base class or inheritance hierarchy is not required.

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
- Process Orchestrator owns complex workflow iteration/progression.
- Commander, when used, selects dispatch/continuation targets.
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

## When to use a Process Orchestrator / Workflow Processing

When dynamic iteration or the workflow algorithm itself is real application processing, model it as a **Process-layer Orchestrator / Workflow Processing**.
This is a different responsibility from Commander.

Examples:
- executing a variable number of sequence steps
- Best-of-N / Top-K candidate evaluation loops
- repeated work consuming a retry budget
- repair -> re-evaluate loops
- state-machine step progression
- batch workflow iteration

A Process Orchestrator may:
- implement workflow algorithms / iteration / state transitions
- call replaceable parts through public Part Contracts
- remain independent from UI widget details and Data storage representations
- delegate HTTP / subprocess / inference / persistence to the proper Part/Data/transport Contract

A loop is not itself a violation here. The rule is to keep unrelated responsibilities out of the loop.

A component such as `SequenceRunner`, which iterates declared steps under a failure policy, naturally fits this category.

## When to use Commander

Commander is **optional**, not a default requirement.
Following UPD Commander semantics, use it when a control point is needed to choose the next Processing / Messenger from an incoming request or returned result.

Examples:
- select Processing from a command type
- select the next Processing / Messenger from a Processing result
- manage the continuation target for an asynchronous response
- dispatch requests/results at a layer boundary

When used:
- Commander selects call targets, dispatches, and chooses success/failure/continuation paths only
- algorithms, I/O, HTTP, subprocesses, inference, and persistence stay outside Commander
- complex loops / candidate iteration / retry algorithms belong in Process Orchestrator / Processing
- Commander uses public Contracts and does not reach into part internals
- only minimal continuation IDs/state may be retained

Do not add a formal Commander to a simple input -> transform -> save flow merely for structure.

### Commander vs Process Orchestrator

- **Commander:** chooses *which processing to call next*.
- **Process Orchestrator:** implements *how a workflow iterates and progresses*.

When both are useful, Commander invokes the Orchestrator as a Processing responsibility and does not absorb its workflow algorithm.

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

## Architecture decision flow

When adding a responsibility, decide in this order.

| Question | Yes | No |
|---|---|---|
| External input/presentation/output? | UI | Continue |
| Application rule/decision/domain flow? | Process | Continue |
| Persistence/retrieval/external data access? | Data | Continue |
| Is independent replacement valuable? | Define a Part Contract | Keep inside the owner |
| Is the peer an independent state/lifecycle subject? | Consider Message | Consider function call |
| Async/process/service boundary? | Prefer Message/transport | Sync Contract is fine |
| Is there dynamic iteration / retry / candidate looping? | Consider Process Orchestrator | Plain Process is enough |
| Is a request/result dispatch control point needed? | Consider Commander | Direct call is enough |
| Is communication itself complex? | Consider Messenger/transport | Direct adjacent Contract is enough |

### Stop rule

Do not add abstraction when all or most of these are true:

- one owner
- one implementation
- simple synchronous call
- shared lifecycle
- little independent replacement value
- no testability improvement

Do not add Message / Commander / registry / interface only because it might be useful someday.

## Standard patterns

### Pattern A: simple synchronous feature

~~~text
UI
 -> Process
 -> Data
~~~

No Commander.
No Message.

### Pattern B: swappable backend

~~~text
UI
 -> Process
 -> Backend Contract
      ├─ Qwen Part
      ├─ SDXL Part
      └─ FLUX Part
~~~

UPD + Part Swap.
The consumer does not know concrete backend internals.

### Pattern C: long-running worker

~~~text
Application
 -> StartRequested Message
 -> Worker Subject
 -> Progress Message
 -> Completed / Failed Message
~~~

UPD + Message Orientated Design.
Worker-internal algorithms remain normal function calls.

### Pattern D: quality orchestration

~~~text
Process Orchestrator
 -> Router Part
 -> Generator Part(s)
 -> Evaluator Part(s)
 -> Ranker
 -> Repair
 -> Retry / Fallback
~~~

UPD + Part Swap + Process Orchestrator.
Add an outer Commander only if request/result dispatch needs a separate control point.
Add Message only if a process/service boundary actually needs it.

### Pattern E: cross-Application training

~~~text
Character Registry Subject
 -> TrainCharacterRequested
 -> Training Subject

Training Subject
 -> TrainingProgress
 -> TrainingCompleted
 -> Character Registry Subject
~~~

UPD + Part Swap + Message.
Add Commander inside Training only if method/workflow selection becomes complex.

## Contract taxonomy

Keep Contracts separated by meaning.

### Value / DTO Contract
Stateless boundary data.

Examples:
- settings snapshot
- generation request values
- evaluation result
- artifact reference

### Part Contract
Input/output/capability for a replaceable implementation.

Examples:
- GenerationBackend
- Evaluator
- OCR detector
- Trainer adapter

Placement:
- Keep a Contract inside its Application when only that Application uses it.
- Promote it to `shared/contracts` only when it is a genuine cross-Application/public contract.
- Do not use `shared/contracts` as a dumping ground for types with unclear ownership.

### Message Contract
Immutable communication between independent stateful subjects.

Examples:
- TrainCharacterRequested
- TrainingProgress
- CancelRequested
- TrainingCompleted

Placement:
- Keep Messages Application-local when the communicating subjects are internal to one Application.
- Treat only cross-Application / cross-process Messages as shared/public protocol contracts.
- The transport wire schema does not have to be identical to the internal typed Message; an adapter may translate between them.

A generic `request/response` kind is not mandatory; the Message type itself may carry the meaning.

### Operation / Job Contract
Execution semantics such as run / cancel / resume / progress / retry / artifact.

Prefer the shared #435-#441 contracts.

### External API Contract
Transport boundary for HTTP / WebSocket / IPC.

Do not expose internal models as wire formats without an adapter when their lifecycle/evolution differs.

## State ownership

Every mutable state has one owner.

- Do not mutate owned state from outside its owner.
- Across a subject boundary, request changes through Messages.
- Across a Part boundary, pass input and return a result.
- Do not use shared mutable global state as a communication channel.
- Caches must have explicit owner / lifecycle / invalidation.
- Process/Data must not directly manipulate UI widget state.
- Another Application must not directly mutate worker/job state.

## Error / cancellation semantics

### Plain function / Part boundary

For local synchronous boundaries, use as appropriate:
- typed result
- explicit exception
- result object carrying failure detail

### Message boundary

Use semantic Messages when needed, for example:
- RequestRejected
- OperationFailed
- CancelRequested
- CancelAccepted
- Cancelled
- Completed

Message Manager must not interpret failures and decide retries/domain behavior.
Retry/fallback decisions belong to Process / Commander.

### Correlation

A global Message ID is not required.
Add a correlation ID only when needed to:
- match request/response
- distinguish concurrent jobs
- target progress/cancellation to a run
- trace distributed transport

Reuse #435 Run Manifest run_id or other existing identity when it already satisfies the need.

## Testing matrix

| Design axis | Primary tests |
|---|---|
| UPD | layer responsibility / UI->Data bypass / Application internal dependency |
| Part Swap | public contract / fake replacement / consumer unchanged |
| Message | immutability / type dispatch / response-failure-cancel / delivery-only manager / receiver replacement |
| Process Orchestrator | workflow iteration / state transition / retry-repair loops / I/O separation |
| Commander | dispatch / continuation selection / no direct work or complex loops |
| External transport | serialization / timeout / protocol error / reconnect where applicable |

Internal helper tests alone do not prove a boundary is complete.
Conversely, do not require Message infrastructure tests for local code that intentionally uses normal function calls.

## Directory patterns

Physical directories support responsibility; they are not the goal.

### Simple Application

~~~text
applications/example/
├ ui/
│  └ view.py
├ process/
│  └ service.py
└ data/
   └ store.py
~~~

### Complex Application

Add only roles with real responsibility.

~~~text
applications/example/
├ ui/
├ process/
│  ├ commander/                         # only when dispatch control is needed
│  ├ processing/
│  │  ├ workflow_orchestrator.py        # when dynamic workflow logic is needed
│  │  └ ...
│  └ messenger/                         # only when transport is a responsibility
└ data/
~~~

Process Orchestrator is not a fourth UPD role; it is a **kind of Process Processing**.
Existing `messenger/` / `commander/` layouts may remain while they have a real responsibility.
Do not create empty role folders in new code merely for symmetry.

## Architecture review checklist

For a new Application / major feature, review only the applicable items.

### Responsibility
- [ ] UI / Process / Data ownership is explainable
- [ ] no UI -> Data bypass
- [ ] no direct dependency on another Application's internals

### Part boundary
- [ ] only responsibilities with real replacement value become Parts
- [ ] consumers do not know private implementations
- [ ] swapping stays inside composition root / binding / part
- [ ] add fake/minimal replacement tests when useful

### State / Message
- [ ] mutable state has one owner
- [ ] Message is considered only across independent state/lifecycle subjects
- [ ] Message boundary preserves from/to/type/content semantics and immutability
- [ ] no domain work leaks into Receptor / Message Manager
- [ ] no unnecessary global event bus

### Orchestration
- [ ] dynamic loops / retry / candidate iteration live in Process Orchestrator when needed
- [ ] simple flows remain Orchestrator/Commander-free
- [ ] Commander has a clear dispatch/continuation-control reason
- [ ] Commander contains no algorithm / complex loop / I/O work

### Runtime / quality
- [ ] reuse #435-#441 shared execution contracts where applicable
- [ ] separate generator/evaluator for quality-sensitive work
- [ ] cancellation / failure / artifact ownership is clear

### Complexity stop
- [ ] no interface / registry / Message / Commander added only for hypothetical future use
- [ ] one-owner internals are not over-fragmented

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
