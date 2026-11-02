from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import mock

from tools.quality import quality_gate


# {
# 責務: [ QualityGateTests: incremental quality gateの主要ruleを検証する ]
# フィールド: []
# 処理: [ 1: comment ruleを検証する, 2: 例外ruleを検証する, 3: 1000行監査を検証する ]
# }
class QualityGateTests(unittest.TestCase):
    # {
    # 責務: [test_added_line_ranges_parse_git_hunks: Git diff hunkから追加行rangeが正しく得られることを確認する]
    # 処理: [1: diff outputをmockする 2: hunk parserの開始/終了lineを確認する]
    # 引数: []
    # 戻り値: []
    # }
    def test_added_line_ranges_parse_git_hunks(self) -> None:
        result = SimpleNamespace(stdout="@@ -10,2 +12,4 @@ def work():\n")
        with mock.patch.object(quality_gate, "_run_git", return_value=result):
            ranges = quality_gate._added_line_ranges(
                Path("."), "sample.py", "base-sha", is_new=False, line_count=30
            )
        self.assertEqual(ranges, ((12, 15),))

    # {
    # 責務: [ test_accepts_json_like_comment_for_new_function: 必須comment付き新規functionを受理する ]
    # 処理: [ 1: sourceを作る, 2: scanする, 3: QUA200がないことを確認する ]
    # 引数: []
    # 戻り値: []
    # }
    def test_accepts_json_like_comment_for_new_function(self) -> None:
        source = """# {
# 責務: [ work: 値を返す ]
# 処理: [ 1: 値を返す ]
# 引数: []
# 戻り値: [ value: 値 ]
# }
def work():
    return 1
"""
        findings = quality_gate.scan_source("sample.py", source, ((1, 8),))
        self.assertFalse(any(item.rule == "QUA200" for item in findings))

    # {
    # 責務: [ test_rejects_new_bare_except: 新規bare exceptをerrorにする ]
    # 処理: [ 1: bare except sourceを作る, 2: scanする, 3: QUA210を確認する ]
    # 引数: []
    # 戻り値: []
    # }
    def test_rejects_new_bare_except(self) -> None:
        source = """# {
# 責務: [ work: 例外を処理する ]
# 処理: [ 1: 処理を実行する ]
# 引数: []
# 戻り値: []
# }
def work():
    try:
        return 1
    except:
        return 0
"""
        findings = quality_gate.scan_source("sample.py", source, ((1, 11),))
        self.assertTrue(any(item.rule == "QUA210" and item.severity == "E" for item in findings))

    # {
    # 責務: [ test_over_1000_lines_is_audit_not_error: 1000行超を禁止ではなく監査通知にする ]
    # 処理: [ 1: 1001行sourceを作る, 2: scanする, 3: QUA100の重大度を確認する ]
    # 引数: []
    # 戻り値: []
    # }
    def test_over_1000_lines_is_audit_not_error(self) -> None:
        source = "\n".join(["value = 1"] * 1001)
        findings = quality_gate.scan_source("large.py", source, ())
        audit = [item for item in findings if item.rule == "QUA100"]
        self.assertEqual(len(audit), 1)
        self.assertEqual(audit[0].severity, "A")

    # {
    #   責務: [test_rejects_new_subprocess_work_in_legacy_tab: legacy tabへ新しいsubprocess callを追加するとerrorになることを確認する]
    #   処理: [added range内のffmpeg callをscanしてQUA230をassertする]
    #   引数: [self]
    #   戻り値: [None]
    # }
    def test_rejects_new_subprocess_work_in_legacy_tab(self) -> None:
        source = "import subprocess\nsubprocess.run(['ffmpeg', '-version'])\n"
        findings = quality_gate.scan_source("scripts/tabs/example.py", source, ((1, 2),))
        self.assertTrue(any(item.rule == "QUA230" and item.severity == "E" for item in findings))

    # {
    #   責務: [test_allows_existing_subprocess_work_outside_added_lines: unchanged legacy subprocess callが新規violationにならないことを確認する]
    #   処理: [空のadded rangeでscanしてQUA230がないことをassertする]
    #   引数: [self]
    #   戻り値: [None]
    # }
    def test_allows_existing_subprocess_work_outside_added_lines(self) -> None:
        source = "import subprocess\nsubprocess.run(['ffmpeg', '-version'])\n"
        findings = quality_gate.scan_source("scripts/tabs/example.py", source, ())
        self.assertFalse(any(item.rule == "QUA230" for item in findings))

    # {
    #   責務: [test_rejects_new_network_and_filesystem_work_in_legacy_tab: legacy UIの新規HTTP and file mutationを検出する]
    #   処理: [requests and Path.write_text fixtureから2件のQUA230をassertする]
    #   引数: [self]
    #   戻り値: [None]
    # }
    def test_rejects_new_network_and_filesystem_work_in_legacy_tab(self) -> None:
        source = "import requests\nfrom pathlib import Path\nrequests.get('http://localhost')\nPath('out.txt').write_text('data')\n"
        findings = quality_gate.scan_source("scripts/tabs/example.py", source, ((1, 4),))
        self.assertEqual(sum(item.rule == "QUA230" for item in findings), 2)

    # {
    # 責務: [test_legacy_tab_file_reads_are_allowed_but_writes_are_rejected: read-only open remains allowed while file mutation is blocked]
    # 処理: [read modes and write modes through builtin/Path.openを比較する]
    # 引数: []
    # 戻り値: []
    # }
    def test_legacy_tab_file_reads_are_allowed_but_writes_are_rejected(self) -> None:
        read_source = "open('input.txt', 'r').read()\nPath('input.txt').open()\n"
        write_source = "open('output.txt', 'w').write('x')\nPath('output.txt').open('a')\n"
        read_findings = quality_gate.scan_source("scripts/tabs/example.py", read_source, ((1, 2),))
        write_findings = quality_gate.scan_source(
            "scripts/tabs/example.py", write_source, ((1, 2),)
        )
        self.assertFalse(any(item.rule == "QUA230" for item in read_findings))
        self.assertEqual(sum(item.rule == "QUA230" for item in write_findings), 2)

    # {
    #   責務: [test_requires_audit_for_new_declarations_in_mega_module: mega moduleへのnew declarationがaudit requirementになることを確認する]
    #   処理: [1000行超sourceへclassを加えてQUA240をassertする]
    #   引数: [self]
    #   戻り値: [None]
    # }
    def test_requires_audit_for_new_declarations_in_mega_module(self) -> None:
        source = "class NewResponsibility:\n    pass\n" + "value = 1\n" * 1000
        findings = quality_gate.scan_source("large.py", source, ((1, 1002),))
        self.assertTrue(any(item.rule == "QUA240" and item.severity == "E" for item in findings))

    # {
    # 責務: [test_audits_substantive_changes_in_mega_module: existing mega-module edits trigger a responsibility review]
    # 処理: [existing function lineをadded rangeに置きQUA241 audit findingを確認する]
    # 引数: []
    # 戻り値: []
    # }
    def test_audits_substantive_changes_in_mega_module(self) -> None:
        source = "def existing():\n    return 1\n" + "value = 1\n" * 1000
        findings = quality_gate.scan_source("large.py", source, ((2, 2),))
        audit = [item for item in findings if item.rule == "QUA241"]
        self.assertEqual(len(audit), 1)
        self.assertEqual(audit[0].severity, "A")

    # {
    #   責務: [test_rejects_direct_application_processing_import_in_legacy_ui: legacy UIのinternal processing module importを拒否する]
    #   処理: [added import fixtureからQUA231をassertする]
    #   引数: [self]
    #   戻り値: [None]
    # }
    def test_rejects_direct_application_processing_import_in_legacy_ui(self) -> None:
        source = "from comfyui_support_tools.applications.demo.data.processing.store import load\n"
        findings = quality_gate.scan_source("scripts/tabs/demo.py", source, ((1, 1),))
        self.assertTrue(any(item.rule == "QUA231" for item in findings))

    # {
    #   責務: [test_requires_central_tool_metadata_to_derive_from_registry: central tool metadataがTOOL_REGISTRY由来であることを確認する]
    #   処理: [hard-coded mappingを拒否しregistry-derived mappingを許可する]
    #   引数: [self]
    #   戻り値: [None]
    # }
    def test_requires_central_tool_metadata_to_derive_from_registry(self) -> None:
        hardcoded = "STABLE_SETTINGS_IDS = {'ImageTab': 'image'}\n"
        derived = "STABLE_SETTINGS_IDS = {item.settings_id for item in TOOL_REGISTRY.descriptors}\n"
        hardcoded_findings = quality_gate.scan_source(
            "scripts/widgets/tk_tab_settings_adapter.py", hardcoded, ((1, 1),)
        )
        derived_findings = quality_gate.scan_source(
            "scripts/widgets/tk_tab_settings_adapter.py", derived, ((1, 1),)
        )
        self.assertTrue(any(item.rule == "QUA232" for item in hardcoded_findings))
        self.assertFalse(any(item.rule == "QUA232" for item in derived_findings))

    # {
    #   責務: [test_precision_change_requires_test_module: precision changeにrelated test and complete validation evidenceが必要なことを確認する]
    #   処理: [missing evidence, valid evidence, unrelated test moduleを比較する]
    #   引数: [self]
    #   戻り値: [None]
    # }
    def test_precision_change_requires_test_module(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_path = root / "src" / "quality" / "evaluator.py"
            source_path.parent.mkdir(parents=True)
            source_path.write_text("def evaluate_score():\n    return 0.5\n", encoding="utf-8")
            changed_files = ("src/quality/evaluator.py",)
            findings = quality_gate.precision_validation_findings(
                root, changed_files
            )
            self.assertTrue(any(item.rule == "QUA250" for item in findings))
            changed_test = "tests/test_evaluator.py"
            changed_files_with_test = (*changed_files, changed_test)
            self.assertTrue(
                any(
                    item.rule == "QUA250"
                    for item in quality_gate.precision_validation_findings(
                        root, changed_files_with_test
                    )
                )
            )
            evidence_path = root / "docs" / "quality" / "evidence" / "evaluator.json"
            evidence_path.parent.mkdir(parents=True)
            evidence_path.write_text(
                '{"feature":"score calibration",'
                '"baseline":"legacy scorer",'
                '"validation_set":"tests/fixtures/scoring_cases.json",'
                '"metric":{"name":"accuracy","before":0.7,"after":0.9},'
                '"representative_failures":["low-light false positive"],'
                '"test_modules":["tests/test_evaluator.py"],'
                '"changed_files":["src/quality/evaluator.py"]}',
                encoding="utf-8",
            )
            self.assertEqual(
                quality_gate.precision_validation_findings(
                    root,
                    changed_files_with_test,
                    (changed_test, "docs/quality/evidence/evaluator.json"),
                ),
                [],
            )
            evidence_path.write_text(
                evidence_path.read_text(encoding="utf-8").replace('"before":0.7', '"before":NaN'),
                encoding="utf-8",
            )
            self.assertTrue(
                any(
                    item.rule == "QUA250"
                    for item in quality_gate.precision_validation_findings(
                        root,
                        changed_files_with_test,
                        (changed_test, "docs/quality/evidence/evaluator.json"),
                    )
                )
            )
            self.assertTrue(
                any(
                    item.rule == "QUA250"
                    for item in quality_gate.precision_validation_findings(
                        root,
                        (*changed_files, "tests/test_unrelated.py"),
                        ("tests/test_unrelated.py", "docs/quality/evidence/evaluator.json"),
                    )
                )
            )


if __name__ == "__main__":
    unittest.main()
