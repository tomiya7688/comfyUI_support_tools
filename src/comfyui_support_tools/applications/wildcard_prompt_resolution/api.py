from src.comfyui_support_tools.applications.wildcard_prompt_resolution.process.messenger.wildcard_data_messenger import (
    load_sequential_prompt_lines,
    parse_wildcard_line,
    resolve_text,
    resolve_wildcard_reference,
)
from src.comfyui_support_tools.applications.wildcard_prompt_resolution.process.processing.wildcard_prompt_resolver import (
    lora_references,
    validate_prompt_request,
)
from src.comfyui_support_tools.shared.contracts.prompt_resolution_request import (
    PromptResolutionRequest,
)
from src.comfyui_support_tools.shared.contracts.prompt_validation_result import (
    PromptValidationResult,
)
from src.comfyui_support_tools.shared.contracts.resolved_prompt import ResolvedPrompt


# {
#   責務: [resolve_prompt: 입력request를 backend 독립 ResolvedPrompt로 변환한다]
#   処理: [1: requestをvalidationする, 2: sourceまたは直接本文をwildcard展開する, 3: LoRA参照とprovenanceを収集する]
#   引数: [request: prompt解決request, wildcard_cache: 指定時は複数prompt間で共有するcache, 未指定時はrequest内cache]
#   戻り値: [ResolvedPrompt: backendへ渡す展開済みpromptと解決情報]
#   エラー: [ValueError: requestが不正またはwildcard重み記法が不正な場合]
# }
def resolve_prompt(
    request: PromptResolutionRequest,
    wildcard_cache: dict[str, str] | None = None,
) -> ResolvedPrompt:
    """Resolve request sources and prompt syntax into a backend-neutral result."""
    request_cache = wildcard_cache if wildcard_cache is not None else {}
    validation = validate_prompt_request(request)
    if not validation.is_valid:
        raise ValueError("; ".join(validation.errors))
    traces: list[str] = []
    warnings = list(validation.warnings)
    positive = (
        resolve_wildcard_reference(
            request.positive_source,
            request.wildcard_root,
            cache=request_cache,
            trace=traces,
            warnings=warnings,
        )
        if request.positive_source
        else resolve_text(
            request.positive_prompt, request.wildcard_root, request_cache, traces, warnings
        )
    )
    negative = (
        resolve_wildcard_reference(
            request.negative_source,
            request.wildcard_root,
            cache=request_cache,
            trace=traces,
            warnings=warnings,
        )
        if request.negative_source
        else resolve_text(
            request.negative_prompt, request.wildcard_root, request_cache, traces, warnings
        )
    )
    return ResolvedPrompt(
        positive_prompt=positive,
        negative_prompt=negative,
        resolved_wildcards=tuple(dict.fromkeys(traces)),
        resolved_loras=lora_references(positive, negative),
        warnings=tuple(dict.fromkeys(warnings)),
        provenance=tuple(dict.fromkeys(traces)),
    )


# {
#   責務: [validate_prompt: prompt resolution API入力を検証する]
#   処理: [process層のrequest validatorを呼び出す]
#   引数: [request: prompt解決request]
#   戻り値: [PromptValidationResult: 検証結果]
# }
def validate_prompt(request: PromptResolutionRequest) -> PromptValidationResult:
    """Validate a prompt request without reading wildcard sources."""
    return validate_prompt_request(request)


__all__ = [
    "load_sequential_prompt_lines",
    "parse_wildcard_line",
    "resolve_prompt",
    "validate_prompt",
]
