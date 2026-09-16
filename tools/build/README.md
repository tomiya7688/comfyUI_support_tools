# PyInstaller one-dir build

API専用配布版はローカルのWebUI/ComfyUI/Tagger本体やモデルを同梱せず、
設定されたHTTP APIへ接続する。Python環境で次を実行する。

```powershell
python tools/build/build_one_dir.py
```

生成物は `dist/KadokaTools/`。起動時に `--api-only` を付けるとローカルの
バックエンド起動・停止・GUI起動を抑止する。API URLは `user_data` の設定を使う。
