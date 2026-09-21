# UPD Commander 標準設計

このプロジェクトの新規主要Applicationは、`upd-commander-base-design` を基準として
**Application境界 + UI / Process / Data + Commander / Messenger / Processing** で構成する。

参照元:
- https://github.com/tomiya7688/upd-commander-base-design
- `specification/application-boundary.md`
- `specification/layer-spec.md`
- `specification/commander-spec.md`
- `specification/messenger-spec.md`
- `specification/processing-spec.md`

## 適用範囲

新規コードは `src/comfyui_support_tools/applications/<application>/` を標準配置とする。
既存の `scripts/` / `nuno/` は一括移行しない。変更対象になった責務から段階的に新構造へ移す。

```text
src/comfyui_support_tools/
├─ entrypoints/
├─ applications/
│  └─ <application>/
│     ├─ ui/
│     │  ├─ commander/
│     │  ├─ messenger/
│     │  └─ processing/
│     ├─ process/
│     │  ├─ commander/
│     │  ├─ messenger/
│     │  └─ processing/
│     └─ data/
│        ├─ commander/
│        ├─ messenger/
│        └─ processing/
└─ shared/
   └─ contracts/
```

## Application境界

ApplicationはUI / Process / Dataが1組として閉じる機能境界とする。
別Applicationの内部moduleへ直接importしてはならない。

Application間通信は以下だけを使用する。
- HTTP / WebSocket等の明示API
- `shared/contracts` のDTO / Contract
- 将来導入する明示的なexternal adapter

`shared` に実処理を逃がしてApplication境界を回避してはならない。

## Layer境界

正式な流れは以下とする。

```text
UI <-> Process <-> Data
```

UIからDataへの直接依存は禁止する。
Processingは別layerのProcessingを直接呼び出さない。
layer間通信はMessengerを通す。

同一プロセス内のMessenger実装であっても、境界を消してよい意味ではない。

## Commander

Commanderは処理順序・呼び出し先の選択だけを担当する。

置いてよいもの:
- command種別の判定
- Processingの選択
- Messengerへの配送指示
- 成功/失敗/継続先の選択

置いてはいけないもの:
- ファイル/DB/APIアクセス
- subprocess実行
- 業務計算
- 複雑なloop
- UI描画
- serialize/deserialize

実処理は各layerのProcessingへ置く。

## Messenger

Messengerはlayer間通信のみ担当する。
payloadの業務的意味を解釈して判断しない。
通信成立に必要な最小限のwrap/unwrapだけ許可する。

## Processing

各layerの実処理を担当する。

- UI Processing: 表示、入力解釈、UI固有変換
- Process Processing: アプリケーションロジック、状態遷移、判定
- Data Processing: 保存、取得、外部形式変換

別layerの情報が必要な場合、ProcessingはCommanderへ要求を返す。

## Shared

`src/comfyui_support_tools/shared/` に置いてよいもの:
- Contract / DTO
- value object
- Application非依存の小さな純粋utility

置いてはいけないもの:
- 特定ApplicationのProcessing
- 保存処理
- GUI処理
- 他Application内部実装のproxy

## Legacyとの共存

- 新規ApplicationはUPD準拠で開始する。
- legacyを理由なく一括変換しない。
- legacyから新Applicationへ移した責務だけ旧実装を縮小する。
- Application間API-only方針は既存のarchitecture checkと併用する。

## Checker

`tools/architecture/upd_check.py` は新規 `src/.../applications/` のみstrictに検査する。

現在の主要rule:
- `UPD101`: layer/role越境import
- `UPD102`: 別Application内部への直接import
- `UPD201`: Commander内loop
- `UPD202`: Commander内計算式
- `UPD203`: Commander内の直接IO/API/subprocess等

legacyはこのcheckerの対象外とし、新規領域からstrict適用する。
