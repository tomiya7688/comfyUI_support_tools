# Character Registry

[English](character-registry.en.md)

`comfyui_support_tools.applications.character_registry` は、stable `character_id` をキーにidentity、衣装、参照画像、prompt policyを保存するCharacter asset機能です。GUIの「Character Library」から登録・名前変更・alias設定・衣装profile作成、identity/outfit/conditional traitの追加・編集・reject、画像登録、resolved prompt previewを利用できます。

core identityと衣装traitは別管理です。ユーザーがcustom outfitのcategoryを指定すると、同じcategoryの登録衣装traitだけを抑制します。hidden traitは通常omitし、camera/pose/materialのvisibility evidenceまたはユーザーの明示指定がある場合だけpromptへ加えます。visibility decisionにはevidence reasonとconfidenceを含めます。

profileはJSONでatomicに保存し、既存profileの更新は読み込み時hashによるoptimistic concurrencyで競合を拒否します。名前変更後も内部IDは維持します。画像登録は元画像hashを記録してexact duplicateを検出し、reference-only、managed WebP、Original + WebPを選べます。training source選択ではoriginalを優先し、compressed-onlyの場合はwarningを返します。

dataset readinessはselected/effective image count、exact duplicate ratio、平均quality、outfit count、low-shot strategy suggestionを返し、画像枚数だけで学習を禁止しません。

## 現在の境界

Character Libraryは現在のTkアプリへ接続済みです。traitの自動分類、衣装cluster候補、Media BrowserからのAdd to Character、生成画像の取り込み、training adapterへの一クリックhandoff、既存#55/#274/#277/#278/#282/#356/#357への実接続、model-family別verbosity、prompt conflict resolverの構造化カテゴリ共有は未接続です。readiness指標は初期のheuristicであり、学習可能性を校正した評価値ではありません。これらを完了したとは扱いません。
