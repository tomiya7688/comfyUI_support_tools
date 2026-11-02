"""Spatially varying, uncertainty-aware material and transmission estimates."""

from __future__ import annotations

import hashlib
import io
import math
from dataclasses import dataclass
from typing import Protocol

import cv2
import numpy as np
from PIL import Image


# {
#   責務: [SurfaceEstimate: estimated surface/transmission maps and uncertaintyを保持する]
#   フィールド: [encoded maps, scalar priors, material label, method and confidence]
#   処理: [keep map payloads immutable and serializable for candidate adapters]
# }
@dataclass(frozen=True, slots=True)
class SurfaceEstimate:
    estimate_id: str
    width: int
    height: int
    surface_color_map: bytes
    alpha_map: bytes
    transmittance_map: bytes
    shading_map: bytes
    blur_scatter_map: bytes
    texture_frequency_map: bytes
    specular_map: bytes
    wrinkle_confidence_map: bytes
    uncertainty_map: bytes
    material_category: str
    material: str
    scattering_strength: float
    confidence: float
    method: str = "classical_spatial_prior_v1"

    # {
    #   責務: [__post_init__: map payloads and normalized model metadataをvalidateする]
    #   処理: [require valid PNG bytes and finite bounded confidence values]
    #   引数: [self: immutable material estimate]
    #   戻り値: []
    # }
    def __post_init__(self) -> None:
        if not self.estimate_id.strip() or self.width < 1 or self.height < 1:
            raise ValueError("surface estimate requires an ID and positive dimensions")
        maps = (
            self.surface_color_map,
            self.alpha_map,
            self.transmittance_map,
            self.shading_map,
            self.blur_scatter_map,
            self.texture_frequency_map,
            self.specular_map,
            self.wrinkle_confidence_map,
            self.uncertainty_map,
        )
        if any(not isinstance(payload, bytes) or not payload for payload in maps):
            raise ValueError("surface estimate requires encoded PNG maps")
        for index, payload in enumerate(maps):
            expected_mode = "RGB" if index == 0 else "L"
            with Image.open(io.BytesIO(payload)) as encoded_map:
                if encoded_map.format != "PNG" or encoded_map.size != (self.width, self.height):
                    raise ValueError("surface estimate maps must be same-sized PNG images")
                if encoded_map.mode not in {expected_mode, "P"}:
                    raise ValueError("surface estimate map has an unexpected color mode")
        for name, value in (
            ("confidence", self.confidence),
            ("scattering_strength", self.scattering_strength),
        ):
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                or not 0 <= value <= 1
            ):
                raise ValueError(f"{name} must be finite and between zero and one")

    # {
    #   責務: [manifest: summary情報とmap dimensionsをdata interchange形式にする]
    #   処理: [report map names and uncertainty without copying binary map content]
    #   引数: [self: one material estimate]
    #   戻り値: [dict[str, object]: compact estimate metadata]
    # }
    def manifest(self) -> dict[str, object]:
        return {
            "estimate_id": self.estimate_id,
            "dimensions": [self.width, self.height],
            "map_names": [
                "surface_color",
                "alpha",
                "transmittance",
                "shading",
                "blur_scatter",
                "texture_frequency",
                "specular",
                "wrinkle_confidence",
                "uncertainty",
            ],
            "material_category": self.material_category,
            "material": self.material,
            "scattering_strength": self.scattering_strength,
            "confidence": self.confidence,
            "method": self.method,
        }


# {
#   責務: [MaterialEstimateSet: source-specific alternative estimatesとrouting confidenceを返す]
#   フィールド: [source_sha256, estimates, warnings]
# }
@dataclass(frozen=True, slots=True)
class MaterialEstimateSet:
    source_sha256: str
    estimates: tuple[SurfaceEstimate, ...]
    warnings: tuple[str, ...] = ()

    # {
    #   責務: [__post_init__: estimate alternativesとsource digestをvalidateする]
    #   処理: [require the stable source binding and at least one hypothesis]
    #   引数: [self: material hypotheses]
    #   戻り値: []
    # }
    def __post_init__(self) -> None:
        if (
            len(self.source_sha256) != 64
            or any(character not in "0123456789abcdef" for character in self.source_sha256)
            or not self.estimates
        ):
            raise ValueError("estimate set requires a SHA-256 and at least one hypothesis")
        if any(not isinstance(item, SurfaceEstimate) for item in self.estimates):
            raise TypeError("estimates must contain SurfaceEstimate values")


# {
#   責務: [MaterialEstimator: alternate material inference backendsのinterfaceを定義する]
#   フィールド: [name, estimate]
#   処理: [allow classical, research and learned estimators to be compared without caller changes]
# }
class MaterialEstimator(Protocol):
    # {
    #   責務: [name: estimator provenance IDを返す]
    #   処理: [expose stable backend identity]
    #   引数: [self: material estimator]
    #   戻り値: [str: estimator identifier]
    # }
    @property
    def name(self) -> str: ...

    # {
    #   責務: [estimate: imageからcandidate SurfaceEstimate群を推定する]
    #   処理: [preserve multiple hypotheses and local uncertainty maps]
    #   引数: [image: source RGB pixels, category: optional prior, material: optional prior, reference_colors: optional external colors]
    #   戻り値: [MaterialEstimateSet: source-bound alternative estimates]
    # }
    def estimate(
        self,
        image: Image.Image,
        category: str = "",
        material: str = "",
        reference_colors: tuple[tuple[int, int, int], ...] = (),
        reference_alpha: float | None = None,
    ) -> MaterialEstimateSet: ...


# {
#   責務: [MaterialEstimatorRegistry: interchangeable estimator pluginsを管理する]
#   フィールド: [ordered estimator list]
#   処理: [return all estimates so a caller can compare multiple methods]
# }
class MaterialEstimatorRegistry:
    # {
    #   責務: [__init__: optional estimator pluginsを登録する]
    #   処理: [start with injected implementations or one conservative classical estimator]
    #   引数: [estimators: ordered estimator implementations]
    #   戻り値: []
    # }
    def __init__(self, estimators: tuple[MaterialEstimator, ...] = ()) -> None:
        self._estimators = estimators or (ClassicalMaterialEstimator(),)

    # {
    #   責務: [estimate: registered estimatorsのhypothesesを列挙する]
    #   処理: [invoke each method independently and preserve its provenance]
    #   引数: [image: source, category: prior, material: prior, reference_colors: optional colors]
    #   戻り値: [tuple[MaterialEstimateSet, ...]: one set per estimator]
    # }
    def estimate(
        self,
        image: Image.Image,
        category: str = "",
        material: str = "",
        reference_colors: tuple[tuple[int, int, int], ...] = (),
        reference_alpha: float | None = None,
    ) -> tuple[MaterialEstimateSet, ...]:
        return tuple(
            estimator.estimate(image, category, material, reference_colors, reference_alpha)
            for estimator in self._estimators
        )


# {
#   責務: [ClassicalMaterialEstimator: spatial image statisticsからmaterial mapsを推定する]
#   フィールド: [three confidence-adjusted alpha hypotheses]
#   処理: [estimate surface color, local alpha/transmission, shading, scatter, texture, specularity, wrinkles and uncertainty]
# }
class ClassicalMaterialEstimator:
    # {
    #   責務: [name: stable estimator provenance identifierを返す]
    #   処理: [expose the classical local-statistics method name]
    #   引数: [self: material estimator]
    #   戻り値: [str: algorithm identifier]
    # }
    @property
    def name(self) -> str:
        return "classical_spatial_prior_v1"

    # {
    #   責務: [estimate: RGB sourceからthree local alpha/transmission hypothesesを構築する]
    #   処理: [combine local color residual, edge frequency and optional material/reference priors]
    #   引数: [image: source RGB, category: coarse material category, material: material prior, reference_colors: optional known surface colors]
    #   戻り値: [MaterialEstimateSet: conservative, natural, and enhanced estimates]
    #   エラー: [ValueError: unsupported dimensions or invalid material prior]
    # }
    def estimate(
        self,
        image: Image.Image,
        category: str = "",
        material: str = "",
        reference_colors: tuple[tuple[int, int, int], ...] = (),
        reference_alpha: float | None = None,
    ) -> MaterialEstimateSet:
        rgb = np.asarray(image.convert("RGB"), dtype=np.uint8)
        if rgb.ndim != 3 or rgb.shape[2] != 3 or rgb.shape[0] * rgb.shape[1] > 16_000_000:
            raise ValueError("material estimation supports RGB images up to 16 megapixels")
        if category not in {
            "",
            "generic",
            "cloth",
            "clothing",
            "paper",
            "film",
            "glass",
            "skin",
            "other",
        }:
            raise ValueError("unsupported material category")
        if material not in {"", "thin_cloth", "thick_cloth", "paper", "plastic", "glass", "other"}:
            raise ValueError("unsupported material prior")
        if reference_alpha is not None and (
            isinstance(reference_alpha, bool)
            or not isinstance(reference_alpha, (int, float))
            or not math.isfinite(reference_alpha)
            or not 0 <= reference_alpha <= 1
        ):
            raise ValueError("reference_alpha must be finite and between zero and one")
        height, width = rgb.shape[:2]
        lab = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB).astype(np.float32)
        sigma = max(2.0, min(width, height) / 28)
        surface_rgb = cv2.GaussianBlur(rgb, (0, 0), sigmaX=sigma).astype(np.uint8)
        surface_lab = cv2.cvtColor(surface_rgb, cv2.COLOR_RGB2LAB).astype(np.float32)
        color_residual = np.linalg.norm(lab - surface_lab, axis=2)
        gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY).astype(np.float32)
        low_frequency = cv2.GaussianBlur(gray, (0, 0), sigmaX=max(4.0, sigma * 1.7))
        local_shading = np.clip(low_frequency - float(np.mean(low_frequency)) + 128, 0, 255).astype(
            np.uint8
        )
        high_frequency = np.abs(gray - cv2.GaussianBlur(gray, (0, 0), sigmaX=2.0))
        frequency_scale = float(np.percentile(high_frequency, 95))
        texture_map = np.clip(high_frequency / max(frequency_scale, 1.0) * 255, 0, 255).astype(
            np.uint8
        )
        blurred_frequency = cv2.GaussianBlur(texture_map, (0, 0), sigmaX=max(2.0, sigma / 2))
        scattering_map = np.clip(255 - blurred_frequency, 0, 255).astype(np.uint8)
        hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
        saturation = hsv[..., 1].astype(np.float32) / 255
        brightness = hsv[..., 2].astype(np.float32)
        highlight_threshold = max(200.0, float(np.percentile(brightness, 92)))
        specular_map = np.clip(
            ((brightness - highlight_threshold) / max(255 - highlight_threshold, 1))
            * (1 - saturation)
            * 255,
            0,
            255,
        ).astype(np.uint8)
        edges_x = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
        edges_y = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
        edge_magnitude = cv2.magnitude(edges_x, edges_y)
        wrinkle_map = cv2.normalize(edge_magnitude, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
        border = np.concatenate((lab[0], lab[-1], lab[:, 0], lab[:, -1]), axis=0)
        border_spread = float(np.mean(np.std(border, axis=0)))
        base_alpha = (
            float(np.clip(reference_alpha, 0.08, 0.30))
            if reference_alpha is not None
            else float(np.clip(0.28 - border_spread / 180.0, 0.08, 0.24))
        )
        if material in {"thin_cloth", "paper"}:
            base_alpha *= 1.08
        elif material in {"thick_cloth", "glass"}:
            base_alpha *= 0.82
        if reference_colors:
            reference_array = np.asarray(reference_colors, dtype=np.uint8).reshape(1, -1, 3)
            reference_lab = (
                cv2.cvtColor(reference_array, cv2.COLOR_RGB2LAB).reshape(-1, 3).astype(np.float32)
            )
            distance_to_reference = np.min(
                np.linalg.norm(lab[..., None, :] - reference_lab[None, None, ...], axis=3),
                axis=2,
            )
            color_residual = 0.55 * color_residual + 0.45 * distance_to_reference
        residual_scale = max(float(np.percentile(color_residual, 75)), 8.0)
        local_alpha = base_alpha * np.exp(-color_residual / residual_scale)
        local_alpha *= 0.72 + 0.28 * (1.0 - scattering_map.astype(np.float32) / 255)
        local_alpha = np.clip(local_alpha, 0.025, 0.36)
        alpha_uncertainty = np.clip(0.66 + 0.20 * np.minimum(color_residual / 64, 1.0), 0.50, 0.92)
        if material or category:
            alpha_uncertainty = np.maximum(0.42, alpha_uncertainty - 0.10)
        inferred_category = category or _infer_category(texture_map, specular_map)
        inferred_material = material or _infer_material(
            inferred_category, texture_map, specular_map
        )
        encoded_rgb = _encode_map(surface_rgb)
        source_digest = hashlib.sha256(image.convert("RGB").tobytes()).hexdigest()
        hypotheses = []
        for label, alpha_scale in (("conservative", 0.65), ("natural", 1.0), ("enhanced", 1.25)):
            alpha_map = np.clip(local_alpha * alpha_scale, 0.01, 0.4)
            alpha_bytes = _encode_map(np.round(alpha_map * 255).astype(np.uint8))
            transmission_bytes = _encode_map(np.round((1 - alpha_map) * 255).astype(np.uint8))
            uncertainty = np.clip(alpha_uncertainty + (0.08 if label == "enhanced" else 0), 0, 1)
            hypotheses.append(
                SurfaceEstimate(
                    f"{self.name}:{label}",
                    width,
                    height,
                    encoded_rgb,
                    alpha_bytes,
                    transmission_bytes,
                    _encode_map(local_shading),
                    _encode_map(scattering_map),
                    _encode_map(texture_map),
                    _encode_map(specular_map),
                    _encode_map(wrinkle_map),
                    _encode_map(np.round(uncertainty * 255).astype(np.uint8)),
                    inferred_category,
                    inferred_material,
                    float(np.mean(scattering_map) / 255),
                    float(1 - np.mean(uncertainty)),
                )
            )
        warnings = ("heuristic_estimates_require_review",)
        if not material and not category:
            warnings += ("material_category_is_unverified",)
        return MaterialEstimateSet(source_digest, tuple(hypotheses), warnings)


# {
#   責務: [EstimateEvaluation: synthetic/known map ground truthとのMAEをまとめる]
#   フィールド: [alpha_mae, transmittance_mae, surface_color_mae]
# }
@dataclass(frozen=True, slots=True)
class EstimateEvaluation:
    alpha_mae: float
    transmittance_mae: float
    surface_color_mae: float


# {
#   責務: [evaluate_against_ground_truth: estimate mapsをsame-resolution GTへ定量比較する]
#   処理: [compute normalized mean absolute errors for alpha, transmission, and color]
#   引数: [estimate: estimated maps, alpha_ground_truth: L image, transmittance_ground_truth: L image, surface_ground_truth: RGB image]
#   戻り値: [EstimateEvaluation: per-map normalized MAE]
# }
def evaluate_against_ground_truth(
    estimate: SurfaceEstimate,
    alpha_ground_truth: Image.Image,
    transmittance_ground_truth: Image.Image,
    surface_ground_truth: Image.Image,
) -> EstimateEvaluation:
    alpha = _decode_map(estimate.alpha_map, "L").astype(np.float32) / 255
    transmission = _decode_map(estimate.transmittance_map, "L").astype(np.float32) / 255
    surface = _decode_map(estimate.surface_color_map, "RGB").astype(np.float32) / 255
    alpha_target = np.asarray(alpha_ground_truth.convert("L"), dtype=np.float32) / 255
    transmission_target = (
        np.asarray(transmittance_ground_truth.convert("L"), dtype=np.float32) / 255
    )
    surface_target = np.asarray(surface_ground_truth.convert("RGB"), dtype=np.float32) / 255
    if (
        alpha.shape != alpha_target.shape
        or transmission.shape != transmission_target.shape
        or surface.shape != surface_target.shape
    ):
        raise ValueError("ground-truth maps must match estimated dimensions")
    return EstimateEvaluation(
        float(np.mean(np.abs(alpha - alpha_target))),
        float(np.mean(np.abs(transmission - transmission_target))),
        float(np.mean(np.abs(surface - surface_target))),
    )


# {
#   責務: [apply_surface_estimate: estimate mapsでconfidence-aware image candidateを作る]
#   処理: [subtract local surface contribution, bound inverse transmission, and reduce estimated scattering conservatively]
#   引数: [image: observed RGB, estimate: selected local maps, profile: processing strength]
#   戻り値: [Image.Image: conservative RGB candidate]
# }
def apply_surface_estimate(
    image: Image.Image, estimate: SurfaceEstimate, profile: str = "balanced"
) -> Image.Image:
    rgb = np.asarray(image.convert("RGB"), dtype=np.float32)
    if rgb.shape[:2] != (estimate.height, estimate.width):
        raise ValueError("surface estimate dimensions must match input image")
    surface = _decode_map(estimate.surface_color_map, "RGB").astype(np.float32)
    alpha = _decode_map(estimate.alpha_map, "L").astype(np.float32) / 255
    uncertainty = _decode_map(estimate.uncertainty_map, "L").astype(np.float32) / 255
    scatter = _decode_map(estimate.blur_scatter_map, "L").astype(np.float32) / 255
    confidence_gain = 0.35 + 0.65 * (1 - uncertainty)
    profile_gain = 0.2 if profile == "conservative" else 1.0
    alpha_ceiling = 0.06 if profile == "conservative" else 0.28
    adjusted_alpha = np.clip(alpha * confidence_gain * profile_gain, 0.0, alpha_ceiling)
    corrected = np.clip(
        (rgb - adjusted_alpha[..., None] * surface) / (1 - adjusted_alpha[..., None]), 0, 255
    )
    if float(np.mean(scatter)) > 0 and profile != "conservative":
        blurred = cv2.GaussianBlur(corrected.astype(np.uint8), (0, 0), sigmaX=1.2).astype(
            np.float32
        )
        correction_weight = (
            scatter[..., None] * confidence_gain[..., None] * (0.08 * estimate.scattering_strength)
        )
        corrected = corrected * (1 - correction_weight) + blurred * correction_weight
    return Image.fromarray(np.clip(corrected, 0, 255).astype(np.uint8), "RGB")


# {
#   責務: [_encode_map: 8-bit NumPy mapをPNGへserializeする]
#   処理: [write deterministic single-channel or RGB bytes]
#   引数: [array: 8-bit map]
#   戻り値: [bytes: PNG map]
# }
def _encode_map(array: np.ndarray) -> bytes:
    image = Image.fromarray(array.astype(np.uint8))
    stream = io.BytesIO()
    image.save(stream, format="PNG", optimize=True)
    return stream.getvalue()


# {
#   責務: [_decode_map: encoded PNG mapをrequested modeでdecodeする]
#   処理: [validate image dimensions and return array pixels]
#   引数: [payload: encoded map, mode: L or RGB]
#   戻り値: [np.ndarray: map data]
# }
def _decode_map(payload: bytes, mode: str) -> np.ndarray:
    with Image.open(io.BytesIO(payload)) as image:
        return np.asarray(image.convert(mode))


# {
#   責務: [_infer_category: texture/specular proxiesからcoarse categoryを推定する]
#   処理: [return a low-commitment category prior with no class probability claim]
#   引数: [texture_map: high-frequency estimate, specular_map: highlight proxy]
#   戻り値: [str: coarse material category]
# }
def _infer_category(texture_map: np.ndarray, specular_map: np.ndarray) -> str:
    texture = float(np.mean(texture_map)) / 255
    specular = float(np.mean(specular_map)) / 255
    if specular > 0.12:
        return "glass"
    return "cloth" if texture > 0.13 else "generic"


# {
#   責務: [_infer_material: category/texture proxiesからcoarse materialを割り当てる]
#   処理: [return only a weak prior; uncertainty stays high]
#   引数: [category: category prior, texture_map: local texture frequency, specular_map: highlight estimate]
#   戻り値: [str: coarse material]
# }
def _infer_material(category: str, texture_map: np.ndarray, specular_map: np.ndarray) -> str:
    if category == "glass":
        return "glass"
    if category == "paper":
        return "paper"
    if category in {"cloth", "clothing"}:
        return "thin_cloth" if float(np.mean(texture_map)) > 72 else "thick_cloth"
    return "other"
