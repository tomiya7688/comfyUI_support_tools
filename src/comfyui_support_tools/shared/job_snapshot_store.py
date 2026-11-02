"""Durable, backend-neutral persistence for shared Job snapshots."""

import json
from contextlib import closing
from pathlib import Path
import sqlite3

from comfyui_support_tools.shared.contracts.job_contracts import JobSnapshot


# {
#   責務: [JobSnapshotStore: immutable Job historyをSQLiteへdurable保存する]
#   フィールド: [SQLite database path]
#   処理: [bounded snapshot一式のatomic置換と再起動時の復元]
# }
class JobSnapshotStore:
    # {
    #   責務: [__init__: SQLite snapshot storeを初期化する]
    #   処理: [1: 保存先directoryを作成する 2: schemaを作成する]
    #   引数: [path: SQLite database file path]
    #   戻り値: []
    # }
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path)) as connection:
            with connection:
                connection.execute(
                    "CREATE TABLE IF NOT EXISTS job_snapshots "
                    "(job_id TEXT PRIMARY KEY, sequence INTEGER NOT NULL, payload TEXT NOT NULL)"
                )

    # {
    #   責務: [replace_all: bounded Job historyをtransaction内で全置換する]
    #   処理: [1: snapshotをJSON化する 2: transactionでtableを置換する]
    #   引数: [snapshots: 保存するJob snapshot列]
    #   戻り値: []
    # }
    def replace_all(self, snapshots: tuple[JobSnapshot, ...]) -> None:
        payloads = [
            (
                snapshot.id,
                index,
                json.dumps(snapshot.__dict__, ensure_ascii=False, allow_nan=False),
            )
            for index, snapshot in enumerate(snapshots)
        ]
        with closing(sqlite3.connect(self.path)) as connection:
            with connection:
                connection.execute("DELETE FROM job_snapshots")
                connection.executemany(
                    "INSERT INTO job_snapshots(job_id, sequence, payload) VALUES (?, ?, ?)",
                    payloads,
                )

    # {
    #   責務: [load: 保存済みJob snapshotをimmutable contractとして復元する]
    #   処理: [1: DBから保存順に読み込む 2: JSON配列をtupleへ変換する 3: dataclassを検証する]
    #   引数: []
    #   戻り値: [snapshots: 保存済みJob snapshot列]
    # }
    def load(self) -> tuple[JobSnapshot, ...]:
        with closing(sqlite3.connect(self.path)) as connection:
            rows = connection.execute(
                "SELECT payload FROM job_snapshots ORDER BY sequence"
            ).fetchall()
        tuple_fields = {
            "source_ids",
            "source_names",
            "logs",
            "completed_items",
            "pending_items",
            "failed_items",
            "artifact_refs",
        }
        snapshots = []
        for (payload,) in rows:
            values = json.loads(payload)
            for key in tuple_fields:
                values[key] = tuple(values.get(key, ()))
            snapshots.append(JobSnapshot(**values))
        return tuple(snapshots)
