# Txt2GIF Anime（Issue #347）

短尺ループ向けの共通処理は`shared.txt2gif`にあります。`Txt2GifRequest`は4〜15fps、8〜48 frame、palette色数、dither、最大容量、解像度と総画素予算を検証します。`AnimationBackendRegistry`へstill生成と領域抽出を行うbackendを登録し、`Txt2GifApplication.generate()`から実行します。

Key Art Firstでは一枚のcanonical stillを基準にします。backendは動かすsubjectをRGBA layerとして切り出し、元の領域をinpaintしたclean plateと一緒に返します。`render_key_art_loop()`は静止plateを保ち、各layerを周期変位させ、最後のframeを最初のframeとpixel一致させます。GIF encoderは全frameから共有paletteを構成し、ditherとloop playbackを設定します。容量上限を超えた場合はpaletteを段階縮小し、次に解像度を下げ、minimum dimensionでも超える場合は不完全ファイルを残さず失敗します。

現時点で実装済みなのはbackend protocol/registry、Key-Art motion renderer、loop closure、palette encoder、size budget、progress callback、出力診断です。ComfyUI txt2img接続、AnimateDiff/ToonCrafterのworkflow adapter、人物segmentation、clean-plate inpainting、region mask editor、desktop UI、実モデル品質評価は未実装です。これらのadapterが揃うまで、共通処理だけでpromptから完成GIFを生成する実行可能な既定backendはありません。直接動画生成や長尺narrativeへの自動fallbackもしません。

`tests.test_txt2gif`はPillow fixtureでregion-only motion、固定背景、loop seam、共通palette/GIF timing、サイズ超過時のatomic failure、backend orchestrationを検証します。
