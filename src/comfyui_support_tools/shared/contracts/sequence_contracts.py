"""Serializable contracts for GUI-independent, ordered command sequences."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping


# {
# 責務: [FailurePolicy: sequence step失敗時にrunnerが取る継続方針]
# フィールド: [STOP: 失敗後のstepを止める, CONTINUE: 残りのstepも試す]
# }
class FailurePolicy(str, Enum):
    STOP = "stop"
    CONTINUE = "continue"


# {
# 責務: [SequenceStep: 一つのnamed commandとJSON-compatible input bindingを表す]
# フィールド: [id: sequence内一意のstep ID, command: registered command ID, inputs: command input mapping]
# }
@dataclass(frozen=True)
class SequenceStep:
    """One named command invocation and its JSON-compatible input bindings."""

    id: str
    command: str
    inputs: Mapping[str, Any] = field(default_factory=dict)


# {
# 責務: [SequenceDefinition: version 1のordered stepsとfailure policyを保持する]
# フィールド: [name, steps, failure_policy, version]
# }
@dataclass(frozen=True)
class SequenceDefinition:
    """An ordered sequence with explicit behavior after a command fails."""

    name: str
    steps: tuple[SequenceStep, ...]
    failure_policy: FailurePolicy = FailurePolicy.STOP
    version: int = 1

    # {
    #   責務: [SequenceDefinition.__post_init__: sequence名/version/policy/step identityを検証する]
    #   処理: [blank name、非対応version、invalid policy、空または重複step ID、空commandを拒否する]
    #   引数: [self: 作成中のimmutable sequence definition]
    #   戻り値: [なし。policy stringは対応enumに正規化する]
    #   エラー: [ValueError: definition fieldが未対応または不正]
    #   副作用: [failure_policyがstringの場合、frozen objectにenum値を設定する]
    # }
    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("sequence name must not be empty")
        if self.version != 1:
            raise ValueError(f"unsupported sequence version: {self.version}")
        if not isinstance(self.failure_policy, FailurePolicy):
            object.__setattr__(self, "failure_policy", FailurePolicy(self.failure_policy))
        ids = [step.id for step in self.steps]
        if any(not value.strip() for value in ids):
            raise ValueError("step id must not be empty")
        if len(ids) != len(set(ids)):
            raise ValueError("step ids must be unique")
        if any(not step.command.strip() for step in self.steps):
            raise ValueError("step command must not be empty")

    # {
    #   責務: [SequenceDefinition.__post_init__: sequence fieldと全stepの構造を検証する]
    #   処理: [name/version/policyを検査し、step IDの空/重複とcommandの空値を拒否する]
    #   引数: [self: 作成中のimmutable sequence definition]
    #   戻り値: [なし]
    #   エラー: [ValueError: sequence definitionが契約を満たさない]
    #   副作用: [必要なfailure_policy stringをenumへ正規化する]
    # }
    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("sequence name must not be empty")
        if self.version != 1:
            raise ValueError(f"unsupported sequence version: {self.version}")
        if not isinstance(self.failure_policy, FailurePolicy):
            object.__setattr__(self, "failure_policy", FailurePolicy(self.failure_policy))
        ids = [step.id for step in self.steps]
        if any(not value.strip() for value in ids):
            raise ValueError("step id must not be empty")
        if len(ids) != len(set(ids)):
            raise ValueError("step ids must be unique")
        if any(not step.command.strip() for step in self.steps):
            raise ValueError("step command must not be empty")


# {
# 責務: [SequenceStepResult: 一つの実行stepの状態、binding、output、errorを保持する]
# フィールド: [step_id, command, state, inputs, outputs, error]
# }
@dataclass(frozen=True)
class SequenceStepResult:
    step_id: str
    command: str
    state: str
    inputs: Mapping[str, Any] = field(default_factory=dict)
    outputs: Mapping[str, Any] = field(default_factory=dict)
    error: str = ""


# {
# 責務: [SequenceRunResult: sequence全体のterminal state、step result、最終contextを保持する]
# フィールド: [sequence_name, state, steps, context]
# }
@dataclass(frozen=True)
class SequenceRunResult:
    sequence_name: str
    state: str
    steps: tuple[SequenceStepResult, ...]
    context: Mapping[str, Any] = field(default_factory=dict)
