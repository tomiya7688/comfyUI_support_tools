"""Command-line entrypoint for saving, listing, and running saved sequences."""

from __future__ import annotations

import argparse
from collections.abc import Mapping
import json
import os
from pathlib import Path
import sys
from typing import Any, TextIO

from comfyui_support_tools.applications.sequence.data.processing.a1111_generate_command import (
    A1111GenerateCommand,
)
from comfyui_support_tools.applications.sequence.data.processing.comfyui_generate_command import (
    ComfyUIGenerateCommand,
)
from comfyui_support_tools.applications.sequence.data.processing.ollama_prompt_command import (
    OllamaPromptCommand,
)
from comfyui_support_tools.applications.sequence.data.processing.sequence_store import SequenceStore
from comfyui_support_tools.applications.sequence.data.processing.tagger_command import TaggerCommand
from comfyui_support_tools.applications.sequence.process.processing.sequence_runner import (
    SequenceRunner,
)
from comfyui_support_tools.shared.contracts.sequence_contracts import SequenceRunResult


DEFAULT_SEQUENCE_DIRECTORY = Path("user_data/input/config/sequences")


# {
#   責務: [_build_runner: sequence CLIが実行可能なbuilt-in command registryを作る]
#   処理: [A1111、ComfyUI、Ollama prompt、Tagger commandをSequenceRunnerへ登録する]
#   引数: []
#   戻り値: [SequenceRunner: built-in command mappingを持つrunner]
# }
def _build_runner() -> SequenceRunner:
    commands = {
        "a1111_generate": A1111GenerateCommand(),
        "comfyui_generate": ComfyUIGenerateCommand(),
        "ollama_prompt": OllamaPromptCommand(),
        "tagger": TaggerCommand(),
    }
    return SequenceRunner(commands)


# {
#   責務: [_sequence_directory: CLI option、環境変数、既定値の順でdefinition directoryを決める]
#   処理: [explicit valueを優先し、次にKADOKA_SEQUENCE_DIR、最後にrepository defaultを使う]
#   引数: [value: optional --directory value]
#   戻り値: [Path: expanduser済みsequence directory]
# }
def _sequence_directory(value: str | None) -> Path:
    configured = value or os.environ.get("KADOKA_SEQUENCE_DIR")
    return Path(configured).expanduser() if configured else DEFAULT_SEQUENCE_DIRECTORY


# {
#   責務: [_definition_names: directory直下のJSON sequence定義名を列挙する]
#   処理: [存在するdirectoryの*.json fileからsuffixを除いたstemをsortして返す]
#   引数: [directory: sequence definition directory]
#   戻り値: [names: sorted sequence names]
#   エラー: [FileNotFoundError: directoryが存在しない]
# }
def _definition_names(directory: Path) -> list[str]:
    if not directory.is_dir():
        raise FileNotFoundError(f"sequence directory does not exist: {directory}")
    return sorted(path.stem for path in directory.glob("*.json") if path.is_file())


# {
#   責務: [_json_value: nested mapping/list/tupleをJSON対応containerへ再帰変換する]
#   処理: [mapping keyをstring化し、配下containerを再帰的にlist/dictへ変換する]
#   引数: [value: sequence result内の値]
#   戻り値: [JSON-compatible containerまたは元scalar]
# }
def _json_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value


# {
#   責務: [_result_payload: sequence run resultをCLIのstable JSON response shapeへ変換する]
#   処理: [sequence stateとstep input/output/errorをserializable mappingへ整形する]
#   引数: [result: SequenceRunResult]
#   戻り値: [payload: JSONへ書けるsequence result object]
# }
def _result_payload(result: SequenceRunResult) -> dict[str, Any]:
    return {
        "sequence_name": result.sequence_name,
        "state": result.state,
        "steps": [
            {
                "step_id": step.step_id,
                "command": step.command,
                "state": step.state,
                "inputs": _json_value(step.inputs),
                "outputs": _json_value(step.outputs),
                "error": step.error,
            }
            for step in result.steps
        ],
    }


# {
#   責務: [_write_json: indented UTF-8互換JSONと改行を指定streamへ書く]
#   処理: [ensure_asciiをfalseにし、indent 2でdumpしてnewlineを追加する]
#   引数: [stream: 出力先text stream, value: JSON-compatible object]
#   戻り値: [なし]
#   副作用: [streamへ文字列を書き込む]
# }
def _write_json(stream: TextIO, value: Any) -> None:
    stream.write(json.dumps(value, ensure_ascii=False, indent=2))
    stream.write("\n")


# {
#   責務: [_parser: sequence save/list/run subcommandとdirectory optionを定義する]
#   処理: [argparse parser、必須action subparser、各subcommand引数を構築する]
#   引数: []
#   戻り値: [ArgumentParser: CLI argument parser]
# }
def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sequence",
        description="List or run GUI-independent saved sequences.",
    )
    parser.add_argument(
        "--directory",
        help="definition folder (default: KADOKA_SEQUENCE_DIR or user_data/input/config/sequences)",
    )
    subparsers = parser.add_subparsers(dest="action", required=True)
    save_parser = subparsers.add_parser("save", help="import a saved sequence definition")
    save_parser.add_argument("source", help="path to an exported sequence JSON file")
    save_parser.add_argument(
        "--overwrite",
        action="store_true",
        help="replace an existing definition with the same name",
    )
    subparsers.add_parser("list", help="list saved sequence names")
    run_parser = subparsers.add_parser("run", help="run one saved sequence")
    run_parser.add_argument("name", help="sequence name (without .json)")
    return parser


# {
#   責務: [main: sequence定義のsave/list/run CLIを実行しJSON結果とstatus codeを返す]
#   処理: [argvをparseし、directoryを選択してstore/runnerを実行しdomain errorsをJSON化する]
#   引数: [argv: optional args, stdout/stderr: injectable text streams, runner: injectable runner]
#   戻り値: [0:成功/done, 1:run結果がdone以外, 2: filesystem/validation/JSON error]
#   副作用: [sequence JSON filesを読み書きし、stdout/stderrへJSONを出力する]
# }
def main(
    argv: list[str] | None = None,
    *,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
    runner: SequenceRunner | None = None,
) -> int:
    args = _parser().parse_args(argv)
    output = stdout or sys.stdout
    errors = stderr or sys.stderr
    directory = _sequence_directory(args.directory)
    try:
        if args.action == "list":
            _write_json(output, {"sequences": _definition_names(directory)})
            return 0
        if args.action == "save":
            source = Path(args.source).expanduser()
            definition = SequenceStore(source.parent).load(source.stem)
            store = SequenceStore(directory)
            try:
                store.load(definition.name)
            except FileNotFoundError:
                pass
            else:
                if not args.overwrite:
                    raise FileExistsError(
                        f"sequence already exists: {definition.name}; pass --overwrite to replace it"
                    )
            saved_path = store.save(definition)
            _write_json(
                output,
                {"state": "saved", "sequence_name": definition.name, "path": str(saved_path)},
            )
            return 0
        definition = SequenceStore(directory).load(args.name)
        result = (runner or _build_runner()).run(definition)
        _write_json(output, _result_payload(result))
        return 0 if result.state == "done" else 1
    except (OSError, ValueError, json.JSONDecodeError) as error:
        _write_json(errors, {"state": "error", "error": f"{type(error).__name__}: {error}"})
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
