"""Boolean query evaluation over normalized dataset classifications."""

from __future__ import annotations

from pathlib import Path

from .contracts import ClassificationResult, DatasetQuery, QueryCondition, QueryGroup


# {
# 責務: [validate_query: reject unsafe or ambiguous dataset query trees]
# 処理: [validate root, action, axes, operators, confidence and nested group limits]
# 引数: [query: query model, max_depth: maximum nested boolean levels]
# 戻り値: [None: query is valid or ValueError]
# }
def validate_query(query: DatasetQuery, max_depth: int = 12) -> None:
    if query.action not in {"copy", "move", "manifest"}:
        raise ValueError("query action must be copy, move, or manifest")
    if len(set(query.axes)) != len(query.axes) or any(not _valid_axis(axis) for axis in query.axes):
        raise ValueError("query axes must be unique safe names")
    _validate_expression(query.expression, 0, max_depth)


# {
# 責務: [_validate_expression: recursively validate boolean expression nodes]
# 処理: [bound tree depth and predicate count; reject unknown axis/operator/value]
# 引数: [expression: condition or group, depth: current depth, max_depth: maximum depth]
# 戻り値: [None: expression is safe to evaluate or ValueError]
# }
def _validate_expression(expression, depth, max_depth):
    if depth > max_depth:
        raise ValueError("query expression exceeds maximum nesting")
    if isinstance(expression, QueryCondition):
        if (
            not _valid_axis(expression.axis)
            or expression.operator not in {"eq", "contains", "any", "none"}
            or not 0 <= expression.min_confidence <= 1
        ):
            raise ValueError("invalid query condition")
        values = (expression.value,) if isinstance(expression.value, str) else expression.value
        if (
            not isinstance(values, tuple)
            or not values
            or len(values) > 64
            or any(not isinstance(value, str) or not value.strip() for value in values)
        ):
            raise ValueError("query values must be non-empty strings")
        if expression.operator in {"eq", "contains"} and not isinstance(expression.value, str):
            raise ValueError("eq and contains require one string value")
        return
    if not isinstance(expression, QueryGroup) or expression.operator not in {"and", "or", "not"}:
        raise ValueError("query groups must use and, or, or not")
    if not expression.children or (expression.operator == "not" and len(expression.children) != 1):
        raise ValueError("query groups need children; not requires exactly one child")
    if len(expression.children) > 64:
        raise ValueError("query group has too many children")
    for child in expression.children:
        _validate_expression(child, depth + 1, max_depth)


# {
# 責務: [matches_query: evaluate an expression against one normalized image result]
# 処理: [apply label membership and minimum axis confidence with grouped boolean logic]
# 引数: [query: validated query tree, result: per-image classification]
# 戻り値: [bool: whether the image satisfies the expression]
# }
def matches_query(query: DatasetQuery, result: ClassificationResult) -> bool:
    validate_query(query)
    return _matches(query.expression, result)


# {
# 責務: [query_preset: build common dataset extraction queries]
# 処理: [compose character/situation/background/style and provenance preset predicates]
# 引数: [name: preset id, root: input dataset, values: axis labels, action: export action]
# 戻り値: [DatasetQuery: validated reusable query]
# }
def query_preset(name, root, values, action="manifest"):
    required = {
        "character_situation": ("character", "situation"),
        "character_background": ("character", "background"),
        "character_style": ("character", "style"),
        "real_only": ("ai_origin",),
        "sfw_real_character": ("character", "rating", "ai_origin"),
        "style_lora": ("style",),
        "background": ("background",),
    }
    if name not in required:
        raise ValueError(f"unknown dataset query preset: {name}")
    axes = required[name]
    conditions = []
    for axis in axes:
        label = values.get(axis)
        if axis == "ai_origin" and name in {"real_only", "sfw_real_character"} and label is None:
            label = "non_ai"
        if axis == "rating" and name == "sfw_real_character" and label is None:
            label = "sfw"
        if not isinstance(label, str) or not label.strip():
            raise ValueError(f"query preset {name} requires a {axis} label")
        conditions.append(QueryCondition(axis, "contains", label.strip()))
    expression = conditions[0] if len(conditions) == 1 else QueryGroup("and", tuple(conditions))
    query = DatasetQuery(Path(root), expression, axes, action)
    validate_query(query)
    return query


# {
# 責務: [_matches: evaluate validated predicates recursively]
# 処理: [short-circuit AND/OR and invert single NOT child]
# 引数: [expression: validated query node, result: per-image classification]
# 戻り値: [bool: expression result]
# }
def _matches(expression, result):
    if isinstance(expression, QueryCondition):
        labels = set(dict(result.labels).get(expression.axis, ()))
        confidence = dict(result.confidence).get(expression.axis, 0.0)
        if confidence < expression.min_confidence:
            return False
        if expression.operator == "eq":
            return labels == {expression.value}
        if expression.operator == "contains":
            return expression.value in labels
        requested = set(expression.value)
        if expression.operator == "any":
            return bool(labels & requested)
        return not bool(labels & requested)
    values = (_matches(child, result) for child in expression.children)
    if expression.operator == "and":
        return all(values)
    if expression.operator == "or":
        return any(values)
    return not next(values)


# {
# 責務: [_valid_axis: ensure axis names are safe manifest/query keys]
# 処理: [allow portable alphanumeric, underscore, and hyphen identifiers]
# 引数: [axis: candidate axis name]
# 戻り値: [bool: axis is a valid short identifier]
# }
def _valid_axis(axis):
    return (
        isinstance(axis, str)
        and 1 <= len(axis) <= 64
        and axis[0].isalnum()
        and all(char.isalnum() or char in "_-" for char in axis)
    )
