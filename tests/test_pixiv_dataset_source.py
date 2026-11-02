"""Focused adapter checks for Pixiv source request and response boundaries."""

from __future__ import annotations

import unittest

from comfyui_support_tools.shared.pixiv_dataset import PixivPy3Adapter
from tests.test_pixiv_dataset import FakePixivApi


# {
# 責務: [PixivDatasetSourceTests: verify API adapter normalization and authentication boundaries]
# フィールド: [fake API endpoint recorder]
# 処理: [exercise source requests without live Pixiv credentials or network]
# }
class PixivDatasetSourceTests(unittest.TestCase):
    # {
    # 責務: [test_paged_bookmark_and_ranking_requests_preserve_api_options]
    # 処理: [validate multi-page result normalization and visibility/ranking mapping]
    # 引数: [None: unittest scenario]
    # 戻り値: [None: assertions pass or raise]
    # }
    def test_paged_bookmark_and_ranking_requests_preserve_api_options(self):
        api = FakePixivApi()
        adapter = PixivPy3Adapter(api, request_interval=0, sleeper=lambda _delay: None)
        adapter.authenticate("temporary-token")

        bookmarks = adapter.list_bookmarks(2, "private")
        ranking = adapter.list_ranking("weekly", 2)

        self.assertEqual([work.work_id for work in bookmarks], ["101", "102"])
        self.assertEqual(api.bookmark_restricts, ["private", "private"])
        self.assertEqual(ranking[0].work_id, "101")
        self.assertEqual(api.ranking_modes, ["week", "week"])
        self.assertNotIn("temporary-token", repr(adapter.__dict__))
