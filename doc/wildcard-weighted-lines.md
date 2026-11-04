# Wildcard行の確率調整

[English](en/wildcard-weighted-lines.md)

Random ImageとPrompt Generateの組み込みwildcard展開では、行頭に重みを指定して行の選択割合を調整できます。

Random Imageのprompt解決はWildcard / Prompt Resolution Applicationの公開APIを通ります。Applicationがwildcardの参照・ファイル読み込み・重み付き選択・nested展開を担当し、生成側には`ResolvedPrompt`のprompt本文を渡します。順次入力行の読み込みも同Applicationへ委譲します。

```text
@weight=3::<lora:character:0.8>
<lora:character:0.6>
```

重みは相対値です。重みを指定しない行は`1`として扱います。この例では、上の行が約75%、下の行が約25%の割合で選ばれます。重みを`0`にするとその行は選択されません。

同じ行を複製して割合を増やす必要はありません。例えばLoRA強度を`0.8`で約75%、`0.6`で約25%にしたい場合は、上記の2行だけを記述します。

`@weight=`で始まる行の値や本文が不正な場合、展開は明示的なエラーになります。ファイル中の全行を`0`にすることもできません。`{a|b}`形式の選択肢は従来どおり等確率です。

## キャラクター用ラッパー

キャラクター用の呼び出しは、LoRA呼び出しwildcardを直接promptへ入れず、ラッパーwildcardを使います。例えば`character_with_lora/aoba_moca.txt`に次の参照を置き、promptでは`__character_with_lora/aoba_moca__`を呼び出します。

```text
__anime_character_lora/aoba_moca__ __anime_character/バンドリ/青葉モカ__
```

この形なら、LoRAの選択肢とキャラクターwildcardを別々に保守しながら、ラッパーが同じキャラクターの組み合わせを指定できます。LoRA呼び出し用ファイルにはLoRA記法だけを置き、通常のキャラクターwildcardにはキャラクターのタグを置きます。

1回のprompt解決中は、同じwildcardファイルを最初の呼び出しで展開し、その結果を再利用します。そのため同じラッパーを複数回書いても、LoRA強度やキャラクタータグの抽選結果が呼び出しごとに食い違いません。複数promptにまたがって同じ結果を使う場合は、呼び出し側から共有cacheを渡します。

順次生成の入力ファイルでは各行が生成ジョブです。`@weight=`接頭辞は除去され、重み`0`のジョブは読み飛ばされます。正の相対重みはwildcardファイル内の候補選択に使い、順次生成のジョブ列は指定順に各1回処理します。

現在の`ResolvedPrompt`は展開済み本文、検出したLoRA名、wildcard解決元、警告を保持します。LoRA metadataからtrigger/recommended promptを自動統合する処理と、ComfyUI/A1111/Built-in各経路への全面移行は別段階です。
