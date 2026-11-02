# LoRA Training Doctor

`comfyui_support_tools.shared.training_doctor` evaluates saved LoRA checkpoints against one repeatable validation plan. The trainer emits checkpoint paths and optional `TrainingTracePoint` records; a `ValidationEvaluator` renders each sample with the fixed seed, sampler, inference-step sweep and resolution sweep and returns `ImageEvidence`. The image-quality adapter supplies normalized fidelity, controllability, image quality, base preservation, trigger-free leakage, training-image similarity and cross-seed diversity measurements. Missing measurements must not be guessed.

`fixed_validation_plan` supplies character, style, object and multi-concept prompt matrices. It includes trigger-present and trigger-absent cases; optional trigger candidates and recommended tags expand the sweep. Checkpoints are compared across the same cases and inference strengths. Per-task balanced weights and a fidelity-priority preset are available, and callers may pass custom `ScoreWeights`.

The report ranks checkpoint/strength/trigger combinations, records axis scores and preview paths, identifies the first multi-signal overfit onset, and explains plateau or overfit early-stop decisions. When a trainer stop callback is supplied, the doctor requests the stop after the configured consecutive rounds. `restore_best` invokes an explicit trainer-specific rollback callback. Reports are atomically saved as bounded JSON and can be loaded to resume review or rollback. `publish_prompt_metadata` sends the recommended trigger, tags, checkpoint and strength through a #240-compatible sink callback. The evaluator contract accepts quality evidence from a #20 quality evaluator.

```python
from pathlib import Path
from comfyui_support_tools.shared.training_doctor import (
    CheckpointRef,
    TrainingDoctorApplication,
    ValidationTask,
    fixed_validation_plan,
    save_report,
)

plan = fixed_validation_plan(
    ValidationTask.CHARACTER,
    trigger="mira_style",
    trigger_candidates=("mira_style", "mira_v2"),
    recommended_tags=("long hair", "blue coat"),
)
report = TrainingDoctorApplication(evaluator, trainer.request_stop).evaluate_checkpoints(
    [CheckpointRef(Path("checkpoint-100.safetensors"), 100)], plan
)
save_report(report, Path("training-doctor-report.json"))
```

The package does not invent image metrics or install a model/trainer. A local generation adapter and measured metric providers must implement `ValidationEvaluator`; use a trainer-specific callback for stopping and rollback. This checkout has no live trainer/model or ComfyUI evaluator configured, so integration against actual generated samples remains unverified. No user model or prompt data is bundled.
