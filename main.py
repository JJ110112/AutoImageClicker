import customtkinter as ctk
import pyautogui
import keyboard
import threading
import time
import os
from PIL import Image
import zipfile
import typing

# Initialize GUI theme
ctk.set_appearance_mode("System")
ctk.set_default_color_theme("blue")

class SnippingOverlay(ctk.CTkToplevel):
    def __init__(self, parent, callback):
        super().__init__(parent)  # type: ignore
        self.callback = callback
        
        # Create a transparent full-screen overlay window
        self.attributes('-fullscreen', True)
        self.attributes('-alpha', 0.3)
        self.attributes('-topmost', True)
        self.overrideredirect(True)
        self.config(cursor="cross")
        
        self.canvas = ctk.CTkCanvas(self, bg='black', highlightthickness=0)
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
        self.rect = self.canvas.create_rectangle(self.start_x, self.start_y, self.start_x, self.start_y, outline='red', width=2, fill='')

    def on_drag(self, event):
        self.canvas.coords(self.rect, self.start_x, self.start_y, event.x, event.y)

    def on_release(self, event):
        x1 = min(self.start_x, event.x)
        y1 = min(self.start_y, event.y)
        x2 = max(self.start_x, event.x)
        y2 = max(self.start_y, event.y)
        
        self.destroy()
        if x2 - x1 > 5 and y2 - y1 > 5:
            # Short delay to allow overlay to close before capturing under it
            self.after(200, lambda: self.capture_region(x1, y1, x2 - x1, y2 - y1))

    def capture_region(self, x, y, w, h):
        img = pyautogui.screenshot(region=(x, y, w, h))
        self.callback(img)


class AutoClickerApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Auto Image Clicker - Multi Targets")
        
        self.update_idletasks() # Ensure dimensions are available
        window_width = 450
        window_height = 680
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        pos_x = 20
        pos_y = screen_height - window_height - 60
        
        self.geometry(f"{window_width}x{window_height}+{pos_x}+{pos_y}")
        
        self.targets_dir = "targets"
        os.makedirs(self.targets_dir, exist_ok=True)
        self.target_images = []
        self.running = False
        self.worker_thread: typing.Any = None
        
        self.grid_columnconfigure(0, weight=1)
        
        # --- UI LAYOUT ---
        # Preview Box (Scrollable)
        self.preview_frame = ctk.CTkScrollableFrame(self, height=150, orientation="horizontal")
        self.preview_frame.grid(row=0, column=0, padx=20, pady=20, sticky="ew")
        
        # Capture & Clear Buttons & Profile Buttons
        self.frame_capture = ctk.CTkFrame(self, fg_color="transparent")
        self.frame_capture.grid(row=1, column=0, padx=20, pady=5, sticky="ew")
        self.frame_capture.grid_columnconfigure(0, weight=1)
        self.frame_capture.grid_columnconfigure(1, weight=1)
        self.frame_capture.grid_columnconfigure(2, weight=1)
        self.frame_capture.grid_columnconfigure(3, weight=1)
        
        self.btn_capture = ctk.CTkButton(self.frame_capture, text="📸 Capture", width=60, command=self.start_capture)
        self.btn_capture.grid(row=0, column=0, padx=(0, 2), sticky="ew")
        
        self.btn_clear = ctk.CTkButton(self.frame_capture, text="🗑️ Clear", width=60, fg_color="red", hover_color="darkred", command=self.clear_targets)
        self.btn_clear.grid(row=0, column=1, padx=(2, 2), sticky="ew")
        
        self.btn_save = ctk.CTkButton(self.frame_capture, text="💾 Save", width=60, fg_color="#0052cc", hover_color="#003d99", command=self.save_profile)
        self.btn_save.grid(row=0, column=2, padx=(2, 2), sticky="ew")
        
        self.btn_load = ctk.CTkButton(self.frame_capture, text="📂 Load", width=60, fg_color="#0052cc", hover_color="#003d99", command=self.load_profile)
        self.btn_load.grid(row=0, column=3, padx=(2, 0), sticky="ew")
        
        # Action Options
        self.frame_action = ctk.CTkFrame(self)
        self.frame_action.grid(row=2, column=0, padx=20, pady=10, sticky="ew")
        self.frame_action.grid_columnconfigure(1, weight=1)
        
        ctk.CTkLabel(self.frame_action, text="Action:").grid(row=0, column=0, padx=10, pady=10, sticky="w")
        self.action_var = ctk.StringVar(value="Left Click")
        self.action_menu = ctk.CTkOptionMenu(self.frame_action, values=["Left Click", "Right Click", "Double Click", "Move Only"], variable=self.action_var)
        self.action_menu.grid(row=0, column=1, padx=10, pady=10, sticky="ew")
        
        # Confidence Settings (Advanced)
        self.frame_conf = ctk.CTkFrame(self)
        self.frame_conf.grid(row=3, column=0, padx=20, pady=10, sticky="ew")
        self.frame_conf.grid_columnconfigure(1, weight=1)
        
        self.lbl_conf = ctk.CTkLabel(self.frame_conf, text="Confidence: 80%")
        self.lbl_conf.grid(row=0, column=0, padx=10, pady=10)
        
        self.conf_slider = ctk.CTkSlider(self.frame_conf, from_=0.1, to=1.0, command=self.update_conf_lbl)
        self.conf_slider.set(0.8)
        self.conf_slider.grid(row=0, column=1, padx=10, pady=10, sticky="ew")
        
        # Delay Settings
        self.frame_delay = ctk.CTkFrame(self)
        self.frame_delay.grid(row=4, column=0, padx=20, pady=10, sticky="ew")
        self.frame_delay.grid_columnconfigure(1, weight=1)
        
        self.lbl_delay = ctk.CTkLabel(self.frame_delay, text="Delay: 0.5s")
        self.lbl_delay.grid(row=0, column=0, padx=10, pady=10)
        
        self.delay_slider = ctk.CTkSlider(self.frame_delay, from_=0.0, to=5.0, command=self.update_delay_lbl)
        self.delay_slider.set(0.5)
        self.delay_slider.grid(row=0, column=1, padx=10, pady=10, sticky="ew")
        
        # Top level Info
        self.lbl_hotkeys = ctk.CTkLabel(self, text="Hotkeys: [Ctrl+Shift+P] Start  |  [Ctrl+Shift+Q] Stop", font=("Arial", 14, "bold"))
        self.lbl_hotkeys.grid(row=5, column=0, padx=20, pady=10)
        
        # Controls Group
        self.frame_ctrl = ctk.CTkFrame(self, fg_color="transparent")
        self.frame_ctrl.grid(row=6, column=0, padx=20, pady=10, sticky="ew")
        self.frame_ctrl.grid_columnconfigure(0, weight=1)
        self.frame_ctrl.grid_columnconfigure(1, weight=1)
        
        self.btn_test = ctk.CTkButton(self.frame_ctrl, text="Test Match Once", fg_color="gray", command=self.test_match)
        self.btn_test.grid(row=0, column=0, padx=(0, 5), sticky="ew")
        
        self.btn_start = ctk.CTkButton(self.frame_ctrl, text="Start [Ctrl+Shift+P]", fg_color="green", hover_color="darkgreen", command=self.toggle_start)
        self.btn_start.grid(row=0, column=1, padx=(5, 0), sticky="ew")
        
        # Status footer
        self.lbl_status = ctk.CTkLabel(self, text="Status: Ready", text_color="gray")
        self.lbl_status.grid(row=7, column=0, padx=20, pady=10, sticky="ew")
        
        # Global hotkey binding
        keyboard.add_hotkey("ctrl+shift+p", lambda: self.trigger_start_hotkey())
        keyboard.add_hotkey("ctrl+shift+q", lambda: self.trigger_stop_hotkey())
        
        # Load saved images on startup
        self.load_target_images()

    def update_delay_lbl(self, value):
        self.lbl_delay.configure(text=f"Delay: {value:.1f}s")

    def update_conf_lbl(self, value):
        self.lbl_conf.configure(text=f"Confidence: {int(value * 100)}%")

    def start_capture(self):
        # Hide the main window down to taskbar
        self.iconify()
        # Give Windows a split second to finish animating the minimize
        self.after(300, lambda: SnippingOverlay(self, self.on_capture_done))

    def load_target_images(self):
        self.target_images = []
        try:
            for filename in os.listdir(self.targets_dir):
                if filename.endswith(".png"):
                    path = os.path.join(self.targets_dir, filename)
                    with Image.open(path) as img:
                        img_copy = img.copy()  # type: ignore
                        img_copy.filepath = path  # type: ignore
                        self.target_images.append(img_copy)
        except Exception as e:
            print("Error loading saved images:", e)
        self.after(200, self.update_preview)

    def clear_targets(self):
        self.target_images = []
        try:
            for filename in os.listdir(self.targets_dir):
                if filename.endswith(".png"):
                    os.remove(os.path.join(self.targets_dir, filename))
        except Exception as e:
            print("Error clearing images:", e)
        self.update_preview()

    def delete_target(self, index):
        if 0 <= index < len(self.target_images):
            img = self.target_images.pop(index)
            path = getattr(img, 'filepath', None)
            
            if path and os.path.exists(path):
                try:
                    os.remove(path)
                except Exception as e:
                    print(f"Error deleting file {path}:", e)
                    
            self.update_preview()

    def update_preview(self):
        for widget in self.preview_frame.winfo_children():
            widget.destroy()
            
        if not self.target_images:
            lbl = ctk.CTkLabel(self.preview_frame, text="Click 'Capture Target' to pick images\n(Multiple targets supported)")
            lbl.pack(expand=True, fill="both", padx=20, pady=50)
            return
            
        for idx in range(len(self.target_images)):
            img = self.target_images[idx]
            preview = img.copy()  # type: ignore
            if preview.height > 100:
                calc_width = int(preview.width * (100 / preview.height))
                preview.thumbnail((calc_width, 100))
            
            ctk_img = ctk.CTkImage(light_image=preview, dark_image=preview, size=preview.size)
            
            frame = ctk.CTkFrame(self.preview_frame, fg_color="transparent")
            frame.pack(side="left", padx=5, pady=5)
            
            lbl = ctk.CTkLabel(frame, image=ctk_img, text=f" #{idx+1}  ", compound="bottom")
            lbl.image = ctk_img
            lbl.grid(row=0, column=0)
            
            btn_del = ctk.CTkButton(frame, text="X", width=20, height=20, font=("Arial", 12, "bold"),
                                    fg_color="red", hover_color="darkred", corner_radius=10,
                                    command=lambda i=idx: self.delete_target(i))
            btn_del.place(relx=1.0, rely=0.0, anchor="ne", x=-2, y=2)

    def save_profile(self):
        if not self.target_images:
            self.lbl_status.configure(text="No targets to save.", text_color="red")
            return
        filepath = ctk.filedialog.asksaveasfilename(defaultextension=".zip", filetypes=[("Scenario Zip", "*.zip")], title="Save Scenario")
        if filepath:
            try:
                with zipfile.ZipFile(filepath, 'w') as zf:
                    for filename in os.listdir(self.targets_dir):
                        if filename.endswith(".png"):
                            zf.write(os.path.join(self.targets_dir, filename), filename)
                self.lbl_status.configure(text=f"Saved to {os.path.basename(filepath)}", text_color="green")
            except Exception as e:
                self.lbl_status.configure(text=f"Save error: {e}", text_color="red")

    def load_profile(self):
        filepath = ctk.filedialog.askopenfilename(filetypes=[("Scenario Zip", "*.zip")], title="Load Scenario")
        if filepath:
            try:
                self.clear_targets()
                with zipfile.ZipFile(filepath, 'r') as zf:
                    zf.extractall(self.targets_dir)
                self.load_target_images()
                self.lbl_status.configure(text=f"Loaded {os.path.basename(filepath)}", text_color="green")
            except Exception as e:
                self.lbl_status.configure(text=f"Load error: {e}", text_color="red")

    def on_capture_done(self, img):
        # Restore window
        self.deiconify()
        
        try:
            filename = f"target_{int(time.time() * 1000)}.png"
            path = os.path.join(self.targets_dir, filename)
            img.save(path)
            img.filepath = path
        except Exception as e:
            print("Error saving image:", e)
            img.filepath = None
            
        self.target_images.append(img)
        self.update_preview()

    def test_match(self):
        if not self.target_images:
            self.lbl_status.configure(text="Please capture at least one target image.", text_color="red")
            return
            
        conf = float(self.conf_slider.get())
        found = False
        try:
            for img in self.target_images:
                loc = pyautogui.locateOnScreen(img, confidence=conf)
                if loc:
                    center = pyautogui.center(loc)
                    pyautogui.moveTo(center.x, center.y, duration=0.2)
                    self.lbl_status.configure(text=f"Found match at X:{center.x} Y:{center.y}", text_color="green")
                    found = True
                    break
                    
            if not found:
                self.lbl_status.configure(text="No targets found on current screen.", text_color="orange")
        except getattr(pyautogui, 'ImageNotFoundException', Exception): # Fallback if library version differs
             self.lbl_status.configure(text="No targets found on current screen.", text_color="orange")
        except Exception as e:
             self.lbl_status.configure(text=f"Error matching: {str(e)}", text_color="red")

    def toggle_start(self):
        if self.running:
            self.stop_auto()
        else:
            self.start_auto()

    def trigger_start_hotkey(self):
        # Safely call from background thread to UI thread
        self.after(0, self.start_auto)
        
    def trigger_stop_hotkey(self):
        self.after(0, self.stop_auto)

    def start_auto(self):
        if self.running:
            return
        if not self.target_images:
            self.lbl_status.configure(text="Please capture at least one image before starting.", text_color="red")
            return
            
        self.running = True
        self.btn_start.configure(text="Stop [Ctrl+Shift+Q]", fg_color="red", hover_color="darkred")
        self.lbl_status.configure(text="Status: RUNNING", text_color="green")
        
        self.iconify()
        
        self.worker_thread = threading.Thread(target=self.auto_loop, daemon=True)
        self.worker_thread.start()

    def stop_auto(self):
        if not self.running:
            return
            
        self.running = False
        self.btn_start.configure(text="Start [Ctrl+Shift+P]", fg_color="green", hover_color="darkgreen")
        self.lbl_status.configure(text="Status: Stopped", text_color="gray")
        
        self.deiconify()

    def auto_loop(self):
        while self.running:
            try:
                # Add a sleep interval to protect CPU
                time.sleep(0.1)
                
                conf = float(self.conf_slider.get())
                action = self.action_var.get()
                delay = float(self.delay_slider.get())
                
                for img in self.target_images:
                    loc = pyautogui.locateOnScreen(img, confidence=conf)
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
                        
                        # Update status safely on main thread
                        self.after(0, lambda cx=center.x, cy=center.y: self.lbl_status.configure(text=f"Match at X:{cx} Y:{cy}", text_color="green"))
                        
                        # Prevent instant repeated clicking
                        time.sleep(delay)
                        break  # Successfully acted, loop from start again
            except getattr(pyautogui, 'ImageNotFoundException', Exception):
                pass
            except Exception as e:
                print("Error in auto_loop:", e)

if __name__ == "__main__":
    app = AutoClickerApp()
    app.mainloop()
