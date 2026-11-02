# Fast / Low-VRAM Txt2Img

[日本語](fast_generation.md)

The Random Image ComfyUI path can treat FLUX.2 Klein 4B Distilled and Sana checkpoints as declarative profiles and optionally route using GPU VRAM/RAM from `system_stats`, precision support declared by the user, and locally installed model names. Quality remains the default; manual model selection and explicit workflow model overrides are respected. Profile few-step settings apply only when Fast or Balanced is selected.

FLUX.2 Klein 4B Base has a separate descriptor with a LoRA fine-tuning capability and is excluded from automatic Fast routing.

The native Klein profile declares an 8 GiB VRAM minimum, Sana Sprint 8 GiB, and Sana 12 GiB, each with 1 GiB of safety headroom. Quantized variants have separate estimated VRAM requirements and are candidates on an 8 GiB GPU only when a fitting quantized model is installed. Automatic selection checks total and currently free VRAM/RAM reported by ComfyUI. These values are provisional requirements for the target hardware described in the issue, not measured benchmarks or generation guarantees. Selection stops when free memory cannot be observed or no installed model fits. Quantized files are identified only by explicit `fp16`, `bf16`, `fp8`, `int8`, or `int4` filename markers, and are eligible only when the user declares that precision supported in the UI.

Each generation stores elapsed seconds, sampled peak VRAM when ComfyUI `system_stats` can be polled every 500 ms, VRAM/RAM capacities, model, profile, and precision in the image sidecar `.generation.json` and `generation_history.jsonl`. Polling can miss brief peaks, and missing measurements remain `null`. Shared API memory includes other processes using the same GPU.

The shared package includes callback-based candidate generation, Top-K selection, optional HQ rerendering, and history aggregation for latency/VRAM/quality measurements. This change does not include distributable Klein/Sana ComfyUI workflow JSON, workflow-node compatibility probing, GUI candidate comparison or automatic HQ handoff, a prompt-alignment evaluator, or real-model speed/VRAM/artifact benchmarks. The current UI requires an existing ComfyUI workflow and locally installed models. Profile step counts and VRAM requirements are provisional and do not represent quality comparisons.
