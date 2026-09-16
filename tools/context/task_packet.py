from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

from diff_context import DiffContext, collect_diff_context
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
    changed_symbols: list[str]
    compact_patch: list[str]


SECTION_MAP = {
    "目的": "goal", "goal": "goal",
    "対応内容": "scope", "scope": "scope", "方針": "scope",
    "必須要件": "required", "required": "required",
    "完了条件": "acceptance", "acceptance": "acceptance",
    "依存": "dependencies", "dependencies": "dependencies",
    "validation": "validation", "検証": "validation",
    "out of scope": "out_of_scope", "対象外": "out_of_scope",
}


def fetch_issue(repository: str, number: int, token: str | None = None) -> Issue:
    payload = _request_json(f"https://api.github.com/repos/{repository}/issues/{number}", token)
    if not isinstance(payload, dict) or "pull_request" in payload:
        raise RuntimeError(f"Issue #{number} was not found")
    return Issue(int(payload["number"]), str(payload.get("title", "")), str(payload.get("body") or ""), str(payload.get("html_url", "")))


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


def build_packet(issue: Issue, diff: DiffContext | None = None) -> TaskPacket:
    sections = parse_sections(issue.body)
    compact = compact_packet(issue)
    diff = diff or DiffContext([], [], [])
    return TaskPacket(
        issue.number, issue.title, issue.priority, issue.html_url,
        sections["goal"][:4], sections["scope"][:8], sections["out_of_scope"][:6],
        sections["required"][:10], (sections["acceptance"] or list(compact["acceptance"]))[:10],
        sections["dependencies"][:8], sections["validation"][:8],
        diff.changed_files[:30], diff.changed_symbols[:30], diff.patch_lines[:80],
    )


def write_packet(packet: TaskPacket, root: Path = Path(".codex/tasks")) -> Path:
    task_dir = root / str(packet.issue)
    task_dir.mkdir(parents=True, exist_ok=True)
    path = task_dir / "task.json"
    path.write_text(json.dumps(asdict(packet), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Create a compact Codex task packet from one GitHub Issue.")
    parser.add_argument("issue", type=int)
    parser.add_argument("--repo", default=DEFAULT_REPOSITORY)
    parser.add_argument("--base", default="main")
    parser.add_argument("--max-patch-lines", type=int, default=80)
    parser.add_argument("--output-root", default=".codex/tasks")
    parser.add_argument("--stdout", action="store_true")
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    try:
        issue = fetch_issue(args.repo, args.issue, os.getenv("GITHUB_TOKEN"))
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    packet = build_packet(issue, collect_diff_context(args.base, max(0, args.max_patch_lines)))
    if args.stdout:
        print(json.dumps(asdict(packet), ensure_ascii=False, indent=2))
    else:
        print(write_packet(packet, Path(args.output_root)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
