# Character Registry タグ取り込み

[English](tag-intake.en.md)

## 現在の範囲

`preview_character_intake` は、画像に隣接するTagger形式の `.txt` captionを読み、タグを `identity`、衣装別 `outfit`、`context`、`unclassified` に分類した確認用候補を返します。これはpreviewであり、Character Registryへの登録や学習開始は行いません。未分類タグをidentityへ自動昇格させないため、誤分類の影響を抑えられます。

分類は組み込みtaxonomyによる候補生成です。自動分類結果は確定情報ではなく、Characterの登録前に人が確認・修正する必要があります。

## 入力形式

データセットは任意のローカルディレクトリで、画像の隣に同じbasenameのUTF-8 `.txt` を置きます。画像拡張子の大文字・小文字は区別しません。画像がないcaptionもpreviewに残りますが、確認用warningが付きます。`outfits/<outfit_id>/` に置いたcaptionは該当outfitの候補になります。それ以外は共通identity候補またはoutfit未割当です。未割当groupは`is_unassigned=true`で識別するため、`outfits/unassigned/`という実profileとは混ざりません。

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

- スクレイピング元の選択・ダウンロードは行いません。取得元固有のAPI・規約・ライセンス確認と分離しています。
- タグの分類は候補です。誤分類を直すUIとprofile登録は後続作業です。
- 管理対象の学習素材やユーザーデータを自動走査しません。呼び出し元が明示したdataset rootだけを読みます。
