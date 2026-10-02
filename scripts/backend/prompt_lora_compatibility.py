"""Resolve prompt LoRA references and check them against the selected base model."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Callable

from src.comfyui_support_tools.shared.model_compatibility import (
    CompatibilityResult,
    CompatibilityStatus,
    check_lora_compatibility,
)
from src.comfyui_support_tools.shared.model_identity import ModelKind

from .local_model_evidence import classify_local_model_choice

from .model_choice_classification import classify_base_model_choice


_LORA_REFERENCE = re.compile(r"<lora:([^:<>]+)(?::[^<>]*)?>", re.IGNORECASE)
_MODEL_SUFFIXES = {".safetensors", ".ckpt", ".pt", ".pth", ".bin"}


@dataclass(frozen=True)
class PromptLoraFinding:
    reference: str
    resolved_name: str | None
    result: CompatibilityResult


def extract_lora_references(prompt: str) -> list[str]:
    """Return unique LoRA names in prompt order, ignoring case-only repeats."""
    references = []
    seen = set()
    for match in _LORA_REFERENCE.finditer(prompt):
        name = match.group(1).strip()
        key = name.casefold()
        if name and key not in seen:
            references.append(name)
            seen.add(key)
    return references


def _normalized_name(value: str) -> str:
    name = value.replace("\\", "/").strip().strip("/").casefold()
    path = PurePosixPath(name)
    if path.suffix in _MODEL_SUFFIXES:
        name = str(path.with_suffix(""))
    return name


def _resolve_lora(reference: str, candidates: list[str]) -> tuple[str | None, str]:
    requested = _normalized_name(reference)
    exact = [name for name in candidates if _normalized_name(name) == requested]
    if len(exact) == 1:
        return exact[0], "Matched a catalog entry by its normalized full name."
    if len(exact) > 1:
        filenames = [name for name in exact if PurePosixPath(name).suffix.casefold() in _MODEL_SUFFIXES]
        aliases = [name for name in exact if PurePosixPath(name).suffix.casefold() not in _MODEL_SUFFIXES]
        if len(filenames) == len(aliases) == 1:
            return aliases[0], "Matched an extensionless API alias and its local catalog filename."
        return None, "Multiple LoRA catalog entries have the same normalized full name."

    requested_base = PurePosixPath(requested).name
    basename_matches = [
        name for name in candidates
        if PurePosixPath(_normalized_name(name)).name == requested_base
    ]
    if len(basename_matches) == 1:
        return basename_matches[0], "Matched the unique catalog entry by basename."
    if len(basename_matches) > 1:
        return None, "Multiple LoRA catalog entries share this basename; the reference is ambiguous."
    return None, "No matching LoRA was found in the current backend catalog."


def assess_prompt_loras(
    prompt: str,
    base_model_name: str | None,
    choices: dict[str, list[str]],
    *,
    base_model_reason: str | None = None,
) -> list[PromptLoraFinding]:
    """Compare every prompt LoRA with the selected base using catalog evidence."""
    base_model = (
        classify_base_model_choice(base_model_name, choices)
        if base_model_name
        else None
    )
    candidates = list(choices.get("loras", []))
    findings = []
    for reference in extract_lora_references(prompt):
        resolved_name, resolution_reason = _resolve_lora(reference, candidates)
        if resolved_name is None:
            findings.append(PromptLoraFinding(
                reference=reference,
                resolved_name=None,
                result=CompatibilityResult(
                    CompatibilityStatus.UNKNOWN,
                    f"{resolution_reason} Family compatibility was not inferred from the prompt tag alone.",
                ),
            ))
            continue

        lora = classify_local_model_choice(resolved_name, ModelKind.LORA)
        if base_model is None:
            result = CompatibilityResult(
                CompatibilityStatus.UNKNOWN,
                base_model_reason or "The active base model could not be identified confidently.",
            )
        else:
            result = check_lora_compatibility(lora, base_model)
        findings.append(PromptLoraFinding(
            reference=reference,
            resolved_name=resolved_name,
            result=CompatibilityResult(result.status, f"{resolution_reason} {result.reason}"),
        ))
    return findings


def validate_prompt_loras(
    prompt: str,
    base_model_name: str | None,
    choices: dict[str, list[str]],
    log: Callable[[str], None],
    *,
    base_model_reason: str | None = None,
) -> list[PromptLoraFinding]:
    """Log compatibility evidence and reject only definite family mismatches."""
    findings = assess_prompt_loras(
        prompt, base_model_name, choices, base_model_reason=base_model_reason
    )
    incompatible = []
    for finding in findings:
        result = finding.result
        level = "警告" if result.status is CompatibilityStatus.UNKNOWN else "互換性"
        log(f"LoRA {level} [{result.status.value}]: {finding.reference} — {result.reason}")
        if result.status is CompatibilityStatus.INCOMPATIBLE:
            incompatible.append(finding)
    if incompatible:
        names = ", ".join(finding.reference for finding in incompatible)
        raise ValueError(f"選択中ベースモデルと非互換のLoRAがあるため生成を中止しました: {names}")
    return findings


def format_prompt_lora_findings(findings: list[PromptLoraFinding]) -> str:
    """Render LoRA findings for the Prompt Generate tab."""
    if not findings:
        return "LoRA指定はありません。"
    return "\n".join(
        f"{finding.result.status.value}: {finding.reference} — {finding.result.reason}"
        for finding in findings
    )
