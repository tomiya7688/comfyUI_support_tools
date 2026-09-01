# 0. agnet.md

0.は編集しないこと
AIがこのプロジェクトの概要や構成などを理解するためのファイル
コンテキスト使用量の削減をめざすためのAI自信のためのメモである
勝手に編集して構わないので好きにagentは設計等のメモを記入すること

# 1.機能

- ToukaのAI対象推定は、Touka専用venvのCUDA PyTorchを使う。学習済み重みは `user_data/input/models/touka`、Fashionpediaデータは `user_data/input/image/dataset/fashionpedia` に置く。
- Fashionpediaは通常の衣類形状の事前学習用であり、半透明素材越しの推定には別途合成透過データを作って追加学習する。詳細な段階と完了条件は `doc/実装予定.md`。


