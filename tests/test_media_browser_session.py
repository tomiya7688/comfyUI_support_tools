from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from comfyui_support_tools.shared.contracts.media_event import MediaEvent
from comfyui_support_tools.shared.contracts.media_item import MediaItem
from comfyui_support_tools.applications.main_gui.process.processing.media_session import MediaSession


def item(key, name, kind="image", collection="library", size=100, modified=1):
    return MediaItem(key, "/media/"+name, name, kind, collection, size, modified)


class MediaSessionTests(unittest.TestCase):
    def setUp(self):
        self.session = MediaSession()
        self.records = (item("a", "猫.PNG", collection="dataset", size=10, modified=3),
                        item("b", "Film.avi", kind="video", size=30, modified=2),
                        item("c", "Z-image.png", collection="generated", size=20))
        self.session.begin(1)
        self.session.accept((MediaEvent("batch", 1, self.records), MediaEvent("done", 1)))

    def test_unicode_case_search_and_type_collection_filters(self):
        for section, text, expected in (("all", "猫", {"a"}), ("all", "FILM", {"b"}),
                                       ("images", "", {"a", "c"}), ("videos", "", {"b"}),
                                       ("dataset", "", {"a"}), ("generated", "", {"c"})):
            self.session.query(section, text, "name", False)
            self.assertEqual({r.id for r in self.session.page_items()}, expected)

    def test_size_modified_sort_and_direction(self):
        self.session.query("all", "", "size", True)
        self.assertEqual([r.id for r in self.session.page_items()], ["b", "c", "a"])
        self.session.query("all", "", "modified", False)
        self.assertEqual([r.id for r in self.session.page_items()], ["c", "b", "a"])

    def test_selection_is_unique_visible_and_immutable(self):
        self.session.select(("a", "a", "b", "unknown"))
        self.assertEqual(self.session.selection(), self.records[:2])
        self.session.query("videos", "", "name", False)
        self.assertEqual(self.session.selection(), (self.records[1],))

    def test_selection_recent_and_session_favorites(self):
        self.session.select(("a", "c"))
        self.session.toggle_favorites()
        self.session.query("favorites", "", "name", False)
        self.assertEqual({r.id for r in self.session.page_items()}, {"a", "c"})
        self.session.toggle_favorites()
        self.assertEqual(self.session.page_items(), ())
        self.assertEqual(self.session.selection(), ())
        self.session.query("recent", "", "name", False)
        self.assertEqual({r.id for r in self.session.page_items()}, {"a", "c"})

    def test_stale_scan_cannot_replace_new_folder(self):
        self.session.begin(2)
        self.session.accept((MediaEvent("batch", 1, self.records), MediaEvent("done", 1)))
        self.assertEqual(self.session.page_items(), ())
        self.assertTrue(self.session.loading)
        self.session.accept((MediaEvent("error", 2, message="missing"),))
        self.assertFalse(self.session.loading)

    def test_ten_thousand_items_use_sixty_item_pages(self):
        records = tuple(item(str(i), f"{i:05}.png") for i in range(10_000))
        self.session.begin(2)
        self.session.accept((MediaEvent("batch", 2, records),))
        self.assertEqual(len(self.session.page_items()), 60)
        self.assertEqual(self.session.summary()["pages"], 167)
        self.session.select(("0", "1"))
        self.session.move_page(1)
        self.assertEqual(self.session.selection(), ())
        self.assertEqual(self.session.page_items()[0].id, "60")
        self.session.move_page(10000)
        self.assertEqual(len(self.session.page_items()), 40)
        self.session.move_page(-10000)
        self.assertEqual(self.session.page_items()[0].id, "0")

    def test_invalid_query_keeps_previous_state(self):
        before = self.session.page_items()
        with self.assertRaises(ValueError):
            self.session.query("bad", "", "name", False)
        with self.assertRaises(ValueError):
            self.session.query("all", "", "bad", False)
        self.assertEqual(self.session.page_items(), before)


if __name__ == "__main__":
    unittest.main()
