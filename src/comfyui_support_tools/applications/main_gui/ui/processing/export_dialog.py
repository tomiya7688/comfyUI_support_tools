"""Explicit output choices for caption/TXT/metadata migration."""
import tkinter as tk
from tkinter import filedialog, ttk

from comfyui_support_tools.shared.contracts.inspector_contracts import ExportSettings
from comfyui_support_tools.shared.transparency_preferences import TransparencyPreferenceStore


class ExportDialog(tk.Toplevel):
    def __init__(self, parent, on_export, log):
        super().__init__(parent)
        self.on_export = on_export
        self.log = log
        self.title("Analysis結果を書き出す")
        self.transient(parent.winfo_toplevel())
        self.geometry("900x860")
        self.minsize(780, 760)
        body = ttk.Frame(self, padding=12)
        body.pack(fill="both", expand=True)
        self.caption = tk.BooleanVar(self, value=True)
        self.metadata = tk.BooleanVar(self, value=True)
        self.batch_enabled = tk.BooleanVar(self, value=False)
        self.batch_path = tk.StringVar(self)
        self.include_style = tk.BooleanVar(self, value=False)
        self.overwrite = tk.BooleanVar(self, value=False)
        self.transparency_assist = tk.BooleanVar(self, value=False)
        self.save_transparency_as_global_default = tk.BooleanVar(self, value=False)
        self.save_transparency_as_application_override = tk.BooleanVar(self, value=False)
        self.transparency_preferences = TransparencyPreferenceStore()
        try:
            from comfyui_support_tools.shared.transparency_contracts import resolve_transparency_enabled

            self.transparency_assist.set(
                resolve_transparency_enabled(
                    self.transparency_preferences.global_enabled(),
                    self.transparency_preferences.application_override("analysis_export"),
                )
            )
        except (OSError, ValueError) as exc:
            self.log(f"Transparency Assist global defaultを読み込めません: {exc}")
        self.transparency_sidecar = tk.BooleanVar(self, value=True)
        self.transparency_png_copy = tk.BooleanVar(self, value=False)
        self.transparency_classification = tk.StringVar(self, value="unknown")
        self.transparency_visible_disclosure = tk.BooleanVar(self, value=False)
        self.transparency_prompt_disclosure = tk.StringVar(self, value="none")
        self.transparency_prompt_summary = tk.StringVar(self)
        self.transparency_model_disclosure = tk.StringVar(self, value="none")
        self.transparency_model_family = tk.StringVar(self)
        self.transparency_model_id = tk.StringVar(self)
        self.transparency_model_version = tk.StringVar(self)
        self.transparency_model_hash = tk.StringVar(self)
        self.transparency_workflow_disclosure = tk.StringVar(self, value="none")
        self.transparency_workflow_id = tk.StringVar(self)
        self.transparency_workflow_json_path = tk.StringVar(self)
        self.transparency_deepfake_assist = tk.BooleanVar(self, value=False)
        self.transparency_deepfake_applicable = tk.BooleanVar(self, value=False)
        self.transparency_real_person = tk.BooleanVar(self, value=False)
        self.transparency_c2pa_sign = tk.BooleanVar(self, value=False)
        self.c2pa_certificate = tk.StringVar(self)
        self.c2pa_private_key = tk.StringVar(self)
        self.c2pa_tsa_url = tk.StringVar(self)
        self.c2pa_verification_policy = tk.StringVar(self, value="error")
        ttk.Checkbutton(
            body,
            text="画像と同じ場所へ caption sidecar (.txt)",
            variable=self.caption,
        ).pack(anchor="w", pady=3)
        transparency_row = ttk.Frame(body)
        transparency_row.pack(fill="x", pady=3)
        ttk.Label(transparency_row, text="技術分類（初期値unknown）").pack(side="left")
        self.transparency_classification_box = ttk.Combobox(
            transparency_row,
            textvariable=self.transparency_classification,
            values=("unknown", "generated", "ai_modified", "conventional_edit"),
            state="readonly",
            width=22,
        )
        self.transparency_classification_box.pack(side="left", padx=5)
        prompt_row = ttk.Frame(body)
        prompt_row.pack(fill="x", pady=2)
        ttk.Label(prompt_row, text="Prompt disclosure").pack(side="left")
        self.prompt_disclosure_box = ttk.Combobox(
            prompt_row,
            textvariable=self.transparency_prompt_disclosure,
            values=("none", "hash_only", "sanitized_summary", "full"),
            state="readonly",
            width=20,
        )
        self.prompt_disclosure_box.pack(side="left", padx=5)
        ttk.Label(prompt_row, text="匿名化要約").pack(side="left")
        self.prompt_summary_entry = ttk.Entry(prompt_row, textvariable=self.transparency_prompt_summary)
        self.prompt_summary_entry.pack(side="left", fill="x", expand=True)
        model_row = ttk.Frame(body)
        model_row.pack(fill="x", pady=2)
        ttk.Label(model_row, text="Model disclosure").pack(side="left")
        self.model_disclosure_box = ttk.Combobox(
            model_row,
            textvariable=self.transparency_model_disclosure,
            values=("none", "family", "model_id", "model_id_and_version"),
            state="readonly",
            width=20,
        )
        self.model_disclosure_box.pack(side="left", padx=5)
        ttk.Label(model_row, text="Family").pack(side="left")
        self.model_family_entry = ttk.Entry(model_row, textvariable=self.transparency_model_family, width=14)
        self.model_family_entry.pack(side="left", padx=2)
        ttk.Label(model_row, text="ID").pack(side="left")
        self.model_id_entry = ttk.Entry(model_row, textvariable=self.transparency_model_id, width=14)
        self.model_id_entry.pack(side="left", padx=2)
        ttk.Label(model_row, text="Version").pack(side="left")
        self.model_version_entry = ttk.Entry(model_row, textvariable=self.transparency_model_version, width=9)
        self.model_version_entry.pack(side="left", padx=2)
        ttk.Label(model_row, text="SHA256").pack(side="left")
        self.model_hash_entry = ttk.Entry(model_row, textvariable=self.transparency_model_hash, width=18)
        self.model_hash_entry.pack(side="left", padx=2)
        workflow_row = ttk.Frame(body)
        workflow_row.pack(fill="x", pady=2)
        ttk.Label(workflow_row, text="Workflow disclosure").pack(side="left")
        self.workflow_disclosure_box = ttk.Combobox(
            workflow_row,
            textvariable=self.transparency_workflow_disclosure,
            values=("none", "id", "hash", "full"),
            state="readonly",
            width=20,
        )
        self.workflow_disclosure_box.pack(side="left", padx=5)
        ttk.Label(workflow_row, text="ID").pack(side="left")
        self.workflow_id_entry = ttk.Entry(workflow_row, textvariable=self.transparency_workflow_id)
        self.workflow_id_entry.pack(side="left", fill="x", expand=True, padx=3)
        workflow_file_row = ttk.Frame(body)
        workflow_file_row.pack(fill="x", pady=2)
        ttk.Label(workflow_file_row, text="Workflow JSON (hash/full時)").pack(side="left")
        self.workflow_json_entry = ttk.Entry(
            workflow_file_row, textvariable=self.transparency_workflow_json_path
        )
        self.workflow_json_entry.pack(side="left", fill="x", expand=True, padx=5)
        self.workflow_json_button = ttk.Button(
            workflow_file_row, text="選択", command=self._choose_workflow_json
        )
        self.workflow_json_button.pack(side="left")
        self.transparency_visible_check = ttk.Checkbutton(
            body,
            text="AI-generated / AI-assistedの表示ラベルを別PNGコピーへ追加",
            variable=self.transparency_visible_disclosure,
        )
        self.transparency_visible_check.pack(anchor="w", pady=3)
        ttk.Checkbutton(
            body,
            text="画像と同じ場所へ構造化 metadata (.画像拡張子.kadoka.json)",
            variable=self.metadata,
        ).pack(anchor="w", pady=3)
        row = ttk.Frame(body)
        row.pack(fill="x", pady=3)
        ttk.Checkbutton(row, text="Batch TXT", variable=self.batch_enabled).pack(side="left")
        ttk.Entry(row, textvariable=self.batch_path).pack(side="left", fill="x", expand=True, padx=5)
        ttk.Button(row, text="選択", command=self._choose_batch).pack(side="left")
        ttk.Checkbutton(
            body,
            text="caption生成時にStyle tagsも連結する",
            variable=self.include_style,
        ).pack(anchor="w", pady=3)
        ttk.Checkbutton(
            body,
            text="既存sidecar/metadata/batch TXTの上書きを許可",
            variable=self.overwrite,
        ).pack(anchor="w", pady=3)
        ttk.Checkbutton(
            body,
            text="EU AI Act Transparency Assist sidecarを追加（任意・既定OFF）",
            variable=self.transparency_assist,
        ).pack(anchor="w", pady=3)
        ttk.Checkbutton(
            body,
            text="Transparency Assist sidecar JSONを書き出す",
            variable=self.transparency_sidecar,
        ).pack(anchor="w", pady=2)
        ttk.Checkbutton(
            body,
            text="現在のON/OFFを今後のexportのglobal defaultとして保存",
            variable=self.save_transparency_as_global_default,
        ).pack(anchor="w", pady=2)
        ttk.Checkbutton(
            body,
            text="現在のON/OFFをAnalysis export専用overrideとして保存",
            variable=self.save_transparency_as_application_override,
        ).pack(anchor="w", pady=2)
        ttk.Checkbutton(
            body,
            text="PNGに機械可読metadataを埋め込んだ別コピーも作成",
            variable=self.transparency_png_copy,
        ).pack(anchor="w", pady=3)
        self.transparency_deepfake_assist_check = ttk.Checkbutton(
            body,
            text="Deepfake disclosure assistance（法的判定ではありません）",
            variable=self.transparency_deepfake_assist,
        )
        self.transparency_deepfake_assist_check.pack(anchor="w", pady=2)
        self.transparency_deepfake_applicable_check = ttk.Checkbutton(
            body,
            text="ユーザー申告: 開示対象に該当する",
            variable=self.transparency_deepfake_applicable,
        )
        self.transparency_deepfake_applicable_check.pack(anchor="w", pady=2)
        self.transparency_real_person_check = ttk.Checkbutton(
            body,
            text="ユーザー申告: 実在する人物・場所・出来事を表す/似せている",
            variable=self.transparency_real_person,
        )
        self.transparency_real_person_check.pack(anchor="w", pady=2)
        self.transparency_c2pa_sign_check = ttk.Checkbutton(
            body,
            text="C2PA Content Credentialsを署名して別コピーへ追加（要optional SDKと証明書）",
            variable=self.transparency_c2pa_sign,
        )
        self.transparency_c2pa_sign_check.pack(anchor="w", pady=2)
        certificate_row = ttk.Frame(body)
        certificate_row.pack(fill="x", pady=2)
        ttk.Label(certificate_row, text="署名証明書PEM").pack(side="left")
        self.c2pa_certificate_entry = ttk.Entry(certificate_row, textvariable=self.c2pa_certificate)
        self.c2pa_certificate_entry.pack(
            side="left", fill="x", expand=True, padx=5
        )
        self.c2pa_certificate_button = ttk.Button(
            certificate_row,
            text="選択",
            command=lambda: self._choose_c2pa_file(self.c2pa_certificate, "certificate"),
        )
        self.c2pa_certificate_button.pack(side="left")
        key_row = ttk.Frame(body)
        key_row.pack(fill="x", pady=2)
        ttk.Label(key_row, text="署名秘密鍵PEM").pack(side="left")
        self.c2pa_private_key_entry = ttk.Entry(key_row, textvariable=self.c2pa_private_key, show="•")
        self.c2pa_private_key_entry.pack(
            side="left", fill="x", expand=True, padx=5
        )
        self.c2pa_private_key_button = ttk.Button(
            key_row,
            text="選択",
            command=lambda: self._choose_c2pa_file(self.c2pa_private_key, "private key"),
        )
        self.c2pa_private_key_button.pack(side="left")
        tsa_row = ttk.Frame(body)
        tsa_row.pack(fill="x", pady=2)
        ttk.Label(tsa_row, text="RFC 3161 TSA URL (任意)").pack(side="left")
        self.c2pa_tsa_entry = ttk.Entry(tsa_row, textvariable=self.c2pa_tsa_url)
        self.c2pa_tsa_entry.pack(
            side="left", fill="x", expand=True, padx=5
        )
        policy_row = ttk.Frame(body)
        policy_row.pack(fill="x", pady=2)
        ttk.Label(policy_row, text="C2PA検証失敗時").pack(side="left")
        self.c2pa_policy_box = ttk.Combobox(
            policy_row,
            textvariable=self.c2pa_verification_policy,
            values=("error", "warning"),
            state="readonly",
            width=12,
        )
        self.c2pa_policy_box.pack(side="left", padx=5)
        ttk.Label(
            body,
            text=(
                "captionはimage-to-text captionがあれば優先し、なければcontent/character/copyright tagsから生成します。\n"
                "Transparency Assistは技術的なprovenance補助で、法的適合を保証しません。prompt/model/workflowの初期開示はnoneです。\n"
                "full promptやworkflow全文は選択時のみ公開します。匿名化要約は利用者が入力します。\n"
                "PNG埋め込みは元画像を変更せず別ファイルを作ります。C2PA署名済みPNGは上書きせず拒否します。\n"
                "元画像は変更しません。既存ファイルは上書きONにしない限り失敗します。"
            ),
            wraplength=570,
        ).pack(anchor="w", pady=8)
        buttons = ttk.Frame(body)
        buttons.pack(fill="x")
        ttk.Button(buttons, text="書き出す", command=self._submit).pack(side="left")
        ttk.Button(buttons, text="閉じる", command=self.destroy).pack(side="right")
        self.transparency_assist.trace_add("write", self._refresh_transparency_controls)
        self._refresh_transparency_controls()

    def _refresh_transparency_controls(self, *_):
        enabled = self.transparency_assist.get()
        state = "readonly" if enabled else "disabled"
        self.transparency_classification_box.configure(state=state)
        self.transparency_visible_check.configure(state="normal" if enabled else "disabled")
        read_only_controls = {
            self.prompt_disclosure_box,
            self.model_disclosure_box,
            self.workflow_disclosure_box,
        }
        for control in (
            self.prompt_disclosure_box,
            self.prompt_summary_entry,
            self.model_disclosure_box,
            self.model_family_entry,
            self.model_id_entry,
            self.model_version_entry,
            self.model_hash_entry,
            self.workflow_disclosure_box,
            self.workflow_id_entry,
            self.workflow_json_entry,
            self.workflow_json_button,
        ):
            control.configure(
                state=("readonly" if control in read_only_controls else "normal")
                if enabled
                else "disabled"
            )
        for control in (
            self.transparency_deepfake_assist_check,
            self.transparency_deepfake_applicable_check,
            self.transparency_real_person_check,
            self.transparency_c2pa_sign_check,
            self.c2pa_certificate_entry,
            self.c2pa_certificate_button,
            self.c2pa_private_key_entry,
            self.c2pa_private_key_button,
            self.c2pa_tsa_entry,
        ):
            control.configure(state="normal" if enabled else "disabled")
        self.c2pa_policy_box.configure(state="readonly" if enabled else "disabled")

    def _choose_batch(self):
        path = filedialog.asksaveasfilename(
            parent=self,
            title="Batch TXT出力",
            defaultextension=".txt",
            filetypes=[("Text", "*.txt")],
        )
        if path:
            self.batch_enabled.set(True)
            self.batch_path.set(path)

    def _choose_c2pa_file(self, variable, label):
        path = filedialog.askopenfilename(
            parent=self,
            title=f"C2PA {label}を選択",
            filetypes=[("PEM", "*.pem *.crt *.key"), ("All files", "*.*")],
        )
        if path:
            variable.set(path)

    def _choose_workflow_json(self):
        path = filedialog.askopenfilename(
            parent=self,
            title="Workflow JSONを選択",
            filetypes=[("JSON", "*.json"), ("All files", "*.*")],
        )
        if path:
            self.transparency_workflow_json_path.set(path)

    def _submit(self):
        settings = ExportSettings(
            caption_sidecar=self.caption.get(),
            metadata_sidecar=self.metadata.get(),
            batch_txt_path=self.batch_path.get().strip() if self.batch_enabled.get() else "",
            include_style_in_caption=self.include_style.get(),
            overwrite=self.overwrite.get(),
            transparency_assist=self.transparency_assist.get(),
            save_transparency_as_global_default=self.save_transparency_as_global_default.get(),
            save_transparency_as_application_override=(
                self.save_transparency_as_application_override.get()
            ),
            transparency_sidecar=self.transparency_sidecar.get(),
            transparency_png_copy=self.transparency_png_copy.get(),
            transparency_classification=self.transparency_classification.get(),
            transparency_visible_disclosure=self.transparency_visible_disclosure.get(),
            transparency_prompt_disclosure=self.transparency_prompt_disclosure.get(),
            transparency_prompt_summary=self.transparency_prompt_summary.get(),
            transparency_model_disclosure=self.transparency_model_disclosure.get(),
            transparency_model_family=self.transparency_model_family.get(),
            transparency_model_id=self.transparency_model_id.get(),
            transparency_model_version=self.transparency_model_version.get(),
            transparency_model_hash=self.transparency_model_hash.get(),
            transparency_workflow_disclosure=self.transparency_workflow_disclosure.get(),
            transparency_workflow_id=self.transparency_workflow_id.get(),
            transparency_workflow_json_path=self.transparency_workflow_json_path.get(),
            transparency_deepfake_assist=self.transparency_deepfake_assist.get(),
            transparency_deepfake_applicable=self.transparency_deepfake_applicable.get(),
            transparency_real_person_place_event=self.transparency_real_person.get(),
            transparency_c2pa_sign=self.transparency_c2pa_sign.get(),
            c2pa_certificate_path=self.c2pa_certificate.get().strip(),
            c2pa_private_key_path=self.c2pa_private_key.get().strip(),
            c2pa_timestamp_authority_url=self.c2pa_tsa_url.get().strip(),
            c2pa_verification_failure_policy=self.c2pa_verification_policy.get(),
        )
        try:
            if self.on_export(settings):
                if settings.save_transparency_as_global_default:
                    try:
                        self.transparency_preferences.set_global_enabled(
                            settings.transparency_assist
                        )
                    except (OSError, ValueError) as exc:
                        self.log(f"Transparency Assist global defaultを保存できません: {exc}")
                if settings.save_transparency_as_application_override:
                    try:
                        self.transparency_preferences.set_application_override(
                            "analysis_export", settings.transparency_assist
                        )
                    except (OSError, ValueError) as exc:
                        self.log(f"Analysis export overrideを保存できません: {exc}")
                self.destroy()
        except (ValueError, OSError) as exc:
            self.log(str(exc))
