# EU AI Act Transparency Assist

EU Transparency Assistは、ユーザーが明示的に有効化する技術的なprovenance補助機能です。ユーザーが法的な適用対象かどうかを判定せず、EU AI Actその他の法令への準拠を保証しません。既定はOFFです。IPアドレス、locale、OS言語を理由に有効化しません。

Analysisのexport dialogから任意の`.transparency.json` sidecarを出力できます。画像hash、metadata export操作、profile version/reference、利用可能な操作履歴を記録します。Inspectorでは画像の生成履歴が分からないため、分類は`unknown`です。dialogではユーザーが技術分類、開示level、人間の関与、deepfake開示contextを明示できます。ここで選んだ分類はuser overrideとして記録します。prompt・model・workflowの開示は既定で`none`です。このモードを有効にした場合、既存のanalysis JSONに含まれるpromptとnegative promptもredactします。元画像は上書きしません。

有効設定の初期値はOFFです。ユーザーは現在の選択をglobal defaultまたはAnalysis export専用overrideとして保存できます。有効状態の優先順はper-export選択、Application override、global default、OFFです。設定ファイルに署名鍵やpromptは保存しません。OSのユーザー設定directoryへ保存し、場所を理由に自動有効化しません。

PNGでは、機械可読なPNG text chunkを埋め込んだ別コピーも任意で作成できます。書き込み前に検証し、既存textと一般的なcolor/profile metadataを維持します。元画像のpixelは変更しません。既存C2PAをPillowで取り除かないよう、C2PA credentialsを含むPNGはこの経路では拒否します。JPEG、WebP、audio、videoはこのPNG metadata経路では書き換えません。これらのformatではC2PA adapterまたはsidecarを利用してください。

profile registryの初期profileは`eu_ai_act_article50_2026`、versionは`2026.1`です。法令referenceやprofile versionを後から追加できるデータ構造にしています。分類は`generated`、`ai_modified`、`conventional_edit`、`unknown`を扱いますが、法的なsubstantial alteration判定はしません。Deepfake補助はユーザーが明示した情報を記録し、identity検出や法的判定は行いません。

## C2PA署名と検証

C2PAはoptional dependencyです。利用する環境に次のpin済みSDKを導入します。

```sh
python -m pip install -r requirements-transparency.txt
```

`shared.c2pa_adapter.C2paAdapter`は公式C2PA SDKを利用し、Builder intent APIでIPTC `digitalSourceType`を設定します。

- AI生成: `trainedAlgorithmicMedia`
- AI編集: `compositeWithTrainedAlgorithmicMedia`
- 通常編集: `humanEdits`

編集元はingredientとして記録します。入力に既存C2PA manifestがあればingredient provenanceとして保持します。`verify()`はmanifest、assertion、SDK validation state、暗号署名検証、証明書trustを個別に返します。署名が有効でも証明書が信頼されていない場合はverified扱いにしません。既定は厳格検証です。明示的にwarning policyを選べますが、検証reportは未検証のままです。

署名にはTransparency AssistとC2PA署名の両方を明示的に有効化する必要があります。adapterは`SignerProvider`を受け取るため、OS key store、KMS、HSM、またはユーザー管理のsecure PEM storeへ接続できます。`PemFileSignerProvider`はproject metadata外で指定したPEM fileを扱う簡易adapterです。private key bytesをlogやsidecarへ記録しません。production keyをcheckoutやtest fixtureへ置かないでください。productionでは組織の承認済みsecure signerと検証trust anchorを`C2paAdapter(context_factory=...)`へ渡してください。

Analysis export dialogではユーザーが分類、証明書、秘密鍵fileを選ぶと、署名済みC2PA copyを作成できます。選択したpathは保存しません。warning policyでは署名credentialがuntrustedでもsigned outputを残しますが、sidecarは`verified: false`を記録します。既定policyはoutputを作成しません。ComfyUIとAUTOMATIC1111のsequence画像生成commandは、明示的なopt-inと注入されたsignerによりprovenance sidecar、PNG metadata copy、C2PA署名copyを作成できます。Analysis dialogも画像copyへ署名できます。repositoryにはvideo生成/exporterやretouch Applicationがないため、MP4署名は共有adapterで可能ですが、host側の明示的な接続が必要です。外部serviceがmetadataを保持することも保証しません。有効な署名証明書が必要です。組織から信頼されていない証明書で作成したcredentialは、署名自体が暗号学的に有効でもuntrustedとしてreportに表示します。

## 参照

- Regulation (EU) 2024/1689, Article 50
- [European Commission Article 50 FAQ](https://digital-strategy.ec.europa.eu/en/faqs/transparency-obligations-under-article-50-ai-act)
- [C2PA Technical Specification 2.4](https://spec.c2pa.org/specifications/specifications/2.4/specs/C2PA_Specification.html)
