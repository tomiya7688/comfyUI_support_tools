"""PMX Model Doctor contracts, parser, and non-destructive repair service."""

from .contracts import (
    BinaryPatch,
    DiagnosticSeverity,
    ModelDoctorReport,
    MotionSuite,
    PmxDiagnostic,
    RepairCandidate,
    RepairEvaluation,
)
from .pmx_parser import PmxFormatError, parse_pmx, parse_pmx_bytes
from .service import ModelDoctorService, PatchConflictError, apply_binary_patches

__all__ = [
    "BinaryPatch",
    "DiagnosticSeverity",
    "ModelDoctorReport",
    "ModelDoctorService",
    "MotionSuite",
    "PatchConflictError",
    "PmxDiagnostic",
    "PmxFormatError",
    "RepairCandidate",
    "RepairEvaluation",
    "apply_binary_patches",
    "parse_pmx",
    "parse_pmx_bytes",
]
