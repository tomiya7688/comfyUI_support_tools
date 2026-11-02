"""Bounded versioned cache policy for reusable expensive results."""

import hashlib
import json
import threading
from collections import OrderedDict
from collections.abc import Mapping


# {
#   責務: [BoundedVersionedCache: bounded LRU cacheとschema version key policyを提供する]
#   フィールド: [capacity、version、ordered entries、lock]
# }
class BoundedVersionedCache:
    # {
    #   責務: [__init__: bounded LRU cacheを初期化する]
    #   処理: [1: capacity/versionを検証する 2: ordered storageを作る]
    #   引数: [capacity: max entries, version: domain result schema version]
    #   戻り値: []
    # }
    def __init__(self, capacity: int, version: str):
        if type(capacity) is not int or capacity < 1 or not version.strip():
            raise ValueError("positive capacity and cache version are required")
        self.capacity = capacity
        self.version = version
        self._entries = OrderedDict()
        self._lock = threading.Lock()

    # {
    #   責務: [key: versionとcanonical inputsからstable cache keyを作る]
    #   処理: [1: JSON serializationをstable化する 2: version-bound SHA-256を返す]
    #   引数: [inputs: JSON-compatible key payload]
    #   戻り値: [key: digest]
    # }
    def key(self, inputs: Mapping) -> str:
        encoded = json.dumps(inputs, sort_keys=True, separators=(",", ":"), allow_nan=False)
        return hashlib.sha256(f"{self.version}:{encoded}".encode()).hexdigest()

    # {
    #   責務: [get: cache hitをLRU末尾へ移動して返す]
    #   処理: [1: lock下でentryを探す 2: hitならmark newest]
    #   引数: [key: cache key]
    #   戻り値: [value: cached object or None]
    # }
    def get(self, key: str):
        with self._lock:
            if key not in self._entries:
                return None
            self._entries.move_to_end(key)
            return self._entries[key]

    # {
    #   責務: [put: entryを保存してcapacity超過時にoldestをevictする]
    #   処理: [1: newest entryを格納する 2: capacityまでoldestを削除する]
    #   引数: [key: cache key, value: result]
    #   戻り値: [evicted: eviction count]
    # }
    def put(self, key: str, value) -> int:
        with self._lock:
            self._entries[key] = value
            self._entries.move_to_end(key)
            evicted = 0
            while len(self._entries) > self.capacity:
                self._entries.popitem(last=False)
                evicted += 1
            return evicted

    # {
    #   責務: [clear: cached resultsを全て削除する]
    #   処理: [1: lock下でentriesをclearする]
    #   引数: []
    #   戻り値: [cleared: removed entry count]
    # }
    def clear(self) -> int:
        with self._lock:
            count = len(self._entries)
            self._entries.clear()
            return count
