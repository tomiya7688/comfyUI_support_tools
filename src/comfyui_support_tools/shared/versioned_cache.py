"""Bounded versioned cache policy for reusable expensive results."""

import hashlib
import json
import sys
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
    def __init__(
        self,
        capacity: int,
        version: str,
        *,
        max_size_bytes: int = 64 * 1024 * 1024,
        size_of=None,
    ):
        if (
            type(capacity) is not int
            or capacity < 1
            or not isinstance(version, str)
            or not version.strip()
            or type(max_size_bytes) is not int
            or max_size_bytes < 1
        ):
            raise ValueError("positive entry/byte capacities and cache version are required")
        if size_of is not None and not callable(size_of):
            raise ValueError("size_of must be callable")
        self.capacity = capacity
        self.version = version
        self.max_size_bytes = max_size_bytes
        self._size_of = size_of or _estimate_size
        self._size_bytes = 0
        self._entries = OrderedDict()
        self._lock = threading.Lock()

    # {
    #   責務: [key: versionとcanonical inputsからstable cache keyを作る]
    #   処理: [1: JSON serializationをstable化する 2: version-bound SHA-256を返す]
    #   引数: [inputs: JSON-compatible key payload]
    #   戻り値: [key: digest]
    # }
    def key(self, inputs: Mapping) -> str:
        try:
            encoded = json.dumps(inputs, sort_keys=True, separators=(",", ":"), allow_nan=False)
        except (TypeError, ValueError) as error:
            raise ValueError("cache key inputs must be finite JSON-compatible values") from error
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
            return self._entries[key][0]

    # {
    #   責務: [put: entryを保存してcapacity超過時にoldestをevictする]
    #   処理: [1: newest entryを格納する 2: capacityまでoldestを削除する]
    #   引数: [key: cache key, value: result]
    #   戻り値: [evicted: eviction count]
    # }
    def put(self, key: str, value) -> int:
        if not isinstance(key, str) or not key:
            raise ValueError("cache key must be a nonempty string")
        try:
            entry_size = self._size_of(value)
        except Exception as error:
            raise ValueError("cache value size could not be measured") from error
        if type(entry_size) is not int or entry_size < 0:
            raise ValueError("cache value size must be a nonnegative integer")
        if entry_size > self.max_size_bytes:
            raise ValueError("cache value exceeds max_size_bytes")
        with self._lock:
            previous = self._entries.pop(key, None)
            if previous is not None:
                self._size_bytes -= previous[1]
            self._entries[key] = (value, entry_size)
            self._size_bytes += entry_size
            self._entries.move_to_end(key)
            evicted = 0
            while len(self._entries) > self.capacity or self._size_bytes > self.max_size_bytes:
                _old_key, (_old_value, old_size) = self._entries.popitem(last=False)
                self._size_bytes -= old_size
                evicted += 1
            return evicted

    # {
    #   責務: [size_bytes: cacheに保持するpayloadの概算byte数を返す]
    #   処理: [1: lock下で現在のaggregate sizeを読む]
    #   引数: []
    #   戻り値: [size_bytes: retained size]
    # }
    @property
    def size_bytes(self) -> int:
        with self._lock:
            return self._size_bytes

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
            self._size_bytes = 0
            return count


# {
#   責務: [_estimate_size: Python valueのretained sizeを再帰的に概算する]
#   処理: [1: nbytesを優先する 2: object/container sizeをcycle-safeに加算する]
#   引数: [value: cache payload, seen: visited object IDs]
#   戻り値: [estimated_bytes: retained size estimate]
# }
def _estimate_size(value, seen=None) -> int:
    """Estimate retained object size, preferring an object's explicit nbytes."""
    seen = set() if seen is None else seen
    identity = id(value)
    if identity in seen:
        return 0
    seen.add(identity)
    explicit_size = getattr(value, "nbytes", None)
    if isinstance(explicit_size, int) and explicit_size >= 0:
        return explicit_size
    size = sys.getsizeof(value)
    if isinstance(value, Mapping):
        size += sum(
            _estimate_size(key, seen) + _estimate_size(item, seen) for key, item in value.items()
        )
    elif isinstance(value, (tuple, list, set, frozenset)):
        size += sum(_estimate_size(item, seen) for item in value)
    elif hasattr(value, "__dict__"):
        size += _estimate_size(vars(value), seen)
    return size
