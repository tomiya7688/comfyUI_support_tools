"""Create a catalog adapter for one selected image-generation backend."""

from __future__ import annotations

from .a1111_backend_catalog import A1111BackendCatalog
from .comfyui_backend_catalog import ComfyUIBackendCatalog
from .generation_backend_catalog import GenerationBackendCatalog


def create_generation_backend_catalog(backend: str) -> GenerationBackendCatalog:
    if backend == "a1111":
        return A1111BackendCatalog()
    if backend == "comfyui":
        return ComfyUIBackendCatalog()
    raise ValueError(f"Unsupported generation backend: {backend}")
