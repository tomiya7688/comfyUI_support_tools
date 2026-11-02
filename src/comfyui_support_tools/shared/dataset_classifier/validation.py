"""Safe identifiers and labels shared by dataset classification services."""

from __future__ import annotations


# {
# 責務: [_valid_identifier: validate axis and adapter identifiers]
# 処理: [allow short portable alphanumeric underscore/hyphen values]
# 引数: [value: candidate identifier]
# 戻り値: [bool: identifier is safe]
# }
def _valid_identifier(value):
    return (
        isinstance(value, str)
        and 1 <= len(value) <= 64
        and value[0].isalnum()
        and all(char.isalnum() or char in "_-" for char in value)
    )


# {
# 責務: [_safe_label: bound and validate a label before manifest or path use]
# 処理: [reject empty strings and control characters]
# 引数: [label: candidate classification label]
# 戻り値: [bool: label is acceptable]
# }
def _safe_label(label):
    return (
        isinstance(label, str)
        and 1 <= len(label.strip()) <= 256
        and not any(ord(char) < 32 for char in label)
    )
