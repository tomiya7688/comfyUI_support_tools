from dataclasses import dataclass


# {
#   責務: [ResolvedPrompt: 生成側へ渡す展開済みpromptと解決情報を保持する]
#   フィールド: [positive_prompt: 展開済み正prompt, negative_prompt: 展開済み負prompt, resolved_wildcards: 解決したwildcard参照, resolved_loras: prompt内LoRA参照, warnings: 解決時の警告, metadata: 拡張metadata, provenance: 解決元の記録]
# }
@dataclass(frozen=True)
class ResolvedPrompt:
    positive_prompt: str
    negative_prompt: str
    resolved_wildcards: tuple[str, ...] = ()
    resolved_loras: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    metadata: tuple[tuple[str, str], ...] = ()
    provenance: tuple[str, ...] = ()
