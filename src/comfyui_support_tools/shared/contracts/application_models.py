from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ApplicationConfig:
    name: str
    version: str


@dataclass(frozen=True)
class ApplicationStatus:
    name: str
    version: str
    ready: bool
