"""Shared resource arbitration, bounded stage, backoff, and cache tests."""

import argparse
import threading
import time
import unittest

from comfyui_support_tools.shared.contracts.resource_budget import (
    ResourceBudget,
    ResourceBudgetOverride,
    ResourceKind,
)
from comfyui_support_tools.shared.resource_budget import (
    BoundedResourceStage,
    ResourceBudgetCancelled,
    ResourceBudgetManager,
    add_resource_budget_arguments,
    resolve_resource_budget_options,
)
from comfyui_support_tools.shared.retry_policy import external_api_backoff
from comfyui_support_tools.shared.versioned_cache import BoundedVersionedCache


# {
#   責務: [ResourceBudgetTests: budget precedence、global sharing、queue/cancel、OOM/cache policyを検証する]
#   フィールド: [thread synchronization events]
# }
class ResourceBudgetTests(unittest.TestCase):
    # {
    #   責務: [test_cli_budget_options_share_partial_profile_schema: CLI resource optionsをGUI/shared schemaと同じ型へ解決する]
    #   処理: [1: common CLI flagsを登録する 2: positive profile valuesとinvalid valuesを検証する]
    #   引数: []
    #   戻り値: []
    # }
    def test_cli_budget_options_share_partial_profile_schema(self):
        parser = argparse.ArgumentParser()
        add_resource_budget_arguments(parser)
        parsed = parser.parse_args(["--gpu-jobs", "1", "--cpu-threads", "6"])
        profile = resolve_resource_budget_options(parsed)
        self.assertEqual(profile.gpu_jobs, 1)
        self.assertEqual(profile.cpu_threads, 6)
        with self.assertRaises(ValueError):
            resolve_resource_budget_options(parser.parse_args(["--network-jobs", "0"]))

    # {
    #   責務: [test_budget_precedence_and_scope_caps: run/app/global profileを解決しglobal capを保持する]
    #   処理: [1: partial profile階層をresolveする 2: budgetを超えるacquireが拒否されることを確認する]
    #   引数: []
    #   戻り値: []
    # }
    def test_budget_precedence_and_scope_caps(self):
        manager = ResourceBudgetManager(
            ResourceBudgetOverride(cpu_threads=4),
            {"image": ResourceBudgetOverride(cpu_threads=3)},
        )
        run = ResourceBudgetOverride(cpu_threads=2, gpu_jobs=2)
        resolved = manager.resolve("image", run)
        self.assertEqual(resolved.cpu_threads, 2)
        self.assertEqual(resolved.gpu_jobs, 2)
        self.assertEqual(manager.resolve("other").cpu_threads, 4)
        with manager.acquire("image", "run-1", ResourceKind.CPU_THREADS, 2, run_budget=run):
            with self.assertRaisesRegex(ValueError, "exceeds"):
                manager.acquire("image", "run-2", ResourceKind.CPU_THREADS, 3, run_budget=run)

    # {
    #   責務: [test_global_lease_is_shared_across_applications: application別runでもglobal limitが共有される]
    #   処理: [1: app Aが唯一leaseを取る 2: app B waiterを起こしてrelease後取得を確認する]
    #   引数: []
    #   戻り値: []
    # }
    def test_global_lease_is_shared_across_applications(self):
        manager = ResourceBudgetManager(ResourceBudget(cpu_threads=1))
        entered = threading.Event()
        acquired = threading.Event()

        # {
        #   責務: [wait_for_shared_lease: second applicationのglobal leaseを待つ]
        #   処理: [1: manager.acquireを呼ぶ 2: acquisition eventを通知してleaseをreleaseする]
        #   引数: []
        #   戻り値: []
        # }
        def wait_for_shared_lease():
            with manager.acquire("app-b", "run-b", ResourceKind.CPU_THREADS):
                acquired.set()

        first = manager.acquire("app-a", "run-a", ResourceKind.CPU_THREADS)
        worker = threading.Thread(target=wait_for_shared_lease)
        worker.start()
        time.sleep(0.1)
        self.assertFalse(acquired.is_set())
        first.release()
        entered.set()
        self.assertTrue(acquired.wait(1))
        worker.join(1)
        self.assertFalse(worker.is_alive())

    # {
    #   責務: [test_resource_dimensions_are_independent: GPU reservationがCPU preprocessingを塞がない]
    #   処理: [1: GPU leaseを保持する 2: 別resource kindのCPU leaseを同時取得する]
    #   引数: []
    #   戻り値: []
    # }
    def test_resource_dimensions_are_independent(self):
        manager = ResourceBudgetManager(ResourceBudget(cpu_threads=4, gpu_jobs=1))
        with manager.acquire("app", "gpu-run", ResourceKind.GPU_JOBS):
            with manager.acquire("app", "cpu-run", ResourceKind.CPU_THREADS, 4):
                self.assertEqual(
                    manager.usage_snapshot()[("global", "", ResourceKind.CPU_THREADS.value)],
                    4,
                )

    # {
    #   責務: [test_stage_priority_runs_next_and_external_wait_can_cancel: priority queueが高優先itemを先に処理する]
    #   処理: [1: active itemをbarrierで止める 2:低優先/高優先を積む 3:順序とcancel waiterを確認する]
    #   引数: []
    #   戻り値: []
    # }
    def test_stage_priority_runs_next_and_external_wait_can_cancel(self):
        started = threading.Event()
        release = threading.Event()
        completed = []

        # {
        #   責務: [record: stage itemを記録して最初だけbarrierを待つ]
        #   処理: [1: first itemのstarted eventをsetする 2: output listへ追加する]
        #   引数: [item: queue entry]
        #   戻り値: []
        # }
        def record(item, cancellation):
            if item == "active":
                started.set()
                release.wait(2)
            completed.append(item)
            return None

        stage = BoundedResourceStage(
            "priority",
            record,
            ResourceBudgetManager(),
            "app",
            "run",
            ResourceKind.CPU_THREADS,
            concurrency=1,
            queue_capacity=3,
        )
        stage.submit("active")
        self.assertTrue(started.wait(1))
        stage.submit("low", priority=10)
        stage.submit("high", priority=-1)
        release.set()
        stage.join()
        self.assertEqual(completed, ["active", "high", "low"])
        self.assertTrue(stage.close())

        manager = ResourceBudgetManager(ResourceBudget(cpu_threads=1))
        lease = manager.acquire("app-1", "run-1", ResourceKind.CPU_THREADS)
        cancelled = threading.Event()
        cancellation_result = []

        # {
        #   責務: [wait_cancelled: blocked resource waiterにcancel tokenを渡す]
        #   処理: [1: blocked acquireを呼ぶ 2: cancellation exceptionを記録する]
        #   引数: []
        #   戻り値: []
        # }
        def wait_cancelled():
            try:
                manager.acquire(
                    "app-2",
                    "run-2",
                    ResourceKind.CPU_THREADS,
                    cancellation=cancelled,
                )
            except ResourceBudgetCancelled:
                cancellation_result.append("cancelled")

        waiter = threading.Thread(target=wait_cancelled)
        waiter.start()
        time.sleep(0.1)
        cancelled.set()
        waiter.join(1)
        lease.release()
        self.assertEqual(cancellation_result, ["cancelled"])
        self.assertFalse(waiter.is_alive())

    # {
    #   責務: [test_bounded_stage_applies_backpressure_and_completes: queue capacity時submitがproducerを待たせる]
    #   処理: [1: workerをhandlerでblockする 2: queue満杯後第三submitがbackpressureすることを確認する 3: releaseしてdrainする]
    #   引数: []
    #   戻り値: []
    # }
    def test_bounded_stage_applies_backpressure_and_completes(self):
        started = threading.Event()
        release = threading.Event()
        results = []

        # {
        #   責務: [process: controlled stage inputを処理して完了値を返す]
        #   処理: [1: 最初のitemでgate待ちする 2: processed itemを記録する]
        #   引数: [item: stage input]
        #   戻り値: [result: processed item]
        # }
        def process(item, cancellation):
            if item == 1:
                started.set()
                release.wait(2)
            results.append(item)
            return None

        stage = BoundedResourceStage(
            "cpu",
            process,
            ResourceBudgetManager(ResourceBudget(cpu_threads=1)),
            "app",
            "run",
            ResourceKind.CPU_THREADS,
            concurrency=1,
            queue_capacity=1,
        )
        stage.submit(1)
        self.assertTrue(started.wait(1))
        stage.submit(2)
        accepted = threading.Event()

        # {
        #   責務: [submit_third: full queueへ第三itemをputする]
        #   処理: [1: submitを呼ぶ 2: backpressure解除後にeventを通知する]
        #   引数: []
        #   戻り値: []
        # }
        def submit_third():
            stage.submit(3)
            accepted.set()

        producer = threading.Thread(target=submit_third)
        producer.start()
        time.sleep(0.12)
        self.assertFalse(accepted.is_set())
        release.set()
        self.assertTrue(accepted.wait(1))
        producer.join(1)
        stage.join()
        self.assertCountEqual(results, [1, 2, 3])
        self.assertGreater(stage.metrics().backpressure_waits, 0)
        self.assertTrue(stage.close())

    # {
    #   責務: [test_stage_cancellation_stops_ingress_and_discards_pending: cancellation後はqueued workを破棄する]
    #   処理: [1: workerをactiveにしqueueへpendingを積む 2: cancelしてdiscardとnew submit拒否を検証する]
    #   引数: []
    #   戻り値: []
    # }
    def test_stage_cancellation_stops_ingress_and_discards_pending(self):
        started = threading.Event()
        release = threading.Event()

        # {
        #   責務: [wait_first: active workをcancel test用barrierで止める]
        #   処理: [1: started eventをsetする 2: releaseまで待つ]
        #   引数: [item: stage input]
        #   戻り値: []
        # }
        def wait_first(item, cancellation):
            started.set()
            release.wait(2)
            return item

        stage = BoundedResourceStage(
            "cancel",
            wait_first,
            ResourceBudgetManager(),
            "app",
            "run",
            ResourceKind.CPU_THREADS,
            concurrency=1,
            queue_capacity=2,
        )
        stage.submit("active")
        self.assertTrue(started.wait(1))
        stage.submit("pending")
        self.assertEqual(stage.cancel(), 1)
        with self.assertRaises(ResourceBudgetCancelled):
            stage.submit("after cancel")
        release.set()
        self.assertTrue(stage.close())

    # {
    #   責務: [test_oom_uses_one_degraded_attempt_and_cache_is_bounded: OOM降格は無限retryせずcacheはLRU上限を守る]
    #   処理: [1: handlerをOOMにする 2: degraded callbackを一度呼ぶ 3: cache eviction/version/clearを確認する]
    #   引数: []
    #   戻り値: []
    # }
    def test_oom_uses_one_degraded_attempt_and_cache_is_bounded(self):
        fallback_calls = []

        # {
        #   責務: [raise_oom: regular stage pathがmemory errorとなることを表す]
        #   処理: [1: MemoryErrorをraiseする]
        #   引数: [item: stage input]
        #   戻り値: []
        # }
        def raise_oom(item, cancellation):
            raise MemoryError("simulated OOM")

        # {
        #   責務: [degrade: lower resource fallbackを一度だけ実行する]
        #   処理: [1: fallback inputを記録する 2: degraded resultを返す]
        #   引数: [item: stage input]
        #   戻り値: [result: fallback output]
        # }
        def degrade(item, cancellation):
            fallback_calls.append(item)
            return f"small:{item}"

        stage = BoundedResourceStage(
            "gpu",
            raise_oom,
            ResourceBudgetManager(),
            "app",
            "run",
            ResourceKind.GPU_JOBS,
            concurrency=1,
            queue_capacity=1,
            degrade_after_oom=degrade,
        )
        stage.submit("item")
        stage.join()
        self.assertEqual(fallback_calls, ["item"])
        self.assertEqual(stage.metrics().degraded_after_oom, 1)
        self.assertTrue(stage.close())

        cache = BoundedVersionedCache(2, "v1")
        first = cache.key({"source": "a", "threshold": 0.4})
        self.assertNotEqual(
            first, BoundedVersionedCache(2, "v2").key({"source": "a", "threshold": 0.4})
        )
        self.assertEqual(cache.put(first, "a"), 0)
        second = cache.key({"source": "b"})
        third = cache.key({"source": "c"})
        cache.put(second, "b")
        self.assertEqual(cache.put(third, "c"), 1)
        self.assertIsNone(cache.get(first))
        self.assertEqual(cache.clear(), 2)

    # {
    #   責務: [test_external_api_backoff_is_bounded_and_honors_server_hint: exponential backoffを上限とRetry-Afterで制限する]
    #   処理: [1: exponential/capped/hint casesを評価する 2: invalid attemptを拒否する]
    #   引数: []
    #   戻り値: []
    # }
    def test_external_api_backoff_is_bounded_and_honors_server_hint(self):
        self.assertEqual(external_api_backoff(1), 0.5)
        self.assertEqual(external_api_backoff(4), 4.0)
        self.assertEqual(external_api_backoff(20), 30.0)
        self.assertEqual(external_api_backoff(2, retry_after_seconds=5), 5)
        with self.assertRaises(ValueError):
            external_api_backoff(0)


if __name__ == "__main__":
    unittest.main()
