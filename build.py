import os
import subprocess
import sys

# Ensure pyinstaller is installed
try:
    import PyInstaller
except ImportError:
    subprocess.run([sys.executable, "-m", "pip", "install", "pyinstaller"])

# Find customtkinter path to include its theme files correctly
try:
    import customtkinter
    ctk_path = os.path.dirname(customtkinter.__file__)
    add_data_arg = f"--add-data={ctk_path};customtkinter/"
except ImportError:
    add_data_arg = ""

print("Building executable with PyInstaller...")

# We use subprocess.run directly with python -m PyInstaller to avoid PATH issues
cmd = [
    sys.executable, "-m", "PyInstaller",
    "--noconsole",
    "--onefile",
    "--icon", "app_icon.ico",
    "--name", "AutoImageClicker",
    "main.py"
]
if add_data_arg:
    cmd.insert(-1, add_data_arg)

subprocess.run(cmd)
print("Build complete! Check the 'dist' folder.")
