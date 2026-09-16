from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

from select_task import DEFAULT_REPOSITORY, Issue, _request_json, compact_packet


@dataclass(frozen=True)
class TaskPacket:
    issue: int
    title: str
    priority: str
    url: str
    goal: list[str]
    scope: list[str]
    out_of_scope: list[str]
    required: list[str]
    acceptance: list[str]
    dependencies: list[str]
    validation: list[str]
    changed_files: list[str]


SECTION_MAP = {
    "目的": "goal",
    "goal": "goal",
    "対応内容": "scope",
    "scope": "scope",
    "方針": "scope",
    "必須要件": "required",
    "required": "required",
    "完了条件": "acceptance",
    "acceptance": "acceptance",
    "依存": "dependencies",
    "dependencies": "dependencies",
    "validation": "validation",
    "検証": "validation",
    "out of scope": "out_of_scope",
    "対象外": "out_of_scope",
}


def fetch_issue(repository: str, number: int, token: str | None = None) -> Issue:
    payload = _request_json(f"https://api.github.com/repos/{repository}/issues/{number}", token)
    if not isinstance(payload, dict) or "pull_request" in payload:
        raise RuntimeError(f"Issue #{number} was not found")
    return Issue(
        number=int(payload["number"]),
        title=str(payload.get("title", "")),
        body=str(payload.get("body") or ""),
        html_url=str(payload.get("html_url", "")),
    )


def parse_sections(body: str) -> dict[str, list[str]]:
    result = {value: [] for value in set(SECTION_MAP.values())}
    current: str | None = None
    for raw_line in body.splitlines():
        line = raw_line.strip()
        if line.startswith("## "):
            heading = line[3:].strip().lower()
            current = next((value for key, value in SECTION_MAP.items() if key in heading), None)
            continue
        if current is None or not line:
            continue
        if line.startswith("-"):
            result[current].append(line.lstrip("- "))
        elif not line.startswith("#") and len(result[current]) < 3:
            result[current].append(line)
    return result


def git_changed_files(base: str = "main") -> list[str]:
    try:
        proc = subprocess.run(
            ["git", "diff", "--name-only", f"{base}...HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return []
    return [line.strip() for line in proc.stdout.splitlines() if line.strip()]


def build_packet(issue: Issue, changed_files: list[str] | None = None) -> TaskPacket:
    sections = parse_sections(issue.body)
    compact = compact_packet(issue)
    acceptance = sections["acceptance"] or list(compact["acceptance"])
    return TaskPacket(
        issue=issue.number,
        title=issue.title,
        priority=issue.priority,
        url=issue.html_url,
        goal=sections["goal"][:4],
        scope=sections["scope"][:8],
        out_of_scope=sections["out_of_scope"][:6],
        required=sections["required"][:10],
        acceptance=acceptance[:10],
        dependencies=sections["dependencies"][:8],
        validation=sections["validation"][:8],
        changed_files=(changed_files if changed_files is not None else git_changed_files())[:30],
    )


def write_packet(packet: TaskPacket, root: Path = Path(".codex/tasks")) -> Path:
    task_dir = root / str(packet.issue)
    task_dir.mkdir(parents=True, exist_ok=True)
    path = task_dir / "task.json"
    path.write_text(json.dumps(asdict(packet), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create a compact Codex task packet from one GitHub Issue.")
    parser.add_argument("issue", type=int)
    parser.add_argument("--repo", default=DEFAULT_REPOSITORY)
    parser.add_argument("--base", default="main")
    parser.add_argument("--output-root", default=".codex/tasks")
    parser.add_argument("--stdout", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    import os

    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        issue = fetch_issue(args.repo, args.issue, os.getenv("GITHUB_TOKEN"))
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    packet = build_packet(issue, git_changed_files(args.base))
    if args.stdout:
        print(json.dumps(asdict(packet), ensure_ascii=False, indent=2))
        return 0

    path = write_packet(packet, Path(args.output_root))
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
