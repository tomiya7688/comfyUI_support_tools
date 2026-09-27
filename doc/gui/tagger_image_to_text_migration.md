# Tagger / image-to-text migration — #222

新GUIのMedia Browser → Inspector → Action導線をTagger/image-to-textの正本とし、
既存Folder Taggerは壊さず段階移行する。

## 現在動作するbackend

- **PixAI HTTP**: 既存 `/pixai/v1/interrogate` 契約をExternal Adapterとして維持。
- **Tagger Service HTTP**: `/tagger/v1/interrogate` の共通導線。
  #229/#231でAnimeTimm Built-in backendがTagger Serviceへ追加された場合、
  GUI変更なしでモデル一覧から選択できる構造。

サービスの自動起動、外部Python/venv/site-packages共有、別Application内部importは行わない。
モデル一覧は同prefixの `/interrogators` を明示接続確認した時だけ取得する。

Style Analyzerは #64 のservice/API契約が未実装なので **Analyze Styleを理由付きdisabled** のままにする。
「Style欄がある」ことと「Style解析済み」を混同しない。

## 正規化result

Tag responseはProcess層で以下へ分離する。

- content/general tags + confidence
- character tags + confidence
- copyright tags
- rating + rating confidence candidates
- free-form caption
- backend / model provenance

`style` fieldがTagger responseに混入していてもcontent tagsへ足さない。
Styleは独立Style Analyzer Actionの責務。

旧PixAI系の `{"tag": {"tag": score}}`、共通serviceのcategory形式、
comma-separated tag caption形式を互換入力として扱う。
free-form captionはcontent tagへ捏造せずcaption fieldに保持する。

## Inspector

単一画像では次を独立表示/編集できる。

- Content Tags
- Style
- Character Tags
- Copyright Tags
- Rating
- Caption / image-to-text
- Prompt / Negative Prompt
- Character memo / Dataset-LoRA memo

Tag実行ではContent/Character/Copyright/Rating/Captionだけを更新し、
Style・Prompt等を保持する。confidence/provenance付き自動結果を手編集した場合は
該当confidenceを破棄し、provenanceを `manual-edit` にする。

複数画像は最大60件まで同じTag Action/Job Queueでbatch処理する。

## Export

Inspectorの **結果をTXT / metadataへExport** は明示操作のみ。

選択可能:
- caption sidecar: 画像と同じstemの `.txt`
- structured metadata: `<image.ext>.kadoka.json`
- optional batch TXT: ユーザーが保存先を指定
- caption生成時にStyle tagsを連結するかを明示指定
- overwriteは既定OFF

caption fieldが存在すればそれを優先する。空の場合は
content + character + copyright tagsからcaptionを作り、Styleは明示ONの場合だけ連結する。
Ratingはcaptionへ暗黙連結しない。

metadata JSONは各field、score、backend/model provenanceを分離保存する。
元画像は変更しない。Sourceのsize/mtimeがBrowser読込時から変わっていればExportを拒否する。
既存sidecar/metadataへはoverwrite ONなしで書き込まない。symlink出力も拒否する。

Export自体もshared Job Queueの `analysis_export` として記録する。

## Extension points

AnimeTimm:
1. #229 Tagger Serviceの共通backend interfaceへ実装。
2. #231 backendを登録し `/interrogators` からmodelを返す。
3. normalized responseを返せば、Main GUIのbackend/model/threshold・batch・Inspector・Exportを再利用。

Style Analyzer:
1. #64で独立service/API adapterを実装。
2. `media_actions.py` のStyle Actionを利用可能にし、StyleResultだけをstyle fieldへ反映。
3. content/rating fieldをStyle Actionから書き換えない。

Florence等caption/image-to-text:
共通Tagger Serviceがfree-form `caption` を返せばInspector/Exportはそのまま利用できる。
モデル固有runtimeはMain GUIへimportしない。

## Validation

- structured/flat/nested responseの正規化、rating/style分離、free-form caption
- PixAI/Common Tagger backendとendpoint整合
- Styleがcontentへ混ざらない
- batch resultが元MediaItemへ紐づく既存回帰
- caption/metadata/batch TXT、overwrite保護、source変更検出
- Windows full completion gate / UPD / app-boundary
- frozen onedir loopback Tagger smokeで正規化fieldsとExportを実ファイルで確認

loopback fixtureはHTTP契約/GUI統合の試験であり、PixAI/AnimeTimm/Styleモデル精度の試験ではない。
