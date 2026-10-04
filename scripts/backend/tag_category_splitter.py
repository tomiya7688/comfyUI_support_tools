from __future__ import annotations

from pathlib import Path


# {
# 責務: [TagCategorySplitter: prompt tagを既知カテゴリへ分類してファイル分割する]
# フィールド: []
# 処理: [1: 各tagの意味に応じて分類する, 2: category別の出力ファイルを作る]
# }
class TagCategorySplitter:
    """タグ行を用途別カテゴリと複合カテゴリへ分けて書き出す。"""

    CATEGORIES = (
        "character", "pose", "clothes", "image_style", "background", "situation", "expression",
        "character_clothes", "pose_situation", "pose_situation_expression",
        "pose_situation_background_expression", "background_image_style",
    )
    _KEYWORDS = {
        "clothes": ("shirt", "t-shirt", "dress", "skirt", "pants", "shorts", "bra", "panties", "underwear", "jacket", "coat", "uniform", "sweater", "hoodie", "blouse", "sleeves", "socks", "shoes", "boots", "hat", "necklace", "ribbon", "bikini", "swimsuit", "clothes", "clothing", "衣", "服", "スカート", "シャツ"),
        "expression": ("smile", "laugh", "cry", "angry", "sad", "surprised", "blush", "embarrassed", "expression", "grin", "open mouth", "closed eyes", "winking", "wink", "涙", "笑"),
        "pose": ("standing", "sitting", "lying", "kneeling", "walking", "running", "jumping", "leaning", "arms", "hand", "leg", "feet", "pose", "from ", "looking at", "cowboy shot", "upper body", "full body", "profile", "背中", "座り", "立ち"),
        "background": ("background", "indoors", "outdoors", "room", "bedroom", "classroom", "street", "city", "forest", "beach", "sky", "sea", "mountain", "wall", "window", "floor", "furniture", "scenery", "landscape", "背景", "室内", "屋外"),
        "situation": ("night", "day", "sunset", "rain", "snow", "festival", "school", "bath", "pool", "bed", "office", "restaurant", "party", "date", "lighting", "weather", "夜", "雨", "雪"),
        "image_style": ("masterpiece", "best quality", "high quality", "quality", "detailed", "anime", "illustration", "realistic", "photorealistic", "style", "artist", "render", "watercolor", "sketch", "lineart", "8k", "4k", "美麗", "高品質"),
    }

    # {
    # 責務: [split_tags: 1行のcomma区切りtagを個別要素へ分ける]
    # 処理: [1: commaで分割する, 2: 前後空白と空要素を除く]
    # 引数: [line: tag一覧を含む1行]
    # 戻り値: [順序を維持したtag一覧]
    # }
    @staticmethod
    def split_tags(line: str) -> list[str]:
        return [tag.strip() for tag in line.split(",") if tag.strip()]

    # {
    # 責務: [classify: tag一覧をカテゴリ別に分類する]
    # 処理: [1: 空のcategory一覧を作る, 2: 各tagのカテゴリを判定する,
    # 3: character_clothes統合categoryも構成する]
    # 引数: [tags: 分類するtag一覧]
    # 戻り値: [カテゴリ名からtag一覧への対応]
    # }
    def classify(self, tags: list[str]) -> dict[str, list[str]]:
        groups = {category: [] for category in self.CATEGORIES[:7]}
        for tag in tags:
            category = self._category_for(tag)
            groups[category].append(tag)
        groups["character_clothes"] = [*groups["character"], *groups["clothes"]]
        groups["pose_situation"] = [*groups["pose"], *groups["situation"]]
        groups["pose_situation_expression"] = [*groups["pose_situation"], *groups["expression"]]
        groups["pose_situation_background_expression"] = [*groups["pose_situation_expression"], *groups["background"]]
        groups["background_image_style"] = [*groups["background"], *groups["image_style"]]
        return groups

    # {
    # 責務: [_category_for: 単一tagをキーワード規則で分類する]
    # 処理: [1: tag表記を正規化する, 2: categoryキーワードを照合し該当分類を返す]
    # 引数: [tag: 分類する単一tag]
    # 戻り値: [tagが属するcategory名]
    # }
    def _category_for(self, tag: str) -> str:
        normalized = tag.casefold().replace("_", " ")
        for category in ("clothes", "expression", "pose", "background", "situation", "image_style"):
            if any(keyword in normalized for keyword in self._KEYWORDS[category]):
                return category
        return "character"

    # {
    # 責務: [process_file: 1つのtag fileを読み、分類別ファイルへ出力する]
    # 処理: [1: 入力内の各行をtag分解する, 2: 行単位に分類して蓄積する,
    # 3: category別の出力を保存する]
    # 引数: [source: 入力tag file, input_root: 入力root、相対path計算用,
    # output_root: category出力directory]
    # 戻り値: [category名から出力pathへの対応]
    # }
    def process_file(self, source: Path, input_root: Path, output_root: Path) -> dict[str, Path]:
        relative = source.relative_to(input_root)
        category_lines = {category: [] for category in self.CATEGORIES}
        for line in source.read_text(encoding="utf-8").splitlines():
            groups = self.classify(self.split_tags(line))
            for category, tags in groups.items():
                category_lines[category].append(", ".join(tags))
        outputs = {}
        for category, lines in category_lines.items():
            target = output_root / category / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
            outputs[category] = target
        return outputs

    # {
    # 責務: [write_category_lines: category別tag行を各出力fileへ書き込む]
    # 処理: [1: categoryごとの出力先を作る, 2: 対応行をUTF-8で保存する]
    # 引数: [category_lines: category別tag行, output_root: 出力directory]
    # 戻り値: [category名から出力pathへの対応]
    # }
    def write_category_lines(self, category_lines: dict[str, list[str]], output_root: Path) -> dict[str, Path]:
        outputs = {}
        for category in self.CATEGORIES:
            target = output_root / f"{category}.txt"
            lines = category_lines.get(category, [])
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
            outputs[category] = target
        return outputs
