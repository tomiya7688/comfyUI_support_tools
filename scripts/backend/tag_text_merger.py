from __future__ import annotations

from pathlib import Path


# {
# 責務: [TagTextMerger: directory内のtag textを統合して重複を整理する]
# フィールド: []
# 処理: [1: 複数fileのtagを読み合わせる, 2: 要求に応じて重複を除いて出力する]
# }
class TagTextMerger:
    """Merge text files while optionally retaining only the first occurrence of each tag."""

    # {
    # 責務: [_key: tagを重複比較用のcanonical keyへ正規化する]
    # 処理: [1: 小文字化しunderscoreと連続spaceを標準化する]
    # 引数: [tag: 比較対象tag]
    # 戻り値: [canonical比較key]
    # }
    @staticmethod
    def _key(tag: str) -> str:
        return " ".join(tag.strip().casefold().replace("_", " ").split())

    # {
    # 責務: [_tags: 複数行またはcomma区切りtextからtag要素を抽出する]
    # 処理: [1: newlineをcomma区切りとして扱う, 2: 空要素を取り除く]
    # 引数: [text: tag text]
    # 戻り値: [前後空白を除いたtag一覧]
    # }
    @staticmethod
    def _tags(text: str) -> list[str]:
        return [tag.strip() for tag in text.replace("\n", ",").split(",") if tag.strip()]

    # {
    # 責務: [merge: folder内のtag fileを1つへ統合して保存する]
    # 処理: [1: source fileを列挙してtagを集める, 2: optionに応じて重複を除く,
    # 3: outputへ書き込み件数を返す]
    # 引数: [folder: 読み込むdirectory, output: 統合file出力先, deduplicate: 重複tagを除くか]
    # 戻り値: [入力・出力tag数などの集計]
    # }
    def merge(self, folder: str, output: str, deduplicate: bool) -> dict[str, int]:
        source = Path(folder)
        destination = Path(output)
        destination.parent.mkdir(parents=True, exist_ok=True)
        existing = destination.read_text(encoding="utf-8") if destination.is_file() else ""
        seen = {self._key(tag) for tag in self._tags(existing)} if deduplicate else set()
        lines: list[str] = []
        added = skipped = files = 0
        for path in sorted(source.glob("*.txt"), key=lambda item: item.name.casefold()):
            if path.resolve() == destination.resolve():
                continue
            files += 1
            tags: list[str] = []
            for tag in self._tags(path.read_text(encoding="utf-8")):
                key = self._key(tag)
                if deduplicate and key in seen:
                    skipped += 1
                    continue
                seen.add(key)
                tags.append(tag)
                added += 1
            if tags:
                lines.append(", ".join(tags))
        if not destination.exists():
            destination.write_text("", encoding="utf-8")
        if lines:
            prefix = "" if not existing or existing.endswith("\n") else "\n"
            with destination.open("a", encoding="utf-8") as target:
                target.write(prefix + "\n".join(lines) + "\n")
        return {"files": files, "added": added, "skipped": skipped}
