# Touka 局所透過・表面推定

`nuno/_touka/material_estimator.py` は、入力画像から表面色、局所 alpha / 透過率、低周波の明暗、散乱・ぼけ、テクスチャ、鏡面反射、しわ候補、不確実性の PNG マップを作ります。現時点の `ClassicalMaterialEstimator` は局所画像統計に基づくヒューリスティック推定器です。物理的な層分離や学習済みモデルとして扱わず、候補の比較と人による確認を前提にします。

画像 CLI は `--mode image --input ... --output ...` で3つの仮説（保守・標準・強）を評価し、プロファイルに応じた候補を処理します。出力画像とともに選択仮説のマップ PNG、および全仮説・警告・手法を記録する `*.material.json` を保存します。明示された材質・カテゴリと表面参照色 / alpha は事前情報として使います。低い確信度では補正を弱め、`conservative` は局所 alpha の上限をさらに制限します。

`evaluate_against_ground_truth` は既知 alpha、透過率、表面色マップとの正規化 MAE を返し、合成データなどを使った比較に利用できます。学習器・実データでの評価データセット・複数推定器の実性能比較は含みません。動画 CLI は既存のスカラー補正経路を維持し、この空間推定器をまだフレームごとに使用しません。推定器 `Protocol` と registry は、後続の推定方式を比較可能にする差し替え口です。

確認: `python -m unittest tests.test_material_estimator` および `python -m unittest tests.test_touka_guidance`。
