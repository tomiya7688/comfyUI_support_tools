from __future__ import annotations

import errno
import os
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

_WINDOWS_LOCK_VIOLATION = 33


# {
#   責務: [character_profile_registration_lock: profile directoryの登録critical sectionをprocess間で排他する]
#   処理: [sidecar lock fileを開き, Windows byte-range lockまたはPOSIX flockを取得して解放する]
#   引数: [profile_directory: CharacterProfileの保存root]
#   戻り値: [Iterator[None]: lock中のcontext]
#   エラー: [OSError: lock fileを作成またはlockできない場合]
# }
@contextmanager
def character_profile_registration_lock(
    profile_directory: str | Path,
) -> Iterator[None]:
    """Hold an OS-level lock shared by processes registering profiles in one directory."""
    root = Path(profile_directory)
    root.mkdir(parents=True, exist_ok=True)
    lock_path = root / ".character-profile-registration.lock"
    descriptor = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
    lock_acquired = False
    try:
        if os.fstat(descriptor).st_size == 0:
            os.write(descriptor, b"\0")
        os.lseek(descriptor, 0, os.SEEK_SET)
        if os.name == "nt":
            _acquire_windows_file_lock(descriptor)
        else:
            import fcntl

            fcntl.flock(descriptor, fcntl.LOCK_EX)
        lock_acquired = True
        yield
    finally:
        try:
            if lock_acquired:
                os.lseek(descriptor, 0, os.SEEK_SET)
                if os.name == "nt":
                    import msvcrt

                    msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)


# {
#   責務: [_acquire_windows_file_lock: Windowsのbyte-range lockを取得する]
#   処理: [lock競合のEACCESだけを短い間隔で再試行し, その他のOSエラーは呼出元へ返す]
#   引数: [descriptor: byte-range lock対象のfile descriptor]
#   戻り値: []
#   エラー: [OSError: lock競合以外の取得失敗]
# }
def _acquire_windows_file_lock(descriptor: int) -> None:
    """Wait for the registration byte lock without msvcrt's ten-retry timeout."""
    import msvcrt

    while True:
        try:
            msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
            return
        except OSError as error:
            if error.errno != errno.EACCES or error.winerror not in (
                None,
                _WINDOWS_LOCK_VIOLATION,
            ):
                raise
            time.sleep(0.05)
