# Wildcard Line Weighting

[日本語](../wildcard-weighted-lines.md)

The built-in wildcard expansion used by Random Image and Prompt Generate accepts a line weight prefix to control how often a line is selected.

```text
@weight=3::<lora:character:0.8>
<lora:character:0.6>
```

Weights are relative. A line without a weight has weight `1`. In this example, the first line is selected about 75% of the time and the second line about 25%. A weight of `0` disables that line.

Do not duplicate a line to increase its share. To select LoRA strength `0.8` about 75% of the time and `0.6` about 25%, write the two lines above once each.

An invalid value or empty body after `@weight=` raises a clear expansion error. A file cannot have zero selectable lines. The existing `{a|b}` choice syntax remains uniform.

## Character wrappers

Use a wrapper wildcard for a character instead of calling a LoRA wildcard directly in the prompt. For example, put these references in `character_with_lora/aoba_moca.txt` and invoke `__character_with_lora/aoba_moca__` from the prompt.

```text
__anime_character_lora/aoba_moca__ __anime_character/バンドリ/青葉モカ__
```

This keeps LoRA choices and character tags in separate files while the wrapper pairs the same character. Keep LoRA syntax in the LoRA-call file and character tags in the regular character wildcard.

In sequential input files, each line is a generation job. The `@weight=` prefix is removed and jobs with weight `0` are skipped. Positive relative weights control candidate selection inside wildcard files; sequential jobs remain in the given order and run once each.
