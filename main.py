import customtkinter as ctk
import tkinter as tk
import pyautogui
import keyboard
import threading
import time
import os
import re
from PIL import Image
import zipfile
import typing
import json

ctk.set_appearance_mode("System")
ctk.set_default_color_theme("blue")


class ToolTip:
    """Hover tooltip for any tkinter/ctk widget."""
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tip_window = None
        widget.bind("<Enter>", self._show)
        widget.bind("<Leave>", self._hide)

    def _show(self, event=None):
        if self.tip_window:
            return
        x = self.widget.winfo_rootx() + 20
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 5
        self.tip_window = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        tw.attributes("-topmost", True)
        label = tk.Label(tw, text=self.text, justify="left",
                         background="#333", foreground="#eee",
                         relief="solid", borderwidth=1,
                         font=("Microsoft JhengHei", 10), padx=6, pady=4)
        label.pack()

    def _hide(self, event=None):
        if self.tip_window:
            self.tip_window.destroy()
            self.tip_window = None


class SnippingOverlay(ctk.CTkToplevel):
    def __init__(self, parent, callback):
        super().__init__(parent)  # type: ignore
        self.callback = callback
        self.attributes('-fullscreen', True)
        self.attributes('-alpha', 0.3)
        self.attributes('-topmost', True)
        self.overrideredirect(True)
        self.config(cursor="cross")

        self.canvas = tk.Canvas(self, bg='black', highlightthickness=0)
        self.canvas.pack(fill='both', expand=True)

        self.start_x = 0
        self.start_y = 0
        self.rect = None

        self.canvas.bind("<ButtonPress-1>", self.on_press)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)
        self.canvas.bind("<Escape>", lambda e: self.destroy())

    def on_press(self, event):
        self.start_x = event.x
        self.start_y = event.y
        self.rect = self.canvas.create_rectangle(
            self.start_x, self.start_y, self.start_x, self.start_y,
            outline='red', width=2, fill=''
        )

    def on_drag(self, event):
        self.canvas.coords(self.rect, self.start_x, self.start_y, event.x, event.y)

    def on_release(self, event):
        x1 = min(self.start_x, event.x)
        y1 = min(self.start_y, event.y)
        x2 = max(self.start_x, event.x)
        y2 = max(self.start_y, event.y)
        parent = self.master
        self.destroy()
        if x2 - x1 > 5 and y2 - y1 > 5:
            parent.after(200, lambda: self.capture_region(x1, y1, x2 - x1, y2 - y1))

    def capture_region(self, x, y, w, h):
        img = pyautogui.screenshot(region=(x, y, w, h))
        self.callback(img)


class AutoClickerApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Auto Image Clicker - Hierarchical")

        self.update_idletasks()
        window_width = 490
        window_height = 980
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        pos_x = 0
        pos_y = 400
        self.geometry(f"{window_width}x{window_height}+{pos_x}+{pos_y}")

        self.targets_dir = "targets"
        self.settings_file = "settings.json"
        os.makedirs(self.targets_dir, exist_ok=True)

        # steps[i] = list of PIL Images; any match in step i triggers click → advance to step i+1
        self.steps: list[list] = [[]]
        self.profile_chain: list[str] = []  # track loaded/appended profile names
        self._capture_target_step = 0
        self.running = False
        self.worker_thread: typing.Any = None
        self.last_click_x: typing.Optional[int] = None

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # ── Steps Panel ──────────────────────────────────────────────
        self.steps_scroll = ctk.CTkScrollableFrame(self, label_text="📋 Recognition Flow")
        self.steps_scroll.grid(row=0, column=0, padx=10, pady=(10, 5), sticky="nsew")
        self.steps_scroll.grid_columnconfigure(0, weight=1)

        self.btn_add_step = ctk.CTkButton(
            self, text="➕ Add Next Step",
            fg_color="#3a3a3a", hover_color="#555",
            command=self.add_step
        )
        self.btn_add_step.grid(row=1, column=0, padx=10, pady=3, sticky="ew")
        ToolTip(self.btn_add_step, "新增下一個辨識步驟\n程式會依序比對每個步驟的圖片")

        # ── Controls ─────────────────────────────────────────────────
        ctrl = ctk.CTkFrame(self)
        ctrl.grid(row=2, column=0, padx=10, pady=5, sticky="ew")
        ctrl.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(ctrl, text="Action:").grid(row=0, column=0, padx=10, pady=6, sticky="w")
        self.action_var = ctk.StringVar(value="Left Click")
        self.action_menu = ctk.CTkOptionMenu(
            ctrl, values=["Left Click", "Right Click", "Double Click", "Move Only"],
            variable=self.action_var, command=lambda _: self.save_settings()
        )
        self.action_menu.grid(row=0, column=1, padx=10, pady=6, sticky="ew")
        ToolTip(self.action_menu, "選擇找到圖片後的動作\nLeft Click: 左鍵點擊\nRight Click: 右鍵點擊\nDouble Click: 雙擊\nMove Only: 僅移動滑鼠不點擊")

        self.lbl_conf = ctk.CTkLabel(ctrl, text="Confidence: 100%")
        self.lbl_conf.grid(row=1, column=0, columnspan=2, padx=10, pady=(6, 0), sticky="w")
        self.conf_slider = ctk.CTkSlider(ctrl, from_=0.1, to=1.0, command=self.update_conf_lbl)
        self.conf_slider.set(1.0)
        self.conf_slider.grid(row=2, column=0, columnspan=2, padx=10, pady=(0, 6), sticky="ew")
        ToolTip(self.conf_slider, "圖片比對信心度\n數值越高要求越精確，100% 表示完全匹配")

        self.lbl_min_conf = ctk.CTkLabel(ctrl, text="Min Confidence (fallback): 90%")
        self.lbl_min_conf.grid(row=3, column=0, columnspan=2, padx=10, pady=(6, 0), sticky="w")
        self.min_conf_slider = ctk.CTkSlider(ctrl, from_=0.1, to=1.0, command=self.update_min_conf_lbl)
        self.min_conf_slider.set(0.90)
        self.min_conf_slider.grid(row=4, column=0, columnspan=2, padx=10, pady=(0, 6), sticky="ew")
        ToolTip(self.min_conf_slider, "最低信心度（遞減重試）\n找不到時會從上方信心度每次降低 5% 重試\n直到此最低值為止")

        self.lbl_delay = ctk.CTkLabel(ctrl, text="Delay after click: 1.5s")
        self.lbl_delay.grid(row=5, column=0, columnspan=2, padx=10, pady=(6, 0), sticky="w")
        self.delay_slider = ctk.CTkSlider(ctrl, from_=0.0, to=5.0, command=self.update_delay_lbl)
        self.delay_slider.set(1.5)
        self.delay_slider.grid(row=6, column=0, columnspan=2, padx=10, pady=(0, 6), sticky="ew")
        ToolTip(self.delay_slider, "點擊成功後的等待時間\n讓畫面有時間載入再進行下一步")

        self.lbl_interval = ctk.CTkLabel(ctrl, text="Check interval: 2.00s")
        self.lbl_interval.grid(row=7, column=0, columnspan=2, padx=10, pady=(6, 0), sticky="w")
        self.interval_slider = ctk.CTkSlider(ctrl, from_=0.0, to=2.0, command=self.update_interval_lbl)
        self.interval_slider.set(2.0)
        self.interval_slider.grid(row=8, column=0, columnspan=2, padx=10, pady=(0, 6), sticky="ew")
        ToolTip(self.interval_slider, "每次搜尋圖片的間隔時間\n數值越小搜尋越頻繁，但較耗資源")

        self.lbl_scroll = ctk.CTkLabel(ctrl, text="找不到圖時捲動: 關閉")
        self.lbl_scroll.grid(row=9, column=0, columnspan=2, padx=10, pady=(6, 0), sticky="w")
        self.scroll_slider = ctk.CTkSlider(ctrl, from_=-1000, to=1000, command=self.update_scroll_lbl)
        self.scroll_slider.set(0)
        self.scroll_slider.grid(row=10, column=0, columnspan=2, padx=10, pady=(0, 6), sticky="ew")
        ToolTip(self.scroll_slider, "找不到圖片時，移動到上次點擊的 X 座標\n並在該位置捲動視窗來尋找按鈕\n← 左邊=往上捲 | 右邊=往下捲 →\n置中為關閉")

        self.lbl_scroll_before = ctk.CTkLabel(ctrl, text="搜尋前捲動: 關閉")
        self.lbl_scroll_before.grid(row=11, column=0, columnspan=2, padx=10, pady=(6, 0), sticky="w")
        self.scroll_before_slider = ctk.CTkSlider(ctrl, from_=-1000, to=1000, command=self.update_scroll_before_lbl)
        self.scroll_before_slider.set(0)
        self.scroll_before_slider.grid(row=12, column=0, columnspan=2, padx=10, pady=(0, 6), sticky="ew")
        ToolTip(self.scroll_before_slider, "每次搜尋圖片之前，先捲動視窗\n← 左邊=往上捲 | 右邊=往下捲 →\n置中為關閉")

        # ── Profile Buttons ───────────────────────────────────────────
        pf = ctk.CTkFrame(self, fg_color="transparent")
        pf.grid(row=3, column=0, padx=10, pady=3, sticky="ew")
        pf.grid_columnconfigure(0, weight=1)
        pf.grid_columnconfigure(1, weight=1)
        pf.grid_columnconfigure(2, weight=1)
        btn_save = ctk.CTkButton(pf, text="💾 Save", fg_color="#0052cc", hover_color="#003d99",
                      command=self.save_profile)
        btn_save.grid(row=0, column=0, padx=(0, 3), sticky="ew")
        ToolTip(btn_save, "儲存目前所有步驟為設定檔（.zip）\n方便之後快速載入相同流程")

        btn_load = ctk.CTkButton(pf, text="📂 Load", fg_color="#0052cc", hover_color="#003d99",
                      command=self.load_profile)
        btn_load.grid(row=0, column=1, padx=3, sticky="ew")
        ToolTip(btn_load, "載入設定檔（.zip）\n會清除目前的步驟，替換為檔案中的內容")

        btn_append = ctk.CTkButton(pf, text="➕ Append", fg_color="#28a745", hover_color="#218838",
                      command=self.append_profile)
        btn_append.grid(row=0, column=2, padx=(3, 0), sticky="ew")
        ToolTip(btn_append, "附加設定檔（.zip）\n將檔案中的步驟接在目前步驟之後\n可串聯多個設定檔形成完整流程")

        # ── Profile Flow Indicator ────────────────────────────────────
        self.lbl_flow = ctk.CTkLabel(self, text="", text_color="#4fc3f7",
                                      font=("Arial", 12, "bold"), wraplength=460, justify="left")

        # ── Hotkeys / Start / Status ──────────────────────────────────
        ctk.CTkLabel(
            self, text="[Ctrl+Shift+P] Start  |  [Ctrl+Shift+Q] Stop",
            font=("Arial", 12, "bold")
        ).grid(row=5, column=0, pady=5)

        self.btn_start = ctk.CTkButton(
            self, text="▶ Start [Ctrl+Shift+P]",
            fg_color="green", hover_color="darkgreen", height=40,
            command=self.toggle_start
        )
        self.btn_start.grid(row=6, column=0, padx=10, pady=5, sticky="ew")
        ToolTip(self.btn_start, "開始/停止自動辨識點擊\n快捷鍵：Ctrl+Shift+P 開始、Ctrl+Shift+Q 停止\n啟動後視窗會自動最小化")

        self.lbl_status = ctk.CTkLabel(self, text="Status: Ready", text_color="gray")
        self.lbl_status.grid(row=7, column=0, padx=10, pady=(3, 10))

        keyboard.add_hotkey("ctrl+shift+p", lambda: self.after(0, self.start_auto))
        keyboard.add_hotkey("ctrl+shift+q", lambda: self.after(0, self.stop_auto))

        self.load_settings()
        self.load_target_images()
        self.rebuild_steps_ui()

    # ── Settings persistence ──────────────────────────────────────────
    def save_settings(self):
        settings = {
            "action": self.action_var.get(),
            "confidence": round(self.conf_slider.get(), 2),
            "min_confidence": round(self.min_conf_slider.get(), 2),
            "delay": round(self.delay_slider.get(), 2),
            "interval": round(self.interval_slider.get(), 2),
            "scroll": int(self.scroll_slider.get()),
            "scroll_before": int(self.scroll_before_slider.get()),
        }
        try:
            with open(self.settings_file, "w") as f:
                json.dump(settings, f)
        except Exception:
            pass

    def load_settings(self):
        try:
            with open(self.settings_file, "r") as f:
                s = json.load(f)
            self.action_var.set(s.get("action", "Left Click"))
            self.conf_slider.set(s.get("confidence", 1.0))
            self.update_conf_lbl(self.conf_slider.get())
            self.min_conf_slider.set(s.get("min_confidence", 0.90))
            self.update_min_conf_lbl(self.min_conf_slider.get())
            self.delay_slider.set(s.get("delay", 1.5))
            self.update_delay_lbl(self.delay_slider.get())
            self.interval_slider.set(s.get("interval", 2.0))
            self.update_interval_lbl(self.interval_slider.get())
            self.scroll_slider.set(s.get("scroll", 0))
            self.update_scroll_lbl(self.scroll_slider.get())
            self.scroll_before_slider.set(s.get("scroll_before", 0))
            self.update_scroll_before_lbl(self.scroll_before_slider.get())
        except (FileNotFoundError, json.JSONDecodeError):
            pass

    # ── Slider callbacks ──────────────────────────────────────────────
    def update_conf_lbl(self, value):
        self.lbl_conf.configure(text=f"Confidence: {int(float(value) * 100)}%")
        self.save_settings()

    def update_min_conf_lbl(self, value):
        self.lbl_min_conf.configure(text=f"Min Confidence (fallback): {int(float(value) * 100)}%")
        self.save_settings()

    def update_delay_lbl(self, value):
        self.lbl_delay.configure(text=f"Delay after click: {float(value):.1f}s")
        self.save_settings()

    def update_interval_lbl(self, value):
        self.lbl_interval.configure(text=f"Check interval: {float(value):.2f}s")
        self.save_settings()

    @staticmethod
    def _scroll_display(val):
        v = int(float(val))
        if v == 0:
            return "關閉"
        if v > 0:
            return f"↓ 往下捲 {v}"
        return f"↑ 往上捲 {abs(v)}"

    def update_scroll_lbl(self, value):
        self.lbl_scroll.configure(text=f"找不到圖時捲動: {self._scroll_display(value)}")
        self.save_settings()

    def update_scroll_before_lbl(self, value):
        self.lbl_scroll_before.configure(text=f"搜尋前捲動: {self._scroll_display(value)}")
        self.save_settings()

    # ── Step management ───────────────────────────────────────────────
    def add_step(self):
        self.steps.append([])
        self.rebuild_steps_ui()

    def delete_step(self, step_idx):
        if len(self.steps) <= 1:
            self._remove_images(self.steps[0])
            self.steps[0] = []
        else:
            self._remove_images(self.steps.pop(step_idx))
            # Rename remaining files to stay consistent
            self._renumber_files()
        self.rebuild_steps_ui()

    def delete_image_from_step(self, step_idx, img_idx):
        if 0 <= step_idx < len(self.steps):
            step = self.steps[step_idx]
            if 0 <= img_idx < len(step):
                img = step.pop(img_idx)
                self._remove_images([img])
                self.rebuild_steps_ui()

    def _remove_images(self, imgs):
        for img in imgs:
            path = getattr(img, 'filepath', None)
            if path and os.path.exists(path):
                try:
                    os.remove(path)
                except Exception:
                    pass

    def _renumber_files(self):
        """Rename on-disk files to match current step indices safely."""
        # Phase 1: temporary rename to avoid collision
        for step in self.steps:
            for img in step:
                old_path = getattr(img, 'filepath', None)
                if old_path and os.path.exists(old_path):
                    tmp = old_path + f".tmp_{int(time.time() * 1000)}"
                    try:
                        os.rename(old_path, tmp)
                        img.filepath = tmp
                    except Exception:
                        pass
        
        # Phase 2: rename to sorted new names
        for step_idx, step in enumerate(self.steps):
            base_timestamp = int(time.time() * 1000)
            for img_idx, img in enumerate(step):
                old_path = getattr(img, 'filepath', None)
                if old_path and os.path.exists(old_path):
                    new_fname = f"s{step_idx:02d}_{base_timestamp + img_idx}.png"
                    new_path = os.path.join(self.targets_dir, new_fname)
                    try:
                        os.rename(old_path, new_path)
                        img.filepath = new_path
                    except Exception:
                        pass

    def move_step(self, step_idx, direction):
        new_idx = step_idx + direction
        if 0 <= new_idx < len(self.steps):
            self.steps[step_idx], self.steps[new_idx] = self.steps[new_idx], self.steps[step_idx]
            self._renumber_files()
            self.rebuild_steps_ui()

    def move_image(self, step_idx, img_idx, direction):
        step = self.steps[step_idx]
        new_idx = img_idx + direction
        if 0 <= new_idx < len(step):
            step[img_idx], step[new_idx] = step[new_idx], step[img_idx]
            self._renumber_files()
            self.rebuild_steps_ui()

    # ── Capture ───────────────────────────────────────────────────────
    def start_capture(self, step_idx):
        self._capture_target_step = step_idx
        self.iconify()
        self.after(300, lambda: SnippingOverlay(self, self.on_capture_done))

    def on_capture_done(self, img):
        self.deiconify()
        step_idx = self._capture_target_step
        try:
            filename = f"s{step_idx:02d}_{int(time.time() * 1000)}.png"
            path = os.path.join(self.targets_dir, filename)
            img.save(path)
            img.filepath = path  # type: ignore
        except Exception as e:
            print("Error saving image:", e)
            img.filepath = None  # type: ignore

        while len(self.steps) <= step_idx:
            self.steps.append([])
        self.steps[step_idx].append(img)
        self.rebuild_steps_ui()

    # ── UI rebuild ────────────────────────────────────────────────────
    def rebuild_steps_ui(self):
        for w in self.steps_scroll.winfo_children():
            w.destroy()

        for step_idx, step_images in enumerate(self.steps):
            # Step frame
            step_frame = ctk.CTkFrame(self.steps_scroll, border_width=2, border_color="#555")
            step_frame.grid(row=step_idx * 2, column=0, padx=5, pady=(5, 0), sticky="ew")
            step_frame.grid_columnconfigure(0, weight=1)

            # Header row
            hdr = ctk.CTkFrame(step_frame, fg_color="transparent")
            hdr.grid(row=0, column=0, padx=5, pady=4, sticky="ew")
            hdr.grid_columnconfigure(0, weight=1)

            ctk.CTkLabel(hdr, text=f"Step {step_idx + 1}",
                         font=("Arial", 13, "bold")).grid(row=0, column=0, sticky="w", padx=5)
            btn_up = ctk.CTkButton(hdr, text="▲", width=26, height=26, fg_color="#555",
                          command=lambda i=step_idx: self.move_step(i, -1))
            btn_up.grid(row=0, column=1, padx=2)
            ToolTip(btn_up, "將此步驟往上移動")

            btn_down = ctk.CTkButton(hdr, text="▼", width=26, height=26, fg_color="#555",
                          command=lambda i=step_idx: self.move_step(i, 1))
            btn_down.grid(row=0, column=2, padx=2)
            ToolTip(btn_down, "將此步驟往下移動")

            btn_capture = ctk.CTkButton(hdr, text="📸 Capture", width=85, height=26,
                          command=lambda i=step_idx: self.start_capture(i))
            btn_capture.grid(row=0, column=3, padx=3)
            ToolTip(btn_capture, "截取螢幕上的目標圖片\n拖曳選取要辨識的按鈕或圖案")

            btn_del = ctk.CTkButton(hdr, text="🗑️", width=32, height=26,
                          fg_color="red", hover_color="darkred",
                          command=lambda i=step_idx: self.delete_step(i))
            btn_del.grid(row=0, column=4, padx=(0, 5))
            ToolTip(btn_del, "刪除此步驟及其所有圖片")

            # Image thumbnail row
            img_scroll = ctk.CTkScrollableFrame(step_frame, height=90,
                                                 orientation="horizontal", fg_color="transparent")
            img_scroll.grid(row=1, column=0, padx=5, pady=(0, 5), sticky="ew")

            if not step_images:
                ctk.CTkLabel(img_scroll, text="(empty — click 📸 Capture)",
                             text_color="gray").pack(padx=10, pady=25)
            else:
                for img_idx, img in enumerate(step_images):
                    preview = img.copy()  # type: ignore
                    if preview.height > 70:
                        preview.thumbnail((int(preview.width * 70 / preview.height), 70))
                    ctk_img = ctk.CTkImage(light_image=preview, dark_image=preview, size=preview.size)

                    img_frame = ctk.CTkFrame(img_scroll, fg_color="transparent")
                    img_frame.pack(side="left", padx=3, pady=3)

                    lbl = ctk.CTkLabel(img_frame, image=ctk_img, text="")
                    lbl.image = ctk_img  # type: ignore
                    lbl.grid(row=0, column=0)

                    actions_frame = ctk.CTkFrame(img_frame, fg_color="transparent")
                    actions_frame.grid(row=1, column=0, pady=(2, 0))

                    ctk.CTkButton(actions_frame, text="◀", width=20, height=20, fg_color="#555", font=("Arial", 10),
                                  command=lambda si=step_idx, ii=img_idx: self.move_image(si, ii, -1)).pack(side="left", padx=1)
                    ctk.CTkButton(actions_frame, text="▶", width=20, height=20, fg_color="#555", font=("Arial", 10),
                                  command=lambda si=step_idx, ii=img_idx: self.move_image(si, ii, 1)).pack(side="left", padx=1)

                    ctk.CTkButton(
                        img_frame, text="✕", width=18, height=18,
                        fg_color="red", hover_color="darkred",
                        corner_radius=9, font=("Arial", 10, "bold"),
                        command=lambda si=step_idx, ii=img_idx: self.delete_image_from_step(si, ii)
                    ).place(relx=1.0, rely=0.0, anchor="ne")

            # Arrow between steps
            if step_idx < len(self.steps) - 1:
                ctk.CTkLabel(self.steps_scroll, text="▼  then look for",
                             font=("Arial", 11), text_color="#888").grid(
                    row=step_idx * 2 + 1, column=0, pady=2
                )

    # ── Profile flow display ────────────────────────────────────────────
    def update_flow_label(self):
        if not self.profile_chain:
            self.lbl_flow.grid_forget()
        else:
            self.lbl_flow.configure(text="📋 " + "  →  ".join(self.profile_chain))
            self.lbl_flow.grid(row=4, column=0, padx=10, pady=(0, 3), sticky="ew")

    # ── Load / Save / Clear ───────────────────────────────────────────
    def load_target_images(self):
        self.steps = []
        try:
            files = sorted(f for f in os.listdir(self.targets_dir) if f.endswith(".png"))
        except Exception:
            self.steps = [[]]
            return

        for filename in files:
            m = re.match(r'^s(\d+)_\d+\.png$', filename)
            step_idx = int(m.group(1)) if m else 0
            path = os.path.join(self.targets_dir, filename)
            try:
                with Image.open(path) as img:
                    img_copy = img.copy()
                    img_copy.filepath = path  # type: ignore
                    while len(self.steps) <= step_idx:
                        self.steps.append([])
                    self.steps[step_idx].append(img_copy)
            except Exception as e:
                print(f"Error loading {filename}:", e)

        if not self.steps:
            self.steps = [[]]

    def clear_all(self):
        self.steps = [[]]
        self.profile_chain = []
        try:
            for f in os.listdir(self.targets_dir):
                if f.endswith(".png"):
                    os.remove(os.path.join(self.targets_dir, f))
        except Exception as e:
            print("Error clearing:", e)
        self.rebuild_steps_ui()

    def save_profile(self):
        if not any(self.steps):
            self.lbl_status.configure(text="No targets to save.", text_color="red")
            return
        filepath = ctk.filedialog.asksaveasfilename(  # type: ignore
            defaultextension=".zip", filetypes=[("Scenario Zip", "*.zip")], title="Save Profile")
        if filepath:
            try:
                with zipfile.ZipFile(filepath, 'w') as zf:
                    for f in os.listdir(self.targets_dir):
                        if f.endswith(".png"):
                            zf.write(os.path.join(self.targets_dir, f), f)
                self.lbl_status.configure(text=f"Saved: {os.path.basename(filepath)}", text_color="green")
            except Exception as e:
                self.lbl_status.configure(text=f"Save error: {e}", text_color="red")

    def load_profile(self):
        filepath = ctk.filedialog.askopenfilename(  # type: ignore
            filetypes=[("Scenario Zip", "*.zip")], title="Load Profile")
        if filepath:
            try:
                self.clear_all()
                with zipfile.ZipFile(filepath, 'r') as zf:
                    for member in zf.namelist():
                        basename = os.path.basename(member)
                        if not basename or basename != member:
                            continue
                        zf.extract(member, self.targets_dir)
                self.load_target_images()
                self.rebuild_steps_ui()
                name = os.path.basename(filepath)
                self.profile_chain = [name]
                self.update_flow_label()
                self.lbl_status.configure(text=f"Loaded: {name}", text_color="green")
            except Exception as e:
                self.lbl_status.configure(text=f"Load error: {e}", text_color="red")

    def append_profile(self):
        filepath = ctk.filedialog.askopenfilename(  # type: ignore
            filetypes=[("Scenario Zip", "*.zip")], title="Append Profile")
        if filepath:
            try:
                if len(self.steps) == 1 and not self.steps[0]:
                    base_step_offset = 0
                else:
                    if not self.steps[-1]:
                        base_step_offset = len(self.steps) - 1
                    else:
                        base_step_offset = len(self.steps)

                with zipfile.ZipFile(filepath, 'r') as zf:
                    for member in zf.namelist():
                        basename = os.path.basename(member)
                        if not basename or basename != member:
                            continue
                        
                        m = re.match(r'^s(\d+)_(\d+)\.png$', basename)
                        if m:
                            orig_step = int(m.group(1))
                            timestamp = m.group(2)
                            new_step = base_step_offset + orig_step
                            new_filename = f"s{new_step:02d}_{timestamp}.png"
                            
                            while os.path.exists(os.path.join(self.targets_dir, new_filename)):
                                timestamp = str(int(time.time() * 1000))
                                new_filename = f"s{new_step:02d}_{timestamp}.png"
                                time.sleep(0.001)

                            extracted_path = os.path.join(self.targets_dir, new_filename)
                            with zf.open(member) as source, open(extracted_path, "wb") as target:
                                target.write(source.read())

                self.load_target_images()
                self.rebuild_steps_ui()
                name = os.path.basename(filepath)
                self.profile_chain.append(name)
                self.update_flow_label()
                self.lbl_status.configure(text=f"Appended: {name}", text_color="green")
            except Exception as e:
                self.lbl_status.configure(text=f"Append error: {e}", text_color="red")

    # ── Start / Stop ──────────────────────────────────────────────────
    def toggle_start(self):
        if self.running:
            self.stop_auto()
        else:
            self.start_auto()

    def start_auto(self):
        if self.running:
            return
        if not any(self.steps):
            self.lbl_status.configure(text="Please capture at least one target.", text_color="red")
            return
        self.running = True
        self.btn_start.configure(text="⏹ Stop [Ctrl+Shift+Q]", fg_color="red", hover_color="darkred")
        self.lbl_status.configure(text="Status: RUNNING — Step 1", text_color="green")
        self.title("[RUNNING] Auto Image Clicker")
        self.iconify()
        self.worker_thread = threading.Thread(target=self.auto_loop, daemon=True)
        self.worker_thread.start()

    def stop_auto(self):
        if not self.running:
            return
        self.running = False
        self.btn_start.configure(text="▶ Start [Ctrl+Shift+P]", fg_color="green", hover_color="darkgreen")
        self.lbl_status.configure(text="Status: Stopped", text_color="gray")
        self.title("Auto Image Clicker - Hierarchical")
        self.deiconify()

    # ── Auto Loop ─────────────────────────────────────────────────────
    def auto_loop(self):
        current_step = 0

        while self.running:
            try:
                interval = float(self.interval_slider.get())
                conf = float(self.conf_slider.get())
                min_conf = float(self.min_conf_slider.get())
                action = str(self.action_var.get())
                delay = float(self.delay_slider.get())
                scroll_amt = int(self.scroll_slider.get())
                scroll_before_amt = int(self.scroll_before_slider.get())
            except Exception:
                time.sleep(0.1)
                continue

            # Sleep in small chunks so stop responds quickly
            elapsed = 0.0
            while elapsed < interval and self.running:
                time.sleep(0.1)
                elapsed += 0.1
            if not self.running:
                break

            if scroll_before_amt != 0:
                pyautogui.scroll(scroll_before_amt)
                time.sleep(0.3)
                if not self.running:
                    break

            # Ensure min_conf <= conf
            min_conf = min(min_conf, conf)

            total = len(self.steps)
            if total == 0:
                continue
            if current_step >= total:
                current_step = 0

            step_images = self.steps[current_step]
            if not step_images:
                # Skip empty step
                current_step = (current_step + 1) % total
                continue

            matched = False
            for img in step_images:
                if matched:
                    break
                # Try confidence from max down to min_conf in steps of 5%
                try_conf = conf
                while try_conf >= min_conf - 0.001:
                    try:
                        loc = pyautogui.locateOnScreen(img, confidence=try_conf, grayscale=False)
                        if loc:
                            center = pyautogui.center(loc)
                            if action == "Left Click":
                                pyautogui.click(center.x, center.y)
                            elif action == "Right Click":
                                pyautogui.rightClick(center.x, center.y)
                            elif action == "Double Click":
                                pyautogui.doubleClick(center.x, center.y)
                            elif action == "Move Only":
                                pyautogui.moveTo(center.x, center.y)

                            self.last_click_x = center.x

                            next_step = (current_step + 1) % total
                            used_pct = int(try_conf * 100)
                            self.after(0, lambda s=current_step, ns=next_step, cx=center.x, cy=center.y, p=used_pct:
                                       self.lbl_status.configure(
                                           text=f"Step {s+1} ✓ (conf {p}%)  →  waiting Step {ns+1} | X:{cx} Y:{cy}",
                                           text_color="green"
                                       ))

                            time.sleep(delay)
                            current_step = next_step
                            matched = True
                            break
                    except getattr(pyautogui, 'ImageNotFoundException', Exception):
                        pass
                    except Exception as e:
                        print("Error in auto_loop:", e)
                        break
                    # Lower confidence by 5% and retry
                    try_conf = round(try_conf - 0.05, 2)
                    if try_conf < min_conf:
                        break

            if not matched and self.running and scroll_amt != 0 and self.last_click_x is not None:
                screen_center_y = pyautogui.size().height // 2
                pyautogui.moveTo(self.last_click_x, screen_center_y)
                pyautogui.scroll(scroll_amt)
                time.sleep(0.3)


if __name__ == "__main__":
    app = AutoClickerApp()
    app.mainloop()
