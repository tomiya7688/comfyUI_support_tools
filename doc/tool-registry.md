# Tool / Settings Registry

[English](tool-registry.en.md)

`scripts/tool_registry.py` がlegacy toolのstable ID、label、category、settings ID、実装binding、media/action metadata、migration状態の正本です。UI shellはdescriptor順にbindingを遅延importし、`scripts.tab_catalog.TAB_CATALOG`と`STABLE_SETTINGS_IDS`は同じdescriptorから導出します。class名はlegacy settings migration用のadapter metadataだけに使い、stable tool IDにはしません。

`ToolRegistry` はID/settings ID/legacy classの重複を登録時に拒否します。既存のtab orderを維持し、label `{backend}` templateをshellで解決します。新しいtabはdescriptorを1件追加してimplementation bindingを指定すれば、app登録・catalog・settings mappingへ個別の重複記述を加えずに接続できます。new Applicationはlegacy registryへの登録を必須としません。

検証はfake extension binding、duplicate rejection、legacy order、settings ID migration adapterを確認します。
