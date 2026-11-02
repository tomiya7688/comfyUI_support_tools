# 共通 Video Frame Analysis Input

動画機能は、brightness filter、OCR、tagging、VLM解析の前に、decoderの出力を
`DecodedVideoFrame` と `normalize_decoded_frame` に通します。decoder固有の設定は
adapterに閉じ込め、consumerには `FrameAnalysisInput` を渡します。

`FrameAnalysisInput` は、幅・高さ、元pixel format、元primaries・transfer・range・matrix
metadata、requested/actual time、PTS/time_base、stream metadata、明示的なdecode状態を
保持します。正常frameにはread-onlyのlinear sRGB/D65 pixelsと0..1 normalized
luminance planeを提供します。packed RGB/BGRの8-bitと16-bit形式を扱います。planar YUVを
渡すdecoderは、元matrixとrangeに従ってpacked RGB/BGRへ変換してからnormalizerを呼びます。
不明なformatはpixelsを返さず `unsupported_pixel_format` にします。

BT.709、sRGB、PQ、HLG transfer functionを処理し、BT.709、BT.2020、Display P3のprimariesを
共通analysis gamutへ変換します。HDR値にはanalysis用のbounded Reinhard luminance mapを
適用します。このrepresentationはsource pixelsのencode/export用代替には使いません。
未対応tagや不正mastering metadataは、閾値を暗黙に変える代わりに明示的に失敗させます。

`detect_active_picture` はuser指定rect、または複数時点で一致するdark-edge rectだけを採用
します。全体が暗いscene、bar位置が不一致、invalid frame、単一frameの場合はfull frameを
維持します。consumerは返されたrectを解析viewへ適用し、source frame自体は変更しません。

## 検証

`tests.test_video_frame_normalization` は、時間方向のletterbox検出、暗いsceneの保護、user
override、SDR/HDR luminance正規化、limited-range 10-bit入力、VFR PTS/time_base復元、未対応
format、破損pixel、decode/timestamp errorを確認します。テスト用のlibav/FFmpeg adapter fixtureは
同じ `DecodedVideoFrame` contractを生成します。production decoderへの接続は各video feature側の
follow-upで行い、この共通層はdecoderの選択や設定を行いません。
