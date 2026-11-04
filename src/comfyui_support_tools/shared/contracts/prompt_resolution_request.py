from dataclasses import dataclass
from pathlib import Path


# {
#   責務: [PromptResolutionRequest: wildcard解決Applicationへの入力を保持する]
#   フィールド: [positive_prompt: 正prompt本文, negative_prompt: 負prompt本文, positive_source: 正promptのwildcard参照, negative_source: 負promptのwildcard参照, wildcard_root: wildcard providerのroot]
# }
@dataclass(frozen=True)
class PromptResolutionRequest:
    positive_prompt: str = ""
    negative_prompt: str = ""
    positive_source: str | None = None
    negative_source: str | None = None
    wildcard_root: Path = Path(".")
