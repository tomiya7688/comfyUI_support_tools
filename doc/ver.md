# 0.ver.mdについて

0.は編集しないこと
バージョンアップ時にはここを更新すること

書き方
```markdown
    # 1. サンプル
        helloworldを出力する機能を追加
        変更したファイル
            start.py
            開発予定.md
            仕様書.md
        追加したファイル
            hello.py
            
```

# 1. タブ画面のスクロール対応
    全タブを共通の縦スクロールコンテナへ配置し、画面外の設定もスクロールバーとマウスホイールで操作可能にした
    変更したファイル
        scripts/app.py
        doc/開発予定.md
        doc/ver.md
    追加したファイル
        scripts/widgets/scrollable_tab_container.py

# 2. Random Imageプリセット
    Random Imageの現在設定をuser_data/input/preset/random_imageへ保存・読み込みできるようにした
    変更したファイル
        scripts/tabs/random_image.py
        doc/ver.md
    追加したファイル
        scripts/widgets/preset_store.py

# 3. Folder Taggerプリセット
    Folder Taggerの入力先・タグ条件・処理オプションを保存・読み込みできるようにした
    変更したファイル
        scripts/tabs/folder_tagger.py
        doc/ver.md

# 4. 共通設定のinput/config移行
    paths.jsonをuser_data/input/config/commonへ移動し、旧配置の互換読み込みを追加した
    変更したファイル
        scripts/context.py
        doc/ver.md
    移動したファイル
        user_data/paths.json
        user_data/input/config/common/paths.json

# 5. Touka設定のinput/config移行
    Toukaのタブ固有設定をuser_data/input/config/touka/settings.jsonへ移動した
    変更したファイル
        scripts/tabs/touka_enhancer.py
        doc/ver.md
    移動したファイル
        user_data/touka_settings.json
        user_data/input/config/touka/settings.json

# 6. Random img2imgプリセット
    Random img2imgのタグ取得・生成・出力設定を保存・読み込みできるようにした
    変更したファイル
        scripts/tabs/random_img2img.py
        doc/ver.md

# 7. Toukaプリセット
    Toukaの処理条件を用途別に保存・読み込みできるようにした
    変更したファイル
        scripts/tabs/touka_enhancer.py
        doc/ver.md

# 8. Tag Deleterプリセット
    Tag Deleterの削除タグリストと処理対象を保存・読み込みできるようにした
    変更したファイル
        scripts/tabs/tag_deleter.py
        doc/ver.md

# 9. 起動設定プリセット
    WebUI1111とComfyUIの起動フラグ・リソース設定を保存・読み込みできるようにした
    変更したファイル
        scripts/tabs/start_webui.py
        doc/ver.md

# 10. YouTube Downloaderプリセット
    URLリスト・出力先・解像度上限・処理済みURL削除設定を保存・読み込みできるようにした
    変更したファイル
        scripts/tabs/youtube_downloader.py
        doc/ver.md

# 11. Flat Copy/Moveプリセット
    ファイル平坦化の操作種別と入出力先を保存・読み込みできるようにした
    変更したファイル
        scripts/tabs/flat_file_copy.py
        doc/ver.md

# 12. Body Promptプリセットと空年齢の修正
    体型入力を用途別に保存・読み込みできるようにし、年齢が未入力でもウエストからの推定処理が例外にならないようにした
    変更したファイル
        scripts/tabs/body_prompt.py
        doc/ver.md

# 13. テキスト処理プリセット
    Random Line Picker と Text Merger の入力・出力・実行設定を用途別に保存・読み込みできるようにした
    変更したファイル
        scripts/tabs/random_line_picker.py
        scripts/tabs/text_merger.py
        doc/ver.md

# 14. 変換・圧縮プリセット
    Images to WebP と Zipper の入出力・品質・圧縮・CPU制限設定を用途別に保存・読み込みできるようにした
    変更したファイル
        scripts/tabs/images_to_webp.py
        scripts/tabs/zipper.py
        doc/ver.md

# 15. ワイルドカード保守プリセット
    Brace Check と Duplicate Line Delete の処理対象を用途別に保存・読み込みできるようにした
    変更したファイル
        scripts/tabs/check_braces.py
        scripts/tabs/duplicate_line_delete.py
        doc/ver.md

# 16. 動画処理プリセット
    FFmpeg Repair と Screenshot from Movie の入出力・修復方式・抽出・CPU設定を用途別に保存・読み込みできるようにした。一時ファイル削除時の不要なコンテキスト操作も除去した
    変更したファイル
        scripts/tabs/ffmpeg_repair.py
        scripts/tabs/screenshot_from_movie.py
        doc/ver.md

# 17. 前回設定の自動保存
    各タブの入力値を終了時に共通設定へ保存し、次回起動時に同じ生成バックエンドごとで自動復元するようにした。手動プリセットとは独立している
    追加・変更したファイル
        scripts/widgets/last_settings_store.py
        scripts/app.py
        doc/ver.md

# 18. ワイルドカード検査とディレクトリ展開
    ワイルドカード参照の欠損検査・確認済み表記ゆれの自動修正タブを追加した。Random txt2imgではワイルドカード指定先がディレクトリなら配下のtxtを一つ選んで展開できるようにした
    追加・変更したファイル
        scripts/tabs/wildcard_checker.py
        scripts/backend/embedded_random_image.py
        scripts/app.py
        doc/ver.md

# 19. 手入力プロンプト生成
    プロンプトを直接入力してWebUI1111またはComfyUIへ1枚生成できるタブを追加した。ワイルドカード・LoRAトークン・選択肢展開、モデル候補、フロー、プリセットに対応する
    追加・変更したファイル
        scripts/tabs/prompt_generate.py
        scripts/app.py
        doc/ver.md

# 20. 画像破綻隔離の基盤
    Random txt2imgに、デコード不能または極端な単色化を検出して通常出力から隔離し、原因・設定・結果をJSON記録する任意機能を追加した
    追加・変更したファイル
        scripts/backend/image_failure_inspector.py
        scripts/backend/embedded_random_image.py
        scripts/tabs/random_image.py
        doc/ver.md

# 21. ComfyUIフロー固有モデル選択
    Random txt2imgでComfyフロー内のcheckpoint・UNet・VAE・CLIP等のモデル入力を検出し、ノードごとに選択してAPIワークフローへ反映できるようにした
    変更したファイル
        scripts/backend/comfy_ui_client.py
        scripts/backend/embedded_random_image.py
        scripts/tabs/random_image.py
        doc/ver.md

# 22. 追加ワイルドカードのファイル別設定
    Random txt2imgの追加ワイルドカードごとに、用途メモ・先頭または末尾・画像ごと再抽選または停止まで固定を設定し、プリセットへ保存できるようにした
    変更したファイル
        scripts/backend/embedded_random_image.py
        scripts/tabs/random_image.py
        doc/ver.md

# 23. Tag to Prompt
    タグ文字列またはtagger出力ファイルから重複を除去してプロンプト化し、txt保存・クリップボードコピー・プリセット保存できるタブを追加した
    追加・変更したファイル
        scripts/tabs/tag_to_prompt.py
        scripts/app.py
        doc/ver.md

# 24. Action wildcard
    展開済みPromptに条件タグが含まれる場合だけ追加ワイルドカードを挿入できるようにした。複数条件、挿入位置、抽選方式、プリセット保存に対応する
    変更したファイル
        scripts/backend/embedded_random_image.py
        scripts/tabs/random_image.py
        doc/ver.md

# 25. Movie to Text
    動画から等間隔の代表フレームを抽出してPixAI Taggerへ送り、出現率と信頼度で統合したタグをプロンプト用TXTへ保存するタブを追加した
    追加・変更したファイル
        scripts/tabs/movie_to_text.py
        scripts/app.py
        doc/ver.md

# 26. タブナビゲーションのスクロールと幅統一
    増加したタブボタンが画面幅からはみ出さないよう横スクロール対応にし、全ナビゲーションボタンの幅を統一した
    追加・変更したファイル
        scripts/widgets/tab_navigation.py
        scripts/app.py
        doc/ver.md

# 27. Touka環境診断
    ToukaタブでTabbed GUI用とTouka専用venvのcv2・NumPy・Pillowを個別に確認できる環境診断を追加した
    変更したファイル
        scripts/tabs/touka_enhancer.py
        doc/ver.md

# 28. Touka表面参考設定の保存
    透過表面参考フォルダをToukaの前回設定とプリセットへ保存・復元するようにした
    変更したファイル
        scripts/tabs/touka_enhancer.py
        doc/ver.md

# 29. Tabbed Tools専用環境と復元ランチャー
    GUI本体をWebUI1111のvenvから分離し、初回起動時にPython 3.10用の専用venvを作成して依存関係を検証するrun.batを追加した。生成・Toukaのバックエンドは従来どおり各専用環境を利用する
    変更したファイル
        run.bat
        doc/開発予定.md
        doc/ver.md
    追加したファイル
        setup_kadoka_tools.bat
        requirements-kadoka-tools.txt
        doc/環境構成.md

# 30. Touka動画フォルダの表面参考引き継ぎ
    動画フォルダ処理と候補全生成でも透過表面参考フォルダを各動画へ渡し、ランキングJSONに使用した参考フォルダを記録するようにした。参考画像の走査も画像ファイル100件を正確に対象にする
    変更したファイル
        nuno/_touka/touka_batch.py
        doc/ver.md

# 31. Touka参考画像の診断記録
    対象参考画像と透過表面参考画像を区別して候補JSON・診断画面へ記録し、両フォルダの役割と保存先を機能説明書へ明記した
    変更したファイル
        nuno/_touka/touka_batch.py
        scripts/tabs/touka_enhancer.py
        nuno/_touka/機能説明書.md
        doc/ver.md

# 32. Touka動画選択用GUI依存
    Tabbed Tools専用venvへ動画ROI選択とAuto objectに必要なOpenCV・NumPy・Pillowを固定し、WebUI1111のvenvを前提にせず動作するようにした
    変更したファイル
        requirements-kadoka-tools.txt
        doc/開発予定.md
        doc/ver.md

# 33. Touka対象プリセットの追加
    色に依存しないシャツ・ブラウス、カーペット・ラグの対象プリセットを追加し、対象別のマスク整形と候補評価を適用できるようにした
    変更したファイル
        nuno/_touka/touka_batch.py
        scripts/tabs/touka_enhancer.py
        nuno/_touka/機能説明書.md
        doc/ver.md

# 34. Touka操作ボタンの折り返し
    画面幅を超えて見切れていたToukaの操作ボタンを、処理・対象選択・結果確認の3行に分けて常に操作できるようにした
    変更したファイル
        scripts/tabs/touka_enhancer.py
        doc/開発予定.md
        doc/ver.md

# 35. Touka参考画像からの対象プリセット提案
    対象参考画像フォルダの形状解析をTouka専用venvで実行し、GUIの対象プリセットへ提案結果と解析画像数を反映できるようにした
    変更したファイル
        nuno/_touka/touka_batch.py
        scripts/tabs/touka_enhancer.py
        nuno/_touka/機能説明書.md
        doc/ver.md

# 36. Touka参考画像の形状内訳
    対象参考画像のプリセット候補について、形状カテゴリ別の件数と最多カテゴリの確信度を解析・GUIログへ表示するようにした
    変更したファイル
        nuno/_touka/touka_batch.py
        scripts/tabs/touka_enhancer.py
        nuno/_touka/機能説明書.md
        doc/ver.md

# 37. Touka透過表面プリセット
    強調対象とは別に透過表面の素材プリセットを追加し、薄布・厚布・薄紙・透明フィルムに応じて推定透過率の補正強度を調整できるようにした
    変更したファイル
        nuno/_touka/touka_batch.py
        scripts/tabs/touka_enhancer.py
        nuno/_touka/機能説明書.md
        doc/ver.md

# 38. Touka表面素材Tシャツ
    透過表面素材へTシャツを追加し、薄布より控えめな透過率補正で布目や影を残しやすくした
    変更したファイル
        nuno/_touka/touka_batch.py
        scripts/tabs/touka_enhancer.py
        nuno/_touka/機能説明書.md
        doc/ver.md

# 39. Touka静止画の表面設定反映
    静止画モードにも動画版と同じ表面色クラスタ弱化・低周波陰影補正・局所コントラストを適用し、表面参考画像と表面素材プリセットを反映するようにした
    変更したファイル
        nuno/_touka/touka_batch.py
        nuno/_touka/機能説明書.md
        doc/ver.md

# 40. Touka共通CPU制限の導入
    WindowsのプロセスCPUアフィニティを設定する共通サービスを追加し、Touka処理で使用CPU論理数を設定・保存できるようにした。空欄では従来どおり無制限で実行する
    追加・変更したファイル
        scripts/backend/process_cpu_limiter.py
        scripts/tabs/touka_enhancer.py
        doc/ver.md

# 41. Toukaの対象用語と設定配置の整理
    操作UIの「表面素材」を「透過対象」へ、「対象」を「強調対象」へ統一した。両プリセットを同じ設定行に配置し、参考画像・診断・ログも同じ用語へそろえた
    変更したファイル
        scripts/tabs/touka_enhancer.py
        nuno/_touka/機能説明書.md
        doc/ver.md

# 42. スクリーンショット処理のCPU制限共通化
    動画スクリーンショットタブのpsutil依存アフィニティ設定を共通CPU制限サービスへ置き換え、Toukaと同じ入力名・空欄時の無制限動作へ統一した
    変更したファイル
        scripts/tabs/screenshot_from_movie.py
        doc/ver.md

# 43. YouTube DownloaderのCPU制限共通化
    YouTube Downloaderへ共通CPU制限を追加し、使用CPU論理数をプリセット保存できるようにした。空欄ではダウンロード・変換処理を無制限で実行する
    変更したファイル
        scripts/tabs/youtube_downloader.py
        doc/ver.md

# 44. FFmpeg RepairのCPU制限共通化
    FFmpeg Repairの実行を共通CPU制限サービスで起動するようにし、使用CPU論理数をプリセット保存できるようにした
    変更したファイル
        scripts/tabs/ffmpeg_repair.py
        doc/ver.md

# 45. Folder TaggerからのTagGUI起動
    Folder Taggerで選択した画像フォルダを渡して、PixAI自動タグ付けとは別にTagGUIを直接起動できるようにした
    変更したファイル
        scripts/tabs/folder_tagger.py
        doc/ver.md

# 46. Folder TaggerからのTagGUI停止
    Folder Taggerから起動したTagGUIを安全に停止する操作を追加し、終了待機後も残る場合は強制終了するようにした
    変更したファイル
        scripts/backend/taggui_controller.py
        scripts/tabs/folder_tagger.py
        doc/ver.md

# 47. Toukaの下着用強調対象
    強調対象にブラジャーとショーツ・パンツを追加し、細かい分断をつなぎつつ輪郭を残す専用マスク整形と動画スコア調整を適用した
    変更したファイル
        nuno/_touka/touka_batch.py
        scripts/tabs/touka_enhancer.py
        nuno/_touka/機能説明書.md
        doc/ver.md

# 48. FashionpediaのToukaプリセット生成
    Fashionpediaの学習画像45,623枚と公式注釈を指定データセット配下へ展開した。注釈ポリゴンから透明背景の参考画像を作り、シャツ・服・パンツ・リボンのToukaプリセットJSONを生成する処理と操作ボタンを追加した
    変更したファイル
        nuno/_touka/fashionpedia_preset_builder.py
        scripts/tabs/touka_enhancer.py
        nuno/_touka/機能説明書.md
        doc/ver.md

# 49. Comfyフロー選択時の候補表示エラー修正
    Random Imageタブが候補重複除去ヘルパーを明示インポートしていなかったため、Comfyフロー選択時に発生していたNameErrorを修正した。候補ヘルパーはNone値も選択肢へ混ぜないようにした
    変更したファイル
        scripts/tabs/random_image.py
        scripts/context.py
        doc/ver.md

# 50. Touka Fashionpediaセグメンテーション学習器
    Fashionpediaの46分類マスクへ半透明素材を合成した学習データセット、DeepLabV3 MobileNetV3のモデル定義、GPU学習・評価・保存コマンドを追加した。GTX 1080で少数サンプルの学習、モデル再読込、47クラス出力を検証済み
    変更したファイル
        nuno/_touka/translucent_surface_augmenter.py
        nuno/_touka/fashionpedia_training_dataset.py
        nuno/_touka/fashionpedia_segmentation_model.py
        nuno/_touka/train_fashionpedia_segmentation.py
        doc/開発予定.md
        doc/ver.md

# 51. 順次生成のワイルドカード読込エラー修正
    順次生成が入力ファイル読込へ不要なroot引数を渡していたために発生したTypeErrorを修正した。入力がディレクトリの場合も選択できるようにし、順次生成内では同じワイルドカードを一度だけ展開して全行で同じ結果を使うようにした
    変更したファイル
        scripts/backend/embedded_random_image.py
        doc/ver.md

# 52. Random Imageのモデル付属VAE
    Random Imageへモデル付属VAE使用チェックボックスを追加した。有効時のWebUI1111生成ではsd_vaeをAutomaticとして送信し、チェック状態はプリセットにも保存する
    変更したファイル
        scripts/tabs/random_image.py
        scripts/backend/embedded_random_image.py
        doc/開発予定.md
        doc/ver.md

# 53. Action wildcardの複数タグ条件
    Action wildcardの条件でカンマ区切りをAND、`|`区切りをORとして扱えるようにした。UIへ条件記法を表示し、複数タグの判定テストを追加した
    変更したファイル
        scripts/backend/embedded_random_image.py
        scripts/tabs/random_image.py
        doc/開発予定.md
        doc/ver.md

# 54. Toukaの肌用強調対象
    Toukaへ「肌（輪郭優先）」を追加した。肌では欠落領域を埋めず、小さなノイズだけを除去して輪郭・分離部分を維持する
    変更したファイル
        nuno/_touka/touka_batch.py
        scripts/tabs/touka_enhancer.py
        doc/開発予定.md
        doc/ver.md

# 55. Wildcard Move
    root内のtxt移動前に参照を新しい相対パスへ書き換えるWildcard Moveタブを追加した。root外参照と既存移動先は拒否する
    変更したファイル
        scripts/tabs/wildcard_move.py
        scripts/app.py
        doc/開発予定.md
        doc/ver.md

# 56. Random Imageのプロンプト保存
    生成プロンプト保存を追加した。保存先がtxtなら追記し、フォルダなら生成画像と同名のtxtを出力する。両方式を一時ディレクトリで検証した
    変更したファイル
        scripts/backend/embedded_random_image.py
        scripts/tabs/random_image.py
        doc/開発予定.md
        doc/ver.md

# 57. 順次生成の無限ループ
    順次生成を先頭行から繰り返すチェックボックスを追加した。周回ごとにワイルドカードを引き直し、同一周回内では結果を共有する。プリセット保存にも対応した
    変更したファイル
        scripts/backend/embedded_random_image.py
        scripts/tabs/random_image.py
        doc/開発予定.md
        doc/ver.md

# 58. Random Imageの出力形式選択
    Random ImageでPNGのほかWebP/JPEGを選択して保存できるようにした。変換後の拡張子を保存先とプロンプト同名ファイルへ反映し、プリセットにも選択状態を保存する
    変更したファイル
        scripts/backend/embedded_random_image.py
        scripts/tabs/random_image.py
        doc/開発予定.md
        doc/ver.md

# 59. Random ImageのGIF出力
    Random Imageの出力形式へGIFを追加した。単一の生成画像を256色GIFへ変換して保存し、従来のPNG/WebP/JPEG選択と同じ保存・プリセット処理を利用する
    変更したファイル
        scripts/backend/embedded_random_image.py
        scripts/tabs/random_image.py
        doc/開発予定.md
        doc/ver.md

# 60. Wildcard Checkerの検証完了
    Wildcard Checkerがroot配下のtxtを再帰検査し、欠損参照を通知できることを確認した。確認できる大小文字・区切り文字の表記ゆれは自動修正し、rootと修正設定はプリセットへ保存できる
    変更したファイル
        doc/開発予定.md
        doc/ver.md

# 61. Random Imageの実行中設定更新
    無限生成・順次生成の実行中に「実行中へ設定を反映」を押すと、現在の1枚を中断せず次の生成開始前に設定をまとめて反映するようにした
    変更したファイル
        scripts/backend/embedded_random_image.py
        scripts/tabs/random_image.py
        doc/開発予定.md
        doc/ver.md

# 62. 順次生成のフォルダ入力と抽選固定
    順次生成の入力にフォルダを指定した場合、配下のtxtを名前順に読み全行を実行するようにした。順次中のワイルドカードを固定するか、行ごとに引き直すかをチェックボックスで選べ、設定はプリセットへ保存される
    変更したファイル
        scripts/backend/embedded_random_image.py
        scripts/tabs/random_image.py
        doc/開発予定.md
        doc/ver.md

# 63. メインWildcardの停止まで固定
    Random ImageのメインWildcardについて、無限生成で生成ごとに再抽選するか停止まで同じ展開結果を使うかを日本語チェックボックスで選べるようにした。既存プリセットの抽選範囲設定も読み込める
    変更したファイル
        scripts/tabs/random_image.py
        doc/開発予定.md
        doc/ver.md

# 64. 画像破綻隔離の検証完了
    画像破綻隔離が単色化した画像を `_image_failure` 側へ振り分け、通常画像は維持することを確認した。原因・生成設定・プロンプトを `user_data/output/image_generate/log/image_failure` のJSONへ記録する
    変更したファイル
        doc/開発予定.md
        doc/ver.md

# 65. Random img2imgの通常生成モード
    Random img2imgへTaggerを使うか選ぶチェックボックスと手動プロンプト欄を追加した。Taggerをオフにしても、入力画像・手動プロンプト・追加タグだけでWebUI1111またはComfyUIへimg2imgを送れる
    変更したファイル
        scripts/tabs/random_img2img.py
        doc/開発予定.md
        doc/ver.md

# 66. Tag Splitterタブ
    フォルダ内のタグtxtを人物・ポーズ・服・画風・背景・状況・表情と複合カテゴリ5種類の合計12種類へ分割し、元の相対パスを保ったカテゴリ別txtとして出力するタブを追加した
    変更したファイル
        scripts/backend/tag_category_splitter.py
        scripts/tabs/tag_splitter.py
        scripts/app.py
        doc/開発予定.md
        doc/ver.md

# 67. Folder TaggerのTag Splitter連携
    Folder Taggerへ「タグを12カテゴリにも出力」を追加した。通常の統合TXTを維持したまま、同じ行順の分類TXTを `<出力TXT名>_split` へ出力する
    変更したファイル
        scripts/backend/tag_category_splitter.py
        scripts/tabs/folder_tagger.py
        doc/開発予定.md
        doc/ver.md

# 68. Tag Replacerタブ
    タグフォルダ内のTXTを完全一致規則で置き換えるタブを追加した。置換先は直接タグまたはWildcard TXTから選べ、上書き・出力先分離・再帰処理・プリセットに対応する
    変更したファイル
        scripts/backend/tag_replacement_engine.py
        scripts/tabs/tag_replacer.py
        scripts/app.py
        doc/開発予定.md
        doc/ver.md

# 69. Video Reencoderタブ
    動画フォルダをH.264/H.265で再エンコードするタブを追加した。最大高さ、音声ビットレート、CRFまたは目標サイズから算出する動画ビットレート、CPU制限を設定でき、元動画とは別の出力先へMP4を書き出す
    変更したファイル
        scripts/backend/video_reencoder.py
        scripts/tabs/video_reencoder.py
        scripts/app.py
        doc/開発予定.md
        doc/ver.md

# 70. 静的仕様書生成タブ
    PythonファイルまたはフォルダをASTで解析し、クラス・継承・関数引数・戻り値注釈・docstring先頭行をMarkdown仕様書として出力するタブを追加した。対象ソースは実行・変更しない
    変更したファイル
        scripts/backend/static_spec_generator.py
        scripts/tabs/static_spec.py
        scripts/app.py
        doc/開発予定.md
        doc/ver.md

# 71. Movie to TextのWildcard出力
    Movie to Textへ出力モードを追加した。共通タグ1行に加え、抽出フレームごとのタグを複数行Wildcard TXTとして保存できる。設定はプリセットに保存される
    変更したファイル
        scripts/tabs/movie_to_text.py
        doc/開発予定.md
        doc/ver.md

# 72. Folder Taggerの動画タグ付け
    Folder Taggerへ動画処理のチェックボックスと抽出フレーム数を追加した。動画は均等に抽出したフレームを同じTaggerへ送り、信頼度を平均して既存の統合TXTと任意の12分類TXTへ出力する
    変更したファイル
        scripts/tabs/folder_tagger.py
        doc/開発予定.md
        doc/ver.md

# 73. Docstring検査タブ
    公開モジュール・クラス・関数・メソッドのdocstring不足をASTで検査し、行番号付きMarkdownレポートへ出力するタブを追加した。対象ソースは変更しない
    変更したファイル
        scripts/backend/docstring_auditor.py
        scripts/tabs/docstring_audit.py
        scripts/app.py
        doc/開発予定.md
        doc/ver.md

# 74. バックエンド選択の起動タブ移行
    起動時のバックエンド選択ダイアログを廃止した。起動タブからWebUI1111用またはComfyUI用のGUI画面を追加で開けるため、両バックエンドの画面を同時に扱える
    変更したファイル
        scripts/tabs/start_webui.py
        scripts/app.py
        doc/開発予定.md
        doc/ver.md

# 75. 依存状態チェックタブ
    WebUI1111、ComfyUI、PixAI Tagger、共有models、Wildcard、ffmpeg/ffprobeの利用可否を読み取り専用で確認するタブを追加した。任意で各ローカルAPIの疎通も確認できる
    変更したファイル
        scripts/backend/dependency_checker.py
        scripts/tabs/dependency_status.py
        scripts/app.py
        doc/開発予定.md
        doc/ver.md

# 76. Ollama Prompt校正タブ
    OllamaのローカルAPIを使い、日本語・自由文を画像生成向けのカンマ区切りタグへ校正するタブを追加した。モデル一覧取得、非ストリーム生成、プリセットに対応し、Ollama未起動時はこのタブだけがエラー表示する
    変更したファイル
        scripts/backend/ollama_prompt_corrector.py
        scripts/tabs/ollama_prompt.py
        scripts/app.py
        doc/開発予定.md
        doc/ver.md

# 77. Random ImageのOllamaプロンプト補正
    Random ImageへOllamaで生成直前の展開済みプロンプトを補正するチェックボックス、API URL、モデル選択とモデル候補更新を追加した。設定はプリセット保存でき、順次生成の同一周回Wildcard固定には影響しない
    変更したファイル
        scripts/backend/embedded_random_image.py
        scripts/tabs/random_image.py
        doc/開発予定.md
        doc/ver.md

# 78. Text Mergerの重複タグ除外
    Text Mergerへ、入力フォルダと既存出力ファイルを照合して重複タグを追記しない設定を追加した。比較は大文字小文字とアンダースコア表記を吸収し、最初のタグ表記を保存する
    追加・変更したファイル
        scripts/backend/tag_text_merger.py
        scripts/tabs/text_merger.py
        doc/開発予定.md
        doc/ver.md

# 79. Wildcardディレクトリ選択
    Random Imageの入力WildcardでtxtファイルまたはフォルダをGUIから選べるようにした。フォルダ指定は配下txtを先に均等抽選し、選ばれたtxtの行を抽選するため、行数によりファイル選択確率が偏らない
    変更したファイル
        scripts/widgets/labeled_path_row.py
        scripts/tabs/random_image.py
        doc/開発予定.md
        doc/ver.md

# 80. Toukaデータセットプリセット作成
    Toukaで指定した強調対象参考画像フォルダを検査し、画像がある場合だけ任意名のToukaプリセットとして保存できるようにした。対象選択と参考画像パスを保存し、次回の動画・画像処理でそのまま読み込める
    追加・変更したファイル
        scripts/backend/touka_dataset_preset_builder.py
        scripts/tabs/touka_enhancer.py
        doc/開発予定.md
        doc/ver.md

# 81. Touka参考画像ノイズ除去
    Toukaに参考画像のノイズ抑制チェックを追加した。形状ヒントの輪郭抽出と透過対象参考画像の色クラスタ推定前だけにバイラテラル・メディアン処理を適用し、入力画像と生成出力は変更しない
    変更したファイル
        nuno/_touka/touka_batch.py
        scripts/tabs/touka_enhancer.py
        doc/開発予定.md
        doc/ver.md

# 82. Touka参考画像の共通形状優先
    Toukaの参考画像解析で、形状カテゴリだけでなく面積比と縦横比の一致度を集計し、複数画像で共通する対象を優先してプリセット候補にした。解析結果には共通候補数・形状一致度・外れ候補数を表示する
    変更したファイル
        nuno/_touka/touka_batch.py
        scripts/tabs/touka_enhancer.py
        doc/開発予定.md
        doc/ver.md

# 83. GUI黒基調テーマ
    Tabbed Tools GUIとバックエンド選択画面へ黒基調の共通テーマを適用した。背景・パネル・入力欄・ログ・Canvas・タブボタン・Treeview・選択状態を明示的に指定し、OSテーマに左右されない表示にした
    追加・変更したファイル
        scripts/widgets/dark_theme.py
        scripts/app.py
        doc/開発予定.md
        doc/ver.md

# 84. Touka操作列の折り返し
    Toukaの処理・範囲選択・結果確認の操作列をResponsiveButtonRowへ移行し、ウィンドウ幅が狭い場合もボタンとプリセット欄を次の行へ折り返すようにした
    追加・変更したファイル
        scripts/widgets/responsive_button_row.py
        scripts/tabs/touka_enhancer.py
        doc/開発予定.md
        doc/ver.md

# 85. Random Image操作列の折り返し
    Random Imageの生成・停止・候補更新・順次設定・プリセット欄をResponsiveButtonRowへ移行し、狭いウィンドウでも操作要素を次の行へ折り返すようにした
    変更したファイル
        scripts/tabs/random_image.py
        doc/開発予定.md
        doc/ver.md

# 86. Touka自動評価履歴
    Touka処理完了後に元画像と出力画像の平均変化量・輝度分散・輪郭変化を計算し、動画候補のスコアと時間安定性を含めてprofile・強調対象プリセット別のJSONL履歴へ保存するようにした。評価履歴フォルダはGUIから指定でき、未指定時は出力先配下へ保存する
    追加・変更したファイル
        scripts/backend/touka_evaluator.py
        scripts/tabs/touka_enhancer.py
        doc/開発予定.md
        doc/ver.md

# 49. ToukaのFashionpedia学習基盤開始
    半透明素材越し対象推定の実装段階をdoc/実装予定.mdへ記録した。Touka専用venvにCUDA対応PyTorchを導入してGTX 1080 8GBを確認し、Fashionpedia画像とポリゴン注釈から46カテゴリ+背景の意味マスクを返すDatasetを追加した
    変更したファイル
        doc/実装予定.md
        doc/Agent.md
        nuno/_touka/fashionpedia_segmentation_dataset.py
        doc/ver.md
