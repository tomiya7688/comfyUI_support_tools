"""Keep generation-backend API details out of Tkinter tabs."""

import ast
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
GENERATION_UI_TAB_FILES = (
    "random_image.py",
    "random_img2img.py",
    "prompt_generate.py",
)
BACKEND_IMPLEMENTATION_MODULES = (
    "a1111_image_generation_backend",
    "comfyui_image_generation_backend",
    "comfy_ui_client",
    "generation_backend_registry",
    "generation_backend_catalog_factory",
    "image_generation_backend_factory",
)
GENERATION_BACKEND_IDS = {"a1111", "comfyui"}


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

    # {
    #   責務: [test_generation_tabs_do_not_select_or_import_backend_details: 生成tabがbackend IDやadapter実装を直接参照しないことを検証する]
    #   処理: [生成tabのASTを走査し, runtime backend名・backend固有module・backend ID literalの使用を検出する]
    #   引数: [self: unittest test case]
    #   戻り値: []
    # }
    def test_generation_tabs_do_not_select_or_import_backend_details(self):
        tab_root = REPOSITORY_ROOT / "scripts" / "tabs"
        violations = []

        for filename in GENERATION_UI_TAB_FILES:
            source_path = tab_root / filename
            source = source_path.read_text(encoding="utf-8")
            syntax_tree = ast.parse(source, filename=str(source_path))
            for node in ast.walk(syntax_tree):
                if isinstance(node, ast.Name) and node.id == "RUNTIME_BACKEND":
                    violations.append(f"{filename}:{node.lineno}: RUNTIME_BACKEND")
                if isinstance(node, ast.Constant) and node.value in GENERATION_BACKEND_IDS:
                    violations.append(f"{filename}:{node.lineno}: {node.value}")
                if isinstance(node, ast.ImportFrom) and node.module:
                    if any(node.module.endswith(name) for name in BACKEND_IMPLEMENTATION_MODULES):
                        violations.append(f"{filename}:{node.lineno}: {node.module}")
                if isinstance(node, ast.Import):
                    for imported_module in node.names:
                        if any(imported_module.name.endswith(name) for name in BACKEND_IMPLEMENTATION_MODULES):
                            violations.append(f"{filename}:{node.lineno}: {imported_module.name}")

        self.assertEqual(violations, [])


if __name__ == "__main__":
    unittest.main()
