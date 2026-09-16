from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass

DEFAULT_REPOSITORY = "tomiya7688/comfyUI_support_tools"
SAFE_MERGEABLE_STATES = {"clean", "unstable"}
BLOCKING_CHECK_STATES = {"failure", "error"}


@dataclass(frozen=True)
class SafetyResult:
    ok: bool
    reasons: tuple[str, ...]


def _run_git(*args: str) -> str:
    proc = subprocess.run(
        ["git", *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return proc.stdout.strip()


def current_branch() -> str:
    return _run_git("branch", "--show-current")


def changed_files(base: str = "main") -> list[str]:
    output = _run_git("diff", "--name-only", f"{base}...HEAD")
    return [line.strip() for line in output.splitlines() if line.strip()]


def _request_json(url: str, token: str | None = None) -> object:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "comfyui-support-tools-pr-safety",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"GitHub API error: HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"GitHub API unavailable: {exc.reason}") from exc


def fetch_pr(repository: str, number: int, token: str | None = None) -> dict[str, object]:
    payload = _request_json(f"https://api.github.com/repos/{repository}/pulls/{number}", token)
    if not isinstance(payload, dict):
        raise RuntimeError("Unexpected pull request response")
    return payload


def fetch_combined_status(repository: str, sha: str, token: str | None = None) -> dict[str, object]:
    payload = _request_json(f"https://api.github.com/repos/{repository}/commits/{sha}/status", token)
    if not isinstance(payload, dict):
        raise RuntimeError("Unexpected commit status response")
    return payload


def evaluate(
    branch: str,
    pr: dict[str, object],
    status: dict[str, object],
    files: list[str],
    allowed_prefixes: tuple[str, ...] = (),
) -> SafetyResult:
    reasons: list[str] = []
    if branch in {"main", "master"}:
        reasons.append("working directly on the default branch is blocked")

    if bool(pr.get("draft")):
        reasons.append("pull request is still a draft")

    mergeable = pr.get("mergeable")
    mergeable_state = str(pr.get("mergeable_state") or "unknown")
    if mergeable is False:
        reasons.append("pull request is not mergeable")
    elif mergeable is None or mergeable_state == "unknown":
        reasons.append("pull request mergeability is unknown")
    elif mergeable_state not in SAFE_MERGEABLE_STATES:
        reasons.append(f"pull request mergeable_state={mergeable_state}")

    combined = str(status.get("state") or "pending")
    if combined in BLOCKING_CHECK_STATES:
        reasons.append(f"CI/status checks are {combined}")

    if allowed_prefixes:
        unexpected = [path for path in files if not path.startswith(allowed_prefixes)]
        if unexpected:
            reasons.append("unexpected diff: " + ", ".join(unexpected[:8]))

    return SafetyResult(not reasons, tuple(reasons))


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Stop automated PR handling on unsafe or unknown states.")
    parser.add_argument("pr", type=int)
    parser.add_argument("--repo", default=DEFAULT_REPOSITORY)
    parser.add_argument("--base", default="main")
    parser.add_argument("--allow-prefix", action="append", default=[])
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    token = os.getenv("GITHUB_TOKEN")
    try:
        branch = current_branch()
        files = changed_files(args.base)
        pr = fetch_pr(args.repo, args.pr, token)
        head = pr.get("head")
        if not isinstance(head, dict) or not head.get("sha"):
            raise RuntimeError("Pull request head SHA is unavailable")
        status = fetch_combined_status(args.repo, str(head["sha"]), token)
        result = evaluate(branch, pr, status, files, tuple(args.allow_prefix))
    except (RuntimeError, OSError, subprocess.CalledProcessError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps({"ok": result.ok, "reasons": result.reasons}, ensure_ascii=False))
    elif result.ok:
        print("PR safety: OK")
    else:
        print("PR safety: BLOCKED")
        for reason in result.reasons:
            print(f"- {reason}")
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
