"""Browser query/selection state; independent of widgets, filesystem and codecs."""

from comfyui_support_tools.shared.contracts.media_item import MediaItem

PAGE_SIZE = 60
SECTIONS = {"all", "images", "videos", "dataset", "generated", "favorites", "recent"}
SORTS = {"name", "modified", "size"}


# {
# 責務: [MediaSession: widget/filesystem/codecから独立したbrowser query/page/selection stateを保持する]
# フィールド: [items, selected IDs, favorites, recent IDs, query/sort/page/token/loading/message, ordered cache]
# }
class MediaSession:
    # {
    #   責務: [__init__: 空browser stateをdefault section/name sortと案内messageで初期化する]
    #   処理: [item/selection/favorite/recent stateを空にしloading false、page/tokenをzeroにする]
    #   引数: [self: browser state]
    #   戻り値: [なし]
    # }
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

    # {
    #   責務: [begin: 新tokenのfolder scanに向けitems/selection/page cacheをresetする]
    #   処理: [tokenを保存しloading stateとprogress messageを設定する]
    #   引数: [self: state, token: new scan generation]
    #   戻り値: [なし]
    # }
    def begin(self, token):
        self.token = token
        self.items.clear()
        self.selected = ()
        self.page = 0
        self.loading = True
        self.message = "フォルダ読込中…"
        self._ordered = None

    # {
    #   責務: [accept: current generationのscan batch/done/error eventsをsession stateへ適用する]
    #   処理: [stale tokenを捨てbatch itemをupsertしterminal eventでloading/messageを更新する]
    #   引数: [self: state, events: MediaEvent iterable]
    #   戻り値: [bool: visible session stateが変わったか]
    # }
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

    # {
    #   責務: [query: section/text/sort条件を検証し可視外selectionを除去する]
    #   処理: [textをtrim/casefoldしpage/cacheをresetしてvisible IDsを再計算する]
    #   引数: [self: state, section: supported section, text: search string, sort: supported key, descending: order flag]
    #   戻り値: [なし]
    #   エラー: [ValueError: sectionまたはsort keyが未対応]
    # }
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

    # {
    #   責務: [ordered: current query条件に合うitemsを決定的sort順でcacheして返す]
    #   処理: [section/collection/favorite/recent/path text filterを適用しselected sort keyでorderする]
    #   引数: [self: state]
    #   戻り値: [MediaItem tuple: filtered and sorted records]
    # }
    def ordered(self):
        if self._ordered is None:
            items = self.items.values()
            section = self.section
            result = [
                item
                for item in items
                if (section not in ("images", "videos") or item.kind == section[:-1])
                and (section not in ("dataset", "generated") or item.collection == section)
                and (section != "favorites" or item.id in self.favorites)
                and (section != "recent" or item.id in self.recent)
                and (not self.text or self.text in item.path.casefold())
            ]
            key = {
                "name": lambda item: (item.name.casefold(), item.path),
                "modified": lambda item: (item.modified_ns, item.path),
                "size": lambda item: (item.size, item.path),
            }[self.sort]
            self._ordered = tuple(sorted(result, key=key, reverse=self.descending))
        return self._ordered

    # {
    #   責務: [page_items: current page size以内のitemsを返しpage/selection boundsを保つ]
    #   処理: [pageをavailable rangeへclampし、visible page sliceから外れるselectionを除く]
    #   引数: [self: state]
    #   戻り値: [MediaItem tuple: current page]
    # }
    def page_items(self):
        ordered = self.ordered()
        self.page = min(max(0, self.page), max(0, (len(ordered) - 1) // PAGE_SIZE))
        start = self.page * PAGE_SIZE
        page = ordered[start : start + PAGE_SIZE]
        visible = {item.id for item in page}
        self.selected = tuple(key for key in self.selected if key in visible)
        return page

    # {
    #   責務: [move_page: relative pageをclampしpage間のselection leakageを防ぐ]
    #   処理: [deltaを加えpage_itemsでclamp後selectionをclearする]
    #   引数: [self: state, delta: relative page movement]
    #   戻り値: [なし]
    # }
    def move_page(self, delta):
        self.page += delta
        self.page_items()
        # Selection is page-scoped, avoiding accidentally acting on hidden files.
        self.selected = ()

    # {
    #   責務: [select: current visible page上のunique IDsだけをselection/recentへ反映する]
    #   処理: [hidden IDsを除き重複排除し、recent historyを最大200に更新する]
    #   引数: [self: state, keys: requested media item IDs]
    #   戻り値: [selected MediaItem tuple]
    # }
    def select(self, keys):
        visible = {item.id for item in self.page_items()}
        self.selected = tuple(dict.fromkeys(key for key in keys if key in visible))
        self.recent = list(dict.fromkeys((*self.selected, *self.recent)))[:200]
        return self.selection()

    # {
    #   責務: [selection: selected IDsの現行MediaItem objectsを返す]
    #   処理: [stale/missing IDをfilterしてitem mappingからlookupする]
    #   引数: [self: state]
    #   戻り値: [MediaItem tuple]
    # }
    def selection(self):
        return tuple(self.items[key] for key in self.selected if key in self.items)

    # {
    #   責務: [toggle_favorites: current selectionをfavoriteに追加または解除する]
    #   処理: [全部favoriteならremove、そうでなければaddしorder cacheとhidden selectionを更新する]
    #   引数: [self: state]
    #   戻り値: [なし]
    # }
    def toggle_favorites(self):
        if self.selected and all(key in self.favorites for key in self.selected):
            self.favorites.difference_update(self.selected)
        else:
            self.favorites.update(self.selected)
        self._ordered = None
        visible = {item.id for item in self.ordered()}
        self.selected = tuple(key for key in self.selected if key in visible)

    # {
    #   責務: [summary: current result/page/loading stateをUI向けmappingで返す]
    #   処理: [filtered total、loaded count、page count、loading、messageを集計する]
    #   引数: [self: state]
    #   戻り値: [dict: total/loaded/page/pages/loading/message]
    # }
    def summary(self):
        total = len(self.ordered())
        return {
            "total": total,
            "loaded": len(self.items),
            "page": self.page,
            "pages": max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE),
            "loading": self.loading,
            "message": self.message,
        }
