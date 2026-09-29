"""Command-line entrypoint for saving, listing, and running saved sequences."""

from __future__ import annotations

import argparse
from collections.abc import Mapping
import json
import os
from pathlib import Path
import sys
from typing import Any, TextIO

from comfyui_support_tools.applications.sequence.data.processing.comfyui_generate_command import (
    ComfyUIGenerateCommand,
)
from comfyui_support_tools.applications.sequence.data.processing.ollama_prompt_command import (
    OllamaPromptCommand,
)
from comfyui_support_tools.applications.sequence.data.processing.sequence_store import SequenceStore
from comfyui_support_tools.applications.sequence.data.processing.tagger_command import TaggerCommand
from comfyui_support_tools.applications.sequence.process.processing.sequence_runner import SequenceRunner
from comfyui_support_tools.shared.contracts.sequence_contracts import SequenceRunResult


DEFAULT_SEQUENCE_DIRECTORY = Path("user_data/input/config/sequences")


def _build_runner() -> SequenceRunner:
    commands = {
        "comfyui_generate": ComfyUIGenerateCommand(),
        "ollama_prompt": OllamaPromptCommand(),
        "tagger": TaggerCommand(),
    }
    return SequenceRunner(commands)


def _sequence_directory(value: str | None) -> Path:
    configured = value or os.environ.get("KADOKA_SEQUENCE_DIR")
    return Path(configured).expanduser() if configured else DEFAULT_SEQUENCE_DIRECTORY


def _definition_names(directory: Path) -> list[str]:
    if not directory.is_dir():
        raise FileNotFoundError(f"sequence directory does not exist: {directory}")
    return sorted(path.stem for path in directory.glob("*.json") if path.is_file())


def _json_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value


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


def _write_json(stream: TextIO, value: Any) -> None:
    stream.write(json.dumps(value, ensure_ascii=False, indent=2))
    stream.write("\n")


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
