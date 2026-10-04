from pathlib import Path
import sys
import tempfile
import unittest

TOOLS_DOCS = Path(__file__).parents[1] / "tools" / "docs"
sys.path.insert(0, str(TOOLS_DOCS))

from generate_dependency_inventory import (  # noqa: E402
    parse_requirement_manifest,
    render_dependency_inventory,
)


class DependencyInventoryTests(unittest.TestCase):
    def test_parses_comments_and_preserves_requirement_constraints(self):
        entries = parse_requirement_manifest(
            "# comment\nPillow==10.4.0  # image processing\nnumpy>=1.26,<2\n",
            "requirements.txt",
        )

        self.assertEqual(
            entries,
            [("Pillow", "Pillow==10.4.0"), ("numpy", "numpy>=1.26,<2")],
        )

    def test_renders_package_purpose_from_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "requirements.txt").write_text(
                "# runtime\nrequests>=2.32,<3\n",
                encoding="utf-8",
            )

            document = render_dependency_inventory(
                root,
                [
                    {
                        "path": "requirements.txt",
                        "environment": "GUI runtime",
                        "purpose": "Runtime dependencies.",
                        "packages": {"Requests": "HTTP API clients."},
                    }
                ],
            )

        self.assertIn("requests>=2.32,<3", document)
        self.assertIn("HTTP API clients.", document)
        self.assertIn("Repeated distributions are intentional", document)

    def test_requires_a_reason_for_every_declared_package(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "requirements.txt").write_text("psutil>=6,<8\n", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "missing rationales: psutil"):
                render_dependency_inventory(
                    root,
                    [
                        {
                            "path": "requirements.txt",
                            "environment": "GUI runtime",
                            "purpose": "Runtime dependencies.",
                            "packages": {},
                        }
                    ],
                )

    def test_rejects_requirements_includes_until_they_are_modeled(self):
        with self.assertRaisesRegex(ValueError, "pip options/includes are unsupported"):
            parse_requirement_manifest("-r shared.txt\n", "requirements.txt")

    def test_rejects_manifest_paths_outside_the_repository(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaisesRegex(ValueError, "must stay in the repository"):
                render_dependency_inventory(
                    root,
                    [
                        {
                            "path": "../outside.txt",
                            "environment": "runtime",
                            "purpose": "runtime",
                            "packages": {},
                        }
                    ],
                )


if __name__ == "__main__":
    unittest.main()
