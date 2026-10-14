"""Keep generation-backend API details out of Tkinter tabs."""

import unittest
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).parents[1]
GENERATION_API_ENDPOINTS = (
    "/sdapi/v1/txt2img",
    "/sdapi/v1/img2img",
    "/sdapi/v1/interrupt",
    "/sdapi/v1/progress",
    "/prompt",
    "/history/",
    "/queue",
    "/system_stats",
    "/object_info/",
)


# {
#   責務: [GenerationBackendUiBoundaryTests: GUI層とgeneration backend APIの境界を検証する]
#   フィールド: [REPOSITORY_ROOT: 対象repository root, GENERATION_API_ENDPOINTS: GUIに漏らさないendpoint一覧]
#   処理: [scripts/tabs内のendpoint参照を走査し, backend固有処理の混入を検出する]
# }
class GenerationBackendUiBoundaryTests(unittest.TestCase):
    # {
    #   責務: [test_tabs_do_not_embed_generation_api_endpoints: Tkinter tabに生成API endpoint直書きがないことを検証する]
    #   処理: [scripts/tabs配下のPythonソースを走査し, backend固有の生成API endpointがあれば失敗させる]
    #   引数: [self: unittest test case]
    #   戻り値: []
    # }
    def test_tabs_do_not_embed_generation_api_endpoints(self):
        tab_root = REPOSITORY_ROOT / "scripts" / "tabs"
        violations = []

        for source_path in sorted(tab_root.rglob("*.py")):
            source = source_path.read_text(encoding="utf-8")
            for endpoint in GENERATION_API_ENDPOINTS:
                if endpoint in source:
                    violations.append(f"{source_path.relative_to(REPOSITORY_ROOT)}: {endpoint}")

        self.assertEqual(violations, [])


if __name__ == "__main__":
    unittest.main()
