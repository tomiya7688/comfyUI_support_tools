# Expression Retouch

[English](expression_retouch.en.md)

`python -m comfyui_support_tools.applications.expression_retouch`で起動します。OpenCV Haar cascadeで正面顔を検出し、複数顔から対象を選択できます。full face / eyes / eyebrows / mouth / cheeks / tear regionの自動mask、canvasでの白塗り追加・右ドラッグ黒消し、expression presetと強度指定、best-of-N generation、候補比較、metadata/history保存を行います。

ComfyUIを使う場合はAPI形式のinpaint workflowを指定します。`EXPRESSION_RETOUCH_WORKFLOW=/absolute/path/workflow.json`に加えて、`EXPRESSION_RETOUCH_IMAGE_NODE`と`EXPRESSION_RETOUCH_MASK_NODE`にComfyUIの`LoadImage`/`LoadImageMask` node IDを設定します。positive/negative text nodeはタイトルから推定できますが、必要なら`EXPRESSION_RETOUCH_PROMPT_NODES`、`EXPRESSION_RETOUCH_NEGATIVE_NODES`へcomma区切りIDを指定します。sampler seed inputは自動検出し、denoise nodeは`EXPRESSION_RETOUCH_SAMPLER_NODE`で指定できます。API URLは`COMFYUI_API_URL` (default `http://127.0.0.1:8188`)です。

元画像とmaskはComfyUIへuploadし、workflowでmask inpaint/noise maskを設定する必要があります。出力はmaskの外側を元画像pixelで再合成するため、非対象pixelは保持されます。画像編集modelにidentityを完全維持させる保証ではありません。

## 評価と制限

- 標準顔検出はOpenCVのfrontal Haar cascadeです。顔パーツはface box比率から推定する近似領域で、landmark segmentationではありません。横顔、低解像度、小さな顔では検出・領域精度が落ちます。
- semantic expression match、face embedding identity、visual artifact評価modelは標準では含みません。表示されるidentity/non-target/locality値は画像差分proxyで、identity評価ではありません。semantic evaluatorは差し替え可能です。evaluator未設定時はproxy signalで順位付けします。
- anime/photo両modeと標準ComfyUI upload/inpaint接続がありますが、実際に対応するmodel/workflow/node mappingが必要です。Workflow Preset/Job Queue/#83/#84連携、batch expression sheet、専用landmark modelは未接続です。
- project historyにはsource SHA-256、target/mode/region/parameters/backend/seed/evaluationと元画像・mask・候補PNGを保存します。画像・maskはimmutable fileとして保存されます。

自動テストは契約、顔検出なしのケース、region mask、mask外pixel保持、候補rank/history、ComfyUI image/mask upload mappingを確認します。実際のmodel qualityはconfigured ComfyUI workflowとモデルで別途確認してください。
