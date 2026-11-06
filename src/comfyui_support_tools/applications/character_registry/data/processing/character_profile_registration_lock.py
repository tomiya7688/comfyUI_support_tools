from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


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
            import msvcrt

            msvcrt.locking(descriptor, msvcrt.LK_LOCK, 1)
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
