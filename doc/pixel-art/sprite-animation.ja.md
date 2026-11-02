# Pixel Sprite Animation / Sheet Creator

`shared.pixel_sprite` にcanonical spriteを基準にするsequence契約と差し替え可能なframe generatorを追加しました。選択した1/4/8方向とactionのframeを生成し、nearest-neighborで固定cellへ収め、canonical spriteのpaletteを全frameに適用します。方向・action・frame index順で厳密なgridへpackし、個別PNG、sprite sheet PNG、座標付きanimation JSON、任意のloop GIF/lossless WebPを出力します。`repack` APIへ外部修正済みframeを渡すと、同じcell・paletteで再packできます。

生成model、pose control workflow、character identity embeddingは同梱していません。設定済みA1111/ComfyUI backendでcanonical spriteをconditionにするimg2img frame draft adapterを用意しましたが、identityやposeの正しさを保証しません。identity evaluatorがない場合は手動review対象と明示します。出力は一時directoryで完成後に移動し、既存assetsの上書きを拒否します。
