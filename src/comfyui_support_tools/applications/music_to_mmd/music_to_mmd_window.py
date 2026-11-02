"""Tk editor for song analysis, section regeneration, and VMD export."""

from __future__ import annotations

import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from comfyui_support_tools.shared.music_to_mmd import DANCE_STYLES, MusicToMmdApplication
from comfyui_support_tools.shared.video_to_mmd.contracts import RetargetProfile, RetargetRule


# {
# 責務: [MusicToMmdWindow: expose music-to-MMD workflows in a standalone desktop app]
# フィールド: [audio/style/BPM controls, section list, background job result queue]
# 処理: [analyze audio, generate and reroll sections, report quality, export VMD]
# }
class MusicToMmdWindow(tk.Tk):
    # {
    # 責務: [__init__: initialize UI and background orchestration]
    # 処理: [create controls and configure shared application]
    # 引数: [application: optional decoder/backend registry]
    # 戻り値: [None: initialized Tk root]
    # }
    def __init__(self, application: MusicToMmdApplication | None = None):
        super().__init__()
        self.title("Music to MMD Dance")
        self.geometry("980x680")
        self.minsize(760, 520)
        self.application = application or MusicToMmdApplication()
        self.session = None
        self._results = queue.Queue()
        self._worker = None
        self.audio_path = tk.StringVar(self)
        self.bpm = tk.StringVar(self)
        self.style = tk.StringVar(self, value="pop")
        self.instruction = tk.StringVar(self)
        self.section_instruction = tk.StringVar(self)
        self.status = tk.StringVar(self, value="PCM WAV is supported by the built-in decoder.")
        self._build()

    # {
    # 責務: [_build: layout audio controls, timeline sections, report, and export]
    # 処理: [provide a selected-section reroll instead of whole-song editing only]
    # 引数: [None: initialized window]
    # 戻り値: [None: widgets attached]
    # }
    def _build(self) -> None:
        row = ttk.Frame(self, padding=8)
        row.pack(fill="x")
        ttk.Label(row, text="Song").pack(side="left")
        ttk.Entry(row, textvariable=self.audio_path).pack(
            side="left", fill="x", expand=True, padx=8
        )
        ttk.Button(row, text="Browse", command=self._browse).pack(side="left")
        settings = ttk.Frame(self, padding=(8, 0, 8, 8))
        settings.pack(fill="x")
        ttk.Label(settings, text="BPM override").pack(side="left")
        ttk.Entry(settings, textvariable=self.bpm, width=8).pack(side="left", padx=4)
        ttk.Label(settings, text="Style").pack(side="left", padx=(8, 0))
        ttk.Combobox(
            settings, textvariable=self.style, values=DANCE_STYLES, state="readonly", width=18
        ).pack(side="left", padx=4)
        ttk.Entry(settings, textvariable=self.instruction).pack(
            side="left", fill="x", expand=True, padx=4
        )
        ttk.Button(settings, text="Analyze + Generate", command=self._generate).pack(side="left")
        panes = ttk.Panedwindow(self, orient="horizontal")
        panes.pack(fill="both", expand=True, padx=8, pady=6)
        left, right = ttk.Frame(panes, padding=6), ttk.Frame(panes, padding=6)
        panes.add(left, weight=1)
        panes.add(right, weight=2)
        ttk.Label(left, text="Song sections").pack(anchor="w")
        self.sections = tk.Listbox(left, exportselection=False)
        self.sections.pack(fill="both", expand=True, pady=6)
        ttk.Entry(left, textvariable=self.section_instruction).pack(fill="x", pady=4)
        ttk.Button(left, text="Regenerate this section", command=self._regenerate).pack(fill="x")
        ttk.Label(right, text="Music and motion evaluation").pack(anchor="w")
        self.report = tk.Text(right, state="disabled", wrap="word")
        self.report.pack(fill="both", expand=True, pady=6)
        ttk.Button(right, text="Export VMD + reports", command=self._export).pack(anchor="e")
        ttk.Label(
            self,
            text="No PMX geometry/cloth physics/IK preview is bundled. Review the exported VMD in MMD.",
            padding=6,
        ).pack(fill="x")
        ttk.Label(self, textvariable=self.status, padding=6).pack(fill="x")

    # {
    # 責務: [_browse: choose an audio source]
    # 処理: [offer WAV/MP3/FLAC and permit custom injected decoders]
    # 引数: [None: opens file selection]
    # 戻り値: [None: updates file entry]
    # }
    def _browse(self) -> None:
        selected = filedialog.askopenfilename(
            filetypes=(("Audio", "*.wav *.mp3 *.flac"), ("All files", "*.*")), parent=self
        )
        if selected:
            self.audio_path.set(selected)

    # {
    # 責務: [_profile: provide the procedural source-to-MMD bone map]
    # 処理: [map generated full-body joints to standard Japanese MMD bone labels]
    # 引数: [None: static profile]
    # 戻り値: [RetargetProfile: configured bone map]
    # }
    def _profile(self) -> RetargetProfile:
        mapping = (
            ("root", "センター"),
            ("center", "グルーブ"),
            ("upper_body", "上半身"),
            ("head", "頭"),
            ("left_arm", "左腕"),
            ("right_arm", "右腕"),
            ("left_leg", "左足"),
            ("right_leg", "右足"),
            ("left_foot", "左つま先"),
            ("right_foot", "右つま先"),
        )
        return RetargetProfile(
            "MMD-standard", tuple(RetargetRule(source, target) for source, target in mapping)
        )

    # {
    # 責務: [_generate: queue full song analysis and motion synthesis]
    # 処理: [capture UI settings then analyze, plan, generate, and evaluate off-thread]
    # 引数: [None: reads window settings]
    # 戻り値: [None: starts worker]
    # }
    def _generate(self) -> None:
        source = Path(self.audio_path.get())
        if not source.is_file():
            messagebox.showerror("Music to MMD", "Choose an audio file first.", parent=self)
            return
        try:
            bpm = float(self.bpm.get()) if self.bpm.get().strip() else None
        except ValueError:
            messagebox.showerror("Music to MMD", "BPM must be a number in 40..240.", parent=self)
            return
        style, instruction, profile = self.style.get(), self.instruction.get(), self._profile()

        # {
        # 責務: [work: create session and generate every planned section]
        # 処理: [run analysis/generation and enqueue session/evaluation]
        # 引数: [None: closes over captured settings]
        # 戻り値: [None: puts completion in queue]
        # }
        def work():
            session = self.application.create_session(
                source,
                profile,
                style=style,
                instruction=instruction,
                bpm=bpm,
                required_capabilities=frozenset(
                    {"beat_alignment", "genre_control", "editable_sections"}
                ),
            )
            session.generate()
            self._results.put(("generated", session, session.evaluate()[2], None))

        self._start(work, "Analyzing audio and generating section motion…")

    # {
    # 責務: [_regenerate: reroll one selected movement section]
    # 処理: [preserve all other cached sections and update only target segment]
    # 引数: [None: reads section selection and instruction]
    # 戻り値: [None: starts selected section job]
    # }
    def _regenerate(self) -> None:
        selection = self.sections.curselection()
        if self.session is None or not selection:
            messagebox.showinfo(
                "Music to MMD", "Generate a song and select a section first.", parent=self
            )
            return
        section_id = self.sections.get(selection[0]).split(" | ", 1)[0]
        instruction = self.section_instruction.get() or None

        # {
        # 責務: [work: regenerate the selected segment]
        # 処理: [use captured instruction and recalculate full-song metrics]
        # 引数: [None: closes over session and selected section]
        # 戻り値: [None: puts updated session in queue]
        # }
        def work():
            self.session.regenerate_section(section_id, instruction=instruction)
            self._results.put(("regenerated", self.session, self.session.evaluate()[2], section_id))

        self._start(work, f"Regenerating {section_id}…")

    # {
    # 責務: [_start: execute long analysis away from Tk event thread]
    # 処理: [run worker callable, queue exceptions, and schedule UI polling]
    # 引数: [work: thread job, message: progress status]
    # 戻り値: [None: starts daemon thread]
    # }
    def _start(self, work, message: str) -> None:
        if self._worker is not None and self._worker.is_alive():
            return
        self.status.set(message)

        # {
        # 責務: [runner: execute worker and transport exceptions]
        # 処理: [run one callback and enqueue any failure]
        # 引数: [None: closes over work and queue]
        # 戻り値: [None: enqueues errors]
        # }
        def runner():
            try:
                work()
            except Exception as error:
                self._results.put(("error", None, None, error))

        self._worker = threading.Thread(target=runner, daemon=True)
        self._worker.start()
        self.after(100, self._poll)

    # {
    # 責務: [_poll: receive background results on the UI thread]
    # 処理: [populate sections/report or show the captured error]
    # 引数: [None: reads result queue]
    # 戻り値: [None: updates window widgets]
    # }
    def _poll(self) -> None:
        try:
            kind, session, evaluation, detail = self._results.get_nowait()
        except queue.Empty:
            if self._worker is not None and self._worker.is_alive():
                self.after(100, self._poll)
            return
        if kind == "error":
            self.status.set("Job failed.")
            messagebox.showerror("Music to MMD", str(detail), parent=self)
            return
        self.session = session
        if kind == "generated":
            self.sections.delete(0, "end")
            for section in session.plan.sections:
                self.sections.insert(
                    "end",
                    f"{section.section_id} | {section.kind} | {section.start_frame}–{section.end_frame}",
                )
        self._show_report(evaluation)
        self.status.set(
            f"{len(session.generated_sections)} sections ready via {session.backend_name}."
        )

    # {
    # 責務: [_show_report: display metric dimensions and analysis caveats]
    # 処理: [render BPM, beat count, score values, and PMX/semantic limitations]
    # 引数: [evaluation: dance score report]
    # 戻り値: [None: replaces report text]
    # }
    def _show_report(self, evaluation) -> None:
        scores = "\n".join(f"{name}: {score:.3f}" for name, score in evaluation.scores)
        notes = "\n".join(f"- {note}" for note in evaluation.notes)
        text = f"BPM: {self.session.analysis.bpm:.1f}\nBeats: {len(self.session.analysis.beats)}\nSections: {len(self.session.plan.sections)}\n\n{scores}\n\nLimitations\n{notes}"
        self.report.configure(state="normal")
        self.report.delete("1.0", "end")
        self.report.insert("1.0", text)
        self.report.configure(state="disabled")

    # {
    # 責務: [_export: write full-song VMD and JSON reports]
    # 処理: [serialize current session to a no-overwrite destination]
    # 引数: [None: asks for target directory]
    # 戻り値: [None: updates status or shows an error]
    # }
    def _export(self) -> None:
        if self.session is None:
            messagebox.showinfo("Music to MMD", "Generate motion first.", parent=self)
            return
        folder = filedialog.askdirectory(parent=self, title="Export VMD and reports")
        if folder:
            try:
                result = self.session.export(Path(folder))
                self.status.set(
                    f"Exported {result.vmd_path.name} with choreography and evaluation reports."
                )
            except (OSError, ValueError) as error:
                messagebox.showerror("Export error", str(error), parent=self)


# {
# 責務: [main: launch Music to MMD standalone editor]
# 処理: [start Tk event loop]
# 引数: [None: no arguments]
# 戻り値: [None: exits when window closes]
# }
def main() -> None:
    MusicToMmdWindow().mainloop()
