from __future__ import annotations

import re
import secrets
from pathlib import Path


# {
# 責務: [TagReplacementEngine: tag置換規則とwildcard展開を適用してfileを変換する]
# フィールド: []
# 処理: [1: tag名を正規化して規則照合する, 2: wildcard置換値をcacheし, 3: 出力fileを保存する]
# }
class TagReplacementEngine:
    """TXTタグを完全一致規則で置換する。"""

    # {
    # 責務: [normalize: tag文字列を規則照合用に正規化する]
    # 処理: [1: 小文字化し連続空白とunderscoreを単一spaceへ変換する]
    # 引数: [tag: 正規化するtag]
    # 戻り値: [比較用の正規化tag]
    # }
    @staticmethod
    def normalize(tag: str) -> str:
        return re.sub(r"[\s_]+", " ", tag.strip().casefold())

    # {
    # 責務: [split_tags: comma区切りの1行をtag一覧にする]
    # 処理: [1: commaで分割する, 2: 空要素を除く]
    # 引数: [line: comma区切りtag行]
    # 戻り値: [tag要素の一覧]
    # }
    @staticmethod
    def split_tags(line: str) -> list[str]:
        return [tag.strip() for tag in line.split(",") if tag.strip()]

    # {
    # 責務: [resolve_replacement: 置換ruleの固定値またはwildcard内容を解決する]
    # 処理: [1: 固定置換値を返す, 2: wildcard fileをcacheから再利用または展開する]
    # 引数: [rule: 置換設定, wildcard_cache: 展開済み値を保持するcache]
    # 戻り値: [rule適用後の置換tag文字列]
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
    # 責務: [replace_line: tag行に一致する置換ruleを適用する]
    # 処理: [1: ruleのsourceと置換値を準備する, 2: 各tagを照合し未一致tagを維持する]
    # 引数: [line: 置換対象tag行, rules: 置換rule一覧, wildcard_cache: wildcard値cache]
    # 戻り値: [置換後のcomma区切りtag行]
    # }
    def replace_line(self, line: str, rules: list[dict], wildcard_cache: dict[str, str]) -> str:
        replacements = {
            self.normalize(str(rule.get("source", ""))): self.resolve_replacement(rule, wildcard_cache)
            for rule in rules if str(rule.get("source", "")).strip()
        }
        return ", ".join(replacements.get(self.normalize(tag), tag) for tag in self.split_tags(line))

    # {
    # 責務: [process_file: tag file全体へ置換ruleを適用して保存する]
    # 処理: [1: 入力行を読む, 2: 行ごとに置換する, 3: 出力fileを書き込み件数を返す]
    # 引数: [source: 入力file, target: 出力file, rules: 置換rule一覧,
    # wildcard_cache: 呼び出し間で再利用する任意cache]
    # 戻り値: [置換処理した行数]
    # }
    def process_file(self, source: Path, target: Path, rules: list[dict], wildcard_cache: dict[str, str] | None = None) -> int:
        cache = wildcard_cache if wildcard_cache is not None else {}
        source_lines = source.read_text(encoding="utf-8").splitlines()
        replaced_lines = [self.replace_line(line, rules, cache) for line in source_lines]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("\n".join(replaced_lines) + ("\n" if source_lines else ""), encoding="utf-8")
        return sum(old != new for old, new in zip(source_lines, replaced_lines))
