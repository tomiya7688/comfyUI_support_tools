from __future__ import annotations

import argparse
import json
import os
import re
import ssl
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass

import certifi

DEFAULT_REPOSITORY = "tomiya7688/comfyUI_support_tools"
PRIORITY_ORDER = ("P0", "P1", "P2", "P3")
NON_TASK_TITLES = ("roadmap", "索引", "backlog", "バックログ", "基盤を導入")


# {
#   責務: [
#     Issue: GitHub issue title/body/priority metadataを保持する
#   ],
#   処理: [
#     1: 宣言に対応する状態を保持する,
#     2: 主要methodがその状態を構築・検査・変換・出力する,
#   ],
#   フィールド: [
#     number: int field stored by this declaration,
#     title: str field stored by this declaration,
#     body: str field stored by this declaration,
#     html_url: str field stored by this declaration,
#   ],
#   引数: [],
#   戻り値: [
#     Issue: instance of this class,
#   ],
# }
@dataclass(frozen=True)
class Issue:
    number: int
    title: str
    body: str
    html_url: str

# {
#   責務: [
#     priority: issue titleからpriority labelを抽出する
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
    @property
    def priority(self) -> str:
        match = re.search(r"\[(P[0-3])\]", self.title, re.IGNORECASE)
        return match.group(1).upper() if match else "P3"

# {
#   責務: [
#     is_implementation_task: issueが実装作業向けかを判定する
#   ],
#   処理: [
#     1: 引数と既存stateを検証して処理結果を算出する,
#     2: validated resultをcallerへ返す,
#   ],
#   引数: [],
#   戻り値: [
#     result: bool as described by the annotated return type,
#   ],
# }
    @property
    def is_implementation_task(self) -> bool:
        title = self.title.lower()
        return not any(marker.lower() in title for marker in NON_TASK_TITLES)


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
        "User-Agent": "comfyui-support-tools-context-selector",
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
#     fetch_open_issues: repositoryからopen issuesを取得し、Issue recordsへ変換する
#   ],
#   処理: [
#     1: 引数と既存stateを検証して処理結果を算出する,
#     2: validated resultをcallerへ返す,
#   ],
#   引数: [
#     repository: GitHub repository owner/name (str),
#     token: GitHub API credential (str | None),
#   ],
#   戻り値: [
#     result: list[Issue] as described by the annotated return type,
#   ],
#   エラー: [
#     RuntimeError: invalid input, unsafe path, or command failure,
#   ],
# }
def fetch_open_issues(repository: str, token: str | None = None) -> list[Issue]:
    url = f"https://api.github.com/repos/{repository}/issues?state=open&per_page=100"
    payload = _request_json(url, token)
    if not isinstance(payload, list):
        raise RuntimeError("Unexpected GitHub API response")

    issues: list[Issue] = []
    for item in payload:
        if not isinstance(item, dict) or "pull_request" in item:
            continue
        issues.append(
            Issue(
                number=int(item["number"]),
                title=str(item.get("title", "")),
                body=str(item.get("body") or ""),
                html_url=str(item.get("html_url", "")),
            )
        )
    return issues


# {
#   責務: [
#     select_issue: priority、dependency、更新順から次のissueを選ぶ
#   ],
#   処理: [
#     1: 引数と既存stateを検証して処理結果を算出する,
#     2: validated resultをcallerへ返す,
#   ],
#   引数: [
#     issues: issues value used by select_issue (list[Issue]),
#   ],
#   戻り値: [
#     result: Issue | None as described by the annotated return type,
#   ],
# }
def select_issue(issues: list[Issue]) -> Issue | None:
    candidates = [issue for issue in issues if issue.is_implementation_task]
    if not candidates:
        return None

    priority_rank = {priority: index for index, priority in enumerate(PRIORITY_ORDER)}
    return min(
        candidates,
        key=lambda issue: (priority_rank.get(issue.priority, len(PRIORITY_ORDER)), issue.number),
    )


# {
#   責務: [
#     compact_packet: issue bodyからGoal/Required/Acceptanceのcompact packetを作る
#   ],
#   処理: [
#     1: 引数と既存stateを検証して処理結果を算出する,
#     2: validated resultをcallerへ返す,
#   ],
#   引数: [
#     issue: issue metadata (Issue),
#   ],
#   戻り値: [
#     result: dict[str, object] as described by the annotated return type,
#   ],
# }
def compact_packet(issue: Issue) -> dict[str, object]:
    acceptance = []
    capture = False
    for raw_line in issue.body.splitlines():
        line = raw_line.strip()
        if line.startswith("## "):
            capture = "完了条件" in line or "Acceptance" in line
            continue
        if capture and line.startswith("-"):
            acceptance.append(line.lstrip("- "))
        elif capture and line:
            capture = False

    return {
        "issue": issue.number,
        "priority": issue.priority,
        "title": issue.title,
        "url": issue.html_url,
        "acceptance": acceptance[:8],
    }


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
    parser = argparse.ArgumentParser(description="Select one highest-priority implementation Issue.")
    parser.add_argument("--repo", default=DEFAULT_REPOSITORY, help="GitHub repository in owner/name form")
    parser.add_argument("--json", action="store_true", help="Emit JSON")
    return parser.parse_args(argv)


# {
#   責務: [
#     main: GitHub open issue一覧から実装対象issueを選び、選択情報を出力する
#   ],
#   処理: [
#     1: CLI argumentsをparseする (),
#     2: GitHub open issue一覧から実装対象issueを選び、選択情報を出力する,
#     3: resultとexit statusを返す,
#   ],
#   引数: [
#     argv: command-line argument vector (list[str] | None),
#   ],
#   戻り値: [
#     result: int as described by the annotated return type,
#   ],
#   副作用: [
#     GitHub REST APIからopen issue dataを取得する,
#     選択issueを標準出力へ表示する,
#   ],
# }
def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        issue = select_issue(fetch_open_issues(args.repo, os.getenv("GITHUB_TOKEN")))
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    if issue is None:
        print("No implementation Issue found.")
        return 1

    packet = compact_packet(issue)
    if args.json:
        print(json.dumps(packet, ensure_ascii=False, separators=(",", ":")))
    else:
        print(f"#{packet['issue']} {packet['priority']} {packet['title']}")
        for item in packet["acceptance"]:
            print(f"- {item}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
