"""
Run: python build.py
Output: dist/CS2ArbBot.exe  (single file, no installation required)
"""
import subprocess
import sys
import os

def main():
    # Ensure PyInstaller is installed
    subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller", "-q"])

    icon = "icon.ico" if os.path.exists("icon.ico") else None

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--windowed",               # no console window (GUI app)
        "--name", "CS2ArbBot",
        "--add-data", "apis;apis",  # include apis subfolder
        "--clean",
    ]
    if icon:
        cmd += ["--icon", icon]

    cmd.append("gui.py")

    print("Building CS2ArbBot.exe ...")
    subprocess.check_call(cmd)
    print("\nDone: dist/CS2ArbBot.exe")


if __name__ == "__main__":
    main()
