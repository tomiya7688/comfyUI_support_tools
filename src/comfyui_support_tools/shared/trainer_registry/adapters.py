"""Runtime probes and trainer-specific translations for external LoRA tools."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import shutil
import subprocess
import urllib.parse
from pathlib import Path
from typing import Any

from ..safetensors_metadata import read_safetensors_evidence
from .contracts import (
    AdapterMethod,
    ArchitectureProfile,
    ConfigValidation,
    Quantization,
    SupportLevel,
    TrainerProbe,
    TrainingSpec,
)

_MAX_MANIFEST_BYTES = 1024 * 1024
_VERSION_PATTERN = re.compile(r"(?<!\d)(\d+)\.(\d+)(?:\.(\d+))?")


# {
# 責務: [_version_tuple: normalize comparable semantic version components]
# 処理: [extract the first stable major/minor/patch tuple from trainer version text]
# 引数: [value: version output]
# 戻り値: [tuple[int, int, int] | None: parsed semantic version]
# }
def _version_tuple(value: str) -> tuple[int, int, int] | None:
    match = _VERSION_PATTERN.search(value)
    if not match:
        return None
    return tuple(int(part or 0) for part in match.groups())


# {
# 責務: [_read_manifest: read an optional trainer capability manifest]
# 処理: [bound file size, require a JSON object and fingerprint content for cache invalidation]
# 引数: [root: trainer checkout path]
# 戻り値: [tuple[dict[str, Any], str]: capability declarations and SHA-256]
# }
def _read_manifest(root: Path | None) -> tuple[dict[str, Any], str]:
    if root is None:
        return {}, hashlib.sha256(b"").hexdigest()
    path = root / "codex_capabilities.json"
    if not path.exists():
        return {}, hashlib.sha256(b"").hexdigest()
    if path.is_symlink() or path.stat().st_size > _MAX_MANIFEST_BYTES:
        raise ValueError("trainer capability manifest must be a bounded regular file")
    raw = path.read_bytes()
    try:
        payload = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("trainer capability manifest is malformed") from error
    if not isinstance(payload, dict):
        raise ValueError("trainer capability manifest must be a JSON object")
    if "models" in payload and (
        not isinstance(payload["models"], list)
        or any(not isinstance(item, str) for item in payload["models"])
    ):
        raise ValueError("trainer capability manifest models must be a string list")
    for key in ("methods", "target_modules", "precision", "quantization", "features"):
        section = payload.get(key, {})
        if not isinstance(section, dict) or any(not isinstance(name, str) for name in section):
            raise ValueError(f"trainer capability manifest {key} section must be an object")
        for architecture, values in section.items():
            if key == "methods":
                if not isinstance(values, dict) or any(
                    not isinstance(method, str)
                    or not isinstance(level, str)
                    or level not in {level.value for level in SupportLevel}
                    for method, level in values.items()
                ):
                    raise ValueError(
                        "trainer manifest methods must map method names to support levels"
                    )
            elif not isinstance(values, list) or any(not isinstance(item, str) for item in values):
                raise ValueError(
                    f"trainer capability manifest {key}.{architecture} must be a string list"
                )
    minimum_versions = payload.get("minimum_versions", {})
    if not isinstance(minimum_versions, dict) or any(
        not isinstance(name, str) or not isinstance(version, str) or _version_tuple(version) is None
        for name, version in minimum_versions.items()
    ):
        raise ValueError("trainer capability minimum_versions must map profile keys to versions")
    if "smoke_command" in payload and (
        not isinstance(payload["smoke_command"], list)
        or not payload["smoke_command"]
        or any(not isinstance(item, str) for item in payload["smoke_command"])
    ):
        raise ValueError("trainer smoke_command must be a nonempty argument list")
    return payload, hashlib.sha256(raw).hexdigest()


# {
# 責務: [_ConfigValidationMixin: validate trainer/model/runtime constraints and estimate memory]
# フィールド: [None: stateless behavior mixin over a runtime trainer adapter]
# 処理: [delegate configuration checks to the combined runtime trainer adapter]
# 引数: [None: behavior is provided by the mixin methods]
# 戻り値: [None: composed behavior is inherited by RuntimeTrainerAdapter]
# }
class _ConfigValidationMixin:
    # {
    # 責務: [validate_config: validate common and trainer-specific constraints]
    # 処理: [reject invalid data, unsupported methods, absent target modules and unavailable quantization]
    # 引数: [self: trainer adapter, spec: common training specification]
    # 戻り値: [ConfigValidation: normalized errors and warnings]
    # }
    def validate_config(self, spec: TrainingSpec):

        errors = []
        warnings = []
        profile = self.profiles.get(spec.architecture)
        probe = self._probe_cache or self.probe()
        if not probe.available:
            errors.append(f"{self.trainer_label} runtime is unavailable: {probe.reason}")
        if profile is None or spec.architecture not in self.supported_models():
            errors.append(
                f"{self.trainer_label} does not support architecture profile {spec.architecture}"
            )
        if spec.steps <= 0 or spec.rank <= 0 or spec.alpha <= 0:
            errors.append("steps, rank and alpha must be positive")
        if not spec.dataset.exists() or not spec.dataset.is_dir():
            errors.append("dataset must be an existing directory")
        if not spec.base_model.exists():
            errors.append("base model path must exist locally")
        if spec.resolution <= 0 or spec.batch_size <= 0 or spec.gradient_accumulation <= 0:
            errors.append("resolution, batch size and gradient accumulation must be positive")
        if profile is not None and probe.available:
            methods = {
                entry.method: entry.level for entry in self.supported_methods(spec.architecture)
            }
            method_level = methods.get(spec.method, SupportLevel.UNSUPPORTED)
            if method_level is SupportLevel.UNSUPPORTED:
                errors.append(f"method {spec.method.value} is unsupported by {self.trainer_name}")
            elif method_level is SupportLevel.EXPERIMENTAL:
                warnings.append(
                    f"method {spec.method.value} is experimental for {spec.architecture}"
                )
            if spec.precision not in self.supported_precision(spec.architecture):
                errors.append(f"precision {spec.precision} is unavailable")
            if spec.quantization not in self.supported_quantization(spec.architecture):
                errors.append(f"quantization {spec.quantization.value} is unavailable")
            features = set(self.supported_features(spec.architecture))
            requested_features = {
                "gradient_checkpointing": spec.gradient_checkpointing,
                "optimizer_offload": spec.optimizer_offload,
                "cpu_offload": spec.cpu_offload,
                "quantized_text_encoder": spec.quantized_text_encoder,
                "cached_embeddings": spec.cached_embeddings,
                "vae_cache": spec.vae_cache,
                "lower_resolution_probe": spec.lower_resolution_probe,
            }
            unavailable = sorted(
                name
                for name, enabled in requested_features.items()
                if enabled and name not in features
            )
            if unavailable:
                errors.append(
                    "requested memory features are unsupported: " + ", ".join(unavailable)
                )
            if spec.train_text_encoder and not profile.text_encoder_trainable:
                errors.append("text encoder training is disabled for this architecture profile")
            model_path = (
                spec.base_model
                if spec.base_model.is_file() and spec.base_model.suffix.casefold() == ".safetensors"
                else None
            )
            available_modules = set(self.target_modules(spec.architecture, model_path))
            missing = set(spec.target_modules) - available_modules
            if missing:
                errors.append(
                    "target modules are absent from trainer/model discovery: "
                    + ", ".join(sorted(missing))
                )
            if not spec.target_modules:
                errors.append("target modules must be discovered and explicitly selected")
            if (
                spec.target_modules
                and available_modules
                and not (set(spec.target_modules) & available_modules)
            ):
                errors.append(
                    "target module selection does not intersect the discovered model targets"
                )
            if (
                profile.dataset_kind != "image_caption"
                and spec.dataset_kind != profile.dataset_kind
            ):
                errors.append(
                    f"dataset kind must be {profile.dataset_kind} for {spec.architecture}"
                )
            if self.available_vram_gib is not None:
                estimate = self._estimated_vram(profile, spec)
                if estimate > self.available_vram_gib:
                    errors.append(
                        f"estimated VRAM {estimate:.1f} GiB exceeds available {self.available_vram_gib:.1f} GiB"
                    )
                elif estimate > self.available_vram_gib * 0.85:
                    warnings.append(f"estimated VRAM {estimate:.1f} GiB leaves little headroom")
        return ConfigValidation(not errors, tuple(errors), tuple(warnings))

    # {
    # 責務: [_estimated_vram: estimate training memory after supported low-VRAM switches]
    # 処理: [apply profile minimum and conservative, independent offload/cache/quantization reductions]
    # 引数: [profile: model architecture, spec: normalized training request]
    # 戻り値: [float: estimated GiB requirement]
    # }
    @staticmethod
    def _estimated_vram(profile: ArchitectureProfile, spec: TrainingSpec) -> float:
        estimate = profile.minimum_vram_gib
        if spec.gradient_checkpointing:
            estimate *= 0.82
        if spec.cpu_offload:
            estimate *= 0.7
        if spec.optimizer_offload:
            estimate *= 0.88
        if spec.quantization is not Quantization.NONE:
            estimate *= 0.72
        if spec.quantized_text_encoder:
            estimate *= 0.9
        if spec.cached_embeddings:
            estimate *= 0.9
        if spec.lower_resolution_probe:
            estimate *= 0.7
        if spec.batch_size == 1 and spec.gradient_accumulation > 1:
            estimate *= 0.9
        return max(4.0, estimate)


# {
# 責務: [_ConfigTranslationMixin: serialize validated specifications and capture provenance]
# フィールド: [None: stateless behavior mixin over a runtime trainer adapter]
# 処理: [delegate config serialization and provenance to the combined adapter]
# 引数: [None: behavior is provided by the mixin methods]
# 戻り値: [None: composed behavior is inherited by RuntimeTrainerAdapter]
# }
class _ConfigTranslationMixin:
    # {
    # 責務: [translate_config: convert common spec into native trainer fields]
    # 処理: [serialize only values accepted by the selected trainer's public configuration surface]
    # 引数: [self: trainer adapter, spec: validated training specification]
    # 戻り値: [dict[str, object]: trainer-native config mapping]
    # }
    def translate_config(self, spec: TrainingSpec) -> dict[str, object]:
        validation = self.validate_config(spec)
        if not validation.valid:
            raise ValueError("invalid training config: " + "; ".join(validation.errors))
        profile = self.profiles[spec.architecture]
        return {
            "model": {
                "architecture_profile": spec.architecture,
                "family": profile.family,
                "base_model": str(spec.base_model),
            },
            "training": {
                "method": spec.method.value,
                "steps": spec.steps,
                "rank": spec.rank,
                "alpha": spec.alpha,
                "target_modules": list(spec.target_modules),
                "resolution": spec.resolution,
                "train_text_encoder": spec.train_text_encoder,
                "precision": spec.precision,
                "quantization": spec.quantization.value,
                "gradient_checkpointing": spec.gradient_checkpointing,
                "optimizer_offload": spec.optimizer_offload,
                "cpu_offload": spec.cpu_offload,
                "quantized_text_encoder": spec.quantized_text_encoder,
                "cached_embeddings": spec.cached_embeddings,
                "vae_cache": spec.vae_cache,
                "batch_size": spec.batch_size,
                "gradient_accumulation": spec.gradient_accumulation,
                "lower_resolution_probe": spec.lower_resolution_probe,
                "seed": spec.seed,
            },
            "dataset": {
                "path": str(spec.dataset),
                "kind": spec.dataset_kind or profile.dataset_kind,
            },
            "output_dir": str(spec.output),
        }

    # {
    # 責務: [training_provenance: capture upstream, version, recipe and local-change identity]
    # 処理: [hash the translated configuration and inspect the checkout revision without exposing remote credentials]
    # 引数: [self: trainer adapter, spec: training specification]
    # 戻り値: [TrainingProvenance: reproducibility record]
    # }
    def training_provenance(self, spec: TrainingSpec):
        from .contracts import TrainingProvenance

        probe = self._probe_cache or self.probe()
        config_hash = hashlib.sha256(
            self.serialize_config(self.translate_config(spec)).encode()
        ).hexdigest()
        revision = None
        local_fingerprint = hashlib.sha256(b"").hexdigest()
        local_changes = False
        if self.trainer_root and (self.trainer_root / ".git").exists():
            try:
                revision_result = subprocess.run(
                    ["git", "rev-parse", "HEAD"],
                    cwd=self.trainer_root,
                    capture_output=True,
                    text=True,
                    timeout=5,
                    check=False,
                )
                status_result = subprocess.run(
                    ["git", "status", "--porcelain"],
                    cwd=self.trainer_root,
                    capture_output=True,
                    text=True,
                    timeout=5,
                    check=False,
                )
                if revision_result.returncode == 0:
                    revision = revision_result.stdout.strip()[:64]
                if status_result.returncode == 0:
                    status = status_result.stdout
                    local_changes = bool(status.strip())
                    local_fingerprint = hashlib.sha256(status.encode()).hexdigest()
            except (OSError, subprocess.TimeoutExpired):
                pass
        return TrainingProvenance(
            self.trainer_name,
            probe.version,
            self.upstream_repository,
            revision,
            config_hash,
            local_changes,
            local_fingerprint,
            probe.capability_fingerprint,
        )

    # {
    # 責務: [serialize_config: encode trainer-native config in the trainer's file format]
    # 処理: [use deterministic JSON, YAML-compatible JSON, or TOML syntax]
    # 引数: [config: trainer config mapping]
    # 戻り値: [str: serialized configuration text]
    # }
    def serialize_config(self, config: dict[str, object]) -> str:
        if self.config_format in {"json", "yaml"}:
            return json.dumps(config, ensure_ascii=False, indent=2, sort_keys=True)
        return self._to_toml(config)

    # {
    # 責務: [_to_toml: serialize nested trainer settings as deterministic TOML]
    # 処理: [emit scalar root fields and one-level nested sections]
    # 引数: [config: trainer config mapping]
    # 戻り値: [str: TOML document]
    # }
    @staticmethod
    def _to_toml(config: dict[str, object]) -> str:
        # {
        # 責務: [scalar: perform the declared operation]
        # 処理: [follow the documented contract and preserve validated invariants]
        # 引数: [declared function inputs]
        # 戻り値: [declared function result]
        # }
        def scalar(value: Any) -> str:
            if isinstance(value, bool):
                return "true" if value else "false"
            if isinstance(value, (int, float)):
                return str(value)
            if isinstance(value, list):
                return "[" + ", ".join(scalar(item) for item in value) + "]"
            return json.dumps(str(value), ensure_ascii=False)

        lines = []
        for key, value in config.items():
            if not isinstance(value, dict):
                lines.append(f"{key} = {scalar(value)}")
        for section, values in config.items():
            if isinstance(values, dict):
                lines.append(f"\n[{section}]")
                lines.extend(f"{key} = {scalar(value)}" for key, value in values.items())
        return "\n".join(lines) + "\n"

    # {
    # 責務: [to_cli: express one spec as a safe trainer command argument sequence]
    # 処理: [translate the config and flatten stable scalar/list options without shell evaluation]
    # 引数: [self: trainer adapter, spec: validated training specification]
    # 戻り値: [tuple[str, ...]: trainer CLI arguments]
    # }
    def to_cli(self, spec: TrainingSpec) -> tuple[str, ...]:
        config = self.translate_config(spec)
        arguments = []
        for section, values in config.items():
            if not isinstance(values, dict):
                arguments.extend((f"--{section.replace('_', '-')}", str(values)))
                continue
            for key, value in values.items():
                name = f"--{section}-{key}".replace("_", "-")
                if isinstance(value, bool):
                    if value:
                        arguments.append(name)
                elif isinstance(value, list):
                    arguments.extend((name, ",".join(str(item) for item in value)))
                else:
                    arguments.extend((name, str(value)))
        return tuple(arguments)


# {
# 責務: [RuntimeTrainerAdapter: coordinate this module responsibility]
# フィールド: [declared values and public collaborators]
# 処理: [follow the documented contract and preserve validated invariants]
# }
class RuntimeTrainerAdapter(_ConfigValidationMixin, _ConfigTranslationMixin):
    """Probe one trainer installation and translate the shared training contract."""

    trainer_name = "base"
    trainer_label = "External Trainer"
    config_format = "json"
    default_executable: str | None = None
    default_version_args = ("--version",)
    required_files: tuple[str, ...] = ()
    required_modules: tuple[str, ...] = ()
    upstream_url = ""

    # {
    # 責務: [__init__: bind trainer executable, local checkout and runtime constraints]
    # 処理: [store only explicit local paths and safe argument vectors]
    # 引数: [trainer_root: optional checkout, executable: optional command, version_args: version arguments, profiles: architecture registry, available_vram_gib: optional detected device memory]
    # 戻り値: [None: adapter ready for runtime probing]
    # }
    def __init__(
        self,
        trainer_root: str | Path | None = None,
        executable: str | None = None,
        version_args: tuple[str, ...] | None = None,
        profiles: dict[str, ArchitectureProfile] | None = None,
        available_vram_gib: float | None = None,
        upstream_repository: str = "",
    ) -> None:
        self.trainer_root = Path(trainer_root).expanduser().resolve() if trainer_root else None
        self.executable = executable if executable is not None else self.default_executable
        self.version_args = tuple(
            version_args if version_args is not None else self.default_version_args
        )
        self.profiles = profiles or {}
        self.available_vram_gib = available_vram_gib or self._detect_vram_gib()
        self.upstream_repository = self._sanitize_repository(
            upstream_repository or self.upstream_url
        )
        self._probe_cache: TrainerProbe | None = None
        self._manifest: dict[str, Any] = {}

    # {
    # 責務: [describe: expose trainer adapter identity]
    # 処理: [return stable descriptive fields without claiming installation support]
    # 引数: [self: trainer adapter]
    # 戻り値: [dict[str, str]: adapter name and config format]
    # }
    def describe(self) -> dict[str, str]:
        return {
            "name": self.trainer_name,
            "label": self.trainer_label,
            "config_format": self.config_format,
        }

    # {
    # 責務: [_sanitize_repository: retain a credential-free upstream repository URL]
    # 処理: [strip user information, query, fragment and unsupported protocols]
    # 引数: [value: configured upstream URL]
    # 戻り値: [str: safe HTTPS/SSH repository identity]
    # }
    @staticmethod
    def _sanitize_repository(value: str) -> str:
        if not value:
            return ""
        parsed = urllib.parse.urlsplit(value)
        if parsed.scheme not in {"https", "ssh"} or not parsed.hostname:
            return ""
        path = parsed.path.removesuffix(".git")
        return urllib.parse.urlunsplit((parsed.scheme, parsed.hostname, path, "", ""))

    # {
    # 責務: [_detect_vram_gib: inspect the first local NVIDIA device when available]
    # 処理: [run a bounded read-only nvidia-smi query without importing a trainer or torch]
    # 引数: [None: use the local execution host]
    # 戻り値: [float | None: device capacity in GiB]
    # }
    @staticmethod
    def _detect_vram_gib() -> float | None:
        executable = shutil.which("nvidia-smi")
        if not executable:
            return None
        try:
            result = subprocess.run(
                [executable, "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
                capture_output=True,
                text=True,
                timeout=3,
                check=True,
            )
        except (OSError, subprocess.SubprocessError):
            return None
        try:
            values = [int(line.strip()) for line in result.stdout.splitlines() if line.strip()]
        except ValueError:
            return None
        return values[0] / 1024 if values else None

    # {
    # 責務: [probe: verify trainer version and capability manifest]
    # 処理: [probe an executable or local git checkout using bounded non-shell commands]
    # 引数: [self: trainer adapter]
    # 戻り値: [TrainerProbe: availability and cache fingerprint]
    # }
    def probe(self) -> TrainerProbe:
        manifest, manifest_hash = _read_manifest(self.trainer_root)
        self._manifest = manifest
        command = shutil.which(self.executable) if self.executable else None
        version = None
        reason = "trainer executable is not installed"
        if command:
            try:
                result = subprocess.run(
                    [command, *self.version_args],
                    cwd=self.trainer_root,
                    capture_output=True,
                    text=True,
                    timeout=8,
                    check=False,
                )
                if result.returncode == 0:
                    version = (result.stdout or result.stderr).strip()[:256]
                    reason = "trainer executable and version probe are available"
                else:
                    reason = f"version probe returned exit code {result.returncode}"
            except (OSError, subprocess.TimeoutExpired) as error:
                reason = f"trainer version probe failed: {type(error).__name__}"
        elif self.trainer_root and (self.trainer_root / ".git").exists():
            try:
                result = subprocess.run(
                    ["git", "describe", "--tags", "--always", "--dirty"],
                    cwd=self.trainer_root,
                    capture_output=True,
                    text=True,
                    timeout=8,
                    check=False,
                )
                if result.returncode == 0:
                    version = result.stdout.strip()[:256]
                    reason = "local trainer checkout identity is available"
            except (OSError, subprocess.TimeoutExpired):
                reason = "local trainer checkout version probe failed"
        available = version is not None and _version_tuple(version) is not None
        if available and self.trainer_root and self.required_files:
            missing = [
                name for name in self.required_files if not (self.trainer_root / name).exists()
            ]
            if missing:
                available = False
                reason = "trainer checkout is missing required runtime files: " + ", ".join(missing)
        if available and any(
            importlib.util.find_spec(name) is None for name in self.required_modules
        ):
            available = False
            reason = "trainer Python dependencies are missing"
        material = f"{self.trainer_name}\0{version or ''}\0{manifest_hash}"
        fingerprint = hashlib.sha256(material.encode()).hexdigest()
        probe = TrainerProbe(self.trainer_name, available, version, command, reason, fingerprint)
        self._probe_cache = probe
        return probe

    # {
    # 責務: [version: return the current probed trainer version]
    # 処理: [reuse cached probe state or perform the bounded local probe]
    # 引数: [self: trainer adapter]
    # 戻り値: [str | None: version identifier]
    # }
    def version(self) -> str | None:
        return (self._probe_cache or self.probe()).version

    # {
    # 責務: [smoke_command: expand a trainer-declared smoke test argv template]
    # 処理: [reject shell strings and replace only config, steps, output and trainer placeholders]
    # 引数: [self: trainer adapter, config_path: generated native config, steps: bounded count, output: temporary output root]
    # 戻り値: [tuple[str, ...] | None: shell-free command or no declared smoke support]
    # }
    def smoke_command(self, config_path: Path, steps: int, output: Path) -> tuple[str, ...] | None:
        template = self._manifest.get("smoke_command")
        if (
            not isinstance(template, list)
            or not template
            or any(not isinstance(part, str) for part in template)
        ):
            return None
        executable = self._probe_cache or self.probe()
        replacements = {
            "{executable}": executable.executable or "",
            "{config}": str(config_path),
            "{steps}": str(steps),
            "{output}": str(output),
        }
        command = tuple(replacements.get(part, part) for part in template)
        if not command[0] or any("\x00" in part for part in command):
            raise ValueError(
                "trainer smoke command template contains an invalid executable or argument"
            )
        return command

    # {
    # 責務: [supported_models: list installed trainer profile candidates]
    # 処理: [filter profile declarations through runtime availability and manifest exclusions]
    # 引数: [self: trainer adapter]
    # 戻り値: [tuple[str, ...]: available architecture profile keys]
    # }
    def supported_models(self) -> tuple[str, ...]:
        if not self._probe_cache or not self._probe_cache.available:
            return ()
        declared = self._manifest.get("models")
        keys = declared if isinstance(declared, list) else self.profiles.keys()
        return tuple(
            key
            for key in keys
            if key in self.profiles
            and self.profiles[key].supported_trainers.get(
                self.trainer_name, SupportLevel.UNSUPPORTED
            )
            is not SupportLevel.UNSUPPORTED
            and self._meets_minimum_version(key)
        )

    # {
    # 責務: [_meets_minimum_version: reject trainer versions below a profile requirement]
    # 処理: [prefer runtime manifest minimum over the built-in profile minimum]
    # 引数: [self: trainer adapter, architecture: profile key]
    # 戻り値: [bool: true when the detected trainer version meets its floor]
    # }
    def _meets_minimum_version(self, architecture: str) -> bool:
        if not self._probe_cache or not self._probe_cache.version:
            return False
        minimum = self._manifest.get("minimum_versions", {}).get(
            architecture,
            self.profiles[architecture].minimum_trainer_versions.get(self.trainer_name),
        )
        if not minimum:
            return True
        detected, required = _version_tuple(self._probe_cache.version), _version_tuple(minimum)
        return detected is not None and required is not None and detected >= required

    # {
    # 責務: [supported_methods: report per-method support for one profile]
    # 処理: [combine profile research status with optional runtime manifest overrides]
    # 引数: [self: trainer adapter, architecture: profile key]
    # 戻り値: [tuple[MethodSupport, ...]: supported, experimental and unsupported methods]
    # }
    def supported_methods(self, architecture: str):
        from .contracts import MethodSupport

        profile = self.profiles.get(architecture)
        if (
            profile is None
            or not self._probe_cache
            or not self._probe_cache.available
            or architecture not in self.supported_models()
        ):
            return tuple(
                MethodSupport(
                    self.trainer_name,
                    architecture,
                    method,
                    SupportLevel.UNSUPPORTED,
                    "trainer/profile unavailable",
                )
                for method in AdapterMethod
            )
        support = self._manifest.get("methods", {}).get(architecture, {})
        entries = []
        for method in AdapterMethod:
            level = profile.methods.get(method.value, SupportLevel.UNSUPPORTED)
            trainer_level = profile.supported_trainers.get(
                self.trainer_name, SupportLevel.UNSUPPORTED
            )
            if trainer_level is SupportLevel.UNSUPPORTED:
                level = SupportLevel.UNSUPPORTED
            elif trainer_level is SupportLevel.EXPERIMENTAL and level is SupportLevel.SUPPORTED:
                level = SupportLevel.EXPERIMENTAL
            if isinstance(support, dict) and method.value in support:
                level = SupportLevel(support[method.value])
            entries.append(
                MethodSupport(
                    self.trainer_name, architecture, method, level, "runtime/profile support matrix"
                )
            )
        return tuple(entries)

    # {
    # 責務: [supported_precision: intersect trainer and architecture precision]
    # 処理: [apply optional runtime manifest precision allowlist]
    # 引数: [self: trainer adapter, architecture: profile key]
    # 戻り値: [tuple[str, ...]: verified precision choices]
    # }
    def supported_precision(self, architecture: str) -> tuple[str, ...]:
        profile = self.profiles.get(architecture)
        if (
            profile is None
            or not self._probe_cache
            or not self._probe_cache.available
            or architecture not in self.supported_models()
        ):
            return ()
        declared = self._manifest.get("precision", {}).get(architecture)
        return tuple(
            value for value in profile.supported_precision if declared is None or value in declared
        )

    # {
    # 責務: [supported_quantization: return trainer-specific quantization capabilities]
    # 処理: [preserve per-trainer profile differences and optional manifest restrictions]
    # 引数: [self: trainer adapter, architecture: profile key]
    # 戻り値: [tuple[Quantization, ...]: available quantizers]
    # }
    def supported_quantization(self, architecture: str) -> tuple[Quantization, ...]:
        profile = self.profiles.get(architecture)
        if (
            profile is None
            or not self._probe_cache
            or not self._probe_cache.available
            or architecture not in self.supported_models()
        ):
            return ()
        values = profile.quantization.get(self.trainer_name, ())
        manifest_values = self._manifest.get("quantization", {}).get(architecture)
        if manifest_values is not None:
            values = tuple(value for value in values if value.value in manifest_values)
        return tuple(values)

    # {
    # 責務: [supported_features: return per-trainer low-VRAM switches]
    # 処理: [intersect architecture declarations with optional runtime manifest capabilities]
    # 引数: [self: trainer adapter, architecture: profile key]
    # 戻り値: [tuple[str, ...]: currently supported memory features]
    # }
    def supported_features(self, architecture: str) -> tuple[str, ...]:
        profile = self.profiles.get(architecture)
        if (
            profile is None
            or not self._probe_cache
            or not self._probe_cache.available
            or architecture not in self.supported_models()
        ):
            return ()
        values = profile.features.get(self.trainer_name, ())
        manifest_values = self._manifest.get("features", {}).get(architecture)
        if manifest_values is not None:
            values = tuple(value for value in values if value in manifest_values)
        return tuple(values)

    # {
    # 責務: [target_modules: discover architecture-specific trainer target modules]
    # 処理: [use probed manifest module names or inspect a local safetensors header]
    # 引数: [self: trainer adapter, architecture: profile key, model_path: optional local model]
    # 戻り値: [tuple[str, ...]: verified parameter/module candidates]
    # }
    def target_modules(self, architecture: str, model_path: Path | None = None) -> tuple[str, ...]:
        if (
            not self._probe_cache
            or not self._probe_cache.available
            or architecture not in self.supported_models()
        ):
            return ()
        profile = self.profiles.get(architecture)
        if profile is None:
            return ()
        manifest_modules = self._manifest.get("target_modules", {}).get(architecture)
        if isinstance(manifest_modules, list) and manifest_modules:
            candidates = tuple(value for value in manifest_modules if isinstance(value, str))
        elif model_path is None:
            candidates = profile.target_modules
        else:
            _, shapes = read_safetensors_evidence(model_path)
            candidates = tuple(
                sorted(
                    {
                        name.removesuffix(".weight")
                        for name in shapes
                        if self._matches_profile_target(name, profile)
                    }
                )
            )
        return candidates

    # {
    # 責務: [_matches_profile_target: match local parameter keys to architecture target declarations]
    # 処理: [compare module tokens and wildcard block prefixes without selecting absent parameters]
    # 引数: [name: model tensor key, profile: architecture profile]
    # 戻り値: [bool: true when key belongs to a declared target family]
    # }
    @staticmethod
    def _matches_profile_target(name: str, profile: ArchitectureProfile) -> bool:
        normalized = name.removesuffix(".weight")
        return any(
            token in normalized
            for target in profile.target_modules
            for token in target.split("*")
            if token
        )


# {
# 責務: [SimpleTunerAdapter: coordinate this module responsibility]
# フィールド: [declared values and public collaborators]
# 処理: [follow the documented contract and preserve validated invariants]
# }
class SimpleTunerAdapter(RuntimeTrainerAdapter):
    """SimpleTuner JSON config adapter."""

    trainer_name = "simpletuner"
    trainer_label = "SimpleTuner"
    config_format = "json"
    default_executable = "simpletuner"
    upstream_url = "https://github.com/bghira/SimpleTuner.git"
    required_modules = ("torch",)

    # {
    # 責務: [translate_config: emit SimpleTuner-specific JSON settings]
    # 処理: [map profile, local model, dataset, LoRA and trainer-specific low-VRAM options]
    # 引数: [self: SimpleTuner adapter, spec: validated common training request]
    # 戻り値: [dict[str, object]: SimpleTuner config fields]
    # }
    def translate_config(self, spec: TrainingSpec) -> dict[str, object]:
        super().translate_config(spec)
        profile = self.profiles[spec.architecture]
        return {
            "model_type": profile.family,
            "model_flavour": profile.flavour,
            "pretrained_model_name_or_path": str(spec.base_model),
            "train_data_dir": str(spec.dataset),
            "dataset_type": spec.dataset_kind or profile.dataset_kind,
            "output_dir": str(spec.output),
            "training_method": spec.method.value,
            "network_dim": spec.rank,
            "network_alpha": spec.alpha,
            "target_modules": list(spec.target_modules),
            "max_train_steps": spec.steps,
            "train_batch_size": spec.batch_size,
            "gradient_accumulation_steps": spec.gradient_accumulation,
            "resolution": spec.resolution,
            "train_text_encoder": spec.train_text_encoder,
            "mixed_precision": spec.precision,
            "quantization": spec.quantization.value,
            "gradient_checkpointing": spec.gradient_checkpointing,
            "optimizer_offload": spec.optimizer_offload,
            "cpu_offload": spec.cpu_offload,
            "quantized_text_encoder": spec.quantized_text_encoder,
            "cached_embeddings": spec.cached_embeddings,
            "vae_cache": spec.vae_cache,
            "seed": spec.seed,
        }


# {
# 責務: [AIToolkitAdapter: coordinate this module responsibility]
# フィールド: [declared values and public collaborators]
# 処理: [follow the documented contract and preserve validated invariants]
# }
class AIToolkitAdapter(RuntimeTrainerAdapter):
    """AI Toolkit YAML-compatible configuration adapter."""

    trainer_name = "ai_toolkit"
    trainer_label = "AI Toolkit"
    config_format = "yaml"
    required_files = ("run.py",)
    required_modules = ("torch",)
    upstream_url = "https://github.com/ostris/ai-toolkit.git"

    # {
    # 責務: [translate_config: emit AI Toolkit process and network settings]
    # 処理: [map profile, paired dataset, adapter and memory policy into a YAML-compatible process config]
    # 引数: [self: AI Toolkit adapter, spec: validated common training request]
    # 戻り値: [dict[str, object]: AI Toolkit config mapping]
    # }
    def translate_config(self, spec: TrainingSpec) -> dict[str, object]:
        super().translate_config(spec)
        profile = self.profiles[spec.architecture]
        process = {
            "type": "sd_trainer",
            "training_folder": str(spec.output),
            "device": "cuda:0",
            "model": {
                "name_or_path": str(spec.base_model),
                "architecture_profile": spec.architecture,
                "family": profile.family,
                "quantize": None
                if spec.quantization is Quantization.NONE
                else spec.quantization.value,
                "quantize_text_encoder": spec.quantized_text_encoder,
                "cpu_offload": spec.cpu_offload,
            },
            "network": {
                "type": spec.method.value,
                "linear": spec.rank,
                "linear_alpha": spec.alpha,
                "target_modules": list(spec.target_modules),
            },
            "datasets": [
                {
                    "folder_path": str(spec.dataset),
                    "dataset_type": spec.dataset_kind or profile.dataset_kind,
                    "resolution": spec.resolution,
                    "cache_latents": spec.vae_cache,
                    "cache_text_embeddings": spec.cached_embeddings,
                }
            ],
            "train": {
                "batch_size": spec.batch_size,
                "steps": spec.steps,
                "gradient_accumulation_steps": spec.gradient_accumulation,
                "train_text_encoder": spec.train_text_encoder,
                "gradient_checkpointing": spec.gradient_checkpointing,
                "optimizer_offload": spec.optimizer_offload,
                "mixed_precision": spec.precision,
                "seed": spec.seed,
            },
        }
        return {"name": spec.output.name, "process": [process]}


# {
# 責務: [SdScriptsAdapter: coordinate this module responsibility]
# フィールド: [declared values and public collaborators]
# 処理: [follow the documented contract and preserve validated invariants]
# }
class SdScriptsAdapter(RuntimeTrainerAdapter):
    """sd-scripts TOML and argument-vector adapter."""

    trainer_name = "sd_scripts"
    trainer_label = "sd-scripts"
    config_format = "toml"
    required_files = ("train_network.py",)
    required_modules = ("torch", "accelerate")
    upstream_url = "https://github.com/kohya-ss/sd-scripts.git"

    # {
    # 責務: [translate_config: map common training settings to sd-scripts options]
    # 処理: [emit train_network-compatible TOML/CLI keys without carrying other trainer config]
    # 引数: [self: sd-scripts adapter, spec: validated common training request]
    # 戻り値: [dict[str, object]: flat native training options]
    # }
    def translate_config(self, spec: TrainingSpec) -> dict[str, object]:
        super().translate_config(spec)
        module = "networks.lora" if spec.method is AdapterMethod.LORA else "lycoris.kohya"
        return {
            "pretrained_model_name_or_path": str(spec.base_model),
            "train_data_dir": str(spec.dataset),
            "output_dir": str(spec.output),
            "output_name": spec.output.name,
            "network_module": module,
            "network_dim": spec.rank,
            "network_alpha": spec.alpha,
            "network_args": [
                f"target_modules={','.join(spec.target_modules)}",
                f"algo={spec.method.value}",
            ],
            "max_train_steps": spec.steps,
            "resolution": spec.resolution,
            "train_batch_size": spec.batch_size,
            "gradient_accumulation_steps": spec.gradient_accumulation,
            "train_text_encoder": spec.train_text_encoder,
            "mixed_precision": spec.precision,
            "gradient_checkpointing": spec.gradient_checkpointing,
            "optimizer_type": "AdamW8bit" if spec.optimizer_offload else "AdamW",
            "seed": spec.seed,
        }

    # {
    # 責務: [to_cli: serialize sd-scripts settings to an argv sequence]
    # 処理: [flatten only native option fields without invoking a shell]
    # 引数: [self: sd-scripts adapter, spec: validated training request]
    # 戻り値: [tuple[str, ...]: CLI arguments]
    # }
    def to_cli(self, spec: TrainingSpec) -> tuple[str, ...]:
        arguments = []
        for key, value in self.translate_config(spec).items():
            if isinstance(value, bool):
                if value:
                    arguments.append(f"--{key}")
            elif isinstance(value, list):
                arguments.extend((f"--{key}", *value))
            else:
                arguments.extend((f"--{key}", str(value)))
        return tuple(arguments)
