"""State boundary tests for the Character Registry panel controller."""

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from src.comfyui_support_tools.applications.character_registry.ui.processing.character_registry_panel import (
    CharacterRegistryPanel,
    _write_wildcards_and_describe,
)
from src.comfyui_support_tools.shared.contracts.character_outfit_profile import (
    CharacterOutfitProfile,
)


# {
#   責務: [_StatusVariable: Tk StringVarのstatus表示動作を代替する]
#   フィールド: [value: 最後に設定されたstatus文字列]
# }
class _StatusVariable:
    """Capture status updates without creating a Tk window."""

    # {
    #   責務: [__init__: 空のstatus valueを初期化する]
    #   処理: [valueへ空文字を保存する]
    #   引数: [self: fake Tk variable]
    #   戻り値: []
    # }
    def __init__(self) -> None:
        self.value = ""

    # {
    #   責務: [set: status表示値を保存する]
    #   処理: [呼出し元から渡された文字列を保持する]
    #   引数: [self: fake Tk variable, value: 表示するstatus]
    #   戻り値: []
    # }
    def set(self, value: str) -> None:
        self.value = value


# {
#   責務: [CharacterRegistryPanelStateTests: 登録前入力照合とwildcard出力案内を検証する]
#   フィールド: [unittest assertion機能]
#   処理: [Tk windowを作らずcontroller state boundaryを検証する]
# }
class CharacterRegistryPanelStateTests(unittest.TestCase):
    """Verify registration uses the displayed preview and reports absent LoRA mappings."""

    # {
    #   責務: [test_changed_form_requires_preview_refresh: preview後の入力変更を登録前に拒否する]
    #   処理: [form snapshot不一致時にstatus案内を出し, saveを開始しない]
    #   引数: [self: unittest.TestCase]
    #   戻り値: []
    # }
    def test_changed_form_requires_preview_refresh(self) -> None:
        panel = object.__new__(CharacterRegistryPanel)
        panel.preview = object()
        panel._preview_request = object()
        panel._preview_candidate = None
        panel.status = _StatusVariable()
        panel._build_request = lambda: object()
        panel._selected_candidate = lambda: None

        panel.register_profile()

        self.assertIn("previewを作り直してください", panel.status.value)

    # {
    #   責務: [test_confirmation_keeps_innerwear_separate: confirmationでinnerwearをgarmentから分離する]
    #   処理: [UI listsからconfirmationを作り, garment_traitsとinnerwear_traitsを個別に確認する]
    #   引数: [self: unittest.TestCase]
    #   戻り値: []
    # }
    def test_confirmation_keeps_innerwear_separate(self) -> None:
        panel = object.__new__(CharacterRegistryPanel)
        panel.identity_tags = ["blue_hair"]
        panel.confirmed_outfits = []
        panel.outfit_tags = ["school_uniform"]
        panel.innerwear_tags = ["undershirt"]
        panel.outfit_id = SimpleNamespace(get=lambda: "default")
        panel.outfit_name = SimpleNamespace(get=lambda: "Default")
        panel.default_outfit_id = SimpleNamespace(get=lambda: "")

        confirmation = CharacterRegistryPanel._build_confirmation(panel)

        outfit = confirmation.outfit_profiles[0]
        self.assertEqual(confirmation.confirmed_identity_traits, ("blue_hair",))
        self.assertEqual(outfit.garment_traits, ("school_uniform",))
        self.assertEqual(outfit.innerwear_traits, ("undershirt",))

    # {
    #   責務: [test_confirmation_contains_multiple_outfits: confirmationに複数の衣装profileを保持する]
    #   処理: [保存済み衣装と入力中衣装を渡し, 両方と既定衣装参照を検証する]
    #   引数: [self: unittest.TestCase]
    #   戻り値: []
    # }
    def test_confirmation_contains_multiple_outfits(self) -> None:
        panel = object.__new__(CharacterRegistryPanel)
        panel.identity_tags = ["blue_hair"]
        panel.confirmed_outfits = [
            CharacterOutfitProfile(
                outfit_id="school",
                name="School Uniform",
                garment_traits=("school_uniform",),
                user_confirmed=True,
            ),
            CharacterOutfitProfile(
                outfit_id="casual",
                name="Casual",
                garment_traits=("casual_clothes",),
                user_confirmed=True,
            ),
        ]
        panel.outfit_tags = []
        panel.innerwear_tags = []
        panel.outfit_id = SimpleNamespace(get=lambda: "outfit-3")
        panel.outfit_name = SimpleNamespace(get=lambda: "Outfit 3")
        panel.default_outfit_id = SimpleNamespace(get=lambda: "casual")

        confirmation = CharacterRegistryPanel._build_confirmation(panel)

        self.assertEqual(
            tuple(outfit.outfit_id for outfit in confirmation.outfit_profiles),
            ("school", "casual"),
        )
        self.assertEqual(confirmation.default_outfit_id, "casual")
        self.assertEqual(
            confirmation.outfit_profiles[1].garment_traits,
            ("casual_clothes",),
        )

    # {
    #   責務: [test_save_outfit_profile_marks_first_outfit_as_default: 追加した衣装を確認済み一覧へ積む]
    #   処理: [衣装入力をsaveし, profileと既定表示を検証する]
    #   引数: [self: unittest.TestCase]
    #   戻り値: []
    # }
    def test_save_outfit_profile_marks_first_outfit_as_default(self) -> None:
        panel = object.__new__(CharacterRegistryPanel)
        panel.confirmed_outfits = []
        panel.outfit_tags = ["school_uniform"]
        panel.innerwear_tags = []
        panel.outfit_id = SimpleNamespace(get=lambda: "school", set=lambda _value: None)
        panel.outfit_name = SimpleNamespace(get=lambda: "School Uniform", set=lambda _value: None)
        default_value = {"value": ""}
        panel.default_outfit_id = SimpleNamespace(
            get=lambda: default_value["value"],
            set=lambda value: default_value.update(value=value),
        )
        panel.status = _StatusVariable()
        panel._render_confirmed_tags = lambda: None
        displayed: list[str] = []
        panel.default_outfit_combo = SimpleNamespace(configure=lambda **_kwargs: None)
        panel.saved_outfit_list = SimpleNamespace(
            delete=lambda *_args: displayed.clear(),
            insert=lambda _index, value: displayed.append(value),
        )

        CharacterRegistryPanel._save_outfit_profile(panel)

        self.assertEqual(len(panel.confirmed_outfits), 1)
        self.assertEqual(panel.confirmed_outfits[0].outfit_id, "school")
        self.assertEqual(default_value["value"], "school")
        self.assertEqual(displayed, ["School Uniform (school)"])
        self.assertEqual(panel.outfit_tags, [])

    # {
    #   責務: [test_missing_local_lora_mapping_is_explained: LoRA候補未登録時の手動設定案内を確認する]
    #   処理: [character wildcard出力後, 対応LoRA fileがない場合に作成pathをstatusへ含める]
    #   引数: [self: unittest.TestCase]
    #   戻り値: []
    # }
    def test_missing_local_lora_mapping_is_explained(self) -> None:
        profile = SimpleNamespace(character_id="sample_character", display_name="Sample")

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            messenger = SimpleNamespace(
                write_character_wildcard_files=lambda _profile, _root: (
                    root / "anime_character" / "sample_character.txt",
                )
            )

            succeeded, message = _write_wildcards_and_describe(messenger, profile, root)

        self.assertTrue(succeeded)
        self.assertIn("対応LoRAは未設定です", message)
        self.assertIn("anime_character_lora", message)


if __name__ == "__main__":
    unittest.main()
