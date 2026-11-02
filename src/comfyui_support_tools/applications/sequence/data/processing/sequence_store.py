"""Persist versioned sequence definitions as JSON files."""

from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any

from comfyui_support_tools.shared.contracts.sequence_contracts import (
    FailurePolicy,
    SequenceDefinition,
    SequenceStep,
)


# {
# 責務: [SequenceStore: versioned sequence definitionをJSON fileから安全にload/saveする]
# フィールド: [_directory: sequence JSONを格納するdirectory]
# }
class SequenceStore:
    """Read and atomically write user-authored sequence definitions."""

    # {
    #   責務: [__init__: sequence storeが使うdirectory pathを保持する]
    #   処理: [str/PathをPathへ変換する]
    #   引数: [self: store instance, directory: sequence files directory]
    #   戻り値: [なし]
    # }
    def __init__(self, directory: str | Path) -> None:
        self._directory = Path(directory)

    # {
    #   責務: [save: sequence definitionをJSONへ変換しatomic replaceで保存する]
    #   処理: [directory作成、target名検証、temporary file書込、os.replaceを行う]
    #   引数: [self: store instance, definition: 保存するSequenceDefinition]
    #   戻り値: [Path: 保存したdefinition file]
    #   エラー: [OSError/ValueError: serializationまたはfilesystem operation失敗]
    #   副作用: [一時fileを作成しtarget JSONを原子的に置換する]
    # }
    def save(self, definition: SequenceDefinition) -> Path:
        self._directory.mkdir(parents=True, exist_ok=True)
        target = self._path_for(definition.name)
        payload = json.dumps(self._to_data(definition), ensure_ascii=False, indent=2)
        handle, temporary_name = tempfile.mkstemp(
            prefix=f".{target.stem}.", suffix=".tmp", dir=self._directory
        )
        try:
            with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
                stream.write(payload)
                stream.write("\n")
            os.replace(temporary_name, target)
        except Exception:
            try:
                os.unlink(temporary_name)
            except OSError:
                pass
            raise
        return target

    # {
    #   責務: [load: 指定sequence JSONを読み、versioned definitionとして構築する]
    #   処理: [slug pathを開きJSON decode後、_from_dataでcontract validationする]
    #   引数: [self: store instance, name: sequence name]
    #   戻り値: [SequenceDefinition: 読み込んだdefinition]
    #   エラー: [OSError/JSONDecodeError/ValueError: fileまたはdefinition不正]
    #   副作用: [JSON fileをUTF-8で読み込む]
    # }
    def load(self, name: str) -> SequenceDefinition:
        with self._path_for(name).open("r", encoding="utf-8") as stream:
            data = json.load(stream)
        return self._from_data(data)

    # {
    #   責務: [_path_for: sequence nameをfilesystem-safe JSON filenameへ変換する]
    #   処理: [非word/dot/dash runをunderscoreへ置換し、edge punctuationを除く]
    #   引数: [self: store instance, name: sequence name]
    #   戻り値: [Path: store directory下のJSON path]
    #   エラー: [ValueError: slugが空になる]
    # }
    def _path_for(self, name: str) -> Path:
        slug = re.sub(r"[^\w.-]+", "_", name.strip(), flags=re.UNICODE).strip("._")
        if not slug:
            raise ValueError("sequence name does not produce a valid filename")
        return self._directory / f"{slug}.json"

    # {
    #   責務: [_to_data: SequenceDefinitionをversion付きJSON-compatible mappingへ変換する]
    #   処理: [enumをvalue化し、step ID/command/inputsを配列へ直列化する]
    #   引数: [definition: 保存するsequence contract]
    #   戻り値: [data: JSON-compatible dict]
    # }
    @staticmethod
    def _to_data(definition: SequenceDefinition) -> dict[str, Any]:
        return {
            "version": definition.version,
            "name": definition.name,
            "failure_policy": definition.failure_policy.value,
            "steps": [
                {"id": step.id, "command": step.command, "inputs": step.inputs}
                for step in definition.steps
            ],
        }

    # {
    #   責務: [_from_data: decoded JSON valueを型検査しSequenceDefinitionへ変換する]
    #   処理: [object/steps/inputs shapeを検証しstepとversioned policyを構築する]
    #   引数: [data: json.loadの結果]
    #   戻り値: [SequenceDefinition: validated immutable sequence]
    #   エラー: [ValueError/TypeError: JSON shapeやenum/version値が不正]
    # }
    @staticmethod
    def _from_data(data: Any) -> SequenceDefinition:
        if not isinstance(data, dict):
            raise ValueError("sequence definition must be a JSON object")
        steps = data.get("steps")
        if not isinstance(steps, list):
            raise ValueError("sequence steps must be a JSON array")
        parsed_steps = []
        for item in steps:
            if not isinstance(item, dict):
                raise ValueError("each sequence step must be a JSON object")
            inputs = item.get("inputs", {})
            if not isinstance(inputs, dict):
                raise ValueError("step inputs must be a JSON object")
            parsed_steps.append(
                SequenceStep(
                    id=str(item.get("id", "")),
                    command=str(item.get("command", "")),
                    inputs=inputs,
                )
            )
        return SequenceDefinition(
            name=str(data.get("name", "")),
            steps=tuple(parsed_steps),
            failure_policy=FailurePolicy(data.get("failure_policy", "stop")),
            version=int(data.get("version", 1)),
        )
