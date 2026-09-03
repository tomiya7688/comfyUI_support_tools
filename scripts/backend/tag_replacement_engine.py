from __future__ import annotations

import re
import secrets
from pathlib import Path


class TagReplacementEngine:
    """TXTタグを完全一致規則で置換する。"""

    @staticmethod
    def normalize(tag: str) -> str:
        return re.sub(r"[\s_]+", " ", tag.strip().casefold())

    @staticmethod
    def split_tags(line: str) -> list[str]:
        return [tag.strip() for tag in line.split(",") if tag.strip()]

    def resolve_replacement(self, rule: dict, wildcard_cache: dict[str, str]) -> str:
        if rule.get("mode") != "wildcard":
            return str(rule.get("replacement", "")).strip()
        path = Path(str(rule.get("replacement", "")).strip())
        key = str(path.resolve()).casefold()
        if key in wildcard_cache:
            return wildcard_cache[key]
        lines = path.read_text(encoding="utf-8").splitlines()
        choices = [line.strip() for line in lines if line.strip()]
        if not choices:
            raise ValueError(f"Wildcardに有効な行がありません: {path}")
        value = secrets.choice(choices)
        wildcard_cache[key] = value
        return value

    def replace_line(self, line: str, rules: list[dict], wildcard_cache: dict[str, str]) -> str:
        replacements = {
            self.normalize(str(rule.get("source", ""))): self.resolve_replacement(rule, wildcard_cache)
            for rule in rules if str(rule.get("source", "")).strip()
        }
        return ", ".join(replacements.get(self.normalize(tag), tag) for tag in self.split_tags(line))

    def process_file(self, source: Path, target: Path, rules: list[dict], wildcard_cache: dict[str, str] | None = None) -> int:
        cache = wildcard_cache if wildcard_cache is not None else {}
        source_lines = source.read_text(encoding="utf-8").splitlines()
        replaced_lines = [self.replace_line(line, rules, cache) for line in source_lines]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("\n".join(replaced_lines) + ("\n" if source_lines else ""), encoding="utf-8")
        return sum(old != new for old, new in zip(source_lines, replaced_lines))
