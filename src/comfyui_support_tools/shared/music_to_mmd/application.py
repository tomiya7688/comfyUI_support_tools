"""Music-to-MMD orchestration using independent audio and dance adapters."""

from __future__ import annotations

import json
import math
import os
import tempfile
from pathlib import Path

from comfyui_support_tools.shared.video_to_mmd.contracts import (
    RecoveredFrame,
    RecoveredMotion,
    RetargetProfile,
    VmdBoneKey,
)
from comfyui_support_tools.shared.video_to_mmd.processing import process_recovered_motion
from comfyui_support_tools.shared.video_to_mmd.vmd import write_motion_vmd

from .audio_analysis import AutoAudioDecoder, analyze_audio
from .contracts import (
    AudioAnalysis,
    AudioDecoderBackend,
    ChoreographyPlan,
    DanceEvaluation,
    DanceGenerationBackend,
    DanceMotionRequest,
    MusicToMmdResult,
)
from .planning import DanceBackendRegistry, build_choreography_plan, replace_section_instruction
from .procedural_backend import ProceduralDanceBackend


# {
# 責務: [MusicToMmdApplication: create section-editable music dance sessions]
# フィールド: [audio decoder registry, dance backend registry]
# 処理: [separate audio analysis, choreography planning, motion generation, and VMD retarget]
# }
class MusicToMmdApplication:
    # {
    # 責務: [__init__: configure WAV decoder and dance backend catalog]
    # 処理: [register a deterministic WAV decoder and retain adapter registries]
    # 引数: [audio_decoder: optional custom decoder backend]
    # 戻り値: [None: initialized orchestrator]
    # }
    def __init__(self, audio_decoder: AudioDecoderBackend | None = None):
        self.audio_decoder = audio_decoder or AutoAudioDecoder()
        self.backends = DanceBackendRegistry()
        self.backends.register(
            "procedural_baseline",
            ProceduralDanceBackend(),
            frozenset({"beat_alignment", "genre_control", "editable_sections", "long_form"}),
        )

    # {
    # 責務: [register_backend: add a dance model adapter with routing capabilities]
    # 処理: [delegate unique id and capability validation to registry]
    # 引数: [name: backend id, backend: model adapter, capabilities: supported conditions]
    # 戻り値: [None: backend added]
    # }
    def register_backend(
        self, name: str, backend: DanceGenerationBackend, capabilities: frozenset[str]
    ) -> None:
        self.backends.register(name, backend, capabilities)

    # {
    # 責務: [create_session: decode song, analyze it, and prepare editable choreography]
    # 処理: [validate BPM/style/profile and select a backend matching requested features]
    # 引数: [audio_path: source song, profile: target MMD retarget, style, instruction, bpm, backend]
    # 戻り値: [MusicToMmdSession: generated-motion workspace]
    # }
    def create_session(
        self,
        audio_path: Path,
        profile: RetargetProfile,
        *,
        style: str = "pop",
        instruction: str = "",
        bpm: float | None = None,
        fps: int = 30,
        backend_name: str | None = None,
        required_capabilities: frozenset[str] = frozenset({"editable_sections"}),
        reference_motion: RecoveredMotion | None = None,
    ) -> MusicToMmdSession:
        source = Path(audio_path)
        if not source.is_file():
            raise FileNotFoundError(source)
        signal = self.audio_decoder.decode(source)
        analysis = analyze_audio(signal, source, bpm)
        plan = build_choreography_plan(analysis, style, instruction, fps)
        descriptor = self.backends.select(required_capabilities, backend_name)
        return MusicToMmdSession(
            analysis, plan, profile, descriptor.name, descriptor.backend, reference_motion
        )


# {
# 責務: [MusicToMmdSession: retain generated section motions for local reroll and export]
# フィールド: [analysis, plan, retarget profile, backend, section motion cache]
# 処理: [generate full choreography, reroll one section, evaluate, and export VMD]
# }
class MusicToMmdSession:
    # {
    # 責務: [__init__: construct one editable music-to-dance session]
    # 処理: [retain song plan, model adapter, reference motion, and target skeleton profile]
    # 引数: [analysis, plan, profile, backend id/adapter, optional reference motion]
    # 戻り値: [None: initialized session]
    # }
    def __init__(
        self,
        analysis: AudioAnalysis,
        plan: ChoreographyPlan,
        profile: RetargetProfile,
        backend_name: str,
        backend: DanceGenerationBackend,
        reference_motion: RecoveredMotion | None = None,
    ):
        self.analysis = analysis
        self.plan = plan
        self.profile = profile
        self.backend_name = backend_name
        self.backend = backend
        self.reference_motion = reference_motion
        self._sections: dict[str, RecoveredMotion] = {}
        self._seed = None

    # {
    # 責務: [generated_sections: list section IDs with cached dance motions]
    # 処理: [expose a stable snapshot for editor UI]
    # 引数: [None: no inputs]
    # 戻り値: [tuple[str, ...]: generated section identifiers]
    # }
    @property
    def generated_sections(self) -> tuple[str, ...]:
        return tuple(
            section.section_id
            for section in self.plan.sections
            if section.section_id in self._sections
        )

    # {
    # 責務: [generate: generate every planned dance section while reusing chorus templates]
    # 処理: [call backend per section and cache each normalized motion clip]
    # 引数: [seed: optional shared random seed]
    # 戻り値: [tuple[str, ...]: generated section IDs]
    # }
    def generate(self, seed: int | None = None) -> tuple[str, ...]:
        self._seed = seed
        motif_templates: dict[str, RecoveredMotion] = {}
        for section in self.plan.sections:
            template = motif_templates.get(section.motif_id)
            request = DanceMotionRequest(
                self.analysis, self.plan, section, self.reference_motion, template, seed
            )
            motion = self.backend.generate_section(request)
            normalized = _place_section_motion(motion, section, self.plan.fps)
            self._sections[section.section_id] = normalized
            motif_templates.setdefault(section.motif_id, normalized)
        return self.generated_sections

    # {
    # 責務: [regenerate_section: reroll one plan section and preserve every other clip]
    # 処理: [update one instruction, pass its prior motif as context, and replace only its cache entry]
    # 引数: [section_id: requested segment, instruction: optional revised direction, seed]
    # 戻り値: [str: regenerated section identifier]
    # }
    def regenerate_section(
        self,
        section_id: str,
        *,
        instruction: str | None = None,
        seed: int | None = None,
    ) -> str:
        if instruction is not None:
            self.plan = replace_section_instruction(self.plan, section_id, instruction)
        section = next((item for item in self.plan.sections if item.section_id == section_id), None)
        if section is None:
            raise KeyError(section_id)
        template = self._sections.get(section.section_id)
        if template is None:
            template = next(
                (
                    motion
                    for other_id, motion in self._sections.items()
                    if next(
                        item for item in self.plan.sections if item.section_id == other_id
                    ).motif_id
                    == section.motif_id
                ),
                None,
            )
        request = DanceMotionRequest(
            self.analysis,
            self.plan,
            section,
            self.reference_motion,
            template,
            self._seed if seed is None else seed,
        )
        self._sections[section_id] = _place_section_motion(
            self.backend.generate_section(request), section, self.plan.fps
        )
        return section_id

    # {
    # 責務: [generate_best_of_n: create and rank bounded full-song dance candidates]
    # 処理: [generate independent seeds, evaluate all quality dimensions, and retain the winner]
    # 引数: [candidate_count: number of alternatives, seed: optional base seed]
    # 戻り値: [tuple[(score, keys), ...]: candidates sorted by combined proxy score]
    # }
    def generate_best_of_n(
        self,
        candidate_count: int,
        seed: int | None = None,
    ) -> tuple[tuple[float, tuple[VmdBoneKey, ...]], ...]:
        if not 1 <= candidate_count <= 8:
            raise ValueError("candidate_count must be within 1..8")
        candidates = []
        winner = None
        for index in range(candidate_count):
            self._sections = {}
            self.generate(None if seed is None else seed + index)
            _motion, keys, evaluation = self.evaluate()
            score = sum(value for _name, value in evaluation.scores) / max(
                len(evaluation.scores), 1
            )
            candidates.append((score, keys))
            if winner is None or score > winner[0]:
                winner = (score, dict(self._sections), self._seed)
        ranked = tuple(sorted(candidates, key=lambda item: item[0], reverse=True))
        self._sections = winner[1]
        self._seed = winner[2]
        return ranked

    # {
    # 責務: [evaluate: merge cached sections and report music/motion quality proxies]
    # 処理: [retarget to keys once and score beat alignment, smoothness, floor, diversity, motifs]
    # 引数: [None: reads generated section cache]
    # 戻り値: [tuple[RecoveredMotion, keys, DanceEvaluation]: auditable motion result]
    # }
    def evaluate(self) -> tuple[RecoveredMotion, tuple[VmdBoneKey, ...], DanceEvaluation]:
        motion = _merge_sections(self._sections, self.plan)
        keys, _confidence, _findings = process_recovered_motion(motion, self.profile)
        evaluation = evaluate_dance_motion(self.analysis, self.plan, motion, keys, self.profile)
        return motion, keys, evaluation

    # {
    # 責務: [export: write VMD, choreography plan, and separate metric report]
    # 処理: [refuse output clobber and atomically reserve all artifacts]
    # 引数: [output_dir: output folder, stem: simple name]
    # 戻り値: [MusicToMmdResult: exported keys/plan/metrics and paths]
    # }
    def export(self, output_dir: Path, stem: str = "music-dance") -> MusicToMmdResult:
        motion, keys, evaluation = self.evaluate()
        destination = Path(output_dir)
        destination.mkdir(parents=True, exist_ok=True)
        if not stem or Path(stem).name != stem or stem in {".", ".."}:
            raise ValueError("export stem must be a plain file name")
        vmd_path = destination / f"{stem}.vmd"
        plan_path = destination / f"{stem}.choreography.json"
        report_path = destination / f"{stem}.evaluation.json"
        plan_data = _plan_json(
            self.analysis, self.plan, self.backend_name, self.profile.model_name, motion
        )
        evaluation_data = {
            "schema_version": 1,
            "analysis_method": self.analysis.analysis_method,
            "backend": self.backend_name,
            "scores": dict(evaluation.scores),
            "counts": dict(evaluation.counts),
            "notes": evaluation.notes,
        }
        _write_artifacts(
            (vmd_path, plan_path, report_path),
            (
                write_motion_vmd(keys, self.profile.model_name),
                (
                    json.dumps(plan_data, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
                ).encode("utf-8"),
                (
                    json.dumps(evaluation_data, ensure_ascii=False, indent=2, allow_nan=False)
                    + "\n"
                ).encode("utf-8"),
            ),
        )
        return MusicToMmdResult(
            self.analysis, self.plan, evaluation, keys, self.plan.fps, vmd_path, report_path
        )


# {
# 責務: [evaluate_dance_motion: score musical alignment and motion quality separately]
# 処理: [measure beat activity, frame smoothness, floor contacts, diversity, and motif consistency]
# 引数: [analysis: music timing, plan: section plan, motion: recovered body motion, keys: retargeted VMD keys]
# 戻り値: [DanceEvaluation: normalized music and movement quality proxies]
# }
def evaluate_dance_motion(
    analysis: AudioAnalysis,
    plan: ChoreographyPlan,
    motion: RecoveredMotion,
    keys: tuple[VmdBoneKey, ...],
    profile: RetargetProfile | None = None,
) -> DanceEvaluation:
    velocities = _frame_activity(keys)
    maximum_activity = max(velocities.values(), default=0.0)
    beat_values = [velocities.get(round(time * plan.fps), 0.0) for time in analysis.beats]
    beat_alignment = min(1.0, sum(beat_values) / max(len(beat_values) * maximum_activity, 1e-8))
    changes = [
        abs(right - left)
        for left, right in zip(velocities.values(), tuple(velocities.values())[1:], strict=False)
    ]
    smoothness = 1.0 / (1.0 + sum(changes) / max(len(changes), 1) * 8)
    foot_keys = [
        key for key in keys if any(word in key.bone.casefold() for word in ("foot", "toe", "足"))
    ]
    floor_violations = sum(key.translation[1] < -0.01 for key in foot_keys)
    floor_score = 1.0 if not foot_keys else max(0.0, 1.0 - floor_violations / len(foot_keys))
    foot_slide = _foot_slide_score(motion, keys, profile, plan.fps)
    section_energy = {
        section.section_id: _section_activity(velocities, section.start_frame, section.end_frame)
        for section in plan.sections
    }
    diversity_values = list(section_energy.values())
    diversity = min(
        1.0, len({round(value, 2) for value in diversity_values}) / max(len(diversity_values), 1)
    )
    repeated_scores = []
    for first, second in plan.repeated_motifs:
        left, right = section_energy[first], section_energy[second]
        repeated_scores.append(1.0 - min(1.0, abs(left - right) / max(left, right, 0.1)))
    motif_consistency = sum(repeated_scores) / len(repeated_scores) if repeated_scores else 1.0
    scores = (
        ("beat_alignment_proxy", beat_alignment),
        ("motion_smoothness", smoothness),
        ("foot_floor_clearance", floor_score),
        ("foot_contact_sliding", foot_slide),
        ("movement_diversity", diversity),
        ("repeated_motif_consistency", motif_consistency),
    )
    notes = (
        "Rhythmic score measures motion activity near estimated beats; it is not a learned music-motion similarity model.",
        "Foot checks use mapped bone names and y translation only; no PMX geometry, collision, or physics simulation is available.",
        "Audio sections are energy-based coarse labels; chorus/verse semantics require review or a specialized analyzer.",
    )
    return DanceEvaluation(
        scores,
        (
            ("frames", len(motion.frames)),
            ("keys", len(keys)),
            ("foot_floor_violations", floor_violations),
        ),
        notes,
    )


# {
# 責務: [_place_section_motion: place a backend clip into the planned song frame interval]
# 処理: [validate fps and clip bounds, offset local frames, and trim section overflow]
# 引数: [motion: backend clip, section: timeline interval, fps: expected frame rate]
# 戻り値: [RecoveredMotion: global-timeline clip]
# }
def _place_section_motion(motion: RecoveredMotion, section, fps: int) -> RecoveredMotion:
    if motion.fps != fps or not motion.frames:
        raise ValueError("dance backend must return non-empty motion at the planned FPS")
    duration = section.end_frame - section.start_frame
    first = min(frame.frame for frame in motion.frames)
    last = max(frame.frame for frame in motion.frames)
    local = first >= 0 and last < duration
    placed = []
    for frame in motion.frames:
        global_frame = frame.frame + section.start_frame if local else frame.frame
        if section.start_frame <= global_frame < section.end_frame:
            placed.append(
                RecoveredFrame(
                    global_frame,
                    frame.person_id,
                    frame.camera_translation,
                    frame.ground_height,
                    frame.bones,
                )
            )
    if not placed:
        raise ValueError(f"dance backend returned no frames inside {section.section_id}")
    return RecoveredMotion(fps, tuple(placed), motion.camera_compensated)


# {
# 責務: [_merge_sections: merge cached timeline intervals into one normalized motion sequence]
# 処理: [require every planned section and reject duplicate/overlapping frame timestamps]
# 引数: [sections: cached clip map, plan: expected section intervals, profile: target mapping]
# 戻り値: [RecoveredMotion: full-song source motion]
# }
def _merge_sections(sections, plan: ChoreographyPlan) -> RecoveredMotion:
    missing = [item.section_id for item in plan.sections if item.section_id not in sections]
    if missing:
        raise ValueError(f"dance motion sections have not been generated: {', '.join(missing)}")
    frames = tuple(
        sorted(
            (frame for item in plan.sections for frame in sections[item.section_id].frames),
            key=lambda frame: frame.frame,
        )
    )
    if len({frame.frame for frame in frames}) != len(frames):
        raise ValueError("generated sections contain overlapping frame timestamps")
    compensated = all(sections[item.section_id].camera_compensated for item in plan.sections)
    return RecoveredMotion(plan.fps, frames, compensated)


# {
# 責務: [_frame_activity: compute framewise centroid displacement activity]
# 処理: [compare average mapped translation vectors across sorted VMD frames]
# 引数: [keys: retargeted VMD bone keys]
# 戻り値: [dict[int, float]: frame to movement activity]
# }
def _frame_activity(keys: tuple[VmdBoneKey, ...]) -> dict[int, float]:
    frames: dict[int, dict[str, VmdBoneKey]] = {}
    for key in keys:
        frames.setdefault(key.frame, {})[key.bone.casefold()] = key
    ordered = sorted(frames.items())
    activity = {}
    for (previous_frame, previous), (frame, current) in zip(ordered, ordered[1:], strict=False):
        frame_delta = frame - previous_frame
        if frame_delta < 1:
            continue
        shared = previous.keys() & current.keys()
        if not shared:
            continue
        deltas = []
        for bone in shared:
            first, second = previous[bone], current[bone]
            translation = math.dist(first.translation, second.translation)
            dot = abs(
                sum(
                    left * right
                    for left, right in zip(first.rotation, second.rotation, strict=True)
                )
            )
            rotation = 2 * math.acos(min(1.0, max(0.0, dot)))
            deltas.append((translation + rotation * 0.1) / frame_delta)
        activity_per_frame = sum(deltas) / len(deltas)
        for current_frame in range(previous_frame + 1, frame + 1):
            activity[current_frame] = activity_per_frame
    return activity


# {
# 責務: [_section_activity: average motion activity in a planned frame range]
# 処理: [average framewise movement samples inside half-open section interval]
# 引数: [activity: frame activity mapping, start/end: section boundaries]
# 戻り値: [float: mean movement activity]
# }
def _section_activity(activity: dict[int, float], start: int, end: int) -> float:
    values = [value for frame, value in activity.items() if start <= frame < end]
    return sum(values) / max(len(values), 1)


# {
# 責務: [_foot_slide_score: estimate horizontal drift during detected foot contacts]
# 処理: [compare retargeted foot keys across consecutive source contact frames]
# 引数: [motion: contact-labeled input, keys: repaired VMD keys, profile: source/target map, fps]
# 戻り値: [float: normalized contact-stability score]
# }
def _foot_slide_score(
    motion: RecoveredMotion,
    keys: tuple[VmdBoneKey, ...],
    profile: RetargetProfile | None,
    fps: int,
) -> float:
    if profile is None:
        return 1.0
    contacts = {
        (frame.frame, pose.name.casefold())
        for frame in motion.frames
        for pose in frame.bones
        if pose.foot_contact
    }
    scores = []
    for rule in profile.rules:
        if not any(
            label in f"{rule.source_name} {rule.target_name}".casefold()
            for label in ("foot", "toe", "足")
        ):
            continue
        track = sorted(
            (key for key in keys if key.bone == rule.target_name), key=lambda key: key.frame
        )
        for first, second in zip(track, track[1:], strict=False):
            contact_samples = [
                frame
                for frame, name in contacts
                if name == rule.source_name.casefold() and first.frame <= frame <= second.frame
            ]
            if len(contact_samples) < 2 or second.frame <= first.frame:
                continue
            horizontal = math.hypot(
                second.translation[0] - first.translation[0],
                second.translation[2] - first.translation[2],
            )
            speed = horizontal / (second.frame - first.frame) * fps
            scores.append(max(0.0, 1.0 - speed / 0.2))
    return sum(scores) / len(scores) if scores else 1.0


# {
# 責務: [_plan_json: serialize provenance, audio structure, and choreography plan]
# 処理: [create portable JSON-compatible dictionaries]
# 引数: [analysis/plan: source timing, backend: generator id, model: target model, motion: source result]
# 戻り値: [dict: auditable plan sidecar]
# }
def _plan_json(analysis, plan, backend, model, motion):
    return {
        "schema_version": 1,
        "source_audio": str(analysis.source),
        "duration_seconds": analysis.duration,
        "bpm": analysis.bpm,
        "beats_seconds": analysis.beats,
        "onsets_seconds": analysis.onsets,
        "analysis_method": analysis.analysis_method,
        "backend": backend,
        "target_model": model,
        "fps": plan.fps,
        "style": plan.style,
        "instruction": plan.instruction,
        "camera_compensated": motion.camera_compensated,
        "repeated_motifs": plan.repeated_motifs,
        "sections": [
            {
                "id": section.section_id,
                "kind": section.kind,
                "start_frame": section.start_frame,
                "end_frame": section.end_frame,
                "intensity": section.intensity,
                "facing": section.facing,
                "stage_position": section.stage_position,
                "motif_id": section.motif_id,
                "instruction": section.instruction,
            }
            for section in plan.sections
        ],
    }


# {
# 責務: [_write_artifacts: reserve and write a grouped output without clobbering user files]
# 処理: [create exclusive placeholders, write sibling temps, replace own placeholders, rollback failures]
# 引数: [paths: target files, contents: encoded VMD/report bytes]
# 戻り値: [None: artifacts written]
# }
def _write_artifacts(paths: tuple[Path, ...], contents: tuple[bytes, ...]) -> None:
    reserved, temporaries = [], []
    try:
        for path in paths:
            descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            os.close(descriptor)
            reserved.append(path)
        for path, content in zip(paths, contents, strict=True):
            with tempfile.NamedTemporaryFile(
                dir=path.parent, prefix=f".{path.name}.", delete=False
            ) as stream:
                stream.write(content)
                temporaries.append(Path(stream.name))
        for temporary, path in zip(temporaries, paths, strict=True):
            os.replace(temporary, path)
        temporaries.clear()
    except BaseException:
        for path in reserved:
            path.unlink(missing_ok=True)
        raise
    finally:
        for temporary in temporaries:
            temporary.unlink(missing_ok=True)
