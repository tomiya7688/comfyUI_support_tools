"""Public contracts and application for local capture-session assistance."""

from .application import (
    CaptureAssistantApplication,
    CaptureAssistantResult,
    CaptureSetBackend,
    ExposureFusion,
)
from .contracts import CaptureFrame, CaptureQuality, CaptureSet
from .decode import RawFrameDecoder, RawpyFrameDecoder
from .importer import CaptureSetImporter
from .quality import score_capture_quality, score_capture_set
from .registration import (
    BurstFusionResult,
    BurstSuperResolutionBackend,
    FrameRegistrationEvidence,
    register_and_fuse_burst,
)

__all__ = [
    "CaptureAssistantApplication",
    "CaptureAssistantResult",
    "CaptureFrame",
    "CaptureQuality",
    "CaptureSet",
    "CaptureSetBackend",
    "CaptureSetImporter",
    "BurstFusionResult",
    "BurstSuperResolutionBackend",
    "ExposureFusion",
    "FrameRegistrationEvidence",
    "RawFrameDecoder",
    "RawpyFrameDecoder",
    "register_and_fuse_burst",
    "score_capture_quality",
    "score_capture_set",
]
