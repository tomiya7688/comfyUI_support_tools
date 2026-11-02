from __future__ import annotations

import json
import struct
import tempfile
import unittest
from pathlib import Path

from comfyui_support_tools.shared.mmd_doctor import (
    ModelDoctorService,
    PmxFormatError,
    RepairEvaluation,
    parse_pmx,
)


# {
# 責務: [tiny_pmx: PMX doctorの関連処理を実行する]
# 処理: [入力を検証し、安全な結果を返す]
# 引数: [weight: 呼び出しに必要な値]
# 戻り値: [bytes: 処理結果]
# }
def tiny_pmx(
    weight: float = 1.2,
    face_indices: tuple[int, ...] = (),
    *,
    version: float = 2.0,
    include_soft_body: bool = False,
) -> bytes:
    output = bytearray(b"PMX " + struct.pack("<fB8B", version, 8, 1, 0, 4, 4, 4, 4, 4, 4))

    # {
    # 責務: [text: PMX doctorの関連処理を実行する]
    # 処理: [入力を検証し、安全な結果を返す]
    # 引数: [value: 呼び出しに必要な値]
    # 戻り値: [None: 処理結果]
    # }
    def text(value: str) -> None:
        encoded = value.encode("utf-8")
        output.extend(struct.pack("<i", len(encoded)))
        output.extend(encoded)

    for value in ("fixture", "", "", ""):
        text(value)
    output.extend(struct.pack("<i", 1))
    output.extend(struct.pack("<8fBii2f", 0, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, weight, 1.0))
    output.extend(struct.pack("<i", len(face_indices)))
    if face_indices:
        output.extend(struct.pack("<" + "I" * len(face_indices), *face_indices))
    for _ in range(2):
        output.extend(struct.pack("<i", 0))
    output.extend(struct.pack("<i", 1))
    for value in ("root", "root"):
        text(value)
    output.extend(struct.pack("<3fiiH3f", 0, 0, 0, -1, 0, 0, 0, 0, 0))
    for _ in range(4):
        output.extend(struct.pack("<i", 0))
    if version >= 2.1:
        output.extend(struct.pack("<i", int(include_soft_body)))
        if include_soft_body:
            for value in ("cloth", ""):
                text(value)
            output.extend(struct.pack("<BiBHBiiffi", 0, -1, 0, 0, 0, 0, 0, 1, 0.01, 0))
            output.extend(struct.pack("<18f10i", *([0.0] * 18), *([0] * 10)))
    return bytes(output)


# {
# 責務: [MmdDoctorServiceTests: PMX parse/weight repair/evaluation/export behaviorを検証する]
# フィールド: [temporary PMX fixture]
# 処理: [strict parse, diagnostics, Best-of-N, diff report, source preservationを確認する]
# }
class MmdDoctorServiceTests(unittest.TestCase):
    # {
    # 責務: [test_parser_reports_weight_risk_and_rejects_malformed_data: parser diagnosticとboundaryを検証する]
    # 処理: [1: malformed signatureを拒否する, 2: weight normalization candidateを確認する]
    # 引数: [self: test case]
    # 戻り値: []
    # }
    def test_parser_reports_weight_risk_and_rejects_malformed_data(self) -> None:
        with self.assertRaisesRegex(PmxFormatError, "signature"):
            from comfyui_support_tools.shared.mmd_doctor import parse_pmx_bytes

            parse_pmx_bytes(b"not a PMX")
        with self.assertRaisesRegex(PmxFormatError, "unsupported PMX version"):
            parse_pmx_bytes(tiny_pmx(version=2.05))
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "source.pmx"
            source.write_bytes(tiny_pmx())
            model = parse_pmx(source)
            service = ModelDoctorService()
            model, diagnostics = service.analyze(source)
            self.assertTrue(any(item.code == "weight.out_of_range" for item in diagnostics))
            candidates = service.candidates(model, diagnostics)
            weight_candidate = next(
                item for item in candidates if item.name == "Weight normalization and root fallback"
            )
            self.assertTrue(weight_candidate.patches)
            self.assertEqual(source.read_bytes(), tiny_pmx())

    # {
    # 責務: [test_motion_suite_selects_repair_and_writes_separate_diff_report: non-destructive repairを検証する]
    # 処理: [1: motion evaluatorが正常weightを高scoreにする, 2: PMX/diff reportとsource hashを確認する]
    # 引数: [self: test case]
    # 戻り値: []
    # }
    def test_motion_suite_selects_repair_and_writes_separate_diff_report(self) -> None:
        # {
        # 責務: [Evaluator: PMX weight validityからfixture scoreを出す]
        # フィールド: [none]
        # 処理: [normalized PMXへhigh scoreを返す]
        # }
        class Evaluator:
            # {
            # 責務: [evaluate: PMX candidate scoreを計算する]
            # 処理: [parserでweightを読み、candidate qualityを比較する]
            # 引数: [self: evaluator, pmx_path: candidate, suite: motion suite]
            # 戻り値: [RepairEvaluation]
            # }
            def evaluate(self, pmx_path, suite):
                weight = parse_pmx(pmx_path).vertices[0].weights[0]
                self.assert_suite = bool(suite.tests)
                return RepairEvaluation(0.9 if weight <= 1.0 else 0.4, 0.0, 0.0, 0.0, 0.0)

        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "source.pmx"
            output = Path(temporary) / "repaired.pmx"
            original = tiny_pmx()
            source.write_bytes(original)
            report = ModelDoctorService(Evaluator()).run(source, output)
            self.assertEqual(source.read_bytes(), original)
            self.assertEqual(report.output_path, str(output))
            self.assertEqual(report.selected_index, 1)
            self.assertTrue(Path(report.diff_report_path).is_file())
            self.assertEqual(parse_pmx(output).vertices[0].weights[0], 1.0)
            diff = json.loads(Path(report.diff_report_path).read_text(encoding="utf-8"))
            self.assertEqual(diff["candidate"], "Weight normalization and root fallback")
            self.assertTrue(diff["before"])
            self.assertFalse(diff["after"])

    # {
    # 責務: [test_candidate_patch_requires_exact_source_bytes: stale patch適用を拒否する]
    # 処理: [1: PMX modelから修正candidateを得る, 2: changed sourceへpatchを拒否する]
    # 引数: [self: test case]
    # 戻り値: []
    # }
    def test_candidate_patch_requires_exact_source_bytes(self) -> None:
        from comfyui_support_tools.shared.mmd_doctor import PatchConflictError, apply_binary_patches

        model_bytes = tiny_pmx()
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "fixture.pmx"
            source.write_bytes(model_bytes)
            service = ModelDoctorService()
            model, diagnostics = service.analyze(source)
            candidate = next(
                item for item in service.candidates(model, diagnostics) if item.patches
            )
            modified = bytearray(model_bytes)
            modified[candidate.patches[0].offset] ^= 1
            with self.assertRaises(PatchConflictError):
                apply_binary_patches(bytes(modified), candidate.patches)

    # {
    # 責務: [test_invalid_face_reference_is_reported_without_crashing_weight_analysis: 不正faceをfail-safe診断する]
    # 処理: [1: 存在しないvertexを参照するPMXを構築する, 2: 診断が例外なく返ることを確認する]
    # 引数: [self: test case]
    # 戻り値: []
    # }
    def test_invalid_face_reference_is_reported_without_crashing_weight_analysis(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "invalid-face.pmx"
            source.write_bytes(tiny_pmx(face_indices=(4, 5, 6)))
            _model, diagnostics = ModelDoctorService().analyze(source)
            self.assertTrue(any(item.code == "mesh.face_vertex_reference" for item in diagnostics))

    # {
    # 責務: [test_pmx_21_float_version_and_soft_body_records_are_parsed: PMX 2.1 parsingを検証する]
    # 処理: [1: float32 versionとsoft body recordを構築, 2: section countとreferential diagnosticを確認]
    # 引数: [self: test case]
    # 戻り値: []
    # }
    def test_pmx_21_float_version_and_soft_body_records_are_parsed(self) -> None:
        from comfyui_support_tools.shared.mmd_doctor import parse_pmx_bytes

        model = parse_pmx_bytes(tiny_pmx(version=2.1, include_soft_body=True))
        self.assertEqual(model.version, 2.1)
        self.assertEqual(model.soft_body_count, 1)
        self.assertTrue(
            any(item.code == "physics.soft_body_material" for item in model.diagnostics)
        )


if __name__ == "__main__":
    unittest.main()
