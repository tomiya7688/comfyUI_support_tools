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
- tracked first-party Python全体の宣言comment coverage report
- bare except / 例外握り潰し
- 新規 shell=True
- 1000行超ファイルの責務監査通知
- 巨大function / classの監査通知

1000行超や120行超functionは自動禁止ではありません。責務境界を確認する監査トリガーです。

宣言comment coverageは次のコマンドで確認できます。

~~~bash
python tools/quality/comment_coverage.py
python tools/quality/comment_coverage.py --path tools --path tests --path src/comfyui_support_tools/shared --path src/comfyui_support_tools/entrypoints --path src/comfyui_support_tools/applications/sequence --path src/comfyui_support_tools/applications/main_gui --path nuno/_touka/fashionpedia_preset_builder.py --path nuno/_touka/fashionpedia_segmentation_model.py --path nuno/_touka/fashionpedia_training_dataset.py --path nuno/_touka/guidance.py --path nuno/_touka/image_enhancer.py --path nuno/_touka/material_estimator.py --path nuno/_touka/touka_batch.py --path nuno/_touka/train_fashionpedia_segmentation.py --path nuno/_touka/translucent_surface_augmenter.py --path scripts/__init__.py --path scripts/app.py --path scripts/context.py --path scripts/context_packet.py --path scripts/runtime_python.py --path scripts/services.py --path scripts/subapp_runtime.py --path scripts/tab_catalog.py --path scripts/widgets --path tabbed_tools_gui.py --path tabbed_tool_gui.py --path scripts/tabs --path scripts/backend --strict
~~~

対象言語はPythonです。Git追跡されたfirst-party Pythonのclass / function / method（同期・非同期、nested、decorator付き、constructorを含む）を対象にします。`.bat`、YAML、JSON、Markdownは現在の規約が対象宣言を定義していないため対象外です。外部checkout、vendored code、generated code、rootのbuild/dist、license成果物、model/user dataも対象外です。`tools/build`のような開発toolのsourceは除外しません。`--path` はfile/directory prefixで対象を絞り、`--strict` は未適用または判定不能があると失敗します。全体移行中はsummaryを基準にし、移行済み領域（tools、tests、shared、entrypoints、applications/sequence、applications/main_gui、nuno/_touka対象9 file、scripts共通部、scripts/widgets、互換launcher、scripts/tabs、scripts/backend）でstrict checkをcompletion gateから実行します。対象file数や宣言数はGit追跡内容から毎回算出します。

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
- a full tracked first-party Python declaration coverage report
- bare except and silently swallowed broad exceptions
- new shell=True usage
- responsibility-audit notices for files over 1000 lines
- audit notices for very large functions and classes

Files over 1000 lines and functions over 120 lines are not automatically forbidden. They trigger an explicit responsibility-boundary review.

Run declaration coverage with `python tools/quality/comment_coverage.py`; the completion gate enforces strict coverage for `tools`, `tests`, the migrated shared and entrypoint packages, Touka implementation files, the legacy `scripts` common modules, widgets, tabs, backend modules, and both compatibility launchers. Python is the covered language. The scanner includes tracked first-party classes/functions/methods, including nested, async, decorated declarations and constructors. `.bat`, YAML, JSON, and Markdown do not define declaration targets under the current standard. It excludes external checkouts, vendored/generated code, root build/dist outputs, license artifacts, and model/user data; development tools such as `tools/build` remain in scope. `--path` filters by file/directory prefix; `--strict` fails on missing or undecidable comments. Counts are recalculated from tracked files at every run. During the repository-wide migration, use the aggregate report; strict enforcement is connected for each migrated area.
