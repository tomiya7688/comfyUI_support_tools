# LoRA Composition Lab

[English](lora_composition.en.md) | [日本語](lora_composition.md)

`comfyui_support_tools.shared.lora_composition` は、互換性を確認したLoRA safetensorsの分析と合成を行う任意利用のCPU backendです。ホスト環境で `requirements-lora-composition.txt` を導入してください。package import時にモデルtensorは読み込みません。

LoRAのroleとsource hashを読み込み、family・architecture・base model・target moduleを事前確認します。provenance欠落は警告として報告します。layerごとのupdate norm、cosine similarity、output-subspace overlap、sign conflict、layer overlap、singular-value summaryを計算します。weighted merge、各要素で強いsourceを選ぶtop-K baseline、role-aware Zip-style conflict selectorを使えます。static出力は指定rankへ圧縮し、sourceとmodel provenanceを付けた安全なA/B tensorを保存します。既存staticファイルは上書きせず、元LoRAも変更しません。runtime recipeは別JSONとして保存します。

`search_scales` はcallerが用意した生成/evaluation bridgeを通して、globalおよびper-layerのscale候補を評価します。`EvaluationCase`には固定promptとseedを指定します。評価値はsubject/style fidelity、prompt controllability、image quality、concept presence、confusion、binding、attribute swap、leakage、anatomyです。過去に選んだscaleは上限付きatomic historyへ保存し、次の探索候補に追加します。

```python
from comfyui_support_tools.shared.lora_composition import (
    LoRACompositionApplication,
)

app = LoRACompositionApplication("preferences.json")
adapters = app.load(
    ["subject.safetensors", "style.safetensors"],
    {"subject": "subject", "style": "style"},
)
report = app.preflight(adapters, "sdxl/base", base_architecture="SDXL")
if report.compatible:
    conflicts = app.analyze(adapters)
    # 固定prompt/seedを描画するbackend evaluatorを用意して候補を評価します。
```

画像生成/evaluation bridgeとvisual UIは数値merge backendから分離しています。このpackageは暗黙に画像を生成したり、権利を推定したり、汎用mergeが研究論文のZipLoRA/K-LoRA学習pipelineを再現すると主張したりしません。`top_k`と`zip_style`は比較用のtraining-free baselineです。dense analysisは1 layerあたり8,388,608要素（float32 updateあたり32 MiB）に制限しています。代表的なadapterと小さな候補gridから始めてください。
