from __future__ import annotations

from dataclasses import dataclass


# {
# 責務: [ApplicationConfig: アプリケーション名と表示するversionを束ねる]
# フィールド: [name: アプリ名, version: アプリversion]
# }
@dataclass(frozen=True)
class ApplicationConfig:
    name: str
    version: str


# {
# 責務: [ApplicationStatus: アプリの識別情報と起動準備状態を表す]
# フィールド: [name: アプリ名, version: アプリversion, ready: 利用準備が整ったか]
# }
@dataclass(frozen=True)
class ApplicationStatus:
    name: str
    version: str
    ready: bool
