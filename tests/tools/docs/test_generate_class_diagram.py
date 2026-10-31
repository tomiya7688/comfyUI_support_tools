"""Tests for source discovery in the generated class diagram."""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from tools.docs import generate_class_diagram


# {
#   責務: [ClassDiagramSourceDiscoveryTest: class diagramがvenvを走査しないことを検証する]
#   フィールド: []
#   処理: [venv/cache directoryのpruneとproject sourceの列挙を確認する]
# }
class ClassDiagramSourceDiscoveryTest(unittest.TestCase):
    # {
    #   責務: [test_python_file_discovery_prunes_virtual_environments: venvとcache directoryを走査前に除外する]
    #   処理: [1: venv/cacheを含むwalk resultを用意する, 2: source discoveryを実行する, 3: directory pruneとPython file一覧を検証する]
    #   引数: [self: unittest test case]
    #   戻り値: []
    # }
    def test_python_file_discovery_prunes_virtual_environments(self):
        directories = [
            "package",
            ".venv",
            ".venv-python-pre-31118",
            "venv",
            "venv.old",
            "__pycache__",
        ]
        walk_results = [("source", directories, ["module.py", "notes.txt"])]

        with patch.object(generate_class_diagram.os, "walk", return_value=iter(walk_results)):
            python_files = generate_class_diagram.iter_python_files(Path("source"))

        self.assertEqual(directories, ["package"])
        self.assertEqual(python_files, [Path("source/module.py")])


if __name__ == "__main__":
    unittest.main()
