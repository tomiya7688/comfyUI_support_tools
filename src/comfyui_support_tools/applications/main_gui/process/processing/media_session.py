"""Browser query/selection state; independent of widgets, filesystem and codecs."""
from comfyui_support_tools.shared.contracts.media_item import MediaItem

PAGE_SIZE = 60
SECTIONS = {"all", "images", "videos", "dataset", "generated", "favorites", "recent"}
SORTS = {"name", "modified", "size"}


class MediaSession:
    def __init__(self):
        self.items: dict[str, MediaItem] = {}
        self.selected: tuple[str, ...] = ()
        self.favorites: set[str] = set()
        self.recent: list[str] = []
        self.section, self.text, self.sort, self.descending = "all", "", "name", False
        self.page = 0
        self.token = 0
        self.loading = False
        self.message = "フォルダを開いてください。バックエンド接続は不要です。"
        self._ordered = None

    def begin(self, token):
        self.token = token
        self.items.clear()
        self.selected = ()
        self.page = 0
        self.loading = True
        self.message = "フォルダ読込中…"
        self._ordered = None

    def accept(self, events):
        changed = False
        for event in events:
            if event.token != self.token:
                continue
            if event.kind == "batch":
                self.items.update((item.id, item) for item in event.items)
                self._ordered = None
                changed = True
            elif event.kind in ("done", "error"):
                self.loading = False
                self.message = event.message
                changed = True
        return changed

    def query(self, section, text, sort, descending):
        if section not in SECTIONS or sort not in SORTS:
            raise ValueError("Unknown media query")
        self.section, self.text = section, text.strip().casefold()
        self.sort, self.descending = sort, bool(descending)
        self.page = 0
        self._ordered = None
        # Hidden selections must never leak into a later Action.
        visible = {item.id for item in self.ordered()}
        self.selected = tuple(key for key in self.selected if key in visible)

    def ordered(self):
        if self._ordered is None:
            items = self.items.values()
            section = self.section
            result = [item for item in items
                      if (section not in ("images", "videos") or item.kind == section[:-1])
                      and (section not in ("dataset", "generated") or item.collection == section)
                      and (section != "favorites" or item.id in self.favorites)
                      and (section != "recent" or item.id in self.recent)
                      and (not self.text or self.text in item.path.casefold())]
            key = {"name": lambda item: (item.name.casefold(), item.path),
                   "modified": lambda item: (item.modified_ns, item.path),
                   "size": lambda item: (item.size, item.path)}[self.sort]
            self._ordered = tuple(sorted(result, key=key, reverse=self.descending))
        return self._ordered

    def page_items(self):
        ordered = self.ordered()
        self.page = min(max(0, self.page), max(0, (len(ordered) - 1) // PAGE_SIZE))
        start = self.page * PAGE_SIZE
        page = ordered[start:start + PAGE_SIZE]
        visible = {item.id for item in page}
        self.selected = tuple(key for key in self.selected if key in visible)
        return page

    def move_page(self, delta):
        self.page += delta
        self.page_items()
        # Selection is page-scoped, avoiding accidentally acting on hidden files.
        self.selected = ()

    def select(self, keys):
        visible = {item.id for item in self.page_items()}
        self.selected = tuple(dict.fromkeys(key for key in keys if key in visible))
        self.recent = list(dict.fromkeys((*self.selected, *self.recent)))[:200]
        return self.selection()

    def selection(self):
        return tuple(self.items[key] for key in self.selected if key in self.items)

    def toggle_favorites(self):
        if self.selected and all(key in self.favorites for key in self.selected):
            self.favorites.difference_update(self.selected)
        else:
            self.favorites.update(self.selected)
        self._ordered = None
        visible = {item.id for item in self.ordered()}
        self.selected = tuple(key for key in self.selected if key in visible)

    def summary(self):
        total = len(self.ordered())
        return {"total": total, "loaded": len(self.items), "page": self.page,
                "pages": max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE),
                "loading": self.loading, "message": self.message}
