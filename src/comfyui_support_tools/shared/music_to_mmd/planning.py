"""Editable section-level choreography plans and backend capability routing."""

from __future__ import annotations

from dataclasses import dataclass, replace

from .contracts import AudioAnalysis, ChoreographyPlan, ChoreographySection, DanceGenerationBackend

DANCE_STYLES = (
    "idol",
    "pop",
    "cute",
    "energetic",
    "cool",
    "hip_hop_like",
    "contemporary_like",
    "simple",
    "mmd_stage",
    "custom",
)
BACKEND_CAPABILITIES = frozenset(
    {
        "beat_alignment",
        "genre_control",
        "editable_sections",
        "long_form",
        "text_control",
        "reference_motion",
    }
)


# {
# 責務: [DanceBackendDescriptor: label a replaceable model with routing capabilities]
# フィールド: [name, backend adapter, capability tags]
# 処理: [let music requests select a backend by required behavior]
# }
@dataclass(frozen=True)
class DanceBackendDescriptor:
    name: str
    backend: DanceGenerationBackend
    capabilities: frozenset[str]


# {
# 責務: [DanceBackendRegistry: register and select dance generation adapters]
# フィールド: [registered descriptors]
# 処理: [route beat/genre/editability/long-form/reference requests]
# }
class DanceBackendRegistry:
    # {
    # 責務: [__init__: initialize empty backend catalog]
    # 処理: [prepare named backend registration]
    # 引数: [None: no inputs]
    # 戻り値: [None: initialized registry]
    # }
    def __init__(self):
        self._backends: dict[str, DanceBackendDescriptor] = {}

    # {
    # 責務: [register: register one unique dance backend descriptor]
    # 処理: [validate capability tags and reject duplicate backend identifiers]
    # 引数: [name: backend id, backend: generator adapter, capabilities: supported routing tags]
    # 戻り値: [None: catalog updated]
    # }
    def register(
        self, name: str, backend: DanceGenerationBackend, capabilities: frozenset[str]
    ) -> None:
        if not name.strip() or name in self._backends:
            raise ValueError("dance backend name must be non-empty and unique")
        unknown = capabilities - BACKEND_CAPABILITIES
        if unknown:
            raise ValueError(f"unsupported dance backend capabilities: {sorted(unknown)}")
        self._backends[name] = DanceBackendDescriptor(name, backend, capabilities)

    # {
    # 責務: [select: choose first registered backend meeting required capability tags]
    # 処理: [filter capable adapters and raise a useful error when none are installed]
    # 引数: [required: routing capabilities, name: optional explicit backend id]
    # 戻り値: [DanceBackendDescriptor: selected adapter and metadata]
    # }
    def select(self, required: frozenset[str], name: str | None = None) -> DanceBackendDescriptor:
        candidates = (
            (self._backends[name],)
            if name in self._backends
            else tuple(self._backends.values())
            if name is None
            else ()
        )
        selected = next((item for item in candidates if required <= item.capabilities), None)
        if selected is None:
            raise LookupError("no installed dance backend satisfies the requested capabilities")
        return selected


# {
# 責務: [build_choreography_plan: turn audio sections into editable timed dance units]
# 処理: [align frame boundaries to beats, normalize intensity, and reuse chorus motifs]
# 引数: [analysis: song structure, style: dance style preset, instruction: optional direction, fps]
# 戻り値: [ChoreographyPlan: section-level movement plan]
# }
def build_choreography_plan(
    analysis: AudioAnalysis,
    style: str = "pop",
    instruction: str = "",
    fps: int = 30,
) -> ChoreographyPlan:
    if style not in DANCE_STYLES:
        raise ValueError(f"unsupported dance style: {style}")
    if fps not in {24, 25, 30, 50, 60}:
        raise ValueError("motion fps must be one of 24, 25, 30, 50, or 60")
    if not analysis.sections:
        raise ValueError("audio analysis has no sections to plan")
    maximum = max((section.energy for section in analysis.sections), default=0.0)
    sections = []
    first_chorus = None
    repeated = []
    for index, source in enumerate(analysis.sections):
        start = max(0, round(source.start_seconds * fps))
        end = max(start + 1, round(source.end_seconds * fps))
        intensity = min(1.0, max(0.0, source.energy / maximum if maximum > 1e-8 else 0.4))
        if source.kind == "chorus":
            if first_chorus is None:
                first_chorus = source.section_id
                motif_id = "chorus-main"
            else:
                motif_id = "chorus-main"
                repeated.append((first_chorus, source.section_id))
        else:
            motif_id = f"motif-{index:03d}"
        sections.append(
            ChoreographySection(
                source.section_id,
                source.kind,
                start,
                end,
                intensity,
                "front",
                (0.0, 0.0),
                motif_id,
                instruction.strip(),
            )
        )
    return ChoreographyPlan(
        fps, analysis.bpm, style, tuple(sections), tuple(repeated), instruction.strip()
    )


# {
# 責務: [replace_section_instruction: immutably revise one section's choreography prompt]
# 処理: [replace selected section instruction and preserve the rest of plan]
# 引数: [plan: current plan, section_id: target segment, instruction: replacement direction]
# 戻り値: [ChoreographyPlan: updated editable plan]
# }
def replace_section_instruction(
    plan: ChoreographyPlan, section_id: str, instruction: str
) -> ChoreographyPlan:
    if not instruction.strip():
        raise ValueError("section instruction must be non-empty")
    if not any(section.section_id == section_id for section in plan.sections):
        raise KeyError(section_id)
    updated = tuple(
        replace(section, instruction=instruction.strip())
        if section.section_id == section_id
        else section
        for section in plan.sections
    )
    return replace(plan, sections=updated)
