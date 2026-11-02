# Touka Real-Input Hard-case Loop

`shared.hard_case_loop` accumulates real-input failures and human choices locally, then supports hard-case grouping, representative selection, active-learning reference manifests, feedback calibration, and fixed regression comparisons without sending images off-device.

## Records and feedback

`HardCaseRecord` (`touka-hard-case.v1`) stores the input SHA-256 and local path reference, image/video/burst metadata, material and conditions, candidate raw scores and confidence, confidence-map references, selected/rejected/preferred candidates, failure tags, runtime / VRAM, model/config, optional GT / weak labels, and multi-axis features. It does not copy image bytes into the record. `HardCaseStore` persists versioned JSON records in a caller-selected SQLite file. `record_feedback` stores explicit user-preferred and rejected candidates.

## Hardness, clusters, and samples

`extract_hard_case_features` computes low-confidence area from a confidence map and keeps candidate disagreement, reconstruction residual, temporal disagreement, and artifact score as separate axes. Current clustering is an explainable deterministic baseline using feature-centroid distance plus material/failure-tag compatibility; it does not use image embeddings or a learned clustering model. `cluster_hard_cases` returns the record closest to each centroid. `select_active_learning_samples` prioritizes rare tags/materials, generator disagreement, hardness, and high-confidence candidates rejected by the user.

## Calibration and regression

`calibrate_confidence` labels only selected candidates with explicit feedback and reports ECE, reliability bins, and high-confidence error IDs. Unlabeled entries are not treated as correct, and raw scores are not probabilities. Mark records with `in_regression_set` and pass them to `run_regression_set`; an injected evaluator reruns the same local references for each model/config and measures user-preferred candidate Top-1/3/5 inclusion and catastrophic failures. `compare_model_configs` applies multiple versions/configurations to the same fixed set.

`export_active_learning_manifest` writes only hashes, local references, metrics, and feedback as JSON; it neither copies nor uploads images. No real-image dataset, embedding model, trainer, or automatic Touka candidate hook is bundled. Users select and freeze the real regression set from locally recorded cases.

Check: `python -m unittest tests.test_hard_case_loop`.
