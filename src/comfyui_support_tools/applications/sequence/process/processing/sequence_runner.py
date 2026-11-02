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


# {
# 責務: [SequenceRunner: registered commandを順に実行しcontext参照と失敗policyを処理する]
# フィールド: [_commands: command IDからcallableへのsnapshot mapping]
# }
class SequenceRunner:
    """Resolve explicit context references and execute commands sequentially."""

    # {
    #   責務: [__init__: command registry mappingのcopyをrunnerへ保持する]
    #   処理: [caller mappingからdict copyを作り、実行時registryを固定する]
    #   引数: [self: runner instance, commands: command ID-to-callable mapping]
    #   戻り値: [なし]
    # }
    def __init__(self, commands: Mapping[str, Command]) -> None:
        self._commands = dict(commands)

    # {
    #   責務: [run: ordered sequenceを実行し各stepの結果とcontext snapshotを返す]
    #   処理: [step input reference解決、immutable input/context渡し、output mapping検証を行いfailure policyに応じて継続/skipする]
    #   引数: [self: runner instance, definition: sequence definition, initial_context: optional初期値]
    #   戻り値: [SequenceRunResult: done/error state、step result、final context]
    #   副作用: [登録command callableを順番に呼び出す]
    # }
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

    # {
    #   責務: [_resolve: nested mapping/list内のexact $ref objectをcontext valueに置き換える]
    #   処理: [mappingがkey set {$ref}だけならlookupし、それ以外はnested valuesを再帰処理する]
    #   引数: [cls: runner class, value: input tree, context: prior step context]
    #   戻り値: [Any: resolved input tree]
    #   エラー: [ValueError/KeyError: reference syntax不正または値がない]
    # }
    @classmethod
    def _resolve(cls, value: Any, context: Mapping[str, Any]) -> Any:
        if isinstance(value, dict):
            if set(value) == {"$ref"}:
                return cls._lookup(str(value["$ref"]), context)
            return {key: cls._resolve(item, context) for key, item in value.items()}
        if isinstance(value, list):
            return [cls._resolve(item, context) for item in value]
        return value

    # {
    #   責務: [_lookup: context.<step>.<field> dotted referenceをmappingから解決する]
    #   処理: [root tokenがcontextかつ2 segment以上を要求し各mapping keyを順に辿る]
    #   引数: [reference: dotted reference string, context: current context mapping]
    #   戻り値: [Any: 指定されたcontext value]
    #   エラー: [ValueError: reference prefix/shape不正, KeyError: path segmentが存在しない]
    # }
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
