# Wildcard行の確率調整

[English](en/wildcard-weighted-lines.md)

Random ImageとPrompt Generateの組み込みwildcard展開では、行頭に重みを指定して行の選択割合を調整できます。

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
