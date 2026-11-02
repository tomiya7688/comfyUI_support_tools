from __future__ import annotations

import re
import secrets
from pathlib import Path


# {
#   責務: [TagReplacementEngine: TXT tag linesへexact normalized replacement rulesを適用する]
#   処理: [plain replacements and cached wildcard choicesを用い、processed filesをwriteする]
#   フィールド: [stateless replacement operations]
# }
class TagReplacementEngine:
    """TXTタグを完全一致規則で置換する。"""

    # {
    #   責務: [normalize: tag comparison用のcase and whitespace normalizationを行う]
    #   処理: [trim, casefold, spaces/underscoresをsingle spaceへ変換する]
    #   引数: [tag]
    #   戻り値: [str]
    # }
    @staticmethod
    def normalize(tag: str) -> str:
        return re.sub(r"[\s_]+", " ", tag.strip().casefold())

    # {
    #   責務: [split_tags: comma-separated lineをnon-empty trimmed tagsへ分割する]
    #   処理: [empty itemsをdropし順序を保つ]
    #   引数: [line]
    #   戻り値: [list[str]]
    # }
    @staticmethod
    def split_tags(line: str) -> list[str]:
        return [tag.strip() for tag in line.split(",") if tag.strip()]

    # {
    #   責務: [resolve_replacement: ruleからplain textまたはwildcard replacementを解決する]
    #   処理: [wildcard file entriesをreadし、path-based cache経由でrandom choiceを再利用する]
    #   引数: [rule, wildcard_cache]
    #   戻り値: [str]
    # }
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

    # {
    #   責務: [replace_line: one line内のexact matching tagsをrulesに従って置換する]
    #   処理: [normalized source keysをbuildし、unmatched tagsをpreserveする]
    #   引数: [line, rules, wildcard_cache]
    #   戻り値: [str]
    # }
    def replace_line(self, line: str, rules: list[dict], wildcard_cache: dict[str, str]) -> str:
        replacements = {
            self.normalize(str(rule.get("source", ""))): self.resolve_replacement(rule, wildcard_cache)
            for rule in rules if str(rule.get("source", "")).strip()
        }
        return ", ".join(replacements.get(self.normalize(tag), tag) for tag in self.split_tags(line))

    # {
    #   責務: [process_file: source fileのtag linesを置換してtargetへ書く]
    #   処理: [shared cacheを使い、parent directoryを作成してchanged line countを返す]
    #   引数: [source, target, rules, wildcard_cache]
    #   戻り値: [int]
    # }
    def process_file(self, source: Path, target: Path, rules: list[dict], wildcard_cache: dict[str, str] | None = None) -> int:
        cache = wildcard_cache if wildcard_cache is not None else {}
        source_lines = source.read_text(encoding="utf-8").splitlines()
        replaced_lines = [self.replace_line(line, rules, cache) for line in source_lines]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("\n".join(replaced_lines) + ("\n" if source_lines else ""), encoding="utf-8")
        return sum(old != new for old, new in zip(source_lines, replaced_lines))
