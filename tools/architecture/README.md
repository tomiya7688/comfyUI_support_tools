# Architecture checks

Two complementary checks protect different boundaries.

## Packaged application boundary

`app_boundary_check.py` enforces the distribution rule that packaged apps/services may live in the same one-dir folder, but must not share Python runtimes or internal implementation details.

Allowed communication is through explicit process boundaries and APIs (for example HTTP/WebSocket). Packaged sibling executables may be started directly.

Run:

```bash
python tools/architecture/app_boundary_check.py
```

## UPD application structure

`upd_check.py` applies the UPD Commander rules to new code under
`src/comfyui_support_tools/applications/`.

It currently blocks:
- `UPD101`: invalid layer/role imports, including UI -> Data direct dependency
- `UPD102`: direct import of another Application's internal implementation
- `UPD201`: loops inside Commander
- `UPD202`: calculations inside Commander
- `UPD203`: direct IO/API/subprocess work inside Commander

Legacy `scripts/` is intentionally outside this strict UPD scan. Migration is incremental.

Run:

```bash
python tools/architecture/upd_check.py
```

The completion gate runs both architecture checks automatically.

## JSON-like declaration comments

The comment_coverage.py checker scans Git-tracked first-party Python files and
reports class/function/method declaration coverage. It excludes external/vendor,
generated, build/cache/output, and user/model-data paths. Existing uncovered
declarations are recorded per file in comment_coverage_baseline.json; any
increase or unreviewed decrease from the baseline, and unrecognized
source/comment structure, fail the completion gate.

Run the report with declaration locations:

    python tools/architecture/comment_coverage.py --list-uncovered

The baseline is temporary migration debt, not an exemption policy. Reduce it
with each scoped migration issue and make it zero when the parent migration is
complete. The scanner validates attachment and minimal block structure; review
is still required for semantic accuracy and required information.
