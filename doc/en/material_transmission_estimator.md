# Touka Local Transmission and Surface Estimation

`nuno/_touka/material_estimator.py` produces PNG maps for surface color, local alpha / transmittance, low-frequency shading, scatter and blur, texture, specular response, wrinkle candidates, and uncertainty. The current `ClassicalMaterialEstimator` uses heuristic local image statistics. Treat its output as reviewable candidate estimates, not physical layer decomposition or a trained model.

The image CLI (`--mode image --input ... --output ...`) evaluates three hypotheses (conservative, natural, enhanced) and processes the hypothesis selected by the profile. It writes the output image, selected-hypothesis map PNGs, and a `*.material.json` report with all hypotheses, warnings, and method provenance. Explicit material/category hints and reference surface colors / alpha act as priors. Lower confidence weakens the correction; the `conservative` profile also limits local alpha.

`evaluate_against_ground_truth` reports normalized MAE for alpha, transmittance, and surface-color maps and can compare synthetic captures with known maps. A learned estimator, real-data evaluation set, and empirical comparison of multiple estimator implementations are not included. Video CLI keeps its existing scalar correction path and does not yet apply this spatial estimator per frame. The estimator `Protocol` and registry provide an extension point for later methods.

Checks: `python -m unittest tests.test_material_estimator` and `python -m unittest tests.test_touka_guidance`.
