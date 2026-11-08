import unittest

from src.comfyui_support_tools.shared.contracts.character_outfit_profile import (
    CharacterOutfitProfile,
)
from src.comfyui_support_tools.shared.contracts.character_tag_intake_confirmation import (
    CharacterTagIntakeConfirmation,
)


# {
#   責務: [CharacterTagIntakeConfirmationTests: 確認済みoutfit traitとrejected traitの衝突を拒否する]
#   処理: [garment/innerwear traitがrejected_traitsにもある場合にValueErrorを検証する]
#   フィールド: []
# }
class CharacterTagIntakeConfirmationTests(unittest.TestCase):
    """Check conflicting outfit confirmation data is rejected."""

    # {
    #   責務: [test_rejected_garment_trait_is_not_confirmable: garment/rejectedの重複を拒否する]
    #   処理: [同じtagをoutfitとrejectedへ渡し, ValueErrorを検証する]
    #   引数: [self: test case]
    #   戻り値: []
    # }
    def test_rejected_garment_trait_is_not_confirmable(self) -> None:
        """Reject an outfit garment that is explicitly marked as rejected."""
        outfit = CharacterOutfitProfile(
            outfit_id="default",
            name="Default",
            garment_traits=("school_uniform",),
            user_confirmed=True,
        )

        with self.assertRaisesRegex(ValueError, "outfit trait"):
            CharacterTagIntakeConfirmation(
                confirmed_identity_traits=("blue_hair",),
                rejected_traits=("school_uniform",),
                outfit_profiles=(outfit,),
            )

    # {
    #   責務: [test_rejected_innerwear_trait_is_not_confirmable: innerwear/rejectedの重複を拒否する]
    #   処理: [同じtagをinnerwearとrejectedへ渡し, ValueErrorを検証する]
    #   引数: [self: test case]
    #   戻り値: []
    # }
    def test_rejected_innerwear_trait_is_not_confirmable(self) -> None:
        """Reject an innerwear trait that is explicitly marked as rejected."""
        outfit = CharacterOutfitProfile(
            outfit_id="default",
            name="Default",
            innerwear_traits=("undershirt",),
            user_confirmed=True,
        )

        with self.assertRaisesRegex(ValueError, "outfit trait"):
            CharacterTagIntakeConfirmation(
                confirmed_identity_traits=("blue_hair",),
                rejected_traits=("undershirt",),
                outfit_profiles=(outfit,),
            )
