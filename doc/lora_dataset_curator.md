[English](lora_dataset_curator.en.md) | [文書索引](README.md)

# LoRA Dataset Curator / Caption Planner

`comfyui_support_tools.applications.lora_dataset_curator` は学習画像の棚卸し、caption所有権、duplicate group、coverage、group-aware validation split、sample weightを一つの再現可能なcuration planにまとめます。画面は次で起動します。

```bash
python -m comfyui_support_tools.applications.lora_dataset_curator
```

Task、caption policy、crop policy、validation比率、seedを選んでAnalyzeします。画像行をdouble-clickすると`keep` / `low_weight` / `exclude`を巡回します。選択画像のconcept-owned tags、variable tags、weight、splitは手動で変更できます。duplicate groupのsplitを一枚で変更すると同じgroup全体へ適用し、trainが空になる変更や同一group内の矛盾は拒否します。出力先には既存ディレクトリを指定できません。

sidecarの`.txt`または`.caption`があればタグとcaptionとして読みます。組み込みのvision taggerは実行しません。`ImageEvidenceProvider`と`EmbeddingSimilarityProvider`を呼び出し側から渡すと、face/body/concept evidenceや埋め込み類似度を接続できます。標準品質値はPillowで測るblur sharpness、8px境界blocking、aspect preservationのproxyです。perceptual hashは64-bit average-hashなので、類似度モデルの実測値や人の確認を代替しません。画像とsidecarはread-onlyで、対応画像は1枚256 MiB以下、inventoryは20,000枚まで、近似候補探索は最大5,000,000比較です。

Characterではidentity/hair/accessoryをconcept側へ置き、pose/viewpoint/background/expressionと既定のclothingはvariable captionへ置きます。Character Registryのaccepted/rejected trait、per-image outfit、variable attributesを反映します。`fixed_clothing`は利用者が明示した場合だけ衣装をidentity側へ移します。Styleはsubject/contextの変動を残し、Objectは対象物をconcept側へ置きます。既知のtag aliasを正規化し、未知語はsubject tagとして保持します。

APIは`DatasetCuratorApplication.curate(root, config, ...)`で解析し、必要なら`compare_caption_policies(analysis, probe)`から#55のlocal trainer probeを利用し、手動レビュー後に`export(analysis, destination, trainer)`を呼びます。`SampleOverride`でaction、weight、train/validation、caption ownershipを上書きできます。出力は通常の`train/`・`validation/`画像とcaption sidecar、regularization画像、`dataset_manifest.json`、trainer設定templateを含みます。sd-scripts向けTOMLはbase modelに合わせてresolution等を確認してください。SimpleTuner / AI Toolkit JSONはdataset starter templateです。個別sample weightとcrop policyはmanifestへ記録されますが、対象trainerがこれらを適用するにはtrainer adapterでの明示的な接続が必要です。

curation fingerprintは入力SHA-256、caption variants、分類証拠、duplicate grouping、設定、override、split、weight、regularization画像を含みます。exportは独立staging directoryへ画像をコピーし、source fingerprintを検証してから新しいdestinationへrenameします。既存の入力画像・captionは変更しません。

`tests/test_dataset_curator.py`はtask別caption ownership、Character Registry、duplicate漏洩防止、manual group split、Auto override、fingerprint、3 trainer export、regularizationコピー、#55 probeを検証します。unit testは通っています。GUIの実画面操作、installed trainerによるtraining、modelによる自動caption、外部vision/embedding providerの実装はこのrepositoryでは検証していません。
