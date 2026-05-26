import os
import sys
import subprocess

def run_build():
    print("PCM (PC Mover) Standalone EXE Build Tool")
    print("=========================================")

    try:
        import customtkinter
    except ImportError:
        print("Error: customtkinter is not installed. Please run 'pip install -r requirements.txt' first.")
        sys.exit(1)

    try:
        import cryptography
    except ImportError:
        print("Error: cryptography is not installed. Please run 'pip install -r requirements.txt' first.")
        sys.exit(1)

    # Find customtkinter location to bundle assets
    ctk_path = os.path.dirname(customtkinter.__file__)
    print(f"Bundling CustomTkinter assets from: {ctk_path}")

    # Build command arguments
    # --onefile: single standalone EXE
    # --noconsole: hide the command window when launching GUI
    # --uac-admin: elevate execution level on Windows
    # --add-data: bundle customtkinter internal theme files
    # Syntax for Windows is: "path;customtkinter"
    add_data_arg = f"{ctk_path}{os.pathsep}customtkinter"
    
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--onefile",
        "--noconsole",
        "--uac-admin",
        "--name=PCM",
        f"--add-data={add_data_arg}",
        "main.py"
    ]

    print("Running command:")
    print(" ".join(cmd))
    print("\nStarting compilation (this may take a minute)...")
    
    try:
        result = subprocess.run(cmd, capture_output=False, text=True)
        if result.returncode == 0:
            print("\n=========================================")
            print("SUCCESS: Standalone executable created!")
            print(f"Check the 'dist' folder: {os.path.abspath('dist/PCM.exe')}")
            print("=========================================")
        else:
            print(f"\nBuild failed with code: {result.returncode}")
    except Exception as e:
        print(f"Error executing PyInstaller: {e}")

if __name__ == "__main__":
    run_build()
