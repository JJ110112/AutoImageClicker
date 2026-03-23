# Auto Image Clicker

A powerful, customizable multi-target image auto-clicker built with Python and CustomTkinter.

## Features
- **Multi-Target Detection**: Capture multiple images and search for any of them on the screen simultaneously.
- **Dynamic Action**: Choose from standard clicks (Left, Right, Double) or Move Only.
- **Save/Load Scenarios**: Export your captured target images into a Zip profile to save scenarios for later.
- **Advanced Options**: Tweak image match confidence thresholds and set specific delay times between clicks.
- **Global Hotkeys**: Control the clicker globally using `Ctrl+Shift+P` (Start) and `Ctrl+Shift+Q` (Stop).
- **Auto Minimum Mode**: Automatically minimizes itself below foreground windows to avoid obscuring your target areas, with automatic restore when stopped.

## Installation
If you have Python installed:
1. Clone this repository.
2. Install dependencies:
   `pip install customtkinter pyautogui keyboard pillow opencv-python Pillow`
3. Run `python main.py` or build the executable:
   `pyinstaller --clean --noconfirm --onefile --windowed --name AutoImageClicker main.py`

## Usage
1. Click **📸 Capture** to snippet part of your screen that you want to target.
2. Repeat for as many targets as you need.
3. Configure Action, Confidence, and Delay to match your use case.
4. When ready, press `Ctrl+Shift+P` to start the automatic loop in the background. Press `Ctrl+Shift+Q` to stop.
5. If you want to switch tasks, click **💾 Save** to save the targets as a `.zip` file, and **📂 Load** to load them whenever you need them again.
