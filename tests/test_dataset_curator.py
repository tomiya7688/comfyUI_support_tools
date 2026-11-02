"""Safety and reproducibility coverage for LoRA dataset curation."""

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

import tomllib
from PIL import Image, ImageDraw

from comfyui_support_tools.applications.lora_dataset_curator import (
    CaptionPolicy,
    CharacterRegistryEvidence,
    CuratorConfig,
    CuratorTask,
    DatasetCuratorApplication,
    DatasetSampleInput,
    SampleAction,
    SampleOverride,
)
from comfyui_support_tools.applications.lora_dataset_curator.data.processing.export import (
    export_dataset,
)
from comfyui_support_tools.applications.lora_dataset_curator.process.processing.split import (
    group_duplicates,
    sample_weights,
)
from comfyui_support_tools.shared.contracts.dataset_curator import (
    CaptionPolicyProbe,
    DatasetAnalysis,
    ImageFeatures,
)


# {
# 責務: [_image: generate a deterministic textured fixture image]
# 処理: [draw a unique pattern to exercise real decode/hash/quality analysis]
# 引数: [path: output fixture path, color: fill color, offset: pattern position]
# 戻り値: [Path: created PNG file]
# }
def _image(path: Path, color: tuple[int, int, int], offset: int) -> Path:
    image = Image.new("RGB", (320, 320), color)
    draw = ImageDraw.Draw(image)
    for index in range(8):
        x = (index * 37 + offset) % 280
        draw.rectangle(
            (x, index * 37, min(x + 30, 319), index * 37 + 20),
            fill=(255 - color[0], index * 19, 255 - color[2]),
        )
    image.save(path)
    return path


# {
# 責務: [_sample: create one explicit dataset label record]
# 処理: [attach repeated pose/background labels for coverage and split assertions]
# 引数: [path: source fixture image, index: deterministic label variant]
# 戻り値: [DatasetSampleInput: caption and attribute evidence]
# }
def _sample(path: Path, index: int) -> DatasetSampleInput:
    pose = "standing" if index % 2 == 0 else "sitting"
    view = "front view" if index % 3 else "side view"
    return DatasetSampleInput(
        path,
        raw_tags=("A woman", pose, view, "indoor", "blue hair", "coat"),
        attributes=(("background", ("indoor",)),),
    )


# {
# 責務: [test_character_caption_ownership_respects_registry_and_fixed_clothing: verify ownership policy]
# 処理: [curate a sample with registry identity/outfit/rejected evidence and compare task caption variants]
# 引数: [tmp_path: isolated dataset directory]
# 戻り値: [None: assertions pass]
# }
def _test_character_caption_ownership_respects_registry_and_fixed_clothing(tmp_path: Path) -> None:
    image_path = _image(tmp_path / "character.png", (50, 90, 120), 4)
    sample = DatasetSampleInput(
        image_path,
        raw_tags=("A woman", "blue hair", "coat", "red scarf", "smile", "standing"),
        registry=CharacterRegistryEvidence(
            identity=("luna",),
            outfit=("winter_coat",),
            variable_attributes=("red_scarf",),
            accepted_traits=("blue_hair",),
            rejected_traits=("red_scarf",),
        ),
    )
    app = DatasetCuratorApplication()
    result = app.curate(
        tmp_path, CuratorConfig(CuratorTask.CHARACTER, fixed_clothing=False), samples=(sample,)
    )
    caption = result.samples[0].captions
    assert "luna" in caption.absorb_tags
    assert "blue_hair" in caption.absorb_tags
    assert "winter_coat" in caption.variable_tags
    assert "red_scarf" not in caption.normalized_tags
    assert "standing" in caption.variable_tags
    fixed = app.curate(
        tmp_path,
        CuratorConfig(CuratorTask.CHARACTER, fixed_clothing=True),
        samples=(DatasetSampleInput(image_path, raw_tags=("coat", "standing")),),
    )
    assert "coat" in fixed.samples[0].captions.absorb_tags


# {
# 責務: [test_duplicate_groups_never_cross_validation_boundary: prevent train/validation leakage]
# 処理: [duplicate one source byte-for-byte, curate task-specific samples, and assert split group isolation]
# 引数: [tmp_path: isolated dataset directory]
# 戻り値: [None: duplicate group remains in one split]
# }
def _test_duplicate_groups_never_cross_validation_boundary(tmp_path: Path) -> None:
    paths = [
        _image(tmp_path / f"sample-{index}.png", (20 + index * 20, 80, 130), index * 11)
        for index in range(5)
    ]
    duplicate = tmp_path / "sample-copy.png"
    shutil.copy2(paths[0], duplicate)
    samples = tuple(_sample(path, index) for index, path in enumerate((*paths, duplicate)))
    result = DatasetCuratorApplication().curate(
        tmp_path, CuratorConfig(CuratorTask.CHARACTER, validation_ratio=0.25), samples=samples
    )
    by_group: dict[str, set[str]] = {}
    for sample in result.samples:
        by_group.setdefault(sample.duplicate_group, set()).add(sample.split)
    assert any(len(paths_in_group) == 2 for _, paths_in_group in result.duplicate_groups)
    assert all(len(splits) == 1 for splits in by_group.values())
    assert any(sample.split == "validation" for sample in result.samples)
    overridden = DatasetCuratorApplication().curate(
        tmp_path,
        CuratorConfig(CuratorTask.CHARACTER),
        samples=samples,
        overrides=(SampleOverride(duplicate, split="validation"),),
    )
    assert all(
        sample.split == "validation"
        for sample in overridden.samples
        if sample.duplicate_group
        == next(item.duplicate_group for item in overridden.samples if item.image_path == paths[0])
    )
    try:
        DatasetCuratorApplication().curate(
            tmp_path,
            CuratorConfig(CuratorTask.CHARACTER),
            samples=samples,
            overrides=(
                SampleOverride(paths[0], split="train"),
                SampleOverride(duplicate, split="validation"),
            ),
        )
    except ValueError as error:
        assert "conflicting split overrides" in str(error)
    else:
        raise AssertionError("conflicting duplicate-group overrides must fail")


# {
# 責務: [test_user_exclusion_and_dataset_fingerprint_are_reproducible: protect explicit decisions]
# 処理: [exclude one image, curate twice with the same seed, and compare stable fingerprint/split output]
# 引数: [tmp_path: isolated dataset directory]
# 戻り値: [None: explicit exclusion and deterministic plan are retained]
# }
def _test_user_exclusion_and_dataset_fingerprint_are_reproducible(tmp_path: Path) -> None:
    paths = [
        _image(tmp_path / f"item-{index}.png", (25 + index * 25, 100, 160), index * 5)
        for index in range(4)
    ]
    samples = tuple(_sample(path, index) for index, path in enumerate(paths))
    config = CuratorConfig(CuratorTask.OBJECT, seed=41)
    override = (SampleOverride(paths[0], action=SampleAction.EXCLUDE),)
    app = DatasetCuratorApplication()
    first = app.curate(tmp_path, config, samples=samples, overrides=override)
    second = app.curate(tmp_path, config, samples=samples, overrides=override)
    assert first.fingerprint == second.fingerprint
    excluded = next(sample for sample in first.samples if sample.image_path == paths[0])
    assert excluded.action == SampleAction.EXCLUDE
    assert excluded.sample_weight == 0
    assert excluded.split == "excluded"

    mismatch = DatasetSampleInput(paths[1], raw_tags=("blue hair", "standing"), concept_match=False)
    kept = app.curate(
        tmp_path,
        config,
        samples=(mismatch,),
        overrides=(SampleOverride(paths[1], action=SampleAction.KEEP),),
    )
    reviewed = kept.samples[0]
    assert reviewed.outlier_class.value == "concept_mismatch"
    assert reviewed.action == SampleAction.KEEP
    assert reviewed.sample_weight > 0.25


# {
# 責務: [test_trainer_export_is_atomic_and_contains_captions_and_templates: validate export artifacts]
# 処理: [export to three trainer formats, parse JSON/TOML, and verify original files remain byte-identical]
# 引数: [tmp_path: isolated source and destination directories]
# 戻り値: [None: export structure and source integrity assertions pass]
# }
def _test_trainer_export_is_atomic_and_contains_captions_and_templates(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    paths = [
        _image(source / f"img-{index}.png", (30 + index * 35, 95, 155), index * 7)
        for index in range(4)
    ]
    regularization = _image(source / "regularization.png", (35, 75, 110), 2)
    duplicate = source / "img-copy.png"
    shutil.copy2(paths[0], duplicate)
    samples = tuple(_sample(path, index) for index, path in enumerate((*paths, duplicate)))
    analysis = DatasetCuratorApplication().curate(
        source,
        CuratorConfig(CuratorTask.STYLE, caption_policy=CaptionPolicy.HYBRID),
        samples=samples,
        regularization_images=(regularization,),
    )
    before = tuple(path.read_bytes() for path in paths)
    for trainer in ("sd-scripts", "simpletuner", "ai-toolkit"):
        output = export_dataset(analysis, tmp_path / trainer, trainer)
        manifest = json.loads((output / "dataset_manifest.json").read_text(encoding="utf-8"))
        config = json.loads((output / "trainer_dataset_config.json").read_text(encoding="utf-8"))
        assert manifest["fingerprint"] == analysis.fingerprint
        assert len(manifest["regularization"]) == 1
        assert (output / manifest["regularization"][0]["image"]).is_file()
        assert config["caption_file_extension"] == ".txt"
        assert len(list((output / "train").glob("*.txt"))) + len(
            list((output / "validation").glob("*.txt"))
        ) == len(samples)
        if trainer == "sd-scripts":
            assert (
                tomllib.loads((output / "sd_scripts_dataset.toml").read_text(encoding="utf-8"))[
                    "datasets"
                ][0]["batch_size"]
                == 1
            )
        else:
            assert (output / f"{trainer.replace('-', '_')}_dataset.json").is_file()
    assert tuple(path.read_bytes() for path in paths) == before


# {
# 責務: [_test_task_caption_policies_are_distinct: guard Character/Style/Object ownership differences]
# 処理: [curate the same subject and context tags for three targets and compare concept/variable ownership]
# 引数: [tmp_path: isolated dataset directory]
# 戻り値: [None: each task retains its own caption ownership]
# }
def _test_task_caption_policies_are_distinct(tmp_path: Path) -> None:
    image_path = _image(tmp_path / "task.png", (75, 90, 120), 3)
    sample = DatasetSampleInput(
        image_path, raw_tags=("chair", "anime", "standing", "indoor", "blue hair", "coat")
    )
    app = DatasetCuratorApplication()
    results = {
        task: app.curate(tmp_path, CuratorConfig(task), samples=(sample,)).samples[0].captions
        for task in (CuratorTask.CHARACTER, CuratorTask.STYLE, CuratorTask.OBJECT)
    }
    assert "coat" in results[CuratorTask.CHARACTER].variable_tags
    assert "chair" in results[CuratorTask.STYLE].variable_tags
    assert "chair" in results[CuratorTask.OBJECT].absorb_tags
    assert "blue_hair" in results[CuratorTask.CHARACTER].absorb_tags


# {
# 責務: [_test_inventory_reads_sidecars_and_rejects_links: validate safe discovery]
# 処理: [inventory a nested sidecar-backed image and ensure explicit symlink paths fail]
# 引数: [tmp_path: isolated source and outside directories]
# 戻り値: [None: automatic inventory and path safety are verified]
# }
def _test_inventory_reads_sidecars_and_rejects_links(tmp_path: Path) -> None:
    source = tmp_path / "dataset"
    source.mkdir()
    image_path = _image(source / "sample.png", (55, 80, 120), 6)
    image_path.with_suffix(".txt").write_text("Blue hair, standing\nindoor", encoding="utf-8")
    analysis = DatasetCuratorApplication().curate(source, CuratorConfig(CuratorTask.CHARACTER))
    assert len(analysis.samples) == 1
    assert analysis.samples[0].captions.source == "sidecar"
    assert "blue_hair" in analysis.samples[0].captions.normalized_tags

    outside = _image(tmp_path / "outside.png", (75, 100, 140), 9)
    link = source / "linked.png"
    link.symlink_to(outside)
    try:
        DatasetCuratorApplication().curate(
            source,
            CuratorConfig(CuratorTask.CHARACTER),
            samples=(DatasetSampleInput(link),),
        )
    except ValueError as error:
        assert "symbolic links" in str(error)
    else:
        raise AssertionError("symbolic-link dataset input must be rejected")


# {
# 責務: [_test_near_duplicate_index_and_weight_balance: verify near grouping and duplicate downweighting]
# 処理: [group synthetic perceptual hashes within/outside a Hamming radius and compare duplicate-group weights]
# 引数: [tmp_path: isolated path namespace]
# 戻り値: [None: near threshold and balance rules are respected]
# }
def _test_near_duplicate_index_and_weight_balance(tmp_path: Path) -> None:
    first = tmp_path / "first.png"
    second = tmp_path / "second.png"
    distant = tmp_path / "distant.png"
    features = {
        first: ImageFeatures(320, 320, "a" * 64, "0000000000000000", 0.8, 0.0, 1.0),
        second: ImageFeatures(320, 320, "b" * 64, "0000000000000001", 0.8, 0.0, 1.0),
        distant: ImageFeatures(320, 320, "c" * 64, "ffffffffffffffff", 0.8, 0.0, 1.0),
    }
    groups = group_duplicates(features, hamming_threshold=1)
    assert groups[first][0] == groups[second][0]
    assert groups[first][1] == "near"
    assert groups[first][0] != groups[distant][0]
    weighted = sample_weights(
        {
            first: ("dupe", "near", 2),
            second: ("dupe", "near", 2),
            distant: ("solo", "none", 1),
        },
        {path: (("subject", ("person",)),) for path in features},
        maximum=3.0,
        low_weight=set(),
        overrides={},
    )
    assert weighted[first] == weighted[second] == 0.5
    assert weighted[distant] == 1.0


# {
# 責務: [_test_export_rejects_changed_source: ensure stale plans cannot publish modified files]
# 処理: [curate an image, mutate its bytes, then verify export fails and removes its staging tree]
# 引数: [tmp_path: isolated source and destination directory]
# 戻り値: [None: source integrity and cleanup are asserted]
# }
def _test_export_rejects_changed_source(tmp_path: Path) -> None:
    source = _image(tmp_path / "mutable.png", (40, 100, 150), 2)
    analysis = DatasetCuratorApplication().curate(
        tmp_path,
        CuratorConfig(CuratorTask.OBJECT),
        samples=(DatasetSampleInput(source, raw_tags=("chair", "indoor")),),
    )
    _image(source, (60, 100, 150), 2)
    destination = tmp_path / "export"
    try:
        export_dataset(analysis, destination, "sd-scripts")
    except ValueError as error:
        assert "fingerprint changed" in str(error)
    else:
        raise AssertionError("export must reject input bytes changed after curation")
    assert not destination.exists()
    assert not tuple(tmp_path.glob(".export.stage-*"))


# {
# 責務: [_FakeProbe: provide deterministic #55 caption comparison scores]
# フィールド: [no mutable state]
# 処理: [verify candidate shape and return normalized synthetic quality scores]
# }
class _FakeProbe(CaptionPolicyProbe):
    # {
    # 責務: [compare: score caption candidates for the probe integration test]
    # 処理: [assert candidate captions are task variants and return a bounded score]
    # 引数: [analysis: curated data, candidates: named-image caption candidates]
    # 戻り値: [tuple[tuple[str, float], ...]: one normalized validation score]
    # }
    def compare(
        self, analysis: DatasetAnalysis, candidates: tuple[tuple[str, tuple[str, ...]], ...]
    ) -> tuple[tuple[str, float], ...]:
        assert analysis.samples
        assert candidates and candidates[0][0] == "full_tags"
        assert len(candidates[0][1]) == len(analysis.samples)
        return (("hybrid", 0.8), ("short", 0.6))


# {
# 責務: [test_caption_policy_probe_is_ordered_and_manual_auto_override_is_supported: check probe and manual controls]
# 処理: [call probe bridge and apply a user-owned caption tag override]
# 引数: [tmp_path: isolated dataset directory]
# 戻り値: [None: probe ranks and explicit caption ownership are preserved]
# }
def _test_caption_policy_probe_is_ordered_and_manual_auto_override_is_supported(
    tmp_path: Path,
) -> None:
    paths = [
        _image(tmp_path / f"probe-{index}.png", (20 + index * 45, 60, 130), index * 9)
        for index in range(3)
    ]
    samples = tuple(_sample(path, index) for index, path in enumerate(paths))
    app = DatasetCuratorApplication()
    analysis = app.curate(tmp_path, CuratorConfig(CuratorTask.STYLE), samples=samples)
    assert app.compare_caption_policies(analysis, _FakeProbe()) == (("hybrid", 0.8), ("short", 0.6))
    edited = app.curate(
        tmp_path,
        CuratorConfig(CuratorTask.CHARACTER),
        samples=samples,
        overrides=(SampleOverride(paths[0], absorb_tags=("coat",)),),
    )
    assert (
        "coat"
        in next(
            sample for sample in edited.samples if sample.image_path == paths[0]
        ).captions.absorb_tags
    )


# {
# 責務: [DatasetCuratorTests: run dataset curation checks using the repository unittest runner]
# フィールド: [temporary source directories]
# 処理: [wrap deterministic curation integration scenarios without external test dependencies]
# }
class DatasetCuratorTests(unittest.TestCase):
    # {
    # 責務: [setUp: create an isolated per-test dataset directory]
    # 処理: [register temporary directory cleanup]
    # 引数: [self: current unittest case]
    # 戻り値: [None: tmp_path assigned]
    # }
    def setUp(self) -> None:
        self.tmp_path = Path(tempfile.mkdtemp(prefix="dataset-curator-test-"))
        self.addCleanup(shutil.rmtree, self.tmp_path, ignore_errors=True)

    # {
    # 責務: [test_character_caption_ownership: run registry-aware caption checks]
    # 処理: [delegate to task-specific assertion scenario]
    # 引数: [self: current unittest case]
    # 戻り値: [None: assertions pass]
    # }
    def test_character_caption_ownership(self) -> None:
        _test_character_caption_ownership_respects_registry_and_fixed_clothing(self.tmp_path)

    # {
    # 責務: [test_duplicate_group_split: run duplicate leakage checks]
    # 処理: [delegate to duplicate grouping scenario]
    # 引数: [self: current unittest case]
    # 戻り値: [None: assertions pass]
    # }
    def test_duplicate_group_split(self) -> None:
        _test_duplicate_groups_never_cross_validation_boundary(self.tmp_path)

    # {
    # 責務: [test_manual_exclusion_and_fingerprint: run manual override and repeatability checks]
    # 処理: [delegate to fingerprint scenario]
    # 引数: [self: current unittest case]
    # 戻り値: [None: assertions pass]
    # }
    def test_manual_exclusion_and_fingerprint(self) -> None:
        _test_user_exclusion_and_dataset_fingerprint_are_reproducible(self.tmp_path)

    # {
    # 責務: [test_trainer_export: run dataset export integrity checks]
    # 処理: [delegate to multi-trainer export scenario]
    # 引数: [self: current unittest case]
    # 戻り値: [None: assertions pass]
    # }
    def test_trainer_export(self) -> None:
        _test_trainer_export_is_atomic_and_contains_captions_and_templates(self.tmp_path)

    # {
    # 責務: [test_task_caption_policies: run task ownership distinction checks]
    # 処理: [delegate to Character/Style/Object ownership scenario]
    # 引数: [self: current unittest case]
    # 戻り値: [None: assertions pass]
    # }
    def test_task_caption_policies(self) -> None:
        _test_task_caption_policies_are_distinct(self.tmp_path)

    # {
    # 責務: [test_safe_inventory: run sidecar discovery and symlink safety checks]
    # 処理: [delegate to automatic inventory scenario]
    # 引数: [self: current unittest case]
    # 戻り値: [None: assertions pass]
    # }
    def test_safe_inventory(self) -> None:
        _test_inventory_reads_sidecars_and_rejects_links(self.tmp_path)

    # {
    # 責務: [test_near_duplicate_weight: run near-hash and duplicate weighting checks]
    # 処理: [delegate to similarity index scenario]
    # 引数: [self: current unittest case]
    # 戻り値: [None: assertions pass]
    # }
    def test_near_duplicate_weight(self) -> None:
        _test_near_duplicate_index_and_weight_balance(self.tmp_path)

    # {
    # 責務: [test_export_source_integrity: run stale-image export protection checks]
    # 処理: [delegate to source-hash revalidation scenario]
    # 引数: [self: current unittest case]
    # 戻り値: [None: assertions pass]
    # }
    def test_export_source_integrity(self) -> None:
        _test_export_rejects_changed_source(self.tmp_path)

    # {
    # 責務: [test_caption_probe_and_manual_ownership: run #55 and editable Auto-policy checks]
    # 処理: [delegate to caption probe scenario]
    # 引数: [self: current unittest case]
    # 戻り値: [None: assertions pass]
    # }
    def test_caption_probe_and_manual_ownership(self) -> None:
        _test_caption_policy_probe_is_ordered_and_manual_auto_override_is_supported(self.tmp_path)
