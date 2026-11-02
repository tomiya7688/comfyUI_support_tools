# Fast / Low-VRAM Txt2Img

[English](fast_generation.en.md)

Random Image の ComfyUI 経路で、FLUX.2 Klein 4B Distilled と Sana 系 checkpoint を宣言型 profile として扱い、`system_stats` の GPU VRAM/RAM、利用者が宣言した precision 対応、インストール済みモデル名から任意にルーティングできます。既定は Quality で、明示モデル選択と workflow の model override を尊重します。Fast / Balanced を選んだ時だけ profile の few-step 設定を使います。

FLUX.2 Klein 4B Base は Distilled profile と分け、LoRA fine-tuning capability を宣言し、自動 Fast route の対象から外します。

Native Klein profile は 8 GiB、Sana Sprint は 8 GiB、Sana は 12 GiB の最低VRAMと1 GiBの余裕を宣言します。量子化variantには別の最低VRAM推定値を持たせ、8 GiB GPUでは条件を満たす量子化モデルがインストールされている時だけ候補になります。自動選択はVRAM/RAMの容量だけでなく、ComfyUIが報告する現在の空きメモリも確認します。値は issue に示された対象環境向けの暫定条件で、実測ベンチマーク値や生成可否の保証ではありません。空きメモリが観測できない場合や条件に合うローカルモデルがない場合は自動選択を中止します。量子化ファイルは名前から明示された `fp16` / `bf16` / `fp8` / `int8` / `int4` を識別し、UIで利用者がその形式への対応を宣言した時だけ候補にします。

生成ごとに経過秒数、利用可能なら ComfyUI `system_stats` を500ms間隔で観測したピークVRAM、VRAM/RAM容量、モデル、profile、precision を画像横の `.generation.json` と `generation_history.jsonl` へ保存します。polling peak は短い瞬間的ピークを見逃す可能性があり、未観測値は `null` のまま残します。共有APIでは同じGPUを使う他プロセスのVRAMも含まれます。

共通部品には evaluator callback を使う候補生成・Top-K・任意HQ再レンダー関数と、latency/VRAM/品質指標の履歴集計を用意しました。実際に配布可能な Klein/Sana ComfyUI workflow JSON、workflow node compatibility probe、GUI上の候補比較と自動HQ handoff、prompt alignment evaluator、実モデルによる速度・VRAM・artifact benchmark はこの変更に含まれません。現在の UI では既存の ComfyUI workflow を選び、ローカルモデルを用意する必要があります。profile の step 数とVRAM条件は暫定値で、品質比較を表すものではありません。
