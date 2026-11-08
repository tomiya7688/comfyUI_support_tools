# Character Registry の取り込み画面

[English](../en/character_registry/ui.md)

既存の Tabbed Tools にある **Character Registry** タブから、caption folderを読み込み、CivitaiのLoRA情報とあわせてタグ候補を確認し、手動確認した内容をCharacter profileとして登録できます。

1. caption dataset folderとprofileの保存先を選びます。選択したパスは設定済みの `USER_INPUT_DIR/config/common/character_registry.json` に保存されます（既定では `user_data/input/config/common/character_registry.json`）。
2. stable ID、表示名、必要なら別名を入力します。
3. 必要な場合だけCivitaiを検索してLoRA versionを選びます。重みファイルや画像はダウンロードしません。
4. previewで候補を確認し、採用するタグを `identity`、`outfit`、`innerwear` に手動で振り分けます。候補は自動で登録対象になりません。innerwearは通常promptへ出力されません。必要ならcustom tagを追加できます。
5. 必要なら「Character参照画像」からローカル画像を複数選択します。画像はコピー・自動解析せず、内容SHA-256 IDと絶対pathを保存します。同じ内容の画像は重複登録しません。衣装を追加した後、一覧で画像を1件選び、「未分類 / 不明」「混在 / カスタム」または登録済み衣装を選択して割当を反映できます。衣装を削除すると、その衣装への画像割当は未分類に戻ります。ファイル移動後は古い参照を外して、移動先から選び直してください。

参照欄には登録候補数、元画像が現在存在する数、衣装別/混在/未分類の件数を表示します。これは登録候補の数え上げで、画像品質、学習有効枚数、LoRA readinessの判定ではありません。
6. identity tagを確認し、衣装ごとにoutfit ID/nameとtagを分類して「この衣装を候補に追加」を押します。複数の衣装を順番に追加でき、誤って追加した衣装は一覧から削除できます。最初に追加した衣装が既定になりますが、登録前に「既定衣装」から別の衣装へ変更できます。未保存の入力中衣装も登録時に含まれます。登録後、設定済みwildcard rootへcharacter wildcardとLoRA wrapperを自動出力します。

画像ごとの衣装割当は手動です。割り当てたIDは `CharacterOutfitProfile.source_image_ids` に保存されます。画像のTagger解析、managed copy、thumbnail、品質/重複分析はまだ行いません。

出力される `character_with_lora/<character_id>.txt` は `__anime_character_lora/<character_id>__` と `__anime_character/<character_id>__` を参照します。登録後は「Character LoRA候補」欄から `anime_character_lora/<character_id>.txt` を作成できます。`<lora:ローカルモデル名:強度>` を1行ずつ入力し、`@weight=3::<lora:model_a:0.8>` のような相対重みも指定できます。保存先はアプリ共通設定の `wildcards` (`WILDCARDS_DIR`) です。書き込み失敗時は登録済みprofileを維持し、画面からwildcard出力を再試行できます。

Civitai候補はページ送りで追加取得できます。preview後にID・表示名・別名・dataset・選択LoRAを変更した場合は、登録前にpreviewを作り直してください。previewと登録に使うpathは設定へ保存されます。

Civitaiの利用条件や学習許諾は自動承認されません。登録内容とprovenanceを確認してから利用してください。
