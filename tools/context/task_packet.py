from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

from diff_context import DiffContext, collect_diff_context
from select_task import DEFAULT_REPOSITORY, Issue, _request_json, compact_packet


# {
#   責務: [
#     TaskPacket: issue情報、required sections、change contextを保持する
#   ],
#   処理: [
#     1: 宣言に対応する状態を保持する,
#     2: 主要methodがその状態を構築・検査・変換・出力する,
#   ],
#   フィールド: [
#     issue: int field stored by this declaration,
#     title: str field stored by this declaration,
#     priority: str field stored by this declaration,
#     url: str field stored by this declaration,
#     goal: list[str] field stored by this declaration,
#     scope: list[str] field stored by this declaration,
#     out_of_scope: list[str] field stored by this declaration,
#     required: list[str] field stored by this declaration,
#     acceptance: list[str] field stored by this declaration,
#     dependencies: list[str] field stored by this declaration,
#     validation: list[str] field stored by this declaration,
#     changed_files: list[str] field stored by this declaration,
#     changed_symbols: list[str] field stored by this declaration,
#     compact_patch: list[str] field stored by this declaration,
#   ],
#   引数: [],
#   戻り値: [
#     TaskPacket: instance of this class,
#   ],
# }
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


# {
#   責務: [
#     fetch_issue: GitHub REST APIから指定 issueを取得してvalidated Issue objectへ変換する
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
#     result: Issue as described by the annotated return type,
#   ],
#   エラー: [
#     RuntimeError: invalid input, unsafe path, or command failure,
#   ],
# }
def fetch_issue(repository: str, number: int, token: str | None = None) -> Issue:
    payload = _request_json(f"https://api.github.com/repos/{repository}/issues/{number}", token)
    if not isinstance(payload, dict) or "pull_request" in payload:
        raise RuntimeError(f"Issue #{number} was not found")
    return Issue(int(payload["number"]), str(payload.get("title", "")), str(payload.get("body") or ""), str(payload.get("html_url", "")))


# {
#   責務: [
#     parse_sections: issue markdownからGoal/Required/Acceptance/Constraints sectionsを抽出する
#   ],
#   処理: [
#     1: 引数と既存stateを検証して処理結果を算出する,
#     2: validated resultをcallerへ返す,
#   ],
#   引数: [
#     body: body value used by parse_sections (str),
#   ],
#   戻り値: [
#     result: dict[str, list[str]] as described by the annotated return type,
#   ],
# }
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


# {
#   責務: [
#     build_packet: Issueとgit diff contextからcompact TaskPacketを組み立てる
#   ],
#   処理: [
#     1: 引数と既存stateを検証して処理結果を算出する,
#     2: validated resultをcallerへ返す,
#   ],
#   引数: [
#     issue: issue metadata (Issue),
#     diff: compact source diff context (DiffContext | None),
#   ],
#   戻り値: [
#     result: TaskPacket as described by the annotated return type,
#   ],
# }
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


# {
#   責務: [
#     write_packet: TaskPacket JSONをrepository-local context directoryへ書き出す
#   ],
#   処理: [
#     1: 計画したfilesystem output/updateを適用する,
#     2: validated resultをcallerへ返す,
#   ],
#   引数: [
#     packet: packet value used by write_packet (TaskPacket),
#     root: repository or migration root (Path),
#   ],
#   戻り値: [
#     result: Path as described by the annotated return type,
#   ],
#   副作用: [
#     指定されたfilesystem pathsを作成、更新、移動、置換、または削除する,
#   ],
# }
def write_packet(packet: TaskPacket, root: Path = Path(".codex/tasks")) -> Path:
    task_dir = root / str(packet.issue)
    task_dir.mkdir(parents=True, exist_ok=True)
    path = task_dir / "task.json"
    path.write_text(json.dumps(asdict(packet), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


# {
#   責務: [
#     main: GitHub issueと現在のdiffからtask packetを作成し、JSON出力または保存する
#   ],
#   処理: [
#     1: CLI argumentsをparseする (issue, --repo, --base, --max-patch-lines, --output-root, --stdout),
#     2: GitHub issueと現在のdiffからtask packetを作成し、JSON出力または保存する,
#     3: resultとexit statusを返す,
#   ],
#   引数: [
#     argv: command-line argument vector (list[str] | None),
#   ],
#   戻り値: [
#     result: int as described by the annotated return type,
#   ],
#   副作用: [
#     GitHub REST APIからissue dataを取得する,
#     --stdout未指定時はtask packet JSONをoutput directoryへ書き込む,
#     packetまたはerrorを標準出力または標準errorへ表示する,
#   ],
# }
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
