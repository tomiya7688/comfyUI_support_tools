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

Message Orientated Designの正本に従い、Messageの意味上の最小構造は次とする。

~~~text
Message
├ from
├ to
├ type
└ content
~~~

- `from`: 送信主体
- `to`: 受信主体
- `type`: Messageの意味
- `content`: そのMessageが運ぶ内容

Python実装では、frozen dataclass等のtyped Message / envelopeを使ってよい。
Message typeをclass型で表現する場合でも、routing/serialization時に上記4要素の意味を失わない。
共通base classや継承階層は必須にしない。

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

## Process Orchestrator / Workflow Processingを使う条件

動的な反復やworkflow algorithm自体が実処理になる場合は、**Process層のOrchestrator / Workflow Processing** として扱う。
Commanderとは別責務とする。

対象例:
- 可変step数のsequence実行
- candidateごとのBest-of-N / Top-K評価loop
- retry budgetを消費する反復
- repair -> re-evaluate loop
- state machineのstep進行
- batch itemを順次処理するworkflow

Process Orchestratorは:
- workflow algorithm / iteration / state transitionを実装してよい。
- public Part Contractを使って交換可能partを呼び出してよい。
- UI widget操作やData保存方式を知らない。
- HTTP / subprocess / inference等の外部I/Oそのものを抱えず、適切なPart/Data/transport Contractへ委譲する。
- loopがあること自体は違反ではない。loop内へ別責務を混ぜないことを重視する。

`SequenceRunner` のような「定義されたstep列をfailure policy付きで反復実行する処理」は、この分類が自然である。

## Commanderを使う条件

Commanderは**標準必須ではない**。
UPD Commanderの原則に従い、「受け取ったrequest/resultから次に呼ぶProcessing / Messengerを選ぶ制御点」が必要な場合だけ導入する。

導入例:
- command typeに応じてProcessingを選択する。
- Processing結果に応じて次のProcessing / Messengerを選択する。
- async responseの継続先を管理する。
- layer境界のrequest/resultを中央のcontrol pointでdispatchする。

Commanderを使う場合:
- call targetの選択・dispatch・成功/失敗/継続先の選択だけを担当する。
- algorithm、I/O、HTTP、subprocess、inference、保存処理を持たない。
- 複雑なloop / candidate iteration / retry algorithmはProcess Orchestrator / Processingへ置く。
- part内部へ入り込まず、公開Contractだけを使う。
- 継続に必要な最小限のID/stateだけ保持してよい。

単純な入力 -> 変換 -> 保存程度のflowに、形式だけのCommanderを置かない。

### CommanderとProcess Orchestratorの違い

- **Commander:** 次に「どの処理を呼ぶか」を選ぶ。
- **Process Orchestrator:** workflowを「どう反復・進行させるか」を実装する。

両方必要な場合、CommanderはOrchestratorを1つのProcessingとして呼び出し、Orchestrator内部のworkflow algorithmへ入り込まない。

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

## 設計判断フロー

新しい責務を追加するときは、次の順序で判断する。

| 質問 | Yes | No |
|---|---|---|
| 外部との入力・表示・返却か | UIへ置く | 次へ |
| application rule / decision / domain flowか | Processへ置く | 次へ |
| persistence / retrieval / external data accessか | Dataへ置く | 次へ |
| 実装を交換する価値があるか | Part Contractを定義 | owner内部へ保持 |
| 相手が独立state/lifecycle主体か | Message候補 | function call候補 |
| async / process / service境界か | Message / transportを優先 | sync Contract可 |
| dynamic iteration / retry / candidate loopがあるか | Process Orchestrator候補 | plain Processで十分 |
| request/resultのdispatch control pointが必要か | Commander候補 | direct callで十分 |
| communication自体が複雑か | Messenger / transport候補 | direct adjacent Contractで十分 |

### Stop rule

以下がそろう場合は、抽象化を増やさない。

- ownerが1つ
- implementationが1つ
- simple synchronous call
- lifecycleを共有
- 独立交換の必要性が低い
- testabilityが改善しない

「将来使うかもしれない」だけでMessage / Commander / registry / interfaceを追加しない。

## 標準パターン

### Pattern A: simple synchronous feature

~~~text
UI
 -> Process
 -> Data
~~~

Commanderなし。
Messageなし。

### Pattern B: swappable backend

~~~text
UI
 -> Process
 -> Backend Contract
      ├─ Qwen Part
      ├─ SDXL Part
      └─ FLUX Part
~~~

UPD + Part Swap。
consumerはconcrete backend内部を知らない。

### Pattern C: long-running worker

~~~text
Application
 -> StartRequested Message
 -> Worker Subject
 -> Progress Message
 -> Completed / Failed Message
~~~

UPD + Message Orientated Design。
worker内部algorithmは通常のfunction call。

### Pattern D: quality orchestration

~~~text
Process Orchestrator
 -> Router Part
 -> Generator Part(s)
 -> Evaluator Part(s)
 -> Ranker
 -> Repair
 -> Retry / Fallback
~~~

UPD + Part Swap + Process Orchestrator。
request/result dispatch pointが別に必要ならCommanderを外側へ追加する。
Messageはprocess/service境界が必要な場合だけ追加する。

### Pattern E: cross-Application training

~~~text
Character Registry Subject
 -> TrainCharacterRequested
 -> Training Subject

Training Subject
 -> TrainingProgress
 -> TrainingCompleted
 -> Character Registry Subject
~~~

UPD + Part Swap + Message。
Training内部のmethod selectionが複雑ならCommanderも追加する。

## Contract taxonomy

Contractは用途を混ぜず、意味ごとに分ける。

### Value / DTO Contract
stateを持たない境界data。

例:
- settings snapshot
- generation request values
- evaluation result
- artifact reference

### Part Contract
交換可能実装のinput / output / capability。

例:
- GenerationBackend
- Evaluator
- OCR detector
- Trainer adapter

### Message Contract
独立stateful subject間のimmutable communication。

例:
- TrainCharacterRequested
- TrainingProgress
- CancelRequested
- TrainingCompleted

generic `request/response` kindを必須にせず、message type自体で意味を表してよい。

### Operation / Job Contract
run / cancel / resume / progress / retry / artifact等のexecution semantics。

#435-#441の共通contractを優先する。

### External API Contract
HTTP / WebSocket / IPC等のtransport boundary。

内部modelをそのまま外部wire formatへ露出させず、必要に応じadapterで変換する。

## State ownership

mutable stateにはownerを1つ決める。

- owner外から直接mutateしない。
- subject境界ではMessageで変更要求を送る。
- Part境界ではinputを渡しresultを返す。
- shared mutable global stateをcommunication channelにしない。
- cacheもowner / lifecycle / invalidationを明示する。
- UI widget stateをProcess/Dataから直接操作しない。
- worker/job stateを別Applicationから直接書き換えない。

## Error / cancellation semantics

### Plain function / Part boundary

同期のlocal boundaryでは:
- typed result
- explicit exception
- result object with failure detail

等を使用してよい。

### Message boundary

Message境界では必要に応じsemantic Messageを使う。

例:
- RequestRejected
- OperationFailed
- CancelRequested
- CancelAccepted
- Cancelled
- Completed

Message Managerがfailureを解釈してretry/domain判断してはいけない。
retry / fallback判断はProcess / Commanderの責務。

### Correlation

global Message IDは不要。
次の場合だけcorrelation IDを持たせる:
- requestとresponseを結びたい
- multiple concurrent jobs
- progress/cancel対象のrunを識別したい
- distributed transportでtraceが必要

#435 Run Manifestのrun_id等が既に意味を満たす場合は再発明しない。

## Testing matrix

| Design axis | 主なtest |
|---|---|
| UPD | layer responsibility / UI->Data bypass / Application internal dependency |
| Part Swap | public contract / fake replacement / consumer unchanged |
| Message | immutability / type dispatch / response-failure-cancel / delivery-only manager / receiver replacement |
| Process Orchestrator | workflow iteration / state transition / retry-repair loop / I/O分離 |
| Commander | dispatch / continuation selection / direct work・複雑loopなし |
| External transport | serialization / timeout / protocol error / reconnect等、必要なtransport semantics |

internal helper testだけでboundary完成扱いにしない。
逆に、Messageを使わないlocal functionへMessage infrastructure testを要求しない。

## Directory patterns

物理directoryは責務を補助するためのものとし、空構造を作ることを目的にしない。

### Simple Application

~~~text
applications/example/
├ ui/
│  └ view.py
├ process/
│  └ service.py
└ data/
   └ store.py
~~~

### Complex Application

必要な役割だけ追加する。

~~~text
applications/example/
├ ui/
├ process/
│  ├ commander/
│  ├ processing/
│  └ messaging/        # Message boundaryが必要な場合のみ
└ data/
~~~

既存の `messenger/` / `commander/` 配置は有効な責務がある限り維持してよい。
新規コードで形式だけのfolderを作らない。

## Architecture review checklist

新規Application / major featureの設計レビューでは、必要な項目だけ確認する。

### Responsibility
- [ ] UI / Process / Dataのownerが説明できる
- [ ] UI -> Data bypassがない
- [ ] 別Application internal dependencyがない

### Part boundary
- [ ] 交換価値がある責務だけPart化している
- [ ] consumerがprivate implementationを知らない
- [ ] swap時の変更がcomposition root / binding / part内部へ閉じる
- [ ] fake/minimal replacement testが有効なら用意する

### State / Message
- [ ] mutable state ownerが1つ
- [ ] 独立state/lifecycle主体間だけMessageを検討している
- [ ] Message境界ならfrom/to/type/content semanticsとimmutabilityを保つ
- [ ] Receptor / Message Managerへdomain処理が漏れていない
- [ ] global busを不要に導入していない

### Orchestration
- [ ] dynamic loop / retry / candidate iterationが必要ならProcess Orchestratorへ置いている
- [ ] simple flowならOrchestrator / Commanderなしで済ませている
- [ ] Commander導入理由がdispatch / continuation controlとして説明できる
- [ ] Commanderへalgorithm / complex loop / I/Oが入っていない

### Runtime / quality
- [ ] #435-#441のshared execution contractを再利用できる
- [ ] quality-sensitiveならgenerator/evaluatorを分離している
- [ ] cancellation / failure / artifact ownershipが明確

### Complexity stop
- [ ] interface / registry / Message / Commanderを「将来用」だけで追加していない
- [ ] 1 owner内部を過分割していない

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
