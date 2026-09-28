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


class SequenceStore:
    """Read and atomically write user-authored sequence definitions."""

    def __init__(self, directory: str | Path) -> None:
        self._directory = Path(directory)

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

    def load(self, name: str) -> SequenceDefinition:
        with self._path_for(name).open("r", encoding="utf-8") as stream:
            data = json.load(stream)
        return self._from_data(data)

    def _path_for(self, name: str) -> Path:
        slug = re.sub(r"[^\w.-]+", "_", name.strip(), flags=re.UNICODE).strip("._")
        if not slug:
            raise ValueError("sequence name does not produce a valid filename")
        return self._directory / f"{slug}.json"

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
