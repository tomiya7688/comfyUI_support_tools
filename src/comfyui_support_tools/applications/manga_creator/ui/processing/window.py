"""Storyboard/project editor UI for Manga Creator."""

from __future__ import annotations

import io
import tkinter as tk
from dataclasses import replace
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

from PIL import Image, ImageTk

from comfyui_support_tools.applications.manga_creator.ui.commander.application import (
    MangaCreatorUiCommander,
)
from comfyui_support_tools.shared.contracts.manga_creator import (
    BalloonKind,
    CharacterSpec,
    DialogueLine,
    LocationSpec,
    MangaLayoutMode,
    MangaProject,
    MangaStyleMode,
    PropSpec,
    ReadingDirection,
)


# {
# 責務: [MangaCreatorWindow: edit a storyboard-first project and review generated panel candidates]
# フィールド: [UI Commander, project metadata, page/panel tree, editor, preview and action state]
# 処理: [keep project data editable and route user actions through UI communication]
# }
class MangaCreatorWindow:
    # {
    # 責務: [__init__: build the Manga Creator project editor]
    # 処理: [create project, bible, storyboard, panel and preview controls]
    # 引数: [root: Tk root, commander: UI action router]
    # 戻り値: [None: editor initialized]
    # }
    def __init__(self, root: tk.Tk, commander: MangaCreatorUiCommander) -> None:
        self.root = root
        self.commander = commander
        self.project: MangaProject | None = None
        self.project_path: Path | None = None
        self.preview: ImageTk.PhotoImage | None = None
        self.tree_ids: dict[str, str] = {}
        root.title("Manga Creator · Storyboard Workspace")
        root.geometry("1380x900")
        self.title = tk.StringVar(value="Untitled manga")
        self.genre = tk.StringVar()
        self.page_count = tk.IntVar(value=1)
        self.layout = tk.StringVar(value=MangaLayoutMode.MANGA_PAGE.value)
        self.direction = tk.StringVar(value=ReadingDirection.RIGHT_TO_LEFT.value)
        self.style = tk.StringVar(value=MangaStyleMode.STORYBOARD.value)
        self.candidate_count = tk.IntVar(value=1)
        self.shot = tk.StringVar(value="medium")
        self.camera = tk.StringVar()
        self.backend_id = tk.StringVar()
        self.panel_bbox = [tk.StringVar() for _ in range(4)]
        self.candidates = tk.StringVar()
        self.status = tk.StringVar(
            value="Create or open a project. The built-in backend makes rough storyboards."
        )
        self._build()

    # {
    # 責務: [_build: assemble project, story, bible, panel and preview controls]
    # 処理: [lay out a navigable page/panel outline with editable script and visual intent]
    # 引数: [self: window]
    # 戻り値: [None: view hierarchy constructed]
    # }
    def _build(self) -> None:
        toolbar = ttk.Frame(self.root, padding=6)
        toolbar.pack(fill="x")
        actions = (
            ("New", self.new_project),
            ("Open", self.open_project),
            ("Save", self.save_project),
            ("Plan story", self.plan_story),
            ("Add character", self.add_character),
            ("Add location", self.add_location),
            ("Add prop", self.add_prop),
            ("Add continuity", self.add_continuity),
            ("Render / resume all", self.render_all),
            ("Compose page", self.compose_page),
        )
        for label, callback in actions:
            ttk.Button(toolbar, text=label, command=callback).pack(side="left", padx=2)
        ttk.Label(toolbar, text="candidates").pack(side="left", padx=(10, 2))
        ttk.Spinbox(toolbar, from_=1, to=8, width=3, textvariable=self.candidate_count).pack(
            side="left"
        )
        main = ttk.Panedwindow(self.root, orient="horizontal")
        main.pack(fill="both", expand=True, padx=8, pady=6)
        left = ttk.Frame(main, padding=6)
        editor = ttk.Frame(main, padding=6)
        preview = ttk.Frame(main, padding=6)
        main.add(left, weight=1)
        main.add(editor, weight=2)
        main.add(preview, weight=3)
        self._build_project_fields(left)
        self.tree = ttk.Treeview(left, columns=("state",), show="tree headings", height=20)
        self.tree.heading("#0", text="Page / panel plan")
        self.tree.heading("state", text="State")
        self.tree.column("state", width=90, stretch=False)
        self.tree.pack(fill="both", expand=True, pady=6)
        self.tree.bind("<<TreeviewSelect>>", self._selection_changed)
        self._build_panel_editor(editor)
        self.canvas = tk.Canvas(preview, background="#343434", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        ttk.Button(editor, text="Generate selected panel", command=self.render_selected).pack(
            fill="x", pady=(12, 0)
        )
        ttk.Button(editor, text="Repair selected panel", command=self.repair_selected).pack(
            fill="x", pady=(3, 0)
        )
        ttk.Label(self.root, textvariable=self.status, anchor="w", padding=7).pack(fill="x")

    # {
    # 責務: [_build_project_fields: create story and project-level planning controls]
    # 処理: [add title, genre, page/layout choices and script editor]
    # 引数: [self: window, parent: project pane]
    # 戻り値: [None: metadata controls placed]
    # }
    def _build_project_fields(self, parent: ttk.Frame) -> None:
        ttk.Label(parent, text="Project title").pack(anchor="w")
        ttk.Entry(parent, textvariable=self.title).pack(fill="x")
        ttk.Label(parent, text="Genre").pack(anchor="w")
        ttk.Entry(parent, textvariable=self.genre).pack(fill="x")
        ttk.Label(parent, text="Pages · layout · reading").pack(anchor="w")
        row = ttk.Frame(parent)
        row.pack(fill="x")
        ttk.Spinbox(row, from_=1, to=500, width=5, textvariable=self.page_count).pack(side="left")
        ttk.Combobox(
            row,
            textvariable=self.layout,
            values=[item.value for item in MangaLayoutMode],
            state="readonly",
            width=13,
        ).pack(side="left", fill="x", expand=True)
        ttk.Combobox(
            row,
            textvariable=self.direction,
            values=[item.value for item in ReadingDirection],
            state="readonly",
            width=13,
        ).pack(side="left", fill="x", expand=True)
        ttk.Combobox(
            parent,
            textvariable=self.style,
            values=[item.value for item in MangaStyleMode],
            state="readonly",
        ).pack(fill="x", pady=(3, 0))
        ttk.Label(
            parent, text="Story / screenplay\nUse `Speaker: dialogue` for exact editable dialogue."
        ).pack(anchor="w", pady=(8, 0))
        self.story_text = tk.Text(parent, height=11, wrap="word", undo=True)
        self.story_text.pack(fill="x")

    # {
    # 責務: [_build_panel_editor: create one panel's editable visual and lettering controls]
    # 処理: [add normalized layout fields, shot/camera notes, action and dialogue editors, and candidate selection]
    # 引数: [self: window, parent: panel editor]
    # 戻り値: [None: panel controls placed]
    # }
    def _build_panel_editor(self, parent: ttk.Frame) -> None:
        ttk.Label(parent, text="Panel geometry · normalized x, y, width, height").pack(anchor="w")
        geometry = ttk.Frame(parent)
        geometry.pack(fill="x")
        for index, label in enumerate(("x", "y", "w", "h")):
            ttk.Label(geometry, text=label).pack(side="left")
            ttk.Entry(geometry, textvariable=self.panel_bbox[index], width=8).pack(
                side="left", padx=(0, 5)
            )
        ttk.Label(parent, text="Shot / camera").pack(anchor="w", pady=(8, 0))
        ttk.Entry(parent, textvariable=self.shot).pack(fill="x")
        ttk.Entry(parent, textvariable=self.camera).pack(fill="x", pady=3)
        ttk.Label(parent, text="Per-panel backend ID (blank uses project policy)").pack(anchor="w")
        ttk.Entry(parent, textvariable=self.backend_id).pack(fill="x")
        ttk.Label(parent, text="Action / panel prompt (edit between render attempts)").pack(
            anchor="w"
        )
        self.action_text = tk.Text(parent, height=7, wrap="word", undo=True)
        self.action_text.pack(fill="both", expand=True)
        ttk.Button(parent, text="Save panel plan", command=self.save_panel_plan).pack(
            fill="x", pady=3
        )
        ttk.Label(parent, text="Dialogue text (one `speaker id: line` per row)").pack(
            anchor="w", pady=(6, 0)
        )
        self.dialogue_text = tk.Text(parent, height=6, wrap="word", undo=True)
        self.dialogue_text.pack(fill="both", expand=True)
        ttk.Button(parent, text="Save lettering", command=self.save_dialogue).pack(fill="x", pady=3)
        ttk.Label(parent, text="Stored best-of-N alternatives").pack(anchor="w", pady=(6, 0))
        self.candidate_box = ttk.Combobox(parent, textvariable=self.candidates, state="readonly")
        self.candidate_box.pack(fill="x")
        self.candidate_box.bind("<<ComboboxSelected>>", self.select_candidate)

    # {
    # 責務: [_call: send one UI operation and report a user-readable failure]
    # 処理: [invoke the UI Commander and refresh project views when a project is returned]
    # 引数: [self: window, operation: Process operation, args: positional data, values: named data]
    # 戻り値: [object | None: Process result]
    # }
    def _call(self, operation: str, *args: object, **values: object) -> object | None:
        try:
            result = self.commander.send(operation, *args, **values)
            if isinstance(result, MangaProject):
                self.project = result
                self._refresh_tree()
            return result
        except (OSError, ValueError, RuntimeError, KeyError, IndexError, TypeError) as error:
            messagebox.showerror("Manga Creator", str(error), parent=self.root)
            self.status.set(f"Action failed: {error}")
            return None

    # {
    # 責務: [new_project: initialize a project from the script editor]
    # 処理: [ask for a project file and create schema with selected page/layout/style settings]
    # 引数: [self: window]
    # 戻り値: [None: project created or dialog canceled]
    # }
    def new_project(self) -> None:
        path = filedialog.asksaveasfilename(
            defaultextension=".manga.json", filetypes=[("Manga project", "*.manga.json")]
        )
        if not path:
            return
        story = self.story_text.get("1.0", "end-1c")
        result = self._call(
            "create_project",
            path,
            self.title.get(),
            story,
            page_count=int(self.page_count.get()),
            genre=self.genre.get(),
            layout_mode=MangaLayoutMode(self.layout.get()),
            reading_direction=ReadingDirection(self.direction.get()),
            style=MangaStyleMode(self.style.get()),
        )
        if isinstance(result, MangaProject):
            self.project_path = Path(path)
            self.status.set(
                f"Created {self.project.title}. Storyboard rendering is active; no trained image model is bundled."
            )

    # {
    # 責務: [open_project: resume a JSON manga project]
    # 処理: [request a project path and restore saved state through Process/Data]
    # 引数: [self: window]
    # 戻り値: [None: project opened or dialog canceled]
    # }
    def open_project(self) -> None:
        path = filedialog.askopenfilename(filetypes=[("Manga project", "*.manga.json *.json")])
        if not path:
            return
        result = self._call("open_project", path)
        if isinstance(result, MangaProject):
            self.project_path = Path(path)
            self.title.set(result.title)
            self.genre.set(result.genre)
            self.page_count.set(result.target_page_count)
            self.layout.set(result.layout_mode.value)
            self.direction.set(result.reading_direction.value)
            self.style.set(result.style.value)
            self.story_text.delete("1.0", tk.END)
            self.story_text.insert("1.0", result.story_script)
            self._refresh_tree()

    # {
    # 責務: [save_project: persist the current project]
    # 処理: [update script and metadata before saving the project file]
    # 引数: [self: window]
    # 戻り値: [None: project saved or no project loaded]
    # }
    def save_project(self) -> None:
        if not self.project:
            return
        self._call(
            "edit_project",
            title=self.title.get(),
            genre=self.genre.get(),
            story_script=self.story_text.get("1.0", "end-1c"),
            target_page_count=int(self.page_count.get()),
            layout_mode=MangaLayoutMode(self.layout.get()),
            reading_direction=ReadingDirection(self.direction.get()),
            style=MangaStyleMode(self.style.get()),
        )
        path = self._call("save_project")
        if isinstance(path, Path):
            self.status.set(f"Saved resumable project {path.name}")

    # {
    # 責務: [plan_story: transform the current story text into editable pages/panels]
    # 処理: [save current story metadata and invoke the deterministic storyboard planner]
    # 引数: [self: window]
    # 戻り値: [None: plan created]
    # }
    def plan_story(self) -> None:
        if not self.project:
            self.new_project()
            if not self.project:
                return
        self._call(
            "edit_project",
            title=self.title.get(),
            genre=self.genre.get(),
            story_script=self.story_text.get("1.0", "end-1c"),
            target_page_count=int(self.page_count.get()),
            layout_mode=MangaLayoutMode(self.layout.get()),
            reading_direction=ReadingDirection(self.direction.get()),
            style=MangaStyleMode(self.style.get()),
        )
        result = self._call("plan", int(self.page_count.get()))
        if isinstance(result, MangaProject):
            self.status.set(
                f"Planned {len(result.pages)} pages and {sum(len(page.panels) for page in result.pages)} panels. Review story causality and camera choices."
            )

    # {
    # 責務: [add_character: add one character bible record]
    # 処理: [collect an ID/name and fixed visual identity from the user]
    # 引数: [self: window]
    # 戻り値: [None: character added or canceled]
    # }
    def add_character(self) -> None:
        if not self.project:
            return
        identifier = simpledialog.askstring(
            "Character Bible", "Stable ID (for example, hero):", parent=self.root
        )
        name = (
            simpledialog.askstring("Character Bible", "Display name:", parent=self.root)
            if identifier
            else None
        )
        traits = (
            simpledialog.askstring(
                "Character Bible", "Fixed identity traits (comma-separated):", parent=self.root
            )
            if name
            else None
        )
        if identifier and name:
            result = self._call(
                "upsert_character",
                CharacterSpec(
                    identifier.strip(),
                    name.strip(),
                    tuple(item.strip() for item in (traits or "").split(",") if item.strip()),
                ),
            )
            if isinstance(result, MangaProject):
                self.status.set(
                    f"Character Bible now has {len(result.characters)} reusable entries."
                )

    # {
    # 責務: [add_location: add one recurring scene/location bible]
    # 処理: [collect a stable location ID, display name and reusable environment notes]
    # 引数: [self: window]
    # 戻り値: [None: location added or canceled]
    # }
    def add_location(self) -> None:
        if not self.project:
            return
        identifier = simpledialog.askstring("Location Bible", "Stable ID:", parent=self.root)
        name = (
            simpledialog.askstring("Location Bible", "Location name:", parent=self.root)
            if identifier
            else None
        )
        description = (
            simpledialog.askstring(
                "Location Bible", "Reusable scene description:", parent=self.root
            )
            if name
            else None
        )
        if identifier and name:
            self._call(
                "upsert_location", LocationSpec(identifier.strip(), name.strip(), description or "")
            )

    # {
    # 責務: [add_prop: add one tracked continuity prop]
    # 処理: [collect a stable prop ID, name and description]
    # 引数: [self: window]
    # 戻り値: [None: prop added or canceled]
    # }
    def add_prop(self) -> None:
        if not self.project:
            return
        identifier = simpledialog.askstring("Prop Bible", "Stable ID:", parent=self.root)
        name = (
            simpledialog.askstring("Prop Bible", "Prop name:", parent=self.root)
            if identifier
            else None
        )
        description = (
            simpledialog.askstring("Prop Bible", "Description:", parent=self.root) if name else None
        )
        if identifier and name:
            self._call("upsert_prop", PropSpec(identifier.strip(), name.strip(), description or ""))

    # {
    # 責務: [add_continuity: add a long-form state change after an accepted panel]
    # 処理: [capture entity/field/value and attach it to the currently selected panel]
    # 引数: [self: window]
    # 戻り値: [None: memory event stored or dialog canceled]
    # }
    def add_continuity(self) -> None:
        panel_id = self._selected_panel_id()
        if not panel_id:
            messagebox.showinfo("Continuity", "Select a panel first.")
            return
        entity = simpledialog.askstring(
            "Continuity memory", "Entity ID (character, location, or prop):", parent=self.root
        )
        field = (
            simpledialog.askstring(
                "Continuity memory",
                "State field (costume, injury, prop, location):",
                parent=self.root,
            )
            if entity
            else None
        )
        value = (
            simpledialog.askstring("Continuity memory", "New state value:", parent=self.root)
            if field
            else None
        )
        if entity and field and value:
            result = self._call("record_continuity_event", entity, field, value, panel_id)
            if isinstance(result, MangaProject):
                self.status.set(
                    f"Continuity memory now tracks {len(result.continuity_memory)} events."
                )

    # {
    # 責務: [_refresh_tree: refresh page/panel navigation from project state]
    # 処理: [show panel status, beat, action summary and stable IDs]
    # 引数: [self: window]
    # 戻り値: [None: tree refreshed]
    # }
    def _refresh_tree(self) -> None:
        self.tree.delete(*self.tree.get_children())
        self.tree_ids.clear()
        if not self.project:
            return
        for page in self.project.pages:
            page_item = self.tree.insert(
                "",
                "end",
                text=f"Page {page.page_number} · {page.layout_mode.value}",
                values=("composed" if page.rendered_path else "planned",),
                open=True,
            )
            self.tree_ids[page_item] = page.id
            for panel in sorted(page.panels, key=lambda item: item.order):
                summary = panel.action.replace("\n", " ")[:50]
                item = self.tree.insert(
                    page_item,
                    "end",
                    text=f"{panel.order + 1}. {panel.beat} · {summary}",
                    values=(panel.status.value,),
                )
                self.tree_ids[item] = panel.id

    # {
    # 責務: [_selected_panel_id: return selected panel identity]
    # 処理: [resolve the selected tree item against current project state]
    # 引数: [self: window]
    # 戻り値: [str | None: panel ID]
    # }
    def _selected_panel_id(self) -> str | None:
        selected = self.tree.selection()
        if not selected:
            return None
        identifier = self.tree_ids.get(selected[0])
        if identifier and any(
            panel.id == identifier for page in self.project.pages for panel in page.panels
        ):
            return identifier
        return None

    # {
    # 責務: [_selection_changed: load the selected page/panel into controls and preview]
    # 処理: [populate edit fields and request its image artifact through Process/Data]
    # 引数: [self: window, event: Tk tree event]
    # 戻り値: [None: editor synchronized]
    # }
    def _selection_changed(self, _event: tk.Event) -> None:
        if not self.project or not self.tree.selection():
            return
        identifier = self.tree_ids.get(self.tree.selection()[0])
        if not identifier:
            return
        page = next((item for item in self.project.pages if item.id == identifier), None)
        if page:
            self._show_artifact(page.rendered_path)
            return
        panel = next(
            (
                panel
                for item in self.project.pages
                for panel in item.panels
                if panel.id == identifier
            ),
            None,
        )
        if not panel:
            return
        for variable, value in zip(self.panel_bbox, panel.bbox, strict=True):
            variable.set(f"{value:.4f}")
        self.shot.set(panel.shot)
        self.camera.set(panel.camera)
        self.backend_id.set(panel.backend_id or "")
        self.action_text.delete("1.0", tk.END)
        self.action_text.insert("1.0", panel.action)
        self.dialogue_text.delete("1.0", tk.END)
        self.dialogue_text.insert(
            "1.0",
            "\n".join(f"{line.speaker_character_id or ''}: {line.text}" for line in panel.dialogue),
        )
        choices = tuple(
            f"{index + 1}: {path}" for index, path in enumerate(panel.candidate_image_paths)
        )
        self.candidate_box["values"] = choices
        self.candidates.set(choices[panel.selected_candidate] if choices else "")
        self._show_artifact(panel.image_path)

    # {
    # 責務: [_show_artifact: display one selected panel or page image]
    # 処理: [retrieve image bytes through the Process messenger and fit a preview on the canvas]
    # 引数: [self: window, path: project-relative asset path]
    # 戻り値: [None: image preview drawn]
    # }
    def _show_artifact(self, path: str | None) -> None:
        self.canvas.delete("all")
        if not path:
            return
        content = self._call("load_panel_preview", path)
        if not isinstance(content, bytes):
            return
        with Image.open(io.BytesIO(content)) as image:
            preview = image.convert("RGB")
            preview.thumbnail((720, 780))
            self.preview = ImageTk.PhotoImage(preview)
        self.canvas.create_image(8, 8, anchor="nw", image=self.preview)

    # {
    # 責務: [save_panel_plan: apply normalized layout and visual intent edits]
    # 処理: [replace selected immutable panel and preserve any other page panels]
    # 引数: [self: window]
    # 戻り値: [None: panel plan updated]
    # }
    def save_panel_plan(self) -> None:
        panel_id = self._selected_panel_id()
        if not panel_id or not self.project:
            return
        current = next(
            panel for page in self.project.pages for panel in page.panels if panel.id == panel_id
        )
        try:
            box = tuple(float(variable.get()) for variable in self.panel_bbox)
            updated = replace(
                current,
                bbox=box,
                shot=self.shot.get().strip(),
                camera=self.camera.get().strip(),
                backend_id=self.backend_id.get().strip() or None,
                action=self.action_text.get("1.0", "end-1c"),
                prompt=self.action_text.get("1.0", "end-1c"),
            )
            self._call("edit_panel", updated)
            self.status.set(f"Updated {panel_id}; neighboring panels retain their current renders.")
        except ValueError as error:
            messagebox.showerror("Panel layout", str(error), parent=self.root)

    # {
    # 責務: [save_dialogue: update editable speaker-attributed lettering]
    # 処理: [parse speaker IDs and preserve dialogue as separate text overlays]
    # 引数: [self: window]
    # 戻り値: [None: dialogue updated]
    # }
    def save_dialogue(self) -> None:
        panel_id = self._selected_panel_id()
        if not panel_id:
            return
        entries = []
        lines = self.dialogue_text.get("1.0", "end-1c").splitlines()
        row_count = max(1, (len(lines) + 1) // 2)
        balloon_height = min(0.22, 0.9 / row_count)
        for index, raw_line in enumerate(lines):
            if not raw_line.strip():
                continue
            speaker, separator, text = raw_line.partition(":")
            speaker_id = speaker.strip() if separator and speaker.strip() else None
            entries.append(
                DialogueLine(
                    f"{panel_id}-dialogue-{index + 1}",
                    text.strip() if separator else raw_line.strip(),
                    speaker_id,
                    BalloonKind.SPEECH,
                    region=(
                        0.62 if index % 2 == 0 else 0.04,
                        0.04 + (index // 2) * (0.92 / row_count),
                        0.34,
                        balloon_height,
                    ),
                )
            )
        self._call("edit_dialogue", panel_id, tuple(entries))
        self.status.set("Dialogue remains editable text and is composed after panel generation.")

    # {
    # 責務: [render_selected: generate candidates for only the selected panel]
    # 処理: [request bounded best-of-N generation and display its proxy review]
    # 引数: [self: window]
    # 戻り値: [None: selected panel regenerated]
    # }
    def render_selected(self) -> None:
        panel_id = self._selected_panel_id()
        if not panel_id:
            return
        self.save_panel_plan()
        result = self._call("render_panel", panel_id, int(self.candidate_count.get()))
        if isinstance(result, tuple):
            self.project = result[0]
            self._refresh_tree()
            panel = next(
                panel
                for page in self.project.pages
                for panel in page.panels
                if panel.id == panel_id
            )
            self._show_artifact(panel.image_path)
            self.status.set(
                "Candidate rendered. "
                + "; ".join(f"{name}={value:.2f}" for name, value in result[1].scores)
                + ". Identity/anatomy/story quality still needs review."
            )

    # {
    # 責務: [repair_selected: request a local correction for one panel]
    # 処理: [send the instruction to an injected repair adapter and preserve other panel renders]
    # 引数: [self: window]
    # 戻り値: [None: targeted repair completed or adapter failure shown]
    # }
    def repair_selected(self) -> None:
        panel_id = self._selected_panel_id()
        if not panel_id:
            return
        instruction = simpledialog.askstring(
            "Local panel repair", "Describe one local correction:", parent=self.root
        )
        if not instruction:
            return
        result = self._call("repair_panel", panel_id, instruction)
        if isinstance(result, tuple):
            self.project = result[0]
            self._refresh_tree()
            panel = next(
                panel
                for page in self.project.pages
                for panel in page.panels
                if panel.id == panel_id
            )
            self._show_artifact(panel.image_path)
            self.status.set(
                "Local repair saved as another candidate; no other panel was regenerated."
            )

    # {
    # 責務: [render_all: generate every planned panel in a resumable sequence]
    # 処理: [invoke the Process pipeline, which persists each panel before continuing]
    # 引数: [self: window]
    # 戻り値: [None: storyboard panel pass completed]
    # }
    def render_all(self) -> None:
        if not self.project:
            return
        result = self._call("render_all_panels", int(self.candidate_count.get()))
        if isinstance(result, MangaProject):
            self._refresh_tree()
            self.status.set("All planned panels have a saved storyboard or backend render.")

    # {
    # 責務: [select_candidate: choose an available panel alternative]
    # 処理: [parse candidate index and route its selection]
    # 引数: [self: window, event: Tk combobox event]
    # 戻り値: [None: selected render becomes active]
    # }
    def select_candidate(self, _event: tk.Event) -> None:
        panel_id = self._selected_panel_id()
        if panel_id and self.candidates.get():
            index = int(self.candidates.get().split(":", 1)[0]) - 1
            self._call("select_candidate", panel_id, index)
            if self.project:
                panel = next(
                    panel
                    for page in self.project.pages
                    for panel in page.panels
                    if panel.id == panel_id
                )
                self._show_artifact(panel.image_path)

    # {
    # 責務: [compose_page: combine one rendered page and dialogue overlays]
    # 処理: [resolve selected page and request Data image composition]
    # 引数: [self: window]
    # 戻り値: [None: page artifact composed]
    # }
    def compose_page(self) -> None:
        if not self.project or not self.tree.selection():
            return
        identifier = self.tree_ids.get(self.tree.selection()[0])
        page = next((item for item in self.project.pages if item.id == identifier), None)
        if page is None:
            panel_id = self._selected_panel_id()
            page = next(
                (
                    item
                    for item in self.project.pages
                    if panel_id and any(panel.id == panel_id for panel in item.panels)
                ),
                None,
            )
        if not page:
            messagebox.showinfo("Compose page", "Select a page or one of its panels first.")
            return
        result = self._call("compose_page", page.id)
        if isinstance(result, tuple):
            self.project = result[0]
            updated_page = next(item for item in self.project.pages if item.id == page.id)
            self._refresh_tree()
            self._show_artifact(updated_page.rendered_path)
            self.status.set(
                "Page composed with dialogue as a separate overlay. " + "; ".join(result[1])
            )


# {
# 責務: [launch: start the Tk Manga Creator editor]
# 処理: [bind the UI Commander and enter the Tk event loop]
# 引数: [commander: UI action router]
# 戻り値: [None: returns after the window closes]
# }
def launch(commander: MangaCreatorUiCommander) -> None:
    root = tk.Tk()
    MangaCreatorWindow(root, commander)
    root.mainloop()
