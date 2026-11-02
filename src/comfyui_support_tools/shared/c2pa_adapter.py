"""Optional adapter around the official C2PA Python SDK."""

import importlib
import json
import mimetypes
import os
import tempfile
from collections.abc import Callable
from contextlib import nullcontext
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from comfyui_support_tools.shared.transparency_contracts import (
    MediaClassification,
    ModelDisclosure,
    ProvenanceRecord,
    TransparencySettings,
)


# {
# 責務: [ C2paUnavailableError: 状態と振る舞いをまとめる ]
# フィールド: [主要な状態: クラスが管理する状態]
# }
class C2paUnavailableError(RuntimeError):
    pass


# {
# 責務: [ C2paSigningError: 状態と振る舞いをまとめる ]
# フィールド: [主要な状態: クラスが管理する状態]
# }
class C2paSigningError(RuntimeError):
    pass


# {
# 責務: [ C2paVerificationError: 状態と振る舞いをまとめる ]
# フィールド: [主要な状態: クラスが管理する状態]
# }
class C2paVerificationError(RuntimeError):
    pass


# {
# 責務: [ SignerProvider: 状態と振る舞いをまとめる ]
# フィールド: [主要な状態: クラスが管理する状態]
# }
class SignerProvider(Protocol):
    # {
    # 責務: [ create_signer: 入力を処理して結果を返す ]
    # 処理: [ 1: 入力を検証・処理する, 2: 結果を返す ]
    # 引数: [self, c2pa_module]
    # 戻り値: [処理結果]
    # }
    def create_signer(self, c2pa_module):
        """Return an SDK signer backed by a secure user-selected key store."""


# {
# 責務: [ PemFileSignerProvider: 状態と振る舞いをまとめる ]
# フィールド: [主要な状態: クラスが管理する状態]
# }
class PemFileSignerProvider:
    """Adapter for user-managed PEM credentials; key bytes are never persisted."""

    # {
    # 責務: [ __init__: 入力を処理して結果を返す ]
    # 処理: [ 1: 入力を検証・処理する, 2: 結果を返す ]
    # 引数: [self, certificate_path, private_key_path, algorithm, timestamp_authority_url]
    # 戻り値: [処理結果]
    # }
    def __init__(
        self,
        certificate_path: str | Path,
        private_key_path: str | Path,
        *,
        algorithm: str | None = None,
        timestamp_authority_url: str | None = None,
    ):
        if algorithm is not None and algorithm not in {
            "ES256",
            "ES384",
            "ES512",
            "PS256",
            "PS384",
            "PS512",
            "ED25519",
        }:
            raise ValueError("unsupported C2PA signing algorithm")
        self._certificate_path = Path(certificate_path).expanduser()
        self._private_key_path = Path(private_key_path).expanduser()
        self._algorithm = algorithm
        self._timestamp_authority_url = timestamp_authority_url

    # {
    # 責務: [ create_signer: 入力を処理して結果を返す ]
    # 処理: [ 1: 入力を検証・処理する, 2: 結果を返す ]
    # 引数: [self, c2pa_module]
    # 戻り値: [処理結果]
    # }
    def create_signer(self, c2pa_module):
        try:
            certificate = self._certificate_path.read_bytes()
            private_key = self._private_key_path.read_bytes()
            algorithm = self._algorithm or self._infer_algorithm(certificate, private_key)
            info = c2pa_module.C2paSignerInfo(
                alg=getattr(c2pa_module.C2paSigningAlg, algorithm),
                sign_cert=certificate,
                private_key=private_key,
                ta_url=(
                    self._timestamp_authority_url.encode("utf-8")
                    if self._timestamp_authority_url
                    else None
                ),
            )
            return c2pa_module.Signer.from_info(info)
        except OSError as exc:
            # Paths and SDK exception text can reveal private deployment details.
            raise C2paSigningError("C2PA signing credentials are unavailable") from exc
        except Exception as exc:
            raise C2paSigningError("C2PA signer could not be initialized") from exc

    # {
    # 責務: [ _infer_algorithm: 入力を処理して結果を返す ]
    # 処理: [ 1: 入力を検証・処理する, 2: 結果を返す ]
    # 引数: [certificate, private_key]
    # 戻り値: [処理結果]
    # }
    @staticmethod
    def _infer_algorithm(certificate: bytes, private_key: bytes) -> str:
        from cryptography import x509
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import ec, ed25519, rsa

        key = serialization.load_pem_private_key(private_key, password=None)
        signing_certificate = x509.load_pem_x509_certificate(certificate)
        key_bytes = key.public_key().public_bytes(
            serialization.Encoding.DER,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        cert_bytes = signing_certificate.public_key().public_bytes(
            serialization.Encoding.DER,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        if key_bytes != cert_bytes:
            raise C2paSigningError("C2PA certificate and private key do not match")
        if isinstance(key, rsa.RSAPrivateKey):
            return "PS256"
        if isinstance(key, ec.EllipticCurvePrivateKey):
            algorithm = {
                "secp256r1": "ES256",
                "secp384r1": "ES384",
                "secp521r1": "ES512",
            }.get(key.curve.name)
            if algorithm:
                return algorithm
        if isinstance(key, ed25519.Ed25519PrivateKey):
            return "ED25519"
        raise C2paSigningError("unsupported C2PA private key algorithm")


# {
# 責務: [ C2paVerificationReport: 状態と振る舞いをまとめる ]
# フィールド: [主要な状態: クラスが管理する状態]
# }
@dataclass(frozen=True)
class C2paVerificationReport:
    manifest_present: bool
    validation_state: str | None
    digital_source_type: str | None
    ingredient_count: int
    signature_valid: bool
    trusted: bool
    ai_disclosure_present: bool
    ai_disclosure_valid: bool

    # {
    # 責務: [ verified: 入力を処理して結果を返す ]
    # 処理: [ 1: 入力を検証・処理する, 2: 結果を返す ]
    # 引数: [self]
    # 戻り値: [処理結果]
    # }
    @property
    def verified(self) -> bool:
        return (
            self.manifest_present
            and self.validation_state == "Valid"
            and self.signature_valid
            and self.trusted
            and bool(self.digital_source_type)
            and self.ai_disclosure_valid
        )

    # {
    # 責務: [ to_dict: 入力を処理して結果を返す ]
    # 処理: [ 1: 入力を検証・処理する, 2: 結果を返す ]
    # 引数: [self]
    # 戻り値: [処理結果]
    # }
    def to_dict(self) -> dict[str, object]:
        return {
            "manifest_present": self.manifest_present,
            "validation_state": self.validation_state,
            "digital_source_type": self.digital_source_type,
            "ingredient_count": self.ingredient_count,
            "signature_valid": self.signature_valid,
            "trusted": self.trusted,
            "ai_disclosure_present": self.ai_disclosure_present,
            "ai_disclosure_valid": self.ai_disclosure_valid,
            "verified": self.verified,
        }


# {
# 責務: [ C2paAdapter: 状態と振る舞いをまとめる ]
# フィールド: [主要な状態: クラスが管理する状態]
# }
class C2paAdapter:
    """Sign and inspect media without exposing keys or legal conclusions."""

    _SOURCE_TYPES = {
        MediaClassification.GENERATED: "trainedAlgorithmicMedia",
        MediaClassification.AI_MODIFIED: "compositeWithTrainedAlgorithmicMedia",
        MediaClassification.CONVENTIONAL_EDIT: "humanEdits",
    }
    _MODEL_TYPES = {
        "c2pa.types.model",
        "c2pa.types.model.caffe",
        "c2pa.types.model.caffe2",
        "c2pa.types.model.catboost",
        "c2pa.types.model.coreml",
        "c2pa.types.model.flax",
        "c2pa.types.model.huggingface.transformers",
        "c2pa.types.model.jax",
        "c2pa.types.model.keras",
        "c2pa.types.model.lightgbm",
        "c2pa.types.model.ml_net",
        "c2pa.types.model.mxnet",
        "c2pa.types.model.onnx",
        "c2pa.types.model.openvino",
        "c2pa.types.model.openvino.parameter",
        "c2pa.types.model.openvino.topology",
        "c2pa.types.model.paddle",
        "c2pa.types.model.pytorch",
        "c2pa.types.model.sklearn",
        "c2pa.types.model.tensorflow",
        "c2pa.types.model.tensorrt",
        "c2pa.types.model.tflite",
        "c2pa.types.model.torchscript",
        "c2pa.types.model.xgboost",
    }

    # {
    # 責務: [ __init__: 入力を処理して結果を返す ]
    # 処理: [ 1: 入力を検証・処理する, 2: 結果を返す ]
    # 引数: [self, context_factory]
    # 戻り値: [処理結果]
    # }
    def __init__(self, context_factory: Callable | None = None):
        """`context_factory(sdk)` may provide configured verification trust anchors."""
        self._context_factory = context_factory

    # {
    # 責務: [ _context: 入力を処理して結果を返す ]
    # 処理: [ 1: 入力を検証・処理する, 2: 結果を返す ]
    # 引数: [self, sdk]
    # 戻り値: [処理結果]
    # }
    def _context(self, sdk):
        return self._context_factory(sdk) if self._context_factory else nullcontext(None)

    # {
    # 責務: [ _sdk: 入力を処理して結果を返す ]
    # 処理: [ 1: 入力を検証・処理する, 2: 結果を返す ]
    # 引数: [なし]
    # 戻り値: [処理結果]
    # }
    @staticmethod
    def _sdk():
        try:
            return importlib.import_module("c2pa")
        except (ImportError, OSError) as exc:
            raise C2paUnavailableError(
                "C2PA support requires the optional c2pa-python package for this platform"
            ) from exc

    # {
    # 責務: [ sign: 入力を処理して結果を返す ]
    # 処理: [ 1: 入力を検証・処理する, 2: 結果を返す ]
    # 引数: [self, source_path, destination_path, record, signer_provider, settings, overwrite]
    # 戻り値: [処理結果]
    # }
    def sign(
        self,
        source_path: str | Path,
        destination_path: str | Path,
        record: ProvenanceRecord,
        signer_provider: SignerProvider,
        settings: TransparencySettings,
        *,
        overwrite: bool = False,
    ) -> C2paVerificationReport:
        source = Path(source_path)
        destination = Path(destination_path)
        if source.resolve() == destination.resolve():
            raise ValueError("C2PA signing must not overwrite the source asset")
        if source.is_symlink() or not source.is_file():
            raise ValueError("C2PA source must be a regular file")
        if destination.is_symlink():
            raise ValueError("C2PA destination must not be a symbolic link")
        if destination.exists() and not overwrite:
            raise FileExistsError(f"C2PA destination already exists: {destination.name}")
        if record.classification not in self._SOURCE_TYPES:
            raise ValueError("C2PA signing requires an explicit media classification")
        if not settings.enabled or not settings.sign_c2pa:
            raise ValueError("C2PA signing requires explicit Transparency Assist and C2PA opt-in")

        sdk = self._sdk()
        mime_type, _ = mimetypes.guess_type(source.name)
        if not mime_type or mime_type not in sdk.Builder.get_supported_mime_types():
            raise ValueError(f"C2PA SDK does not support media format: {source.suffix.lower()}")
        source_type = self._SOURCE_TYPES[record.classification]
        if record.c2pa_model_type and record.c2pa_model_type not in self._MODEL_TYPES:
            raise ValueError("C2PA model type must use the C2PA 2.4 model vocabulary")
        intent = (
            sdk.C2paBuilderIntent.CREATE
            if record.classification is MediaClassification.GENERATED
            else sdk.C2paBuilderIntent.EDIT
        )
        digital_source_type = {
            "trainedAlgorithmicMedia": sdk.C2paDigitalSourceType.TRAINED_ALGORITHMIC_MEDIA,
            "compositeWithTrainedAlgorithmicMedia": sdk.C2paDigitalSourceType.COMPOSITE_WITH_TRAINED_ALGORITHMIC_MEDIA,
            "humanEdits": sdk.C2paDigitalSourceType.HUMAN_EDITS,
        }[source_type]

        destination.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            prefix=f".{destination.stem}.",
            suffix=destination.suffix,
            dir=destination.parent,
            delete=False,
        ) as staged_file:
            staged = Path(staged_file.name)
        try:
            manifest = {
                "claim_generator_info": [
                    {
                        "name": record.application,
                        "version": record.application_version,
                    }
                ],
                "title": destination.name,
            }
            ai_disclosure = self.ai_disclosure_assertion(record, settings)
            if ai_disclosure is not None:
                manifest["assertions"] = [ai_disclosure]
            with self._context(sdk) as context:
                with signer_provider.create_signer(sdk) as signer:
                    with sdk.Builder(manifest, context=context) as builder:
                        builder.set_intent(intent, digital_source_type)
                        existing_ingredient = self._has_manifest(sdk, source, context=context)
                        if (
                            existing_ingredient
                            or record.classification is not MediaClassification.GENERATED
                        ):
                            with source.open("rb") as ingredient_stream:
                                builder.add_ingredient(
                                    {"title": source.name, "relationship": "parentOf"},
                                    mime_type,
                                    ingredient_stream,
                                )
                        for action in record.actions:
                            if (
                                record.classification is MediaClassification.GENERATED
                                and action.operation in {"generation", "txt2img"}
                            ):
                                continue
                            action_data = {
                                "action": "c2pa.edited",
                                "description": action.operation,
                                "when": action.timestamp,
                                "softwareAgent": (
                                    f"{action.application}/{action.application_version}"
                                ),
                            }
                            if action.ai_involvement:
                                action_data["digitalSourceType"] = (
                                    "http://cv.iptc.org/newscodes/digitalsourcetype/"
                                    "compositeWithTrainedAlgorithmicMedia"
                                )
                            builder.add_action(action_data)
                        builder.sign_file(source, staged, signer)

                report = self.verify(
                    staged,
                    expected_source_type=source_type,
                    expected_ai_disclosure=(
                        record.classification
                        in {
                            MediaClassification.GENERATED,
                            MediaClassification.AI_MODIFIED,
                        }
                    ),
                    expected_ingredient=(
                        record.classification is not MediaClassification.GENERATED
                    ),
                    context=context,
                )
            if not report.manifest_present or not report.digital_source_type:
                raise C2paVerificationError(
                    "C2PA output did not contain the expected signed assertions"
                )
            if (
                settings.verify_export
                and not report.verified
                and settings.verification_failure_policy.value == "error"
            ):
                raise C2paVerificationError(
                    "C2PA signature is not trusted by the configured verification trust store"
                )
            if overwrite:
                os.replace(staged, destination)
            else:
                os.link(staged, destination)
                staged.unlink(missing_ok=True)
            return report
        except C2paVerificationError:
            raise
        except Exception as exc:
            # SDK errors can include signer/configuration details. Do not expose them in logs.
            raise C2paSigningError("C2PA signing failed; no output was committed") from exc
        finally:
            staged.unlink(missing_ok=True)

    # {
    # 責務: [ _has_manifest: 入力を処理して結果を返す ]
    # 処理: [ 1: 入力を検証・処理する, 2: 結果を返す ]
    # 引数: [sdk, source, context]
    # 戻り値: [処理結果]
    # }
    @staticmethod
    def _has_manifest(sdk, source: Path, *, context=None) -> bool:
        try:
            with sdk.Reader(source, context=context) as reader:
                return bool(reader.is_embedded())
        except sdk.C2paError.ManifestNotFound:
            return False
        except Exception as exc:
            raise C2paVerificationError(
                "existing C2PA provenance could not be inspected; refusing to discard it"
            ) from exc

    # {
    # 責務: [ verify: 入力を処理して結果を返す ]
    # 処理: [ 1: 入力を検証・処理する, 2: 結果を返す ]
    # 引数: [self, media_path, expected_source_type, expected_ai_disclosure, expected_ingredient, context]
    # 戻り値: [処理結果]
    # }
    def verify(
        self,
        media_path: str | Path,
        *,
        expected_source_type: str | None = None,
        expected_ai_disclosure: bool | None = None,
        expected_ingredient: bool = False,
        context=None,
    ) -> C2paVerificationReport:
        sdk = self._sdk()
        path = Path(media_path)
        if path.is_symlink() or not path.is_file():
            raise ValueError("C2PA verification requires a regular file")
        try:
            with self._context(sdk) if context is None else nullcontext(context) as active_context:
                with sdk.Reader(path, context=active_context) as reader:
                    return self._read_report(
                        reader,
                        expected_source_type,
                        expected_ai_disclosure,
                        expected_ingredient,
                    )
        except sdk.C2paError.ManifestNotFound:
            return C2paVerificationReport(False, None, None, 0, False, False, False, False)
        except C2paVerificationError:
            raise
        except Exception as exc:
            raise C2paVerificationError("C2PA manifest could not be parsed or verified") from exc

    # {
    # 責務: [ _read_report: 入力を処理して結果を返す ]
    # 処理: [ 1: 入力を検証・処理する, 2: 結果を返す ]
    # 引数: [reader, expected_source_type, expected_ai_disclosure, expected_ingredient]
    # 戻り値: [処理結果]
    # }
    @staticmethod
    def _read_report(reader, expected_source_type, expected_ai_disclosure, expected_ingredient):
        if not reader.is_embedded():
            return C2paVerificationReport(False, None, None, 0, False, False, False, False)
        manifest_store = json.loads(reader.json())
        active_label = manifest_store.get("active_manifest")
        manifests = manifest_store.get("manifests", {})
        active_manifest = manifests.get(active_label, {}) if active_label else {}
        assertion_labels = {
            assertion.get("label") for assertion in active_manifest.get("assertions", [])
        }
        ai_disclosure_present = "c2pa.ai-disclosure" in assertion_labels
        ai_assertions = [
            assertion
            for assertion in active_manifest.get("assertions", [])
            if assertion.get("label") == "c2pa.ai-disclosure"
        ]
        ai_disclosure_valid = all(
            isinstance(assertion.get("data"), dict)
            and assertion["data"].get("modelType") in C2paAdapter._MODEL_TYPES
            and (
                assertion["data"].get("contentProfile", {}).get("humanOversightLevel")
                in {"fully_autonomous", "prompt_guided", "human_validated"}
                if "contentProfile" in assertion["data"]
                else True
            )
            for assertion in ai_assertions
        )
        source_types = []
        for assertion in active_manifest.get("assertions", []):
            if assertion.get("label") in {"c2pa.actions", "c2pa.actions.v2"}:
                actions = assertion.get("data", {}).get("actions", [])
                source_types.extend(
                    action.get("digitalSourceType", "").rsplit("/", 1)[-1]
                    for action in actions
                    if action.get("digitalSourceType")
                )
        source_type = source_types[-1] if source_types else None
        ingredients = active_manifest.get("ingredients", [])
        state = reader.get_validation_state()
        results = reader.get_validation_results() or {}
        active_results = results.get("activeManifest", {})
        successes = active_results.get("success", [])
        failures = active_results.get("failure", [])
        signature_valid = any(item.get("code") == "claimSignature.validated" for item in successes)
        trusted = not failures
        report = C2paVerificationReport(
            True,
            state,
            source_type,
            len(ingredients),
            signature_valid,
            trusted,
            ai_disclosure_present,
            ai_disclosure_valid,
        )
        if expected_source_type is not None and expected_source_type not in source_types:
            raise C2paVerificationError("C2PA output is missing the expected IPTC source type")
        ai_source_types = {
            "trainedAlgorithmicMedia",
            "compositeWithTrainedAlgorithmicMedia",
        }
        requires_ai_disclosure = (
            expected_ai_disclosure
            if expected_ai_disclosure is not None
            else bool(ai_source_types.intersection(source_types))
        )
        if requires_ai_disclosure and not ai_disclosure_present:
            raise C2paVerificationError(
                "C2PA output is missing the expected AI disclosure assertion"
            )
        if ai_disclosure_present and not ai_disclosure_valid:
            raise C2paVerificationError(
                "C2PA AI disclosure assertion does not follow the C2PA 2.4 schema"
            )
        if expected_ingredient and not ingredients:
            raise C2paVerificationError("C2PA edit output is missing its source ingredient")
        return report

    # {
    # 責務: [ _human_oversight: 入力を処理して結果を返す ]
    # 処理: [ 1: 入力を検証・処理する, 2: 結果を返す ]
    # 引数: [record]
    # 戻り値: [処理結果]
    # }
    @staticmethod
    def _human_oversight(record: ProvenanceRecord) -> str | None:
        values = {action.user_oversight for action in record.actions}
        if values.intersection({"human_reviewed", "human_edited"}):
            return "human_validated"
        if "prompt_guided" in values:
            return "prompt_guided"
        if values and values == {"fully_automated"}:
            return "fully_autonomous"
        return None

    # {
    # 責務: [ ai_disclosure_assertion: 入力を処理して結果を返す ]
    # 処理: [ 1: 入力を検証・処理する, 2: 結果を返す ]
    # 引数: [cls, record, settings]
    # 戻り値: [処理結果]
    # }
    @classmethod
    def ai_disclosure_assertion(
        cls, record: ProvenanceRecord, settings: TransparencySettings
    ) -> dict[str, object] | None:
        """Build the C2PA 2.4 AI disclosure assertion with its required modelType."""
        if record.classification not in {
            MediaClassification.GENERATED,
            MediaClassification.AI_MODIFIED,
        }:
            return None
        model_type = record.c2pa_model_type or "c2pa.types.model"
        if model_type not in cls._MODEL_TYPES:
            raise ValueError("C2PA model type must use the C2PA 2.4 model vocabulary")
        data: dict[str, object] = {"modelType": model_type}
        if settings.model_disclosure is ModelDisclosure.FAMILY and record.model_family:
            data["modelName"] = record.model_family
        elif settings.model_disclosure in {
            ModelDisclosure.MODEL_ID,
            ModelDisclosure.MODEL_ID_AND_VERSION,
        }:
            if record.model_id:
                data["modelIdentifier"] = record.model_id
            if settings.model_disclosure is ModelDisclosure.MODEL_ID_AND_VERSION:
                model_name = record.model_family or record.model_id
                if model_name and record.model_version:
                    data["modelName"] = f"{model_name} {record.model_version}"
                elif model_name:
                    data["modelName"] = model_name
        oversight = cls._human_oversight(record)
        if oversight:
            data["contentProfile"] = {"humanOversightLevel": oversight}
        return {"label": "c2pa.ai-disclosure", "data": data}
