from __future__ import annotations

import argparse
import json
import os
import subprocess
import ssl
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass

import certifi

DEFAULT_REPOSITORY = "tomiya7688/comfyUI_support_tools"
SAFE_MERGEABLE_STATES = {"clean", "unstable"}
BLOCKING_STATUS_STATES = {"failure", "error"}
SAFE_CHECK_CONCLUSIONS = {"success", "neutral", "skipped"}


# {
#   責務: [
#     SafetyResult: PR safety decisionと停止理由を保持する
#   ],
#   処理: [
#     1: 宣言に対応する状態を保持する,
#     2: 主要methodがその状態を構築・検査・変換・出力する,
#   ],
#   フィールド: [
#     ok: bool field stored by this declaration,
#     reasons: tuple[str, ...] field stored by this declaration,
#   ],
#   引数: [],
#   戻り値: [
#     SafetyResult: instance of this class,
#   ],
# }
@dataclass(frozen=True)
class SafetyResult:
    ok: bool
    reasons: tuple[str, ...]


# {
#   責務: [
#     _run_git: repository rootでgit commandを実行してstdoutを返す
#   ],
#   処理: [
#     1: 必要なexternal commandを実行しreturn statusを確認する,
#     2: validated resultをcallerへ返す,
#   ],
#   引数: [
#     *args: *args value used by _run_git (str),
#   ],
#   戻り値: [
#     result: str as described by the annotated return type,
#   ],
#   副作用: [
#     external processを起動し、結果を取得する,
#   ],
# }
def _run_git(*args: str) -> str:
    proc = subprocess.run(
        ["git", *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return proc.stdout.strip()


# {
#   責務: [
#     current_branch: 現在のgit branch名を取得する
#   ],
#   処理: [
#     1: 引数と既存stateを検証して処理結果を算出する,
#     2: validated resultをcallerへ返す,
#   ],
#   引数: [],
#   戻り値: [
#     result: str as described by the annotated return type,
#   ],
# }
def current_branch() -> str:
    return _run_git("branch", "--show-current")


# {
#   責務: [
#     changed_files: baseとのdiffから変更file pathsを取得する
#   ],
#   処理: [
#     1: 引数と既存stateを検証して処理結果を算出する,
#     2: validated resultをcallerへ返す,
#   ],
#   引数: [
#     base: git base reference (str),
#   ],
#   戻り値: [
#     result: list[str] as described by the annotated return type,
#   ],
# }
def changed_files(base: str = "main") -> list[str]:
    output = _run_git("diff", "--name-only", f"{base}...HEAD")
    return [line.strip() for line in output.splitlines() if line.strip()]


# {
#   責務: [_request_json: 管理対象CA bundleで検証しながらGitHub JSONを取得する]
#   処理: [1: 認証要求を組み立てる, 2: certifiでTLS検証する, 3: JSON応答をdecodeする]
#   引数: [url: GitHub API URL, token: Optional API token]
#   戻り値: [payload: decode済みJSON応答]
#   エラー: [RuntimeError: GitHub APIエラーまたは接続不可]
# }
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
        with urllib.request.urlopen(
            request,
            timeout=15,
            context=ssl.create_default_context(cafile=certifi.where()),
        ) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"GitHub API error: HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"GitHub API unavailable: {exc.reason}") from exc


# {
#   責務: [
#     fetch_pr: repositoryとPR番号からPR detailsを取得する
#   ],
#   処理: [
#     1: 引数と既存stateを検証して処理結果を算出する,
#     2: validated resultをcallerへ返す,
#   ],
#   引数: [
#     repository: GitHub repository owner/name (str),
#     number: GitHub issue or pull request number (int),
#     token: GitHub API credential (str | None),
#   ],
#   戻り値: [
#     result: dict[str, object] as described by the annotated return type,
#   ],
#   エラー: [
#     RuntimeError: invalid input, unsafe path, or command failure,
#   ],
# }
def fetch_pr(repository: str, number: int, token: str | None = None) -> dict[str, object]:
    payload = _request_json(f"https://api.github.com/repos/{repository}/pulls/{number}", token)
    if not isinstance(payload, dict):
        raise RuntimeError("Unexpected pull request response")
    return payload


# {
#   責務: [
#     fetch_combined_status: commit SHAのcombined GitHub statusを取得する
#   ],
#   処理: [
#     1: 引数と既存stateを検証して処理結果を算出する,
#     2: validated resultをcallerへ返す,
#   ],
#   引数: [
#     repository: GitHub repository owner/name (str),
#     sha: commit SHA (str),
#     token: GitHub API credential (str | None),
#   ],
#   戻り値: [
#     result: dict[str, object] as described by the annotated return type,
#   ],
#   エラー: [
#     RuntimeError: invalid input, unsafe path, or command failure,
#   ],
# }
def fetch_combined_status(repository: str, sha: str, token: str | None = None) -> dict[str, object]:
    payload = _request_json(f"https://api.github.com/repos/{repository}/commits/{sha}/status", token)
    if not isinstance(payload, dict):
        raise RuntimeError("Unexpected commit status response")
    return payload


# {
#   責務: [
#     fetch_check_runs: commit SHAのindividual GitHub check runsを取得する
#   ],
#   処理: [
#     1: 引数と既存stateを検証して処理結果を算出する,
#     2: validated resultをcallerへ返す,
#   ],
#   引数: [
#     repository: GitHub repository owner/name (str),
#     sha: commit SHA (str),
#     token: GitHub API credential (str | None),
#   ],
#   戻り値: [
#     result: dict[str, object] as described by the annotated return type,
#   ],
#   エラー: [
#     RuntimeError: invalid input, unsafe path, or command failure,
#   ],
# }
def fetch_check_runs(repository: str, sha: str, token: str | None = None) -> dict[str, object]:
    payload = _request_json(f"https://api.github.com/repos/{repository}/commits/{sha}/check-runs", token)
    if not isinstance(payload, dict):
        raise RuntimeError("Unexpected check-runs response")
    return payload


# {
#   責務: [
#     _ref_name: PR objectからbase/head branch refを解決する
#   ],
#   処理: [
#     1: 引数と既存stateを検証して処理結果を算出する,
#     2: validated resultをcallerへ返す,
#   ],
#   引数: [
#     pr: GitHub pull request object (dict[str, object]),
#     side: base or head selector (str),
#   ],
#   戻り値: [
#     result: str as described by the annotated return type,
#   ],
# }
def _ref_name(pr: dict[str, object], side: str) -> str:
    value = pr.get(side)
    return str(value.get("ref") or "") if isinstance(value, dict) else ""


# {
#   責務: [
#     _repo_name: PR objectからbase/head repository full nameを解決する
#   ],
#   処理: [
#     1: 引数と既存stateを検証して処理結果を算出する,
#     2: validated resultをcallerへ返す,
#   ],
#   引数: [
#     pr: GitHub pull request object (dict[str, object]),
#     side: base or head selector (str),
#   ],
#   戻り値: [
#     result: str as described by the annotated return type,
#   ],
# }
def _repo_name(pr: dict[str, object], side: str) -> str:
    value = pr.get(side)
    if not isinstance(value, dict):
        return ""
    repo = value.get("repo")
    return str(repo.get("full_name") or "") if isinstance(repo, dict) else ""


# {
#   責務: [
#     evaluate: branch、repository、checks、filesを照合してsafe-to-merge resultを作る
#   ],
#   処理: [
#     1: 引数と既存stateを検証して処理結果を算出する,
#     2: validated resultをcallerへ返す,
#   ],
#   引数: [
#     branch: branch value used by evaluate (str),
#     pr: GitHub pull request object (dict[str, object]),
#     status: combined GitHub status (dict[str, object]),
#     checks: CI check results (dict[str, object]),
#     files: filesystem paths to inspect (list[str]),
#     allowed_prefixes: allowed PR branch prefixes (tuple[str, ...]),
#     expected_repository: expected GitHub repository name (str),
#     expected_base: expected PR base branch (str),
#   ],
#   戻り値: [
#     result: SafetyResult as described by the annotated return type,
#   ],
# }
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


# {
#   責務: [
#     parse_args: PR safety CLI optionsをargparse Namespaceへparseする
#   ],
#   処理: [
#     1: 引数と既存stateを検証して処理結果を算出する,
#     2: validated resultをcallerへ返す,
#   ],
#   引数: [
#     argv: command-line argument vector (list[str]),
#   ],
#   戻り値: [
#     result: argparse.Namespace as described by the annotated return type,
#   ],
# }
def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Stop automated PR handling on unsafe or unknown states.")
    parser.add_argument("pr", type=int)
    parser.add_argument("--repo", default=DEFAULT_REPOSITORY)
    parser.add_argument("--base", default="main")
    parser.add_argument("--allow-prefix", action="append", default=[])
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


# {
#   責務: [
#     main: PRとbranchのsafety条件を検証し、結果と終了statusを出力する
#   ],
#   処理: [
#     1: CLI argumentsをparseする (),
#     2: PRとbranchのsafety条件を検証し、結果と終了statusを出力する,
#     3: resultとexit statusを返す,
#   ],
#   引数: [
#     argv: command-line argument vector (list[str] | None),
#   ],
#   戻り値: [
#     result: int as described by the annotated return type,
#   ],
#   副作用: [
#     GitHub REST APIからPR/check statusを取得する,
#     git commandsをexternal processとして実行する,
#     safety判定とerrorを標準出力または標準errorへ表示する,
#   ],
#   エラー: [
#     RuntimeError: invalid input, unsafe path, or command failure,
#   ],
# }
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
