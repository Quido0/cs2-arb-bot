"""
Запусти: python build.py
Результат: dist/CS2ArbBot.exe  (один файл, без установки)
"""
import subprocess
import sys
import os

def main():
    # Убеждаемся что PyInstaller установлен
    subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller", "-q"])

    icon = "icon.ico" if os.path.exists("icon.ico") else None

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--windowed",               # без консоли (GUI-приложение)
        "--name", "CS2ArbBot",
        "--add-data", "apis;apis",  # включаем подпапку apis
        "--clean",
    ]
    if icon:
        cmd += ["--icon", icon]

    cmd.append("gui.py")

    print("Собираем CS2ArbBot.exe ...")
    subprocess.check_call(cmd)
    print("\nГотово: dist/CS2ArbBot.exe")


if __name__ == "__main__":
    main()
