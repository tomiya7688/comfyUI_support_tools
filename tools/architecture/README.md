# App boundary checks

`app_boundary_check.py` enforces the distribution rule that packaged apps/services may live in the same one-dir folder, but must not share Python runtimes or internal implementation details.

Allowed communication is through explicit process boundaries and APIs (for example HTTP/WebSocket). Packaged sibling executables may be started directly.

Legacy violations are recorded in `app_boundary_baseline.json` with a maximum count and a reason. New violations fail the check, and reducing an existing violation also fails until the baseline is reduced, preventing stale exemptions.

Run:

```bash
python tools/architecture/app_boundary_check.py
```

The completion gate runs this automatically.
