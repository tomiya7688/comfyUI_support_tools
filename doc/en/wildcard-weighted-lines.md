# Wildcard Line Weighting

[日本語](../wildcard-weighted-lines.md)

The built-in wildcard expansion used by Random Image and Prompt Generate accepts a line weight prefix to control how often a line is selected.

Random Image resolves prompts through the public API of the Wildcard / Prompt Resolution Application. The Application owns wildcard references, file reads, weighted selection, and nested expansion, then returns prompt text in a `ResolvedPrompt`. Sequential input lines are also loaded through this Application.

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

Within one prompt-resolution request, each wildcard file is expanded on its first use and its result is reused. Repeating the same wrapper therefore cannot select different LoRA strengths or character tags at each occurrence. Callers can pass a shared cache to reuse the same choices across multiple prompts.

In sequential input files, each line is a generation job. The `@weight=` prefix is removed and jobs with weight `0` are skipped. Positive relative weights control candidate selection inside wildcard files; sequential jobs remain in the given order and run once each.

The current `ResolvedPrompt` carries expanded text, detected LoRA names, wildcard provenance, and warnings. Automatic merging of trigger/recommended prompts from LoRA metadata and migration of every ComfyUI/A1111/Built-in route are separate steps.
