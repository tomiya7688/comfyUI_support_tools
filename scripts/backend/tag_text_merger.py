from __future__ import annotations

from pathlib import Path


# {
#   責務: [TagTextMerger: folder直下のTXT tagsを既存outputへmergeする]
#   処理: [optional normalized deduplicationを行い、files/added/skipped countsを返す]
#   フィールド: [stateless text merge operations]
# }
class TagTextMerger:
    """Merge text files while optionally retaining only the first occurrence of each tag."""

    # {
    #   責務: [_key: tagをdeduplication comparison keyへnormalizeする]
    #   処理: [casefold, underscore conversion, and whitespace collapseを行う]
    #   引数: [tag]
    #   戻り値: [str]
    # }
    @staticmethod
    def _key(tag: str) -> str:
        return " ".join(tag.strip().casefold().replace("_", " ").split())

    # {
    #   責務: [_tags: text contentをcomma/newline separated tagsへparseする]
    #   処理: [empty trimmed tokensを除外する]
    #   引数: [text]
    #   戻り値: [list[str]]
    # }
    @staticmethod
    def _tags(text: str) -> list[str]:
        return [tag.strip() for tag in text.replace("\n", ",").split(",") if tag.strip()]

    # {
    #   責務: [merge: folder内のTXT filesを順序固定でoutputへ追記する]
    #   処理: [destination itselfをskipし、必要なら既存内容も含めてduplicate tagsをskipする]
    #   引数: [folder, output, deduplicate]
    #   戻り値: [dict[str, int]]
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
