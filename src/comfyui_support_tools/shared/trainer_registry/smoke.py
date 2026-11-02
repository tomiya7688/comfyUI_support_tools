"""Bounded smoke training gate that prevents full runs after failed probes."""

from __future__ import annotations

import subprocess
import tempfile
from collections.abc import Callable
from pathlib import Path

from .adapters import RuntimeTrainerAdapter
from .contracts import SmokeTestResult, TrainingSpec


# {
# 責務: [SmokeTestRunner: coordinate this module responsibility]
# フィールド: [declared values and public collaborators]
# 処理: [follow the documented contract and preserve validated invariants]
# }
class SmokeTestRunner:
    """Run an explicitly declared trainer smoke command and verify artifacts."""

    # {
    # 責務: [__init__: bound smoke step count and execution timeout]
    # 処理: [reject unsafe unbounded smoke settings]
    # 引数: [steps: short training steps, timeout_seconds: maximum local process time]
    # 戻り値: [None: runner configured]
    # }
    def __init__(self, steps: int = 4, timeout_seconds: int = 1800) -> None:
        if not 1 <= steps <= 8 or timeout_seconds <= 0 or timeout_seconds > 7200:
            raise ValueError("smoke test must use 1..8 steps and a timeout within 1..7200 seconds")
        self.steps = steps
        self.timeout_seconds = timeout_seconds

    # {
    # 責務: [run: validate then run one short trainer-specific smoke job]
    # 処理: [write temporary config, execute without a shell, and require checkpoint plus sample outputs]
    # 引数: [adapter: probed trainer adapter, spec: common training request]
    # 戻り値: [SmokeTestResult: pass/fail with evidence paths and bounded output]
    # }
    def run(self, adapter: RuntimeTrainerAdapter, spec: TrainingSpec) -> SmokeTestResult:
        probe = adapter.probe()
        validation = adapter.validate_config(spec)
        if not validation.valid:
            return SmokeTestResult(
                False,
                adapter.trainer_name,
                probe.version,
                self.steps,
                None,
                None,
                "",
                "; ".join(validation.errors),
            )
        spec.output.parent.mkdir(parents=True, exist_ok=True)
        if spec.output.parent.is_symlink() or spec.output.is_symlink():
            raise ValueError("smoke output path cannot use a symlink")
        root = Path(tempfile.mkdtemp(prefix=f".{spec.output.name}.smoke-", dir=spec.output.parent))
        output = root / "output"
        output.mkdir()
        smoke_spec = TrainingSpec(**{**vars(spec), "steps": self.steps, "output": output})
        config = adapter.translate_config(smoke_spec)
        config_path = root / f"config.{adapter.config_format}"
        config_path.write_text(adapter.serialize_config(config), encoding="utf-8")
        command = adapter.smoke_command(config_path, self.steps, output)
        if not command:
            return SmokeTestResult(
                False,
                adapter.trainer_name,
                probe.version,
                self.steps,
                None,
                None,
                "",
                "trainer has no explicit smoke-command capability",
            )
        try:
            result = subprocess.run(
                command,
                cwd=adapter.trainer_root,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                check=False,
                shell=False,
            )
        except subprocess.TimeoutExpired as error:
            output_text = (
                (error.stdout or b"").decode(errors="replace")
                if isinstance(error.stdout, bytes)
                else (error.stdout or "")
            )
            return SmokeTestResult(
                False,
                adapter.trainer_name,
                probe.version,
                self.steps,
                None,
                None,
                output_text[-4000:],
                "smoke training timed out",
            )
        except OSError as error:
            return SmokeTestResult(
                False,
                adapter.trainer_name,
                probe.version,
                self.steps,
                None,
                None,
                "",
                f"smoke process failed: {type(error).__name__}",
            )
        checkpoints = tuple(
            path
            for path in output.rglob("*")
            if path.is_file()
            and path.suffix.casefold() in {".safetensors", ".ckpt", ".pt"}
            and path.stat().st_size > 0
        )
        samples = tuple(
            path
            for path in output.rglob("*")
            if path.is_file()
            and path.suffix.casefold() in {".png", ".webp", ".jpg", ".jpeg"}
            and path.stat().st_size > 0
        )
        passed = result.returncode == 0 and bool(checkpoints) and bool(samples)
        reason = (
            "smoke training produced a checkpoint and sample"
            if passed
            else "smoke training must succeed and produce both checkpoint and sample"
        )
        evidence = (result.stdout + "\n" + result.stderr)[-4000:]
        checkpoint = checkpoints[0] if checkpoints else None
        sample = samples[0] if samples else None
        return SmokeTestResult(
            passed,
            adapter.trainer_name,
            probe.version,
            self.steps,
            checkpoint,
            sample,
            evidence,
            reason,
        )


# {
# 責務: [SmokeGatedTraining: coordinate this module responsibility]
# フィールド: [declared values and public collaborators]
# 処理: [follow the documented contract and preserve validated invariants]
# }
class SmokeGatedTraining:
    """Require a passing smoke result before invoking the full-training callback."""

    # {
    # 責務: [__init__: bind one smoke runner]
    # 処理: [retain injected local runner]
    # 引数: [runner: bounded trainer smoke runner]
    # 戻り値: [None: gate ready]
    # }
    def __init__(self, runner: SmokeTestRunner) -> None:
        self.runner = runner

    # {
    # 責務: [start: gate full training on successful model-load and sample smoke]
    # 処理: [return immediately on smoke failure and call full trainer only after evidence passes]
    # 引数: [adapter: selected trainer, spec: full training request, start_full_training: deferred training callback]
    # 戻り値: [tuple[SmokeTestResult, object | None]: smoke evidence and optional full run result]
    # }
    def start(
        self,
        adapter,
        spec,
        start_full_training: Callable[[RuntimeTrainerAdapter, TrainingSpec], object],
    ):
        smoke = self.runner.run(adapter, spec)
        if not smoke.passed:
            return smoke, None
        return smoke, start_full_training(adapter, spec)
