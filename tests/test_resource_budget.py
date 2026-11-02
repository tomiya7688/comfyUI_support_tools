"""Shared resource arbitration, bounded stage, backoff, and cache tests."""

import argparse
import threading
import time
import unittest

from comfyui_support_tools.shared.contracts.resource_budget import (
    CancellationPolicy,
    ResourceBudget,
    ResourceBudgetOverride,
    ResourceKind,
)
from comfyui_support_tools.shared.resource_budget import (
    BoundedResourceStage,
    ResourceBudgetCancelled,
    ResourceBudgetManager,
    ResourceBudgetUnavailable,
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
        parsed = parser.parse_args(
            [
                "--gpu-jobs",
                "1",
                "--cpu-threads",
                "6",
                "--priority",
                "-2",
                "--cancellation-policy",
                "finish_active",
            ]
        )
        profile = resolve_resource_budget_options(parsed)
        self.assertEqual(profile.gpu_jobs, 1)
        self.assertEqual(profile.cpu_threads, 6)
        self.assertEqual(profile.priority, -2)
        self.assertEqual(profile.cancellation_policy, CancellationPolicy.FINISH_ACTIVE)
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
#   責務: [ResourceBudgetConcurrencyTests: resource wait、stage queue、backpressure/cancelを検証する]
#   フィールド: [thread synchronization eventsとshared budget manager]
# }
class ResourceBudgetConcurrencyTests(unittest.TestCase):
    # {
    #   責務: [test_resource_waiters_respect_queue_capacity_and_timeout: global waiter queueをboundedにする]
    #   処理: [1: leaseを占有する 2: capacity一杯までwaiterを追加する 3: overflowとtimeoutを確認する]
    #   引数: []
    #   戻り値: []
    # }
    def test_resource_waiters_respect_queue_capacity_and_timeout(self):
        manager = ResourceBudgetManager(ResourceBudget(cpu_threads=1, queue_capacity=1))
        lease = manager.acquire("app", "active", ResourceKind.CPU_THREADS)
        waiting = threading.Event()
        cancelled = threading.Event()

        # {
        #   責務: [wait_for_resource: capacity解放までresource acquireを待つ]
        #   処理: [1: blocked acquireへ入る 2: cancellationでwaitを終了する]
        #   引数: []
        #   戻り値: []
        # }
        def wait_for_resource():
            waiting.set()
            try:
                manager.acquire("app", "queued", ResourceKind.CPU_THREADS, cancellation=cancelled)
            except ResourceBudgetCancelled:
                pass

        worker = threading.Thread(target=wait_for_resource)
        worker.start()
        self.assertTrue(waiting.wait(1))
        deadline = time.monotonic() + 1
        while not manager._waiter_scopes and time.monotonic() < deadline:
            time.sleep(0.005)
        with self.assertRaises(ResourceBudgetUnavailable):
            manager.acquire("app", "overflow", ResourceKind.CPU_THREADS, timeout=0.1)
        cancelled.set()
        worker.join(1)
        self.assertFalse(worker.is_alive())
        with self.assertRaises(ResourceBudgetUnavailable):
            manager.acquire("app", "timeout", ResourceKind.CPU_THREADS, timeout=0)
        lease.release()

    # {
    #   責務: [test_resource_waiters_are_priority_ordered: shared lease waiterをpriority順に処理する]
    #   処理: [1: resourceを占有する 2: low/high waitersを登録する 3: release後の取得順を確認する]
    #   引数: []
    #   戻り値: []
    # }
    def test_resource_waiters_are_priority_ordered(self):
        manager = ResourceBudgetManager(ResourceBudget(cpu_threads=1))
        first = manager.acquire("app", "first", ResourceKind.CPU_THREADS)
        order = []
        lock = threading.Lock()

        # {
        #   責務: [request_with_priority: requested priorityでshared resourceを待つ]
        #   処理: [1: leaseを待つ 2: 取得順を記録する 3: leaseをreleaseする]
        #   引数: [name: completion label, priority: urgency rank]
        #   戻り値: []
        # }
        def request_with_priority(name, priority):
            with manager.acquire("app", name, ResourceKind.CPU_THREADS, priority=priority):
                with lock:
                    order.append(name)

        low = threading.Thread(target=request_with_priority, args=("low", 10))
        high = threading.Thread(target=request_with_priority, args=("high", -1))
        low.start()
        deadline = time.monotonic() + 1
        while len(manager._waiter_scopes) < 1 and time.monotonic() < deadline:
            time.sleep(0.005)
        high.start()
        deadline = time.monotonic() + 1
        while len(manager._waiter_scopes) < 2 and time.monotonic() < deadline:
            time.sleep(0.005)
        first.release()
        low.join(1)
        high.join(1)
        self.assertFalse(low.is_alive())
        self.assertFalse(high.is_alive())
        self.assertEqual(order, ["high", "low"])

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
    #   責務: [test_gpu_stage_reserves_vram_and_gpu_jobs_together: GPU concurrencyをVRAM予算でも制御する]
    #   処理: [1: GPU job capより低いVRAM capを設定する 2: simultaneous VRAM leaseが超過しないことを確認する]
    #   引数: []
    #   戻り値: []
    # }
    def test_gpu_stage_reserves_vram_and_gpu_jobs_together(self):
        manager = ResourceBudgetManager(ResourceBudget(gpu_jobs=4, vram_budget_mb=500))
        started = threading.Event()
        release = threading.Event()
        count_lock = threading.Lock()
        active = 0
        maximum_active = 0

        # {
        #   責務: [hold_gpu: GPU stageを一時停止して同時実行数を観測する]
        #   処理: [1: active countを加算する 2: gateを待つ 3: countを戻す]
        #   引数: [item: stage item, cancellation: cancellation token]
        #   戻り値: []
        # }
        def hold_gpu(item, cancellation):
            nonlocal active, maximum_active
            with count_lock:
                active += 1
                maximum_active = max(maximum_active, active)
            started.set()
            release.wait(1)
            with count_lock:
                active -= 1

        stage = BoundedResourceStage(
            "gpu-vram",
            hold_gpu,
            manager,
            "app",
            "run",
            ResourceKind.GPU_JOBS,
            resource_requirements={ResourceKind.VRAM_MB: 400},
            concurrency=4,
            queue_capacity=2,
        )
        stage.submit("one")
        stage.submit("two")
        self.assertTrue(started.wait(1))
        time.sleep(0.05)
        self.assertEqual(manager.usage_snapshot()[("global", "", "vram_budget_mb")], 400)
        self.assertEqual(maximum_active, 1)
        release.set()
        stage.join()
        self.assertEqual(maximum_active, 1)
        self.assertTrue(stage.close())

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
    #   責務: [test_stage_worker_count_respects_resource_budget_and_can_finish_active_item: worker countとcancel policyをbudgetに従わせる]
    #   処理: [1: concurrencyをresource capacityへclampする 2: finish-active cancellationで処理中itemを完了する]
    #   引数: []
    #   戻り値: []
    # }
    def test_stage_worker_count_respects_resource_budget_and_can_finish_active_item(self):
        started = threading.Event()
        release = threading.Event()
        completed = []

        # {
        #   責務: [finish_current: active itemをgate解放後に記録する]
        #   処理: [1: handler開始を通知する 2: gateを待って完了記録する]
        #   引数: [item: input, cancellation: shared cancel token]
        #   戻り値: []
        # }
        def finish_current(item, cancellation):
            started.set()
            release.wait(1)
            completed.append(item)

        stage = BoundedResourceStage(
            "finish-active",
            finish_current,
            ResourceBudgetManager(ResourceBudget(cpu_threads=1)),
            "app",
            "run",
            ResourceKind.CPU_THREADS,
            concurrency=8,
            queue_capacity=1,
            budget=ResourceBudgetOverride(cancellation_policy=CancellationPolicy.FINISH_ACTIVE),
        )
        self.assertEqual(stage.concurrency, 1)
        stage.submit("active")
        self.assertTrue(started.wait(1))
        stage.submit("pending")
        self.assertEqual(stage.cancel(), 1)
        self.assertFalse(stage._cancellation.is_set())
        release.set()
        self.assertTrue(stage.close())
        self.assertEqual(completed, ["active"])

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
        manager = ResourceBudgetManager(ResourceBudget(gpu_jobs=1))

        # {
        #   責務: [degrade: GPU lease返却後に縮退callbackから同じbudgetを再取得する]
        #   処理: [1: lease取得可能性を確認する 2: fallback inputを記録して縮退値を返す]
        #   引数: [item: fallback input, cancellation: cancellation token]
        #   戻り値: [result: degraded output]
        # }
        def degrade(item, cancellation):
            with manager.acquire("app", "fallback", ResourceKind.GPU_JOBS, timeout=0.1):
                pass
            fallback_calls.append(item)
            return f"small:{item}"

        stage = BoundedResourceStage(
            "gpu",
            raise_oom,
            manager,
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

        byte_cache = BoundedVersionedCache(
            3, "v1", max_size_bytes=5, size_of=lambda value: len(value)
        )
        self.assertEqual(byte_cache.put("first", "abc"), 0)
        self.assertEqual(byte_cache.put("second", "def"), 1)
        self.assertEqual(byte_cache.size_bytes, 3)
        with self.assertRaisesRegex(ValueError, "exceeds"):
            byte_cache.put("too-large", "123456")

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
        self.assertEqual(external_api_backoff(2, retry_after_seconds=0), 0)
        with self.assertRaises(ValueError):
            external_api_backoff(0)
        with self.assertRaises(ValueError):
            external_api_backoff(1, base_seconds="fast")


if __name__ == "__main__":
    unittest.main()
