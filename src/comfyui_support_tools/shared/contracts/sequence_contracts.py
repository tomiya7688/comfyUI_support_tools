"""Serializable contracts for GUI-independent, ordered command sequences."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping


class FailurePolicy(str, Enum):
    STOP = "stop"
    CONTINUE = "continue"


@dataclass(frozen=True)
class SequenceStep:
    """One named command invocation and its JSON-compatible input bindings."""

    id: str
    command: str
    inputs: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SequenceDefinition:
    """An ordered sequence with explicit behavior after a command fails."""

    name: str
    steps: tuple[SequenceStep, ...]
    failure_policy: FailurePolicy = FailurePolicy.STOP
    version: int = 1

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


@dataclass(frozen=True)
class SequenceStepResult:
    step_id: str
    command: str
    state: str
    inputs: Mapping[str, Any] = field(default_factory=dict)
    outputs: Mapping[str, Any] = field(default_factory=dict)
    error: str = ""


@dataclass(frozen=True)
class SequenceRunResult:
    sequence_name: str
    state: str
    steps: tuple[SequenceStepResult, ...]
    context: Mapping[str, Any] = field(default_factory=dict)
