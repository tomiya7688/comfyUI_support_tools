"""Shared identifiers accepted by generation backend boundaries."""

from __future__ import annotations

from typing import Literal, TypeAlias

# {
#   責務: [GenerationBackendId: generation backend境界で利用できるbackend IDを制約する]
#   許可値: [a1111: Stable Diffusion WebUI 1111, comfyui: ComfyUI]
# }
GenerationBackendId: TypeAlias = Literal["a1111", "comfyui"]
