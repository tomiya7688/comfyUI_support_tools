from __future__ import annotations

import ctypes
import os


class ProcessCpuLimiter:
    """Apply a Windows CPU affinity limit to a spawned process."""

    @staticmethod
    def core_count(value: str | int | None) -> int | None:
        if value is None or str(value).strip() == "":
            return None
        requested = int(str(value).strip())
        return max(1, min(requested, os.cpu_count() or 1))

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
