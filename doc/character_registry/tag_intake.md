# Character Registry タグ取り込み

[English](tag-intake.en.md)

## 現在の範囲

`preview_character_intake` は、画像に隣接するTagger形式の `.txt` captionを読み、タグを `identity`、衣装別 `outfit`、`context`、`unclassified` に分類した確認用候補を返します。これはpreviewであり、Character Registryへの登録や学習開始は行いません。未分類タグをidentityへ自動昇格させないため、誤分類の影響を抑えられます。

分類は組み込みtaxonomyによる候補生成です。自動分類結果は確定情報ではなく、Characterの登録前に人が確認・修正する必要があります。

## 入力形式

データセットは任意のローカルディレクトリで、画像の隣に同じbasenameのUTF-8 `.txt` を置きます。画像拡張子は大文字・小文字を区別せずに照合します。stemは完全一致を優先するため、大文字・小文字だけが異なる別ファイルを取り違えません。画像がないcaptionもpreviewに残りますが、確認用warningが付きます。`outfits/<outfit_id>/` に置いたcaptionは該当outfitの候補になります。それ以外は共通identity候補またはoutfit未割当です。未割当groupは`is_unassigned=true`で識別するため、`outfits/unassigned/`という実profileとは混ざりません。

任意の `manifest.json` は次の形です。

```json
{
  "assets": [
    {
      "caption_file": "identity/ref-01.txt",
      "image_file": "identity/ref-01.png",
      "source_url": "https://source.example/item/123",
      "source_work_id": "123",
      "license_status": "確認済みの状態",
      "training_permission": "確認済みの状態"
    }
  ]
}
```

`caption_file` と `image_file` はデータセット内の相対pathである必要があります。POSIX/Windows形式の絶対path、親ディレクトリ参照、dataset外manifest symlinkは拒否します。manifestがない場合や利用条件が記録されていない場合、状態は `unknown` のままです。ダウンロード可能であることを学習・再配布許可の根拠として扱いません。

## 現在の制限

- Civitai候補検索は公式の匿名REST APIを使い、LoRAのmodel/version情報、作者、base model、利用条件、model tagsとtrained wordsを読み取れます。利用条件はAPI応答のまま保持し、未設定はunknownのままです。
- Civitai接続はJSON APIだけに限定します。HTMLの巡回、画像/LoRA重みのダウンロード、学習素材への自動登録はしません。利用条件と出典を人が確認してから登録してください。
- タグ分類は候補として表示し、Character Registry UIで人が修正・確認した内容だけをprofileへ登録します。
- 管理対象の学習素材やユーザーデータを自動走査しません。呼び出し元が明示したdataset rootだけを読みます。

## Civitai候補API

`search_civitai_loras(query, limit=20, cursor=None)` はLoRAの検索結果をversion単位で返し、続きがある場合はopaque cursorを返します。`fetch_civitai_lora_version(candidate)` は選択した版の `trainedWords` と公開状態を取得します。Civitai公式APIの利用制限に従い、429を含むHTTPエラーは呼び出し元へ返し、自動再試行しません。

`preview_character_intake(request, civitai_candidate=...)` を使うと、明示選択した版の `model tags` と `trainedWords` を別々の出典としてローカルcaptionと同じidentity/outfit/context/unclassified分類previewへ加えられます。Civitai情報には `civitai://` のstable source reference、元ページURL、作者、base model、APIの利用条件flagを保持します。ライセンス/学習許可は未確認として扱い、利用条件flagだけで許可を確定しません。画像が無いタグ候補は見た目の証拠ではなく、必ず人が確認します。

確認後は `CharacterTagIntakeConfirmation` に登録するidentity traitと `user_confirmed=True` のoutfit profileを明示し、`register_character_intake(preview, confirmation, profile_directory)` で保存します。未確認のoutfitは登録できず、既存 `character_id` は上書きせずエラーにします。`profile_directory` は呼び出し側が設定から渡します。Civitaiのsource metadataもprofile JSONへ保存・復元されます。

API仕様: [Models](https://github.com/civitai/civitai-developer-docs/blob/main/site/reference/models.md)、[Model Versions](https://github.com/civitai/civitai-developer-docs/blob/main/site/reference/model-versions.md)、[Authentication](https://github.com/civitai/civitai-developer-docs/blob/main/site/guide/authentication.md)。公開情報の取得は匿名API接続で行います。

候補には `allowNoCredit`、`allowCommercialUse`、`allowDerivatives`、`allowDifferentLicense` を保存します。これらは配布物・学習・生成物の全条件を保証するものではありません。実利用前に元ページと適用ライセンスを確認してください。
