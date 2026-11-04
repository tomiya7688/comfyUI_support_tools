from dataclasses import dataclass


# {
#   責務: [PromptValidationResult: prompt解決requestの検証結果を保持する]
#   フィールド: [errors: 入力エラー, warnings: 未解決記法などの警告]
# }
@dataclass(frozen=True)
class PromptValidationResult:
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    # {
    #   責務: [is_valid: エラーがない状態を返す]
    #   処理: [errorsが空であることを確認する]
    #   引数: [self: 検証結果]
    #   戻り値: [bool: 検証成功状態]
    # }
    @property
    def is_valid(self) -> bool:
        return not self.errors
