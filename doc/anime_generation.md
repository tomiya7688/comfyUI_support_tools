# Anime / Illustration Prompt Routing

[English](anime_generation.en.md)

Prompt Generate画面でAnime/Illustrationのuse case（general / character / background / manga）とcontent profile（unspecified / SFW / NSFW）を選べます。チェックポイント名が登録profileに一致すると、Animagine XL、Illustrious XL、NoobAI XL、汎用SDXLそれぞれのquality・intent・rating・negative tag policyを適用します。同一tagを重複追加せず、適用profile・routing理由・選択モデルをgeneration metadataへ記録します。

通常は手動選択したcheckpointを保持します。任意のAuto-routeを有効にすると、ローカルcatalog内のprofileからuse caseの宣言適合度を優先し、prompt内LoRAのfamily metadataが分かる場合は互換profileだけを候補にします。Auto-route時にLoRA familyを判定できなければ安全な選択を装わず停止します。手動選択モデルに既知の非互換anime LoRAが指定された場合も生成を拒否します。ComfyUIの明示的なnode model overrideがある場合、Auto-routeは拒否します。

`AnimeModelRegistry`にはalias、family ID、lineage、native resolution、prompt policy、LoRA互換family、license参照、training-base suitability、use-case適合宣言をprofileとして登録します。別familyを追加する際にrouting algorithmや既存のmodel classifierへ分岐を足す必要はありません。benchmark helperは同一caseを各profileのprompt policyで個別に展開し、出力比較で使用した入力を記録できます。

## 検証範囲と制限

- 組み込みpolicyは初期descriptorです。Animagine / Illustrious / NoobAIの実checkpointでprompt品質を測定したbaseline、validation set、metric、before/after比較はまだありません。routerは宣言されたuse-case適合度を並べるだけで、画像品質の勝者を主張しません。
- license参照は各model card URLです。license text/versionや利用条件は自動取得・検証せず、profile上のtraining-base suitabilityもunknownのままです。配布やtrainingへ利用する前にモデルversionの条件を確認してください。
- Character / backgroundのintent policyはprompt層へ接続されていますが、Character Generator、Landscape generator、#55 LoRA Method Selector、#20 Evaluator、Workflow Presetとの専用handoffはありません。実model/LoRA/workflowでの生成品質も未検証です。
- model familyの誤判定、登録外model、family不明LoRAは自動的に適合扱いしません。登録外checkpointにはpromptを書き換えず、手動選択を維持します。

対象テストはfamily descriptorの追加、prompt tag順序/deduplication、use-case routing、既知LoRA互換性、explicit selection、profile別benchmark prompt生成、backend adapterへのprompt/model受け渡しを確認します。
