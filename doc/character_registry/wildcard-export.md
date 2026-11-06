# Character Registryからwildcard bundleを書き出す

[English](wildcard-export.en.md)

`build_character_wildcard_files(profile)`は、確認済みCharacterProfileをwildcard rootへ書き出すための相対pathとUTF-8本文に変換します。APIはファイルを直接作成しないため、保存先は呼び出し側が設定から決定します。

出力はstable `character_id`を使用し、次の役割を分けます。

- `anime_character/<id>/identity.txt`: `confirmed_core_traits`のみ
- `anime_character/<id>/outfit/<outfit_id>.txt`: 手動確認済み衣装の外衣・衣服・アクセサリーtrait
- `anime_character/<id>.txt`: identityと確認済みdefault outfitへの参照
- `character_with_lora/<id>.txt`: `anime_character_lora/<id>`とキャラクターwildcardへのwrapper参照

未確認のidentity候補と未確認衣装は出力しません。innerwear traitとvisibility ruleも通常promptへ自動挿入しません。identityに確認済みtraitがない場合は`ValueError`になります。wildcard/inline選択構文や改行を含むtraitも拒否します。

`anime_character_lora/<id>.txt`はCharacter Registry画面の「Character LoRA候補」欄から作成できます。登録済みprofileのstable IDを使い、ローカルLoRA名と強度を `<lora:model_name:0.8>` の形式で入力します。複数候補は1行ずつ記述し、`@weight=3::<lora:model_a:0.8>` のように相対重みを付けられます。保存時に行ごとのwildcard重みとLoRA呼び出し形式を検証し、正の重みを持つ候補を必須にします。重みファイルやCivitai画像は取得しません。

保存した `anime_character_lora/<id>.txt` は既存wrapperから参照されます。同じprompt内や順次生成の同一実行中はwildcard cacheにより選択結果が再利用されます。利用するLoRAがローカルに存在し、選択中のbase modelと互換かを生成前に確認してください。
