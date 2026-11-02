# Txt2Img Capability Router

The Random Image “Capability Router” selects candidates from the requested use case, installed ComfyUI models and workflows, free VRAM/RAM, commercial-use requirements, and offline requirements. It is disabled by default. When enabled, it reads ComfyUI `/system_stats` and only considers candidates for which both the model and matching workflow are installed. The selected profile, use case, workflow, observed memory, selection reason, and exclusion reasons are written to the image `.generation.json` sidecar.

`GenerationCapability` declares model aliases, use cases, prompt policy, workflow ID, features, resource requirements, license evidence, and lifecycle. `GenerationIntent` captures runtime constraints. `CapabilityRouter` filters hard constraints before returning an explainable ranking. New families and use cases can be added through descriptors; unknown capabilities are not inferred.

When commercial use is required, a profile must explicitly allow it and set `verified=True`. Built-in weight licenses have not been individually verified, so commercial routing currently fails closed. A repository code license does not establish a model-weight license. Unknown resource requirements are normally excluded. Users can explicitly allow profiles with unknown memory requirements, but Low-VRAM use always excludes unknown VRAM/RAM requirements.

Workflow JSON files are not bundled. A local workflow whose filename stem matches the profile `workflow_profile_id` is required. If a model or workflow is missing, routing stops with an explanation instead of silently falling back to another use case. Descriptive quality tiers are metadata, not measured results.

`EvaluatorRegistry` registers named, use-case-specific metrics. `run_cross_family_best_of_n` can compare different model families generated from the same prompt using a selected metric. The benchmark matrix only defines comparison prompts; it does not contain model scores or recommendations. The project does not yet provide production image-quality evaluators, so UI-driven automatic Best-of-N comparison and real-model score collection are not available. Recommendations are not updated using invented scores.

Declared candidates include FLUX.2 Klein/Dev, Qwen Image 2.1, HunyuanImage 3 Instruct, HiDream-I1, Sana Sprint, and SDXL anime families. Unverified VRAM/RAM values, workflow compatibility, and weight licenses remain marked as unverified. Checkpoint classification uses declared aliases; unknown or ambiguous names are not automatically selected.
