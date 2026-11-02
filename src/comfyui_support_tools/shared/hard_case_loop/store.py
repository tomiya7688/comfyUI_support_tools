"""Append-oriented SQLite storage for local Touka hard-case records."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path

from .contracts import HardCaseRecord


# {
#   責務: [HardCaseStore: local-only SQLite record storeを提供する]
#   フィールド: [database path]
#   処理: [persist versioned metadata without copying source image/video bytes]
# }
class HardCaseStore:
    # {
    #   責務: [__init__: database fileをprepareする]
    #   処理: [create one versioned table and keep all data on the caller-selected local path]
    #   引数: [database_path: local SQLite file path]
    #   戻り値: []
    # }
    def __init__(self, database_path: Path) -> None:
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connection() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS hard_cases (
                    record_id TEXT PRIMARY KEY,
                    dataset_id TEXT NOT NULL,
                    in_regression_set INTEGER NOT NULL,
                    payload TEXT NOT NULL
                )
                """
            )
            connection.execute("PRAGMA user_version = 1")

    # {
    #   責務: [save: one immutable failure recordをlocal storeへ追加する]
    #   処理: [reject duplicate IDs rather than silently rewriting evaluation history]
    #   引数: [record: validated local hard-case record]
    #   戻り値: []
    #   エラー: [sqlite3.IntegrityError: duplicate record ID]
    # }
    def save(self, record: HardCaseRecord) -> None:
        with self._connection() as connection:
            connection.execute(
                "INSERT INTO hard_cases VALUES (?, ?, ?, ?)",
                (
                    record.record_id,
                    record.dataset_id,
                    int(record.in_regression_set),
                    json.dumps(record.to_document(), ensure_ascii=False, sort_keys=True),
                ),
            )

    # {
    #   責務: [get: record IDからpersisted entryを読み込む]
    #   処理: [decode JSON and revalidate nested schema]
    #   引数: [record_id: stable local ID]
    #   戻り値: [HardCaseRecord | None: stored entry]
    # }
    def get(self, record_id: str) -> HardCaseRecord | None:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT payload FROM hard_cases WHERE record_id = ?", (record_id,)
            ).fetchone()
        return HardCaseRecord.from_document(json.loads(row[0])) if row else None

    # {
    #   責務: [list_records: dataset / regression scopeでrecordを列挙する]
    #   処理: [sort stably by record ID for repeatable selection and export]
    #   引数: [dataset_id: optional dataset filter, regression_only: include fixed-set records only]
    #   戻り値: [tuple[HardCaseRecord, ...]: validated local records]
    # }
    def list_records(
        self, dataset_id: str | None = None, regression_only: bool = False
    ) -> tuple[HardCaseRecord, ...]:
        query = "SELECT payload FROM hard_cases WHERE 1=1"
        parameters: list[object] = []
        if dataset_id is not None:
            query += " AND dataset_id = ?"
            parameters.append(dataset_id)
        if regression_only:
            query += " AND in_regression_set = 1"
        query += " ORDER BY record_id"
        with self._connection() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return tuple(HardCaseRecord.from_document(json.loads(row[0])) for row in rows)

    # {
    #   責務: [record_feedback: user preference / rejectionをrecordへ追加する]
    #   処理: [validate candidate IDs, mark feedback explicit, and retain other metadata]
    #   引数: [record_id: target entry, preferred_candidate: optional preferred candidate, rejected_candidates: user-rejected candidates]
    #   戻り値: [HardCaseRecord: updated validated record]
    #   エラー: [KeyError: record missing]
    # }
    def record_feedback(
        self,
        record_id: str,
        preferred_candidate: str = "",
        rejected_candidates: tuple[str, ...] = (),
    ) -> HardCaseRecord:
        current = self.get(record_id)
        if current is None:
            raise KeyError(record_id)
        updated = replace(
            current,
            user_preferred_candidate=preferred_candidate,
            rejected_candidates=tuple(rejected_candidates),
            feedback_received=True,
        )
        with self._connection() as connection:
            connection.execute(
                "UPDATE hard_cases SET payload = ? WHERE record_id = ?",
                (json.dumps(updated.to_document(), ensure_ascii=False, sort_keys=True), record_id),
            )
        return updated

    # {
    #   責務: [set_regression_membership: recordをfixed regression setへ追加 / 除外する]
    #   処理: [update only set membership while preserving evaluation data]
    #   引数: [record_id: local case ID, included: desired membership]
    #   戻り値: []
    #   エラー: [KeyError: record missing]
    # }
    def set_regression_membership(self, record_id: str, included: bool) -> None:
        if not isinstance(included, bool):
            raise ValueError("included must be boolean")
        current = self.get(record_id)
        if current is None:
            raise KeyError(record_id)
        updated = replace(current, in_regression_set=included)
        with self._connection() as connection:
            connection.execute(
                "UPDATE hard_cases SET in_regression_set = ?, payload = ? WHERE record_id = ?",
                (
                    int(updated.in_regression_set),
                    json.dumps(updated.to_document(), ensure_ascii=False, sort_keys=True),
                    record_id,
                ),
            )

    # {
    #   責務: [_connection: database connection scopeを作る]
    #   処理: [use explicit local path and bounded timeout]
    #   引数: [self: store]
    #   戻り値: [sqlite3.Connection: context-managed connection]
    # }
    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database_path, timeout=5.0)
        try:
            with connection:
                yield connection
        finally:
            connection.close()
