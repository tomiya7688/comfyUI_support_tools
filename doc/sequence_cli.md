# シーケンスCLI

シーケンス定義はJSONとして保存し、GUIを起動せずに実行できます。

```powershell
python -m comfyui_support_tools.entrypoints.sequence_cli list
python -m comfyui_support_tools.entrypoints.sequence_cli run <sequence-name>
python -m comfyui_support_tools.entrypoints.sequence_cli save <definition.json>
```

既定の保存先は `user_data/input/config/sequences` です。`--directory` または
`KADOKA_SEQUENCE_DIR` で変更できます。

## WebUI 1111で生成するstep

`a1111_generate` は既存のWebUI 1111 API adapterを利用します。例:

```json
{
  "id": "generate",
  "command": "a1111_generate",
  "inputs": {
    "api_url": "http://127.0.0.1:7860",
    "prompt": {"$ref": "context.correct.prompt_after"},
    "negative_prompt": "low quality",
    "checkpoint": "model.safetensors",
    "sampler": "Euler a",
    "steps": 24,
    "cfg": 6.5,
    "width": 512,
    "height": 512,
    "output_dir": "K:/sd/output/sequence"
  }
}
```

`prompt` は必須です。`negative_prompt` は省略できます。checkpointは必須で、
sampler・steps・cfg・寸法・Hires.fix設定は省略時に既定値を使います。
画像は `output_dir` に一意なファイル名で保存され、後続stepでは
`{"$ref": "context.generate.image"}` で受け取れます。

接続先はローカルホストまたはloopback IPに限られます。WebUI 1111本体やモデルは
同梱せず、既存のHTTP APIを呼び出します。
