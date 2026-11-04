# Character Registryからwildcard bundleを書き出す

[English](wildcard-export.en.md)

`build_character_wildcard_files(profile)`は、確認済みCharacterProfileをwildcard rootへ書き出すための相対pathとUTF-8本文に変換します。APIはファイルを直接作成しないため、保存先は呼び出し側が設定から決定します。

出力はstable `character_id`を使用し、次の役割を分けます。

- `anime_character/<id>/identity.txt`: `confirmed_core_traits`のみ
- `anime_character/<id>/outfit/<outfit_id>.txt`: 手動確認済み衣装の外衣・衣服・アクセサリーtrait
- `anime_character/<id>.txt`: identityと確認済みdefault outfitへの参照
- `character_with_lora/<id>.txt`: `character_lora/<id>`とキャラクターwildcardへのwrapper参照

未確認のidentity候補と未確認衣装は出力しません。innerwear traitとvisibility ruleも通常promptへ自動挿入しません。identityに確認済みtraitがない場合は`ValueError`になります。wildcard/inline選択構文や改行を含むtraitも拒否します。

`character_lora/<id>.txt`はこのexporterでは作成しません。スクレイピング/LoRA登録側が所有するLoRA呼び出しwildcardを、wrapperから参照するだけです。
