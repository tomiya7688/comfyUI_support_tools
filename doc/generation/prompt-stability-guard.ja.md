# Prompt Stability Guard

共有 `prompt_stability` capabilityは、prompt構造、選択したSFW/NSFW品質mode、backend/model family、LoRAの役割・強度、任意の過去failure情報を解析します。policyはcontent mode・model family・backendごとに登録できます。提案のみ、自動適用、回数上限付き評価・retryの計画に加え、prompt、negative、generation config、candidate budgetのadapterを提供します。ユーザー固定値、個別調整の無効化、元prompt指定、計算budgetを適用してから計画を返します。履歴はprompt本文を保存せず、hashと結果metadataだけをappend-onlyで記録します。

Random Imageタブに、opt-inのSFW/NSFW mode、適用方法、budget、調整案表示を追加しました。candidate expansionはbackend requestを追加して出力を個別保存します。内蔵の生成後feedbackは画像decodeと極端な単色化の検出に限られ、人体・本人性・絵柄の評価、backend固有configの調整、local repairはまだhost adapter統合が必要です。共有APIにはその接続点がありますが、テキストだけのheuristicで画像品質を保証しません。Guardは既定でOFF、suggest-onlyでは生成入力を変更しません。
