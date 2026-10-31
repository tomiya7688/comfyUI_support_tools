# 画像エンハンサー

[English](README.md)

人物画像以外の一般画像を対象に、元画像へ調整済みの画像を重ね、見えにくい情報を確認しやすくするデスクトップツールです。元画像に含まれない情報は復元できません。

## 起動

```text
python -m pip install -r requirements.txt
python image_enhancer.py
```

Windowsでは `run_image_enhancer.bat` をダブルクリックします。CPython 3.11.18以上が必要です。初回起動時に同じフォルダへ `.venv` を作成し、固定したPillow 10.4.0とNumPy 1.26.4をインストールします。既存の未対応 `.venv` は削除せず `.venv-python-pre-31118` に退避します。Windowsの `py` ランチャーでCPythonを選べない場合は、対応する `python.exe` のパスを環境変数 `KADOKA_PYTHON31118` に設定してください。次回以降は既存環境を使い、依存ライブラリの版を確認します。

**Open…** で画像を開き、Master RGBまたはRed/Green/Blue曲線、コントラスト、ハイライト、シャドウ、ディテールを調整して、ブレンド方法と不透明度を選びます。操作に応じてプレビューが更新されます。**Show original** は元画像と処理後のプレビューを切り替え、**Reset all** はすべての設定を初期値へ戻します。**Repeated passes** は同じ処理を最大5回まで重ねます。**Save export…** は元画像の全解像度で処理結果を保存します。

曲線エディター内をクリックすると点を追加でき、ドラッグして調整できます。両端の点は固定されています。ブレンド方法はNormal、Darken、Lighten、Multiply、Screen、Overlayです。

## GUIなしの起動確認

```text
python image_enhancer.py --smoke-test
```

元画像を上書きしません。読み込み時にカメラの向き情報を適用します。PNG出力はアルファチャンネルを保持し、ファイル名が `.jpg` または `.jpeg` の場合はPillowでJPEGとして保存します。
