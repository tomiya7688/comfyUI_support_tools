"""Local, append-only, non-destructive erase operation history."""

import hashlib
import json
import os
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from uuid import uuid4

from PIL import Image

from comfyui_support_tools.shared.output_artifact import ConflictPolicy, atomic_write_bytes
from comfyui_support_tools.shared.semantic_erase.contracts import (
    RLEMask,
    SemanticEraseTarget,
)

MAX_HISTORY_ENTRIES = 10_000
MAX_HISTORY_BYTES = 64 * 1024 * 1024


# {
# 責務: [EraseHistoryEntry: 1操作のsource/candidate/mask情報を表現する]
# フィールド: [operation_id,target policy,source hash,output,mask,backend,acceptance]
# }
@dataclass(frozen=True)
class EraseHistoryEntry:
    operation_id: str
    query: str
    source_sha256: str
    source_name: str
    output_name: str
    mask: RLEMask
    backend_id: str
    accepted: bool
    target_type: str = "object"
    match_policy: str = "review"
    fill_policy: str = "auto"
    fill_instruction: str | None = None
    preserve_rules: tuple[str, ...] = ()
    confidence_threshold: float = 0.65
    normalized_tag: str | None = None
    provider_query: str | None = None
    range_label: str | None = None
    replay_mask: RLEMask | None = None
    quality_profile: str = "standard"


# {
# 責務: [EraseHistoryStore: local operation artifactsをappend-onlyで管理する]
# フィールド: [root: history directory, manifest_path: versioned index]
# 補足: [undo/redoはactive pointerを変更し、image artifactを削除しない]
# }
class EraseHistoryStore:
    # {
    # 責務: [__init__: history directoryを検証しversioned manifestを準備する]
    # 処理: [1: path/symlinkを検証する, 2: owner-only directoryを作る, 3: manifestを読む]
    # 引数: [root: history directory]
    # 戻り値: []
    # エラー: [ValueError: rootがsymlinkまたはfileの場合]
    # }
    def __init__(self, root: str | Path):
        self.root = Path(root).expanduser().absolute()
        if self.root.is_symlink():
            raise ValueError("history root must not be a symbolic link")
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.manifest_path = self.root / "history.json"
        if self.manifest_path.is_symlink():
            raise ValueError("history manifest must not be a symbolic link")
        if not self.manifest_path.exists():
            self._save(
                {
                    "schema_version": 2,
                    "entries": [],
                    "branches": {"main": []},
                    "active_branch": "main",
                    "active_index": -1,
                }
            )
        self._load()

    # {
    # 責務: [record: inpaint candidateとmaskを新しい履歴entryへ保存する]
    # 処理: [1: source hashを計算する, 2: output imageをatomic保存する, 3: manifestへentryをappendする]
    # 引数: [source_path: original input, target: semantic request, output: candidate image, mask: edited mask, backend_id: producer]
    # 戻り値: [entry: persistent operation record]
    # エラー: [OSError: artifact保存に失敗した場合]
    # }
    def record(
        self,
        source_path: str | Path,
        target: SemanticEraseTarget,
        output: Image.Image,
        mask: RLEMask,
        backend_id: str,
        accepted: bool,
        replay_mask: RLEMask | None = None,
        quality_profile: str = "standard",
    ) -> EraseHistoryEntry:
        source = Path(source_path)
        if source.is_symlink() or not source.is_file():
            raise ValueError("erase history source must be a regular file")
        operation_id = uuid4().hex
        output_name = f"{source.stem}.semantic-erase.{operation_id}.png"
        output_path = self.root / output_name
        with tempfile.NamedTemporaryFile(
            dir=self.root, prefix=".erase-", suffix=".png", delete=False
        ) as staged:
            staged_path = Path(staged.name)
        try:
            output.convert("RGB").save(staged_path, format="PNG")
            data = staged_path.read_bytes()
            staged_path.unlink(missing_ok=True)
            atomic_write_bytes(output_path, data, policy=ConflictPolicy.FAIL)
        finally:
            staged_path.unlink(missing_ok=True)
        entry = EraseHistoryEntry(
            operation_id=operation_id,
            query=target.query,
            target_type=target.target_type.value,
            match_policy=target.match_policy.value,
            fill_policy=target.fill_policy.value,
            fill_instruction=target.fill_instruction,
            preserve_rules=target.preserve_rules,
            confidence_threshold=target.confidence_threshold,
            normalized_tag=target.normalized_tag,
            provider_query=target.provider_query,
            range_label=target.range_label,
            replay_mask=replay_mask,
            quality_profile=quality_profile,
            source_sha256=source_sha256(source),
            source_name=source.name,
            output_name=output_name,
            mask=mask,
            backend_id=backend_id,
            accepted=accepted,
        )
        manifest = self._load()
        entries = manifest["entries"]
        entries.append(_serialize_entry(entry))
        branch_id = manifest["active_branch"]
        operation_ids = manifest["branches"][branch_id]
        active_index = manifest["active_index"]
        if active_index < len(operation_ids) - 1:
            branch_id = f"branch-{uuid4().hex}"
            manifest["branches"][branch_id] = operation_ids[: active_index + 1]
            manifest["active_branch"] = branch_id
            operation_ids = manifest["branches"][branch_id]
        operation_ids.append(operation_id)
        manifest["active_index"] = len(operation_ids) - 1
        self._save(manifest)
        return entry

    # {
    # 責務: [undo: active operation pointerを一段前へ戻す]
    # 処理: [1: manifestを読む, 2: active pointerを更新する]
    # 引数: [self: history]
    # 戻り値: [active_path: 現在activeなoutput pathまたはNone]
    # }
    def undo(self) -> Path | None:
        manifest = self._load()
        manifest["active_index"] = max(-1, int(manifest["active_index"]) - 1)
        self._save(manifest)
        return self.active_output()

    # {
    # 責務: [redo: active operation pointerを一段先へ進める]
    # 処理: [1: manifestを読む, 2: next operationがあればpointerを進める]
    # 引数: [self: history]
    # 戻り値: [active_path: 現在activeなoutput pathまたはNone]
    # }
    def redo(self) -> Path | None:
        manifest = self._load()
        next_index = int(manifest["active_index"]) + 1
        branch = manifest["branches"][manifest["active_branch"]]
        if next_index < len(branch):
            manifest["active_index"] = next_index
            self._save(manifest)
        return self.active_output()

    # {
    # 責務: [switch_branch: preserved operation timeline branchへ切替える]
    # 処理: [1: branch IDを確認する, 2: branch末尾をactiveにする]
    # 引数: [self: history, branch_id: existing timeline ID]
    # 戻り値: [active_path: switched branch output]
    # エラー: [ValueError: branch IDが見つからない場合]
    # }
    def switch_branch(self, branch_id: str) -> Path | None:
        manifest = self._load()
        if branch_id not in manifest["branches"]:
            raise ValueError("history branch does not exist")
        manifest["active_branch"] = branch_id
        manifest["active_index"] = len(manifest["branches"][branch_id]) - 1
        self._save(manifest)
        return self.active_output()

    # {
    # 責務: [branch_ids: 保存済みtimeline branch ID一覧を返す]
    # 処理: [1: manifestを読み, 2: stable sortでIDを返す]
    # 引数: [self: history]
    # 戻り値: [branch_ids: immutable ID tuple]
    # }
    def branch_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._load()["branches"]))

    # {
    # 責務: [get_entry: operation IDからimmutable replay recordを取り出す]
    # 処理: [1: manifest entriesを検索する, 2: RLE maskを復元してrecordを返す]
    # 引数: [self: history, operation_id: requested operation]
    # 戻り値: [entry: replay metadata]
    # エラー: [KeyError: operation IDがhistoryに存在しない場合]
    # }
    def get_entry(self, operation_id: str) -> EraseHistoryEntry:
        manifest = self._load()
        payload = next(
            (item for item in manifest["entries"] if item["operation_id"] == operation_id), None
        )
        if payload is None:
            raise KeyError("history operation does not exist")
        mask_payload = payload["mask"]
        replay_payload = payload.get("replay_mask")
        replay_mask = (
            RLEMask(
                replay_payload["width"],
                replay_payload["height"],
                tuple(tuple(run) for run in replay_payload["runs"]),
            )
            if replay_payload
            else None
        )
        return EraseHistoryEntry(
            **{
                **payload,
                "mask": RLEMask(
                    mask_payload["width"],
                    mask_payload["height"],
                    tuple(tuple(run) for run in mask_payload["runs"]),
                ),
                "replay_mask": replay_mask,
                "preserve_rules": tuple(payload.get("preserve_rules", ())),
            }
        )

    # {
    # 責務: [active_output: active pointerが参照するartifact pathを返す]
    # 処理: [1: manifestを検証する, 2: artifact pathがregular fileなら返す]
    # 引数: [self: history]
    # 戻り値: [path: active output pathまたはNone]
    # }
    def active_output(self) -> Path | None:
        manifest = self._load()
        index = int(manifest["active_index"])
        if index < 0:
            return None
        operation_id = manifest["branches"][manifest["active_branch"]][index]
        entry = next(item for item in manifest["entries"] if item["operation_id"] == operation_id)
        name = entry["output_name"]
        path = self.root / name
        if path.parent != self.root or path.is_symlink() or not path.is_file():
            raise ValueError("history output artifact is missing or unsafe")
        return path

    # {
    # 責務: [_load: schema version付きhistory manifestを安全に読む]
    # 処理: [1: manifestをdecodeする, 2: schema/index/artifact nameを検証する]
    # 引数: [self: history]
    # 戻り値: [manifest: validated mutable data]
    # エラー: [ValueError: manifestが破損または不正の場合]
    # }
    def _load(self) -> dict:
        if self.manifest_path.is_symlink() or not self.manifest_path.is_file():
            raise ValueError("history manifest is missing or unsafe")
        if self.manifest_path.stat().st_size > MAX_HISTORY_BYTES:
            raise ValueError("history manifest exceeds the size safety limit")
        try:
            manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError("history manifest could not be read") from exc
        if manifest.get("schema_version") == 1:
            entries = manifest.get("entries", [])
            branch = [entry.get("operation_id") for entry in entries]
            manifest = {
                "schema_version": 2,
                "entries": entries,
                "branches": {"main": branch},
                "active_branch": "main",
                "active_index": min(int(manifest.get("active_index", -1)), len(branch) - 1),
            }
            self._save(manifest)
        if (
            manifest.get("schema_version") != 2
            or not isinstance(manifest.get("entries"), list)
            or not isinstance(manifest.get("branches"), dict)
        ):
            raise ValueError("unsupported history manifest schema")
        if len(manifest["entries"]) > MAX_HISTORY_ENTRIES:
            raise ValueError("history contains too many operations")
        operation_ids = set()
        for entry in manifest["entries"]:
            if not isinstance(entry, dict) or not isinstance(entry.get("operation_id"), str):
                raise ValueError("history entry is invalid")
            if entry["operation_id"] in operation_ids:
                raise ValueError("history operation IDs must be unique")
            operation_ids.add(entry["operation_id"])
        for branch in manifest["branches"].values():
            if not isinstance(branch, list) or any(item not in operation_ids for item in branch):
                raise ValueError("history branch references an unknown operation")
        branch_id = manifest.get("active_branch")
        if not isinstance(branch_id, str) or branch_id not in manifest["branches"]:
            raise ValueError("history active branch is invalid")
        index = manifest.get("active_index")
        branch_length = len(manifest["branches"][branch_id])
        if isinstance(index, bool) or not isinstance(index, int) or not -1 <= index < branch_length:
            raise ValueError("history active index is invalid")
        for entry in manifest["entries"]:
            name = entry.get("output_name", "")
            if not name or Path(name).name != name:
                raise ValueError("history contains an unsafe output name")
        return manifest

    # {
    # 責務: [_save: history manifestをatomic・owner-onlyで保存する]
    # 処理: [1: JSONをencodeする, 2: safe atomic writeを行う, 3: permissionを制限する]
    # 引数: [self: history, manifest: serializable index]
    # 戻り値: []
    # }
    def _save(self, manifest: dict) -> None:
        payload = json.dumps(manifest, ensure_ascii=False, indent=2, allow_nan=False).encode(
            "utf-8"
        )
        atomic_write_bytes(self.manifest_path, payload, policy=ConflictPolicy.OVERWRITE)
        try:
            os.chmod(self.root, 0o700)
            os.chmod(self.manifest_path, 0o600)
        except OSError:
            # Windows ACLs are managed by the account security descriptor.
            pass


# {
# 責務: [_serialize_entry: dataclass entryをschema-stable JSONへ変換する]
# 処理: [1: mask RLEとscalar metadataをJSON valueへ変換する]
# 引数: [entry: erase history entry]
# 戻り値: [payload: JSON object]
# }
def _serialize_entry(entry: EraseHistoryEntry) -> dict:
    payload = asdict(entry)
    payload["mask"]["runs"] = [list(run) for run in entry.mask.runs]
    return payload


# {
# 責務: [source_sha256: source assetをstreamingでhashする]
# 処理: [1: fileをbinary streamで開く, 2: SHA256 digestを返す]
# 引数: [path: regular source asset]
# 戻り値: [digest: lower-case hex SHA256]
# エラー: [OSError: sourceを読めない場合]
# }
def source_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
