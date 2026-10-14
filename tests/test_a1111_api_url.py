"""Tests for normalizing A1111 API URLs."""

import unittest

from scripts.backend.a1111_api_url import normalize_a1111_api_root


# {
#   責務: [A1111ApiUrlTests: A1111 API URLの各入力形式が同じrootへ正規化されることを検証する]
#   フィールド: []
#   処理: [既知endpoint suffixとbase URLを共通rootへ正規化する]
# }
class A1111ApiUrlTests(unittest.TestCase):
    # {
    #   責務: [test_known_endpoint_suffixes_are_removed: 既知のA1111 endpointがrootから除去されることを検証する]
    #   処理: [1: base URLと各endpoint URLを渡す, 2: 同一rootになることを確認する]
    #   引数: [self: test case]
    #   戻り値: []
    # }
    def test_known_endpoint_suffixes_are_removed(self):
        urls = (
            "http://localhost:7860",
            "http://localhost:7860/",
            "http://localhost:7860/sdapi",
            "http://localhost:7860/sdapi/v1",
            "http://localhost:7860/sdapi/v1/txt2img",
            "http://localhost:7860/sdapi/v1/img2img",
            "http://localhost:7860/sdapi/v1/interrogate",
        )

        for url in urls:
            with self.subTest(url=url):
                self.assertEqual(normalize_a1111_api_root(url), "http://localhost:7860")


if __name__ == "__main__":
    unittest.main()
