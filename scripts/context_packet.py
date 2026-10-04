"""Generate a small, reproducible work packet from a GitHub Issue.

The command deliberately stores issue metadata and a bounded diff instead of
copying repository-wide documents into every task context.
"""
from __future__ import annotations

import argparse
import ast
import json
import subprocess
from pathlib import Path


# {
#   "責務": "repository rootをworking directoryにしてsubprocessを実行しstdoutを返す。",
#   "処理": ["text captureとUTF-8 replacementを有効にして実行する", "nonzero exitを例外として伝える"],
#   "引数": {"command": "argv list", "cwd": "working directory"}, "戻り値": "標準出力文字列"
# }
def run(command: list[str], cwd: Path) -> str:
    result = subprocess.run(
        command,
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return result.stdout


# {
#   "責務": "baseとHEAD間で変更されたrelative file pathを列挙する。",
#   "処理": ["git diff --name-onlyを実行し空行を除いて返す"],
#   "引数": {"root": "repository root", "base": "比較するgit ref"}, "戻り値": "変更file path list"
# }
def changed_files(root: Path, base: str) -> list[str]:
    output = run(["git", "diff", "--name-only", f"{base}...HEAD"], root)
    return [line.strip() for line in output.splitlines() if line.strip()]


# {
#   "責務": "変更Python filesからclass/function宣言位置を抽出する。",
#   "処理": ["Python fileをAST parseする", "class/function/async function名とlineを収集し一意安定順で返す"],
#   "引数": {"root": "repository root", "files": "relative file path list"}, "戻り値": "宣言位置文字列list"
# }
def changed_symbols(root: Path, files: list[str]) -> list[str]:
    symbols: list[str] = []
    for relative in files:
        path = root / relative
        if path.suffix != ".py" or not path.is_file():
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=relative)
        except (OSError, SyntaxError):
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                symbols.append(f"{relative}:{node.lineno} {node.name}")
    return sorted(set(symbols))


# {
#   "責務": "GitHub Issue、変更file/symbol、bounded diffからlocal task packetを生成する。",
#   "処理": ["ghからissue metadataを取得する", "変更file・symbol・diffを集め上限を適用する", "packet内の案内file群を保存する"],
#   "引数": {"root": "repository root", "issue": "Issue number", "base": "比較git ref", "max_diff": "diff行上限"}, "戻り値": "生成したpacket directory Path"
# }
def create_packet(root: Path, issue: int, base: str, max_diff: int) -> Path:
    issue_data = json.loads(run(["gh", "issue", "view", str(issue), "--json", "number,title,body,url"], root))
    files = changed_files(root, base)
    diff = run(["git", "diff", f"{base}...HEAD", "--", *files], root) if files else ""
    diff_lines = diff.splitlines()
    if len(diff_lines) > max_diff:
        diff = "\n".join(diff_lines[:max_diff]) + f"\n\n[diff truncated at {max_diff} lines]\n"
    packet = root / ".codex" / "tasks" / str(issue)
    packet.mkdir(parents=True, exist_ok=True)
    (packet / "task.md").write_text(
        f"# Issue #{issue}: {issue_data['title']}\n\n"
        f"URL: {issue_data['url']}\n\n{issue_data.get('body', '').strip()}\n",
        encoding="utf-8",
    )
    (packet / "files.txt").write_text("\n".join(files) + ("\n" if files else ""), encoding="utf-8")
    (packet / "symbols.txt").write_text("\n".join(changed_symbols(root, files)) + "\n", encoding="utf-8")
    (packet / "constraints.md").write_text(
        "- Search-first, Read-second.\n- Keep unrelated files out of the change.\n"
        "- Validate with targeted tests and report unverified areas.\n",
        encoding="utf-8",
    )
    (packet / "diff.patch").write_text(diff, encoding="utf-8")
    return packet


# {
#   "責務": "task packet CLIの引数を解析しpacket生成を開始する。",
#   "処理": ["issue/base/root/diff上限optionを読む", "create_packetを呼び生成pathを表示する"],
#   "引数": [], "戻り値": []
# }
def main() -> None:
    parser = argparse.ArgumentParser(description="Create a bounded Codex task packet from a GitHub Issue")
    parser.add_argument("issue", type=int, help="GitHub Issue number")
    parser.add_argument("--base", default="origin/main", help="Git diff base (default: origin/main)")
    parser.add_argument("--max-diff-lines", type=int, default=400, help="Maximum diff lines in packet")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    packet = create_packet(args.root.resolve(), args.issue, args.base, max(1, args.max_diff_lines))
    print(packet)


if __name__ == "__main__":
    main()
