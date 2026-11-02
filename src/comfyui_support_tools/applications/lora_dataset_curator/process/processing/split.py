"""Duplicate grouping, attribute-aware group splitting, and bounded sample weights."""

from __future__ import annotations

import hashlib
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from comfyui_support_tools.shared.contracts.dataset_curator import (
    EmbeddingSimilarityProvider,
    ImageFeatures,
)

MAX_DUPLICATE_COMPARISONS = 5_000_000
EMBEDDING_DUPLICATE_THRESHOLD = 0.94


# {
# 責務: [_HashNode: index images by Hamming-distance edges]
# フィールド: [value: perceptual hash, indexes: images with the same hash, children: edge-distance subtrees]
# 処理: [support bounded BK-tree candidate search without materializing all image pairs]
# }
@dataclass
class _HashNode:
    value: int
    representatives: dict[str, int] = field(default_factory=dict)
    children: dict[int, _HashNode] = field(default_factory=dict)


# {
# 責務: [_hamming: count differing bits in two perceptual hashes]
# 処理: [parse hexadecimal image signatures and count xor bits]
# 引数: [first: first perceptual hash, second: second perceptual hash]
# 戻り値: [int: differing bit count]
# }
def _hamming(first: str, second: str) -> int:
    return (int(first, 16) ^ int(second, 16)).bit_count()


# {
# 責務: [_hash_candidates: find existing perceptual hashes within an edit radius]
# 処理: [walk only BK-tree branches compatible with the Hamming metric and enforce a shared comparison budget]
# 引数: [root: current tree, value: query hash, radius: allowed Hamming distance, comparisons: mutable bounded work counter]
# 戻り値: [tuple[int, ...]: candidate input indexes]
# エラー: [ValueError: perceptual index work exceeds the safe budget]
# }
def _hash_candidates(
    root: _HashNode, value: int, radius: int, comparisons: list[int]
) -> tuple[int, ...]:
    matches = []
    pending = [root]
    while pending:
        node = pending.pop()
        distance = (value ^ node.value).bit_count()
        comparisons[0] += 1
        if comparisons[0] > MAX_DUPLICATE_COMPARISONS:
            raise ValueError(
                "dataset near-duplicate index exceeds the five-million comparison budget"
            )
        if distance <= radius:
            matches.extend(node.representatives.values())
        pending.extend(
            child
            for edge, child in node.children.items()
            if distance - radius <= edge <= distance + radius
        )
    return tuple(matches)


# {
# 責務: [_insert_hash: add one image hash to the BK-tree]
# 処理: [follow Hamming-distance edges and retain equal perceptual hashes in one node]
# 引数: [root: current tree root, value: perceptual hash, index: image position, comparisons: bounded work counter]
# 戻り値: [_HashNode: updated root]
# エラー: [ValueError: perceptual index work exceeds the safe budget]
# }
def _insert_hash(
    root: _HashNode | None, value: int, index: int, digest: str, comparisons: list[int]
) -> _HashNode:
    if root is None:
        return _HashNode(value, {digest: index})
    node = root
    while True:
        distance = (value ^ node.value).bit_count()
        comparisons[0] += 1
        if comparisons[0] > MAX_DUPLICATE_COMPARISONS:
            raise ValueError(
                "dataset near-duplicate index exceeds the five-million comparison budget"
            )
        if distance == 0:
            node.representatives.setdefault(digest, index)
            return root
        child = node.children.get(distance)
        if child is None:
            node.children[distance] = _HashNode(value, {digest: index})
            return root
        node = child


# {
# 責務: [group_duplicates: join exact and near-duplicate images into split-safe groups]
# 処理: [merge exact hashes, compare bounded perceptual candidates, optionally verify embeddings, and return stable group IDs]
# 引数: [features: image path to features, hamming_threshold: average-hash radius, embedding_provider: optional local similarity model]
# 戻り値: [dict[Path, tuple[str, str, int]]: group ID, duplicate kind and group size per image]
# エラー: [ValueError: pair comparison work exceeds the safe budget]
# }
def group_duplicates(
    features: dict[Path, ImageFeatures],
    hamming_threshold: int,
    embedding_provider: EmbeddingSimilarityProvider | None = None,
) -> dict[Path, tuple[str, str, int]]:
    paths = tuple(sorted(features, key=lambda path: path.as_posix().casefold()))
    parent = list(range(len(paths)))
    kinds: dict[tuple[int, int], str] = {}

    # {
    # 責務: [find: resolve a disjoint-set group root]
    # 処理: [follow and compress parent links]
    # 引数: [index: image position]
    # 戻り値: [int: representative index]
    # }
    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    # {
    # 責務: [union: merge two related image positions]
    # 処理: [join roots and preserve the strongest exact/near evidence]
    # 引数: [left: first image position, right: second image position, kind: exact or near duplicate]
    # 戻り値: [None: parent map updated]
    # }
    def union(left: int, right: int, kind: str) -> None:
        left_root, right_root = find(left), find(right)
        if left_root != right_root:
            parent[max(left_root, right_root)] = min(left_root, right_root)
        kinds[(min(left, right), max(left, right))] = kind

    exact: dict[str, int] = {}
    for index, path in enumerate(paths):
        digest = features[path].sha256
        if digest in exact:
            union(index, exact[digest], "exact")
        else:
            exact[digest] = index
    root = None
    comparisons = [0]
    radius = hamming_threshold + (8 if embedding_provider else 0)
    for right, path in enumerate(paths):
        right_feature = features[path]
        if root:
            candidates = _hash_candidates(
                root, int(right_feature.perceptual_hash, 16), radius, comparisons
            )
            for left in candidates:
                left_feature = features[paths[left]]
                if left_feature.sha256 == right_feature.sha256:
                    continue
                comparisons[0] += 1
                if comparisons[0] > MAX_DUPLICATE_COMPARISONS:
                    raise ValueError(
                        "dataset near-duplicate index exceeds the five-million comparison budget"
                    )
                distance = _hamming(left_feature.perceptual_hash, right_feature.perceptual_hash)
                near = distance <= hamming_threshold
                if not near and embedding_provider and distance <= radius:
                    similarity = embedding_provider.similarity(paths[left], path)
                    if not 0 <= similarity <= 1:
                        raise ValueError("embedding similarity must be normalized to 0..1")
                    near = similarity >= EMBEDDING_DUPLICATE_THRESHOLD
                if near:
                    union(left, right, "near")
        root = _insert_hash(
            root, int(right_feature.perceptual_hash, 16), right, right_feature.sha256, comparisons
        )
    groups: dict[int, list[int]] = {}
    for index in range(len(paths)):
        groups.setdefault(find(index), []).append(index)
    result = {}
    for members in groups.values():
        group_hash = hashlib.sha256(
            "\0".join(features[paths[index]].sha256 for index in members).encode()
        ).hexdigest()[:16]
        group_kind = "none"
        if len(members) > 1:
            kinds_in_group = {
                kinds.get((min(left, right), max(left, right)))
                for offset, left in enumerate(members)
                for right in members[offset + 1 :]
            }
            group_kind = "exact" if kinds_in_group == {"exact"} else "near"
        for index in members:
            result[paths[index]] = (group_hash, group_kind, len(members))
    return result


# {
# 責務: [split_by_duplicate_group: choose validation groups by rare attribute coverage]
# 処理: [prioritize rare attributes, use a seeded tie-break, preserve whole duplicate groups, and keep train nonempty]
# 引数: [groups: image duplicate assignments, attributes: per-image category labels, validation_ratio: target fraction, seed: deterministic ordering key]
# 戻り値: [dict[Path, str]: train/validation split per image]
# }
def split_by_duplicate_group(
    groups: dict[Path, tuple[str, str, int]],
    attributes: dict[Path, tuple[tuple[str, tuple[str, ...]], ...]],
    validation_ratio: float,
    seed: int,
) -> dict[Path, str]:
    paths = tuple(groups)
    if len(paths) < 2:
        return {path: "train" for path in paths}
    group_members: dict[str, list[Path]] = {}
    for path, (group, _, _) in groups.items():
        group_members.setdefault(group, []).append(path)
    if len(group_members) < 2:
        return {path: "train" for path in paths}
    group_labels: dict[str, set[tuple[str, str]]] = {}
    for path, (group_id, _, _) in groups.items():
        group_labels.setdefault(group_id, set()).update(
            (axis, label) for axis, labels in attributes.get(path, ()) for label in set(labels)
        )
    label_counts = Counter(label for labels in group_labels.values() for label in labels)
    target = min(len(paths) - 1, max(1, round(len(paths) * validation_ratio)))

    # {
    # 責務: [priority: rank a duplicate group for validation coverage]
    # 処理: [prefer groups containing globally rare user-visible attributes and break ties from the configured seed]
    # 引数: [group: stable duplicate group identifier]
    # 戻り値: [tuple[float, str]: rarity descending followed by stable tie key]
    # }
    def priority(group: str) -> tuple[float, str]:
        labels = group_labels[group]
        rarity = sum(1 / label_counts[label] for label in labels if label_counts[label]) / max(
            len(labels), 1
        )
        tie = hashlib.sha256(f"{seed}:{group}".encode()).hexdigest()
        return -rarity, tie

    ordered = sorted(group_members, key=priority)
    validation_groups = set()
    validation_count = 0
    for group in ordered:
        if len(group_members) - len(validation_groups) <= 1:
            break
        size = len(group_members[group])
        if validation_count and validation_count + size > target:
            continue
        validation_groups.add(group)
        validation_count += size
        if validation_count >= target:
            break
    if not validation_groups:
        validation_groups.add(ordered[0])
    return {
        path: "validation" if groups[path][0] in validation_groups else "train" for path in paths
    }


# {
# 責務: [sample_weights: balance duplicates and rare user-visible attributes]
# 処理: [divide duplicates, apply square-root rarity weights, honor manual weights, and cap oversampling]
# 引数: [groups: duplicate group evidence, attributes: category labels, maximum: weight ceiling, low_weight: images marked as low importance, overrides: manual weights]
# 戻り値: [dict[Path, float]: positive bounded trainer sample weights]
# }
def sample_weights(
    groups: dict[Path, tuple[str, str, int]],
    attributes: dict[Path, tuple[tuple[str, tuple[str, ...]], ...]],
    maximum: float,
    low_weight: set[Path],
    overrides: dict[Path, float],
) -> dict[Path, float]:
    group_labels: dict[str, set[tuple[str, str]]] = {}
    for path, (group_id, _, _) in groups.items():
        group_labels.setdefault(group_id, set()).update(
            (axis, label) for axis, labels in attributes.get(path, ()) for label in set(labels)
        )
    counts = Counter(label for labels in group_labels.values() for label in labels)
    max_count = max(counts.values(), default=1)
    result = {}
    for path, (_, _, duplicate_count) in groups.items():
        rarity = [
            math_sqrt(max_count / counts[(axis, label)])
            for axis, label in group_labels.get(groups[path][0], set())
            if counts[(axis, label)]
        ]
        if path in overrides:
            weight = overrides[path]
        else:
            weight = (sum(rarity) / len(rarity) if rarity else 1.0) / duplicate_count
            if path in low_weight:
                weight = min(weight, 0.25)
        result[path] = min(maximum, max(0.05, weight))
    return result


# {
# 責務: [math_sqrt: compute a dependency-free square root for rarity weights]
# 処理: [call the standard math implementation]
# 引数: [value: finite nonnegative rarity ratio]
# 戻り値: [float: square root]
# }
def math_sqrt(value: float) -> float:
    import math

    return math.sqrt(value)
