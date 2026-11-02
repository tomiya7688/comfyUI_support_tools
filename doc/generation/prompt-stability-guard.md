# Prompt Stability Guard

The shared `prompt_stability` capability analyzes prompt structure, selected
SFW/NSFW quality mode, backend/model family, LoRA roles/weights, and optional
failure priors. Policies are registered by content mode, model family, and
backend. The planner supports suggest-only, auto-apply, and bounded evaluate /
retry plans, plus prompt, negative, configuration and candidate-budget adapters.
User locks, disabled adjustment keys, original-prompt override, and finite
budgets are applied before a plan is returned. The append-only local history
stores a prompt hash and outcome metadata, never raw prompt text.

The Random Image tab exposes opt-in SFW/NSFW mode checkboxes, apply mode, budget,
and a preview toggle. Automatic candidate expansion submits additional backend
requests and saves each output. The current built-in image feedback is limited
to decode and near-uniform-color detection; full anatomy, identity, and style
evaluation, backend-specific config rewrites, and local repair still require
host adapters. The core exposes those adapter seams and does not claim that a
text-only heuristic can guarantee image quality. Guard defaults to disabled,
and suggest-only leaves generation inputs unchanged.
