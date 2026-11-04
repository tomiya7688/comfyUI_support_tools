from __future__ import annotations


# {
#   責務: [validate_text_tuple: profileの文字列tupleが空値を含まないことを検証する]
#   処理: [tuple型と各要素の文字列/非空条件を検査する]
#   引数: [field_name: エラー表示用field名, values: 検証するtuple]
#   戻り値: []
#   エラー: [ValueError: tupleまたは要素がschema条件を満たさない場合]
# }
def validate_text_tuple(field_name: str, values: tuple[str, ...]) -> None:
    if not isinstance(values, tuple) or any(
        not isinstance(value, str) or not value.strip() for value in values
    ):
        raise ValueError(f"{field_name}は空でない文字列だけを含むtupleで指定してください")
