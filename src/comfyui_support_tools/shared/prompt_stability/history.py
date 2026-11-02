"""Privacy-preserving append-only prompt failure provenance."""

from __future__ import annotations

import hashlib
import json
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from .contracts import ContentMode


# {
# 責務: [PromptFailureRecord: 生成失敗から得た匿名化priorを記録する]
# フィールド: [prompt hash, mode/backend/model, failure, evaluator, repair outcome]
# 処理: [raw promptを保存せず再利用可能なprovenanceを持つ]
# }
@dataclass(frozen=True)
class PromptFailureRecord:
    prompt_features_hash: str
    content_mode: str
    backend: str
    model: str
    failure_types: tuple[str, ...]
    evaluator_scores: tuple[tuple[str, float], ...]
    repair_actions: tuple[str, ...]
    accepted: bool
    timestamp: float


# {
# 責務: [PromptFailureHistory: opt-in local historyをappend-only形式で管理する]
# フィールド: [JSONL path, process lock]
# 処理: [prompt本文を残さず障害patternを保存・照会する]
# }
class PromptFailureHistory:
    # {
    # 責務: [__init__: history locationを初期化する]
    # 処理: [1: local JSONL pathを設定する]
    # 引数: [self: history store, path: local file]
    # 戻り値: []
    # }
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._lock = threading.Lock()

    # {
    # 責務: [append: anonymized generation feedbackを追記する]
    # 処理: [1: normalized prompt feature hashを作る, 2: raw promptなしのJSONLをappendする]
    # 引数: [self: history store, prompt: source prompt, content_mode: mode, backend: backend ID, model: model ID, failure_types: evaluator failures, evaluator_scores: scores, repair_actions: actions, accepted: accepted status]
    # 戻り値: [PromptFailureRecord: appended record]
    # }
    def append(
        self,
        *,
        prompt: str,
        content_mode: ContentMode,
        backend: str,
        model: str,
        failure_types: tuple[str, ...],
        evaluator_scores: tuple[tuple[str, float], ...] = (),
        repair_actions: tuple[str, ...] = (),
        accepted: bool = False,
    ) -> PromptFailureRecord:
        normalized = " ".join(prompt.casefold().split())
        digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
        record = PromptFailureRecord(
            digest,
            content_mode.value,
            backend,
            model,
            failure_types,
            evaluator_scores,
            repair_actions,
            accepted,
            time.time(),
        )
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock, self.path.open("a", encoding="utf-8") as stream:
            stream.write(
                json.dumps(asdict(record), ensure_ascii=False, separators=(",", ":")) + "\n"
            )
        return record

    # {
    # 責務: [recent_failures: local historyからmatching model/modeのfailure typesを読む]
    # 処理: [1: JSONL recordを読み込む, 2: matching failuresを新しい順に制限して返す]
    # 引数: [self: history store, content_mode: requested mode, backend: backend ID, model: model ID, limit: maximum records]
    # 戻り値: [failure keys: recent failure types]
    # }
    def recent_failures(
        self, *, content_mode: ContentMode, backend: str, model: str, limit: int = 20
    ) -> tuple[str, ...]:
        if not self.path.exists() or limit <= 0:
            return ()
        matches: list[str] = []
        with self._lock, self.path.open(encoding="utf-8") as stream:
            for line in stream:
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if (
                    record.get("content_mode") == content_mode.value
                    and record.get("backend") == backend
                    and record.get("model") == model
                    and not record.get("accepted", False)
                ):
                    matches.extend(str(item) for item in record.get("failure_types", ()))
        return tuple(matches[-limit:])
