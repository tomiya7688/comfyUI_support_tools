"""Run registered commands in order without importing GUI or backend modules."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from types import MappingProxyType
from typing import Any

from comfyui_support_tools.shared.contracts.sequence_contracts import (
    FailurePolicy,
    SequenceDefinition,
    SequenceRunResult,
    SequenceStepResult,
)


Command = Callable[[Mapping[str, Any], Mapping[str, Any]], Mapping[str, Any]]


class SequenceRunner:
    """Resolve explicit context references and execute commands sequentially."""

    def __init__(self, commands: Mapping[str, Command]) -> None:
        self._commands = dict(commands)

    def run(
        self,
        definition: SequenceDefinition,
        initial_context: Mapping[str, Any] | None = None,
    ) -> SequenceRunResult:
        context = dict(initial_context or {})
        results: list[SequenceStepResult] = []
        failed = False
        stopped = False

        for step in definition.steps:
            if stopped:
                results.append(SequenceStepResult(step.id, step.command, "skipped"))
                continue
            resolved_inputs: dict[str, Any] = {}
            try:
                resolved_inputs = self._resolve(step.inputs, context)
                command = self._commands[step.command]
                outputs = command(
                    MappingProxyType(resolved_inputs), MappingProxyType(dict(context))
                )
                if not isinstance(outputs, Mapping):
                    raise TypeError("command output must be a mapping")
                copied_outputs = dict(outputs)
                context[step.id] = copied_outputs
                results.append(
                    SequenceStepResult(
                        step.id, step.command, "done", resolved_inputs, copied_outputs
                    )
                )
            except Exception as error:  # Step failures become structured run results.
                failed = True
                results.append(
                    SequenceStepResult(
                        step.id,
                        step.command,
                        "error",
                        inputs=resolved_inputs,
                        error=f"{type(error).__name__}: {error}",
                    )
                )
                stopped = definition.failure_policy is FailurePolicy.STOP

        state = "error" if failed else "done"
        return SequenceRunResult(
            definition.name,
            state,
            tuple(results),
            MappingProxyType(context),
        )

    @classmethod
    def _resolve(cls, value: Any, context: Mapping[str, Any]) -> Any:
        if isinstance(value, dict):
            if set(value) == {"$ref"}:
                return cls._lookup(str(value["$ref"]), context)
            return {key: cls._resolve(item, context) for key, item in value.items()}
        if isinstance(value, list):
            return [cls._resolve(item, context) for item in value]
        return value

    @staticmethod
    def _lookup(reference: str, context: Mapping[str, Any]) -> Any:
        parts = reference.split(".")
        if len(parts) < 2 or parts[0] != "context":
            raise ValueError(f"invalid context reference: {reference}")
        value: Any = context
        for part in parts[1:]:
            if not isinstance(value, Mapping) or part not in value:
                raise KeyError(f"context reference not found: {reference}")
            value = value[part]
        return value
