from __future__ import annotations

import ctypes
import os


# {
# 責務: [ProcessCpuLimiter: 子processへ適用するCPU core数を解釈しOS別に制限する]
# フィールド: []
# 処理: [1: 要求値を利用可能範囲へ正規化する, 2: 対応OSでprocess affinityを設定する]
# }
class ProcessCpuLimiter:
    """Apply a Windows CPU affinity limit to a spawned process."""

    # {
    # 責務: [core_count: CPU制限入力を有効なcore数へ正規化する]
    # 処理: [1: 空値なら制限なしを返す, 2: 整数化し利用可能CPU数の範囲へclampする]
    # 引数: [value: core数または文字列指定]
    # 戻り値: [有効なcore数、空入力ならNone]
    # }
    @staticmethod
    def core_count(value: str | int | None) -> int | None:
        if value is None or str(value).strip() == "":
            return None
        requested = int(str(value).strip())
        return max(1, min(requested, os.cpu_count() or 1))

    # {
    # 責務: [apply: 指定processへ可能な範囲でCPU制限を適用する]
    # 処理: [1: core数を検証する, 2: OS・process状態を確認する, 3: affinity設定結果を説明する]
    # 引数: [pid: 対象process ID, value: 希望するCPU core数]
    # 戻り値: [適用結果または未適用理由の表示文]
    # }
    @classmethod
    def apply(cls, pid: int, value: str | int | None) -> str:
        try:
            cores = cls.core_count(value)
        except ValueError:
            return f"CPU制限を適用しません: 数値を指定してください ({value})"
        if cores is None:
            return "CPU制限: なし"
        if os.name != "nt":
            return "CPU制限はこのOSでは未対応です"
        from ctypes import wintypes
        access = 0x0200 | 0x0400
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.SetProcessAffinityMask.argtypes = (wintypes.HANDLE, ctypes.c_size_t)
        kernel32.SetProcessAffinityMask.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
        kernel32.CloseHandle.restype = wintypes.BOOL
        handle = kernel32.OpenProcess(access, False, int(pid))
        if not handle:
            return f"CPU制限の適用に失敗しました (PID {pid})"
        try:
            mask = (1 << cores) - 1
            if not kernel32.SetProcessAffinityMask(handle, mask):
                return f"CPUアフィニティの設定に失敗しました (PID {pid})"
        finally:
            kernel32.CloseHandle(handle)
        return f"CPU制限: 論理CPU 0-{cores - 1}"
