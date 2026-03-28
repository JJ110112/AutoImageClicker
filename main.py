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

ctk.set_appearance_mode("System")
ctk.set_default_color_theme("blue")


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
        window_height = 910
        screen_height = self.winfo_screenheight()
        pos_x = 20
        pos_y = 20  # Stay at the top instead of aligning to bottom
        self.geometry(f"{window_width}x{window_height}+{pos_x}+{pos_y}")

        self.targets_dir = "targets"
        os.makedirs(self.targets_dir, exist_ok=True)

        # steps[i] = list of PIL Images; any match in step i triggers click → advance to step i+1
        self.steps: list[list] = [[]]
        self._capture_target_step = 0
        self.running = False
        self.worker_thread: typing.Any = None

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

        # ── Controls ─────────────────────────────────────────────────
        ctrl = ctk.CTkFrame(self)
        ctrl.grid(row=2, column=0, padx=10, pady=5, sticky="ew")
        ctrl.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(ctrl, text="Action:").grid(row=0, column=0, padx=10, pady=6, sticky="w")
        self.action_var = ctk.StringVar(value="Left Click")
        ctk.CTkOptionMenu(
            ctrl, values=["Left Click", "Right Click", "Double Click", "Move Only"],
            variable=self.action_var
        ).grid(row=0, column=1, padx=10, pady=6, sticky="ew")

        self.lbl_conf = ctk.CTkLabel(ctrl, text="Confidence: 75%")
        self.lbl_conf.grid(row=1, column=0, columnspan=2, padx=10, pady=(6, 0), sticky="w")
        self.conf_slider = ctk.CTkSlider(ctrl, from_=0.1, to=1.0, command=self.update_conf_lbl)
        self.conf_slider.set(0.75)
        self.conf_slider.grid(row=2, column=0, columnspan=2, padx=10, pady=(0, 6), sticky="ew")

        self.lbl_min_conf = ctk.CTkLabel(ctrl, text="Min Confidence (fallback): 50%")
        self.lbl_min_conf.grid(row=3, column=0, columnspan=2, padx=10, pady=(6, 0), sticky="w")
        self.min_conf_slider = ctk.CTkSlider(ctrl, from_=0.1, to=1.0, command=self.update_min_conf_lbl)
        self.min_conf_slider.set(0.50)
        self.min_conf_slider.grid(row=4, column=0, columnspan=2, padx=10, pady=(0, 6), sticky="ew")

        self.lbl_delay = ctk.CTkLabel(ctrl, text="Delay after click: 0.5s")
        self.lbl_delay.grid(row=5, column=0, columnspan=2, padx=10, pady=(6, 0), sticky="w")
        self.delay_slider = ctk.CTkSlider(ctrl, from_=0.0, to=5.0, command=self.update_delay_lbl)
        self.delay_slider.set(0.5)
        self.delay_slider.grid(row=6, column=0, columnspan=2, padx=10, pady=(0, 6), sticky="ew")

        self.lbl_interval = ctk.CTkLabel(ctrl, text="Check interval: 0.1s")
        self.lbl_interval.grid(row=7, column=0, columnspan=2, padx=10, pady=(6, 0), sticky="w")
        self.interval_slider = ctk.CTkSlider(ctrl, from_=0.0, to=2.0, command=self.update_interval_lbl)
        self.interval_slider.set(0.1)
        self.interval_slider.grid(row=8, column=0, columnspan=2, padx=10, pady=(0, 6), sticky="ew")

        self.lbl_scroll = ctk.CTkLabel(ctrl, text="Scroll after click: 0")
        self.lbl_scroll.grid(row=9, column=0, columnspan=2, padx=10, pady=(6, 0), sticky="w")
        self.scroll_slider = ctk.CTkSlider(ctrl, from_=-1000, to=1000, command=self.update_scroll_lbl)
        self.scroll_slider.set(0)
        self.scroll_slider.grid(row=10, column=0, columnspan=2, padx=10, pady=(0, 6), sticky="ew")

        # ── Profile Buttons ───────────────────────────────────────────
        pf = ctk.CTkFrame(self, fg_color="transparent")
        pf.grid(row=3, column=0, padx=10, pady=3, sticky="ew")
        pf.grid_columnconfigure(0, weight=1)
        pf.grid_columnconfigure(1, weight=1)
        ctk.CTkButton(pf, text="💾 Save Profile", fg_color="#0052cc", hover_color="#003d99",
                      command=self.save_profile).grid(row=0, column=0, padx=(0, 3), sticky="ew")
        ctk.CTkButton(pf, text="📂 Load Profile", fg_color="#0052cc", hover_color="#003d99",
                      command=self.load_profile).grid(row=0, column=1, padx=(3, 0), sticky="ew")

        # ── Hotkeys / Start / Status ──────────────────────────────────
        ctk.CTkLabel(
            self, text="[Ctrl+Shift+P] Start  |  [Ctrl+Shift+Q] Stop",
            font=("Arial", 12, "bold")
        ).grid(row=4, column=0, pady=5)

        self.btn_start = ctk.CTkButton(
            self, text="▶ Start [Ctrl+Shift+P]",
            fg_color="green", hover_color="darkgreen", height=40,
            command=self.toggle_start
        )
        self.btn_start.grid(row=5, column=0, padx=10, pady=5, sticky="ew")

        self.lbl_status = ctk.CTkLabel(self, text="Status: Ready", text_color="gray")
        self.lbl_status.grid(row=6, column=0, padx=10, pady=(3, 10))

        keyboard.add_hotkey("ctrl+shift+p", lambda: self.after(0, self.start_auto))
        keyboard.add_hotkey("ctrl+shift+q", lambda: self.after(0, self.stop_auto))

        self.load_target_images()
        self.rebuild_steps_ui()

    # ── Slider callbacks ──────────────────────────────────────────────
    def update_conf_lbl(self, value):
        self.lbl_conf.configure(text=f"Confidence: {int(value * 100)}%")

    def update_min_conf_lbl(self, value):
        self.lbl_min_conf.configure(text=f"Min Confidence (fallback): {int(value * 100)}%")

    def update_delay_lbl(self, value):
        self.lbl_delay.configure(text=f"Delay after click: {value:.1f}s")

    def update_interval_lbl(self, value):
        self.lbl_interval.configure(text=f"Check interval: {value:.2f}s")

    def update_scroll_lbl(self, value):
        self.lbl_scroll.configure(text=f"Scroll after click: {int(value)}")

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
        """Rename on-disk files to match current step indices after a delete."""
        for step_idx, step in enumerate(self.steps):
            for img in step:
                old_path = getattr(img, 'filepath', None)
                if not old_path or not os.path.exists(old_path):
                    continue
                fname = os.path.basename(old_path)
                m = re.match(r'^s(\d+)_(\d+)\.png$', fname)
                if m and int(m.group(1)) != step_idx:
                    new_fname = f"s{step_idx:02d}_{m.group(2)}.png"
                    new_path = os.path.join(self.targets_dir, new_fname)
                    try:
                        os.rename(old_path, new_path)
                        img.filepath = new_path
                    except Exception:
                        pass

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
            ctk.CTkButton(hdr, text="📸 Capture", width=85, height=26,
                          command=lambda i=step_idx: self.start_capture(i)).grid(row=0, column=1, padx=3)
            ctk.CTkButton(hdr, text="🗑️", width=32, height=26,
                          fg_color="red", hover_color="darkred",
                          command=lambda i=step_idx: self.delete_step(i)).grid(row=0, column=2, padx=(0, 5))

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
                self.lbl_status.configure(text=f"Loaded: {os.path.basename(filepath)}", text_color="green")
            except Exception as e:
                self.lbl_status.configure(text=f"Load error: {e}", text_color="red")

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
        # Removing iconify to keep the window visible on the left side
        self.worker_thread = threading.Thread(target=self.auto_loop, daemon=True)
        self.worker_thread.start()

    def stop_auto(self):
        if not self.running:
            return
        self.running = False
        self.btn_start.configure(text="▶ Start [Ctrl+Shift+P]", fg_color="green", hover_color="darkgreen")
        self.lbl_status.configure(text="Status: Stopped", text_color="gray")
        self.title("Auto Image Clicker - Hierarchical")
        # Removed deiconify since it's no longer minimized during play

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
            except Exception:
                time.sleep(0.1)
                continue

            time.sleep(interval)

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

                            if scroll_amt != 0:
                                pyautogui.scroll(scroll_amt)

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


if __name__ == "__main__":
    app = AutoClickerApp()
    app.mainloop()
