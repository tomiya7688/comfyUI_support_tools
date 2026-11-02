"""Expose the shared Data-layer JobRuntime through its boundary."""

from comfyui_support_tools.applications.main_gui.data.processing.job_runtime import JobRuntime


# {
# 責務: [JobDataCommander: JobRuntimeのsnapshot/cancel/backend ID/close操作を境界へ公開する]
# フィールド: [_runtime: shared JobRuntime]
# }
class JobDataCommander:
    # {
    #   責務: [__init__: shared JobRuntimeを保持する]
    #   処理: [渡されたruntimeを操作delegateとして保存する]
    #   引数: [self: commander, runtime: job lifecycle owner]
    #   戻り値: [なし]
    # }
    def __init__(self, runtime: JobRuntime):
        self._runtime = runtime

    # {
    #   責務: [snapshots: 現在のjob snapshot一覧をruntimeから取得する]
    #   処理: [runtime.snapshotsを呼び戻り値を返す]
    #   引数: [self: commander]
    #   戻り値: [JobSnapshot sequence]
    # }
    def snapshots(self):
        return self._runtime.snapshots()

    # {
    #   責務: [cancel: job IDで識別したcancel可能jobの停止を依頼する]
    #   処理: [runtime.cancelへjob_idを渡す]
    #   引数: [self: commander, job_id: 対象job識別子]
    #   戻り値: [runtimeのcancel result]
    # }
    def cancel(self, job_id):
        return self._runtime.cancel(job_id)

    # {
    #   責務: [set_backend_job_id: job snapshotへbackend側job識別子を記録する]
    #   処理: [runtimeへlocal job IDとbackend IDを渡す]
    #   引数: [self: commander, job_id: local job ID, backend_job_id: remote backend ID]
    #   戻り値: [runtimeの更新result]
    # }
    def set_backend_job_id(self, job_id, backend_job_id):
        return self._runtime.set_backend_job_id(job_id, backend_job_id)

    # {
    #   責務: [close: shared job runtimeのworkerを閉じる]
    #   処理: [runtime.closeへ委譲する]
    #   引数: [self: commander]
    #   戻り値: [runtimeのclose result]
    #   副作用: [runtime worker lifecycleを終了する]
    # }
    def close(self):
        return self._runtime.close()
