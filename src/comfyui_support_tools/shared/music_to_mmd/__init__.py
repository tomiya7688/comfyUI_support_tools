"""Music-driven choreography planning and MMD motion backend contracts."""

from .application import MusicToMmdApplication, MusicToMmdSession, evaluate_dance_motion
from .audio_analysis import AutoAudioDecoder, FFmpegAudioDecoder, WavAudioDecoder, analyze_audio
from .contracts import (
    AudioAnalysis,
    AudioDecoderBackend,
    AudioSection,
    AudioSignal,
    ChoreographyPlan,
    ChoreographySection,
    DanceEvaluation,
    DanceGenerationBackend,
    DanceMotionRequest,
    MusicToMmdResult,
)
from .planning import (
    BACKEND_CAPABILITIES,
    DANCE_STYLES,
    DanceBackendDescriptor,
    DanceBackendRegistry,
    build_choreography_plan,
    replace_section_instruction,
)
from .procedural_backend import ProceduralDanceBackend

__all__ = [
    "BACKEND_CAPABILITIES",
    "DANCE_STYLES",
    "AudioAnalysis",
    "AutoAudioDecoder",
    "AudioDecoderBackend",
    "AudioSection",
    "AudioSignal",
    "ChoreographyPlan",
    "ChoreographySection",
    "DanceBackendDescriptor",
    "DanceBackendRegistry",
    "DanceEvaluation",
    "DanceGenerationBackend",
    "DanceMotionRequest",
    "FFmpegAudioDecoder",
    "MusicToMmdApplication",
    "MusicToMmdResult",
    "MusicToMmdSession",
    "ProceduralDanceBackend",
    "WavAudioDecoder",
    "analyze_audio",
    "build_choreography_plan",
    "evaluate_dance_motion",
    "replace_section_instruction",
]
