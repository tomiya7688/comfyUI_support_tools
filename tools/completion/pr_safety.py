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
BLOCKING_STATUS_STATES = {"failure", "error"}
SAFE_CHECK_CONCLUSIONS = {"success", "neutral", "skipped"}


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


def fetch_check_runs(repository: str, sha: str, token: str | None = None) -> dict[str, object]:
    payload = _request_json(f"https://api.github.com/repos/{repository}/commits/{sha}/check-runs", token)
    if not isinstance(payload, dict):
        raise RuntimeError("Unexpected check-runs response")
    return payload


def _ref_name(pr: dict[str, object], side: str) -> str:
    value = pr.get(side)
    return str(value.get("ref") or "") if isinstance(value, dict) else ""


def _repo_name(pr: dict[str, object], side: str) -> str:
    value = pr.get(side)
    if not isinstance(value, dict):
        return ""
    repo = value.get("repo")
    return str(repo.get("full_name") or "") if isinstance(repo, dict) else ""


def evaluate(
    branch: str,
    pr: dict[str, object],
    status: dict[str, object],
    checks: dict[str, object],
    files: list[str],
    allowed_prefixes: tuple[str, ...] = (),
    *,
    expected_repository: str = DEFAULT_REPOSITORY,
    expected_base: str = "main",
) -> SafetyResult:
    reasons: list[str] = []
    if branch in {"main", "master"}:
        reasons.append("working directly on the default branch is blocked")

    if str(pr.get("state") or "open") != "open":
        reasons.append("pull request is not open")

    if bool(pr.get("draft")):
        reasons.append("pull request is still a draft")

    base_ref = _ref_name(pr, "base")
    head_ref = _ref_name(pr, "head")
    base_repo = _repo_name(pr, "base")
    head_repo = _repo_name(pr, "head")

    if base_ref and base_ref != expected_base:
        reasons.append(f"pull request base is {base_ref}, expected {expected_base}")
    if head_ref and branch and branch != head_ref:
        reasons.append(f"working branch {branch} does not match PR head {head_ref}")
    if base_repo and base_repo != expected_repository:
        reasons.append(f"pull request base repository is {base_repo}, expected {expected_repository}")
    if head_repo and head_repo != expected_repository:
        reasons.append(f"pull request head repository is {head_repo}, expected {expected_repository}")
    if head_ref and base_ref and head_ref == base_ref:
        reasons.append("pull request head and base branches must differ")

    mergeable = pr.get("mergeable")
    mergeable_state = str(pr.get("mergeable_state") or "unknown")
    if mergeable is False:
        reasons.append("pull request is not mergeable")
    elif mergeable is None or mergeable_state == "unknown":
        reasons.append("pull request mergeability is unknown")
    elif mergeable_state not in SAFE_MERGEABLE_STATES:
        reasons.append(f"pull request mergeable_state={mergeable_state}")

    combined = str(status.get("state") or "pending")
    if combined in BLOCKING_STATUS_STATES:
        reasons.append(f"CI/status checks are {combined}")

    raw_runs = checks.get("check_runs", [])
    if isinstance(raw_runs, list):
        for run in raw_runs:
            if not isinstance(run, dict):
                continue
            name = str(run.get("name") or "unnamed check")
            run_status = str(run.get("status") or "")
            conclusion = run.get("conclusion")
            if run_status != "completed":
                reasons.append(f"check is not complete: {name} ({run_status or 'unknown'})")
            elif conclusion not in SAFE_CHECK_CONCLUSIONS:
                reasons.append(f"check did not pass: {name} ({conclusion or 'unknown'})")

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
        sha = str(head["sha"])
        status = fetch_combined_status(args.repo, sha, token)
        checks = fetch_check_runs(args.repo, sha, token)
        result = evaluate(
            branch,
            pr,
            status,
            checks,
            files,
            tuple(args.allow_prefix),
            expected_repository=args.repo,
            expected_base=args.base,
        )
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
