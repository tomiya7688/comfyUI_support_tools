# Code quality gate / コード品質ゲート

[日本語](#日本語) | [English](#english)

## 日本語

このディレクトリは、既存legacyコードを一括で失格にせず、**新規・変更コードの品質悪化を止める**ための品質ゲートを管理します。

### 実行

~~~bash
python -m pip install -r requirements-dev.txt
python tools/quality/quality_gate.py
~~~

PRではbase branchとの差分Pythonファイルを検査します。

主な検査:

- Ruffによる高信頼なPython不具合検査
- 新規Pythonファイルへのより厳しいRuff検査とformat check
- 新規class / function / methodのJSON-like Comment Outs
- bare except / 例外握り潰し
- 新規 shell=True
- 1000行超ファイルの責務監査通知
- 巨大function / classの監査通知

1000行超や120行超functionは自動禁止ではありません。責務境界を確認する監査トリガーです。

## English

This directory contains the incremental quality gate used to **stop new or modified code from making quality worse without declaring all legacy code invalid at once**.

### Run

~~~bash
python -m pip install -r requirements-dev.txt
python tools/quality/quality_gate.py
~~~

On pull requests, the gate inspects Python files changed from the base branch.

Main checks:

- high-confidence Python defect checks with Ruff
- stricter Ruff checks and formatting for newly added Python files
- JSON-like Comment Outs on newly added classes, functions, and methods
- bare except and silently swallowed broad exceptions
- new shell=True usage
- responsibility-audit notices for files over 1000 lines
- audit notices for very large functions and classes

Files over 1000 lines and functions over 120 lines are not automatically forbidden. They trigger an explicit responsibility-boundary review.
