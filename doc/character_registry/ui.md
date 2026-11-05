# Character Registry の取り込み画面

[English](../en/character_registry/ui.md)

既存の Tabbed Tools にある **Character Registry** タブから、caption folderを読み込み、CivitaiのLoRA情報とあわせてタグ候補を確認し、手動確認した内容をCharacter profileとして登録できます。

1. caption dataset folderとprofileの保存先を選びます。選択したパスは設定済みの `USER_INPUT_DIR/config/common/character_registry.json` に保存されます（既定では `user_data/input/config/common/character_registry.json`）。
2. stable ID、表示名、必要なら別名を入力します。
3. 必要な場合だけCivitaiを検索してLoRA versionを選びます。重みファイルや画像はダウンロードしません。
4. previewで候補を確認し、採用するタグを選択して `identity` または `outfit` に手動で振り分けます。候補は自動で登録対象になりません。必要ならcustom tagを追加できます。
5. identity tagを確認し、任意でoutfit ID/nameを入力して登録します。

Civitaiの利用条件や学習許諾は自動承認されません。登録内容とprovenanceを確認してから利用してください。
