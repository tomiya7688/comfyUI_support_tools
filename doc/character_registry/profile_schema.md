# Character Registry プロファイルschema

[English](profile-schema.en.md)

## この作業で追加した型

- `CharacterProfile` は表示名に依存しないstable `character_id`、identity候補、確認済み/除外trait、複数の衣装profile、参照画像ID、source provenance、UTC timestampsを保持します。
- `CharacterOutfitProfile` は外衣、衣服、アクセサリー、innerwear、visibility rule、参照画像、推定confidence、手動確認状態を保持します。
- `create_character_id()` はランダムな不透明IDを一度だけ生成します。表示名を変えても、既存IDを再生成しないでください。

両型はimmutable dataclassです。空の表示名、無効なID、重複outfit ID、不存在のdefault outfit参照、timezoneのない時刻を拒否します。confidenceは有限の0.0〜1.0の値に限ります。

## 現在の境界

これは登録・保存処理が利用するデータ契約です。永続化、画像コピー、GUIでの手動編集、prompt注入、学習処理はまだ行いません。タグ候補を確定traitへ自動昇格させず、確認状態を呼び出し側が明示する設計です。
