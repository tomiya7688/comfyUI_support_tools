# Manga Creator / Storyboard

[English](manga_creator.en.md)

`python -m comfyui_support_tools.applications.manga_creator`で起動します。story/screenplayからページとコマの編集可能な計画を作り、Character/Location/Prop Bible、読み方向とコマ割り、panel prompt/pose/camera、dialogueと吹き出し、continuity eventをJSON projectとして保存します。4コマ、通常ページ、webtoon縦長、splash pageを扱います。panel単位のbest-of-N候補保存、候補選択、局所再生成、各panelを進捗保存しながらの連続render、ページ合成を行えます。セリフはpanel画像の後から独立して文字レイヤーへ合成します。

既定の`StoryboardRenderBackend`は構図をレビューするための粗い線画です。最終画ではなく、学習済み画像modelを呼び出しません。ComfyUIへ接続する場合はAPI形式workflowのJSONを用意し、起動前に`COMFYUI_MANGA_WORKFLOW=/absolute/path/workflow.json`を設定します。必要なら`COMFYUI_API_URL=http://127.0.0.1:8188`でlocal API URLを指定します。起動後はpanelのbackend IDに`comfyui`を設定します。一般的なCLIP text nodeは自動検出し、workflow固有のnode IDやsampler seed nodeは`ComfyUIPanelBackend`の引数で明示できます。character/location/propのテキスト情報はpromptへ入りますが、参照画像のpixel conditioningは汎用workflowへ自動注入しません。別の生成系は`PanelGenerationBackend`を実装してProcessへ登録できます。Story plannerも決定的なrule baselineなので、speaker表記`名前: セリフ`を拾い、本文を複数コマへ分割しますが、脚本の意味理解、story beat評価、camera演出を保証しません。

## 保存形式と制約

- MangaProject schema v1は、人物/場所/prop、story section、ページ/コマ、dialogue、生成候補、continuity eventを編集可能な中間表現として保持します。画像PNGは同じproject folder内の`panels/`と`pages/`に分け、JSON project fileはatomic replaceで保存します。
- project JSONは64 MiB、story textは2 MiB、panel画像は64 MiB/80 megapixelに制限されます。未知field、重複JSON key、未知bible参照、座標範囲外、無効な画像を拒否します。
- page合成で吹き出しやセリフを別レイヤーとして描き、文字列はproject JSONに残ります。日本語グリフは設定fontまたはOS内の候補CJK fontを探します。見つからない環境ではPNG preview内の日本語を正しく描画できず、warningを返します。`generation_settings`の`font_path`にフォントファイルを設定できます。
- candidate評価はpanel aspect、最低解像度、セリフ密度のproxyだけです。人物identity、pose/anatomy、OCR、story correspondence、page reading flowは測定しません。selection後も候補画像は保持されます。
- Continuity memoryは採用panelから明示的に記録したstate eventを後続panelへ適用します。衣装、prop、injury、locationの自動認識はしません。
- #348/#350/#353のrouter連携、Job Queue、Workflow Preset、外部評価、ComfyUI inpaintによる標準修復、縦書きglyph orientation、PDF/CBZ/EPUB exportはまだ接続されていません。MangaFlow/DiffSensei/MangaCrafterはadapter設計の参考で、論文methodの実装やmodel weightsを含みません。

テストは4コマpanel計画、right-to-left順、dialogue speaker参照、長期記憶の適用時点、best-of-N保存、単一panel再生成、ページ合成、保存/再開とJSON不正入力を確認します。
