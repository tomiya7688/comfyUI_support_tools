"""Create and verify the final release archive and SHA-256 manifest."""

import argparse
import hashlib
import os
import stat
import tempfile
from pathlib import Path, PurePosixPath
from zipfile import ZIP_DEFLATED, BadZipFile, ZipFile, ZipInfo

ARCHIVE_NAME = "KadokaTools-windows-onedir.zip"
CHECKSUM_NAME = "SHA256SUMS.txt"
CHUNK_SIZE = 1024 * 1024
NORMALIZED_TIMESTAMP = (1980, 1, 1, 0, 0, 0)


# {
#   責務: [package_distribution: signed staging directoryをdeterministic zipとchecksum manifestへ梱包する]
#   処理: [1: source/output境界を検証する 2: sorted file entriesをnormalized timestampでzip化する 3: SHA256SUMSをatomic publishする]
#   引数: [source_dir: distribution root, output_dir: release output directory]
#   戻り値: [archive_path/checksum_path: final artifact paths]
# }
def package_distribution(source_dir: Path, output_dir: Path) -> tuple[Path, Path]:
    source = Path(source_dir).resolve(strict=True)
    destination = Path(output_dir).resolve()
    if not source.is_dir():
        raise ValueError("distribution source must be a directory")
    if destination == source or source in destination.parents:
        raise ValueError("release output directory must be outside the distribution source")
    entries = _distribution_entries(source)
    if not entries:
        raise ValueError("distribution source is empty")
    destination.mkdir(parents=True, exist_ok=True)
    archive = destination / ARCHIVE_NAME
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{ARCHIVE_NAME}.", suffix=".tmp", dir=destination
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        with ZipFile(
            temporary, "w", compression=ZIP_DEFLATED, compresslevel=6, strict_timestamps=True
        ) as bundle:
            for source_path, archive_name in entries:
                info = ZipInfo(archive_name, NORMALIZED_TIMESTAMP)
                info.compress_type = ZIP_DEFLATED
                info.create_system = 3
                mode = source_path.stat().st_mode
                info.external_attr = (stat.S_IMODE(mode) & 0xFFFF) << 16
                if source_path.is_dir():
                    info.external_attr |= 0x10
                    bundle.writestr(info, b"")
                else:
                    with source_path.open("rb") as content, bundle.open(info, "w") as target:
                        while chunk := content.read(CHUNK_SIZE):
                            target.write(chunk)
        with ZipFile(temporary, "r") as bundle:
            bad_member = bundle.testzip()
            if bad_member is not None:
                raise ValueError(f"archive CRC validation failed for {bad_member}")
        temporary.replace(archive)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise

    checksum = destination / CHECKSUM_NAME
    digest = sha256_file(archive)
    checksum_data = f"{digest}  {ARCHIVE_NAME}\n".encode("ascii")
    _atomic_write(checksum, checksum_data)
    return archive, checksum


# {
#   責務: [verify_distribution: archive/checksumの一致とzip member path安全性を検証する]
#   処理: [1: checksum manifestの形式/対象を検証する 2: digestを比較する 3: CRCとmember pathを検証する]
#   引数: [output_dir: packaged artifact directory]
#   戻り値: [verified: archive and manifest paths]
# }
def verify_distribution(output_dir: Path) -> tuple[Path, Path]:
    root = Path(output_dir)
    archive = root / ARCHIVE_NAME
    checksum = root / CHECKSUM_NAME
    try:
        lines = checksum.read_text(encoding="ascii").splitlines()
    except (OSError, UnicodeError) as error:
        raise ValueError("checksum manifest cannot be read") from error
    if len(lines) != 1:
        raise ValueError("checksum manifest must contain exactly one artifact entry")
    fields = lines[0].split("  ", 1)
    if len(fields) != 2 or fields[1] != ARCHIVE_NAME or len(fields[0]) != 64:
        raise ValueError("checksum manifest entry is malformed")
    try:
        int(fields[0], 16)
    except ValueError as error:
        raise ValueError("checksum digest is not hexadecimal") from error
    if sha256_file(archive) != fields[0].lower():
        raise ValueError("archive SHA-256 does not match the checksum manifest")
    try:
        with ZipFile(archive, "r") as bundle:
            members = bundle.infolist()
            names = [member.filename for member in members]
            normalized_names = [PurePosixPath(name).as_posix().rstrip("/") for name in names]
            if not names or bundle.testzip() is not None:
                raise ValueError("archive is empty or has a CRC failure")
            if len(normalized_names) != len(set(normalized_names)) or any(
                not _safe_archive_name(member.filename) or stat.S_ISLNK(member.external_attr >> 16)
                for member in members
            ):
                raise ValueError("archive contains an unsafe member path")
            if not any(
                name.startswith("KadokaTools/") and not name.endswith("/") for name in names
            ):
                raise ValueError("archive does not contain the KadokaTools distribution root")
    except (BadZipFile, OSError, RuntimeError) as error:
        raise ValueError("release archive cannot be read") from error
    return archive, checksum


# {
#   責務: [sha256_file: artifact bytesをchunked SHA-256 digestへ変換する]
#   処理: [1: fileをchunkで読む 2: stable lowercase hex digestを返す]
#   引数: [path: file to hash]
#   戻り値: [digest: SHA-256 hex]
# }
def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


# {
#   責務: [_distribution_entries: symlink/special fileを拒否してsorted relative entriesを作る]
#   処理: [1: source treeをsortする 2: regular files/directoriesだけを返す]
#   引数: [source: resolved distribution directory]
#   戻り値: [entries: (source path, archive path) tuple]
# }
def _distribution_entries(source: Path) -> tuple[tuple[Path, str], ...]:
    entries = []
    for path in sorted(source.rglob("*"), key=lambda item: item.relative_to(source).as_posix()):
        metadata = path.lstat()
        if stat.S_ISLNK(metadata.st_mode):
            raise ValueError(f"distribution contains a symlink: {path.relative_to(source)}")
        if not (stat.S_ISDIR(metadata.st_mode) or stat.S_ISREG(metadata.st_mode)):
            raise ValueError(f"distribution contains a special file: {path.relative_to(source)}")
        relative = path.relative_to(source).as_posix()
        archive_name = f"KadokaTools/{relative}" + ("/" if path.is_dir() else "")
        entries.append((path, archive_name))
    return tuple(entries)


# {
#   責務: [_safe_archive_name: untrusted ZIP member nameをrelative safe pathとして検証する]
#   処理: [1: POSIX path componentsを解析する 2: absolute/dotdot/drive風pathを拒否する]
#   引数: [name: zip member path]
#   戻り値: [safe: safe relative path flag]
# }
def _safe_archive_name(name: str) -> bool:
    path = PurePosixPath(name)
    return (
        bool(path.parts)
        and not path.is_absolute()
        and "\\" not in name
        and ":" not in name
        and all(part not in {"", ".", ".."} for part in path.parts)
    )


# {
#   責務: [_atomic_write: checksum manifestをfsync後atomic replaceする]
#   処理: [1: sibling temp fileへwrite/flushする 2: fsync後destinationへreplaceする]
#   引数: [destination: final path, data: small checksum bytes]
#   戻り値: []
# }
def _atomic_write(destination: Path, data: bytes) -> None:
    descriptor, name = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent
    )
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        Path(name).replace(destination)
    except Exception:
        Path(name).unlink(missing_ok=True)
        raise


# {
#   責務: [main: package/verify CLI operationをdispatchする]
#   処理: [1: source/output or --verifyをparseする 2: artifact operationを実行する 3: result pathを表示する]
#   引数: [argv: optional command arguments]
#   戻り値: [code: exit status]
# }
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Package or verify the final Windows onedir artifact"
    )
    parser.add_argument("source_dir", type=Path, nargs="?")
    parser.add_argument("output_dir", type=Path, nargs="?")
    parser.add_argument("--verify", type=Path, metavar="OUTPUT_DIR")
    arguments = parser.parse_args(argv)
    try:
        paths = (
            verify_distribution(arguments.verify)
            if arguments.verify is not None
            else package_distribution(arguments.source_dir, arguments.output_dir)
        )
    except (OSError, TypeError, ValueError) as error:
        parser.error(str(error))
    for path in paths:
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
