# JSON-like Comment Out の適用範囲と検査

## 基本ルール

形式の正本は[Json-like-comment-outs の日本語仕様](https://github.com/tomiya7688/Json-like-comment-outs/blob/main/docs/jp/SPECIFICATION.md)です。このリポジトリでは、宣言レベルの説明として以下を必須にします。

- クラス: 責務と主要フィールド（主要状態の意味）を説明する。
- 関数・メソッド: 責務、処理順、引数、戻り値を説明する。該当する引数や戻り値がない場合も項目を省略せず、空のリスト等で明示する。
- 処理・状態の変化を説明し、実装と一致させる。
- キー名の言語は固定しない。意味が分かる名前を一貫して使う。
- 関数・メソッド内部の処理説明、条件分岐、ローカル変数には通常コメントを使う。

## 対象

自作・Git追跡対象のPythonソースを検査します。現在の対象領域はリポジトリ直下のPythonファイル、および nuno/、scripts/、src/、tests/、tools/ にあります。対象宣言はクラス、関数、メソッドです。非同期関数、ネスト宣言、__init__等の特殊メソッド、抽象メソッド、Protocol/interface相当のクラス、decorator付き宣言も含みます。decoratorがある場合、コメントは最初のdecoratorより前に置きます。

引数や戻り値の有無、public/private、抽象/具象による除外はしません。

現在の4つの追跡済み .bat は起動・分岐ラベルのみで、call :label で呼ばれるサブルーチン宣言はありません。YAML・JSON等の設定、Markdown、テキスト、画像、ライセンス文書はクラス/関数/メソッド宣言がないため対象外です。

外部チェックアウト・vendor、生成コード（generated/、*_pb2.py等）、build/dist/cache/output、user_data/、モデル・checkpoint・wildcardデータは対象外です。未追跡ファイルは走査せず、Gitの追跡ファイル一覧を基準にします。

## 検査の意味と限界

tools/architecture/comment_coverage.py はPython ASTから対象宣言を列挙し、decoratorを含む宣言の直前に連続して置かれた # コメントを調べます。コメント本文が外側の { ... }、対応する括弧、およびトップレベル項目を持つ場合に「covered」と数えます。普通のコメントや宣言本体内のコメントは宣言コメントに数えません。

この検査器は意味キーの同義語を推測せず、説明の正確さ、クラスの責務/フィールドや関数の責務/処理/引数/戻り値の内容までは検証しません。それらはレビューで確認します。構造候補の括弧不整合やPython構文解析不能は「unrecognized」とし、未記載とは別にcompletion gateを失敗させます。

## 段階移行とcompletion gate

既存コード全体を一括編集すると無関係な変更とレビュー負荷が大きいため、初期ベースラインはファイル別の既存未記載数を記録します。completion gateはファイル単位でベースラインとの増減を検査し、移行Issueでファイルを直した際に許容数をレビューして減らすまで失敗させます。ベースラインの自動更新は行いません。

親Issueの全移行が完了した時点で、ベースラインを空にし、全対象で uncovered=0 を確認してから段階移行用の許容を撤去します。報告は次のコマンドで確認できます。

    python tools/architecture/comment_coverage.py --list-uncovered
