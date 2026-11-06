"""Tests for saving manually confirmed Character Registry intake results."""

import multiprocessing
import tempfile
import time
import unittest
from pathlib import Path
from typing import Any

from src.comfyui_support_tools.applications.character_registry.api import (
    register_character_intake,
)
from src.comfyui_support_tools.applications.character_registry.data.processing.character_profile_store import (
    CharacterProfileStore,
)
from src.comfyui_support_tools.shared.contracts.character_outfit_profile import (
    CharacterOutfitProfile,
)
from src.comfyui_support_tools.shared.contracts.character_outfit_tag_group import (
    CharacterOutfitTagGroup,
)
from src.comfyui_support_tools.shared.contracts.character_profile import CharacterProfile
from src.comfyui_support_tools.shared.contracts.character_source_asset import CharacterSourceAsset
from src.comfyui_support_tools.shared.contracts.character_tag_candidate import (
    CharacterTagCandidate,
)
from src.comfyui_support_tools.shared.contracts.character_tag_intake_confirmation import (
    CharacterTagIntakeConfirmation,
)
from src.comfyui_support_tools.shared.contracts.character_tag_intake_preview import (
    CharacterTagIntakePreview,
)


# {
#   責務: [_register_in_process: childからprofile登録結果をparentへ返す]
#   処理: [saveを遅延させ, success/FileExistsErrorをresult queueへ送る]
#   引数: [start_event/result_queue: process sync, preview/confirmation: intake contract, profile_directory: 保存root]
#   戻り値: []
# }
def _register_in_process(
    start_event: Any,
    result_queue: Any,
    preview: CharacterTagIntakePreview,
    confirmation: CharacterTagIntakeConfirmation,
    profile_directory: str,
) -> None:
    """Run one competing registration after both child processes are ready."""
    original_save = CharacterProfileStore.save

    # {
    #   責務: [delayed_save: 保存を遅らせて同時登録のrace windowを広げる]
    #   処理: [少し待ってから元のatomic saveを呼ぶ]
    #   引数: [store: profile store, profile: 保存するCharacterProfile]
    #   戻り値: [Path: 保存先]
    # }
    def delayed_save(store: CharacterProfileStore, profile: CharacterProfile) -> Path:
        """Widen the save race window while preserving the original file operation."""
        time.sleep(0.4)
        return original_save(store, profile)

    CharacterProfileStore.save = delayed_save
    result_queue.put("ready")
    if not start_event.wait(timeout=10):
        result_queue.put("start-timeout")
        return
    try:
        profile = register_character_intake(preview, confirmation, Path(profile_directory))
    except FileExistsError:
        result_queue.put("exists")
    except Exception as error:
        result_queue.put(f"error:{type(error).__name__}:{error}")
    else:
        result_queue.put(("saved", profile.confirmed_core_traits))


# {
#   責務: [CharacterIntakeRegistrationTest: 明示確認済みtraitだけの登録とprovenance保存を検証する]
#   フィールド: [unittest assertion機能]
#   処理: [一時profile storeを使い, 手動確認と再読込の結果を確認する]
# }
class CharacterIntakeRegistrationTest(unittest.TestCase):
    """Keep profile registration and provenance persistence offline and isolated."""

    # {
    #   責務: [_preview: 登録テスト用のtag candidateとsource assetを作る]
    #   処理: [identity/outfit/contextを分類したpreviewを返す]
    #   引数: []
    #   戻り値: [CharacterTagIntakePreview: fixture preview]
    # }
    @staticmethod
    def _preview() -> CharacterTagIntakePreview:
        source = CharacterSourceAsset(
            caption_file="civitai://models/12/versions/34/trainedWords",
            image_file=None,
            tags=("blue_hair", "school_uniform"),
            outfit_id=None,
            source_url="https://civitai.com/models/12",
            source_work_id="12:34",
            license_status="unknown",
            training_permission="unknown",
            source_metadata=(("allow_commercial_use", "Image"), ("creator", "artist")),
        )
        return CharacterTagIntakePreview(
            character_id="registered_character",
            display_name="Registered Character",
            aliases=("RC",),
            identity_candidates=(
                CharacterTagCandidate("blue_hair", "identity", 1, 0.8, (source.caption_file,)),
            ),
            outfit_groups=(
                CharacterOutfitTagGroup(
                    outfit_id="unassigned",
                    is_unassigned=True,
                    tags=(
                        CharacterTagCandidate(
                            "school_uniform", "outfit", 1, 0.7, (source.caption_file,)
                        ),
                    ),
                ),
            ),
            context_candidates=(),
            unclassified_candidates=(),
            source_assets=(source,),
            warnings=("Civitai trigger候補は手動確認してください",),
        )

    # {
    #   責務: [test_register_saves_only_confirmed_identity_and_outfits: 手動確認後の保存とmetadata round-tripを検証する]
    #   処理: [profileを登録し, 再読込してidentity/outfit/source metadataを比較する]
    #   引数: [self: unittest.TestCase instance]
    #   戻り値: []
    # }
    def test_register_saves_only_confirmed_identity_and_outfits(self) -> None:
        preview = self._preview()
        confirmed_outfit = CharacterOutfitProfile(
            outfit_id="school-uniform",
            name="School Uniform",
            garment_traits=("school_uniform",),
            user_confirmed=True,
        )
        confirmation = CharacterTagIntakeConfirmation(
            confirmed_identity_traits=("blue_hair",),
            rejected_traits=("temporary_unknown_trait",),
            outfit_profiles=(confirmed_outfit,),
            default_outfit_id="school-uniform",
        )

        with tempfile.TemporaryDirectory() as temporary_directory:
            profile = register_character_intake(
                preview,
                confirmation,
                Path(temporary_directory),
            )
            restored = CharacterProfileStore(temporary_directory).load(profile.character_id)

        self.assertEqual(profile.confirmed_core_traits, ("blue_hair",))
        self.assertEqual(profile.outfit_profiles, (confirmed_outfit,))
        self.assertEqual(restored, profile)
        self.assertEqual(
            restored.provenance[0].source_metadata,
            (("allow_commercial_use", "Image"), ("creator", "artist")),
        )

    # {
    #   責務: [test_registration_rejects_existing_character_id: 登録時に既存profileを上書きしないことを検証する]
    #   処理: [同じcharacter IDを2回登録し, 2回目のFileExistsErrorと保存内容維持をassertする]
    #   引数: [self: unittest.TestCase instance]
    #   戻り値: []
    # }
    def test_registration_rejects_existing_character_id(self) -> None:
        """Verify a rejected duplicate cannot replace the first stored profile."""
        preview = self._preview()
        confirmation = CharacterTagIntakeConfirmation(confirmed_identity_traits=("blue_hair",))

        with tempfile.TemporaryDirectory() as temporary_directory:
            original = register_character_intake(preview, confirmation, Path(temporary_directory))
            duplicate = CharacterTagIntakeConfirmation(confirmed_identity_traits=("red_hair",))
            with self.assertRaises(FileExistsError):
                register_character_intake(preview, duplicate, Path(temporary_directory))
            restored = CharacterProfileStore(temporary_directory).load(preview.character_id)

        self.assertEqual(restored, original)

    # {
    #   責務: [test_concurrent_registration_allows_only_one_process: 同一IDのprocess競合で一件だけ保存する]
    #   処理: [二つのspawn processを同時開始し, success一件とFileExistsError一件を確認する]
    #   引数: [self: unittest.TestCase instance]
    #   戻り値: []
    # }
    def test_concurrent_registration_allows_only_one_process(self) -> None:
        """Verify process-level locking permits exactly one registration for an ID."""
        preview = self._preview()
        first_confirmation = CharacterTagIntakeConfirmation(
            confirmed_identity_traits=("blue_hair",)
        )
        second_confirmation = CharacterTagIntakeConfirmation(
            confirmed_identity_traits=("red_hair",)
        )
        context = multiprocessing.get_context("spawn")

        with tempfile.TemporaryDirectory() as temporary_directory:
            start_event = context.Event()
            result_queue = context.Queue()
            processes = [
                context.Process(
                    target=_register_in_process,
                    args=(start_event, result_queue, preview, confirmation, temporary_directory),
                )
                for confirmation in (first_confirmation, second_confirmation)
            ]
            for process in processes:
                process.start()
            try:
                ready_states = [result_queue.get(timeout=15) for _ in processes]
            finally:
                start_event.set()
            self.assertEqual(ready_states, ["ready", "ready"])
            for process in processes:
                process.join(timeout=15)
                if process.is_alive():
                    process.terminate()
                    process.join(timeout=5)
                    self.fail("registration child process did not finish")
                self.assertEqual(process.exitcode, 0)

            outcomes = [result_queue.get(timeout=3) for _ in processes]
            result_queue.close()
            result_queue.join_thread()
            restored = CharacterProfileStore(temporary_directory).load(preview.character_id)

        self.assertEqual(
            sum(isinstance(outcome, tuple) and outcome[0] == "saved" for outcome in outcomes), 1
        )
        self.assertEqual(outcomes.count("exists"), 1)
        self.assertIn(restored.confirmed_core_traits, (("blue_hair",), ("red_hair",)))

    # {
    #   責務: [test_confirmation_rejects_unconfirmed_outfit: 自動推定だけでoutfit登録させないことを検証する]
    #   処理: [user_confirmed=Falseのoutfitをconfirmationに渡し, ValueErrorをassertする]
    #   引数: [self: unittest.TestCase instance]
    #   戻り値: []
    # }
    def test_confirmation_rejects_unconfirmed_outfit(self) -> None:
        guessed_outfit = CharacterOutfitProfile(
            outfit_id="guessed-outfit",
            name="Guessed Outfit",
            garment_traits=("school_uniform",),
        )

        with self.assertRaises(ValueError):
            CharacterTagIntakeConfirmation(
                confirmed_identity_traits=("blue_hair",),
                outfit_profiles=(guessed_outfit,),
            )

    # {
    #   責務: [test_confirmation_rejects_contradictory_identity_decisions: 同じtraitのconfirm/reject競合を拒否する]
    #   処理: [identityとrejectedへ同じtagを渡し, ValueErrorをassertする]
    #   引数: [self: unittest.TestCase instance]
    #   戻り値: []
    # }
    def test_confirmation_rejects_contradictory_identity_decisions(self) -> None:
        with self.assertRaises(ValueError):
            CharacterTagIntakeConfirmation(
                confirmed_identity_traits=("blue_hair",),
                rejected_traits=("blue_hair",),
            )
