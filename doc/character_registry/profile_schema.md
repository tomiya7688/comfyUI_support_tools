# Character Registry プロファイルschema

[English](profile-schema.en.md)

## この作業で追加した型

- CharacterReferenceImage は内容SHA-256から作るIDと元画像の絶対pathを保持します。参照onlyのため画像をprofile保存先へコピーせず、同じ内容の画像は同じIDになります。画像分類は `unknown`、`mixed_custom`、`outfit` のいずれかで、`outfit` のときだけoutfit IDを持ちます。
- `CharacterProfile` は表示名に依存しないstable `character_id`、identity候補、確認済み/除外trait、複数の衣装profile、参照画像ID、source provenance、UTC timestampsを保持します。
- `CharacterOutfitProfile` は外衣、衣服、アクセサリー、innerwear、visibility rule、手動で割り当てた参照画像ID、推定confidence、手動確認状態を保持します。
- `create_character_id()` はランダムな不透明IDを一度だけ生成します。表示名を変えても、既存IDを再生成しないでください。

既存JSONで画像分類fieldがない場合は `unknown` として読み込みます。Profileは衣装割当先が存在することと、割当画像IDが該当衣装の `source_image_ids` に含まれることを検証します。

両型はimmutable dataclassです。空の表示名、無効なID、重複outfit ID、不存在のdefault outfit参照、timezoneのない時刻を拒否します。confidenceは有限の0.0〜1.0の値に限ります。

## 保存形式

`CharacterProfileStore` は呼び出し側から明示されたstorage rootだけを使い、`<character_id>.json`としてschema version 1のJSONをatomicに保存/読込します。保存rootの既定pathやユーザーデータの探索はしません。アプリ設定から決めたpathを呼び出し側が渡します。JSONは未知version、壊れた型、root外path、profile fileのsymlinkを拒否します。

## 現在の境界

Profileの契約とJSON保存/読込、選択済み画像のreference-only保存は利用できます。画像のcopy/圧縮、画像内容の自動解析、Character Library UIでの保存済みprofile編集、prompt注入、学習処理はまだ行いません。タグ候補を確定traitへ自動昇格させず、確認状態を呼び出し側が明示する設計です。
