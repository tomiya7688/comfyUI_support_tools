from __future__ import annotations

import unittest

from tools.quality import resource_leak_gate


# {
# 責務: [ ResourceLeakGateTests: resource leak gateの主要ruleを固定する ]
# フィールド: []
# 処理: [ 1: Queue上限を検証する, 2: communicate禁止を検証する, 3: health thread停止可能性を検証する ]
# }
class ResourceLeakGateTests(unittest.TestCase):
    # {
    # 責務: [ test_unbounded_queue_is_rejected: maxsizeなしQueueを検出する ]
    # 処理: [ 1: sourceをscanする, 2: RLG001を確認する ]
    # 引数: []
    # 戻り値: []
    # }
    def test_unbounded_queue_is_rejected(self) -> None:
        findings = resource_leak_gate.scan_source(
            "sample.py",
            "import queue\nitems = queue.Queue()\n",
        )
        self.assertTrue(any(item.rule == "RLG001" for item in findings))

    # {
    # 責務: [ test_bounded_queue_is_allowed: 正のmaxsize付きQueueを許可する ]
    # 処理: [ 1: sourceをscanする, 2: RLG001がないことを確認する ]
    # 引数: []
    # 戻り値: []
    # }
    def test_bounded_queue_is_allowed(self) -> None:
        findings = resource_leak_gate.scan_source(
            "sample.py",
            "import queue\nitems = queue.Queue(maxsize=100)\n",
        )
        self.assertFalse(any(item.rule == "RLG001" for item in findings))

    # {
    # 責務: [ test_communicate_is_rejected: subprocess全量bufferingを検出する ]
    # 処理: [ 1: communicate sourceをscanする, 2: RLG002を確認する ]
    # 引数: []
    # 戻り値: []
    # }
    def test_communicate_is_rejected(self) -> None:
        findings = resource_leak_gate.scan_source(
            "sample.py",
            "def run(process):\n    process.communicate()\n",
        )
        self.assertTrue(any(item.rule == "RLG002" for item in findings))

    # {
    # 責務: [ test_health_monitor_sleep_is_rejected: health監視の停止不能sleepを検出する ]
    # 処理: [ 1: health check sourceをscanする, 2: RLG003を確認する ]
    # 引数: []
    # 戻り値: []
    # }
    def test_health_monitor_sleep_is_rejected(self) -> None:
        findings = resource_leak_gate.scan_source(
            "sample.py",
            "import time\ndef health_check_thread():\n    time.sleep(100)\n",
        )
        self.assertTrue(any(item.rule == "RLG003" for item in findings))


if __name__ == "__main__":
    unittest.main()
