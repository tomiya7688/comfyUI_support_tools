# UPD + パーツ組み換え標準設計

[English](upd_standard.en.md)

このプロジェクトの新規主要Applicationは、**UPD + パーツ組み換え設計（Part Swap Design）** を標準設計とする。

- UPD: UI / Process / Data の責務境界と依存方向を決める。
- Part Swap Design: backend / algorithm / adapter 等を、外部から内部実装を知らずに交換できる閉じたパーツとして設計する。
- UPD Commander Base Design: 複雑なオーケストレーションや通信責務が必要な場合に追加で使う。全Applicationへ強制しない。

参照元:
- https://github.com/tomiya7688/upd-design
- https://github.com/tomiya7688/part-swap-design
- https://github.com/tomiya7688/upd-commander-base-design

## 適用範囲

新規コードは `src/comfyui_support_tools/applications/<application>/` を標準配置とする。
既存の `scripts/` / `nuno/` は一括移行しない。変更対象になった責務から段階的に新構造へ移す。

基本形:

~~~text
Application
├─ UI
├─ Process
└─ Data
~~~

必要になった場合だけ、各層の内部にCommander / Messenger / Processing等の役割を追加する。

## Application境界

ApplicationはUI / Process / Dataが1組として閉じる機能境界とする。
別Applicationの内部moduleへ直接importしてはならない。

Application間通信は以下を使用する。
- HTTP / WebSocket等の明示API
- `shared/contracts` のDTO / Contract
- 明示的なexternal adapter / transport

`shared` に実処理を逃がしてApplication境界を回避してはならない。

## UPD Layer境界

責務上の基本フローは以下とする。

~~~text
要求: UI -> Process -> Data
結果: Data -> Process -> UI
~~~

- UIは外部入力、表示、外部への結果返却を担当する。
- Processはアプリケーション判断、検証、変換、domain flowを担当する。
- Dataは保存、取得、外部data accessを担当する。
- UIからProcessを飛び越えてDataへ直接依存してはならない。
- DataはUI固有表現を知らない。
- ProcessはUI widgetやstorage implementationの内部を知らない。

単純な同一process内処理では、隣接layer間を小さな公開function / Contractで接続してよい。
UPDを適用するためだけにCommander / Messenger classや空folderを作る必要はない。

## Part Swap Design

交換可能な実装は、閉じた呼び出し関係を持つ「パーツ」とする。

例:
- generation backend / workflow adapter
- model family detector
- evaluator / ranker / repair strategy
- image / video filter
- OCR / text detector
- trainer / personalization adapter
- video decode / analysis backend
- storage / cache / artifact / export adapter
- Post Process processor

### パーツ境界

- consumerはパーツ内部moduleを直接importしない。
- consumerはstable input/output Contract、semantic ID、capability、result typeへ依存する。
- 実装AからBへ交換する場合、原則としてcomposition root / registry / config bindingだけを変更する。
- `if backend == ...` / `if model == ...` 等の具象分岐をconsumerへ散らさない。
- internal helperを複数Applicationから直接呼ぶopen call relationshipを作らない。
- 本当に共通な責務は独立パーツまたはshared Contractへ昇格させる。
- 1 ownerしか使わない内部処理を、交換価値がないのに無理にinterface化しない。

### Test

明示的なextension pointでは可能な範囲で:
- public boundary contract test
- fake / minimal implementationによるswap test
- implementation固有test
を分離する。

Contractが許す範囲で実装ごとの結果差は許可し、必須invariant / failure semantics / Acceptanceを検証する。

## Message Orientated Designを使う条件

Message Orientated Designは**独立した状態主体間で選択適用**する。
すべてのmodule/class間通信をMessage化しない。

この文書での「主体」は、独立したstate/lifecycleを持つApplication、service、worker、job runtime、training session、plugin host等を指す。
1主体 / 1part内部では通常のfunction callを使う。

### Message境界を使う

次のような場合:
- async / event / queueで協調する
- process / service / Application / plugin / worker境界を越える
- progress / cancel / completion / failure / state changeを独立eventとして扱う
- sender / receiverが別lifecycleを持つ
- receiverが自分のstateに応じてrequestを解釈する
- receiver / transportを交換可能にしたい

### Message境界を使わない

次のような場合:
- pure helper
- 1つのPart Swap part内部
- 同一owner/lifecycleのlocal algorithm
- 小さな同期validation / conversion
- Message化しても依存関係が減らない

### Message Contract

Message Orientated Designを採用した境界では:

~~~text
Subject A
  -> Sender
  -> immutable Message
  -> Message Manager / transport
  -> Receptor
  -> Subject B internal processing
~~~

- 主体間でprivate/internal functionを直接callしない。
- 他主体のowned stateを直接read/writeしない。
- Messageはimmutableとし、変更が必要なら新しいMessageを生成する。
- responseも選択したMessage境界では新しいMessageとして返す。
- typed/frozen contractを優先し、巨大なuntyped dictを共通protocolにしない。
- Receptorはtype識別とdispatchに限定し、domain判断を持たない。
- Senderは外部へMessageを出す境界とする。
- Message Managerは配送だけを担当し、routing以外のdomain判断、retry policy、model選択、保存、workflow orchestrationを持たない。
- global Message Managerを必須にせず、必要最小のmanager/domain scopeで配送する。
- Message自体へglobal IDを必須にしない。correlationが必要なprotocolだけrequest/run/job IDを持つ。

### 他設計との関係

- UPD: state/meaningを所有するlayerを決める。
- Part Swap: subject内部の実装を交換可能にする。
- Message Orientated Design: independent subject間をMessageで通信させる。
- Commander: 複雑なworkflow順序を指揮する。
- Message Manager: Messageを配送するだけ。

UPD MessengerとMessage Orientated DesignのSender/Receptor/Message Managerは自動的に同一視しない。
責務が一致する場合に限り、同じtransport/boundary implementationとして統合してよい。

### 代表例

~~~text
Character Registry
  -> TrainCharacterRequested
  -> Training Application

Training Application
  -> TrainingProgress
  -> Character Registry / Job UI

Training Application
  -> TrainingCompleted
  -> Character Registry
~~~

Character Registryはtrainer内部関数やtraining session stateを直接操作しない。

## Commanderを使う条件

Commander / Orchestratorは**標準必須ではない**。
次のように、処理順序そのものが意味のある責務になった場合に導入する。

- 複数の独立パーツを順に実行する。
- routing / branchingで次のパーツを選ぶ。
- retry / fallback / Top-K / repair / re-evaluationでflowが変わる。
- long jobのcancel / pause / resume / checkpointがflowに影響する。
- workflow自体を個々のpartと独立して重点testする必要がある。

Commanderを使う場合:
- 呼び出し順序・flow判断のみを担当する。
- algorithm、I/O、HTTP、subprocess、inference、保存処理を持たない。
- part内部へ入り込まず、公開Contractだけを使う。

単純な入力 -> 変換 -> 保存程度のflowに、形式だけのCommanderを置かない。

## Messengerを使う条件

Messengerも標準必須ではない。
通信 / transport自体を独立責務として隔離する価値がある場合に使う。

例:
- async / event / queue
- IPC / subprocess service
- HTTP / WebSocket
- cross-process
- cross-Application
- protocol translation / delivery reliability

Messengerを使う場合:
- payload / Contractを運ぶ。
- domain判断・algorithm・保存処理を持たない。

単純な同一process内の隣接UPD layer接続に、pass-through Messengerを強制しない。

## Shared

`src/comfyui_support_tools/shared/` に置いてよいもの:
- Contract / DTO
- value object
- Application非依存の小さな純粋utility
- 複数Applicationから利用されること自体が責務として成立する交換パーツの公開境界

置いてはいけないもの:
- 特定ApplicationのProcessing
- 特定Applicationの保存処理
- GUI処理
- 他Application内部実装のproxy
- パーツ境界を迂回するためだけに移動したhelper

## Legacyとの共存

- 新規ApplicationはUPD + Part Swap Designで開始する。
- legacyを理由なく一括変換しない。
- legacyから新Applicationへ移した責務だけ旧実装を縮小する。
- legacy Tabへ新しいsubprocess / HTTP / file mutation / inference / scoringを追加せず、触った責務からApplication/partへ移す。

## Checker

architecture checkerは**設計を助ける道具であり、設計正本そのものではない**。

必須:
- UI -> Data bypassを検出する。
- 別Application内部への直接依存を検出する。
- Commanderを使用する場合、Commanderへの実処理混入を検出する。
- Messengerを使用する場合、Messengerへのdomain処理混入を検出する。
- 新規extension pointでconsumerが具体実装へ密結合する構造を可能な範囲で検出/テストする。

禁止:
- 単純なUPD flowへ空のCommander / Messenger scaffoldを要求すること。
- checkerに合わせるためだけに責務のないclass/fileを作ること。

現行 `tools/architecture/upd_check.py` が本規約よりCommander/Messengerを強制する場合、本規約を正本としてchecker側を更新する。
