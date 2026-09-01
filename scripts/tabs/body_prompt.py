from ..context import *
from ..context import _safe_thread
from ..services import *
from ..widgets.preset_store import PresetStore

class BodyPromptTab(ttk.Frame):
    """body_prompt_gui.py を統合版向けに移植したタブ。

    元ファイルは import すると単体 GUI の mainloop が走るため、
    ここでは処理だけを安全に移植しています。
    """
    FIELDS = ["height", "weight", "bust", "waist", "hips", "cup", "age"]

    def __init__(self, master):
        super().__init__(master, padding=10)
        self.vars = {name: tk.StringVar(value="") for name in self.FIELDS}
        self.preset_store = PresetStore("body_prompt")
        self.preset_name = tk.StringVar()
        self._build()

    def _build(self):
        form = ttk.LabelFrame(self, text="入力", padding=8)
        form.pack(fill="x")

        labels = {
            "height": "height / 身長(cm)",
            "weight": "weight / 体重(kg)",
            "bust": "bust / バスト(cm)",
            "waist": "waist / ウエスト(cm)",
            "hips": "hips / ヒップ(cm)",
            "cup": "cup / カップ",
            "age": "age / 年齢",
        }

        for i, field in enumerate(self.FIELDS):
            ttk.Label(form, text=labels[field], width=22).grid(row=i, column=0, sticky="w", padx=4, pady=3)
            ttk.Entry(form, textvariable=self.vars[field], width=24).grid(row=i, column=1, sticky="w", padx=4, pady=3)

        buttons = ttk.Frame(form)
        buttons.grid(row=len(self.FIELDS), column=0, columnspan=2, sticky="we", padx=4, pady=(8, 2))
        ttk.Button(buttons, text="生成", command=self.process_safe).pack(side="left")
        ttk.Label(buttons, text="preset").pack(side="left", padx=(16, 4))
        self.preset_combo = ttk.Combobox(buttons, textvariable=self.preset_name, width=18)
        self.preset_combo.pack(side="left")
        ttk.Button(buttons, text="保存", command=self.save_preset).pack(side="left", padx=4)
        ttk.Button(buttons, text="読込", command=self.load_preset).pack(side="left", padx=4)

        out_frame = ttk.LabelFrame(self, text="出力 / エラー", padding=8)
        out_frame.pack(fill="both", expand=True, pady=(8, 0))
        self.output = ScrolledText(out_frame, height=14, width=90, wrap="word")
        self.output.pack(fill="both", expand=True)
        self._refresh_preset_choices()

    def _refresh_preset_choices(self):
        self.preset_combo.configure(values=self.preset_store.names())

    def save_preset(self):
        try:
            values = {field: variable.get() for field, variable in self.vars.items()}
            path = self.preset_store.save(self.preset_name.get(), values)
            self.preset_name.set(path.stem)
            self._refresh_preset_choices()
            self._write_output(f"プリセットを保存しました: {path}")
        except Exception as error:
            self._write_output(f"プリセット保存エラー: {error}")

    def load_preset(self):
        try:
            values = self.preset_store.load(self.preset_name.get())
            for field, variable in self.vars.items():
                variable.set(str(values.get(field, variable.get())))
            self._write_output("プリセットを読み込みました")
        except Exception as error:
            self._write_output(f"プリセット読込エラー: {error}")

    def _write_output(self, text: str) -> None:
        self.output.configure(state="normal")
        self.output.delete("1.0", tk.END)
        self.output.insert(tk.END, text)
        self.output.see("end")

    @staticmethod
    def _parse_float(text: str):
        text = text.strip().replace("，", ",").replace(",", ".")
        if text == "":
            return None
        return float(text)

    @staticmethod
    def _parse_int(text: str):
        text = text.strip()
        if text == "":
            return None
        return int(float(text))

    def get_input_data(self):
        return {
            "height": self._parse_float(self.vars["height"].get()),
            "weight": self._parse_float(self.vars["weight"].get()),
            "bust": self._parse_float(self.vars["bust"].get()),
            "waist": self._parse_float(self.vars["waist"].get()),
            "hips": self._parse_float(self.vars["hips"].get()),
            "cup": self.vars["cup"].get().strip().upper() or None,
            "age": self._parse_int(self.vars["age"].get()),
        }

    @staticmethod
    def estimate_underbust(data):
        """
        ウエストからアンダーを推定
        """
        if data["waist"] is None:
            return None
        age = data["age"]
        if age is None:
            return None
        if age < 8:
            return data["waist"] + 2
        elif data["age"] < 10:
            return data["waist"] + 3
        elif data["age"] < 12:
            return data["waist"] + 4
        elif data["age"] < 13:
            return data["waist"] + 5
        elif data["age"] < 14:
            return data["waist"] + 6
        elif data["age"] < 15:
            return data["waist"] + 7
        elif data["age"] < 16:
            return data["waist"] + 8
        elif data["age"] < 18:
            return data["waist"] + 9
        else:
            return data["waist"] + 11


    @staticmethod
    def estimate_cup(data, under):
        if data["cup"]:
            return data["cup"]
        if data["bust"] is None or under is None:
            return None
        diff = data["bust"] - under
        if diff < 5: return "AA"
        if diff < 10: return "A"
        if diff < 12.5: return "B"
        if diff < 15: return "C"
        if diff < 17.5: return "D"
        if diff < 20: return "E"
        if diff < 22.5: return "F"
        if diff < 25: return "G"
        if diff < 27.5: return "H"
        if diff < 30: return "I"
        if diff < 32.5: return "J"
        if diff < 35: return "K"
        if diff < 37.5: return "L"
        if diff < 40: return "M"
        if diff < 42.5: return "N"
        if diff < 45: return "O"
        if diff < 47.5: return "P"
        if diff < 50: return "Q"
        if diff < 52.5: return "R"
        if diff < 55: return "S"
        if diff < 57.5: return "T"
        if diff < 60: return "U"
        if diff < 62.5: return "V"
        if diff < 65: return "W"
        if diff < 67.5: return "X"
        if diff < 70: return "Y"
        if diff < 72.5: return "Z"
        return "ZZ"

    @staticmethod
    def calculate_bmi(data):
        if data["height"] and data["weight"]:
            return data["weight"] / ((data["height"] / 100) ** 2)
        return None

    @staticmethod
    def generate_body_tags(data, bmi, cup):
        tags = []
        age = data["age"]

        if age:
            if age < 7:
                tags += ["toddler"]
            elif age < 12:
                tags += ["child"]
            elif age < 15:
                tags += ["pre-teen"]
            elif age < 18:
                tags += ["teenager"]
            elif age < 25:
                tags += ["young girl"]

            if age < 6:
                tags += ["preschooler girl"]
            elif 6 < age <= 12:
                tags += ["js", "elementary School student girl"]
            elif 12 < age <= 15:
                tags += ["jc", "junior high school student girl"]
            elif 15 < age <= 18:
                tags += ["jk", "high school student girl"]
            elif 18 < age <= 22:
                tags += ["college student girl", "university student girl", "jd"]

        if data["height"]:
            if data["height"] < 150:
                tags += ["petite", "short height"]
            elif data["height"] > 165:
                tags += ["tall"]

        if bmi:
            if bmi < 17:
                tags += ["slim body", "delicate frame"]
            elif bmi < 20:
                tags += ["slim body"]
            else:
                tags += ["average body"]

       
        if cup == "AA":
            tags += ["flat chest"]
        elif cup == "A":
            tags += ["flat chest", "very small breasts"]
        elif cup == "B":
            tags += ["small breasts"]
        elif cup == "C":
            tags += ["medium breasts", "small breasts"]
        elif cup == "D":
            tags += ["medium breasts"]
        elif cup == "E":
            tags += ["large breasts", "medium breasts"]
        elif cup == "F":
            tags += ["large breasts"]
        elif cup == "G":
            tags += ["large breasts", "busty"]
        elif cup == "H":
            tags += ["huge breasts", "large breasts", "busty"]
        elif cup in ["I", "J", "K"]:
            tags += ["huge breasts", "busty"]
        else:
            tags += ["gigantic breasts"]

        if data["waist"]:
            if data["waist"] < 63:
                tags += ["slim waist"]

        if data["hips"]:
            if data["hips"] < 80:
                tags += ["small hips"]
            elif data["hips"] < 90:
                tags += ["balanced hips"]
            else:
                tags += ["wide hips"]

        tags += ["feminine proportions", "compact build"]
        return tags

    @staticmethod
    def generate_prompt(data, cup, tags):
        prompt = ["1girl"]
        age = data["age"]

        if age:
            prompt.append(f"({age} years old girl)")

        for tag in tags:
            prompt.append(f"({tag})")

        if age:
            prompt.append(f"(The girl's age is {int(age)} years old)")
        if data["height"]:
            prompt.append(f"(The girl's height is {int(data['height'])}cm)")
        if data["weight"]:
            prompt.append(f"(The girl's weight is {int(data['weight'])}kg)")

        
        if data["bust"]:
            prompt.append(f"(the girl's Bust size is {int(data['bust'])}cm)")
        if cup:
            prompt.append(f"({cup} cup breasts)")

        if data["waist"]:
            prompt.append(f"(the girl's Waist size is {int(data['waist'])}cm)")
        if data["hips"]:
            prompt.append(f"(the girl's Hips size is {int(data['hips'])}cm)")

        return ", ".join(prompt)

    def process_safe(self):
        try:
            data = self.get_input_data()
            under = self.estimate_underbust(data)
            cup = self.estimate_cup(data, under)
            bmi = self.calculate_bmi(data)
            tags = self.generate_body_tags(data, bmi, cup)
            prompt = self.generate_prompt(data, cup, tags)
            self._write_output(prompt)
        except Exception as e:
            import traceback
            self._write_output("❌ Body Prompt エラー:\n" + "".join(traceback.format_exception_only(type(e), e)).strip())
