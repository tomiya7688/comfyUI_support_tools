from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass

DEFAULT_REPOSITORY = "tomiya7688/comfyUI_support_tools"
PRIORITY_ORDER = ("P0", "P1", "P2", "P3")
NON_TASK_TITLES = ("roadmap", "索引", "backlog", "バックログ", "基盤を導入")


@dataclass(frozen=True)
class Issue:
    number: int
    title: str
    body: str
    html_url: str

    @property
    def priority(self) -> str:
        match = re.search(r"\[(P[0-3])\]", self.title, re.IGNORECASE)
        return match.group(1).upper() if match else "P3"

    @property
    def is_implementation_task(self) -> bool:
        title = self.title.lower()
        return not any(marker.lower() in title for marker in NON_TASK_TITLES)


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
        with urllib.request.urlopen(request, timeout=15) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"GitHub API error: HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"GitHub API unavailable: {exc.reason}") from exc


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


def select_issue(issues: list[Issue]) -> Issue | None:
    candidates = [issue for issue in issues if issue.is_implementation_task]
    if not candidates:
        return None

    priority_rank = {priority: index for index, priority in enumerate(PRIORITY_ORDER)}
    return min(
        candidates,
        key=lambda issue: (priority_rank.get(issue.priority, len(PRIORITY_ORDER)), issue.number),
    )


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


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Select one highest-priority implementation Issue.")
    parser.add_argument("--repo", default=DEFAULT_REPOSITORY, help="GitHub repository in owner/name form")
    parser.add_argument("--json", action="store_true", help="Emit JSON")
    return parser.parse_args(argv)


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
